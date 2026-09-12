from __future__ import annotations

from datetime import datetime
from tkinter import messagebox

from app_config import *
from medical_constants import DATE_FMT
from medical_formatting import parse_date


class DialogDatesMixin:
    def _today_str(self) -> str:
        return datetime.now().strftime(DATE_FMT)

    def _normalize_date_for_ui(self, value: str) -> str:
        parsed = parse_date(value)
        return parsed.strftime(DATE_FMT) if parsed else (value or "").strip()

    @staticmethod
    def _is_date_input_label(label: str) -> bool:
        """Return True for UI fields that accept a full calendar date."""
        low = (label or "").strip().lower().replace("ё", "е")
        return "дата" in low or "с какого числа" in low

    @staticmethod
    def _compact_date_can_continue(digits: str) -> bool:
        """Return True when more digits can still form a supported compact date."""
        if not digits.isdigit() or len(digits) >= 8:
            return False
        remaining = 8 - len(digits)
        # We only call this for six/seven digit input, so at most 110 cheap
        # parser probes are needed. This preserves legacy 7-digit forms such as
        # 1012026 instead of prematurely turning their six-digit prefix into
        # an unrelated DD.MM.YY value.
        for extra_len in range(1, remaining + 1):
            for suffix in range(10 ** extra_len):
                candidate = digits + f"{suffix:0{extra_len}d}"
                if parse_date(candidate):
                    return True
        return False

    @staticmethod
    def _format_date_input_live(value: str) -> str:
        """Insert separators only when compact input is safe to finalize live.

        The parser intentionally supports 4/5/6/7/8-digit compact dates. A
        six-digit value can therefore be the prefix of a valid seven/eight
        digit date. We mask only completed, unambiguous input and leave partial
        legacy forms untouched until Enter/focus loss/OK normalization.
        """
        raw = (value or "").strip()
        if not raw or not raw.isdigit():
            return raw
        if len(raw) not in {6, 7, 8}:
            return raw
        parsed = parse_date(raw)
        if not parsed:
            return raw
        if len(raw) < 8 and DialogDatesMixin._compact_date_can_continue(raw):
            return raw
        if len(raw) == 6:
            return parsed.strftime("%d.%m.%y")
        return parsed.strftime(DATE_FMT)

    def _normalize_date_entry_var(self, variable) -> str:
        """Normalize a date entry after typing without forcing separators.

        The doctor may type ``090926`` (or ``09092026``); on Enter/focus loss
        the visible field becomes ``09.09.2026``. Invalid/partial input is left
        unchanged so creation-time validation can explain the error.
        """
        raw = variable.get().strip() if variable is not None else ""
        if not raw:
            return ""
        normalized = self._normalize_date_for_ui(raw)
        if normalized != raw:
            try:
                self._set_ui_var(variable, normalized)
            except Exception:
                variable.set(normalized)
        return normalized

    def _bind_date_entry_normalization(self, entry, variable, label: str) -> None:
        """Attach live compact-date masking and final normalization."""
        if not self._is_date_input_label(label):
            return

        def live_mask(event=None) -> None:
            # Navigation/modifier keys must never rewrite the field.
            if getattr(event, "keysym", "") in {
                "Left", "Right", "Up", "Down", "Home", "End", "Tab",
                "Shift_L", "Shift_R", "Control_L", "Control_R",
                "Alt_L", "Alt_R", "Escape", "Return",
            }:
                return
            raw = variable.get() if variable is not None else ""
            masked = self._format_date_input_live(raw)
            if masked == raw:
                return
            try:
                self._set_ui_var(variable, masked)
            except Exception:
                variable.set(masked)
            try:
                entry.icursor("end")
            except Exception:
                pass

        entry.bind("<KeyRelease>", live_mask, add="+")
        entry.bind("<FocusOut>", lambda _event: self._normalize_date_entry_var(variable), add="+")
        entry.bind("<Return>", lambda _event: self._normalize_date_entry_var(variable), add="+")

    def _normalize_required_date_for_ui(self, value: str, label: str) -> str | None:
        """Normalize a required user-entered date or warn and reject it.

        Several popup contracts store dates that later go directly into DOCX
        headers. A non-empty but invalid value must not pass as plain text.
        """
        raw = (value or "").strip()
        parsed = parse_date(raw)
        if not parsed:
            messagebox.showwarning(
                "Некорректная дата",
                f"{label} должна быть в формате ДД.ММ.ГГГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.",
            )
            return None
        normalized = parsed.strftime(DATE_FMT)
        if not self._date_is_not_before_admission(normalized):
            messagebox.showwarning(
                "Некорректная дата",
                f"{label} не может быть раньше даты поступления.",
            )
            return None
        return normalized

    def _admission_date_for_validation(self) -> str:
        data = getattr(self, "data", None)
        data_value = getattr(data, "admission_date", "") if data is not None else ""
        ui_var = getattr(self, "admission_date_var", None)
        ui_value = ui_var.get().strip() if ui_var is not None else ""
        return (data_value or ui_value or "").strip()

    def _date_is_not_before_admission(self, value: str) -> bool:
        admission_value = self._admission_date_for_validation()
        if not admission_value or not value:
            return True
        admission = parse_date(admission_value)
        parsed = parse_date(value)
        if not admission or not parsed:
            return True
        return parsed.date() >= admission.date()

    def _on_discharge_date_field_commit(self, _event=None) -> None:
        """Commit manual «Дата выписки» input as the global discharge date.

        A manually typed value such as ``1126`` is normalized to ``01.01.2026``
        on focus loss/Enter and then reused by both the discharge epicrisis and
        diary termination logic. Invalid partial input is left untouched until
        creation-time validation.
        """
        value = self.discharge_date_var.get().strip() if hasattr(self, "discharge_date_var") else ""
        if not value:
            self._popup_discharge_date_override = ""
            if hasattr(self, "data"):
                self.data.discharge_date = ""
            return None
        parsed = parse_date(value)
        if not parsed:
            return None
        normalized = parsed.strftime(DATE_FMT)
        if not self._date_is_not_before_admission(normalized):
            return None
        if self.discharge_date_var.get().strip() != normalized:
            self._set_ui_var(self.discharge_date_var, normalized)
        self._popup_discharge_date_override = normalized
        self._manual_discharge_date = True
        if hasattr(self, "data"):
            self.data.discharge_date = normalized
        return None

    def _default_committee_date(self) -> str:
        """Новая комиссия не получает календарную дату автоматически."""
        return ""

    def _default_protocol_date(self, fallback: str | None = None) -> str:
        """Дата протокола наследует только введённую врачом дату этого popup."""
        return (fallback or "").strip()

    def _remember_committee_dates(self, *, committee_date: str | None = None, protocol_date: str | None = None) -> None:
        """Ничего не запоминаем между разными popup-окнами.

        Раньше дата, введённая в одном окне, подставлялась в другие окна
        комиссии/ВК. Это давало неверные документы, когда, например,
        совместный осмотр был 11.05.2026, а РВК/ВК — 12.05.2026.
        """
        return None
