"""CO-R1: carga con EXIF y control de calidad."""

import io
import json

import cv2
import numpy as np
import pytest
from PIL import Image
from tools.sintetico.fotografiar import ORIENTACIONES, guardar_jpeg

from autoevalpsi.core.imagen import (
    ImagenInvalida,
    InformeCalidad,
    UmbralesCalidad,
    cargar_imagen,
    evaluar_calidad,
)


@pytest.fixture(scope="module")
def foto_nitida(lote_sintetico):
    return cargar_imagen(lote_sintetico[0].foto.read_bytes())


def _asimetrica(alto=120, ancho=200):
    """Imagen sin simetrías: cada giro/espejo deja una huella distinta."""
    img = np.full((alto, ancho, 3), 255, np.uint8)
    img[:40, :60] = (0, 0, 255)  # rojo arriba-izquierda
    img[-30:, -80:] = (255, 0, 0)  # azul abajo-derecha
    img[50:70, :20] = (0, 160, 0)  # verde a la izquierda
    return img


# --- carga ---------------------------------------------------------------------------------


@pytest.mark.parametrize("orientacion", ORIENTACIONES)
def test_exif_se_aplica_y_la_foto_queda_como_se_tomo(tmp_path, orientacion):
    original = _asimetrica()
    ruta = tmp_path / "f.jpg"
    guardar_jpeg(original, ruta, calidad=95, orientacion=orientacion)
    cargada = cargar_imagen(ruta.read_bytes())
    assert cargada.shape == original.shape
    assert cargada.dtype == np.uint8
    assert np.abs(cargada.astype(int) - original).mean() < 6


def test_negativo_sin_exif_la_foto_vertical_llega_acostada(tmp_path):
    """Sin aplicar EXIF (`IMREAD_IGNORE_ORIENTATION`) la foto llega acostada: el test de
    arriba discrimina de verdad."""
    ruta = tmp_path / "f.jpg"
    guardar_jpeg(_asimetrica(), ruta, calidad=95, orientacion=6)
    crudo = cv2.imread(str(ruta), cv2.IMREAD_IGNORE_ORIENTATION | cv2.IMREAD_COLOR)
    assert crudo.shape[:2] == (200, 120)  # acostada
    assert cargar_imagen(ruta.read_bytes()).shape[:2] == (120, 200)


def test_foto_del_lote_con_exif_rotado_queda_vertical(lote_sintetico):
    for f in lote_sintetico:
        verdad = json.loads(f.verdad.read_text(encoding="utf-8"))
        img = cargar_imagen(f.foto.read_bytes())
        ancho, alto = verdad["fotografia"]["tamano_foto"]
        assert img.shape[:2] == (alto, ancho), f.foto.name
        assert alto > ancho


def test_png_en_rgba_y_en_gris_se_entrega_en_bgr():
    for modo in ("RGBA", "L", "P"):
        buf = io.BytesIO()
        Image.new(modo, (30, 20)).save(buf, "PNG")
        assert cargar_imagen(buf.getvalue()).shape == (20, 30, 3)


def test_heic_se_rechaza_con_mensaje_claro():
    heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
    with pytest.raises(ImagenInvalida, match="HEIC"):
        cargar_imagen(heic)


@pytest.mark.parametrize(
    "datos", [b"", b"%PDF-1.7 hola", b"GIF89a....", b"\xff\xd8\xff" + b"basura" * 5]
)
def test_entradas_invalidas_lanzan_imagen_invalida(datos):
    with pytest.raises(ImagenInvalida):
        cargar_imagen(datos)


def test_imagen_invalida_es_value_error():
    assert issubclass(ImagenInvalida, ValueError)


# --- calidad -------------------------------------------------------------------------------


def test_todas_las_fotos_sinteticas_nitidas_pasan(lote_sintetico):
    for f in lote_sintetico:
        r = evaluar_calidad(cargar_imagen(f.foto.read_bytes()))
        assert r.ok, (f.foto.name, r)


def test_foto_nitida_informe(foto_nitida):
    r = evaluar_calidad(foto_nitida)
    assert isinstance(r, InformeCalidad)
    assert r.ok and r.problemas == []
    assert r.nitidez > 500
    assert 100 < r.brillo < 215
    assert r.lado_largo == 2400


def test_desenfocada_falla(foto_nitida):
    r = evaluar_calidad(cv2.GaussianBlur(foto_nitida, (0, 0), 4))
    assert not r.ok
    assert any("desenfocada" in p for p in r.problemas)


def test_oscura_falla(foto_nitida):
    r = evaluar_calidad((foto_nitida * 0.3).astype(np.uint8))
    assert not r.ok
    assert any("oscura" in p for p in r.problemas)


def test_quemada_falla(foto_nitida):
    r = evaluar_calidad(np.clip(foto_nitida.astype(np.float32) * 1.6, 0, 255).astype(np.uint8))
    assert not r.ok
    assert any("quemadas" in p or "clara" in p for p in r.problemas)


def test_resolucion_baja_falla(foto_nitida):
    chica = cv2.resize(foto_nitida, (300, 400), interpolation=cv2.INTER_AREA)
    r = evaluar_calidad(chica)
    assert any("Resolución" in p for p in r.problemas)


def test_nitidez_no_depende_del_tamano(foto_nitida):
    """Se mide sobre la imagen reducida: la misma foto a 2400 y a 1200 px da lo mismo."""
    a = evaluar_calidad(foto_nitida).nitidez
    mitad = cv2.resize(foto_nitida, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    b = evaluar_calidad(mitad, UmbralesCalidad(lado_min=0)).nitidez
    assert 0.5 < b / a < 2.0


def test_umbrales_configurables(foto_nitida):
    r = evaluar_calidad(foto_nitida, UmbralesCalidad(nitidez_min=1e9))
    assert not r.ok
