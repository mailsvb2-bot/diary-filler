param(
    [Parameter(Mandatory=$true)][string]$InstallerPath
)

$ErrorActionPreference = 'Stop'
$installer = (Resolve-Path $InstallerPath).Path
$installDir = Join-Path $env:RUNNER_TEMP 'MedicalDiaryAutofill-Installer-Smoke'

if (Test-Path $installDir) {
    Remove-Item -LiteralPath $installDir -Recurse -Force
}

$install = Start-Process -FilePath $installer -ArgumentList @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/NORESTART',
    "/DIR=$installDir"
) -Wait -PassThru
if ($install.ExitCode -ne 0) {
    throw "Installer exited with code $($install.ExitCode)"
}

$app = Join-Path $installDir 'MedicalDiaryAutofill.exe'
if (-not (Test-Path $app)) {
    throw 'Installed MedicalDiaryAutofill.exe is missing'
}

# Do not count a successful copy as an installation smoke. Launch the exact
# installed EXE in normal GUI mode and require a real visible top-level window.
# The child PowerShell script throws on failure; $ErrorActionPreference='Stop'
# propagates that failure. Do not inspect $LASTEXITCODE here because a .ps1
# invocation does not own/reset the native-process exit-code register.
& (Join-Path $PSScriptRoot 'windows_visible_gui_smoke.ps1') -AppPath $app

$uninstaller = Get-ChildItem -LiteralPath $installDir -Filter 'unins*.exe' -File | Select-Object -First 1
if ($null -eq $uninstaller) {
    throw 'Inno Setup uninstaller is missing'
}

$uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
    '/VERYSILENT',
    '/SUPPRESSMSGBOXES',
    '/NORESTART'
) -Wait -PassThru
if ($uninstall.ExitCode -ne 0) {
    throw "Uninstaller exited with code $($uninstall.ExitCode)"
}

if (Test-Path $app) {
    throw 'Application executable survived uninstall'
}

Write-Host 'WINDOWS INSTALLER SMOKE OK'
