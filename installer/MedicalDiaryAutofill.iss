#define MyAppName "MedicalDiaryAutofill"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.8"
#endif
#define MyAppExeName "MedicalDiaryAutofill.exe"

[Setup]
AppId={{C54E563F-55F4-4D9A-A6EB-2A5C0E7722B4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=MedicalDiaryAutofill
DefaultDirName={localappdata}\MedicalDiaryAutofill
DefaultGroupName=MedicalDiaryAutofill
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MedicalDiaryAutofill-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Dirs]
; The normal installed workflow must expose the intake folder immediately,
; even before the first GUI launch. Patient data belongs to the user, so the
; uninstaller must never remove this folder, including when it is empty.
Name: "{userdesktop}\Выписанные пациенты"; Flags: uninsneveruninstall

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Проверить MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--self-check"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить MedicalDiaryAutofill"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{autostartup}\MedicalDiaryAutofill Intake.vbs"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-gui.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent-handoff.json"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.log"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\self-check.txt"
Type: dirifempty; Name: "{localappdata}\MedicalDiaryAutofill"

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  { Uninstall must never be blocked by a damaged/stale watcher. }
  { Remove both persistence routes first, then stop every process of this app. }
  RegDeleteValue(
    HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Run',
    'MedicalDiaryAutofill Intake'
  );
  DeleteFile(ExpandConstant('{userstartup}\MedicalDiaryAutofill Intake.vbs'));

  { taskkill is best-effort: even "process not found" must not cancel uninstall. }
  Exec(
    ExpandConstant('{sys}\taskkill.exe'),
    '/F /IM {#MyAppExeName}',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  Result := True;
end;
