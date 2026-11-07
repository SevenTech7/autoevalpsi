"""Prueba manual en Docker (sin ventana): la interfaz en el navegador de la laptop y el celular
real por el WiFi. Solo para desarrollo; la app de verdad es `autoevalpsi abrir`.

Dentro de Docker no hay loopback real ni la IP del WiFi, y Docker reenvía todo con la IP de su
puente. Por eso se abren **dos puertos**: el de la laptop (compose lo publica solo en `127.0.0.1`
del anfitrión; aquí cuenta como «laptop») y el del celular (publicado a la red; trato de celular:
solo credencial vinculada). La IP del QR la da quien prueba (`--ip-lan`).
"""

import io
import socket
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

import uvicorn

from autoevalpsi.app.datos import BaseDatos, raiz_por_defecto
from autoevalpsi.app.plantillas import PlantillaYaInstalada, RepositorioPlantillas
from autoevalpsi.app.red import Interfaz
from autoevalpsi.app.servidor import crear_app
from autoevalpsi.core.ocr.lector import Lector


def instalar_demo(plantillas: RepositorioPlantillas, carpeta: Path) -> list[str]:
    """Instala las plantillas sintéticas de `plantillas_demo/`; las ya instaladas se saltan."""
    nuevas = []
    for json in sorted(carpeta.glob("*.json")):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.write(json, json.name)
            zf.write(json.with_suffix(".png"), json.with_suffix(".png").name)
        try:
            nuevas.append(plantillas.importar_zip(buffer.getvalue()).plantilla.id)
        except PlantillaYaInstalada:
            continue
    return nuevas


def _abrir_socket(puerto: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", puerto))  # dentro del contenedor; compose decide qué se publica
    s.listen(100)
    return s


def servir(
    *,
    ip_lan: str,
    puerto_laptop: int = 8765,
    puerto_celular: int = 8766,
    lector: Lector | None = None,
    demo: Path | None = None,
    raiz: Path | None = None,
) -> int:
    bd = BaseDatos(Path(raiz) if raiz else raiz_por_defecto())
    plantillas = RepositorioPlantillas(bd.raiz / "plantillas")
    if demo is not None:
        nuevas = instalar_demo(plantillas, demo)
        if nuevas:
            print("Plantillas de demostración instaladas:", ", ".join(nuevas))
    app = crear_app(
        bd,
        plantillas,
        lector=lector,
        puerto=puerto_celular,
        interfaces=lambda: [Interfaz(ip=ip_lan, nombre="WiFi", ruta_por_defecto=True)],
        puertos_laptop=frozenset({puerto_laptop}),
        guardar_fallidas=bd.raiz / "fallidas",
        carpeta_por_defecto=bd.raiz / "exportaciones",  # compose la une a Descargas de la laptop
    )
    sockets = [_abrir_socket(puerto_laptop), _abrir_socket(puerto_celular)]
    servidor = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="on"))
    hilo = threading.Thread(target=servidor.run, kwargs={"sockets": sockets}, daemon=True)
    hilo.start()
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{puerto_laptop}/api/salud", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    print(
        f"\nAbre en el navegador de la laptop:\n  http://localhost:{puerto_laptop}/?token={app.state.token}\n"
    )
    print(f"El celular entrará por http://{ip_lan}:{puerto_celular}/ (QR de la tarjeta «Celular»).")
    print("Ctrl+C para terminar.")
    try:
        while hilo.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        servidor.should_exit = True
        hilo.join(timeout=10)
        for s in sockets:
            s.close()
        bd.cerrar()
    return 0
