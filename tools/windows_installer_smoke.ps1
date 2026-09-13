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
