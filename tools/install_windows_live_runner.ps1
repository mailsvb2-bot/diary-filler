param(
    [Parameter(Mandatory = $true)]
    [string]$RepositoryUrl,

    [Parameter(Mandatory = $true)]
    [string]$RegistrationToken,

    [Parameter(Mandatory = $true)]
    [string]$RunnerVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[A-Fa-f0-9]{64}$")]
    [string]$ExpectedSha256,

    [ValidateSet("windows10", "windows11")]
    [string]$TargetOs = "windows11",

    [string]$RunnerName = "",
    [string]$InstallRoot = "$env:LOCALAPPDATA\GitHubActionsRunner\diary-filler",
    [string]$Labels = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Fail([string]$Message) {
    throw "LIVE RUNNER INSTALL FAILED: $Message"
}

if ($env:OS -ne "Windows_NT") { Fail "Windows is required" }
if (-not [Environment]::Is64BitOperatingSystem) { Fail "x64 Windows is required" }
if ($PSVersionTable.PSVersion.Major -lt 5) { Fail "Windows PowerShell 5.1+ is required" }

try {
    $parsedRunnerVersion = [version]$RunnerVersion
} catch {
    Fail "RunnerVersion must be a valid semantic version such as 2.337.0"
}
if ($parsedRunnerVersion -lt [version]"2.327.1") {
    Fail "GitHub Actions runner v2.327.1 or newer is required by the pinned Node 24 actions; requested $RunnerVersion"
}

$os = Get-CimInstance Win32_OperatingSystem
if ([int]$os.ProductType -ne 1) {
    Fail "Windows workstation is required"
}
$build = [int]$os.BuildNumber
if ($TargetOs -eq "windows10") {
    if ($build -lt 14393 -or $build -ge 22000) {
        Fail "Windows 10 client build 14393..21999 is required for the windows10 runner; detected build $build"
    }
    $targetLabel = "windows10-interactive"
} elseif ($TargetOs -eq "windows11") {
    if ($build -lt 22000) {
        Fail "Windows 11 build >= 22000 is required for the windows11 runner; detected build $build"
    }
    $targetLabel = "windows11-interactive"
} else {
    Fail "unsupported TargetOs '$TargetOs'"
}

if ([string]::IsNullOrWhiteSpace($RunnerName)) {
    $RunnerName = "$env:COMPUTERNAME-diary-filler-$TargetOs-live"
}
if ([string]::IsNullOrWhiteSpace($Labels)) {
    $Labels = "diary-filler-live-e2e,$targetLabel"
}
$labelSet = @($Labels.Split(",") | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
if ($labelSet -notcontains "diary-filler-live-e2e" -or $labelSet -notcontains $targetLabel) {
    Fail "Labels must include diary-filler-live-e2e and $targetLabel"
}

$sessionId = (Get-Process -Id $PID).SessionId
if ($sessionId -eq 0) {
    Fail "run this installer from the interactive Windows user session, not Session 0"
}

$repo = $RepositoryUrl.TrimEnd("/")
if ($repo -notmatch "^https://github\.com/[^/]+/[^/]+$") {
    Fail "RepositoryUrl must look like https://github.com/owner/repo"
}
if ([string]::IsNullOrWhiteSpace($RegistrationToken)) { Fail "registration token is empty" }

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$zip = Join-Path $env:TEMP "actions-runner-win-x64-$RunnerVersion.zip"
$asset = "https://github.com/actions/runner/releases/download/v$RunnerVersion/actions-runner-win-x64-$RunnerVersion.zip"

Write-Host "Downloading official GitHub Actions runner v$RunnerVersion..."
# Windows 10 1607 / Windows PowerShell 5.1 may otherwise negotiate the
# framework's legacy HTTPS default. GitHub requires TLS 1.2+.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
    Fail "TLS 1.2 could not be enabled in Windows PowerShell: $($_.Exception.Message)"
}
try {
    Invoke-WebRequest -UseBasicParsing -Uri $asset -OutFile $zip
} catch {
    Fail "GitHub runner download failed over TLS 1.2. Ensure Windows root certificates and TLS 1.2 support are current. Underlying error: $($_.Exception.Message)"
}
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash
if ($actual.ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant()) {
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
    Fail "runner archive SHA-256 mismatch"
}

if (Test-Path (Join-Path $InstallRoot ".runner")) {
    Fail "runner is already configured at $InstallRoot; remove it with config.cmd remove before reinstalling"
}

Expand-Archive -LiteralPath $zip -DestinationPath $InstallRoot -Force
Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue

Push-Location $InstallRoot
try {
    # Deliberately do NOT use --runasservice. Windows services execute in
    # Session 0 and cannot provide trustworthy interactive GUI E2E evidence.
    & .\config.cmd --unattended --url $repo --token $RegistrationToken --name $RunnerName --labels $Labels --work "_work" --replace
    if ($LASTEXITCODE -ne 0) { Fail "config.cmd failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}

$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
New-Item -ItemType Directory -Force -Path $startupDir | Out-Null
$launcher = Join-Path $InstallRoot "run-interactive.cmd"
@"
@echo off
cd /d "$InstallRoot"
call run.cmd
"@ | Set-Content -LiteralPath $launcher -Encoding ASCII

$startupVbs = Join-Path $startupDir "DiaryFiller Live E2E Runner.vbs"
$escapedLauncher = $launcher.Replace('"', '""')
@"
On Error Resume Next
Set shell = CreateObject("WScript.Shell")
shell.Run """" & "$escapedLauncher" & """", 0, False
"@ | Set-Content -LiteralPath $startupVbs -Encoding Unicode

$readme = Join-Path $InstallRoot "INTERACTIVE-RUNNER.txt"
@"
This runner is intentionally NOT installed as a Windows service.
It must run in a signed-in, unlocked $TargetOs user session.

Repository: $repo
Target OS: $TargetOs
Detected OS: $($os.Caption) build $build
Runner name: $RunnerName
Runner version: $RunnerVersion
Labels: self-hosted, Windows, X64, $Labels

Operational requirements:
- keep the dedicated test user signed in;
- keep the desktop unlocked;
- do not disconnect RDP in a way that locks the console session;
- Microsoft Word must be installed for the live legacy .doc contour;
- at least one Windows printer must be installed;
- use a dedicated disposable test profile with no patient data.
"@ | Set-Content -LiteralPath $readme -Encoding UTF8

Write-Host "LIVE RUNNER CONFIGURED: $TargetOs / build $build"
Write-Host "Startup launcher: $startupVbs"
Write-Host "Starting runner in the current interactive session..."
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", ('"' + $launcher + '"') -WindowStyle Hidden
Write-Host "Runner must remain signed in and unlocked. It is intentionally not a service."
