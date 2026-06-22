from __future__ import annotations

from pathlib import Path
import re

_TEXT_SNIFF_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")

from app_config import *


class DragDropMixin:
    def _install_file_drop_support(self) -> None:
        """Безопасно включить drag-and-drop, если доступен tkinterdnd2.

        В предыдущем варианте использовалась нативная подмена Windows WndProc
        через pywin32/WM_DROPFILES. Это рискованный механизм для Tkinter-окна:
        на части Windows-сборок приложение может не открываться вовсе.
        Поэтому запуск программы теперь не зависит от drag-and-drop. Если
        TkDND доступен, перетаскивание включается; если нет — программа всё
        равно запускается, а зона работает как большая кнопка выбора файла.
        """
        if self._register_tkinterdnd_drop_targets():
            self._log("\n✅ Drag-and-drop включён: файлы можно перетаскивать в окно программы.\n")
            return
        self._log("\nℹ️ Drag-and-drop недоступен в этом запуске. Используйте зону как кнопку «Выбрать».\n")

    def _register_tkinterdnd_drop_targets(self) -> bool:
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
        except Exception:
            return False

        widgets = [self.root]
        widgets.extend(getattr(self, "_drop_widgets", []))
        registered = False
        for widget in widgets:
            if not hasattr(widget, "drop_target_register") or not hasattr(widget, "dnd_bind"):
                continue
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop_event)
                registered = True
            except Exception:
                continue
        return registered

    def _on_drop_event(self, event):
        paths = self._parse_drop_event_data(getattr(event, "data", ""))
        if paths:
            self._handle_dropped_files(paths)
        return "break"

    def _parse_drop_event_data(self, data: str) -> list[str]:
        data = (data or "").strip()
        if not data:
            return []
        try:
            return [str(item).strip() for item in self.root.tk.splitlist(data) if str(item).strip()]
        except Exception:
            # Fallback без Tcl: поддерживаем не только один путь, но и типичный
            # Windows-набор ``{C:\путь 1.docx} {C:\путь 2.docx}``. Старый
            # fallback возвращал всю строку одним "путём", из-за чего DnD
            # нескольких файлов мог молча ничего не распознать.
            braced = [match.group(1).strip() for match in re.finditer(r"\{([^{}]+)\}", data) if match.group(1).strip()]
            if braced:
                return braced
            return [data.strip("{} ")]

    def _handle_dropped_files(self, paths: list[str]) -> None:
        primary_path = ""
        epi_path = ""
        status_paths: list[str] = []
        diary_paths: list[str] = []
        numbered_template_dirs: list[str] = []
        diary_text_dirs: list[str] = []
        ignored: list[str] = []

        for raw_path in paths:
            path = str(raw_path).strip().strip("{}")
            if not path or not Path(path).exists():
                continue
            kind = self._classify_dropped_file(path)
            if kind == "primary":
                primary_path = path
            elif kind == "epi":
                epi_path = path
            elif kind == "diary_template":
                diary_paths.append(path)
            elif kind == "diary_status":
                status_paths.append(path)
            elif kind == "numbered_diary_template_dir":
                numbered_template_dirs.append(path)
            elif kind == "diary_text_dir":
                diary_text_dirs.append(path)
            else:
                ignored.append(Path(path).name)

        if primary_path:
            self._apply_primary_document_path(primary_path, prompt_for_referral=True)
        if epi_path:
            self.epi_path_var.set(epi_path)
            self._remember_dialog_directory(DIR_EPI, epi_path)
            self.reparse_navigation(silent=True)
        if status_paths:
            self.diary_texts_dir = str(Path(status_paths[0]).parent)
            self.status_files = []
            self._diary_text_files_auto_selected = True
            if not self._auto_select_diary_text_by_diagnosis(ask_folder=False):
                self.status_files = status_paths
                self._diary_text_files_auto_selected = False
                self._remember_dialog_directory(DIR_DIARY_TEXTS, status_paths[0])
                self._update_diary_text_label(success=True)
                self._redraw_selection_controls()
        if diary_paths:
            parent = Path(diary_paths[0]).parent
            if self._folder_contains_numbered_diary_templates(parent):
                self._set_numbered_diary_template_dir(parent, auto_select=True, warn_if_missing=False)
            else:
                # Совместимость с перетаскиванием одиночной старой таблицы: не
                # ломаем прежний путь, но кнопка UI теперь выбирает именно папку.
                self.diary_files = diary_paths
                self._diary_files_auto_selected = False
                self._remember_dialog_directory(DIR_DIARY_TEMPLATES, diary_paths[0])
                self._update_diary_template_label(success=True)
                self._redraw_selection_controls()
        if numbered_template_dirs:
            self._set_numbered_diary_template_dir(numbered_template_dirs[0], auto_select=True, warn_if_missing=False)
        if diary_text_dirs:
            self.diary_texts_dir = diary_text_dirs[0]
            self._remember_dialog_directory(DIR_DIARY_TEXTS, diary_text_dirs[0], selected_is_dir=True)
            if not self._auto_select_diary_text_by_diagnosis(ask_folder=False):
                self._update_diary_text_label(success=True)
                self._redraw_selection_controls()
        first_known = primary_path or epi_path or (status_paths[0] if status_paths else "") or (diary_paths[0] if diary_paths else "") or (numbered_template_dirs[0] if numbered_template_dirs else "") or (diary_text_dirs[0] if diary_text_dirs else "")
        if first_known and not self.output_dir_var.get().strip():
            first_path = Path(first_known)
            self._set_output_dir_auto(first_path if first_path.is_dir() else first_path.parent)

        recognized = sum(bool(x) for x in [primary_path, epi_path]) + len(status_paths) + len(diary_paths) + len(numbered_template_dirs) + len(diary_text_dirs)
        if recognized:
            self._log(f"\n✅ Через drag-and-drop распознано файлов: {recognized}.\n")
            self._set_status(f"Распознано файлов: {recognized}")
        if ignored:
            self._log("\n⚠️ Не удалось распознать файлы: " + ", ".join(ignored) + "\n")

    @staticmethod
    def _read_text_snippet_for_classification(path: Path, *, limit: int = 65536) -> str:
        """Read enough of a TXT file to classify it without corrupting cp1251 Cyrillic.

        Drag-and-drop classification must match service-layer EPI loading. The old
        utf-8/errors=ignore read could silently drop every Cyrillic byte from a
        Windows-1251 TXT and therefore fail to recognize an EPI file.
        """
        try:
            raw = path.read_bytes()[:limit]
        except Exception:
            return ""
        for encoding in _TEXT_SNIFF_ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _classify_dropped_file(self, path: str) -> str:
        p = Path(path)
        if p.is_dir():
            if self._folder_contains_numbered_diary_templates(p):
                return "numbered_diary_template_dir"
            try:
                from diary_text_selection import folder_has_diary_text_candidates
                if folder_has_diary_text_candidates(p):
                    return "diary_text_dir"
            except Exception:
                pass
            return "unknown"
        suffix = p.suffix.lower()
        stem_low = p.stem.lower().replace("ё", "е")
        if suffix == ".txt":
            txt = self._read_text_snippet_for_classification(p)
            txt_low = txt.lower().replace("ё", "е")
            if "эпи" in stem_low or txt_low.strip().startswith("эпи") or "эпи:" in txt_low or "эпидемиологическ" in txt_low:
                return "epi"
            return "unknown"
        if suffix not in {".docx", ".docm"}:
            return "unknown"

        text = ""
        try:
            from medical_docx_reader import extract_docx_text
            text = extract_docx_text(path)
        except Exception:
            text = ""
        low = text.lower().replace("ё", "е")

        if "эпи" in stem_low or low.strip().startswith("эпи") or "эпи:" in low:
            return "epi"

        try:
            data = self._parse_primary_document(path)
            kind = (data.input_document_kind or "").lower().replace("ё", "е")
            if "направ" in kind or "первичный осмотр" in kind:
                return "primary"
            if data.fio and (data.birth or data.admission_date) and (data.complaints or data.mental_status or data.diagnosis):
                return "primary"
        except Exception:
            pass

        try:
            from diary_table import detect_first_month_year_from_docx
            if detect_first_month_year_from_docx(path) is not None:
                return "diary_template"
        except Exception:
            pass

        try:
            from diary_text_parser import extract_statuses_from_docx
            statuses = extract_statuses_from_docx(path)
            if statuses:
                return "diary_status"
        except Exception:
            pass

        if "эпи" in low or "эпидемиологическ" in low:
            return "epi"
        return "unknown"
