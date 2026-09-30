param(
    [switch]$RequireWord = $true,
    [switch]$RequirePrinter = $true,
    [string]$JsonOut = "live-e2e-artifacts\preflight.json"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    throw "WINDOWS11 LIVE E2E PREFLIGHT FAILED: $Message"
}

if (-not $IsWindows) { Fail "runner is not Windows" }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "Windows is not x64" }

$os = Get-CimInstance Win32_OperatingSystem
if ([int]$os.ProductType -ne 1) {
    Fail "Windows workstation is required; server/domain-controller editions are not valid live desktop evidence"
}
$build = [int]$os.BuildNumber
if ($build -lt 22000) {
    Fail "Windows 11 build >= 22000 is required; detected build $build"
}

$sessionId = (Get-Process -Id $PID).SessionId
if ($sessionId -eq 0) {
    Fail "runner is executing in Session 0; GUI E2E must run in an interactive signed-in user session"
}

$computer = Get-CimInstance Win32_ComputerSystem
if ([string]::IsNullOrWhiteSpace([string]$computer.UserName)) {
    Fail "no interactive Windows user is signed in"
}

$explorer = @(Get-Process explorer -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq $sessionId })
if ($explorer.Count -eq 0) {
    Fail "explorer.exe is not running in the runner session; desktop is not a normal interactive user desktop"
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class LiveDesktopProbe {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern IntPtr OpenInputDesktop(uint flags, bool inherit, uint desiredAccess);
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool CloseDesktop(IntPtr hDesktop);
}
"@
$desktop = [LiveDesktopProbe]::OpenInputDesktop(0, $false, 0x0100)
if ($desktop -eq [IntPtr]::Zero) {
    Fail "input desktop cannot be opened; session is locked, disconnected, or non-interactive"
}
[void][LiveDesktopProbe]::CloseDesktop($desktop)

Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
if ($screen.Width -lt 1280 -or $screen.Height -lt 720) {
    Fail "primary desktop resolution must be at least 1280x720; detected $($screen.Width)x$($screen.Height)"
}

$wordPath = $null
$wordCandidates = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
)
foreach ($key in $wordCandidates) {
    try {
        $candidate = (Get-ItemProperty -Path $key -ErrorAction Stop)."(default)"
        if ($candidate -and (Test-Path $candidate)) {
            $wordPath = [string]$candidate
            break
        }
    } catch {}
}
if ($RequireWord -and -not $wordPath) {
    Fail "Microsoft Word is required for the live .doc/user-print contour but WINWORD.EXE was not found"
}

$printers = @()
try {
    $printers = @(Get-Printer -ErrorAction Stop)
} catch {
    if ($RequirePrinter) { Fail "Windows printer subsystem is unavailable: $($_.Exception.Message)" }
}
if ($RequirePrinter -and $printers.Count -eq 0) {
    Fail "at least one Windows printer is required (Microsoft Print to PDF is acceptable for the automated live contour)"
}

$inno = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

$artifactDir = Split-Path -Parent $JsonOut
if ($artifactDir) { New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null }

$report = [ordered]@{
    schema_version = 1
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    os_caption = [string]$os.Caption
    os_version = [string]$os.Version
    os_build = $build
    product_type = [int]$os.ProductType
    architecture = [string]$os.OSArchitecture
    process_is_64_bit = [Environment]::Is64BitProcess
    session_id = $sessionId
    interactive_user_present = $true
    explorer_in_session = $true
    input_desktop_openable = $true
    screen = @{
        width = $screen.Width
        height = $screen.Height
    }
    word_present = [bool]$wordPath
    printer_count = $printers.Count
    printer_names = @($printers | ForEach-Object { [string]$_.Name })
    inno_setup_present = [bool]$inno
}

$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $JsonOut -Encoding UTF8
Write-Host "WINDOWS11 LIVE E2E PREFLIGHT OK"
Write-Host "OS: $($os.Caption) build $build; session=$sessionId; screen=$($screen.Width)x$($screen.Height); printers=$($printers.Count); Word=$([bool]$wordPath)"
