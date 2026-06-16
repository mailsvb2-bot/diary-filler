"""
Единый автозаполнитель: медицинские документы + дневники.

Лёгкий красивый UI на стандартном Tkinter, один экран без вкладок:
- сверху общая карточка пациента;
- ниже входные файлы;
- общий список "Что создать" с галочками, включая "Дневники";
- одна итоговая кнопка создаёт только отмеченные позиции.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from printer_support import get_default_printer, list_printers, print_files

from medical_documents import (
    DATE_FMT,
    DOCUMENT_LABELS,
    DOCUMENT_ORDER,
    MedicalDocumentService,
    PatientData,
    bundled_template_path,
    format_preview,
    parse_date,
)
from diary_filler import (
    detect_first_month_year_from_docx,
    fill_diary_batch,
    format_month_year,
)
from icd10_f import format_diagnosis, search_icd10_f

APP_TITLE = "Медицинский автозаполнитель"

# Лёгкая “медицинская неон-панель” без внешних UI-библиотек.
# Только стандартный Tkinter: красивее визуально, но без утяжеления проекта.
BG = "#071421"
BG_2 = "#0a1d2f"
PANEL = "#10263d"
PANEL_2 = "#15314d"
PANEL_3 = "#1a3b5d"
BORDER = "#2a5576"
BORDER_SOFT = "#1b3f5e"
ACCENT = "#38c7ff"
ACCENT_2 = "#34e6a8"
ACCENT_3 = "#8bb7ff"
TEXT = "#f2f9ff"
MUTED = "#a7bad0"
WARN = "#ffd166"
ERROR = "#ff7a9c"
SUCCESS = "#70f5bd"
FIELD = "#081b2c"
FIELD_BORDER = "#2f5f83"

DIARY_KIND = "diaries"
DIARY_LABEL = "Дневники наблюдения"


class CombinedMedicalDiaryApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.service = MedicalDocumentService()
        self.data = PatientData()

        # Общая карточка пациента. ФИО в UI используется для названия файлов.
        # ФИО внутри документов всегда берётся из выбранного первичного документа.
        self.patient_name_var = tk.StringVar()
        self.admission_date_var = tk.StringVar(value=datetime.now().strftime(DATE_FMT))
        self.discharge_date_var = tk.StringVar(value=datetime.now().strftime(DATE_FMT))
        self.diagnosis_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        # Печать: выбор принтера и сценарий "создать + сохранить + распечатать".
        self.printer_var = tk.StringVar()
        self.available_printers: list[str] = []
        self._settings_path = self._get_settings_path()
        self._settings = self._load_settings()
        saved_printer = str(self._settings.get("printer", "")).strip()
        if saved_printer:
            self.printer_var.set(saved_printer)

        # Тип входного первичного документа.
        # Если выбран вариант «направление на госпитализацию», назначенное лечение
        # вводится вручную через маленькое окно и затем используется во всех документах.
        # Если выбран «первичный осмотр», лечение берётся из самого первичного осмотра.
        self.primary_document_type_var = tk.StringVar(value="primary_exam")
        self.assigned_treatment_var = tk.StringVar()

        # Защита ручного ввода UI. Некоторые файлы умеют подтягивать ФИО/дату/диагноз
        # автоматически, но уже набранные врачом значения нельзя перетирать при выборе
        # направления, ЭПИ или таблиц дневников.
        self._suspend_user_edit_tracking = False
        self._manual_patient_name = False
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._manual_diagnosis = False
        self.patient_name_var.trace_add("write", lambda *_: self._mark_manual_field("patient_name"))
        self.admission_date_var.trace_add("write", lambda *_: self._mark_manual_field("admission_date"))
        self.discharge_date_var.trace_add("write", lambda *_: self._mark_manual_field("discharge_date"))
        self.diagnosis_var.trace_add("write", lambda *_: self._mark_manual_field("diagnosis"))

        # Ручные реквизиты для отдельных документов. В UI они не занимают место:
        # появляются маленькие окна при включении соответствующих галочек.
        self.rvk_act_number_var = tk.StringVar()
        self.rvk_military_commissariat_var = tk.StringVar()
        self.rvk_work_position_var = tk.StringVar()
        self.vk_date_var = tk.StringVar()
        self.vk_protocol_number_var = tk.StringVar()
        self.vk_protocol_date_var = tk.StringVar()
        self.vk_mse_work_org_var = tk.StringVar()
        self.vk_mse_position_var = tk.StringVar()
        self.sick_leave_vk_date_var = tk.StringVar()
        self.sick_leave_vk_protocol_number_var = tk.StringVar()
        self.sick_leave_vk_protocol_date_var = tk.StringVar()
        self.sick_leave_vk_commission_date_var = tk.StringVar()
        self.sick_leave_vk_work_position_var = tk.StringVar()
        self.commission_date_var = tk.StringVar()
        self.commission_number_var = tk.StringVar()

        # Общие даты для popup-окон ВК/комиссий.
        # Если дата введена в одном окне, она автоматически предлагается
        # в связанных полях других окон, но каждое поле остаётся редактируемым.
        self._last_committee_date = ""
        self._last_protocol_date = ""

        # Медицинские документы.
        self.navigation_path_var = tk.StringVar()
        self.epi_path_var = tk.StringVar()
        self.strict_mode_var = tk.BooleanVar(value=True)

        # Общий список создаваемых сущностей: медицинские документы + дневники.
        self.output_vars: Dict[str, tk.BooleanVar] = {
            # По умолчанию включены самые частые задачи: выписной эпикриз и дневники.
            # Остальные документы врач включает галочками вручную.
            kind: tk.BooleanVar(value=(kind == "discharge")) for kind in DOCUMENT_ORDER
        }
        self.output_vars[DIARY_KIND] = tk.BooleanVar(value=True)

        # Дневники.
        self.status_files: List[str] = []
        self.diary_files: List[str] = []
        self.repeat_statuses_var = tk.BooleanVar(value=True)
        self.reset_each_file_var = tk.BooleanVar(value=True)
        self.keep_signature_var = tk.BooleanVar(value=True)
        self.fill_months_var = tk.BooleanVar(value=True)
        self.force_final_diary_var = tk.BooleanVar(value=True)
        self.remove_holiday_rows_var = tk.BooleanVar(value=True)
        self.open_result_folder_var = tk.BooleanVar(value=True)

        # Скрытые служебные данные вместо прежних видимых блоков "Предпросмотр" и "Журнал".
        # Функционал остаётся: данные пациента хранятся, ошибки показываются в messagebox,
        # а короткий статус выводится в нижней панели.
        self._last_preview_text = ""
        self._log_buffer: List[str] = []

        # Собственный быстрый список диагноза, встроенный прямо в карточку пациента.
        # Не используется плавающее окно: оно могло сбивать фокус и положение UI.
        self._diagnosis_popup: tk.Frame | None = None
        self._diagnosis_listbox: tk.Listbox | None = None
        self._diagnosis_popup_matches: list[str] = []

        self.root.title(APP_TITLE)
        self.root.geometry("1180x820")
        self.root.minsize(1040, 760)
        self.root.configure(bg=BG)
        self._install_text_shortcuts()
        self._build_ui()
        self._check_templates()
        self.root.after(250, self.refresh_printers)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self._setup_style()

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True, padx=20, pady=14)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(2, weight=1)

        self._build_header(shell)
        self._build_patient_card(shell)
        self._build_one_window_workspace(shell)
        self._build_action_bar(shell)
        self._log("Готово. Выберите первичный документ, проверьте дату/диагноз и нажмите нужную кнопку создания.\n")

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Header.TLabel", background=BG_2, foreground=TEXT, font=("Segoe UI", 22, "bold"))
        style.configure("Subheader.TLabel", background=BG_2, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), foreground="#03101f", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#7ee3ff")])
        style.configure("Green.TButton", font=("Segoe UI", 12, "bold"), foreground="#03101f", background=ACCENT_2)
        style.map("Green.TButton", background=[("active", "#8fffd5")])
        style.configure("Dark.TButton", font=("Segoe UI", 10), foreground=TEXT, background=PANEL_3, borderwidth=0)
        style.map("Dark.TButton", background=[("active", BORDER)], foreground=[("active", TEXT)])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("active", TEXT)])
        style.configure("TRadiobutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TRadiobutton", background=[("active", PANEL)], foreground=[("active", TEXT)])
        style.configure("TCombobox", fieldbackground=FIELD, background=PANEL_3, foreground=TEXT, arrowcolor=TEXT)
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=BG_2,
            background=ACCENT_2,
            bordercolor=BG_2,
            lightcolor=ACCENT_2,
            darkcolor=ACCENT_2,
        )

    def _install_text_shortcuts(self) -> None:
        """Нормальные Ctrl+A/C/V/X во всех полях, включая popup-окна.

        На Windows с русской раскладкой Tkinter иногда видит Ctrl+C не как
        латинскую C, а как Cyrillic_es. Поэтому ловим общий Control-KeyPress
        и вызываем стандартные виртуальные события Entry вручную.
        """
        for cls in ("Entry", "TEntry"):
            try:
                self.root.bind_class(cls, "<Control-KeyPress>", self._entry_control_shortcut, add="+")
            except tk.TclError:
                pass

    def _entry_control_shortcut(self, event) -> str | None:
        widget = getattr(event, "widget", None)
        if widget is None:
            return None
        keysym = str(getattr(event, "keysym", "")).lower()
        char = str(getattr(event, "char", "")).lower()
        keycode = getattr(event, "keycode", None)

        def is_key(*names: str, codes: int = -1) -> bool:
            return keysym in names or char in names or (codes != -1 and keycode == codes)

        try:
            if is_key("a", "ф", "cyrillic_ef", codes=65):
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
                return "break"
            if is_key("c", "с", "cyrillic_es", codes=67):
                widget.event_generate("<<Copy>>")
                return "break"
            if is_key("v", "м", "cyrillic_em", codes=86):
                widget.event_generate("<<Paste>>")
                return "break"
            if is_key("x", "ч", "cyrillic_che", codes=88):
                widget.event_generate("<<Cut>>")
                return "break"
        except tk.TclError:
            return None
        return None

    def _get_settings_path(self) -> Path:
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home()
        return root / "MedicalDiaryAutofill" / "settings.json"

    def _load_settings(self) -> dict:
        try:
            if self._settings_path.exists():
                return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_settings(self) -> None:
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._settings_path.write_text(json.dumps(self._settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            # Настройки — удобство, не критичная функция. Ошибку не показываем врачу.
            pass

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=BG_2, highlightbackground=BORDER_SOFT, highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(1, weight=1)

        stripe = tk.Frame(header, bg=ACCENT_2, width=5)
        stripe.grid(row=0, column=0, sticky="nsw")

        title_box = tk.Frame(header, bg=BG_2, padx=18, pady=10)
        title_box.grid(row=0, column=1, sticky="ew")
        title_box.grid_columnconfigure(0, weight=1)
        ttk.Label(title_box, text="Медицинский автозаполнитель", style="Header.TLabel").grid(row=0, column=0, sticky="w")

    def _build_patient_card(self, parent: tk.Frame) -> None:
        card = self._card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for col in range(9):
            card.grid_columnconfigure(col, weight=1)

        self._card_title(card, "01 · Пациент, даты и диагноз").grid(
            row=0, column=0, columnspan=9, sticky="ew", pady=(0, 8)
        )

        self._field(card, "ФИО для имени файла", self.patient_name_var, row=1, col=0, colspan=2)
        self._field(card, "Дата поступления / месяц-год", self.admission_date_var, row=1, col=2, colspan=2)
        self._field(card, "Дата выписки", self.discharge_date_var, row=1, col=4, colspan=1)
        self._diagnosis_field(card, row=2, col=0, colspan=5)
        self._output_folder_group(card, row=1, col=5, colspan=4)

    def _build_one_window_workspace(self, parent: tk.Frame) -> None:
        workspace = tk.Frame(parent, bg=BG)
        workspace.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        workspace.grid_columnconfigure(0, weight=5)
        workspace.grid_columnconfigure(1, weight=4)
        workspace.grid_rowconfigure(0, weight=1)

        left = tk.Frame(workspace, bg=BG)
        right = tk.Frame(workspace, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        left.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self._build_input_files_card(left)
        self._build_create_checklist_card(right)

    def _build_input_files_card(self, parent: tk.Frame) -> None:
        files = self._card(parent)
        files.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        files.grid_columnconfigure(1, weight=1)
        self._card_title(files, "02 · Входные данные").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        type_box = tk.Frame(files, bg=PANEL_2, highlightbackground=BORDER_SOFT, highlightthickness=1, padx=10, pady=7)
        type_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 7))
        type_box.grid_columnconfigure(2, weight=1)
        ttk.Label(type_box, text="Тип первичного документа", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 14))
        ttk.Radiobutton(
            type_box,
            text="Направление на госпитализацию",
            variable=self.primary_document_type_var,
            value="hospitalization_referral",
            command=self._on_primary_document_type_changed,
        ).grid(row=0, column=1, sticky="w", padx=(0, 14))
        ttk.Radiobutton(
            type_box,
            text="Первичный осмотр",
            variable=self.primary_document_type_var,
            value="primary_exam",
            command=self._on_primary_document_type_changed,
        ).grid(row=0, column=2, sticky="w")

        self._file_row(files, 2, "Первичный документ", self.navigation_path_var, self.choose_navigation, "Выбрать")
        self._file_row(files, 3, "ЭПИ файл", self.epi_path_var, self.choose_epi, "Выбрать", optional=True)

        ttk.Label(files, text="Тексты дневников", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=3)
        self.status_files_label = ttk.Label(files, text="Файлы не выбраны", style="Muted.TLabel", wraplength=330)
        self.status_files_label.grid(row=4, column=1, sticky="ew", padx=10, pady=3)
        ttk.Button(files, text="Выбрать", command=self.choose_status_files, style="Dark.TButton").grid(row=4, column=2, sticky="e", pady=3)

        ttk.Label(files, text="Таблицы дневников", style="Card.TLabel").grid(row=5, column=0, sticky="w", pady=3)
        self.diary_files_label = ttk.Label(files, text="Файлы не выбраны", style="Muted.TLabel", wraplength=330)
        self.diary_files_label.grid(row=5, column=1, sticky="ew", padx=10, pady=3)
        ttk.Button(files, text="Выбрать", command=self.choose_diary_files, style="Dark.TButton").grid(row=5, column=2, sticky="e", pady=3)


    def _build_create_checklist_card(self, parent: tk.Frame) -> None:
        docs = self._card(parent)
        docs.grid(row=0, column=0, sticky="nsew")
        docs.grid_columnconfigure(0, weight=1)
        self._card_title(docs, "03 · Что создать").grid(row=0, column=0, sticky="ew", pady=(0, 8))

        checklist = tk.Frame(docs, bg=PANEL)
        checklist.grid(row=1, column=0, sticky="ew")
        checklist.grid_columnconfigure(0, weight=1)
        checklist.grid_columnconfigure(1, weight=1)
        all_items = [(kind, DOCUMENT_LABELS[kind]) for kind in DOCUMENT_ORDER] + [(DIARY_KIND, DIARY_LABEL)]
        for idx, (kind, label) in enumerate(all_items):
            item = tk.Frame(checklist, bg=PANEL_2, highlightbackground=BORDER_SOFT, highlightthickness=1, padx=10, pady=7)
            item.grid(row=idx // 2, column=idx % 2, sticky="ew", padx=(0 if idx % 2 == 0 else 8, 0), pady=5)
            item.grid_columnconfigure(0, weight=1)
            cb = tk.Checkbutton(
                item,
                text=label,
                variable=self.output_vars[kind],
                command=lambda k=kind: self._on_output_toggle(k),
                bg=PANEL_2,
                fg=TEXT,
                activebackground=PANEL_2,
                activeforeground=TEXT,
                selectcolor=FIELD,
                font=("Segoe UI", 10, "bold" if kind in {"discharge", DIARY_KIND} else "normal"),
                relief="flat",
                anchor="w",
            )
            cb.grid(row=0, column=0, sticky="ew")


    def _build_action_bar(self, parent: tk.Frame) -> None:
        action = self._card(parent)
        action.grid(row=3, column=0, sticky="ew", pady=(0, 0))
        action.grid_columnconfigure(0, weight=1)
        action.grid_columnconfigure(1, weight=1)
        action.grid_columnconfigure(2, weight=0)

        self._card_title(action, "04 · Сохранение и печать").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        printer_row = tk.Frame(action, bg=PANEL_2, highlightbackground=BORDER_SOFT, highlightthickness=1)
        printer_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        printer_row.configure(padx=10, pady=8)
        printer_row.grid_columnconfigure(1, weight=1)
        ttk.Label(printer_row, text="Принтер", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.printer_combo = ttk.Combobox(
            printer_row,
            textvariable=self.printer_var,
            values=[],
            state="readonly",
            font=("Segoe UI", 10),
        )
        self.printer_combo.grid(row=0, column=1, sticky="ew", ipady=4)
        self.printer_combo.bind("<<ComboboxSelected>>", self._on_printer_selected)
        ttk.Button(printer_row, text="Обновить", command=self.refresh_printers, style="Dark.TButton").grid(
            row=0, column=2, sticky="e", padx=(10, 0)
        )

        ttk.Button(
            action,
            text="СОЗДАТЬ И СОХРАНИТЬ БЕЗ ПЕЧАТИ",
            command=lambda: self.create_selected_outputs(print_after=False),
            style="Green.TButton",
        ).grid(row=2, column=0, sticky="ew", ipady=12, padx=(0, 8))

        ttk.Button(
            action,
            text="СОЗДАТЬ, СОХРАНИТЬ, РАСПЕЧАТАТЬ",
            command=lambda: self.create_selected_outputs(print_after=True),
            style="Accent.TButton",
        ).grid(row=2, column=1, sticky="ew", ipady=12, padx=(8, 14))

        self.progress = ttk.Progressbar(action, mode="indeterminate", style="Horizontal.TProgressbar", length=180)
        self.progress.grid(row=2, column=2, sticky="e")
        self.status_label = ttk.Label(action, text="Готово", style="Muted.TLabel")
        self.status_label.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))

    # Блоки "Настройки дневников", "Предпросмотр пациента" и "Журнал" намеренно не строятся в UI.
    # Их функционал сохранён скрытыми переменными и служебным буфером.

    def _on_output_toggle(self, kind: str) -> None:
        """Открывает маленькие окна реквизитов при включении специальных документов."""
        if kind == "commission" and self.output_vars[kind].get():
            if not self._prompt_commission_details():
                self.output_vars[kind].set(False)
        elif kind == "rvk" and self.output_vars[kind].get():
            if not self._prompt_rvk_details():
                self.output_vars[kind].set(False)
        elif kind == "vk_mse" and self.output_vars[kind].get():
            if not self._prompt_vk_mse_details():
                self.output_vars[kind].set(False)
        elif kind == "sick_leave_vk" and self.output_vars[kind].get():
            if not self._prompt_sick_leave_vk_details():
                self.output_vars[kind].set(False)

    def _today_str(self) -> str:
        return datetime.now().strftime(DATE_FMT)

    def _default_committee_date(self) -> str:
        """Дата, которая автоматически предлагается во всех popup-окнах комиссии/ВК."""
        candidates = (
            self._last_committee_date,
            self.vk_date_var.get().strip(),
            self.sick_leave_vk_commission_date_var.get().strip(),
            self.sick_leave_vk_date_var.get().strip(),
            self.commission_date_var.get().strip(),
            self.discharge_date_var.get().strip(),
            self.admission_date_var.get().strip(),
        )
        for value in candidates:
            if value:
                return value
        return self._today_str()

    def _default_protocol_date(self, fallback: str | None = None) -> str:
        candidates = (
            self._last_protocol_date,
            self.vk_protocol_date_var.get().strip(),
            self.sick_leave_vk_protocol_date_var.get().strip(),
            fallback or "",
            self._default_committee_date(),
        )
        for value in candidates:
            if value:
                return value
        return self._today_str()

    def _remember_committee_dates(self, *, committee_date: str | None = None, protocol_date: str | None = None) -> None:
        if committee_date:
            self._last_committee_date = committee_date.strip()
        if protocol_date:
            self._last_protocol_date = protocol_date.strip()

    def _prompt_commission_details(self) -> bool:
        date_default = self.commission_date_var.get().strip() or self._default_committee_date()
        values = self._prompt_fields(
            title="Совместный осмотр",
            rows=[
                ("Дата / дата проведения комиссии", date_default),
                ("Номер", self.commission_number_var.get().strip()),
            ],
            linked_groups=[],
        )
        if values is None:
            return False
        self.commission_date_var.set(values[0].strip())
        self.commission_number_var.set(values[1].strip())
        self._remember_committee_dates(committee_date=values[0].strip())
        return all(value.strip() for value in values)

    def _prompt_rvk_details(self) -> bool:
        values = self._prompt_fields(
            title="Акт РВК",
            rows=[
                ("Номер медицинского заключения", self.rvk_act_number_var.get().strip()),
                ("Какой военкомат", self.rvk_military_commissariat_var.get().strip()),
                ("Место работы, должность", self.rvk_work_position_var.get().strip()),
            ],
            width=54,
        )
        if values is None:
            return False
        self.rvk_act_number_var.set(values[0].strip())
        self.rvk_military_commissariat_var.set(values[1].strip())
        self.rvk_work_position_var.set(values[2].strip())
        return all(value.strip() for value in values)

    def _prompt_vk_mse_details(self) -> bool:
        date_default = self.vk_date_var.get().strip() or self._default_committee_date()
        protocol_date_default = self.vk_protocol_date_var.get().strip() or self._default_protocol_date(date_default)
        values = self._prompt_fields(
            title="ВК на МСЭ",
            rows=[
                ("Дата / дата проведения ВК / дата проведения комиссии", date_default),
                ("Протокол номер", self.vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Место работы, должность", self.vk_mse_work_org_var.get().strip()),
            ],
            width=64,
            # Если врач меняет первую дату, поле «От / дата протокола»
            # автоматически получает ту же дату, пока врач сам его не изменил.
            linked_groups=[(0, [2])],
        )
        if values is None:
            return False
        self.vk_date_var.set(values[0].strip())
        self.vk_protocol_number_var.set(values[1].strip())
        self.vk_protocol_date_var.set(values[2].strip())
        self.vk_mse_work_org_var.set(values[3].strip())
        self.vk_mse_position_var.set("")
        self._remember_committee_dates(committee_date=values[0].strip(), protocol_date=values[2].strip())
        return all(value.strip() for value in values)

    def _prompt_sick_leave_vk_details(self) -> bool:
        date_default = self.sick_leave_vk_date_var.get().strip() or self._default_committee_date()
        protocol_date_default = self.sick_leave_vk_protocol_date_var.get().strip() or self._default_protocol_date(date_default)
        commission_date_default = self.sick_leave_vk_commission_date_var.get().strip() or date_default
        values = self._prompt_fields(
            title="ВК больничный",
            rows=[
                ("Дата / дата проведения ВК", date_default),
                ("Номер протокола", self.sick_leave_vk_protocol_number_var.get().strip()),
                ("От / дата протокола / Дата протокола", protocol_date_default),
                ("Дата проведения комиссии", commission_date_default),
                ("Место работы, должность", self.sick_leave_vk_work_position_var.get().strip()),
            ],
            width=54,
            # Первая дата автоматически дублируется в «От» и в
            # «Дата проведения комиссии», но оба поля можно изменить вручную.
            linked_groups=[(0, [2, 3])],
        )
        if values is None:
            return False
        self.sick_leave_vk_date_var.set(values[0].strip())
        self.sick_leave_vk_protocol_number_var.set(values[1].strip())
        self.sick_leave_vk_protocol_date_var.set(values[2].strip())
        self.sick_leave_vk_commission_date_var.set(values[3].strip())
        self.sick_leave_vk_work_position_var.set(values[4].strip())
        self._remember_committee_dates(committee_date=values[3].strip() or values[0].strip(), protocol_date=values[2].strip())
        return all(value.strip() for value in values)

    def _on_primary_document_type_changed(self) -> None:
        """Реакция на выбор типа первичного документа.

        Для направления на госпитализацию лечения обычно нет в самом файле,
        поэтому сразу просим врача ввести назначенное лечение. Для первичного
        осмотра окно не открывается: лечение читается из блока «План лечения»
        / «Лечение» внутри выбранного документа.
        """
        if self.primary_document_type_var.get() == "hospitalization_referral":
            self._prompt_assigned_treatment_if_needed(force=True)
        else:
            self.status_label.config(text="Тип источника: первичный осмотр. Лечение будет взято из документа.")

    def _prompt_assigned_treatment_if_needed(self, *, force: bool = False) -> bool:
        if self.primary_document_type_var.get() != "hospitalization_referral":
            return True
        if self.assigned_treatment_var.get().strip() and not force:
            return True
        values = self._prompt_fields(
            title="Назначенное лечение",
            rows=[("Назначенное лечение", self.assigned_treatment_var.get().strip())],
            width=64,
        )
        if values is None:
            return False
        self.assigned_treatment_var.set(values[0].strip())
        ok = bool(self.assigned_treatment_var.get().strip())
        if ok:
            self.status_label.config(text="Назначенное лечение сохранено для направления на госпитализацию.")
        return ok

    def _prompt_fields(
        self,
        *,
        title: str,
        rows: list[tuple[str, str]],
        width: int = 28,
        linked_groups: list[tuple[int, list[int]]] | None = None,
    ) -> list[str] | None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        result: list[str] | None = None
        entries: list[tk.Entry] = []
        entry_vars: list[tk.StringVar] = []
        entry_auto_values: list[str] = []

        body = tk.Frame(win, bg=PANEL, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        for idx, (label, initial) in enumerate(rows, start=1):
            tk.Label(body, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 10)).grid(row=idx, column=0, sticky="w", pady=6)
            var = tk.StringVar(value=initial)
            entry = tk.Entry(
                body,
                textvariable=var,
                bg=FIELD,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                width=width,
                font=("Segoe UI", 10),
                highlightbackground=FIELD_BORDER,
                highlightcolor=ACCENT,
                highlightthickness=1,
            )
            entry.grid(row=idx, column=1, sticky="ew", padx=(12, 0), ipady=6, pady=6)
            entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
            entries.append(entry)
            entry_vars.append(var)
            entry_auto_values.append(initial)
        body.grid_columnconfigure(1, weight=1)

        # Автодублирование связанных дат.
        # Пример: врач меняет «Дата проведения ВК», а «От / дата протокола»
        # и «Дата проведения комиссии» получают ту же дату, пока врач не изменил
        # их вручную. Если изменил — программа больше их не трогает.
        if linked_groups:
            def mirror_from(source_index: int, target_indices: list[int]) -> None:
                if source_index >= len(entry_vars):
                    return
                source_value = entry_vars[source_index].get().strip()
                for target_index in target_indices:
                    if target_index >= len(entry_vars):
                        continue
                    current_value = entry_vars[target_index].get().strip()
                    previous_auto = entry_auto_values[target_index].strip()
                    if not current_value or current_value == previous_auto:
                        entry_vars[target_index].set(source_value)
                        entry_auto_values[target_index] = source_value

            for source_index, target_indices in linked_groups:
                if source_index < len(entry_vars):
                    entry_vars[source_index].trace_add(
                        "write",
                        lambda *_args, si=source_index, ti=target_indices: mirror_from(si, ti),
                    )
                    # Первичное дублирование сразу при открытии окна.
                    mirror_from(source_index, target_indices)

        error_label = tk.Label(body, text="", bg=PANEL, fg=ERROR, font=("Segoe UI", 9))
        error_label.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        buttons.grid_columnconfigure(0, weight=1)

        def ok() -> None:
            nonlocal result
            values = [entry.get().strip() for entry in entries]
            if not all(values):
                error_label.config(text="Заполните все поля.")
                return
            result = values
            win.destroy()

        def cancel() -> None:
            win.destroy()

        tk.Button(buttons, text="ОК", command=ok, bg=ACCENT_2, fg="#03101f", relief="flat", padx=18, pady=8, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="e", padx=(0, 8))
        tk.Button(buttons, text="Отмена", command=cancel, bg=PANEL_3, fg=TEXT, relief="flat", padx=18, pady=8, font=("Segoe UI", 10)).grid(row=0, column=1, sticky="e")

        entries[0].focus_set()
        win.bind("<Return>", lambda _event: ok())
        win.bind("<Escape>", lambda _event: cancel())
        self.root.wait_window(win)
        return result

    def _card(self, parent) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PANEL,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER,
            highlightthickness=1,
            padx=18,
            pady=15,
        )

    def _pill(self, parent, text: str, color: str) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=color,
            fg="#03101f",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
        )

    def _card_title(self, parent, title: str, subtitle: str = "") -> tk.Frame:
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid_columnconfigure(1, weight=1)
        tk.Label(frame, text="", bg=ACCENT_2, width=1).grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        ttk.Label(frame, text=title, style="Card.TLabel", font=("Segoe UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        return frame

    def _field(self, parent, label: str, variable: tk.StringVar, *, row: int, col: int, colspan: int = 1, placeholder: str = "") -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=(0 if col == 0 else 8, 0), pady=2)
        box.grid_columnconfigure(0, weight=1)
        ttk.Label(box, text=label, style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        entry = tk.Entry(box, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1)
        entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        entry.grid(row=1, column=0, sticky="ew", ipady=7, pady=(5, 0))

    def _output_folder_group(self, parent, *, row: int, col: int, colspan: int = 1) -> None:
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, rowspan=2, sticky="nsew", padx=(10, 0), pady=2)
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(2, weight=0)
        ttk.Label(box, text="Папка результата", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        entry = tk.Entry(
            box,
            textvariable=self.output_dir_var,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10),
            highlightbackground=FIELD_BORDER,
            highlightcolor=ACCENT,
            highlightthickness=1,
        )
        entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        entry.grid(row=1, column=0, sticky="ew", ipady=7, pady=(5, 0))
        tk.Frame(box, bg=BORDER_SOFT, width=2).grid(row=1, column=1, sticky="ns", padx=10, pady=(5, 0))
        ttk.Button(box, text="Выбрать папку", command=self.choose_output_dir, style="Dark.TButton").grid(
            row=1, column=2, sticky="e", ipady=3, pady=(5, 0)
        )

    def _diagnosis_field(self, parent, *, row: int, col: int, colspan: int = 1) -> None:
        """Поле диагноза без плавающих окон.

        Предыдущая версия использовала ttk.Combobox + отдельный Toplevel-подсказчик.
        В Tkinter такая связка может перехватывать фокус и визуально «сбивать» UI.
        Здесь используется обычное поле ввода и встроенный список подсказок внутри
        той же карточки пациента: он не уезжает, не забирает окно и не ломает ввод.
        """
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=(0 if col == 0 else 8, 0), pady=2)
        box.grid_columnconfigure(0, weight=1)
        box.grid_columnconfigure(1, weight=0)

        ttk.Label(box, text="Диагноз по МКБ-10, раздел F", style="Card.TLabel", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        self.diagnosis_entry = tk.Entry(
            box,
            textvariable=self.diagnosis_var,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10),
            highlightbackground=FIELD_BORDER,
            highlightcolor=ACCENT,
            highlightthickness=1,
        )
        # Совместимое имя для старых внутренних вызовов.
        self.diagnosis_combo = self.diagnosis_entry
        self.diagnosis_entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        self.diagnosis_entry.grid(row=1, column=0, sticky="ew", ipady=7, pady=(5, 0))
        self.diagnosis_entry.bind("<KeyRelease>", self._on_diagnosis_key_release)
        self.diagnosis_entry.bind("<Return>", self._select_first_diagnosis_match)
        self.diagnosis_entry.bind("<Down>", self._focus_diagnosis_popup)
        self.diagnosis_entry.bind("<Escape>", lambda _event: self._hide_diagnosis_popup())
        self.diagnosis_entry.bind("<FocusOut>", self._schedule_hide_diagnosis_popup)

        ttk.Button(box, text="МКБ-10 F", command=self._open_diagnosis_selector, style="Dark.TButton").grid(
            row=1, column=1, sticky="e", padx=(8, 0), pady=(5, 0)
        )

        self._diagnosis_popup = tk.Frame(box, bg=BORDER, highlightbackground=BORDER, highlightthickness=1)
        self._diagnosis_popup.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._diagnosis_popup.grid_columnconfigure(0, weight=1)
        self._diagnosis_listbox = tk.Listbox(
            self._diagnosis_popup,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground="#03101f",
            activestyle="none",
            font=("Segoe UI", 10),
            height=6,
            bd=0,
            highlightthickness=0,
            exportselection=False,
        )
        self._diagnosis_listbox.grid(row=0, column=0, sticky="ew")
        self._diagnosis_listbox.bind("<ButtonRelease-1>", self._choose_diagnosis_from_popup)
        self._diagnosis_listbox.bind("<Return>", self._choose_diagnosis_from_popup)
        self._diagnosis_listbox.bind("<Escape>", lambda _event: self._hide_diagnosis_popup())
        self._diagnosis_listbox.bind("<FocusOut>", self._schedule_hide_diagnosis_popup)
        self._diagnosis_popup.grid_remove()


    def _on_diagnosis_selected(self, _event=None) -> None:
        self.diagnosis_var.set(self.diagnosis_var.get().strip())
        self._hide_diagnosis_popup()

    def _on_diagnosis_key_release(self, event=None) -> None:
        if event is not None:
            if event.keysym in {"Up", "Left", "Right", "Return", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"}:
                return
            if event.keysym == "Down":
                self._focus_diagnosis_popup(event)
                return

        query = self.diagnosis_var.get().strip()
        display_values = [format_diagnosis(item) for item in search_icd10_f(query, limit=80)]
        if query and display_values:
            self._show_diagnosis_popup(display_values[:12], keep_entry_focus=True)
        else:
            self._hide_diagnosis_popup()

    def _select_first_diagnosis_match(self, _event=None) -> str:
        query = self.diagnosis_var.get().strip()
        matches = search_icd10_f(query, limit=1)
        if matches:
            self._select_diagnosis_value(format_diagnosis(matches[0]))
        return "break"

    def _select_diagnosis_value(self, value: str) -> None:
        self.diagnosis_var.set(value.strip())
        self.diagnosis_entry.icursor(tk.END)
        self._hide_diagnosis_popup()
        self.diagnosis_entry.focus_set()

    def _show_diagnosis_popup(self, values: list[str], *, keep_entry_focus: bool = True) -> None:
        if not values:
            self._hide_diagnosis_popup()
            return
        self._diagnosis_popup_matches = values
        if self._diagnosis_popup is None or self._diagnosis_listbox is None:
            return
        self._diagnosis_listbox.delete(0, tk.END)
        for value in values:
            self._diagnosis_listbox.insert(tk.END, value)
        self._diagnosis_listbox.selection_clear(0, tk.END)
        self._diagnosis_listbox.selection_set(0)
        self._diagnosis_listbox.activate(0)
        self._diagnosis_listbox.configure(height=min(6, max(1, len(values))))
        self._diagnosis_popup.grid()
        if keep_entry_focus:
            self.root.after_idle(lambda: self.diagnosis_entry.focus_set())

    def _choose_diagnosis_from_popup(self, event=None) -> str:
        listbox = self._diagnosis_listbox
        if listbox is None:
            return "break"
        if event is not None and getattr(event, "y", None) is not None:
            index = listbox.nearest(event.y)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(index)
        selection = listbox.curselection()
        if selection:
            self._select_diagnosis_value(listbox.get(selection[0]))
        return "break"

    def _focus_diagnosis_popup(self, _event=None) -> str:
        query = self.diagnosis_var.get().strip()
        values = [format_diagnosis(item) for item in search_icd10_f(query, limit=12)]
        if query and values:
            self._show_diagnosis_popup(values, keep_entry_focus=False)
        if self._diagnosis_listbox is not None:
            self._diagnosis_listbox.focus_set()
            if not self._diagnosis_listbox.curselection() and self._diagnosis_listbox.size():
                self._diagnosis_listbox.selection_set(0)
                self._diagnosis_listbox.activate(0)
        return "break"

    def _schedule_hide_diagnosis_popup(self, _event=None) -> None:
        self.root.after(180, self._hide_diagnosis_popup_if_focus_left)

    def _hide_diagnosis_popup_if_focus_left(self) -> None:
        focus = self.root.focus_get()
        if focus in {self.diagnosis_entry, self._diagnosis_listbox}:
            return
        self._hide_diagnosis_popup()

    def _hide_diagnosis_popup(self) -> None:
        if self._diagnosis_popup is not None:
            self._diagnosis_popup.grid_remove()

    def _open_diagnosis_selector(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Выбор диагноза: МКБ-10, раздел F")
        win.configure(bg=PANEL)
        win.geometry("720x520")
        win.minsize(620, 440)
        win.transient(self.root)
        win.grab_set()

        body = tk.Frame(win, bg=PANEL, padx=16, pady=14)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tk.Label(
            body,
            text="МКБ-10: психические расстройства и расстройства поведения, F00-F99",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            body,
            text="Введите код, цифры кода или часть названия. Например: 41, F41.2, тревож, шизо.",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w", pady=(2, 10))

        search_var = tk.StringVar(value=self.diagnosis_var.get().strip())
        search_entry = tk.Entry(body, textvariable=search_var, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 11), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1)
        search_entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        search_entry.grid(row=2, column=0, sticky="new", ipady=7)

        list_frame = tk.Frame(body, bg=PANEL)
        list_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        scrollbar = tk.Scrollbar(list_frame)
        listbox = tk.Listbox(
            list_frame,
            bg=FIELD,
            fg=TEXT,
            selectbackground=ACCENT,
            selectforeground="#03101f",
            activestyle="none",
            font=("Segoe UI", 10),
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=listbox.yview)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        current_matches = []

        def refresh(*_args) -> None:
            nonlocal current_matches
            current_matches = search_icd10_f(search_var.get(), limit=300)
            listbox.delete(0, tk.END)
            for item in current_matches:
                listbox.insert(tk.END, format_diagnosis(item))
            if current_matches:
                listbox.selection_set(0)
                listbox.activate(0)

        def choose() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            value = listbox.get(selection[0])
            self.diagnosis_var.set(value)
            self._hide_diagnosis_popup()
            win.destroy()

        buttons = tk.Frame(body, bg=PANEL)
        buttons.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        buttons.grid_columnconfigure(0, weight=1)
        tk.Button(
            buttons,
            text="Выбрать диагноз",
            command=choose,
            bg=ACCENT_2,
            fg="#03101f",
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="e", padx=(0, 8))
        tk.Button(
            buttons,
            text="Отмена",
            command=win.destroy,
            bg=PANEL_3,
            fg=TEXT,
            relief="flat",
            padx=18,
            pady=8,
            font=("Segoe UI", 10),
        ).grid(row=0, column=1, sticky="e")

        search_var.trace_add("write", refresh)
        listbox.bind("<Double-Button-1>", lambda _event: choose())
        listbox.bind("<Return>", lambda _event: choose())
        search_entry.bind("<Return>", lambda _event: choose())
        win.bind("<Escape>", lambda _event: win.destroy())

        refresh()
        search_entry.focus_set()
        self.root.wait_window(win)

    def _file_row(self, parent, row: int, label: str, variable: tk.StringVar, command, button_text: str, *, optional: bool = False) -> None:
        ttk.Label(parent, text=f"{label}{' (необязательно)' if optional else ''}", style="Card.TLabel", wraplength=150).grid(row=row, column=0, sticky="w", pady=3)
        entry = tk.Entry(parent, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10), highlightbackground=FIELD_BORDER, highlightcolor=ACCENT, highlightthickness=1)
        entry.bind("<Control-KeyPress>", self._entry_control_shortcut, add="+")
        entry.grid(row=row, column=1, sticky="ew", padx=10, ipady=5, pady=3)
        ttk.Button(parent, text=button_text, command=command, style="Dark.TButton").grid(row=row, column=2, sticky="e", pady=3)

    # ------------------------------------------------------------------ file choices
    def choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку результата")
        if path:
            self.output_dir_var.set(path)

    def choose_navigation(self) -> None:
        path = filedialog.askopenfilename(title="Выберите первичный документ", filetypes=[("Word DOCX", "*.docx")])
        if not path:
            return
        self.navigation_path_var.set(path)
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(Path(path).parent))
        if self.primary_document_type_var.get() == "hospitalization_referral":
            # Направление не содержит полноценного блока лечения. Сразу просим
            # назначенное лечение и затем используем его во всех документах.
            self._prompt_assigned_treatment_if_needed(force=False)
        self.reparse_navigation()

    def choose_epi(self) -> None:
        path = filedialog.askopenfilename(title="Выберите файл ЭПИ", filetypes=[("Word DOCX", "*.docx"), ("Text", "*.txt"), ("All files", "*.*")])
        if path:
            self.epi_path_var.set(path)
            self.reparse_navigation(silent=True)

    def choose_status_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Выберите файлы с текстами дневников", filetypes=[("Word DOCX", "*.docx")])
        if not paths:
            return
        self.status_files = list(paths)
        self.status_files_label.config(text=self._short_file_list(self.status_files), foreground=SUCCESS)
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(Path(self.status_files[0]).parent))
        self._log(f"\n✅ Выбраны тексты дневников: {len(self.status_files)} файл(ов).\n")

    def choose_diary_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Выберите таблицы дневников", filetypes=[("Word DOCX", "*.docx")])
        if not paths:
            return
        self.diary_files = list(paths)
        self.diary_files_label.config(text=self._short_file_list(self.diary_files), foreground=SUCCESS)
        if not self.output_dir_var.get().strip():
            self.output_dir_var.set(str(Path(self.diary_files[0]).parent))
        detected_start = detect_first_month_year_from_docx(self.diary_files[0])
        if detected_start is not None:
            detected_value = format_month_year(*detected_start)
            if not self._manual_admission_date or not self.admission_date_var.get().strip():
                self._set_ui_var(self.admission_date_var, detected_value)
                self._log(f"\nℹ️ В таблице найдено поступление: {detected_value}\n")
            else:
                self._log(f"\nℹ️ В таблице найдено поступление: {detected_value}; ручная дата в UI сохранена.\n")
        self._log(f"✅ Выбраны таблицы дневников: {len(self.diary_files)} файл(ов).\n")

    def _short_file_list(self, paths: List[str], limit: int = 3) -> str:
        names = [Path(path).name for path in paths]
        if len(names) <= limit:
            return "\n".join(names)
        return "\n".join(names[:limit]) + f"\n… ещё {len(names) - limit}"

    # ------------------------------------------------------------------ printer logic
    def refresh_printers(self) -> None:
        """Обновить список системных принтеров и восстановить выбранный ранее."""
        printers = list_printers()
        self.available_printers = printers
        if hasattr(self, "printer_combo"):
            self.printer_combo.configure(values=printers)
        current = self.printer_var.get().strip()
        saved = str(self._settings.get("printer", "")).strip()
        if printers:
            default = get_default_printer()
            if current in printers:
                chosen = current
            elif saved in printers:
                chosen = saved
            elif default in printers:
                chosen = default
            else:
                chosen = printers[0]
            self.printer_var.set(chosen)
            self._log(f"\n🖨 Найдены принтеры: {len(printers)}. Выбран: {chosen}\n")
        else:
            self.printer_var.set("")
            self._log("\n🖨 Принтеры не найдены. Печать доступна в Windows при установленном принтере.\n")

    def _on_printer_selected(self, _event=None) -> None:
        selected = self.printer_var.get().strip()
        if selected:
            self._settings["printer"] = selected
            self._save_settings()
            self._log(f"\n🖨 Принтер сохранён: {selected}\n")

    # ------------------------------------------------------------------ selection
    def selected_medical_docs(self) -> List[str]:
        return [kind for kind in DOCUMENT_ORDER if self.output_vars[kind].get()]

    def diaries_selected(self) -> bool:
        return bool(self.output_vars[DIARY_KIND].get())

    def create_selected_outputs(self, *, print_after: bool = False) -> None:
        selected_medical = self.selected_medical_docs()
        selected_diaries = self.diaries_selected()
        if not selected_medical and not selected_diaries:
            messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы один документ или «Дневники наблюдения».")
            return
        if "commission" in selected_medical and not all([
            self.commission_date_var.get().strip(),
            self.commission_number_var.get().strip(),
        ]):
            if not self._prompt_commission_details():
                return
        if "rvk" in selected_medical and not all([
            self.rvk_act_number_var.get().strip(),
            self.rvk_military_commissariat_var.get().strip(),
            self.rvk_work_position_var.get().strip(),
        ]):
            if not self._prompt_rvk_details():
                return
        if "vk_mse" in selected_medical and not all([
            self.vk_date_var.get().strip(),
            self.vk_protocol_number_var.get().strip(),
            self.vk_protocol_date_var.get().strip(),
            self.vk_mse_work_org_var.get().strip(),
        ]):
            if not self._prompt_vk_mse_details():
                return
        if "sick_leave_vk" in selected_medical and not all([
            self.sick_leave_vk_date_var.get().strip(),
            self.sick_leave_vk_protocol_number_var.get().strip(),
            self.sick_leave_vk_protocol_date_var.get().strip(),
            self.sick_leave_vk_commission_date_var.get().strip(),
            self.sick_leave_vk_work_position_var.get().strip(),
        ]):
            if not self._prompt_sick_leave_vk_details():
                return
        if selected_medical and self.primary_document_type_var.get() == "hospitalization_referral":
            if not self._prompt_assigned_treatment_if_needed(force=False):
                return
        if print_after and not self.printer_var.get().strip():
            self.refresh_printers()
            if not self.printer_var.get().strip():
                messagebox.showwarning("Принтер не выбран", "Выберите принтер перед печатью или используйте кнопку сохранения без печати.")
                return

        self._start_progress()
        created_medical: List[Path] = []
        diary_result = None
        errors: List[str] = []

        try:
            if selected_medical:
                try:
                    created_medical = self._create_medical_documents_impl(selected_medical)
                except Exception as exc:
                    errors.append(f"Медицинские документы: {exc}")
                    self._log(f"\n❌ Медицинские документы: {exc}\n")

            if selected_diaries:
                try:
                    diary_result = self._create_diaries_impl()
                except Exception as exc:
                    errors.append(f"Дневники: {exc}")
                    self._log(f"\n❌ Дневники: {exc}\n")
        finally:
            self._stop_progress()

        if errors:
            messagebox.showwarning("Готово с ошибками", "Часть задач не выполнена:\n\n" + "\n".join(errors))
            return

        created_files: List[Path] = list(created_medical)
        if diary_result is not None:
            created_files.extend(list(diary_result.created_files))

        print_result = None
        if print_after:
            self._set_status("Отправляю документы на печать...")
            self.root.update_idletasks()
            print_result = print_files(created_files, self.printer_var.get().strip())
            if print_result.errors:
                messagebox.showwarning(
                    "Создано, но печать с ошибками",
                    "Файлы сохранены, но часть документов не удалось отправить на печать:\n\n"
                    + "\n".join(print_result.errors[:10])
                )

        parts: List[str] = []
        if created_medical:
            parts.append("Медицинские документы:\n" + "\n".join(path.name for path in created_medical))
        if diary_result is not None:
            parts.append(f"Дневники: {diary_result.processed_files} файл(ов).")
        if print_after and print_result is not None:
            parts.append(f"Печать: отправлено {len(print_result.printed_files)} файл(ов) на принтер: {self.printer_var.get().strip()}")
        if parts:
            messagebox.showinfo("Готово", "\n\n".join(parts))

    # ------------------------------------------------------------------ medical logic
    def _check_templates(self) -> None:
        missing = self.service.missing_templates()
        if missing:
            self._log("\n❌ Не найдены встроенные шаблоны:\n")
            for path in missing:
                self._log(f"- {path}\n")
            self._log("Проверьте папку templates рядом с программой или сборку EXE с --add-data.\n")
        else:
            self._log("\n✅ Встроенные медицинские шаблоны найдены.\n")

    def reparse_navigation(self, *, silent: bool = False) -> None:
        path = self.navigation_path_var.get().strip()
        if not path:
            if not silent:
                messagebox.showwarning("Нет файла", "Сначала выберите первичный документ.")
            return
        try:
            data = self.service.parse_primary_document(path)
            if self.primary_document_type_var.get() == "hospitalization_referral":
                data.input_document_kind = "направление на госпитализацию"
                if self.assigned_treatment_var.get().strip():
                    data.treatment_plan = self.assigned_treatment_var.get().strip()
            elif self.primary_document_type_var.get() == "primary_exam":
                data.input_document_kind = "первичный осмотр"
            if self.epi_path_var.get().strip() and Path(self.epi_path_var.get().strip()).exists():
                data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
            data.discharge_date = self.discharge_date_var.get().strip()
            self.data = data
            # ФИО из первичного документа подтягивается в UI только как имя файлов.
            # Ручная правка этого UI-поля НЕ подменяет ФИО внутри документов.
            if data.fio and (not self._manual_patient_name or not self.patient_name_var.get().strip()):
                self._set_ui_var(self.patient_name_var, data.fio)
            if data.admission_date and (not self._manual_admission_date or not self.admission_date_var.get().strip()):
                self._set_ui_var(self.admission_date_var, data.admission_date)
            if data.diagnosis and (not self._manual_diagnosis or not self.diagnosis_var.get().strip()):
                self._set_ui_var(self.diagnosis_var, data.diagnosis)
            self._set_preview(format_preview(data))
            self._log(f"\n✅ Первичный документ прочитан ({data.input_document_kind or 'тип не определён'}). Данные подтянуты в общую карточку пациента.\n")
        except Exception as exc:
            self._show_error("Не удалось прочитать первичный документ", exc)

    def _medical_override_data(self, navigation: str) -> PatientData:
        data = self.service.parse_primary_document(navigation)
        selected_source_type = self.primary_document_type_var.get()
        if selected_source_type == "hospitalization_referral":
            data.input_document_kind = "направление на госпитализацию"
            # Для направления лечение вводится вручную через UI, потому что
            # в самом направлении блока «План лечения» может не быть.
            if self.assigned_treatment_var.get().strip():
                data.treatment_plan = self.assigned_treatment_var.get().strip()
        elif selected_source_type == "primary_exam":
            data.input_document_kind = "первичный осмотр"
        # UI-ФИО используется только для имени создаваемых файлов.
        # ФИО внутри документов не подменяется вручную введённым названием файла.
        data.output_fio = self.patient_name_var.get().strip() or data.fio
        # UI имеет приоритет только для дат и диагноза.
        if self.admission_date_var.get().strip():
            value = self.admission_date_var.get().strip()
            if parse_date(value):
                data.admission_date = value
        if self.discharge_date_var.get().strip():
            data.discharge_date = self.discharge_date_var.get().strip()
        if self.diagnosis_var.get().strip():
            data.diagnosis = self.diagnosis_var.get().strip()
        if self.epi_path_var.get().strip():
            data.epi_text = self.service.load_epi_text(self.epi_path_var.get().strip())
        else:
            data.epi_text = ""
        data.rvk_act_number = self.rvk_act_number_var.get().strip()
        data.rvk_military_commissariat = self.rvk_military_commissariat_var.get().strip()
        data.rvk_work_position = self.rvk_work_position_var.get().strip()
        data.vk_date = self.vk_date_var.get().strip()
        data.vk_protocol_number = self.vk_protocol_number_var.get().strip()
        data.vk_protocol_date = self.vk_protocol_date_var.get().strip()
        data.vk_mse_work_org = self.vk_mse_work_org_var.get().strip()
        data.vk_mse_position = self.vk_mse_position_var.get().strip()
        data.sick_leave_vk_date = self.sick_leave_vk_date_var.get().strip()
        data.sick_leave_vk_protocol_number = self.sick_leave_vk_protocol_number_var.get().strip()
        data.sick_leave_vk_protocol_date = self.sick_leave_vk_protocol_date_var.get().strip()
        data.sick_leave_vk_commission_date = self.sick_leave_vk_commission_date_var.get().strip()
        data.sick_leave_vk_work_position = self.sick_leave_vk_work_position_var.get().strip()
        data.commission_date = self.commission_date_var.get().strip()
        data.commission_number = self.commission_number_var.get().strip()
        return data

    def _create_medical_documents_impl(self, selected_docs: List[str]) -> List[Path]:
        navigation = self.navigation_path_var.get().strip()
        if not navigation or not Path(navigation).exists():
            raise ValueError("Выберите первичный документ: направление на госпитализацию или первичный осмотр.")
        discharge = self.discharge_date_var.get().strip()
        if discharge and not parse_date(discharge):
            raise ValueError("Дата выписки должна быть в формате ДД.ММ.ГГГГ.")
        missing_templates = [bundled_template_path(kind) for kind in selected_docs if not bundled_template_path(kind).exists()]
        if missing_templates:
            raise FileNotFoundError("Не найдены шаблоны:\n" + "\n".join(str(path) for path in missing_templates))
        out_dir = self.output_dir_var.get().strip() or str(Path(navigation).parent)
        data = self._medical_override_data(navigation)
        missing = data.missing_critical_fields()
        if missing:
            msg = "Не найдены критические поля: " + ", ".join(missing)
            if self.strict_mode_var.get():
                raise ValueError(msg + ". Проверьте, что выбран заполненный файл пациента, а не пустой шаблон.")
            if not messagebox.askyesno("Есть пропуски", msg + "\n\nПродолжить медицинские документы всё равно?"):
                raise RuntimeError("Создание медицинских документов отменено пользователем.")
        created, used_data = self.service.create_documents(
            navigation_path=navigation,
            output_dir=out_dir,
            discharge_date=discharge,
            epi_path=self.epi_path_var.get().strip() or None,
            selected_docs=selected_docs,
            override_data=data,
        )
        self._set_preview(format_preview(used_data))
        self._log("\n✅ Созданы медицинские документы:\n")
        for path in created:
            self._log(f"- {path}\n")
        return list(created)

    # Оставлены как совместимые методы на случай горячих клавиш/старых вызовов.
    def create_medical_documents(self) -> None:
        selected = self.selected_medical_docs()
        if not selected:
            messagebox.showwarning("Нет документов", "Отметьте хотя бы один медицинский документ.")
            return
        self.output_vars[DIARY_KIND].set(False)
        self.create_selected_outputs()

    # ------------------------------------------------------------------ diary logic
    def _create_diaries_impl(self):
        if not self.diary_files:
            raise ValueError("Выберите файлы-таблицы дневников.")
        diary_patient_name = self.patient_name_var.get().strip()
        source_patient_fio = ""
        if self.navigation_path_var.get().strip():
            try:
                parsed_for_name = self.service.parse_primary_document(self.navigation_path_var.get().strip())
                source_patient_fio = parsed_for_name.fio.strip()
                if not diary_patient_name and source_patient_fio:
                    diary_patient_name = source_patient_fio
                    self._set_ui_var(self.patient_name_var, diary_patient_name)
            except Exception:
                source_patient_fio = ""
        if not diary_patient_name:
            raise ValueError("Введите ФИО для названия файлов или выберите первичный документ с ФИО пациента.")
        out_dir = self.output_dir_var.get().strip() or str(Path(self.diary_files[0]).parent)
        result = fill_diary_batch(
            status_files=self.status_files,
            diary_files=self.diary_files,
            output_dir=out_dir,
            patient_name=diary_patient_name,
            admission_value=self.admission_date_var.get().strip(),
            # Род дневников определяется по ФИО из первичного документа,
            # а UI-ФИО используется только для имени выходного файла.
            gender_source_name=source_patient_fio or diary_patient_name,
            discharge_value=self.discharge_date_var.get().strip(),
            repeat_statuses=self.repeat_statuses_var.get(),
            reset_each_file=self.reset_each_file_var.get(),
            keep_signature=self.keep_signature_var.get(),
            fill_months=self.fill_months_var.get(),
            force_final_diary=self.force_final_diary_var.get(),
            remove_holiday_rows=self.remove_holiday_rows_var.get(),
            open_result_folder=self.open_result_folder_var.get(),
        )
        self._log("\n✅ Дневники заполнены:\n")
        for path in result.created_files:
            self._log(f"- {path}\n")
        self._log(f"Отчёт: {result.report_path}\n")
        self._log(
            f"Итого: файлов {result.processed_files}, дневников {result.filled_rows}, "
            f"дат {result.month_cells_filled}, финальных записей {result.final_rows_filled}, "
            f"удалено после выписки {result.removed_after_discharge_rows}.\n"
        )
        return result

    def create_diaries(self) -> None:
        self.output_vars[DIARY_KIND].set(True)
        for kind in DOCUMENT_ORDER:
            self.output_vars[kind].set(False)
        self.create_selected_outputs()

    # ------------------------------------------------------------------ helpers
    def _mark_manual_field(self, field: str) -> None:
        if self._suspend_user_edit_tracking:
            return
        if field == "patient_name":
            self._manual_patient_name = True
        elif field == "admission_date":
            self._manual_admission_date = True
        elif field == "discharge_date":
            self._manual_discharge_date = True
        elif field == "diagnosis":
            self._manual_diagnosis = True

    def _set_ui_var(self, variable: tk.StringVar, value: str) -> None:
        self._suspend_user_edit_tracking = True
        try:
            variable.set(value)
        finally:
            self._suspend_user_edit_tracking = False

    def _set_preview(self, text: str) -> None:
        self._last_preview_text = text

    def _log(self, text: str) -> None:
        self._log_buffer.append(text)
        if hasattr(self, "status_label"):
            # В UI оставляем только короткий статус, без отдельного окна журнала.
            clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
            if clean_lines:
                self.status_label.config(text=clean_lines[-1][:180])

    def _set_status(self, text: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.config(text=text)

    def _start_progress(self) -> None:
        if hasattr(self, "progress"):
            self.progress.start(12)
        if hasattr(self, "status_label"):
            self.status_label.config(text="Создаю отмеченные документы...")
        self.root.update_idletasks()

    def _stop_progress(self) -> None:
        if hasattr(self, "progress"):
            self.progress.stop()
        if hasattr(self, "status_label"):
            self.status_label.config(text="Готово")
        self.root.update_idletasks()

    def _show_error(self, title: str, exc: Exception) -> None:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self._log(f"\n❌ {title}: {exc}\n{details}\n")
        messagebox.showerror(title, str(exc))


def main() -> None:
    root = tk.Tk()
    CombinedMedicalDiaryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
