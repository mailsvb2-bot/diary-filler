param(
    [Parameter(Mandatory=$true)][string]$AppPath
)

$ErrorActionPreference = 'Stop'
$app = (Resolve-Path $AppPath).Path
$testRoot = Join-Path $env:RUNNER_TEMP ("MedicalDiaryAutofill-GUI-Smoke-" + [guid]::NewGuid().ToString('N'))
$appData = Join-Path $testRoot 'AppData\Roaming'
$localAppData = Join-Path $testRoot 'AppData\Local'
$settingsDir = Join-Path $appData 'MedicalDiaryAutofill'
$settingsPath = Join-Path $settingsDir 'settings.json'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class VisibleWindowProbe {
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

try {
    New-Item -ItemType Directory -Path $settingsDir -Force | Out-Null
    $settings = @{
        desktop_intake_enabled = $true
        staff_profile = @{
            configured = $true
            doctor = 'Автоврач А.А.'
            department_head = 'Автозаведующая З.З.'
            deputy_chief = 'Автозам Д.Д.'
        }
    } | ConvertTo-Json -Depth 4
    Set-Content -LiteralPath $settingsPath -Value $settings -Encoding UTF8

    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $app
    $psi.WorkingDirectory = Split-Path -Parent $app
    $psi.UseShellExecute = $false
    $psi.Environment['APPDATA'] = $appData
    $psi.Environment['LOCALAPPDATA'] = $localAppData
    $psi.Environment['MEDICAL_AUTOFILL_DISABLE_DESKTOP_INTAKE'] = '1'
    $null = $psi.Environment.Remove('CI')
    $null = $psi.Environment.Remove('MEDICAL_AUTOFILL_STARTUP_PROBE')
    $process = [Diagnostics.Process]::Start($psi)

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $visible = $false
    do {
        if ($process.HasExited) { break }
        foreach ($record in @(Get-AppProcessRecords)) {
            try {
                if ([VisibleWindowProbe]::HasVisibleTopLevelWindow([int]$record.ProcessId)) {
                    $visible = $true
                    break
                }
            } catch {}
        }
        if ($visible) { break }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)

    if (-not $visible) {
        $exit = if ($process.HasExited) { [string]$process.ExitCode } else { 'still-running' }
        throw "Normal packaged launch produced no visible GUI window (exit=$exit)"
    }
    Write-Host 'WINDOWS VISIBLE GUI SMOKE OK'
}
finally {
    foreach ($record in @(Get-AppProcessRecords)) {
        try { Stop-Process -Id $record.ProcessId -Force -ErrorAction SilentlyContinue } catch {}
    }
    Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue
}
