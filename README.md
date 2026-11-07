# AutoEvalPsi

App local de Windows que convierte fotos de formularios psicológicos en Excel (OMR + OCR).
Producto y decisiones: [plan.md](plan.md). Estado del trabajo:
[docs/planes/autoevalpsi/BITACORA.md](docs/planes/autoevalpsi/BITACORA.md).

## Entorno (desde cero)

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/) (`python -m pip install --user uv`;
si `uv` no queda en el PATH, usar `python -m uv`).

```
uv sync --all-extras      # crea .venv con dependencias núcleo, app, ocr y dev
uv run pytest             # suite rápida (excluye los marcadores real y lento)
uv run ruff check .
uv run autoevalpsi --version
```

## Reglas

- `autoevalpsi.core` no importa `fastapi`, `uvicorn`, `webview` ni `autoevalpsi.app`
  (lo vigila `tests/core/test_frontera_core.py`).
- Nunca se versionan `muestras/`, `plantillas/` reales, `modelos/`, `*.onnx`, BD ni fotos.
