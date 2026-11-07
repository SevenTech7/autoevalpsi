"""FS-R0/FS-R1: borrador de plantilla Sí/No desde la foto de un formulario lleno (uso manual).

    docker compose run --rm dev python -m tools.sino_desde_foto foto.jpg salida/nombre

Deja `nombre.json` (borrador), `nombre.png` (revisión visual) y `nombre.zip` (plantilla lista para
importar). La lógica está en `autoevalpsi.core.borrador`; la app la usa desde «Plantillas».
"""

import json
import re
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np

from autoevalpsi.core.borrador import dibujar, plantilla_desde_foto
from autoevalpsi.core.ocr.onnx import LectorONNX


def main(argv: list[str]) -> int:
    foto, destino = Path(argv[1]), Path(argv[2])
    img = cv2.imdecode(np.fromfile(str(foto), np.uint8), cv2.IMREAD_COLOR)
    ident = re.sub(r"[^a-z0-9]+", "-", destino.stem.lower()).strip("-") or "formulario"
    v1, limpia, borrador = plantilla_desde_foto(img, LectorONNX(), id=ident, nombre=destino.stem)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.with_suffix(".json").write_text(
        json.dumps(borrador, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    cv2.imencode(".png", dibujar(img, borrador))[1].tofile(str(destino.with_suffix(".png")))
    with zipfile.ZipFile(destino.with_suffix(".zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("plantilla.json", json.dumps(v1, indent=1, ensure_ascii=False))
        z.writestr(f"{ident}.png", cv2.imencode(".png", limpia)[1].tobytes())
    total = 0
    for s in borrador["secciones"]:
        total += len(s["items"])
        print(f"{s['codigo']:>5} {s['titulo'][:46]:46} ítems={len(s['items']):2d}")
    print(f"{len(borrador['secciones'])} secciones, {total} ítems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
