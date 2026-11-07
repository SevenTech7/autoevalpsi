# BITÁCORA DE EJECUCIÓN — AutoEvalPsi v1

> **Fuente única del estado de ejecución.** Para retomar después de `/clear`, pedir:
>
> **«Continúa según `docs/planes/autoevalpsi/BITACORA.md`»**
>
> El detalle de cada fase está en el `PLAN-*.md` de su frente; aquí solo viven el orden, el
> estado y el diario. El documento de producto es [`plan.md`](../../../plan.md) (objetivo,
> decisiones de stack, pipeline, riesgos); no se repite aquí.

---

## 1. Estado actual

| Campo | Valor |
|---|---|
| Última actualización | 2026-11-07 |
| Fase en curso | — |
| Siguiente acción | BS-R0, CO-R0, BS-R1, CO-R1, CO-R2, CO-R3, CO-R5, CO-R6, CO-R7, OC-R0, OC-R1, OC-R2, AP-R0, AP-R1, AP-R2, AP-R3, AP-R3b, AP-R4, AP-R5, AP-R6 y PL-R1 (referencia derivada de una foto llena) hechas; DI-R0 parcial (medida en Linux; el cierre exige Windows: `windows-latest` tras B-2, o a mano). **Siguiente: AP-R7** (prueba de aceptación con la usuaria, humana: el agente solo prepara el guion de una página y la lista de observaciones; ella procesa una hoja del celular al Excel). Sin fase de código libre salvo PI-R0. OC-R3 y PL-R0 esperan las fotos en blanco y la verdad de la usuaria. BS-R2 espera B-2. Pendiente humano: P-5. |
| Rama base | `main` (decisión B-1, aprobada 2026-11-06) |
| Bloqueos activos | Insumos de la usuaria (fotos) bloquean PL-R0; B-2 (repo GitHub) bloquea BS-R2 |
| Fases hechas | 21 de 38 (BS-R0, CO-R0, BS-R1, CO-R1, CO-R2, CO-R3, CO-R5, CO-R6, CO-R7, OC-R0, OC-R1, OC-R2, AP-R0, AP-R1, AP-R2, AP-R3, AP-R3b, AP-R4, AP-R5, AP-R6, PL-R1); DI-R0 parcial |

> Al cerrar o pausar una fase, actualizar esta tabla primero.

---

## 2. Protocolo para reanudar

1. Leer esta bitácora: §1, la última entrada de §6 y §4.
2. `git branch --show-current` y `git status`. Cambios sin explicar: detenerse y preguntar.
3. Elegir la primera fase pendiente con dependencias hechas y decisiones aprobadas. Si está
   bloqueada, saltarla y anotarlo. Nunca decidir en nombre del responsable.
4. Leer la fase en su plan y el código que toca, completos.
5. Rama propia desde `main`, con el nombre de la columna "Rama".
6. Línea base de la suite antes de tocar nada (`pytest -m "not real"`). Fallos preexistentes:
   ninguno (todavía no hay suite).
7. Tests primero (caracterización y test negativo), después el cambio, después la suite.
   Suites lentas — banco de fotos reales (`-m real`), OCR con modelo real (`-m lento`), build de
   PyInstaller/instalador: durante las fases solo lo enfocado; la corrida completa una vez al
   cierre de cada ola. El diario anota «completo diferido al cierre de la Ola N».
8. Contrato público afectado (esquema de plantilla, esquema de BD, API HTTP, formato del Excel):
   detenerse y reportar.
9. Cerrar: plan del frente, esta bitácora (§3, §1, §6), [README](README.md), commit en la rama
   y fusión a `main`. Push solo si se pide.
10. Una fase por sesión.

Estados: `pendiente` · `en curso` · `parcial` · `hecha` · `bloqueada (decisión)` · `no aplica (motivo)`.

### Preferencia de comunicación del responsable

**Silencioso** (elegido 2026-11-06): solo escribir en el chat para pedir una decisión, avisar de un
contrato afectado, un bloqueo o cambios sin explicar en el árbol; cerrar cada sesión con una línea.

---

## 3. Orden de ejecución

Equivalencia con `plan.md`: Fase 0 = PL-R0 · Fase 1 = Ola 2 · Fase 2 = Ola 3 · Fase 3 = Ola 4 ·
Fase 4 = Ola 5 · Fase 5 = Ola 6 · Fase 6 = Ola 7. Esfuerzo: S ≈ ½ día, M ≈ 1 día, L ≈ 2 días.

### Ola 0 — Preparación

| # | Paso | Detalle | Estado |
|---|---|---|---|
| P-1 | `git init`, commitear `plan.md` y planes | Hecho 2026-11-06; incluye `.gitignore` mínimo (BS-R0 lo completa) | hecha |
| P-2 | Resolver cambios ajenos sin commitear | No aplica: carpeta nueva, solo `plan.md` | no aplica (repo nuevo) |
| P-3 | Fijar rama base | Decisión B-1: `git init -b main` | hecha |
| P-4 | `CLAUDE.md` con una línea que apunte a esta bitácora | BS-05 | hecha |
| P-5 | Repo privado en GitHub y `git remote add` | Lo crea el responsable (B-2) | pendiente (humano) |

### Ola 1 — Cimientos y riesgos que pueden tumbar el plan

