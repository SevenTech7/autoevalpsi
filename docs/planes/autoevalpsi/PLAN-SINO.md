# PLAN-SINO — Formularios con «Sí ( ) No ( )», puntajes manuscritos y texto libre

Prefijo `FS`. Origen: el formulario real de la usuaria (neuropsicológico, 2 hojas de muestra en
`muestras/`, fuera de git). A diferencia de «evaluación continua» (tablas con columnas fijas), aquí
cada ítem tiene sus propios paréntesis en posiciones irregulares, a veces dos ítems por renglón, y
cada sección termina con un puntaje escrito a mano (`P.E.E. 1 / leve`). No hay formulario en
blanco: la plantilla se arma desde una foto llena.

| Fase | Título | Estado |
|---|---|---|
| FS-R0 | Spike: ¿el OCR ubica los `( )` de una foto real? | hecha (2026-11-07) |
| FS-R1 | Esquema de plantilla v2 (ítems con cajas propias, puntaje por sección) | bloqueada (FS-D1) |
| FS-R2 | Lectura de esas cajas (OMR) y del puntaje (OCR de vocabulario cerrado) | pendiente |
| FS-R3 | Armar la plantilla desde la foto + editor para corregirla | bloqueada (FS-D2) |
| FS-R4 | Revisión por secciones y Excel «Resumen / Detalle / Escrito a mano» | pendiente |
| FS-R5 | Ítems de texto manuscrito con marca ✓/✗ (6.1, 6.3, 6.6) | pendiente |

## FS-R0 — resultado

`tools/sino_desde_foto.py` lee la foto con el OCR (posición de cada carácter por los pasos CTC),
encuentra cada `Si ( ) No ( )`, le pone su texto y su sección y ubica la caja del puntaje.
Sobre las dos fotos de muestra (sin enderezar, tomadas con el celular):

- **Secciones:** 21 de 21 encabezados (tras admitir la letra suelta del margen: «E 5.5 …»).
- **Ítems Sí/No:** 100 encontrados de ≈ 112 (≈ 90 %). Faltan los que el OCR leyó muy sucios
  (`siNo( )`) y algunos en renglones apretados (5.2, 5.4, 5.8, 5.12, 6.4, 6.7).
- **Posición:** las cajas caen sobre los paréntesis con unos ±10 px en fotos de 1200 px; sirven
  para medir tinta, no para dibujar bonito.
- **Puntaje manuscrito:** caja ubicada en las 21 secciones.
- **No es Sí/No:** 6.1, 6.3 y 6.6 son texto escrito a mano con ✓/✗ al lado (FS-R5).
- **Conclusión:** la herramienta propone y una persona corrige; arreglar a mano ≈ 10 % de 150
  ítems es razonable **si hay un editor visual** (FS-D2); sin él, no.

## Decisiones

- **FS-D1 — Cómo representa el esquema estos ítems.**
  - a) `ESQUEMA_VERSION = 2`: la página admite `secciones[]` con `items[]` (texto + cajas por
    opción) y `puntaje` (caja manuscrita), además de las `tablas` actuales, que siguen valiendo.
  - b) Forzar los ítems en la cuadrícula de `tablas` (no encaja: x irregulares).
  - **Recomendación: a)**. Aditivo: las plantillas v1 siguen cargando.
- **FS-D2 — Cómo se corrige la plantilla armada.**
  - a) Editor visual en la app: ver la foto con las cajas, mover/agregar/borrar.
  - b) Editar el `.json` a mano con el visor de `tools/visor_plantilla.py`.
  - **Recomendación: a)** (la usuaria no va a editar JSON de 150 ítems).
