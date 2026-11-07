"""CO-R6: exportador Excel."""

import os
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from openpyxl import load_workbook

from autoevalpsi.core import excel
from autoevalpsi.core.excel import (
    ArchivoBloqueado,
    Evaluacion,
    FilaEvaluacion,
    NombreArchivo,
    actualizar_consolidado,
    exportar,
    exportar_evaluacion,
    iniciales,
    nombre_archivo,
    ruta_consolidado,
    sanear_nombre,
)
from autoevalpsi.core.plantilla import cargar_plantilla

PLANTILLA = Path(__file__).parents[2] / "plantillas_demo" / "demo-5opciones-a4.json"


@pytest.fixture(scope="module")
def plantilla():
    return cargar_plantilla(PLANTILLA)


def _ev(plantilla, id="ev-1", paciente="Ana María Pérez", fecha=date(2026, 11, 6), filas=None):
    if filas is None:
        filas = (
            FilaEvaluacion(1, "Casi nunca", "texto transcrito", True),
            FilaEvaluacion(2, "Siempre"),
            FilaEvaluacion(3, None),
        )
    return Evaluacion(id, plantilla, fecha, paciente, tuple(filas), {"edad": "34"})


def _hoja(ruta, nombre="Evaluación"):
    return load_workbook(ruta)[nombre]


# --- fecha y hora de Bolivia ------------------------------------------------------------------


def test_fecha_con_hora_se_escribe_en_hora_de_bolivia(plantilla, tmp_path):
    momento = datetime(2026, 11, 8, 2, 35, tzinfo=UTC)  # 22:35 del día 7 en Bolivia
    archivos = exportar(_ev(plantilla, fecha=momento), tmp_path)
    celda = _hoja(archivos.evaluacion).cell(2, 2)
    assert celda.value == datetime(2026, 11, 7, 22, 35)
    assert celda.number_format == "DD/MM/YYYY HH:MM"
    consolidado = _hoja(archivos.consolidado, "Consolidado")
    col = [c.value for c in consolidado[1]].index("Fecha") + 1
    assert consolidado.cell(2, col).value == datetime(2026, 11, 7, 22, 35)


def test_el_nombre_del_archivo_lleva_el_dia_de_bolivia(plantilla):
    momento = datetime(2026, 11, 8, 2, 35, tzinfo=UTC)
    assert nombre_archivo(_ev(plantilla, fecha=momento)).startswith("2026-11-07_")


def test_fecha_sin_hora_sigue_como_texto_aaaa_mm_dd(plantilla, tmp_path):
    archivos = exportar(_ev(plantilla), tmp_path)
    assert _hoja(archivos.evaluacion).cell(2, 2).value == "2026-11-06"


# --- nombres (CO-07) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("crudo", "esperado"),
    [
        ("Ana María Pérez", "Ana_María_Pérez"),
        ('a/b\\c:d*e?f"g<h>i|j', "a_b_c_d_e_f_g_h_i_j"),
        ("  ..Juan..  ", "Juan"),
        ("", "sin-nombre"),
        ("???", "sin-nombre"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("x" * 200, "x" * 60),
    ],
)
def test_sanear_nombre(crudo, esperado):
    assert sanear_nombre(crudo) == esperado


def test_iniciales():
    assert iniciales("Ana María Pérez") == "AMP"
    assert iniciales("  ") == "sin-nombre"


def test_nombre_de_archivo_de_plan(plantilla):
    ev = _ev(plantilla)
    assert nombre_archivo(ev) == "2026-11-06_demo-5opciones-a4_Ana_María_Pérez.xlsx"
    assert nombre_archivo(ev, NombreArchivo.INICIALES) == "2026-11-06_demo-5opciones-a4_AMP.xlsx"


def test_nombre_nunca_trae_caracteres_invalidos(plantilla):
    nombre = nombre_archivo(_ev(plantilla, paciente='../..\\evil:*?"<>|'))
    assert not set('/\\:*?"<>|') & set(nombre)


# --- archivo de la evaluación ---------------------------------------------------------------


