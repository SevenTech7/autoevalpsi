"""Actualizar la aplicación desde un Release público de GitHub, solo cuando la usuaria lo pide.

Nada corre solo: no hay tarea programada ni consulta al arrancar. El botón «Buscar actualización»
(Configuración) consulta el último Release, y si hay una versión más nueva la descarga en segundo
plano, comprueba su SHA-256 y, con la confirmación de la usuaria, lanza el instalador (que cierra
la app, instala encima y la vuelve a abrir). Los datos viven en `%LOCALAPPDATA%` y no se tocan.

Límites de confianza: solo se habla con `api.github.com` y solo se baja el instalador y su suma de
control de ESE repositorio, por HTTPS. La suma detecta descargas dañadas, no un Release comprometido.
"""

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)

REPOSITORIO = "SevenTech7/autoevalpsi"
URL_ULTIMO = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
HOSTS_PERMITIDOS = ("api.github.com", "github.com", "objects.githubusercontent.com")
PATRON_INSTALADOR = re.compile(r"^AutoEvalPsi-Instalador-(\d+\.\d+\.\d+)\.exe$")
TIEMPO_ESPERA = 20  # segundos sin respuesta de la red
TROZO = 1024 * 256


class ErrorActualizacion(Exception):
    """Algo falló con un mensaje que la usuaria puede leer."""


def version_instalada() -> str:
    try:
        return version("autoevalpsi")
    except PackageNotFoundError:
        return "0.0.0"


