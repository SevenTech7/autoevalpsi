"""AP-R3: ventana de escritorio (AP-08).

Arranca el servidor de `app/servidor.py` con uvicorn en un hilo, espera a que responda, abre la
ventana (pywebview, WebView2 en Windows) y lo cierra ordenadamente. El servidor escucha solo en
`127.0.0.1` y en las IP privadas de la laptop (AP-03), nunca en `0.0.0.0`.

Instancia única: el puerto es el candado. Si ya está tomado, se mira `/api/salud`; si responde,
es otra AutoEvalPsi (`AplicacionYaAbierta`), si no, otro programa (`PuertoOcupado`). En Windows el
socket se abre con `SO_EXCLUSIVEADDRUSE` para que otro proceso no pueda colarse en el mismo puerto.

La ventana real no se prueba en CI: `abrir_ventana` queda fuera de las pruebas.
"""

import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.red import candidatas, listar_interfaces
from autoevalpsi.app.servidor import PUERTO, crear_app
from autoevalpsi.core.ocr.lector import Lector

log = logging.getLogger(__name__)

LOCAL = "127.0.0.1"
CLAVE_CARPETA_EXPORTACION = "carpeta_exportacion"
TITULO = "AutoEvalPsi"


class ErrorArranque(Exception):
    """El mensaje es apto para mostrarlo a la usuaria."""


class AplicacionYaAbierta(ErrorArranque):
    def __init__(self) -> None:
        super().__init__("AutoEvalPsi ya está abierta. Búscala en la barra de tareas.")


class PuertoOcupado(ErrorArranque):
    def __init__(self, puerto: int) -> None:
        super().__init__(
            f"El puerto {puerto} lo usa otro programa y AutoEvalPsi no puede arrancar. "
            "Cierra el otro programa o reinicia la laptop."
        )


def _abrir_socket(host: str, puerto: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, puerto))
    except OSError:
        s.close()
        raise
    return s


