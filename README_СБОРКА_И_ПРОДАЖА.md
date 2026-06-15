# Заполнитель дневников — коммерческая упаковка v9

## Что внутри

- `src/zapolnitel_dnevnikov_app.py` — исходный код приложения.
- `assets/app_icon.ico` — иконка приложения.
- `build/diary_filler_onefile.spec` — сборка одного EXE.
- `build/diary_filler_onedir.spec` — сборка portable-папки для установщика.
- `installer/ZapolnitelDnevnikov.iss` — скрипт Inno Setup.
- `СОБРАТЬ_ONEFILE_EXE.bat` — создаёт один файл `dist/ZapolnitelDnevnikov.exe`.
- `СОБРАТЬ_УСТАНОВЩИК.bat` — создаёт установщик `release/ZapolnitelDnevnikov_Setup.exe`, если установлен Inno Setup 6.

## Для конечного пользователя

Пользователь не устанавливает Python, pip, PySide6 или python-docx.
Он получает либо:

- `ZapolnitelDnevnikov.exe` — portable-версия;
- `ZapolnitelDnevnikov_Setup.exe` — установщик.

## Как собрать на Windows

1. Распаковать архив.
2. Запустить `СОБРАТЬ_ONEFILE_EXE.bat` для portable `.exe`.
3. Или установить Inno Setup 6 и запустить `СОБРАТЬ_УСТАНОВЩИК.bat` для нормального установщика.

## Почему готовый Windows EXE не приложен здесь

EXE нужно собирать на Windows, потому что PyInstaller/PySide6 собирают бинарник под текущую операционную систему.
Сборка на Linux создаст Linux-бинарник, а не Windows-программу.

## Коммерческие замечания

Для продажи желательно:

- подписать EXE code-signing сертификатом, чтобы Windows SmartScreen меньше пугал пользователей;
- добавить сайт/страницу загрузки;
- добавить короткую PDF-инструкцию;
- добавить EULA/дисклеймер, что программа помогает заполнять шаблоны, а итог проверяет специалист.
