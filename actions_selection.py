from __future__ import annotations

from pathlib import Path
from typing import List

from app_config import *
from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER


class ActionsSelectionMixin:
    def selected_medical_docs(self) -> List[str]:
        return [kind for kind in DOCUMENT_ORDER if self.output_vars[kind].get()]

    def diaries_selected(self) -> bool:
        return bool(self.output_vars[DIARY_KIND].get())

    def _selected_output_names(self, selected_medical: List[str], selected_diaries: bool) -> List[str]:
        names = [DOCUMENT_LABELS.get(kind, kind) for kind in selected_medical]
        if selected_diaries:
            names.append(DIARY_LABEL)
        return names

    def _update_selected_outputs_status(self) -> None:
        names = self._selected_output_names(self.selected_medical_docs(), self.diaries_selected())
        if names:
            self._set_status("Выбрано: " + ", ".join(names))
        else:
            self._set_status("Документы для создания не выбраны")
        self._redraw_selection_controls()

    def _result_output_dir(self) -> Path:
        explicit = self.output_dir_var.get().strip()
        navigation = self.navigation_path_var.get().strip()
        if navigation and Path(navigation).exists() and not self._manual_output_dir:
            return Path(navigation).parent
        if explicit:
            return Path(explicit)
        if navigation:
            return Path(navigation).parent
        if self.diary_files:
            return Path(self.diary_files[0]).parent
        return Path.cwd()
