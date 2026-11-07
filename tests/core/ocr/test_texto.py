"""OC-R2: observaciones por fila y cabecera sobre la hoja registrada, con un `Lector` falso."""

import json
from datetime import date

import cv2
import numpy as np
import openpyxl
import pytest

from autoevalpsi.cli import main
from autoevalpsi.core.excel import exportar
from autoevalpsi.core.ocr.lector import Caja, LectorFalso, Linea
from autoevalpsi.core.ocr.texto import (
    BANDERA_CABECERA_VACIA,
    BANDERA_OCR_CONFIANZA_BAJA,
    BANDERA_OCR_ERROR,
    BANDERA_OCR_SIN_TEXTO,
    leer_texto,
)
from autoevalpsi.core.pipeline import a_evaluacion, procesar_foto
from autoevalpsi.core.plantilla import cargar_plantilla


@pytest.fixture(scope="module")
def caso(lote_sintetico):
    f = lote_sintetico[0]
    plantilla = cargar_plantilla(f.plantilla)
    ref = cv2.imread(str(f.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    hoja = cv2.imread(str(f.hoja))  # hoja llena, sin perspectiva, a tamaño de plantilla
    verdad = json.loads(f.verdad.read_text(encoding="utf-8"))
    tabla = plantilla.paginas[0].tablas[0]
    return f, plantilla, ref, hoja, verdad, tabla


def _lector_segun_verdad(tabla, verdad, confianza=0.95):
    """Devuelve, sobre la franja, una línea por observación escrita (y lo de cabecera, que mide
    menos de 200 px de alto, como un campo)."""
    y0 = tabla.filas[0].y[0]
    ancho = tabla.observacion_x[1] - tabla.observacion_x[0]

    def leer(imagen):
        if imagen.shape[0] < 200:  # un campo de cabecera
            return [Linea("dato", confianza, Caja(0, 0, 10, 10))]
        lineas = []
        for fila in tabla.filas:
            texto = verdad["items"][str(fila.item)]["observacion"]
            if texto:
                cy = (fila.y[0] + fila.y[1]) // 2 - y0
                lineas.append(Linea(texto, confianza, Caja(10, cy - 20, ancho - 10, cy + 20)))
        return lineas

    return leer


def test_cada_linea_cae_en_su_fila(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    lector = LectorFalso(_lector_segun_verdad(tabla, verdad))
    r = leer_texto(hoja, plantilla, ref, lector)
    assert len(r.observaciones) == len(tabla.filas)
    escritas = 0
    for o in r.observaciones:
        esperado = verdad["items"][str(o.item)]["observacion"]
        assert o.texto == esperado
        assert o.tiene_tinta == bool(esperado)
        assert o.ok
        escritas += bool(esperado)
    assert 0 < escritas < len(tabla.filas)  # la foto cubre ambos casos


def test_el_lector_corre_una_vez_para_toda_la_tabla(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    lector = LectorFalso(_lector_segun_verdad(tabla, verdad))
    leer_texto(hoja, plantilla, ref, lector)
    franjas = [im for im in lector.llamadas if im.shape[0] >= 200]
    assert len(franjas) == 1  # no una por fila (OC-05)
    assert franjas[0].shape[0] == tabla.filas[-1].y[1] - tabla.filas[0].y[0]


def test_hoja_en_blanco_no_llama_al_lector(caso):
    _f, plantilla, ref, _hoja, _verdad, _tabla = caso
    blanca = cv2.cvtColor(ref, cv2.COLOR_GRAY2BGR)
    lector = LectorFalso()
    r = leer_texto(blanca, plantilla, ref, lector)
    assert lector.llamadas == []
    assert all(not o.tiene_tinta and o.texto == "" and o.ok for o in r.observaciones)
    assert r.recortes == {} and r.recortes_cabecera == {}
    # la cabecera vacía se avisa; una observación vacía es normal
    assert all(c.banderas == (BANDERA_CABECERA_VACIA,) for c in r.cabecera)


def test_filas_sin_tinta_se_blanquean_en_la_franja(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    lector = LectorFalso(_lector_segun_verdad(tabla, verdad))
    leer_texto(hoja, plantilla, ref, lector)
    franja = next(im for im in lector.llamadas if im.shape[0] >= 200)
    y0 = tabla.filas[0].y[0]
    for fila in tabla.filas:
        zona = franja[fila.y[0] - y0 : fila.y[1] - y0]
        escrita = bool(verdad["items"][str(fila.item)]["observacion"])
        assert (zona.min() < 128) == escrita  # solo las filas con tinta conservan oscuros


def test_la_linea_ajena_a_una_fila_vacia_se_descarta(caso):
    """Un texto «alucinado» sobre una fila sin tinta no llega al resultado."""
    _f, plantilla, ref, hoja, verdad, tabla = caso
    vacia = next(f for f in tabla.filas if not verdad["items"][str(f.item)]["observacion"])
    cy = (vacia.y[0] + vacia.y[1]) // 2 - tabla.filas[0].y[0]
    base = _lector_segun_verdad(tabla, verdad)

    def leer(imagen):
        extra = (
            [Linea("fantasma", 0.99, Caja(0, cy - 10, 50, cy + 10))]
            if imagen.shape[0] >= 200
            else []
        )
        return [*base(imagen), *extra]

    r = leer_texto(hoja, plantilla, ref, LectorFalso(leer))
    assert next(o for o in r.observaciones if o.item == vacia.item).texto == ""


def test_varias_lineas_de_una_fila_se_unen_con_la_peor_confianza(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    fila = next(f for f in tabla.filas if verdad["items"][str(f.item)]["observacion"])
    cy = (fila.y[0] + fila.y[1]) // 2 - tabla.filas[0].y[0]
    lector = LectorFalso(
        lambda im: (
            [
                Linea("hola", 0.97, Caja(0, cy - 20, 40, cy + 20)),
                Linea("mundo", 0.90, Caja(60, cy - 20, 120, cy + 20)),
            ]
            if im.shape[0] >= 200
            else []
        )
    )
    r = leer_texto(hoja, plantilla, ref, lector)
    o = next(o for o in r.observaciones if o.item == fila.item)
    assert o.texto == "hola mundo" and o.confianza == pytest.approx(0.90)


def test_confianza_baja_deja_bandera_y_conserva_el_texto(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    r = leer_texto(hoja, plantilla, ref, LectorFalso(_lector_segun_verdad(tabla, verdad, 0.4)))
    escritas = [o for o in r.observaciones if o.tiene_tinta]
    assert escritas and all(o.banderas == (BANDERA_OCR_CONFIANZA_BAJA,) for o in escritas)
    assert all(o.texto for o in escritas)
    assert all(o.ok for o in r.observaciones if not o.tiene_tinta)


def test_tinta_sin_texto_leido_es_amarilla(caso):
    _f, plantilla, ref, hoja, _verdad, _tabla = caso
    r = leer_texto(hoja, plantilla, ref, LectorFalso([]))
    escritas = [o for o in r.observaciones if o.tiene_tinta]
    assert escritas and all(o.banderas == (BANDERA_OCR_SIN_TEXTO,) for o in escritas)
    assert all(c.banderas == (BANDERA_OCR_SIN_TEXTO,) for c in r.cabecera)


def test_el_recorte_existe_aunque_el_lector_falle(caso):
    _f, plantilla, ref, hoja, verdad, tabla = caso
    r = leer_texto(hoja, plantilla, ref, LectorFalso(error=RuntimeError("modelo roto")))
    escritas = {int(i) for i, v in verdad["items"].items() if v["observacion"]}
    assert set(r.recortes) == escritas  # solo las filas con tinta, todas
    for o in r.observaciones:
        assert o.banderas == ((BANDERA_OCR_ERROR,) if o.tiene_tinta else ())
    fila = next(f for f in tabla.filas if f.item in escritas)
    x0, x1 = tabla.observacion_x
    recorte = r.recortes[fila.item]
    assert recorte.shape[:2] == (fila.y[1] - fila.y[0], x1 - x0)
    assert np.array_equal(recorte, hoja[fila.y[0] : fila.y[1], x0:x1])  # original, sin limpiar
    assert set(r.recortes_cabecera) == {c.campo for c in plantilla.paginas[0].cabecera}


def test_modelos_ausentes_no_se_disfrazan_de_ocr_error(caso):
    _f, plantilla, ref, hoja, _verdad, _tabla = caso
    lector = LectorFalso(error=FileNotFoundError("faltan archivos del modelo OCR"))
    with pytest.raises(FileNotFoundError, match="modelo OCR"):
        leer_texto(hoja, plantilla, ref, lector)


def test_imagen_de_otro_tamano_se_rechaza(caso):
    _f, plantilla, ref, hoja, _verdad, _tabla = caso
    with pytest.raises(ValueError, match="no coinciden"):
        leer_texto(hoja[:-10], plantilla, ref, LectorFalso())


# --- integración en el pipeline ---------------------------------------------------------------


@pytest.fixture(scope="module")
def procesada(caso):
    f, plantilla, ref, _hoja, verdad, tabla = caso
    lector = LectorFalso(_lector_segun_verdad(tabla, verdad))
    proc = procesar_foto(f.foto.read_bytes(), plantilla, ref, lector=lector)
    return proc, verdad


def test_pipeline_con_lector_trae_observaciones_cabecera_y_recortes(procesada):
    proc, verdad = procesada
    r = proc.resultado
    assert r.ocr_activo and len(r.observaciones) == len(r.filas)
    assert {c.campo for c in r.cabecera} == set(verdad["cabecera"])
    assert set(proc.recortes) == {int(i) for i, v in verdad["items"].items() if v["observacion"]}
    d = json.loads(json.dumps(r.a_dict(), allow_nan=False))
    assert d["ocr_activo"] is True and len(d["observaciones"]) == len(r.filas)
    assert d["cabecera"][0]["texto"] == "dato"


def test_pipeline_sin_lector_no_lee_texto(caso):
    f, plantilla, ref, *_ = caso
    proc = procesar_foto(f.foto.read_bytes(), plantilla, ref)
    r = proc.resultado
    assert not r.ocr_activo and r.observaciones == () and r.cabecera == ()
    assert proc.recortes == {} and not r.requiere_revision


def test_texto_dudoso_obliga_a_revisar_y_deja_la_fila_sin_revisar(caso):
    f, plantilla, ref, _hoja, verdad, tabla = caso
    lector = LectorFalso(_lector_segun_verdad(tabla, verdad, 0.3))
    proc = procesar_foto(f.foto.read_bytes(), plantilla, ref, lector=lector)
    r = proc.resultado
    assert r.requiere_revision and r.n_cabecera_dudosa == len(r.cabecera)
    assert r.n_amarillas == sum(o.tiene_tinta for o in r.observaciones)
    ev = a_evaluacion(r, plantilla, paciente="Ana", fecha=date(2026, 11, 6))
    for fila, res in zip(ev.filas, r.filas, strict=True):
        assert fila.revisado == (res.item not in r.items_amarillos)


def test_a_evaluacion_lleva_el_texto_al_excel_con_recortes(procesada, caso, tmp_path):
    proc, verdad = procesada
    plantilla = caso[1]
    ev = a_evaluacion(proc.resultado, plantilla, fecha=date(2026, 11, 6), recortes=proc.recortes)
    assert ev.paciente == "dato"  # sin --paciente, sale de la cabecera leída
    assert ev.cabecera == {"Fecha manuscrita": "dato"}
    exportar(ev, tmp_path, incluir_recortes=True)
    hoja = openpyxl.load_workbook(next(tmp_path.glob("2026-*.xlsx")))["Evaluación"]
    textos = {c.value for fila in hoja.iter_rows() for c in fila if isinstance(c.value, str)}
    escritas = {v["observacion"] for v in verdad["items"].values() if v["observacion"]}
    assert escritas <= textos
    assert len(hoja._images) == len(proc.recortes)


def test_lo_pasado_a_mano_manda_sobre_la_cabecera_leida(procesada, caso):
    proc, _verdad = procesada
    ev = a_evaluacion(
        proc.resultado, caso[1], paciente="Ana", cabecera={"Fecha manuscrita": "6/11"}
    )
    assert ev.paciente == "Ana" and ev.cabecera["Fecha manuscrita"] == "6/11"


# --- comando ---------------------------------------------------------------------------------


def test_comando_ocr_sin_modelos_da_error_claro(lote_sintetico, tmp_path, capsys, monkeypatch):
    f = lote_sintetico[0]
    carpeta = tmp_path / "plantilla"
    carpeta.mkdir()
    (carpeta / "p.json").write_text(f.plantilla.read_text("utf-8"), "utf-8")
    plantilla = cargar_plantilla(f.plantilla)
    (carpeta / plantilla.paginas[0].imagen_referencia).write_bytes(
        (f.plantilla.parent / "blanca.png").read_bytes()
    )
    monkeypatch.chdir(tmp_path)  # sin `modelos/` aquí
    codigo = main(
        ["procesar", str(f.foto), "--plantilla", str(carpeta / "p.json"),
         "--salida", str(tmp_path / "o"), "--ocr"]
    )  # fmt: skip
    err = capsys.readouterr().err
    assert codigo == 2
    assert "descargar_modelos" in err
    assert not any((tmp_path / "o").glob("*.xlsx")) if (tmp_path / "o").exists() else True
