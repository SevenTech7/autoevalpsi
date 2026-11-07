"""AP-R2: página de captura del celular y enlace del QR."""

import io
import json
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.red import Interfaz
from autoevalpsi.app.servidor import crear_app

TOKEN = "token-de-prueba-0123456789"

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


def test_la_pagina_se_sirve_con_el_token_en_el_formulario(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app) as c:
        r = c.get(f"/captura?token={TOKEN}")
    bd.cerrar()
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["cache-control"] == "no-store"
    assert f'action="/api/fotos?token={TOKEN}"' in r.text
    assert f'data-token="{TOKEN}"' in r.text
    assert "{{" not in r.text  # ningún marcador sin reemplazar


def test_la_pagina_ofrece_camara_y_galeria_y_los_formularios_instalados(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app) as c:
        html = c.get(f"/captura?token={TOKEN}").text
        instalada = c.get("/api/plantillas", headers={"X-Token": TOKEN}).json()[0]
    bd.cerrar()
    assert 'capture="environment"' in html  # cámara trasera
    assert len(re.findall(r'type="file"', html)) == 2  # y otro sin `capture` (galería)
    assert f'<option value="{instalada["id"]}">' in html
    assert f"&quot;{instalada['id']}&quot;: {instalada['paginas']}" in html


def test_sin_token_la_pagina_no_se_sirve_ni_filtra_el_token(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app) as c:
        for url in ("/captura", "/captura/", "/captura?token=otro"):
            r = c.get(url)
            assert r.status_code == 401, url
            assert TOKEN not in r.text
    bd.cerrar()


def test_un_token_con_caracteres_html_no_rompe_la_pagina(tmp_path, zip_plantilla):
    raro = 'a"><script>x</script>'
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI], token=raro)
    with TestClient(app) as c:
        r = c.get("/captura", headers={"X-Token": raro})
    bd.cerrar()
    assert r.status_code == 200
    assert "<script>x</script>" not in r.text


def test_sin_formularios_instalados_lo_dice(tmp_path):
    bd, app = _montar(tmp_path, None, [WIFI])
    with TestClient(app) as c:
        html = c.get(f"/captura?token={TOKEN}").text
    bd.cerrar()
    assert "Sin formularios instalados" in html


def test_enlace_elige_la_ip_de_la_ruta_por_defecto(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [HYPERV, WIFI])
    with TestClient(app, headers={"X-Token": TOKEN}) as c:
        d = c.get("/api/captura/enlace").json()
    bd.cerrar()
    assert d["ip"] == "192.168.1.20" and d["puerto"] == 9000
    assert d["url"] == f"http://192.168.1.20:9000/captura?token={TOKEN}"
    assert d["ips"] == ["192.168.1.20", "172.28.96.1"]
    assert d["qr_svg"].startswith("<svg")


def test_enlace_acepta_otra_ip_de_la_lista_y_rechaza_las_ajenas(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [HYPERV, WIFI])
    with TestClient(app, headers={"X-Token": TOKEN}) as c:
        elegida = c.get("/api/captura/enlace?ip=172.28.96.1").json()
        ajena = c.get("/api/captura/enlace?ip=10.9.9.9").json()
    bd.cerrar()
    assert elegida["ip"] == "172.28.96.1" and "172.28.96.1:9000" in elegida["url"]
    assert ajena["ip"] == "192.168.1.20"


def test_enlace_sin_red_explica_que_falta_el_wifi(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [Interfaz("127.0.0.1")])
    with TestClient(app, headers={"X-Token": TOKEN}) as c:
        d = c.get("/api/captura/enlace").json()
    bd.cerrar()
    assert d["url"] is None and d["qr_svg"] is None and d["ips"] == []
    assert "WiFi" in d["mensaje"]


def test_enlace_pide_token(tmp_path, zip_plantilla):
    bd, app = _montar(tmp_path, zip_plantilla, [WIFI])
    with TestClient(app) as c:
        assert c.get("/api/captura/enlace").status_code == 401
    bd.cerrar()
