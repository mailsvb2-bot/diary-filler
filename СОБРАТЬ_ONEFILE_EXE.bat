@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Сборка Заполнителя дневников в один .EXE
echo  Пользователю Python и зависимости ставить не нужно.
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
  echo [1/4] Создаю виртуальное окружение сборки...
  python -m venv .venv_build
)

call .venv_build\Scripts\activate.bat

echo [2/4] Обновляю pip...
python -m pip install --upgrade pip

echo [3/4] Устанавливаю сборочные зависимости...
python -m pip install -r requirements_build.txt

echo [4/4] Собираю один EXE через PyInstaller...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ZapolnitelDnevnikov --collect-all docx --collect-all lxml src\zapolnitel_dnevnikov_app.py

if exist dist\ZapolnitelDnevnikov.exe (
  echo.
  echo ГОТОВО: dist\ZapolnitelDnevnikov.exe
  echo Этот файл можно отдавать пользователям. Он запускается без Python/pip.
) else (
  echo.
  echo [ОШИБКА] EXE не найден. Смотри вывод выше.
)

pause
