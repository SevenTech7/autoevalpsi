# PLAN-SINO — Formularios con «Sí ( ) No ( )», puntajes manuscritos y texto libre

Prefijo `FS`. Origen: el formulario real de la usuaria (neuropsicológico, 2 hojas de muestra en
`muestras/`, fuera de git). A diferencia de «evaluación continua» (tablas con columnas fijas), aquí
cada ítem tiene sus propios paréntesis en posiciones irregulares, a veces dos ítems por renglón, y
cada sección termina con un puntaje escrito a mano (`P.E.E. 1 / leve`). No hay formulario en
blanco: la plantilla se arma desde una foto llena.

| Fase | Título | Estado |
|---|---|---|
| FS-R0 | Spike: ¿el OCR ubica los `( )` de una foto real? | hecha (2026-11-07) |
| FS-R1 | Plantilla v1 desde la foto: una tabla de una fila por ítem + referencia sin marcas | hecha (2026-11-07) |
| FS-R2 | Puntaje manuscrito por sección (OCR de vocabulario cerrado); `contraste_min` por plantilla | pendiente |
| FS-R3 | **Editor de plantilla en la app** (campos, columnas, filas, cajas; sirve para todas las plantillas) | hecha (2026-11-07; falta verlo en la ventana real y probarlo con la usuaria) |
| FS-R4 | Revisión por secciones y Excel «Resumen / Detalle / Escrito a mano» | pendiente (faltan los significados de P.E.E./P.E.C./Intrus./Persev.) |
| FS-R5 | Ítems de texto manuscrito con marca ✓/✗ (6.1, 6.3, 6.6) | pendiente |
| FS-R6 | Referencia limpia a partir de varias fotos llenas (mediana tras registrar) | pendiente (necesita más fotos) |

## FS-R0 — resultado

`tools/sino_desde_foto.py` lee la foto con el OCR (posición de cada carácter por los pasos CTC),
encuentra cada `Si ( ) No ( )`, le pone su texto y su sección y ubica la caja del puntaje.
Sobre las dos fotos de muestra (sin enderezar, tomadas con el celular):

- **Secciones:** 21 de 21 encabezados (tras admitir la letra suelta del margen: «E 5.5 …»).
- **Ítems Sí/No:** 100 encontrados de ≈ 106 contados a ojo (≈ 94 %, con 1 falso en 6.1). Faltan los que el OCR leyó muy sucios
  (`siNo( )`) y algunos en renglones apretados (5.2, 5.4, 5.8, 5.12, 6.4, 6.7).
- **Posición:** las cajas caen sobre los paréntesis con unos ±10 px en fotos de 1200 px; sirven
  para medir tinta, no para dibujar bonito.
- **Puntaje manuscrito:** caja ubicada en las 21 secciones.
- **No es Sí/No:** 6.1, 6.3 y 6.6 son texto escrito a mano con ✓/✗ al lado (FS-R5).
- **Conclusión:** la herramienta propone y una persona corrige; arreglar a mano ≈ 10 % de ≈ 106
  ítems es razonable **si hay un editor visual** (FS-D2); sin él, no.

## Decisiones

- **FS-D1 — Cómo representa el esquema estos ítems. Resuelta: v1 alcanza (FS-R1).**
  - a) `ESQUEMA_VERSION = 2`: la página admite `secciones[]` con `items[]` (texto + cajas por
    opción) y `puntaje` (caja manuscrita), además de las `tablas` actuales, que siguen valiendo.
  - b) Forzar los ítems en la cuadrícula de `tablas` (no encaja: x irregulares).
  - **Recomendación: a)**. Aditivo: las plantillas v1 siguen cargando.
- **FS-D2 — Cómo se corrige la plantilla armada. Aprobada (2026-11-07): editor visual, para campos, columnas y filas de cualquier plantilla.**
  - a) Editor visual en la app: ver la foto con las cajas, mover/agregar/borrar.
  - b) Editar el `.json` a mano con el visor de `tools/visor_plantilla.py`.
  - **Recomendación: a)** (la usuaria no va a editar JSON de 150 ítems).

## FS-R1 — resultado

**El esquema v1 ya representa estos ítems:** cada «Sí ( ) No ( )» es una tabla de **una fila** con
dos columnas (las cajas interiores de los paréntesis). No hizo falta un esquema v2 ni tocar la
lectura (`casillas`), el registro, la revisión ni el Excel. Único cambio de contrato, aditivo:
`Tabla.seccion` (opcional, informativa) para agrupar tablas en secciones.

- `tools/sino_desde_foto.py foto salida/nombre` deja `nombre.json` (borrador), `nombre.png`
  (revisión visual) y `nombre.zip` (plantilla v1 + referencia limpia, listo para importar).
- Referencia limpia: se borra con inpainting la tinta **dentro** de cada caja (las marcas); los
  paréntesis impresos quedan fuera y se descuentan como «impreso».
- Prueba sobre la propia foto: `registro_ok`, Sí/No bien separados (la tinta del «Sí» marcado
  ≈ 0,10–0,25 contra ≈ 0 del «No»; las celdas vacías salen «sin marca»). Casi todas las filas
  salen con `contraste_bajo` porque el trazo de bolígrafo en fotos de celular es más tenue que el
  de la lectura sintética: hay que bajar `contraste_min` para esta plantilla (FS-R2).
- Lo que falta de verdad es **corregir** lo que el OCR no ve o ve mal (≈ 6 %): FS-R3.

## FS-D1 — resuelta por FS-R1

No hace falta esquema v2 (ver arriba).

## FS-R3 — resultado

Pantalla **Plantillas** (`#/plantillas`) y editor (`#/plantillas/<id>`), solo en la laptop.

- **Crear desde una foto** (`POST /api/plantillas/desde-foto`, necesita OCR, ≈ 13 s): arma el
  borrador (`core/borrador.py`) y lo instala como versión 1; luego se abre en el editor.
  También se puede **importar un .zip** desde la misma pantalla.
- **Editor** sobre la imagen en blanco: arrastrar una casilla la mueve (mueve su columna y su
  fila), las esquinas la redimensionan, las flechas mueven de a 1 px (Mayús: 10), los números de
  la caja se escriben. Agregar/quitar preguntas Sí/No, filas, opciones (columnas) y campos de la
  cabecera; renombrar sección, opciones, textos y campos; deshacer/rehacer (Ctrl+Z / Ctrl+Y,
  escribir en un campo cuenta como un paso). Los límites son los del servidor (columnas y filas
  ordenadas y sin solaparse, dentro de la hoja), así que no se puede dejar una plantilla inválida
  arrastrando.
- **Guardar** crea la **versión siguiente** (`POST /api/plantillas/<id>/versiones`); las
  versiones viejas y las evaluaciones que las citan no se tocan. El cliente no puede fijar `id`,
  `version` ni las imágenes. Un borrador sin guardar se conserva en el navegador y se ofrece
  recuperar al volver a abrir.
- **Verificado** en Firefox (Playwright, contra el servidor de prueba): arrastrar movió la
  casilla 38 px, deshacer la devolvió, la esquina ensanchó 11 → 36 px, sin errores de consola.
- **Pendiente:** mover una tabla entera o un grupo de casillas a la vez, y reordenar preguntas
  (hoy el orden es el de creación). No se probó en WebView2.
