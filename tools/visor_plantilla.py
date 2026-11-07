"""PL-R1: superpone las cajas de una plantilla sobre su imagen de referencia.

    python -m tools.visor_plantilla plantillas/<id>/plantilla.json --salida control.png

Dibuja las cajas de cabecera (azul), cada celda de casilla (verde) con el número de ítem y la zona de
observación (naranja). Sirve para ver a ojo si todo cae donde toca antes de usar la plantilla.
"""

import argparse
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.plantilla import Plantilla, cargar_plantilla
from autoevalpsi.core.registro import cargar_referencia

AZUL, VERDE, NARANJA, ROJO = (200, 90, 0), (0, 150, 0), (0, 130, 255), (0, 0, 220)


def dibujar(plantilla: Plantilla, referencia: np.ndarray, pagina: int = 0) -> np.ndarray:
    """La referencia (gris) en color con las cajas de la página `pagina` dibujadas encima."""
    img = cv2.cvtColor(referencia, cv2.COLOR_GRAY2BGR)
    pg = plantilla.paginas[pagina]
    grosor = max(2, img.shape[1] // 800)
    for c in pg.cabecera:
        x0, y0, x1, y1 = c.caja
        cv2.rectangle(img, (x0, y0), (x1, y1), AZUL, grosor)
        cv2.putText(img, c.campo, (x0 + 6, y0 - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.0, AZUL, 2)
    for t in pg.tablas:
        for f in t.filas:
            for a, b in t.columnas_x:
                cv2.rectangle(img, (a, f.y[0]), (b, f.y[1]), VERDE, grosor)
            if t.observacion_x:
                a, b = t.observacion_x
                cv2.rectangle(img, (a, f.y[0]), (b, f.y[1]), NARANJA, grosor)
            cv2.putText(img, str(f.item), (t.columnas_x[0][0] - 70, (f.y[0] + f.y[1]) // 2 + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, ROJO, 3)  # fmt: skip
    return img


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("plantilla", help="Ruta al plantilla.json.")
    p.add_argument("--salida", required=True, help="PNG de control que se escribe.")
    p.add_argument("--pagina", type=int, default=0, help="Página (0-based).")
    args = p.parse_args(argv)
    ruta = Path(args.plantilla)
    plantilla = cargar_plantilla(ruta)
    pg = plantilla.paginas[args.pagina]
    ref = cargar_referencia(ruta, pg.imagen_referencia)
    if list(ref.shape[::-1]) != pg.tamano_px:
        print(f"Aviso: la imagen mide {ref.shape[::-1]} y tamano_px dice {pg.tamano_px}.")
    cv2.imwrite(args.salida, dibujar(plantilla, ref, args.pagina))
    print(f"Escrito {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
