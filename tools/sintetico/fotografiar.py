"""BS-R1: convierte una hoja llena en una «foto de celular» y la guarda como JPEG con EXIF.

`fotografiar` devuelve la foto en posición vertical (sin EXIF aplicado) y `meta` con la
homografía hoja -> foto, para que los tests de CO-R2/CO-R3 comparen contra la verdad.
`guardar_jpeg` almacena los píxeles girados y la etiqueta EXIF Orientation que los endereza.
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_EXIF_ORIENTACION = 0x0112
# orientación EXIF -> giro de los píxeles guardados (el lector aplica el inverso).
_GIRO_ALMACENADO = {
    1: None,
    3: Image.Transpose.ROTATE_180,
    6: Image.Transpose.ROTATE_90,
    8: Image.Transpose.ROTATE_270,
}
ORIENTACIONES = tuple(_GIRO_ALMACENADO)


def _suave(rng, ancho, alto, celdas, sigma):
    """Campo aleatorio de baja frecuencia, media 0, escalado a (alto, ancho)."""
    pequeno = rng.normal(0, sigma, (celdas[1], celdas[0])).astype(np.float32)
    return cv2.resize(pequeno, (ancho, alto), interpolation=cv2.INTER_CUBIC)


def _fondo(rng, ancho, alto):
    base = np.array(rng.uniform(50, 130, 3) * np.array([0.8, 0.9, 1.0]), np.float32)
    campo = _suave(rng, ancho, alto, (6, 8), 12) + _suave(rng, ancho, alto, (60, 80), 5)
    return np.clip(base[None, None, :] + campo[:, :, None], 0, 255)


def fotografiar(
    hoja: np.ndarray,
    rng: np.random.Generator,
    *,
    tamano: tuple[int, int] = (2400, 3200),
    relleno: tuple[float, float] = (0.80, 0.90),
    rotacion_max: float = 8.0,
    perspectiva_max: float = 0.035,
    desenfoque: tuple[float, float] = (0.4, 1.4),
    ruido: tuple[float, float] = (2.0, 6.0),
    sombra: tuple[float, float] = (0.05, 0.35),
) -> tuple[np.ndarray, dict]:
    W, H = tamano
    h, w = hoja.shape[:2]
    esc = float(rng.uniform(*relleno)) * min(W / w, H / h)
    sw, sh = int(w * esc), int(h * esc)
    hoja_s = cv2.resize(hoja, (sw, sh), interpolation=cv2.INTER_AREA)

    ang = np.deg2rad(rng.uniform(-rotacion_max, rotacion_max))
    rot = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    rect = np.array([[-sw, -sh], [sw, -sh], [sw, sh], [-sw, sh]], np.float64) / 2
    centro = np.array([W / 2, H / 2]) + rng.uniform(-0.02, 0.02, 2) * (W, H)
    jit = rng.uniform(-perspectiva_max, perspectiva_max, (4, 2)) * (W, H)
    quad = rect @ rot.T + centro + jit
    while (quad < 0.01 * np.array([W, H])).any() or (quad > 0.99 * np.array([W, H])).any():
        quad = (quad - [W / 2, H / 2]) * 0.97 + [W / 2, H / 2]  # no debe salirse del cuadro

    src = np.array([[0, 0], [sw, 0], [sw, sh], [0, sh]], np.float32)
    Hs = cv2.getPerspectiveTransform(src, quad.astype(np.float32))
    hom = Hs @ np.diag([sw / w, sh / h, 1.0])  # hoja (px de plantilla) -> foto

    papel = rng.uniform(0.93, 1.0, 3).astype(np.float32)
    warped = cv2.warpPerspective(hoja_s, Hs, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32)
    mask = cv2.warpPerspective(np.full((sh, sw), 255, np.uint8), Hs, (W, H))
    mask = mask.astype(np.float32)[:, :, None] / 255
    foto = _fondo(rng, W, H) * (1 - mask) + warped * papel * mask

    # Iluminación: degradé direccional + dominante de color.
    th = rng.uniform(0, 2 * np.pi)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xx * np.cos(th) + yy * np.sin(th)) / np.hypot(W, H)
    t = np.clip((t - rng.uniform(-0.1, 0.3)) / 0.5, 0, 1)
    fuerza = float(rng.uniform(*sombra))
    foto *= (1 - fuerza * t * t * (3 - 2 * t))[:, :, None]
    foto *= rng.uniform(0.95, 1.05, 3).astype(np.float32)

    sigma = float(rng.uniform(*desenfoque))
    foto = cv2.GaussianBlur(foto, (0, 0), sigma)
    sd_ruido = float(rng.uniform(*ruido))
    foto += rng.standard_normal((H, W, 3), dtype=np.float32) * sd_ruido

    meta = {
        "homografia": hom.tolist(),
        "esquinas": quad.tolist(),
        "tamano_foto": [W, H],
        "tamano_hoja": [w, h],
        "rotacion_grados": float(np.rad2deg(ang)),
        "desenfoque_sigma": sigma,
        "ruido_sd": sd_ruido,
        "sombra": fuerza,
    }
    return np.clip(foto, 0, 255).astype(np.uint8), meta


def guardar_jpeg(foto: np.ndarray, ruta: str | Path, *, calidad: int = 85, orientacion: int = 1):
    """Guarda `foto` (BGR vertical) con la orientación EXIF dada; un lector que la aplique
    recupera `foto`."""
    img = Image.fromarray(cv2.cvtColor(foto, cv2.COLOR_BGR2RGB))
    giro = _GIRO_ALMACENADO[orientacion]
    if giro is not None:
        img = img.transpose(giro)
    exif = Image.Exif()
    exif[_EXIF_ORIENTACION] = orientacion
    img.save(ruta, "JPEG", quality=calidad, exif=exif)
