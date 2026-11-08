"""VD-R1: tablas de dígitos manuscritos (el valor es un número, no una casilla marcada)."""

from dataclasses import replace

import cv2
import numpy as np
import pytest

from autoevalpsi.core.casillas import (
    BANDERA_CELDA_VACIA,
    BANDERA_DIGITO_DUDOSO,
    BANDERA_DIGITO_ILEGIBLE,
    BANDERA_SIN_LECTOR,
    leer_casillas,
)
from autoevalpsi.core.ocr.lector import LectorFalso, LecturaDigito
from autoevalpsi.core.plantilla import Plantilla
from autoevalpsi.core.registro import Registro

ANCHO, ALTO = 300, 260
FILAS_Y = [(20, 70), (80, 130), (140, 190), (200, 250)]


def plantilla(**tabla) -> Plantilla:
    return Plantilla.model_validate(
        {
            "esquema_version": 1,
            "id": "dig",
            "nombre": "Dígitos",
            "version": 1,
            "paginas": [
                {
                    "imagen_referencia": "dig.png",
                    "tamano_px": [ANCHO, ALTO],
                    "tablas": [
                        {
                            "tipo": "digito",
                            "opciones": ["0", "1", "2"],
                            "columnas_x": [[100, 160]],
                            "filas": [
                                {"item": i + 1, "texto": f"ítem {i + 1}", "y": list(y)}
                                for i, y in enumerate(FILAS_Y)
                            ],
                            **tabla,
                        }
                    ],
                }
            ],
        }
    )


def hoja_en_blanco() -> np.ndarray:
    img = np.full((ALTO, ANCHO), 255, np.uint8)
    for y0, y1 in FILAS_Y:
        cv2.rectangle(img, (100, y0), (160, y1), 0, 2)  # la cuadrícula impresa
    return img


