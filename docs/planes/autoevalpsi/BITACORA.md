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
| Última actualización | 2026-11-06 |
| Fase en curso | — |
| Siguiente acción | BS-R0, CO-R0, BS-R1, CO-R1, CO-R2, CO-R3, CO-R5, CO-R6, OC-R0 y OC-R1 hechas; DI-R0 parcial (medida en Linux; el cierre exige Windows: `windows-latest` tras B-2, o a mano). **Siguiente: CO-R7** (desbloquea OC-R2 y AP-R0). PL-R0/R1 siguen sin las fotos de la usuaria; BS-R2 espera B-2. Pendiente humano: P-5. |
| Rama base | `main` (decisión B-1, aprobada 2026-11-06) |
| Bloqueos activos | Insumos de la usuaria (fotos) bloquean PL-R0; B-2 (repo GitHub) bloquea BS-R2 |
| Fases hechas | 10 de 38 (BS-R0, CO-R0, BS-R1, CO-R1, CO-R2, CO-R3, CO-R5, CO-R6, OC-R0, OC-R1); DI-R0 parcial |

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
| 13 | [CO-R7](PLAN-CORE.md#co-r7--comando-de-foto-a-excel-e-imágenes-de-depuración) | — | `fase-co-7` | CO-R6 | S | pendiente |
| 14 | [PL-R1](PLAN-PLANTILLAS.md#pl-r1--plantilla-del-primer-formulario-y-visor-de-plantillas) | — | `fase-pl-1` | PL-R0, CO-R0, PL-D2 | M | pendiente |
| 15 | [CO-R8](PLAN-CORE.md#co-r8--banco-de-validación-con-fotos-reales-gate-de-fase-1) | gate Fase 1 | `fase-co-8` | CO-R7, PL-R1 | M | pendiente |

### Ola 3 — Observaciones (Fase 2)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 16 | [OC-R1](PLAN-OCR.md#oc-r1--lector-ocr) | OC-04, OC-06 | `fase-oc-1` | OC-R0, OC-D1 | M | hecha |
| 17 | [OC-R2](PLAN-OCR.md#oc-r2--integración-en-el-pipeline) | OC-05, CO-03 | `fase-oc-2` | OC-R1, CO-R7 | M | pendiente |
| 18 | [OC-R3](PLAN-OCR.md#oc-r3--medición-de-error-por-carácter-con-su-letra-gate-de-fase-2) | gate Fase 2 → OC-D2 | `fase-oc-3` | OC-R2, PL-R0 | M | pendiente |

### Ola 4 — Aplicación (Fase 3)

| # | Fase | Qué cierra | Rama | Requiere | Esfuerzo | Estado |
|---|---|---|---|---|---|---|
| 19 | [AP-R0](PLAN-APP.md#ap-r0--capa-de-datos-local) | AP-05 | `fase-ap-0` | CO-R7 | M | pendiente |
| 20 | [AP-R1](PLAN-APP.md#ap-r1--servidor-fastapi-y-cola-de-procesamiento) | AP-03, AP-04, AP-06 | `fase-ap-1` | AP-R0 | M | pendiente |
| 21 | [AP-R2](PLAN-APP.md#ap-r2--página-de-captura-en-el-celular-qr-e-ip-local) | AP-01, AP-02, AP-07 | `fase-ap-2` | AP-R1 | M | pendiente |
| 22 | [AP-R3](PLAN-APP.md#ap-r3--ventana-de-escritorio-con-pywebview) | AP-08 | `fase-ap-3` | AP-R1 | S | pendiente |
| 23 | [AP-R4](PLAN-APP.md#ap-r4--interfaz-react-base) | BS-03 | `fase-ap-4` | AP-R1, Node | M | pendiente |
| 24 | [AP-R5](PLAN-APP.md#ap-r5--pantalla-de-revisión) | — | `fase-ap-5` | AP-R4, OC-R2, OC-D2 | L | pendiente |
| 25 | [AP-R6](PLAN-APP.md#ap-r6--exportación-desde-la-interfaz) | — | `fase-ap-6` | AP-R5, CO-R6, AP-D1 | S | pendiente |
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
| B-2 | Crear el repo privado en GitHub (lo hace el responsable) | P-5, BS-R2, DI-R3 | pendiente |
| BS-D1 | Gestor de entorno. **Rec.: uv con lockfile** (alternativa: venv + pip) | BS-R0 | aprobada: uv + lockfile (2026-11-06) |
| CO-D3 | ¿Varias tablas por página en el esquema? **Rec.: sí** (`tablas[]`, formato plano como atajo) | CO-R0 | aprobada: `tablas[]` (2026-11-06) |
| PL-D2 | ¿Dónde viven las plantillas reales? **Rec.: fuera del repo, importadas desde .zip** | PL-R1, DI-R1 | aprobada: rec. (2026-11-06) |
| CO-D1 | Estructura del Excel. **Rec.: por evaluación + consolidado por formulario** | CO-R6 | aprobada: a) (2026-11-06) |
| CO-D2 | ¿Nombre del paciente en el archivo? **Rec.: sí, saneado, con opción de iniciales** | CO-R6 | aprobada: a) (2026-11-06) |
| PL-D1 | ¿Reimprimir hojas con ArUco y QR? **Rec.: sí para las que ella imprime; v1 funciona sin ellas** | PL-R5 | pendiente |
| OC-D1 | Modelo OCR definitivo. **a) PP-OCRv6 medium ONNX** (cifras en PLAN-OCR) | OC-R1 | aprobada: a) (2026-11-06) |
| OC-D2 | Texto como sugerencia, solo imagen o según confianza. **Rec.: según confianza**; se decide con el CER de OC-R3 | AP-R5 (parcial) | pendiente (tras OC-R3) |
| AP-D1 | ¿Borrar fotos al exportar por defecto? **Rec.: no durante el piloto, sí después** | AP-R6 | pendiente |
| DI-D1 | Datos al desinstalar. **Rec.: preguntar, "conservar" por defecto** | DI-R2 | pendiente |
| DI-D2 | Instalación por máquina o por usuario. **Rec.: por máquina** (regla de firewall acotada) | DI-R2 | pendiente |

### Insumos pendientes del responsable o de la usuaria

El agente no puede hacerlos; se anotan aquí hasta que lleguen.

- [ ] Fotos en blanco de los 3–5 formularios más usados (bloquea PL-R0, PL-R1, CO-R8).
- [ ] Una foto de cada uno lleno con datos inventados y su letra real, con la verdad de terreno
      (`verdad.csv`, PL-05) (bloquea CO-R8, OC-R3).
- [ ] ¿Hay formularios de más de una hoja? (PL-03).
- [ ] Versión de Windows de la laptop (DI-05).
- [ ] Perfil de red del WiFi de la casa en la laptop: Privada o Pública (AP-01).
- [ ] Instalar Node LTS en la máquina de desarrollo antes de AP-R4 (BS-03).

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
