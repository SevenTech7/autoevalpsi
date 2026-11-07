"""FS-R3: versiones nuevas de una plantilla (editor) y plantilla armada desde una foto."""

import copy
import io
import json
import zipfile

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import ImportacionInvalida, RepositorioPlantillas
from autoevalpsi.app.servidor import crear_app
from autoevalpsi.core.ocr.lector import LectorFalso

TOKEN = "token-de-prueba-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
LAPTOP = ("127.0.0.1", 50000)


def _codigo(r) -> str:
    return r.json()["detail"]["codigo"]


@pytest.fixture(scope="module")
def zip_plantilla(lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plantilla.json", (carpeta / "plantilla.json").read_bytes())
        zf.writestr(datos["paginas"][0]["imagen_referencia"], (carpeta / "blanca.png").read_bytes())
    return buf.getvalue()


@pytest.fixture
def entorno(tmp_path, zip_plantilla):
    bd = BaseDatos(tmp_path / "datos")
    repo = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
    repo.importar_zip(zip_plantilla)
    with TestClient(crear_app(bd, repo, token=TOKEN), headers=AUTH, client=LAPTOP) as c:
        yield c, repo
    bd.cerrar()


def _definicion(cliente) -> tuple[str, dict]:
    id = cliente.get("/api/plantillas").json()[0]["id"]
    return id, cliente.get(f"/api/plantillas/{id}").json()


def test_la_imagen_de_referencia_se_sirve_para_el_editor(entorno):
    cliente, _ = entorno
    id, _ = _definicion(cliente)
    r = cliente.get(f"/api/plantillas/{id}/referencia/0")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert cliente.get(f"/api/plantillas/{id}/referencia/9").status_code == 404


def test_guardar_la_edicion_crea_la_version_siguiente_y_no_toca_la_vieja(entorno):
    cliente, repo = entorno
    id, definicion = _definicion(cliente)
    v1 = definicion["version"]
    editada = copy.deepcopy(definicion)
    editada["nombre"] = "Nombre corregido"
    editada["paginas"][0]["tablas"][0]["filas"][0]["texto"] = "Pregunta corregida"
    r = cliente.post(f"/api/plantillas/{id}/versiones", json={"plantilla": editada})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == v1 + 1
    nueva = cliente.get(f"/api/plantillas/{id}").json()  # la más nueva por defecto
    assert nueva["version"] == v1 + 1 and nueva["nombre"] == "Nombre corregido"
    vieja = cliente.get(f"/api/plantillas/{id}", params={"version": v1}).json()
    assert vieja["nombre"] == definicion["nombre"]  # la versión anterior queda como estaba
    assert repo.ruta_imagen(repo.obtener(id), 0).is_file()  # la imagen en blanco viajó


def test_el_cliente_no_puede_fijar_id_ni_version(entorno):
    cliente, _ = entorno
    id, definicion = _definicion(cliente)
    editada = {**definicion, "id": "otro", "version": 99}
    r = cliente.post(f"/api/plantillas/{id}/versiones", json={"plantilla": editada})
    assert r.status_code == 201
    assert r.json()["id"] == id and r.json()["version"] == definicion["version"] + 1


def test_una_edicion_invalida_se_rechaza_con_un_mensaje_y_no_deja_nada(entorno):
    cliente, repo = entorno
    id, definicion = _definicion(cliente)
    mala = copy.deepcopy(definicion)
    t = mala["paginas"][0]["tablas"][0]
    t["columnas_x"] = [[500, 400], *t["columnas_x"][1:]]  # inicio ≥ fin
    r = cliente.post(f"/api/plantillas/{id}/versiones", json={"plantilla": mala})
    assert r.status_code == 422 and _codigo(r) == "plantilla_invalida"
    assert [i.plantilla.version for i in repo.listar()] == [definicion["version"]]
    assert not list(repo.carpeta.glob(".editando-*"))


def test_no_se_pueden_cambiar_las_imagenes(entorno):
    cliente, _ = entorno
    id, definicion = _definicion(cliente)
    mala = copy.deepcopy(definicion)
    mala["paginas"][0]["imagen_referencia"] = "otra.png"
    r = cliente.post(f"/api/plantillas/{id}/versiones", json={"plantilla": mala})
    assert r.status_code == 422 and "imágenes" in r.json()["detail"]["mensaje"]


def test_editar_una_plantilla_inexistente_es_404(entorno):
    cliente, _ = entorno
    r = cliente.post("/api/plantillas/no-existe/versiones", json={"plantilla": {}})
    assert r.status_code == 404


def test_crear_version_directo_en_el_repositorio_valida(entorno):
    _, repo = entorno
    with pytest.raises(ImportacionInvalida):
        repo.crear_version(repo.listar()[0].plantilla.id, {"nombre": ""})


# --- desde una foto ---------------------------------------------------------------------------


def _foto_png() -> bytes:
    return cv2.imencode(".png", np.full((200, 300, 3), 255, np.uint8))[1].tobytes()


def test_sin_ocr_no_se_puede_armar_desde_una_foto(entorno):
    cliente, _ = entorno
    r = cliente.post(
        "/api/plantillas/desde-foto", files={"foto": ("f.png", _foto_png())}, data={"nombre": "X"}
    )
    assert r.status_code == 409 and _codigo(r) == "ocr_no_disponible"


def test_el_nombre_es_obligatorio(tmp_path):
    with BaseDatos(tmp_path / "d") as bd:
        repo = RepositorioPlantillas(tmp_path / "d" / "p")
        with TestClient(
            crear_app(bd, repo, token=TOKEN, lector=LectorFalso([])), headers=AUTH, client=LAPTOP
        ) as c:
            r = c.post(
                "/api/plantillas/desde-foto",
                files={"foto": ("f.png", _foto_png())},
                data={"nombre": "  "},
            )
    assert r.status_code == 422 and _codigo(r) == "nombre_vacio"
