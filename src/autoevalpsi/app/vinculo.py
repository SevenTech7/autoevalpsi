"""AP-D2: vínculo del celular con la laptop.

La laptop solo acepta **un** celular, el que ella vinculó (reemplazable). El flujo:

1. Desde la ventana de la laptop (loopback + token de la app) se pide un **código de vínculo**:
   128 bits, de un solo uso, vence a los 5 minutos y va en el QR. Pedir otro anula el anterior.
2. El celular lee el QR, la página manda el código a `POST /api/vinculo` y recibe una
   **credencial** (256 bits) que guarda en su `localStorage` y manda en `X-Dispositivo`.
3. La base guarda solo la huella SHA-256 de la credencial. Vincular otro celular reemplaza la
   huella: el anterior recibe 403 y debe vincularse de nuevo.

Códigos y huella viven en memoria además de la base: la `Guardia` ASGI consulta la huella en
cada petición y no debe tocar SQLite (ni esperar el candado del trabajador de la cola).
"""

import hashlib
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from autoevalpsi.app.datos import BaseDatos

log = logging.getLogger(__name__)

VENCIMIENTO_CODIGO = 5 * 60.0  # segundos
_REGISTRO_USO = 60.0  # el «último uso» se escribe como mucho una vez por minuto


def huella(credencial: str) -> str:
    return hashlib.sha256(credencial.encode()).hexdigest()


@dataclass(frozen=True)
class CodigoVinculo:
    codigo: str
    vence_en: float  # segundos de validez que le quedan al emitirlo


class Vinculos:
    def __init__(
        self,
        bd: BaseDatos,
        *,
        reloj: Callable[[], float] = time.monotonic,
        vencimiento: float = VENCIMIENTO_CODIGO,
    ) -> None:
        self._bd = bd
        self._reloj = reloj
        self._vencimiento = vencimiento
        self._candado = threading.Lock()
        d = bd.leer_dispositivo()
        self._huella: str | None = d.huella if d else None
        self._codigo: tuple[str, float] | None = None  # (código, instante de vencimiento)
        self._ultimo_registro = float("-inf")

    @property
    def vinculado(self) -> bool:
        return self._huella is not None

    def iniciar(self) -> CodigoVinculo:
        """Código nuevo; el pendiente anterior (si lo hay) deja de servir."""
        with self._candado:
            codigo = secrets.token_urlsafe(16)
            self._codigo = (codigo, self._reloj() + self._vencimiento)
        return CodigoVinculo(codigo, self._vencimiento)

    def canjear(self, codigo: str) -> str | None:
        """Credencial nueva si el código sirve (y lo gasta); si no, None. Un código equivocado no
        gasta el pendiente: un intento ajeno no debe anular el QR de ella."""
        with self._candado:
            pendiente, self._codigo = self._codigo, None
            if pendiente is None or self._reloj() > pendiente[1]:
                return None
            if not secrets.compare_digest(codigo.encode(), pendiente[0].encode()):
                self._codigo = pendiente  # un intento ajeno no debe gastar el código de ella
                return None
            credencial = secrets.token_urlsafe(32)
            self._bd.guardar_dispositivo(huella(credencial))
            self._huella = huella(credencial)
            return credencial

    def credencial_valida(self, credencial: str) -> bool:
        actual = self._huella
        if actual is None or not credencial:
            return False
        if not secrets.compare_digest(huella(credencial).encode(), actual.encode()):
            return False
        ahora = self._reloj()
        if ahora - self._ultimo_registro >= _REGISTRO_USO:
            self._ultimo_registro = ahora
            try:
                self._bd.registrar_uso_dispositivo(actual)
            except Exception:  # un fallo al anotar el uso no debe tumbar la subida
                log.warning("No se pudo anotar el último uso del celular", exc_info=True)
        return True

    def olvidar(self) -> bool:
        with self._candado:
            self._huella = None
            self._codigo = None
        return self._bd.borrar_dispositivo()
