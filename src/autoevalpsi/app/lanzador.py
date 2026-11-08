"""DI-R1: punto de entrada del ejecutable empaquetado (y de `python -m autoevalpsi.app.lanzador`).

Sin argumentos abre la aplicación como la usuaria la usa: busca los modelos OCR junto al programa
y, si están, activa el OCR. `--prueba-humo` es para el build: arranca el servidor en un puerto
aparte y una carpeta temporal, comprueba `/api/salud`, carga los modelos con una imagen en blanco
(así salen a la luz las DLL que falten) y termina con 0 si todo respondió. No abre ventana.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

from autoevalpsi.core.ocr.lector import Lector

PUERTO_PRUEBA = 8777
SUBCARPETA_MODELOS = Path("modelos") / "pp-ocrv6"


def raiz_recursos() -> Path:
    """Carpeta con los datos del paquete: `_MEIPASS` si va empaquetado, la raíz del repo si no."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


def carpeta_modelos() -> Path:
    return raiz_recursos() / SUBCARPETA_MODELOS


def lector_por_defecto() -> Lector | None:
    """El OCR si los modelos están junto al programa; si no, sin OCR (todo se confirma a mano)."""
    carpeta = carpeta_modelos()
    if not (carpeta / "det" / "inference.onnx").is_file():
        return None
    from autoevalpsi.core.ocr.onnx import LectorONNX

    return LectorONNX(carpeta)  # perezoso: carga los modelos en la primera lectura


def prueba_humo(
    lector: Lector | None, *, puerto: int = PUERTO_PRUEBA, informe: Path | None = None
) -> int:
    """El ejecutable de Windows no tiene consola: el resultado también se deja en `informe`."""
    mensaje, codigo = _prueba_humo(lector, puerto)
    print(mensaje, file=sys.stderr if codigo else sys.stdout)
    if informe is not None:
        informe.write_text(mensaje + "\n", encoding="utf-8")
    return codigo


def _prueba_humo(lector: Lector | None, puerto: int) -> tuple[str, int]:
    import numpy as np

    from autoevalpsi.app.escritorio import _responde_salud, ejecutar

    resultado: list[str] = []

    def ventana(url: str, bd: object) -> None:
        if not _responde_salud(puerto, espera=5.0):
            resultado.append("/api/salud no responde")
            return
        if lector is not None:
            try:
                lector.leer(np.full((64, 256, 3), 255, np.uint8))
            except Exception as e:  # noqa: BLE001 - cualquier fallo del OCR es un fallo del build
                resultado.append(f"el OCR no carga: {type(e).__name__}: {e}")

    errores: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        codigo = ejecutar(
            raiz=Path(tmp),
            puerto=puerto,
            lector=lector,
            ventana=ventana,
            mostrar_error=errores.append,
        )
    resultado += errores
    if codigo != 0 or resultado:
        return "PRUEBA DE HUMO FALLÓ: " + "; ".join(resultado or [f"código {codigo}"]), 1
    return "prueba de humo ok" + (" (con OCR)" if lector else " (sin OCR)"), 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="AutoEvalPsi")
    parser.add_argument("--prueba-humo", action="store_true", help="Solo para el build.")
    parser.add_argument(
        "--informe", type=Path, help="Con --prueba-humo: archivo donde dejar el resultado."
    )
    args = parser.parse_args(argv)
    for nombre in ("stdout", "stderr"):  # el .exe sin consola no tiene salidas estándar
        if getattr(sys, nombre) is None:
            setattr(sys, nombre, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115
    lector = lector_por_defecto()
    if args.prueba_humo:
        return prueba_humo(lector, informe=args.informe)
    from autoevalpsi.app.datos import raiz_por_defecto
    from autoevalpsi.app.escritorio import configurar_registro, ejecutar

    configurar_registro(raiz_por_defecto())
    return ejecutar(lector=lector)


if __name__ == "__main__":
    raise SystemExit(main())
