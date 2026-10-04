param(
    [Parameter(Mandatory=$true)][string]$InstallerPath
)

$ErrorActionPreference = 'Stop'
$installerSource = (Resolve-Path $InstallerPath).Path
$installerProbeDir = Join-Path $env:RUNNER_TEMP 'Проверка установщика с пробелами'
$installer = Join-Path $installerProbeDir 'MedicalDiaryAutofill Установщик тест.exe'
$installDir = Join-Path $env:RUNNER_TEMP 'MedicalDiaryAutofill-Installer-Smoke'
$selfDeleteHelper = Join-Path $installDir '.MedicalDiaryAutofill-delete-setup.cmd'
$runKeyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValueName = 'MedicalDiaryAutofill Intake'
$patientSummaryRunValueName = 'MedicalDiaryAutofill Patients'
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
$installedFixtureName = 'Первичный_installed_intake_E2E.docx'
$installedFixture = Join-Path $intakeDir $installedFixtureName
$installedCreatedPatientFolder = $null
$ciLicenseProvisioner = Join-Path $PSScriptRoot 'provision_ci_license.py'
$ciLicenseProvisioned = $false

function Provision-CiLicenseForCurrentProfile {
    if ($env:MEDICAL_AUTOFILL_LICENSE_REQUIRED -ne '1') { return }
    if ([string]::IsNullOrWhiteSpace($env:MEDICAL_AUTOFILL_CI_ACTIVATION_CODE)) {
        throw 'Licensed installer E2E requires MEDICAL_AUTOFILL_CI_ACTIVATION_CODE GitHub Actions secret'
    }
    & python $ciLicenseProvisioner
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not provision a real signed license for installed E2E'
    }
    $script:ciLicenseProvisioned = $true
    # The secret is required only by the provisioning subprocess. Never let
    # Setup or the installed application inherit it.
    Remove-Item Env:MEDICAL_AUTOFILL_CI_ACTIVATION_CODE -ErrorAction SilentlyContinue
}

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

