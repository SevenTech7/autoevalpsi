"""CO-R0: el ejemplo de plan.md carga y cada regla del esquema falla nombrando el campo."""

import copy
import json

import pytest

from autoevalpsi.core.plantilla import PlantillaInvalida, cargar_plantilla

EJEMPLO = {
    "id": "escala-ejemplo",
    "nombre": "Escala de ejemplo",
    "version": 1,
    "paginas": [
        {
            "imagen_referencia": "escala-ejemplo-p1.png",
            "tamano_px": [2480, 3508],
            "cabecera": [
                {"campo": "paciente", "caja": [300, 220, 1500, 300], "tipo": "texto"},
                {"campo": "fecha", "caja": [1700, 220, 2300, 300], "tipo": "texto"},
            ],
            "opciones": ["Nunca", "Casi nunca", "A veces", "Casi siempre", "Siempre"],
            "columnas_x": [[1180, 1290], [1290, 1400], [1400, 1510], [1510, 1620], [1620, 1730]],
            "observacion_x": [1740, 2400],
            "filas": [
                {"item": 1, "texto": "Descripción del ítem 1", "y": [520, 600]},
                {"item": 2, "texto": "Descripción del ítem 2", "y": [600, 680]},
            ],
        }
    ],
}

CLAVES_TABLA = ("opciones", "columnas_x", "observacion_x", "filas")


def _escribir(tmp_path, datos):
    ruta = tmp_path / "p.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def _falla(tmp_path, mutar, *fragmentos):
    datos = copy.deepcopy(EJEMPLO)
    mutar(datos)
    with pytest.raises(PlantillaInvalida) as e:
        cargar_plantilla(_escribir(tmp_path, datos))
    for f in fragmentos:
        assert f in str(e.value)


def test_ejemplo_de_plan_md_carga(tmp_path):
    p = cargar_plantilla(_escribir(tmp_path, EJEMPLO))
    assert p.esquema_version == 1
    assert len(p.paginas[0].tablas) == 1  # formato plano -> una tabla
    assert [f.item for f in p.paginas[0].tablas[0].filas] == [1, 2]


def test_formato_con_tablas_equivale_al_plano(tmp_path):
    datos = copy.deepcopy(EJEMPLO)
    pag = datos["paginas"][0]
    pag["tablas"] = [{k: pag.pop(k) for k in CLAVES_TABLA}]
    assert cargar_plantilla(_escribir(tmp_path, datos)) == cargar_plantilla(
        _escribir(tmp_path, EJEMPLO)
    )


def test_varias_tablas_en_una_pagina(tmp_path):
    datos = copy.deepcopy(EJEMPLO)
    pag = datos["paginas"][0]
    t1 = {k: pag.pop(k) for k in CLAVES_TABLA}
    t2 = copy.deepcopy(t1)
    t2["opciones"] = ["No", "Sí"]
    t2["columnas_x"] = [[1180, 1290], [1290, 1400]]
    t2["filas"] = [{"item": 3, "y": [900, 980]}]
    pag["tablas"] = [t1, t2]
    assert len(cargar_plantilla(_escribir(tmp_path, datos)).paginas[0].tablas) == 2


def test_plano_y_tablas_a_la_vez_se_rechaza(tmp_path):
    _falla(tmp_path, lambda d: d["paginas"][0].update(tablas=[]), "no ambos")


def test_caja_de_cabecera_fuera_de_tamano(tmp_path):
    _falla(
        tmp_path,
        lambda d: d["paginas"][0]["cabecera"][1].update(caja=[1700, 220, 2600, 300]),
        "cabecera 'fecha'",
        "sale de tamano_px",
    )


def test_opciones_y_columnas_de_distinta_longitud(tmp_path):
    _falla(
        tmp_path,
        lambda d: d["paginas"][0]["opciones"].pop(),
        "tablas.0",
        "misma longitud",
    )


def test_columnas_solapadas(tmp_path):
    _falla(
        tmp_path,
        lambda d: d["paginas"][0]["columnas_x"].__setitem__(1, [1250, 1400]),
        "columnas_x",
        "se solapa",
    )


def test_filas_desordenadas(tmp_path):
    def mutar(d):
        f = d["paginas"][0]["filas"]
        f[0], f[1] = f[1], f[0]

    _falla(tmp_path, mutar, "filas", "ordenado")


def test_item_repetido(tmp_path):
    _falla(
        tmp_path,
        lambda d: d["paginas"][0]["filas"][1].update(item=1),
        "item repetidos",
        "[1]",
    )


def test_item_repetido_entre_paginas(tmp_path):
    def mutar(d):
        d["paginas"].append(copy.deepcopy(d["paginas"][0]))

    _falla(tmp_path, mutar, "item repetidos")


def test_esquema_version_desconocida(tmp_path):
    _falla(tmp_path, lambda d: d.update(esquema_version=2), "esquema_version", "no soportada")


def test_intervalo_invertido(tmp_path):
    _falla(
        tmp_path,
        lambda d: d["paginas"][0]["filas"][0].update(y=[600, 520]),
        "filas.0.y",
        "inicio < fin",
    )


def test_campo_desconocido_se_rechaza(tmp_path):
    _falla(tmp_path, lambda d: d.update(nombr="x"), "nombr")


def test_json_mal_formado(tmp_path):
    ruta = tmp_path / "mal.json"
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(PlantillaInvalida, match="JSON mal formado"):
        cargar_plantilla(ruta)
