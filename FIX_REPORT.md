## Дополнение v1.3.18-production-quality-gate — доведение production-gate до 100/100

Исправлено в этой итерации:

1. Добавлена `.gitattributes`, чтобы Git на Windows не превращал весь проект в LF→CRLF warning-churn.
2. GitHub Actions получил явные `permissions: contents: read` для least-privilege.
3. GitHub Actions получил `concurrency` с `cancel-in-progress`, чтобы старые сборки не конкурировали с новым релизом.
4. GitHub Actions получил `timeout-minutes`, чтобы зависшая сборка не висела бесконечно.
5. `medical_service.py`: output_dir теперь валидируется как папка; путь к существующему файлу отклоняется понятной ошибкой.
6. `medical_service.py`: убран двойной `mkdir` папки результата.
7. `medical_service.py`: публичная граница `selected_docs` теперь принимает и внутренние ключи, и видимые UI-названия документов.
8. `diary_batch.py`: output_dir теперь валидируется как папка; путь к файлу отклоняется до копирования шаблонов.
9. `diary_batch.py`: пустые пути к DOCX отклоняются понятным `ValueError`.
10. `diary_batch.py`: повторно выбранные одинаковые DOCX схлопываются с сохранением порядка.
11. `diary_batch.py`: дедупликация текстов дневников нормализует пробелы и `ё/е`.
12. `diary_batch.py`: `open_folder()` возвращает фактический статус открытия вместо молчаливого no-op.
13. `actions_creation_orchestrator.py`: лог успешного создания больше не утверждает, что папка открыта, если открытие не запускалось/невозможно.
14. `medical_paths.py`: embedded DOCX cache больше не доверяет старому temp-файлу; base64 валидируется строго.
15. `medical_paths.py`: embedded-шаблоны заменяются атомарно через `.tmp`, если temp-cache повреждён/неполный.
16. `medical_formatting.py`: `available_path()` получил bounded loop и понятную ошибку вместо потенциально бесконечного перебора имён.
17. `make_release_zip.py`: ZIP теперь самопроверяется на duplicate entries.
18. `make_release_zip.py`: ZIP теперь самопроверяется на мусорные папки/pycache/spec/tmp/test_run entries.
19. `release_check.py`: добавлены контракты на `.gitattributes` и усиленный GitHub Actions workflow.
20. `prod_audit.py` + smoke-suite: добавлены regression-tests/contract-tests на весь слой v1.3.18.
21. Версия синхронизирована до `v1.3.18-production-quality-gate`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
python make_release_zip.py
```

## Дополнение v1.3.17-deep-service-boundary-audit — въедливый audit service-boundary и пользовательских edge-cases

Исправлено в этой итерации:

1. `medical_service.py`: прямой вызов генерации больше не создаёт медицинские DOCX без ФИО пациента.
2. `medical_service.py`: прямой вызов генерации больше не создаёт DOCX без даты госпитализации/поступления.
3. `medical_service.py`: номер истории болезни стал обязательным на service-boundary для всех медицинских документов, а не только в UI.
4. `medical_service.py`: диагноз стал обязательным на service-boundary до рендера DOCX.
5. `medical_service.py`: лечение стало обязательным для документов, где есть лечебный блок (`primary`, `discharge`, `commission`, `vk_mse`, `sick_leave_vk`).
6. `medical_service.py`: `Акт для РВК` теперь требует отдельный номер медицинского заключения РВК, а не молча использует номер истории болезни вместо него.
7. `medical_service.py`: дата совместного осмотра раньше даты поступления теперь отклоняется до DOCX-render.
8. `medical_service.py`: дата ВК на МСЭ и дата протокола ВК раньше поступления теперь отклоняются.
9. `medical_service.py`: даты ВК больничного/протокола/комиссии раньше поступления теперь отклоняются.
10. `dialog_dates.py`: UI-popup обязательных дат комиссий/ВК теперь также не принимает даты раньше поступления.
11. `medical_formatting.py`: `format_military_commissariat_area()` очищает вводы с `военный комиссариат`/`военкомат` и не создаёт фразы вида `военкомата района`.
12. `medical_formatting.py`: `format_military_commissariat_referral()` очищает уже готовые фразы `по направлению из ... военкомата`, не дублируя начало фразы.
13. `dialog_expert.py`: common/discharge popup больше не спрашивает номер истории болезни повторно, если он уже есть в UI-state.
14. `smoke_combined_part06_diary_columns_settings.py`: добавлены regression-tests на все перечисленные service-boundary и formatting дефекты.
15. Версия синхронизирована до `v1.3.17-deep-service-boundary-audit`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
python make_release_zip.py
```

