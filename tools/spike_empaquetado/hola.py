"""Spike DI-R0: «hola mundo» que ejercita lo que PyInstaller suele romper.

Importa cv2 y onnxruntime (con una sesión sobre un ONNX mínimo hecho a mano), levanta uvicorn
en un hilo con FastAPI, consulta /api/salud y, salvo con --sin-ventana, abre pywebview.
Imprime una línea JSON con tiempos. Descartable.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

T0 = time.perf_counter()


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _campo(num: int, tipo: int, datos: bytes | int) -> bytes:
    clave = _varint((num << 3) | tipo)
    if tipo == 0:
        return clave + _varint(int(datos))
    return clave + _varint(len(datos)) + bytes(datos)


def onnx_identidad() -> bytes:
    """ModelProto mínimo: y = Identity(x), float[4]. Protobuf escrito a mano (sin paquete onnx)."""
    dim = _campo(1, 0, 4)
    forma = _campo(1, 2, dim)
    tensor = _campo(1, 0, 1) + _campo(2, 2, forma)
    tipo = _campo(1, 2, tensor)

    def info(nombre: bytes) -> bytes:
        return _campo(1, 2, nombre) + _campo(2, 2, tipo)

    nodo = _campo(1, 2, b"x") + _campo(2, 2, b"y") + _campo(4, 2, b"Identity")
    grafo = _campo(1, 2, nodo) + _campo(2, 2, b"g") + _campo(11, 2, info(b"x"))
    grafo += _campo(12, 2, info(b"y"))
    return _campo(1, 0, 8) + _campo(7, 2, grafo) + _campo(8, 2, _campo(2, 0, 13))


def probar_onnx() -> list[float]:
    import numpy as np
    import onnxruntime as ort

    ruta = Path(tempfile.gettempdir()) / "spike_identidad.onnx"
    ruta.write_bytes(onnx_identidad())
    sesion = ort.InferenceSession(str(ruta), providers=["CPUExecutionProvider"])
    x = np.array([1, 2, 3, 4], dtype=np.float32)
    return sesion.run(None, {"x": x})[0].tolist()


def probar_cv2() -> tuple[str, int]:
    import cv2
    import numpy as np

    img = np.zeros((32, 32, 3), dtype=np.uint8)
    cv2.circle(img, (16, 16), 8, (255, 255, 255), -1)
    _ok, buf = cv2.imencode(".jpg", img)
    gris = cv2.cvtColor(cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2GRAY)
    return cv2.__version__, int(gris.sum())


def servidor(puerto: int):
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()

    @app.get("/api/salud")
    def salud() -> dict:
        return {"ok": True}

    @app.get("/")
    def raiz():
        from fastapi.responses import HTMLResponse

        return HTMLResponse("<h1>AutoEvalPsi spike</h1>")

    cfg = uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning")
    srv = uvicorn.Server(cfg)
    hilo = threading.Thread(target=srv.run, daemon=True)
    hilo.start()
    return srv, hilo


def main(argv: list[str]) -> int:
    sin_ventana = "--sin-ventana" in argv
    puerto = 8765
    res: dict = {"frozen": bool(getattr(sys, "frozen", False))}
    res["cv2"] = probar_cv2()
    res["onnx"] = probar_onnx()
    res["t_importes_s"] = round(time.perf_counter() - T0, 2)
    srv, hilo = servidor(puerto)
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/salud", timeout=1) as r:
                res["salud"] = json.loads(r.read())
                break
        except OSError:
            time.sleep(0.1)
    res["t_servidor_s"] = round(time.perf_counter() - T0, 2)
    if not sin_ventana:
        import webview

        webview.create_window("AutoEvalPsi spike", f"http://127.0.0.1:{puerto}/")
        res["ventana"] = "abierta"
        print(json.dumps(res), flush=True)
        webview.start()
    else:
        print(json.dumps(res), flush=True)
    srv.should_exit = True
    hilo.join(timeout=3)
    return 0 if res.get("salud") == {"ok": True} else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
