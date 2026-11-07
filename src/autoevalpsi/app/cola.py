"""AP-R1: cola de procesamiento con un único trabajador (AP-04).

OpenCV y el OCR son CPU intensivos: correrlos dentro de la petición congelaría el servidor y, con
varias fotos a la vez, saturaría la laptop. La petición solo valida y encola; **un** hilo toma las
fotos de a una (así el lector OCR, que no es reentrante, nunca se usa en paralelo) y deja el
estado de cada trabajo a la vista: `en_cola` → `procesando` → `lista` | `error`.

Un fallo de la foto (`ValueError`: ilegible, sin hoja, plantilla que no cuadra) deja el trabajo en
`error` con un mensaje apto para la usuaria; cualquier otro fallo es un error del programa: se
registra en el log y se informa con un mensaje genérico, y el trabajador sigue vivo.
"""

import logging
import queue
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from autoevalpsi.core.tiempo import ahora_bolivia

log = logging.getLogger(__name__)

ESTADOS = ("en_cola", "procesando", "lista", "error")
MAX_PENDIENTES = 50  # más allá, el celular recibe 503 en vez de acumular fotos en memoria
MAX_HISTORIAL = 200


class ColaLlena(Exception):
    pass


class FotoEnProceso(Exception):
    """La misma foto (por SHA-256) ya está en la cola: p. ej. un doble toque en el celular."""


@dataclass
class Trabajo:
    id: str
    sha256: str
    evaluacion_id: str
    pagina: int
    plantilla_id: str
    problemas_calidad: tuple[str, ...]
    creado_en: str
    estado: str = "en_cola"
    mensaje: str = ""
    requiere_revision: bool | None = None  # se sabe al terminar bien

    def a_dict(self) -> dict:
        return {
            "id": self.id,
            "estado": self.estado,
            "evaluacion_id": self.evaluacion_id,
            "pagina": self.pagina,
            "plantilla_id": self.plantilla_id,
            "problemas_calidad": list(self.problemas_calidad),
            "creado_en": self.creado_en,
            "mensaje": self.mensaje,
            "requiere_revision": self.requiere_revision,
        }


@dataclass
class _Tarea:
    trabajo: Trabajo
    datos: object = field(repr=False)


class ColaProcesamiento:
    """`ejecutar(trabajo, datos)` hace el trabajo pesado y devuelve si requiere revisión."""

    def __init__(
        self,
        ejecutar: Callable[[Trabajo, object], bool],
        *,
        maximo: int = MAX_PENDIENTES,
    ) -> None:
        self._ejecutar = ejecutar
        self._cola: queue.Queue[_Tarea | None] = queue.Queue(maxsize=maximo)
        self._trabajos: OrderedDict[str, Trabajo] = OrderedDict()
        self._en_vuelo: set[str] = set()
        self._candado = threading.Condition()
        self._pendientes = 0
        self._hilo: threading.Thread | None = None
        self._siguiente = 0

    # --- ciclo de vida ------------------------------------------------------------------

    def iniciar(self) -> None:
        with self._candado:
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._hilo = threading.Thread(target=self._bucle, name="cola-fotos", daemon=True)
            self._hilo.start()

    def detener(self, timeout: float = 5.0) -> None:
        """Termina lo que está procesando y para; lo que siga en cola se descarta."""
        with self._candado:
            hilo = self._hilo
        if hilo is None:
            return
        try:
            while True:  # vaciar para que el centinela entre
                self._cola.get_nowait()
                self._terminar_pendiente()
        except queue.Empty:
            pass
        self._cola.put(None)
        hilo.join(timeout)
        with self._candado:
            self._hilo = None

    # --- uso ----------------------------------------------------------------------------

    def encolar(
        self,
        datos: object,
        *,
        sha256: str,
        evaluacion_id: str,
        pagina: int,
        plantilla_id: str,
        problemas_calidad: tuple[str, ...] = (),
    ) -> Trabajo:
        with self._candado:
            if sha256 in self._en_vuelo:
                raise FotoEnProceso(sha256)
            self._siguiente += 1
            trabajo = Trabajo(
                id=f"t{self._siguiente}",
                sha256=sha256,
                evaluacion_id=evaluacion_id,
                pagina=pagina,
                plantilla_id=plantilla_id,
                problemas_calidad=problemas_calidad,
                creado_en=ahora_bolivia().isoformat(timespec="seconds"),
            )
            try:
                self._cola.put_nowait(_Tarea(trabajo, datos))
            except queue.Full:
                raise ColaLlena from None
            self._en_vuelo.add(sha256)
            self._pendientes += 1
            self._trabajos[trabajo.id] = trabajo
            self._recortar_historial()
        self.iniciar()
        return trabajo

    def trabajo(self, id: str) -> Trabajo | None:
        with self._candado:
            return self._trabajos.get(id)

    def estado(self) -> dict:
        with self._candado:
            trabajos = list(self._trabajos.values())
        cuenta = {e: sum(1 for t in trabajos if t.estado == e) for e in ESTADOS}
        return {"pendientes": cuenta["en_cola"] + cuenta["procesando"], **cuenta,
                "trabajos": [t.a_dict() for t in reversed(trabajos)]}  # fmt: skip

    def esperar(self, timeout: float = 30.0) -> bool:
        """Espera a que no quede nada pendiente (para pruebas y para cerrar la app)."""
        with self._candado:
            return self._candado.wait_for(lambda: self._pendientes == 0, timeout)

    # --- interno ------------------------------------------------------------------------

    def _recortar_historial(self) -> None:
        for id in list(self._trabajos):
            if len(self._trabajos) <= MAX_HISTORIAL:
                break
            if self._trabajos[id].estado in ("lista", "error"):
                del self._trabajos[id]

    def _terminar_pendiente(self) -> None:
        with self._candado:
            self._pendientes -= 1
            self._candado.notify_all()

    def _bucle(self) -> None:
        while (tarea := self._cola.get()) is not None:
            t = tarea.trabajo
            with self._candado:
                t.estado = "procesando"
            try:
                revision = self._ejecutar(t, tarea.datos)
                resultado = ("lista", "", revision)
            except ValueError as e:
                resultado = ("error", str(e), None)
            except Exception:
                log.exception("fallo inesperado procesando %s", t.id)
                resultado = (
                    "error",
                    "Ocurrió un error inesperado al leer la foto. Vuelve a intentarlo.",
                    None,
                )
            with self._candado:
                t.estado, t.mensaje, t.requiere_revision = resultado
                self._en_vuelo.discard(t.sha256)
            self._terminar_pendiente()
