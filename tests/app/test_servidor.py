"""AP-R1: servidor FastAPI, cola de procesamiento y plantillas instaladas."""

import io
import json
import threading
import time
import zipfile

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.cola import ColaLlena, ColaProcesamiento, FotoEnProceso
from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import (
    ImportacionInvalida,
    PlantillaNoInstalada,
    PlantillaYaInstalada,
    RepositorioPlantillas,
)
from autoevalpsi.app.servidor import MAX_FOTO, crear_app
from autoevalpsi.core.ocr.lector import Caja, LectorFalso, Linea

TOKEN = "token-de-prueba-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
LAPTOP = ("127.0.0.1", 50000)  # desde aquí llama la ventana de la laptop (AP-D2)


def _zip(archivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nombre, datos in archivos.items():
            zf.writestr(nombre, datos)
    return buf.getvalue()


@pytest.fixture(scope="module")
def zip_plantilla(lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    imagen = datos["paginas"][0]["imagen_referencia"]
    return _zip(
        {
            "plantilla.json": (carpeta / "plantilla.json").read_bytes(),
            imagen: (carpeta / "blanca.png").read_bytes(),
        }
    )


@pytest.fixture
def entorno(tmp_path, zip_plantilla):
    bd = BaseDatos(tmp_path / "datos")
    plantillas = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    app = crear_app(bd, plantillas, token=TOKEN)
    with TestClient(app, headers=AUTH, client=LAPTOP) as cliente:
        yield cliente, app, bd, plantillas
    bd.cerrar()


@pytest.fixture
def cliente(entorno):
    return entorno[0]


def _id_plantilla(cliente) -> str:
    return cliente.get("/api/plantillas").json()[0]["id"]


def _subir(cliente, foto, **datos):
    datos.setdefault("plantilla", _id_plantilla(cliente))
    return cliente.post(
        "/api/fotos", data=datos, files={"foto": (foto.name, foto.read_bytes(), "image/jpeg")}
    )


def _procesar(entorno, foto, **datos):
    cliente, app = entorno[0], entorno[1]
    r = _subir(cliente, foto, **datos)
    assert r.status_code == 202, r.text
    assert app.state.cola.esperar(60)
    return r.json()


def _codigo(r) -> str:
    return r.json()["detail"]["codigo"]


# --- token y límites (AP-03) -----------------------------------------------------------------


def test_salud_no_pide_token_pero_lo_demas_si(entorno):
    _, app, *_ = entorno
    with TestClient(app, client=LAPTOP) as anonimo:
        assert anonimo.get("/api/salud").json()["ok"] is True
        r = anonimo.get("/api/evaluaciones")
        assert r.status_code == 401 and _codigo(r) == "sin_token"


def test_subida_sin_token_o_con_token_malo_es_401_y_no_se_lee_el_cuerpo(entorno, lote_sintetico):
    _, app, bd, _ = entorno
    foto = lote_sintetico[0].foto
    with TestClient(app, client=LAPTOP) as anonimo:
        for cabeceras in ({}, {"Authorization": "Bearer otro"}, {"X-Token": TOKEN + "x"}):
            r = anonimo.post(
                "/api/fotos",
                data={"plantilla": "x"},
                files={"foto": ("f.jpg", foto.read_bytes())},
                headers=cabeceras,
            )
            assert r.status_code == 401
    assert bd.listar_evaluaciones() == []


def test_el_token_vale_por_cabecera_x_token_o_por_query(entorno):
    _, app, *_ = entorno
    with TestClient(app, client=LAPTOP) as anonimo:
        assert anonimo.get("/api/evaluaciones", headers={"X-Token": TOKEN}).status_code == 200
        assert anonimo.get(f"/api/evaluaciones?token={TOKEN}").status_code == 200


def test_el_token_por_defecto_es_aleatorio_y_largo(tmp_path):
    with BaseDatos(tmp_path) as bd:
        a = crear_app(bd, RepositorioPlantillas(tmp_path / "p"))
        b = crear_app(bd, RepositorioPlantillas(tmp_path / "p"))
    assert a.state.token != b.state.token and len(a.state.token) >= 22  # 128 bits en base64


def test_archivo_enorme_es_413_sin_leerlo(entorno):
    cliente, *_ = entorno
    r = cliente.post(
        "/api/fotos",
        data={"plantilla": "x"},
        files={"foto": ("f.jpg", b"\xff\xd8\xff" + b"0" * (MAX_FOTO + 200_000))},
    )
    assert r.status_code == 413 and _codigo(r) == "demasiado_grande"


def test_cuerpo_json_enorme_es_413(entorno):
    cliente, *_ = entorno
    r = cliente.put("/api/evaluaciones/x", content=b"{" + b" " * 2_000_000 + b"}")
    assert r.status_code == 413


def test_subida_sin_tamano_es_411(entorno):
    # TestClient no emite chunked; se simula la petición a mano contra el middleware
    from autoevalpsi.app.servidor import Guardia

    respuestas = []

    async def interior(scope, receive, send):  # pragma: no cover - no debe llamarse
        raise AssertionError

    async def enviar(m):
        respuestas.append(m)

    import asyncio

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/fotos",
        "query_string": b"",
        "headers": [(b"authorization", f"Bearer {TOKEN}".encode())],
        "client": LAPTOP,
    }
    asyncio.run(Guardia(interior, TOKEN, entorno[1].state.vinculos)(scope, None, enviar))
    assert respuestas[0]["status"] == 411


def test_no_imagen_es_415(cliente):
    r = cliente.post(
        "/api/fotos",
        data={"plantilla": _id_plantilla(cliente)},
        files={"foto": ("f.jpg", b"%PDF-1.4 no soy una foto", "image/jpeg")},
    )
    assert r.status_code == 415 and _codigo(r) == "tipo_no_soportado"


def test_jpeg_corrupto_es_422_con_mensaje(cliente):
    r = cliente.post(
        "/api/fotos",
        data={"plantilla": _id_plantilla(cliente)},
        files={"foto": ("f.jpg", b"\xff\xd8\xff\xe0" + b"basura" * 50, "image/jpeg")},
    )
    assert r.status_code == 422 and _codigo(r) == "imagen_invalida"


def test_plantilla_inexistente_es_404(cliente, lote_sintetico):
    r = _subir(cliente, lote_sintetico[0].foto, plantilla="no-existe")
    assert r.status_code == 404 and _codigo(r) == "plantilla_no_instalada"


def test_pagina_fuera_de_rango_es_422(cliente, lote_sintetico):
    r = _subir(cliente, lote_sintetico[0].foto, pagina=3)
    assert r.status_code == 422 and _codigo(r) == "pagina_invalida"


def test_id_de_evaluacion_invalido_es_422(cliente, lote_sintetico):
    r = _subir(cliente, lote_sintetico[0].foto, evaluacion="../x")
    assert r.status_code == 422 and _codigo(r) == "id_invalido"


# --- foto → evaluación -----------------------------------------------------------------------


def test_foto_sintetica_produce_evaluacion_con_filas(entorno, lote_sintetico):
    cliente = entorno[0]
    verdad = json.loads(lote_sintetico[0].verdad.read_text(encoding="utf-8"))
    resp = _procesar(entorno, lote_sintetico[0].foto, paciente="Ana Pérez")
    assert resp["trabajo"]["estado"] in ("en_cola", "procesando", "lista")
    assert resp["repetir"] is False
    trabajo = cliente.get(f"/api/cola/{resp['trabajo']['id']}").json()
    assert trabajo["estado"] == "lista", trabajo
    assert trabajo["requiere_revision"] is False

    lista = cliente.get("/api/evaluaciones").json()
    assert len(lista) == 1 and lista[0]["id"] == trabajo["evaluacion_id"]
    ev = cliente.get(f"/api/evaluaciones/{lista[0]['id']}").json()
    assert ev["paciente"] == "Ana Pérez" and ev["estado"] == "revisada"  # todo verde y sin OCR
    assert len(ev["filas"]) == len(verdad["items"])
    for f in ev["filas"]:
        assert f["opcion_leida"] == verdad["items"][str(f["item"])]["marcas"][0]


def test_cola_informa_el_estado(entorno, lote_sintetico):
    cliente = entorno[0]
    _procesar(entorno, lote_sintetico[0].foto)
    estado = cliente.get("/api/cola").json()
    assert estado["lista"] == 1 and estado["pendientes"] == 0 and len(estado["trabajos"]) == 1
    assert cliente.get("/api/cola/t999").status_code == 404


def test_la_misma_foto_dos_veces_es_409(entorno, lote_sintetico):
    cliente = entorno[0]
    _procesar(entorno, lote_sintetico[0].foto)
    r = _subir(cliente, lote_sintetico[0].foto)
    assert r.status_code == 409 and _codigo(r) == "foto_repetida"


def test_hoja_en_blanco_deja_el_trabajo_en_error_y_el_trabajador_sigue(entorno, lote_sintetico):
    cliente = entorno[0]
    ruta = lote_sintetico[0].foto.parent / "negra.jpg"
    _ok, buf = cv2.imencode(".jpg", np.zeros((1200, 900, 3), np.uint8))
    ruta.write_bytes(buf.tobytes())
    r = _subir(cliente, ruta)
    assert r.status_code == 202
    entorno[1].state.cola.esperar(60)
    t = cliente.get(f"/api/cola/{r.json()['trabajo']['id']}").json()
    assert t["estado"] == "error" and t["mensaje"]
    assert cliente.get("/api/evaluaciones").json() == []
    # el trabajador sigue vivo
    _procesar(entorno, lote_sintetico[0].foto)
    assert len(cliente.get("/api/evaluaciones").json()) == 1


def test_mala_calidad_se_avisa_en_la_misma_respuesta(entorno, lote_sintetico):
    cliente = entorno[0]
    img = cv2.imdecode(np.frombuffer(lote_sintetico[0].foto.read_bytes(), np.uint8), 1)
    borrosa = cv2.GaussianBlur(img, (0, 0), 25)
    ruta = lote_sintetico[0].foto.parent / "borrosa.jpg"
    ruta.write_bytes(cv2.imencode(".jpg", borrosa)[1].tobytes())
    r = _subir(cliente, ruta)
    assert r.status_code == 202
    assert r.json()["repetir"] is True and r.json()["problemas_calidad"]
    entorno[1].state.cola.esperar(60)


def test_dos_paginas_se_agrupan_en_una_evaluacion(entorno, lote_sintetico):
    """PL-03: la misma `evaluacion` agrupa las fotos; la plantilla demo tiene 1 página."""
    cliente = entorno[0]
    _procesar(entorno, lote_sintetico[0].foto, evaluacion="sesion-1")
    r = _subir(cliente, lote_sintetico[1].foto, evaluacion="sesion-1")
    assert r.status_code == 409 and _codigo(r) == "pagina_repetida"
    r = _subir(cliente, lote_sintetico[1].foto, evaluacion="sesion-1", pagina=1)
    assert r.status_code == 422 and _codigo(r) == "pagina_invalida"
    assert [e["id"] for e in cliente.get("/api/evaluaciones").json()] == ["sesion-1"]


def test_ocr_con_lector_falso_llena_la_cabecera_y_observaciones(
    tmp_path, zip_plantilla, lote_sintetico
):
    bd = BaseDatos(tmp_path / "d")
    plantillas = RepositorioPlantillas(tmp_path / "d" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    lector = LectorFalso([Linea("Maria Lopez", 0.97, Caja(0, 0, 100, 20))])
    app = crear_app(bd, plantillas, token=TOKEN, lector=lector)
    try:
        with TestClient(app, headers=AUTH, client=LAPTOP) as c:
            r = c.post(
                "/api/fotos",
                data={"plantilla": plantillas.listar()[0].plantilla.id},
                files={"foto": ("f.jpg", lote_sintetico[0].foto.read_bytes())},
            )
            assert r.status_code == 202
            app.state.cola.esperar(60)
            ev = c.get("/api/evaluaciones").json()[0]
            assert c.get(f"/api/evaluaciones/{ev['id']}").json()["paginas"][0]["ocr_activo"] is True
    finally:
        bd.cerrar()
    assert lector.llamadas  # el lector se usó en el trabajador


# --- revisión y exportación (AP-06) -----------------------------------------------------------


def _con_filas_amarillas(entorno, lote_sintetico) -> str:
    """La foto 1 recorre los casos de borde: tiene filas con bandera."""
    resp = _procesar(entorno, lote_sintetico[1].foto)
    return resp["trabajo"]["evaluacion_id"]


def test_exportar_con_filas_sin_revisar_es_409(entorno, lote_sintetico, tmp_path):
    cliente = entorno[0]
    id = _con_filas_amarillas(entorno, lote_sintetico)
    ev = cliente.get(f"/api/evaluaciones/{id}").json()
    assert ev["filas_pendientes"] > 0
    r = cliente.post(f"/api/evaluaciones/{id}/exportar", json={"carpeta": str(tmp_path / "x")})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["codigo"] == "revision_pendiente" and d["filas_pendientes"] == ev["filas_pendientes"]
    assert not (tmp_path / "x").exists() or not list((tmp_path / "x").iterdir())
    assert cliente.get(f"/api/evaluaciones/{id}").json()["estado"] != "exportada"


def test_exportar_con_la_cabecera_sin_confirmar_es_409(tmp_path, zip_plantilla, lote_sintetico):
    """Con OCR dudoso (confianza baja) la cabecera nace sin confirmar aunque las filas sean verdes."""
    bd = BaseDatos(tmp_path / "d")
    plantillas = RepositorioPlantillas(tmp_path / "d" / "plantillas")
    plantillas.importar_zip(zip_plantilla)
    lector = LectorFalso([Linea("Mria", 0.2, Caja(0, 0, 100, 20))])
    app = crear_app(bd, plantillas, token=TOKEN, lector=lector)
    try:
        with TestClient(app, headers=AUTH, client=LAPTOP) as c:
            r = c.post(
                "/api/fotos",
                data={"plantilla": plantillas.listar()[0].plantilla.id},
                files={"foto": ("f.jpg", lote_sintetico[0].foto.read_bytes())},
            )
            app.state.cola.esperar(60)
            id = r.json()["trabajo"]["evaluacion_id"]
            ev = c.get(f"/api/evaluaciones/{id}").json()
            assert ev["cabecera_revisada"] is False
            r = c.post(f"/api/evaluaciones/{id}/exportar", json={"carpeta": str(tmp_path / "x")})
            assert r.status_code == 409 and "cabecera" in r.json()["detail"]["mensaje"]
            assert r.json()["detail"]["cabecera_revisada"] is False
            assert (
                c.put(f"/api/evaluaciones/{id}", json={"confirmar_cabecera": True}).status_code
                == 200
            )
    finally:
        bd.cerrar()


def test_revisar_y_exportar_deja_el_excel_y_marca_exportada(entorno, lote_sintetico, tmp_path):
    cliente = entorno[0]
    id = _con_filas_amarillas(entorno, lote_sintetico)
    ev = cliente.get(f"/api/evaluaciones/{id}").json()
    pendientes = [f["item"] for f in ev["filas"] if not f["revisada"]]
    r = cliente.put(
        f"/api/evaluaciones/{id}",
        json={
            "paciente": "Luis Díaz",
            "filas": [{"item": i} for i in pendientes],
        },
    )
    assert r.status_code == 200
    assert r.json()["filas_pendientes"] == 0 and r.json()["estado"] == "revisada"

    carpeta = tmp_path / "excel"
    r = cliente.post(f"/api/evaluaciones/{id}/exportar", json={"carpeta": str(carpeta)})
    assert r.status_code == 200, r.text
    assert (carpeta / r.json()["evaluacion"].split("\\")[-1].split("/")[-1]).is_file()
    assert "Luis" in r.json()["evaluacion"]
    assert r.json()["carpeta"] == str(carpeta)
    assert cliente.get(f"/api/evaluaciones/{id}").json()["estado"] == "exportada"


def test_exportar_sin_cuerpo_usa_la_carpeta_de_la_raiz(entorno, lote_sintetico):
    cliente, _, bd, _ = entorno
    id = _procesar(entorno, lote_sintetico[0].foto)["trabajo"]["evaluacion_id"]
    assert (
        cliente.put(f"/api/evaluaciones/{id}", json={"confirmar_cabecera": True}).status_code == 200
    )
    r = cliente.post(f"/api/evaluaciones/{id}/exportar")
    assert r.status_code == 200, r.text
    assert (bd.raiz / "exportaciones").is_dir() and any((bd.raiz / "exportaciones").iterdir())


def test_sin_carpeta_elegida_se_exporta_a_descargas(entorno, lote_sintetico, tmp_path, monkeypatch):
    cliente, _, bd, _ = entorno
    descargas = tmp_path / "Descargas"
    descargas.mkdir()
    monkeypatch.setattr("autoevalpsi.app.servidor.carpeta_descargas", lambda: descargas)
    assert cliente.get("/api/configuracion").json()["carpeta_exportacion_efectiva"] == str(
        descargas
    )
    id = _procesar(entorno, lote_sintetico[0].foto)["trabajo"]["evaluacion_id"]
    cliente.put(f"/api/evaluaciones/{id}", json={"confirmar_cabecera": True})
    r = cliente.post(f"/api/evaluaciones/{id}/exportar")
    assert r.status_code == 200, r.text
    assert r.json()["carpeta"] == str(descargas)
    assert any(f.suffix == ".xlsx" for f in descargas.iterdir())
    assert not (bd.raiz / "exportaciones").exists()


def test_la_carpeta_elegida_gana_a_descargas(entorno, tmp_path, monkeypatch):
    cliente, _, _, _ = entorno
    descargas, elegida = tmp_path / "Descargas", tmp_path / "Mis Excel"
    descargas.mkdir()
    monkeypatch.setattr("autoevalpsi.app.servidor.carpeta_descargas", lambda: descargas)
    cliente.put("/api/configuracion", json={"carpeta_exportacion": str(elegida)})
    assert cliente.get("/api/configuracion").json()["carpeta_exportacion_efectiva"] == str(elegida)


def test_correcciones_dejan_registro_y_validan_la_opcion(entorno, lote_sintetico):
    cliente, _, bd, _ = entorno
    id = _con_filas_amarillas(entorno, lote_sintetico)
    ev = cliente.get(f"/api/evaluaciones/{id}").json()
    fila = ev["filas"][0]
    plantilla = cliente.get(f"/api/plantillas/{ev['plantilla_id']}").json()
    opciones = plantilla["paginas"][0]["tablas"][0]["opciones"]
    nueva = next(o for o in opciones if o != fila["opcion"])

    malo = cliente.put(
        f"/api/evaluaciones/{id}", json={"filas": [{"item": fila["item"], "opcion": "ZZ"}]}
    )
    assert malo.status_code == 422 and _codigo(malo) == "opcion_invalida"
    assert bd.listar_correcciones(id) == []

    inexistente = cliente.put(f"/api/evaluaciones/{id}", json={"filas": [{"item": 9999}]})
    assert inexistente.status_code == 422 and _codigo(inexistente) == "item_inexistente"

    ok = cliente.put(
        f"/api/evaluaciones/{id}",
        json={"filas": [{"item": fila["item"], "opcion": nueva, "observacion": "nota"}]},
    )
    assert ok.status_code == 200
    campos = {c.campo: (c.antes, c.despues) for c in bd.listar_correcciones(id)}
    assert campos["opcion"][1] == nueva and campos["observacion"][1] == "nota"
    nuevo = next(f for f in ok.json()["filas"] if f["item"] == fila["item"])
    assert nuevo["opcion"] == nueva and nuevo["opcion_leida"] == fila["opcion_leida"]


def test_opcion_null_explicita_es_sin_respuesta_y_ausente_no_toca(entorno, lote_sintetico):
    cliente = entorno[0]
    id = _procesar(entorno, lote_sintetico[0].foto)["trabajo"]["evaluacion_id"]
    item = cliente.get(f"/api/evaluaciones/{id}").json()["filas"][0]
    assert item["opcion"] is not None
    r = cliente.put(f"/api/evaluaciones/{id}", json={"filas": [{"item": item["item"]}]})
    assert r.json()["filas"][0]["opcion"] == item["opcion"]
    r = cliente.put(
        f"/api/evaluaciones/{id}", json={"filas": [{"item": item["item"], "opcion": None}]}
    )
    assert r.json()["filas"][0]["opcion"] is None


def test_evaluacion_inexistente_es_404(cliente):
    assert cliente.get("/api/evaluaciones/nada").status_code == 404
    assert cliente.put("/api/evaluaciones/nada", json={}).status_code == 404
    assert cliente.post("/api/evaluaciones/nada/exportar").status_code == 404


def test_campos_desconocidos_en_el_put_se_rechazan(entorno, lote_sintetico):
    cliente = entorno[0]
    id = _procesar(entorno, lote_sintetico[0].foto)["trabajo"]["evaluacion_id"]
    assert cliente.put(f"/api/evaluaciones/{id}", json={"estado": "exportada"}).status_code == 422


# --- plantillas -------------------------------------------------------------------------------


def test_importar_plantilla_por_http_y_listarla(tmp_path, zip_plantilla):
    with BaseDatos(tmp_path / "d") as bd:
        repo = RepositorioPlantillas(tmp_path / "d" / "plantillas")
        with TestClient(crear_app(bd, repo, token=TOKEN), headers=AUTH, client=LAPTOP) as c:
            assert c.get("/api/plantillas").json() == []
            r = c.post("/api/plantillas/importar", files={"archivo": ("p.zip", zip_plantilla)})
            assert r.status_code == 201, r.text
            lista = c.get("/api/plantillas").json()
            assert lista == [r.json()] and lista[0]["items"] > 0
            otra = c.post("/api/plantillas/importar", files={"archivo": ("p.zip", zip_plantilla)})
            assert otra.status_code == 409 and _codigo(otra) == "plantilla_ya_instalada"
            malo = c.post("/api/plantillas/importar", files={"archivo": ("p.zip", b"no soy zip")})
            assert malo.status_code == 422 and _codigo(malo) == "zip_invalido"
            assert c.get("/api/plantillas/no-existe").status_code == 404


# --- repositorio de plantillas ----------------------------------------------------------------


@pytest.fixture
def repo(tmp_path):
    return RepositorioPlantillas(tmp_path / "plantillas")


def test_importar_instala_por_version_y_obtener_da_la_mas_nueva(
    repo, lote_sintetico, zip_plantilla
):
    inst = repo.importar_zip(zip_plantilla)
    assert inst.ruta.is_file() and inst.ruta.parent.name == f"v{inst.plantilla.version}"
    assert repo.obtener(inst.plantilla.id).plantilla.version == inst.plantilla.version
    # versión nueva: otra carpeta, las dos conviven
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    datos["version"] = inst.plantilla.version + 1
    imagen = datos["paginas"][0]["imagen_referencia"]
    z2 = _zip(
        {
            "plantilla.json": json.dumps(datos).encode(),
            imagen: (carpeta / "blanca.png").read_bytes(),
        }
    )
    repo.importar_zip(z2)
    assert [i.plantilla.version for i in repo.listar()] == [
        inst.plantilla.version,
        datos["version"],
    ]
    assert repo.obtener(inst.plantilla.id).plantilla.version == datos["version"]
    assert (
        repo.obtener(inst.plantilla.id, inst.plantilla.version).plantilla.version
        == inst.plantilla.version
    )
    with pytest.raises(PlantillaNoInstalada):
        repo.obtener(inst.plantilla.id, 99)


def test_mismo_id_y_version_no_se_pisa(repo, zip_plantilla):
    repo.importar_zip(zip_plantilla)
    with pytest.raises(PlantillaYaInstalada):
        repo.importar_zip(zip_plantilla)
    assert len(repo.listar()) == 1


def test_zip_dentro_de_una_carpeta_tambien_sirve(repo, lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    imagen = datos["paginas"][0]["imagen_referencia"]
    z = _zip({"mi-form/p.json": (carpeta / "plantilla.json").read_bytes(),
              f"mi-form/{imagen}": (carpeta / "blanca.png").read_bytes()})  # fmt: skip
    inst = repo.importar_zip(z)
    assert repo.referencia(inst, 0).ndim == 2


@pytest.mark.parametrize(
    ("archivos", "mensaje"),
    [
        ({"../fuera.json": b"{}"}, "ruta no permitida"),
        ({"/abs/p.json": b"{}"}, "ruta no permitida"),
        ({"C:/p.json": b"{}"}, "ruta no permitida"),
        ({"a.txt": b"x"}, "un solo archivo .json"),
        ({"a.json": b"{}", "b.json": b"{}"}, "un solo archivo .json"),
        ({"a.json": b"no es json"}, "JSON mal formado"),
        ({"a.json": b"{}"}, "Plantilla inválida"),
    ],
)
def test_zips_malos_se_rechazan_sin_dejar_nada(repo, archivos, mensaje):
    with pytest.raises(ImportacionInvalida, match=mensaje):
        repo.importar_zip(_zip(archivos))
    assert list(repo.carpeta.iterdir()) == []
    assert not (repo.carpeta.parent / "fuera.json").exists()


def test_falta_la_imagen_en_blanco(repo, lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    with pytest.raises(ImportacionInvalida, match="imagen en blanco"):
        repo.importar_zip(_zip({"p.json": (carpeta / "plantilla.json").read_bytes()}))
    assert list(repo.carpeta.iterdir()) == []


def test_la_imagen_no_puede_apuntar_fuera_de_la_plantilla(repo, lote_sintetico):
    carpeta = lote_sintetico[0].plantilla.parent
    datos = json.loads((carpeta / "plantilla.json").read_text(encoding="utf-8"))
    datos["paginas"][0]["imagen_referencia"] = "sub/../../x.png"
    with pytest.raises(ImportacionInvalida, match="fuera de la plantilla"):
        repo.importar_zip(_zip({"p.json": json.dumps(datos).encode()}))


def test_zip_que_no_es_zip(repo):
    with pytest.raises(ImportacionInvalida, match="no es un .zip"):
        repo.importar_zip(b"hola")


def test_id_de_plantilla_con_ruta_no_se_resuelve(repo):
    with pytest.raises(PlantillaNoInstalada):
        repo.obtener("../x")


# --- cola -------------------------------------------------------------------------------------


def test_la_cola_procesa_de_a_una_y_en_orden():
    en_curso, maximo, orden = 0, 0, []
    candado = threading.Lock()

    def ejecutar(trabajo, datos):
        nonlocal en_curso, maximo
        with candado:
            en_curso += 1
            maximo = max(maximo, en_curso)
        time.sleep(0.02)
        orden.append(datos)
        with candado:
            en_curso -= 1
        return False

    cola = ColaProcesamiento(ejecutar)
    for i in range(6):
        cola.encolar(i, sha256=f"s{i}", evaluacion_id=f"e{i}", pagina=0, plantilla_id="p")
    assert cola.esperar(10)
    cola.detener()
    assert orden == list(range(6)) and maximo == 1
    assert cola.estado()["lista"] == 6


def test_error_de_foto_y_error_inesperado_no_matan_al_trabajador(caplog):
    def ejecutar(trabajo, datos):
        if datos == "foto":
            raise ValueError("No se ve la hoja entera.")
        if datos == "bug":
            raise RuntimeError("secreto interno")
        return True

    cola = ColaProcesamiento(ejecutar)
    for n, d in enumerate(["foto", "bug", "bien"]):
        cola.encolar(d, sha256=f"s{n}", evaluacion_id="e", pagina=0, plantilla_id="p")
    assert cola.esperar(10)
    cola.detener()
    foto, bug, bien = (cola.trabajo(f"t{i}") for i in (1, 2, 3))
    assert (foto.estado, foto.mensaje) == ("error", "No se ve la hoja entera.")
    assert bug.estado == "error" and "secreto" not in bug.mensaje and "inesperado" in bug.mensaje
    assert "secreto interno" in caplog.text  # al log, no a la usuaria
    assert bien.estado == "lista" and bien.requiere_revision is True


def test_cola_llena_y_foto_en_proceso():
    puerta = threading.Event()
    cola = ColaProcesamiento(lambda t, d: puerta.wait(10) and False, maximo=2)
    cola.encolar(0, sha256="a", evaluacion_id="e", pagina=0, plantilla_id="p")
    time.sleep(0.1)  # el trabajador toma la primera; quedan 2 sitios
    cola.encolar(1, sha256="b", evaluacion_id="e", pagina=0, plantilla_id="p")
    cola.encolar(2, sha256="c", evaluacion_id="e", pagina=0, plantilla_id="p")
    with pytest.raises(ColaLlena):
        cola.encolar(3, sha256="d", evaluacion_id="e", pagina=0, plantilla_id="p")
    with pytest.raises(FotoEnProceso):
        cola.encolar(4, sha256="b", evaluacion_id="e", pagina=0, plantilla_id="p")
    puerta.set()
    assert cola.esperar(10)
    cola.detener()
    # terminada la foto, se puede volver a mandar (si el servidor la rechaza es por la base)
    cola.encolar(5, sha256="b", evaluacion_id="e", pagina=0, plantilla_id="p")
    cola.esperar(10)
    cola.detener()
