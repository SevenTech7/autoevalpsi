"""Actualización a pedido de la usuaria: consulta del Release, descarga verificada y lanzamiento."""

import hashlib
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

from autoevalpsi.app.actualizacion import (
    URL_ULTIMO,
    Actualizador,
    ErrorActualizacion,
    es_mas_nueva,
)
from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.servidor import crear_app

TOKEN = "token-de-prueba-0123456789"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
LAPTOP = ("127.0.0.1", 50000)

INSTALADOR = b"MZ-instalador-falso" * 5000
SUMA = hashlib.sha256(INSTALADOR).hexdigest()
BASE = "https://github.com/SevenTech7/autoevalpsi/releases/download"


def _release(version="0.2.0", *, con_suma=True, host="github.com"):
    nombre = f"AutoEvalPsi-Instalador-{version}.exe"
    assets = [
        {
            "name": nombre,
            "size": len(INSTALADOR),
            "browser_download_url": f"https://{host}/SevenTech7/autoevalpsi/releases/download/v{version}/{nombre}",
        }
    ]
    if con_suma:
        assets.append(
            {
                "name": nombre + ".sha256",
                "browser_download_url": f"{BASE}/v{version}/{nombre}.sha256",
            }
        )
    return {"tag_name": f"v{version}", "body": "Mejoras", "assets": assets}


class Red:
    """Sustituye a la red: responde a cada URL con bytes y anota lo pedido."""

    def __init__(self, release=None, suma=SUMA, instalador=INSTALADOR, falla=False):
        self.release, self.suma, self.instalador, self.falla = release, suma, instalador, falla
        self.pedidas: list[str] = []

    def __call__(self, url):
        self.pedidas.append(url)
        if self.falla:
            raise OSError("sin internet")
        if url == URL_ULTIMO:
            return io.BytesIO(json.dumps(self.release).encode())
        if url.endswith(".sha256"):
            return io.BytesIO(f"{self.suma}  AutoEvalPsi-Instalador.exe\n".encode())
        return io.BytesIO(self.instalador)


def _actualizador(tmp_path, red, actual="0.1.0"):
    lanzados = []
    a = Actualizador(tmp_path / "act", actual=actual, abrir=red, lanzar=lanzados.append)
    return a, lanzados


def _esperar_descarga(a):
    for _ in range(200):
        if a.estado()["estado"] != "descargando":
            return a.estado()
        time.sleep(0.02)
    raise AssertionError("la descarga no terminó")


def test_comparacion_de_versiones():
    assert es_mas_nueva("0.2.0", "0.1.0")
    assert es_mas_nueva("0.10.0", "0.9.0")  # numérica, no de texto
    assert not es_mas_nueva("0.1.0", "0.1.0")
    assert not es_mas_nueva("0.1.0", "0.2.0")
    assert not es_mas_nueva("0.2.0", "0.1.0+local")  # versión de desarrollo: no se toca


def test_sin_version_nueva_no_hay_novedad(tmp_path):
    a, _ = _actualizador(tmp_path, Red(_release("0.1.0")))
    e = a.buscar()
    assert e["buscada"] and e["novedad"] is None and e["actual"] == "0.1.0"


def test_con_version_nueva_se_describe(tmp_path):
    a, _ = _actualizador(tmp_path, Red(_release("0.2.0")))
    n = a.buscar()["novedad"]
    assert n["version"] == "0.2.0" and n["notas"] == "Mejoras" and n["tamano"] == len(INSTALADOR)


def test_sin_internet_explica_y_no_rompe(tmp_path):
    a, _ = _actualizador(tmp_path, Red(falla=True))
    with pytest.raises(ErrorActualizacion, match="conexión a internet"):
        a.buscar()


def test_release_sin_instalador_publicado(tmp_path):
    a, _ = _actualizador(tmp_path, Red(_release("0.2.0", con_suma=False)))
    with pytest.raises(ErrorActualizacion, match="todavía no tiene su instalador"):
        a.buscar()


def test_no_baja_de_un_sitio_que_no_es_de_github(tmp_path):
    a, _ = _actualizador(tmp_path, Red(_release("0.2.0", host="malo.example.com")))
    with pytest.raises(ErrorActualizacion, match="sitio permitido"):
        a.buscar()


def test_descarga_verifica_y_lanza(tmp_path):
    a, lanzados = _actualizador(tmp_path, Red(_release()))
    a.buscar()
    a.descargar()
    e = _esperar_descarga(a)
    assert e["estado"] == "lista" and e["bajado"] == len(INSTALADOR)
    a.instalar()
    assert len(lanzados) == 1
    assert lanzados[0].name == "AutoEvalPsi-Instalador-0.2.0.exe"
    assert lanzados[0].read_bytes() == INSTALADOR


def test_descarga_danada_se_rechaza_y_no_deja_el_archivo(tmp_path):
    a, lanzados = _actualizador(tmp_path, Red(_release(), suma="0" * 64))
    a.buscar()
    a.descargar()
    e = _esperar_descarga(a)
    assert e["estado"] == "error" and "dañada" in e["mensaje"]
    assert not list((tmp_path / "act").glob("*.exe")) and not list(
        (tmp_path / "act").glob("*.parcial")
    )
    with pytest.raises(ErrorActualizacion, match="no está descargada"):
        a.instalar()
    assert lanzados == []


