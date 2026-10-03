"""Tk licensing UX for visible MedicalDiaryAutofill sessions."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, simpledialog

from license_client import (
    LicenseError,
    LicenseExpiredError,
    PaidLicenseRecoveryError,
    PaymentPendingError,
    PaymentTerminalError,
    activate_owner,
    begin_monthly_payment,
    current_status,
    discard_pending_order,
    pending_payment_details,
    recover_paid_license,
    refresh_paid_order,
    runtime_config,
)


def _format_status(status) -> str:
    if status.active:
        if status.owner_unlimited:
            return "Лицензия активна."
        if status.valid_until is not None:
            return "Лицензия активна до " + status.valid_until.astimezone().strftime("%d.%m.%Y %H:%M")
        return "Лицензия активна."
    if status.mode == "owner_reactivation":
        return "Требуется повторная активация лицензии на этом компьютере."
    return status.message


def _manager_state(status) -> dict:
    if status.active and status.owner_unlimited:
        return {
            "title": "Лицензия активна",
            "details": "Доступ активирован.",
            "show_payment": False,
            "show_activation": False,
            "show_recovery": False,
        }
    if status.active:
        details = (
            "Действует до: " + status.valid_until.astimezone().strftime("%d.%m.%Y %H:%M")
            if status.valid_until is not None
            else "Лицензия активна."
        )
        return {
            "title": "Лицензия активна",
            "details": details,
            "show_payment": False,
            "show_activation": True,
            "show_recovery": False,
        }
    if status.mode == "owner_reactivation":
        return {
            "title": "Требуется активация",
            "details": "Введите код активации для этого компьютера.",
            "show_payment": False,
            "show_activation": True,
            "show_recovery": False,
        }
    if status.mode == "paid_recovery":
        return {
            "title": "Требуется проверка лицензии",
            "details": "Повторная оплата не требуется. Проверьте уже оплаченную лицензию.",
            "show_payment": False,
            "show_activation": False,
            "show_recovery": True,
        }
    return {
        "title": "Лицензия не активна",
        "details": _format_status(status),
        "show_payment": True,
        "show_activation": True,
        "show_recovery": False,
    }


def _activate_code(parent, config, *, prompt: str = "Введите код активации:"):
    code = simpledialog.askstring(
        "Код активации",
        prompt,
        show="•",
        parent=parent,
    )
    if not code:
        return None
    try:
        status = activate_owner(code, config)
    except LicenseError as exc:
        messagebox.showerror("Активация лицензии", str(exc), parent=parent)
        return None
    messagebox.showinfo("Лицензия", "Лицензия активирована.", parent=parent)
    return status


def _payment_flow(parent, config):
    try:
        pending = pending_payment_details()
    except LicenseError as exc:
        messagebox.showwarning(
            "Проверка оплаты",
            str(exc)
            + "\n\nНовый счёт не создан, чтобы исключить повторную оплату.",
            parent=parent,
        )
        return None

    if pending:
        try:
            already_paid = refresh_paid_order(config)
        except PaymentPendingError:
            already_paid = None
        except PaymentTerminalError:
            pending = None
            already_paid = None
        except LicenseError as exc:
            messagebox.showwarning(
                "Проверка оплаты",
                str(exc)
                + "\n\nНовый счёт не создан, чтобы исключить повторную оплату. "
                + "Повторите проверку позже.",
                parent=parent,
            )
            return None
        if already_paid is not None and already_paid.active:
            messagebox.showinfo("Лицензия", _format_status(already_paid), parent=parent)
            return already_paid

    try:
        if pending and pending.get("payment_url"):
            reuse = messagebox.askyesno(
                "Незавершённая оплата",
                "Оплата по предыдущему счёту пока не подтверждена.\n\n"
                "Да — продолжить прошлую оплату.\n"
                "Нет — отменить локально старый счёт и создать новый.",
                parent=parent,
            )
            if reuse:
                payment = pending
            else:
                discard_pending_order()
                payment = begin_monthly_payment(config)
        else:
            payment = begin_monthly_payment(config)
    except LicenseError as exc:
        messagebox.showerror("Лицензия", str(exc), parent=parent)
        return None

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
    except PaymentPendingError as exc:
        messagebox.showwarning(
            "Оплата пока не подтверждена",
            str(exc) + "\n\nПроверку можно повторить из окна «Лицензия».",
            parent=parent,
        )
        return None
    except LicenseError as exc:
        messagebox.showwarning(
            "Проверка лицензии",
            str(exc)
            + "\n\nНовый платёж не требуется. Повторите проверку позже.",
            parent=parent,
        )
        return None
    messagebox.showinfo("Лицензия", _format_status(status), parent=parent)
    return status


def show_license_manager(parent) -> None:
    config = runtime_config()
    window = tk.Toplevel(parent)
    window.title("Лицензия")
    window.transient(parent)
    window.resizable(False, False)
    window.configure(bg="#07111f")
    try:
        window.grab_set()
    except tk.TclError:
        pass

    width, height = 430, 245
    try:
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        window.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        window.geometry(f"{width}x{height}")

    title_var = tk.StringVar()
    details_var = tk.StringVar()
    content = tk.Frame(window, bg="#07111f", padx=24, pady=22)
    content.pack(fill="both", expand=True)

    tk.Label(
        content,
        textvariable=title_var,
        bg="#07111f",
        fg="#eaf6ff",
        font=("Segoe UI", 15, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        content,
        textvariable=details_var,
        bg="#07111f",
        fg="#91a8bb",
        font=("Segoe UI", 10),
        anchor="w",
        justify="left",
        wraplength=380,
    ).pack(fill="x", pady=(10, 18))

    buttons = tk.Frame(content, bg="#07111f")
    buttons.pack(fill="x", side="bottom")

    def button(text: str, command, *, accent: bool = False):
        return tk.Button(
            buttons,
            text=text,
            command=command,
            bg="#24c8fb" if accent else "#10263a",
            fg="#03101f" if accent else "#eaf6ff",
            activebackground="#7ee3ff" if accent else "#18344d",
            activeforeground="#03101f" if accent else "#ffffff",
            relief="flat",
            bd=0,
            padx=14,
            pady=8,
            font=("Segoe UI", 10, "bold" if accent else "normal"),
            cursor="hand2",
        )

    def refresh() -> None:
        for child in buttons.winfo_children():
            child.destroy()
        status = current_status(config)
        state = _manager_state(status)
        title_var.set(state["title"])
        details_var.set(state["details"])

        if state["show_activation"]:
            button(
                "Ввести код активации",
                lambda: activate_and_refresh(),
                accent=not state["show_payment"],
            ).pack(side="left", padx=(0, 8))
        if state.get("show_recovery"):
            button(
                "Проверить лицензию",
                lambda: recover_and_refresh(),
                accent=True,
            ).pack(side="left", padx=(0, 8))
        if state["show_payment"]:
            button(
                "Оплатить лицензию",
                lambda: pay_and_refresh(),
                accent=True,
            ).pack(side="left", padx=(0, 8))
        button("Закрыть", window.destroy).pack(side="right")

    def activate_and_refresh() -> None:
        if _activate_code(window, config) is not None:
            refresh()

    def recover_and_refresh() -> None:
        try:
            status = recover_paid_license(config)
        except LicenseExpiredError:
            messagebox.showinfo(
                "Лицензия",
                "Срок предыдущей лицензии истёк. Можно оформить новый период.",
                parent=window,
            )
        except LicenseError as exc:
            messagebox.showwarning(
                "Проверка лицензии",
                str(exc) + "\n\nПовторная оплата не требуется. Повторите проверку позже.",
                parent=window,
            )
        else:
            messagebox.showinfo("Лицензия", _format_status(status), parent=window)
        refresh()

    def pay_and_refresh() -> None:
        _payment_flow(window, config)
        refresh()

    refresh()
    try:
        window.wait_window()
    except tk.TclError:
        pass


def ensure_license(parent, *, interactive: bool = True) -> bool:
    config = runtime_config()
    status = current_status(config)
    if status.active:
        return True
    if not interactive:
        return False

    if status.mode == "paid_recovery":
        try:
            recovered = recover_paid_license(config)
        except LicenseExpiredError:
            status = current_status(config)
        except LicenseError as exc:
            messagebox.showwarning(
                "Проверка лицензии",
                str(exc)
                + "\n\nПовторная оплата не требуется. Повторите проверку позже.",
                parent=parent,
            )
            return False
        else:
            return bool(recovered.active)

    # A previously signed privileged entitlement never enters paid UX.
    if status.mode == "owner_reactivation":
        while True:
            if _activate_code(
                parent,
                config,
                prompt="Повторно введите код активации для этого компьютера:",
            ) is not None:
                return True
            retry = messagebox.askretrycancel(
                "Активация лицензии",
                "Лицензия не активирована. Повторить ввод кода?",
                parent=parent,
            )
            if not retry:
                return False

    while True:
        choice = messagebox.askyesnocancel(
            "Лицензия MedicalDiaryAutofill",
            _format_status(status)
            + "\n\n"
            + "Да — оплатить лицензию.\n"
            + "Нет — ввести код активации.\n"
            + "Отмена — закрыть.",
            parent=parent,
        )
        if choice is None:
            return False
        if choice is False:
            if _activate_code(parent, config) is not None:
                return True
            status = current_status(config)
            continue

        paid = _payment_flow(parent, config)
        if paid is not None and paid.active:
            return True
        status = current_status(config)


def ensure_generation_license(parent) -> bool:
    return ensure_license(parent, interactive=True)
