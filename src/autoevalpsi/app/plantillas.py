"""AP-R1: plantillas instaladas en la raíz de la app (PL-D2).

Las plantillas reales viven **fuera del repo**: se importan desde un .zip (el .json de la
plantilla más las imágenes en blanco que cita) y quedan en `<carpeta>/<id>/v<versión>/`. Una
versión instalada no se pisa: una plantilla corregida lleva `version` nueva, porque las
evaluaciones ya guardadas citan la versión con que se leyeron (`BaseDatos.como_evaluacion`).
"""

import io
import json
import re
import shutil
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np
from pydantic import ValidationError

from autoevalpsi.core.libro import (
    LibroBaseInvalido,
    comprobar_libro,
    proponer_conservar,
    proponer_vaciado,
)
from autoevalpsi.core.plantilla import Plantilla, PlantillaInvalida, cargar_plantilla
from autoevalpsi.core.registro import RegistroInvalido, cargar_referencia

NOMBRE_JSON = "plantilla.json"
MAX_ARCHIVOS = 100
MAX_DESCOMPRIMIDO = 200 * 1024 * 1024
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _resumen_errores(e: ValidationError) -> str:
    lineas = []
    for err in e.errors():
        campo = ".".join(str(x) for x in err["loc"]) or "(raíz)"
        lineas.append(f"{campo}: {str(err['msg']).removeprefix('Value error, ')}")
    return "La plantilla editada no es válida: " + "; ".join(lineas)


class PlantillaNoInstalada(LookupError):
    pass


class ImportacionInvalida(ValueError):
    """El .zip no sirve como plantilla; el mensaje dice por qué, apto para mostrar."""


class PlantillaYaInstalada(ValueError):
    pass


@dataclass(frozen=True)
class PlantillaInstalada:
    plantilla: Plantilla
    ruta: Path  # el plantilla.json instalado


