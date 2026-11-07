"""CO-R3: registro fino de la foto contra la imagen en blanco de la plantilla.

`registrar(foto, referencia)` lleva la foto al sistema de coordenadas de la plantilla (px de
`tamano_px`), de modo que una casilla caiga donde dice el JSON. Pasos:

1. **Hoja enderezada** (CO-R2): `detectar_hoja` + `rectificar` al tamaño de la referencia.
2. **Giro**: el contorno no distingue 0° de 180°; se prueba la hoja tal cual y girada 180°, y se
   queda la que registra mejor (la segunda solo se prueba si la primera no sale bien).
3. **ORB + RANSAC**: coincidencias entre la hoja enderezada y la referencia. La hoja ya está casi
   alineada, así que solo valen las coincidencias *cerca* de donde deberían estar (descarta los
   falsos emparejamientos de una cuadrícula repetitiva); `findHomography(RANSAC)` da el resto.
4. **Ajuste con las líneas de la tabla** (CO-R3, «morfología»): máscaras de líneas largas
   (apertura morfológica) de la referencia y de la hoja registrada, y `findTransformECC`
   (afín) entre ellas corrige el desplazamiento residual. Solo se acepta si mejora la correlación.
5. **Calidad (CO-09)**: nº y proporción de inliers, error de reproyección, cobertura de la hoja
   por los inliers (área de su casco) y correlación de líneas. Si algo no llega al umbral, la página lleva la
   bandera `registro_dudoso` y debe pasar a revisión obligatoria: nunca se leen casillas «en
   silencio» con un registro malo.

La imagen final se obtiene con **una sola** deformación desde la foto original (sin pasos
intermedios que pierdan nitidez). `registrar` no lanza por mal registro (devuelve `ok=False`);
sí lanza `HojaNoEncontrada` si no se ve la hoja (error explicable, igual que en CO-R2).
"""

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.hoja import detectar_hoja
from autoevalpsi.core.imagen import ImagenInvalida

BANDERA_REGISTRO_DUDOSO = "registro_dudoso"
_LADO_ORB = 1400  # px del lado largo para buscar coincidencias
_NFEATURES = 6000
_RAZON_LOWE = 0.8
_RADIO_BUSQUEDA = 0.06  # fracción del lado largo: una coincidencia más lejos es falsa
_UMBRAL_RANSAC_PX = 6.0  # a escala _LADO_ORB
_LADO_ECC = 1000  # px del lado largo para las máscaras de líneas
_LARGO_LINEA = 0.035  # fracción del ancho: núcleo de la apertura morfológica
_SHIFT_ECC_MAX = 0.02  # el ajuste fino no mueve más de esta fracción del lado largo


class RegistroInvalido(ImagenInvalida):
    """La referencia no sirve (vacía o ilegible); no es un fallo de la foto."""


@dataclass(frozen=True)
class UmbralesRegistro:
    """Umbrales de calidad del registro (CO-09). Se ajustan con fotos reales (CO-R8)."""

    inliers_min: int = 40
    proporcion_inliers_min: float = 0.30
    error_reproyeccion_max: float = 4.0  # px de plantilla, mediana de los inliers
    cobertura_min: float = 0.35  # fracción de la hoja que cubren los inliers (casco)
    correlacion_lineas_min: float = 0.25


@dataclass(frozen=True)
class Registro:
    homografia: np.ndarray  # (3, 3) px de la foto original -> px de la plantilla
    imagen: np.ndarray  # BGR a tamaño de la plantilla, casillas donde dice el JSON
    metodo_hoja: str  # "aruco" | "contorno"
    giro: int  # 0 | 180: grados que se giró la hoja enderezada
    coincidencias: int
    inliers: int
    proporcion_inliers: float
    error_reproyeccion: float  # px de plantilla (mediana de los inliers)
    cobertura: float  # fracción de la hoja cubierta por los inliers
    correlacion_lineas: float  # -1..1: líneas de la tabla de la hoja vs la referencia
    ajuste_lineas: bool  # True si el ajuste fino con líneas se aplicó
    banderas: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return BANDERA_REGISTRO_DUDOSO not in self.banderas


