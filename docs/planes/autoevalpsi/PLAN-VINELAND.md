# PLAN-VINELAND — Hoja de respuestas con dígitos manuscritos y Excel «de la usuaria»

Prefijo `VD`. Origen: el formulario que la usuaria **usará siempre** (Vineland-3, hoja de
respuestas de 2 caras) y su libro de Excel de muestra (`muestras/VINELAND 3 BOL DIGITAL.xlsx`, fuera
de git). La usuaria aclaró: el Excel es el **modelo de salida** (hay que basarse en él) y las fotos
pueden ser de otro paciente pero tienen el mismo formato.

## Cómo es el formulario

- Cada ítem es una celda con un **dígito escrito a mano**: 0, 1 o 2 (también aparece un «?» y
  notas). Las áreas son columnas de celdas numeradas: 1 Escuchar (1–39), 2 Hablar (1–49), 3 Leer
  y escribir, 4 Cuidarse a sí mismo (1–55), 5 Cuidar el hogar (1–30), 6 Vivir en la comunidad
  (1–58) en el frente; 7 Relacionarse, 8 Jugar, 9 Adaptarse y 10 Comportamientos problemáticos
  (A, B, C) en el reverso.
- Una celda azul marca el ítem de inicio; los ítems anteriores quedan en blanco en el papel.

## Cómo es el Excel de muestra

- Una columna por subárea (A…I = áreas 1–9), una fila por ítem (fila n = ítem n), y en la fila 59
  la suma (`=SUM(A1:A39)`…). Los ítems anteriores al de inicio van con **2** (p. ej. Escuchar 1–22
  = 2); los posteriores al último escrito quedan vacíos.
- Debajo, tablas que la usuaria escribe a mano con ayuda del manual y la edad: puntaje v-scale
  (I63:I71), clasificación (K63:K71), sumas (I75:I77) y puntajes estándar (J75:J79).
- J/K/L parecen ser las letras de «Comportamientos problemáticos».

## Decisiones tomadas (con lo dicho por la usuaria)

- **VD-D1 — La salida es el libro de la usuaria.** La app llena una **copia de su .xlsx** (ítem →
  celda), conservando fórmulas y formato; no genera otro diseño. Supuesto a confirmar: los valores
  escritos a mano de la muestra (v-scale, puntajes estándar, clasificaciones) son del paciente de
  la muestra, así que en la copia se vacían y los completa ella; las sumas (`SUM`) se recalculan
  solas al abrir.
- **VD-D2 — Ítems en blanco (corregida por la usuaria, 2026-11-07).** Una celda vacía **queda
  vacía**: no se rellena con 2 ni con nada (como en la hoja de papel). Pero **se avisa**, igual que
  cuando una marca no es nítida: la fila sale con el aviso «La celda está vacía» y hay que
  confirmarla (vacía). Un «?» o cualquier cosa que no sea un dígito permitido **no se adivina**:
  va a revisión. (La muestra de Excel traía los ítems previos al de inicio con 2: eso lo escribió la
  evaluadora; la app no lo inventa.)
- **VD-D3 — Contratos aditivos aprobados (2026-11-07, «ok»):** `Tabla.tipo`, `Fila.celda` y el libro
  base. Los valores escritos a mano de la muestra (v-scale, puntajes estándar, clasificación) se
  vacían en la copia y los completa ella.

## Fases

| Fase | Título | Estado |
|---|---|---|
| VD-R0 | Spike: ¿se leen los dígitos 0/1/2 con el OCR restringido? | hecha (2026-11-07) |
| VD-R1 | Tabla de dígitos (`Tabla.tipo = "digito"`, una columna, una fila por ítem) y su lectura | hecha (2026-11-07) |
| VD-R2 | Detectar la cuadrícula en la foto y armar la plantilla (borrador editable en el editor) | hecha (2026-11-07) |
| VD-R3 | Exportar en el libro de la usuaria (`Fila.celda` + libro base, reglas de blancos) | hecha (2026-11-07) |
| VD-R4 | Reverso: áreas 7–10 y letras A/B/C | pendiente |

## VD-R0 — resultado

Sobre la foto del frente (luz amarilla, hojas debajo, sin enderezar):

- El OCR actual ya encuentra los números impresos de ítem y la mayoría de los dígitos.
  Sin restringir, confunde algunos con «A», «乙», «O».
