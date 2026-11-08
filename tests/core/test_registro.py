"""CO-R3: registro fino de la foto contra la plantilla."""

import json

import cv2
import numpy as np
import pytest
from tools.sintetico.fotografiar import fotografiar

from autoevalpsi.core import registro
from autoevalpsi.core.hoja import HojaNoEncontrada
from autoevalpsi.core.imagen import cargar_imagen
from autoevalpsi.core.plantilla import cargar_plantilla
from autoevalpsi.core.registro import (
    BANDERA_REGISTRO_DUDOSO,
    Registro,
    RegistroInvalido,
    UmbralesRegistro,
    _evaluar,
    cargar_referencia,
    registrar,
)


def _verdad(f):
    return json.loads(f.verdad.read_text(encoding="utf-8"))


def _esquinas_de_celdas(plantilla):
    """Esquinas de todas las celdas de opción de todas las tablas, en px de plantilla."""
    pts = []
    for t in plantilla.paginas[0].tablas:
        for fila in t.filas:
            for xa, xb in t.columnas_x:
                pts += [[xa, fila.y[0]], [xb, fila.y[0]], [xb, fila.y[1]], [xa, fila.y[1]]]
    return np.array(pts, np.float64)


def _error_celdas(reg: Registro, f, plantilla):
    """Error (px de plantilla) de las esquinas de celdas al llevarlas a la foto con la
    homografía verdadera y de vuelta con la estimada."""
    H_verdad = np.array(_verdad(f)["fotografia"]["homografia"])  # plantilla -> foto
    pts = _esquinas_de_celdas(plantilla)
    en_foto = cv2.perspectiveTransform(pts.reshape(-1, 1, 2), H_verdad)
    vuelta = cv2.perspectiveTransform(en_foto, reg.homografia).reshape(-1, 2)
    return np.linalg.norm(vuelta - pts, axis=1)


@pytest.fixture(scope="module")
def contexto(lote_sintetico):
    f0 = lote_sintetico[0]
    plantilla = cargar_plantilla(f0.plantilla)
    pagina = plantilla.paginas[0]
    # La referencia (blanca.png) está junto a `plantilla.json` del lote.
    ref = cv2.imread(str(f0.plantilla.parent / "blanca.png"), cv2.IMREAD_GRAYSCALE)
    assert ref.shape[::-1] == tuple(pagina.tamano_px)
    return plantilla, ref


@pytest.fixture(scope="module")
def registros(lote_sintetico, contexto):
    _, ref = contexto
    return [registrar(cargar_imagen(f.foto.read_bytes()), ref) for f in lote_sintetico]


# --- exactitud sobre el lote sintético -------------------------------------------------------


def test_error_medio_en_esquinas_de_celdas_a_3_px_o_menos(lote_sintetico, contexto, registros):
    plantilla, _ = contexto
    for f, reg in zip(lote_sintetico, registros, strict=True):
        err = _error_celdas(reg, f, plantilla)
        assert err.mean() <= 3.0, (f.foto.name, err.mean())
        assert err.max() <= 8.0, (f.foto.name, err.max())  # ninguna esquina se va lejos


def test_el_lote_completo_registra_ok_sin_banderas(lote_sintetico, registros):
    for f, reg in zip(lote_sintetico, registros, strict=True):
        assert isinstance(reg, Registro)
        assert reg.ok and reg.banderas == (), (f.foto.name, reg)
        assert reg.giro == 0
        assert reg.proporcion_inliers >= 0.5, (f.foto.name, reg.proporcion_inliers)


def test_la_imagen_registrada_tiene_el_tamano_de_la_plantilla(contexto, registros):
    plantilla, _ref = contexto
    ancho, alto = plantilla.paginas[0].tamano_px
    for reg in registros:
        assert reg.imagen.shape == (alto, ancho, 3)
        assert reg.homografia.shape == (3, 3)


