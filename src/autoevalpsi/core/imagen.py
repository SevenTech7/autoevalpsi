"""CO-R1: carga de la foto (con EXIF) y control de calidad previo al registro.

`cargar_imagen(bytes)` devuelve un arreglo BGR uint8 ya enderezado según la etiqueta EXIF
Orientation (CO-01: OpenCV la ignora y una foto vertical del celular llegaría acostada).
Solo JPEG y PNG; HEIC/HEIF (iPhone) se rechaza con un mensaje que dice qué hacer.

`evaluar_calidad(imagen)` mide nitidez, brillo y altas luces recortadas sobre una versión
reducida y devuelve un `InformeCalidad`; no lanza: dice qué falla y por qué, para que la
interfaz pida otra foto antes de gastar tiempo en el registro. Los umbrales viven en
`UmbralesCalidad` (configurables; se ajustan con fotos reales en CO-R8 y el piloto).
"""

import io
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

_LADO_ANALISIS = 1000  # px del lado largo para medir; hace la nitidez independiente del tamaño
_MAGIA_PNG = b"\x89PNG\r\n\x1a\n"
_MARCAS_HEIF = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif")


class ImagenInvalida(ValueError):
    """La entrada no se puede usar como foto; el mensaje está pensado para mostrarse."""


def _es_heif(datos: bytes) -> bool:
    return datos[4:8] == b"ftyp" and datos[8:12] in _MARCAS_HEIF


def cargar_imagen(datos: bytes) -> np.ndarray:
    """Decodifica JPEG/PNG, aplica la orientación EXIF y devuelve BGR uint8 (alto, ancho, 3)."""
    if not datos:
        raise ImagenInvalida("El archivo está vacío.")
    if _es_heif(datos):
        raise ImagenInvalida(
            "Formato HEIC/HEIF no admitido. Configura la cámara para guardar en JPEG "
            "(o comparte la foto como JPEG) e inténtalo de nuevo."
        )
    if not (datos[:3] == b"\xff\xd8\xff" or datos[:8] == _MAGIA_PNG):
        raise ImagenInvalida("Formato no admitido: solo se aceptan fotos JPEG o PNG.")
    try:
        with Image.open(io.BytesIO(datos)) as img:
            img = ImageOps.exif_transpose(img)
            rgb = np.asarray(img.convert("RGB"))
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as e:
        raise ImagenInvalida(f"No se pudo leer la imagen (¿archivo dañado?): {e}") from e
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


@dataclass(frozen=True)
class UmbralesCalidad:
    """Umbrales por defecto, calibrados con el lote sintético (ver tests/core/test_imagen.py)."""

    nitidez_min: float = 150.0  # varianza del Laplaciano de la imagen reducida
    brillo_min: float = 70.0  # media de gris (0-255)
    brillo_max: float = 215.0
    luces_max: float = 0.20  # fracción de píxeles ≥ `nivel_luz` (quemados)
    nivel_luz: int = 250
    lado_min: int = 1000  # px del lado largo; por debajo no se lee una casilla


@dataclass(frozen=True)
class InformeCalidad:
    nitidez: float
    brillo: float
    luces: float
    lado_largo: int
    problemas: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problemas


def evaluar_calidad(imagen: np.ndarray, umbrales: UmbralesCalidad | None = None) -> InformeCalidad:
    u = umbrales or UmbralesCalidad()
    if imagen.ndim == 3:
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    else:
        gris = imagen
    h, w = gris.shape
    lado = max(h, w)
    if lado > _LADO_ANALISIS:
        k = _LADO_ANALISIS / lado
        gris = cv2.resize(gris, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA)

    nitidez = float(cv2.Laplacian(gris, cv2.CV_64F).var())
    brillo = float(gris.mean())
    luces = float((gris >= u.nivel_luz).mean())

    problemas = []
    if lado < u.lado_min:
        problemas.append(f"Resolución baja ({lado} px): acércate o usa la cámara principal.")
    if nitidez < u.nitidez_min:
        problemas.append("La foto está desenfocada: sostén firme el celular y vuelve a enfocar.")
    if brillo < u.brillo_min:
        problemas.append("La foto está muy oscura: busca más luz.")
    elif brillo > u.brillo_max:
        problemas.append("La foto está muy clara: evita el flash directo.")
    if luces > u.luces_max:
        problemas.append("Hay zonas quemadas por reflejo o flash: cambia el ángulo.")
    return InformeCalidad(nitidez, brillo, luces, lado, problemas)