Se atacan primero el OCR sin probar (OC-01) y el empaquetado (DI-01), porque si fallan cambian
el diseño. PL-R0 depende de la usuaria y corre en paralelo.

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 1 | [BS-R0](PLAN-BASE.md#bs-r0--esqueleto-del-repo-y-entorno) | BS-01, BS-04 | `fase-bs-0` | P-1, BS-D1 | S | hecha |
| 2 | [CO-R0](PLAN-CORE.md#co-r0--esquema-y-cargador-de-plantillas) | CO-04, CO-05 | `fase-co-0` | BS-R0, CO-D3 | S | hecha |
| 3 | [BS-R1](PLAN-BASE.md#bs-r1--formulario-sintético-y-generador-de-fotos-de-prueba) | BS-02 | `fase-bs-1` | CO-R0 | M | hecha |
| 4 | [OC-R0](PLAN-OCR.md#oc-r0--prueba-de-viabilidad-de-pp-ocrv6-en-onnx) | OC-01, OC-03, OC-05 (medición) | `fase-oc-0` | BS-R0 | M | hecha |
| 5 | [DI-R0](PLAN-DIST.md#di-r0--prueba-temprana-de-empaquetado-spike) | DI-01 | `fase-di-0` | BS-R0 | M | parcial (falta Windows) |
| 6 | [BS-R2](PLAN-BASE.md#bs-r2--ci-de-tests-en-github-actions) | — | `fase-bs-2` | BS-R0, P-5 | S | pendiente |
| 7 | [PL-R0](PLAN-PLANTILLAS.md#pl-r0--recepción-de-muestras-y-lista-priorizada-fase-0) | PL-01, PL-05 | `fase-pl-0` | insumos de la usuaria | S | pendiente |

### Ola 2 — Núcleo de casillas (Fase 1)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 8 | [CO-R1](PLAN-CORE.md#co-r1--carga-de-imagen-y-control-de-calidad) | CO-01 | `fase-co-1` | CO-R0, BS-R1 | S | hecha |
| 9 | [CO-R2](PLAN-CORE.md#co-r2--detección-de-hoja-y-corrección-de-perspectiva) | — | `fase-co-2` | CO-R1 | M | hecha |
| 10 | [CO-R3](PLAN-CORE.md#co-r3--registro-fino-contra-la-plantilla) | CO-09 | `fase-co-3` | CO-R2 | L | hecha |
| 11 | [CO-R5](PLAN-CORE.md#co-r5--lectura-de-casillas-y-banderas-omr) | CO-02 | `fase-co-5` | CO-R3 | M | hecha |
| 12 | [CO-R6](PLAN-CORE.md#co-r6--exportador-excel) | CO-06, CO-07, CO-08 | `fase-co-6` | CO-R5, CO-D1, CO-D2 | M | hecha |
| 13 | [CO-R7](PLAN-CORE.md#co-r7--comando-de-foto-a-excel-e-imágenes-de-depuración) | — | `fase-co-7` | CO-R6 | S | hecha |
| 14 | [PL-R1](PLAN-PLANTILLAS.md#pl-r1--plantilla-del-primer-formulario-y-visor-de-plantillas) | — | `fase-pl-1` | PL-R0, CO-R0, PL-D2 | M | hecha (referencia derivada) |
| 15 | [CO-R8](PLAN-CORE.md#co-r8--banco-de-validación-con-fotos-reales-gate-de-fase-1) | gate Fase 1 | `fase-co-8` | CO-R7, PL-R1 | M | pendiente |

### Ola 3 — Observaciones (Fase 2)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 16 | [OC-R1](PLAN-OCR.md#oc-r1--lector-ocr) | OC-04, OC-06 | `fase-oc-1` | OC-R0, OC-D1 | M | hecha |
| 17 | [OC-R2](PLAN-OCR.md#oc-r2--integración-en-el-pipeline) | OC-05, CO-03 | `fase-oc-2` | OC-R1, CO-R7 | M | hecha |
| 18 | [OC-R3](PLAN-OCR.md#oc-r3--medición-de-error-por-carácter-con-su-letra-gate-de-fase-2) | gate Fase 2 → OC-D2 | `fase-oc-3` | OC-R2, PL-R0 | M | pendiente |

### Ola 4 — Aplicación (Fase 3)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 19 | [AP-R0](PLAN-APP.md#ap-r0--capa-de-datos-local) | AP-05 | `fase-ap-0` | CO-R7 | M | hecha |
| 20 | [AP-R1](PLAN-APP.md#ap-r1--servidor-fastapi-y-cola-de-procesamiento) | AP-03, AP-04, AP-06 | `fase-ap-1` | AP-R0 | M | hecha |
| 21 | [AP-R2](PLAN-APP.md#ap-r2--página-de-captura-en-el-celular-qr-e-ip-local) | AP-01, AP-02, AP-07 | `fase-ap-2` | AP-R1 | M | hecha |
| 22 | [AP-R3](PLAN-APP.md#ap-r3--ventana-de-escritorio-con-pywebview) | AP-08 | `fase-ap-3` | AP-R1 | S | hecha |
| 22b | [AP-R3b](PLAN-APP.md#ap-r3b--vínculo-del-celular-ap-d2) | AP-D2 | `fase-ap-3b` | AP-R3 | M | hecha |
| 23 | [AP-R4](PLAN-APP.md#ap-r4--interfaz-react-base) | BS-03 | `fase-ap-4` | AP-R1, Node (Docker) | M | hecha |
| 24 | [AP-R5](PLAN-APP.md#ap-r5--pantalla-de-revisión) | — | `fase-ap-5` | AP-R4, OC-R2, OC-D2 | L | hecha |
| 25 | [AP-R6](PLAN-APP.md#ap-r6--exportación-desde-la-interfaz) | — | `fase-ap-6` | AP-R5, CO-R6, AP-D1 | S | hecha |
| 26 | [AP-R7](PLAN-APP.md#ap-r7--prueba-de-aceptación-con-la-usuaria-gate-de-fase-3) | gate Fase 3 | — | AP-R6 | humano | pendiente |

### Ola 5 — Resto de plantillas (Fase 4)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 27 | [PL-R2](PLAN-PLANTILLAS.md#pl-r2--script-de-detección-de-cuadrícula) | — | `fase-pl-2` | PL-R1, CO-R2 | M | pendiente |
| 28 | [PL-R3](PLAN-PLANTILLAS.md#pl-r3--lectura-de-los-textos-impresos-de-los-ítems) | — | `fase-pl-3` | PL-R2, OC-R1 | S | pendiente |
| 29 | [CO-R4](PLAN-CORE.md#co-r4--identificación-del-formulario) | PL-04 | `fase-co-4` | CO-R3, 2+ plantillas | M | pendiente |
| 30 | [PL-R4](PLAN-PLANTILLAS.md#pl-r4--plantillas-de-los-formularios-restantes-fase-4) | gate Fase 4 | `fase-pl-4-<formulario>` | PL-R2, PL-R3, CO-R4 | L (1 sesión por formulario) | pendiente |
| 31 | [PL-R5](PLAN-PLANTILLAS.md#pl-r5--hojas-reimprimibles-con-marcas-aruco-y-qr) | PL-04 | `fase-pl-5` | PL-D1 = sí, CO-R4 | M | bloqueada (PL-D1) |

### Ola 6 — Distribución (Fase 5)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 32 | [DI-R1](PLAN-DIST.md#di-r1--spec-de-pyinstaller-de-la-app-real) | DI-04 | `fase-di-1` | AP-R6, DI-R0, PL-D2 | M | pendiente |
| 33 | [DI-R2](PLAN-DIST.md#di-r2--instalador-inno-setup) | DI-02, DI-03, DI-05, DI-06 | `fase-di-2` | DI-R1, DI-D1, DI-D2 | M | bloqueada (DI-D1, DI-D2) |
| 34 | [DI-R3](PLAN-DIST.md#di-r3--build-y-release-en-github-actions) | DI-07 | `fase-di-3` | DI-R2, BS-R2 | M | pendiente |
| 35 | [DI-R4](PLAN-DIST.md#di-r4--instalación-limpia-en-la-laptop-de-la-usuaria-gate-de-fase-5) | gate Fase 5 | — | DI-R3 | humano + S | pendiente |

### Ola 7 — Piloto (Fase 6)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 36 | [PI-R0](PLAN-PILOTO.md#pi-r0--informe-local-de-correcciones-y-errores) | PI-01 | `fase-pi-0` | AP-R5 | S | pendiente |
| 37 | [PI-R1](PLAN-PILOTO.md#pi-r1--piloto-de-2-semanas) | — | — | DI-R4, PI-R0 | humano (2 semanas) | pendiente |
| 38 | [PI-R2](PLAN-PILOTO.md#pi-r2--ajuste-de-umbrales-y-lista-de-mejoras-v2-gate-de-fase-6) | gate Fase 6 | `fase-pi-2` | PI-R1 | M | pendiente |

**Paralelismo permitido** (`plan.md`: las Fases 1 y 2 pueden avanzar juntas): OC-R0 y DI-R0 no
dependen del núcleo; OC-R1 puede adelantarse a la Ola 2 en cuanto OC-D1 esté decidida. AP-R0 y
AP-R1 pueden empezar con un `Lector` OCR falso si la Ola 3 se atrasa. Sigue valiendo una fase por
sesión.

---

## 4. Decisiones humanas

Detalle, opciones y recomendación en el plan de cada frente.

| ID | Pregunta (resumen y recomendación) | Bloquea | Estado |
|---|---|---|---|
| B-1 | Rama base. **Rec.: `main`**, ramas `fase-*` fusionadas a ella | P-3, todo | aprobada: `main` (2026-11-06) |
| B-2 | Crear el repo privado en GitHub (lo hace el responsable) | P-5, BS-R2, DI-R3 | aprobada crearlo (2026-11-07); falta que lo cree el responsable |
| BS-D1 | Gestor de entorno. **Rec.: uv con lockfile** (alternativa: venv + pip) | BS-R0 | aprobada: uv + lockfile (2026-11-06) |
| CO-D3 | ¿Varias tablas por página en el esquema? **Rec.: sí** (`tablas[]`, formato plano como atajo) | CO-R0 | aprobada: `tablas[]` (2026-11-06) |
| PL-D2 | ¿Dónde viven las plantillas reales? **Rec.: fuera del repo, importadas desde .zip** | PL-R1, DI-R1 | aprobada: rec. (2026-11-06) |
| CO-D1 | Estructura del Excel. **Rec.: por evaluación + consolidado por formulario** | CO-R6 | aprobada: a) (2026-11-06) |
| CO-D2 | ¿Nombre del paciente en el archivo? **Rec.: sí, saneado, con opción de iniciales** | CO-R6 | aprobada: a) (2026-11-06) |
| PL-D1 | ¿Reimprimir hojas con ArUco y QR? **Rec.: sí para las que ella imprime; v1 funciona sin ellas** | PL-R5 | aprobada: sí (2026-11-07) |
| OC-D1 | Modelo OCR definitivo. **a) PP-OCRv6 medium ONNX** (cifras en PLAN-OCR) | OC-R1 | aprobada: a) (2026-11-06) |
| OC-D2 | Texto como sugerencia, solo imagen o según confianza. **Rec.: según confianza**; se decide con el CER de OC-R3 | AP-R5 (parcial) | aprobada: siempre como sugerencia, el OCR puede equivocarse (2026-11-07); el CER de OC-R3 solo ajusta cuándo se resalta como dudoso |
| AP-D2 | Requisito nuevo (2026-11-07): la app solo funciona con el celular y la laptop de ella; el celular no debe poder conectarse a otra computadora. Diseño de emparejamiento pendiente | AP-R2 (ya hecha), AP-R3/AP-R4 | aprobada (2026-11-07): vínculo explícito con un código de un solo uso (5 min) desde un botón en la ventana; **un solo celular, reemplazable**; la credencial del celular solo sube fotos, ve la cola y lista plantillas (el resto, solo desde la laptop); si cambia la IP se vuelve a vincular. Hecha en AP-R3b |
| AP-D1 | ¿Borrar fotos al exportar por defecto? **Rec.: no durante el piloto, sí después** | AP-R6 | aprobada (2026-11-07, interpretada): celular y laptop son personales de ella y seguros, no se borra por defecto; el borrado queda como acción manual (`borrar_fotos`). Corregir si se quiso otra cosa |
| DI-D1 | Datos al desinstalar. **Rec.: preguntar, "conservar" por defecto** | DI-R2 | aprobada: debe poderse conservar (2026-11-07); preguntar, «conservar» por defecto |
| DI-D2 | Instalación por máquina o por usuario. **Rec.: por máquina** (regla de firewall acotada) | DI-R2 | aprobada: por máquina (2026-11-07) |

### Insumos pendientes del responsable o de la usuaria

El agente no puede hacerlos; se anotan aquí hasta que lleguen.

- [ ] Fotos en blanco de los 3–5 formularios más usados (bloquea PL-R0, PL-R1, CO-R8). Recibida 2026-11-07 una foto *llena* de «Evaluación Continua al Personal» en `muestras/evaluacion-continua-llena-1.jpeg` (12 ítems, 6 columnas, 5 campos de cabecera); falta en blanco y su verdad.
- [ ] Una foto de cada uno lleno con datos inventados y su letra real, con la verdad de terreno
      (`verdad.csv`, PL-05) (bloquea CO-R8, OC-R3).
- [ ] ¿Hay formularios de más de una hoja? (PL-03).
- [ ] Versión de Windows de la laptop (DI-05).
- [ ] Perfil de red del WiFi de la casa en la laptop: Privada o Pública (AP-01).
- [x] ~~Instalar Node LTS en la máquina de desarrollo (BS-03)~~: no hace falta; Node corre en Docker (servicio `ui`).

---

## 5. Riesgos conocidos del entorno

- **Máquina de desarrollo ≠ máquina objetivo.** Las latencias medidas aquí son aproximadas; las que
  cuentan son las del Vivobook Flip (Ryzen 7) de la usuaria (OC-07).
- **Herramientas (verificado 2026-11-06):** Python 3.12.0, git 2.42, gh 2.32 disponibles; **uv y
  Node no instalados, y no se instalan**: todo el entorno va en Docker Desktop (regla del
  responsable, 2026-11-06). AP-R4 (React) compilará con una imagen `node` en compose. Ojo con
  `pywebview` (AP-R3): la ventana de escritorio no se puede ver desde un contenedor; se prueba la
  lógica en Docker y la ventana real queda como verificación humana.
- **Shell:** Windows con PowerShell 5.1 y Git Bash; en PowerShell no hay `&&`.
- **Datos que nunca van a git:** `muestras/`, `plantillas/` reales, `modelos/`, `*.onnx`, BD y fotos
  de `%LOCALAPPDATA%\AutoEvalPsi`. Revisar `git status` antes de cada commit.
- **Sin tareas automáticas en los equipos:** ni en la máquina de desarrollo ni en la laptop de la
  usuaria (cron, Programador de tareas, autoarranque, actualizadores). Lo periódico se corre a mano.
  Los workflows de GitHub Actions sí están permitidos, sin `schedule:`.
- **No verificable por el agente:** prueba con el Samsung A32 real, conexión por WiFi, SmartScreen
  y antivirus en la laptop de ella, instalación limpia. Se anotan como pendientes humanos, nunca
  como verificados.

---

## 6. Diario

| Fecha | Fase | Rama · commit | Resultado | Tests antes → después | Nota / siguiente |
|---|---|---|---|---|---|
| 2026-11-06 | — (creación) | sin repo · sin commit | Bitácora y 7 planes creados a partir de `plan.md` | — | No cambia código. Aprobadas B-1 (`main`), BS-D1 (uv), CO-D3 (`tablas[]`); modo silencioso. Siguiente: Ola 0 (P-1, P-4). |
| 2026-11-06 | Ola 0 (P-1, P-3, P-4) | `main` · commit inicial | Repo creado; `plan.md`, planes, `.gitignore` mínimo y `CLAUDE.md` commiteados. Cierra BS-05. | — (sin suite aún) | No cambia ninguna fase de código. Aviso: la identidad global de git es el marcador «Tu Nombre / tucorreo@example.com»; el commit salió con ella. Corregir con `git config --global user.name/user.email` y, si se quiere, reescribir el commit inicial. Pendiente humano: P-5 (repo GitHub) y uv. |
| 2026-11-06 | BS-R0 | `fase-bs-0` → `main` | `pyproject.toml` (Py 3.12, layout `src/`, extras `app`/`ocr`, grupo `dev`), paquetes vacíos, `cli --version`, test de frontera de `core` (con test negativo), README con entorno, `uv.lock`. | — → 3 passed; ruff limpio | uv no está en el PATH: se usa `python -m uv`. Siguiente: CO-R0. |
| 2026-11-06 | BS-R0 (corrección) | `main` | Revertida la instalación de uv en el equipo (`pip uninstall uv`, borradas la caché de uv en `%LOCALAPPDATA%` y `.venv`). Añadidos `Dockerfile`, `docker-compose.yml`, `.dockerignore`; README y CLAUDE.md reescritos. | 3 passed y ruff limpio, dentro de Docker | Regla: todo en Docker Desktop, nada en la máquina ni variables globales. BS-D1 sigue siendo uv, pero dentro de la imagen. |
| 2026-11-06 | CO-R0 | `fase-co-0` → `main` | `core/plantilla.py`: modelos pydantic `Plantilla`/`Pagina`/`Tabla`/`Fila`/`CampoCabecera`, `cargar_plantilla()`, `PlantillaInvalida` con el campo en el mensaje, `esquema_version` = 1. `tablas[]` con atajo plano (el ejemplo de `plan.md` carga). `item` único en toda la plantilla; umbrales OMR (`omr`) por plantilla (CO-02). | 3 → 17 passed (14 nuevos); ruff check limpio | **Contrato fijado:** formato de plantilla v1 (documentado en el docstring del módulo). `tests/` previos sin `ruff format` (preexistente). Siguiente: BS-R1. |
| 2026-11-06 | BS-R1 | `fase-bs-1` → `main` | `tools/sintetico/`: formulario «demo-5opciones» (A4 y Carta, 12 filas × 5 opciones + observación) con su plantilla JSON que carga con el esquema real, en `plantillas_demo/`; `llenar` (X, ✓, círculo, relleno; tinta azul/negra; casos vacía, doble, tachón, fuera, tenue; texto Hershey script; verdad de terreno); `fotografiar` (perspectiva, rotación, fondo, degradé de sombra, desenfoque, ruido, JPEG, EXIF); `lote` y fixture `lote_sintetico`. | 17 → 53 passed (36 nuevos); ruff limpio | Sin contrato público afectado (el formato de verdad `*.verdad.json` es nuevo y solo de pruebas). Suite completa tarda ~26 s. Siguiente: CO-R1. |
| 2026-11-06 | CO-R1 | `fase-co-1` → `main` | `core/imagen.py`: `cargar_imagen` (EXIF vía Pillow, JPEG/PNG, HEIC y basura rechazados con `ImagenInvalida`) y `evaluar_calidad` con `UmbralesCalidad` (nitidez, brillo, luces quemadas, resolución). Umbrales calibrados con el lote sintético. | 53 → 74 passed (21 nuevos); ruff limpio | Sin contrato público afectado (API interna nueva). Hallazgo: OpenCV 5.0.0 `imread` ya aplica EXIF (CO-01 corregido en el plan). Umbrales a recalibrar con fotos reales en CO-R8. Siguiente: CO-R2. |
| 2026-11-06 | CO-R2 | `fase-co-2` → `main` | `core/hoja.py`: `detectar_hoja` (ArUco ids 0-3 con prioridad; si no, contorno por Canny y Otsu), `rectificar`, `enderezar_hoja`, `HojaNoEncontrada` («no se ve la hoja entera»). Esquinas a ≤ 1 % del lado de la hoja en todo el lote; hoja cortada, diminuta, sin hoja y homografía degenerada se rechazan. | 74 → 87 passed (13 nuevos); ruff limpio | Sin contrato público afectado (API interna nueva). CO-R3 debe probar giros de 180°/90°. Tamaño de marcas ArUco en la plantilla queda para PL-R5. Siguiente: CO-R3. |
| 2026-11-06 | CO-R3 | `fase-co-3` → `main` | `core/registro.py`: `registrar` (hoja enderezada → giro 0°/180° → ORB con coincidencias locales + RANSAC → ajuste afín ECC con líneas de la tabla → una sola deformación) y métricas de calidad CO-09 con bandera `registro_dudoso`; `cargar_referencia`. Error medio de esquinas de celdas 0,3–1,6 px (a 300 dpi) en las 6 fotos; formulario ajeno y hoja en blanco quedan marcados. | 87 → 102 passed (15 nuevos); ruff check limpio | Sin contrato público afectado (API interna nueva). Hallazgo: ratio test global + cobertura por cuadrantes dejaban 2 fotos a 16–26 px sin bandera → coincidencias locales y cobertura por área de casco. Umbrales a recalibrar con fotos reales en CO-R8. Siguiente: CO-R5. |
| 2026-11-06 | CO-R5 | `fase-co-5` → `main` | `core/casillas.py`: `leer_casillas` (tinta por celda completa menos lo impreso de la referencia, fondo adaptativo, decisión CO-02) con banderas `sin_marca`, `doble_marca`, `contraste_bajo`, `registro_dudoso`; `ResultadoFila`/`ResultadoPagina`. Lote base y lote de otra semilla (12 fotos): 0 errores silenciosos; tachón siempre amarillo. | 102 → 126 passed (24 nuevos); ruff limpio | **Contrato menor:** `omr.tinta_minima` por defecto 0,15 → 0,03 (esquema igual). Desviación: sin margen interior (un círculo grande sobre el borde se leía en la vecina sin bandera). Hallazgo CO-R3: 1 de 18 fotos sintéticas (semilla 777, foto_09) registra con ~62 px de error, bien marcada `registro_dudoso`; revisar en CO-R8. CO-R6 sigue bloqueada por CO-D1/CO-D2. Siguiente: OC-R0, DI-R0 o PL-R1. |
| 2026-11-06 | OC-R0 | `fase-oc-0` → `main` | Spike `tools/spike_ocr/`: PP-OCRv6 medium det+rec en ONNX (Apache-2.0, 62+77 MB, SHA-256 verificados) corre con onnxruntime CPU. Diccionario con todo el español salvo `¡`. Impreso 4/4 líneas, cursiva de fuente 12/12 detectadas, 1 error. Carga ≈ 2 s; detección 0,2–0,3 s por franja; reconocimiento 0,13–0,23 s/línea. | 126 → 126 passed (spike sin tests; ruff limpio) | Sin contrato público afectado. **No hay manuscrito real aún:** el acierto con su letra lo mide OC-R3. OC-D1: propuesta a). Siguiente: DI-R0. |
| 2026-11-06 | DI-R0 (parcial) | `fase-di-0` → `main` | Spike `tools/spike_empaquetado/` (cv2 + onnxruntime con ONNX mínimo + uvicorn en hilo + pywebview) empaquetado con PyInstaller `onedir` **en Linux/Docker**: 261 MB, arranque en frío ≈ 1,05 s, 0 `hiddenimports`, 0 avisos. | 126 → 126 passed (spike sin tests; ruff limpio) | Sin contrato público afectado. DI-08: Docker no puede producir el .exe; falta correrlo en Windows (CI tras B-2, o a mano) y pasar Defender/SmartScreen: **no verificado**. Siguiente: ninguna fase libre; ver §1. |
| 2026-11-06 | OC-R1 | `fase-oc-1` → `main` | `core/ocr`: interfaz `Lector`/`Linea`/`Caja`, `LectorFalso`, `LectorONNX` (PP-OCRv6 medium, sesiones perezosas, 4 hilos, orden de lectura); `tools/descargar_modelos.py` con revisión fijada y SHA-256 (también del diccionario). Cierra OC-04, OC-06. | 126 → 139 passed + 4 `lento` con el modelo real (13 + 4 nuevos); ruff limpio | **Contrato nuevo:** interfaz `Lector` (OC-R2 y el plan B dependen de ella). `pyyaml` al grupo `dev` (uv.lock). Aprobada OC-D1 a). Acierto con letra real sigue sin medirse (OC-R3). Siguiente: ninguna fase libre; ver §1. |
| 2026-11-06 | CO-R6 | `fase-co-6` → `main` | `core/excel.py`: archivo por evaluación (hoja «Evaluación», forma del papel, recortes opcionales) y consolidado por formulario sin duplicar por id; nombre saneado con opción de iniciales; `ArchivoBloqueado` con escritura atómica. Cierra CO-06, CO-07, CO-08. | 139 → 164 passed (25 nuevos); ruff limpio | **Contrato nuevo:** forma del Excel. Aprobadas CO-D1 a), CO-D2 a) y PL-D2 (rec.). Bloqueo probado simulando `PermissionError`; con Excel abierto en Windows **no verificado**. Siguiente: CO-R7. |
| 2026-11-06 | CO-R7 | `fase-co-7` → `main` | `core/pipeline.py` (`procesar_foto`, `ResultadoProcesamiento` serializable, `a_evaluacion`), `core/depuracion.py` (hoja enderezada con cuadrícula y celdas coloreadas) y comando `autoevalpsi procesar FOTO --plantilla --salida [--depuracion]`. | 164 → 180 passed (16 nuevos); ruff limpio | **Contrato nuevo:** CLI `procesar` y forma del resultado JSON (la usará AP-R1). Cabecera (paciente/fecha) por flags, sin OCR hasta OC-R2. Depuración revisada a ojo sobre una foto sintética. Siguiente: OC-R2 o AP-R0. |
| 2026-11-06 | OC-R2 | `fase-oc-2` → `main` | `core/ocr/texto.py`: `leer_texto` (franja de observaciones limpia y una sola lectura por tabla, líneas asignadas a su fila, filas sin tinta blanqueadas y sin llamada si ninguna tiene tinta; cabecera por campo); `procesar_foto(lector=)`, `a_evaluacion(recortes=)` y `procesar --ocr --recortes`. Banderas `ocr_confianza_baja`, `ocr_sin_texto`, `ocr_error`, `cabecera_vacia`; recorte de cada fila con tinta aunque el lector falle. Cierra OC-05, CO-03. | 180 → 197 passed (17 nuevos) + 1 `lento` nuevo con el modelo real (6/6 observaciones y 2/2 campos de cabecera exactos sobre letra sintética); ruff limpio | **Contrato nuevo:** resultado JSON ampliado (`ocr_activo`, `observaciones[]`, `cabecera[]`) y flags del CLI. Modelos ausentes no se disfrazan de `ocr_error`. Umbrales (tinta 0,004; confianza 0,85) provisionales: los calibra OC-R3 con letra real. La fecha manuscrita va como texto, no se interpreta. Siguiente: AP-R0. |
| 2026-11-06 | AP-R0 | `fase-ap-0` → `main` | `app/datos.py`: `BaseDatos` sobre SQLite (stdlib) con raíz configurable (`AUTOEVALPSI_HOME`, `%LOCALAPPDATA%\AutoEvalPsi`), migraciones por `PRAGMA user_version` (v1; una BD más nueva se rechaza sin tocarla), tablas `evaluaciones`/`paginas`/`filas`/`correcciones`/`configuracion`; fotos y recortes en disco con rutas relativas; `guardar_procesamiento` (multipágina), `actualizar_fila`/`actualizar_cabecera` (cada cambio deja una corrección), `filas_pendientes`/`cabecera_revisada` para AP-06, `borrar_fotos` (AP-D1), `como_evaluacion` → `core.excel`. | 197 → 233 passed (36 nuevos); ruff limpio | **Contrato nuevo:** esquema de BD v1 y API de `BaseDatos` (la usa AP-R1). `core.pipeline.nombre_campo_cabecera` extraído (sin cambio de conducta). Decisiones de diseño: lo leído no se pisa, lo confirmado va aparte; tocar una fila la confirma; editar tras exportar vuelve el estado a pendiente/revisada. Una conexión con candado (hilo de la cola, AP-04). AP-D1 sigue pendiente: `borrar_fotos` no decide cuándo. Siguiente: AP-R1. |
| 2026-11-06 | AP-R1 | `fase-ap-1` → `main` | `app/servidor.py` (`crear_app(bd, plantillas, token, lector)`), `app/cola.py` (un trabajador, estados `en_cola/procesando/lista/error`, tope de 50, rechaza la misma foto en vuelo) y `app/plantillas.py` (instalación desde .zip en `<raíz>/plantillas/<id>/v<versión>/`, sin pisar versiones, a prueba de rutas peligrosas). Token de 128 bits revisado antes de leer el cuerpo; topes por `Content-Length` (25 MB fotos, 100 MB .zip, 1 MB JSON); calidad en la misma petición y lectura en la cola; el servidor impone la revisión antes de exportar (409). Cierra AP-03, AP-04, AP-06. | 233 → 279 passed (46 nuevos); ruff limpio | **Contrato nuevo:** API HTTP v1 (docstring de `servidor.py`) y errores `{detail:{codigo,mensaje}}`. `httpx` al grupo `dev` (uv.lock) para `TestClient`; `datos.validar_id` pública y `BaseDatos.evaluacion_de_foto`. Sin OCR la cabecera nace «revisada» (conducta de AP-R0). Pendiente para AP-R2/R3: escuchar solo en la IP privada (AP-03), no es de este módulo. Para AP-R6: `exportar` acepta una `carpeta` en el cuerpo (cualquiera con el token escribe en el disco de la laptop); decidir si se limita a la configurada. Una foto en cola se pierde si la app se cierra antes de leerla. Siguiente: AP-R2. |
| 2026-11-06 | AP-R2 | `fase-ap-2` → `main` | `app/red.py` (IP del QR: ruta por defecto, solo rangos privados, nombres virtuales al final; solo biblioteca estándar), `app/qr.py` (segno, SVG; test que lo decodifica con OpenCV) y `app/captura/index.html` (cámara trasera y galería, progreso de subida, aviso inmediato de calidad, varias hojas con un mismo id, sigue la cola hasta «Lista»). Servidor: `GET /captura` y `GET /api/captura/enlace[?ip=]`; `crear_app(puerto=, interfaces=)`. | 279 → 302 passed (23 nuevos); ruff limpio; JS revisado con `node --check` en Docker | **Contrato ampliado:** API HTTP v1 con dos rutas nuevas; `/captura` también exige el token (la página lo incrusta escapado). Sin nombres de adaptador (stdlib) la IP se elige por ruta por defecto y rango; si una VPN toma la ruta por defecto el QR llevaría su IP: la usuaria puede elegir otra (`ips`). Hallazgos: una foto con aviso de calidad igual queda en cola y no hay forma de descartarla ni de repetir la misma hoja con el mismo id (409 `pagina_repetida`) → AP-R5 necesita «descartar foto»; para DI-R1 el HTML de `app/captura/` es dato del paquete. AP-01 (red Pública) se explica en AP-R4/guía. **No verificado:** A32 real por WiFi, firewall de Windows. Siguiente: AP-R3. |
| 2026-11-07 | — (decisiones) | `main` · sin commit | Aprobadas B-2 (crear), PL-D1 sí, AP-D1 no borrar por defecto, DI-D1 conservar, DI-D2 por máquina, OC-D2 sugerencia. Abierta AP-D2 (solo su celular con su laptop). Dos fotos recibidas movidas de `plantillas_demo/` a `muestras/` (ignorada por git); una es un récord académico con datos personales y fuera del alcance v1. | — | Sin código. Siguiente: AP-R3 o plantilla de la foto 1 (a decir por el responsable). |
| 2026-11-07 | AP-R3 | `fase-ap-3` → `main` | `app/escritorio.py`: `ServidorLocal` (uvicorn en un hilo, sockets propios en `127.0.0.1` y las IP privadas, nunca `0.0.0.0`; espera a `/api/salud`; cierre ordenado), instancia única por puerto (`AplicacionYaAbierta`/`PuertoOcupado`, mensajes para la usuaria; cuadro de Windows por `ctypes`), `Puente` con el diálogo nativo de carpeta (guarda `carpeta_exportacion`), `ejecutar` y comando `autoevalpsi abrir`. Cierra AP-08. | 302 → 315 passed (13 nuevos); ruff check limpio | **Contrato nuevo (aditivo):** comando CLI `abrir`; clave de configuración `carpeta_exportacion`. Sin cambio de API HTTP. **No verificado:** la ventana real y el cuadro de error en Windows. Las IP se enlazan al arrancar. AP-D2 (emparejamiento) sigue abierta: no se tocó. Siguiente: AP-R4 (imagen `node` en compose). |
| 2026-11-07 | — (decisión AP-D2) | `main` · sin commit | Aprobado el diseño de vínculo del celular: un solo celular reemplazable; volver a vincular si cambia la IP. Fase nueva AP-R3b antes de AP-R4. | — | **Contrato a afectar en AP-R3b:** API HTTP (rutas de vínculo; QR con código de un solo uso en vez del token de sesión) y esquema de BD v2 (`dispositivos`). |
| 2026-11-07 | AP-R3b | `fase-ap-3b` → `main` | `app/vinculo.py` (`Vinculos`: códigos de 128 bits, un solo uso, 5 min, en memoria; credencial de 256 bits, en la BD solo su SHA-256); `Guardia` con tres niveles: público (`salud`, `POST /api/vinculo`, `/captura`), celular vinculado (`X-Dispositivo`: `POST /api/fotos`, `GET /api/cola*`, `GET /api/plantillas*`) y laptop (loopback + token: todo lo demás); BD v2 con `dispositivos` (un solo registro); `POST /api/vinculo/iniciar`, `GET/POST/DELETE /api/vinculo`; página del celular reescrita (canjea el código del QR, guarda la credencial en `localStorage`, muestra «Vincula este celular desde la laptop»). | 315 → 340 passed (`test_vinculo.py` nuevo; ajustes en `test_captura`, `test_servidor` y `test_qr`); ruff limpio; JS con `node --check` | **Contratos cambiados (anunciados en AP-D2):** API HTTP v1 (el token de la app ya no sale de la laptop; se retira `GET /api/captura/enlace`; `/captura` pública y estática) y esquema de BD v1 → v2 (migración probada con una BD v1 con datos). Cierra el riesgo de `exportar` con `carpeta` libre. **No verificado:** vincular el A32 real, HTTP sin cifrar en el WiFi, comportamiento del JS de la página en un navegador (solo sintaxis). Siguiente: AP-R4 (imagen `node` en compose; pantalla de inicio con el botón de vincular; llamar a la API desde `127.0.0.1`). |
| 2026-11-07 | AP-R4 | `fase-ap-4` → `main` | `ui/` (Vite + React 19 + TS + Tailwind 4, vitest) compilada en Docker (servicio `ui`, `node:22-slim`) a `app/estaticos/` (fuera de git); FastAPI la sirve en `/` y `/assets` con CSP estricta. Pantallas: inicio (vincular celular con QR, cuenta regresiva, sondeo del canje, selector de red, desvincular; evaluaciones por terminar), lista de evaluaciones con filtros, configuración (carpeta de exportación, borrar fotos de lo exportado). Cliente tipado, token de `?token=` quitado de la barra. Cierra BS-03. | 340 → 354 passed (14 nuevos en `tests/app/test_interfaz.py`); ruff check limpio; vitest 29 passed; `tsc` y `vite build` limpios | **Contrato ampliado (aditivo):** `GET/PUT /api/configuracion`, `POST /api/evaluaciones/{id}/borrar_fotos`, `GET /` y `/assets/*`. Node no se instala en el equipo (regla Docker). **No verificado:** la ventana real (WebView2), el diálogo nativo de carpeta y el aspecto en pantalla. Hallazgo para DI-R1: hatch excluye lo ignorado por git; `estaticos/` va como dato de PyInstaller y el build de `ui/` precede al empaquetado. `ruff format --check` falla en 2 tests previos (`test_frontera_core.py`, `test_cli.py`), preexistente. Siguiente: AP-R5. |
| 2026-11-07 | AP-R5 | `fase-ap-5` → `main` | `ui/src/pantallas/Revision.tsx`: ruta `#/evaluaciones/<id>` con cabecera editable (recorte de cada campo, «Confirmar datos de la hoja»), contador «Faltan N filas por revisar», filtro «solo lo que falta», y por fila: ítem con su texto, casillas leídas (clic o teclado), banderas en palabras, recorte de la observación y texto editable marcado «leída de la foto: puede tener errores» (OC-D2: siempre sugerencia). Teclado: ↑/↓ fila, 1–9 opción, 0 «sin respuesta», Enter confirma y salta a la siguiente por revisar (Ctrl+Enter dentro del texto). «Descartar esta foto» por hoja. Servidor: `GET /api/evaluaciones/{id}/recortes/{item}` y `/cabecera/{campo}` (PNG) y `DELETE /api/evaluaciones/{id}/paginas/{n}`; `BaseDatos.descartar_pagina` y `archivo`. | 354 → 365 passed (11 nuevos en `test_datos`/`test_interfaz`, incluye e2e foto→recortes→confirmar→exportar); ruff limpio; vitest 29 → 50 passed (21 nuevos); `tsc` y `vite build` limpios | **Contrato ampliado (aditivo):** tres rutas HTTP nuevas, solo laptop; los recortes se piden con `?token=` porque un `<img>` no manda cabeceras (el token ya se aceptaba en la URL; la guardia sigue exigiendo loopback). Cierra el hallazgo de AP-R2 (no había forma de repetir una hoja): descartar libera el SHA-256 y la página, y la última foto elimina la evaluación con sus correcciones y archivos. Desviaciones: las filas siguen en el orden del papel (resaltadas, no reordenadas) con filtro para ver solo las pendientes; la foto completa de la hoja no se muestra, solo los recortes. **No verificado:** el aspecto y el uso real con teclado en la ventana (WebView2); el OCR con letra real (OC-R3 ajusta cuándo se resalta el texto como dudoso). Siguiente: AP-R6. |
| 2026-11-07 | AP-R6 | `fase-ap-6` → `main` | Tarjeta «Exportar a Excel» al pie de la revisión (`Exportar.tsx`): habilitada solo con filas y cabecera revisadas y sin cambios por confirmar (si no, dice qué falta); primera vez pide la carpeta con el diálogo nativo (cancelar = no exporta); errores del servidor (Excel abierto, revisión pendiente) en palabras y con reintento; al terminar dice dónde quedó y ofrece «Abrir la carpeta» (`Puente.abrir_carpeta`, solo carpetas existentes). Casillas: iniciales (CO-D2) y borrar las fotos de esa evaluación tras exportar (AP-D1: apagada por defecto, con confirmación). | 365 → 367 passed (2 nuevos en `test_escritorio`, `carpeta` en `test_servidor`); ruff check limpio; vitest 50 → 64 passed (14 nuevos); `tsc` y `vite build` limpios | **Contrato ampliado (aditivo):** `POST .../exportar` devuelve también `carpeta`. `ui/src/puente.ts` centraliza `window.pywebview.api`. Desviación: los recortes dentro del Excel no se ofrecen en la interfaz. **No verificado:** Excel abierto en Windows real, diálogo y Explorador reales (WebView2). Siguiente: AP-R7 (humana; preparar guion de prueba si se pide) o PI-R0. |
| 2026-11-07 | PL-R1 (+ modo de prueba) | `fase-pl-1` → `main` | **Modo de prueba en Docker** (`autoevalpsi probar`, `app/prueba.py`, servicio `probar`): interfaz en el navegador de la laptop y celular real por la LAN; dos puertos (laptop solo en `127.0.0.1` del anfitrión; celular a la red) porque Docker reenvía con la IP del puente. **PL-R1:** plantilla `evaluacion-continua` v1 (fuera de git) con referencia derivada de la foto llena (sin formulario en blanco), `tools/visor_plantilla.py`. **Registro (núcleo):** `registrar` ahora cae a emparejamiento directo foto↔referencia (ORB global) si la hoja no se detecta o el registro clásico no sale bueno, y el clásico prueba también 90°/270°; la foto del A07 y la de muestra, con la tabla casi cuadrada y sin esquinas del papel, no registraban. | 367 → 375 passed (4 nuevos en `test_registro`, 1 `test_visor_plantilla`, 3 `test_prueba`); ruff limpio | **Contratos:** `Registro.giro` ahora 0/90/180/270 y `metodo_hoja` puede ser `directo` (el JSON del resultado conserva su forma); `crear_app(puertos_laptop=)` solo para la prueba (vacío en producción). Resultado con la muestra real: 12/12 casillas (verdad = mi lectura, **por confirmar**), cabecera exacta con OCR; todas las filas con `contraste_bajo`. **Sin formulario en blanco:** la referencia sale de la foto llena con relleno de imagen; rehacerla cuando llegue el blanco. **No verificado:** otras fotos del formulario, ni la ventana real. Siguiente: probar la captura con el A07 contra esta plantilla; PL-R0 (insumos) o AP-R7. |
| 2026-11-07 | Ajuste de captura | `fix-captura-raiz` → `main` | Quien entra a `/` desde otro equipo (el celular, escribiendo solo `http://IP:puerto`) ahora va a `/captura` (302) en vez de ver la interfaz de la laptop; la página del celular recuerda que ya quedó vinculado y sugiere «Añadir a la pantalla de inicio». El vínculo ya persistía (BD y `localStorage`): no hace falta volver a leer el QR mientras no se desvincule ni cambie la IP/puerto. | 375 → 376 passed (`test_interfaz`: raíz laptop vs celular); ruff limpio; JS con `node` | **Contrato menor:** `GET /` desde fuera de la laptop responde 302 a `/captura`. **No verificado:** el comportamiento en el navegador del A07. |
