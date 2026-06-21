; Inno Setup script — builds a Windows setup.exe for the Aviation Maintenance
; Records Processor (the Streamlit app + the Go handwriting OCR engine, with a
; private Python runtime bundled). Produces a single installer the recipient
; double-clicks; no Python, no admin rights, nothing else to install.
;
; Build it with:  build_installer.bat   (from the repo root)
; or directly:    ISCC.exe installer\aviation_app.iss
;
; Prerequisites on the BUILD machine (not the end user's):
;   1) Inno Setup 6  -> https://jrsoftware.org/isdl.php  (provides ISCC.exe)
;   2) runtime\      -> built by build_portable.bat (embeddable Python + deps)
;   3) handwriting.exe at the repo root -> the Go engine (build_installer.bat
;      builds it, or drop a prebuilt one there)

#define AppName "Aviation Maintenance Records Processor"
#define AppShort "AviationRecordsProcessor"
#define AppVersion "1.0.0"
#define AppPublisher "Aviation Records"
#define Launcher "run.bat"

[Setup]
; A stable GUID identifies this app for upgrades/uninstall. Generated once.
AppId={{8F3C2E14-7A6B-4C29-9D51-2B0E7F4A1C88}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Per-user install to a writable location: the app stores records.db, uploads,
; and output beside itself, which would fail under Program Files without admin.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppShort}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_installer
OutputBaseFilename={#AppShort}-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; App code (all top-level Python modules) and launcher.
Source: "..\*.py";              DestDir: "{app}"; Flags: ignoreversion
Source: "..\{#Launcher}";       DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements*.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example";      DestDir: "{app}"; Flags: ignoreversion
; The Go handwriting OCR engine (single static exe, model embedded).
Source: "..\handwriting.exe";   DestDir: "{app}"; Flags: ignoreversion
; Private Python runtime built by build_portable.bat.
Source: "..\runtime\*";         DestDir: "{app}\runtime";   Flags: ignoreversion recursesubdirs createallsubdirs
; Form templates shipped with the app.
Source: "..\templates\*";       DestDir: "{app}\templates"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Writable working folders the app expects at runtime.
Name: "{app}\uploads"
Name: "{app}\output"

[Icons]
Name: "{group}\{#AppName}";        Filename: "{app}\{#Launcher}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#Launcher}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offer to launch immediately after install.
Filename: "{app}\{#Launcher}"; Description: "Launch {#AppName} now"; Flags: postinstall skipifsilent nowait shellexec

[UninstallDelete]
; Remove generated caches; leaves user data (records.db, uploads, output) in
; place by default so an uninstall/reinstall does not wipe their records.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\runtime"