function Wait-ForInstallerSelfDelete {
    param([int]$TimeoutSeconds = 70)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (-not (Test-Path -LiteralPath $installer)) {
            $helperDeadline = [DateTime]::UtcNow.AddSeconds(10)
            do {
                if (-not (Test-Path -LiteralPath $selfDeleteHelper)) {
                    return
                }
                Start-Sleep -Milliseconds 200
            } while ([DateTime]::UtcNow -lt $helperDeadline)
            throw 'Installer self-delete helper did not remove itself'
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Downloaded installer did not delete itself after successful installation'
}

try {
    Provision-CiLicenseForCurrentProfile
    Stop-AppProcesses
    New-Item -ItemType Directory -Path $installerProbeDir -Force | Out-Null
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $installerSource -Destination $installer -Force
    Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $runKeyPath -Name $patientSummaryRunValueName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupScript -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $agentHeartbeat -Force -ErrorAction SilentlyContinue
    if (Test-Path $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force
    }

    # Do not use Start-Process -Wait here: on Windows it waits for the full
    # descendant process tree, and a correct installation intentionally leaves
    # the intake-agent child running. WaitForExit() waits only for Setup itself.
    $install = Start-Process -FilePath $installer -ArgumentList @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART',
        "/DIR=$installDir"
    ) -PassThru
    $install.WaitForExit()
    if ($install.ExitCode -ne 0) {
        throw "Installer exited with code $($install.ExitCode)"
    }

    $app = Join-Path $installDir 'MedicalDiaryAutofill.exe'
    if (-not (Test-Path $app)) {
        throw 'Installed MedicalDiaryAutofill.exe is missing'
    }
    $internalDir = Join-Path $installDir '_internal'
    if (-not (Test-Path -LiteralPath $internalDir -PathType Container)) {
        throw 'Installer did not deploy the fast PyInstaller onedir runtime'
    }

    # User-facing regression: after a successful install the downloaded Setup
    # must remove itself automatically. The installed agent must stay alive and
    # the original build artifact used to create the disposable copy must remain.
    Wait-ForAgentHeartbeat
    if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -eq 0) {
        throw 'Installer-started intake-agent is not running before installer self-delete probe'
    }

    Wait-ForInstallerSelfDelete
    if (-not (Test-Path -LiteralPath $installerSource -PathType Leaf)) {
        throw 'Installer self-delete removed the build artifact instead of only the launched Setup copy'
    }
    if (@(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue).Count -eq 0) {
        throw 'Background agent stopped when the downloaded installer self-deleted'
    }
    Write-Host 'INSTALLER AUTO-SELF-DELETE WHILE AGENT RUNS PROBE OK'

    # Measure the actual installed onedir startup path, not the slower portable
    # one-file launcher. The startup probe constructs the real GUI and TkDND
    # wiring, writes evidence, then exits before mainloop.
    $probeResult = Join-Path $env:RUNNER_TEMP 'MedicalDiaryAutofill-installed-startup-probe.txt'
    Remove-Item -LiteralPath $probeResult -Force -ErrorAction SilentlyContinue
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $app
    $psi.WorkingDirectory = $installDir
    $psi.UseShellExecute = $false
    $psi.Environment['MEDICAL_AUTOFILL_STARTUP_PROBE'] = '1'
    $psi.Environment['MEDICAL_AUTOFILL_STARTUP_PROBE_RESULT'] = $probeResult
    $startupWatch = [Diagnostics.Stopwatch]::StartNew()
    $startupProbe = [Diagnostics.Process]::Start($psi)
    if (-not $startupProbe.WaitForExit(8000)) {
        try { $startupProbe.Kill($true) } catch {}
        throw 'Installed application startup probe exceeded hard 8 second timeout'
    }
    $startupWatch.Stop()
    if ($startupProbe.ExitCode -ne 0) {
        throw "Installed application startup probe exited with code $($startupProbe.ExitCode)"
    }
    if (-not (Test-Path -LiteralPath $probeResult)) {
        throw 'Installed application startup probe did not write evidence'
    }
    $probeText = Get-Content -LiteralPath $probeResult -Raw
    if ($probeText -notmatch 'OK' -or $probeText -notmatch 'dnd=1') {
        throw "Installed application startup evidence is incomplete: $probeText"
    }
    $startupMs = [math]::Round($startupWatch.Elapsed.TotalMilliseconds, 0)
    Write-Host "INSTALLED ONEDIR STARTUP PROBE: $startupMs ms"
    if ($startupWatch.Elapsed.TotalSeconds -gt 5.0) {
        throw "Installed application exceeded production startup budget: $startupMs ms > 5000 ms"
    }
    if (-not (Test-Path -LiteralPath $onboardingMarker -PathType Leaf)) {
        throw 'Installer did not create onboarding-required.flag'
    }

    # The startup probe intentionally does not consume first-run onboarding.
    # For the installed intake E2E, preconfigure staff and consume the marker so
    # no modal dialog can hide the actual watcher -> visible-GUI latency.
    $settingsDir = Join-Path $env:APPDATA 'MedicalDiaryAutofill'
    New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
    @{
        desktop_intake_enabled = $true
        staff_profile = @{
            configured = $true
            doctor = 'Автоврач А.А.'
            department_head = 'Автозаведующая З.З.'
            deputy_chief = 'Автозам Д.Д.'
        }
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $settingsDir 'settings.json') -Encoding UTF8
    Remove-Item -LiteralPath $onboardingMarker -Force

    $fixtureBuilder = Join-Path $env:RUNNER_TEMP 'make_installed_intake_fixture.py'
    @'
