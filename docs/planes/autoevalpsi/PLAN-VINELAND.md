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
- **VD-D2 — Ítems en blanco.** Siguiendo la muestra: los blancos **antes** del primer dígito de
  una columna valen 2; los posteriores al último dígito quedan vacíos; un blanco en medio queda
  vacío y marcado para revisar. Un «?» o cualquier cosa que no sea 0/1/2 **no se adivina**: va a
  revisión.

## Fases

| Fase | Título | Estado |
|---|---|---|
| VD-R0 | Spike: ¿se leen los dígitos 0/1/2 con el OCR restringido? | hecha (2026-11-07) |
| VD-R1 | Tabla de dígitos (`Tabla.tipo = "digito"`, una columna, una fila por ítem) y su lectura | pendiente |
| VD-R2 | Detectar la cuadrícula en la foto y armar la plantilla (borrador editable en el editor) | pendiente |
| VD-R3 | Exportar en el libro de la usuaria (`Fila.celda` + libro base, reglas de blancos) | pendiente |
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
