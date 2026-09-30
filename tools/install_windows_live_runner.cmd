@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "TARGET_OS=%~1"
if "%TARGET_OS%"=="" set "TARGET_OS=windows10"
if /I not "%TARGET_OS%"=="windows10" if /I not "%TARGET_OS%"=="windows11" (
  echo ERROR: first argument must be windows10 or windows11
  exit /b 2
)

where powershell.exe >nul 2>&1
if errorlevel 1 (
  echo ERROR: Windows PowerShell is required.
  exit /b 3
)

set "SCRIPT_URL=https://raw.githubusercontent.com/mailsvb2-bot/diary-filler/main/tools/install_windows_live_runner.ps1"
set "SCRIPT_PATH=%TEMP%\install_windows_live_runner.ps1"

echo Downloading diary-filler live runner bootstrap...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri '%SCRIPT_URL%' -OutFile '%SCRIPT_PATH%'"
if errorlevel 1 (
  echo ERROR: failed to download install_windows_live_runner.ps1
  exit /b 4
)

set /p "RUNNER_TOKEN=Paste GitHub runner registration token and press Enter: "
if "%RUNNER_TOKEN%"=="" (
  echo ERROR: token is empty
  exit /b 6
)

echo.
echo Registering %TARGET_OS% live runner...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" ^
  -RepositoryUrl "https://github.com/mailsvb2-bot/diary-filler" ^
  -RegistrationToken "%RUNNER_TOKEN%" ^
  -RunnerVersion "2.337.0" ^
  -ExpectedSha256 "1150692afa94e71f872017e254ea55b6eece1eece3fe7e3a6d4c93d0a1b85cfc" ^
  -TargetOs "%TARGET_OS%"

set "RC=%ERRORLEVEL%"
set "RUNNER_TOKEN="
if not "%RC%"=="0" (
  echo.
  echo Live runner setup FAILED with exit code %RC%.
  exit /b %RC%
)

echo.
echo Live runner setup completed successfully.
echo Keep this Windows user signed in and the desktop unlocked during live E2E.
exit /b 0
