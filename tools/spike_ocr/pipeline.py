"""Detección DB + reconocimiento CTC con onnxruntime CPU. Código de spike, sin pulir."""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODELOS = Path("modelos/pp-ocrv6")


def cargar_diccionario(ruta: Path) -> list[str]:
    """Lee `character_dict` del inference.yml sin PyYAML (cada ítem es `  - x`, quizá entrecomillado)."""
    import yaml  # solo para el spike; se ejecuta con `uv run --with pyyaml`

    d = yaml.safe_load(ruta.read_text(encoding="utf8"))
    return ["blank", *d["PostProcess"]["character_dict"], " "]


def sesion(ruta: Path, hilos: int = 4) -> ort.InferenceSession:
    op = ort.SessionOptions()
    op.intra_op_num_threads = hilos
    return ort.InferenceSession(str(ruta), op, providers=["CPUExecutionProvider"])


def detectar(s, img: np.ndarray, lado_max=960, thresh=0.2, box_thresh=0.45, unclip=1.4):
    h, w = img.shape[:2]
    esc = min(1.0, lado_max / max(h, w))
    nh, nw = max(32, round(h * esc / 32) * 32), max(32, round(w * esc / 32) * 32)
    x = cv2.resize(img, (nw, nh)).astype(np.float32) / 255.0
    x = (x[..., ::-1] - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]  # BGR→RGB
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    mapa = s.run(None, {"x": x})[0][0, 0]
    bw = (mapa > thresh).astype(np.uint8)
    cs, _ = cv2.findContours(bw, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cajas = []
    for c in cs:
        if len(c) < 4:
            continue
        rect = cv2.minAreaRect(c)
        if min(rect[1]) < 3:
            continue
        m = np.zeros_like(bw)
        cv2.drawContours(m, [c], -1, 1, -1)
        if float(mapa[m > 0].mean()) < box_thresh:
            continue
        (cx, cy), (rw, rh), ang = rect
        d = rw * rh * unclip / (2 * (rw + rh))
        rect = ((cx, cy), (rw + 2 * d, rh + 2 * d), ang)
        p = cv2.boxPoints(rect) * [w / nw, h / nh]
        cajas.append(p.astype(np.float32))
    return cajas


def recortar(img, p):
    p = _ordenar(p)
    ancho = int(max(np.linalg.norm(p[0] - p[1]), np.linalg.norm(p[2] - p[3])))
    alto = int(max(np.linalg.norm(p[0] - p[3]), np.linalg.norm(p[1] - p[2])))
    dst = np.float32([[0, 0], [ancho, 0], [ancho, alto], [0, alto]])
    r = cv2.warpPerspective(
        img,
        cv2.getPerspectiveTransform(p, dst),
        (ancho, alto),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if r.shape[0] / max(r.shape[1], 1) >= 1.5:
        r = np.rot90(r)
    return r


def _ordenar(p):
    s, d = p.sum(1), np.diff(p, axis=1)[:, 0]
    return np.float32([p[s.argmin()], p[d.argmin()], p[s.argmax()], p[d.argmax()]])


def reconocer(s, dic, recortes: list[np.ndarray]):
    out = []
    for r in recortes:
        h, w = r.shape[:2]
        nw = min(3200, max(16, int(np.ceil(48 * w / h))))
        x = cv2.resize(r, (nw, 48)).astype(np.float32) / 255.0
        x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None].astype(np.float32)
        p = s.run(None, {"x": x})[0][0]
        idx, conf = p.argmax(1), p.max(1)
        txt, cs, prev = [], [], 0
        for i, c in zip(idx, conf):
            if i != 0 and i != prev:
                txt.append(dic[i])
                cs.append(float(c))
            prev = i
        out.append(("".join(txt), float(np.mean(cs)) if cs else 0.0))
    return out


class Lector:
    def __init__(self, hilos=4):
        t = time.perf_counter()
        self.det = sesion(MODELOS / "det/inference.onnx", hilos)
        self.rec = sesion(MODELOS / "rec/inference.onnx", hilos)
        self.dic = cargar_diccionario(MODELOS / "rec/inference.yml")
        self.t_carga = time.perf_counter() - t

    def leer(self, img):
        t0 = time.perf_counter()
        cajas = detectar(self.det, img)
        t1 = time.perf_counter()
        cajas.sort(key=lambda p: (round(p[:, 1].mean() / 20), p[:, 0].mean()))
        res = reconocer(self.rec, self.dic, [recortar(img, p) for p in cajas])
        t2 = time.perf_counter()
        return cajas, res, t1 - t0, t2 - t1