# --- utilidades ------------------------------------------------------------------------------


def _gris(imagen: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen


def _escala(k: float) -> np.ndarray:
    return np.diag([k, k, 1.0])


def _aplicar(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.asarray(pts, np.float64).reshape(-1, 1, 2), H).reshape(-1, 2)


def cargar_referencia(ruta_plantilla: str | Path, imagen_referencia: str) -> np.ndarray:
    """Lee la imagen en blanco (gris) que está junto al JSON de la plantilla."""
    ruta = Path(ruta_plantilla).parent / imagen_referencia
    try:
        datos = np.fromfile(ruta, np.uint8)  # np.fromfile: rutas con tildes en Windows
    except OSError as e:
        raise RegistroInvalido(f"No se pudo leer la imagen de referencia {ruta}: {e}") from e
    img = cv2.imdecode(datos, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RegistroInvalido(f"La imagen de referencia {ruta} no se puede decodificar.")
    return img


# --- ORB + RANSAC ----------------------------------------------------------------------------


def _orb(gris: np.ndarray, k: float):
    chica = cv2.resize(gris, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    chica = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(chica)
    orb = cv2.ORB_create(nfeatures=_NFEATURES, fastThreshold=10, edgeThreshold=15)
    return orb.detectAndCompute(chica, None)


def _bits(des: np.ndarray) -> np.ndarray:
    return np.unpackbits(des, axis=1).astype(np.float32)


def _coincidencias_locales(kp_h, des_h, kp_r, des_r, radio: float):
    """Para cada punto de la hoja, su mejor descriptor de la referencia *entre los que están a
    menos de `radio` px*, con prueba de razón de Lowe solo contra ese vecindario. La hoja llega
    casi alineada: comparar contra toda la página haría fallar la prueba en filas repetidas."""
    a, b = _bits(des_h), _bits(des_r)
    nbits = a.shape[1]
    ph = np.array([p.pt for p in kp_h], np.float32)
    pr = np.array([p.pt for p in kp_r], np.float32)
    src, dst = [], []
    for i0 in range(0, len(a), 1000):
        sl = slice(i0, i0 + 1000)
        # distancia de Hamming = nbits - coincidencias de bit (unos y ceros)
        dist = nbits - (a[sl] @ b.T + (1 - a[sl]) @ (1 - b).T)
        lejos = np.linalg.norm(ph[sl, None, :] - pr[None, :, :], axis=2) > radio
        dist[lejos] = np.inf
        orden = np.argpartition(dist, 1, axis=1)[:, :2]
        d2 = np.take_along_axis(dist, orden, axis=1)
        for fila, (j, d) in enumerate(zip(orden, d2, strict=True)):
            m, n = (0, 1) if d[0] <= d[1] else (1, 0)
            if np.isfinite(d[m]) and (not np.isfinite(d[n]) or d[m] < _RAZON_LOWE * d[n]):
                src.append(ph[i0 + fila])
                dst.append(pr[j[m]])
    return np.array(src, np.float32).reshape(-1, 2), np.array(dst, np.float32).reshape(-1, 2)


def _cobertura(pts: np.ndarray, w: float, h: float) -> float:
    """Fracción de la hoja que cubre el casco convexo de los inliers (riesgo de extrapolar)."""
    if len(pts) < 3:
        return 0.0
    return float(cv2.contourArea(cv2.convexHull(pts.astype(np.float32))) / (w * h))


def _homografia_orb(hoja: np.ndarray, referencia: np.ndarray):
    """H (px de `hoja` -> px de `referencia`) y métricas, o (None, métricas con ceros)."""
    h, w = referencia.shape
    k = min(1.0, _LADO_ORB / max(h, w))
    kp_r, des_r = _orb(referencia, k)
    kp_h, des_h = _orb(hoja, k)
    vacio = {"coincidencias": 0, "inliers": 0, "error": np.inf, "cobertura": 0.0}
    if des_r is None or des_h is None or len(kp_r) < 8 or len(kp_h) < 8:
        return None, vacio

    src, dst = _coincidencias_locales(kp_h, des_h, kp_r, des_r, _RADIO_BUSQUEDA * max(h, w) * k)
    vacio["coincidencias"] = len(src)
    if len(src) < 8:
        return None, vacio

    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, _UMBRAL_RANSAC_PX, maxIters=5000)
    if H is None or mask is None:
        return None, vacio
    dentro = mask.ravel().astype(bool)
    n_in = int(dentro.sum())
    if n_in < 4:
        return None, vacio
    # Error de reproyección en px de plantilla (no en px reducidos).
    res = np.linalg.norm(_aplicar(H, src[dentro]) - dst[dentro], axis=1) / k
    # H está en px reducidos de ambas imágenes: pasarla a px completos de la hoja y la referencia.
    H_full = np.linalg.inv(_escala(k)) @ H @ _escala(k)
    return H_full, {
        "coincidencias": len(src),
        "inliers": n_in,
        "error": float(np.median(res)),
        "cobertura": _cobertura(dst[dentro] / k, w, h),
    }


# --- ajuste fino con las líneas de la tabla -----------------------------------------------------


def _mascara_lineas(gris: np.ndarray) -> np.ndarray:
    """Líneas largas, horizontales y verticales, de una hoja (float32 0..1, desenfocada)."""
    h, w = gris.shape
    fondo = cv2.GaussianBlur(gris, (0, 0), max(h, w) / 40)
    tinta = cv2.subtract(fondo, gris)  # oscuro sobre claro, sin iluminación
    tinta = cv2.threshold(tinta, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    largo = max(9, int(_LARGO_LINEA * w))
    horiz = cv2.morphologyEx(
        tinta, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (largo, 1))
    )
    vert = cv2.morphologyEx(
        tinta, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, largo))
    )
    lineas = cv2.max(horiz, vert).astype(np.float32) / 255
    return cv2.GaussianBlur(lineas, (0, 0), max(1.5, w / 400))


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 0 else 0.0