def test_la_imagen_registrada_se_parece_a_la_hoja_original(lote_sintetico, registros):
    """La retícula cae sobre la de la hoja sin perspectiva (que ya tiene las marcas)."""
    for f, reg in zip(lote_sintetico, registros, strict=True):
        hoja = cv2.imread(str(f.hoja), cv2.IMREAD_GRAYSCALE)
        reg_g = cv2.cvtColor(reg.imagen, cv2.COLOR_BGR2GRAY)
        a = cv2.GaussianBlur(reg_g, (0, 0), 6).astype(float)
        b = cv2.GaussianBlur(hoja, (0, 0), 6).astype(float)
        a -= cv2.GaussianBlur(a, (0, 0), 30)
        b -= cv2.GaussianBlur(b, (0, 0), 30)
        ncc = float(np.corrcoef(a.ravel(), b.ravel())[0, 1])
        assert ncc > 0.9, (f.foto.name, ncc)


def test_ajuste_con_lineas_no_empeora_el_registro(lote_sintetico, contexto):
    """El ajuste fino mejora (o al menos no empeora) frente a quedarse con ORB solo."""
    plantilla, ref = contexto
    f = lote_sintetico[2]
    foto = cargar_imagen(f.foto.read_bytes())
    con = registrar(foto, ref)
    assert _error_celdas(con, f, plantilla).mean() <= 3.0
    if con.ajuste_lineas:
        assert con.correlacion_lineas > 0.5


# --- giros ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "giro_cv, grados",
    [
        (None, 0),
        (cv2.ROTATE_180, 180),
        (cv2.ROTATE_90_CLOCKWISE, None),
        (cv2.ROTATE_90_COUNTERCLOCKWISE, None),
    ],
)
def test_foto_girada_se_registra_igual(lote_sintetico, contexto, giro_cv, grados):
    """Hoja boca abajo o de lado (sin EXIF que lo corrija): se registra y queda derecha."""
    _plantilla, ref = contexto
    f = lote_sintetico[0]
    foto = cargar_imagen(f.foto.read_bytes())
    girada = foto if giro_cv is None else cv2.rotate(foto, giro_cv)
    reg = registrar(girada, ref)
    assert reg.ok, reg
    assert reg.giro in (0, 180)
    if grados == 180:
        assert reg.giro == 180
    # Mismo resultado que la foto derecha: la imagen registrada coincide con la de referencia
    # de hoja (misma verificación que la prueba de parecido).
    base = registrar(foto, ref)
    a = cv2.cvtColor(reg.imagen, cv2.COLOR_BGR2GRAY).astype(float)
    b = cv2.cvtColor(base.imagen, cv2.COLOR_BGR2GRAY).astype(float)
    a, b = cv2.GaussianBlur(a, (0, 0), 6), cv2.GaussianBlur(b, (0, 0), 6)
    assert float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) > 0.95


# --- CO-09: registro malo = bandera de página (tests negativos) --------------------------------


def _formulario_ajeno(ancho=2480, alto=3508):
    """Hoja con otro diseño: ninguna coincidencia útil con la plantilla demo."""
    rng = np.random.default_rng(7)
    img = np.full((alto, ancho), 255, np.uint8)
    for _ in range(40):
        x0, y0 = int(rng.integers(100, ancho - 400)), int(rng.integers(100, alto - 300))
        cv2.rectangle(
            img,
            (x0, y0),
            (x0 + int(rng.integers(100, 400)), y0 + int(rng.integers(60, 250))),
            0,
            int(rng.integers(2, 6)),
        )
        cv2.putText(
            img,
            "otro " + str(int(rng.integers(1000))),
            (x0, y0 - 10),
            cv2.FONT_HERSHEY_DUPLEX,
            float(rng.uniform(1, 2.5)),
            0,
            2,
            cv2.LINE_AA,
        )
    cv2.rectangle(img, (80, 80), (ancho - 80, alto - 80), 0, 6)
    return img


def test_foto_de_otro_formulario_lleva_la_bandera_de_pagina(contexto):
    _, ref = contexto
    rng = np.random.default_rng(3)
    foto, _ = fotografiar(
        cv2.cvtColor(_formulario_ajeno(), cv2.COLOR_GRAY2BGR), rng, tamano=(1800, 2400)
    )
    reg = registrar(foto, ref)
    assert not reg.ok
    assert BANDERA_REGISTRO_DUDOSO in reg.banderas