## Дополнение v1.3.16-silent-success-open-folder — тихий успешный сценарий

1. `actions_creation_orchestrator.py`: удалён popup-подтверждение «Выбраны только дневники» — выбранные дневники сразу создаются по контракту.
2. `actions_creation_orchestrator.py`: удалён финальный `messagebox.showinfo("Готово", ...)` со списком созданных файлов.
3. `actions_creation_orchestrator.py`: добавлено открытие папки результата после успешного создания без лишнего окна.
4. `actions_diary_flow.py`: убрано информационное окно «Нужны тексты дневников» перед ручным выбором текстов; если автоподбор не нашёл файл, сразу открывается выбор.
5. `diary_batch.py`: открытие папки сделано безопасным для CI/headless-среды, чтобы release-check не зависал на `xdg-open/open`.
6. `smoke_combined_part04_medical_generation.py`: усилен contract-test — успешный сценарий не должен показывать `info/warning/error/askyesno` и должен открыть папку результата.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
```

## Дополнение v1.3.15-user-flow-fix — пользовательские сценарии блока 03

1. `actions_creation_orchestrator.py` + `dialog_expert.py`: выбор только `Дневники наблюдения` теперь вызывает popup только с `Дата выписки`; поля `Лечение`, `Диагноз` и `Номер истории болезни` для diaries-only не спрашиваются.
2. `files_mixin.py` + `diary_template_selection.py`: при загрузке нового первичного документа старый точный дневниковый шаблон очищается, папка шаблонов сохраняется, новый шаблон `01–31` автоматически подбирается по дате поступления и сразу отображается в UI.
3. `medical_formatting.py` + `medical_renderer_primary.py`: военкомат, введённый в popup `Акт для РВК`, используется в первичном осмотре фразой `По направлению из … военкомата`, если первичный осмотр выбран одновременно.
4. Добавлены contract-tests: diaries-only popup без лечения, refresh auto-selected diary template UI, склонение/форматирование военкомата и проверка текста военкомата в итоговом DOCX.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
```

## Дополнение v1.3.14-ci-contract-fix — исправление Windows GitHub Actions

- Исправлен непереносимый smoke-test на Windows для `output_dir="   "`.
- Контракт не ослаблен: теперь проверяется фактическое пользовательское поведение — все созданные дневниковые DOCX попадают в папку исходного шаблона, если `output_dir` пустой или состоит только из пробелов.
- EXE/runtime-логика не менялась; исправлен только contract-test, который падал из-за Windows path-normalization.

## Дополнение v1.3.13-ui-label — чистая UI-правка перед GitHub

1. `window_mixin.py`: в блоке 01 главного экрана подпись поля изменена на `Дата поступления`.
2. Удалена лишняя часть подписи `конс. тел.` без изменения модели данных и генерации документов.
3. Синхронизированы release metadata для чистого GitHub-архива.

# Дополнение v1.3.12-deep-audit — сверх-глубокий аудит и hardening

Исправлено в этой итерации:

1. `dialog_document_details.py`: дата совместного осмотра больше не принимается как произвольный текст; неверная дата отклоняется до сохранения.
2. `dialog_document_details.py`: номер совместного осмотра валидируется явно, а не только косвенно через generic popup.
3. `dialog_document_details.py`: дата ВК на МСЭ валидируется строго и нормализуется из compact-ввода.
4. `dialog_document_details.py`: дата протокола ВК на МСЭ валидируется строго и нормализуется.
5. `dialog_document_details.py`: номер протокола ВК на МСЭ проверяется явно.
6. `dialog_document_details.py`: место работы для ВК на МСЭ больше не может пройти пустым при programmatic/stub вызове popup.
7. `dialog_document_details.py`: дата ВК больничного валидируется строго и нормализуется.
8. `dialog_document_details.py`: дата протокола ВК больничного валидируется строго и нормализуется.
9. `dialog_document_details.py`: дата проведения комиссии ВК больничного валидируется строго и нормализуется.
10. `dialog_document_details.py`: номер протокола ВК больничного проверяется явно.
11. `dialog_document_details.py`: место работы для ВК больничного больше не может пройти пустым при programmatic/stub вызове popup.
12. `dialog_dates.py` + `dialog_expert.py`: дата выписки раньше даты поступления больше не сохраняется в UI-state.
13. `medical_service.py`: `create_documents()` теперь требует дату выписки для `Выписной эпикриз` и `Акт для РВК` даже при прямом вызове без UI.
14. `medical_service.py`: `create_documents()` теперь требует дату и номер совместного осмотра для `Совместный осмотр`.
15. `medical_service.py`: `create_documents()` теперь требует дату, номер протокола и дату протокола для `ВК на МСЭ`.
16. `medical_service.py`: `create_documents()` теперь требует дату, номер протокола, дату протокола и дату комиссии для `ВК больничный`.
17. `medical_service.py`: `create_documents()` теперь требует номер заключения/истории и военкомат для `Акт РВК`.
18. `medical_service.py`: compact popup-даты (`18062026`, `19062026`, `20062026`) нормализуются на service-boundary до `ДД.ММ.ГГГГ` перед DOCX-render.
19. `smoke_combined_part02_ui_parser_regressions.py`: добавлены UI-contract тесты на нормализацию popup-дат, отклонение неверной даты и запрет даты выписки раньше поступления.
20. `smoke_combined_part06_diary_columns_settings.py`: добавлены service-boundary tests на обязательные реквизиты и проверка отсутствия raw compact-даты в итоговых DOCX.
21. Версия синхронизирована до `v1.3.12-deep-audit`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
python make_release_zip.py
```

---

# Дополнение v1.3.11-contract-tests — усиление пользовательских contract-tests

В этой итерации runtime-логика сохранена, усилен именно проверочный слой пользовательских сценариев:

1. `smoke_combined_part04_medical_generation.py`: добавлен application-level contract-test `выбор документа → popup → создание комплекта → проверка DOCX`.
2. Тест создаёт первичный DOCX без явного блока «План лечения», чтобы подтвердить обязательный popup лечения для медицинских документов.
3. Симулируется выбор плиток `Первичный осмотр` + `Выписной эпикриз` в блоке 03 через `create_selected_outputs()`, а не прямым вызовом renderer.
4. Проверяется, что открывается ровно один merged popup `Данные для выписного эпикриза`.
5. Проверяется состав popup-полей: `Номер истории болезни`, `Лечение`, `Дата выписки`.
6. Проверяется, что создаётся ровно выбранный комплект из двух DOCX: первичный осмотр и выписной эпикриз.
7. Проверяется содержимое созданного первичного DOCX: номер истории болезни и лечение из popup реально вставлены в документ.
8. Проверяется содержимое выписного DOCX: номер истории болезни, дата выписки, лечение и диагноз реально вставлены в документ.
9. Добавлен cancel-contract: отмена popup останавливает сценарий и не создаёт частичные DOCX.
10. Версия синхронизирована до `v1.3.11-contract-tests`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
python make_release_zip.py
```

---

# Дополнение v1.3.10-audit-hardening — текущий аудит

Исправлено в этой итерации:

