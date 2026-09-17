#define MyAppName "MedicalDiaryAutofill"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.14"
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
; The intake folder is part of the installed workflow and belongs to the user.
; It must exist before the first GUI launch and must survive uninstall.
Name: "{userdesktop}\Выписанные пациенты"; Flags: uninsneveruninstall

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; Bootstrap the hidden watcher at logon even if the GUI has never been opened.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MedicalDiaryAutofill Intake"; ValueData: """{app}\{#MyAppExeName}"" --intake-agent"; Flags: uninsdeletevalue

[InstallDelete]
; An in-place update must not leave a stale build-identity handoff that makes the
; freshly installed watcher retire itself before it can observe the intake folder.
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent-handoff.json"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-gui.heartbeat"

[Icons]
Name: "{group}\MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Проверить MedicalDiaryAutofill"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--self-check"

[Run]
; Start the watcher independently of the optional visible post-install launch.
; This is what makes dropping a DOC/DOCX work immediately after install/update.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--intake-agent"; Flags: runhidden nowait
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить MedicalDiaryAutofill"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{autostartup}\MedicalDiaryAutofill Intake.vbs"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-gui.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent-handoff.json"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.log"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\self-check.txt"
Type: files; Name: "{app}\onboarding-required.flag"
Type: dirifempty; Name: "{localappdata}\MedicalDiaryAutofill"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Force one visible onboarding after every install/upgrade. }
    SaveStringToFile(ExpandConstant('{app}\onboarding-required.flag'), '1', False);
  end;
end;

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
