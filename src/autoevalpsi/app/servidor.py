"""AP-R1: servidor local FastAPI.

`crear_app(bd, plantillas, ...)` arma la aplicación; quien la arranca (AP-R3: uvicorn en un hilo,
escuchando solo en la IP privada elegida, AP-03) es dueño de la `BaseDatos` y de su cierre.

**Contrato (API HTTP v1).** Todo bajo `/api`, JSON salvo las subidas (`multipart/form-data`).
Errores: `{"detail": {"codigo": "...", "mensaje": "..."}}` con el `mensaje` apto para la usuaria.

    GET  /api/salud                          sin token; para esperar a que el servidor arranque
    POST /api/fotos                          foto + plantilla [+ evaluacion, pagina, paciente, fecha]
                                             sin `pagina`, la app decide a qué hoja pertenece la foto
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
    GET  /api/actualizacion                  estado de la actualización (versión instalada, novedad, descarga)
    POST /api/actualizacion/{buscar,descargar,instalar}   solo cuando la usuaria lo pide
    POST /api/evaluaciones/{id}/borrar_fotos [{incluir_recortes}] -> {borrados}; acción manual (AP-D1)
    GET  /api/evaluaciones/{id}/recortes/{item}   PNG del recorte de la observación de una fila
    GET  /api/evaluaciones/{id}/cabecera/{campo}  PNG del recorte de un campo de la cabecera
    DELETE /api/evaluaciones/{id}/paginas/{n}     descarta una foto para repetirla (AP-R5)
    DELETE /api/evaluaciones/{id}                 elimina la evaluación entera (los Excel exportados quedan)
    GET  /api/incompletas                    evaluaciones a las que les falta una hoja (también el celular)
    DELETE /api/plantillas/{id}[?con_evaluaciones=true]  elimina el formulario (409 si tiene evaluaciones)
    GET  /captura                            página del celular (HTML estático, sin secretos); AP-07
    GET  /, /assets/*                        la interfaz React compilada (AP-R4); estática y sin secretos

**Quién puede qué (AP-03, AP-D2).** Tres niveles:

- *Público*: `GET /api/salud`, `POST /api/vinculo` (exige un código válido), `GET /captura` y la
  interfaz compilada (`/`, `/assets/*`): son archivos estáticos; el token de la app llega a la
  ventana en la URL de arranque y la interfaz lo manda en cada llamada a `/api`.
- *Celular vinculado* (cabecera `X-Dispositivo` con su credencial): `POST /api/fotos`,
  `GET /api/cola*`, `GET /api/plantillas*` y `GET /api/incompletas`. Una credencial que no es la del celular vinculado
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
import mimetypes
import re
import secrets
import threading
import unicodedata
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs

import cv2
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

from autoevalpsi.app.actualizacion import Actualizador, ErrorActualizacion
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
from autoevalpsi.core.borrador import plantilla_automatica
from autoevalpsi.core.excel import ArchivoBloqueado, NombreArchivo, exportar
from autoevalpsi.core.imagen import ImagenInvalida, cargar_imagen, evaluar_calidad
from autoevalpsi.core.libro import LibroBaseInvalido
from autoevalpsi.core.ocr.lector import Lector
from autoevalpsi.core.ocr.onnx import LectorONNX
from autoevalpsi.core.pipeline import procesar_foto
from autoevalpsi.core.registro import elegir_hoja

log = logging.getLogger(__name__)

MAX_FOTO = 25 * 1024 * 1024
MAX_ZIP = 100 * 1024 * 1024
MAX_JSON = 1024 * 1024
_SOBRECARGA_MULTIPART = 64 * 1024
_SUBIDAS = {
    "/api/fotos": MAX_FOTO,
    "/api/plantillas/importar": MAX_ZIP,
    "/api/plantillas/desde-foto": MAX_FOTO,
}
_SUBIDA_DE_PLANTILLA = re.compile(r"/api/plantillas/[^/]+/(libro|paginas)")  # libro .xlsx o foto


def _tope_de_subida(ruta: str) -> int | None:
    if ruta in _SUBIDAS:
        return _SUBIDAS[ruta]
    return MAX_FOTO if _SUBIDA_DE_PLANTILLA.fullmatch(ruta) else None


PUERTO = 8765
PAGINA_CAPTURA = Path(__file__).parent / "captura" / "index.html"
ESTATICOS = Path(__file__).parent / "estaticos"  # salida de `ui/` (vite build)
# En Windows `mimetypes` lee el registro, y en muchas laptops `.js` figura como `text/plain` (lo
# deja algún programa instalado): el navegador se niega a ejecutar el script y la ventana sale en
# blanco. Los tipos de la interfaz se fijan aquí, sin depender del registro de Windows.
_TIPOS_ESTATICOS = {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


def _fijar_tipos_estaticos() -> None:
    previo = mimetypes.guess_type("x.js")[0]
    for extension, tipo in _TIPOS_ESTATICOS.items():
        mimetypes.add_type(tipo, extension)
    if previo != "text/javascript":
        log.warning("El sistema declara `.js` como %r; se fuerza text/javascript.", previo)


_CSP_INTERFAZ = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))


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
        return ruta in ("/api/cola", "/api/plantillas", "/api/incompletas") or ruta.startswith(
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


class RegistroInterfaz:
    """ASGI: deja en el registro cómo se sirvió la interfaz (`/` y `/assets/*`: estado y tipo).
    Si una ventana sale en blanco, ahí se ve si faltó un archivo o llegó con un tipo equivocado."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        ruta = scope.get("path", "")
        if scope["type"] != "http" or not (ruta == "/" or ruta.startswith("/assets/")):
            return await self.app(scope, receive, send)

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                tipo = dict(mensaje.get("headers", [])).get(b"content-type", b"").decode("latin-1")
                log.info("interfaz %s -> %s %s", ruta, mensaje["status"], tipo)
            await send(mensaje)

        await self.app(scope, receive, enviar)


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
            tope = _tope_de_subida(ruta)
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


