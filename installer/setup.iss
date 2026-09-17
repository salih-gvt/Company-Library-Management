; Inno Setup script for Company Library Management.
;
; Build with:
;   "C:\Users\Dell\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\setup.iss
;
; Output: installer\Company Library Management-Setup.exe

#define MyAppName "Company Library Management"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Gravity BP"
#define MyAppExeName "Company Library.exe"

[Setup]
AppId={{6C7B7C8E-2C7B-4B9A-9F3D-4C7C6C8B7B0A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user data lives in %LOCALAPPDATA%, not here, so uninstalling or
; upgrading the program files never touches the library database.
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=.
OutputBaseFilename={#MyAppName}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Installs for the current user by default (no admin prompt required);
; an admin can still choose "for all users" if run elevated.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Company Library Management\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] entries for the database/Excel file:
; they live under %LOCALAPPDATA%\CompanyLibraryManagement, outside {app},
; so a normal uninstall never removes them.
