param(
    [Parameter(Mandatory=$true)][string]$AppPath
)

$ErrorActionPreference = 'Stop'
$app = (Resolve-Path $AppPath).Path
$testRoot = Join-Path $env:RUNNER_TEMP ("MedicalDiaryAutofill-Intake-E2E-" + [guid]::NewGuid().ToString('N'))
$appData = Join-Path $testRoot 'AppData\Roaming'
$localAppData = Join-Path $testRoot 'AppData\Local'
$settingsDir = Join-Path $appData 'MedicalDiaryAutofill'
$runtimeDir = Join-Path $localAppData 'MedicalDiaryAutofill'
$agentHeartbeat = Join-Path $runtimeDir 'desktop-intake-agent.heartbeat'
$agentLog = Join-Path $runtimeDir 'desktop-intake-agent.log'
$startupScript = Join-Path $appData 'Microsoft\Windows\Start Menu\Programs\Startup\MedicalDiaryAutofill Intake.vbs'
$runKeyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValueName = 'MedicalDiaryAutofill Intake'

function Resolve-DesktopPath {
    try {
        $raw = Get-ItemPropertyValue -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' -Name 'Desktop' -ErrorAction Stop
        if ($raw) {
            $expanded = [Environment]::ExpandEnvironmentVariables([string]$raw)
            if ($expanded) { return [IO.Path]::GetFullPath($expanded) }
        }
    } catch {}
    $fallback = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
    if (-not $fallback) { throw 'Cannot resolve Windows Desktop for intake E2E' }
    return [IO.Path]::GetFullPath($fallback)
}

$desktop = Resolve-DesktopPath
$intakeRoot = Join-Path $desktop 'Выписанные пациенты'
$intakeExisted = Test-Path -LiteralPath $intakeRoot
$fixtureName = 'Первичный_автозапуск_E2E.docx'
$fixture = Join-Path $intakeRoot $fixtureName
$createdPatientFolder = $null

