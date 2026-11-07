"""Modo de prueba en Docker (app/prueba.py): el puerto de la laptop cuenta como laptop."""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from autoevalpsi.app.datos import BaseDatos
from autoevalpsi.app.plantillas import RepositorioPlantillas
from autoevalpsi.app.prueba import instalar_demo
from autoevalpsi.app.servidor import _es_laptop, crear_app

DEMO = Path("plantillas_demo")
TOKEN = "token-de-prueba-0123456789"


def _scope(cliente: str, puerto: int) -> dict:
    return {"client": (cliente, 50000), "server": ("0.0.0.0", puerto)}


def test_es_laptop_por_loopback_o_por_el_puerto_de_la_laptop():
    puertos = frozenset({8765})
    assert _es_laptop(_scope("127.0.0.1", 9999), puertos)
    assert _es_laptop(_scope("172.17.0.1", 8765), puertos)  # Docker reenvía con la IP del puente
    assert not _es_laptop(_scope("172.17.0.1", 8766), puertos)
    assert not _es_laptop(_scope("172.17.0.1", 8765), frozenset())  # producción: sin puertos
    assert not _es_laptop({"client": ("172.17.0.1", 1)}, puertos)


@pytest.fixture
def servidor(tmp_path):
    with BaseDatos(tmp_path) as bd:
        app = crear_app(
            bd, RepositorioPlantillas(tmp_path / "p"), token=TOKEN, puertos_laptop=frozenset({8765})
        )
        yield app


def _cliente(app, puerto: int) -> TestClient:
    # El cliente de pruebas lleva la IP del puente de Docker; el puerto sale de la URL base.
    return TestClient(app, base_url=f"http://testserver:{puerto}", client=("172.17.0.1", 5000))


def test_el_puerto_de_la_laptop_acepta_el_token_y_el_del_celular_no(servidor):
    cabecera = {"Authorization": f"Bearer {TOKEN}"}
    with _cliente(servidor, 8765) as c:
        assert c.get("/api/evaluaciones", headers=cabecera).status_code == 200
    with _cliente(servidor, 8766) as c:
        r = c.get("/api/evaluaciones", headers=cabecera)
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "solo_laptop"


def test_instalar_demo_es_idempotente(tmp_path):
    repo = RepositorioPlantillas(tmp_path / "p")
    nuevas = instalar_demo(repo, DEMO)
    assert "demo-5opciones-a4" in nuevas and "demo-5opciones-carta" in nuevas
    assert instalar_demo(repo, DEMO) == []
