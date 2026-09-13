#define MyAppName "MedicalDiaryAutofill"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.4"
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
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent-handoff.json"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\desktop-intake-agent.log"
Type: files; Name: "{localappdata}\MedicalDiaryAutofill\self-check.txt"
Type: dirifempty; Name: "{localappdata}\MedicalDiaryAutofill"

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  AppExe: String;
begin
  Result := True;
  AppExe := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(AppExe) then
  begin
    if (not Exec(AppExe, '--uninstall-intake-agent', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      SuppressibleMsgBox('Не удалось безопасно завершить фоновое наблюдение MedicalDiaryAutofill. Закройте программу и повторите удаление.', mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;
