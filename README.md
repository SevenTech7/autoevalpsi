# AutoEvalPsi

App local de Windows que convierte fotos de formularios psicológicos en Excel (OMR + OCR).
Producto y decisiones: [plan.md](plan.md). Estado del trabajo:
[docs/planes/autoevalpsi/BITACORA.md](docs/planes/autoevalpsi/BITACORA.md).

## Entorno (desde cero)

Todo corre en **Docker Desktop**; no se instala nada en el equipo ni se tocan variables globales.

```
docker compose build
docker compose run --rm dev pytest                 # suite rápida (excluye real y lento)
docker compose run --rm dev ruff check .
docker compose run --rm dev autoevalpsi --version
docker compose run --rm dev uv add <paquete>       # cambia dependencias y uv.lock
```

Datos de prueba sintéticos (sin fotos reales):

```
docker compose run --rm dev python -m tools.sintetico.formulario   # regenera plantillas_demo/
docker compose run --rm dev python -m tools.sintetico.lote --salida .datos/lote
```

El entorno virtual y la caché de uv viven en volúmenes de Docker, no en la carpeta del proyecto.

## Reglas

- `autoevalpsi.core` no importa `fastapi`, `uvicorn`, `webview` ni `autoevalpsi.app`
  (lo vigila `tests/core/test_frontera_core.py`).
- Nunca se versionan `muestras/`, `plantillas/` reales, `modelos/`, `*.onnx`, BD ni fotos.
