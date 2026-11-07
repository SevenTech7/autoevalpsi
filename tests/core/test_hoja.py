"""CO-R2: detección de la hoja y corrección de perspectiva."""

import json

import cv2
import numpy as np
import pytest

from autoevalpsi.core.hoja import (
    HojaDetectada,
    HojaNoEncontrada,
    detectar_hoja,
    enderezar_hoja,
    rectificar,
)
from autoevalpsi.core.imagen import cargar_imagen

TAMANO_A4 = (1240, 1754)  # w, h (150 dpi); el registro fino (CO-R3) trabaja a mayor resolución


def _verdad(f):
    return json.loads(f.verdad.read_text(encoding="utf-8"))


def _lado_hoja(esquinas):
    e = np.asarray(esquinas, float)
    return max(np.linalg.norm(e[1] - e[0]), np.linalg.norm(e[3] - e[0]))


def _ncc(a, b, margen=20):
    """Correlación entre dos grises tras quitar la iluminación (paso alto) y el borde de ~1 %,
    donde está justo el error permitido de las esquinas."""

    def filtrar(x):
        x = cv2.GaussianBlur(x, (0, 0), 6).astype(float)
        return (x - cv2.GaussianBlur(x, (0, 0), 25))[margen:-margen, margen:-margen]

    return float(np.corrcoef(filtrar(a).ravel(), filtrar(b).ravel())[0, 1])


# --- contorno del papel --------------------------------------------------------------------


def test_esquinas_a_menos_del_1_por_ciento_en_todo_el_lote(lote_sintetico):
    for f in lote_sintetico:
        img = cargar_imagen(f.foto.read_bytes())
        real = np.array(_verdad(f)["fotografia"]["esquinas"])
        hoja = detectar_hoja(img)
        assert isinstance(hoja, HojaDetectada)
        assert hoja.metodo == "contorno"
        assert hoja.esquinas.shape == (4, 2)
        error = np.linalg.norm(hoja.esquinas - real, axis=1).max()
        assert error <= 0.01 * _lado_hoja(real), (f.foto.name, error)


def test_rectificada_coincide_con_la_hoja_original(lote_sintetico):
    """La hoja enderezada se parece a la hoja llena sin perspectiva (tras reducir ambas)."""
    for f in lote_sintetico:
        img = cargar_imagen(f.foto.read_bytes())
        plana, _ = enderezar_hoja(img, TAMANO_A4)
        assert plana.shape[:2] == (TAMANO_A4[1], TAMANO_A4[0])
        ref = cv2.imread(str(f.hoja), cv2.IMREAD_GRAYSCALE)
        ref = cv2.resize(ref, TAMANO_A4, interpolation=cv2.INTER_AREA)
        ncc = _ncc(cv2.cvtColor(plana, cv2.COLOR_BGR2GRAY), ref)
        assert ncc > 0.9, (f.foto.name, ncc)


def test_orden_de_esquinas_arriba_izq_arriba_der_abajo_der_abajo_izq(lote_sintetico):
    img = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    tl, tr, br, bl = detectar_hoja(img).esquinas
    assert tl[0] < tr[0] and bl[0] < br[0] and tl[1] < bl[1] and tr[1] < br[1]