def _tupla(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def es_mas_nueva(candidata: str, actual: str) -> bool:
    try:
        return _tupla(candidata) > _tupla(actual)
    except ValueError:  # versión de desarrollo («0.1.0+local»): nunca se actualiza sola
        return False


@dataclass(frozen=True)
class Novedad:
    version: str
    notas: str
    url_instalador: str
    url_suma: str
    tamano: int


def _https_permitido(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in HOSTS_PERMITIDOS


def _abrir_url(url: str):  # pragma: no cover - red real
    if not _https_permitido(url):
        raise ErrorActualizacion("Dirección de descarga no permitida.")
    pedido = urllib.request.Request(url, headers={"User-Agent": "AutoEvalPsi"})
    return urllib.request.urlopen(pedido, timeout=TIEMPO_ESPERA)


def _lanzar_instalador(ruta: Path) -> None:  # pragma: no cover - solo Windows
    """`os.startfile` pasa por ShellExecute: pide la elevación (UAC) que el instalador necesita."""
    os.startfile(ruta, arguments="/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /REABRIR")


class Actualizador:
    """Estado de la búsqueda y la descarga. `abrir` y `lanzar` se inyectan para probar sin red."""

    def __init__(
        self,
        carpeta: Path,
        *,
        actual: str | None = None,
        abrir: Callable[[str], object] = _abrir_url,
        lanzar: Callable[[Path], None] = _lanzar_instalador,
    ) -> None:
        self._carpeta = carpeta
        self._actual = actual or version_instalada()
        self._abrir = abrir
        self._lanzar = lanzar
        self._candado = threading.RLock()
        self._estado = "libre"  # libre | descargando | lista | error
        self._novedad: Novedad | None = None
        self._buscada = False
        self._bajado = 0
        self._mensaje = ""
        self._ruta: Path | None = None

    # --- consulta --------------------------------------------------------------------------
    def estado(self) -> dict:
        with self._candado:
            return {
                "actual": self._actual,
                "buscada": self._buscada,
                "novedad": asdict(self._novedad) if self._novedad else None,
                "estado": self._estado,
                "bajado": self._bajado,
                "mensaje": self._mensaje,
            }

    def buscar(self) -> dict:
        """Consulta el último Release. Lanza `ErrorActualizacion` si no hay red o la respuesta
        no es la esperada."""
        with self._candado:
            if self._estado == "descargando":
                return self.estado()
        try:
            with self._abrir(URL_ULTIMO) as r:  # type: ignore[attr-defined]
                datos = json.loads(r.read(2_000_000).decode("utf-8"))
        except ErrorActualizacion:
            raise
        except Exception as e:
            log.warning("No se pudo consultar las actualizaciones: %s", e)
            raise ErrorActualizacion(
                "No se pudo consultar si hay una versión nueva. Revisa la conexión a internet "
                "e inténtalo de nuevo."
            ) from e
        novedad = self._leer_release(datos)
        with self._candado:
            self._buscada = True
            self._novedad = novedad
            if self._estado in ("lista", "error"):
                self._estado, self._mensaje, self._ruta = "libre", "", None
        return self.estado()

    def _leer_release(self, datos: dict) -> Novedad | None:
        etiqueta = str(datos.get("tag_name", "")).lstrip("v")
        if not es_mas_nueva(etiqueta, self._actual):
            return None
        instalador = suma = None
        for a in datos.get("assets", []):
            m = PATRON_INSTALADOR.match(str(a.get("name", "")))
            if m and m.group(1) == etiqueta:
                instalador = a
            elif a.get("name") == f"AutoEvalPsi-Instalador-{etiqueta}.exe.sha256":
                suma = a
        if not instalador or not suma:
            raise ErrorActualizacion(
                f"La versión {etiqueta} todavía no tiene su instalador publicado. Inténtalo más tarde."
            )
        urls = (instalador.get("browser_download_url", ""), suma.get("browser_download_url", ""))
        if not all(_https_permitido(u) for u in urls):
            raise ErrorActualizacion("La descarga de la versión nueva no es de un sitio permitido.")
        return Novedad(
            version=etiqueta,
            notas=str(datos.get("body") or "")[:2000],
            url_instalador=urls[0],
            url_suma=urls[1],
            tamano=int(instalador.get("size") or 0),
        )

    # --- descarga --------------------------------------------------------------------------
    def descargar(self) -> dict:
        """Empieza a bajar el instalador en segundo plano (no bloquea la petición)."""
        with self._candado:
            if self._estado == "descargando":
                return self.estado()
            if self._novedad is None:
                raise ErrorActualizacion("Primero busca si hay una versión nueva.")
            self._estado, self._bajado, self._mensaje, self._ruta = "descargando", 0, "", None
            novedad = self._novedad
        threading.Thread(target=self._bajar, args=(novedad,), daemon=True).start()
        return self.estado()

    def _bajar(self, novedad: Novedad) -> None:
        try:
            ruta = self._descargar_verificado(novedad)
        except Exception as e:  # noqa: BLE001 - se informa a la usuaria, no se pierde el hilo
            log.warning("Falló la descarga de la actualización: %s", e)
            mensaje = (
                str(e)
                if isinstance(e, ErrorActualizacion)
                else "No se pudo descargar la versión nueva. Revisa la conexión e inténtalo de nuevo."
            )
            with self._candado:
                self._estado, self._mensaje = "error", mensaje
            return
        with self._candado:
            self._estado, self._ruta = "lista", ruta

    def _descargar_verificado(self, novedad: Novedad) -> Path:
        self._carpeta.mkdir(parents=True, exist_ok=True)
        for viejo in self._carpeta.glob("AutoEvalPsi-Instalador-*"):
            viejo.unlink(missing_ok=True)
        with self._abrir(novedad.url_suma) as r:  # type: ignore[attr-defined]
            esperada = r.read(4096).decode("ascii", "ignore").split()[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", esperada):
            raise ErrorActualizacion("El archivo de control de la versión nueva no es válido.")
        destino = self._carpeta / f"AutoEvalPsi-Instalador-{novedad.version}.exe"
        parcial = destino.with_suffix(".parcial")
        suma = hashlib.sha256()
        with self._abrir(novedad.url_instalador) as r, parcial.open("wb") as f:  # type: ignore[attr-defined]
            while trozo := r.read(TROZO):
                f.write(trozo)
                suma.update(trozo)
                with self._candado:
                    self._bajado += len(trozo)
        if suma.hexdigest() != esperada:
            parcial.unlink(missing_ok=True)
            raise ErrorActualizacion(
                "La descarga llegó dañada (no coincide con la suma de control). Inténtalo de nuevo."
            )
        parcial.replace(destino)
        return destino

    # --- instalación -----------------------------------------------------------------------
    def instalar(self) -> None:
        with self._candado:
            if self._estado != "lista" or self._ruta is None or not self._ruta.is_file():
                raise ErrorActualizacion("La versión nueva todavía no está descargada.")
            ruta = self._ruta
        try:
            self._lanzar(ruta)
        except OSError as e:
            log.warning("No se pudo lanzar el instalador: %s", e)
            raise ErrorActualizacion(
                "Windows no abrió el instalador (¿cancelaste el permiso de administrador?). "
                "La app sigue como estaba; puedes intentarlo otra vez."
            ) from e

    def limpiar(self) -> None:
        shutil.rmtree(self._carpeta, ignore_errors=True)


__all__ = ["Actualizador", "ErrorActualizacion", "Novedad", "es_mas_nueva", "version_instalada"]