def test_hoja_evaluacion_tiene_la_forma_del_papel(tmp_path, plantilla):
    ruta = exportar_evaluacion(_ev(plantilla), tmp_path)
    h = _hoja(ruta)
    assert [h.cell(r, 1).value for r in (1, 2, 3, 4)] == ["Formulario", "Fecha", "Paciente", "edad"]
    assert h["B2"].value == "2026-11-06"
    assert h["B3"].value == "Ana María Pérez"
    assert [c.value for c in h[6]] == [
        "Ítem", "Descripción", "Nunca", "Casi nunca", "A veces", "Casi siempre", "Siempre",
        "Observación", "Revisado",
    ]  # fmt: skip
    f1 = [c.value for c in h[7]]
    assert f1 == [
        1,
        "Descripcion del item 1",
        None,
        "X",
        None,
        None,
        None,
        "texto transcrito",
        "Sí",
    ]
    f2 = [c.value for c in h[8]]
    assert f2[2:7] == [None, None, None, None, "X"] and f2[8] == "No"
    assert [c.value for c in h[9]][2:7] == [None] * 5  # ítem 3 sin respuesta


def test_item_que_falta_queda_vacio_y_sin_revisar(tmp_path, plantilla):
    h = _hoja(exportar_evaluacion(_ev(plantilla, filas=()), tmp_path))
    assert [c.value for c in h[7]][2:] == [None] * 5 + [None, "No"]


def test_texto_que_parece_formula_se_guarda_como_texto(tmp_path, plantilla):
    ev = _ev(plantilla, paciente="=1+1", filas=[FilaEvaluacion(1, None, "=HYPERLINK(1)")])
    ruta = exportar_evaluacion(ev, tmp_path)
    h = _hoja(ruta)
    assert h["B3"].value == "=1+1" and h["B3"].data_type == "s"
    assert h["H7"].data_type == "s"


def test_recorte_como_imagen(tmp_path, plantilla):
    recorte = np.full((120, 400, 3), 200, np.uint8)
    ev = _ev(plantilla, filas=[FilaEvaluacion(1, "Nunca", "x", False, recorte)])
    ruta = exportar_evaluacion(ev, tmp_path, incluir_recortes=True)
    libro = load_workbook(ruta)
    h = libro[excel.HOJA_EVALUACION]
    assert h["J6"].value == "Recorte"
    assert len(h._images) == 1
    sin = load_workbook(exportar_evaluacion(ev, tmp_path / "otra"))[excel.HOJA_EVALUACION]
    assert len(sin._images) == 0 and sin["J6"].value is None


def test_reexportar_la_misma_evaluacion_sobrescribe(tmp_path, plantilla):
    a = exportar_evaluacion(_ev(plantilla), tmp_path)
    b = exportar_evaluacion(_ev(plantilla, filas=[FilaEvaluacion(1, "Nunca")]), tmp_path)
    assert a == b
    assert len(list(tmp_path.glob("*.xlsx"))) == 1
    assert _hoja(b)["C7"].value == "X"


def test_otra_evaluacion_con_el_mismo_nombre_no_pisa_la_primera(tmp_path, plantilla):
    a = exportar_evaluacion(_ev(plantilla, id="ev-1"), tmp_path)
    b = exportar_evaluacion(_ev(plantilla, id="ev-2"), tmp_path)
    c = exportar_evaluacion(_ev(plantilla, id="ev-3"), tmp_path)
    assert len({a, b, c}) == 3
    assert b.stem.endswith("(2)") and c.stem.endswith("(3)")
    assert exportar_evaluacion(_ev(plantilla, id="ev-2"), tmp_path) == b


def test_opcion_o_item_invalidos_se_rechazan(plantilla):
    with pytest.raises(ValueError, match="no es una opción válida"):
        _ev(plantilla, filas=[FilaEvaluacion(1, "Quizás")])
    with pytest.raises(ValueError, match="no existe en la plantilla"):
        _ev(plantilla, filas=[FilaEvaluacion(999, "Nunca")])
    with pytest.raises(ValueError, match="repetido"):
        _ev(plantilla, filas=[FilaEvaluacion(1, "Nunca"), FilaEvaluacion(1, "Siempre")])
    with pytest.raises(ValueError, match="id"):
        _ev(plantilla, id=" ")


# --- consolidado ----------------------------------------------------------------------------


def _filas_consolidado(ruta):
    return list(_hoja(ruta, excel.HOJA_CONSOLIDADO).iter_rows(values_only=True))


def test_consolidado_una_fila_por_evaluacion(tmp_path, plantilla):
    actualizar_consolidado(_ev(plantilla, id="ev-1"), tmp_path)
    ruta = actualizar_consolidado(
        _ev(plantilla, id="ev-2", paciente="Luis", filas=[FilaEvaluacion(2, "Nunca")]), tmp_path
    )
    assert ruta == ruta_consolidado(plantilla, tmp_path)
    filas = _filas_consolidado(ruta)
    assert filas[0][:6] == (
        "ID evaluación",
        "Fecha",
        "Paciente",
        "Versión plantilla",
        "Ítem 1",
        "Ítem 2",
    )
    assert len(filas) == 3
    assert filas[1][:7] == (
        "ev-1",
        "2026-11-06",
        "Ana María Pérez",
        1,
        "Casi nunca",
        "Siempre",
        None,
    )
    assert filas[2][:6] == ("ev-2", "2026-11-06", "Luis", 1, None, "Nunca")