def con_digitos(escritos: dict[int, str]) -> np.ndarray:
    img = hoja_en_blanco()
    for item, d in escritos.items():
        _, y1 = FILAS_Y[item - 1]
        cv2.putText(img, d, (118, y1 - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 0, 4)
    return img


def registro(img: np.ndarray) -> Registro:
    return Registro(
        homografia=np.eye(3),
        imagen=cv2.cvtColor(img, cv2.COLOR_GRAY2BGR),
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


def leer(escritos, lector, tabla=None):
    pagina = leer_casillas(
        registro(con_digitos(escritos)), plantilla(**(tabla or {})), hoja_en_blanco(), lector=lector
    )
    return {f.item: f for f in pagina.filas}


def seguro(d: str) -> LecturaDigito:
    return LecturaDigito(d, 0.95, 0.9)


def test_el_esquema_exige_una_sola_columna_y_digitos_de_un_caracter():
    base = plantilla()
    assert base.paginas[0].tablas[0].tipo == "digito"
    with pytest.raises(ValueError, match="una sola columna"):
        plantilla(columnas_x=[[100, 130], [140, 170]], opciones=["0", "1"])
    with pytest.raises(ValueError, match="0-9"):
        plantilla(opciones=["0", "10"])


def test_una_celda_con_numero_y_lectura_segura_sale_verde():
    f = leer({1: "2"}, LectorFalso(digitos=[seguro("2")]))
    assert f[1].opcion == "2" and f[1].ok


def test_una_celda_vacia_queda_vacia_y_avisa():
    lector = LectorFalso(digitos=[seguro("2")])
    f = leer({1: "2"}, lector)
    for item in (2, 3, 4):
        assert f[item].opcion is None
        assert f[item].banderas == (BANDERA_CELDA_VACIA,)
    assert len(lector.llamadas_digito) == 1  # no se gasta OCR en las celdas vacías


def test_la_lectura_dudosa_se_propone_pero_se_marca():
    lector = LectorFalso(digitos=[LecturaDigito("1", 0.45, 0.2)])
    f = leer({1: "1"}, lector)
    assert f[1].opcion == "1" and f[1].banderas == (BANDERA_DIGITO_DUDOSO,)


def test_si_el_lector_no_reconoce_nada_no_se_adivina():
    f = leer({1: "2"}, LectorFalso(digitos=[LecturaDigito(None, 0.0, 0.0)]))
    assert f[1].opcion is None and f[1].banderas == (BANDERA_DIGITO_ILEGIBLE,)
    f = leer({1: "2"}, LectorFalso(digitos=[LecturaDigito("2", 0.1, 0.05)]))
    assert f[1].opcion is None and f[1].banderas == (BANDERA_DIGITO_ILEGIBLE,)


def test_sin_lector_los_numeros_escritos_se_avisan_y_los_vacios_siguen_vacios():
    f = leer({1: "2"}, None)
    assert f[1].opcion is None and f[1].banderas == (BANDERA_SIN_LECTOR,)
    assert f[2].banderas == (BANDERA_CELDA_VACIA,)


def test_la_cuadricula_impresa_no_cuenta_como_tinta():
    f = leer({}, LectorFalso(digitos=[seguro("2")]))
    assert all(r.banderas == (BANDERA_CELDA_VACIA,) for r in f.values())


def test_el_recorte_que_recibe_el_lector_no_trae_la_cuadricula():
    lector = LectorFalso(digitos=[seguro("2")])
    leer({1: "2"}, lector)
    (recorte,) = lector.llamadas_digito
    assert recorte.min() == 0 and (recorte < 128).mean() < 0.5  # el trazo sí, el marco no
    assert recorte.shape[0] < 50  # menos que la celda: sin los bordes


def test_un_lector_que_solo_lee_lineas_no_sirve_para_digitos():
    class SoloLineas:
        def leer(self, imagen):
            return []

    f = leer({1: "2"}, SoloLineas())
    assert f[1].banderas == (BANDERA_SIN_LECTOR,)


def test_las_tablas_de_marcas_siguen_igual_con_lector():
    # una plantilla v1 de siempre no cambia por pasar un lector
    t = Plantilla.model_validate(
        {
            "esquema_version": 1,
            "id": "m",
            "nombre": "M",
            "version": 1,
            "paginas": [
                {
                    "imagen_referencia": "m.png",
                    "tamano_px": [ANCHO, ALTO],
                    "tablas": [
                        {
                            "opciones": ["A", "B"],
                            "columnas_x": [[100, 130], [140, 170]],
                            "filas": [{"item": 1, "texto": "x", "y": [20, 70]}],
                        }
                    ],
                }
            ],
        }
    )
    assert t.paginas[0].tablas[0].tipo == "marcas"
    pagina = leer_casillas(registro(hoja_en_blanco()), t, hoja_en_blanco(), lector=LectorFalso())
    assert pagina.filas[0].opcion is None and pagina.filas[0].banderas == ("sin_marca",)


def test_cada_celda_con_numero_deja_su_recorte_para_la_revision():
    pagina = leer_casillas(
        registro(con_digitos({1: "2", 3: "1"})),
        plantilla(),
        hoja_en_blanco(),
        lector=LectorFalso(digitos=[seguro("2"), seguro("1")]),
    )
    assert sorted(pagina.recortes) == [1, 3]  # las vacías no tienen recorte
    assert pagina.recortes[1].shape[:2] == (50, 60)  # la celda completa, con su marco


def test_con_la_hoja_mal_calzada_no_se_lee_ningun_numero():
    """Si el registro salió mal, las celdas miradas no son las de la plantilla: no se inventa."""
    lector = LectorFalso(digitos=[seguro("2")] * 4)
    mal = replace(
        registro(con_digitos({1: "2", 2: "1"})),
        error_reproyeccion=2.8,
        correlacion_lineas=-0.03,
        banderas=("registro_dudoso",),
    )
    pagina = leer_casillas(mal, plantilla(), hoja_en_blanco(), lector=lector)
    assert [f.opcion for f in pagina.filas] == [None] * 4
    assert all("registro_dudoso" in f.banderas for f in pagina.filas)
    assert lector.llamadas_digito == []
    # un registro dudoso pero preciso (esquina fuera de la foto) sí se lee, con el aviso
    dudoso = replace(
        registro(con_digitos({1: "2"})), error_reproyeccion=0.7, banderas=("registro_dudoso",)
    )
    f = leer_casillas(
        dudoso, plantilla(), hoja_en_blanco(), lector=LectorFalso(digitos=[seguro("2")])
    )
    assert f.filas[0].opcion == "2" and "registro_dudoso" in f.filas[0].banderas
