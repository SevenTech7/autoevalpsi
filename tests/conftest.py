"""Fixtures compartidos (BS-R1)."""

import pytest
from tools.sintetico.lote import generar_lote


@pytest.fixture(scope="session")
def lote_sintetico(tmp_path_factory):
    """Lote determinista (semilla fija) de 6 fotos A4 sintéticas con su verdad de terreno.

    Se genera una vez por sesión de pytest; los tests no deben modificar los archivos.
    """
    return generar_lote(tmp_path_factory.mktemp("lote_sintetico"), n=6, formato="a4")
