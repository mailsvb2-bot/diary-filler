@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

set VENV_DIR=.venv_runtime
set PY=%VENV_DIR%\Scripts\python.exe
set PYW=%VENV_DIR%\Scripts\pythonw.exe

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] python.exe не найден. Для обычного пользователя используйте готовый EXE из dist\MedicalDiaryAutofill.exe или GitHub Actions artifact.
  pause
  exit /b 1
)

if not exist "%PY%" (
  echo [1/3] Создаю локальное окружение запуска...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать локальное окружение.
    pause
    exit /b 1
  )
)

echo [2/3] Проверяю зависимости...
"%PY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости. Запустите start_windows_debug.bat для подробностей.
  pause
  exit /b 1
)

echo [3/3] Запускаю программу...
if exist "%PYW%" (
  start "" "%PYW%" "%~dp0main.py"
) else (
  start "" "%PY%" "%~dp0main.py"
)
exit /b 0
