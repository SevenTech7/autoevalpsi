"""AP-R4: lo que el servidor le da a la interfaz React (estáticos, configuración, borrar fotos)."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.servidor import crear_app

TOKEN = "token-de-prueba-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
LAPTOP = ("127.0.0.1", 50000)
CELULAR = ("192.168.1.50", 40000)


@pytest.fixture(scope="module")
def zip_plantilla(lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    imagen = datos["paginas"][0]["imagen_referencia"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plantilla.json", (carpeta / "plantilla.json").read_bytes())
        zf.writestr(imagen, (carpeta / "blanca.png").read_bytes())
    return buf.getvalue()


@pytest.fixture
def estaticos(tmp_path):
    carpeta = tmp_path / "estaticos"
    (carpeta / "assets").mkdir(parents=True)
    (carpeta / "index.html").write_text("<!doctype html><title>UI</title>", encoding="utf-8")
    (carpeta / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return carpeta


@pytest.fixture
def entorno(tmp_path, zip_plantilla, estaticos):
    bd = BaseDatos(tmp_path / "datos")
    plantillas = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    app = crear_app(bd, plantillas, token=TOKEN, estaticos=estaticos)
    with (
        TestClient(app, headers=AUTH, client=LAPTOP) as laptop,
        TestClient(app, client=CELULAR) as celular,
    ):
        yield laptop, celular, app, bd
    bd.cerrar()


def _cod(r) -> str:
    return r.json()["detail"]["codigo"]


# --- la interfaz compilada ---------------------------------------------------------------------


def test_la_raiz_sirve_el_index_sin_token_y_sin_cache(entorno):
    _, celular, _, _ = entorno
    for cliente in (TestClient(entorno[2], client=LAPTOP), celular):
        r = cliente.get("/")
        assert r.status_code == 200 and "<title>UI</title>" in r.text
        assert r.headers["cache-control"] == "no-store"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'self'" in r.headers["content-security-policy"]


def test_los_assets_se_sirven_y_no_se_escapan_de_la_carpeta(entorno, tmp_path):
    _, celular, _, _ = entorno
    assert celular.get("/assets/app.js").text == "console.log(1)"
    assert celular.get("/assets/no-existe.js").status_code == 404
    (tmp_path / "estaticos" / "secreto.txt").write_text("no", encoding="utf-8")
    assert celular.get("/assets/../secreto.txt").status_code in (400, 404)
    assert celular.get("/assets/%2e%2e/secreto.txt").status_code in (400, 404)


def test_sin_compilar_la_raiz_explica_que_falta_la_interfaz(tmp_path, zip_plantilla):
    bd = BaseDatos(tmp_path / "datos")
    try:
        app = crear_app(
            bd,
            RepositorioPlantillas(tmp_path / "p"),
            token=TOKEN,
            estaticos=tmp_path / "no-existe",
        )
        with TestClient(app, client=LAPTOP) as c:
            r = c.get("/")
            assert r.status_code == 503 and "compil" in r.text.lower()
            assert c.get("/api/salud").status_code == 200  # la API sigue en pie
    finally:
        bd.cerrar()


def test_la_pagina_del_celular_sigue_en_captura(entorno):
    r = entorno[1].get("/captura")
    assert r.status_code == 200 and "<title>UI</title>" not in r.text


# --- configuración -----------------------------------------------------------------------------


def test_configuracion_por_defecto_muestra_la_carpeta_de_la_raiz(entorno):
    laptop, _, _, bd = entorno
    c = laptop.get("/api/configuracion").json()
    assert c["carpeta_exportacion"] is None
    assert c["carpeta_exportacion_efectiva"] == str(bd.raiz / "exportaciones")


def test_guardar_la_carpeta_de_exportacion_la_crea_y_la_usa(entorno, tmp_path):
    laptop, _, _, bd = entorno
    destino = tmp_path / "Mis Excel"
    r = laptop.put("/api/configuracion", json={"carpeta_exportacion": str(destino)})
    assert r.status_code == 200, r.text
    assert destino.is_dir()
    assert r.json()["carpeta_exportacion"] == str(destino)
    assert bd.leer_configuracion("carpeta_exportacion") == str(destino)
    assert laptop.get("/api/configuracion").json()["carpeta_exportacion_efectiva"] == str(destino)


def test_carpeta_vacia_vuelve_al_valor_por_defecto(entorno, tmp_path):
    laptop, _, _, bd = entorno
    laptop.put("/api/configuracion", json={"carpeta_exportacion": str(tmp_path / "x")})
    r = laptop.put("/api/configuracion", json={"carpeta_exportacion": ""})
    assert r.status_code == 200 and r.json()["carpeta_exportacion"] is None
    assert r.json()["carpeta_exportacion_efectiva"] == str(bd.raiz / "exportaciones")


def test_carpeta_relativa_o_imposible_se_rechaza(entorno, tmp_path):
    laptop, _, _, bd = entorno
    r = laptop.put("/api/configuracion", json={"carpeta_exportacion": "relativa/carpeta"})
    assert r.status_code == 422 and _cod(r) == "carpeta_invalida"
    archivo = tmp_path / "archivo.txt"
    archivo.write_text("x", encoding="utf-8")
    r = laptop.put("/api/configuracion", json={"carpeta_exportacion": str(archivo / "sub")})
    assert r.status_code == 422 and _cod(r) == "carpeta_invalida"
    assert bd.leer_configuracion("carpeta_exportacion") is None


def test_campos_desconocidos_de_la_configuracion_se_rechazan(entorno):
    r = entorno[0].put("/api/configuracion", json={"otra_cosa": 1})
    assert r.status_code == 422


def test_la_configuracion_es_solo_de_la_laptop(entorno):
    _, celular, _, _ = entorno
    assert celular.get("/api/configuracion").status_code == 403
    r = celular.put("/api/configuracion", json={"carpeta_exportacion": "C:\\x"})
    assert r.status_code == 403 and _cod(r) == "solo_laptop"


# --- borrar fotos (AP-D1: acción manual) -------------------------------------------------------


def _evaluacion(entorno, lote_sintetico) -> str:
    laptop, _, app, _ = entorno
    plantilla = laptop.get("/api/plantillas").json()[0]["id"]
    foto = lote_sintetico[0].foto
    r = laptop.post(
        "/api/fotos",
        data={"plantilla": plantilla},
        files={"foto": (foto.name, foto.read_bytes(), "image/jpeg")},
    )
    assert r.status_code == 202, r.text
    assert app.state.cola.esperar(60)
    return r.json()["trabajo"]["evaluacion_id"]


def test_borrar_fotos_quita_la_foto_y_conserva_lo_leido(entorno, lote_sintetico):
    laptop, _, _, bd = entorno
    id = _evaluacion(entorno, lote_sintetico)
    antes = laptop.get(f"/api/evaluaciones/{id}").json()
    assert antes["paginas"][0]["foto_ruta"]
    r = laptop.post(f"/api/evaluaciones/{id}/borrar_fotos", json={})
    assert r.status_code == 200 and r.json()["borrados"] == 1
    despues = laptop.get(f"/api/evaluaciones/{id}").json()
    assert despues["paginas"][0]["foto_ruta"] is None
    assert despues["filas"] == antes["filas"]  # lo leído sigue
    assert not any((bd.raiz / "fotos").glob("**/*.jp*g"))
    # idempotente
    assert laptop.post(f"/api/evaluaciones/{id}/borrar_fotos", json={}).json()["borrados"] == 0


def test_borrar_fotos_pasa_incluir_recortes_al_almacen(entorno, lote_sintetico, monkeypatch):
    laptop, _, _, bd = entorno
    id = _evaluacion(entorno, lote_sintetico)
    llamadas = []
    monkeypatch.setattr(
        bd,
        "borrar_fotos",
        lambda i, *, incluir_recortes=False: llamadas.append(incluir_recortes) or 7,
    )
    assert laptop.post(f"/api/evaluaciones/{id}/borrar_fotos").json() == {"borrados": 7}
    assert laptop.post(
        f"/api/evaluaciones/{id}/borrar_fotos", json={"incluir_recortes": True}
    ).json() == {"borrados": 7}
    assert llamadas == [False, True]


def test_borrar_fotos_de_una_evaluacion_inexistente_es_404(entorno):
    r = entorno[0].post("/api/evaluaciones/nada/borrar_fotos", json={})
    assert r.status_code == 404 and _cod(r) == "evaluacion_inexistente"


def test_borrar_fotos_es_solo_de_la_laptop(entorno, lote_sintetico):
    _, celular, _, _ = entorno
    r = celular.post("/api/evaluaciones/abc/borrar_fotos", json={})
    assert r.status_code == 403