- Con el reconocedor **restringido a {0, 1, 2}** (renormalizar las probabilidades de esas tres
  clases y el blanco) los dígitos de celdas bien ubicadas se leyeron bien: p. ej. Escuchar 19–30 →
  2 2 2 2 1 1 2 1 2 2 1 2, igual que a ojo. Con umbral de confianza, lo dudoso se marca.
- **Lo que no funcionó:** ubicar las celdas solo con los números del OCR. Mezcla columnas de
  etiquetas con columnas de dígitos (18 «columnas» halladas contra 11 reales). Hay que detectar
  la **cuadrícula** (líneas de la tabla) y tomar como etiqueta la celda cuyo contenido es un
  número ascendente.
- **Riesgos:** tachaduras y dígitos sobrescritos (p. ej. un 1 remarcado), 1 escrito con
  base, «?», celdas azules (el relleno sube la tinta de fondo), hojas curvas.
- **Conclusión:** viable. El cuello de botella es la detección de la cuadrícula (VD-R2) y el
  editor para corregir lo que falle (ya existe).

## Contratos que se tocarían (aditivos, a confirmar)

- `Tabla.tipo: "marcas" | "digito"` (por defecto «marcas»; con «digito», `opciones` son los
  dígitos permitidos y hay una sola columna).
- `Fila.celda: str | None` (celda del libro de Excel, p. ej. `"A19"`) y `Plantilla.libro` (archivo
  base y celdas a vaciar). El editor ganaría un campo «Celda del Excel».

## VD-R1 — resultado

- **Esquema:** `Tabla.tipo: "marcas" | "digito"` (por defecto «marcas»; las plantillas v1 siguen
  igual). Con «digito»: una sola columna (la celda del número) y `opciones` = dígitos permitidos.
- **Lectura:** `LectorONNX.leer_digito(recorte, permitidos)` renormaliza el reconocedor sobre el
  blanco y los dígitos permitidos (probado con el modelo real: 0, 1 y 2 en tipografía manuscrita
  bien; una letra o una celda en blanco no dan confianza). `casillas._leer_digitos` mide la tinta
  de cada celda (sin cuadrícula ni impreso) y decide, sin adivinar:
  - sin tinta → opción vacía + `celda_vacia`;
  - tinta y lectura segura → el dígito, sin aviso;
  - lectura poco segura → el dígito propuesto + `ocr_digito_dudoso`;
  - tinta pero ilegible → vacía + `ocr_digito_ilegible`;
  - sin lector de texto → vacía + `ocr_sin_lector`.
- **Revisión:** cada celda con número guarda su recorte y la tabla muestra la columna «Lo escrito»
  para compararlo; la tecla es el número mismo (0, 1, 2) y Borrar/Supr deja «sin respuesta». Las
  celdas vacías se confirman vacías (sin inventar valor). Avisos con su texto en español.
- **Editor:** una tabla de dígitos no deja agregar ni quitar columnas.
- **Pruebas:** 12 de Python (10 con lector falso + 3 con el modelo real, marcador `lento`) y 5 de la
  interfaz. Suites completas en verde (428 Python, 132 interfaz).

## VD-R2 — resultado

`core/cuadricula.py` + `core/borrador.plantilla_automatica` (la usa «Crear una plantilla desde una
foto»: si ve una cuadrícula de celdas numeradas arma tablas de dígitos; si no, busca «Sí ( ) No ( )»).

- **Celdas:** son los huecos cerrados que dejan las líneas (binarización adaptativa, robusta a la
  luz amarilla y a la sombra), filtrados por tamaño relativo a la foto.
- **Columnas:** se arman de arriba abajo encadenando celdas, así siguen una columna inclinada (el
  borde derecho de la hoja de la foto está torcido). Las celdas que no dan hueco (relleno azul de
  la evaluadora) se completan por la separación entre filas.
- **Etiquetas y respuestas:** `LectorONNX.leer_numero` (OCR restringido a 0-9) lee el número
  impreso de cada celda; una columna que cuenta 1, 2, 3… es de etiquetas (la numeración se corrige
  votando con todas las lecturas) y su vecina de la derecha es la de respuestas. El título de cada
  sección sale de la celda de encabezado que cubre la columna.
- **Plantilla:** una tabla de dígitos por columna de respuestas (una columna inclinada se parte en
  tablas rectas) y una referencia con lo escrito a mano borrado. Es un borrador: se corrige en el
  editor.
