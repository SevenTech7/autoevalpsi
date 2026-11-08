"""VD-R2: cuadrícula de una hoja de respuestas con celdas numeradas."""

from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np
import pytest

from autoevalpsi.core.cuadricula import (
    Celda,
    Columna,
    _bandas_y,
    _tramos_rectos,
    agrupar_columnas,
    bloques_de_items,
    completar_huecos,
    numeracion,
    plantilla_de_digitos,
)
from autoevalpsi.core.plantilla import Plantilla

# --- lógica pura (sin OCR) ----------------------------------------------------------------------


def columna_inclinada(n=20, x0=100, ancho=40, alto=32, deriva=2.0) -> list[Celda]:
    return [
        Celda(
            int(x0 + k * deriva), 100 + k * alto, int(x0 + k * deriva) + ancho, 100 + (k + 1) * alto
        )
        for k in range(n)
    ]


def test_las_columnas_siguen_una_inclinacion_que_cortaria_un_agrupado_por_x():
    cs = columna_inclinada(deriva=3.0) + [
        Celda(c.x0 + 45, c.y0, c.x1 + 45, c.y1) for c in columna_inclinada(deriva=3.0)
    ]
    columnas = agrupar_columnas(cs, 40, 32)
    assert [len(c.celdas) for c in columnas] == [20, 20]
    assert columnas[0].celdas[0].cx < columnas[1].celdas[0].cx


def test_las_celdas_encimadas_no_hacen_otra_columna():
    cs = columna_inclinada(8)
    cs.append(Celda(cs[3].x0 + 5, cs[3].y0 + 5, cs[3].x1 - 5, cs[3].y1 - 5))  # el hueco de un hueco
    (col,) = agrupar_columnas(cs, 40, 32)
    assert len(col.celdas) == 8


def test_una_celda_que_falta_en_medio_se_rellena():
    cs = columna_inclinada(10, deriva=0)
    del cs[4]  # una celda azul que no dio hueco
    col = completar_huecos(Columna(cs), 32)
    assert len(col.celdas) == 10
    assert abs(col.celdas[4].cy - (100 + 4.5 * 32)) < 2


def test_una_columna_muy_inclinada_se_parte_en_tablas_rectas():
    fs = columna_inclinada(30, deriva=3.0)  # se corre 87 px en 30 filas: más de 2 celdas
    tramos = _tramos_rectos(fs, 40)
    assert len(tramos) > 1
    assert sorted(i for t in tramos for i in t) == list(range(30))
    for t in tramos:
        xs = [fs[i].cx for i in t]
        assert max(xs) - min(xs) <= 0.5 * 40 + 1


def test_las_bandas_de_las_filas_no_se_solapan():
    celdas_ = [Celda(0, 0, 10, 30), Celda(0, 28, 10, 60), Celda(0, 60, 10, 90)]
    bandas = _bandas_y(celdas_)
    assert all(a[1] <= b[0] for a, b in pairwise(bandas))


def test_la_numeracion_se_corrige_con_el_voto_de_las_demas():
    leidas = [(31, 0.9), (32, 0.9), (33, 0.9), (38, 0.5), (35, 0.9), (None, 0.0), (37, 0.9)]
    numeros, apoyo = numeracion(leidas)
    assert numeros == [31, 32, 33, 34, 35, 36, 37]
    assert apoyo > 0.6


def test_una_columna_que_no_cuenta_no_es_de_etiquetas():
    assert numeracion([(2, 0.9), (0, 0.9), (2, 0.9), (1, 0.9), (0, 0.9), (2, 0.9)]) is None
    assert numeracion([(None, 0.0)] * 5) is None


# --- una hoja dibujada, con el lector real ------------------------------------------------------

FILAS, ALTO_CELDA, ANCHO_CELDA = 12, 40, 52
X_ETIQUETA, Y0 = 90, 160


