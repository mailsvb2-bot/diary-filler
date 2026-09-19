@echo off
chcp 65001 > nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  Сборка медицинского автозаполнителя в один .EXE
echo  Пользователю Python и зависимости ставить не нужно.
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ОШИБКА] Python не найден. Для сборки нужен Python на компьютере разработчика.
  if "%CI%"=="" pause
  exit /b 1
)

if not exist .venv_build (
  echo [1/6] Создаю виртуальное окружение сборки...
  python -m venv .venv_build
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось создать виртуальное окружение.
    if "%CI%"=="" pause
    exit /b 1
  )
)

call .venv_build\Scripts\activate.bat
if errorlevel 1 (
  echo [ОШИБКА] Не удалось активировать виртуальное окружение.
  if "%CI%"=="" pause
  exit /b 1
)

echo [2/6] Обновляю pip...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ОШИБКА] Не удалось обновить pip.
  if "%CI%"=="" pause
  exit /b 1
)

echo [3/6] Устанавливаю сборочные зависимости...
python -m pip install -r requirements_build.txt
if errorlevel 1 (
  echo [ОШИБКА] Не удалось установить зависимости сборки.
  if "%CI%"=="" pause
  exit /b 1
)

echo [4/6] Проверяю production-safety gate...
python tools\production_safety_gate.py
if errorlevel 1 (
  echo [ОШИБКА] Production-safety gate не прошёл. EXE не собираю.
  if "%CI%"=="" pause
  exit /b 1
)

echo [5/6] Проверяю release-gate...
python release_check.py
if errorlevel 1 (
  echo [ОШИБКА] Release-gate не прошёл. EXE не собираю.
  if "%CI%"=="" pause
  exit /b 1
)

echo [6/6] Собираю portable EXE и быстрый installed runtime через PyInstaller...
set ADD_TEMPLATES=
if exist templates (
  set ADD_TEMPLATES=--add-data "templates;templates"
) else (
  echo [INFO] Папка templates не найдена, используются встроенные шаблоны из embedded_templates.py
)

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name MedicalDiaryAutofill ^
  --version-file version_info.txt ^
  --noupx ^
  %ADD_TEMPLATES% ^
  --collect-all docx ^
  --collect-all lxml ^
  --collect-all tkinterdnd2 ^
  --hidden-import win32api ^
  --hidden-import win32print ^
  --hidden-import pythoncom ^
  --hidden-import win32com ^
  --hidden-import win32com.client ^
  main.py

if not exist dist\MedicalDiaryAutofill.exe (
  echo.
  echo [ОШИБКА] Portable EXE не найден. Смотри вывод выше.
  if "%CI%"=="" pause
  exit /b 1
)

echo.
echo [6/6] Собираю быстрый runtime для установленной версии...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name MedicalDiaryAutofill ^
  --distpath dist\installed ^
  --workpath build\installed ^
  --specpath build\installed-spec ^
  --version-file "%CD%\version_info.txt" ^
  --noupx ^
  %ADD_TEMPLATES% ^
  --collect-all docx ^
  --collect-all lxml ^
  --collect-all tkinterdnd2 ^
  --hidden-import win32api ^
  --hidden-import win32print ^
  --hidden-import pythoncom ^
  --hidden-import win32com ^
  --hidden-import win32com.client ^
  main.py
if errorlevel 1 exit /b 1

if not exist dist\installed\MedicalDiaryAutofill\MedicalDiaryAutofill.exe (
  echo [ОШИБКА] Быстрый installed runtime не создан.
  if "%CI%"=="" pause
  exit /b 1
)

echo.
echo ГОТОВО:
echo   portable: dist\MedicalDiaryAutofill.exe
echo   installed runtime: dist\installed\MedicalDiaryAutofill\MedicalDiaryAutofill.exe
echo Пользователю Python и зависимости не нужны.
if "%CI%"=="" pause
exit /b 0
