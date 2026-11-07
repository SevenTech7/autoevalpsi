"""OC-R1: lector OCR con PP-OCRv6 medium en ONNX (detección DB + reconocimiento CTC).

Sin PaddlePaddle: solo onnxruntime CPU, OpenCV y numpy. Los modelos viven en `modelos/pp-ocrv6/`
(fuera de git, OC-04) y los deja `tools/descargar_modelos.py` con su hash verificado:

    modelos/pp-ocrv6/det/inference.onnx
    modelos/pp-ocrv6/rec/inference.onnx
    modelos/pp-ocrv6/rec/diccionario.txt    (un carácter por línea; el blanco CTC y el espacio se
                                             agregan aquí)

Las sesiones se crean una sola vez y perezosamente, en la primera lectura (OC-06), con un número
fijo de hilos para no quitarle todos los núcleos al servidor y a la interfaz.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.ocr.lector import Caja, Linea, ordenar_lectura

MODELOS_POR_DEFECTO = Path("modelos/pp-ocrv6")

# Parámetros del inference.yml de PP-OCRv6 medium (verificados en OC-R0).
DET_LADO_MAX = 960
DET_UMBRAL = 0.2
DET_UMBRAL_CAJA = 0.45
DET_UNCLIP = 1.4
DET_LADO_MIN_CAJA = 3
REC_ALTO = 48
REC_ANCHO_MAX = 3200
REC_ANCHO_MIN = 16


class ModelosNoEncontrados(FileNotFoundError):
    """Faltan los archivos del modelo; se bajan con `tools/descargar_modelos.py`."""


def cargar_diccionario(ruta: Path) -> list[str]:
    """Clases del reconocedor: blanco CTC (índice 0), los caracteres del archivo y el espacio."""
    # `split("\n")` y no `splitlines()`: este último parte también en U+2028, U+0085, etc.
    caracteres = ruta.read_text(encoding="utf8").split("\n")
    if caracteres and caracteres[-1] == "":
        caracteres.pop()
    return ["", *caracteres, " "]


def _a_bgr(imagen: np.ndarray) -> np.ndarray:
    if imagen is None or imagen.ndim not in (2, 3) or imagen.size == 0:
        raise ValueError("imagen vacía o con forma no válida para el OCR")
    if imagen.dtype != np.uint8:
        raise ValueError(f"el OCR espera uint8, no {imagen.dtype}")
    if imagen.ndim == 2:
        return cv2.cvtColor(imagen, cv2.COLOR_GRAY2BGR)
    if imagen.shape[2] == 4:
        return cv2.cvtColor(imagen, cv2.COLOR_BGRA2BGR)
    if imagen.shape[2] != 3:
        raise ValueError("el OCR espera 1, 3 o 4 canales")
    return imagen


def _ordenar_esquinas(p: np.ndarray) -> np.ndarray:
    s, d = p.sum(1), np.diff(p, axis=1)[:, 0]
    return np.float32([p[s.argmin()], p[d.argmin()], p[s.argmax()], p[d.argmax()]])


def _recortar(img: np.ndarray, poligono: np.ndarray) -> np.ndarray:
    """Endereza el recorte de una caja (puede venir inclinada); lo gira si salió vertical."""
    p = _ordenar_esquinas(poligono)
    ancho = max(1, int(max(np.linalg.norm(p[0] - p[1]), np.linalg.norm(p[2] - p[3]))))
    alto = max(1, int(max(np.linalg.norm(p[0] - p[3]), np.linalg.norm(p[1] - p[2]))))
    destino = np.float32([[0, 0], [ancho, 0], [ancho, alto], [0, alto]])
    r = cv2.warpPerspective(
        img,
        cv2.getPerspectiveTransform(p, destino),
        (ancho, alto),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if r.shape[0] / max(r.shape[1], 1) >= 1.5:
        r = np.ascontiguousarray(np.rot90(r))
    return r


def decodificar_ctc(probabilidades: np.ndarray, clases: list[str]) -> tuple[str, float]:
    """CTC voraz: argmax por paso, colapsa repetidos, quita el blanco. Confianza = media de los
    pasos que aportan un carácter (0 si no hay texto)."""
    indices = probabilidades.argmax(1)
    confs = probabilidades.max(1)
    texto: list[str] = []
    cs: list[float] = []
    previo = 0
    for i, c in zip(indices, confs, strict=True):
        if i != 0 and i != previo:
            texto.append(clases[i])
            cs.append(float(c))
        previo = i
    return "".join(texto), float(np.mean(cs)) if cs else 0.0


class LectorONNX:
    """Implementa `Lector` con los modelos medium. Seguro entre hilos (una lectura a la vez)."""

    def __init__(self, carpeta: Path | str = MODELOS_POR_DEFECTO, hilos: int = 4):
        self.carpeta = Path(carpeta)
        self.hilos = hilos
        self._det = None
        self._rec = None
        self._clases: list[str] = []
        self._candado = threading.Lock()

    def _cargar(self) -> None:
        if self._det is not None:
            return
        rutas = {
            "det": self.carpeta / "det" / "inference.onnx",
            "rec": self.carpeta / "rec" / "inference.onnx",
            "dic": self.carpeta / "rec" / "diccionario.txt",
        }
        faltan = [str(r) for r in rutas.values() if not r.is_file()]
        if faltan:
            raise ModelosNoEncontrados(
                "faltan archivos del modelo OCR: "
                + ", ".join(faltan)
                + ". Bajarlos con `python -m tools.descargar_modelos`."
            )
        import onnxruntime as ort  # perezoso: el extra `ocr` puede no estar instalado

        def sesion(ruta: Path):
            op = ort.SessionOptions()
            op.intra_op_num_threads = self.hilos
            return ort.InferenceSession(str(ruta), op, providers=["CPUExecutionProvider"])

        self._clases = cargar_diccionario(rutas["dic"])
        self._rec = sesion(rutas["rec"])
        self._det = sesion(rutas["det"])

    # --- detección -------------------------------------------------------------------------

    def _detectar(self, img: np.ndarray) -> list[np.ndarray]:
        h, w = img.shape[:2]
        esc = min(1.0, DET_LADO_MAX / max(h, w))
        nh, nw = max(32, round(h * esc / 32) * 32), max(32, round(w * esc / 32) * 32)
        x = cv2.resize(img, (nw, nh)).astype(np.float32) / 255.0
        x = (x[..., ::-1] - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]  # BGR → RGB
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        mapa = self._det.run(None, {"x": x})[0][0, 0]
        binaria = (mapa > DET_UMBRAL).astype(np.uint8)
        contornos, _ = cv2.findContours(binaria, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cajas = []
        for c in contornos:
            if len(c) < 4:
                continue
            rect = cv2.minAreaRect(c)
            if min(rect[1]) < DET_LADO_MIN_CAJA:
                continue
            relleno = np.zeros_like(binaria)
            cv2.drawContours(relleno, [c], -1, 1, -1)
            if float(mapa[relleno > 0].mean()) < DET_UMBRAL_CAJA:
                continue
            (cx, cy), (rw, rh), ang = rect
            d = rw * rh * DET_UNCLIP / (2 * (rw + rh))
            ampliada = ((cx, cy), (rw + 2 * d, rh + 2 * d), ang)
            cajas.append((cv2.boxPoints(ampliada) * [w / nw, h / nh]).astype(np.float32))
        return cajas

    # --- reconocimiento --------------------------------------------------------------------

    def _reconocer(self, recorte: np.ndarray) -> tuple[str, float]:
        h, w = recorte.shape[:2]
        ancho = min(REC_ANCHO_MAX, max(REC_ANCHO_MIN, int(np.ceil(REC_ALTO * w / max(h, 1)))))
        x = cv2.resize(recorte, (ancho, REC_ALTO)).astype(np.float32) / 255.0
        x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None].astype(np.float32)
        salida = self._rec.run(None, {"x": x})[0][0]
        return decodificar_ctc(salida, self._clases)

    # --- API pública -----------------------------------------------------------------------

    def leer(self, imagen: np.ndarray) -> list[Linea]:
        img = _a_bgr(imagen)
        alto, ancho = img.shape[:2]
        with self._candado:
            self._cargar()
            lineas = []
            for poligono in self._detectar(img):
                texto, confianza = self._reconocer(_recortar(img, poligono))
                if not texto:
                    continue
                x0, y0 = np.floor(poligono.min(0)).astype(int)
                x1, y1 = np.ceil(poligono.max(0)).astype(int)
                caja = Caja(
                    int(max(x0, 0)), int(max(y0, 0)), int(min(x1, ancho)), int(min(y1, alto))
                )
                lineas.append(Linea(texto, confianza, caja))
        return ordenar_lectura(lineas)
