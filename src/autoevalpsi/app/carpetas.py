"""Carpetas del usuario que la app usa por defecto (hoy: Descargas, para los Excel)."""

import os
import uuid
from pathlib import Path


def _descargas_de_windows() -> Path | None:  # pragma: no cover - solo Windows
    r"""La carpeta Descargas de verdad (puede estar redirigida o con otro nombre), vía la API del
    sistema; no se asume `%USERPROFILE%\Downloads`."""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(texto: str) -> GUID:
        u = uuid.UUID(texto)
        g = GUID()
        g.Data1, g.Data2, g.Data3 = u.time_low, u.time_mid, u.time_hi_version
        g.Data4[:] = u.bytes[8:]
        return g

    ruta = ctypes.c_wchar_p()
    resultado = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid("374DE290-123F-4565-9164-39C4925E467B")), 0, None, ctypes.byref(ruta)
    )
    try:
        return Path(ruta.value) if resultado == 0 and ruta.value else None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ruta)


def carpeta_descargas() -> Path | None:
    """La carpeta Descargas del usuario si existe; None si no se encuentra."""
    candidata = _descargas_de_windows() if os.name == "nt" else None
    candidata = candidata or Path.home() / "Downloads"
    return candidata if candidata.is_dir() else None
