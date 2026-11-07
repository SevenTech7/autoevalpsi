"""CO-R7: imagen de depuración — la hoja enderezada con la cuadrícula y cada celda coloreada.

Colores (BGR) por celda:

- **verde**: opción elegida y la fila sin banderas;
- **amarillo**: opción elegida con alguna bandera (hay que mirarla);
- **naranja**: celda con tinta sobre `tinta_minima` que *no* quedó elegida (doble marca, tachón);
- sin relleno: celda vacía.

Las filas sin marca llevan un borde rojo en toda la fila. La cuadrícula va en azul y el número del
ítem a la izquierda de cada fila. Es solo una ayuda para el desarrollador y para calibrar.
"""

from collections.abc import Iterable

import cv2
import numpy as np

from autoevalpsi.core.casillas import BANDERA_SIN_MARCA, ResultadoFila
from autoevalpsi.core.plantilla import Plantilla
from autoevalpsi.core.registro import Registro

VERDE = (60, 170, 60)
AMARILLO = (0, 215, 255)
NARANJA = (0, 140, 255)
ROJO = (0, 0, 220)
AZUL = (200, 90, 0)


def _relleno(
    imagen: np.ndarray, caja: tuple[int, int, int, int], color, alfa: float = 0.35
) -> None:
    x0, y0, x1, y1 = caja
    zona = imagen[y0:y1, x0:x1]
    imagen[y0:y1, x0:x1] = cv2.addWeighted(zona, 1 - alfa, np.full_like(zona, color), alfa, 0)


def dibujar_depuracion(
    registro: Registro,
    plantilla: Plantilla,
    filas: Iterable[ResultadoFila],
    *,
    pagina: int = 0,
) -> np.ndarray:
    """Devuelve una copia BGR de la hoja registrada con la lectura superpuesta."""
    img = registro.imagen.copy()
    por_item = {f.item: f for f in filas}
    minima = plantilla.omr.tinta_minima
    grosor = max(1, round(min(img.shape[:2]) / 700))
    escala_texto = max(0.5, min(img.shape[:2]) / 1800)

    for tabla in plantilla.paginas[pagina].tablas:
        for fila in tabla.filas:
            res = por_item.get(fila.item)
            if res is None:
                continue
            y0, y1 = fila.y
            for k, (x0, x1) in enumerate(tabla.columnas_x):
                caja = (x0, y0, x1, y1)
                if res.opcion == tabla.opciones[k]:
                    _relleno(img, caja, VERDE if res.ok else AMARILLO)
                elif res.proporciones[k] >= minima:
                    _relleno(img, caja, NARANJA)
                cv2.rectangle(img, (x0, y0), (x1, y1), AZUL, grosor)
            if BANDERA_SIN_MARCA in res.banderas:
                x_ini, x_fin = tabla.columnas_x[0][0], tabla.columnas_x[-1][1]
                cv2.rectangle(img, (x_ini, y0), (x_fin, y1), ROJO, grosor * 2)
            cv2.putText(
                img,
                str(fila.item),
                (max(tabla.columnas_x[0][0] - int(70 * escala_texto * 2), 0), (y0 + y1) // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                escala_texto,
                AZUL,
                grosor,
                cv2.LINE_AA,
            )
    return img
