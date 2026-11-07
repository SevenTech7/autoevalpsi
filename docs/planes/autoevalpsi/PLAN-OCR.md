# PLAN-OCR — Observaciones y cabecera manuscritas

Paquete `autoevalpsi.core.ocr`. Cubre la Fase 2 de `plan.md` (paso 7 del pipeline). Prefijo `OC`.

| Fase | Título | Estado |
|---|---|---|
| OC-R0 | Prueba de viabilidad de PP-OCRv6 en ONNX | hecha (2026-11-06) |
| OC-R1 | Lector OCR (detección + reconocimiento + confianza) | bloqueada (OC-D1) |
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

### Informe OC-R0 (2026-11-06)

**Veredicto: PP-OCRv6 medium en ONNX es viable.** Detección y reconocimiento corren con
onnxruntime 1.31.1 CPU, sin PaddlePaddle. Código del spike (descartable): `tools/spike_ocr/`
(`pipeline.py` = preproceso + DB + CTC; `medir.py` = la medición). Modelos en `modelos/pp-ocrv6/`
(fuera de git).

| Pieza | Repo de Hugging Face (rama `main`, 2026-06-18) | Licencia | Tamaño | SHA-256 |
|---|---|---|---|---|
| Detección medium | `PaddlePaddle/PP-OCRv6_medium_det_onnx` · `inference.onnx` | Apache-2.0 | 62 032 837 B | `eb13b44b25bb36f89528b68720af8a61d9cf381176107f465db1757b65d086e1` |
| Reconocimiento medium | `PaddlePaddle/PP-OCRv6_medium_rec_onnx` · `inference.onnx` | Apache-2.0 | 76 554 979 B | `9c09abf0957f7968c7586464b7397b84ad2387a0497a351af40e9acc71b673ba` |

URL: `https://huggingface.co/PaddlePaddle/<repo>/resolve/main/inference.onnx` (+ `inference.yml`,
que trae el diccionario y los parámetros de pre/postproceso). El hash coincide con el que
publica Hugging Face. Para OC-R1 conviene fijar la revisión (commit `61323801…` det,
`50c7eaca…` rec) en el script de descarga, no `main`.

- **Diccionario (OC-03):** 18 708 caracteres (+ blank + espacio = 18 710 clases). Tiene
  `á é í ó ú ü ñ Á É Í Ó Ú Ñ ¿`. **Falta `¡`** (el modelo lo omite al leer; irrelevante para
  observaciones clínicas, anotado). Entradas dinámicas: det `x[N,3,H,W]`, rec `x[N,3,48,W]`.
- **Preproceso usado:** det: lado largo ≤ 960 px, múltiplos de 32, RGB, media/desvío ImageNet;
  umbral 0,2, caja 0,45, unclip 1,4 (del `inference.yml`). Rec: alto 48, ancho proporcional,
  normalización (x/255 − 0,5)/0,5, CTC con blanco = 0.
- **Exactitud** (imagen de 1600 px de ancho, 4 líneas en español con tildes, ñ, ¿ ? °):
  - Impreso (Arial): 4/4 líneas detectadas; texto correcto salvo `¡` (omitido) y `·` leído como
    `:`. Confianza 0,98–1,00.
  - Cursiva de fuente (Ink Free, Segoe Print, Segoe Script) 4 líneas cada una: 12/12 líneas
    detectadas; un solo error (`quiso`→`tranquilo` leído «tranguilo» en Ink Free). Confianza
    0,96–1,00.
  - **Límite de la prueba:** no hay `muestras/` aún y la cursiva de fuente **no es manuscrito
    real**; el acierto con letra de la usuaria sigue sin medirse (OC-02). Lo mide OC-R3.
    Nota: la fuente por defecto de Pillow no tiene acentos y dibuja cuadrados; no usarla en
    pruebas sintéticas de OCR.
- **Latencia** (Docker Desktop, 4 hilos de onnxruntime, mediana de 5 corridas; máquina de
  desarrollo, no la de ella, OC-07): carga de ambos modelos + diccionario **≈ 2,0 s**;
  detección sobre una franja de 1600×320–440 px **0,19–0,28 s**; reconocimiento
  **0,13–0,23 s por línea** (más lento con texto largo). Una hoja con 15–30 líneas: ≈ 0,3 s de
  detección + 2–7 s de reconocimiento, sin los 15–60 s del reconocimiento por fila (OC-05
  confirmado: detectar una vez sobre la franja). Tamaño en disco ≈ 139 MB (a considerar en el
  instalador, DI-R2).
- **Riesgos para OC-R1:** (1) el reconocimiento por línea costó más de lo supuesto ("barato");
  si en el Vivobook pasa de ~0,3 s/línea, evaluar `PP-OCRv6_small_rec_onnx`. (2) Los repos
  small/tiny existen en ONNX y pueden servir de plan B de velocidad. (3) El spike usa PyYAML
  para leer el diccionario: OC-R1 debería exportarlo a un `.txt` verificado por hash.

**Propuesta para OC-D1: a) PP-OCRv6 medium en ONNX** (ONNX oficial, Apache-2.0, diccionario con
español completo salvo `¡`, latencia aceptable). Pendiente solo de la medición con letra real en
OC-R3. La decisión es del responsable.

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

- **OC-D1 — Modelo OCR a usar** (cifras de OC-R0 en su informe arriba; propuesta: a).
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
