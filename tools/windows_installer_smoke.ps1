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
$agentHeartbeat = Join-Path $runtimeDir 'desktop-intake-agent.heartbeat'
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

function Wait-ForAgentHeartbeat {
    param([int]$TimeoutSeconds = 20)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (Test-Path -LiteralPath $agentHeartbeat) {
            try {
                $payload = Get-Content -LiteralPath $agentHeartbeat -Raw | ConvertFrom-Json
                $age = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 - [double]$payload.timestamp
                if ($payload.schema -eq 1 -and $payload.identity -and $age -ge 0 -and $age -le 8) {
                    return
                }
            } catch {}
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Installer did not bootstrap a live intake-agent heartbeat'
}

try {
    Stop-AppProcesses
    Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupScript -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $agentHeartbeat -Force -ErrorAction SilentlyContinue
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
    if (-not (Test-Path -LiteralPath $intakeDir -PathType Container)) {
        throw 'Installer did not create Desktop\Выписанные пациенты before first GUI launch'
    }

    $runValue = Get-ItemPropertyValue -Path $runKeyPath -Name $runValueName -ErrorAction Stop
    if ([string]$runValue -notmatch '--intake-agent') {
        throw 'Installer HKCU Run watcher entry does not contain --intake-agent'
    }
    if ([string]$runValue -notmatch [regex]::Escape($app)) {
        throw 'Installer HKCU Run watcher entry does not target the installed EXE'
    }

    # Critical production proof: the hidden watcher must already be alive after a
    # silent install, before any normal GUI launch has happened.
    Wait-ForAgentHeartbeat

    Set-Content -LiteralPath $preserveProbe -Value 'preserve intake folder' -Encoding UTF8

    $uninstaller = Get-ChildItem -LiteralPath $installDir -Filter 'unins*.exe' -File | Select-Object -First 1
    if ($null -eq $uninstaller) {
        throw 'Inno Setup uninstaller is missing'
    }

    # Keep the Startup route present too so uninstall proves it cleans both
    # persistence routes while the installer-started watcher is alive.
    New-Item -ItemType Directory -Path (Split-Path -Parent $startupScript) -Force | Out-Null
    Set-Content -LiteralPath $startupScript -Value 'stub' -Encoding Unicode

    if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -eq 0) {
        throw 'Installer-started intake-agent process is not running before uninstall'
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

    Write-Host 'WINDOWS INSTALLER WATCHER BOOTSTRAP AND UNINSTALL SMOKE OK'
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