def _responde_salud(puerto: int, espera: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{LOCAL}:{puerto}/api/salud", timeout=espera) as r:
            return json.loads(r.read()).get("ok") is True
    except (OSError, ValueError):
        return False


class ServidorLocal:
    """uvicorn en un hilo. `iniciar()` bloquea hasta que responde; `detener()` lo cierra."""

    def __init__(self, app: FastAPI, puerto: int = PUERTO, ips: list[str] | None = None) -> None:
        self._app = app
        self._puerto = puerto
        self._ips = list(ips or [])
        self._servidor: uvicorn.Server | None = None
        self._hilo: threading.Thread | None = None
        self._sockets: list[socket.socket] = []
        self.puerto = puerto  # el real, por si se pidió 0
        self.ips_escuchadas: list[str] = []

    def iniciar(self, espera: float = 15.0) -> None:
        try:
            principal = _abrir_socket(LOCAL, self._puerto)
        except OSError:
            if self._puerto and _responde_salud(self._puerto):
                raise AplicacionYaAbierta() from None
            raise PuertoOcupado(self._puerto) from None
        self._sockets = [principal]
        self.puerto = principal.getsockname()[1]
        self.ips_escuchadas = [LOCAL]
        for ip in self._ips:
            try:
                self._sockets.append(_abrir_socket(ip, self.puerto))
                self.ips_escuchadas.append(ip)
            except OSError as e:  # la IP pudo desaparecer; la ventana sigue funcionando
                log.warning("No se pudo escuchar en %s:%s (%s)", ip, self.puerto, e)

        config = uvicorn.Config(
            self._app,
            log_level="warning",
            lifespan="on",
            log_config=None,  # el formateador de uvicorn llama a sys.stderr.isatty(): sin consola es None
        )
        self._servidor = uvicorn.Server(config)
        self._hilo = threading.Thread(
            target=self._servidor.run, kwargs={"sockets": self._sockets}, daemon=True
        )
        self._hilo.start()

        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if self._servidor.started and _responde_salud(self.puerto):
                return
            if not self._hilo.is_alive():
                break
            time.sleep(0.05)
        self.detener()
        raise ErrorArranque("El servidor interno no arrancó. Cierra y vuelve a abrir AutoEvalPsi.")

    def detener(self, espera: float = 10.0) -> None:
        if self._servidor is not None:
            self._servidor.should_exit = True
        if self._hilo is not None:
            self._hilo.join(timeout=espera)
        for s in self._sockets:
            s.close()
        self._sockets = []
        self._servidor = None
        self._hilo = None


class Puente:
    """Lo que la página de la ventana puede pedir al escritorio (`window.pywebview.api`).

    `dialogo` recibe la carpeta inicial y devuelve la elegida o None; `abrir` muestra una carpeta
    en el Explorador. Ambos se inyectan para probar sin ventana."""

    def __init__(
        self,
        bd: BaseDatos,
        dialogo: Callable[[str], str | None],
        abrir: Callable[[Path], None] | None = None,
    ) -> None:
        self._bd = bd
        self._dialogo = dialogo
        self._abrir = abrir or _abrir_en_explorador

    def elegir_carpeta_exportacion(self) -> str | None:
        """Diálogo nativo; si la usuaria elige, queda guardada para AP-R6. None si cancela."""
        actual = self._bd.leer_configuracion(CLAVE_CARPETA_EXPORTACION, "") or ""
        elegida = self._dialogo(actual)
        if not elegida:
            return None
        self._bd.guardar_configuracion(CLAVE_CARPETA_EXPORTACION, str(Path(elegida)))
        return str(Path(elegida))

    def abrir_carpeta(self, ruta: str) -> bool:
        """Muestra una carpeta en el Explorador (AP-R6). Solo carpetas que existen: nunca ejecuta
        un archivo. False si no se pudo."""
        carpeta = Path(ruta)
        if not ruta or not carpeta.is_dir():
            return False
        try:
            self._abrir(carpeta)
        except OSError as e:
            log.warning("No se pudo abrir %s (%s)", carpeta, e)
            return False
        return True


def _abrir_en_explorador(carpeta: Path) -> None:  # pragma: no cover - solo Windows
    if os.name == "nt":
        os.startfile(carpeta)


def avisar(mensaje: str) -> None:
    """Sin consola (PyInstaller `--windowed`) un `print` no lo ve nadie: cuadro de Windows.
    La usuaria no lee la consola; solo fuera de Windows (desarrollo) se escribe en ella."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, mensaje, TITULO, 0x10)
    else:
        print(mensaje, file=sys.stderr)


def abrir_ventana(url: str, bd: BaseDatos) -> None:  # pragma: no cover - ventana real
    """Bloquea hasta que se cierra la ventana (o `webview.start` falla)."""
    import webview

    ventana: list = []

    def dialogo(inicial: str) -> str | None:
        elegida = ventana[0].create_file_dialog(webview.FileDialog.FOLDER, directory=inicial)
        return elegida[0] if elegida else None

    ventana.append(
        webview.create_window(TITULO, url, js_api=Puente(bd, dialogo), width=1100, height=760)
    )
    webview.start()


def ejecutar(
    *,
    raiz: Path | None = None,
    puerto: int = PUERTO,
    lector: Lector | None = None,
    ventana: Callable[[str, BaseDatos], None] = abrir_ventana,
    mostrar_error: Callable[[str], None] = avisar,
) -> int:
    """Arranca todo, abre la ventana y cierra en orden. Devuelve el código de salida."""
    from autoevalpsi.app.datos import raiz_por_defecto

    raiz = Path(raiz) if raiz else raiz_por_defecto()
    bd = BaseDatos(raiz)
    plantillas = RepositorioPlantillas(raiz / "plantillas")
    ips = [i.ip for i in candidatas(listar_interfaces())]
    app = crear_app(bd, plantillas, lector=lector, puerto=puerto)
    servidor = ServidorLocal(app, puerto, ips)
    try:
        servidor.iniciar()
        url = f"http://{LOCAL}:{servidor.puerto}/?token={app.state.token}"
        ventana(url, bd)
        return 0
    except ErrorArranque as e:
        mostrar_error(str(e))
        return 2
    finally:
        servidor.detener()
        bd.cerrar()