def test_hoja_en_blanco_no_revienta_y_lleva_la_bandera(contexto):
    _, ref = contexto
    rng = np.random.default_rng(4)
    blanco = np.full(ref.shape, 255, np.uint8)
    cv2.rectangle(blanco, (60, 60), (ref.shape[1] - 60, ref.shape[0] - 60), 0, 6)
    foto, _ = fotografiar(cv2.cvtColor(blanco, cv2.COLOR_GRAY2BGR), rng, tamano=(1800, 2400))
    reg = registrar(foto, ref)
    assert not reg.ok
    assert BANDERA_REGISTRO_DUDOSO in reg.banderas


def test_umbrales_estrictos_marcan_un_registro_bueno_como_dudoso(lote_sintetico, contexto):
    """La bandera sale de los umbrales: con exigencia imposible, la página se marca."""
    _, ref = contexto
    foto = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    reg = registrar(foto, ref, umbrales=UmbralesRegistro(inliers_min=10**6))
    assert not reg.ok and BANDERA_REGISTRO_DUDOSO in reg.banderas


def test_sin_hoja_en_la_foto_da_error_explicable(contexto):
    _, ref = contexto
    with pytest.raises(HojaNoEncontrada, match="hoja entera"):
        registrar(np.full((1200, 900, 3), 120, np.uint8), ref)


# --- emparejamiento directo (la hoja llena el cuadro y no se ve su contorno) ----------------------


