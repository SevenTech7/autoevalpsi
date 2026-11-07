"""CO-R2: detección de la hoja en la foto y corrección de perspectiva.

`detectar_hoja(imagen)` devuelve las 4 esquinas de la hoja (px de la imagen original, orden
arriba-izq, arriba-der, abajo-der, abajo-izq) y el método usado:

1. **ArUco** (prioridad): si se ven las 4 marcas `DICT_4X4_50` con ids 0-3 (arriba-izq,
   arriba-der, abajo-der, abajo-izq), las esquinas son la esquina *externa* de cada marca. Las
   marcas se identifican por id, así que el orden sale bien aunque la foto esté girada. Dónde
   caen esas esquinas dentro de la plantilla lo fija PL-R5 (hojas reimprimibles).
2. **Contorno del papel**: mayor cuadrilátero convexo en los bordes (Canny) o, si no, en la
   máscara de lo claro (Otsu). Si la hoja toca el borde de la foto, es diminuta o no hay
   cuadrilátero, lanza `HojaNoEncontrada` («no se ve la hoja entera»): nunca se inventan
   esquinas.

`rectificar(imagen, esquinas, tamano)` aplica la homografía a una imagen `tamano` = (ancho, alto);
`enderezar_hoja` junta ambos pasos. El giro de 180° (hoja boca abajo) no se puede saber solo
con el contorno: lo resuelve el registro contra la plantilla (CO-R3). Con `proporcion` (ancho/
alto de la plantilla), una hoja que se ve apaisada se ordena como vertical (giro de 90°).
"""

from dataclasses import dataclass

import cv2
import numpy as np

from autoevalpsi.core.imagen import ImagenInvalida

_LADO_ANALISIS = 1000  # px del lado largo para buscar el contorno
_AREA_MIN = 0.25  # la hoja ocupa al menos esta fracción de la foto
_MARGEN_BORDE = 0.004  # fracción del lado largo: una esquina más cerca del borde = hoja cortada
_RAZON_LADOS_MIN = 0.5  # lados opuestos parecidos; descarta tiras y cuadriláteros torcidos
_IDS_ARUCO = (0, 1, 2, 3)

MENSAJE_NO_SE_VE = (
    "No se ve la hoja entera: pon la hoja completa dentro de la foto, sobre un fondo que "
    "contraste, con sus cuatro esquinas visibles."
)


class HojaNoEncontrada(ImagenInvalida):
    """No se pudo ubicar la hoja; el mensaje está pensado para mostrarse al usuario."""

    def __init__(self, mensaje: str = MENSAJE_NO_SE_VE):
        super().__init__(mensaje)


@dataclass(frozen=True)
class HojaDetectada:
    esquinas: np.ndarray  # (4, 2) float64: arriba-izq, arriba-der, abajo-der, abajo-izq
    metodo: str  # "aruco" | "contorno"


