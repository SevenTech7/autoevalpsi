import sys

from autoevalpsi.app import lanzador
from autoevalpsi.core.ocr.lector import LectorFalso


def test_la_prueba_de_humo_arranca_el_servidor_y_usa_el_lector(capsys):
    lector = LectorFalso([])
    assert lanzador.prueba_humo(lector, puerto=8791) == 0
    assert len(lector.llamadas) == 1
    assert "prueba de humo ok (con OCR)" in capsys.readouterr().out


def test_la_prueba_de_humo_sin_ocr_tambien_pasa(capsys):
    assert lanzador.prueba_humo(None, puerto=8792) == 0
    assert "(sin OCR)" in capsys.readouterr().out


def test_la_prueba_de_humo_falla_si_el_ocr_no_carga(capsys):
    lector = LectorFalso(error=ImportError("falta una DLL"))
    assert lanzador.prueba_humo(lector, puerto=8793) == 1
    assert "falta una DLL" in capsys.readouterr().err


def test_sin_modelos_junto_al_programa_no_hay_ocr(monkeypatch, tmp_path):
    monkeypatch.setattr(lanzador, "raiz_recursos", lambda: tmp_path)
    assert lanzador.lector_por_defecto() is None


def test_con_modelos_junto_al_programa_hay_ocr(monkeypatch, tmp_path):
    (tmp_path / "modelos" / "pp-ocrv6" / "det").mkdir(parents=True)
    (tmp_path / "modelos" / "pp-ocrv6" / "det" / "inference.onnx").write_bytes(b"x")
    monkeypatch.setattr(lanzador, "raiz_recursos", lambda: tmp_path)
    assert lanzador.lector_por_defecto() is not None


def test_empaquetado_los_recursos_estan_en_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert lanzador.raiz_recursos() == tmp_path


def test_sin_empaquetar_la_raiz_es_la_del_repo():
    assert (lanzador.raiz_recursos() / "pyproject.toml").is_file()
