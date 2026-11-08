"""VD-R3: la evaluación escrita en el libro de Excel de la usuaria."""

from datetime import date

import pytest
from openpyxl import Workbook, load_workbook

from autoevalpsi.core.excel import Evaluacion, FilaEvaluacion, exportar
from autoevalpsi.core.libro import HOJA_DATOS, LibroBaseInvalido
from autoevalpsi.core.plantilla import Plantilla


def plantilla(**extra) -> Plantilla:
    datos = {
        "esquema_version": 1,
        "id": "vine",
        "nombre": "Vineland",
        "version": 2,
        "libro": {"archivo": "base.xlsx", "vaciar": ["A1:B6", "D1:D2"]},
        "paginas": [
            {
                "imagen_referencia": "v.png",
                "tamano_px": [300, 300],
                "tablas": [
                    {
                        "tipo": "digito",
                        "opciones": ["0", "1", "2"],
                        "columnas_x": [[100, 150]],
                        "filas": [
                            {"item": 1, "texto": "a · 1", "y": [10, 40], "celda": "A1"},
                            {"item": 2, "texto": "a · 2", "y": [50, 80], "celda": "A2"},
                            {"item": 3, "texto": "a · 3", "y": [90, 120], "celda": "A3"},
                        ],
                    },
                    {
                        "opciones": ["Sí", "No"],
                        "columnas_x": [[100, 130], [140, 170]],
                        "filas": [{"item": 4, "texto": "b", "y": [130, 160], "celda": "B1"}],
                    },
                ],
            }
        ],
        **extra,
    }
    return Plantilla.model_validate(datos)


@pytest.fixture
def base(tmp_path):
    """El libro de la usuaria: sumas con fórmula, valores de otro paciente y notas."""
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hoja1"
    for r in range(1, 7):
        hoja.cell(r, 1, 2)  # valores viejos de otro paciente
        hoja.cell(r, 2, 1)
    hoja["A9"] = "=SUM(A1:A6)"
    hoja["B9"] = "=SUM(B1:B6)"
    hoja["D1"] = 99
    hoja["D2"] = "nota vieja"
    hoja["D3"] = "esto no se vacía"
    ruta = tmp_path / "base.xlsx"
    libro.save(ruta)
    return ruta


def evaluacion(**kw) -> Evaluacion:
    p = plantilla()
    filas = (
        FilaEvaluacion(1, "2"),
        FilaEvaluacion(2, "0"),
        FilaEvaluacion(3, None),  # sin respuesta: vacía, no se inventa
        FilaEvaluacion(4, "Sí"),
    )
    return Evaluacion(
        id="ev1", plantilla=p, fecha=date(2026, 11, 7), paciente="Ana Pérez", filas=filas, **kw
    )


def test_las_celdas_mapeadas_se_llenan_con_numeros_y_texto(tmp_path, base):
    r = exportar(evaluacion(), tmp_path / "salida", libro_base=base)
    hoja = load_workbook(r.evaluacion)["Hoja1"]
    assert hoja["A1"].value == 2 and isinstance(hoja["A1"].value, int)
    assert hoja["A2"].value == 0
    assert hoja["A3"].value is None
    assert hoja["B1"].value == "Sí"


def test_se_vacian_los_rangos_pero_nunca_las_formulas_ni_lo_demas(tmp_path, base):
    r = exportar(evaluacion(), tmp_path / "salida", libro_base=base)
    hoja = load_workbook(r.evaluacion)["Hoja1"]
    assert hoja["A4"].value is None and hoja["B6"].value is None  # valores viejos fuera
    assert hoja["D1"].value is None and hoja["D2"].value is None
    assert hoja["D3"].value == "esto no se vacía"
    assert hoja["A9"].value == "=SUM(A1:A6)"  # la suma sigue siendo una fórmula
    assert hoja["B9"].value == "=SUM(B1:B6)"


def test_agrega_una_hoja_con_paciente_fecha_y_formulario(tmp_path, base):
    r = exportar(evaluacion(cabecera={"Cargo": "docente"}), tmp_path / "salida", libro_base=base)
    datos = load_workbook(r.evaluacion)[HOJA_DATOS]
    filas = {datos.cell(i, 1).value: datos.cell(i, 2).value for i in range(1, 6)}
    assert filas["Paciente"] == "Ana Pérez"
    assert filas["Fecha"] == "07/11/2026"
    assert filas["Formulario"] == "Vineland (versión 2)"
    assert filas["Cargo"] == "docente"


def test_el_libro_base_no_se_modifica(tmp_path, base):
    antes = base.read_bytes()
    exportar(evaluacion(), tmp_path / "salida", libro_base=base)
    assert base.read_bytes() == antes


def test_reexportar_la_misma_evaluacion_reemplaza_el_archivo(tmp_path, base):
    a = exportar(evaluacion(), tmp_path / "salida", libro_base=base)
    b = exportar(evaluacion(), tmp_path / "salida", libro_base=base)
    assert a.evaluacion == b.evaluacion
    assert len(list((tmp_path / "salida").glob("*.xlsx"))) == 2  # el libro y el consolidado


def test_sin_libro_base_la_exportacion_se_rechaza_con_un_mensaje(tmp_path):
    with pytest.raises(ValueError, match="libro de Excel"):
        exportar(evaluacion(), tmp_path / "salida")


def test_un_libro_base_ilegible_dice_cual(tmp_path):
    malo = tmp_path / "base.xlsx"
    malo.write_bytes(b"no soy un excel")
    with pytest.raises(LibroBaseInvalido, match="base.xlsx"):
        exportar(evaluacion(), tmp_path / "salida", libro_base=malo)


def test_el_esquema_valida_las_celdas_y_los_rangos():
    with pytest.raises(ValueError, match="celda de Excel no válida"):
        Plantilla.model_validate({**plantilla().model_dump(), "paginas": _con_celda("1A")})
    with pytest.raises(ValueError, match="misma celda"):
        Plantilla.model_validate({**plantilla().model_dump(), "paginas": _con_celda("A1")})
    with pytest.raises(ValueError, match="rango de Excel"):
        plantilla(libro={"archivo": "b.xlsx", "vaciar": ["no-es-un-rango"]})


def test_celdas_sin_libro_declarado_se_aceptan_y_no_se_usan():
    datos = plantilla().model_dump()
    datos["libro"] = None  # el constructor las deja sugeridas antes de que haya un libro
    assert Plantilla.model_validate(datos).libro is None


def test_una_plantilla_sin_libro_ni_celdas_sigue_siendo_valida():
    datos = plantilla().model_dump()
    datos["libro"] = None
    for t in datos["paginas"][0]["tablas"]:
        for f in t["filas"]:
            f["celda"] = None
    assert Plantilla.model_validate(datos).libro is None


def _con_celda(celda: str):
    datos = plantilla().model_dump()
    paginas = datos["paginas"]
    paginas[0]["tablas"][0]["filas"][1]["celda"] = celda
    return paginas
