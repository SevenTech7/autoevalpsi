# PLAN-CORE — Núcleo: registro, casillas y Excel

Paquete `autoevalpsi.core`, sin dependencias de interfaz (BS-04). Cubre la Fase 1 de `plan.md`
(pasos 1–6 y 9 del pipeline) y la identificación de formulario. Prefijo `CO`.

| Fase | Título | Estado |
|---|---|---|
| CO-R0 | Esquema y cargador de plantillas | hecha |
| CO-R1 | Carga de imagen y control de calidad | hecha |
| CO-R2 | Detección de hoja y corrección de perspectiva | hecha |
| CO-R3 | Registro fino contra la plantilla | hecha |
| CO-R4 | Identificación del formulario | pendiente |
| CO-R5 | Lectura de casillas y banderas (OMR) | pendiente |
| CO-R6 | Exportador Excel | bloqueada (CO-D1, CO-D2) |
| CO-R7 | Comando de foto a Excel e imágenes de depuración | pendiente |
| CO-R8 | Banco de validación con fotos reales (gate de Fase 1) | pendiente |

---

## Hallazgos

- **CO-01** — Las fotos del Samsung llegan con orientación EXIF; OpenCV (`imread`) la ignora.
  Sin aplicarla, una foto vertical llega acostada y el registro falla. Aplicar `exif_transpose`
  de Pillow al cargar. *(Nota CO-R1: con OpenCV 5.0.0 `imread` sí la aplica por defecto; se
  mantiene Pillow para no depender de la versión/compilación de OpenCV y poder rechazar formatos.)*
- **CO-02** — "Gana la celda con más tinta" (paso 5) siempre elige una celda, incluso en una fila
  vacía. Hace falta un **umbral absoluto mínimo** de tinta (fila sin marca) y un **margen
  relativo** entre la primera y la segunda celda (doble marca/tachón). Ambos configurables por
  plantilla y ajustables en el piloto (PI-R2).
- **CO-03** — Los campos de cabecera (paciente, fecha) están escritos a mano: necesitan OCR
  (OC-R2). Hasta entonces, la cabecera se completa a mano en la revisión.
- **CO-04** — El ejemplo usa `tamano_px: [2480, 3508]` (A4 a 300 dpi). En Bolivia es común el
  tamaño Carta (2550×3300). El esquema no debe asumir A4; todas las coordenadas son relativas a
  la imagen de referencia de cada página.
- **CO-05** — El esquema de `plan.md` asume **una sola tabla por página** con las mismas opciones
  en todas las filas. Un formulario con secciones o escalas distintas en la misma hoja no cabe.
  Ver CO-D3.
- **CO-06** — "Pendientes para arrancar" deja abierto "un archivo por evaluación, por paciente o
  por formulario", mientras §Salida en Excel ya describe "por evaluación + consolidado por
  formulario". Hay que confirmarlo antes de CO-R6 (CO-D1).
- **CO-07** — El nombre `AAAA-MM-DD_<formulario>_<paciente>.xlsx` pone un dato clínico
  identificable en el nombre del archivo (visible en listados, recientes de Windows, copias) y
  puede tener caracteres inválidos en Windows (`/ \ : * ? " < > |`). Ver CO-D2.
- **CO-08** — Si el consolidado está abierto en Excel, Windows lo bloquea y `openpyxl` falla con
  `PermissionError`. Hay que detectarlo y avisar ("cierra el archivo y reintenta"), sin perder la
  evaluación ya confirmada.
- **CO-09** — Falta una medida de calidad del registro: si la homografía es mala, todas las
  casillas se leen mal sin aviso. El error de reproyección / proporción de inliers debe convertir
  la página entera en "revisión obligatoria".

---

## CO-R0 — Esquema y cargador de plantillas

- **Requiere:** BS-R0, CO-D3.
- **Esfuerzo:** S. **Toca un contrato** (formato de plantilla): fijarlo aquí y versionarlo.
- **Pasos:** modelos pydantic `Plantilla`, `Pagina`, `Tabla`, `Fila`, `CampoCabecera`;
  `cargar_plantilla(ruta)`; validaciones: cajas dentro de `tamano_px`, `len(opciones) ==
  len(columnas_x)`, columnas y filas ordenadas y sin solapes, `item` únicos; campo
  `esquema_version`.
