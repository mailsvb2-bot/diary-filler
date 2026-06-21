@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

set VENV_DIR=.venv_runtime
set PY=%VENV_DIR%\Scripts\python.exe

echo ============================================================
echo  Диагностический запуск медицинского автозаполнителя
echo  Если окно не открылось, ошибка будет в startup_error.log
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] python.exe не найден. Для обычного пользователя используйте готовый EXE.
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

echo [2/3] Устанавливаю зависимости...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости.
  pause
  exit /b 1
)

echo [3/3] Запускаю main.py в диагностическом режиме...
"%PY%" main.py

if errorlevel 1 (
  echo.
  echo [ОШИБКА] Программа завершилась с ошибкой.
  echo Проверьте файл startup_error.log в этой папке.
)

pause
