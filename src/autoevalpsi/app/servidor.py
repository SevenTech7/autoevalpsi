"""AP-R1: servidor local FastAPI.

`crear_app(bd, plantillas, ...)` arma la aplicación; quien la arranca (AP-R3: uvicorn en un hilo,
escuchando solo en la IP privada elegida, AP-03) es dueño de la `BaseDatos` y de su cierre.

**Contrato (API HTTP v1).** Todo bajo `/api`, JSON salvo las subidas (`multipart/form-data`).
Errores: `{"detail": {"codigo": "...", "mensaje": "..."}}` con el `mensaje` apto para la usuaria.

    GET  /api/salud                          sin token; para esperar a que el servidor arranque
    POST /api/fotos                          foto + plantilla [+ evaluacion, pagina, paciente, fecha]
    GET  /api/cola, /api/cola/{trabajo}      estado del procesamiento
    GET  /api/evaluaciones                   resúmenes, más recientes primero
    GET  /api/evaluaciones/{id}              evaluación completa, lo leído y lo confirmado
    PUT  /api/evaluaciones/{id}              confirma/corrige filas y cabecera (deja correcciones)
    POST /api/evaluaciones/{id}/exportar     a Excel; 409 si hay algo sin revisar (AP-06) o el
                                             archivo está abierto; {carpeta, evaluacion, consolidado}
    GET  /api/plantillas[/{id}]              plantillas instaladas
    POST /api/plantillas/importar            .zip con el .json y las imágenes en blanco (PL-D2)
    POST /api/vinculo/iniciar[?ip=]          código de vínculo de un solo uso (5 min), su QR y las IP (AP-02)
    GET  /api/vinculo                        ¿hay un celular vinculado?
    POST /api/vinculo                        {codigo} -> {dispositivo}: la credencial del celular
    DELETE /api/vinculo                      desvincula el celular
    GET  /api/configuracion                  carpeta de exportación (la elegida y la efectiva)
    PUT  /api/configuracion                  {carpeta_exportacion}; "" vuelve a la de por defecto
    POST /api/evaluaciones/{id}/borrar_fotos [{incluir_recortes}] -> {borrados}; acción manual (AP-D1)
    GET  /api/evaluaciones/{id}/recortes/{item}   PNG del recorte de la observación de una fila
    GET  /api/evaluaciones/{id}/cabecera/{campo}  PNG del recorte de un campo de la cabecera
    DELETE /api/evaluaciones/{id}/paginas/{n}     descarta una foto para repetirla (AP-R5)
    GET  /captura                            página del celular (HTML estático, sin secretos); AP-07
    GET  /, /assets/*                        la interfaz React compilada (AP-R4); estática y sin secretos

**Quién puede qué (AP-03, AP-D2).** Tres niveles:

- *Público*: `GET /api/salud`, `POST /api/vinculo` (exige un código válido), `GET /captura` y la
  interfaz compilada (`/`, `/assets/*`): son archivos estáticos; el token de la app llega a la
  ventana en la URL de arranque y la interfaz lo manda en cada llamada a `/api`.
- *Celular vinculado* (cabecera `X-Dispositivo` con su credencial): `POST /api/fotos`,
  `GET /api/cola*` y `GET /api/plantillas*`. Una credencial que no es la del celular vinculado
  recibe 403 `dispositivo_no_vinculado`.
- *Laptop*: todo lo demás, y también lo del celular. Exige el **token de la app** (cada arranque
  genera uno de 128 bits, en `Authorization: Bearer`, `X-Token` o `?token=`) **y** que la petición
  llegue por loopback; el token no sale nunca de la laptop. Desde otra IP: 403 `solo_laptop`.

El token y la credencial se comparan en tiempo constante y se revisan **antes** de leer el cuerpo.
Las subidas llevan tope de tamaño (25 MB las fotos) comprobado sobre `Content-Length`; la foto se
reconoce por sus bytes (JPEG/PNG), no por lo que declare el celular. La laptop no puede impedir
que el celular hable con otra computadora; garantiza que solo acepta el suyo.

Varias fotos de un mismo formulario (PL-03): se sube cada una con la misma `evaluacion` (el id lo
elige quien sube, p. ej. la página del celular) y su `pagina` (0-based).

El control de calidad (rápido) se responde en la misma petición; la lectura pesada va a la cola
(`app/cola.py`) y la respuesta es `202` con el trabajo.
"""

