"""OC-R2: pipeline completo con el modelo real sobre fotos sintéticas (marcador `lento`).

La letra es la de Hershey script de OpenCV, no manuscrito real: esto prueba el cableado de punta a
punta (franja única, asignación a filas, cabecera), no el acierto con la letra de la usuaria (OC-R3).
"""

import json
import time

import cv2
import pytest

from autoevalpsi.core.ocr.onnx import MODELOS_POR_DEFECTO, LectorONNX
from autoevalpsi.core.pipeline import procesar_foto
from autoevalpsi.core.plantilla import cargar_plantilla

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module")
def lector():
    if not (MODELOS_POR_DEFECTO / "rec" / "diccionario.txt").is_file():
        pytest.skip("faltan modelos/ (python -m tools.descargar_modelos)")
    return LectorONNX()


def test_foto_sintetica_de_punta_a_punta(lote_sintetico, lector):
    f = lote_sintetico[0]
    plantilla = cargar_plantilla(f.plantilla)
    ref = cv2.imread(str(f.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    verdad = json.loads(f.verdad.read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    proc = procesar_foto(f.foto.read_bytes(), plantilla, ref, lector=lector)
    print(f"\nprocesar_foto con OCR: {time.perf_counter() - t0:.1f} s (incluye carga del modelo)")
    r = proc.resultado
    escritas = {int(i): v["observacion"] for i, v in verdad["items"].items() if v["observacion"]}
    assert set(proc.recortes) == set(escritas)  # recorte siempre, lea bien o mal
    leidas = {o.item: o for o in r.observaciones if o.tiene_tinta}
    assert set(leidas) == set(escritas)
    for item, esperado in escritas.items():
        print(f"item {item}: {esperado!r} -> {leidas[item].texto!r} ({leidas[item].confianza})")
    for c in r.cabecera:
        print(f"cabecera {c.campo}: {verdad['cabecera'][c.campo]!r} -> {c.texto!r} ({c.confianza})")
    con_texto = [o for o in leidas.values() if o.texto]
    assert len(con_texto) >= len(leidas) // 2  # el lector ve la mayoría de las líneas