$oldRunExists = $false
$oldRunValue = $null
try {
    $oldRunValue = Get-ItemPropertyValue -Path $runKeyPath -Name $runValueName -ErrorAction Stop
    $oldRunExists = $true
} catch {}

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class IntakeVisibleWindowProbe {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr extraData);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    public static bool HasVisibleTopLevelWindow(int targetPid) {
        bool found = false;
        EnumWindows((hWnd, lParam) => {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pid == (uint)targetPid && IsWindowVisible(hWnd)) {
                found = true;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
'@

function Get-AppProcessRecords {
    $resolved = [IO.Path]::GetFullPath($app)
    @(Get-CimInstance Win32_Process -Filter "Name = 'MedicalDiaryAutofill.exe'" -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ([IO.Path]::GetFullPath([string]$_.ExecutablePath) -ieq $resolved)
    })
}

function Wait-Until {
    param(
        [Parameter(Mandatory=$true)][string]$Description,
        [Parameter(Mandatory=$true)][scriptblock]$Condition,
        [int]$TimeoutSeconds = 35
    )
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (& $Condition) { return }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $deadline)
    Write-Host "INTAKE E2E timeout diagnostics: $Description"
    try {
        $records = @(Get-AppProcessRecords)
        foreach ($record in $records) {
            $isAgent = [bool]([string]$record.CommandLine -match '--intake-agent')
            $isPrimary = [bool]([string]$record.CommandLine -match '--intake-primary')
            Write-Host "  process pid=$($record.ProcessId) agent=$isAgent primary=$isPrimary"
        }
        Write-Host "  fixture_present=$(Test-Path -LiteralPath $fixture)"
        if (Test-Path -LiteralPath $agentHeartbeat) {
            Write-Host "  agent_heartbeat=$(Get-Content -LiteralPath $agentHeartbeat -Raw)"
        }
        if (Test-Path -LiteralPath $agentLog) {
            Write-Host '  agent_log_begin'
            Get-Content -LiteralPath $agentLog | Select-Object -Last 40 | ForEach-Object { Write-Host "    $_" }
            Write-Host '  agent_log_end'
        }
    } catch {
        Write-Host "  diagnostics_failed=$($_.Exception.GetType().Name)"
    }
    throw "Timed out waiting for: $Description"
}

function Start-IsolatedApp {
    param([string[]]$Arguments = @())
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $app
    $psi.WorkingDirectory = Split-Path -Parent $app
    $psi.UseShellExecute = $false
    $null = $psi.Environment.Remove('CI')
    $null = $psi.Environment.Remove('MEDICAL_AUTOFILL_DISABLE_DESKTOP_INTAKE')
    $psi.Environment['APPDATA'] = $appData
    $psi.Environment['LOCALAPPDATA'] = $localAppData
    foreach ($arg in $Arguments) { $psi.ArgumentList.Add($arg) }
    return [Diagnostics.Process]::Start($psi)
}

function Test-AppHasVisibleWindow {
    foreach ($record in @(Get-AppProcessRecords | Where-Object { $_.CommandLine -notmatch '--intake-agent' })) {
        try {
            if ([IntakeVisibleWindowProbe]::HasVisibleTopLevelWindow([int]$record.ProcessId)) { return $true }
        } catch {}
    }
    return $false
}

function Stop-TestAppProcesses {
    foreach ($record in @(Get-AppProcessRecords)) {
        try { Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
}

try {
    New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
    New-Item -ItemType Directory -Path $intakeRoot -Force | Out-Null
    Remove-Item -LiteralPath $fixture -Force -ErrorAction SilentlyContinue

    $settings = @{
        desktop_intake_enabled = $true
        staff_profile = @{
            configured = $true
            doctor = 'Автоврач А.А.'
            department_head = 'Автозаведующая З.З.'
            deputy_chief = 'Автозам Д.Д.'
        }
    } | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath (Join-Path $settingsDir 'settings.json') -Value $settings -Encoding UTF8

    $initialGui = Start-IsolatedApp
    Wait-Until -Description 'watcher heartbeat after normal GUI start' -TimeoutSeconds 25 -Condition {
        if (-not (Test-Path -LiteralPath $agentHeartbeat)) { return $false }
        try {
            $hb = Get-Content -LiteralPath $agentHeartbeat -Raw | ConvertFrom-Json
            return ($hb.schema -eq 1 -and $hb.timestamp -and $hb.identity)
        } catch { return $false }
    }
    Wait-Until -Description 'hidden intake-agent process' -Condition {
        @((Get-AppProcessRecords) | Where-Object { $_.CommandLine -match '--intake-agent' }).Count -ge 1
    }
    if (-not (Test-Path -LiteralPath $startupScript)) {
        throw 'Watcher Startup-VBS was not installed by the packaged EXE'
    }
    $runValue = Get-ItemPropertyValue -Path $runKeyPath -Name $runValueName -ErrorAction Stop
    if ([string]$runValue -notmatch '--intake-agent') {
        throw 'HKCU Run watcher entry does not contain --intake-agent'
    }

    $agentTimestampBeforeClose = 0.0
    try {
        $hbBeforeClose = Get-Content -LiteralPath $agentHeartbeat -Raw | ConvertFrom-Json
        $agentTimestampBeforeClose = [double]$hbBeforeClose.timestamp
    } catch {}

    if (-not $initialGui.HasExited) {
        try { $null = $initialGui.CloseMainWindow() } catch {}
        $null = $initialGui.WaitForExit(2500)
    }

    # PyInstaller one-file can leave a GUI child after the launcher process exits.
    # Stop every non-agent process for this exact EXE, but never kill the watcher.
    foreach ($record in @(Get-AppProcessRecords | Where-Object { $_.CommandLine -notmatch '--intake-agent' })) {
        try { Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Wait-Until -Description 'all GUI processes closed while intake-agent stays alive' -TimeoutSeconds 15 -Condition {
        $records = @(Get-AppProcessRecords)
        $agents = @($records | Where-Object { $_.CommandLine -match '--intake-agent' })
        $nonAgents = @($records | Where-Object { $_.CommandLine -notmatch '--intake-agent' })
        if ($agents.Count -lt 1 -or $nonAgents.Count -ne 0 -or -not (Test-Path -LiteralPath $agentHeartbeat)) { return $false }
        try {
            $hb = Get-Content -LiteralPath $agentHeartbeat -Raw | ConvertFrom-Json
            return ([double]$hb.timestamp -gt $agentTimestampBeforeClose)
        } catch { return $false }
    }

    $launchLogCountBeforeDrop = 0
    if (Test-Path -LiteralPath $agentLog) {
        $launchLogCountBeforeDrop = @((Get-Content -LiteralPath $agentLog) | Where-Object { $_ -match 'new Word arrival; GUI launch requested' }).Count
    }

    $builder = Join-Path $testRoot 'make_intake_fixture.py'
    @'
import sys
from docx import Document
p = sys.argv[1]
d = Document()
d.add_paragraph("12.05.2026 Первичный осмотр")
d.add_paragraph("История болезни № E2E-001")
d.add_paragraph("Ф.И.О.: Автотестов Агент Тестович")
d.add_paragraph("Дата рождения: 01.01.1980")
d.add_paragraph("Жалобы при поступлении: тестовая запись")
d.add_paragraph("Анамнез жизни: без особенностей")
d.add_paragraph("Психический статус: контактен, ориентирован")
d.add_paragraph("Диагноз: F20.0")
d.add_paragraph("План лечения: тестовая терапия")
d.save(p)
'@ | Set-Content -LiteralPath $builder -Encoding UTF8
    & python $builder $fixture
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $fixture)) {
        throw 'Failed to create primary DOCX fixture for watcher E2E'
    }
    $dropToVisible = [Diagnostics.Stopwatch]::StartNew()

    Wait-Until -Description 'watcher-triggered launch request with a visible GUI window' -TimeoutSeconds 40 -Condition {
        $records = @(Get-AppProcessRecords)
        $nonAgents = @($records | Where-Object { $_.CommandLine -notmatch '--intake-agent' })
        if ($nonAgents.Count -lt 1 -or -not (Test-Path -LiteralPath $agentLog)) { return $false }
        $launchLogCount = @((Get-Content -LiteralPath $agentLog) | Where-Object { $_ -match 'new Word arrival; GUI launch requested' }).Count
        if ($launchLogCount -le $launchLogCountBeforeDrop) { return $false }
        return (Test-AppHasVisibleWindow)
    }
    $dropToVisible.Stop()
    $dropToVisibleMs = [math]::Round($dropToVisible.Elapsed.TotalMilliseconds, 0)
    Write-Host "INTAKE E2E drop-to-visible latency: $dropToVisibleMs ms"
    # This path intentionally exercises the portable PyInstaller one-file binary,
    # which includes extraction overhead and is not the installed production
    # runtime. Keep a generous regression ceiling here; the installed onedir
    # path is separately gated at 5 seconds in windows_installer_smoke.ps1.
    if ($dropToVisible.Elapsed.TotalSeconds -gt 20.0) {
        throw "Portable one-file watcher-triggered GUI exceeded CI latency budget: $dropToVisibleMs ms > 20000 ms"
    }

    Wait-Until -Description 'primary DOCX moved into patient subfolder' -TimeoutSeconds 20 -Condition {
        if (Test-Path -LiteralPath $fixture) { return $false }
        $matches = @(Get-ChildItem -LiteralPath $intakeRoot -Directory -ErrorAction SilentlyContinue | Where-Object {
            Test-Path -LiteralPath (Join-Path $_.FullName $fixtureName)
        })
        return $matches.Count -ge 1
    }
    $moved = Get-ChildItem -LiteralPath $intakeRoot -Directory -ErrorAction Stop | ForEach-Object {
        $candidate = Join-Path $_.FullName $fixtureName
        if (Test-Path -LiteralPath $candidate) { Get-Item -LiteralPath $candidate }
    } | Select-Object -First 1
    if ($null -eq $moved) { throw 'Moved primary DOCX cannot be located after watcher launch' }
    $createdPatientFolder = $moved.Directory.FullName

    if (-not (Test-Path -LiteralPath $agentLog)) {
        throw 'Watcher technical log was not created'
    }
    $logText = Get-Content -LiteralPath $agentLog -Raw
    if ($logText -notmatch 'new Word arrival; GUI launch requested') {
        throw 'Watcher did not record a GUI launch request for the dropped primary DOCX'
    }

    Write-Host 'WINDOWS DESKTOP INTAKE AUTOLAUNCH E2E OK'
}
finally {
    Stop-TestAppProcesses
    Start-Sleep -Milliseconds 500
    if ($oldRunExists) {
        New-Item -Path $runKeyPath -Force | Out-Null
        New-ItemProperty -Path $runKeyPath -Name $runValueName -Value $oldRunValue -PropertyType String -Force | Out-Null
    } else {
        Remove-ItemProperty -Path $runKeyPath -Name $runValueName -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $fixture -Force -ErrorAction SilentlyContinue
    if ($createdPatientFolder) {
        Remove-Item -LiteralPath $createdPatientFolder -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not $intakeExisted) {
        try {
            if ((Get-ChildItem -LiteralPath $intakeRoot -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
                Remove-Item -LiteralPath $intakeRoot -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
