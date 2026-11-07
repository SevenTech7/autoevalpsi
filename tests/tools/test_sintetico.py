"""BS-R1: el generador sintético dibuja lo que su verdad de terreno dice."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageOps
from tools.sintetico.formulario import FORMATOS, construir, escribir
from tools.sintetico.fotografiar import ORIENTACIONES, fotografiar, guardar_jpeg
from tools.sintetico.llenar import CASOS, fraccion_tinta, llenar
from tools.sintetico.lote import generar_lote

from autoevalpsi.core.plantilla import cargar_plantilla


@pytest.fixture(scope="module", params=list(FORMATOS))
def formulario(request, tmp_path_factory):
    destino = tmp_path_factory.mktemp(f"form_{request.param}")
    escribir(destino, [request.param])
    id_ = f"demo-5opciones-{request.param}"
    blanca = cv2.imread(str(destino / f"{id_}.png"), cv2.IMREAD_GRAYSCALE)
    return request.param, blanca, cargar_plantilla(destino / f"{id_}.json")


def _celdas(plantilla, item):
    t = plantilla.paginas[0].tablas[0]
    fila = next(f for f in t.filas if f.item == item)
    return {
        op: [x[0] + 12, fila.y[0] + 12, x[1] - 12, fila.y[1] - 12]
        for op, x in zip(t.opciones, t.columnas_x, strict=True)
    }


# --- formulario ---------------------------------------------------------------------------


def test_plantilla_carga_con_el_esquema_real_y_coincide_con_la_imagen(formulario):
    formato, blanca, plantilla = formulario
    pagina = plantilla.paginas[0]
    assert pagina.tamano_px == list(FORMATOS[formato])
    assert blanca.shape == (pagina.tamano_px[1], pagina.tamano_px[0])
    t = pagina.tablas[0]
    assert len(t.filas) == 12 and len(t.columnas_x) == 5 and t.observacion_x is not None


def test_formulario_en_blanco_tiene_las_casillas_vacias_y_la_retícula_dibujada(formulario):
    _, blanca, plantilla = formulario
    t = plantilla.paginas[0].tablas[0]
    for fila in t.filas:
        for caja in _celdas(plantilla, fila.item).values():
            assert (blanca[caja[1] : caja[3], caja[0] : caja[2]] == 255).all()
    x = t.columnas_x[2][0]  # borde izquierdo de una columna: línea vertical continua
    y0, y1 = t.filas[0].y[0], t.filas[-1].y[1]
    assert (blanca[y0 + 5 : y1 - 5, x - 1 : x + 2].min(axis=1) < 100).all()


def test_los_archivos_versionados_de_plantillas_demo_estan_al_dia(tmp_path):
    escribir(tmp_path)
    for formato in FORMATOS:
        id_ = f"demo-5opciones-{formato}"
        versionado = json.loads(Path(f"plantillas_demo/{id_}.json").read_text(encoding="utf-8"))
        assert versionado == construir(formato)[1], "regenera: python -m tools.sintetico.formulario"
        a = cv2.imread(f"plantillas_demo/{id_}.png", cv2.IMREAD_GRAYSCALE)
        b = cv2.imread(str(tmp_path / f"{id_}.png"), cv2.IMREAD_GRAYSCALE)
        assert a.shape == b.shape and np.abs(a.astype(int) - b).mean() < 1.0


# --- llenar -------------------------------------------------------------------------------


def _llenar_todos(formulario, caso, semilla=1):
    _, blanca, plantilla = formulario
    items = [f.item for f in plantilla.paginas[0].tablas[0].filas]
    llena, verdad = llenar(
        blanca, plantilla, np.random.default_rng(semilla), casos=dict.fromkeys(items, caso)
    )
    return blanca, plantilla, llena, verdad


def _tinta(blanca, llena, plantilla, item):
    return {op: fraccion_tinta(blanca, llena, c) for op, c in _celdas(plantilla, item).items()}


@pytest.mark.parametrize("caso", CASOS)
def test_la_tinta_dibujada_coincide_con_la_verdad_por_caso(formulario, caso):
    blanca, plantilla, llena, verdad = _llenar_todos(formulario, caso)
    for item, v in verdad["items"].items():
        assert v["caso"] == caso
        tinta = _tinta(blanca, llena, plantilla, int(item))
        marcadas = set(v["marcas"])
        for op, f in tinta.items():
            if op in marcadas and caso != "tenue":
                assert f > 0.01, (item, op, f)
            if op not in marcadas and caso not in ("tachon", "fuera"):
                assert f < 0.005, (item, op, f)
        if caso == "vacia":
            assert v["marcas"] == []
        elif caso == "doble":
            assert len(v["marcas"]) == 2
        elif caso == "tachon":
            assert v["tachada"] not in marcadas and tinta[v["tachada"]] > 0.03
        elif caso == "fuera":
            assert tinta[v["marcas"][0]] == max(tinta.values())
        elif caso == "tenue":
            assert all(tinta[op] > 0 for op in marcadas)


def test_marca_tenue_tiene_menos_tinta_que_la_normal(formulario):
    blanca, plantilla, normal, vn = _llenar_todos(formulario, "normal")
    _, _, tenue, vt = _llenar_todos(formulario, "tenue")
    suma = lambda llena, v: sum(
        _tinta(blanca, llena, plantilla, int(i))[x["marcas"][0]] for i, x in v["items"].items()
    )
    assert suma(tenue, vt) < suma(normal, vn)


def test_la_marca_que_sale_de_la_celda_deja_tinta_fuera_de_ella(formulario):
    blanca, plantilla, llena, verdad = _llenar_todos(formulario, "fuera")
    t = plantilla.paginas[0].tablas[0]
    for fila in t.filas:
        op = verdad["items"][str(fila.item)]["marcas"][0]
        x = t.columnas_x[t.opciones.index(op)]
        celda = [x[0], fila.y[0], x[1], fila.y[1]]
        ampliada = [x[0] - 40, fila.y[0] - 40, x[1] + 40, fila.y[1] + 40]
        px = lambda c: fraccion_tinta(blanca, llena, c) * (c[2] - c[0]) * (c[3] - c[1])
        assert px(ampliada) - px(celda) > 20, f"item {fila.item}"


def test_observaciones_y_cabecera_escritas_donde_dice_la_verdad(formulario):
    blanca, plantilla, llena, verdad = _llenar_todos(formulario, "normal", semilla=7)
    t = plantilla.paginas[0].tablas[0]
    con = [f for f in t.filas if verdad["items"][str(f.item)]["observacion"]]
    sin = [f for f in t.filas if not verdad["items"][str(f.item)]["observacion"]]
    assert con and sin
    obs = lambda f: [t.observacion_x[0] + 8, f.y[0] + 8, t.observacion_x[1] - 8, f.y[1] - 8]
    assert all(fraccion_tinta(blanca, llena, obs(f)) > 0.003 for f in con)
    assert all(fraccion_tinta(blanca, llena, obs(f)) == 0 for f in sin)
    for c in plantilla.paginas[0].cabecera:
        x0, y0, x1, y1 = c.caja
        assert verdad["cabecera"][c.campo]
        assert fraccion_tinta(blanca, llena, [x0 + 6, y0 + 6, x1 - 6, y1 - 6]) > 0.003


def test_llenar_es_determinista_y_depende_de_la_semilla(formulario):
    _, blanca, plantilla = formulario
    a, va = llenar(blanca, plantilla, np.random.default_rng(3))
    b, vb = llenar(blanca, plantilla, np.random.default_rng(3))
    _c, vc = llenar(blanca, plantilla, np.random.default_rng(4))
    assert (a == b).all() and va == vb
    assert va != vc


def test_caso_desconocido_falla(formulario):
    _, blanca, plantilla = formulario
    with pytest.raises(ValueError, match="caso desconocido"):
        llenar(blanca, plantilla, np.random.default_rng(1), casos={1: "inexistente"})


# --- fotografiar --------------------------------------------------------------------------


def _hoja_y_foto(semilla=5, **kw):
    blanca, datos = construir("a4")
    plantilla = cargar_plantilla_dict(datos)
    hoja, _ = llenar(blanca, plantilla, np.random.default_rng(semilla))
    foto, meta = fotografiar(hoja, np.random.default_rng(semilla), tamano=(1500, 2000), **kw)
    return hoja, foto, meta


def cargar_plantilla_dict(datos):
    from autoevalpsi.core.plantilla import Plantilla

    return Plantilla.model_validate(datos)


def test_la_homografia_de_la_verdad_lleva_la_hoja_a_la_foto():
    hoja, foto, meta = _hoja_y_foto()
    assert foto.shape == (2000, 1500, 3) and meta["tamano_foto"] == [1500, 2000]
    H = np.array(meta["homografia"])
    w, h = meta["tamano_hoja"]
    esquinas = cv2.perspectiveTransform(
        np.array([[[0, 0], [w, 0], [w, h], [0, h]]], np.float32), H
    )[0]
    assert np.allclose(esquinas, meta["esquinas"], atol=1.0)
    # Enderezar la foto con la homografía inversa reproduce la hoja.
    plana = cv2.warpPerspective(foto, np.linalg.inv(H), (w, h))
    a = cv2.cvtColor(plana, cv2.COLOR_BGR2GRAY).astype(float)
    b = cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY).astype(float)
    corr = lambda x, y: np.corrcoef(
        cv2.resize(x, (w // 4, h // 4)).ravel(), cv2.resize(y, (w // 4, h // 4)).ravel()
    )[0, 1]
    # Una homografía desplazada 30 px (de hoja) debe correlacionar claramente peor.
    corrida = cv2.warpPerspective(
        foto, np.linalg.inv(H @ np.array([[1, 0, 30], [0, 1, 0], [0, 0, 1]])), (w, h)
    )
    peor = cv2.cvtColor(corrida, cv2.COLOR_BGR2GRAY).astype(float)
    assert corr(a, b) > 0.8
    assert corr(a, b) > corr(peor, b) + 0.1


def test_fotografiar_es_determinista_y_cambia_con_la_semilla():
    _, f1, m1 = _hoja_y_foto(5)
    _, f2, m2 = _hoja_y_foto(5)
    _, f3, _ = _hoja_y_foto(6)
    assert (f1 == f2).all() and m1 == m2
    assert not np.array_equal(f1, f3)


@pytest.mark.parametrize("orientacion", ORIENTACIONES)
def test_exif_orientacion_se_aplica_y_recupera_la_foto_vertical(tmp_path, orientacion):
    _, foto, _ = _hoja_y_foto()
    ruta = tmp_path / "f.jpg"
    guardar_jpeg(foto, ruta, calidad=90, orientacion=orientacion)
    img = Image.open(ruta)
    assert img.getexif()[0x0112] == orientacion
    assert (img.size == (foto.shape[0], foto.shape[1])) == (orientacion in (6, 8))
    leida = np.asarray(ImageOps.exif_transpose(img).convert("RGB"))[:, :, ::-1]
    assert leida.shape == foto.shape
    assert np.abs(leida.astype(int) - foto).mean() < 6


# --- lote ---------------------------------------------------------------------------------


def test_lote_completo_y_con_verdad_valida(lote_sintetico):
    assert len(lote_sintetico) == 6
    casos = set()
    for f in lote_sintetico:
        assert f.foto.exists() and f.hoja.exists()
        v = json.loads(f.verdad.read_text(encoding="utf-8"))
        plantilla = cargar_plantilla(f.plantilla)
        assert v["plantilla"] == plantilla.id and set(v["items"]) == {str(i) for i in range(1, 13)}
        assert Image.open(f.foto).getexif()[0x0112] == v["exif_orientacion"]
        casos |= {i["caso"] for i in v["items"].values()}
    assert casos == set(CASOS)
    v0 = json.loads(lote_sintetico[0].verdad.read_text(encoding="utf-8"))
    assert {i["caso"] for i in v0["items"].values()} == {"normal"}


def test_lote_es_reproducible_con_la_misma_semilla(lote_sintetico, tmp_path):
    otro = generar_lote(tmp_path, n=2, formato="a4")
    for a, b in zip(lote_sintetico, otro, strict=False):
        assert a.foto.read_bytes() == b.foto.read_bytes()
        assert a.verdad.read_text(encoding="utf-8") == b.verdad.read_text(encoding="utf-8")


def test_lote_en_carta_usa_la_plantilla_de_carta(tmp_path):
    f = generar_lote(tmp_path, n=1, formato="carta", tamano_foto=(900, 1200))[0]
    assert cargar_plantilla(f.plantilla).paginas[0].tamano_px == list(FORMATOS["carta"])
