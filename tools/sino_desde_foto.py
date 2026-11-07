"""FS-R0 (spike): borrador de plantilla Sí/No a partir de la foto de un formulario lleno.

Lee la foto con el OCR (con la posición de cada carácter), encuentra cada «Si ( ) No ( )», le pone
su texto y su sección, y ubica el puntaje manuscrito de cada sección (la línea «P.E.E.»).
Escribe un borrador `.json` y una imagen de revisión con todo dibujado.

Uso (dentro de Docker):
    docker compose run --rm dev python -m tools.sino_desde_foto foto.jpg salida/borrador
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.ocr.onnx import LectorONNX, _recortar

ANCHO_PAREN = 24  # px de la foto; solo se usa si el OCR no vio algún paréntesis
MARGEN_Y = 18  # un texto «a la izquierda» debe estar a menos de esto en vertical
# Las letras sueltas del margen (R-A-X-I-A-S...) a veces se pegan al encabezado: «E 5.5 Lenguaje...»
SECCION = re.compile(r"^\s*(?:[A-Za-z*]\s*)?(\d{1,2}\.\d{1,2})\s+(.+)")


@dataclass
class LineaCar:
    texto: str
    x0: int
    y0: int
    x1: int
    y1: int
    car: list[tuple[str, int]]  # (carácter, x en la foto)

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def leer_con_posiciones(img: np.ndarray, lector: LectorONNX) -> list[LineaCar]:
    lector._cargar()
    salida = []
    for poligono in lector._detectar(img):
        rec = _recortar(img, poligono)
        h, w = rec.shape[:2]
        ancho = min(3200, max(16, int(np.ceil(48 * w / max(h, 1)))))
        x = cv2.resize(rec, (ancho, 48)).astype(np.float32) / 255.0
        x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None].astype(np.float32)
        prob = lector._rec.run(None, {"x": x})[0][0]
        pasos = prob.shape[0]
        x0, y0 = np.floor(poligono.min(0)).astype(int)
        x1, y1 = np.ceil(poligono.max(0)).astype(int)
        car, previo = [], 0
        for t, i in enumerate(prob.argmax(1)):
            if i != 0 and i != previo:
                car.append((lector._clases[i], int(x0 + (x1 - x0) * (t + 0.5) / pasos)))
            previo = i
        if car:
            salida.append(
                LineaCar("".join(c for c, _ in car), int(x0), int(y0), int(x1), int(y1), car)
            )
    return sorted(salida, key=lambda ln: (round(ln.cy / 12), ln.x0))


def _palabras(ln: LineaCar, que: str) -> list[int]:
    """Índices (en `ln.car`) donde empieza la palabra `que` («Si» o «No»), ignorando mayúsculas."""
    s = ln.texto
    return [m.start() for m in re.finditer(que, s, flags=re.IGNORECASE) if _es_palabra(s, m, que)]


def _es_palabra(s: str, m: re.Match[str], que: str) -> bool:
    antes = s[m.start() - 1] if m.start() else " "
    despues = s[m.end()] if m.end() < len(s) else " "
    return not antes.isalpha() and not despues.isalpha()


def _caja_opcion(ln: LineaCar, fin_palabra: int, limite_x: int, y: tuple[int, int]) -> list[int]:
    """Caja del paréntesis que sigue a la palabra que termina en `fin_palabra` (índice de `car`)."""
    xs = [x for c, x in ln.car[fin_palabra:] if c in "()" and x < limite_x]
    x_palabra = ln.car[fin_palabra - 1][1]
    if len(xs) >= 2:
        x0, x1 = xs[0] - 4, xs[1] + 4
    elif len(xs) == 1:
        x0, x1 = xs[0] - 4, xs[0] + ANCHO_PAREN
    else:
        x0, x1 = x_palabra + 8, x_palabra + 8 + ANCHO_PAREN
    return [int(x0), int(y[0]), int(x1), int(y[1])]


def encontrar_grupos(ln: LineaCar) -> list[dict]:
    """Cada «Si ( ) No ( )» de la línea, con la posición de sus dos paréntesis."""
    sis, nos = _palabras(ln, "Si"), _palabras(ln, "No")
    grupos = []
    for k, i_si in enumerate(sis):
        i_no = next((n for n in nos if n > i_si), None)
        if i_no is None:
            continue
        siguiente = sis[k + 1] if k + 1 < len(sis) else len(ln.car)
        if i_no >= siguiente:  # el «No» es de otro grupo: éste está incompleto
            continue
        y = (ln.y0, ln.y1)
        x_no = ln.car[i_no][1]
        x_sig = ln.car[siguiente][1] if siguiente < len(ln.car) else ln.x1 + 40
        caja_si = _caja_opcion(ln, i_si + 2, x_no - 4, y)
        caja_no = _caja_opcion(ln, i_no + 2, x_sig - 4, y)
        grupos.append(
            {
                "i_si": i_si,
                "x_si": ln.car[i_si][1],
                "si": caja_si,
                "no": caja_no,
                "x_fin": caja_no[2],
            }
        )
    return grupos


def _texto_entre(ln: LineaCar, x0: int, x1: int) -> str:
    return "".join(c for c, x in ln.car if x0 <= x < x1).strip(" .:;,")


def construir(lineas: list[LineaCar]) -> dict:
    secciones: list[dict] = []
    for ln in lineas:  # encabezados «5.2 Lenguaje denominativo» pegados al margen izquierdo
        m = SECCION.match(ln.texto)
        if m and ln.x0 < 160 and not _palabras(ln, "Si"):
            secciones.append(
                {
                    "codigo": m.group(1),
                    "titulo": m.group(2).strip(),
                    "y": ln.y0,
                    "items": [],
                    "puntaje": None,
                }
            )
    secciones.sort(key=lambda s: s["y"])

    def seccion_de(y: float) -> dict | None:
        previa = [s for s in secciones if s["y"] <= y + 6]
        return previa[-1] if previa else None

    for ln in lineas:  # puntaje manuscrito: lo que queda a la derecha de «P.E.E.»
        if re.match(r"^\s*P\.?E\.?E", ln.texto):
            sec = seccion_de(ln.y0 - 4)
            if sec is not None and sec["puntaje"] is None:
                otra = [
                    o for o in lineas if o is not ln and abs(o.cy - ln.cy) < 14 and o.x0 > ln.x1 - 5
                ]
                tope = min([o.x0 for o in otra], default=ln.x1 + 260)
                sec["puntaje"] = [ln.x0 + 40, ln.y0 - 2, min(tope - 6, ln.x1 + 200), ln.y1 + 2]

    for ln in lineas:
        grupos = encontrar_grupos(ln)
        previo_fin = ln.x0 - 1
        for g in grupos:
            etiqueta = _texto_entre(ln, previo_fin + 1, g["x_si"])
            if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9]{2}", etiqueta):
                izq = [
                    o
                    for o in lineas
                    if o is not ln
                    and abs(o.cy - ln.cy) < MARGEN_Y
                    and o.x1 <= g["x_si"] + 8
                    and not encontrar_grupos(o)
                ]
                etiqueta = max(izq, key=lambda o: o.x1).texto if izq else ""
            previo_fin = g["x_fin"]
            sec = seccion_de(ln.cy)
            if sec is None:
                continue
            sec["items"].append(
                {
                    "texto": etiqueta,
                    "y": int(ln.cy),
                    "opciones": [
                        {"nombre": "Sí", "caja": g["si"]},
                        {"nombre": "No", "caja": g["no"]},
                    ],
                }
            )
    for s in secciones:
        s["items"].sort(key=lambda it: (it["y"] // 14, it["opciones"][0]["caja"][0]))
    return {"secciones": secciones}


def dibujar(img: np.ndarray, plantilla: dict) -> np.ndarray:
    vis = img.copy()
    for s in plantilla["secciones"]:
        cv2.putText(
            vis, s["codigo"], (4, s["y"] + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1
        )
        if s["puntaje"]:
            x0, y0, x1, y1 = s["puntaje"]
            cv2.rectangle(vis, (x0, y0), (x1, y1), (255, 0, 255), 2)
        for it in s["items"]:
            for o, color in zip(it["opciones"], ((0, 150, 0), (0, 0, 230)), strict=True):
                x0, y0, x1, y1 = o["caja"]
                cv2.rectangle(vis, (x0, y0), (x1, y1), color, 1)
    return vis


def main(argv: list[str]) -> int:
    foto, destino = Path(argv[1]), Path(argv[2])
    img = cv2.imdecode(np.fromfile(str(foto), np.uint8), cv2.IMREAD_COLOR)
    lineas = leer_con_posiciones(img, LectorONNX())
    plantilla = construir(lineas)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.with_suffix(".json").write_text(
        json.dumps(plantilla, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    cv2.imencode(".png", dibujar(img, plantilla))[1].tofile(str(destino.with_suffix(".png")))
    total = 0
    for s in plantilla["secciones"]:
        total += len(s["items"])
        print(
            f"{s['codigo']:>5} {s['titulo'][:46]:46} ítems={len(s['items']):2d} puntaje={'sí' if s['puntaje'] else 'NO'}"
        )
    print(f"{len(plantilla['secciones'])} secciones, {total} ítems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