1. `release_check.py`: устранён зависающий/слишком тяжёлый release-gate — combined smoke-suite больше не запускается дважды.
2. `release_check.py`: добавлен bounded subprocess runner с таймаутами и периодическим статусом для долгих команд.
3. `release_check.py`: performance/prod/dnd gates перенесены до тяжёлого smoke-corpus, чтобы startup-performance измерялся в чистом процессе.
4. `performance_check.py`: startup probe вынесен в `startup_import_probe_code()` и получил timeout.
5. `medical_service.py`: первичный документ теперь принимает только `.docx/.docm`, а не падает поздно внутри `python-docx`.
6. `medical_service.py`: ЭПИ теперь принимает только `.docx/.docm/.txt`, неверные расширения отклоняются понятным `ValueError`.
7. `medical_service.py`: `selected_docs="primary"` больше не разбирается посимвольно как последовательность символов.
8. `medical_service.py`: `output_dir=None` больше не создаёт папку `None`, а использует папку первичного документа.
9. `medical_service.py`: `override_data` больше не мутируется при создании документов.
10. `medical_service.py`: дата выписки раньше даты госпитализации теперь запрещена.
11. `medical_formatting.py`: медицинский `parse_date()` ограничен годами 1900–2200.
12. `dnd_mixin.py`: TXT-классификация drag-and-drop теперь читает cp1251, поэтому `ЭПИ.txt` с Windows-кодировкой распознаётся.
13. `diary_batch.py`: дневниковые входные DOCX/DOCM файлы валидируются до копирования/парсинга.
14. `diary_batch.py`: повторяющиеся дневниковые статусы из нескольких файлов схлопываются.
15. `diary_batch.py`: дата выписки раньше поступления теперь запрещена и для дневников.
16. `diary_batch.py`: пустой/пробельный `output_dir` больше не создаёт папку из пробелов.
17. `actions_medical_flow.py`: ручная компактная дата поступления нормализуется в `ДД.ММ.ГГГГ` перед renderer.
18. `pyproject.toml`: поддерживаемый диапазон Python синхронизирован с реально пройденной проверкой Python 3.13 (`>=3.11,<3.14`).
19. `smoke_combined_part06_diary_columns_settings.py`: добавлены regression-тесты на все новые фиксы.
20. Версия синхронизирована до `v1.3.10-audit-hardening`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python dnd_contract_check.py
python performance_check.py
python release_check.py
```

---

# Дополнение v1.3.9-audit-hardening — текущий аудит

Исправлено в этой итерации:

1. `medical_service.py`: добавлена проверка существования первичного DOCX до парсинга, вместо позднего непонятного падения внутри `python-docx`.
2. `medical_service.py`: добавлена проверка существования ЭПИ-файла.
3. `medical_service.py`: неизвестные типы документов в `selected_docs` теперь дают понятный `ValueError`, а не `KeyError`/полурендер.
4. `medical_service.py`: пустой список медицинских документов теперь явно запрещён.
5. `medical_service.py`: повторяющиеся документы в `selected_docs` схлопываются с сохранением порядка, чтобы не плодить дубли файлов.
6. `medical_service.py`: дата выписки валидируется и нормализуется на уровне service-layer, а не только в UI.
7. `medical_service.py`: `.docm` ЭПИ читается как Word-документ, а не как бинарный TXT.
8. `medical_service.py`: TXT ЭПИ читается через `utf-8-sig` / `utf-8` / `cp1251`, без тихого удаления кириллицы.
9. `dnd_mixin.py`: fallback drag-and-drop теперь разбирает несколько путей вида `{file 1} {file 2}`, даже если Tcl `splitlist` недоступен.
10. `dnd_mixin.py`: при перетаскивании папки папка результата больше не становится родительской папкой ошибочно.
11. `settings_mixin.py`: валидный JSON неверного типа (`[]`, строка и т.п.) теперь карантинится как повреждённый settings.
12. `settings_mixin.py`: имена quarantine-файлов получили микросекунды, чтобы не перетираться при двух быстрых ошибках.
13. `settings_mixin.py`: после неудачной записи настроек удаляется оставшийся `settings.json.tmp`.
14. `files_mixin.py`: silent-поиск принтеров теперь тоже учитывает системный принтер по умолчанию.
15. `actions_ui_state.py`: progress start/stop стал безопаснее для headless/test-вызовов без полноценного root lifecycle.
16. `smoke_combined_part06_diary_columns_settings.py`: добавлены regression-тесты на service hardening, cp1251 ЭПИ, DnD fallback и wrong-type settings.
17. Версия синхронизирована до `v1.3.9-audit-hardening` в `app_config.py`, `pyproject.toml`, `version_info.txt`, `README.md`, `RELEASE_NOTES.md`, `prod_audit.py`.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python release_check.py
```

---

# Audit + Production Fix Report

Архив проверен по коду, а не по README. Исправления внесены в исходники, smoke-tests, сборочную инфраструктуру и release-процесс.

## Базовый аудит: исправлено ранее

