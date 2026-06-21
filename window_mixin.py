from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import *


class WindowMixin:
    def _build_ui(self) -> None:
        self._setup_style()

        # Нижняя служебная строка убрана по пользовательскому требованию.
        # Скрытый label оставлен как безопасная цель для внутренних _set_status/_log,
        # чтобы callback-контракты UI не ломались, но текст больше не виден в окне.
        self._status_bar_label = tk.Label(self.root, text="", bg=DEEP, fg=MUTED, font=self._font(11))

        shell = tk.Frame(self.root, bg=DEEP, highlightthickness=1, highlightbackground="#123958")
        shell.pack(fill="both", expand=True, padx=0, pady=0)

        content = tk.Frame(shell, bg=DEEP)
        content.pack(fill="both", expand=True, padx=self._px(21, 12), pady=(self._px(14, 7), self._px(10, 4)))

        content.grid_columnconfigure(0, weight=1)
        for row in range(5):
            content.grid_rowconfigure(row, weight=0)
        # Все секции имеют естественную высоту, чтобы блок 03 не схлопывался при нехватке места.

        self._build_header(content)
        # Логичный поток работы: источник данных + распознанные поля пациента,
        # затем дополнительные входные файлы, затем список итоговых документов.
        self._build_patient_card(content)
        self._build_input_files_card(content)
        self._build_create_checklist_card(content)
        self._build_action_bar(content)

    def _px(self, value: int | float, minimum: int = 1) -> int:
        """Pixel helper: сохраняет пропорции референса на компактном окне 1/3 экрана."""
        return max(minimum, int(round(float(value) * getattr(self, "_ui_scale", 1.0))))

    def _font(self, size: int | float, weight: str | None = None) -> tuple:
        scaled = max(8, int(round(float(size) * getattr(self, "_font_scale", 1.0))))
        return ("Segoe UI", scaled, weight) if weight else ("Segoe UI", scaled)

    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        default_font = self._font(10)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=default_font)
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT, font=self._font(11))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=self._font(10))
        style.configure("Header.TLabel", background=DEEP, foreground=TEXT, font=self._font(23, "bold"))
        style.configure("Subheader.TLabel", background=DEEP, foreground=MUTED, font=self._font(12))
        style.configure("Accent.TButton", font=self._font(11, "bold"), foreground="#03101f", background=ACCENT)
        style.map("Accent.TButton", background=[("active", "#7ee3ff")])
        style.configure("Green.TButton", font=self._font(12, "bold"), foreground="#03101f", background=ACCENT_2)
        style.map("Green.TButton", background=[("active", "#8fffd5")])
        style.configure("Dark.TButton", font=self._font(10), foreground=TEXT, background=PANEL_3, borderwidth=0)
        style.map("Dark.TButton", background=[("active", BORDER)], foreground=[("active", TEXT)])
        style.configure("TCheckbutton", background=PANEL_2, foreground=TEXT, font=self._font(11))
        style.map("TCheckbutton", background=[("active", PANEL_2)], foreground=[("active", TEXT)])
        style.configure("TRadiobutton", background=FIELD, foreground=TEXT, font=self._font(11))
        style.map("TRadiobutton", background=[("active", FIELD)], foreground=[("active", TEXT)])

        # Combobox: тёмный стиль под референс, fieldbackground = FIELD
        for combo_style in ("TCombobox", "Printer.TCombobox"):
            style.configure(
                combo_style,
                fieldbackground=FIELD,
                background=FIELD,
                foreground=TEXT,
                arrowcolor=ACCENT,
                bordercolor=FIELD_BORDER,
                lightcolor=FIELD,
                darkcolor=FIELD,
                padding=6,
            )
            style.map(
                combo_style,
                fieldbackground=[("readonly", FIELD), ("!disabled", FIELD)],
                background=[("readonly", FIELD), ("active", PANEL_3), ("!disabled", FIELD)],
                foreground=[("readonly", TEXT), ("!disabled", TEXT)],
                selectbackground=[("readonly", FIELD), ("!disabled", FIELD)],
                selectforeground=[("readonly", TEXT), ("!disabled", TEXT)],
                arrowcolor=[("readonly", ACCENT), ("!disabled", ACCENT)],
            )
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", PANEL_3)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
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

    def _apply_custom_window_chrome(self) -> None:
        """Frameless window like the reference screenshot, with safe fallback for platforms that reject it."""
        try:
            if self.root.state() == "normal":
                self.root.overrideredirect(True)
        except tk.TclError:
            pass

    def _disable_custom_window_chrome(self) -> None:
        """Return a normal Windows shell frame before minimizing.

        Tk/Windows плохо сворачивает окно с overrideredirect(True): приложение может
        исчезать из обычной цепочки окон, а при запуске из .bat на экране остаётся
        только консоль. Поэтому перед minimize временно возвращаем системную рамку,
        а кастомный chrome включаем обратно только после восстановления окна.
        """
        try:
            self.root.overrideredirect(False)
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _restore_custom_window_chrome_after_map(self) -> None:
        try:
            if self.root.state() != "normal":
                return
            self.root.overrideredirect(True)
            self.root.update_idletasks()
            self._custom_chrome_restore_pending = False
        except tk.TclError:
            pass

    def _on_root_mapped(self, event) -> None:
        if getattr(event, "widget", None) is not self.root:
            return
        if not getattr(self, "_custom_chrome_restore_pending", False):
            return
        try:
            if self.root.state() == "normal":
                self.root.after_idle(self._restore_custom_window_chrome_after_map)
        except tk.TclError:
            pass

    def _bind_window_drag(self, widget) -> None:
        widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
        widget.bind("<B1-Motion>", self._move_window_drag, add="+")

    def _start_window_drag(self, event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _move_window_drag(self, event) -> None:
        if self._is_maximized:
            return
        x = self.root.winfo_pointerx() - self._drag_start_x
        y = self.root.winfo_pointery() - self._drag_start_y
        self.root.geometry(f"+{x}+{y}")

    def _minimize_window(self) -> None:
        try:
            self._custom_chrome_restore_pending = True
            self._disable_custom_window_chrome()
            self.root.iconify()
        except tk.TclError:
            try:
                self.root.iconify()
            except tk.TclError:
                pass

    def _toggle_maximize(self) -> None:
        try:
            if self._is_maximized:
                self.root.geometry(self._normal_geometry)
                self._is_maximized = False
                return
            self._normal_geometry = self.root.geometry()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
            self._is_maximized = True
        except tk.TclError:
            pass

    def _window_control_button(self, parent, text: str, command, *, danger: bool = False) -> tk.Canvas:
        width, height = self._px(48, 34), self._px(32, 24)
        c = tk.Canvas(parent, width=width, height=height, bg=DEEP, highlightthickness=0, bd=0, cursor="hand2")
        def draw(active: bool = False) -> None:
            c.delete("all")
            bg = "#2c1018" if danger and active else ("#0d1b2a" if active else DEEP)
            fg = "#ff8ba0" if danger and active else (TEXT if active else MUTED)
            c.create_rectangle(0, 0, width, height, fill=bg, outline=bg)
            c.create_text(width // 2, height // 2 - 1, text=text, fill=fg, font=self._font(18 if text == "×" else 14))
        draw(False)
        c.bind("<Enter>", lambda _e: draw(True))
        c.bind("<Leave>", lambda _e: draw(False))
        c.bind("<Button-1>", lambda _e: command())
        return c

    def _status_shield_icon(self, parent) -> tk.Canvas:
        c = tk.Canvas(parent, width=23, height=23, bg=DEEP, highlightthickness=0, bd=0)
        c.create_polygon(11, 2, 19, 5, 18, 14, 11, 21, 4, 14, 3, 5, fill="", outline=ACCENT, width=1.2)
        c.create_line(7, 11, 10, 14, 16, 7, fill=ACCENT, width=1.4, capstyle="round", joinstyle="round")
        return c

    def _build_header(self, parent: tk.Frame) -> None:
        """Шапка без зачёркнутых элементов: убраны логотип слева и service-icons справа."""
        header = tk.Frame(parent, bg=DEEP, padx=self._px(7, 4), pady=self._px(4, 2))
        header.grid(row=0, column=0, sticky="ew", pady=(0, self._px(10 if self._compact_ui else 13, 6)))
        header.grid_columnconfigure(0, weight=1)
        self._bind_window_drag(header)

        title_box = tk.Frame(header, bg=DEEP)
        title_box.grid(row=0, column=0, sticky="ew", pady=(self._px(2, 0), 0), padx=(self._px(8, 4), 0))
        self._bind_window_drag(title_box)

        title = tk.Label(
            title_box,
            text=APP_TITLE,
            bg=DEEP,
            fg=TEXT,
            font=self._font(21 if self._compact_ui else 23, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            title_box,
            text="Автоматическое заполнение медицинских документов",
            bg=DEEP,
            fg=MUTED,
            font=self._font(11 if self._compact_ui else 12),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(self._px(2, 0), 0))
        self._bind_window_drag(title)
        self._bind_window_drag(subtitle)

        # Оставляем только системные кнопки окна. Зачёркнутые иконки настроек/справки убраны.
        controls = tk.Frame(header, bg=DEEP)
        controls.grid(row=0, column=1, sticky="ne", pady=(0, self._px(18 if self._compact_ui else 22, 7)))
        self._window_control_button(controls, "−", self._minimize_window).grid(row=0, column=0)
        self._window_control_button(controls, "□", self._toggle_maximize).grid(row=0, column=1)
        self._window_control_button(controls, "×", self.root.destroy, danger=True).grid(row=0, column=2)

    def _header_icon_button(self, parent, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=DEEP,
            fg=MUTED,
            activebackground=BG_2,
            activeforeground=ACCENT,
            relief="flat",
            bd=0,
            width=2,
            height=1,
            font=("Segoe UI", 14, "bold"),
            cursor="hand2",
        )

    def _build_patient_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "01", "patient", "Источник\nданных")
        section.grid(row=1, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)

        top = tk.Frame(body, bg=PANEL)
        top.grid(row=0, column=0, sticky="ew", pady=(0, self._px(10, 5)))
        top.grid_columnconfigure(0, weight=1)
        self._source_drop_row(top, 0)

        card = tk.Frame(body, bg=PANEL)
        card.grid(row=1, column=0, sticky="new", pady=(0, self._px(2, 1)))
        card.grid_columnconfigure(0, weight=5)
        card.grid_columnconfigure(1, weight=3)
        card.grid_columnconfigure(2, weight=3)
        card.grid_columnconfigure(3, weight=4)
        card.grid_columnconfigure(4, weight=4)
        card.grid_columnconfigure(5, weight=3)
        card.grid_columnconfigure(6, weight=3)
        card.grid_columnconfigure(7, weight=3)
        card.grid_columnconfigure(8, weight=3)
        card.grid_columnconfigure(9, weight=3)
        card.grid_columnconfigure(10, weight=3)
        card.grid_columnconfigure(11, weight=3)

        self._field(card, "ФИО или название файла", self.patient_name_var, row=0, col=0, colspan=5)
        self._field(card, "Дата поступления", self.admission_date_var, row=0, col=5, colspan=3)
        self._field(card, "Дата выписки", self.discharge_date_var, row=0, col=8, colspan=4)
        self._diagnosis_field(card, row=1, col=0, colspan=8)
        self._sick_leave_need_field(card, row=1, col=8, colspan=4)

    def _build_one_window_workspace(self, parent: tk.Frame) -> None:
        # Оставлено для совместимости со старой внутренней структурой.
        # Новый экран строит секции 02 и 03 напрямую, без двухколоночного разбиения.
        self._build_input_files_card(parent)
        self._build_create_checklist_card(parent)

    def _build_input_files_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "02", "folder", "Входные\nфайлы")
        section.grid(row=2, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)

        files = tk.Frame(body, bg=PANEL)
        files.grid(row=0, column=0, sticky="nsew", pady=(self._px(1, 0), 0))
        files.grid_columnconfigure(0, minsize=self._px(190, 128))
        files.grid_columnconfigure(1, weight=1)
        files.grid_columnconfigure(2, minsize=self._px(146, 104))

        self._file_row(files, 0, "Файл ЭПИ", self.epi_path_var, self.choose_epi, "Выбрать", optional=True)
        self._diary_compact_row(files, 1)
