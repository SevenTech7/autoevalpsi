"""Carpeta Descargas: por defecto de los Excel."""

from pathlib import Path

from autoevalpsi.app import carpetas


def test_devuelve_descargas_si_existe(tmp_path, monkeypatch):
    (tmp_path / "Downloads").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(carpetas, "_descargas_de_windows", lambda: None)
    assert carpetas.carpeta_descargas() == tmp_path / "Downloads"


def test_none_si_no_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(carpetas, "_descargas_de_windows", lambda: None)
    assert carpetas.carpeta_descargas() is None


def test_en_windows_manda_la_carpeta_del_sistema(tmp_path, monkeypatch):
    redirigida = tmp_path / "D" / "Mis descargas"
    redirigida.mkdir(parents=True)
    monkeypatch.setattr(carpetas.os, "name", "nt")
    monkeypatch.setattr(carpetas, "_descargas_de_windows", lambda: redirigida)
    assert carpetas.carpeta_descargas() == redirigida