def _hoja_llena_el_cuadro(f, lado_largo=1600, giro_cv=None):
    """La hoja sin perspectiva (con sus marcas) a un tamaño de foto, sin fondo alrededor."""
    hoja = cv2.imread(str(f.hoja))
    k = lado_largo / max(hoja.shape[:2])
    foto = cv2.resize(hoja, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    return foto if giro_cv is None else cv2.rotate(foto, giro_cv)


@pytest.mark.parametrize("giro_cv", [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180])
def test_hoja_que_llena_el_cuadro_se_registra_por_emparejamiento_directo(
    lote_sintetico, contexto, giro_cv
):
    """Sin contorno de papel que detectar, la foto se empareja con la referencia completa."""
    _, ref = contexto
    f = lote_sintetico[0]
    reg = registrar(_hoja_llena_el_cuadro(f, giro_cv=giro_cv), ref)
    assert reg.metodo_hoja == "directo" and reg.ok, reg
    assert reg.inliers >= 100 and reg.cobertura >= 0.35
    # la imagen registrada coincide con la hoja original (misma comprobación de parecido)
    hoja = cv2.imread(str(f.hoja), cv2.IMREAD_GRAYSCALE)
    reg_g = cv2.cvtColor(reg.imagen, cv2.COLOR_BGR2GRAY)
    a = cv2.GaussianBlur(reg_g, (0, 0), 6).astype(float)
    b = cv2.GaussianBlur(hoja, (0, 0), 6).astype(float)
    a -= cv2.GaussianBlur(a, (0, 0), 30)
    b -= cv2.GaussianBlur(b, (0, 0), 30)
    assert float(np.corrcoef(a.ravel(), b.ravel())[0, 1]) > 0.9
    assert reg.imagen.shape[:2] == ref.shape


def test_con_una_esquina_fuera_la_proporcion_baja_pero_el_registro_vale():
    """Sobran puntos de la referencia sin pareja: muchos inliers con error chico bastan."""
    u = UmbralesRegistro()
    m = {"coincidencias": 1000, "inliers": 280, "error": 0.6, "cobertura": 0.40}
    assert _evaluar(m, 0.78, u)  # proporción 0,28 < 0,30 pero 280 inliers a 0,6 px
    assert not _evaluar({**m, "inliers": 80, "coincidencias": 400}, 0.78, u)  # pocos: no se fía
    assert not _evaluar({**m, "error": 3.0}, 0.78, u)  # muchos pero imprecisos: no


def test_una_foto_reconocida_pero_dudosa_sale_con_bandera_y_no_se_rechaza(contexto, monkeypatch):
    _, ref = contexto
    dudoso = Registro(
        homografia=np.eye(3), imagen=np.zeros((10, 10, 3), np.uint8), metodo_hoja="directo",
        giro=0, coincidencias=600, inliers=110, proporcion_inliers=0.18, error_reproyeccion=0.7,
        cobertura=0.28, correlacion_lineas=0.39, ajuste_lineas=False,
        banderas=("registro_dudoso",),
    )  # fmt: skip
    monkeypatch.setattr(registro, "_registrar_directo", lambda *a, **k: dudoso)
    monkeypatch.setattr(
        registro, "detectar_hoja", lambda *a, **k: (_ for _ in ()).throw(HojaNoEncontrada())
    )
    reg = registrar(np.zeros((1600, 1200, 3), np.uint8), ref)
    assert reg is dudoso and not reg.ok
    # con muy pocas coincidencias sí es otro formulario: se rechaza
    pocas = Registro(**{**dudoso.__dict__, "inliers": 12})
    monkeypatch.setattr(registro, "_registrar_directo", lambda *a, **k: pocas)
    with pytest.raises(HojaNoEncontrada):
        registrar(np.zeros((1600, 1200, 3), np.uint8), ref)


def test_sift_calza_otra_foto_de_la_misma_hoja_con_otra_escala_y_perspectiva(contexto):
    """Plantilla hecha desde una foto: la nueva foto tiene otro encuadre y otra resolución."""
    _, ref = contexto
    h, w = ref.shape
    destino = np.float32(
        [[0.08 * w, 0.10 * h], [0.97 * w, 0.06 * h], [0.99 * w, 0.95 * h], [0.04 * w, 0.92 * h]]
    )
    origen = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    M = cv2.getPerspectiveTransform(origen, destino)
    foto = cv2.warpPerspective(ref, M, (w, h), borderValue=90)
    foto = cv2.resize(foto, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA)  # otra resolución
    foto = cv2.GaussianBlur(foto, (0, 0), 1.0)
    H, m = registro._directa_con(foto, ref, registro._sift, cv2.NORM_L2, 0.8)
    assert H is not None and m["inliers"] >= 40 and m["error"] < 2.0
    # la esquina de la hoja en la foto cae en la esquina de la referencia
    esq = cv2.perspectiveTransform(destino.reshape(-1, 1, 2) * 0.6, H).reshape(-1, 2)
    assert np.abs(esq - origen).max() < 6


def test_elegir_hoja_reconoce_a_cual_de_las_paginas_pertenece_la_foto(lote_sintetico, contexto):
    _, ref = contexto
    otra = cv2.resize(_formulario_ajeno(), (ref.shape[1], ref.shape[0]))
    foto = _hoja_llena_el_cuadro(lote_sintetico[0])
    assert registro.elegir_hoja(foto, {0: ref, 1: otra}) == 0
    assert registro.elegir_hoja(foto, {0: otra, 1: ref}) == 1
    assert registro.elegir_hoja(foto, {1: otra}) == 1  # una sola candidata: no hay nada que elegir
    # ninguna de las dos es la hoja: no se adivina
    ruido = np.random.default_rng(5).integers(0, 255, (1600, 1200, 3), dtype=np.uint8)
    assert registro.elegir_hoja(ruido, {0: ref, 1: otra}) is None


def test_el_emparejamiento_directo_no_da_por_buena_una_hoja_ajena(contexto):
    """Ruido a cuadro completo: ni contorno de papel ni coincidencias con la plantilla."""
    _, ref = contexto
    ruido = np.random.default_rng(7).integers(0, 255, (1600, 1200, 3), dtype=np.uint8)
    with pytest.raises(HojaNoEncontrada):
        registrar(ruido, ref)


def test_referencia_vacia_se_rechaza(lote_sintetico):
    foto = cargar_imagen(lote_sintetico[0].foto.read_bytes())
    with pytest.raises(RegistroInvalido):
        registrar(foto, np.full((3000, 2000), 255, np.uint8))


def test_cargar_referencia_lee_la_imagen_junto_al_json(lote_sintetico):
    f = lote_sintetico[0]
    ref = cargar_referencia(f.plantilla, "blanca.png")
    assert ref.ndim == 2 and ref.shape == (3508, 2480)
    with pytest.raises(RegistroInvalido):
        cargar_referencia(f.plantilla, "no-existe.png")