def _ajuste_lineas(registrada: np.ndarray, referencia: np.ndarray):
    """(W, correlación_final, aplicado): W lleva coords de plantilla -> coords de `registrada`
    (convención de ECC) y corrige el desplazamiento residual; identidad si no mejora."""
    h, w = referencia.shape
    k = min(1.0, _LADO_ECC / max(h, w))
    chica = lambda g: cv2.resize(g, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    m_ref, m_reg = _mascara_lineas(chica(referencia)), _mascara_lineas(chica(registrada))
    antes = _ncc(m_ref, m_reg)
    if m_ref.max() <= 0 or m_reg.max() <= 0:
        return np.eye(3), antes, False
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        criterio = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-6)
        _, warp = cv2.findTransformECC(m_ref, m_reg, warp, cv2.MOTION_AFFINE, criterio, None, 5)
    except cv2.error:
        return np.eye(3), antes, False
    W_chica = np.vstack([warp, [0, 0, 1]]).astype(np.float64)
    # Correlación tras aplicar W (m_reg muestreada en W·x) para decidir si se acepta.
    ajustada = cv2.warpAffine(
        m_reg, warp, (m_ref.shape[1], m_ref.shape[0]), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    )
    despues = _ncc(m_ref, ajustada)
    desplazamiento = np.abs(
        _aplicar(W_chica, [[0, 0], [w * k, 0], [w * k, h * k], [0, h * k]])
        - [[0, 0], [w * k, 0], [w * k, h * k], [0, h * k]]
    ).max()
    if despues <= antes or desplazamiento > _SHIFT_ECC_MAX * max(h, w) * k:
        return np.eye(3), antes, False
    W = np.linalg.inv(_escala(k)) @ W_chica @ _escala(k)
    return W, despues, True


# --- API ---------------------------------------------------------------------------------------