def test_hoja_apaisada_en_la_foto_se_ordena_como_la_plantilla_vertical(lote_sintetico):
    """Foto tomada de lado (EXIF no la corrige): la hoja vertical se ve horizontal."""
    img = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    acostada = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    hoja = detectar_hoja(acostada, proporcion=TAMANO_A4[0] / TAMANO_A4[1])
    plana = rectificar(acostada, hoja.esquinas, TAMANO_A4)
    # Aunque la hoja entra girada 90°, queda con el lado largo en vertical (la proporción
    # coincide); el giro fino lo resuelve el registro de CO-R3.
    assert plana.shape[:2] == (TAMANO_A4[1], TAMANO_A4[0])
    ref = cv2.imread(str(lote_sintetico[0].hoja), cv2.IMREAD_GRAYSCALE)
    ref = cv2.resize(ref, TAMANO_A4, interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(plana, cv2.COLOR_BGR2GRAY)
    giros = [_ncc(np.rot90(g, k).copy(), ref) for k in (0, 2)]
    assert max(giros) > 0.85  # igual que la hoja, salvo un giro de 180°


# --- errores explicables (tests negativos) -------------------------------------------------


def test_sin_hoja_en_la_imagen_da_error_explicable():
    rng = np.random.default_rng(1)
    ruido = rng.integers(60, 140, (1200, 900, 3), dtype=np.uint8)
    with pytest.raises(HojaNoEncontrada, match="hoja entera"):
        detectar_hoja(ruido)


def test_imagen_lisa_da_error_explicable():
    with pytest.raises(HojaNoEncontrada, match="hoja entera"):
        detectar_hoja(np.full((1200, 900, 3), 120, np.uint8))


def test_hoja_cortada_por_el_borde_de_la_foto_se_rechaza(lote_sintetico):
    """La hoja se sale del cuadro: no se ve entera, no hay que inventar las esquinas."""
    img = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    h = img.shape[0]
    recortada = img[int(0.25 * h) :, :]  # se pierde el borde superior de la hoja
    with pytest.raises(HojaNoEncontrada, match="hoja entera"):
        detectar_hoja(recortada)


def test_hoja_diminuta_en_la_foto_se_rechaza(lote_sintetico):
    img = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    h, w = img.shape[:2]
    lienzo = np.full((h * 3, w * 3, 3), 90, np.uint8)
    lienzo[h : 2 * h, w : 2 * w] = img  # la hoja ocupa ~7 % del cuadro
    with pytest.raises(HojaNoEncontrada):
        detectar_hoja(lienzo)


def test_homografia_degenerada_se_rechaza():
    with pytest.raises(HojaNoEncontrada):
        rectificar(
            np.zeros((100, 100, 3), np.uint8),
            np.array([[0, 0], [50, 50], [100, 100], [10, 10]], float),
            TAMANO_A4,
        )


# --- marcas ArUco --------------------------------------------------------------------------


def _hoja_con_marcas(ids=(0, 1, 2, 3), margen=80, lado=140):
    """Página blanca 1000×1400 con marcas en las esquinas; devuelve (página, esquinas externas)."""
    w, h = 1000, 1400
    pagina = np.full((h, w, 3), 255, np.uint8)
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    pos = [(margen, margen), (w - margen - lado, margen),
           (w - margen - lado, h - margen - lado), (margen, h - margen - lado)]  # fmt: skip
    for i, (x, y) in zip(ids, pos, strict=True):
        m = cv2.aruco.generateImageMarker(dic, i, lado)
        pagina[y : y + lado, x : x + lado] = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
    externas = np.array(
        [[margen, margen], [w - margen, margen], [w - margen, h - margen], [margen, h - margen]],
        float,
    )
    return pagina, externas


def _foto_de(pagina, esquinas_foto, tamano=(1800, 2400), fondo=100):
    h, w = pagina.shape[:2]
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    H = cv2.getPerspectiveTransform(src, np.asarray(esquinas_foto, np.float32))
    foto = np.full((tamano[1], tamano[0], 3), fondo, np.uint8)
    papel = cv2.warpPerspective(pagina, H, tamano, flags=cv2.INTER_LINEAR)
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), H, tamano) > 0
    foto[mask] = papel[mask]
    return foto, H


def test_aruco_tiene_prioridad_y_da_las_esquinas_externas_de_las_marcas():
    pagina, externas = _hoja_con_marcas()
    quad = [[300, 400], [1500, 450], [1450, 2000], [250, 1950]]
    foto, H = _foto_de(pagina, quad)
    esperado = cv2.perspectiveTransform(externas[None].astype(np.float32), H)[0]
    hoja = detectar_hoja(foto)
    assert hoja.metodo == "aruco"
    assert np.linalg.norm(hoja.esquinas - esperado, axis=1).max() < 6


def test_aruco_funciona_aunque_el_papel_no_se_distinga_del_fondo():
    """Mesa blanca, papel blanco: sin contorno visible, las marcas bastan."""
    pagina, externas = _hoja_con_marcas()
    quad = [[300, 400], [1500, 450], [1450, 2000], [250, 1950]]
    foto, H = _foto_de(pagina, quad, fondo=255)
    esperado = cv2.perspectiveTransform(externas[None].astype(np.float32), H)[0]
    hoja = detectar_hoja(foto)
    assert hoja.metodo == "aruco"
    assert np.linalg.norm(hoja.esquinas - esperado, axis=1).max() < 6


def test_con_marcas_incompletas_se_cae_al_contorno():
    pagina, _ = _hoja_con_marcas()
    pagina[60:240, 60:240] = 255  # borra la marca 0
    quad = [[300, 400], [1500, 450], [1450, 2000], [250, 1950]]
    foto, _ = _foto_de(pagina, quad)
    hoja = detectar_hoja(foto)
    assert hoja.metodo == "contorno"
    assert np.linalg.norm(hoja.esquinas - np.array(quad), axis=1).max() < 12


def test_marcas_con_ids_repetidos_o_ajenos_no_se_usan():
    """Cuatro marcas con ids que no son 0-3 (otro formulario/objeto): se ignoran."""
    pagina, _ = _hoja_con_marcas(ids=(10, 11, 12, 13))
    quad = [[300, 400], [1500, 450], [1450, 2000], [250, 1950]]
    foto, _ = _foto_de(pagina, quad)
    assert detectar_hoja(foto).metodo == "contorno"
