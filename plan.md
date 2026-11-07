# AutoEvalPsi — Plan del proyecto

Fecha: 2026-11-05

## Objetivo y alcance

AutoEvalPsi convierte fotos de evaluaciones psicológicas impresas en un Excel con casillas y observaciones ya transcritas, sin que los datos salgan de la laptop.

- **Usuaria:** psicóloga sin perfil técnico, que llena las evaluaciones a mano en papel.
- **Equipos:** Samsung A32 como cámara; ASUS Vivobook Flip (Ryzen 7, NVIDIA básica) procesa todo en CPU.
- **Experiencia buscada:** instalar un .exe, abrir desde el ícono del escritorio, fotografiar, revisar y exportar.

**Dentro del alcance (v1):** formularios tipo tabla con descripción, 5 o más casillas (una marcada por fila) y observación a la derecha; datos de cabecera como paciente y fecha; revisión manual; exportación a Excel.

**Fase posterior:** informes de texto libre escritos a mano, cuando se sepa qué tan bien lee el OCR su letra.

**Fuera del alcance:** calificación o interpretación clínica, sincronización en la nube y app nativa para el celular.

## Decisiones tomadas

Todo corre local y en CPU: visión clásica para las casillas y un OCR pequeño para la letra, sin modelos de IA pesados.

| Tema | Decisión | Motivo |
| --- | --- | --- |
| Casillas | OMR con OpenCV, sin IA | Medir tinta por celda es rápido y casi exacto si la foto está alineada |
| Letra a mano | PP-OCRv6 medium en ONNX (34.5M parámetros) | 1–2 s por imagen en CPU; transcribe fiel, sin inventar texto |
| Respaldo de la letra | Recorte de imagen junto a cada texto leído | Si el OCR falla, no se pierde información |
| Revisión | Obligatoria antes de exportar | Son datos clínicos |
| Captura | Página local abierta desde el celular con un QR | Sin app en el celular y sin pasar por internet |
| Distribución | Instalador .exe con ícono en el escritorio | Se usa como cualquier programa de Windows |
| Modelo grande (Qwen3-VL) | Descartado en v1; posible modo opcional después | Demasiado lento en esta laptop |

PP-OCRv6 se adopta sin prueba previa. La Fase 2 mide su precisión con la letra real y decide cómo se muestra el texto.

## Arquitectura y stack

Una sola aplicación de escritorio en Python levanta un servidor local: la laptop muestra la interfaz y el celular solo sube fotos por el WiFi de la casa.

```
 Celular A32                    LAPTOP · AutoEvalPsi.exe · todo local en CPU
┌────────────────┐        ┌─────────────────────────────────────────┐
│ Escanea el QR  │        │ Servidor local (FastAPI, token del QR)  │
│ Toma/elige foto│──WiFi─▶│            │ foto                       │
│ Sube la foto   │        │            ▼                            │
└────────────────┘        │ Pipeline core/  ◀── Plantillas (JSON +  │
                          │  OpenCV: endereza, alinea, lee casillas │   hoja en blanco)
                          │  PP-OCRv6 (ONNX): lee observaciones     │
                          │            │ casillas, texto, recortes  │
                          │            ▼                            │
                          │ Ventana de revisión ◀──▶ Datos locales  │
                          │  (pywebview + React)     (SQLite + img) │
                          │            │ valores confirmados        │
                          │            ▼                            │
                          │ Exportador Excel (openpyxl)             │
                          │            ▼                            │
                          │ Excel por evaluación + consolidado      │
                          └─────────────────────────────────────────┘
```

| Capa | Tecnología |
| --- | --- |
| Lenguaje | Python 3.12 |
| Servidor local | FastAPI + Uvicorn, puerto fijo (8765), solo red privada |
| Ventana de escritorio | pywebview sobre WebView2 (incluido en Windows 10/11) |
| Interfaz | React + Vite + TypeScript + Tailwind, compilada a archivos estáticos |
| Visión | opencv-python-headless + NumPy |
| OCR | PP-OCRv6 medium (detección + reconocimiento) en ONNX con onnxruntime CPU |
| QR | segno |
| Excel | openpyxl |
| Datos | SQLite + carpeta de imágenes en `%LOCALAPPDATA%\AutoEvalPsi` |
| Empaquetado | PyInstaller (modo onedir) + Inno Setup |
| Build | GitHub Actions (runner Windows) → Releases en repo privado |