class RepositorioPlantillas:
    def __init__(self, carpeta: str | Path) -> None:
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._candado = threading.Lock()
        self._referencias: dict[tuple[str, int, int], np.ndarray] = {}

    # --- lectura ------------------------------------------------------------------------

    def listar(self) -> list[PlantillaInstalada]:
        """Todas las versiones instaladas, por id y versión. Las ilegibles se saltan."""
        out = []
        for ruta in self.carpeta.glob(f"*/v*/{NOMBRE_JSON}"):
            try:
                out.append(PlantillaInstalada(cargar_plantilla(ruta), ruta))
            except PlantillaInvalida:
                continue
        return sorted(out, key=lambda i: (i.plantilla.id, i.plantilla.version))

    def obtener(self, id: str, version: int | None = None) -> PlantillaInstalada:
        """La versión pedida o, sin `version`, la más nueva."""
        if not _ID.fullmatch(id):
            raise PlantillaNoInstalada(f"No hay una plantilla «{id}» instalada.")
        candidatas = [i for i in self.listar() if i.plantilla.id == id]
        if version is not None:
            candidatas = [i for i in candidatas if i.plantilla.version == version]
        if not candidatas:
            que = f"«{id}»" if version is None else f"«{id}» versión {version}"
            raise PlantillaNoInstalada(f"No hay una plantilla {que} instalada.")
        return candidatas[-1]

    def referencia(self, inst: PlantillaInstalada, pagina: int) -> np.ndarray:
        """Imagen en blanco (gris) de la página `pagina` (0-based), con caché."""
        clave = (inst.plantilla.id, inst.plantilla.version, pagina)
        with self._candado:
            if clave not in self._referencias:
                self._referencias[clave] = cargar_referencia(
                    inst.ruta, inst.plantilla.paginas[pagina].imagen_referencia
                )
            return self._referencias[clave]

    # --- importación --------------------------------------------------------------------

    def importar_zip(self, datos: bytes) -> PlantillaInstalada:
        """Instala la plantilla de un .zip. Valida todo antes de dejar nada en la carpeta."""
        try:
            zf = zipfile.ZipFile(io.BytesIO(datos))
        except zipfile.BadZipFile as e:
            raise ImportacionInvalida("El archivo no es un .zip válido.") from e
        with zf:
            miembros = [m for m in zf.infolist() if not m.is_dir()]
            if len(miembros) > MAX_ARCHIVOS:
                raise ImportacionInvalida(f"El .zip trae demasiados archivos ({len(miembros)}).")
            if sum(m.file_size for m in miembros) > MAX_DESCOMPRIMIDO:
                raise ImportacionInvalida("El .zip es demasiado grande al descomprimirlo.")
            rutas = {m.filename: self._ruta_segura(m.filename) for m in miembros}
            jsons = [n for n, r in rutas.items() if r.suffix.lower() == ".json"]
            if len(jsons) != 1:
                raise ImportacionInvalida(
                    f"El .zip debe traer un solo archivo .json de plantilla (trae {len(jsons)})."
                )
            base = rutas[jsons[0]].parent

            tmp = self.carpeta / f".importando-{uuid.uuid4().hex}"
            try:
                tmp.mkdir()
                for nombre, ruta in rutas.items():
                    if ruta.parent != base and base not in ruta.parents:
                        continue  # fuera de la carpeta de la plantilla: se ignora
                    destino = tmp / (NOMBRE_JSON if nombre == jsons[0] else ruta.relative_to(base))
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(zf.read(nombre))
                plantilla = self._validar(tmp / NOMBRE_JSON)
                final = self.carpeta / plantilla.id / f"v{plantilla.version}"
                with self._candado:
                    if final.exists():
                        raise PlantillaYaInstalada(
                            f"La plantilla «{plantilla.id}» versión {plantilla.version} ya está "
                            "instalada. Si la corregiste, súbele la versión en el .json."
                        )
                    final.parent.mkdir(parents=True, exist_ok=True)
                    tmp.rename(final)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return PlantillaInstalada(plantilla, final / NOMBRE_JSON)

    # --- edición (FS-R3) ----------------------------------------------------------------

    def crear_version(self, id: str, definicion: dict) -> PlantillaInstalada:
        """Guarda `definicion` (la plantilla editada) como la **versión siguiente** de `id`.

        Una versión instalada nunca se pisa (las evaluaciones ya guardadas la citan): la corrección
        queda como `v<más alta + 1>`. Las imágenes en blanco se copian de la versión más nueva y la
        definición no puede citar otras.
        """
        base = self.obtener(id)
        datos = {**definicion, "id": id, "version": base.plantilla.version + 1}
        datos["esquema_version"] = base.plantilla.esquema_version
        nombres = {pg.imagen_referencia for pg in base.plantilla.paginas}
        try:
            plantilla = Plantilla.model_validate(datos)
        except ValidationError as e:
            raise ImportacionInvalida(_resumen_errores(e)) from e
        citadas = [pg.imagen_referencia for pg in plantilla.paginas]
        if len(citadas) != len(base.plantilla.paginas) or any(c not in nombres for c in citadas):
            raise ImportacionInvalida(
                "No se pueden cambiar las imágenes ni el número de páginas de la plantilla."
            )
        origen = base.ruta.parent
        tmp = self.carpeta / f".editando-{uuid.uuid4().hex}"
        try:
            shutil.copytree(origen, tmp)
            (tmp / NOMBRE_JSON).write_text(
                json.dumps(plantilla.model_dump(mode="json"), indent=1, ensure_ascii=False),
                encoding="utf-8",
            )
            final = self.carpeta / id / f"v{plantilla.version}"
            with self._candado:
                if final.exists():
                    raise PlantillaYaInstalada(
                        "Alguien guardó otra versión a la vez; vuelve a abrir."
                    )
                tmp.rename(final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return PlantillaInstalada(plantilla, final / NOMBRE_JSON)

    def instalar_nueva(self, definicion: dict, imagenes: dict[str, bytes]) -> PlantillaInstalada:
        """Instala una plantilla recién armada (versión 1). Si el id ya existe, le pone « -2», «-3»…"""
        base_id = definicion["id"]
        ocupados = {i.plantilla.id for i in self.listar()}
        id = base_id
        n = 1
        while id in ocupados:
            n += 1
            id = f"{base_id}-{n}"
        datos = {**definicion, "id": id, "version": 1}
        tmp = self.carpeta / f".creando-{uuid.uuid4().hex}"
        try:
            tmp.mkdir()
            for nombre, contenido in imagenes.items():
                (tmp / self._ruta_segura(nombre).name).write_bytes(contenido)
            (tmp / NOMBRE_JSON).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            plantilla = self._validar(tmp / NOMBRE_JSON)
            final = self.carpeta / id / "v1"
            final.parent.mkdir(parents=True, exist_ok=True)
            with self._candado:
                tmp.rename(final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return PlantillaInstalada(plantilla, final / NOMBRE_JSON)

    def eliminar(self, id: str) -> int:
        """Borra la plantilla con todas sus versiones; devuelve cuántas versiones eran."""
        if not _ID.fullmatch(id):
            raise PlantillaNoInstalada(f"No hay una plantilla «{id}» instalada.")
        versiones = [i for i in self.listar() if i.plantilla.id == id]
        carpeta = self.carpeta / id
        if not versiones and not carpeta.is_dir():
            raise PlantillaNoInstalada(f"No hay una plantilla «{id}» instalada.")
        with self._candado:
            shutil.rmtree(carpeta, ignore_errors=True)
            for clave in [k for k in self._referencias if k[0] == id]:
                del self._referencias[clave]
        return len(versiones)

    def ruta_imagen(self, inst: PlantillaInstalada, pagina: int) -> Path:
        return inst.ruta.parent / inst.plantilla.paginas[pagina].imagen_referencia

    def ruta_libro(self, inst: PlantillaInstalada) -> Path | None:
        """El libro de Excel base de la plantilla, si declara uno."""
        libro = inst.plantilla.libro
        return inst.ruta.parent / libro.archivo if libro else None

    def comprobar_libro(self, id: str) -> dict:
        """Cruza la versión más nueva con su libro de Excel (`core.libro.comprobar_libro`)."""
        inst = self.obtener(id)
        ruta, libro = self.ruta_libro(inst), inst.plantilla.libro
        if ruta is None or libro is None:
            raise LibroBaseInvalido("Esta plantilla no tiene un libro de Excel.")
        items = [
            (f.texto.rsplit("·", 1)[-1].strip() or str(f.item), f.celda)
            for p in inst.plantilla.paginas
            for t in p.tablas
            for f in t.filas
        ]
        return comprobar_libro(ruta, libro.hoja, items)

    def _nueva_version(
        self, id: str, cambiar, archivos: dict[str, bytes] | None = None
    ) -> PlantillaInstalada:
        """Copia la versión más nueva de `id`, aplica `cambiar(dict)` a su definición, le agrega
        `archivos` y la instala como la versión siguiente. Nada queda a medias si algo falla."""
        base = self.obtener(id)
        datos = base.plantilla.model_dump(mode="json")
        datos["version"] = base.plantilla.version + 1
        cambiar(datos)
        tmp = self.carpeta / f".editando-{uuid.uuid4().hex}"
        try:
            shutil.copytree(base.ruta.parent, tmp)
            for nombre, contenido in (archivos or {}).items():
                (tmp / self._ruta_segura(nombre).name).write_bytes(contenido)
            (tmp / NOMBRE_JSON).write_text(
                json.dumps(datos, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            plantilla = self._validar(tmp / NOMBRE_JSON)
            final = self.carpeta / id / f"v{plantilla.version}"
            with self._candado:
                if final.exists():
                    raise PlantillaYaInstalada(
                        "Alguien guardó otra versión a la vez; vuelve a abrir."
                    )
                tmp.rename(final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return PlantillaInstalada(plantilla, final / NOMBRE_JSON)

    def agregar_pagina(self, id: str, pagina: dict, imagen: bytes) -> PlantillaInstalada:
        """Versión nueva con una página más (armada desde otra foto); su imagen se guarda aparte."""
        return self._nueva_version(
            id, lambda d: d["paginas"].append(pagina), {pagina["imagen_referencia"]: imagen}
        )

    def poner_libro(self, id: str, contenido: bytes) -> tuple[PlantillaInstalada, list[str]]:
        """Versión nueva que declara `contenido` (un .xlsx) como libro base de la salida.

        Devuelve también los rangos que se vaciarán (una propuesta, que se corrige en el editor).
        Lanza `LibroBaseInvalido` si el archivo no es un libro de Excel."""
        base = self.obtener(id)
        celdas = [
            f.celda for p in base.plantilla.paginas for t in p.tablas for f in t.filas if f.celda
        ]
        with tempfile.TemporaryDirectory(dir=self.carpeta, prefix=".analizando-") as d:
            ruta = Path(d) / "base.xlsx"
            ruta.write_bytes(contenido)
            vaciar = proponer_vaciado(ruta, None, celdas)
            conservar = proponer_conservar(ruta, None, celdas)
        archivo = f"libro-{uuid.uuid4().hex[:8]}.xlsx"
        inst = self._nueva_version(
            id,
            lambda d: d.update(
                libro={"archivo": archivo, "hoja": None, "vaciar": vaciar, "conservar": conservar}
            ),
            {archivo: contenido},
        )
        return inst, vaciar

    @staticmethod
    def _ruta_segura(nombre: str) -> PurePosixPath:
        ruta = PurePosixPath(nombre.replace("\\", "/"))
        if ruta.is_absolute() or ".." in ruta.parts or (ruta.parts and ":" in ruta.parts[0]):
            raise ImportacionInvalida(f"El .zip trae una ruta no permitida: «{nombre}».")
        return ruta

    @staticmethod
    def _validar(json: Path) -> Plantilla:
        try:
            plantilla = cargar_plantilla(json)
        except PlantillaInvalida as e:
            raise ImportacionInvalida(str(e).replace(str(json), "plantilla.json")) from e
        raiz = json.parent.resolve()
        for i, pagina in enumerate(plantilla.paginas):
            imagen = (raiz / pagina.imagen_referencia).resolve()
            if raiz not in imagen.parents:
                raise ImportacionInvalida(
                    f"La imagen de la página {i + 1} apunta fuera de la plantilla: "
                    f"«{pagina.imagen_referencia}»."
                )
            try:
                cargar_referencia(json, pagina.imagen_referencia)
            except RegistroInvalido as e:
                raise ImportacionInvalida(
                    f"Falta o no se lee la imagen en blanco «{pagina.imagen_referencia}» "
                    f"(página {i + 1}) en el .zip."
                ) from e
        return plantilla
