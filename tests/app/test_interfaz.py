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
PNG = b"\x89PNG"


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


def test_los_scripts_salen_como_javascript_aunque_windows_diga_otra_cosa(
    tmp_path, zip_plantilla, estaticos, monkeypatch
):
    """En algunas laptops el registro de Windows declara `.js` como `text/plain`: pantalla en blanco."""
    import mimetypes

    mimetypes.add_type("text/plain", ".js")
    bd = BaseDatos(tmp_path / "datos")
    try:
        plantillas = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
        app = crear_app(bd, plantillas, token=TOKEN, estaticos=estaticos)
        with TestClient(app, client=LAPTOP) as c:
            r = c.get("/assets/app.js")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/javascript")
    finally:
        bd.cerrar()


def test_el_registro_deja_como_se_sirvio_la_interfaz(entorno, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="autoevalpsi.app.servidor"):
        c = TestClient(entorno[2], client=LAPTOP)
        c.get("/")
        c.get("/assets/app.js")
        c.get("/api/salud")
    propios = " | ".join(
        r.getMessage() for r in caplog.records if r.name == "autoevalpsi.app.servidor"
    )
    assert "interfaz / -> 200 text/html" in propios
    assert "interfaz /assets/app.js -> 200 text/javascript" in propios
    assert "salud" not in propios  # solo la interfaz, nunca lo que lleva datos


def test_la_raiz_sirve_el_index_a_la_laptop_sin_token_y_sin_cache(entorno):
    r = TestClient(entorno[2], client=LAPTOP).get("/")
    assert r.status_code == 200 and "<title>UI</title>" in r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_el_celular_que_entra_a_la_raiz_va_a_la_pagina_de_captura(entorno):
    _, celular, _, _ = entorno
    r = celular.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/captura"
    assert celular.get("/").status_code == 200  # y llega a la página del celular


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


# --- revisión (AP-R5): recortes y descartar foto -------------------------------------------------


