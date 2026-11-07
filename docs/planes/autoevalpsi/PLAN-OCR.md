# PLAN-OCR — Observaciones y cabecera manuscritas

Paquete `autoevalpsi.core.ocr`. Cubre la Fase 2 de `plan.md` (paso 7 del pipeline). Prefijo `OC`.

| Fase | Título | Estado |
|---|---|---|
| OC-R0 | Prueba de viabilidad de PP-OCRv6 en ONNX | pendiente |
| OC-R1 | Lector OCR (detección + reconocimiento + confianza) | bloqueada (OC-D1, tras OC-R0) |
| OC-R2 | Integración en el pipeline: recortes, observaciones y cabecera | pendiente |
| OC-R3 | Medición de error por carácter con su letra (gate de Fase 2) | pendiente |

---

## Hallazgos

- **OC-01** — `plan.md` adopta PP-OCRv6 medium "sin prueba previa". Antes de construir encima hay
  que confirmar que existe un export ONNX utilizable de detección y reconocimiento, su licencia,
  su tamaño y su diccionario. Es el mayor riesgo técnico del proyecto y se ataca en la Ola 1.
- **OC-02** — Los modelos de reconocimiento de PaddleOCR se entrenan sobre todo con texto impreso;
  el rendimiento con manuscrito en español es incierto (ya reconocido en `plan.md`). El recorte de
  imagen junto al texto es la red de seguridad y no es opcional.
- **OC-03** — El diccionario del reconocedor debe incluir `á é í ó ú ü ñ Á É Í Ó Ú Ñ ¿ ¡`. Si el
  modelo elegido no los tiene, todas las palabras con tilde salen mal.
- **OC-04** — Los archivos `.onnx` no van a git: se descargan con un script que verifica SHA-256 y
  los deja en `modelos/` (fuera de git); el build de CI hace lo mismo (DI-R3).
- **OC-05** — **Latencia:** "1–2 s por imagen" × 15–30 filas con observación = 15–60 s por hoja,
  lejos de "pocos segundos". Recomendación: correr la **detección una vez** sobre la franja de
  observaciones de la hoja enderezada y asignar cada línea a su fila por `y`; reconocer solo las
  líneas detectadas (el reconocimiento por línea es barato). Saltar filas sin tinta.
- **OC-06** — onnxruntime usa todos los núcleos por defecto; con el servidor y la UI en el mismo
  proceso conviene fijar `intra_op_num_threads` y reutilizar una sola sesión cargada al inicio.
- **OC-07** — Las mediciones de velocidad en la máquina de desarrollo son solo una aproximación;
  la cifra que cuenta es la del Vivobook (Ryzen 7) de ella.

---

## OC-R0 — Prueba de viabilidad de PP-OCRv6 en ONNX

- **Requiere:** BS-R0. Puede ir en paralelo con el núcleo de casillas.
- **Esfuerzo:** M. Es un **spike**: el código vive en `tools/spike_ocr/` y puede descartarse.
- **Pasos:**
  1. Ubicar los modelos oficiales (detección + reconocimiento medium) y su export ONNX; anotar
     URL, versión, licencia, tamaño y SHA-256 en este plan.
  2. Revisar el diccionario (OC-03).
  3. Correr detección + reconocimiento con onnxruntime CPU sobre texto impreso sintético y sobre
     una línea manuscrita (de `muestras/` si ya existe; si no, una propia).
  4. Medir latencia de carga, de detección por franja y de reconocimiento por línea.
- **Criterio de salida:** informe en este plan con las cifras y una propuesta para OC-D1.

## OC-R1 — Lector OCR

- **Requiere:** OC-R0, OC-D1.
- **Esfuerzo:** M.
- **Pasos:** interfaz `Lector` (`leer(imagen) -> list[Linea(texto, confianza, caja)]`) para poder
  enchufar el plan B (modelo grande por lotes) sin tocar el pipeline; implementación ONNX con
  pre/postproceso (redimensionado, normalización, DB postprocess, CTC decode); sesión única y
  perezosa (OC-06); `tools/descargar_modelos.py` con verificación de hash (OC-04).
- **Tests:** marcador `lento` para el modelo real sobre texto impreso sintético (exactitud alta
  esperada); tests rápidos con un `Lector` falso para el resto del pipeline.

## OC-R2 — Integración en el pipeline

- **Requiere:** OC-R1, CO-R7.
- **Esfuerzo:** M.
- **Pasos:** detección sobre la franja de observaciones (OC-05); asignación de líneas a filas;
  detección de "fila con tinta" para saltar vacías; recorte PNG por fila guardado siempre; bandera
  `ocr_confianza_baja` bajo umbral; OCR de los campos de cabecera (CO-03); salida en el resultado
  del pipeline y en el Excel (columna de observación y recorte opcional).
- **Tests:** con un `Lector` falso, cada línea cae en su fila; fila sin tinta no llama al lector;
  el recorte existe aunque el lector falle (excepción simulada).

## OC-R3 — Medición de error por carácter con su letra (gate de Fase 2)

- **Requiere:** OC-R2, muestras llenas con transcripción de referencia (PL-05).
- **Esfuerzo:** M. Suite `real`, local.
- **Pasos:** `tools/medir_cer.py` calcula CER y WER por formulario y por campo contra la
  transcripción de referencia; histograma de confianza vs. acierto para fijar el umbral amarillo.
- **Criterio de salida (Fase 2 de `plan.md`):** CER medido con su letra y decisión OC-D2 tomada
  por el responsable.

---

## Decisiones

- **OC-D1 — Modelo OCR a usar** (se decide con las cifras de OC-R0).
  - a) PP-OCRv6 medium en ONNX, como dice `plan.md`.
  - b) La versión anterior disponible de PP-OCR con modelo de reconocimiento latino, si la v6 no
    tiene export ONNX usable o le faltan caracteres españoles.
  - **Recomendación: a) si OC-R0 confirma ONNX, licencia y diccionario; b) si no.**
- **OC-D2 — Cómo se muestra el texto en la revisión** (se decide con el CER de OC-R3).
  - a) Texto leído como sugerencia editable, con el recorte al lado.
  - b) Solo el recorte; ella tipea la observación.
  - c) Sugerencia solo cuando la confianza supera el umbral; si no, campo vacío con el recorte.
  - **Recomendación: c)** — evita que ella acepte sin leer un texto mal transcrito y le ahorra
    tipeo cuando el OCR acierta. La decisión final depende de las cifras.