import sys
from docx import Document
p = sys.argv[1]
d = Document()
d.add_paragraph("12.05.2026 Первичный осмотр")
d.add_paragraph("История болезни № INSTALLED-E2E-001")
d.add_paragraph("Ф.И.О.: Маркер Установочный Тестовый")
d.add_paragraph("Дата рождения: 01.01.1980")
d.add_paragraph("Жалобы при поступлении: тестовая запись")
d.add_paragraph("Анамнез жизни: без особенностей")
d.add_paragraph("Психический статус: контактен, ориентирован")
d.add_paragraph("Диагноз: F20.0")
d.add_paragraph("План лечения: тестовая терапия")
d.save(p)
'@ | Set-Content -LiteralPath $fixtureBuilder -Encoding UTF8

    $dropWatch = [Diagnostics.Stopwatch]::StartNew()
    & python $fixtureBuilder $installedFixture
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $installedFixture)) {
        throw 'Failed to create installed intake E2E primary DOCX'
    }

    $visibleDeadline = [DateTime]::UtcNow.AddSeconds(8)
    $visibleFound = $false
    do {
        foreach ($process in @(Get-Process -Name 'MedicalDiaryAutofill' -ErrorAction SilentlyContinue)) {
            try {
                $process.Refresh()
                if ($process.MainWindowHandle -ne 0) {
                    $visibleFound = $true
                    break
                }
            } catch {}
        }
        if ($visibleFound) { break }
        Start-Sleep -Milliseconds 100
    } while ([DateTime]::UtcNow -lt $visibleDeadline)
    $dropWatch.Stop()
    $installedDropMs = [math]::Round($dropWatch.Elapsed.TotalMilliseconds, 0)
    Write-Host "INSTALLED INTAKE drop-to-visible latency: $installedDropMs ms"
    if (-not $visibleFound) {
        throw 'Installed watcher did not open a visible GUI for the dropped primary DOCX'
    }
    if ($dropWatch.Elapsed.TotalSeconds -gt 5.0) {
        throw "Installed watcher exceeded production drop-to-visible budget: $installedDropMs ms > 5000 ms"
    }

    $moveDeadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        if (-not (Test-Path -LiteralPath $installedFixture)) {
            $moved = Get-ChildItem -LiteralPath $intakeDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $candidate = Join-Path $_.FullName $installedFixtureName
                if (Test-Path -LiteralPath $candidate) { Get-Item -LiteralPath $candidate }
            } | Select-Object -First 1
            if ($null -ne $moved) {
                $installedCreatedPatientFolder = $moved.Directory.FullName
                break
            }
        }
        Start-Sleep -Milliseconds 150
    } while ([DateTime]::UtcNow -lt $moveDeadline)
    if (-not $installedCreatedPatientFolder) {
        throw 'Installed watcher GUI did not move the primary DOCX into a patient subfolder'
    }

    # Restore a marker before uninstall so the original cleanup proof remains
    # meaningful even though the installed-intake E2E consumed first-run state.
    Set-Content -LiteralPath $onboardingMarker -Value 'installer-smoke-uninstall-proof' -Encoding ASCII

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

    # Simulate the entry created after the user configures «Мои пациенты».
    # The uninstaller must own cleanup even if the GUI is no longer runnable.
    Set-ItemProperty -Path $runKeyPath -Name $patientSummaryRunValueName -Value ('"' + $app + '" --patient-summary')

    $uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @(
        '/VERYSILENT',
        '/SUPPRESSMSGBOXES',
        '/NORESTART'
    ) -PassThru
    $uninstall.WaitForExit()
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
    try {
        $leftoverSummary = Get-ItemPropertyValue -Path $runKeyPath -Name $patientSummaryRunValueName -ErrorAction Stop
        throw "HKCU Run patient summary entry survived uninstall: $leftoverSummary"
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

    Write-Host 'WINDOWS INSTALLER FAST ONEDIR WATCHER BOOTSTRAP AND UNINSTALL SMOKE OK'
}
finally {
    Stop-AppProcesses
    if ($ciLicenseProvisioned) {
        & python $ciLicenseProvisioner --cleanup
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'Could not clean the temporary CI license profile'
        }
    }
    Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $selfDeleteHelper -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $installerProbeDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $startupScript -Force -ErrorAction SilentlyContinue
    if (Test-Path $installDir) {
        Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $preserveProbe -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $installedFixture -Force -ErrorAction SilentlyContinue
    if ($installedCreatedPatientFolder) {
        Remove-Item -LiteralPath $installedCreatedPatientFolder -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath (Join-Path $env:RUNNER_TEMP 'MedicalDiaryAutofill-installed-startup-probe.txt') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:RUNNER_TEMP 'make_installed_intake_fixture.py') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $env:APPDATA 'MedicalDiaryAutofill\settings.json') -Force -ErrorAction SilentlyContinue
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