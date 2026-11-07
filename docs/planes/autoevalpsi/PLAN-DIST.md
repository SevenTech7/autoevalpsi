# PLAN-DIST — Empaquetado, instalador y build

Carpeta `packaging/` y `.github/workflows/`. Cubre la Fase 5 de `plan.md`. Prefijo `DI`.

| Fase | Título | Estado |
|---|---|---|
| DI-R0 | Prueba temprana de empaquetado (spike) | parcial (Linux hecho; falta Windows) |
| DI-R1 | Spec de PyInstaller de la app real | pendiente |
| DI-R2 | Instalador Inno Setup | bloqueada (DI-D1, DI-D2) |
| DI-R3 | Build y release en GitHub Actions | pendiente |
| DI-R4 | Instalación limpia en la laptop de la usuaria (gate de Fase 5) | pendiente (humano) |

---

## Hallazgos

- **DI-01** — PyInstaller con opencv + onnxruntime + pywebview es la combinación con más
  sorpresas (DLLs no detectadas, `hiddenimports`, tamaño > 300 MB, falsos positivos de antivirus).
  Descubrirlo en la Fase 5 es tarde; por eso DI-R0 va en la Ola 1.
- **DI-02** — Sin firma de código, SmartScreen mostrará "Windows protegió su PC". `plan.md` lo
  asume; la guía debe tener captura de pantalla de "Más información → Ejecutar de todos modos".
- **DI-03** — Crear la regla de firewall requiere privilegios de administrador; condiciona la
  instalación por máquina (DI-D2). La regla debe limitarse a perfil **Privado**, TCP 8765 y al
  ejecutable de la app.
- **DI-04** — Las plantillas reales no deben estar en el build de CI (PL-D2). El modelo ONNX se
  descarga en CI con verificación de hash (OC-04).
- **DI-05** — WebView2 viene en Windows 11 y en Windows 10 actualizado; falta confirmar la versión
  de Windows de la laptop (pendiente de `plan.md`). El instalador puede comprobarlo y, si falta,
  avisar con el enlace al instalador oficial.
- **DI-06** — El instalador **no** crea tareas programadas, servicios, arranque automático ni
  actualizador en segundo plano: la app solo corre cuando ella la abre. Coherente con la
  preferencia del responsable de no dejar tareas automáticas en los equipos.
- **DI-08** — PyInstaller no cruza de plataforma y Docker Desktop corre contenedores Linux: dentro
  de Docker solo se puede empaquetar un binario **Linux**. Todo lo propio de Windows (DLLs,
  pywebview/WebView2, Defender, tamaño real) solo se verifica en `windows-latest` de GitHub
  Actions (necesita B-2) o a mano por el responsable en una máquina sin Python.
- **DI-07** — Sin Node local (BS-03), el build completo solo es posible en CI hasta que se instale.

---

## DI-R0 — Prueba temprana de empaquetado (spike)

- **Requiere:** BS-R0.
- **Esfuerzo:** M. Código en `tools/spike_empaquetado/`, descartable.
- **Pasos:** "hola mundo" que importa cv2, onnxruntime (con una sesión de un modelo ONNX mínimo),
  arranca uvicorn en un hilo y abre una ventana pywebview con una página; PyInstaller `onedir`;
  medir tamaño, tiempo de arranque en frío y revisar con Windows Defender.
- **Criterio de salida:** el ejecutable arranca en una máquina sin Python; cifras e
  `hiddenimports` necesarios anotados aquí.