- **Captura en el celular:** el QR lleva un token de sesión; sin token el servidor rechaza la subida. El botón usa `<input type="file" accept="image/*" capture="environment">`, que abre la cámara directo y funciona sobre HTTP en la red local.
- **Alternativa de galería:** un segundo botón permite subir fotos hechas con el modo Escanear documentos de la cámara Samsung.
- **Núcleo desacoplado:** el paquete `core/` (registro, OMR, OCR, Excel) no depende de la interfaz. Si más adelante se integra a PsicoEval, va como sidecar de Tauri sin reescribirlo.

## Pipeline de procesamiento

Cada foto pasa por nueve pasos y debería quedar lista para revisar en pocos segundos.

1. **Control de calidad al subir:** si la foto está borrosa (varianza del Laplaciano) o muy oscura, el celular pide repetirla al instante.
2. **Detección de la hoja:** contorno del papel y corrección de perspectiva a vista frontal. Si la hoja tiene marcas ArUco en las esquinas, se usan esas.
3. **Identificación del formulario:** por el QR de la hoja si existe; si no, comparando rasgos ORB contra las plantillas. Si la coincidencia es baja, ella elige el formulario de una lista.
4. **Registro fino:** homografía ORB + RANSAC contra la imagen en blanco de la plantilla y ajuste final con las líneas de la tabla.
5. **Lectura de casillas:** por celda, recorte con margen interior, umbral adaptativo y proporción de tinta. Gana la celda con más tinta comparando dentro de la misma fila, lo que tolera cambios de luz y de lapicero.
6. **Banderas:** fila sin marca, dos marcas parecidas (tachón o corrección) o contraste bajo quedan en amarillo para revisión.
7. **Observaciones:** se recorta la zona de cada fila; si tiene tinta, PP-OCRv6 detecta las líneas y las transcribe con su confianza. Confianza baja va en amarillo.
8. **Revisión:** la imagen de cada fila aparece al lado del valor leído. Un clic cambia la casilla, el texto se edita en línea y se navega con el teclado.
9. **Exportación:** genera el Excel descrito más abajo y guarda la evaluación en SQLite.

## Plantillas de formularios

Cada formulario se describe una sola vez con un JSON y una foto de la hoja en blanco; la app no aprende formularios nuevos por sí sola.

```json
{
  "id": "escala-ejemplo",
  "nombre": "Escala de ejemplo",
  "version": 1,
  "paginas": [
    {
      "imagen_referencia": "escala-ejemplo-p1.png",
      "tamano_px": [2480, 3508],
      "cabecera": [
        {"campo": "paciente", "caja": [300, 220, 1500, 300], "tipo": "texto"},
        {"campo": "fecha", "caja": [1700, 220, 2300, 300], "tipo": "texto"}
      ],
      "opciones": ["Nunca", "Casi nunca", "A veces", "Casi siempre", "Siempre"],
      "columnas_x": [[1180, 1290], [1290, 1400], [1400, 1510], [1510, 1620], [1620, 1730]],
      "observacion_x": [1740, 2400],
      "filas": [
        {"item": 1, "texto": "Descripción del ítem 1", "y": [520, 600]},
        {"item": 2, "texto": "Descripción del ítem 2", "y": [600, 680]}
      ]
    }
  ]
}
```

- **v1:** las plantillas las crea Jhulen con un script de ayuda. El script detecta las líneas de la tabla (morfología de OpenCV), propone filas y columnas, y lee los textos impresos de los ítems con PP-OCRv6 para corregirlos a mano.
- **v2:** editor visual dentro de la app para que ella agregue formularios nuevos sin ayuda.
- **Varias hojas:** un formulario de varias páginas es una plantilla con varias entradas en `paginas`; sus fotos se agrupan en una sola evaluación.
- **Derechos:** las plantillas e imágenes de referencia no van a un repo público, porque pueden ser instrumentos con derechos de autor.

## Salida en Excel

Cada evaluación genera un .xlsx con la misma forma del papel, y un archivo consolidado por formulario acumula todas para análisis.

**Hoja "Evaluación":** arriba la cabecera (paciente, fecha, formulario); debajo, la tabla del formulario.

| Ítem | Descripción | Nunca | Casi nunca | A veces | Casi siempre | Siempre | Observación | Revisado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Descripción del ítem 1 |  | X |  |  |  | Texto transcrito | Sí |
| 2 | Descripción del ítem 2 |  |  |  | X |  |  | Sí |

