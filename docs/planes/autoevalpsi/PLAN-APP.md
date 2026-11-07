# PLAN-APP — Aplicación: datos, servidor local, captura y revisión

Paquete `autoevalpsi.app` y carpeta `ui/`. Cubre la Fase 3 de `plan.md` (pasos 1, 8 y 9 del
pipeline desde la interfaz). Prefijo `AP`.

| Fase | Título | Estado |
|---|---|---|
| AP-R0 | Capa de datos local (SQLite + imágenes) | hecha |
| AP-R1 | Servidor FastAPI y cola de procesamiento | hecha |
| AP-R2 | Página de captura en el celular, QR e IP local | hecha |
| AP-R3 | Ventana de escritorio con pywebview | hecha (ventana real sin verificar) |
| AP-R3b | Vínculo del celular (AP-D2) | hecha (A32 real sin verificar) |
| AP-R4 | Interfaz React base | pendiente (requiere Node, BS-03) |
| AP-R5 | Pantalla de revisión | pendiente |
| AP-R6 | Exportación desde la interfaz | pendiente |
| AP-R7 | Prueba de aceptación con la usuaria (gate de Fase 3) | pendiente (humano) |

---

## Hallazgos

- **AP-01** — Si Windows clasifica el WiFi de la casa como red **Pública**, la regla de firewall
  para red privada no aplica y el celular no conecta. La app debe detectarlo (o al menos
  explicarlo en pantalla si no llega ninguna subida) y la guía de instalación debe cubrirlo.
- **AP-02** — Las laptops suelen tener adaptadores virtuales (Hyper-V, WSL, VPN, VirtualBox). Si el
  QR lleva la IP equivocada, el celular no conecta. Elegir la IP de la interfaz con puerta de
  enlace por defecto, en rangos privados, y permitir elegir otra en la pantalla del QR.
- **AP-03** — El token del QR viaja en la URL por HTTP en la red local. Aceptable para el modelo de
  amenaza (red de la casa), pero: token aleatorio de 128 bits por inicio de la app, comparación
  en tiempo constante, límite de tamaño de subida (p. ej. 25 MB), solo `image/jpeg`/`image/png`,
  y el servidor escucha solo en la IP privada elegida, no en `0.0.0.0`.
- **AP-04** — El OCR y OpenCV son CPU intensivos. Ejecutarlos dentro del event loop congela el
  servidor. Usar un único trabajador en un hilo/proceso aparte y una cola: el celular recibe
  "foto recibida" al instante y el control de calidad (rápido) se responde en la misma petición.
- **AP-05** — El piloto (PI-R0) necesita el registro de cada corrección. La tabla de correcciones
  debe existir desde AP-R0, no agregarse al final.
- **AP-06** — "Revisión obligatoria antes de exportar" debe imponerla el servidor (rechaza exportar
  si hay filas sin confirmar), no solo la interfaz.
- **AP-07** — La página del celular no necesita React: una sola página HTML liviana servida por
  FastAPI carga más rápido en el A32 y no depende del build de `ui/`.
- **AP-08** — Puerto fijo 8765 ocupado (segunda instancia u otra app): la app debe detectarlo y
  traer al frente la instancia existente o informar, no fallar en silencio.

---

## AP-R0 — Capa de datos local

- **Requiere:** CO-R7.
- **Estado:** hecha (2026-11-06). `app/datos.py` (`BaseDatos`), esquema v1; 36 tests en `tests/app/test_datos.py`.
- **Esfuerzo:** M. **Toca un contrato** (esquema de BD): versionarlo con `PRAGMA user_version`.
- **Pasos:** raíz `%LOCALAPPDATA%\AutoEvalPsi` (configurable para tests); tablas `evaluaciones`,
  `paginas`, `filas` (valor leído, valor confirmado, banderas, texto OCR, ruta del recorte),
  `correcciones` (fila, campo, antes, después, momento), `configuracion`; migraciones simples;
  borrado de fotos de una evaluación (AP-D1).
- **Tests:** crear/leer/actualizar en una BD temporal; cada cambio de valor confirmado deja una fila
  en `correcciones`; migración de una BD vacía a la versión actual.

## AP-R1 — Servidor FastAPI y cola de procesamiento

