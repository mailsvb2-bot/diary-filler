from __future__ import annotations

from datetime import date
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from app_config import *
from medical_formatting import parse_date
from patient_registry import (
    PatientRegistryEntry,
    PatientSummaryTray,
    hospitalization_days_on,
    install_patient_summary_autostart,
    launch_patient_summary_tray_process,
    next_sick_leave_vk_date,
    open_patient_folder,
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
        if current and Path(current).expanduser().is_dir():
            install_patient_summary_autostart()
            return True
        # Empty, moved or deleted roots are not a valid completed onboarding.
        # Ask again instead of silently keeping a stale saved string.
        return self._prompt_patient_registry_folder(first_run=first_run)

    def _registry_query_date(self, raw: str) -> date | None:
        parsed = parse_date(str(raw or "").strip())
        return parsed.date() if parsed else None

    def _open_patient_registry_path(
        self,
        path: str | Path | None = None,
        *,
        parent: tk.Misc | None = None,
    ) -> bool:
        target = Path(path or self._patient_registry_root()).expanduser()
        if open_patient_folder(target):
            return True
        messagebox.showerror(
            "Папка пациентов",
            "Не удалось открыть папку. Проверьте, что она существует и доступна.",
            parent=parent or self.root,
        )
        return False

    def show_patient_registry_folder_settings(self) -> None:
        """Open/change the root folder used by «Мои пациенты»."""
        if not self._patient_registry_root():
            if not self._prompt_patient_registry_folder(first_run=False):
                return

        win = tk.Toplevel(self.root)
        win.title("Папка пациентов")
        win.configure(bg=DEEP)
        win.resizable(False, False)
        win.transient(self.root)

        body = tk.Frame(win, bg=DEEP)
        body.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            body,
            text="Папка пациентов",
            bg=DEEP,
            fg=TEXT,
            font=self._font(13, "bold"),
        ).pack(anchor="w")
        path_var = tk.StringVar(value=self._patient_registry_root())
        tk.Label(
            body,
            textvariable=path_var,
            bg=DEEP,
            fg=MUTED,
            justify="left",
            anchor="w",
            wraplength=620,
            font=self._font(9),
        ).pack(fill="x", pady=(8, 12))

        buttons = tk.Frame(body, bg=DEEP)
        buttons.pack(fill="x")

        def change_path() -> None:
            if self._prompt_patient_registry_folder(first_run=False):
                path_var.set(self._patient_registry_root())

        tk.Button(
            buttons,
            text="Открыть папку",
            command=lambda: self._open_patient_registry_path(parent=win),
            bg=PANEL_3,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            font=self._font(9, "bold"),
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Сменить путь",
            command=change_path,
            bg=PANEL_3,
            fg=TEXT,
            activebackground=BORDER,
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            font=self._font(9, "bold"),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons,
            text="× Закрыть",
            command=win.destroy,
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=TEXT,
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
            font=self._font(9),
        ).pack(side="right")

        win.bind("<Escape>", lambda _event: win.destroy())
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.update_idletasks()
        try:
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - win.winfo_width()) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - win.winfo_height()) // 2)
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.lift()

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

    def show_my_patients(self, *, startup_mode: bool = False, start_in_tray: bool = False) -> None:
        # A logon summary must never block Windows with a first-run folder dialog.
        # Folder onboarding belongs to the normal visible application start.
        if startup_mode and not self._patient_registry_root():
            try:
                self.root.destroy()
            except Exception:
                pass
            return
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
        width = 900 if not startup_mode else 840
        height = 620 if not startup_mode else 560
        win.geometry(f"{width}x{height}")
        win.minsize(720, 440)
        if startup_mode:
            try:
                win.attributes("-topmost", True)
                win.after(1800, lambda: win.attributes("-topmost", False))
            except Exception:
                pass

        tray = PatientSummaryTray("Мои пациенты")

        def close_window() -> None:
            tray.stop()
            try:
                win.destroy()
            finally:
                if startup_mode:
                    try:
                        self.root.destroy()
                    except Exception:
                        pass

        def restore_from_tray() -> None:
            # Keep the tray icon alive while the summary is open. The user can
            # close this independent summary only via its own X or tray menu.
            try:
                win.deiconify()
                win.lift()
                win.focus_force()
            except Exception:
                pass

        def minimize_to_tray() -> None:
            if not startup_mode:
                # A summary opened from the main GUI must survive that GUI being
                # closed. Move it into its own detached summary process before
                # removing this in-process child window.
                if launch_patient_summary_tray_process():
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    return
            if tray.start():
                try:
                    win.withdraw()
                except Exception:
                    tray.stop()
                    win.iconify()
            else:
                # Development/non-Windows fallback: never make the summary
                # unreachable merely because a native tray is unavailable.
                try:
                    win.deiconify()
                except Exception:
                    pass
                win.iconify()

        def poll_tray_requests() -> None:
            try:
                if not win.winfo_exists():
                    tray.stop()
                    return
                if tray.consume_close_request():
                    close_window()
                    return
                if tray.consume_restore_request():
                    restore_from_tray()
                win.after(200, poll_tray_requests)
            except Exception:
                tray.stop()

        win.protocol("WM_DELETE_WINDOW", close_window)
        win.after(200, poll_tray_requests)

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

            admission_text = (
                entry.admission_date.strftime("%d.%m.%Y")
                if entry.admission_date is not None
                else "дата не распознана"
            )
            title = f"{entry.fio} — поступление {admission_text}"
            title_label = tk.Label(
                row,
                text=title,
                bg=PANEL,
                fg=ACCENT,
                anchor="w",
                justify="left",
                cursor="hand2",
                font=self._font(10, "bold"),
            )
            title_label.grid(row=0, column=0, sticky="ew")

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
                    hospital_text = (
                        f"{hospital_at_vk} дн."
                        if hospital_at_vk is not None
                        else "дата поступления не распознана"
                    )
                    details = (
                        f"ЛН с {entry.sick_leave_from.strftime('%d.%m.%Y')}; "
                        f"на выбранную дату {sick_days} дн. по ЛН; "
                        f"следующая ВК {next_vk.strftime('%d.%m.%Y')}; "
                        f"на день ВК: госпитализация {hospital_text}, ЛН {sick_at_vk} дн."
                    )

            details_label = tk.Label(
                row,
                text=details,
                bg=PANEL,
                fg=MUTED,
                anchor="w",
                justify="left",
                wraplength=620,
                cursor="hand2",
                font=self._font(9),
            )
            details_label.grid(row=1, column=0, sticky="ew", pady=(3, 0))

            open_folder = lambda _event=None, folder=entry.folder: self._open_patient_registry_path(
                folder,
                parent=win,
            )
            row.bind("<Button-1>", open_folder)
            title_label.bind("<Button-1>", open_folder)
            details_label.bind("<Button-1>", open_folder)

            if next_vk is not None:
                tk.Button(
                    row,
                    text=f"Подготовить ВК по больничному на {next_vk.strftime('%d.%m.%Y')}",
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

        scan_results: queue.Queue = queue.Queue()
        refresh_generation = 0

        def render_snapshot(snapshot, query_date: date, generation: int) -> None:
            if generation != refresh_generation:
                return
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return

            clear_rows()
            summary_var.set(
                f"На {query_date.strftime('%d.%m.%Y')} у вас {len(snapshot.patients)} пациентов. "
                f"По больничному листу: {len(snapshot.sick_leave_patients)}."
            )
            if not snapshot.patients:
                empty_text = "Пациенты с первичным документом на эту дату не найдены."
                if snapshot.issues:
                    empty_text += " Ниже показаны предупреждения по отдельным папкам."
                else:
                    empty_text += (
                        " Проверьте выбранную папку и наличие файлов вида "
                        "«Фамилия первичный/первичка.docx» в её подпапках."
                    )
                tk.Label(
                    rows,
                    text=empty_text,
                    bg=PANEL,
                    fg=MUTED,
                    justify="left",
                    anchor="w",
                    wraplength=760,
                    font=self._font(10),
                    pady=16,
                ).pack(fill="x", padx=10)
            else:
                # scan_patient_registry already guarantees this order, but keep
                # the UI contract explicit: sick-leave patients are always shown
                # first, followed by the rest of the ward census.
                ordered_patients = sorted(
                    snapshot.patients,
                    key=lambda item: (
                        0 if item.is_on_sick_leave_on(query_date) else 1,
                        item.fio.casefold(),
                    ),
                )
                for entry in ordered_patients:
                    add_patient_row(entry, query_date)

            if snapshot.issues:
                tk.Label(
                    rows,
                    text=f"Не удалось полностью проанализировать папок: {len(snapshot.issues)}.",
                    bg=PANEL,
                    fg=WARN,
                    font=self._font(9, "bold"),
                    pady=6,
                ).pack(fill="x", padx=10)
                for issue in snapshot.issues[:10]:
                    tk.Label(
                        rows,
                        text=f"• {issue.folder.name}: {issue.message}",
                        bg=PANEL,
                        fg=WARN,
                        justify="left",
                        anchor="w",
                        wraplength=760,
                        font=self._font(9),
                    ).pack(fill="x", padx=18, pady=(0, 3))
                if len(snapshot.issues) > 10:
                    tk.Label(
                        rows,
                        text=f"… и ещё {len(snapshot.issues) - 10}.",
                        bg=PANEL,
                        fg=WARN,
                        anchor="w",
                        font=self._font(9),
                    ).pack(fill="x", padx=18, pady=(0, 4))

        def poll_scan_results() -> None:
            try:
                while True:
                    kind, generation, query_date, payload = scan_results.get_nowait()
                    if generation != refresh_generation:
                        continue
                    if kind == "error":
                        clear_rows()
                        summary_var.set("")
                        messagebox.showerror(
                            "Мои пациенты",
                            f"Не удалось проанализировать папку пациентов: {payload}",
                            parent=win,
                        )
                    else:
                        render_snapshot(payload, query_date, generation)
            except queue.Empty:
                pass
            try:
                if win.winfo_exists():
                    win.after(60, poll_scan_results)
            except Exception:
                pass

        def refresh() -> None:
            nonlocal refresh_generation
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

            refresh_generation += 1
            generation = refresh_generation
            clear_rows()
            summary_var.set("Анализирую папки пациентов…")
            tk.Label(
                rows,
                text="Список загружается. Окно уже можно перемещать и сворачивать.",
                bg=PANEL,
                fg=MUTED,
                justify="left",
                anchor="w",
                font=self._font(10),
                pady=16,
            ).pack(fill="x", padx=10)

            def scan_worker() -> None:
                try:
                    snapshot = scan_patient_registry(root_path, as_of=query_date)
                except Exception as exc:
                    scan_results.put(("error", generation, query_date, str(exc)))
                    return
                scan_results.put(("ok", generation, query_date, snapshot))

            threading.Thread(
                target=scan_worker,
                name="MedicalDiaryAutofillPatientRegistryScan",
                daemon=True,
            ).start()

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
            text="Открыть папку пациентов",
            command=lambda: self._open_patient_registry_path(parent=win),
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
            text="Сменить путь",
            command=lambda: (self._prompt_patient_registry_folder(first_run=False) and refresh()),
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=ACCENT,
            relief="flat",
            cursor="hand2",
            font=self._font(9),
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            footer,
            text="Свернуть в трей",
            command=minimize_to_tray,
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=ACCENT,
            relief="flat",
            cursor="hand2",
            font=self._font(9),
        ).pack(side="right", padx=(0, 10))

        tk.Button(
            footer,
            text="× Закрыть",
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
        win.after(60, poll_scan_results)
        refresh()
        if start_in_tray:
            # Detached tray hosts must not flash a visible summary window before
            # the notification-area icon is ready.
            try:
                win.withdraw()
            except Exception:
                pass
            win.after(50, minimize_to_tray)
        else:
            win.lift()
            try:
                win.focus_force()
            except Exception:
                pass
