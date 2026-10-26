; Inno Setup script for the URL Monitor installer.
; Built by packaging\build.ps1, which passes /DAppVersion=<version>.
; Installs for the current user only, so no administrator rights are needed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId identifies the app for upgrades and uninstalling. Never change it.
AppId={{650DC6BA-9FC4-4F5C-9199-690B49320FD5}
AppName=URL Monitor
AppVersion={#AppVersion}
AppVerName=URL Monitor {#AppVersion}
AppPublisher=SNBDev
AppPublisherURL=https://github.com/snb-dev/url-monitoring-system-Proxy-based
AppSupportURL=https://github.com/snb-dev/url-monitoring-system-Proxy-based/issues
DefaultDirName={localappdata}\Programs\URL Monitor
DefaultGroupName=URL Monitor
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=URLMonitor-Setup-{#AppVersion}
UninstallDisplayIcon={app}\URLMonitor.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "autostart"; Description: "Start URL Monitor when I sign in to Windows"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\URLMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[INI]
Filename: "{app}\Dashboard.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://127.0.0.1:5000/"

[Icons]
Name: "{group}\URL Monitor"; Filename: "{app}\URLMonitor.exe"; Parameters: "start"
Name: "{group}\URL Monitor dashboard"; Filename: "{app}\Dashboard.url"
Name: "{group}\URL Monitor status"; Filename: "{cmd}"; Parameters: "/k ""{app}\URLMonitor.exe"" status"
Name: "{group}\Restore proxy settings"; Filename: "{cmd}"; Parameters: "/k ""{app}\URLMonitor.exe"" restore"
Name: "{autodesktop}\URL Monitor"; Filename: "{app}\URLMonitor.exe"; Parameters: "start"; Tasks: desktopicon

[Run]
Filename: "{app}\URLMonitor.exe"; Parameters: "autostart on"; Flags: runhidden; Tasks: autostart
Filename: "{app}\URLMonitor.exe"; Parameters: "autostart off"; Flags: runhidden; Tasks: not autostart
Filename: "{app}\URLMonitor.exe"; Parameters: "start"; Description: "Start URL Monitor now"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\Dashboard.url"

[UninstallRun]
; Stop URL Monitor, then put the user's proxy settings back (the forced stop
; skips URL Monitor's own clean-up), then remove the start-up entry and the
; certificate. Windows asks the user to confirm removing the certificate.
Filename: "{sys}\taskkill.exe"; Parameters: "/im URLMonitor.exe /f"; Flags: runhidden; RunOnceId: "Stop"
Filename: "{app}\URLMonitor.exe"; Parameters: "restore"; Flags: runhidden; RunOnceId: "RestoreProxy"
Filename: "{app}\URLMonitor.exe"; Parameters: "autostart off"; Flags: runhidden; RunOnceId: "AutostartOff"
Filename: "{app}\URLMonitor.exe"; Parameters: "uninstall-cert"; Flags: runhidden; RunOnceId: "UninstallCert"
