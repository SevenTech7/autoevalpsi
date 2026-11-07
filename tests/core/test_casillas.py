"""CO-R5: lectura de casillas (OMR) y banderas."""

import dataclasses
import json

import cv2
import numpy as np
import pytest
from tools.sintetico.lote import generar_lote

from autoevalpsi.core.casillas import (
    BANDERA_CONTRASTE_BAJO,
    BANDERA_DOBLE_MARCA,
    BANDERA_SIN_MARCA,
    ParametrosLectura,
    ResultadoFila,
    ResultadoPagina,
    decidir_fila,
    leer_casillas,
)
from autoevalpsi.core.imagen import cargar_imagen
from autoevalpsi.core.plantilla import UmbralesOMR, cargar_plantilla
from autoevalpsi.core.registro import BANDERA_REGISTRO_DUDOSO, UmbralesRegistro, registrar

OPCIONES = ["Nunca", "Casi nunca", "A veces", "Casi siempre", "Siempre"]


def _verdad(f):
    return json.loads(f.verdad.read_text(encoding="utf-8"))


def _leer_lote(fotos):
    """[(foto, verdad, ResultadoPagina)] registrando cada foto contra la `blanca.png` del lote."""
    plantilla = cargar_plantilla(fotos[0].plantilla)
    ref = cv2.imread(str(fotos[0].plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    salida = []
    for f in fotos:
        reg = registrar(cargar_imagen(f.foto.read_bytes()), ref)
        salida.append((f, _verdad(f), leer_casillas(reg, plantilla, ref)))
    return plantilla, ref, salida


def _correcta(fila: ResultadoFila, item_verdad: dict) -> bool:
    marcas = item_verdad["marcas"]
    return fila.opcion == (marcas[0] if len(marcas) == 1 else None)


@pytest.fixture(scope="module")
def lote_leido(lote_sintetico):
    return _leer_lote(lote_sintetico)


@pytest.fixture(scope="module")
def lote_amplio(tmp_path_factory):
    """Otro lote (otra semilla, más fotos) para que el test de errores silenciosos no dependa
    de las 6 fotos con las que se calibraron los umbrales."""
    fotos = generar_lote(tmp_path_factory.mktemp("lote_omr"), semilla=777, n=12)
    return _leer_lote(fotos)


# --- caracterización sobre el lote sintético --------------------------------------------------


def test_devuelve_una_fila_por_item_con_una_proporcion_por_opcion(lote_leido):
    plantilla, _ref, salida = lote_leido
    items = [f.item for t in plantilla.paginas[0].tablas for f in t.filas]
    for _f, _v, pagina in salida:
        assert isinstance(pagina, ResultadoPagina)
        assert [r.item for r in pagina.filas] == items
        for r in pagina.filas:
            assert len(r.proporciones) == len(OPCIONES)
            assert all(0.0 <= p <= 1.0 for p in r.proporciones)


def test_foto_limpia_lee_las_12_filas_sin_bandera(lote_leido):
    """Foto 0: todos los casos normales (X, ✓, círculo, relleno; tinta azul o negra)."""
    _p, _ref, salida = lote_leido
    f, verdad, pagina = salida[0]
    assert pagina.registro_ok
    for r in pagina.filas:
        esperado = verdad["items"][str(r.item)]["marcas"][0]
        assert r.opcion == esperado, (f.foto.name, r.item, r.proporciones)
        assert r.ok and r.banderas == (), (r.item, r.banderas)


def test_filas_normales_y_fuera_de_celda_se_leen_bien_en_todo_el_lote(lote_leido):
    _p, _ref, salida = lote_leido
    vistas = 0
    for f, verdad, pagina in salida:
        for r in pagina.filas:
            it = verdad["items"][str(r.item)]
            if it["caso"] in ("normal", "fuera"):
                vistas += 1
                assert r.opcion == it["marcas"][0], (f.foto.name, r.item, it["caso"], it["estilo"])
    assert vistas >= 40


def test_fila_vacia_da_sin_marca_y_ninguna_opcion(lote_leido):
    _p, _ref, salida = lote_leido
    n = 0
    for _f, verdad, pagina in salida:
        for r in pagina.filas:
            if verdad["items"][str(r.item)]["caso"] == "vacia":
                n += 1
                assert r.opcion is None and BANDERA_SIN_MARCA in r.banderas
    assert n >= 2


def test_doble_marca_no_se_adivina_y_lleva_bandera(lote_leido):
    _p, _ref, salida = lote_leido
    n = 0
    for _f, verdad, pagina in salida:
        for r in pagina.filas:
            if verdad["items"][str(r.item)]["caso"] == "doble":
                n += 1
                assert r.opcion is None and BANDERA_DOBLE_MARCA in r.banderas
    assert n >= 3


def test_tachon_nunca_sale_verde(lote_leido):
    """La opción tachada tiene más tinta que la válida: si se lee mal, al menos con bandera."""
    _p, _ref, salida = lote_leido
    n = 0
    for _f, verdad, pagina in salida:
        for r in pagina.filas:
            if verdad["items"][str(r.item)]["caso"] == "tachon":
                n += 1
                assert BANDERA_DOBLE_MARCA in r.banderas, (r.item, r.proporciones)
    assert n >= 3


def test_marca_tenue_se_lee_pero_con_contraste_bajo(lote_leido):
    _p, _ref, salida = lote_leido
    n = 0
    for _f, verdad, pagina in salida:
        for r in pagina.filas:
            it = verdad["items"][str(r.item)]
            if it["caso"] == "tenue":
                n += 1
                assert r.banderas, (r.item, r.proporciones, r.contraste)  # nunca verde
                if r.opcion is not None:
                    assert r.opcion == it["marcas"][0]
                    assert BANDERA_CONTRASTE_BAJO in r.banderas
    assert n >= 2


# --- test negativo clave: cero errores silenciosos --------------------------------------------


def _silenciosos(salida):
    malos = []
    for f, verdad, pagina in salida:
        for r in pagina.filas:
            if not _correcta(r, verdad["items"][str(r.item)]) and not r.banderas:
                malos.append((f.foto.name, r.item, verdad["items"][str(r.item)], r.opcion))
    return malos


def test_cero_errores_silenciosos_en_el_lote_base(lote_leido):
    _p, _ref, salida = lote_leido
    assert _silenciosos(salida) == []


def test_cero_errores_silenciosos_en_otro_lote(lote_amplio):
    _p, _ref, salida = lote_amplio
    # Con esta semilla, foto_09 registra mal (~60 px de error; hallazgo de CO-R3, anotado en la
    # bitácora): el registro la marca dudosa y por eso todas sus filas llevan bandera.
    malas = [f.foto.name for f, _v, pagina in salida if not pagina.registro_ok]
    assert len(malas) <= 1, malas
    assert _silenciosos(salida) == []
    # y no por marcar todo: la mayoría de las filas correctas salen verdes
    filas = [(r, v["items"][str(r.item)]) for _f, v, p in salida for r in p.filas]
    verdes = sum(1 for r, it in filas if r.ok and _correcta(r, it))
    assert verdes / len(filas) >= 0.6


# --- CO-09: página con registro dudoso --------------------------------------------------------


def test_registro_dudoso_marca_todas_las_filas(lote_sintetico, lote_leido):
    plantilla, ref, _ = lote_leido
    foto = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    reg = registrar(foto, ref, umbrales=UmbralesRegistro(inliers_min=10**6))
    assert not reg.ok
    pagina = leer_casillas(reg, plantilla, ref)
    assert not pagina.registro_ok and pagina.banderas == (BANDERA_REGISTRO_DUDOSO,)
    assert all(BANDERA_REGISTRO_DUDOSO in r.banderas and not r.ok for r in pagina.filas)


# --- umbrales de la plantilla (CO-02) ----------------------------------------------------------


def test_los_umbrales_de_la_plantilla_mandan(lote_sintetico, lote_leido):
    plantilla, ref, _ = lote_leido
    foto = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    reg = registrar(foto, ref)
    exigente = plantilla.model_copy(update={"omr": UmbralesOMR(tinta_minima=0.99)})
    pagina = leer_casillas(reg, exigente, ref)
    assert all(r.opcion is None and BANDERA_SIN_MARCA in r.banderas for r in pagina.filas)


def test_imagen_de_otro_tamano_que_la_plantilla_se_rechaza(lote_leido):
    plantilla, _ref, salida = lote_leido
    reg = registrar(
        cargar_imagen(salida[0][0].foto.read_bytes()),
        cv2.resize(_ref, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
    )
    with pytest.raises(ValueError, match="otra referencia"):
        leer_casillas(reg, plantilla, _ref)


def test_referencia_de_otro_tamano_que_la_plantilla_se_rechaza(lote_sintetico, lote_leido):
    plantilla, ref, _ = lote_leido
    reg = registrar(cargar_imagen(lote_sintetico[0].foto.read_bytes()), ref)
    with pytest.raises(ValueError, match="referencia es"):
        leer_casillas(reg, plantilla, ref[:-10])


def test_lo_impreso_no_cuenta_como_tinta(lote_sintetico, lote_leido):
    """Hoja en blanco registrada contra sí misma: la cuadrícula no es tinta (sin_marca en todo)."""
    plantilla, ref, _ = lote_leido
    reg = registrar(cargar_imagen(lote_sintetico[0].foto.read_bytes()), ref)
    en_blanco = dataclasses.replace(reg, imagen=cv2.cvtColor(ref, cv2.COLOR_GRAY2BGR))
    pagina = leer_casillas(en_blanco, plantilla, ref)
    assert all(max(r.proporciones) < 0.005 for r in pagina.filas)
    assert all(r.banderas == (BANDERA_SIN_MARCA,) for r in pagina.filas)


def test_parametros_son_inmutables():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ParametrosLectura().holgura_impreso = 0.5  # type: ignore[misc]


# --- decisión por fila (unidad) ----------------------------------------------------------------


def _decidir(props, profs=None, tinta=0.05, margen=0.25, contraste=100.0):
    profs = profs or [200.0] * len(props)
    return decidir_fila(OPCIONES[: len(props)], props, profs, tinta, margen, contraste)


def test_decidir_ganadora_clara():
    opcion, banderas, _ = _decidir([0.0, 0.0, 0.3, 0.0, 0.0])
    assert opcion == "A veces" and banderas == ()


def test_decidir_sin_tinta_suficiente():
    opcion, banderas, _ = _decidir([0.01, 0.0, 0.04, 0.0, 0.0])
    assert opcion is None and banderas == (BANDERA_SIN_MARCA,)


def test_decidir_empate_es_doble_marca_sin_opcion():
    opcion, banderas, _ = _decidir([0.0, 0.3, 0.28, 0.0, 0.0])
    assert opcion is None and banderas == (BANDERA_DOBLE_MARCA,)


def test_decidir_segunda_real_pero_dominada_conserva_la_ganadora_con_bandera():
    opcion, banderas, _ = _decidir([0.0, 0.6, 0.1, 0.0, 0.0])
    assert opcion == "Casi nunca" and banderas == (BANDERA_DOBLE_MARCA,)


def test_decidir_segunda_por_debajo_del_umbral_no_cuenta():
    opcion, banderas, _ = _decidir([0.0, 0.3, 0.04, 0.0, 0.0])
    assert opcion == "Casi nunca" and banderas == ()


def test_decidir_tinta_poco_profunda_es_contraste_bajo():
    opcion, banderas, contraste = _decidir([0.0, 0.0, 0.3, 0.0, 0.0], [0, 0, 70.0, 0, 0])
    assert opcion == "A veces" and banderas == (BANDERA_CONTRASTE_BAJO,) and contraste == 70.0


def test_decidir_margen_relativo_de_la_plantilla():
    props = [0.0, 0.3, 0.2, 0.0, 0.0]  # la segunda está al 67 % de la primera
    assert _decidir(props, margen=0.25)[0] == "Casi nunca"  # domina: margen del 25 %
    assert _decidir(props, margen=0.5)[0] is None  # margen más amplio: ambigua


def test_decidir_fila_de_una_sola_opcion():
    opcion, banderas, _ = decidir_fila(["Si"], [0.3], [200.0], 0.05, 0.25, 100.0)
    assert opcion == "Si" and banderas == ()


def test_los_numeros_de_las_proporciones_son_estables(lote_leido):
    """Caracterización: una marca limpia ocupa un 7-30 % de la celda; el papel vacío, 0."""
    _p, _ref, salida = lote_leido
    _f, _v, pagina = salida[0]
    marcadas = [max(r.proporciones) for r in pagina.filas]
    vacias = [p for r in pagina.filas for p in sorted(r.proporciones)[:-1]]
    assert min(marcadas) > 0.05 and max(vacias) < 0.01
    assert np.isfinite(marcadas).all()