- **Imagen opcional:** una columna adicional con el recorte de la observación, insertado como imagen con openpyxl.
- **Consolidado:** un archivo por formulario, con una fila por evaluación y una columna por ítem con el valor elegido, listo para tabular o graficar.
- **Nombre de archivo:** `AAAA-MM-DD_<formulario>_<paciente>.xlsx`, en una carpeta que ella elige la primera vez.

## Fases y esfuerzo

Son unos 16 días de trabajo efectivo hasta el piloto; avanzando en noches y fines de semana, de 6 a 8 semanas. Las fases 1 y 2 pueden avanzar en paralelo.

1. **Fase 0 — Muestras (1 día).** Juntar sus 3–5 formularios más usados: foto en blanco y una llena con datos inventados. Decidir si se reimprimen con marcas en las esquinas.
    - Criterio de salida: carpeta de muestras y lista priorizada de formularios.
2. **Fase 1 — Núcleo de casillas (3–4 días).** Plantilla JSON del primer formulario, registro, OMR y un comando que va de foto a Excel.
    - Criterio de salida: con 10 fotos reales, cada casilla sale correcta o marcada en amarillo; cero errores silenciosos.
3. **Fase 2 — Observaciones (2–3 días).** PP-OCRv6 en ONNX, recortes y confianza por línea.
    - Criterio de salida: tasa de error por carácter medida con su letra y decisión sobre si el texto se muestra como sugerencia o solo la imagen.
4. **Fase 3 — Aplicación (4–5 días).** Servidor local, ventana de escritorio, captura por QR, pantalla de revisión y exportación.
    - Criterio de salida: ella procesa una hoja completa sin ayuda, del celular al Excel.
5. **Fase 4 — Resto de plantillas (2–4 días).** Script de detección de cuadrícula y plantillas de los demás formularios.
    - Criterio de salida: todos los formularios priorizados funcionando.
6. **Fase 5 — Instalador (1–2 días).** PyInstaller + Inno Setup, regla de firewall, ícono en el escritorio y build en GitHub Actions.
    - Criterio de salida: instalación limpia en su laptop sin abrir una terminal.
7. **Fase 6 — Piloto (2 semanas de uso).** Uso real; la app registra cada corrección que ella hace.
    - Criterio de salida: errores medidos por formulario, umbrales ajustados y lista de mejoras para v2.

## Riesgos y mitigaciones

El riesgo principal es que PP-OCRv6 lea mal su letra; el recorte de imagen asegura que la app siga siendo útil aunque eso pase.

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| PP-OCRv6 lee mal la letra a mano | Ella tipea las observaciones | Recorte siempre visible; plan B: modelo grande opcional procesando por lotes |
| Fotos con sombra, curvatura o movidas | Casillas mal leídas | Control de nitidez al subir, guía en pantalla, opción galería con Escanear documentos de Samsung |
| Formularios parecidos se confunden | Plantilla equivocada | QR en la hoja o selección manual cuando la confianza es baja |
| Marcas tenues, tachones o correcciones | Fila con dos marcas | Comparación dentro de la fila y bandera amarilla |
| SmartScreen o antivirus bloquean el .exe | No se instala | Modo onedir e instrucción de "Ejecutar de todos modos" una vez |
| Cambia la IP de la laptop | El celular no conecta | QR nuevo en cada inicio; opcional: IP reservada en el router |
| Datos clínicos en la laptop | Exposición si se pierde el equipo | Nada sale de la red local, sin telemetría, opción de borrar fotos tras exportar, contraseña de Windows y cifrado de disco (BitLocker o Cifrado de dispositivo) |

## Pendientes para arrancar

La Fase 0 depende de estos insumos; los dos primeros bloquean todo lo demás.

- [ ] Fotos en blanco de los 3–5 formularios más usados, tomadas de frente
- [ ] Una foto de cada uno lleno con datos inventados y su letra real
- [ ] Confirmar si las hojas se pueden reimprimir con marcas en las esquinas y QR
- [ ] Definir el Excel: un archivo por evaluación, por paciente o por formulario
- [ ] Saber si hay formularios de más de una hoja
- [ ] Confirmar la versión de Windows de la laptop
- [ ] Crear el repo privado en GitHub