def _gris(imagen: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen


def _ordenar(pts: np.ndarray) -> np.ndarray:
    """Arriba-izq, arriba-der, abajo-der, abajo-izq (geométrico, para giros leves)."""
    pts = np.asarray(pts, np.float64).reshape(4, 2)
    s, d = pts.sum(axis=1), pts[:, 0] - pts[:, 1]
    return np.array([pts[s.argmin()], pts[d.argmax()], pts[s.argmax()], pts[d.argmin()]])


def _area(q: np.ndarray) -> float:
    return float(abs(cv2.contourArea(np.asarray(q, np.float32))))


def _es_cuadrilatero_valido(q: np.ndarray) -> bool:
    if not cv2.isContourConvex(np.asarray(q, np.float32).reshape(4, 1, 2)):
        return False
    lados = np.linalg.norm(q - np.roll(q, -1, axis=0), axis=1)
    return bool(
        lados.min() > 0
        and min(lados[0], lados[2]) / max(lados[0], lados[2]) >= _RAZON_LADOS_MIN
        and min(lados[1], lados[3]) / max(lados[1], lados[3]) >= _RAZON_LADOS_MIN
    )


# --- ArUco ---------------------------------------------------------------------------------


def _detectar_aruco(gris: np.ndarray) -> np.ndarray | None:
    dic = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    esquinas, ids, _ = cv2.aruco.ArucoDetector(dic, cv2.aruco.DetectorParameters()).detectMarkers(
        gris
    )
    if ids is None:
        return None
    ids = ids.ravel().tolist()
    if sorted(ids) != list(_IDS_ARUCO):  # faltan, sobran o se repiten: no es nuestra hoja
        return None
    quad = np.array([esquinas[ids.index(k)].reshape(4, 2)[k] for k in _IDS_ARUCO], np.float64)
    return quad if _es_cuadrilatero_valido(quad) else None


# --- contorno del papel --------------------------------------------------------------------


def _mejor_cuadrilatero(contornos, area_img: float) -> np.ndarray | None:
    """Mayor cuadrilátero entre `contornos` (por área). None si ninguno llega al mínimo."""
    mejor, mejor_area = None, 0.0
    for c in contornos:
        if cv2.contourArea(c) < _AREA_MIN * area_img * 0.5:
            continue  # descarte barato antes de calcular el casco
        casco = cv2.convexHull(c)
        if cv2.contourArea(casco) < _AREA_MIN * area_img:
            continue
        perimetro = cv2.arcLength(casco, True)
        for eps in (0.01, 0.02, 0.03, 0.05, 0.08):
            aprox = cv2.approxPolyDP(casco, eps * perimetro, True)
            if len(aprox) == 4:
                q = _ordenar(aprox)
                a = _area(q)
                if a > mejor_area and _es_cuadrilatero_valido(q):
                    mejor, mejor_area = q, a
                break
            if len(aprox) < 4:
                break
    return mejor


def _candidatos(gris: np.ndarray):
    """Contornos por método, en orden de preferencia (bordes primero)."""
    borroso = cv2.GaussianBlur(gris, (0, 0), 2.0)
    bordes = cv2.Canny(borroso, 30, 90)
    bordes = cv2.morphologyEx(bordes, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
    yield cv2.findContours(bordes, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]

    _, mascara = cv2.threshold(borroso, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    yield cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]


def _detectar_contorno(gris: np.ndarray) -> np.ndarray | None:
    h, w = gris.shape
    k = min(1.0, _LADO_ANALISIS / max(h, w))
    chica = cv2.resize(gris, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)
    hc, wc = chica.shape
    margen = _MARGEN_BORDE * max(hc, wc)
    for contornos in _candidatos(chica):
        q = _mejor_cuadrilatero(contornos, float(hc * wc))
        if q is None:
            continue
        dentro = (
            (q[:, 0] > margen).all()
            and (q[:, 0] < wc - 1 - margen).all()
            and (q[:, 1] > margen).all()
            and (q[:, 1] < hc - 1 - margen).all()
        )
        if dentro:
            return q / k
        # La hoja más grande toca el borde: está cortada. No seguir con otro método
        # ni con un cuadrilátero interior (p. ej. la tabla), que sería un falso positivo.
        return None
    return None


# --- API -----------------------------------------------------------------------------------


def _orientar(q: np.ndarray, proporcion: float | None) -> np.ndarray:
    """Si la hoja se ve apaisada y la plantilla es vertical (o al revés), gira el orden 90°."""
    if proporcion is None:
        return q
    ancho = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    alto = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    if (ancho / alto > 1) != (proporcion > 1):
        return np.roll(q, 1, axis=0)
    return q


def detectar_hoja(imagen: np.ndarray, *, proporcion: float | None = None) -> HojaDetectada:
    """Ubica la hoja; `proporcion` = ancho/alto de la plantilla (para hojas giradas 90°)."""
    gris = _gris(imagen)
    quad = _detectar_aruco(gris)
    if quad is not None:
        return HojaDetectada(quad, "aruco")
    quad = _detectar_contorno(gris)
    if quad is None:
        raise HojaNoEncontrada()
    return HojaDetectada(_orientar(quad, proporcion), "contorno")


def rectificar(imagen: np.ndarray, esquinas: np.ndarray, tamano: tuple[int, int]) -> np.ndarray:
    """Endereza el cuadrilátero `esquinas` a una imagen de `tamano` = (ancho, alto) px."""
    q = np.asarray(esquinas, np.float32).reshape(4, 2)
    if not _es_cuadrilatero_valido(q.astype(np.float64)) or _area(q) <= 0:
        raise HojaNoEncontrada()
    ancho, alto = tamano
    destino = np.array([[0, 0], [ancho, 0], [ancho, alto], [0, alto]], np.float32)
    H = cv2.getPerspectiveTransform(q, destino)
    return cv2.warpPerspective(
        imagen, H, (ancho, alto), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def enderezar_hoja(imagen: np.ndarray, tamano: tuple[int, int]) -> tuple[np.ndarray, HojaDetectada]:
    """Detecta la hoja y la devuelve enderezada a `tamano` = (ancho, alto), con la detección."""
    hoja = detectar_hoja(imagen, proporcion=tamano[0] / tamano[1])
    return rectificar(imagen, hoja.esquinas, tamano), hoja