def test_reexportar_no_duplica_y_reemplaza_la_fila(tmp_path, plantilla):
    actualizar_consolidado(_ev(plantilla, id="ev-1"), tmp_path)
    actualizar_consolidado(_ev(plantilla, id="ev-2"), tmp_path)
    ruta = actualizar_consolidado(
        _ev(plantilla, id="ev-1", filas=[FilaEvaluacion(2, "A veces")]), tmp_path
    )
    filas = _filas_consolidado(ruta)
    assert [f[0] for f in filas[1:]] == ["ev-1", "ev-2"]
    assert filas[1][4:6] == (None, "A veces")  # el ítem 1 anterior se borró


def test_consolidado_agrega_columnas_si_la_plantilla_crece(tmp_path, plantilla):
    actualizar_consolidado(_ev(plantilla), tmp_path)
    ruta = ruta_consolidado(plantilla, tmp_path)
    libro = load_workbook(ruta)
    hoja = libro[excel.HOJA_CONSOLIDADO]
    hoja.delete_cols(hoja.max_column)  # simula un consolidado hecho con una versión con menos ítems
    libro.save(ruta)
    cols_antes = len(_filas_consolidado(ruta)[0])
    ev = _ev(plantilla, filas=[FilaEvaluacion(12, "Nunca")])
    actualizar_consolidado(ev, tmp_path)
    cabecera = _filas_consolidado(ruta)[0]
    assert len(cabecera) == cols_antes + 1 and cabecera[-1] == "Ítem 12"


def test_consolidado_ajeno_se_rechaza(tmp_path, plantilla):
    ruta = ruta_consolidado(plantilla, tmp_path)
    libro = load_workbook(exportar_evaluacion(_ev(plantilla), tmp_path / "x"))
    libro.save(ruta)
    with pytest.raises(ValueError, match="no es un consolidado"):
        actualizar_consolidado(_ev(plantilla), tmp_path)


def test_exportar_hace_las_dos_cosas(tmp_path, plantilla):
    r = exportar(_ev(plantilla), tmp_path, nombre=NombreArchivo.INICIALES)
    assert r.evaluacion.name.endswith("_AMP.xlsx") and r.consolidado.exists()


# --- archivo bloqueado (CO-08) --------------------------------------------------------------


@pytest.fixture
def bloquear(monkeypatch):
    """Windows rechaza `os.replace` sobre un archivo abierto en Excel: se simula para `destino`."""
    real = os.replace
    objetivos: set[Path] = set()

    def replace(origen, destino):
        if Path(destino) in objetivos:
            raise PermissionError(13, "Permission denied", str(destino))
        return real(origen, destino)

    monkeypatch.setattr(excel.os, "replace", replace)
    return objetivos


def test_consolidado_bloqueado_lanza_error_tipado_y_no_pierde_nada(tmp_path, plantilla, bloquear):
    ruta = actualizar_consolidado(_ev(plantilla, id="ev-1"), tmp_path)
    antes = ruta.read_bytes()
    bloquear.add(ruta)
    with pytest.raises(ArchivoBloqueado, match="ciérralo") as e:
        exportar(_ev(plantilla, id="ev-2"), tmp_path)
    assert e.value.ruta == ruta
    assert ruta.read_bytes() == antes  # el consolidado anterior quedó intacto
    assert list(tmp_path.glob(".*.tmp")) == []  # sin temporales
    assert len(list(tmp_path.glob("2026-*.xlsx"))) == 1  # la evaluación nueva ya se guardó
    bloquear.clear()
    actualizar_consolidado(_ev(plantilla, id="ev-2"), tmp_path)  # reintento
    assert len(_filas_consolidado(ruta)) == 3


def test_archivo_de_evaluacion_bloqueado(tmp_path, plantilla, bloquear):
    ruta = exportar_evaluacion(_ev(plantilla), tmp_path)
    bloquear.add(ruta)
    with pytest.raises(ArchivoBloqueado):
        exportar_evaluacion(_ev(plantilla, filas=[FilaEvaluacion(1, "Nunca")]), tmp_path)
    assert _hoja(ruta)["D7"].value == "X"  # sigue la versión anterior
