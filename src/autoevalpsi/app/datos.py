"""AP-R0: capa de datos local — SQLite + imágenes en disco.

Todo vive bajo una **raíz** (`%LOCALAPPDATA%\\AutoEvalPsi` por defecto; configurable con el
argumento o con `AUTOEVALPSI_HOME`):

    autoevalpsi.db                         la base
    fotos/<evaluación>/<página>.jpg|png    las fotos recibidas
    recortes/<evaluación>/...png           recortes de observaciones y de cabecera

Las rutas guardadas en la base son **relativas a la raíz** (la carpeta se puede mover).

**Contrato (esquema de BD, versión 2).** Se versiona con `PRAGMA user_version`; una base de una
versión posterior a `VERSION_ESQUEMA` se rechaza sin tocarla. Tablas: `evaluaciones`, `paginas`,
`filas`, `correcciones` (AP-05: el piloto la lee), `configuracion` y, desde la v2 (AP-D2),
`dispositivos` (el único celular vinculado: solo la huella SHA-256 de su credencial). Para cambiar el esquema se
agrega una migración al final de `_MIGRACIONES` y no se edita ninguna anterior.

Lo **leído** (`opcion_leida`, `texto_ocr`) nunca se pisa; lo que la persona confirma va en
`opcion` y `observacion`, y cada cambio respecto del valor confirmado anterior deja una fila en
`correcciones`. «Revisada» es una decisión de la persona: las filas verdes nacen revisadas, las
amarillas no, y la revisión obligatoria antes de exportar (AP-06) la impone el servidor con
`filas_pendientes` y `cabecera_revisada`.

Una sola conexión compartida entre hilos (el trabajador de la cola y las peticiones, AP-04),
serializada con un candado.
"""

import json
import os
import re
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Self

import cv2
import numpy as np

from autoevalpsi.core.excel import Evaluacion, FilaEvaluacion
from autoevalpsi.core.pipeline import ResultadoProcesamiento, nombre_campo_cabecera
from autoevalpsi.core.plantilla import Plantilla
from autoevalpsi.core.tiempo import a_bolivia, ahora_bolivia

NOMBRE_BD = "autoevalpsi.db"

_MIGRACIONES: tuple[tuple[str, ...], ...] = (
    # v1
    (
        """CREATE TABLE configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )""",
        """CREATE TABLE evaluaciones (
            id TEXT PRIMARY KEY,
            plantilla_id TEXT NOT NULL,
            plantilla_version INTEGER NOT NULL,
            paciente TEXT NOT NULL DEFAULT '',
            fecha TEXT NOT NULL,
            cabecera TEXT NOT NULL DEFAULT '{}',
            recortes_cabecera TEXT NOT NULL DEFAULT '{}',
            cabecera_revisada INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (estado IN ('pendiente', 'revisada', 'exportada')),
            creada_en TEXT NOT NULL,
            actualizada_en TEXT NOT NULL
        )""",
        """CREATE TABLE paginas (
            evaluacion_id TEXT NOT NULL REFERENCES evaluaciones(id) ON DELETE CASCADE,
            pagina INTEGER NOT NULL,
            foto_sha256 TEXT NOT NULL,
            foto_ruta TEXT,
            problemas_calidad TEXT NOT NULL DEFAULT '[]',
            registro TEXT NOT NULL DEFAULT '{}',
            ocr_activo INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (evaluacion_id, pagina)
        )""",
        """CREATE TABLE filas (
            evaluacion_id TEXT NOT NULL REFERENCES evaluaciones(id) ON DELETE CASCADE,
            item INTEGER NOT NULL,
            pagina INTEGER NOT NULL,
            opcion_leida TEXT,
            opcion TEXT,
            banderas TEXT NOT NULL DEFAULT '[]',
            texto_ocr TEXT NOT NULL DEFAULT '',
            observacion TEXT NOT NULL DEFAULT '',
            ruta_recorte TEXT,
            revisada INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (evaluacion_id, item)
        )""",
        """CREATE TABLE correcciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluacion_id TEXT NOT NULL REFERENCES evaluaciones(id) ON DELETE CASCADE,
            item INTEGER,
            campo TEXT NOT NULL,
            antes TEXT,
            despues TEXT,
            momento TEXT NOT NULL
        )""",
        "CREATE INDEX correcciones_evaluacion ON correcciones(evaluacion_id)",
    ),
    # v2 (AP-D2): un solo celular vinculado, reemplazable; `id = 1` lo impone el esquema
    (
        """CREATE TABLE dispositivos (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            huella TEXT NOT NULL,
            creado TEXT NOT NULL,
            ultimo_uso TEXT
        )""",
    ),
)
VERSION_ESQUEMA = len(_MIGRACIONES)

