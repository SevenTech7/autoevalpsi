"""BS-04: `core` no puede depender de la UI ni del servidor."""

import json
import subprocess
import sys

PROHIBIDOS = ("fastapi", "webview", "uvicorn", "autoevalpsi.app")

SCRIPT = """
import importlib, json, pkgutil, sys
import autoevalpsi.core as core
for m in pkgutil.walk_packages(core.__path__, core.__name__ + "."):
    importlib.import_module(m.name)
print(json.dumps(sorted(sys.modules)))
"""


def _cargados() -> list[str]:
    salida = subprocess.run(
        [sys.executable, "-c", SCRIPT], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(salida)


def test_core_no_importa_ui_ni_servidor():
    cargados = _cargados()
    malos = [m for m in cargados if any(m == p or m.startswith(p + ".") for p in PROHIBIDOS)]
    assert not malos, f"core cargó módulos prohibidos: {malos}"


def test_el_detector_detecta():
    """Test negativo: un módulo de core que importe la app debe hacer fallar la frontera."""
    from autoevalpsi import core

    ruta = core.__path__[0] + "/_trampa.py"
    with open(ruta, "w") as f:
        f.write("import autoevalpsi.app\n")
    try:
        assert any(m.startswith("autoevalpsi.app") for m in _cargados())
    finally:
        import os

        os.remove(ruta)
