from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List

from app_config import *


class ActionsReportsMixin:
    def _diagnostic_reports_enabled(self) -> bool:
        """Писать служебные TXT-отчёты только в явном debug-режиме.

        По умолчанию папка результата должна содержать только документы,
        которые пользователь выбрал в UI. Для диагностики можно запустить
        программу с переменной окружения MEDICAL_AUTOFILL_WRITE_REPORTS=1.
        """
        value = os.environ.get("MEDICAL_AUTOFILL_WRITE_REPORTS", "").strip().lower()
        return value in {"1", "true", "yes", "y", "да", "on"}

    def _write_creation_report(
        self,
        *,
        selected_medical: List[str],
        selected_diaries: bool,
        created_medical: List[Path],
        diary_result=None,
        errors: List[str] | None = None,
    ) -> Path | None:
        if not self._diagnostic_reports_enabled():
            return None
        try:
            out_dir = self._result_output_dir()
            out_dir.mkdir(parents=True, exist_ok=True)
            report_path = out_dir / "ОТЧЁТ_создание_документов.txt"
            lines: List[str] = []
            lines.append("ОТЧЁТ: создание выбранных документов")
            lines.append(f"Дата запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            lines.append("")
            names = self._selected_output_names(selected_medical, selected_diaries)
            lines.append("Выбрано в UI: " + (", ".join(names) if names else "ничего"))
            lines.append(f"Медицинских документов выбрано: {len(selected_medical)}")
            lines.append(f"Дневники выбраны: {'да' if selected_diaries else 'нет'}")
            lines.append("")
            lines.append(f"Медицинских документов создано: {len(created_medical)}")
            for path in created_medical:
                lines.append(f"- {path.name}")
            if diary_result is not None:
                lines.append("")
                lines.append(f"Дневниковых файлов создано: {len(list(diary_result.created_files))}")
                for path in diary_result.created_files:
                    lines.append(f"- {Path(path).name}")
            if errors:
                lines.append("")
                lines.append("Ошибки:")
                lines.extend(f"- {item}" for item in errors)
            report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._log(f"Отчёт создания: {report_path}\n")
            return report_path
        except Exception as exc:
            self._log(f"\n⚠️ Не удалось записать отчёт создания документов: {exc}\n")
            return None
