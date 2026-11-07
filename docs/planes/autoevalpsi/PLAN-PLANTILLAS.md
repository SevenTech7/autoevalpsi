# PLAN-PLANTILLAS — Muestras y plantillas de formularios

Cubre la Fase 0 (muestras) y la Fase 4 (resto de plantillas) de `plan.md`. Prefijo `PL`.

| Fase | Título | Estado |
|---|---|---|
| PL-R0 | Recepción de muestras y lista priorizada (Fase 0) | pendiente (insumos de la usuaria) |
| PL-R1 | Plantilla del primer formulario y visor de plantillas | hecha (referencia derivada de una foto llena) |
| PL-R2 | Script de detección de cuadrícula | pendiente |
| PL-R3 | Lectura de los textos impresos de los ítems | pendiente |
| PL-R4 | Plantillas de los formularios restantes | pendiente |
| PL-R5 | Hojas reimprimibles con marcas ArUco y QR | bloqueada (PL-D1) |

---

## Hallazgos

- **PL-01** — Los dos primeros insumos de "Pendientes para arrancar" (fotos en blanco y fotos
  llenas) bloquean toda validación real. El núcleo puede avanzar con el formulario sintético
  (BS-R1), pero CO-R8 y PL-R1 no.
- **PL-02** — Las plantillas e imágenes de referencia pueden tener derechos de autor
  (`plan.md` §Plantillas). Eso choca con un build en GitHub Actions que las empaquete (DI-R3).
  Ver PL-D2.
- **PL-03** — No se sabe si hay formularios de más de una hoja. El esquema ya lo soporta
  (`paginas`), pero la app debe agrupar fotos en una evaluación (AP-R1) solo si hace falta.
- **PL-04** — Identificar el formulario por QR (`plan.md` paso 3) solo es posible si las hojas se
  reimprimen (PL-D1). Sin eso, la identificación es por ORB o manual (CO-R4).
- **PL-05** — Para el criterio de la Fase 1 ("cero errores silenciosos") cada foto llena necesita
  su verdad de terreno: qué casilla se marcó en cada fila. Alguien debe anotarla al llenar la
  hoja o transcribirla después; sin eso no se puede medir nada.

---

## PL-R0 — Recepción de muestras y lista priorizada (Fase 0)

- **Requiere:** insumos de la usuaria (fotos). La parte del agente no depende de ellos.
- **Esfuerzo:** S para el agente; 1 día de la usuaria.
- **Pasos del agente:**
  1. `muestras/README.md` (versionado) con la estructura `muestras/<formulario>/blanco.jpg`,
     `llena-01.jpg`, `llena-01.verdad.csv` y una guía de toma de fotos (de frente, luz pareja,
     hoja entera, sin flash).
  2. `tools/revisar_muestras.py`: lista resolución, nitidez (varianza del Laplaciano), brillo y
     orientación EXIF de cada foto; marca las que convendría repetir.
  3. Plantilla de `verdad.csv` (`item,opcion,observacion`) para PL-05.
  4. Registrar en este plan la lista priorizada de formularios (solo nombres y número de
     páginas/ítems; sin imágenes).
- **Pasos humanos:** fotos de 3–5 formularios en blanco y llenos; responder PL-D1; confirmar si hay
  formularios multipágina; versión de Windows de la laptop.
- **Criterio de salida:** carpeta de muestras completa y lista priorizada (criterio de `plan.md`).

## PL-R1 — Plantilla del primer formulario y visor de plantillas

- **Requiere:** PL-R0, CO-R0, PL-D2.
- **Estado:** hecha (2026-11-07), con una salvedad: no había formulario en blanco, así que la
  referencia se derivó de `muestras/evaluacion-continua-llena-1.jpeg` (enderezada con el borde de la
  tabla, ×2; sin las X, los valores de cabecera ni las rayas del margen, por relleno de imagen).
  Plantilla `evaluacion-continua` v1 (12 ítems en 4 tablas de 3 filas, 6 columnas «1 Nula»…«6
  Excelente», sin observación, 5 campos: paciente, cargo, oficina, fecha, motivo), en
  `plantillas/evaluacion-continua/` (fuera de git, PL-D2) y como .zip lista para importar.
  `tools/visor_plantilla.py` (con test). Medido contra mi lectura de la foto (verdad 5,5,5,5,5,5,4,5,5,6,5,4;
  **pendiente que la confirme el responsable**): **12/12** casillas, cabecera 4/4 exacta con OCR, también
  con otra foto del mismo formulario (A07, 4080 px, de lado). `omr.tinta_minima` = 0,003 (las X
  dan 0,005–0,012 y todo lo demás 0). Todas las filas salen con `contraste_bajo` (trazo claro, umbral
  global de `ParametrosLectura`): amarillas pero con la opción correcta. Con un formulario en blanco
  hay que rehacer la referencia (las coordenadas de la plantilla se mantienen si se endereza igual).
