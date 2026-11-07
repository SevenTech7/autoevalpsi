"""BS-R1: formulario propio «demo-5opciones» (sin derechos) y su plantilla JSON.

Se dibuja con OpenCV a 300 dpi en A4 y en Carta. La plantilla que emite carga con el esquema
real (`autoevalpsi.core.plantilla`). Solo ASCII: las fuentes Hershey de OpenCV no tienen tildes.

Uso:  python -m tools.sintetico.formulario [--salida plantillas_demo]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

FORMATOS = {"a4": (2480, 3508), "carta": (2550, 3300)}
OPCIONES = ["Nunca", "Casi nunca", "A veces", "Casi siempre", "Siempre"]
N_FILAS = 12
MARGEN = 150
X_OPCIONES = 1000
ANCHO_COL = 130
Y_ENCABEZADO = 470
Y_FILAS = 620
ALTO_FILA = 150
_NEGRO = 0
_FUENTE = cv2.FONT_HERSHEY_SIMPLEX


def _texto(img, txt, origen, escala, grosor=2):
    cv2.putText(img, txt, origen, _FUENTE, escala, _NEGRO, grosor, cv2.LINE_AA)


def _geometria(formato: str) -> dict:
    ancho, alto = FORMATOS[formato]
    return {
        "tamano_px": [ancho, alto],
        "cabecera": [
            {"campo": "paciente", "caja": [450, 300, 1500, 390], "tipo": "texto"},
            {"campo": "fecha", "caja": [1750, 300, ancho - MARGEN, 390], "tipo": "texto"},
        ],
        "columnas_x": [
            [X_OPCIONES + ANCHO_COL * i, X_OPCIONES + ANCHO_COL * (i + 1)]
            for i in range(len(OPCIONES))
        ],
        "observacion_x": [X_OPCIONES + ANCHO_COL * len(OPCIONES), ancho - MARGEN],
        "filas": [
            {
                "item": i + 1,
                "texto": f"Descripcion del item {i + 1}",
                "y": [Y_FILAS + ALTO_FILA * i, Y_FILAS + ALTO_FILA * (i + 1)],
            }
            for i in range(N_FILAS)
        ],
    }


def plantilla_dict(formato: str) -> dict:
    g = _geometria(formato)
    id_ = f"demo-5opciones-{formato}"
    return {
        "esquema_version": 1,
        "id": id_,
        "nombre": f"Demo 5 opciones ({'A4' if formato == 'a4' else 'Carta'})",
        "version": 1,
        "paginas": [
            {
                "imagen_referencia": f"{id_}.png",
                "tamano_px": g["tamano_px"],
                "cabecera": g["cabecera"],
                "tablas": [
                    {
                        "opciones": OPCIONES,
                        "columnas_x": g["columnas_x"],
                        "observacion_x": g["observacion_x"],
                        "filas": g["filas"],
                    }
                ],
            }
        ],
    }


def dibujar(formato: str) -> np.ndarray:
    """Imagen en blanco del formulario (gris uint8)."""
    g = _geometria(formato)
    ancho, alto = g["tamano_px"]
    img = np.full((alto, ancho), 255, np.uint8)
    x_izq, x_der = MARGEN, ancho - MARGEN
    y_fin = Y_FILAS + ALTO_FILA * N_FILAS

    _texto(img, "FORMULARIO DEMO - 5 OPCIONES", (MARGEN, 220), 2.2, 4)
    _texto(img, "Paciente:", (MARGEN, 360), 1.6)
    _texto(img, "Fecha:", (1560, 360), 1.6)
    for c in g["cabecera"]:
        x0, y0, x1, y1 = c["caja"]
        cv2.rectangle(img, (x0, y0), (x1, y1), _NEGRO, 2)

    # Retícula de la tabla.
    cv2.rectangle(img, (x_izq, Y_ENCABEZADO), (x_der, y_fin), _NEGRO, 5)
    cv2.line(img, (x_izq, Y_FILAS), (x_der, Y_FILAS), _NEGRO, 4)
    for f in g["filas"][:-1]:
        cv2.line(img, (x_izq, f["y"][1]), (x_der, f["y"][1]), _NEGRO, 3)
    for x in [X_OPCIONES, *(c[1] for c in g["columnas_x"])]:
        cv2.line(img, (x, Y_ENCABEZADO), (x, y_fin), _NEGRO, 3)

    # Encabezados de columna (dos líneas si el nombre tiene espacio).
    for nombre, (xa, _xb) in zip(OPCIONES, g["columnas_x"], strict=True):
        palabras = nombre.split(" ")
        for k, p in enumerate(palabras):
            (w, _), _ = cv2.getTextSize(p, _FUENTE, 0.6, 1)
            y = Y_ENCABEZADO + 90 + (k - (len(palabras) - 1) / 2) * 40
            _texto(img, p, (xa + (ANCHO_COL - w) // 2, int(y)), 0.6, 1)
    _texto(img, "Item", (x_izq + 20, Y_ENCABEZADO + 95), 1.0)
    _texto(img, "Observacion", (g["observacion_x"][0] + 20, Y_ENCABEZADO + 95), 1.0)

    for f in g["filas"]:
        yc = (f["y"][0] + f["y"][1]) // 2
        _texto(img, f"{f['item']}. {f['texto']}", (x_izq + 20, yc + 12), 0.9, 2)

    _texto(
        img, "Formulario sintetico propio, sin derechos - AutoEvalPsi", (MARGEN, alto - 120), 0.9
    )
    return img


def construir(formato: str) -> tuple[np.ndarray, dict]:
    return dibujar(formato), plantilla_dict(formato)


def escribir(destino: str | Path, formatos=tuple(FORMATOS)) -> list[Path]:
    """Escribe `<id>.png` y `<id>.json` por formato; devuelve las rutas creadas."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for formato in formatos:
        img, plantilla = construir(formato)
        id_ = plantilla["id"]
        ok, buf = cv2.imencode(".png", img, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise RuntimeError(f"no se pudo codificar {id_}.png")
        png = destino / f"{id_}.png"
        png.write_bytes(buf.tobytes())
        js = destino / f"{id_}.json"
        js.write_text(json.dumps(plantilla, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rutas += [png, js]
    return rutas


def main() -> None:
    p = argparse.ArgumentParser(description="Genera el formulario sintético demo-5opciones.")
    p.add_argument("--salida", default="plantillas_demo")
    for r in escribir(p.parse_args().salida):
        print(r)


if __name__ == "__main__":
    main()
