# DI-R1: PyInstaller, modo carpeta (onedir), sin consola, sin UPX (menos falsos positivos de antivirus).
# Se ejecuta desde la raíz del repo:  pyinstaller packaging/autoevalpsi.spec --noconfirm
# Antes: `npm run build` en ui/ (deja la interfaz en src/autoevalpsi/app/estaticos) y
# `python -m tools.descargar_modelos` (modelos/pp-ocrv6, verificados por hash).
# Las plantillas reales NO van en el paquete (PL-D2): se importan desde un .zip.
import os
import sys

from PyInstaller.utils.hooks import copy_metadata

RAIZ = os.path.abspath(os.path.join(SPECPATH, os.pardir))
APP = os.path.join(RAIZ, "src", "autoevalpsi", "app")
MODELOS = os.path.join(RAIZ, "modelos", "pp-ocrv6")
ICONO = os.path.join(SPECPATH, "icono.ico")

for requerido in (os.path.join(APP, "estaticos", "index.html"), os.path.join(MODELOS, "det", "inference.onnx")):
    if not os.path.isfile(requerido):
        sys.exit(f"Falta {requerido}. Compila la interfaz y baja los modelos antes de empaquetar.")

datas = [
    (os.path.join(APP, "estaticos"), "autoevalpsi/app/estaticos"),
    (os.path.join(APP, "captura"), "autoevalpsi/app/captura"),
    (MODELOS, "modelos/pp-ocrv6"),  # det, rec y diccionario.txt
]
datas += copy_metadata("autoevalpsi")  # para `importlib.metadata.version`

a = Analysis(
    [os.path.join(SPECPATH, "lanzador.py")],
    pathex=[os.path.join(RAIZ, "src")],
    datas=datas,
    excludes=["tkinter", "pytest", "ruff", "pyinstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AutoEvalPsi",
    console=False,
    upx=False,
    icon=ICONO if os.path.isfile(ICONO) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AutoEvalPsi", upx=False)