import hashlib
import ipaddress
import logging
import secrets
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from autoevalpsi.app.carpetas import carpeta_descargas
from autoevalpsi.app.cola import ColaLlena, ColaProcesamiento, FotoEnProceso, Trabajo
from autoevalpsi.app.datos import (
    BaseDatos,
    EvaluacionInexistente,
    IdInvalido,
    validar_id,
)
from autoevalpsi.app.plantillas import (
    ImportacionInvalida,
    PlantillaNoInstalada,
    PlantillaYaInstalada,
    RepositorioPlantillas,
)
from autoevalpsi.app.qr import RUTA_CAPTURA, qr_svg, url_captura
from autoevalpsi.app.red import Interfaz, candidatas, elegir_ip, listar_interfaces
from autoevalpsi.app.vinculo import Vinculos
from autoevalpsi.core.excel import ArchivoBloqueado, NombreArchivo, exportar
from autoevalpsi.core.imagen import ImagenInvalida, cargar_imagen, evaluar_calidad
from autoevalpsi.core.ocr.lector import Lector
from autoevalpsi.core.pipeline import procesar_foto

log = logging.getLogger(__name__)

MAX_FOTO = 25 * 1024 * 1024
MAX_ZIP = 100 * 1024 * 1024
MAX_JSON = 1024 * 1024
_SOBRECARGA_MULTIPART = 64 * 1024
_SUBIDAS = {"/api/fotos": MAX_FOTO, "/api/plantillas/importar": MAX_ZIP}
PUERTO = 8765
PAGINA_CAPTURA = Path(__file__).parent / "captura" / "index.html"
ESTATICOS = Path(__file__).parent / "estaticos"  # salida de `ui/` (vite build)
_CSP_INTERFAZ = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def _error(status: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status, {"codigo": codigo, "mensaje": mensaje})


