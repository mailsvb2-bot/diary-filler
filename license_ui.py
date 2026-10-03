"""Small Tk licensing UX for visible MedicalDiaryAutofill sessions."""
from __future__ import annotations

import webbrowser
from tkinter import messagebox, simpledialog

from license_client import (
    LicenseError,
    activate_owner,
    begin_monthly_payment,
    current_status,
    pending_payment_details,
    refresh_paid_order,
    runtime_config,
)


def _format_status(status) -> str:
    if status.active:
        if status.owner_unlimited:
            return "Безлимитный доступ владельца активен."
        if status.valid_until is not None:
            return "Лицензия активна до " + status.valid_until.astimezone().strftime("%d.%m.%Y %H:%M")
        return status.message
    return status.message


def ensure_license(parent, *, interactive: bool = True) -> bool:
    config = runtime_config()
    status = current_status(config)
    if status.active:
        return True
    if not interactive:
        return False

    while True:
        choice = messagebox.askyesnocancel(
            "Лицензия MedicalDiaryAutofill",
            _format_status(status)
            + "\n\n"
            + "Да — оплатить/продлить лицензию на месяц.\n"
            + "Нет — ввести код владельца.\n"
            + "Отмена — закрыть.",
            parent=parent,
        )
        if choice is None:
            return False
        if choice is False:
            code = simpledialog.askstring(
                "Доступ владельца",
                "Введите код владельца:",
                show="•",
                parent=parent,
            )
            if not code:
                continue
            try:
                status = activate_owner(code, config)
            except LicenseError as exc:
                messagebox.showerror("Лицензия", str(exc), parent=parent)
                status = current_status(config)
                continue
            messagebox.showinfo("Лицензия", _format_status(status), parent=parent)
            return True

        pending = pending_payment_details()
        try:
            if pending and pending.get("payment_url"):
                payment = pending
            else:
                payment = begin_monthly_payment(config)
        except LicenseError as exc:
            messagebox.showerror("Лицензия", str(exc), parent=parent)
            status = current_status(config)
            continue

        url = str(payment.get("payment_url") or "")
        amount = int(payment.get("amount_rub") or 0)
        if url:
            try:
                webbrowser.open(url, new=2)
            except Exception:
                pass
        messagebox.showinfo(
            "Оплата лицензии",
            (f"Сумма: {amount} ₽\n\n" if amount else "")
            + "Страница оплаты открыта в браузере.\n"
            + "После завершения оплаты нажмите ОК — программа проверит платёж.",
            parent=parent,
        )
        try:
            status = refresh_paid_order(config)
        except LicenseError as exc:
            messagebox.showwarning(
                "Оплата пока не подтверждена",
                str(exc) + "\n\nМожно повторить проверку, снова нажав «Оплатить/продлить».",
                parent=parent,
            )
            status = current_status(config)
            continue
        messagebox.showinfo("Лицензия", _format_status(status), parent=parent)
        return True


def ensure_generation_license(parent) -> bool:
    return ensure_license(parent, interactive=True)
