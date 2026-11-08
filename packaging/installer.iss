; DI-R2: instalador de AutoEvalPsi (Inno Setup 6). Se compila desde la raíz del repo:
;   iscc /DVersion=0.1.0 packaging\installer.iss
; Antes hace falta la carpeta dist\AutoEvalPsi que deja PyInstaller (packaging\autoevalpsi.spec).
;
; Decisiones: por máquina (DI-D2) y datos conservados por defecto al desinstalar (DI-D1).
; No crea tareas programadas, servicios, arranque automático ni actualizador (DI-06).

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6C1F6E0A-4B9D-4E52-9C2A-3F7A1D0B8E41}
AppName=AutoEvalPsi
AppVersion={#Version}
AppPublisher=AutoEvalPsi
DefaultDirName={autopf}\AutoEvalPsi
DefaultGroupName=AutoEvalPsi
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\salida
OutputBaseFilename=AutoEvalPsi-Instalador-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\AutoEvalPsi.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un ícono en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\AutoEvalPsi\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\AutoEvalPsi"; Filename: "{app}\AutoEvalPsi.exe"
Name: "{autodesktop}\AutoEvalPsi"; Filename: "{app}\AutoEvalPsi.exe"; Tasks: escritorio

[Run]
; Regla de firewall acotada (DI-03): solo este programa, TCP 8765 y redes de perfil Privado.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""AutoEvalPsi"""; Flags: runhidden; StatusMsg: "Preparando la red local..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""AutoEvalPsi"" dir=in action=allow program=""{app}\AutoEvalPsi.exe"" protocol=TCP localport=8765 profile=private"; Flags: runhidden; StatusMsg: "Permitiendo el celular en la red privada..."
Filename: "{app}\AutoEvalPsi.exe"; Description: "Abrir AutoEvalPsi"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""AutoEvalPsi"""; Flags: runhidden; RunOnceId: "QuitarReglaFirewall"

[Code]
const
  // ISPP toma como directiva toda línea que empieza con «#»: por eso el salto va en una constante.
  NL = #13#10;
  GuidWebView2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function WebView2Instalado(): Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + GuidWebView2, 'pv', Version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + GuidWebView2, 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + GuidWebView2, 'pv', Version);
  Result := Result and (Version <> '') and (Version <> '0.0.0.0');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not WebView2Instalado() and not WizardSilent() then
    if MsgBox('Falta "Microsoft Edge WebView2 Runtime", que AutoEvalPsi usa para mostrar su ventana. ' +
              'Viene con Windows 11 y con Windows 10 actualizado.' + NL + NL +
              'Puedes seguir con la instalación y, si la ventana no abre, instalarlo desde ' +
              'https://go.microsoft.com/fwlink/p/?LinkId=2124703' + NL + NL +
              '¿Continuar con la instalación?', mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Datos: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Datos := ExpandConstant('{localappdata}\AutoEvalPsi');
    if DirExists(Datos) and not UninstallSilent() then
      // «No» (conservar) es el botón por defecto (DI-D1).
      if MsgBox('¿Borrar también las evaluaciones, fotos y plantillas guardadas?' + NL + NL +
                'Si eliges "No", se conservan en:' + NL + Datos + NL +
                'y una reinstalación las encontrará.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Datos, True, True, True);
  end;
end;
