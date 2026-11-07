# PLAN-BASE — Repositorio, estructura y red de tests

Frente transversal: deja el repo, el entorno y los datos de prueba sintéticos que usan todos los
demás frentes. Prefijo `BS`.

| Fase | Título | Estado |
|---|---|---|
| BS-R0 | Esqueleto del repo y entorno | pendiente |
| BS-R1 | Formulario sintético y generador de fotos de prueba | pendiente |
| BS-R2 | CI de tests en GitHub Actions | pendiente |

---

## Hallazgos

- **BS-01** — La carpeta solo contiene `plan.md`: no hay repo git, código, entorno ni tests.
- **BS-02** — Las muestras de la usuaria (fotos con su letra) y las plantillas reales
  (instrumentos con posibles derechos de autor) **no pueden entrar a git**, ni siquiera al repo
  privado de código (ver PL-D2). Por eso los tests de CI no pueden depender de ellas: hace falta un
  formulario propio, sin derechos, y un generador de fotos sintéticas.
- **BS-03** — Node/npm no están instalados en la máquina de desarrollo (verificado 2026-11-06).
  La interfaz React (AP-R4) no se puede compilar localmente hasta instalarlo; uv tampoco está
  instalado (ver BS-D1). Python 3.12.0 y git 2.42 sí están.
- **BS-04** — `plan.md` habla del paquete `core/` desacoplado de la interfaz. Esa regla debe
  vigilarla un test, no solo la disciplina: si `core` importa `fastapi`, `webview` o `app`, el test
  falla.
- **BS-05** — No hay `CLAUDE.md`; sin él, una sesión nueva no sabe que existe la bitácora (P-4).
  **Resuelto 2026-11-06:** `CLAUDE.md` creado en la raíz con enlace a la bitácora y reglas fijas.

---

## Estructura propuesta

```
AUTOEVALPSI/
  pyproject.toml            dependencias + ruff + pytest
  src/autoevalpsi/
    core/                   sin dependencias de UI (BS-04)
      plantillas.py  imagen.py  hoja.py  registro.py  omr.py
      identificacion.py  excel.py  pipeline.py
      ocr/                  lector.py (interfaz), ppocr_onnx.py
    app/                    servidor.py  datos.py  red.py  qr.py  escritorio.py  captura/
    cli.py
  ui/                       React + Vite + TS + Tailwind (AP-R4)
  tools/                    generador sintético, visor de plantillas, cuadrícula, evaluadores
  plantillas_demo/          formulario sintético propio (SÍ en git)
  tests/                    core/  app/  conftest.py
  packaging/                autoevalpsi.spec  installer.iss
  .github/workflows/
  docs/planes/autoevalpsi/
  # fuera de git (.gitignore): muestras/  plantillas/  modelos/  *.onnx  .datos/
```

---

## BS-R0 — Esqueleto del repo y entorno

- **Requiere:** P-1 (git init), BS-D1.
- **Esfuerzo:** S.
- **Pasos:**
  1. `pyproject.toml` con Python `>=3.12,<3.13`, layout `src/`, dependencias núcleo
     (`opencv-python-headless`, `numpy`, `pydantic`, `openpyxl`, `pillow`) y grupos opcionales
     `app` (`fastapi`, `uvicorn`, `pywebview`, `segno`, `python-multipart`), `ocr` (`onnxruntime`),
     `dev` (`pytest`, `ruff`, `pyinstaller`).
  2. `.gitignore` con las exclusiones de BS-02; `muestras/README.md` (sí versionado) que explica
     qué va ahí y por qué no se versiona.
  3. Paquetes vacíos con `__init__.py` y `cli.py` con `autoevalpsi --version`.
  4. Test de frontera `tests/core/test_frontera_core.py`: importa todo `autoevalpsi.core` en un
     subproceso y falla si quedaron cargados `fastapi`, `webview`, `uvicorn` o `autoevalpsi.app`.
- **Tests:** `pytest` verde con el test de frontera y un smoke del CLI.
- **Criterio de salida:** entorno se crea desde cero con un comando documentado en el README.

## BS-R1 — Formulario sintético y generador de fotos de prueba

- **Requiere:** BS-R0, CO-R0 (el JSON que emite debe cargar con el esquema real).
- **Esfuerzo:** M.
- **Pasos:**
  1. `tools/sintetico/formulario.py`: dibuja con OpenCV un formulario propio "demo-5opciones"
     (cabecera, tabla de 12 filas, 5 columnas de opciones, columna de observación) a 300 dpi, en
     A4 y en Carta (ver CO-04). Emite la imagen en blanco y su plantilla JSON en
     `plantillas_demo/`.
  2. `tools/sintetico/llenar.py`: marca casillas con X, ✓, círculo y relleno; con tinta azul y
     negra; casos de borde (fila vacía, doble marca, tachón, marca que sale de la celda, marca
     tenue). Escribe "texto" en observaciones con una fuente manuscrita libre o trazos.
     Devuelve la verdad de terreno (`.json`) junto a cada imagen.
  3. `tools/sintetico/fotografiar.py`: perspectiva aleatoria, rotación, fondo de mesa, sombra en
     degradé, desenfoque, ruido, compresión JPEG, orientación EXIF.
  4. Fixture de pytest que genera un lote determinista (semilla fija) en `tmp_path`.
- **Tests:** el propio generador tiene tests (la verdad de terreno coincide con lo dibujado).
- **Criterio de salida:** los tests de CO-R1…CO-R7 pueden correr sin ninguna foto real.

## BS-R2 — CI de tests en GitHub Actions

- **Requiere:** BS-R0, P-5 (repo remoto, lo crea el responsable).
- **Esfuerzo:** S.
- **Pasos:** workflow `tests.yml` en `windows-latest` (la plataforma real) con Python 3.12,
  instalación de dependencias, `ruff check` y `pytest -m "not lento and not real"`.
  Marcadores: `lento` (generación grande, OCR real) y `real` (fotos de `muestras/`, solo local).
- **Criterio de salida:** el workflow corre verde en un push a `main`.
- **Nota:** es CI en GitHub, no una tarea en la máquina del responsable; compatible con su
  preferencia de no dejar jobs calendarizados locales. Sin `schedule:` en el workflow.

---

## Decisiones

- **BS-D1 — Gestor de entorno.**
  - a) `uv` con `uv.lock`: entorno reproducible para dev, CI y PyInstaller; requiere instalar uv.
  - b) `venv` + `pip` + `requirements.lock` generado con `pip freeze`: no instala nada nuevo.
  - **Decisión (2026-11-06): a) uv con lockfile.**
  - **Recomendación: a)** — el lockfile evita que el build del instalador (DI-R1) traiga versiones
    distintas de opencv/onnxruntime que las probadas.
