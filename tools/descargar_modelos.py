"""OC-04: baja los modelos OCR a `modelos/` con revisión fijada y SHA-256 verificado.

Uso (dentro de Docker):  docker compose run --rm dev python -m tools.descargar_modelos

- Idempotente: si un archivo ya existe con el hash correcto, no lo baja otra vez.
- Un archivo con hash distinto se rechaza (y se borra el parcial); nunca se deja uno sin verificar.
- Genera `modelos/pp-ocrv6/rec/diccionario.txt` desde el `inference.yml` del reconocedor, para que
  el runtime no necesite PyYAML; el diccionario también se verifica por hash.
- Los modelos van fuera de git (`modelos/` está en `.gitignore`).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DESTINO = Path("modelos/pp-ocrv6")
HF = "https://huggingface.co/PaddlePaddle/{repo}/resolve/{rev}/{archivo}"


@dataclass(frozen=True)
class Archivo:
    repo: str
    rev: str
    nombre: str  # nombre en el repo
    destino: str  # relativo a DESTINO
    sha256: str


ARCHIVOS = [
    Archivo(
        "PP-OCRv6_medium_det_onnx",
        "61323801669c338b7891481ec7bac61ce31b576a",
        "inference.onnx",
        "det/inference.onnx",
        "eb13b44b25bb36f89528b68720af8a61d9cf381176107f465db1757b65d086e1",
    ),
    Archivo(
        "PP-OCRv6_medium_rec_onnx",
        "50c7eacafc52fa7bcf4194e8cd08e46f8558504b",
        "inference.onnx",
        "rec/inference.onnx",
        "9c09abf0957f7968c7586464b7397b84ad2387a0497a351af40e9acc71b673ba",
    ),
]
YML_REC = Archivo(
    "PP-OCRv6_medium_rec_onnx",
    "50c7eacafc52fa7bcf4194e8cd08e46f8558504b",
    "inference.yml",
    "rec/inference.yml",
    "991b700facf5b50a7de193468207d5f4255b538dde0d312ae3b7c7a9b6873129",
)
# SHA-256 de `rec/diccionario.txt` (generado desde inference.yml de la revisión fijada).
DICCIONARIO_SHA256 = "b5f2bfe2bdd9448429e3e82b51c789775d9b42f2403d082b00662eb77e401c5d"


class HashIncorrecto(RuntimeError):
    pass


def sha256_de(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def bajar(a: Archivo, destino: Path = DESTINO) -> Path:
    ruta = destino / a.destino
    if a.sha256 and ruta.is_file() and sha256_de(ruta) == a.sha256:
        print(f"ok   {a.destino} (ya estaba, hash correcto)")
        return ruta
    ruta.parent.mkdir(parents=True, exist_ok=True)
    parcial = ruta.with_suffix(ruta.suffix + ".parcial")
    url = HF.format(repo=a.repo, rev=a.rev, archivo=a.nombre)
    print(f"baja {a.destino} ← {url}")
    with urllib.request.urlopen(url, timeout=60) as r, parcial.open("wb") as f:
        while bloque := r.read(1 << 20):
            f.write(bloque)
    if a.sha256 and sha256_de(parcial) != a.sha256:
        obtenido = sha256_de(parcial)
        parcial.unlink()
        raise HashIncorrecto(f"{a.destino}: esperado {a.sha256}, obtenido {obtenido}")
    parcial.replace(ruta)
    return ruta


def escribir_diccionario(yml: Path, salida: Path) -> str:
    """Extrae `PostProcess.character_dict` del yml a un .txt de un carácter por línea."""
    import yaml  # solo la herramienta de descarga (grupo dev)

    d = yaml.safe_load(yml.read_text(encoding="utf8"))
    caracteres = d["PostProcess"]["character_dict"]
    malos = [c for c in caracteres if not isinstance(c, str) or len(c) != 1 or c == "\n"]
    if malos:
        raise ValueError(f"entradas del diccionario no válidas: {malos[:5]}")
    salida.write_text("\n".join(caracteres) + "\n", encoding="utf8", newline="\n")
    return sha256_de(salida)


def main(destino: Path = DESTINO) -> int:
    for a in ARCHIVOS:
        bajar(a, destino)
    yml = bajar(YML_REC, destino)
    txt = destino / "rec/diccionario.txt"
    if DICCIONARIO_SHA256 and txt.is_file() and sha256_de(txt) == DICCIONARIO_SHA256:
        print("ok   rec/diccionario.txt (ya estaba, hash correcto)")
        return 0
    h = escribir_diccionario(yml, txt)
    if DICCIONARIO_SHA256 and h != DICCIONARIO_SHA256:
        txt.unlink()
        raise HashIncorrecto(f"rec/diccionario.txt: esperado {DICCIONARIO_SHA256}, obtenido {h}")
    print(f"ok   rec/diccionario.txt generado (sha256 {h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
