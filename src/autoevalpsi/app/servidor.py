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
    POST /api/evaluaciones/{id}/exportar     a Excel; 409 si hay algo sin revisar (AP-06)
    GET  /api/plantillas[/{id}]              plantillas instaladas
    POST /api/plantillas/importar            .zip con el .json y las imágenes en blanco (PL-D2)
    GET  /api/captura/enlace[?ip=]           URL de captura, su QR (SVG) y las IP posibles (AP-02)
    GET  /captura?token=                     página del celular (HTML); AP-R2, AP-07

**Token (AP-03).** Cada arranque genera uno de 128 bits; todo `/api` salvo `/api/salud` lo exige,
en `Authorization: Bearer <token>`, `X-Token` o `?token=` (la URL del QR). Se compara en tiempo
constante y se revisa **antes** de leer el cuerpo. Las subidas llevan tope de tamaño (25 MB las
fotos) comprobado sobre `Content-Length`; la foto se reconoce por sus bytes (JPEG/PNG), no por lo
que declare el celular.

Varias fotos de un mismo formulario (PL-03): se sube cada una con la misma `evaluacion` (el id lo
elige quien sube, p. ej. la página del celular) y su `pagina` (0-based).

El control de calidad (rápido) se responde en la misma petición; la lectura pesada va a la cola
(`app/cola.py`) y la respuesta es `202` con el trabajo.
"""

import hashlib
import html
import json
import logging
import secrets
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

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
_SIN_TOKEN = {"/api/salud"}
PUERTO = 8765
PAGINA_CAPTURA = Path(__file__).parent / "captura" / "index.html"


def _error(status: int, codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(status, {"codigo": codigo, "mensaje": mensaje})


def _respuesta(status: int, codigo: str, mensaje: str) -> JSONResponse:
    return JSONResponse({"detail": {"codigo": codigo, "mensaje": mensaje}}, status_code=status)


class Guardia:
    """ASGI: token y tope de tamaño antes de que nadie lea el cuerpo de la petición."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._token = token.encode()

    def _token_valido(self, scope) -> bool:
        cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        candidatos = [cabeceras.get("x-token", "")]
        auth = cabeceras.get("authorization", "")
        if auth.lower().startswith("bearer "):
            candidatos.append(auth[7:].strip())
        candidatos += parse_qs(scope.get("query_string", b"").decode("latin-1")).get("token", [])
        return any(secrets.compare_digest(c.encode(), self._token) for c in candidatos if c)

    async def __call__(self, scope, receive, send) -> None:
        ruta = scope["path"].rstrip("/") if scope["type"] == "http" else ""
        if scope["type"] != "http" or not (ruta.startswith("/api") or ruta == RUTA_CAPTURA):
            return await self.app(scope, receive, send)
        if ruta not in _SIN_TOKEN and not self._token_valido(scope):
            r = _respuesta(401, "sin_token", "Esta página necesita el código QR de la aplicación.")
            return await r(scope, receive, send)
        if scope["method"] in ("POST", "PUT", "PATCH"):
            cabeceras = dict(scope["headers"])
            largo = cabeceras.get(b"content-length")
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


class PedidoExportar(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carpeta: str | None = None  # por defecto: la configurada o `<raíz>/exportaciones`
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
) -> FastAPI:
    """`lector` (OCR) es opcional: sin él solo se leen las casillas. `app.state.token` es el
    token del arranque y `app.state.cola` la cola, por si quien arranca los necesita. `puerto` e
    `interfaces` (IP de la red local, AP-02) arman la URL del QR."""
    token = token or secrets.token_urlsafe(16)

    def ejecutar(trabajo: Trabajo, subida: object) -> bool:
        assert isinstance(subida, _Subida)
        inst = plantillas.obtener(subida.plantilla_id, subida.plantilla_version)
        referencia = plantillas.referencia(inst, trabajo.pagina)
        proc = procesar_foto(
            subida.foto, inst.plantilla, referencia, pagina=trabajo.pagina, lector=lector
        )
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
    app.add_middleware(Guardia, token=token)
    app.state.token = token
    app.state.cola = cola

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
        carpeta = Path(
            pedido.carpeta
            or bd.leer_configuracion("carpeta_exportacion")
            or bd.raiz / "exportaciones"
        )
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
        return {"evaluacion": str(archivos.evaluacion), "consolidado": str(archivos.consolidado)}

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

    # --- captura desde el celular (AP-R2) -----------------------------------------------

    @app.get("/api/captura/enlace")
    def enlace_captura(ip: str | None = None) -> dict:
        """`ip` opcional: la que la usuaria eligió de `ips`; si no sirve se usa la mejor."""
        lista = candidatas(interfaces())
        elegida = elegir_ip(lista, ip)
        if elegida is None:
            return {"url": None, "qr_svg": None, "ip": None, "puerto": puerto, "ips": [],
                    "mensaje": "La laptop no está en una red WiFi o cable con IP privada. "
                               "Conéctala al WiFi de la casa."}  # fmt: skip
        url = url_captura(elegida, puerto, token)
        return {"url": url, "qr_svg": qr_svg(url), "ip": elegida, "puerto": puerto,
                "ips": [i.ip for i in lista], "mensaje": ""}  # fmt: skip

    @app.get(RUTA_CAPTURA, response_class=HTMLResponse)
    def pagina_captura() -> HTMLResponse:
        """La página del celular: HTML liviano sin build (AP-07). El token ya lo validó la
        `Guardia`; se incrusta el mismo para que la página llame a la API."""
        instaladas = plantillas.listar()
        ultimas = {}
        for i in instaladas:  # la versión más nueva de cada id (`listar` ordena por id y versión)
            ultimas[i.plantilla.id] = i.plantilla
        opciones = (
            "\n".join(
                f'<option value="{html.escape(p.id)}">{html.escape(p.nombre)}</option>'
                for p in ultimas.values()
            )
            or '<option value="" disabled selected>Sin formularios instalados</option>'
        )
        paginas = {p.id: len(p.paginas) for p in ultimas.values()}
        cuerpo = (
            PAGINA_CAPTURA.read_text(encoding="utf-8")
            .replace("{{OPCIONES}}", opciones)
            .replace("{{PAGINAS}}", html.escape(json.dumps(paginas), quote=True))
            .replace("{{TOKEN_URL}}", html.escape(quote(token, safe=""), quote=True))
            .replace("{{TOKEN}}", html.escape(token, quote=True))
        )
        return HTMLResponse(
            cuerpo, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
        )

    return app
