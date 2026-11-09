"""Arranque que se repite si una DLL está tomada por otro proceso (tras instalar o actualizar)."""

import pytest

from autoevalpsi.app.reintento import ESPERA, INTENTOS, arrancar


def _falla(_=None):
    raise ImportError("DLL load failed: está siendo utilizado por otro proceso")


def test_si_el_import_sale_bien_corre_main_y_no_espera():
    esperas, relanzado = [], []
    codigo = arrancar(
        lambda: lambda: 7, intento=0, relanzar=lambda: relanzado.append(1), esperar=esperas.append
    )
    assert codigo == 7 and not esperas and not relanzado


def test_si_el_import_falla_espera_y_se_relanza_sin_abrir_nada():
    esperas, relanzado = [], []
    codigo = arrancar(
        _falla, intento=0, relanzar=lambda: relanzado.append(1), esperar=esperas.append
    )
    assert codigo == 0 and esperas == [ESPERA] and relanzado == [1]


def test_agotados_los_intentos_deja_ver_el_error():
    relanzado = []
    with pytest.raises(ImportError, match="DLL"):
        arrancar(
            _falla, intento=INTENTOS, relanzar=lambda: relanzado.append(1), esperar=lambda _: None
        )
    assert not relanzado


def test_un_error_que_no_es_de_import_no_se_repite():
    def importar():
        raise RuntimeError("otra cosa")

    with pytest.raises(RuntimeError):
        arrancar(importar, intento=0, relanzar=lambda: None, esperar=lambda _: None)


def test_el_intento_sale_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("AUTOEVALPSI_INTENTO", str(INTENTOS))
    with pytest.raises(ImportError):
        arrancar(_falla, relanzar=lambda: None, esperar=lambda _: None)