- **Estado: parcial (2026-11-06).** Hecho el spike (`tools/spike_empaquetado/hola.py`, `correr.sh`)
  y medido **en Linux dentro de Docker** (DI-08). Falta repetirlo en Windows.
  - **Qué ejercita:** cv2 (encode/decode/cvtColor), onnxruntime con un ONNX de una sola operación
    escrito a mano (sin paquete `onnx`), FastAPI + uvicorn en un hilo con `/api/salud` consultado
    por HTTP, y `webview.create_window` (omitido con `--sin-ventana`; en Linux no hay pantalla).
  - **`hiddenimports`: ninguno.** `pyinstaller` 6.22.3 con `pyinstaller-hooks-contrib` 2026.9
    resolvió solo cv2, onnxruntime, uvicorn (sus imports por cadena) y pywebview; 0 avisos de
    módulos no hallados. En Linux PyInstaller exige `binutils` (`objdump`), que no está en la
    imagen `python:3.12-slim`; `correr.sh` lo instala en el contenedor efímero.
  - **Tamaño `onedir` (Linux, sin modelos reales):** 261 MB. Mayores: opencv headless 155 MB
    (`cv2` 72 + libs 83), onnxruntime 30, numpy 41 (14 + libs 27). A sumar: 139 MB de modelos OCR
    (OC-R0), UI y plantillas ⇒ ≈ 400 MB sin comprimir; el instalador comprimido será bastante menor.
  - **Arranque en frío:** ≈ 1,05 s hasta responder `/api/salud` (0,54 s por dentro; 0,11 s de
    importes). Sin sesión OCR real: añadir ≈ 2 s de carga de modelos (OC-R0). Cifras de Linux, no
    de la laptop de la usuaria.
  - **Pendiente (Windows):** repetir `pyinstaller` en `windows-latest` o a mano, ejecutar sin
    Python instalado, confirmar la ventana WebView2, medir tamaño real y pasar Windows Defender /
    SmartScreen. Ahí pueden aparecer DLLs no detectadas de onnxruntime y de `webview`
    (`pythonnet`/`clr`), que Linux no ejercita. Cierra DI-R0 al hacerse.

## DI-R1 — Spec de PyInstaller de la app real

- **Requiere:** AP-R6, DI-R0, PL-D2.
- **Esfuerzo:** M.
- **Pasos:** `packaging/autoevalpsi.spec` (onedir, sin consola, ícono); incluir UI compilada,
  página de captura, modelos ONNX; resolución de rutas de recursos con `sys._MEIPASS` en un solo
  módulo `app/recursos.py`; versión de la app embebida.
- **Tests:** smoke del ejecutable: arranca, `/api/salud` responde, procesa una foto sintética.

## DI-R2 — Instalador Inno Setup

- **Requiere:** DI-R1, DI-D1, DI-D2.
- **Esfuerzo:** M.
- **Pasos:** `packaging/installer.iss`: carpeta de instalación, ícono en el escritorio y menú
  inicio, regla de firewall (DI-03) creada al instalar y eliminada al desinstalar, comprobación de
  WebView2 (DI-05), política de datos al desinstalar (DI-D1), nada de lo listado en DI-06.

## DI-R3 — Build y release en GitHub Actions

- **Requiere:** DI-R2, BS-R2.
- **Esfuerzo:** M.
- **Pasos:** workflow `release.yml` en `windows-latest` disparado por tag `v*` (sin `schedule:`):
  build de `ui/`, descarga y verificación de modelos, PyInstaller, Inno Setup (`iscc`), smoke del
  ejecutable, publicación en Releases del repo privado.

## DI-R4 — Instalación limpia en la laptop de la usuaria (gate de Fase 5)

- **Requiere:** DI-R3.
- **Humano:** instalar desde el .exe de Releases sin abrir terminal (criterio de `plan.md`).
  El agente prepara la guía de una página: SmartScreen, permiso de red privada, perfil de red
  (AP-01), verificación de BitLocker/Cifrado de dispositivo y contraseña de Windows, importar
  plantillas (PL-D2).

---

## Decisiones

- **DI-D1 — ¿Qué pasa con los datos al desinstalar?**
  - a) Se conservan siempre (`%LOCALAPPDATA%\AutoEvalPsi`).
  - b) El desinstalador pregunta, con "conservar" marcado por defecto.
  - c) Se borran siempre.
  - **Recomendación: b)** — una reinstalación no pierde evaluaciones, pero ella puede dejar el
    equipo limpio.
- **DI-D2 — ¿Instalación por máquina o por usuario?**
  - a) Por máquina (`Program Files`, pide administrador una vez).
  - b) Por usuario (sin administrador), pero entonces no puede crear la regla de firewall y
    Windows mostrará su propio aviso de red la primera vez.
  - **Recomendación: a)** — la regla de firewall acotada (DI-03) es más segura y predecible que el
    aviso genérico de Windows.