- **Requiere:** AP-R0.
- **Estado:** hecha (2026-11-06). `app/servidor.py` (`crear_app`, contrato HTTP v1 en su docstring), `app/cola.py`, `app/plantillas.py`; 45 tests en `tests/app/test_servidor.py`.
- **Esfuerzo:** M. **Toca un contrato** (API HTTP).
- **Pasos:** endpoints `POST /api/fotos` (con token, AP-03), `GET /api/evaluaciones`,
  `GET/PUT /api/evaluaciones/{id}`, `POST /api/evaluaciones/{id}/exportar` (AP-06),
  `POST /api/plantillas/importar` (PL-D2), estado de la cola; trabajador único (AP-04);
  agrupación de varias fotos en una evaluación multipágina (PL-03).
- **Tests:** `TestClient`: subida sin token → 401; archivo enorme o no imagen → 4xx; foto
  sintética → evaluación con filas; exportar con filas sin revisar → 409.

## AP-R2 — Página de captura en el celular, QR e IP local

- **Requiere:** AP-R1.
- **Estado:** hecha (2026-11-06). `app/red.py`, `app/qr.py`, `app/captura/index.html` y dos rutas en `servidor.py`; 23 tests en `tests/app/test_{red,qr,captura}.py`. Pendiente humano: prueba con el A32 real, por WiFi.
- **Esfuerzo:** M.
- **Pasos:** `app/red.py` (AP-02); `app/qr.py` con segno (URL con IP, puerto y token); página
  `captura/index.html` con dos botones (`capture="environment"` y galería), barra de progreso,
  y respuesta inmediata del control de calidad ("está borrosa, repítela"); textos grandes y en
  español sencillo.
- **Tests:** selección de IP con una lista simulada de interfaces (virtual, VPN, WiFi);
  la página se sirve y contiene el token en el formulario.
- **No verificable por el agente:** la prueba con el A32 real; anotar como pendiente humano.

## AP-R3 — Ventana de escritorio con pywebview

- **Requiere:** AP-R1.
- **Estado:** hecha (2026-11-07). `app/escritorio.py` (`ServidorLocal`, `Puente`, `ejecutar`, `abrir_ventana`) y comando `autoevalpsi abrir [--puerto] [--ocr]`; 13 tests (`tests/app/test_escritorio.py`, `tests/test_cli.py`). Escucha solo en `127.0.0.1` y en las IP privadas (nunca `0.0.0.0`); `SO_EXCLUSIVEADDRUSE` en Windows. Instancia única por el puerto: `AplicacionYaAbierta` si `/api/salud` responde, `PuertoOcupado` si no. La carpeta de exportación elegida con el diálogo nativo se guarda en `configuracion` (`carpeta_exportacion`) para AP-R6. **No verificado:** la ventana real en Windows (WebView2) y el cuadro de error; la página en `/` no existe hasta AP-R4 (la ventana abre `/?token=…`). Las IP se enlazan al arrancar: si la laptop cambia de red, hay que reabrir la app.
- **Esfuerzo:** S.
- **Pasos:** `app/escritorio.py`: arranca uvicorn en un hilo, espera a que responda, abre la ventana
  (WebView2), cierra ordenadamente; instancia única y puerto ocupado (AP-08); diálogo nativo para
  elegir la carpeta de exportación.
- **Tests:** arranque/parada del servidor en hilo; puerto ocupado → mensaje. La ventana real no
  se prueba en CI.

## AP-R3b — Vínculo del celular (AP-D2)

- **Requiere:** AP-R3. **Esfuerzo:** M. **Toca dos contratos** (API HTTP v1 y esquema de BD → v2).
- **Estado:** hecha (2026-11-07). `app/vinculo.py` (`Vinculos`), `Guardia` con tres niveles de acceso
  (docstring de `servidor.py`), BD v2 (`dispositivos`), página `captura/index.html` reescrita;
  tests en `tests/app/test_vinculo.py` y ajustes en `test_captura.py`, `test_servidor.py`,
  `test_qr.py`. **Desviaciones:** (1) `GET /captura` es público y estático: el navegador no puede
  mandar `X-Dispositivo` al abrir una página, y la página no contiene secretos; la lista de
  formularios la pide con la credencial. (2) Se retiró `GET /api/captura/enlace`; lo reemplaza
  `POST /api/vinculo/iniciar`. (3) Los códigos viven en memoria (reiniciar la app los anula; 5 min
  de todos modos). (4) La credencial va solo en cabecera, no en la URL. (5) El «botón en la
  ventana» que pide el código es de la interfaz: lo construye AP-R4 (pantalla de inicio), usando
  `POST /api/vinculo/iniciar`, `GET /api/vinculo` y `DELETE /api/vinculo`. **Cierra** el riesgo de
  `exportar` con `carpeta` libre de AP-R1: solo la laptop (loopback + token) lo alcanza. **Hallazgos:**
  AP-R4 debe llamar a la API desde `127.0.0.1` (no desde la IP de la LAN, que no es loopback);
  si el WebView llegara a pedir desde otra dirección, la guardia lo rechazaría con `solo_laptop`.
