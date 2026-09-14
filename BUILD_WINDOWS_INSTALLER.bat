@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "dist\MedicalDiaryAutofill.exe" (
  echo [ОШИБКА] Сначала нужен dist\MedicalDiaryAutofill.exe
  exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  for %%I in (ISCC.exe) do if not "%%~$PATH:I"=="" set "ISCC=%%~$PATH:I"
)

if not defined ISCC (
  echo [ОШИБКА] Inno Setup 6 не найден. Установите Inno Setup только на сборочной машине.
  exit /b 1
)

"%ISCC%" /DMyAppVersion=1.4.4 "installer\MedicalDiaryAutofill.iss"
if errorlevel 1 exit /b 1

if not exist "dist\MedicalDiaryAutofill-Setup-1.4.4.exe" (
  echo [ОШИБКА] Installer не создан.
  exit /b 1
)

echo ГОТОВО: dist\MedicalDiaryAutofill-Setup-1.4.4.exe
exit /b 0
