"""Línea de comandos de AutoEvalPsi."""

import argparse
import json
import os
import sys
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

CARPETA_PLANTILLAS = (
    "plantillas"  # plantillas reales: fuera de git (PL-D2); override con --plantillas
)


def _version() -> str:
    try:
        return version("autoevalpsi")
    except PackageNotFoundError:
        return "0.0.0+local"


def _resolver_plantilla(valor: str, carpeta: str) -> Path:
    """`valor` es una ruta a un .json o un id que se busca como `<carpeta>/<id>.json`."""
    directa = Path(valor)
    if directa.is_file():
        return directa
    candidata = Path(carpeta) / f"{valor}.json"
    if candidata.is_file():
        return candidata
    raise FileNotFoundError(
        f"No encuentro la plantilla «{valor}» (busqué {directa} y {candidata}). "
        "Usa --plantillas para indicar la carpeta."
    )


def _procesar(args: argparse.Namespace) -> int:
    # Importes perezosos: `--version` no debe cargar OpenCV.
    import cv2

    from autoevalpsi.core.depuracion import dibujar_depuracion
    from autoevalpsi.core.excel import ArchivoBloqueado, NombreArchivo, exportar
    from autoevalpsi.core.pipeline import a_evaluacion, procesar_foto
    from autoevalpsi.core.plantilla import PlantillaInvalida, cargar_plantilla
    from autoevalpsi.core.registro import cargar_referencia

    try:
        ruta = _resolver_plantilla(args.plantilla, args.plantillas)
        plantilla = cargar_plantilla(ruta)
        referencia = cargar_referencia(ruta, plantilla.paginas[0].imagen_referencia)
        datos = Path(args.foto).read_bytes()
        lector = None
        if args.ocr:
            from autoevalpsi.core.ocr.onnx import LectorONNX

            lector = LectorONNX()  # perezoso: los modelos se cargan al leer
        proc = procesar_foto(datos, plantilla, referencia, lector=lector)
    except (FileNotFoundError, ImportError, PlantillaInvalida, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    res = proc.resultado
    evaluacion = a_evaluacion(
        res,
        plantilla,
        paciente=args.paciente,
        fecha=date.fromisoformat(args.fecha) if args.fecha else None,
        recortes=proc.recortes,
    )
    modo = NombreArchivo.INICIALES if args.iniciales else NombreArchivo.PACIENTE
    try:
        archivos = exportar(evaluacion, salida, nombre=modo, incluir_recortes=args.recortes)
    except ArchivoBloqueado as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.depuracion:
        carpeta = salida / "depuracion"
        carpeta.mkdir(exist_ok=True)
        imagen = dibujar_depuracion(proc.registro, plantilla, res.filas)
        ok, buf = cv2.imencode(".png", imagen)
        if not ok:
            print("Error: no se pudo codificar la imagen de depuración.", file=sys.stderr)
            return 2
        (carpeta / f"{Path(args.foto).stem}.hoja.png").write_bytes(buf.tobytes())
        for item, recorte in proc.recortes.items():  # siempre que haya OCR, aunque falle (OC-02)
            ok_png, png = cv2.imencode(".png", recorte)
            if ok_png:
                (carpeta / f"{Path(args.foto).stem}.obs{item:03d}.png").write_bytes(png.tobytes())
        (carpeta / f"{Path(args.foto).stem}.resultado.json").write_text(
            json.dumps(res.a_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    print(f"Evaluación: {archivos.evaluacion}")
    print(f"Consolidado: {archivos.consolidado}")
    print(f"Filas: {len(res.filas)} · a revisar: {res.n_amarillas}")
    for c in res.cabecera:
        if not c.ok:
            print(
                f"Aviso: el campo de cabecera «{c.campo}» necesita revisión ({', '.join(c.banderas)})."
            )
    for problema in res.problemas_calidad:
        print(f"Aviso de calidad: {problema}")
    if not res.registro_ok:
        print("Aviso: la hoja no se alineó bien con la plantilla; revisa todas las filas.")
    return 0


def _abrir(args: argparse.Namespace) -> int:
    from autoevalpsi.app.escritorio import ejecutar

    lector = None
    if args.ocr:
        from autoevalpsi.core.ocr.onnx import LectorONNX

        lector = LectorONNX()  # perezoso: los modelos se cargan al leer
    return ejecutar(puerto=args.puerto, lector=lector)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autoevalpsi")
    parser.add_argument("--version", action="version", version=f"autoevalpsi {_version()}")
    sub = parser.add_subparsers(dest="comando")

    p = sub.add_parser("procesar", help="Convierte la foto de un formulario en un Excel.")
    p.add_argument("foto", help="Foto JPEG o PNG del formulario lleno.")
    p.add_argument("--plantilla", required=True, help="Id de la plantilla o ruta a su .json.")
    p.add_argument("--salida", required=True, help="Carpeta donde se escriben los Excel.")
    p.add_argument(
        "--plantillas",
        default=os.environ.get("AUTOEVALPSI_PLANTILLAS", CARPETA_PLANTILLAS),
        help=f"Carpeta de plantillas para buscar por id (por defecto «{CARPETA_PLANTILLAS}»).",
    )
    p.add_argument("--paciente", default="", help="Nombre del paciente (va en el Excel).")
    p.add_argument("--fecha", help="Fecha de la evaluación AAAA-MM-DD (por defecto, hoy).")
    p.add_argument("--iniciales", action="store_true", help="Nombre de archivo con iniciales.")
    p.add_argument(
        "--depuracion",
        action="store_true",
        help="Guarda la hoja enderezada con la lectura superpuesta y el resultado en JSON.",
    )
    p.add_argument(
        "--ocr",
        action="store_true",
        help="Lee con OCR las observaciones y la cabecera (necesita `modelos/`; ver README).",
    )
    p.add_argument(
        "--recortes",
        action="store_true",
        help="Incluye en el Excel la imagen de cada observación manuscrita.",
    )
    p.set_defaults(ejecutar=_procesar)

    p = sub.add_parser("abrir", help="Abre la ventana de la aplicación (servidor local incluido).")
    p.add_argument("--puerto", type=int, default=8765, help="Puerto local (por defecto 8765).")
    p.add_argument("--ocr", action="store_true", help="Activa el OCR (necesita `modelos/`).")
    p.set_defaults(ejecutar=_abrir)

    args = parser.parse_args(argv)
    if getattr(args, "ejecutar", None) is None:
        parser.print_help()
        return 0
    return args.ejecutar(args)


if __name__ == "__main__":
    raise SystemExit(main())
