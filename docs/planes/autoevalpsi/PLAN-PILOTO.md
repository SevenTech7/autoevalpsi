# PLAN-PILOTO — Piloto de uso real

Cubre la Fase 6 de `plan.md`. Prefijo `PI`.

| Fase | Título | Estado |
|---|---|---|
| PI-R0 | Informe local de correcciones y errores | pendiente |
| PI-R1 | Piloto de 2 semanas | pendiente (humano) |
| PI-R2 | Ajuste de umbrales y lista de mejoras v2 (gate de Fase 6) | pendiente |

---

## Hallazgos

- **PI-01** — El criterio "errores medidos por formulario" solo es posible si la tabla
  `correcciones` existe desde AP-R0 (AP-05) y si se conservan las fotos durante el piloto (AP-D1).
- **PI-02** — Los datos del piloto son clínicos: el análisis se hace **en la laptop de ella** o
  con un informe agregado sin nombres (conteos por formulario, ítem y bandera). Nada de copiar
  la BD a otro equipo sin acuerdo explícito.

---

## PI-R0 — Informe local de correcciones y errores

- **Requiere:** AP-R5, AP-R0.
- **Esfuerzo:** S.
- **Pasos:** comando `autoevalpsi informe-piloto --salida informe.xlsx` que agrega, sin nombres de
  pacientes: evaluaciones por formulario, casillas cambiadas (error silencioso = cambio en fila
  sin bandera), amarillas confirmadas sin cambio (falsas alarmas), observaciones editadas y CER
  aproximado (distancia de edición OCR → confirmado), tiempos de procesamiento.
- **Tests:** sobre una BD sintética con correcciones conocidas, las cifras coinciden.

## PI-R1 — Piloto de 2 semanas

- **Requiere:** DI-R4, PI-R0.
- **Humano:** uso real. El agente prepara una hoja de registro de incidencias (qué pasó, cuándo,
  qué formulario) para lo que no queda en la BD (no conectó el celular, foto rechazada, etc.).

## PI-R2 — Ajuste de umbrales y lista de mejoras v2 (gate de Fase 6)

- **Requiere:** PI-R1 y el informe de PI-R0 entregado por el responsable.
- **Esfuerzo:** M.
- **Pasos:** ajustar CO-02 (umbral de tinta y margen), umbral de confianza OCR y de calidad de foto
  por formulario; correr de nuevo el banco CO-R8 y OC-R3 para confirmar que no aparecen errores
  silenciosos; escribir la lista priorizada de mejoras v2 (editor visual de plantillas, informes de
  texto libre, modelo grande opcional, etc.); decidir AP-D1 definitivo.
- **Criterio de salida (Fase 6 de `plan.md`):** errores medidos por formulario, umbrales
  ajustados y lista de mejoras para v2.
