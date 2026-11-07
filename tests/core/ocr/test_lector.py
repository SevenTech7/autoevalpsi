"""OC-R1: interfaz `Lector`, `LectorFalso`, orden de lectura, CTC y errores del lector ONNX."""

import numpy as np
import pytest

from autoevalpsi.core.ocr import Caja, Lector, LectorFalso, Linea, ordenar_lectura
from autoevalpsi.core.ocr.onnx import (
    LectorONNX,
    ModelosNoEncontrados,
    _a_bgr,
    cargar_diccionario,
    decodificar_ctc,
)


def _linea(texto, x0, y0, x1, y1, conf=0.9):
    return Linea(texto, conf, Caja(x0, y0, x1, y1))


def test_lector_falso_cumple_la_interfaz_y_registra_llamadas():
    lineas = [_linea("hola", 0, 0, 50, 20)]
    falso = LectorFalso(lineas)
    img = np.zeros((10, 10, 3), np.uint8)
    assert isinstance(falso, Lector)
    assert falso.leer(img) == lineas
    assert len(falso.llamadas) == 1


def test_lector_falso_con_funcion_y_con_error():
    falso = LectorFalso(lambda im: [_linea(str(im.shape[0]), 0, 0, 1, 1)])
    assert falso.leer(np.zeros((7, 3), np.uint8))[0].texto == "7"
    with pytest.raises(RuntimeError, match="boom"):
        LectorFalso(error=RuntimeError("boom")).leer(np.zeros((2, 2), np.uint8))


def test_orden_de_lectura_agrupa_renglones_y_ordena_por_x():
    a = _linea("b2", 200, 102, 300, 130)  # renglón 2, derecha
    b = _linea("a1", 10, 10, 100, 40)  # renglón 1, izquierda
    c = _linea("a2", 150, 14, 260, 44)  # renglón 1, derecha, un poco más abajo
    d = _linea("b1", 10, 100, 120, 128)  # renglón 2, izquierda
    assert [li.texto for li in ordenar_lectura([a, b, c, d])] == ["a1", "a2", "b1", "b2"]


def test_ordenar_lectura_lista_vacia():
    assert ordenar_lectura([]) == []


def test_decodificar_ctc_colapsa_repetidos_y_quita_blanco():
    clases = ["", "a", "b", " "]
    p = np.zeros((7, 4), np.float32)
    # a a blanco a b b blanco → "aab"
    for t, (i, c) in enumerate(
        [(1, 0.9), (1, 0.8), (0, 1.0), (1, 0.7), (2, 0.6), (2, 0.5), (0, 1)]
    ):
        p[t, i] = c
    texto, conf = decodificar_ctc(p, clases)
    assert texto == "aab"
    assert conf == pytest.approx((0.9 + 0.7 + 0.6) / 3)


def test_decodificar_ctc_sin_texto_da_confianza_cero():
    p = np.zeros((3, 4), np.float32)
    p[:, 0] = 1.0
    assert decodificar_ctc(p, ["", "a", "b", " "]) == ("", 0.0)


def test_diccionario_agrega_blanco_y_espacio_y_no_parte_en_separadores_unicode(tmp_path):
    ruta = tmp_path / "d.txt"
    ruta.write_text("a\nñ\n \nb\n", encoding="utf8", newline="\n")
    assert cargar_diccionario(ruta) == ["", "a", "ñ", " ", "b", " "]


@pytest.mark.parametrize(
    "imagen",
    [np.zeros((0, 5, 3), np.uint8), np.zeros((5, 5), np.float32), np.zeros((5, 5, 2), np.uint8)],
)
def test_imagen_no_valida_se_rechaza(imagen):
    with pytest.raises(ValueError):
        _a_bgr(imagen)


def test_a_bgr_acepta_gris_y_bgra():
    assert _a_bgr(np.zeros((4, 4), np.uint8)).shape == (4, 4, 3)
    assert _a_bgr(np.zeros((4, 4, 4), np.uint8)).shape == (4, 4, 3)


def test_modelos_ausentes_dan_error_claro_y_no_cargan_nada(tmp_path):
    lector = LectorONNX(tmp_path / "no_existe")
    with pytest.raises(ModelosNoEncontrados, match="descargar_modelos"):
        lector.leer(np.full((40, 200, 3), 255, np.uint8))
    assert lector._det is None  # no quedó a medio cargar


def test_carga_perezosa_no_toca_el_disco_al_construir(tmp_path):
    LectorONNX(tmp_path / "no_existe")  # no debe lanzar
