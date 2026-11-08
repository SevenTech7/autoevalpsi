# Guía de instalación de AutoEvalPsi (una página)

Para instalar en tu laptop y después en la de tu hermana. No hace falta abrir ninguna terminal.

## Antes de empezar

- **Windows 10 u 11 de 64 bits.** La laptop de tu hermana (Ryzen 7 4700U, 8 GB de RAM, unos 46 GB
  libres) cumple de sobra: la aplicación usa unos 520 MB de memoria mientras lee una foto (medido) y
  el instalador pesa 156 MB. No usa la tarjeta gráfica; lee con el procesador, unos 20 a 40 segundos
  por foto.
- **El celular y la laptop en el mismo WiFi**, y ese WiFi en Windows como **red privada**
  (Configuración → Red e Internet → WiFi → tu red → «Privada»).
- Tener a mano los dos archivos de formularios (`formulario-vineland-3.zip` y
  `formulario-neuropsicologica.zip`) y tu libro de Excel de Vineland.

## 1. Conseguir el instalador

1. Entra a GitHub con tu cuenta y abre
   `github.com/SevenTech7/autoevalpsi/actions/runs/42518065928` (el repositorio es privado).
2. Abajo, en **Artifacts**, descarga `AutoEvalPsi-0.1.0` (unos 156 MB). Trae el instalador y un
   archivo `.sha256`.

## 2. Instalar

1. Descomprime el .zip y abre `AutoEvalPsi-Instalador-0.1.0.exe`.
2. Windows mostrará **«Windows protegió su PC»** (SmartScreen), porque el instalador todavía no
   está firmado. Pulsa **Más información → Ejecutar de todos modos**. Es normal.
3. Pulsa **Sí** cuando pida permiso de administrador (una sola vez: crea la regla de red privada).
4. Si falta «Microsoft Edge WebView2 Runtime», el instalador lo avisa y lo instalas desde el
   enlace que muestra.
5. Al terminar, abre **AutoEvalPsi** desde el menú Inicio.

## 3. Primera vez

1. **Formularios:** pantalla **Plantillas** → «Importar una plantilla (.zip)» → elige
   `formulario-vineland-3.zip`; repite con `formulario-neuropsicologica.zip`.
2. **Celular:** en **Inicio**, tarjeta «Celular» → «Vincular celular». Lee el código QR con la
   cámara del celular (una sola vez; después queda vinculado). Si Windows pregunta por el acceso a
   la red, elige **Redes privadas**.
3. **Prueba:** en el celular elige el formulario, toma la foto de una hoja (con buena luz, hoja
   entera, plana). La aplicación reconoce sola si es la hoja 1 o la 2. Mira el resultado en
   **Evaluaciones** y exporta.
4. Los Excel salen a **Descargas**. Se puede cambiar en **Configuración**.

## Si algo falla

- **No encuentra el formulario o dice «no se reconoce»:** revisa que elegiste el formulario
  correcto y que la hoja se vea entera, sobre un fondo que contraste.
- **El celular no conecta:** misma red WiFi, red en «Privada», y vuelve a pulsar «Vincular
  celular» para un código nuevo.
- **Quieres empezar de cero con una evaluación:** en la lista, botón **Eliminar** (los Excel que
  ya exportaste no se tocan).

## Para tu hermana (el equipo que usará a diario)

- Activa una **contraseña de Windows** y, si el equipo lo permite, el **cifrado de dispositivo** o
  BitLocker (Configuración → Privacidad y seguridad → Cifrado de dispositivo): las fotos y las
  evaluaciones quedan guardadas en `%LOCALAPPDATA%\AutoEvalPsi`.
- Las fotos se pueden borrar desde la evaluación una vez revisada; lo leído y lo corregido se queda.