- **Decidido (2026-11-07):** un solo celular, reemplazable; si cambia la IP se vuelve a vincular.
  La laptop no puede impedir que el celular hable con otra computadora; garantiza que solo acepta
  el suyo.
- **Pasos:** tabla `dispositivos` (huella SHA-256 de la credencial, creado, último uso) con
  migración v2 y un solo registro; códigos de vínculo de un solo uso, de 128 bits, con vencimiento
  de 5 min, que solo se piden desde la propia laptop (loopback + token de la app);
  `POST /api/vinculo/iniciar` (QR con el código), `POST /api/vinculo` (código → credencial),
  `DELETE /api/vinculo`; `/captura` y la API se abren con la credencial (`X-Dispositivo`, en
  `localStorage` del celular). Alcance de la credencial: `GET /captura`, `POST /api/fotos`,
  `GET /api/cola*`, `GET /api/plantillas*` y `GET /api/captura/enlace` no; el resto exige el token
  de la app desde loopback (cierra el riesgo de `exportar` con `carpeta` libre de AP-R1). El QR de
  sesión actual se retira. La página del celular muestra «Vincula este celular desde la laptop»
  si no tiene credencial.
- **Tests:** código usado dos veces → rechazado; código vencido; segunda vinculación reemplaza a
  la primera; credencial ajena → 403; la credencial no abre rutas de administración; desde una IP
  no loopback no se pueden pedir códigos; BD v1 migra a v2 sin perder datos.
- **No verificable por el agente:** vincular el A32 real; HTTP sin cifrar en el WiFi de la casa.

## AP-R4 — Interfaz React base

- **Requiere:** AP-R1, Node instalado (BS-03).
- **Esfuerzo:** M.
- **Pasos:** `ui/` con Vite + React + TS + Tailwind; pantallas: inicio (QR + evaluaciones
  pendientes), lista de evaluaciones, configuración (carpeta de exportación, borrar fotos, IP);
  cliente tipado de la API; build a `src/autoevalpsi/app/estaticos/` servido por FastAPI.
- **Tests:** typecheck + build; un test de componente para la lista.

## AP-R5 — Pantalla de revisión

- **Requiere:** AP-R4, OC-R2; el modo del texto depende de OC-D2 (si no está decidida, dejar el
  modo configurable y la fase **parcial**).
- **Esfuerzo:** L.
- **Pasos:** por fila: recorte de la fila al lado de las casillas leídas, clic para cambiar,
  observación editable en línea con su recorte, filas amarillas primero o resaltadas, navegación
  con teclado (↑/↓ fila, 1–5 opción, Enter confirmar), confirmación de cabecera; cada cambio va a
  `correcciones`; contador "faltan N filas por revisar".
- **Tests:** de componente para teclado y cambio de casilla; e2e mínimo contra el servidor con una
  evaluación sintética.

## AP-R6 — Exportación desde la interfaz

- **Requiere:** AP-R5, CO-R6.
- **Esfuerzo:** S.
- **Pasos:** botón exportar (habilitado solo con todo revisado), primera vez pide carpeta,
  mensaje claro si el consolidado está abierto (CO-08), abrir la carpeta al terminar, borrado de
  fotos según AP-D1.

## AP-R7 — Prueba de aceptación con la usuaria (gate de Fase 3)

- **Requiere:** AP-R6.
- **Humano:** ella procesa una hoja completa sin ayuda, del celular al Excel (criterio de
  `plan.md`). El agente prepara un guion de prueba de una página y una lista de observaciones;
  el resultado se anota en el diario.

---

## Decisiones

- **AP-D1 — ¿Borrar las fotos al exportar, por defecto?**
  - a) Sí por defecto.
  - b) No por defecto; casilla visible para activarlo.
  - **Recomendación: b) durante el piloto** (las fotos permiten analizar errores en PI-R2) y
    **cambiar a a) al cerrar el piloto** (minimización de datos clínicos).