ESTADOS = ("pendiente", "revisada", "exportada")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SIN = object()  # «no se pasó»: distinto de None, que para la opción significa «sin respuesta»


class BaseDatosNueva(Exception):
    """La base la creó una versión más nueva de la app."""


class EvaluacionInexistente(LookupError):
    pass


class IdInvalido(ValueError):
    pass


def raiz_por_defecto() -> Path:
    if home := os.environ.get("AUTOEVALPSI_HOME"):
        return Path(home)
    if local := os.environ.get("LOCALAPPDATA"):
        return Path(local) / "AutoEvalPsi"
    return Path.home() / ".local" / "share" / "AutoEvalPsi"


@dataclass(frozen=True)
class PaginaGuardada:
    pagina: int
    foto_sha256: str
    foto_ruta: str | None  # None: la foto se borró (AP-D1)
    problemas_calidad: tuple[str, ...]
    registro: dict
    ocr_activo: bool


@dataclass(frozen=True)
class FilaGuardada:
    item: int
    pagina: int
    opcion_leida: str | None
    opcion: str | None  # la confirmada; al nacer, igual a la leída
    banderas: tuple[str, ...]
    texto_ocr: str
    observacion: str
    ruta_recorte: str | None
    revisada: bool


@dataclass(frozen=True)
class EvaluacionGuardada:
    id: str
    plantilla_id: str
    plantilla_version: int
    paciente: str
    fecha: str  # ISO
    cabecera: dict[str, str]  # campos distintos de «paciente», con el nombre leído (p. ej. «fecha»)
    recortes_cabecera: dict[str, str]
    cabecera_revisada: bool
    estado: str
    creada_en: str
    actualizada_en: str
    paginas: tuple[PaginaGuardada, ...]
    filas: tuple[FilaGuardada, ...]


@dataclass(frozen=True)
class ResumenEvaluacion:
    id: str
    plantilla_id: str
    paciente: str
    fecha: str
    estado: str
    creada_en: str
    n_filas: int
    filas_pendientes: int


@dataclass(frozen=True)
class Correccion:
    id: int
    evaluacion_id: str
    item: int | None  # None: cabecera
    campo: str  # «opcion», «observacion», «paciente» o «cabecera.<campo>»
    antes: str | None
    despues: str | None
    momento: str


@dataclass(frozen=True)
class Dispositivo:
    huella: str  # SHA-256 (hex) de la credencial; la credencial en sí no se guarda
    creado: str
    ultimo_uso: str | None


def validar_id(id: str) -> str:
    if not _ID.fullmatch(id):
        raise IdInvalido(f"id de evaluación no válido: {id!r} (letras, números, «-» y «_»)")
    return id


def _extension(datos: bytes) -> str:
    if datos.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if datos.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    raise ValueError("la foto no es JPEG ni PNG")


