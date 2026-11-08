"""OC-R1: modelo real sobre texto impreso sintético (marcador `lento`; necesita `modelos/`)."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from autoevalpsi.core.ocr.onnx import MODELOS_POR_DEFECTO, LectorONNX

pytestmark = pytest.mark.lento

FUENTE = Path("modelos/fuentes/arial.ttf")
LINEAS = [
    "Observaciones: el paciente mostró ansiedad ante la prueba",
    "Peña, Núñez, Ibáñez — año 2025, ¿cómo está?",
    "Se observa dificultad para concentrarse y fatiga",
]


def _hoja(lineas, ancho=1600, alto_linea=90):
    im = Image.new("RGB", (ancho, alto_linea * len(lineas) + 40), "white")
    f = ImageFont.truetype(str(FUENTE), 38)
    d = ImageDraw.Draw(im)
    for i, t in enumerate(lineas):
        d.text((30, 30 + i * alto_linea), t, fill=(20, 20, 20), font=f)
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


@pytest.fixture(scope="module")
def lector():
    if not (MODELOS_POR_DEFECTO / "rec" / "diccionario.txt").is_file() or not FUENTE.is_file():
        pytest.skip("faltan modelos/ o la fuente (python -m tools.descargar_modelos)")
    return LectorONNX()


def _norm(t):
    return t.replace(" ", "").lower()


def test_texto_impreso_se_lee_en_orden_con_tildes_y_confianza_alta(lector):
    lineas = lector.leer(_hoja(LINEAS))
    assert len(lineas) == len(LINEAS)
    for leida, esperada in zip(lineas, LINEAS, strict=True):
        assert _norm(leida.texto) == _norm(esperada)
        assert leida.confianza > 0.9
    ys = [li.caja.y0 for li in lineas]
    assert ys == sorted(ys)


def test_las_cajas_caen_sobre_su_renglon(lector):
    img = _hoja(LINEAS)
    for i, li in enumerate(lector.leer(img)):
        centro = 30 + i * 90 + 22  # texto de 38 px dibujado desde y = 30 + i·90
        assert li.caja.y0 <= centro <= li.caja.y1
        assert 0 <= li.caja.x0 < li.caja.x1 <= img.shape[1]


def test_imagen_en_blanco_no_devuelve_lineas(lector):
    assert lector.leer(np.full((300, 1200, 3), 255, np.uint8)) == []


def test_acepta_escala_de_grises(lector):
    gris = cv2.cvtColor(_hoja(LINEAS[:1]), cv2.COLOR_BGR2GRAY)
    assert len(lector.leer(gris)) == 1


# --- VD-R1: dígitos con vocabulario cerrado ----------------------------------------------------


def _celda_con(texto: str, fuente: str = "inkfree.ttf", tam: int = 56):
    im = Image.new("L", (60, 70), 255)
    f = ImageFont.truetype(str(Path("modelos/fuentes") / fuente), tam)
    ImageDraw.Draw(im).text((14, 4), texto, fill=20, font=f)
    return np.array(im)


@pytest.mark.parametrize("digito", ["0", "1", "2"])
def test_lee_un_digito_manuscrito_entre_0_1_2(digito):
    lectura = LectorONNX().leer_digito(_celda_con(digito), ["0", "1", "2"])
    assert lectura.digito == digito
    assert lectura.confianza > 0.5


def test_una_letra_se_vuelve_el_digito_mas_parecido_pero_con_poca_confianza():
    lectura = LectorONNX().leer_digito(_celda_con("W"), ["0", "1", "2"])
    assert lectura.digito in {"0", "1", "2", None}
    assert lectura.confianza < 0.9


def test_una_celda_en_blanco_no_da_ningun_digito_seguro():
    lectura = LectorONNX().leer_digito(np.full((60, 60), 255, np.uint8), ["0", "1", "2"])
    assert lectura.digito is None or lectura.confianza < 0.3
