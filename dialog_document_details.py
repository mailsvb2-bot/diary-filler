from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from app_config import *
from medical_parser_sanitize import sanitize_diagnosis


class DialogDocumentDetailsMixin:
    def _prompt_commission_details(self) -> bool:
        date_default = self.commission_date_var.get().strip() or self._today_str()
        values = self._prompt_fields(
            title="Совместный осмотр",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения комиссии", date_default),
                ("Номер", self.commission_number_var.get().strip()),
            ],
            linked_groups=[],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        commission_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата комиссии")
        if commission_date is None:
            return False
        commission_number = values[2].strip()
        if not commission_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер совместного осмотра.")
            return False
        self.commission_date_var.set(commission_date)
        self.commission_number_var.set(commission_number)
        self._remember_committee_dates(committee_date=commission_date)
        return True

    def _prompt_rvk_details(self) -> bool:
        """Единый popup Акта РВК.

        В этом окне собираются все вопросы, которые иначе могли бы
        открываться отдельными popup подряд: реквизиты направления/лечения,
        дата выписки, номер медицинского заключения и военкомат.
        """
        win = tk.Toplevel(self.root)
        win.title("Акт РВК")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        result = {"ok": False}
        case_var = tk.StringVar(value=self._case_number_popup_default())
        treatment_var = tk.StringVar(value=self.assigned_treatment_var.get().strip() or self._treatment_popup_default())
        diagnosis_var = tk.StringVar(value=self.diagnosis_var.get().strip() or sanitize_diagnosis(getattr(getattr(self, "data", None), "diagnosis", "")))
        discharge_var = tk.StringVar(value=self._discharge_popup_default())
        act_var = tk.StringVar(value=self.rvk_act_number_var.get().strip())
        military_var = tk.StringVar(value=self.rvk_military_commissariat_var.get().strip())

        need_hospitalization_details = self._hospitalization_details_missing()
        need_manual_treatment = (not need_hospitalization_details) and self._manual_treatment_missing()
        need_discharge_date = self._selected_outputs_require_discharge_date() and self._discharge_date_missing_or_invalid()

        frame = tk.Frame(win, bg=PANEL, padx=18, pady=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        row = 0
        entries: list[tk.Entry] = []

        def add_entry(label_text: str, var: tk.StringVar, *, width: int = 44) -> tk.Entry:
            nonlocal row
            tk.Label(frame, text=label_text, bg=PANEL, fg=TEXT, font=self._font(10), anchor="w").grid(
                row=row, column=0, sticky="w", pady=(0, 4)
            )
            entry = tk.Entry(frame, textvariable=var, width=width, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat")
            entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 10))
            row += 2
            entries.append(entry)
            return entry

        add_entry("Номер истории болезни", case_var)
        if need_hospitalization_details:
            add_entry("Лечение", treatment_var, width=64)
            add_entry("Диагноз", diagnosis_var, width=64)
        elif need_manual_treatment:
            add_entry("Лечение", treatment_var, width=64)

        if need_discharge_date:
            add_entry("Дата выписки", discharge_var, width=28)

        number_entry = add_entry("Номер медицинского заключения", act_var, width=36)

        tk.Label(frame, text="Военкомат", bg=PANEL, fg=TEXT, font=self._font(10), anchor="w").grid(
            row=row, column=0, sticky="w", pady=(0, 6)
        )
        row += 1
        options_frame = tk.Frame(frame, bg=PANEL)
        options_frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        row += 1
        for idx, value in enumerate(("Ленинский", "Канавинский", "Сормовский и Московский")):
            options_frame.grid_columnconfigure(idx, weight=1)
            btn = tk.Button(
                options_frame,
                text=value,
                command=lambda v=value: military_var.set(v),
                bg=FIELD,
                fg=TEXT,
                activebackground=ACCENT,
                activeforeground="#03101f",
                relief="flat",
                padx=8,
                pady=6,
                cursor="hand2",
            )
            btn.grid(row=0, column=idx, sticky="ew", padx=(0 if idx == 0 else 6, 0))

        selected_label = tk.Label(frame, textvariable=military_var, bg=PANEL, fg=ACCENT, font=self._font(10), anchor="w")
        selected_label.grid(row=row, column=0, sticky="w", pady=(0, 12))
        row += 1

        buttons = tk.Frame(frame, bg=PANEL)
        buttons.grid(row=row, column=0, sticky="e")

        def ok() -> None:
            case_value = case_var.get().strip()
            if not self._store_case_number_value(case_value):
                messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.", parent=win)
                return
            if need_hospitalization_details:
                treatment_value = treatment_var.get().strip()
                diagnosis_value = sanitize_diagnosis(self._normalize_popup_diagnosis_value(diagnosis_var.get().strip()))
                if not treatment_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.", parent=win)
                    return
                if not diagnosis_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите диагноз.", parent=win)
                    return
                self.assigned_treatment_var.set(treatment_value)
                self.diagnosis_var.set(diagnosis_value)
                self._popup_diagnosis_override = diagnosis_value
                self._manual_diagnosis = True
                if hasattr(self, "data"):
                    self.data.treatment_plan = treatment_value
                    self.data.diagnosis = diagnosis_value
            elif need_manual_treatment:
                treatment_value = treatment_var.get().strip()
                if not treatment_value:
                    messagebox.showwarning("Не заполнено поле", "Укажите лечение.", parent=win)
                    return
                self.assigned_treatment_var.set(treatment_value)
                if hasattr(self, "data"):
                    self.data.treatment_plan = treatment_value

            if need_discharge_date and not self._store_discharge_date_value(discharge_var.get().strip()):
                messagebox.showwarning(
                    "Некорректная дата выписки",
                    "Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ, например 20.04.2026, 200426 или 1126.",
                    parent=win,
                )
                return

            if not act_var.get().strip():
                messagebox.showwarning("Не заполнено поле", "Укажите номер медицинского заключения.", parent=win)
                return
            if not military_var.get().strip():
                messagebox.showwarning("Не выбран военкомат", "Выберите военкомат кнопкой.", parent=win)
                return
            self.rvk_act_number_var.set(act_var.get().strip())
            self.rvk_military_commissariat_var.set(military_var.get().strip())
            # В акте военкомата больше нет ручного запроса места работы/должности.
            # Саму строку «Место работы» medical_documents.py удаляет из итогового Акта РВК.
            self.rvk_work_position_var.set("")
            result["ok"] = True
            win.destroy()

        def cancel() -> None:
            win.destroy()

        tk.Button(buttons, text="OK", command=ok, bg=ACCENT, fg="#03101f", relief="flat", padx=16, pady=6).grid(row=0, column=0, padx=(0, 8))
        tk.Button(buttons, text="Отмена", command=cancel, bg=FIELD, fg=TEXT, relief="flat", padx=14, pady=6).grid(row=0, column=1)
        win.bind("<Return>", lambda _event: ok())
        win.bind("<Escape>", lambda _event: cancel())
        (entries[0] if entries else number_entry).focus_set()
        win.update_idletasks()
        self.root.wait_window(win)
        return bool(result["ok"])

    def _prompt_vk_mse_details(self) -> bool:
        date_default = self.vk_date_var.get().strip() or self._today_str()
        protocol_date_default = self.vk_protocol_date_var.get().strip() or date_default
        shared_org, shared_position = self._shared_work_defaults()
        values = self._prompt_fields(
            title="ВК на МСЭ",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения ВК / дата проведения комиссии", date_default),
                ("Протокол номер", self.vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Место работы", self.vk_mse_work_org_var.get().strip() or shared_org),
                ("Должность", self.vk_mse_position_var.get().strip() or shared_position),
            ],
            width=64,
            # Если врач меняет первую дату, поле «От / дата протокола»
            # автоматически получает ту же дату, пока врач сам его не изменил.
            linked_groups=[(1, [3])],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        vk_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата ВК")
        vk_protocol_date = self._normalize_required_date_for_ui(values[3].strip(), "Дата протокола ВК")
        if vk_date is None or vk_protocol_date is None:
            return False
        protocol_number = values[2].strip()
        work_org = values[4].strip()
        position = values[5].strip()
        if not protocol_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер протокола ВК.")
            return False
        if not work_org:
            messagebox.showwarning("Не заполнено поле", "Укажите место работы.")
            return False
        self.vk_date_var.set(vk_date)
        self.vk_protocol_number_var.set(protocol_number)
        self.vk_protocol_date_var.set(vk_protocol_date)
        self._sync_shared_work_details(work_org, position)
        self._remember_committee_dates(committee_date=vk_date, protocol_date=vk_protocol_date)
        return True

    def _prompt_sick_leave_vk_details(self) -> bool:
        date_default = self.sick_leave_vk_date_var.get().strip() or self._today_str()
        protocol_date_default = self.sick_leave_vk_protocol_date_var.get().strip() or date_default
        commission_date_default = self.sick_leave_vk_commission_date_var.get().strip() or date_default
        shared_org, shared_position = self._shared_work_defaults()
        values = self._prompt_fields(
            title="ВК больничный",
            rows=[
                ("Номер истории болезни", self._case_number_popup_default()),
                ("Дата / дата проведения ВК", date_default),
                ("Номер протокола", self.sick_leave_vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Дата проведения комиссии", commission_date_default),
                ("Место работы", self.sick_leave_vk_work_org_var.get().strip() or shared_org),
                ("Должность", self.sick_leave_vk_position_var.get().strip() or shared_position),
            ],
            width=64,
            # Первая дата автоматически дублируется в «От» и в
            # «Дата проведения комиссии», но оба поля можно изменить вручную.
            linked_groups=[(1, [3, 4])],
        )
        if values is None:
            return False
        if not self._store_case_number_value(values[0].strip()):
            messagebox.showwarning("Не заполнено поле", "Укажите номер истории болезни.")
            return False
        sick_vk_date = self._normalize_required_date_for_ui(values[1].strip(), "Дата ВК больничного")
        sick_vk_protocol_date = self._normalize_required_date_for_ui(values[3].strip(), "Дата протокола ВК больничного")
        sick_vk_commission_date = self._normalize_required_date_for_ui(values[4].strip(), "Дата проведения комиссии")
        if sick_vk_date is None or sick_vk_protocol_date is None or sick_vk_commission_date is None:
            return False
        protocol_number = values[2].strip()
        work_org = values[5].strip()
        position = values[6].strip()
        if not protocol_number:
            messagebox.showwarning("Не заполнено поле", "Укажите номер протокола ВК больничного.")
            return False
        if not work_org:
            messagebox.showwarning("Не заполнено поле", "Укажите место работы.")
            return False
        self.sick_leave_vk_date_var.set(sick_vk_date)
        self.sick_leave_vk_protocol_number_var.set(protocol_number)
        self.sick_leave_vk_protocol_date_var.set(sick_vk_protocol_date)
        self.sick_leave_vk_commission_date_var.set(sick_vk_commission_date)
        self._sync_shared_work_details(work_org, position)
        self._remember_committee_dates(committee_date=sick_vk_commission_date or sick_vk_date, protocol_date=sick_vk_protocol_date)
        return True

    def _on_primary_document_type_changed(self) -> None:
        """Реакция на выбор типа первичного документа."""
        selected_type = self.primary_document_type_var.get()
        desired_display = "Направление на госпитализацию" if selected_type == "hospitalization_referral" else "Первичный осмотр"
        if hasattr(self, "primary_document_type_display_var") and self.primary_document_type_display_var.get() != desired_display:
            self.primary_document_type_display_var.set(desired_display)
        self.assigned_treatment_var.set("")
        self.case_number_var.set("")
        if self.navigation_path_var.get().strip():
            self.reparse_navigation(silent=True)
            if self.primary_document_type_var.get() == "hospitalization_referral":
                self._prompt_assigned_treatment_if_needed(force=True)
                self.reparse_navigation(silent=True)
            else:
                self._set_status("Тип изменён на первичный осмотр. Popup не требуется.")
        else:
            self.status_label.config(text="Готово")

    def _treatment_popup_default(self) -> str:
        """Текст по умолчанию для popup-окна лечения."""
        if self.assigned_treatment_var.get().strip():
            return self.assigned_treatment_var.get().strip()
        if self.data.treatment_plan.strip():
            return self.data.treatment_plan.strip()
        navigation = self.navigation_path_var.get().strip()
        if navigation and Path(navigation).exists():
            try:
                return self._parse_primary_document(navigation).treatment_plan.strip()
            except Exception:
                return ""
        return ""

    def _case_number_popup_default(self) -> str:
        if self.case_number_var.get().strip():
            return self.case_number_var.get().strip()
        if self.data.case_number.strip():
            return self.data.case_number.strip()
        navigation = self.navigation_path_var.get().strip()
        if navigation and Path(navigation).exists():
            try:
                return self._parse_primary_document(navigation).case_number.strip()
            except Exception:
                return ""
        return ""

    def _store_case_number_value(self, value: str) -> bool:
        """Save shared «номер истории болезни» for all popup windows and renderers."""
        value = (value or "").strip()
        if not value:
            return False
        self.case_number_var.set(value)
        if hasattr(self, "data"):
            self.data.case_number = value
        return True

    def _case_number_missing(self) -> bool:
        return not bool(self._case_number_popup_default())

    def _discharge_popup_default(self) -> str:
        value = self.discharge_date_var.get().strip()
        if value:
            return value
        data = getattr(self, "data", None)
        if data is not None and getattr(data, "discharge_date", "").strip():
            return data.discharge_date.strip()
        return ""

    def _primary_has_treatment_section(self) -> bool:
        """True if the uploaded primary DOCX itself has a treatment row.

        The parser scans the full DOCX text, including tables. We intentionally
        check the explicit section-row flag rather than any random occurrence of
        the word "лечение", so phrases like «за время лечения» do not suppress
        the doctor's popup.
        """
        data = getattr(self, "data", None)
        if data is not None and getattr(data, "has_treatment_section", False):
            return True
        navigation = self.navigation_path_var.get().strip() if hasattr(self, "navigation_path_var") else ""
        if navigation and Path(navigation).exists():
            try:
                parsed = self._parse_primary_document(navigation)
                return bool(getattr(parsed, "has_treatment_section", False))
            except Exception:
                return False
        return False

    def _primary_treatment_missing_for_medical_docs(self) -> bool:
        """Need manual treatment when primary DOCX has no treatment section."""
        if self.assigned_treatment_var.get().strip():
            return False
        navigation = self.navigation_path_var.get().strip() if hasattr(self, "navigation_path_var") else ""
        if not navigation or not Path(navigation).exists():
            return False
        return not self._primary_has_treatment_section()

    def _prompt_missing_primary_treatment_if_needed(self, *, prompt_if_needed: bool = True) -> bool:
        """Ask shared case number and missing «Лечение» for block-03 medical docs.

        Contract: if the uploaded primary document has no explicit row
        «Лечение» / «Назначенное лечение» / «План лечения», every medical
        output tile except «Дневники наблюдения» must request treatment.
        The shared case number is shown in the same popup and then reused by
        all subsequent popups and renderers.
        """
        treatment_missing = self._primary_treatment_missing_for_medical_docs()
        case_missing = self._case_number_missing()
        if not treatment_missing and not case_missing:
            default_treatment = self._treatment_popup_default()
            if default_treatment and not self.assigned_treatment_var.get().strip():
                self.assigned_treatment_var.set(default_treatment)
            return True
        if not prompt_if_needed:
            return False

        rows: list[tuple[str, str]] = []
        fields: list[str] = []
        if case_missing or treatment_missing:
            rows.append(("Номер истории болезни", self._case_number_popup_default()))
            fields.append("case_number")
        if treatment_missing:
            rows.append(("Лечение", self.assigned_treatment_var.get().strip() or self._treatment_popup_default()))
            fields.append("treatment")

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
        return True

    def _prompt_primary_exam_details_if_needed(self, *, force: bool = False) -> bool:
        """For primary exams, ask only for missing treatment when needed.

        If the primary DOCX already has an explicit treatment section, no popup
        is shown. If the section is absent and any medical document is selected,
        the doctor fills exactly one field: «Лечение».
        """
        default_treatment = self._treatment_popup_default()
        default_case_number = self._case_number_popup_default()
        if default_treatment and not self.assigned_treatment_var.get().strip() and self._primary_has_treatment_section():
            self.assigned_treatment_var.set(default_treatment)
        if default_case_number and not self.case_number_var.get().strip():
            self.case_number_var.set(default_case_number)
        return self._prompt_missing_primary_treatment_if_needed(prompt_if_needed=True)
