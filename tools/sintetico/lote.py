"""BS-R1: lote determinista de fotos sintéticas con su verdad de terreno.

Por foto `i` escribe en `destino`: `foto_NN.jpg`, `foto_NN.hoja.png` (hoja llena sin
perspectiva) y `foto_NN.verdad.json` (verdad de `llenar` + meta de `fotografiar` + exif y
calidad JPEG). Además `blanca.png` y `plantilla.json` del formulario usado.

Foto 0: limpia (sin giro ni EXIF, todos los casos normales). Foto 1: recorre los casos de borde.
Las demás: casos al azar, perspectiva, EXIF y calidad variables. Misma semilla, mismos bytes.

Uso:  python -m tools.sintetico.lote --salida DIR [--n 6] [--formato a4|carta]
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.plantilla import cargar_plantilla

from .formulario import FORMATOS, construir
from .fotografiar import ORIENTACIONES, fotografiar, guardar_jpeg
from .llenar import CASOS, llenar

SEMILLA = 20261106


@dataclass(frozen=True)
class FotoSintetica:
    foto: Path
    hoja: Path
    verdad: Path
    plantilla: Path


def _json(ruta: Path, datos: dict) -> None:
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generar_lote(
    destino: str | Path,
    *,
    semilla: int = SEMILLA,
    n: int = 6,
    formato: str = "a4",
    tamano_foto: tuple[int, int] = (1800, 2400),
) -> list[FotoSintetica]:
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    blanca, datos_plantilla = construir(formato)
    ruta_plantilla = destino / "plantilla.json"
    _json(ruta_plantilla, datos_plantilla)
    cv2.imwrite(str(destino / "blanca.png"), blanca)
    plantilla = cargar_plantilla(ruta_plantilla)
    items = [f.item for t in plantilla.paginas[0].tablas for f in t.filas]

    fotos = []
    for i in range(n):
        rng = np.random.default_rng([semilla, i])
        casos = None
        opciones_foto: dict = {}
        orientacion = int(rng.choice(ORIENTACIONES))
        calidad = int(rng.integers(70, 93))
        if i == 0:
            casos = dict.fromkeys(items, "normal")
            opciones_foto = {
                "rotacion_max": 1.5,
                "perspectiva_max": 0.01,
                "desenfoque": (0.3, 0.4),
                "ruido": (1.0, 1.5),
            }
            orientacion, calidad = 1, 92
        elif i == 1:
            casos = {it: CASOS[(k + 1) % len(CASOS)] for k, it in enumerate(items)}
        hoja, verdad = llenar(blanca, plantilla, rng, casos=casos)
        foto, meta = fotografiar(hoja, rng, tamano=tamano_foto, **opciones_foto)

        ruta_foto = destino / f"foto_{i:02d}.jpg"
        guardar_jpeg(foto, ruta_foto, calidad=calidad, orientacion=orientacion)
        ruta_hoja = destino / f"foto_{i:02d}.hoja.png"
        cv2.imwrite(str(ruta_hoja), hoja)
        ruta_verdad = destino / f"foto_{i:02d}.verdad.json"
        _json(
            ruta_verdad,
            {
                "foto": ruta_foto.name,
                "formato": formato,
                "semilla": [semilla, i],
                "exif_orientacion": orientacion,
                "calidad_jpeg": calidad,
                **verdad,
                "fotografia": meta,
            },
        )
        fotos.append(FotoSintetica(ruta_foto, ruta_hoja, ruta_verdad, ruta_plantilla))
    return fotos


def main() -> None:
    p = argparse.ArgumentParser(description="Genera un lote de fotos sintéticas.")
    p.add_argument("--salida", required=True)
    p.add_argument("--n", type=int, default=6)
    p.add_argument("--formato", choices=list(FORMATOS), default="a4")
    a = p.parse_args()
    for f in generar_lote(a.salida, n=a.n, formato=a.formato):
        print(f.foto)


if __name__ == "__main__":
    main()
