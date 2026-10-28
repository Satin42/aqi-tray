; Per-user installer: no admin prompt, installs to %LOCALAPPDATA%\Programs\AQI Tray.
; Built by .github/workflows/release.yml from the PyInstaller output in dist\AQITray.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0C8A52-3B1E-4C47-9D2A-AB1C7E5D9F30}
AppName=AQI Tray
AppVersion={#AppVersion}
AppPublisher=Dan Demenskyi
AppPublisherURL=https://github.com/Satin42/aqi-tray
DefaultDirName={localappdata}\Programs\AQI Tray
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AQI-Tray-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\AQITray.exe
UninstallDisplayName=AQI Tray
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=force

[Tasks]
Name: "startup"; Description: "Start AQI Tray automatically when I sign in"

[Files]
Source: "..\dist\AQITray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\AQI Tray"; Filename: "{app}\AQITray.exe"
Name: "{userstartup}\AQI Tray"; Filename: "{app}\AQITray.exe"; Tasks: startup

[Run]
Filename: "{app}\AQITray.exe"; Description: "Start AQI Tray now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im AQITray.exe"; Flags: runhidden; RunOnceId: "KillApp"