def _png(recorte: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", recorte)
    if not ok:
        raise ValueError("no se pudo codificar el recorte")
    return buf.tobytes()


def _nombre_seguro(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", texto) or "_"


class BaseDatos:
    """Base local de una raíz. Úsese como gestor de contexto o llamando a `cerrar()`."""

    def __init__(
        self,
        raiz: str | Path | None = None,
        *,
        ahora: Callable[[], datetime] | None = None,
    ) -> None:
        self.raiz = Path(raiz) if raiz is not None else raiz_por_defecto()
        self._ahora = ahora or ahora_bolivia  # hora de Bolivia (UTC−4), no UTC
        self.raiz.mkdir(parents=True, exist_ok=True)
        self._candado = threading.RLock()
        self._con = sqlite3.connect(
            self.raiz / NOMBRE_BD, check_same_thread=False, isolation_level=None
        )
        self._con.row_factory = sqlite3.Row
        try:
            self._con.execute("PRAGMA foreign_keys = ON")
            self._migrar()
        except BaseException:
            self._con.close()
            raise

    # --- ciclo de vida ------------------------------------------------------------------

    def cerrar(self) -> None:
        with self._candado:
            self._con.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc) -> None:
        self.cerrar()

    @property
    def version(self) -> int:
        with self._candado:
            return self._con.execute("PRAGMA user_version").fetchone()[0]

    def _migrar(self) -> None:
        actual = self.version
        if actual > VERSION_ESQUEMA:
            raise BaseDatosNueva(
                f"La base de datos es de una versión más nueva ({actual}) que esta app "
                f"({VERSION_ESQUEMA}). Actualiza AutoEvalPsi."
            )
        for destino in range(actual + 1, VERSION_ESQUEMA + 1):
            with self._tx():
                for sentencia in _MIGRACIONES[destino - 1]:
                    self._con.execute(sentencia)
                self._con.execute(f"PRAGMA user_version = {destino}")

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._candado:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                yield self._con
            except BaseException:
                self._con.execute("ROLLBACK")
                raise
            self._con.execute("COMMIT")

    def _momento(self) -> str:
        return a_bolivia(self._ahora()).isoformat(timespec="seconds")

    # --- configuración ------------------------------------------------------------------

    def leer_configuracion(self, clave: str, defecto: str | None = None) -> str | None:
        with self._candado:
            r = self._con.execute(
                "SELECT valor FROM configuracion WHERE clave = ?", (clave,)
            ).fetchone()
        return r["valor"] if r else defecto

    def guardar_configuracion(self, clave: str, valor: str) -> None:
        with self._tx() as con:
            con.execute(
                "INSERT INTO configuracion(clave, valor) VALUES (?, ?)"
                " ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )

    # --- celular vinculado (AP-D2) -------------------------------------------------------

    def guardar_dispositivo(self, huella: str) -> None:
        """Vincula un celular; si había otro, lo reemplaza (el anterior deja de servir)."""
        with self._tx() as con:
            con.execute(
                "INSERT INTO dispositivos(id, huella, creado, ultimo_uso) VALUES (1, ?, ?, NULL)"
                " ON CONFLICT(id) DO UPDATE SET huella = excluded.huella,"
                " creado = excluded.creado, ultimo_uso = NULL",
                (huella, self._momento()),
            )

    def leer_dispositivo(self) -> Dispositivo | None:
        with self._candado:
            r = self._con.execute(
                "SELECT huella, creado, ultimo_uso FROM dispositivos WHERE id = 1"
            ).fetchone()
        return Dispositivo(r["huella"], r["creado"], r["ultimo_uso"]) if r else None

    def registrar_uso_dispositivo(self, huella: str) -> None:
        with self._tx() as con:
            con.execute(
                "UPDATE dispositivos SET ultimo_uso = ? WHERE id = 1 AND huella = ?",
                (self._momento(), huella),
            )

    def borrar_dispositivo(self) -> bool:
        with self._tx() as con:
            return con.execute("DELETE FROM dispositivos WHERE id = 1").rowcount > 0

    # --- escritura ----------------------------------------------------------------------

    def guardar_procesamiento(
        self,
        resultado: ResultadoProcesamiento,
        *,
        foto: bytes,
        recortes: dict[int, np.ndarray] | None = None,
        recortes_cabecera: dict[str, np.ndarray] | None = None,
        evaluacion_id: str | None = None,
        paciente: str = "",
        fecha: date | None = None,
    ) -> str:
        """Guarda la lectura de una página (y sus imágenes); devuelve el id de la evaluación.

        Sin `evaluacion_id` se crea una evaluación nueva con id derivado de la foto (SHA-256, igual
        que `core.pipeline.a_evaluacion`): subir dos veces la misma foto da `ValueError`, no un
        duplicado. Con un `evaluacion_id` existente se agrega la página siguiente (PL-03); con uno
        inexistente se crea con ese id. `paciente` pasado a mano manda sobre el leído.
        """
        recortes = recortes or {}
        recortes_cabecera = recortes_cabecera or {}
        ext = _extension(foto)
        id = validar_id(evaluacion_id if evaluacion_id is not None else resultado.foto_sha256[:12])
        leidos = {c.campo: c for c in resultado.cabecera}
        paciente_leido = leidos["paciente"].texto if "paciente" in leidos else ""
        cabecera_leida = {
            c.campo: c.texto for c in resultado.cabecera if c.campo != "paciente" and c.texto
        }
        cabecera_ok = all(c.ok for c in resultado.cabecera)
        escritos: list[Path] = []
        try:
            with self._tx() as con:
                existe = con.execute("SELECT 1 FROM evaluaciones WHERE id = ?", (id,)).fetchone()
                if existe and evaluacion_id is None:
                    raise ValueError(f"la evaluación {id} ya existe (¿la misma foto otra vez?)")
                if (
                    existe
                    and con.execute(
                        "SELECT 1 FROM paginas WHERE evaluacion_id = ? AND pagina = ?",
                        (id, resultado.pagina),
                    ).fetchone()
                ):
                    raise ValueError(
                        f"la página {resultado.pagina} ya existe en la evaluación {id}"
                    )
                ahora = self._momento()

                def guardar_archivo(relativa: Path, datos: bytes) -> str:
                    destino = self.raiz / relativa
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(datos)
                    escritos.append(destino)
                    return relativa.as_posix()

                ruta_foto = guardar_archivo(Path("fotos") / id / f"{resultado.pagina}{ext}", foto)
                rutas_cab = {
                    campo: guardar_archivo(
                        Path("recortes") / id / f"cabecera_{_nombre_seguro(campo)}.png", _png(img)
                    )
                    for campo, img in recortes_cabecera.items()
                }
                if not existe:
                    con.execute(
                        "INSERT INTO evaluaciones(id, plantilla_id, plantilla_version, paciente,"
                        " fecha, cabecera, recortes_cabecera, cabecera_revisada, creada_en,"
                        " actualizada_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            id,
                            resultado.plantilla_id,
                            resultado.plantilla_version,
                            paciente or paciente_leido,
                            (fecha or a_bolivia(self._ahora()).date()).isoformat(),
                            json.dumps(cabecera_leida, ensure_ascii=False),
                            json.dumps(rutas_cab),
                            int(cabecera_ok),
                            ahora,
                            ahora,
                        ),
                    )
                else:
                    actual = con.execute(
                        "SELECT paciente, cabecera, recortes_cabecera, cabecera_revisada, "
                        "plantilla_id, plantilla_version FROM evaluaciones WHERE id = ?",
                        (id,),
                    ).fetchone()
                    if (actual["plantilla_id"], actual["plantilla_version"]) != (
                        resultado.plantilla_id,
                        resultado.plantilla_version,
                    ):
                        raise ValueError("la página es de otra plantilla que la evaluación")
                    cab = {**cabecera_leida, **json.loads(actual["cabecera"])}
                    rutas = {**rutas_cab, **json.loads(actual["recortes_cabecera"])}
                    con.execute(
                        "UPDATE evaluaciones SET paciente = ?, cabecera = ?, recortes_cabecera = ?,"
                        " cabecera_revisada = ?, actualizada_en = ? WHERE id = ?",
                        (
                            actual["paciente"] or paciente or paciente_leido,
                            json.dumps(cab, ensure_ascii=False),
                            json.dumps(rutas),
                            int(bool(actual["cabecera_revisada"]) and cabecera_ok),
                            ahora,
                            id,
                        ),
                    )
                con.execute(
                    "INSERT INTO paginas(evaluacion_id, pagina, foto_sha256, foto_ruta,"
                    " problemas_calidad, registro, ocr_activo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        id,
                        resultado.pagina,
                        resultado.foto_sha256,
                        ruta_foto,
                        json.dumps(list(resultado.problemas_calidad)),
                        json.dumps(resultado.registro),
                        int(resultado.ocr_activo),
                    ),
                )
                obs = {o.item: o for o in resultado.observaciones}
                for f in resultado.filas:
                    ruta_recorte = (
                        guardar_archivo(
                            Path("recortes") / id / f"item_{f.item}.png", _png(recortes[f.item])
                        )
                        if f.item in recortes
                        else None
                    )
                    texto = obs[f.item].texto if f.item in obs else ""
                    amarilla = f.item in resultado.items_amarillos
                    con.execute(
                        "INSERT INTO filas(evaluacion_id, item, pagina, opcion_leida, opcion,"
                        " banderas, texto_ocr, observacion, ruta_recorte, revisada)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            id,
                            f.item,
                            resultado.pagina,
                            f.opcion,
                            f.opcion,
                            json.dumps(
                                list(f.banderas)
                                + (list(obs[f.item].banderas) if f.item in obs else [])
                            ),
                            texto,
                            texto,
                            ruta_recorte,
                            int(not amarilla),
                        ),
                    )
                self._recalcular_estado(con, id, ahora)
        except BaseException:
            for archivo in escritos:
                archivo.unlink(missing_ok=True)
            raise
        return id

    def _recalcular_estado(self, con: sqlite3.Connection, id: str, ahora: str) -> None:
        r = con.execute(
            "SELECT cabecera_revisada, (SELECT COUNT(*) FROM filas WHERE evaluacion_id = e.id"
            " AND revisada = 0) AS pendientes FROM evaluaciones e WHERE id = ?",
            (id,),
        ).fetchone()
        estado = "revisada" if r["cabecera_revisada"] and r["pendientes"] == 0 else "pendiente"
        con.execute(
            "UPDATE evaluaciones SET estado = ?, actualizada_en = ? WHERE id = ?",
            (estado, ahora, id),
        )

    def _existe(self, con: sqlite3.Connection, id: str) -> None:
        if not con.execute("SELECT 1 FROM evaluaciones WHERE id = ?", (id,)).fetchone():
            raise EvaluacionInexistente(f"no existe la evaluación {id!r}")

    def actualizar_fila(
        self,
        evaluacion_id: str,
        item: int,
        *,
        opcion: str | None | object = _SIN,
        observacion: str | object = _SIN,
    ) -> None:
        """Confirma una fila, con o sin cambios. Cada valor que cambia deja una `corrección`.

        `opcion=None` es «sin respuesta» (válido); no pasar `opcion` la deja como está. Tocar la
        fila la marca revisada aunque no cambie nada: es la confirmación de la persona.
        """
        with self._tx() as con:
            fila = con.execute(
                "SELECT opcion, observacion FROM filas WHERE evaluacion_id = ? AND item = ?",
                (evaluacion_id, item),
            ).fetchone()
            if fila is None:
                raise EvaluacionInexistente(f"no existe el ítem {item} en {evaluacion_id!r}")
            ahora = self._momento()
            nuevos = {"opcion": opcion, "observacion": observacion}
            for campo, valor in nuevos.items():
                if valor is _SIN or valor == fila[campo]:
                    continue
                con.execute(
                    "INSERT INTO correcciones(evaluacion_id, item, campo, antes, despues, momento)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (evaluacion_id, item, campo, fila[campo], valor, ahora),
                )
                con.execute(
                    f"UPDATE filas SET {campo} = ? WHERE evaluacion_id = ? AND item = ?",
                    (valor, evaluacion_id, item),
                )
            con.execute(
                "UPDATE filas SET revisada = 1 WHERE evaluacion_id = ? AND item = ?",
                (evaluacion_id, item),
            )
            self._recalcular_estado(con, evaluacion_id, ahora)

    def actualizar_cabecera(
        self,
        evaluacion_id: str,
        *,
        paciente: str | None = None,
        cabecera: dict[str, str] | None = None,
    ) -> None:
        """Corrige la cabecera (`cabecera` se mezcla con lo guardado) y la da por revisada."""
        with self._tx() as con:
            self._existe(con, evaluacion_id)
            actual = con.execute(
                "SELECT paciente, cabecera FROM evaluaciones WHERE id = ?", (evaluacion_id,)
            ).fetchone()
            ahora = self._momento()
            cambios: list[tuple[str, str | None, str]] = []
            if paciente is not None and paciente != actual["paciente"]:
                cambios.append(("paciente", actual["paciente"], paciente))
            cab = json.loads(actual["cabecera"])
            for k, v in (cabecera or {}).items():
                if v != cab.get(k):
                    cambios.append((f"cabecera.{k}", cab.get(k), v))
                    cab[k] = v
            for campo, antes, despues in cambios:
                con.execute(
                    "INSERT INTO correcciones(evaluacion_id, item, campo, antes, despues, momento)"
                    " VALUES (?, NULL, ?, ?, ?, ?)",
                    (evaluacion_id, campo, antes, despues, ahora),
                )
            con.execute(
                "UPDATE evaluaciones SET paciente = ?, cabecera = ?, cabecera_revisada = 1"
                " WHERE id = ?",
                (
                    actual["paciente"] if paciente is None else paciente,
                    json.dumps(cab, ensure_ascii=False),
                    evaluacion_id,
                ),
            )
            self._recalcular_estado(con, evaluacion_id, ahora)

    def confirmar_cabecera(self, evaluacion_id: str) -> None:
        self.actualizar_cabecera(evaluacion_id)

    def marcar_exportada(self, evaluacion_id: str) -> None:
        with self._tx() as con:
            self._existe(con, evaluacion_id)
            con.execute(
                "UPDATE evaluaciones SET estado = 'exportada', actualizada_en = ? WHERE id = ?",
                (self._momento(), evaluacion_id),
            )

    def borrar_fotos(self, evaluacion_id: str, *, incluir_recortes: bool = False) -> int:
        """Borra del disco las fotos de la evaluación (AP-D1); conserva todo lo leído.

        Los recortes siguen (hacen falta para revisar y para el Excel con recortes) salvo con
        `incluir_recortes`. Idempotente y tolera archivos ya ausentes. Devuelve cuántos archivos
        quitó.
        """
        with self._tx() as con:
            self._existe(con, evaluacion_id)
            rutas = [
                r["foto_ruta"]
                for r in con.execute(
                    "SELECT foto_ruta FROM paginas WHERE evaluacion_id = ? AND foto_ruta IS NOT NULL",
                    (evaluacion_id,),
                )
            ]
            con.execute(
                "UPDATE paginas SET foto_ruta = NULL WHERE evaluacion_id = ?", (evaluacion_id,)
            )
            carpetas = [self.raiz / "fotos" / evaluacion_id]
            if incluir_recortes:
                rutas += [
                    r["ruta_recorte"]
                    for r in con.execute(
                        "SELECT ruta_recorte FROM filas WHERE evaluacion_id = ?"
                        " AND ruta_recorte IS NOT NULL",
                        (evaluacion_id,),
                    )
                ]
                cab = con.execute(
                    "SELECT recortes_cabecera FROM evaluaciones WHERE id = ?", (evaluacion_id,)
                ).fetchone()
                rutas += list(json.loads(cab["recortes_cabecera"]).values())
                con.execute(
                    "UPDATE filas SET ruta_recorte = NULL WHERE evaluacion_id = ?", (evaluacion_id,)
                )
                con.execute(
                    "UPDATE evaluaciones SET recortes_cabecera = '{}' WHERE id = ?",
                    (evaluacion_id,),
                )
                carpetas.append(self.raiz / "recortes" / evaluacion_id)
        borrados = 0
        for ruta in rutas:
            archivo = self.raiz / ruta
            if archivo.is_file():
                archivo.unlink()
                borrados += 1
        for carpeta in carpetas:
            try:
                carpeta.rmdir()  # solo si quedó vacía
            except OSError:
                pass
        return borrados

    def descartar_pagina(self, evaluacion_id: str, pagina: int) -> bool:
        """Descarta una foto (AP-R5): quita la página, sus filas y sus archivos del disco.

        Sirve para repetir una hoja mala: tras descartarla se puede subir de nuevo la misma
        página (y la misma foto). Si era la última página se elimina la evaluación entera, con
        sus correcciones y recortes de cabecera. Devuelve si la evaluación desapareció. Los
        recortes de cabecera de una evaluación que sigue viva se conservan.
        """
        with self._tx() as con:
            self._existe(con, evaluacion_id)
            p = con.execute(
                "SELECT foto_ruta FROM paginas WHERE evaluacion_id = ? AND pagina = ?",
                (evaluacion_id, pagina),
            ).fetchone()
            if p is None:
                raise EvaluacionInexistente(
                    f"no existe la página {pagina} en la evaluación {evaluacion_id!r}"
                )
            rutas = [p["foto_ruta"]] if p["foto_ruta"] else []
            rutas += [
                r["ruta_recorte"]
                for r in con.execute(
                    "SELECT ruta_recorte FROM filas WHERE evaluacion_id = ? AND pagina = ?"
                    " AND ruta_recorte IS NOT NULL",
                    (evaluacion_id, pagina),
                )
            ]
            carpetas = [self.raiz / "fotos" / evaluacion_id]
            con.execute(
                "DELETE FROM filas WHERE evaluacion_id = ? AND pagina = ?", (evaluacion_id, pagina)
            )
            con.execute(
                "DELETE FROM paginas WHERE evaluacion_id = ? AND pagina = ?",
                (evaluacion_id, pagina),
            )
            quedan = con.execute(
                "SELECT COUNT(*) FROM paginas WHERE evaluacion_id = ?", (evaluacion_id,)
            ).fetchone()[0]
            if quedan:
                self._recalcular_estado(con, evaluacion_id, self._momento())
            else:
                cab = con.execute(
                    "SELECT recortes_cabecera FROM evaluaciones WHERE id = ?", (evaluacion_id,)
                ).fetchone()
                rutas += list(json.loads(cab["recortes_cabecera"]).values())
                carpetas.append(self.raiz / "recortes" / evaluacion_id)
                con.execute("DELETE FROM evaluaciones WHERE id = ?", (evaluacion_id,))
        for ruta in rutas:
            (self.raiz / ruta).unlink(missing_ok=True)
        for carpeta in carpetas:
            try:
                carpeta.rmdir()
            except OSError:
                pass
        return not quedan

    def eliminar_evaluacion(self, evaluacion_id: str) -> None:
        """Elimina la evaluación entera (todas sus fotos, lecturas, correcciones y recortes).
        Los Excel ya exportados no se tocan. Lanza `EvaluacionInexistente` si no existe."""
        with self._candado:
            paginas = [
                r[0]
                for r in self._con.execute(
                    "SELECT pagina FROM paginas WHERE evaluacion_id = ? ORDER BY pagina",
                    (evaluacion_id,),
                )
            ]
        if not paginas:
            with self._tx() as con:
                self._existe(con, evaluacion_id)
                con.execute("DELETE FROM evaluaciones WHERE id = ?", (evaluacion_id,))
            return
        for pagina in paginas:
            self.descartar_pagina(evaluacion_id, pagina)

    def archivo(self, ruta_relativa: str) -> Path | None:
        """Ruta absoluta de un archivo guardado, o None si no existe o se sale de la raíz."""
        destino = (self.raiz / ruta_relativa).resolve()
        if not destino.is_relative_to(self.raiz.resolve()) or not destino.is_file():
            return None
        return destino

    # --- lectura ------------------------------------------------------------------------

    def leer_evaluacion(self, evaluacion_id: str) -> EvaluacionGuardada:
        with self._candado:
            e = self._con.execute(
                "SELECT * FROM evaluaciones WHERE id = ?", (evaluacion_id,)
            ).fetchone()
            if e is None:
                raise EvaluacionInexistente(f"no existe la evaluación {evaluacion_id!r}")
            paginas = self._con.execute(
                "SELECT * FROM paginas WHERE evaluacion_id = ? ORDER BY pagina", (evaluacion_id,)
            ).fetchall()
            filas = self._con.execute(
                "SELECT * FROM filas WHERE evaluacion_id = ? ORDER BY item", (evaluacion_id,)
            ).fetchall()
        return EvaluacionGuardada(
            id=e["id"],
            plantilla_id=e["plantilla_id"],
            plantilla_version=e["plantilla_version"],
            paciente=e["paciente"],
            fecha=e["fecha"],
            cabecera=json.loads(e["cabecera"]),
            recortes_cabecera=json.loads(e["recortes_cabecera"]),
            cabecera_revisada=bool(e["cabecera_revisada"]),
            estado=e["estado"],
            creada_en=e["creada_en"],
            actualizada_en=e["actualizada_en"],
            paginas=tuple(
                PaginaGuardada(
                    p["pagina"],
                    p["foto_sha256"],
                    p["foto_ruta"],
                    tuple(json.loads(p["problemas_calidad"])),
                    json.loads(p["registro"]),
                    bool(p["ocr_activo"]),
                )
                for p in paginas
            ),
            filas=tuple(
                FilaGuardada(
                    f["item"],
                    f["pagina"],
                    f["opcion_leida"],
                    f["opcion"],
                    tuple(json.loads(f["banderas"])),
                    f["texto_ocr"],
                    f["observacion"],
                    f["ruta_recorte"],
                    bool(f["revisada"]),
                )
                for f in filas
            ),
        )

    def listar_evaluaciones(self) -> list[ResumenEvaluacion]:
        """Más recientes primero (el orden de llegada decide los empates)."""
        with self._candado:
            rs = self._con.execute(
                "SELECT e.id, e.plantilla_id, e.paciente, e.fecha, e.estado, e.creada_en,"
                " COUNT(f.item) AS n_filas,"
                " COALESCE(SUM(f.revisada = 0), 0) AS pendientes"
                " FROM evaluaciones e LEFT JOIN filas f ON f.evaluacion_id = e.id"
                " GROUP BY e.id ORDER BY julianday(e.creada_en) DESC, e.rowid DESC"
            ).fetchall()
        return [
            ResumenEvaluacion(
                r["id"],
                r["plantilla_id"],
                r["paciente"],
                r["fecha"],
                r["estado"],
                r["creada_en"],
                r["n_filas"],
                r["pendientes"],
            )
            for r in rs
        ]

    def filas_pendientes(self, evaluacion_id: str) -> int:
        with self._candado:
            r = self._con.execute(
                "SELECT COUNT(*) FROM filas WHERE evaluacion_id = ? AND revisada = 0",
                (evaluacion_id,),
            ).fetchone()
        return r[0]

    def evaluacion_de_foto(self, foto_sha256: str) -> str | None:
        """Id de la evaluación que ya tiene esta foto (por SHA-256), o None (AP-R1: duplicados)."""
        with self._candado:
            r = self._con.execute(
                "SELECT evaluacion_id FROM paginas WHERE foto_sha256 = ? LIMIT 1", (foto_sha256,)
            ).fetchone()
        return r[0] if r else None

    def lecturas_de_foto(self, foto_sha256: str) -> list[tuple[str, str]]:
        """(id de la evaluación, id de su plantilla) de cada lectura que ya tiene esta foto.
        La misma foto puede leerse con otro formulario (la usuaria se equivocó de plantilla)."""
        with self._candado:
            filas = self._con.execute(
                "SELECT p.evaluacion_id, e.plantilla_id FROM paginas p"
                " JOIN evaluaciones e ON e.id = p.evaluacion_id WHERE p.foto_sha256 = ?",
                (foto_sha256,),
            ).fetchall()
        return [(f[0], f[1]) for f in filas]

    def cabecera_revisada(self, evaluacion_id: str) -> bool:
        with self._candado:
            r = self._con.execute(
                "SELECT cabecera_revisada FROM evaluaciones WHERE id = ?", (evaluacion_id,)
            ).fetchone()
        if r is None:
            raise EvaluacionInexistente(f"no existe la evaluación {evaluacion_id!r}")
        return bool(r[0])

    def listar_correcciones(self, evaluacion_id: str | None = None) -> list[Correccion]:
        """Las de una evaluación o, sin argumento, todas (las lee el informe del piloto)."""
        with self._candado:
            if evaluacion_id is None:
                rs = self._con.execute("SELECT * FROM correcciones ORDER BY id").fetchall()
            else:
                rs = self._con.execute(
                    "SELECT * FROM correcciones WHERE evaluacion_id = ? ORDER BY id",
                    (evaluacion_id,),
                ).fetchall()
        return [
            Correccion(
                r["id"],
                r["evaluacion_id"],
                r["item"],
                r["campo"],
                r["antes"],
                r["despues"],
                r["momento"],
            )
            for r in rs
        ]

    def leer_imagen(self, ruta_relativa: str) -> np.ndarray:
        """Carga un recorte guardado (acepta rutas con tildes en Windows, a diferencia de imread)."""
        datos = np.frombuffer((self.raiz / ruta_relativa).read_bytes(), np.uint8)
        img = cv2.imdecode(datos, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"imagen ilegible: {ruta_relativa}")
        return img

    # --- puente hacia core.excel --------------------------------------------------------

    def como_evaluacion(
        self, evaluacion_id: str, plantilla: Plantilla, *, con_recortes: bool = False
    ) -> Evaluacion:
        """La evaluación con los valores **confirmados**, lista para `core.excel.exportar`."""
        ev = self.leer_evaluacion(evaluacion_id)
        if (ev.plantilla_id, ev.plantilla_version) != (plantilla.id, plantilla.version):
            raise ValueError(
                f"la evaluación es de la plantilla {ev.plantilla_id} v{ev.plantilla_version}, "
                f"no de {plantilla.id} v{plantilla.version}"
            )
        filas = tuple(
            FilaEvaluacion(
                f.item,
                f.opcion,
                observacion=f.observacion,
                revisado=f.revisada,
                recorte=(
                    self.leer_imagen(f.ruta_recorte)
                    if con_recortes and f.ruta_recorte and (self.raiz / f.ruta_recorte).is_file()
                    else None
                ),
            )
            for f in ev.filas
        )
        # Fecha **y hora** de Bolivia del momento de exportar, si la evaluación es de hoy; si la
        # usuaria puso otra fecha, solo esa fecha.
        dia = date.fromisoformat(ev.fecha)
        exportada = a_bolivia(self._ahora())
        return Evaluacion(
            id=ev.id,
            plantilla=plantilla,
            fecha=exportada if exportada.date() == dia else dia,
            paciente=ev.paciente,
            filas=filas,
            cabecera={nombre_campo_cabecera(k): v for k, v in ev.cabecera.items()},
        )