- **Tests:** el JSON de ejemplo de `plan.md` carga; uno inválido por cada regla falla con un
  mensaje que nombra el campo.

## CO-R1 — Carga de imagen y control de calidad

- **Requiere:** CO-R0, BS-R1.
- **Esfuerzo:** S.
- **Pasos:** `cargar_imagen(bytes)` con EXIF (CO-01) y formatos JPEG/PNG (HEIC rechazado con
  mensaje claro); `evaluar_calidad()` → nitidez (varianza del Laplaciano sobre la imagen
  reducida), brillo medio, recorte de altas luces; umbrales en configuración.
- **Tests:** foto sintética nítida pasa; desenfocada y oscura fallan; foto con EXIF rotado
  queda vertical.
- **Hecha (2026-11-06):** `core/imagen.py`: `cargar_imagen(bytes)` → BGR uint8 con
  `exif_transpose` (Pillow), solo JPEG/PNG por firma de bytes, HEIC/HEIF y basura →
  `ImagenInvalida` (subclase de `ValueError`, mensaje para mostrar). `evaluar_calidad(img,
  UmbralesCalidad)` → `InformeCalidad(nitidez, brillo, luces, lado_largo, problemas, ok)`; no
  lanza. Se mide sobre la imagen reducida a 1000 px de lado largo. Umbrales por defecto
  (calibrados con el lote sintético, que tiene ruido): nitidez ≥ 150 (nítidas 750–2300; blur σ=2.5
  a 2400 px → 107; σ=4 → 24), brillo 70–215, luces quemadas ≤ 20 %, lado largo ≥ 1000 px.
  **Pendiente CO-R8:** recalibrar con fotos reales (el ruido sintético infla la nitidez).

## CO-R2 — Detección de hoja y corrección de perspectiva

- **Requiere:** CO-R1.
- **Esfuerzo:** M.
- **Pasos:** contorno del papel (Canny + mayor cuadrilátero convexo) → warp a la proporción de la
  plantilla; si hay 4 marcas ArUco (`cv2.aruco`), usarlas con prioridad; si no se encuentra la
  hoja, devolver error explicable ("no se ve la hoja entera").
- **Tests:** sobre el lote sintético con perspectiva y fondo, las esquinas quedan a ≤ 1 % del
  tamaño de la hoja.
- **Hecha (2026-11-06):** `core/hoja.py`: `detectar_hoja(img, proporcion=None)` →
  `HojaDetectada(esquinas (4,2) TL,TR,BR,BL en px de la foto, metodo)`; `rectificar(img,
  esquinas, (ancho, alto))`; `enderezar_hoja(img, tamano)`. `HojaNoEncontrada` (subclase de
  `ImagenInvalida`) con «No se ve la hoja entera…». **ArUco** primero: `DICT_4X4_50`, ids 0-3 =
  TL/TR/BR/BL, esquina *externa* de cada marca; con marcas incompletas o ids ajenos cae al
  contorno. **Contorno:** Canny + cierre, mayor cuadrilátero convexo del casco (reducido a 1000
  px); si no, máscara Otsu. Rechaza: hoja < 25 % de la foto, esquina a < 0,4 % del borde (hoja
  cortada; no prueba otros candidatos para no devolver la tabla interior) y lados opuestos muy
  distintos. Con `proporcion`, una hoja apaisada se ordena como vertical (giro 90°, un solo
  sentido). Lote sintético: error de esquinas ≤ 1 % del lado de la hoja en las 6 fotos.
  **Para CO-R3:** el giro de 180° y el sentido del giro de 90° no se pueden saber aquí; el
  registro debe probar los giros. **Para PL-R5:** dónde caen las esquinas externas de las marcas
  en la plantilla (margen) se fija al diseñar las hojas reimprimibles. Sin refinamiento
  subpíxel de esquinas (no hizo falta con el lote sintético); revisar con fotos reales (CO-R8).

