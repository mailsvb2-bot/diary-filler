from __future__ import annotations

import re
from pathlib import Path
from typing import List
import tkinter as tk
from tkinter import messagebox

from app_config import *
from medical_formatting import parse_date
from medical_models import PatientData
from medical_parser_sanitize import sanitize_diagnosis

def _search_icd10_f(query: str, *, limit: int):
    from icd10_f import search_icd10_f as _real_search_icd10_f
    return _real_search_icd10_f(query, limit=limit)


def _format_diagnosis(item) -> str:
    from icd10_f import format_diagnosis as _real_format_diagnosis
    return _real_format_diagnosis(item)


class DialogExpertMixin:
    @staticmethod
    def _normalize_yes_no(value: str) -> str:
        value = (value or "").strip().lower().replace("ё", "е")
        if value in {"да", "д", "yes", "y", "1", "+", "нужен", "нужна", "нужно", "работает"}:
            return "да"
        if value in {"нет", "н", "no", "n", "0", "-", "не нужен", "не нужна", "не нужно", "не работает"}:
            return "нет"
        return ""

    @staticmethod
    def _clean_popup_work_org(value: str) -> str:
        value = (value or "").strip().strip(" ,.;:")
        value = re.sub(r"^(?:в\s+организации|организации|в)\s+", "", value, flags=re.IGNORECASE).strip(" ,.;:")
        low = value.lower().replace("ё", "е")
        if low in {"не работает", "нет", "не указан", "не указано", "-"}:
            return ""
        return value

    @staticmethod
    def _clean_popup_position(value: str) -> str:
        value = (value or "").strip().strip(" ,.;:")
        value = re.sub(r"^(?:должность|в\s+должности)\s*[:.\-]?\s*", "", value, flags=re.IGNORECASE).strip(" ,.;:")
        return value

    def _primary_work_pair_from_data(self, data: PatientData) -> tuple[str, str]:
        """Работа/должность, распознанные из первичного документа.

        Если в документе написано «не работает», popup-поля остаются пустыми.
        """
        org = self._clean_popup_work_org(getattr(data, "work_org", ""))
        position = self._clean_popup_position(getattr(data, "position", ""))
        return org, position

    def _set_shared_work_details_auto(self, org: str, position: str) -> None:
        """Разнести работу/должность без отметки ручной правки врача."""
        org = self._clean_popup_work_org(org)
        position = self._clean_popup_position(position)
        if not org and not position:
            return
        self.expert_work_status_var.set("да")
        self.expert_work_org_var.set(org)
        self.expert_position_var.set(position)
        self.vk_mse_work_org_var.set(org)
        self.vk_mse_position_var.set(position)
        self.sick_leave_vk_work_org_var.set(org)
        self.sick_leave_vk_position_var.set(position)
        self.sick_leave_vk_work_position_var.set(", ".join(part for part in [org, position] if part))

    def _shared_work_defaults(self) -> tuple[str, str]:
        """Единый источник места работы/должности для всех popup-окон.

        При выборе первичного документа работа и должность автоматически
        подтягиваются из него. Если врач затем меняет эти поля в любом popup,
        введённые значения становятся общими для остальных popup текущего
        пациента и уже не перетираются повторным reparse.
        """
        pairs = (
            (self.expert_work_org_var.get().strip(), self.expert_position_var.get().strip()),
            (self.vk_mse_work_org_var.get().strip(), self.vk_mse_position_var.get().strip()),
            (self.sick_leave_vk_work_org_var.get().strip(), self.sick_leave_vk_position_var.get().strip()),
        )
        for org, position in pairs:
            if org or position:
                return org, position
        return "", ""

    def _sync_shared_work_details(self, org: str, position: str) -> None:
        """Разнести введённые врачом место работы/должность во все popup-поля."""
        org = self._clean_popup_work_org(org)
        position = self._clean_popup_position(position)
        if not org and not position:
            return
        self._work_details_manually_edited = True
        self._set_shared_work_details_auto(org, position)

    def _apply_primary_work_defaults(self, data: PatientData) -> None:
        """Автоматически заполнить popup-поля работой из первичного DOCX."""
        org, position = self._primary_work_pair_from_data(data)
        if not org and not position:
            return
        current_org, current_position = self._shared_work_defaults()
        current_is_previous_primary = (
            current_org == self._primary_work_org_default
            and current_position == self._primary_work_position_default
        )
        self._primary_work_org_default = org
        self._primary_work_position_default = position
        if self._work_details_manually_edited and not current_is_previous_primary:
            return
        if (not current_org and not current_position) or current_is_previous_primary:
            self._set_shared_work_details_auto(org, position)

    def _expert_defaults_from_primary(self) -> tuple[str, str, str, str, str]:
        """Вернуть дефолты popup: работает, организация, должность, нужен ЛН, дата ЛН.

        Работу и должность берём из общих popup-полей. Эти поля при выборе
        первичного документа автоматически заполняются распознанными из DOCX
        значениями, а ручная правка врача имеет приоритет.
        """
        data = self.data
        navigation = self.navigation_path_var.get().strip()
        if navigation and Path(navigation).exists():
            try:
                data = self._parse_primary_document(navigation)
            except Exception:
                pass

        work_org, position = self._shared_work_defaults()
        if not work_org and not position:
            work_org, position = self._primary_work_pair_from_data(data)
        work_status = self._normalize_yes_no(self.expert_work_status_var.get())
        if not work_status:
            work_status = "да" if work_org or position else ""

        sick_needed = self._normalize_yes_no(self.expert_sick_leave_needed_var.get())
        if not sick_needed and data.sick_leave.strip():
            low = data.sick_leave.lower().replace("ё", "е")
            if "не нуж" in low or "нет" == low.strip():
                sick_needed = "нет"
            elif "нуж" in low or "лн" in low or "больнич" in low:
                sick_needed = "да"

        return (
            "да" if work_status == "да" else ("нет" if work_status == "нет" else ""),
            work_org,
            position,
            "да" if sick_needed == "да" else ("нет" if sick_needed == "нет" else ""),
            self.expert_sick_leave_from_var.get().strip(),
        )

    def _expert_details_are_complete(self) -> bool:
        """Проверить заполненность блока больничного листа.

        Если в модуле 01 стоит «нет», popup не нужен: экспертный анамнез
        будет сформирован с фразой о том, что ЛН не требуется.
        Если выбрано «да», требуются только дата начала, организация и должность.
        """
        sick_needed = self._normalize_yes_no(self.expert_sick_leave_needed_var.get())
        if sick_needed == "нет":
            return True
        if sick_needed != "да":
            return False
        if not self.expert_sick_leave_from_var.get().strip():
            return False
        if not self.expert_work_org_var.get().strip():
            return False
        if not self.expert_position_var.get().strip():
            return False
        return True

    def _prompt_expert_anamnesis_details(self, *, force: bool = False) -> bool:
        """Popup для больничного листа.

        Открывается только когда в модуле 01 выбран ответ «да».
        Внутри нет дублирующих переключателей «работает да/нет» и
        «нужен больничный да/нет»: сам факт открытия означает, что ЛН нужен,
        а организация и должность обязательны для экспертного анамнеза.
        """
        if self._expert_details_are_complete() and not force:
            return True

        _default_work_status, default_org, default_position, _default_sick, default_from = self._expert_defaults_from_primary()
        win = tk.Toplevel(self.root)
        win.title("Экспертный анамнез")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        result: bool | None = None
        body = tk.Frame(win, bg=PANEL, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Больничный лист", bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        hint = "Укажите номер истории болезни, дату начала больничного, организацию и должность."
        tk.Label(body, text=hint, bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=440, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        rows = [
            ("Номер истории болезни", self._case_number_popup_default()),
            ("С какого числа больничный", self.expert_sick_leave_from_var.get().strip() or default_from),
            ("Где работает / организация", self.expert_work_org_var.get().strip() or default_org),
            ("Должность", self.expert_position_var.get().strip() or default_position),
        ]
        vars_: list[tk.StringVar] = []
        entries: list[tk.Entry] = []
        for idx, (label, initial) in enumerate(rows, start=2):
            tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 8)).grid(row=idx, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=initial)
            entry = tk.Entry(
                body, textvariable=var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                width=56, font=("Segoe UI", 8), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1,
            )
            entry.grid(row=idx, column=1, sticky="ew", padx=(12, 0), ipady=6, pady=6)
            entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
            vars_.append(var)
            entries.append(entry)
        body.grid_columnconfigure(1, weight=1)

        error_label = tk.Label(body, text="", bg=PANEL, fg=ERROR, font=("Segoe UI", 8), wraplength=440, justify="left")
        error_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        buttons.grid_columnconfigure(0, weight=1)

        def ok() -> None:
            nonlocal result
            case_number = vars_[0].get().strip()
            sick_from = vars_[1].get().strip()
            org = vars_[2].get().strip()
            position = vars_[3].get().strip()
            problems: list[str] = []
            if not case_number:
                problems.append("укажите номер истории болезни")
            if not sick_from:
                problems.append("укажите дату начала больничного")
            elif not parse_date(sick_from):
                problems.append("дата больничного должна быть в формате ДД.ММ.ГГГГ или ДД.ММ.ГГ")
            if not org:
                problems.append("укажите организацию")
            if not position:
                problems.append("укажите должность")
            if problems:
                error_label.config(text="; ".join(problems) + ".")
                return
            if not self._store_case_number_value(case_number):
                error_label.config(text="укажите номер истории болезни.")
                return
            self._sync_shared_work_details(org, position)
            self.expert_sick_leave_needed_var.set("да")
            sick_from = self._normalize_date_for_ui(sick_from)
            self.expert_sick_leave_from_var.set(sick_from)
            self._update_expert_sick_leave_display()
            result = True
            win.destroy()

        def cancel() -> None:
            nonlocal result
            result = False
            win.destroy()

        tk.Button(buttons, text="ОК", command=ok, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 8))
        tk.Button(buttons, text="Отмена", command=cancel, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=("Segoe UI", 8)).grid(row=0, column=1, sticky="e")
        entries[0].focus_set()
        win.bind("<Return>", lambda _event: ok())
        win.bind("<Escape>", lambda _event: cancel())
        self.root.wait_window(win)
        return bool(result)

    def _should_prompt_discharge_sick_leave_number(self) -> bool:
        """True только для строгого условия popup номера ЛН.

        Номер ЛН относится только к документу «Выписной эпикриз».
        Номер больничного относится только к выписному эпикризу. Поэтому
        popup нельзя открывать при обычном выборе «Больничный лист: да» в
        модуле 01: он допустим только когда уже выбран документ
        «Выписной эпикриз» и сам больничный лист отмечен как нужный.
        """
        discharge_var = self.output_vars.get("discharge") if hasattr(self, "output_vars") else None
        discharge_selected = bool(discharge_var and discharge_var.get())
        sick_selected = self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) == "да"
        number_missing = not self.expert_sick_leave_number_var.get().strip()
        return discharge_selected and sick_selected and number_missing

    def _ensure_discharge_sick_leave_number(self, *, prompt_if_needed: bool = True) -> bool:
        """Убедиться, что номер больничного указан только для выписного эпикриза."""
        if not self._should_prompt_discharge_sick_leave_number():
            return True
        return self._prompt_discharge_sick_leave_number() if prompt_if_needed else False

    def _prompt_discharge_sick_leave_number(self) -> bool:
        """Запросить номер больничного листа для выписного эпикриза."""
        values = self._prompt_fields(
            title="Больничный лист для выписного эпикриза",
            rows=[("Номер больничного листа", self.expert_sick_leave_number_var.get().strip())],
            width=52,
        )
        if values is None:
            return False
        number = values[0].strip()
        if not number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер больничного листа.")
            return False
        self.expert_sick_leave_number_var.set(number)
        self._update_expert_sick_leave_display()
        return True

    def _selected_outputs_require_discharge_date(self) -> bool:
        """Дата выписки нужна для эпикриза, дневников и Акта РВК."""
        if not hasattr(self, "output_vars"):
            return False
        required_kinds = ("discharge", DIARY_KIND, "rvk")
        for kind in required_kinds:
            var = self.output_vars.get(kind)
            if var is not None and bool(var.get()):
                return True
        return False

    def _current_discharge_date_value(self) -> str:
        return ((getattr(self, "_popup_discharge_date_override", "") or "").strip()
                or self.discharge_date_var.get().strip())

    def _discharge_date_missing_or_invalid(self) -> bool:
        value = self._current_discharge_date_value()
        return not value or parse_date(value) is None

    def _store_discharge_date_value(self, value: str) -> bool:
        value = (value or "").strip()
        if not value or not parse_date(value):
            return False
        normalized = self._normalize_date_for_ui(value)
        if not self._date_is_not_before_admission(normalized):
            return False
        self._popup_discharge_date_override = normalized
        self._set_ui_var(self.discharge_date_var, normalized)
        self._manual_discharge_date = True
        if hasattr(self, "data"):
            self.data.discharge_date = normalized
        return True

    def _should_prompt_discharge_date(self) -> bool:
        """True, если для выбранных документов ещё нет даты выписки.

        Дата выписки обязательна не только для «Выписного эпикриза», но и
        для «Дневников наблюдения» и «Акта для РВК»: она задаёт финальную
        дату заполнения дневников и используется в соответствующих документах.
        """
        return self._selected_outputs_require_discharge_date() and self._discharge_date_missing_or_invalid()

    def _ensure_discharge_date(self, *, prompt_if_needed: bool = True) -> bool:
        """Убедиться, что общая дата выписки указана и нормализована.

        она подставляется в выписной эпикриз и задаёт конечную дату
        дневников/Акта РВК.
        """
        if not self._selected_outputs_require_discharge_date():
            return True
        current = self._current_discharge_date_value()
        if current and self._store_discharge_date_value(current):
            return True
        return self._prompt_discharge_date() if prompt_if_needed else False

    def _prompt_discharge_date(self) -> bool:
        """Запросить дату выписки для эпикриза, дневников или Акта РВК."""
        values = self._prompt_fields(
            title="Дата выписки",
            rows=[("Дата выписки", self._discharge_popup_default())],
            width=36,
        )
        if values is None:
            return False
        discharge_value = values[0].strip()
        if not self._store_discharge_date_value(discharge_value):
            messagebox.showwarning(
                "Некорректная дата выписки",
                "Укажите дату выписки не раньше даты поступления в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
            )
            return False
        return True

    def _hospitalization_details_missing(self) -> bool:
        """True, если для направления нужны недостающие реквизиты."""
        primary_type_var = getattr(self, "primary_document_type_var", None)
        if primary_type_var is None or primary_type_var.get() != "hospitalization_referral":
            return False
        data = getattr(self, "data", None)
        diagnosis = self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(data, "diagnosis", ""))
        return not (
            self.case_number_var.get().strip()
            and self.assigned_treatment_var.get().strip()
            and diagnosis
        )

    def _manual_treatment_missing(self) -> bool:
        """True, если нужно ручное поле «Лечение» из-за отсутствия раздела в первичном DOCX."""
        try:
            return bool(self._primary_treatment_missing_for_medical_docs())
        except Exception:
            return False

    def _prompt_common_output_requirements(self, *, include_discharge_date: bool, include_case_number: bool = True, include_medical_details: bool = True) -> bool:
        """Единый popup для общих недостающих полей выбора документов.

        Используется для сценариев без специальных merged-popup документов
        («Выписной эпикриз» и «Акт РВК»). Так лечение/реквизиты направления
        и дата выписки для дневников не открываются двумя окнами подряд.
        Номер истории болезни и лечение показываются только для медицинских
        документов блока 03 и переиспользуются всеми следующими popup-окнами.
        Если выбран только документ «Дневники наблюдения», здесь запрашивается
        только «Дата выписки».
        """
        detail_rows: list[tuple[str, str]] = []
        detail_fields: list[str] = []

        if include_medical_details:
            if self._hospitalization_details_missing():
                detail_rows.append(("Лечение", self._treatment_popup_default()))
                detail_fields.append("treatment")
                detail_rows.append(("Диагноз", self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(getattr(self, "data", None), "diagnosis", ""))))
                detail_fields.append("diagnosis")
            elif self._manual_treatment_missing():
                detail_rows.append(("Лечение", self.assigned_treatment_var.get().strip() or self._treatment_popup_default()))
                detail_fields.append("treatment")

        if include_discharge_date and self._selected_outputs_require_discharge_date() and self._discharge_date_missing_or_invalid():
            detail_rows.append(("Дата выписки", self._discharge_popup_default()))
            detail_fields.append("discharge_date")

        rows: list[tuple[str, str]] = []
        fields: list[str] = []
        if include_case_number and self._case_number_missing():
            rows.append(("Номер истории болезни", self._case_number_popup_default()))
            fields.append("case_number")
        rows.extend(detail_rows)
        fields.extend(detail_fields)

        if not rows:
            return True

        values = self._prompt_fields(
            title="Данные для выбранных документов",
            rows=rows,
            width=72,
        )
        if values is None:
            return False

        for field, raw_value in zip(fields, values):
            value = raw_value.strip()
            if field == "case_number":
                if not self._store_case_number_value(value):
                    messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
                    return False
            elif field == "treatment":
                if not value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.")
                    return False
                self.assigned_treatment_var.set(value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = value
            elif field == "diagnosis":
                diagnosis = sanitize_diagnosis(self._normalize_popup_diagnosis_value(value))
                if not diagnosis:
                    messagebox.showwarning("Не заполнено поле", "Укажите диагноз.")
                    return False
                self.diagnosis_var.set(diagnosis)
                self._popup_diagnosis_override = diagnosis
                self._manual_diagnosis = True
                if hasattr(self, "data"):
                    self.data.diagnosis = diagnosis
            elif field == "discharge_date":
                if not self._store_discharge_date_value(value):
                    messagebox.showwarning(
                        "Некорректная дата выписки",
                        "Дата выписки должна быть корректной, не раньше даты поступления и в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
                    )
                    return False
        return True

    def _prompt_discharge_output_requirements(self) -> bool:
        """Единый popup для «Выписного эпикриза».

        Раньше могли открываться два окна подряд: одно с реквизитами
        направления/лечения, затем отдельное с датой выписки или номером ЛН.
        Теперь все недостающие вопросы для эпикриза собираются в одно окно,
        включая общий номер истории болезни.
        """
        detail_rows: list[tuple[str, str]] = []
        detail_fields: list[str] = []

        if self._hospitalization_details_missing():
            detail_rows.append(("Лечение", self._treatment_popup_default()))
            detail_fields.append("treatment")
            detail_rows.append(("Диагноз", self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(getattr(self, "data", None), "diagnosis", ""))))
            detail_fields.append("diagnosis")
        elif self._manual_treatment_missing():
            detail_rows.append(("Лечение", self.assigned_treatment_var.get().strip() or self._treatment_popup_default()))
            detail_fields.append("treatment")

        if self._selected_outputs_require_discharge_date() and self._discharge_date_missing_or_invalid():
            detail_rows.append(("Дата выписки", self._discharge_popup_default()))
            detail_fields.append("discharge_date")

        if self._should_prompt_discharge_sick_leave_number():
            detail_rows.append(("Номер больничного листа", self.expert_sick_leave_number_var.get().strip()))
            detail_fields.append("sick_leave_number")

        rows: list[tuple[str, str]] = []
        fields: list[str] = []
        if self._case_number_missing():
            rows.append(("Номер истории болезни", self._case_number_popup_default()))
            fields.append("case_number")
        rows.extend(detail_rows)
        fields.extend(detail_fields)

        if not rows:
            return True

        values = self._prompt_fields(
            title="Данные для выписного эпикриза",
            rows=rows,
            width=72,
        )
        if values is None:
            return False

        for field, raw_value in zip(fields, values):
            value = raw_value.strip()
            if field == "case_number":
                if not self._store_case_number_value(value):
                    messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
                    return False
            elif field == "treatment":
                if not value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.")
                    return False
                self.assigned_treatment_var.set(value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = value
            elif field == "diagnosis":
                diagnosis = sanitize_diagnosis(self._normalize_popup_diagnosis_value(value))
                if not diagnosis:
                    messagebox.showwarning("Не заполнено поле", "Укажите диагноз.")
                    return False
                self.diagnosis_var.set(diagnosis)
                self._popup_diagnosis_override = diagnosis
                self._manual_diagnosis = True
                if hasattr(self, "data"):
                    self.data.diagnosis = diagnosis
            elif field == "discharge_date":
                if not self._store_discharge_date_value(value):
                    messagebox.showwarning(
                        "Некорректная дата выписки",
                        "Дата выписки должна быть корректной, не раньше даты поступления и в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
                    )
                    return False
            elif field == "sick_leave_number":
                if not value:
                    messagebox.showwarning("Не заполнено поле", "Укажите номер больничного листа.")
                    return False
                self.expert_sick_leave_number_var.set(value)
                self._update_expert_sick_leave_display()
        return True

    def _selected_docs_need_expert_anamnesis(self, selected_medical: List[str]) -> bool:
        return any(kind in selected_medical for kind in ("primary", "discharge", "commission"))

    def _prompt_assigned_treatment_if_needed(self, *, force: bool = False) -> bool:
        """Запросить поля, зависящие от типа первичного документа.

        При «Первичном осмотре» общий treatment-popup открывается только если
        в исходном DOCX нет явной строки лечения. При «Направлении на
        госпитализацию» спрашиваем номер истории болезни, лечение и диагноз;
        дату выписки добавляем в то же окно только для документов, которым она
        действительно нужна: выписной эпикриз, дневники или Акт РВК.
        """
        if self.primary_document_type_var.get() == "primary_exam":
            return self._prompt_primary_exam_details_if_needed(force=force)

        default_treatment = self._treatment_popup_default()
        default_case_number = self._case_number_popup_default()
        if default_treatment and not self.assigned_treatment_var.get().strip():
            self.assigned_treatment_var.set(default_treatment)
        if default_case_number and not self.case_number_var.get().strip():
            self.case_number_var.set(default_case_number)

        diagnosis_value = self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(getattr(self, "data", None), "diagnosis", ""))
        discharge_required = self._selected_outputs_require_discharge_date()
        discharge_ready = (not discharge_required) or (not self._discharge_date_missing_or_invalid())
        if (
            self.assigned_treatment_var.get().strip()
            and self.case_number_var.get().strip()
            and diagnosis_value
            and discharge_ready
            and not force
        ):
            return True

        rows: list[tuple[str, str]] = [
            ("Номер истории болезни", self._case_number_popup_default()),
            ("Лечение", self._treatment_popup_default()),
            ("Диагноз", diagnosis_value),
        ]
        fields = ["case_number", "treatment", "diagnosis"]
        if discharge_required:
            rows.append(("Дата выписки", self._discharge_popup_default()))
            fields.append("discharge_date")

        values = self._prompt_fields(
            title="Данные направления на госпитализацию",
            rows=rows,
            width=72,
        )
        if values is None:
            return False

        for field, raw_value in zip(fields, values):
            value = raw_value.strip()
            if field == "case_number":
                if not self._store_case_number_value(value):
                    messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
                    return False
            elif field == "treatment":
                if not value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.")
                    return False
                self.assigned_treatment_var.set(value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = value
            elif field == "diagnosis":
                popup_diagnosis = sanitize_diagnosis(self._normalize_popup_diagnosis_value(value))
                if not popup_diagnosis:
                    messagebox.showwarning("Не заполнено поле", "Укажите диагноз.")
                    return False
                self.diagnosis_var.set(popup_diagnosis)
                # Врач мог выбрать в popup другой диагноз, чем был в исходном документе.
                # Такой диагноз должен идти во все создаваемые документы и не должен
                # перетираться последующим reparse_navigation().
                self._popup_diagnosis_override = popup_diagnosis
                self._manual_diagnosis = True
                if hasattr(self, "data"):
                    self.data.diagnosis = popup_diagnosis
            elif field == "discharge_date":
                if not self._store_discharge_date_value(value):
                    messagebox.showwarning(
                        "Некорректная дата выписки",
                        "Дата выписки должна быть корректной, не раньше даты поступления и в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
                    )
                    return False

        missing: list[str] = []
        if not self.case_number_var.get().strip():
            missing.append("номер истории болезни")
        if not self.assigned_treatment_var.get().strip():
            missing.append("лечение")
        if not self.diagnosis_var.get().strip():
            missing.append("диагноз")
        if discharge_required and self._discharge_date_missing_or_invalid():
            missing.append("дату выписки")
        if missing:
            messagebox.showwarning(
                "Не заполнены поля",
                "Заполните: " + ", ".join(missing) + ".",
            )
            return False

        status_text = "Номер истории болезни, лечение и диагноз сохранены."
        if discharge_required:
            status_text = "Номер истории болезни, лечение, диагноз и дата выписки сохранены."
        self.status_label.config(text=status_text)
        return True

    def _normalize_popup_diagnosis_value(self, value: str) -> str:
        """Развернуть краткий ввод МКБ в полную строку диагноза.

        В popup направления врач может ввести только цифры шифра, например
        ``41.2`` или ``412``. При подтверждении это превращается в
        ``F41.2 ...``. Если введён свободный текст, он сохраняется как есть.
        """
        raw = (value or "").strip()
        if not raw:
            return ""
        code_like = bool(re.fullmatch(r"[Ff]?\s*\d{1,2}(?:\s*[.,]\s*\d{1,2})?", raw))
        digits_like = bool(re.fullmatch(r"\d{2,4}", raw))
        if code_like or digits_like:
            matches = _search_icd10_f(raw, limit=1)
            if matches:
                return _format_diagnosis(matches[0])
        return raw
