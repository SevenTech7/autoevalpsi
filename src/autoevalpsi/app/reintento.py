"""Arranque que aguanta que las DLL estén tomadas por otro proceso unos segundos.

Justo después de instalar o actualizar, el instalador o el antivirus pueden tener abiertos los
archivos recién escritos, y Windows responde «el proceso no puede obtener acceso al archivo porque
está siendo utilizado por otro proceso» al cargar una DLL (le pasó a NumPy). Un `import` que falló
no se puede repetir con seguridad dentro del mismo proceso: se relanza el programa entero.

Solo la biblioteca estándar: este módulo se importa antes que NumPy.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable

VARIABLE = "AUTOEVALPSI_INTENTO"
INTENTOS = 6
ESPERA = 3.0  # segundos entre intentos


def _relanzar() -> None:  # pragma: no cover - lanza un proceso de verdad
    entorno = {**os.environ, VARIABLE: str(int(os.environ.get(VARIABLE, "0")) + 1)}
    subprocess.Popen([sys.executable, *sys.argv[1:]], env=entorno)


def arrancar(
    importar: Callable[[], Callable[[], int]],
    *,
    intento: int | None = None,
    relanzar: Callable[[], None] = _relanzar,
    esperar: Callable[[float], None] = time.sleep,
) -> int:
    """Importa y corre `main`. Si el import falla y quedan intentos, espera y se relanza (devuelve
    0 sin abrir nada); al agotarlos, deja pasar el error para que se vea qué pasó."""
    if intento is None:
        intento = int(os.environ.get(VARIABLE, "0") or 0)
    try:
        main = importar()
    except ImportError:
        if intento >= INTENTOS:
            raise
        esperar(ESPERA)
        relanzar()
        return 0
    return main()


def principal() -> int:  # pragma: no cover - lo usa el punto de entrada empaquetado
    def importar() -> Callable[[], int]:
        from autoevalpsi.app.lanzador import main

        return main

    return arrancar(importar)