## CO-R3 — Registro fino contra la plantilla

- **Requiere:** CO-R2.
- **Esfuerzo:** L.
- **Pasos:** ORB + `BFMatcher` + `findHomography(RANSAC)` contra la imagen en blanco; ajuste final
  con las líneas de la tabla (morfología) para corregir desplazamientos residuales; métrica de
  calidad (CO-09).
- **Tests:** error medio en las esquinas de celdas ≤ 3 px a 300 dpi sobre el lote sintético; un
  registro forzado a fallar (imagen de otro formulario) produce la bandera de página.
- **Hecha (2026-11-06):** `core/registro.py`: `registrar(foto, referencia, umbrales=None)` →
  `Registro(homografia foto→plantilla, imagen BGR a tamaño de plantilla, metodo_hoja, giro,
  coincidencias, inliers, proporcion_inliers, error_reproyeccion, cobertura, correlacion_lineas,
  ajuste_lineas, banderas, ok)`; `cargar_referencia(ruta_json, imagen_referencia)`;
  `UmbralesRegistro`; `RegistroInvalido`. Flujo: hoja enderezada (CO-R2) → se prueba 0° y, solo si
  no sale bien, 180° → ORB (CLAHE, 6000 pts, a 1400 px) → **coincidencias locales**: ratio test de
  Lowe solo entre descriptores a < 6 % del lado largo (la hoja ya llega casi alineada; contra toda
  la página las filas repetidas hacían fallar la prueba y los puntos quedaban solo en el título) →
  `findHomography(RANSAC)` → ajuste fino afín con `findTransformECC` entre máscaras de líneas
  largas (apertura morfológica), aceptado solo si sube la correlación y el movimiento es < 2 % →
  **una sola deformación** desde la foto original. Calidad (CO-09): inliers ≥ 40, proporción ≥
  0,30, error de reproyección ≤ 4 px, cobertura (área del casco de inliers / hoja) ≥ 0,35 y
  correlación de líneas ≥ 0,25; si falla algo, `banderas = ("registro_dudoso",)` (`ok` False).
  No lanza por mal registro; sí `HojaNoEncontrada` si no se ve la hoja. **Cifras (lote de 6
  fotos A4):** error medio de esquinas de celdas 0,3–1,6 px a 300 dpi (máx. 3,1 px; criterio ≤ 3
  de media); inliers 840–970, proporción 0,61–0,69, cobertura 0,54–0,70, correlación de líneas
  0,86–0,95. Formulario ajeno: 22 inliers, 21 %, cobertura 0,23, correlación −0,04 (falla por
  todo). Hoja girada 180° y de lado (±90°): se registra y queda derecha.
  **Hallazgos:** (1) con ratio test global y cuadrantes como cobertura, 2 de 6 fotos salían a
  16–26 px de error con error de reproyección de ~2 px: el error de reproyección solo no basta,
  por eso se mide la cobertura. (2) Un formulario real suele tener zonas vacías (aquí, el pie), de
  ahí «área del casco» y no «cuatro cuadrantes». (3) El ajuste con líneas gana ~0,5–1 px donde
  engancha; con ORB solo ya cumple el criterio. **Pendiente CO-R8:** recalibrar umbrales con fotos
  reales (rayados, sombras, hojas arrugadas, tinta que tapa líneas). **Para CO-R4:** `Registro`
  da inliers/proporción como puntaje de identificación contra cada plantilla. **Para CO-R5:**
  leer casillas sobre `Registro.imagen` con las coordenadas de la plantilla; si `not ok`, toda
  la página es revisión obligatoria.

## CO-R4 — Identificación del formulario

- **Requiere:** CO-R3, PL-R4 en curso (con 2+ plantillas tiene sentido).
- **Esfuerzo:** M.
- **Pasos:** QR de la hoja si existe (`cv2.QRCodeDetector`); si no, puntaje ORB contra cada
  plantilla; si el mejor no supera el umbral o el segundo está cerca, devolver "elegir de la
  lista".
- **Tests:** con dos formularios sintéticos distintos, cada foto se asigna bien; una foto ajena
  pide selección manual.