1. `main.py`: исправлена неправильная подпись compact UI после drag-and-drop текстов дневников — вместо чужого текста про первичный осмотр теперь показывается `Тексты: ...`.
2. `main.py`: drag-and-drop теперь принимает `.docm`, как и файловые диалоги; раньше DOCM отклонялся как неизвестный файл.
3. `main.py`: TXT-файл ЭПИ теперь распознаётся не только по имени, но и по содержимому (`ЭПИ`, `эпи:`, эпидемиологический текст).
4. `medical_documents.py`: исправлена проверка контекста дат рождения — индексы `regex match` больше не применяются к нормализованной строке другой длины.
5. `medical_documents.py`: дата поступления из строгого text-fallback больше не затирается пустым результатом структурного DOCX-поиска.
6. `medical_documents.py`: предупреждения пациента пересчитываются после финального выбора даты поступления, чтобы не оставались устаревшие warning-и.
7. `medical_documents.py`: чтение DOCX-таблиц больше не дублирует текст из объединённых ячеек.
8. `diary_filler.py`: извлечение текстов дневников больше не дублирует один и тот же статус из объединённых ячеек.
9. `diary_filler.py`: добавлена дедупликация одинаковых дневниковых статусов.
10. `diary_filler.py`: даты и месяц/год теперь принимают русские хвосты `г.` / `год`, например `11.06.2026 г.` и `06.2026 г.`.
11. `medical_documents.py`: `parse_date()` теперь принимает `ДД.ММ.ГГ г.` / `ДД.ММ.ГГГГ год`.
12. `medical_documents.py`: исправлено форматирование дат в заголовках документов: теперь `12.01.2026 г.`, а не `12.01.2026г.`.
13. `medical_documents.py`: исправлено дублирование `г.р.` в строках пациента, когда год рождения уже содержит `г.р.`.
14. `medical_documents.py`: исправлена опечатка района `Канвинский` → `Канавинского района`.
15. `smoke_test_combined.py`: добавлены регрессионные проверки на перечисленные ошибки.
16. `.github/workflows/windows-build.yml`: добавлен реально отсутствовавший GitHub Actions workflow, который README уже обещал.
17. `build_exe_windows.bat`: перед сборкой EXE выполняются проверки; в CI `pause` больше не блокирует workflow.
18. `start_windows.bat`: если `pythonw.exe` отсутствует, программа запускается через `python.exe`, а не падает сразу.
19. `README.md`: исправлен список документов, логика автоподбора дневников, описание smoke-test и структура разделов.

## Production hardening: исправлено сейчас

20. `main.py`: версия поднята до `v 1.1.0-production`.
21. `main.py`: `settings.json` теперь пишется атомарно через `.tmp` + `os.replace()`.
22. `main.py`: повреждённый `settings.json` переносится в `settings.broken.<timestamp>.json`, запуск продолжается.
23. `main.py`: добавлен whitelist настроек на диск — сохраняются только папки диалогов и принтер.
24. `main.py`: ФИО, диагноз, даты лечения и медицинские данные пациента принудительно не попадают в `settings.json`.
25. `smoke_test_combined.py`: добавлена регрессия на безопасную запись настроек.
26. `start_windows.bat`: запуск из исходников переведён на локальное `.venv_runtime`, без установки зависимостей в глобальный Python.
27. `start_windows_debug.bat`: диагностический запуск тоже переведён на `.venv_runtime`.
28. `start_windows_no_console.vbs`: добавлен fallback на `.venv_runtime` и основной launcher.
29. `requirements.txt`: runtime-зависимости ограничены major-диапазонами.
30. `requirements_build.txt`: build-зависимости ограничены major-диапазонами.
31. `requirements_dev.txt`: добавлен отдельный dev/build профиль.
32. `pyproject.toml`: добавлен project metadata и минимальный Ruff production-gate.
33. `version_info.txt`: добавлены Windows version metadata для EXE.
34. `release_check.py`: добавлен единый production-gate.
35. `make_release_zip.py`: добавлена воспроизводимая сборка clean source archive.
36. `build_exe_windows.bat`: сборка EXE теперь идёт только после `release_check.py`.
37. `build_exe_windows.bat`: добавлены `--version-file version_info.txt` и `--noupx`.
38. `.github/workflows/windows-build.yml`: CI теперь собирает EXE и clean source archive как два artifacts.
39. `.github/workflows/windows-build.yml`: upload падает, если EXE/архив не созданы.
40. `.gitignore`: добавлены `.venv_runtime/`, `release/`, `.ruff_cache/`.
41. `README.md`: переписан под production-поставку.
42. `PRODUCTION_REPORT.md`: добавлен честный отчёт о статусе release-candidate.
43. `RELEASE_NOTES.md`: добавлены release notes для `v1.1.0-production`.

