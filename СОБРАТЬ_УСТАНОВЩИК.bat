@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Сборка установщика Заполнителя дневников
echo  Результат: release\ZapolnitelDnevnikov_Setup.exe
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Для сборки на компьютере разработчика нужен Python.
  echo Конечным пользователям Python будет не нужен.
  pause
  exit /b 1
)

if not exist .venv_build (
  echo [1/5] Создаю виртуальное окружение сборки...
  python -m venv .venv_build
)

call .venv_build\Scripts\activate.bat

echo [2/5] Обновляю pip...
python -m pip install --upgrade pip

echo [3/5] Устанавливаю сборочные зависимости...
python -m pip install -r requirements_build.txt

echo [4/5] Собираю portable-папку приложения...
python -m PyInstaller --noconfirm --clean build\diary_filler_onedir.spec

if not exist dist\ZapolnitelDnevnikov\ZapolnitelDnevnikov.exe (
  echo [ОШИБКА] Portable-сборка не создана. Смотри вывод выше.
  pause
  exit /b 1
)

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% goto build_inno
set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% goto build_inno

echo.
echo [ВНИМАНИЕ] Inno Setup 6 не найден.
echo Portable-версия уже готова здесь:
echo dist\ZapolnitelDnevnikov\ZapolnitelDnevnikov.exe
echo.
echo Чтобы получить красивый Setup.exe, установи Inno Setup 6 и снова запусти этот BAT.
pause
exit /b 0

:build_inno
echo [5/5] Собираю установщик Inno Setup...
if not exist release mkdir release
%ISCC% installer\ZapolnitelDnevnikov.iss

if exist release\ZapolnitelDnevnikov_Setup.exe (
  echo.
  echo ГОТОВО: release\ZapolnitelDnevnikov_Setup.exe
  echo Это установщик для пользователей: без Python, без pip, без зависимостей.
) else (
  echo [ОШИБКА] Установщик не найден. Смотри вывод выше.
)

pause
