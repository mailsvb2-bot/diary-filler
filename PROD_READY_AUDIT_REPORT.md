# Current prod-ready audit addendum — v1.3.10-audit-hardening

Автоматические gates после текущего аудита: `compileall`, `smoke_test.py`, `smoke_test_combined.py` вручную, `prod_audit.py`, `dnd_contract_check.py`, `performance_check.py`, `release_check.py` — успешно. `release_check.py` теперь не дублирует identical combined-suite, но проверяет оба smoke-entrypoint контракта.

Статус: исходники стали сильнее как Windows release-candidate, но финальный коммерческий production всё ещё требует ручной Windows-проверки EXE, TkDND, печати, SmartScreen/code-signing и корпуса реальных обезличенных DOCX.

---

# Prod-ready audit report — v1.2.3-audit-hardening

## Итог

Проект доведён до состояния **production release-candidate для GitHub и Windows EXE-сборки**. Код прошёл синтаксическую компиляцию, smoke-тесты, release-gate и дополнительный production-audit.

Важно: в этой Linux-среде нельзя честно проверить реальный Windows GUI, PyInstaller EXE, drag-and-drop через TkDND и физическую печать. Эти проверки вынесены в `LAUNCH_CHECKLIST.md` и должны быть выполнены на Windows перед платным трафиком.

## Что сделано

1. Схлопнута архитектурная пыль после последней чрезмерной нарезки: удалены 49 одноцелевых micro-mixin-файлов.
2. Сохранены публичные входы: `main.py`, `medical_documents.py`, `diary_filler.py`, `printer_support.py`, `icd10_f.py`.
3. Сохранены рабочие контракты запуска: `python main.py`, `python smoke_test.py`, `python smoke_test_combined.py`, `python release_check.py`, `python make_release_zip.py`.
4. Добавлен `prod_audit.py` как отдельный production-gate.
5. `release_check.py` усилен запуском `prod_audit.py`.
6. Синхронизирована версия: `v1.2.3-audit-hardening` в `app_config.py`, `pyproject.toml`, `version_info.txt`, `README.md`, `RELEASE_NOTES.md`.
7. Удалены промежуточные split-отчёты из release-root, чтобы GitHub/archive не засорялись процессными файлами.
8. Добавлен `LAUNCH_CHECKLIST.md` для финального Windows/prod/paid-traffic gate.

## Проверенные автоматикой зоны

- Python syntax/bytecode compile.
- Генерация медицинских документов с ЭПИ и без ЭПИ.
- Генерация дневников.
- Регрессии парсера: `Не работает`, `врач`, `врач-психиатр`, дата `12.01.26`, районы через `\`.
- UI static contracts: selected-state, большая зона выбора файла, больничный popup.
- Release hygiene: нет `__pycache__`, `.pyc`, `.spec`, `.DS_Store`, `Thumbs.db`, `build`, `dist`, временных run-папок.
- Import graph: нет циклических локальных импортов.
- Архитектурная пыль: запрещён возврат одноцелевых micro-mixin-файлов.

## Остаточные риски

- Windows EXE и печать не проверены в этой среде.
- EXE не подписан code-signing сертификатом; для платного трафика это может ухудшить доверие и вызвать SmartScreen.
- Нет автоматизированных GUI-тестов с реальным Tkinter-окном.
- Реальный рынок/пользовательская воронка не подтверждены кодом; перед масштабированием рекламы нужен пилот на ограниченном бюджете.

## Рейтинг

- Архитектура после схлопывания пыли: **9.1 / 10**.
- Автоматический release-gate: **9.2 / 10**.
- Готовность исходников к GitHub: **9.3 / 10**.
- Готовность к платному трафику без Windows QA/code-signing: **8.2 / 10**.
- Готовность к платному трафику после выполнения `LAUNCH_CHECKLIST.md`: ориентировочно **9.0 / 10**.



## v1.2.3 audit hardening

- Исправлен no-op `smoke_test.py`: теперь совместимый entrypoint реально запускает combined smoke-suite.
- Закрыта утечка `test_run*`/`*_run` директорий в source zip при прямом запуске `make_release_zip.py`.
- Усилен `prod_audit.py`: проверяет importability публичных runtime-модулей, executable smoke-entrypoints и archive hygiene contract.
- Исправлен парсинг работы: `Работает в организации: не работает` / `безработный` больше не попадает в место работы.
- Исправлена защита Windows-reserved имён с расширениями: `CON.txt`, `LPT1.docx`.
- Убрана двойная декорация `@dataclass` у `DiaryBatchResult`; очищены тяжёлые лишние импорты в `diary_constants.py`.

## v1.2.2 startup hotfix

- Убраны галочки с выбранных canvas-кнопок.
- Выбранное состояние переведено на мягкую cyan-обводку и левую акцентную метку.
- Active/hover-цвета сделаны менее грубыми.