- **Resultado en las dos fotos de muestra:** frente → 11 columnas de respuestas (1-30 y 31-39,
  1-30 y 31-49, …, 31-58), reverso → 9 (7, 8, 9 y las tres de «Comportamientos problemáticos»), con
  la numeración exacta. Leyendo la misma foto con su propia plantilla: reverso, columna de
  «Relacionarse con otros» (43 ítems) y «Jugar y usar el tiempo libre» como se ven a ojo; frente,
  «Escuchar y entender» 19-39 igual salvo el ítem 24 (un 1 sobrescrito).
- **Lectura de la celda (cambio):** se mira solo el **interior** de la celda (sin el borde con la
  cuadrícula) y el contraste mínimo de la tinta se mide contra el papel (con sombra el lápiz apenas
  baja 30 niveles). Ya no depende de la referencia, que en fotos con poca luz no separaba bien lo
  impreso.
- **Pruebas:** 10 de lógica pura, 2 con el lector real sobre una hoja dibujada (`lento`) y 1 sobre
  la foto real del reverso (`real`, solo local). Suite completa: 435 de Python en verde.
- **Límites conocidos:** una hoja curva se parte en muchas tablas pequeñas; el encabezado de una
  sección puede salir vacío si su celda no se detecta (se llama «Columna N»); el nombre del
  paciente, escrito a mano arriba, no se ubica solo (se agrega como campo en el editor).

## VD-R3 — resultado

- **Esquema (aditivo):** `Fila.celda` («A19») y `Plantilla.libro` (`archivo`, `hoja`, `vaciar`:
  rangos). Las celdas no pueden repetirse; sin `libro`, se ignoran.
- **Exportar:** `core/libro.py` abre una **copia** del libro de la usuaria, vacía los rangos de
  `vaciar` (nunca una fórmula), escribe cada ítem en su celda (un dígito como número; sin respuesta
  → vacía) y agrega la hoja «AutoEvalPsi» (paciente, fecha, formulario, campos de la cabecera). Las
  sumas se recalculan al abrir. El consolidado sigue siendo el genérico.
- **Libro base:** `POST /api/plantillas/{id}/libro` (versión nueva). El servidor **propone** qué se
  vacía: el rectángulo de los ítems, los números escritos a mano fuera de él y los textos cortos
  junto a un número o fórmula (clasificaciones). Sobre el libro de muestra propuso
  `A1:L58, I63:I71, J75:J77, J79, K63:K71, K79`: justo lo que la usuaria llena a mano; los
  rótulos y las fórmulas quedan. Se corrige en el editor («Libro de Excel»).
- **Varias hojas:** `POST /api/plantillas/{id}/paginas` arma otra página desde otra foto (el
  reverso), continuando la numeración de ítems y la columna del libro (una por área; un bloque que
  vuelve a empezar en 1 abre columna nueva, el 31… sigue en la misma: A…F en el frente, G…I y J…L
  en el reverso).
- **Editor:** campo «Celda del Excel» por fila (si hay libro), lista de rangos que se vacían, subir
  el libro y agregar una página (piden no tener cambios sin guardar).
- **Prueba de punta a punta con el material real** (servidor de prueba): frente + reverso → plantilla
  de 2 páginas (427 celdas) + libro de la muestra → las dos fotos leídas → exportar. El Excel sale
  con los dígitos en sus columnas (A…L) y filas, `=SUM` y `=A59` intactos, los valores a mano de la
  muestra vaciados y «AutoEvalPsi» con el paciente.
- **Ajustes de lectura que salieron de esa prueba:** una columna se parte en tablas rectas cada vez
  que su celda se desvía más de 6 % del ancho de la primera del tramo; el contraste mínimo de la
  tinta es `max(20, 0,15 × papel)` (el lápiz fino del área 6 solo baja ~40 niveles sobre un papel de
  177). Resultado leyendo la misma foto con su plantilla: frente 85 celdas vacías (hay ≈ 80 de
  verdad), el resto con dígito; reverso 158 de 158 con dígito. Algunas celdas con lápiz muy fino
  aún salen «vacía» (se avisa y se ve el recorte).
- **Pruebas:** 10 del libro, 4 del servidor (libro, exportación, página) y 7 de la interfaz; suites
  completas en verde (449 de Python, 139 de la interfaz).
- **Pendiente (VD-R4):** nombre del paciente y las letras A/B/C como campos; hoja curva muy
  distinta de la de referencia (hoy se parte en muchas tablas).
