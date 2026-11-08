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


# --- libro de Excel de la usuaria y páginas nuevas (VD-R3) ---------------------------------------


def _xlsx(celdas: dict[str, object]) -> bytes:
    from io import BytesIO

    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Hoja1"
    for k, v in celdas.items():
        hoja[k] = v
    buf = BytesIO()
    libro.save(buf)
    return buf.getvalue()


def test_poner_el_libro_crea_la_version_siguiente_con_lo_que_se_vaciara(entorno):
    cliente, repo = entorno
    id, definicion = _definicion(cliente)
    editada = copy.deepcopy(definicion)
    filas = editada["paginas"][0]["tablas"][0]["filas"]
    filas[0]["celda"], filas[1]["celda"] = "A1", "A2"
    assert (
        cliente.post(f"/api/plantillas/{id}/versiones", json={"plantilla": editada}).status_code
        == 201
    )
    base = _xlsx(
        {
            "A1": 2,
            "A2": 1,
            "A9": "=SUM(A1:A2)",
            "I63": 9,
            "H63": "receptivo",
            "J63": "=A9",
            "K63": "b",
        }
    )
    r = cliente.post(
        f"/api/plantillas/{id}/libro",
        files={"archivo": ("VINELAND.xlsx", base, "application/octet-stream")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["version"] == definicion["version"] + 2
    assert r.json()["vaciar"] == ["A1:A2", "I63", "K63"]  # el rótulo y las fórmulas no
    nueva = cliente.get(f"/api/plantillas/{id}").json()
    assert nueva["libro"]["vaciar"] == ["A1:A2", "I63", "K63"]
    assert repo.ruta_libro(repo.obtener(id)).is_file()


def test_el_libro_debe_ser_xlsx_y_legible(entorno):
    cliente, _ = entorno
    id, _ = _definicion(cliente)
    r = cliente.post(f"/api/plantillas/{id}/libro", files={"archivo": ("x.txt", b"hola")})
    assert r.status_code == 422 and _codigo(r) == "no_es_xlsx"
    r = cliente.post(f"/api/plantillas/{id}/libro", files={"archivo": ("x.xlsx", b"no es excel")})
    assert r.status_code == 422 and _codigo(r) == "libro_base_invalido"
    assert (
        "x.xlsx" not in r.json()["detail"]["mensaje"]
        or "base.xlsx" in r.json()["detail"]["mensaje"]
    )


def test_exportar_escribe_en_el_libro_de_la_usuaria(tmp_path, zip_plantilla, lote_sintetico):
    from openpyxl import load_workbook

    bd = BaseDatos(tmp_path / "d")
    repo = RepositorioPlantillas(tmp_path / "d" / "plantillas")
    repo.importar_zip(zip_plantilla)
    app = crear_app(bd, repo, token=TOKEN)
    try:
        with TestClient(app, headers=AUTH, client=LAPTOP) as c:
            id, definicion = _definicion(c)
            editada = copy.deepcopy(definicion)
            filas = [f for t in editada["paginas"][0]["tablas"] for f in t["filas"]]
            for k, f in enumerate(filas, start=1):
                f["celda"] = f"A{k}"
            assert (
                c.post(f"/api/plantillas/{id}/versiones", json={"plantilla": editada}).status_code
                == 201
            )
            r = c.post(
                f"/api/plantillas/{id}/libro",
                files={"archivo": ("base.xlsx", _xlsx({"A40": "=SUM(A1:A12)"}))},
            )
            assert r.status_code == 201, r.text
            sub = c.post(
                "/api/fotos",
                data={"plantilla": id},
                files={"foto": ("f.jpg", lote_sintetico[0].foto.read_bytes())},
            )
            assert app.state.cola.esperar(60)
            ev_id = sub.json()["trabajo"]["evaluacion_id"]
            assert (
                c.put(f"/api/evaluaciones/{ev_id}", json={"confirmar_cabecera": True}).status_code
                == 200
            )
            ex = c.post(
                f"/api/evaluaciones/{ev_id}/exportar", json={"carpeta": str(tmp_path / "x")}
            )
            assert ex.status_code == 200, ex.text
            libro = load_workbook(ex.json()["evaluacion"])
            assert "AutoEvalPsi" in libro.sheetnames  # hoja con paciente y fecha
            assert libro["Hoja1"]["A40"].value == "=SUM(A1:A12)"  # la fórmula de la usuaria sigue
            leidos = [libro["Hoja1"][f"A{k}"].value for k in range(1, 13)]
            assert any(v is not None for v in leidos)  # los ítems quedaron en sus celdas
    finally:
        bd.cerrar()


def test_agregar_una_pagina_desde_otra_foto(tmp_path, zip_plantilla, monkeypatch):
    """El constructor (OCR) se sustituye por uno falso: aquí se prueba el cableado y la versión."""
    from autoevalpsi.core.ocr.onnx import LectorONNX

    llamadas = {}

    def falso(foto, lector, **kw):
        llamadas.update(kw)
        pagina = {
            "imagen_referencia": kw["imagen"],
            "tamano_px": [300, 300],
            "tablas": [
                {
                    "tipo": "digito",
                    "opciones": ["0", "1", "2"],
                    "columnas_x": [[100, 150]],
                    "filas": [
                        {"item": kw["primer_item"], "texto": "nueva", "y": [10, 40], "celda": "Z1"}
                    ],
                }
            ],
        }
        return (
            {"paginas": [pagina]},
            np.full((300, 300), 255, np.uint8),
            {"tipo": "celdas", "items": 1, "secciones": 1},
        )

    monkeypatch.setattr("autoevalpsi.app.servidor.plantilla_automatica", falso)
    bd = BaseDatos(tmp_path / "d")
    repo = RepositorioPlantillas(tmp_path / "d" / "plantillas")
    repo.importar_zip(zip_plantilla)
    app = crear_app(bd, repo, token=TOKEN, lector=LectorONNX())
    try:
        with TestClient(app, headers=AUTH, client=LAPTOP) as c:
            id, definicion = _definicion(c)
            items = sum(len(t["filas"]) for t in definicion["paginas"][0]["tablas"])
            r = c.post(f"/api/plantillas/{id}/paginas", files={"foto": ("f.png", _foto_png())})
            assert r.status_code == 201, r.text
            assert r.json()["paginas"] == 2 and r.json()["version"] == definicion["version"] + 1
            assert llamadas["primer_item"] == items + 1  # la numeración sigue donde iba
            assert llamadas["imagen"] == f"{id}-p2.png"
            assert (
                c.get(f"/api/plantillas/{id}/referencia/1").status_code == 200
            )  # su imagen se sirve
            vieja = c.get(f"/api/plantillas/{id}", params={"version": definicion["version"]}).json()
            assert len(vieja["paginas"]) == 1  # la versión anterior no cambió
    finally:
        bd.cerrar()
