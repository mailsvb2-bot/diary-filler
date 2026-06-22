from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import *


class LayoutActionBarMixin:
    def _build_action_bar(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "04", "printer", "Сохранение\nи печать")
        section.grid(row=4, column=0, sticky="ew")

        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)
        body.grid_rowconfigure(2, weight=1)
        body.grid_columnconfigure(0, weight=1)

        action = tk.Frame(body, bg=PANEL)
        action.grid(row=1, column=0, sticky="ew")
        action.grid_columnconfigure(0, weight=1)
        action.grid_columnconfigure(1, weight=0, minsize=self._px(368, 300 if self._compact_ui else 280))
        action.grid_rowconfigure(0, weight=1)

        # В блоке 04 выравниваем всё относительно краёв контентной области:
        # общий content-frame центрируется по вертикали, а левая и правая части
        # живут в одной двухстрочной сетке с согласованными отступами.
        grid = tk.Frame(action, bg=PANEL)
        grid.grid(row=0, column=0, columnspan=2, sticky="nsew")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=0, minsize=self._px(368, 300 if self._compact_ui else 280))
        grid.grid_rowconfigure(0, weight=1, uniform="action_rows")
        grid.grid_rowconfigure(1, weight=1, uniform="action_rows")

        left = tk.Frame(grid, bg=PANEL)
        left.grid(
            row=0,
            column=0,
            rowspan=2,
            sticky="nsew",
            padx=(0, self._px(18 if self._compact_ui else 28, 9)),
            pady=0,
        )
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1, uniform="left_rows")
        left.grid_rowconfigure(1, weight=1, uniform="left_rows")

        def make_left_row(row: int, title: str, field_widget, command) -> None:
            row_frame = tk.Frame(left, bg=PANEL)
            if row == 0:
                row_frame.grid(row=row, column=0, sticky="nsew", pady=(0, self._px(4, 2)))
            else:
                row_frame.grid(row=row, column=0, sticky="nsew", pady=(self._px(4, 2), 0))
            row_frame.grid_columnconfigure(0, weight=0, minsize=self._px(128, 96))
            row_frame.grid_columnconfigure(1, weight=1)
            row_frame.grid_columnconfigure(2, weight=0)
            tk.Label(row_frame, text=title, bg=PANEL, fg=TEXT, font=self._font(11), anchor="w").grid(
                row=0, column=0, sticky="w", padx=(0, self._px(8, 4))
            )
            field_widget(row_frame).grid(row=0, column=1, sticky="ew", padx=(0, self._px(10, 5)))
            self._small_neon_button(row_frame, text="Выбрать", command=command).grid(row=0, column=2, sticky="ew")

        def output_field(parent_frame):
            return self._rounded_entry_canvas(parent_frame, self.output_dir_var, height=self._px(40, 28), calendar=False, font=self._font(11))

        def printer_field(parent_frame):
            wrap = tk.Frame(parent_frame, bg=PANEL)
            wrap.grid_columnconfigure(0, weight=1)
            self.printer_combo = ttk.Combobox(
                wrap,
                textvariable=self.printer_var,
                values=[],
                state="readonly",
                font=self._font(11),
                style="Printer.TCombobox",
            )
            self.printer_combo.grid(row=0, column=0, sticky="ew", ipady=self._px(5 if self._compact_ui else 9, 3))
            self.printer_combo.bind("<<ComboboxSelected>>", self._on_printer_selected)
            return wrap

        make_left_row(0, "Папка результата", output_field, self.choose_output_dir)
        make_left_row(1, "Принтер", printer_field, self.refresh_printers)

        buttons = tk.Frame(grid, bg=PANEL)
        buttons.grid(row=0, column=1, rowspan=2, sticky="nsew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_rowconfigure(0, weight=1, uniform="action_buttons")
        buttons.grid_rowconfigure(1, weight=1, uniform="action_buttons")

        self._big_action_tile(
            buttons,
            text="Создать и сохранить\nбез печати",
            command=lambda: self.create_selected_outputs(print_after=False),
            kind="save",
        ).grid(row=0, column=0, sticky="nsew", pady=(0, self._px(5, 2)))

        self._big_action_tile(
            buttons,
            text="Создать, сохранить,\nраспечатать",
            command=lambda: self.create_selected_outputs(print_after=True),
            kind="print",
        ).grid(row=1, column=0, sticky="nsew", pady=(self._px(4, 2), 0))

        self.progress = ttk.Progressbar(action, mode="indeterminate", style="Horizontal.TProgressbar", length=180)
        self.status_label = self._status_bar_label

    def _big_action_tile(self, parent, *, text: str, command, kind: str) -> tk.Canvas:
        """Крупная action-кнопка как на «Нужный дизайн», с компактным масштабом."""
        base_height = 44 if self._compact_ui else 86
        canvas = tk.Canvas(parent, height=base_height, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        pointer = {"hover": False, "pressed": False}

        def draw(active: bool = False) -> None:
            canvas.delete("all")
            width = max(self._px(340, 250), canvas.winfo_width())
            height = max(base_height, canvas.winfo_height())
            scale = height / 86
            pressed = bool(pointer["pressed"])
            # При фактическом нажатии большая кнопка получает лёгкий
            # цветовой градиент и короткий верхний блик, без резкой инверсии.
            if kind == "print":
                if pressed:
                    top, bottom, border = "#46d7ff", "#0878b0", "#a4efff"
                    icon_top, icon_bottom = "#5de0ff", "#1188c5"
                elif active:
                    top, bottom, border = "#24c8fb", "#0a83be", "#61e0ff"
                    icon_top, icon_bottom = "#39cff8", "#1593cf"
                else:
                    top, bottom, border = "#1db9ed", "#087ab2", "#38c9f3"
                    icon_top, icon_bottom = "#2eb9e4", "#0f7faf"
                inner = "#82e8ff"
            else:
                if pressed:
                    top, bottom, border = "#1d5d86", "#09243a", "#82e7ff"
                    icon_top, icon_bottom = "#1f638d", "#0c2b47"
                elif active:
                    top, bottom, border = "#153e63", "#0b2238", "#43cef8"
                    icon_top, icon_bottom = "#16466e", "#0c2944"
                else:
                    top, bottom, border = "#123654", "#091d31", "#287eb3"
                    icon_top, icon_bottom = "#123a5f", "#092137"
                inner = "#61d8ff"
            r = self._px(8, 5)
            self._gradient_round_rect(canvas, 1, 1, width - 1, height - 1, r, top, bottom, outline=border, width=1, glow=active or pressed)
            self._round_rect(canvas, 2, 2, width - 2, height - 2, r, fill="", outline=self._mix(inner, bottom, 0.35), width=1)
            if pressed:
                canvas.create_line(self._px(18, 12), self._px(6, 4), width - self._px(18, 12), self._px(6, 4), fill=self._mix("#e0fbff", top, 0.42))
            icon_scale = min(scale, 0.62 if self._compact_ui else scale)
            ix1, iy1 = int(55 * icon_scale), max(5, int((height - 58 * icon_scale) / 2))
            ix2, iy2 = ix1 + int(58 * icon_scale), iy1 + int(58 * icon_scale)
            self._gradient_round_rect(canvas, ix1, iy1, ix2, iy2, self._px(9, 6), icon_top, icon_bottom, outline=border, width=1)
            self._round_rect(canvas, ix1 + 1, iy1 + 1, ix2 - 1, iy2 - 1, self._px(9, 6), fill="", outline=self._mix(inner, icon_bottom, 0.35), width=1)
            # Центрируем пиктограмму строго внутри собственного квадратного блока,
            # а не относительно всей высоты кнопки. На компактной Windows-разметке
            # разница даже в 1–2 px визуально заметна: стрелка «скакивает» вверх/вниз.
            icon_cx, icon_cy = (ix1 + ix2) // 2, (iy1 + iy2) // 2
            if kind == "print":
                self._draw_print_icon(canvas, icon_cx, icon_cy, color=TEXT, scale=0.82 * icon_scale)
            else:
                # Оптический центр стрелки «скачать» чуть правее геометрического центра:
                # из-за левого края стрелки и ширины линии на Windows она визуально уезжала влево.
                # Небольшой X-nudge центрирует именно видимую массу пиктограммы внутри квадрата.
                save_icon_cx = icon_cx + self._px(3, 2)
                self._draw_save_icon(canvas, save_icon_cx, icon_cy, color=TEXT, scale=0.86 * icon_scale)
            canvas.create_text(
                max(int(105 * icon_scale), ix2 + self._px(20, 12)),
                height // 2,
                text=text,
                fill=TEXT,
                justify="left",
                anchor="w",
                font=self._font(12 if self._compact_ui else 13, "bold"),
            )

        def on_enter(_event=None) -> None:
            pointer["hover"] = True
            draw(True)

        def on_leave(_event=None) -> None:
            pointer["hover"] = False
            pointer["pressed"] = False
            draw(False)

        def on_press(_event=None) -> None:
            pointer["pressed"] = True
            draw(pointer["hover"])

        def on_release(_event=None) -> None:
            if pointer["pressed"]:
                pointer["pressed"] = False
                command()
            draw(pointer["hover"])

        canvas.bind("<Configure>", lambda _event: draw(False))
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.after(1, draw)
        return canvas

    def _bind_click_recursive(self, widget, command) -> None:
        widget.bind("<Button-1>", lambda _event: command())
        for child in widget.winfo_children():
            self._bind_click_recursive(child, command)

    def _redraw_selection_controls(self) -> None:
        """Refresh all visual selected states after programmatic state changes."""
        for redraw in list(getattr(self, "_check_tile_redrawers", {}).values()):
            try:
                redraw(False)
            except Exception:
                pass
        for redraw in list(getattr(self, "_state_button_redrawers", [])):
            try:
                redraw(False)
            except Exception:
                pass

    def _on_output_toggle(self, kind: str) -> None:
        """Open required-detail popups when a block-03 tile is enabled.

        Date/treatment popups are merged for the document kinds that need
        them, so the doctor does not get two windows in a row.
        """
        if not self.output_vars[kind].get():
            self._update_selected_outputs_status()
            self._redraw_selection_controls()
            return

        if kind == "discharge":
            if not self._prompt_discharge_output_requirements():
                self.output_vars[kind].set(False)
        elif kind == DIARY_KIND:
            if not self._ensure_discharge_date(prompt_if_needed=True):
                self.output_vars[kind].set(False)
        elif kind == "rvk":
            if not self._prompt_rvk_details():
                self.output_vars[kind].set(False)
        else:
            if kind != DIARY_KIND:
                # Full-primary scan contract: if the uploaded primary DOCX has no
                # explicit treatment row, every medical document tile asks for
                # missing common fields. For hospitalization referrals this must
                # be the full merged set (case number + treatment + diagnosis),
                # not a separate one-field treatment popup followed by another
                # hospitalization popup. Diaries remain excluded here.
                if not self._prompt_common_output_requirements(include_discharge_date=False, include_case_number=True):
                    self.output_vars[kind].set(False)
                    self._update_selected_outputs_status()
                    self._redraw_selection_controls()
                    return
            if kind == "commission":
                if not self._prompt_commission_details():
                    self.output_vars[kind].set(False)
            elif kind == "vk_mse":
                if not self._prompt_vk_mse_details():
                    self.output_vars[kind].set(False)
            elif kind == "sick_leave_vk":
                if not self._prompt_sick_leave_vk_details():
                    self.output_vars[kind].set(False)
        self._update_selected_outputs_status()
        self._redraw_selection_controls()
