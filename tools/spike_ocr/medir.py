"""Corre el spike: texto impreso sintético + línea 'manuscrita' (Hershey). Uso: ver README del plan."""

from __future__ import annotations

import statistics as st
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools.spike_ocr.pipeline import Lector

IMPRESO = [
    "Observaciones: el paciente mostró ansiedad ante la prueba",
    "Peña, Núñez, Ibáñez — año 2025, ¿cómo está? ¡Muy bien!",
    "Evaluación psicológica N° 0042 · Niño de 9 años",
    "Se observa dificultad para concentrarse y fatiga",
]
MANUSCRITO = [
    "Se muestra tranquilo y colaborador",
    "Nervioso al inicio, después se relajó",
    "No quiso responder la pregunta 7",
    "Niña muy atenta, año escolar 2025",
]
FUENTES = Path("modelos/fuentes")  # copiadas de C:\Windows\Fonts; fuera de git


def _dibujar(lineas, fuente, tam, tinta, ancho, alto_linea):
    im = Image.new("RGB", (ancho, alto_linea * len(lineas) + 40), "white")
    f = ImageFont.truetype(str(FUENTES / fuente), tam)
    d = ImageDraw.Draw(im)
    for i, t in enumerate(lineas):
        d.text((30, 20 + i * alto_linea), t, fill=tinta, font=f)
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def hoja_impresa(lineas):
    return _dibujar(lineas, "arial.ttf", 38, (20, 20, 20), 1600, 70)


def hoja_manuscrita(lineas, fuente):
    return _dibujar(lineas, fuente, 52, (30, 40, 140), 1600, 100)


def correr(nombre, img, esperado, lector):
    ts_det, ts_rec = [], []
    for _ in range(5):
        cajas, res, td, tr = lector.leer(img)
        ts_det.append(td)
        ts_rec.append(tr)
    print(f"\n== {nombre}: {len(cajas)} líneas detectadas (esperadas {len(esperado)})")
    for (txt, conf), esp in zip(res, esperado + [""] * len(res)):
        print(f"  conf {conf:.2f}  «{txt}»   [esperado: «{esp}»]")
    print(
        f"  detección {st.median(ts_det) * 1000:.0f} ms · reconocimiento {st.median(ts_rec) * 1000:.0f} ms"
        f" ({st.median(ts_rec) * 1000 / max(len(cajas), 1):.0f} ms/línea) · img {img.shape[1]}x{img.shape[0]}"
    )


if __name__ == "__main__":
    lector = Lector(hilos=4)
    print(f"carga de modelos + diccionario: {lector.t_carga:.2f} s")
    lector.leer(hoja_impresa(["calentamiento"]))
    correr("impreso (Arial)", hoja_impresa(IMPRESO), IMPRESO, lector)
    for f in ("inkfree.ttf", "segoepr.ttf", "segoesc.ttf"):
        correr(
            f"cursiva {f} (sustituto, NO manuscrito real)",
            hoja_manuscrita(MANUSCRITO, f),
            MANUSCRITO,
            lector,
        )
