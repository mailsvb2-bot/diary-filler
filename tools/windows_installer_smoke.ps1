param(
    [Parameter(Mandatory=$true)][string]$InstallerPath
)

$ErrorActionPreference = 'Stop'
$installer = (Resolve-Path $InstallerPath).Path
$installDir = Join-Path $env:RUNNER_TEMP 'MedicalDiaryAutofill-Installer-Smoke'
$runKeyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValueName = 'MedicalDiaryAutofill Intake'
$startupScript = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\MedicalDiaryAutofill Intake.vbs'
$runtimeDir = Join-Path $env:LOCALAPPDATA 'MedicalDiaryAutofill'
$desktopDir = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktopDir)) {
    throw 'Windows Desktop path is unavailable'
}
$intakeDir = Join-Path $desktopDir 'Выписанные пациенты'
$intakeExistedBefore = Test-Path -LiteralPath $intakeDir
$preserveProbe = Join-Path $intakeDir '.installer-smoke-preserve.txt'
$onboardingMarker = Join-Path $installDir 'onboarding-required.flag'

function Stop-AppProcesses {
    Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue | ForEach-Object {
        try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}

try {
    Stop-AppProcesses
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
    if (-not (Test-Path -LiteralPath $onboardingMarker -PathType Leaf)) {
        throw 'Installer did not create onboarding-required.flag'
    }
    if (-not $intakeExistedBefore -and (Test-Path -LiteralPath $intakeDir -PathType Container)) {
        throw 'Installer unexpectedly created Desktop\Выписанные пациенты before onboarding'
    }

    # Simulate the user accepting first-run creation. A user-owned file must survive uninstall.
    New-Item -ItemType Directory -Path $intakeDir -Force | Out-Null
    Set-Content -LiteralPath $preserveProbe -Value 'preserve intake folder' -Encoding UTF8

    $uninstaller = Get-ChildItem -LiteralPath $installDir -Filter 'unins*.exe' -File | Select-Object -First 1
    if ($null -eq $uninstaller) {
        throw 'Inno Setup uninstaller is missing'
    }

    # Reproduce the real problematic state: watcher is alive and both persistence
    # routes exist when uninstall starts. Uninstall must still complete by itself.
    New-Item -Path $runKeyPath -Force | Out-Null
    New-ItemProperty -Path $runKeyPath -Name $runValueName -Value ('"' + $app + '" --intake-agent') -PropertyType String -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $startupScript) -Force | Out-Null
    Set-Content -LiteralPath $startupScript -Value 'stub' -Encoding Unicode

    $watcher = Start-Process -FilePath $app -ArgumentList @('--intake-agent') -PassThru
    $deadline = [DateTime]::UtcNow.AddSeconds(12)
    do {
        $running = @(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue)
        if ($running.Count -gt 0) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -eq 0) {
        throw 'Failed to start installed intake-agent before uninstall smoke'
    }

    $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART'
    ) -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) {
        throw "Uninstaller exited with code $($uninstall.ExitCode)"
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(8)
    do {
        if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -eq 0) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -ne 0) {
        throw 'MedicalDiaryAutofill process survived uninstall'
    }
    if (Test-Path $app) {
        throw 'Application executable survived uninstall'
    }
    if (Test-Path -LiteralPath $onboardingMarker) {
        throw 'Installer onboarding marker survived uninstall'
    }
    try {
        $leftoverRun = Get-ItemPropertyValue -Path $runKeyPath -Name $runValueName -ErrorAction Stop
        throw "HKCU Run watcher entry survived uninstall: $leftoverRun"
    } catch [System.Management.Automation.PSArgumentException] {
    } catch [System.Management.Automation.ItemNotFoundException] {
    }
    if (Test-Path -LiteralPath $startupScript) {
        throw 'Startup watcher script survived uninstall'
    }
    if (-not (Test-Path -LiteralPath $intakeDir -PathType Container)) {
        throw 'Uninstaller removed Desktop\Выписанные пациенты'
    }
    if (-not (Test-Path -LiteralPath $preserveProbe -PathType Leaf)) {
        throw 'Uninstaller removed a user-owned file from Desktop\Выписанные пациенты'
    }

    Write-Host 'WINDOWS INSTALLER ACTIVE-WATCHER UNINSTALL SMOKE OK'
}
finally {
    Stop-AppProcesses
    Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupScript -Force -ErrorAction SilentlyContinue
    if (Test-Path $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $preserveProbe -Force -ErrorAction SilentlyContinue
    if (-not $intakeExistedBefore -and (Test-Path -LiteralPath $intakeDir -PathType Container)) {
        $remaining = @(Get-ChildItem -LiteralPath $intakeDir -Force -ErrorAction SilentlyContinue)
        if ($remaining.Count -eq 0) {
            Remove-Item -LiteralPath $intakeDir -Force -ErrorAction SilentlyContinue
        }
    }
    # Only technical runtime files are test residue. Real patient folders/documents are never touched here.
    foreach ($name in @(
        'desktop-intake-gui.heartbeat',
        'desktop-intake-agent.heartbeat',
        'desktop-intake-agent-handoff.json',
        'desktop-intake-agent.log',
        'self-check.txt'
    )) {
        Remove-Item -LiteralPath (Join-Path $runtimeDir $name) -Force -ErrorAction SilentlyContinue
    }
}
