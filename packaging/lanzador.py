"""Punto de entrada de PyInstaller (DI-R1); la lógica está en `autoevalpsi.app.lanzador`.

Pasa por `reintento`: justo tras instalar o actualizar, Windows puede tener las DLL tomadas unos
segundos y el programa se relanza solo en vez de mostrar un error."""

from autoevalpsi.app.reintento import principal

raise SystemExit(principal())
