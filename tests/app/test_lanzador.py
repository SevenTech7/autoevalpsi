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


def test_el_informe_queda_en_un_archivo(tmp_path):
    informe = tmp_path / "humo.txt"
    assert lanzador.prueba_humo(None, puerto=8794, informe=informe) == 0
    assert "prueba de humo ok" in informe.read_text(encoding="utf-8")
    assert (
        lanzador.prueba_humo(LectorFalso(error=ValueError("x")), puerto=8795, informe=informe) == 1
    )
    assert "FALLÓ" in informe.read_text(encoding="utf-8")


def test_sin_consola_el_programa_arranca_igual(monkeypatch, tmp_path):
    """El .exe de Windows va sin consola: stdout y stderr valen None."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(lanzador, "raiz_recursos", lambda: tmp_path)
    informe = tmp_path / "humo.txt"
    assert lanzador.main(["--prueba-humo", "--informe", str(informe)]) == 0
    assert "prueba de humo ok" in informe.read_text(encoding="utf-8")


def _servir_con_interfaz(tmp_path, nombre_js="app.js", contenido_index=None):
    from autoevalpsi.app.datos import BaseDatos
    from autoevalpsi.app.escritorio import ServidorLocal
    from autoevalpsi.app.plantillas import RepositorioPlantillas
    from autoevalpsi.app.servidor import crear_app

    est = tmp_path / "estaticos"
    (est / "assets").mkdir(parents=True)
    (est / "assets" / nombre_js).write_text("console.log(1)", encoding="utf-8")
    index = (
        contenido_index
        if contenido_index is not None
        else f'<script type="module" src="/assets/{nombre_js}"></script>'
    )
    (est / "index.html").write_text(index, encoding="utf-8")
    bd = BaseDatos(tmp_path / "d")
    app = crear_app(bd, RepositorioPlantillas(tmp_path / "d" / "p"), estaticos=est)
    servidor = ServidorLocal(app, puerto=0)
    servidor.iniciar()
    return bd, servidor


def test_la_comprobacion_de_la_interfaz_acepta_un_script_bien_servido(tmp_path):
    bd, servidor = _servir_con_interfaz(tmp_path)
    try:
        assert lanzador._interfaz_se_sirve(servidor.puerto) is None
    finally:
        servidor.detener()
        bd.cerrar()


def test_la_comprobacion_de_la_interfaz_detecta_que_falta_el_script(tmp_path):
    bd, servidor = _servir_con_interfaz(tmp_path, contenido_index="<p>sin scripts</p>")
    try:
        assert "ningún script" in lanzador._interfaz_se_sirve(servidor.puerto)
    finally:
        servidor.detener()
        bd.cerrar()