## Проверки

Выполнено успешно:

```bat
python release_check.py
python make_release_zip.py
```

Внутри `release_check.py` выполнено:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
```

Ожидаемый результат smoke-test:

```text
OK
Medical docs with EPI: 7
Medical docs without EPI: 7
Diary files: 1
```

## Оставшиеся архитектурные риски

- `main.py` всё ещё слишком большой: UI, настройки, drag-and-drop, печать и orchestration смешаны в одном файле.
- Много широких `except Exception`, часть из них оправдана для UI, но часть лучше заменить точечными исключениями и логированием.
- Полный `ruff`/type-check по всему проекту пока не включён, потому что это потребует отдельной безопасной декомпозиции `main.py`.
- Для массовой продажи нужен реальный Windows EXE smoke-test на машине врача, code-signing, installer/update strategy и обезличенный корпус реальных DOCX-fixtures.

## Оценка после production hardening

**8.8 / 10**.

Проект стал release-candidate для локального Windows production: есть рабочая логика, smoke/regression проверки, безопасная запись настроек, чистый production archive, CI-сборка EXE и понятный release-gate. До коммерческого “коробочного” продукта не хватает подписи EXE, реального Windows QA и расширенного корпуса обезличенных DOCX-документов.


## UI fix v1.1.1 — selected state

- Усилена видимость выбранных документов: активная плитка теперь подсвечивается всей поверхностью, border/glow и бейджем `ВЫБРАНО`.
- Кнопки `Тексты`/`Даты` после выбора файлов остаются визуально нажатыми.
- Кнопки `Да`/`Нет` в поле больничного листа переведены на единый устойчивый selected-state.
- Добавлен централизованный refresh selected-controls после кликов, popup-отмен и drag-and-drop.

## Дополнение v1.1.2: selected-state + больничный лист

1. `main.py`: версия поднята до `v 1.1.2-production`.
2. `main.py`: выбранные плитки документов теперь подсвечиваются всей карточкой, включая яркую рамку и бейдж `ВЫБРАНО`.
3. `main.py`: кнопки `Тексты` и `Даты` получают persistent selected-state после выбора файлов/папок.
4. `main.py`: кнопки `Да`/`Нет` для `Нужен больничный лист?` используют единый selected-state.
5. `main.py`: добавлен `_should_prompt_discharge_sick_leave_number()` как единый контракт popup номера ЛН.
6. `main.py`: удалён вызов popup номера ЛН из обработчика кнопки `Да` в блоке больничного листа.
7. `main.py`: popup `Номер больничного листа` теперь открывается только при выборе/создании `Выписного эпикриза`, если больничный лист отмечен как нужный.
8. `smoke_test_combined.py`: добавлена регрессия, что кнопка больничного листа не открывает второй popup.
9. `release_check.py`: добавлен production-contract для selected-state и логики popup номера ЛН.
## Дополнение v1.1.3: интеллигентная подсветка выбранных кнопок

1. `main.py`: версия поднята до `v 1.1.3-production`.
2. `main.py`: selected-state кнопок `Тексты`/`Даты`/`Да`/`Нет` стал мягче — без яркой заливки всей кнопки.
3. `main.py`: выбранные плитки документов больше не получают грубую яркую плашку; оставлены тёмный выбранный тон, тонкая cyan-обводка и аккуратная галочка.
4. `main.py`: удалён визуально тяжёлый бейдж `ВЫБРАНО` из блока документов.
5. `main.py`: зона `Перетащите сюда первичный осмотр/направление на госпитализацию` увеличена и получила дополнительную подсказку клика.
6. `release_check.py`: UI selected-state contract обновлён под мягкую production-подсветку.
## Дополнение v1.1.4: audit fixes + parser safety

1. `medical_documents.py`: исправлен ложный парсинг строки `Не работает` — раньше место работы могло стать мусорным значением `ет`.
2. `medical_documents.py`: broad label-cleaner больше не удаляет реальные должности `врач` и `врач-психиатр`.
3. `medical_documents.py`: должность из строки `Работает: ООО ..., в должности врач` сохраняется в отдельное поле `position`.
4. `medical_documents.py`: `Врач-психиатр` внутри поля `Должность` больше не считается началом чужого поля `Врач`.
5. `medical_documents.py`: компактный парсер работы получил границы слова, поэтому `Работа` больше не цепляется внутри `Работает`.
6. `medical_documents.py`: `parse_date()` принимает пробелы вокруг разделителей даты.
7. `medical_documents.py`: военкомат/районы с `\` без пробелов форматируются как список районов.
8. `medical_documents.py`: `safe_filename()` защищён от control chars и Windows-reserved names (`CON`, `NUL`, `COM1`... ).
9. `diary_filler.py`: `safe_filename_part()` получил ту же защиту от Windows-reserved names.
10. `main.py`: после drag-and-drop текстов дневников non-compact status label теперь показывает тот же префикс `Тексты:`, что и обычный выбор.
11. `make_release_zip.py`: clean archive исключает `.spec`, `.DS_Store`, `Thumbs.db`, `.vscode`, `.idea`.
12. `release_check.py`: production-gate теперь ловит эти мусорные артефакты до релиза.
13. `smoke_test_combined.py`: добавлены регрессии на все перечисленные ошибки.

Проверено: `python release_check.py`, `python make_release_zip.py`, отдельная проверка clean archive на фейковых `.spec`/`.DS_Store`/`Thumbs.db`/IDE-файлах.


## Дополнение v1.1.5: popup merge + discharge-date safety

1. `actions_creation_orchestrator.py`: убраны две последовательные проверки `Лечение` → `Дата выписки` для сценариев без выписного/РВК; теперь общие недостающие поля собираются одним popup.
2. `actions_creation_orchestrator.py`: если выбран выписной эпикриз или Акт РВК, именно их merged-popup владеет датой выписки и общими полями, поэтому отдельный popup даты больше не открывается заранее.
3. `layout_action_bar.py`: при клике по обычным медицинским документам вместо узкого treatment-popup используется общий merged-popup, чтобы направление на госпитализацию не давало два окна подряд.
4. `dialog_expert.py`: добавлен `_prompt_common_output_requirements()` — единый сборщик полей `Номер истории болезни`, `Лечение`, `Диагноз`, `Дата выписки` для общих сценариев.
5. `dialog_expert.py`: popup направления на госпитализацию больше не спрашивает `Дата выписки`, если среди выбранных итоговых документов нет выписного эпикриза, дневников или Акта РВК.
6. `dialog_expert.py`: ранний выход из popup направления теперь проверяет не только номер истории и лечение, но и диагноз.
7. `dialog_expert.py`: ранний выход также учитывает обязательную дату выписки, если она нужна выбранным документам.
8. `actions_navigation.py`: повторный разбор первичного документа больше не обнуляет дату поступления, найденную строгим fallback-парсером, если структурный поиск по заголовку дату не нашёл.
9. `medical_treatment_detection.py`: строка `Назначенное лечение терапия по схеме` без двоеточия теперь распознаётся как явный раздел лечения.
10. `medical_parser_inline.py`: добавлен отсутствующий импорт `List`, чтобы `typing.get_type_hints()` не падал на публичной аннотации `_all_inline_aliases()`.
11. `medical_parser_demographics.py`: добавлен отсутствующий импорт `List` для корректности type-hints/инструментов аудита.
12. `medical_renderer_labs.py`: добавлен отсутствующий импорт `Dict` для корректности type-hints/инструментов аудита.
13. `smoke_combined_part02_ui_parser_regressions.py`: добавлены регрессии на единый общий popup и отсутствие лишней даты выписки в popup направления.
14. `prod_audit.py`: production-contract обновлён под merged common popup и лечение без двоеточия.

Проверено успешно:

```bat
python -m compileall -q .
python smoke_test.py
python smoke_test_combined.py
python prod_audit.py
python release_check.py
```