## CO-R5 — Lectura de casillas y banderas (OMR)

- **Requiere:** CO-R3.
- **Esfuerzo:** M.
- **Pasos:** por celda, recorte con margen interior; umbral adaptativo; proporción de tinta;
  decisión por fila con CO-02; banderas `sin_marca`, `doble_marca`, `contraste_bajo`,
  `registro_dudoso`; salida `ResultadoFila(item, opcion|None, proporciones, banderas)`.
- **Tests:** caracterización sobre el lote sintético (X, ✓, círculo, relleno, azul/negro).
  **Test negativo clave:** en ningún caso del lote una fila sale con una opción equivocada **sin**
  bandera (cero errores silenciosos).

## CO-R6 — Exportador Excel

- **Requiere:** CO-R5, CO-D1, CO-D2.
- **Esfuerzo:** M.
- **Pasos:** hoja "Evaluación" (cabecera + tabla con la forma de `plan.md`); columna opcional con
  el recorte como imagen; consolidado por formulario (una fila por evaluación, una columna por
  ítem), creado o ampliado sin duplicar la evaluación (clave = id de evaluación); nombre de
  archivo saneado (CO-07); manejo del archivo bloqueado (CO-08).
- **Tests:** abrir el .xlsx generado con openpyxl y comprobar celdas; reexportar la misma
  evaluación no duplica la fila del consolidado; consolidado bloqueado → error tipado.

## CO-R7 — Comando de foto a Excel e imágenes de depuración

- **Requiere:** CO-R5, CO-R6.
- **Esfuerzo:** S.
- **Pasos:** `autoevalpsi procesar FOTO --plantilla ID --salida DIR [--depuracion]`; con
  depuración, guarda la hoja enderezada con la cuadrícula superpuesta y cada celda coloreada por
  decisión/bandera. `core/pipeline.py` orquesta los pasos y devuelve un resultado serializable
  (lo usará la app).

## CO-R8 — Banco de validación con fotos reales (gate de Fase 1)

- **Requiere:** CO-R7, PL-R1, PL-05 (verdad de terreno).
- **Esfuerzo:** M. **Suite lenta y local** (marcador `real`): se corre al cierre de la Ola 2 y
  cada vez que cambien umbrales.
- **Pasos:** `tools/evaluar_omr.py` recorre `muestras/<formulario>/llena-*.jpg`, compara con
  `verdad.csv` y reporta por foto: correctas, amarillas, **errores silenciosos**.
- **Criterio de salida (Fase 1 de `plan.md`):** con 10 fotos reales, cada casilla correcta o
  amarilla; errores silenciosos = 0. Registrar las cifras en el diario.

---

## Decisiones

- **CO-D1 — Estructura del Excel.**
  - a) Un archivo por evaluación + un consolidado por formulario (lo que describe `plan.md`).
  - b) Un archivo por paciente con una hoja por evaluación.
  - c) Solo el consolidado por formulario.
  - **Recomendación: a)** — es lo ya descrito, sirve para archivar y para analizar.
- **CO-D2 — ¿Nombre del paciente en el nombre del archivo?**
  - a) Sí, saneado: `AAAA-MM-DD_<formulario>_<paciente>.xlsx` (como `plan.md`).
  - b) Iniciales o un código de paciente que ella asigna.
  - **Recomendación: a) saneado y con opción de cambiar a b) en la configuración** — ella
    necesita encontrar los archivos; la carpeta de destino ya está en su equipo cifrado.
- **CO-D3 — ¿Varias tablas por página en el esquema?**
  - a) Esquema plano de `plan.md` (una tabla por página).
  - b) `paginas[].tablas[]`, cada una con sus `opciones`, `columnas_x`, `observacion_x` y
    `filas`; el formato plano se sigue aceptando como atajo de una sola tabla.
  - **Recomendación: b)** — cuesta poco ahora y evita romper el contrato cuando aparezca el
    primer formulario con secciones.
  - **Decisión (2026-11-06): b) `paginas[].tablas[]`, con el formato plano como atajo.**