def _evaluar(m: dict, correlacion: float, umbrales: UmbralesRegistro) -> bool:
    return (
        m["inliers"] >= umbrales.inliers_min
        and m["inliers"] / max(m["coincidencias"], 1) >= umbrales.proporcion_inliers_min
        and m["error"] <= umbrales.error_reproyeccion_max
        and m["cobertura"] >= umbrales.cobertura_min
        and correlacion >= umbrales.correlacion_lineas_min
    )


def _intento(rect_gris, referencia, umbrales):
    """Registra una hoja enderezada contra la referencia: (H, métricas) de ORB + RANSAC."""
    H, m = _homografia_orb(rect_gris, referencia)
    m["proporcion"] = m["inliers"] / max(m["coincidencias"], 1)
    return H, m


def registrar(
    foto: np.ndarray,
    referencia: np.ndarray,
    *,
    umbrales: UmbralesRegistro | None = None,
) -> Registro:
    """Lleva `foto` (BGR) al sistema de coordenadas de `referencia` (gris, tamaño de plantilla).

    No lanza por un mal registro: devuelve `Registro` con la bandera `registro_dudoso`. Lanza
    `HojaNoEncontrada` si no se ve la hoja y `RegistroInvalido` si la referencia no sirve.
    """
    umbrales = umbrales or UmbralesRegistro()
    referencia = _gris(referencia)
    h, w = referencia.shape
    if h < 200 or w < 200 or referencia.std() < 1:
        raise RegistroInvalido("La imagen de referencia de la plantilla está vacía o es muy chica.")
    hoja = detectar_hoja(foto, proporcion=w / h)
    destino = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    Hr = cv2.getPerspectiveTransform(hoja.esquinas.astype(np.float32), destino).astype(np.float64)
    rect = cv2.warpPerspective(_gris(foto), Hr, (w, h), flags=cv2.INTER_AREA)

    # Giro: se prueba 0° y, si no sale bien, 180° (el contorno no los distingue).
    giro_180 = np.array([[-1, 0, w], [0, -1, h], [0, 0, 1]], np.float64)
    mejor = None
    for giro, G in ((0, np.eye(3)), (180, giro_180)):
        rect_g = rect if giro == 0 else cv2.rotate(rect, cv2.ROTATE_180)
        H0, m = _intento(rect_g, referencia, umbrales)
        if H0 is not None:
            candidato = (m["inliers"], giro, G, H0, m)
            if mejor is None or candidato[0] > mejor[0]:
                mejor = candidato
        if (
            mejor is not None
            and mejor[4]["inliers"] >= umbrales.inliers_min
            and (mejor[4]["proporcion"] >= umbrales.proporcion_inliers_min)
        ):
            break

    if mejor is None:  # ni una homografía: página no registrable (p. ej. hoja en blanco)
        m = {"coincidencias": 0, "inliers": 0, "error": np.inf, "cobertura": 0.0, "proporcion": 0.0}
        giro, H_total = 0, Hr
        correlacion, ajustado = 0.0, False
    else:
        _, giro, G, H0, m = mejor
        H_total = H0 @ G @ Hr
        previa = cv2.warpPerspective(_gris(foto), H_total, (w, h), flags=cv2.INTER_LINEAR)
        W, correlacion, ajustado = _ajuste_lineas(previa, referencia)
        if ajustado:
            H_total = np.linalg.inv(W) @ H_total

    imagen = cv2.warpPerspective(
        foto if foto.ndim == 3 else cv2.cvtColor(foto, cv2.COLOR_GRAY2BGR),
        H_total,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    ok = mejor is not None and _evaluar(m, correlacion, umbrales)
    return Registro(
        homografia=H_total,
        imagen=imagen,
        metodo_hoja=hoja.metodo,
        giro=giro,
        coincidencias=m["coincidencias"],
        inliers=m["inliers"],
        proporcion_inliers=m["proporcion"],
        error_reproyeccion=m["error"],
        cobertura=m["cobertura"],
        correlacion_lineas=correlacion,
        ajuste_lineas=ajustado,
        banderas=() if ok else (BANDERA_REGISTRO_DUDOSO,),
    )
