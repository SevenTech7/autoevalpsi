# AutoEvalPsi

App local de Windows que convierte fotos de formularios psicológicos en Excel (OMR + OCR).
Producto y decisiones de stack: [plan.md](plan.md).

**Estado y método de trabajo: [docs/planes/autoevalpsi/BITACORA.md](docs/planes/autoevalpsi/BITACORA.md).**
Para retomar: «Continúa según `docs/planes/autoevalpsi/BITACORA.md`». Una fase por sesión; leer
su sección en el `PLAN-*.md` del frente antes de tocar código.

Reglas fijas:
- Modo silencioso: escribir en el chat solo para pedir una decisión, avisar de un contrato
  afectado, un bloqueo o cambios sin explicar; cerrar con una línea.
- Nunca decidir en nombre del responsable (ver §4 de la bitácora).
- Sin tareas automáticas en los equipos (cron, Programador de tareas, autoarranque). Los
  workflows de GitHub Actions están permitidos, sin `schedule:`.
- Nunca commitear `muestras/`, `plantillas/` reales, `modelos/`, `*.onnx`, BD ni fotos.