- **Esfuerzo:** M.
- **Pasos:**
  1. `tools/visor_plantilla.py`: superpone sobre la imagen en blanco las cajas de cabecera,
     columnas, filas y zona de observación, con el número de ítem; guarda PNG de control.
  2. Escribir a mano el JSON del primer formulario priorizado, iterando con el visor.
  3. Validarlo con el cargador de CO-R0.
- **Criterio de salida:** el visor muestra todas las cajas alineadas sobre la hoja en blanco.

## PL-R2 — Script de detección de cuadrícula

- **Requiere:** PL-R1 (para comparar contra una plantilla hecha a mano), CO-R2.
- **Esfuerzo:** M.
- **Pasos:** morfología de OpenCV (aperturas horizontales y verticales) para extraer líneas,
  agrupar en filas y columnas, proponer `filas[].y`, `columnas_x` y `observacion_x`; emitir un JSON
  borrador y el PNG del visor.
- **Tests:** sobre el formulario sintético, la cuadrícula propuesta difiere ≤ 5 px de la real;
  sobre el primer formulario real (marcador `real`), contra la plantilla de PL-R1.

## PL-R3 — Lectura de los textos impresos de los ítems

- **Requiere:** PL-R2, OC-R1.
- **Esfuerzo:** S.
- **Pasos:** recortar la columna de descripción de cada fila detectada y pasarla por el lector OCR;
  rellenar `filas[].texto` en el borrador para corrección manual.

## PL-R4 — Plantillas de los formularios restantes (Fase 4)

- **Requiere:** PL-R2, PL-R3, CO-R4.
- **Esfuerzo:** L — **una sesión por formulario**; anotar en el diario cuál se cerró.
- **Pasos por formulario:** borrador con PL-R2/PL-R3 → corrección manual → visor → banco de
  validación de CO-R8 con sus fotos llenas.
- **Criterio de salida:** todos los formularios priorizados pasan el banco de CO-R8 con cero
  errores silenciosos.

## PL-R5 — Hojas reimprimibles con marcas ArUco y QR

- **Requiere:** PL-D1 = sí, CO-R2 (lectura de ArUco), CO-R4 (lectura del QR).
- **Esfuerzo:** M.
- **Pasos:** `tools/reimprimir.py` agrega cuatro marcas ArUco en las esquinas y un QR con
  `id`+`version`+`pagina` en un margen libre del PDF/imagen original, y actualiza la plantilla con
  las posiciones. Solo para uso de la usuaria con sus propios impresos.

---

## Decisiones

- **PL-D1 — ¿Se reimprimen las hojas con marcas en las esquinas y QR?**
  - a) Sí: alineación y detección de formulario casi infalibles; requiere imprimir hojas nuevas.
  - b) No: todo por contorno de hoja + ORB; más frágil con fotos malas.
  - **Recomendación: a) para los formularios que ella imprime**, manteniendo b) como camino que
    siempre funciona (v1 no puede depender de hojas reimpresas).
- **PL-D2 — ¿Dónde viven las plantillas reales y sus imágenes de referencia?**
  - a) En el repo privado de código, empaquetadas en el instalador.
  - b) Fuera del repo de código (carpeta local o un repo privado aparte); la app las **importa**
    desde un archivo `.zip` a `%LOCALAPPDATA%\AutoEvalPsi\plantillas` en el primer uso.
  - **Recomendación: b)** — el instalador y el build de CI no contienen material con derechos, y
    agregar un formulario nuevo no exige reinstalar. Afecta a AP-R1 (endpoint de importación) y
    DI-R1.
