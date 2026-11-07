"""AP-R2/AP-D2: página de captura del celular y QR de vínculo."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.red import Interfaz
from autoevalpsi.app.servidor import crear_app

TOKEN = "token-de-prueba-0123456789"

LAPTOP = ("127.0.0.1", 50000)
WIFI = Interfaz("192.168.1.20", "Wi-Fi", ruta_por_defecto=True)
HYPERV = Interfaz("172.28.96.1", "vEthernet (WSL)")


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


def _montar(tmp_path, zip_plantilla, interfaces, token=TOKEN):
    bd = BaseDatos(tmp_path / "datos")
    plantillas = RepositorioPlantillas(tmp_path / "datos" / "plantillas")
    if zip_plantilla is not None:
        plantillas.importar_zip(zip_plantilla)
    app = crear_app(bd, plantillas, token=token, puerto=9000, interfaces=lambda: interfaces)
    return bd, app


def test_la_pagina_es_estatica_y_no_lleva_ningun_secreto(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app, client=("192.168.1.50", 40000)) as c:
        r = c.get("/captura")
        otra = c.get(f"/captura?token={TOKEN}")
    bd.cerrar()
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    assert TOKEN not in r.text and TOKEN not in otra.text
    assert "{{" not in r.text  # ningún marcador sin reemplazar


def test_la_pagina_ofrece_camara_galeria_y_el_aviso_de_vincular(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app, client=("192.168.1.50", 40000)) as c:
        html = c.get("/captura").text
    bd.cerrar()
    assert 'capture="environment"' in html  # cámara trasera
    assert html.count('type="file"') == 2  # y otro sin `capture` (galería)
    assert "Vincula este celular desde la laptop" in html
    assert "X-Dispositivo" in html and "?token=" not in html


def test_el_codigo_de_vinculo_entra_en_la_url_del_qr_y_no_el_token(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [HYPERV, WIFI])
    with TestClient(app, headers={"X-Token": TOKEN}, client=LAPTOP) as c:
        d = c.post("/api/vinculo/iniciar").json()
    bd.cerrar()
    assert d["ip"] == "192.168.1.20" and d["puerto"] == 9000
    assert d["url"].startswith("http://192.168.1.20:9000/captura?vinculo=")
    assert TOKEN not in d["url"] and TOKEN not in d["qr_svg"]
    assert d["ips"] == ["192.168.1.20", "172.28.96.1"]
    assert d["qr_svg"].startswith("<svg") and d["vence_en"] == 300 and d["vinculado"] is False


def test_el_enlace_acepta_otra_ip_de_la_lista_y_rechaza_las_ajenas(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [HYPERV, WIFI])
    with TestClient(app, headers={"X-Token": TOKEN}, client=LAPTOP) as c:
        elegida = c.post("/api/vinculo/iniciar?ip=172.28.96.1").json()
        ajena = c.post("/api/vinculo/iniciar?ip=10.9.9.9").json()
    bd.cerrar()
    assert elegida["ip"] == "172.28.96.1" and "172.28.96.1:9000" in elegida["url"]
    assert ajena["ip"] == "192.168.1.20"


def test_sin_red_explica_que_falta_el_wifi_y_no_emite_codigo(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [Interfaz("127.0.0.1")])
    with TestClient(app, headers={"X-Token": TOKEN}, client=LAPTOP) as c:
        d = c.post("/api/vinculo/iniciar").json()
    bd.cerrar()
    assert d["url"] is None and d["qr_svg"] is None and d["ips"] == []
    assert "WiFi" in d["mensaje"]