def hoja_de_celdas(escritos: dict[int, str]) -> np.ndarray:
    """Dos bloques de 6 filas: etiquetas 1-6 y 7-12 con su celda de respuesta a la derecha."""
    img = np.full((620, 460), 235, np.uint8)
    cv2.rectangle(img, (X_ETIQUETA, 40), (X_ETIQUETA + 2 * ANCHO_CELDA + 150, 100), 0, 2)
    cv2.putText(img, "ESCUCHAR", (X_ETIQUETA + 20, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.8, 0, 2)
    for bloque, x in enumerate((X_ETIQUETA, X_ETIQUETA + 2 * ANCHO_CELDA + 50)):
        for k in range(FILAS // 2):
            n = bloque * (FILAS // 2) + k + 1
            y = Y0 + k * ALTO_CELDA
            cv2.rectangle(img, (x, y), (x + ANCHO_CELDA, y + ALTO_CELDA), 0, 2)
            cv2.rectangle(img, (x + ANCHO_CELDA, y), (x + 2 * ANCHO_CELDA, y + ALTO_CELDA), 0, 2)
            cv2.putText(img, str(n), (x + 12, y + 29), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 20, 2)
            if n in escritos:
                cv2.putText(
                    img,
                    escritos[n],
                    (x + ANCHO_CELDA + 14, y + 31),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    40,
                    3,
                )
    return img


@pytest.mark.lento
def test_arma_una_tabla_de_digitos_por_columna_de_respuestas_con_el_lector_real():
    from autoevalpsi.core.ocr.onnx import LectorONNX

    escritos = {1: "2", 2: "1", 3: "0", 7: "2", 9: "1"}
    gris = hoja_de_celdas(escritos)
    img = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
    bloques = bloques_de_items(gris, LectorONNX())
    assert [b.numeros for b in bloques] == [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]

    dic, limpia, _ = plantilla_de_digitos(img, LectorONNX(), id="hoja", nombre="Hoja")
    plantilla = Plantilla.model_validate(dic)
    tablas = plantilla.paginas[0].tablas
    assert [len(t.filas) for t in tablas] == [6, 6]
    assert all(t.tipo == "digito" and t.opciones == ["0", "1", "2"] for t in tablas)
    assert [f.item for t in tablas for f in t.filas] == list(range(1, 13))
    # la referencia sale sin lo escrito a mano
    x0, x1 = tablas[0].columnas_x[0]
    y0, y1 = tablas[0].filas[0].y
    celda = limpia[y0 + 8 : y1 - 8, x0 + 8 : x1 - 8]
    assert celda.min() > 200


@pytest.mark.lento
def test_la_hoja_dibujada_se_lee_con_su_plantilla_y_el_lector_real():
    from autoevalpsi.core.casillas import leer_casillas
    from autoevalpsi.core.ocr.onnx import LectorONNX
    from autoevalpsi.core.registro import Registro

    escritos = {1: "2", 2: "1", 3: "0", 7: "2", 9: "1"}
    gris = hoja_de_celdas(escritos)
    img = cv2.cvtColor(gris, cv2.COLOR_GRAY2BGR)
    lector = LectorONNX()
    dic, limpia, _ = plantilla_de_digitos(img, lector, id="hoja", nombre="Hoja")
    registro = Registro(
        homografia=np.eye(3),
        imagen=img,
        metodo_hoja="contorno",
        giro=0,
        coincidencias=100,
        inliers=100,
        proporcion_inliers=1.0,
        error_reproyeccion=0.1,
        cobertura=1.0,
        correlacion_lineas=1.0,
        ajuste_lineas=False,
    )
    pagina = leer_casillas(registro, Plantilla.model_validate(dic), limpia, lector=lector)
    leidas = {f.item: f.opcion for f in pagina.filas}
    assert [leidas[i] for i in (1, 2, 3, 7, 9)] == ["2", "1", "0", "2", "1"]
    assert all(leidas[i] is None for i in (4, 5, 6, 8, 10, 11, 12))  # vacías: quedan vacías


# --- foto real de la usuaria (solo local) -------------------------------------------------------

FOTO_REVERSO = Path("muestras/WhatsApp Image 2026-11-07 at 19.17.17.jpeg")


@pytest.mark.real
@pytest.mark.skipif(not FOTO_REVERSO.exists(), reason="la foto de muestra no está en este equipo")
def test_reverso_del_vineland_real():
    from autoevalpsi.core.borrador import leer_con_posiciones
    from autoevalpsi.core.ocr.onnx import LectorONNX

    img = cv2.imdecode(np.fromfile(str(FOTO_REVERSO), np.uint8), cv2.IMREAD_COLOR)
    lector = LectorONNX()
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bloques = bloques_de_items(gris, lector, leer_con_posiciones(img, lector))
    assert [(b.numeros[0], b.numeros[-1]) for b in bloques] == [
        (1, 30),
        (31, 43),
        (1, 30),
        (31, 36),
        (1, 30),
        (31, 34),
        (1, 14),
        (1, 11),
        (1, 20),
    ]
