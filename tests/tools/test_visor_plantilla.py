"""PL-R1: el visor superpone las cajas de la plantilla sobre su referencia."""

from pathlib import Path

import cv2
import numpy as np
from tools.visor_plantilla import main

DEMO = Path("plantillas_demo/demo-5opciones-a4.json")


def test_el_visor_dibuja_las_cajas_en_color_sobre_la_referencia(tmp_path):
    salida = tmp_path / "control.png"
    assert main([str(DEMO), "--salida", str(salida)]) == 0
    img = cv2.imread(str(salida))
    ref = cv2.imread(str(DEMO.with_suffix(".png")), cv2.IMREAD_GRAYSCALE)
    assert img.shape[:2] == ref.shape
    color = np.abs(img.astype(int) - img[:, :, :1].astype(int)).sum(axis=2) > 30
    assert color.sum() > 5000  # hay trazos de color (cajas) sobre el gris de la referencia
