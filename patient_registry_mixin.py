from __future__ import annotations

from datetime import date
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from app_config import *
from medical_formatting import parse_date
from patient_registry import (
    PatientRegistryEntry,
    hospitalization_days_on,
    install_patient_summary_autostart,
    next_sick_leave_vk_date,
    scan_patient_registry,
    sick_leave_days_on,
)


class PatientRegistryMixin:
    def _patient_registry_root(self) -> str:
        return self._get_saved_directory(DIR_PATIENT_REGISTRY)

    def _prompt_patient_registry_folder(self, *, first_run: bool = False) -> bool:
        current = self._patient_registry_root()
        selected = filedialog.askdirectory(
            title="Из какой папки анализировать пациентов?",
            initialdir=current or str(Path.home()),
            mustexist=True,
            parent=self.root,
        )
        if not selected:
            return False
        self._remember_dialog_directory(
            DIR_PATIENT_REGISTRY,
            selected,
            selected_is_dir=True,
        )
        install_patient_summary_autostart()
        if not first_run:
            messagebox.showinfo(
                "Мои пациенты",
                "Папка пациентов сохранена. Список будет пересчитываться по первичным документам при каждом открытии.",
                parent=self.root,
            )
        return True

    def _ensure_patient_registry_folder(self, *, first_run: bool = False) -> bool:
        current = self._patient_registry_root()
        if current:
            install_patient_summary_autostart()
            return True
        return self._prompt_patient_registry_folder(first_run=first_run)

    def _registry_query_date(self, raw: str) -> date | None:
        parsed = parse_date(str(raw or "").strip())
        return parsed.date() if parsed else None

    def _prepare_registry_sick_leave_vk(
        self,
        entry: PatientRegistryEntry,
        vk_date: date,
        *,
        owner_window: tk.Toplevel | None = None,
    ) -> None:
        if entry.sick_leave_from is None:
            messagebox.showwarning(
                "ВК по больничному",
                "В первичном документе отмечен больничный лист, но дата его начала не распознана. "
                "Сначала уточните дату «с какого числа».",
                parent=owner_window or self.root,
            )
            return

        vk_text = vk_date.strftime("%d.%m.%Y")
        if not messagebox.askyesno(
            "Подготовить ВК по больничному",
            f"{entry.fio}\n\nПодготовить ВК по больничному на {vk_text}?",
            parent=owner_window or self.root,
        ):
            return

        try:
            self.root.deiconify()
            self.root.lift()
        except Exception:
            pass

        if owner_window is not None:
            try:
                owner_window.destroy()
            except Exception:
                pass

        if not self._apply_primary_document_path(
            str(entry.primary_path),
            prompt_for_referral=False,
        ):
            return

        sick_from_text = entry.sick_leave_from.strftime("%d.%m.%Y")
        self.expert_sick_leave_needed_var.set("да")
        self.expert_sick_leave_from_var.set(sick_from_text)
        self.data.expert_sick_leave_needed = "да"
        self.data.expert_sick_leave_from = sick_from_text
        self.data.sick_leave = f"нужен с {sick_from_text}"

        self.sick_leave_vk_date_var.set(vk_text)
        self.sick_leave_vk_protocol_date_var.set(vk_text)
        self.sick_leave_vk_commission_date_var.set(vk_text)
        self.data.sick_leave_vk_date = vk_text
        self.data.sick_leave_vk_protocol_date = vk_text
        self.data.sick_leave_vk_commission_date = vk_text
        if hasattr(self, "_update_expert_sick_leave_display"):
            self._update_expert_sick_leave_display()

        for kind, var in self.output_vars.items():
            var.set(kind == "sick_leave_vk")
        self._redraw_selection_controls()

        # Reuse the canonical document-detail flow. Dates and sick-leave start are
        # derived; protocol number and any other non-derivable medical facts are
        # still requested instead of being invented.
        self._on_output_toggle("sick_leave_vk")
        if self.output_vars["sick_leave_vk"].get():
            self.create_selected_outputs(print_after=False)

    def show_my_patients(self, *, startup_mode: bool = False) -> None:
        if not self._ensure_patient_registry_folder(first_run=False):
            if startup_mode:
                try:
                    self.root.destroy()
                except Exception:
                    pass
            return

        win = tk.Toplevel(self.root)
        win.title("Мои пациенты")
        win.configure(bg=DEEP)
        width = 840 if not startup_mode else 760
        height = 620 if not startup_mode else 540
        win.geometry(f"{width}x{height}")
        win.minsize(680, 420)
        if startup_mode:
            try:
                win.attributes("-topmost", True)
                win.after(1800, lambda: win.attributes("-topmost", False))
            except Exception:
                pass

        def close_window() -> None:
            try:
                win.destroy()
            finally:
                if startup_mode:
                    try:
                        self.root.destroy()
                    except Exception:
                        pass

        win.protocol("WM_DELETE_WINDOW", close_window)

        top = tk.Frame(win, bg=DEEP)
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            top,
            text="Мои пациенты",
            bg=DEEP,
            fg=TEXT,
            font=self._font(17, "bold"),
        ).grid(row=0, column=0, sticky="w")

        date_var = tk.StringVar(value=date.today().strftime("%d.%m.%Y"))
        tk.Label(
            top,
            text="Дата:",
            bg=DEEP,
            fg=MUTED,
            font=self._font(10),
        ).grid(row=0, column=1, sticky="e", padx=(16, 6))
        date_entry = tk.Entry(
            top,
            textvariable=date_var,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            width=13,
            font=self._font(10),
        )
        date_entry.grid(row=0, column=2, sticky="e")
        top.grid_columnconfigure(0, weight=1)

        summary_var = tk.StringVar()
        summary = tk.Label(
            win,
            textvariable=summary_var,
            bg=DEEP,
            fg=ACCENT,
            justify="left",
            anchor="w",
            font=self._font(11, "bold"),
        )
        summary.pack(fill="x", padx=16, pady=(0, 8))

        list_shell = tk.Frame(win, bg=PANEL, highlightbackground=BORDER_SOFT, highlightthickness=1)
        list_shell.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        canvas = tk.Canvas(list_shell, bg=PANEL, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(list_shell, orient="vertical", command=canvas.yview)
        rows = tk.Frame(canvas, bg=PANEL)
        window_id = canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        footer = tk.Frame(win, bg=DEEP)
        footer.pack(fill="x", padx=16, pady=(0, 14))

        def clear_rows() -> None:
            for child in rows.winfo_children():
                child.destroy()

        def add_patient_row(entry: PatientRegistryEntry, query_date: date) -> None:
            row = tk.Frame(rows, bg=PANEL)
            row.pack(fill="x", padx=10, pady=6)
            row.grid_columnconfigure(0, weight=1)

            title = f"{entry.fio} — поступление {entry.admission_date.strftime('%d.%m.%Y')}"
            tk.Label(
                row,
                text=title,
                bg=PANEL,
                fg=TEXT,
                anchor="w",
                justify="left",
                font=self._font(10, "bold"),
            ).grid(row=0, column=0, sticky="ew")

            details = "Без больничного листа на выбранную дату."
            next_vk = None
            if entry.sick_leave_needed:
                if entry.sick_leave_from is None:
                    details = "Лечится по больничному листу; дата начала не распознана."
                    if entry.warning:
                        details += " " + entry.warning
                elif entry.sick_leave_from > query_date:
                    details = (
                        f"Больничный лист с {entry.sick_leave_from.strftime('%d.%m.%Y')} "
                        f"(на {query_date.strftime('%d.%m.%Y')} ещё не начат)."
                    )
                else:
                    sick_days = sick_leave_days_on(entry, query_date) or 0
                    next_vk = next_sick_leave_vk_date(entry.sick_leave_from, query_date)
                    hospital_at_vk = hospitalization_days_on(entry, next_vk)
                    sick_at_vk = sick_leave_days_on(entry, next_vk) or 0
                    details = (
                        f"ЛН с {entry.sick_leave_from.strftime('%d.%m.%Y')}; "
                        f"на выбранную дату {sick_days} дн. по ЛН; "
                        f"следующая ВК {next_vk.strftime('%d.%m.%Y')}; "
                        f"на день ВК: госпитализация {hospital_at_vk} дн., ЛН {sick_at_vk} дн."
                    )

            tk.Label(
                row,
                text=details,
                bg=PANEL,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=590,
                font=self._font(9),
            ).grid(row=1, column=0, sticky="ew", pady=(3, 0))

            if next_vk is not None:
                tk.Button(
                    row,
                    text=f"Подготовить ВК на {next_vk.strftime('%d.%m.%Y')}",
                    command=lambda item=entry, vk=next_vk: self._prepare_registry_sick_leave_vk(
                        item,
                        vk,
                        owner_window=win,
                    ),
                    bg=PANEL_3,
                    fg=TEXT,
                    activebackground=BORDER,
                    activeforeground=TEXT,
                    relief="flat",
                    padx=8,
                    pady=5,
                    cursor="hand2",
                    font=self._font(9, "bold"),
                ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        def refresh() -> None:
            query_date = self._registry_query_date(date_var.get())
            if query_date is None:
                messagebox.showwarning(
                    "Мои пациенты",
                    "Укажите дату в формате ДД.ММ.ГГГГ.",
                    parent=win,
                )
                return
            root_path = self._patient_registry_root()
            if not root_path:
                return
            try:
                snapshot = scan_patient_registry(root_path, as_of=query_date)
            except Exception as exc:
                messagebox.showerror(
                    "Мои пациенты",
                    f"Не удалось проанализировать папку пациентов: {exc}",
                    parent=win,
                )
                return

            clear_rows()
            summary_var.set(
                f"На {query_date.strftime('%d.%m.%Y')} у вас {len(snapshot.patients)} пациентов. "
                f"По больничному листу: {len(snapshot.sick_leave_patients)}."
            )
            if not snapshot.patients:
                tk.Label(
                    rows,
                    text="Пациенты с распознанным первичным документом на эту дату не найдены.",
                    bg=PANEL,
                    fg=MUTED,
                    font=self._font(10),
                    pady=16,
                ).pack(fill="x")
            else:
                for entry in snapshot.patients:
                    add_patient_row(entry, query_date)

            if snapshot.issues:
                tk.Label(
                    rows,
                    text=f"Не удалось полностью проанализировать папок: {len(snapshot.issues)}.",
                    bg=PANEL,
                    fg=WARN,
                    font=self._font(9),
                    pady=8,
                ).pack(fill="x", padx=10)

        tk.Button(
            top,
            text="Обновить",
            command=refresh,
            bg=PANEL_3,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=TEXT,
            relief="flat",
            padx=9,
            cursor="hand2",
            font=self._font(9, "bold"),
        ).grid(row=0, column=3, padx=(7, 0))

        tk.Button(
            footer,
            text="Сменить папку пациентов",
            command=lambda: (self._prompt_patient_registry_folder(first_run=False) and refresh()),
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=ACCENT,
            relief="flat",
            cursor="hand2",
            font=self._font(9),
        ).pack(side="left")

        tk.Button(
            footer,
            text="Закрыть",
            command=close_window,
            bg=PANEL_3,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            cursor="hand2",
            font=self._font(9),
        ).pack(side="right")

        date_entry.bind("<Return>", lambda _event: refresh())
        refresh()
        win.lift()
        try:
            win.focus_force()
        except Exception:
            pass
