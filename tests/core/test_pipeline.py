"""CO-R7: pipeline foto → Excel, depuración y comando `procesar`."""

import json
import subprocess
import sys
from datetime import date

import cv2
import numpy as np
import openpyxl
import pytest

from autoevalpsi.cli import main
from autoevalpsi.core.depuracion import dibujar_depuracion
from autoevalpsi.core.excel import exportar
from autoevalpsi.core.hoja import HojaNoEncontrada
from autoevalpsi.core.imagen import ImagenInvalida
from autoevalpsi.core.pipeline import a_evaluacion, procesar_foto
from autoevalpsi.core.plantilla import cargar_plantilla


@pytest.fixture(scope="module")
def contexto(lote_sintetico):
    f = lote_sintetico[0]
    plantilla = cargar_plantilla(f.plantilla)
    ref = cv2.imread(str(f.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    verdad = json.loads(f.verdad.read_text(encoding="utf-8"))
    proc = procesar_foto(f.foto.read_bytes(), plantilla, ref)
    return f, plantilla, ref, verdad, proc


def test_foto_limpia_sale_verde_y_coincide_con_la_verdad(contexto):
    _f, _p, _ref, verdad, proc = contexto
    r = proc.resultado
    assert r.registro_ok and not r.requiere_revision and r.n_amarillas == 0
    for fila in r.filas:
        assert fila.opcion == verdad["items"][str(fila.item)]["marcas"][0]


def test_resultado_es_serializable_a_json(contexto):
    _f, _p, _ref, _v, proc = contexto
    d = json.loads(json.dumps(proc.resultado.a_dict()))
    assert d["plantilla"]["id"] == proc.resultado.plantilla_id
    assert len(d["filas"]) == len(proc.resultado.filas)
    assert d["registro"]["ok"] is True and d["requiere_revision"] is False


def test_resultado_con_error_infinito_sigue_siendo_json(lote_sintetico):
    """Hoja en blanco: el registro falla con error = inf, que JSON no admite."""
    f = lote_sintetico[0]
    plantilla = cargar_plantilla(f.plantilla)
    ref = cv2.imread(str(f.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    blanca = cv2.cvtColor(ref, cv2.COLOR_GRAY2BGR)
    fondo = np.full((ref.shape[0] + 600, ref.shape[1] + 600, 3), 90, np.uint8)
    fondo[300 : 300 + ref.shape[0], 300 : 300 + ref.shape[1]] = blanca
    ok, buf = cv2.imencode(".jpg", cv2.resize(fondo, None, fx=0.5, fy=0.5))
    assert ok
    r = procesar_foto(buf.tobytes(), plantilla, ref).resultado
    json.dumps(r.a_dict(), allow_nan=False)
    assert r.requiere_revision  # nunca verde por defecto: hoja en blanco = todas sin marca


def test_filas_con_bandera_quedan_sin_revisar_en_la_evaluacion(lote_sintetico):
    """Foto 1: recorre los casos de borde; ninguna fila con bandera sale como revisada."""
    f = lote_sintetico[1]
    plantilla = cargar_plantilla(f.plantilla)
    ref = cv2.imread(str(f.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    r = procesar_foto(f.foto.read_bytes(), plantilla, ref).resultado
    ev = a_evaluacion(r, plantilla, paciente="Ana", fecha=date(2026, 11, 6))
    assert r.n_amarillas > 0 and r.requiere_revision
    for res, fila in zip(r.filas, ev.filas, strict=True):
        assert fila.item == res.item and fila.opcion == res.opcion
        assert fila.revisado == res.ok


def test_misma_foto_no_duplica_el_consolidado(contexto, tmp_path):
    _f, plantilla, _ref, _v, proc = contexto
    for _ in range(2):
        ev = a_evaluacion(proc.resultado, plantilla, paciente="Ana", fecha=date(2026, 11, 6))
        exportar(ev, tmp_path)
    consolidado = next(tmp_path.glob("consolidado_*.xlsx"))
    hoja = openpyxl.load_workbook(consolidado).active
    assert hoja.max_row == 2  # cabecera + una evaluación


def test_depuracion_pinta_cada_celda_segun_la_decision(contexto):
    _f, plantilla, _ref, _v, proc = contexto
    img = dibujar_depuracion(proc.registro, plantilla, proc.resultado.filas)
    assert img.shape == proc.registro.imagen.shape and img.dtype == np.uint8
    assert not np.array_equal(img, proc.registro.imagen)
    # la celda elegida de la fila 1 es verde (la foto limpia no tiene banderas)
    fila = proc.resultado.filas[0]
    tabla = plantilla.paginas[0].tablas[0]
    k = tabla.opciones.index(fila.opcion)
    x0 = tabla.columnas_x[k][0]
    y0 = tabla.filas[0].y[0]
    centro = img[y0 + 15, x0 + 15].astype(int)  # esquina interior: papel, sin tinta
    assert centro[1] > centro[0] and centro[1] > centro[2]  # domina el verde (BGR)


def test_depuracion_no_modifica_el_registro(contexto):
    _f, plantilla, _ref, _v, proc = contexto
    antes = proc.registro.imagen.copy()
    dibujar_depuracion(proc.registro, plantilla, proc.resultado.filas)
    assert np.array_equal(antes, proc.registro.imagen)


# --- errores de la foto: llegan sin capturar --------------------------------------------------


def test_foto_ilegible_lanza_imagen_invalida(contexto):
    _f, plantilla, ref, _v, _proc = contexto
    with pytest.raises(ImagenInvalida):
        procesar_foto(b"no soy una foto", plantilla, ref)


def test_foto_sin_hoja_lanza_hoja_no_encontrada(contexto):
    _f, plantilla, ref, _v, _proc = contexto
    rng = np.random.default_rng(1)
    ruido = rng.integers(0, 255, (1600, 1200, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", cv2.GaussianBlur(ruido, (0, 0), 25))
    assert ok
    with pytest.raises(HojaNoEncontrada):
        procesar_foto(buf.tobytes(), plantilla, ref)


# --- comando ---------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plantilla_autocontenida(lote_sintetico, tmp_path_factory):
    """El JSON del lote apunta a una imagen con otro nombre que `blanca.png`: se deja junto."""
    f = lote_sintetico[0]
    carpeta = tmp_path_factory.mktemp("plantilla")
    plantilla = cargar_plantilla(f.plantilla)
    ruta = carpeta / "plantilla.json"
    ruta.write_text(f.plantilla.read_text("utf-8"), "utf-8")
    (carpeta / plantilla.paginas[0].imagen_referencia).write_bytes(
        (f.plantilla.parent / "blanca.png").read_bytes()
    )
    return ruta


def test_comando_procesar_escribe_excel_y_depuracion(
    lote_sintetico, tmp_path, capsys, plantilla_autocontenida
):
    f = lote_sintetico[0]
    salida = tmp_path / "salida"
    codigo = main(
        [
            "procesar", str(f.foto),
            "--plantilla", str(plantilla_autocontenida),
            "--salida", str(salida),
            "--paciente", "Ana Pérez",
            "--fecha", "2026-11-06",
            "--depuracion",
        ]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert codigo == 0, out
    assert (salida / "2026-11-06_demo-5opciones-a4_Ana_Pérez.xlsx").is_file()
    assert any(salida.glob("consolidado_*.xlsx"))
    assert (salida / "depuracion" / "foto_00.hoja.png").is_file()
    datos = json.loads((salida / "depuracion" / "foto_00.resultado.json").read_text("utf-8"))
    assert datos["requiere_revision"] is False
    assert "a revisar: 0" in out


def test_comando_sin_depuracion_no_crea_la_carpeta(
    lote_sintetico, tmp_path, plantilla_autocontenida
):
    f = lote_sintetico[0]
    codigo = main(
        [
            "procesar",
            str(f.foto),
            "--plantilla",
            str(plantilla_autocontenida),
            "--salida",
            str(tmp_path),
        ]
    )
    assert codigo == 0
    assert not (tmp_path / "depuracion").exists()


def test_comando_busca_la_plantilla_por_id(lote_sintetico, tmp_path, plantilla_autocontenida):
    f = lote_sintetico[0]
    carpeta = plantilla_autocontenida.parent
    datos = json.loads(plantilla_autocontenida.read_text("utf-8"))
    (carpeta / f"{datos['id']}.json").write_text(
        plantilla_autocontenida.read_text("utf-8"), "utf-8"
    )
    codigo = main(
        ["procesar", str(f.foto), "--plantilla", datos["id"], "--plantillas", str(carpeta),
         "--salida", str(tmp_path)]
    )  # fmt: skip
    assert codigo == 0


def test_comando_plantilla_inexistente_da_error_claro(lote_sintetico, tmp_path, capsys):
    f = lote_sintetico[0]
    codigo = main(["procesar", str(f.foto), "--plantilla", "no-existe", "--salida", str(tmp_path)])
    assert codigo == 2
    assert "No encuentro la plantilla" in capsys.readouterr().err


def test_comando_foto_sin_hoja_da_mensaje_para_la_usuaria(
    tmp_path, capsys, plantilla_autocontenida
):
    mala = tmp_path / "mala.jpg"
    mala.write_bytes(b"\xff\xd8\xff basura")
    codigo = main(
        [
            "procesar",
            str(mala),
            "--plantilla",
            str(plantilla_autocontenida),
            "--salida",
            str(tmp_path / "o"),
        ]
    )
    assert codigo == 2
    assert capsys.readouterr().err.startswith("Error:")
    assert not (tmp_path / "o").exists() or not any((tmp_path / "o").glob("*.xlsx"))


def test_comando_archivo_bloqueado_da_error_sin_traza(
    lote_sintetico, tmp_path, capsys, monkeypatch, plantilla_autocontenida
):
    import os

    f = lote_sintetico[0]
    real = os.replace

    def bloqueado(origen, destino):
        raise PermissionError("abierto en Excel")

    monkeypatch.setattr(os, "replace", bloqueado)
    codigo = main(
        [
            "procesar",
            str(f.foto),
            "--plantilla",
            str(plantilla_autocontenida),
            "--salida",
            str(tmp_path),
        ]
    )
    monkeypatch.setattr(os, "replace", real)
    assert codigo == 2
    assert "No se pudo guardar" in capsys.readouterr().err


def test_version_no_carga_opencv():
    codigo = """
import sys
from autoevalpsi.cli import main
try:
    main(["--version"])
except SystemExit:
    pass
print("cv2" in sys.modules)
"""
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert r.stdout.strip().endswith("False")
