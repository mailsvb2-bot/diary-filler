#define MyAppName "MedicalDiaryAutofill"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.28"
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
; Installed builds use PyInstaller onedir: no per-launch onefile extraction delay.
Source: "..\dist\installed\MedicalDiaryAutofill\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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

[UninstallDelete]
Type: files; Name: "{autostartup}\MedicalDiaryAutofill Intake.vbs"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-gui.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.heartbeat"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent-handoff.json"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.log"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\self-check.txt"
Type: files; Name: "{app}\onboarding-required.flag"
Type: files; Name: "{app}\.MedicalDiaryAutofill-delete-setup.cmd"
Type: dirifempty; Name: "{localappdata}\MedicalDiaryAutofill"

[Code]
procedure ScheduleSetupSelfDelete;
var
  ResultCode: Integer;
  SourceExe: String;
  CleanupScript: String;
  ScriptBody: String;
begin
  { ssDone is reached only after a successful installation. Start a detached
    helper from the installed app directory, then let Setup terminate. The
    helper retries until Windows releases the original Setup EXE, removes it,
    and finally removes itself. }
  SourceExe := ExpandConstant('{srcexe}');
  CleanupScript := ExpandConstant('{app}\.MedicalDiaryAutofill-delete-setup.cmd');
  ScriptBody :=
    '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "target=%~1"' + #13#10 +
    'for /L %%I in (1,1,60) do (' + #13#10 +
    '  del /F /Q "%target%" >nul 2>&1' + #13#10 +
    '  if not exist "%target%" goto deleted' + #13#10 +
    '  >nul 2>&1 ping 127.0.0.1 -n 2' + #13#10 +
    ')' + #13#10 +
    ':deleted' + #13#10 +
    'del /F /Q "%~f0" >nul 2>&1' + #13#10;

  if not SaveStringToFile(CleanupScript, ScriptBody, False) then
  begin
    Log('Could not write setup self-delete helper: ' + CleanupScript);
    Exit;
  end;

  if not Exec(
    CleanupScript,
    '"' + SourceExe + '"',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewNoWait,
    ResultCode
  ) then
    Log(Format('Could not schedule setup self-delete: %s', [SysErrorMessage(ResultCode)]))
  else
    Log('Scheduled setup self-delete for: ' + SourceExe);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Force one visible onboarding after every install/upgrade. }
    SaveStringToFile(ExpandConstant('{app}\onboarding-required.flag'), '1', False);
  end
  else if CurStep = ssDone then
  begin
    ScheduleSetupSelfDelete;
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
  { The visible daily patient summary is registered by the app only after the
    user explicitly selects the patient root. Uninstall must remove that
    application-owned persistence too. }
  RegDeleteValue(
    HKCU,
    'Software\Microsoft\Windows\CurrentVersion\Run',
    'MedicalDiaryAutofill Patients'
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
