from __future__ import annotations

from pathlib import Path
from typing import List
from tkinter import filedialog, messagebox
import threading

from app_config import *
from medical_models import PatientData
from diary_text_selection import (
    find_diary_text_file_for_diagnosis,
    folder_has_diary_text_candidates,
)


class FilesMixin:
    def _mark_manual_output_dir(self) -> None:
        if self._suspend_output_dir_tracking:
            return
        # Пользователь изменил папку результата вручную или через кнопку:
        # дальше автоматический выбор первичного документа её не перетирает.
        self._manual_output_dir = True

    def _set_output_dir_auto(self, path: str | Path) -> None:
        value = str(path).strip()
        if not value:
            return
        self._suspend_output_dir_tracking = True
        try:
            self.output_dir_var.set(value)
        finally:
            self._suspend_output_dir_tracking = False

    def _set_output_dir_from_primary_default(self, primary_path: str | Path) -> None:
        # Главный пользовательский контракт: если выбран первичный осмотр
        # или направление на госпитализацию, папка сохранения по умолчанию
        # становится папкой этого входного файла.
        if self._manual_output_dir:
            return
        try:
            parent = Path(primary_path).resolve().parent
        except Exception:
            parent = Path(primary_path).parent
        self._set_output_dir_auto(parent)

    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(
            title="Выберите папку результата",
            initialdir=self._dialog_initial_dir(DIR_OUTPUT),
        )
        if path:
            self.output_dir_var.set(path)
            self._manual_output_dir = True
            self._remember_dialog_directory(DIR_OUTPUT, path, selected_is_dir=True)

    def _set_primary_document_type(self, selected_type: str) -> None:
        selected_type = "hospitalization_referral" if selected_type == "hospitalization_referral" else "primary_exam"
        self.primary_document_type_var.set(selected_type)
        self.primary_document_type_display_var.set(
            "Направление на госпитализацию" if selected_type == "hospitalization_referral" else "Первичный осмотр"
        )

    def _reset_primary_document_runtime_state(self) -> None:
        """Сбросить данные прошлого пациента перед новым первичным файлом."""
        self.assigned_treatment_var.set("")
        self.case_number_var.set("")
        self.expert_work_status_var.set("")
        self.expert_work_org_var.set("")
        self.expert_position_var.set("")
        self.expert_sick_leave_needed_var.set("нет")
        self.expert_sick_leave_from_var.set("")
        self.expert_sick_leave_number_var.set("")
        self.vk_mse_work_org_var.set("")
        self.vk_mse_position_var.set("")
        self.sick_leave_vk_work_org_var.set("")
        self.sick_leave_vk_position_var.set("")
        self.sick_leave_vk_work_position_var.set("")
        self._primary_work_org_default = ""
        self._primary_work_position_default = ""
        self._work_details_manually_edited = False
        self._update_expert_sick_leave_display()
        self._manual_patient_name = False
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._manual_diagnosis = False
        self._popup_diagnosis_override = ""
        self._popup_discharge_date_override = ""
        # Сбрасываем только автоматически выбранные файлы прошлого пациента.
        # Папки оставляем: по новому диагнозу/дате программа подберёт новые
        # тексты дневников и новый 01–31-шаблон.
        if getattr(self, "_diary_text_files_auto_selected", False):
            self.status_files = []
            self._diary_text_files_auto_selected = False
            self._update_diary_text_label(success=bool(getattr(self, "diary_texts_dir", "")))
        if getattr(self, "_diary_files_auto_selected", False):
            self.diary_files = []
            self._diary_files_auto_selected = False
            self._update_diary_template_label(success=bool(getattr(self, "diary_template_dir", "")))
        self._set_ui_var(self.patient_name_var, "")
        self._set_ui_var(self.admission_date_var, "")
        self._set_ui_var(self.discharge_date_var, "")
        self._set_ui_var(self.diagnosis_var, "")
        if hasattr(self, "_set_primary_drop_empty"):
            self._set_primary_drop_empty()
        elif hasattr(self, "primary_selected_status_var"):
            self.primary_selected_status_var.set(" ")
        self.data = PatientData()

    def _primary_type_from_parsed_data(data: PatientData) -> str:
        kind = (data.input_document_kind or "").lower().replace("ё", "е")
        if "направ" in kind or "госпитализируется" in kind:
            return "hospitalization_referral"
        return "primary_exam"

    def _apply_primary_document_path(self, path: str, *, prompt_for_referral: bool) -> None:
        path = str(path)
        if not path or not Path(path).exists():
            return
        self.navigation_path_var.set(path)
        self._remember_dialog_directory(DIR_PRIMARY_DOCUMENTS, path)
        self._reset_primary_document_runtime_state()
        self._set_output_dir_from_primary_default(path)

        try:
            parsed = self._parse_primary_document(path)
            self._set_primary_document_type(self._primary_type_from_parsed_data(parsed))
        except Exception:
            # Если файл формально выбран, но тип не удалось понять до основного
            # разбора, оставляем безопасный режим первичного осмотра без popup.
            self._set_primary_document_type("primary_exam")

        if hasattr(self, "_set_primary_drop_selected"):
            self._set_primary_drop_selected(path)
        elif hasattr(self, "primary_selected_status_var"):
            kind_text = "Выбрано направление на госпитализацию" if self.primary_document_type_var.get() == "hospitalization_referral" else "Выбран первичный осмотр"
            self.primary_selected_status_var.set(f"{kind_text}: {Path(path).name}")
        # Drop-зона показывает только короткое имя файла, чтобы длинный путь не
        # растягивал первый блок и не сдвигал поля/кнопки.

        self.reparse_navigation()
        # Перед popup ещё раз жёстко подтягиваем дату поступления из строки
        # заголовка, например «15.04.2026 Направление на госпитализацию».
        # Это не даёт полю даты остаться пустым или подхватить дату рождения.
        self._sync_admission_date_from_title(force=True)
        if self.primary_document_type_var.get() == "hospitalization_referral" and prompt_for_referral:
            self._prompt_assigned_treatment_if_needed(force=True)
            # reparse_navigation нужен, чтобы обновить preview и данные из файла,
            # но он не имеет права стереть дату выписки, введённую врачом в popup.
            popup_discharge_after_prompt = self._popup_discharge_date_override.strip()
            self.reparse_navigation(silent=True)
            if popup_discharge_after_prompt:
                self._popup_discharge_date_override = popup_discharge_after_prompt
                self._set_ui_var(self.discharge_date_var, popup_discharge_after_prompt)
                self._manual_discharge_date = True
                self.data.discharge_date = popup_discharge_after_prompt
        else:
            self._set_status("Первичный осмотр распознан. Popup не требуется.")
        # После того как диагноз и дата поступления точно подтянуты, пробуем
        # автоматически подобрать тексты дневников по названию диагноза и
        # конкретный 01–31-шаблон по дате госпитализации.
        self._auto_select_diary_text_by_diagnosis(ask_folder=False)
        self._auto_select_numbered_diary_template(ask_folder=False)

    def choose_navigation(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите первичный документ",
            initialdir=self._dialog_initial_dir(DIR_PRIMARY_DOCUMENTS),
            filetypes=[("Word DOCX", "*.docx")],
        )
        if not path:
            return
        self._apply_primary_document_path(path, prompt_for_referral=True)

    def choose_epi(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите файл ЭПИ",
            initialdir=self._dialog_initial_dir(DIR_EPI),
            filetypes=[("Word DOCX", "*.docx"), ("Text", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.epi_path_var.set(path)
            self._remember_dialog_directory(DIR_EPI, path)
            self.reparse_navigation(silent=True)

    def _diary_text_label_text(self) -> str:
        max_chars = 56 if self._compact_ui else 96
        if self.status_files:
            text = self._short_file_list(
                self.status_files,
                limit=2 if self._compact_ui else 3,
                single_line=self._compact_ui,
                max_chars=max_chars,
            )
            return "Тексты: " + text
        if getattr(self, "diary_texts_dir", ""):
            return "Тексты: " + self._truncate_label_text(Path(self.diary_texts_dir).name, max_chars=max_chars)
        return "Тексты: не выбраны"

    def _update_diary_text_label(self, *, success: bool | None = None) -> None:
        if not hasattr(self, "status_files_label"):
            return
        text = self._diary_text_label_text()
        color = SUCCESS if (success or self.status_files or getattr(self, "diary_texts_dir", "")) else MUTED
        self.status_files_label.config(text=text, foreground=color)

    def _candidate_diary_text_dirs(self) -> list[Path]:
        result: list[Path] = []
        seen: set[str] = set()

        def add_folder(candidate: str | Path) -> None:
            if not candidate:
                return
            try:
                folder = Path(candidate).expanduser()
                if folder.is_file():
                    folder = folder.parent
                if not folder.exists() or not folder.is_dir():
                    return
                if not folder_has_diary_text_candidates(folder):
                    return
                key = str(folder.resolve())
            except Exception:
                return
            if key not in seen:
                seen.add(key)
                result.append(folder)

        if getattr(self, "diary_texts_dir", ""):
            add_folder(self.diary_texts_dir)
        add_folder(self._get_saved_directory(DIR_DIARY_TEXTS))

        # Автопоиск рядом с первичным документом: только прямые папки с
        # понятными именами, чтобы не шерстить весь компьютер и не взять чужой DOCX.
        roots: list[Path] = []
        for value in (self.navigation_path_var.get().strip(), self.output_dir_var.get().strip()):
            if value:
                try:
                    p = Path(value).expanduser()
                    roots.append(p.parent if p.is_file() else p)
                except Exception:
                    pass
        for root in roots:
            try:
                children = [root, *list(root.iterdir())[:120]]
            except Exception:
                children = [root]
            for child in children:
                if not child.is_dir():
                    continue
                name = child.name.lower().replace("ё", "е")
                if any(token in name for token in ("дневник", "дневники", "тексты")):
                    add_folder(child)
        return result

    def _auto_select_diary_text_by_diagnosis(self, *, ask_folder: bool = False) -> bool:
        diagnosis = self.diagnosis_var.get().strip()
        if not diagnosis and getattr(self, "data", None) is not None:
            diagnosis = getattr(self.data, "diagnosis", "") or ""
        if not diagnosis:
            return False
        # Ручной выбор нескольких файлов врачом сохраняем. Автоподбор может
        # заменить только пустой выбор или прошлый автоматический выбор.
        if self.status_files and not getattr(self, "_diary_text_files_auto_selected", False):
            return True

        for folder in self._candidate_diary_text_dirs():
            found = find_diary_text_file_for_diagnosis(folder, diagnosis)
            if not found:
                continue
            self.diary_texts_dir = str(found.parent)
            self.status_files = [str(found)]
            self._diary_text_files_auto_selected = True
            self._remember_dialog_directory(DIR_DIARY_TEXTS, str(found))
            self._update_diary_text_label(success=True)
            self._redraw_selection_controls()
            self._log(f"\n✅ Автоматически выбран текст дневников по диагнозу: {found.name}.\n")
            return True

        if ask_folder:
            selected = filedialog.askopenfilename(
                title="Выберите любой DOCX из папки с текстами дневников",
                initialdir=self._dialog_initial_dir(DIR_DIARY_TEXTS),
                filetypes=[("Word DOCX", "*.docx *.docm"), ("All files", "*.*")],
            )
            if selected:
                folder = Path(selected).parent
                self.diary_texts_dir = str(folder)
                self._remember_dialog_directory(DIR_DIARY_TEXTS, str(folder), selected_is_dir=True)
                found = find_diary_text_file_for_diagnosis(folder, diagnosis)
                if found:
                    self.status_files = [str(found)]
                    self._diary_text_files_auto_selected = True
                    self._remember_dialog_directory(DIR_DIARY_TEXTS, str(found))
                    self._update_diary_text_label(success=True)
                    self._redraw_selection_controls()
                    self._log(f"\n✅ Автоматически выбран текст дневников по диагнозу: {found.name}.\n")
                    return True
                # Если совпадения нет, выбранный файл остаётся ручным fallback.
                self.status_files = [str(selected)]
                self._diary_text_files_auto_selected = False
                self._update_diary_text_label(success=True)
                self._redraw_selection_controls()
                return True
        return False

    def choose_status_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите файл(ы) с текстами дневников или любой DOCX из папки диагнозов",
            initialdir=self._dialog_initial_dir(DIR_DIARY_TEXTS),
            filetypes=[("Word DOCX", "*.docx *.docm"), ("All files", "*.*")],
        )
        if not paths:
            return
        selected_paths = list(paths)
        self.diary_texts_dir = str(Path(selected_paths[0]).parent)
        self._remember_dialog_directory(DIR_DIARY_TEXTS, selected_paths[0])

        # Новый контракт: если в выбранной папке файлы дневников названы
        # диагнозами, после чтения первичного документа выбираем DOCX по
        # diagnosis_var. Если диагноз ещё не прочитан, выбранный файл считается
        # временным указателем на папку и потом может быть заменён автоматически.
        had_diagnosis = bool(self.diagnosis_var.get().strip() or getattr(getattr(self, "data", None), "diagnosis", ""))
        self.status_files = []
        self._diary_text_files_auto_selected = True
        if not self._auto_select_diary_text_by_diagnosis(ask_folder=False):
            self.status_files = selected_paths
            self._diary_text_files_auto_selected = not had_diagnosis
            self._update_diary_text_label(success=True)
            self._redraw_selection_controls()
            self._log(f"\n✅ Выбраны тексты дневников: {len(self.status_files)} файл(ов).\n")
        if self.status_files and not self.output_dir_var.get().strip():
            self._set_output_dir_auto(Path(self.status_files[0]).parent)

    def _diary_template_label_text(self) -> str:
        max_chars = 42 if self._compact_ui else 78
        if self.diary_files:
            path = Path(self.diary_files[0])
            return "Даты: " + self._truncate_label_text(path.name, max_chars=max_chars)
        if getattr(self, "diary_template_dir", ""):
            return "Даты: " + self._truncate_label_text(Path(self.diary_template_dir).name, max_chars=max_chars)
        return "Даты: не выбраны"

    def _update_diary_template_label(self, *, success: bool | None = None) -> None:
        if not hasattr(self, "diary_files_label"):
            return
        text = self._diary_template_label_text()
        color = SUCCESS if (success or self.diary_files or getattr(self, "diary_template_dir", "")) else MUTED
        self.diary_files_label.config(text=text, foreground=color)

    def _set_numbered_diary_template_dir(self, folder: str | Path, *, auto_select: bool = True, warn_if_missing: bool = False) -> bool:
        root = Path(folder).expanduser()
        if not root.exists() or not root.is_dir():
            if warn_if_missing:
                messagebox.showwarning("Папка не найдена", "Выбранная папка шаблонов дневников не найдена.")
            return False
        if not self._folder_contains_numbered_diary_templates(root):
            if warn_if_missing:
                messagebox.showwarning(
                    "Нет шаблонов 01–31",
                    "В выбранной папке не найдены DOCX-шаблоны с именами 01.docx, 02.docx, 03.docx … 31.docx.",
                )
            return False
        self.diary_template_dir = str(root)
        self.diary_files = []
        self._diary_files_auto_selected = True
        self._remember_numbered_diary_template_dir(root)
        self._update_diary_template_label(success=True)
        self._redraw_selection_controls()
        selected = self._auto_select_numbered_diary_template(ask_folder=False) if auto_select else False
        if selected:
            self.output_vars[DIARY_KIND].set(True)
        self._log(f"\n✅ Выбрана папка шаблонов дневников: {root}\n")
        return True

    def choose_diary_files(self) -> None:
        # Кнопка «Шаблоны дневников» выбирает ПАПКУ шаблонов.
        # Чтобы врач видел, что файлы внутри действительно есть, сначала открываем
        # файловое окно и просим выбрать любой DOCX из этой папки. Если пользователь
        # отменил — даём fallback на обычный выбор папки.
        initial_dir = self._dialog_initial_dir(
            DIR_NUMBERED_DIARY_TEMPLATES,
            self._get_saved_directory(DIR_DIARY_TEMPLATES),
        )
        selected = filedialog.askopenfilename(
            title="Выберите любой DOCX из папки «шаблоны дневников»",
            initialdir=initial_dir,
            filetypes=[("Word DOCX", "*.docx *.docm"), ("All files", "*.*")],
        )
        if selected:
            folder = Path(selected).parent
        else:
            folder_value = filedialog.askdirectory(
                title="Выберите папку «шаблоны дневников»",
                initialdir=initial_dir,
            )
            if not folder_value:
                return
            folder = Path(folder_value)
        if self._set_numbered_diary_template_dir(folder, auto_select=True, warn_if_missing=True):
            if not self.output_dir_var.get().strip():
                self._set_output_dir_auto(folder)

    @staticmethod
    def _truncate_label_text(text: str, *, max_chars: int = 64) -> str:
        """Return a stable one-line label that cannot stretch compact UI rows."""
        value = " ".join(str(text or "").split())
        if len(value) <= max_chars:
            return value
        if max_chars <= 12:
            return value[:max_chars].rstrip()
        left = max(4, (max_chars - 1) // 2)
        right = max(4, max_chars - left - 1)
        return value[:left].rstrip() + "…" + value[-right:].lstrip()

    def _short_file_list(
        self,
        paths: List[str],
        limit: int = 3,
        *,
        single_line: bool = False,
        max_chars: int = 80,
    ) -> str:
        names = [self._truncate_label_text(Path(path).name, max_chars=max_chars) for path in paths]
        separator = ", " if single_line else "\n"
        if len(names) <= limit:
            return separator.join(names)
        tail = f"… ещё {len(names) - limit}"
        return separator.join(names[:limit] + [tail])

    def _apply_printer_discovery_result(self, printers: list[str], default: str = "", *, silent: bool = False) -> None:
        self.available_printers = printers
        if hasattr(self, "printer_combo"):
            self.printer_combo.configure(values=printers)
        current = self.printer_var.get().strip()
        saved = str(self._settings.get("printer", "")).strip()
        if printers:
            if current in printers:
                chosen = current
            elif saved in printers:
                chosen = saved
            elif default in printers:
                chosen = default
            else:
                chosen = printers[0]
            self.printer_var.set(chosen)
            if not silent:
                self._log(f"\n🖨 Найдены принтеры: {len(printers)}. Выбран: {chosen}\n")
        else:
            self.printer_var.set("")
            if not silent:
                self._log("\n🖨 Принтеры не найдены. Печать доступна в Windows при установленном принтере.\n")

    def _select_default_printer_sync(self) -> bool:
        """Synchronously choose a printer only when the user explicitly asked to print."""
        try:
            from printer_support import get_default_printer, list_printers
            printers = list_printers()
            default = get_default_printer() if printers else ""
        except Exception:
            printers = []
            default = ""
        self._apply_printer_discovery_result(printers, default, silent=True)
        return bool(self.printer_var.get().strip())

    def refresh_printers(self, *, silent: bool = False) -> None:
        """Обновить список системных принтеров без подвисания UI.

        Windows printer discovery may call PowerShell/WMIC/win32 APIs and can take
        noticeable time on some machines. Discovery runs in a daemon thread and
        only the final combobox update is returned to the Tk thread. Repeated
        clicks do not spawn parallel discovery threads.
        """
        if getattr(self, "_printer_refresh_in_progress", False):
            return
        self._printer_refresh_in_progress = True

        def worker() -> None:
            try:
                from printer_support import get_default_printer, list_printers
                printers = list_printers()
                default = get_default_printer() if printers else ""
            except Exception:
                printers = []
                default = ""

            def apply_result() -> None:
                self._printer_refresh_in_progress = False
                self._apply_printer_discovery_result(printers, default, silent=silent)

            try:
                self.root.after(0, apply_result)
            except Exception:
                self._printer_refresh_in_progress = False

        if not silent:
            self._set_status("Ищу принтеры…")
        threading.Thread(target=worker, name="printer-discovery", daemon=True).start()

    def _on_printer_selected(self, _event=None) -> None:
        selected = self.printer_var.get().strip()
        if selected:
            self._settings["printer"] = selected
            self._save_settings()
            self._log(f"\n🖨 Принтер сохранён: {selected}\n")