def test_no_se_instala_sin_haber_descargado(tmp_path):
    a, lanzados = _actualizador(tmp_path, Red(_release()))
    a.buscar()
    with pytest.raises(ErrorActualizacion, match="no está descargada"):
        a.instalar()
    assert lanzados == []


def test_no_se_descarga_sin_buscar(tmp_path):
    a, _ = _actualizador(tmp_path, Red(_release()))
    with pytest.raises(ErrorActualizacion, match="Primero busca"):
        a.descargar()


def test_si_windows_no_abre_el_instalador_se_explica(tmp_path):
    def lanzar(_ruta):
        raise OSError("cancelado")

    a = Actualizador(tmp_path / "act", actual="0.1.0", abrir=Red(_release()), lanzar=lanzar)
    a.buscar()
    a.descargar()
    _esperar_descarga(a)
    with pytest.raises(ErrorActualizacion, match="sigue como estaba"):
        a.instalar()


# --- por la API -------------------------------------------------------------------------


@pytest.fixture
def api(tmp_path):
    bd = BaseDatos(tmp_path / "datos")
    red = Red(_release())
    act, lanzados = _actualizador(tmp_path, red)
    app = crear_app(bd, RepositorioPlantillas(tmp_path / "p"), token=TOKEN, actualizador=act)
    with TestClient(app, headers=AUTH, client=LAPTOP) as cliente:
        yield cliente, app, lanzados, red
    bd.cerrar()


def test_api_flujo_completo(api):
    cliente, _app, lanzados, _ = api
    assert cliente.get("/api/actualizacion").json()["buscada"] is False
    assert cliente.post("/api/actualizacion/buscar").json()["novedad"]["version"] == "0.2.0"
    assert cliente.post("/api/actualizacion/descargar").status_code == 200
    for _ in range(200):
        if cliente.get("/api/actualizacion").json()["estado"] == "lista":
            break
        time.sleep(0.02)
    assert cliente.post("/api/actualizacion/instalar").status_code == 200
    assert len(lanzados) == 1


def test_api_sin_internet_es_un_error_legible(api):
    cliente, _app, _l, red = api
    red.falla = True
    r = cliente.post("/api/actualizacion/buscar")
    assert r.status_code == 502 and "internet" in r.json()["detail"]["mensaje"]


def test_api_no_instala_mientras_se_leen_fotos(api, monkeypatch):
    cliente, app, lanzados, _ = api
    cliente.post("/api/actualizacion/buscar")
    cliente.post("/api/actualizacion/descargar")
    for _ in range(200):
        if cliente.get("/api/actualizacion").json()["estado"] == "lista":
            break
        time.sleep(0.02)
    monkeypatch.setattr(app.state.cola, "estado", lambda: {"pendientes": 1})
    r = cliente.post("/api/actualizacion/instalar")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "fotos_en_lectura"
    assert lanzados == []


def test_el_celular_no_puede_actualizar():
    from autoevalpsi.app.servidor import _del_celular

    assert not _del_celular("GET", "/api/actualizacion")
    assert not _del_celular("POST", "/api/actualizacion/instalar")


def _api_con_cierre(tmp_path, lanzar):
    bd = BaseDatos(tmp_path / "datos")
    cerrados = []
    act = Actualizador(tmp_path / "act", actual="0.1.0", abrir=Red(_release()), lanzar=lanzar)
    app = crear_app(
        bd,
        RepositorioPlantillas(tmp_path / "p"),
        token=TOKEN,
        actualizador=act,
        al_instalar=lambda: cerrados.append(1),
    )
    return bd, app, cerrados


def _bajar(cliente):
    cliente.post("/api/actualizacion/buscar")
    cliente.post("/api/actualizacion/descargar")
    for _ in range(200):
        if cliente.get("/api/actualizacion").json()["estado"] == "lista":
            return
        time.sleep(0.02)


def test_tras_lanzar_el_instalador_la_app_se_cierra_sola(tmp_path):
    bd, app, cerrados = _api_con_cierre(tmp_path, lambda ruta: None)
    with TestClient(app, headers=AUTH, client=LAPTOP) as cliente:
        _bajar(cliente)
        assert cliente.post("/api/actualizacion/instalar").status_code == 200
        for _ in range(100):
            if cerrados:
                break
            time.sleep(0.05)
    bd.cerrar()
    assert cerrados == [1]


def test_si_windows_no_abre_el_instalador_la_app_no_se_cierra(tmp_path):
    def lanzar(_ruta):
        raise OSError("cancelado")

    bd, app, cerrados = _api_con_cierre(tmp_path, lanzar)
    with TestClient(app, headers=AUTH, client=LAPTOP) as cliente:
        _bajar(cliente)
        assert cliente.post("/api/actualizacion/instalar").status_code == 502
        time.sleep(2.0)
    bd.cerrar()
    assert cerrados == []