def test_revision_de_punta_a_punta_con_los_recortes_de_una_foto_real(
    tmp_path, zip_plantilla, estaticos, lote_sintetico
):
    """Sube una foto con OCR, mira los recortes, confirma todo y exporta (AP-R5, e2e mínimo)."""
    from autoevalpsi.core.ocr.lector import Caja, LectorFalso, Linea

    bd = BaseDatos(tmp_path / "ocr")
    plantillas = RepositorioPlantillas(tmp_path / "ocr" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    lector = LectorFalso([Linea("Maria Lopez", 0.97, Caja(0, 0, 100, 20))])
    app = crear_app(bd, plantillas, token=TOKEN, estaticos=estaticos, lector=lector)
    try:
        with (
            TestClient(app, headers=AUTH, client=LAPTOP) as laptop,
            TestClient(app, client=CELULAR) as celular,
            TestClient(app, client=LAPTOP) as sin_cabecera,
        ):
            plantilla = laptop.get("/api/plantillas").json()[0]["id"]
            foto = lote_sintetico[0].foto
            r = laptop.post(
                "/api/fotos",
                data={"plantilla": plantilla},
                files={"foto": (foto.name, foto.read_bytes(), "image/jpeg")},
            )
            assert r.status_code == 202, r.text
            assert app.state.cola.esperar(60)
            id = r.json()["trabajo"]["evaluacion_id"]

            ev = laptop.get(f"/api/evaluaciones/{id}").json()
            con_recorte = [f for f in ev["filas"] if f["ruta_recorte"]]
            assert con_recorte and ev["recortes_cabecera"]
            url = f"/api/evaluaciones/{id}/recortes/{con_recorte[0]['item']}"
            r = laptop.get(url)
            assert r.status_code == 200 and r.content.startswith(PNG)
            assert "no-store" in r.headers["cache-control"]
            campo = next(iter(ev["recortes_cabecera"]))
            r = laptop.get(f"/api/evaluaciones/{id}/cabecera/{campo}")
            assert r.status_code == 200 and r.content.startswith(PNG)

            # un <img> no puede mandar cabeceras: el token va en la URL; sin él, nada
            assert sin_cabecera.get(url).status_code == 401
            assert sin_cabecera.get(f"{url}?token={TOKEN}").status_code == 200
            assert celular.get(url).status_code == 403

            pendientes = [f["item"] for f in ev["filas"] if not f["revisada"]]
            r = laptop.put(
                f"/api/evaluaciones/{id}",
                json={"filas": [{"item": i} for i in pendientes], "confirmar_cabecera": True},
            )
            assert r.status_code == 200 and r.json()["filas_pendientes"] == 0
            r = laptop.post(
                f"/api/evaluaciones/{id}/exportar", json={"carpeta": str(tmp_path / "excel")}
            )
            assert r.status_code == 200, r.text
    finally:
        bd.cerrar()


def test_un_recorte_que_no_existe_es_404_con_mensaje(entorno, lote_sintetico):
    laptop = entorno[0]
    id = _evaluacion(entorno, lote_sintetico)
    r = laptop.get(f"/api/evaluaciones/{id}/recortes/9999")
    assert r.status_code == 404 and _cod(r) == "recorte_inexistente"
    r = laptop.get(f"/api/evaluaciones/{id}/cabecera/nada")
    assert r.status_code == 404 and _cod(r) == "recorte_inexistente"
    r = laptop.get("/api/evaluaciones/nada/recortes/1")
    assert r.status_code == 404 and _cod(r) == "evaluacion_inexistente"


def test_descartar_la_unica_foto_elimina_la_evaluacion_y_deja_repetirla(entorno, lote_sintetico):
    laptop, _, app, bd = entorno
    id = _evaluacion(entorno, lote_sintetico)
    plantilla = laptop.get("/api/plantillas").json()[0]["id"]
    r = laptop.delete(f"/api/evaluaciones/{id}/paginas/0")
    assert r.status_code == 200 and r.json() == {"evaluacion_eliminada": True}
    assert laptop.get(f"/api/evaluaciones/{id}").status_code == 404
    assert not any((bd.raiz / "fotos").glob("**/*.jp*g"))
    # la misma foto se puede subir de nuevo
    foto = lote_sintetico[0].foto
    r = laptop.post(
        "/api/fotos",
        data={"plantilla": plantilla},
        files={"foto": (foto.name, foto.read_bytes(), "image/jpeg")},
    )
    assert r.status_code == 202, r.text
    assert app.state.cola.esperar(60)


def test_descartar_una_pagina_inexistente_o_de_una_evaluacion_inexistente_es_404(
    entorno, lote_sintetico
):
    laptop = entorno[0]
    id = _evaluacion(entorno, lote_sintetico)
    r = laptop.delete(f"/api/evaluaciones/{id}/paginas/7")
    assert r.status_code == 404 and _cod(r) == "pagina_inexistente"
    r = laptop.delete("/api/evaluaciones/nada/paginas/0")
    assert r.status_code == 404 and _cod(r) == "evaluacion_inexistente"
    assert laptop.get(f"/api/evaluaciones/{id}").status_code == 200


def test_no_se_descarta_una_foto_que_todavia_se_lee(entorno, lote_sintetico):
    laptop, _, app, _ = entorno
    id = _evaluacion(entorno, lote_sintetico)
    trabajo = app.state.cola.estado()["trabajos"][0]
    # simula un trabajo en vuelo de esa misma página
    from autoevalpsi.app.cola import Trabajo

    pendiente = Trabajo("t99", "x", id, trabajo["pagina"], "p", (), "ahora", estado="procesando")
    app.state.cola._trabajos["t99"] = pendiente
    r = laptop.delete(f"/api/evaluaciones/{id}/paginas/{trabajo['pagina']}")
    assert r.status_code == 409 and _cod(r) == "foto_en_lectura"
    pendiente.estado = "lista"
    assert laptop.delete(f"/api/evaluaciones/{id}/paginas/{trabajo['pagina']}").status_code == 200


def test_descartar_es_solo_de_la_laptop(entorno):
    _, celular, _, _ = entorno
    r = celular.delete("/api/evaluaciones/abc/paginas/0")
    assert r.status_code == 403 and _cod(r) == "solo_laptop"