def _respuesta(status: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse({"detail": {"codigo": codigo, "mensaje": mensaje}}, status_code=status)


_PUBLICAS = {("GET", "/api/salud"), ("POST", "/api/vinculo")}


def _del_celular(metodo: str, ruta: str) -> bool:
    """Rutas que también puede usar el celular vinculado (el resto es solo de la laptop)."""
    if metodo == "POST":
        return ruta == "/api/fotos"
    if metodo == "GET":
        return ruta in ("/api/cola", "/api/plantillas") or ruta.startswith(
            ("/api/cola/", "/api/plantillas/")
        )
    return False


def _es_loopback(scope) -> bool:
    cliente = scope.get("client")
    try:
        return ipaddress.ip_address(cliente[0]).is_loopback if cliente else False
    except ValueError:
        return False


def _es_laptop(scope, puertos_laptop: frozenset[int]) -> bool:
    """Loopback; o, solo en la prueba en Docker (`app/prueba.py`), el puerto que el contenedor
    publica únicamente en `127.0.0.1` del anfitrión. Docker reenvía todo con la IP de su puente,
    así que la IP de origen ya no distingue la laptop del celular; el puerto sí."""
    if _es_loopback(scope):
        return True
    servidor = scope.get("server")
    return bool(servidor and servidor[1] in puertos_laptop)


class Guardia:
    """ASGI: quién llama y tope de tamaño antes de que nadie lea el cuerpo de la petición."""

    def __init__(
        self, app, token: str, vinculos: Vinculos, puertos_laptop: frozenset[int] = frozenset()
    ) -> None:
        self.app = app
        self._puertos_laptop = puertos_laptop
        self._token = token.encode()
        self._vinculos = vinculos

    def _token_valido(self, cabeceras: dict[str, str], scope) -> bool:
        candidatos = [cabeceras.get("x-token", "")]
        auth = cabeceras.get("authorization", "")
        if auth.lower().startswith("bearer "):
            candidatos.append(auth[7:].strip())
        candidatos += parse_qs(scope.get("query_string", b"").decode("latin-1")).get("token", [])
        return any(secrets.compare_digest(c.encode(), self._token) for c in candidatos if c)

    def _rechazo(self, scope, cabeceras: dict[str, str], ruta: str) -> JSONResponse | None:
        """None si la petición puede seguir; si no, la respuesta que la corta."""
        metodo = scope["method"]
        if (metodo, ruta) in _PUBLICAS:
            return None
        local = _es_laptop(scope, self._puertos_laptop)
        if local and self._token_valido(cabeceras, scope):
            return None
        if _del_celular(metodo, ruta) and not local:
            credencial = cabeceras.get("x-dispositivo", "")
            if not credencial:
                return _respuesta(
                    401, "sin_credencial", "Vincula este celular desde la laptop para enviar fotos."
                )
            if self._vinculos.credencial_valida(credencial):
                return None
            return _respuesta(
                403,
                "dispositivo_no_vinculado",
                "Este celular ya no está vinculado. Vincúlalo de nuevo desde la laptop.",
            )
        if not local:
            return _respuesta(403, "solo_laptop", "Esto solo se puede hacer desde la laptop.")
        return _respuesta(401, "sin_token", "Falta el token de la aplicación.")

    async def __call__(self, scope, receive, send) -> None:
        ruta = scope["path"].rstrip("/") if scope["type"] == "http" else ""
        if scope["type"] != "http" or not ruta.startswith("/api"):
            return await self.app(scope, receive, send)
        cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if (r := self._rechazo(scope, cabeceras, ruta)) is not None:
            return await r(scope, receive, send)
        if scope["method"] in ("POST", "PUT", "PATCH"):
            largo = cabeceras.get("content-length")
            tope = _SUBIDAS.get(ruta)
            if largo is None and tope is not None:
                r = _respuesta(411, "sin_tamano", "La petición no indica su tamaño.")
                return await r(scope, receive, send)
            if largo is not None:
                if not largo.isdigit():
                    r = _respuesta(400, "tamano_invalido", "Tamaño de la petición no válido.")
                    return await r(scope, receive, send)
                limite = (tope + _SOBRECARGA_MULTIPART) if tope else MAX_JSON
                if int(largo) > limite:
                    mb = (tope or MAX_JSON) // (1024 * 1024)
                    r = _respuesta(
                        413, "demasiado_grande", f"El archivo supera el máximo de {mb} MB."
                    )
                    return await r(scope, receive, send)
        await self.app(scope, receive, send)


# --- modelos de petición -------------------------------------------------------------------


class CambioFila(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: int
    opcion: str | None = None  # null explícito = «sin respuesta»; ausente = no tocar
    observacion: str | None = None


class CambioEvaluacion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paciente: str | None = None
    cabecera: dict[str, str] | None = None
    confirmar_cabecera: bool = False
    filas: list[CambioFila] = []


class PedidoVinculo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codigo: str


class PedidoConfiguracion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carpeta_exportacion: str | None = None  # "" o null: la de por defecto


class PedidoBorrarFotos(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incluir_recortes: bool = False


class PedidoExportar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carpeta: str | None = None  # por defecto: la configurada, Descargas o `<raíz>/exportaciones`
    iniciales: bool = False
    recortes: bool = False


@dataclass(frozen=True)
class _Subida:
    foto: bytes
    plantilla_id: str
    plantilla_version: int
    evaluacion_pedida: str | None
    paciente: str
    fecha: date | None


def _es_imagen(datos: bytes) -> bool:
    return datos.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"))


def crear_app(
    bd: BaseDatos,
    plantillas: RepositorioPlantillas,
    *,
    token: str | None = None,
    lector: Lector | None = None,
    puerto: int = PUERTO,
    interfaces: Callable[[], list[Interfaz]] = listar_interfaces,
    estaticos: Path = ESTATICOS,
    puertos_laptop: frozenset[int] = frozenset(),
    guardar_fallidas: Path | None = None,
    carpeta_por_defecto: Path | None = None,
) -> FastAPI:
    """`lector` (OCR) es opcional: sin él solo se leen las casillas. `app.state.token` es el
    token del arranque y `app.state.cola` la cola, por si quien arranca los necesita. `puerto` e
    `interfaces` (IP de la red local, AP-02) arman la URL del QR. `estaticos` es la carpeta de la
    interfaz compilada; si no existe, `/` explica que falta compilarla. `puertos_laptop` y
    `guardar_fallidas` (carpeta donde dejar las fotos que no se pudieron leer) y
    `carpeta_por_defecto` (en lugar de Descargas) son solo para la prueba en Docker."""
    token = token or secrets.token_urlsafe(16)

    def ejecutar(trabajo: Trabajo, subida: object) -> bool:
        assert isinstance(subida, _Subida)
        inst = plantillas.obtener(subida.plantilla_id, subida.plantilla_version)
        referencia = plantillas.referencia(inst, trabajo.pagina)
        try:
            proc = procesar_foto(
                subida.foto, inst.plantilla, referencia, pagina=trabajo.pagina, lector=lector
            )
        except Exception:
            if guardar_fallidas is not None:  # solo prueba manual: para ver por qué falló
                guardar_fallidas.mkdir(parents=True, exist_ok=True)
                nombre = f"{trabajo.id}-{subida.plantilla_id}.jpg"
                (guardar_fallidas / nombre).write_bytes(subida.foto)
            raise
        bd.guardar_procesamiento(
            proc.resultado,
            foto=subida.foto,
            recortes=proc.recortes,
            recortes_cabecera=proc.recortes_cabecera,
            evaluacion_id=subida.evaluacion_pedida,
            paciente=subida.paciente,
            fecha=subida.fecha,
        )
        return proc.resultado.requiere_revision

    cola = ColaProcesamiento(ejecutar)
    candado_exportar = threading.Lock()

    @asynccontextmanager
    async def vida(_app: FastAPI):
        cola.iniciar()
        yield
        cola.detener()

    app = FastAPI(title="AutoEvalPsi", lifespan=vida, docs_url=None, redoc_url=None)
    vinculos = Vinculos(bd)
    app.add_middleware(Guardia, token=token, vinculos=vinculos, puertos_laptop=puertos_laptop)
    app.state.token = token
    app.state.cola = cola
    app.state.vinculos = vinculos

    def instalada(id: str, version: int | None = None):
        try:
            return plantillas.obtener(id, version)
        except PlantillaNoInstalada as e:
            raise _error(404, "plantilla_no_instalada", str(e)) from e

    def evaluacion(id: str):
        try:
            return bd.leer_evaluacion(id)
        except EvaluacionInexistente as e:
            raise _error(404, "evaluacion_inexistente", str(e)) from e

    def carpeta_exportacion() -> Path:
        """La que eligió la usuaria; si no, Descargas (donde ella busca sus archivos); si no existe,
        `<raíz>/exportaciones`."""
        elegida = bd.leer_configuracion("carpeta_exportacion")
        if elegida:
            return Path(elegida)
        return carpeta_por_defecto or carpeta_descargas() or bd.raiz / "exportaciones"

    def detalle(id: str) -> dict:
        ev = evaluacion(id)
        return {**asdict(ev), "filas_pendientes": bd.filas_pendientes(id)}

    # --- salud y cola -------------------------------------------------------------------

    @app.get("/api/salud")
    def salud() -> dict:
        return {"ok": True, "pendientes": cola.estado()["pendientes"]}

    @app.get("/api/cola")
    def estado_cola() -> dict:
        return cola.estado()

    @app.get("/api/cola/{trabajo_id}")
    def estado_trabajo(trabajo_id: str) -> dict:
        t = cola.trabajo(trabajo_id)
        if t is None:
            raise _error(404, "trabajo_inexistente", "No conozco ese trabajo.")
        return t.a_dict()

    # --- fotos --------------------------------------------------------------------------

    @app.post("/api/fotos", status_code=202)
    def subir_foto(
        foto: Annotated[UploadFile, File()],
        plantilla: Annotated[str, Form()],
        evaluacion_id: Annotated[str | None, Form(alias="evaluacion")] = None,
        pagina: Annotated[int, Form()] = 0,
        paciente: Annotated[str, Form()] = "",
        fecha: Annotated[str | None, Form()] = None,
    ) -> dict:
        datos = foto.file.read(MAX_FOTO + 1)
        if len(datos) > MAX_FOTO:
            raise _error(413, "demasiado_grande", "La foto supera el máximo de 25 MB.")
        if not _es_imagen(datos):
            raise _error(415, "tipo_no_soportado", "Solo se aceptan fotos JPEG o PNG.")
        try:
            fecha_eval = date.fromisoformat(fecha) if fecha else None
        except ValueError:
            raise _error(422, "fecha_invalida", "La fecha debe ser AAAA-MM-DD.") from None

        version = None
        if evaluacion_id is not None:
            try:
                validar_id(evaluacion_id)
            except IdInvalido as e:
                raise _error(422, "id_invalido", str(e)) from e
            try:
                previa = bd.leer_evaluacion(evaluacion_id)
            except EvaluacionInexistente:
                previa = None
            if previa is not None:
                if previa.plantilla_id != plantilla:
                    raise _error(
                        422,
                        "plantilla_distinta",
                        f"Esa evaluación es de la plantilla «{previa.plantilla_id}».",
                    )
                if any(p.pagina == pagina for p in previa.paginas):
                    raise _error(409, "pagina_repetida", f"La página {pagina + 1} ya se subió.")
                version = previa.plantilla_version
        inst = instalada(plantilla, version)
        if not 0 <= pagina < len(inst.plantilla.paginas):
            raise _error(
                422,
                "pagina_invalida",
                f"El formulario tiene {len(inst.plantilla.paginas)} página(s); "
                f"pagina va de 0 a {len(inst.plantilla.paginas) - 1}.",
            )

        try:
            problemas = tuple(evaluar_calidad(cargar_imagen(datos)).problemas)
        except ImagenInvalida as e:
            raise _error(422, "imagen_invalida", str(e)) from e

        sha = hashlib.sha256(datos).hexdigest()
        if (otra := bd.evaluacion_de_foto(sha)) is not None:
            raise _error(409, "foto_repetida", f"Esa foto ya se subió (evaluación {otra}).")
        try:
            trabajo = cola.encolar(
                _Subida(
                    datos,
                    inst.plantilla.id,
                    inst.plantilla.version,
                    evaluacion_id,
                    paciente.strip(),
                    fecha_eval,
                ),
                sha256=sha,
                evaluacion_id=evaluacion_id or sha[:12],
                pagina=pagina,
                plantilla_id=inst.plantilla.id,
                problemas_calidad=problemas,
            )
        except FotoEnProceso:
            raise _error(409, "foto_repetida", "Esa foto ya se está leyendo.") from None
        except ColaLlena:
            raise _error(
                503, "cola_llena", "Hay muchas fotos esperando; vuelve a intentarlo en un momento."
            ) from None
        return {"trabajo": trabajo.a_dict(), "problemas_calidad": list(problemas),
                "repetir": bool(problemas)}  # fmt: skip

    # --- evaluaciones -------------------------------------------------------------------

    @app.get("/api/evaluaciones")
    def listar_evaluaciones() -> list[dict]:
        return [asdict(r) for r in bd.listar_evaluaciones()]

    @app.get("/api/evaluaciones/{id}")
    def leer_evaluacion(id: str) -> dict:
        return detalle(id)

    @app.put("/api/evaluaciones/{id}")
    def corregir_evaluacion(id: str, cambio: CambioEvaluacion) -> dict:
        ev = evaluacion(id)
        inst = instalada(ev.plantilla_id, ev.plantilla_version)
        opciones = {
            f.item: t.opciones for p in inst.plantilla.paginas for t in p.tablas for f in t.filas
        }
        existentes = {f.item for f in ev.filas}
        for c in cambio.filas:  # validar todo antes de tocar nada
            if c.item not in existentes:
                raise _error(422, "item_inexistente", f"El ítem {c.item} no existe.")
            if (
                "opcion" in c.model_fields_set
                and c.opcion is not None
                and c.opcion not in opciones[c.item]
            ):
                raise _error(
                    422,
                    "opcion_invalida",
                    f"Ítem {c.item}: «{c.opcion}» no es una opción válida {opciones[c.item]}.",
                )
        for c in cambio.filas:
            nuevos = {}
            if "opcion" in c.model_fields_set:
                nuevos["opcion"] = c.opcion
            if c.observacion is not None:
                nuevos["observacion"] = c.observacion
            bd.actualizar_fila(id, c.item, **nuevos)
        if cambio.paciente is not None or cambio.cabecera:
            bd.actualizar_cabecera(id, paciente=cambio.paciente, cabecera=cambio.cabecera)
        elif cambio.confirmar_cabecera:
            bd.confirmar_cabecera(id)
        return detalle(id)

    @app.post("/api/evaluaciones/{id}/exportar")
    def exportar_evaluacion(id: str, pedido: PedidoExportar | None = None) -> dict:
        pedido = pedido or PedidoExportar()
        ev = evaluacion(id)
        pendientes = bd.filas_pendientes(id)
        if pendientes or not ev.cabecera_revisada:  # AP-06: lo impone el servidor
            partes = []
            if pendientes:
                partes.append(f"{pendientes} fila(s) sin confirmar")
            if not ev.cabecera_revisada:
                partes.append("la cabecera sin confirmar")
            raise HTTPException(
                409,
                {
                    "codigo": "revision_pendiente",
                    "mensaje": "Antes de exportar falta revisar: " + " y ".join(partes) + ".",
                    "filas_pendientes": pendientes,
                    "cabecera_revisada": ev.cabecera_revisada,
                },
            )
        inst = instalada(ev.plantilla_id, ev.plantilla_version)
        carpeta = Path(pedido.carpeta) if pedido.carpeta else carpeta_exportacion()
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise _error(422, "carpeta_invalida", f"No se pudo usar la carpeta: {e}") from e
        modo = NombreArchivo.INICIALES if pedido.iniciales else NombreArchivo.PACIENTE
        with candado_exportar:
            try:
                archivos = exportar(
                    bd.como_evaluacion(id, inst.plantilla, con_recortes=pedido.recortes),
                    carpeta,
                    nombre=modo,
                    incluir_recortes=pedido.recortes,
                )
            except ArchivoBloqueado as e:
                raise _error(409, "archivo_bloqueado", str(e)) from e
            bd.marcar_exportada(id)
        return {
            "carpeta": str(carpeta),
            "evaluacion": str(archivos.evaluacion),
            "consolidado": str(archivos.consolidado),
        }

    @app.post("/api/evaluaciones/{id}/borrar_fotos")
    def borrar_fotos(id: str, pedido: PedidoBorrarFotos | None = None) -> dict:
        """AP-D1: el borrado es una acción manual de la usuaria; lo leído y lo corregido se queda."""
        evaluacion(id)
        incluir = (pedido or PedidoBorrarFotos()).incluir_recortes
        return {"borrados": bd.borrar_fotos(id, incluir_recortes=incluir)}

    # --- revisión (AP-R5) ---------------------------------------------------------------

    def imagen(ruta: str | None) -> FileResponse:
        archivo = bd.archivo(ruta) if ruta else None
        if archivo is None:
            raise _error(404, "recorte_inexistente", "Esa imagen ya no está guardada.")
        return FileResponse(archivo, headers={"Cache-Control": "private, no-store"})

    @app.get("/api/evaluaciones/{id}/recortes/{item}")
    def recorte_de_fila(id: str, item: int) -> FileResponse:
        """El recorte original de la observación de una fila (solo las que tenían tinta)."""
        fila = next((f for f in evaluacion(id).filas if f.item == item), None)
        return imagen(fila.ruta_recorte if fila else None)

    @app.get("/api/evaluaciones/{id}/cabecera/{campo}")
    def recorte_de_cabecera(id: str, campo: str) -> FileResponse:
        return imagen(evaluacion(id).recortes_cabecera.get(campo))

    @app.delete("/api/evaluaciones/{id}/paginas/{pagina}")
    def descartar_pagina(id: str, pagina: int) -> dict:
        """Descarta una foto para repetirla. Si era la única, la evaluación desaparece."""
        evaluacion(id)
        leyendo = any(
            t["evaluacion_id"] == id and t["pagina"] == pagina
            for t in cola.estado()["trabajos"]
            if t["estado"] in ("en_cola", "procesando")
        )
        if leyendo:
            raise _error(
                409, "foto_en_lectura", "Esa foto todavía se está leyendo; espera un momento."
            )
        try:
            eliminada = bd.descartar_pagina(id, pagina)
        except EvaluacionInexistente as e:
            raise _error(404, "pagina_inexistente", str(e)) from e
        return {"evaluacion_eliminada": eliminada}

    # --- configuración (AP-R4) ----------------------------------------------------------

    def configuracion() -> dict:
        elegida = bd.leer_configuracion("carpeta_exportacion") or None
        return {
            "carpeta_exportacion": elegida,
            "carpeta_exportacion_efectiva": str(carpeta_exportacion()),
        }

    @app.get("/api/configuracion")
    def leer_configuracion() -> dict:
        return configuracion()

    @app.put("/api/configuracion")
    def guardar_configuracion(pedido: PedidoConfiguracion) -> dict:
        carpeta = (pedido.carpeta_exportacion or "").strip()
        if carpeta:
            ruta = Path(carpeta)
            if not ruta.is_absolute():
                raise _error(
                    422,
                    "carpeta_invalida",
                    "Escribe la ruta completa de la carpeta, empezando por la unidad (C:).",
                )
            try:
                ruta.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise _error(422, "carpeta_invalida", f"No se pudo usar la carpeta: {e}") from e
            carpeta = str(ruta)
        bd.guardar_configuracion("carpeta_exportacion", carpeta)
        return configuracion()

    # --- plantillas ---------------------------------------------------------------------

    def resumen(inst) -> dict:
        p = inst.plantilla
        return {
            "id": p.id,
            "nombre": p.nombre,
            "version": p.version,
            "paginas": len(p.paginas),
            "items": sum(len(t.filas) for pg in p.paginas for t in pg.tablas),
        }

    @app.get("/api/plantillas")
    def listar_plantillas() -> list[dict]:
        return [resumen(i) for i in plantillas.listar()]

    @app.get("/api/plantillas/{id}")
    def leer_plantilla(id: str, version: int | None = None) -> dict:
        return instalada(id, version).plantilla.model_dump(mode="json")

    @app.post("/api/plantillas/importar", status_code=201)
    def importar_plantilla(archivo: Annotated[UploadFile, File()]) -> dict:
        datos = archivo.file.read(MAX_ZIP + 1)
        if len(datos) > MAX_ZIP:
            raise _error(413, "demasiado_grande", "El .zip supera el máximo de 100 MB.")
        try:
            return resumen(plantillas.importar_zip(datos))
        except PlantillaYaInstalada as e:
            raise _error(409, "plantilla_ya_instalada", str(e)) from e
        except ImportacionInvalida as e:
            raise _error(422, "zip_invalido", str(e)) from e

    # --- vínculo del celular (AP-D2) y página de captura (AP-R2) ------------------------------

    @app.post("/api/vinculo/iniciar")
    def iniciar_vinculo(ip: str | None = None) -> dict:
        """Código de un solo uso y su QR. `ip` opcional: la que la usuaria eligió de `ips`; si no
        sirve se usa la mejor. Pedir otro código anula el anterior."""
        lista = candidatas(interfaces())
        elegida = elegir_ip(lista, ip)
        if elegida is None:
            return {"url": None, "qr_svg": None, "ip": None, "puerto": puerto, "ips": [],
                    "vence_en": 0, "vinculado": vinculos.vinculado,
                    "mensaje": "La laptop no está en una red WiFi o cable con IP privada. "
                               "Conéctala al WiFi de la casa."}  # fmt: skip
        emitido = vinculos.iniciar()
        url = url_captura(elegida, puerto, emitido.codigo)
        return {"url": url, "qr_svg": qr_svg(url), "ip": elegida, "puerto": puerto,
                "ips": [i.ip for i in lista], "vence_en": int(emitido.vence_en),
                "vinculado": vinculos.vinculado, "mensaje": ""}  # fmt: skip

    @app.get("/api/vinculo")
    def estado_vinculo() -> dict:
        d = bd.leer_dispositivo()
        return {"vinculado": d is not None, "creado": d.creado if d else None,
                "ultimo_uso": d.ultimo_uso if d else None}  # fmt: skip

    @app.post("/api/vinculo")
    def vincular(pedido: PedidoVinculo) -> dict:
        credencial = vinculos.canjear(pedido.codigo)
        if credencial is None:
            raise _error(
                403,
                "codigo_invalido",
                "El código no sirve (ya se usó o venció). Pide uno nuevo en la laptop.",
            )
        return {"dispositivo": credencial}

    @app.delete("/api/vinculo")
    def desvincular() -> dict:
        return {"desvinculado": vinculos.olvidar()}

    @app.get(RUTA_CAPTURA, response_class=HTMLResponse)
    def pagina_captura() -> HTMLResponse:
        """La página del celular: HTML liviano sin build (AP-07). Es estática y no lleva ningún
        secreto (el navegador no puede mandar la credencial al abrir una página); la lista de
        formularios y las subidas las pide con la credencial del celular."""
        return HTMLResponse(
            PAGINA_CAPTURA.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    # --- la interfaz compilada (AP-R4) --------------------------------------------------

    index = estaticos / "index.html"
    if (estaticos / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=estaticos / "assets"), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def interfaz(request: Request) -> Response:
        """La interfaz de la ventana. Estática y sin secretos: el token viaja en la URL de
        arranque y lo lee la propia página. Quien entra desde otro equipo (el celular, que escribe
        solo `http://IP:puerto`) no tiene nada que hacer aquí: va a la página de captura."""
        if not _es_laptop(request.scope, puertos_laptop):
            return RedirectResponse(RUTA_CAPTURA, status_code=302)
        if not index.is_file():
            return HTMLResponse(
                "<!doctype html><meta charset=utf-8><title>AutoEvalPsi</title>"
                "<p>Falta compilar la interfaz: <code>docker compose run --rm ui npm run build</code>.",
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(
            index.read_text(encoding="utf-8"),
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": _CSP_INTERFAZ,
            },
        )

    return app
