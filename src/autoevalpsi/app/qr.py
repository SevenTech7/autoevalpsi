"""AP-R2: URL de la página de captura y su código QR (segno).

La URL lleva IP, puerto y el token del arranque (AP-03): `http://192.168.1.20:8765/captura?token=…`.
El QR sale como SVG para incrustarlo en la interfaz sin archivos intermedios.
"""

import io
from urllib.parse import quote

import segno

RUTA_CAPTURA = "/captura"


def url_captura(ip: str, puerto: int, token: str) -> str:
    return f"http://{ip}:{puerto}{RUTA_CAPTURA}?token={quote(token, safe='')}"


def qr_svg(url: str) -> str:
    """El QR como `<svg>` (sin cabecera XML), con zona de silencio y corrección de errores M."""
    buf = io.BytesIO()
    segno.make(url, error="m", micro=False).save(
        buf, kind="svg", scale=8, border=4, xmldecl=False, svgns=True, nl=False
    )
    return buf.getvalue().decode("utf-8")
