"""OC-R1: interfaz del lector OCR.

`Lector.leer(imagen)` devuelve las líneas de texto que ve en la imagen, en orden de lectura
(de arriba abajo, de izquierda a derecha). El pipeline (OC-R2) depende solo de esta interfaz, de
modo que el plan B (un modelo más grande, por lotes) se enchufa sin tocarlo, y las pruebas rápidas
usan `LectorFalso`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class Caja:
    """Rectángulo en píxeles de la imagen leída: `(x0, y0)` arriba-izquierda, `(x1, y1)` abajo-derecha."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def ancho(self) -> int:
        return self.x1 - self.x0

    @property
    def alto(self) -> int:
        return self.y1 - self.y0

    @property
    def centro_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Linea:
    """Una línea de texto leída: lo que dice, qué tan segura está (0–1) y dónde está."""

    texto: str
    confianza: float
    caja: Caja


@runtime_checkable
class Lector(Protocol):
    def leer(self, imagen: np.ndarray) -> list[Linea]:
        """Líneas de texto de `imagen` (BGR o gris, uint8), en orden de lectura."""
        ...


class LectorFalso:
    """Lector de prueba: devuelve las líneas que se le dieron, o falla si se le pide.

    `lineas` puede ser una lista fija (se devuelve la misma en cada llamada) o una función que
    recibe la imagen y devuelve las líneas (para simular una respuesta según el recorte).
    Registra cada imagen recibida en `llamadas`.
    """

    def __init__(
        self,
        lineas: Sequence[Linea] | Callable[[np.ndarray], Sequence[Linea]] = (),
        error: Exception | None = None,
    ):
        self._lineas = lineas
        self._error = error
        self.llamadas: list[np.ndarray] = []

    def leer(self, imagen: np.ndarray) -> list[Linea]:
        self.llamadas.append(imagen)
        if self._error is not None:
            raise self._error
        if callable(self._lineas):
            return list(self._lineas(imagen))
        return list(self._lineas)


def ordenar_lectura(lineas: Sequence[Linea]) -> list[Linea]:
    """Orden de lectura: agrupa por renglón (centros verticales cercanos) y ordena por x dentro."""
    por_y = sorted(lineas, key=lambda li: li.caja.centro_y)
    renglones: list[list[Linea]] = []
    for li in por_y:
        if renglones:
            ref = renglones[-1][0].caja
            if abs(li.caja.centro_y - ref.centro_y) <= 0.5 * min(li.caja.alto, ref.alto):
                renglones[-1].append(li)
                continue
        renglones.append([li])
    return [li for r in renglones for li in sorted(r, key=lambda li: li.caja.x0)]