class PedidoVersion(BaseModel):
    """La plantilla editada completa (el servidor fija `id`, `version` y `esquema_version`)."""

    model_config = ConfigDict(extra="forbid")
    plantilla: dict


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
    actualizador: Actualizador | None = None,
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
    app.add_middleware(RegistroInterfaz)
    app.state.token = token
    app.state.cola = cola
    app.state.vinculos = vinculos
    actualizador = actualizador or Actualizador(bd.raiz / "actualizaciones")
    app.state.actualizador = actualizador

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
        pagina: Annotated[int | None, Form()] = None,
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
        hechas: set[int] = set()
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
                version = previa.plantilla_version
                hechas = {p.pagina for p in previa.paginas}
        inst = instalada(plantilla, version)
        total = len(inst.plantilla.paginas)
        if pagina is None:
            # Sin `pagina`: la app decide a qué hoja del formulario pertenece la foto, entre las que
            # todavía no se subieron.
            pendientes = [n for n in range(total) if n not in hechas]
            if not pendientes:
                raise _error(
                    409, "pagina_repetida", "Ya se subieron todas las hojas de esta evaluación."
                )
            referencias = {n: plantillas.referencia(inst, n) for n in pendientes}
            try:
                imagen = cargar_imagen(datos)
            except ImagenInvalida as e:
                raise _error(422, "imagen_invalida", str(e)) from e
            elegida = elegir_hoja(imagen, referencias)
            if elegida is None:
                raise _error(
                    422,
                    "hoja_no_reconocida",
                    "No se reconoce a qué hoja del formulario pertenece la foto. Revisa que sea "
                    "el formulario correcto, que se vea la hoja entera y que no sea una hoja que "
                    "ya subiste.",
                )
            pagina = elegida
        if pagina in hechas:
            raise _error(409, "pagina_repetida", f"La página {pagina + 1} ya se subió.")
        if not 0 <= pagina < total:
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
        previas = bd.lecturas_de_foto(sha)
        for otra, plantilla_previa in previas:
            if plantilla_previa == inst.plantilla.id:
                raise _error(
                    409,
                    "foto_repetida",
                    "Esa foto ya se subió con este mismo formulario. Si quieres repetirla, "
                    "descártala antes en la lista de evaluaciones.",
                )
        # Misma foto leída con otro formulario (se equivocó de plantilla): se permite, como una
        # evaluación aparte; la anterior queda en la lista para descartarla.
        id_nuevo = sha[:12]
        if previas and evaluacion_id is None:
            id_nuevo = hashlib.sha256(f"{sha}/{inst.plantilla.id}".encode()).hexdigest()[:12]
        try:
            trabajo = cola.encolar(
                _Subida(
                    datos,
                    inst.plantilla.id,
                    inst.plantilla.version,
                    evaluacion_id or (id_nuevo if previas else None),
                    paciente.strip(),
                    fecha_eval,
                ),
                sha256=sha,
                evaluacion_id=evaluacion_id or id_nuevo,
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
        return [
            {
                **asdict(r),
                "paginas_total": paginas_de(r.plantilla_id, r.plantilla_version, r.paginas_subidas),
            }
            for r in bd.listar_evaluaciones()
        ]

    def paginas_de(plantilla_id: str, version: int, por_defecto: int) -> int:
        """Cuántas hojas tiene el formulario con que se hizo la evaluación."""
        try:
            return len(plantillas.obtener(plantilla_id, version).plantilla.paginas)
        except PlantillaNoInstalada:
            return por_defecto

    @app.get("/api/incompletas")
    def evaluaciones_incompletas() -> list[dict]:
        """Evaluaciones a las que les falta alguna hoja: sirven para seguir desde el celular."""
        salida = []
        for r in bd.listar_evaluaciones():
            try:
                inst = plantillas.obtener(r.plantilla_id, r.plantilla_version)
            except PlantillaNoInstalada:
                continue
            total = len(inst.plantilla.paginas)
            if r.paginas_subidas >= total:
                continue
            ev = bd.leer_evaluacion(r.id)
            hechas = {p.pagina for p in ev.paginas}
            salida.append(
                {
                    "id": r.id,
                    "paciente": r.paciente,
                    "plantilla_id": r.plantilla_id,
                    "plantilla_nombre": inst.plantilla.nombre,
                    "paginas_total": total,
                    "faltan": [n for n in range(total) if n not in hechas],
                }
            )
        return salida

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
                    libro_base=plantillas.ruta_libro(inst),
                )
            except ArchivoBloqueado as e:
                raise _error(409, "archivo_bloqueado", str(e)) from e
            except LibroBaseInvalido as e:
                raise _error(422, "libro_base_invalido", str(e)) from e
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

    @app.delete("/api/evaluaciones/{id}")
    def eliminar_evaluacion(id: str) -> dict:
        """Elimina una evaluación entera (por ejemplo, una hecha con el formulario equivocado).
        Los Excel que ya exportó se quedan donde están."""
        evaluacion(id)
        leyendo = any(
            t["evaluacion_id"] == id
            for t in cola.estado()["trabajos"]
            if t["estado"] in ("en_cola", "procesando")
        )
        if leyendo:
            raise _error(
                409, "foto_en_lectura", "Esa evaluación todavía se está leyendo; espera un momento."
            )
        try:
            bd.eliminar_evaluacion(id)
        except EvaluacionInexistente as e:
            raise _error(404, "evaluacion_inexistente", str(e)) from e
        return {"eliminada": True}

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

    # --- actualización (solo a pedido de la usuaria) --------------------------------------

    def actualizar(accion: Callable[[], object]) -> dict:
        try:
            accion()
        except ErrorActualizacion as e:
            raise _error(502, "actualizacion_fallo", str(e)) from e
        return actualizador.estado()

    @app.get("/api/actualizacion")
    def estado_actualizacion() -> dict:
        return actualizador.estado()

    @app.post("/api/actualizacion/buscar")
    def buscar_actualizacion() -> dict:
        return actualizar(actualizador.buscar)

    @app.post("/api/actualizacion/descargar")
    def descargar_actualizacion() -> dict:
        return actualizar(actualizador.descargar)

    @app.post("/api/actualizacion/instalar")
    def instalar_actualizacion() -> dict:
        if cola.estado()["pendientes"]:
            raise _error(
                409,
                "fotos_en_lectura",
                "Hay fotos leyéndose. Espera a que terminen y vuelve a intentarlo.",
            )
        return actualizar(actualizador.instalar)

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

    @app.delete("/api/plantillas/{id}")
    def eliminar_plantilla(id: str, con_evaluaciones: bool = False) -> dict:
        """Elimina un formulario con todas sus versiones. Si tiene evaluaciones, pide confirmarlo
        (`con_evaluaciones=true`) y se eliminan también; los Excel ya exportados quedan."""
        instalada(id)
        usadas = bd.evaluaciones_de_plantilla(id)
        leyendo = any(
            t["plantilla_id"] == id
            for t in cola.estado()["trabajos"]
            if t["estado"] in ("en_cola", "procesando")
        )
        if leyendo:
            raise _error(
                409, "foto_en_lectura", "Hay una foto de este formulario leyéndose; espera."
            )
        if usadas and not con_evaluaciones:
            raise _error(
                409,
                "plantilla_en_uso",
                f"Hay {len(usadas)} evaluaciones hechas con este formulario. "
                "Si lo eliminas, también se eliminan.",
            )
        for ev in usadas:
            bd.eliminar_evaluacion(ev)
        plantillas.eliminar(id)
        return {"eliminada": True, "evaluaciones_eliminadas": len(usadas)}

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

    @app.get("/api/plantillas/{id}/referencia/{pagina}")
    def referencia_de_plantilla(id: str, pagina: int, version: int | None = None) -> FileResponse:
        """La imagen en blanco de la página (0-based): el fondo del editor de plantillas."""
        inst = instalada(id, version)
        if not 0 <= pagina < len(inst.plantilla.paginas):
            raise _error(404, "pagina_inexistente", "Esa página no existe en la plantilla.")
        return FileResponse(
            plantillas.ruta_imagen(inst, pagina), headers={"Cache-Control": "private, no-store"}
        )

    @app.post("/api/plantillas/{id}/versiones", status_code=201)
    def guardar_version(id: str, pedido: PedidoVersion) -> dict:
        """FS-R3: la plantilla corregida se guarda como versión nueva; las viejas no se tocan."""
        instalada(id)
        try:
            return resumen(plantillas.crear_version(id, pedido.plantilla))
        except ImportacionInvalida as e:
            raise _error(422, "plantilla_invalida", str(e)) from e
        except PlantillaYaInstalada as e:
            raise _error(409, "plantilla_ya_instalada", str(e)) from e

    @app.post("/api/plantillas/desde-foto", status_code=201)
    def plantilla_desde_foto_llena(
        foto: Annotated[UploadFile, File()], nombre: Annotated[str, Form()]
    ) -> dict:
        """FS-R1: borrador preliminar a partir de la foto de un formulario lleno (necesita OCR)."""
        nombre = nombre.strip()
        if not nombre:
            raise _error(422, "nombre_vacio", "Escribe un nombre para el formulario.")
        if not isinstance(lector, LectorONNX):
            raise _error(
                409,
                "ocr_no_disponible",
                "Armar una plantilla desde una foto necesita el lector de texto (OCR), que esta "
                "instalación no tiene activado.",
            )
        datos = foto.file.read(MAX_FOTO + 1)
        if len(datos) > MAX_FOTO:
            raise _error(413, "demasiado_grande", "La foto supera el máximo de 25 MB.")
        try:
            imagen = cargar_imagen(datos)
        except ImagenInvalida as e:
            raise _error(422, "foto_invalida", str(e)) from e
        ident = re.sub(r"[^a-z0-9]+", "-", _sin_tildes(nombre).lower()).strip("-") or "formulario"
        definicion, limpia, hallazgo = plantilla_automatica(imagen, lector, id=ident, nombre=nombre)
        if hallazgo["items"] == 0:
            raise _error(
                422,
                "sin_items",
                "No encontré preguntas «Sí ( ) No ( )» ni celdas numeradas en la foto. Prueba con "
                "una foto más derecha, con buena luz y la hoja completa.",
            )
        ok, png = cv2.imencode(".png", limpia)
        if not ok:
            raise _error(500, "imagen", "No se pudo guardar la imagen de la plantilla.")
        inst = plantillas.instalar_nueva(
            definicion, {definicion["paginas"][0]["imagen_referencia"]: png.tobytes()}
        )
        return {**resumen(inst), "secciones": hallazgo["secciones"], "tipo": hallazgo["tipo"]}

    @app.post("/api/plantillas/{id}/libro", status_code=201)
    def poner_libro_de_excel(id: str, archivo: Annotated[UploadFile, File()]) -> dict:
        """VD-R3: el libro de Excel de la usuaria pasa a ser el molde de la salida (versión nueva)."""
        instalada(id)
        datos = archivo.file.read(MAX_FOTO + 1)
        if len(datos) > MAX_FOTO:
            raise _error(413, "demasiado_grande", "El libro supera el máximo de 25 MB.")
        if not (archivo.filename or "").lower().endswith(".xlsx"):
            raise _error(422, "no_es_xlsx", "El libro debe ser un archivo de Excel (.xlsx).")
        try:
            inst, vaciar = plantillas.poner_libro(id, datos)
        except LibroBaseInvalido as e:
            raise _error(422, "libro_base_invalido", str(e)) from e
        except PlantillaYaInstalada as e:
            raise _error(409, "plantilla_ya_instalada", str(e)) from e
        return {**resumen(inst), "vaciar": vaciar}

    @app.post("/api/plantillas/{id}/paginas", status_code=201)
    def agregar_pagina_desde_foto(id: str, foto: Annotated[UploadFile, File()]) -> dict:
        """Una página más para la plantilla (el reverso de una hoja), armada desde otra foto."""
        base = instalada(id)
        if not isinstance(lector, LectorONNX):
            raise _error(
                409,
                "ocr_no_disponible",
                "Armar una página desde una foto necesita el lector de texto (OCR), que esta "
                "instalación no tiene activado.",
            )
        datos = foto.file.read(MAX_FOTO + 1)
        if len(datos) > MAX_FOTO:
            raise _error(413, "demasiado_grande", "La foto supera el máximo de 25 MB.")
        try:
            imagen = cargar_imagen(datos)
        except ImagenInvalida as e:
            raise _error(422, "foto_invalida", str(e)) from e
        p = base.plantilla
        filas = [f for pg in p.paginas for t in pg.tablas for f in t.filas]
        letras = {re.match(r"[A-Z]+", f.celda).group() for f in filas if f.celda}
        n = len(p.paginas) + 1
        definicion, limpia, hallazgo = plantilla_automatica(
            imagen,
            lector,
            id=id,
            nombre=p.nombre,
            primer_item=max((f.item for f in filas), default=0) + 1,
            primera_columna=len(letras),
            imagen=f"{id}-p{n}.png",
        )
        if hallazgo["items"] == 0:
            raise _error(
                422,
                "sin_items",
                "No encontré preguntas ni celdas numeradas en esa foto. Prueba con una foto más "
                "derecha, con buena luz y la hoja completa.",
            )
        ok, png = cv2.imencode(".png", limpia)
        if not ok:
            raise _error(500, "imagen", "No se pudo guardar la imagen de la página.")
        pagina = definicion["paginas"][0]
        try:
            inst = plantillas.agregar_pagina(id, pagina, png.tobytes())
        except PlantillaYaInstalada as e:
            raise _error(409, "plantilla_ya_instalada", str(e)) from e
        return {**resumen(inst), "items_nuevos": hallazgo["items"], "tipo": hallazgo["tipo"]}

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
    _fijar_tipos_estaticos()
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
