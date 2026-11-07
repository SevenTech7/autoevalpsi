import pytest


@pytest.fixture(autouse=True)
def _sin_descargas_reales(monkeypatch):
    """Ningún test de la app debe escribir en la carpeta Descargas de quien lo corre."""
    monkeypatch.setattr("autoevalpsi.app.servidor.carpeta_descargas", lambda: None)
