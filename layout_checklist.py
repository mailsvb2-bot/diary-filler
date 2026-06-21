from __future__ import annotations

import tkinter as tk

from app_config import *
from medical_constants import DOCUMENT_LABELS


class LayoutChecklistMixin:
    def _build_create_checklist_card(self, parent: tk.Frame) -> None:
        section, body = self._section(parent, "03", "checklist", "Документы\nдля создания")
        section.grid(row=3, column=0, sticky="ew", pady=(0, 3))

        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)
        body.grid_rowconfigure(2, weight=1)
        body.grid_columnconfigure(0, weight=1)

        docs = tk.Frame(body, bg=PANEL)
        docs.grid(row=1, column=0, sticky="ew")
        for col in range(4):
            docs.grid_columnconfigure(col, weight=1)

        display_order = ["discharge", "primary", "commission", "vk_mse", "sick_leave_vk", "rvk", DIARY_KIND, "admission_doctor_referral"]
        labels = {**DOCUMENT_LABELS, DIARY_KIND: DIARY_LABEL}
        icons = {
            "discharge": "doc",
            "primary": "stethoscope",
            "commission": "people",
            "vk_mse": "wheelchair",
            "sick_leave_vk": "clipboard",
            "rvk": "shield",
            "admission_doctor_referral": "doc",
            DIARY_KIND: "book",
        }
        for idx, kind in enumerate(display_order):
            item = self._check_tile(docs, kind=kind, label=labels[kind], icon=icons[kind])
            item.grid(
                row=idx // 4,
                column=idx % 4,
                sticky="ew",
                padx=(0 if idx % 4 == 0 else self._px(12 if self._compact_ui else 19, 6), 0),
                pady=(0 if idx < 4 else self._px(10 if self._compact_ui else 15, 4), 0),
            )

    def _check_tile(self, parent, *, kind: str, label: str, icon: str) -> tk.Canvas:
        """Responsive checklist tile with a clear selected state."""
        height = 34 if self._compact_ui else 64
        canvas = tk.Canvas(parent, height=height, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        scale = max(0.58, height / 64)
        pointer = {"hover": False, "pressed": False}

        def draw(active: bool = False) -> None:
            canvas.delete("all")
            width = max(self._px(180, 145), canvas.winfo_width())
            checked = self.output_vars[kind].get()
            pressed = bool(pointer["pressed"])
            if checked:
                # Выбранное состояние без чекбокса/галочки: нажатые плитки
                # получают лёгкий цветовой градиент, мягкую обводку и
                # тонкую акцентную полосу слева.
                if pressed:
                    top, bottom, border = "#2b7892", "#0d344f", "#a8f0ff"
                elif active:
                    top, bottom, border = "#1d637f", "#0b3049", "#8be6f5"
                else:
                    top, bottom, border = "#15536e", "#08273e", "#63cfe4"
                text_fill = TEXT
                icon_fill = "#c8f5ff"
                marker = "#77def1"
                inner = "#95e8f5"
            else:
                if pressed:
                    top, bottom, border = "#123653", "#071928", "#3eb7df"
                elif active:
                    top, bottom, border = "#0d2236", "#0a1a2a", "#2b80b5"
                else:
                    top, bottom, border = "#091b2b", "#071625", "#173c5c"
                text_fill = TEXT
                icon_fill = ACCENT
                marker = "#58bdd5"
                inner = "#8bd8ec"
            self._gradient_round_rect(
                canvas,
                1,
                1,
                width - 1,
                height - 1,
                self._px(8, 5),
                top,
                bottom,
                outline=border,
                width=1,
                glow=active or pressed,
            )
            if checked:
                self._round_rect(
                    canvas,
                    3,
                    3,
                    width - 3,
                    height - 3,
                    self._px(7, 5),
                    fill="",
                    outline=self._mix(inner, bottom, 0.50),
                    width=1,
                )
                self._round_rect(
                    canvas,
                    self._px(6, 4),
                    self._px(8, 5),
                    self._px(11, 8),
                    height - self._px(8, 5),
                    self._px(3, 2),
                    fill=marker,
                    outline="",
                    width=0,
                )
                canvas.create_line(
                    self._px(16, 11),
                    self._px(5, 4),
                    width - self._px(16, 11),
                    self._px(5, 4),
                    fill=self._mix("#d7fbff", top, 0.45),
                )
            # Чекбокс и галочка удалены: выбранность читается через лёгкий
            # цветной градиент, левую cyan-метку, обводку и цвет иконки.
            icon_x, icon_y = self._px(34, 22), max(5, int(height * 0.23))
            if self._compact_ui and icon == "people":
                # Центрирование по зелёной пометке пользователя.
                people_scale = 0.46
                people_w = 27 * people_scale
                people_h = 29 * people_scale
                icon_x = self._px(34, 22) - int(people_w / 2)
                icon_y = max(4, int(height * 0.5 - people_h / 2))
                self._draw_tile_icon(canvas, icon, icon_x, icon_y, color=icon_fill, scale=people_scale)
            else:
                self._draw_tile_icon(canvas, icon, icon_x, icon_y, color=icon_fill, scale=(0.58 if self._compact_ui else 1.0))
            text_x = self._px(72, 48)
            canvas.create_text(
                text_x,
                height // 2,
                text=label,
                fill=text_fill,
                font=self._font(12, "bold" if checked else None),
                anchor="w",
                width=max(70, width - text_x - self._px(12, 8)),
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
                self._activate_output_tile(kind)
            draw(pointer["hover"])

        canvas.bind("<Configure>", lambda _event: draw(False))
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.after(1, draw)
        self._check_tile_redrawers[kind] = draw
        return canvas

    def _activate_output_tile(self, kind: str) -> None:
        """Toggle a document tile with the discharge/sick-leave guard.

        If the discharge tile is already selected, a click is interpreted as
        an attempt to complete missing discharge requirements, not as a silent
        deselect. First date of discharge is requested, then sick-leave number
        if «Больничный лист: да» is set.
        """
        var = self.output_vars[kind]
        currently_selected = bool(var.get())
        if kind == "discharge" and currently_selected:
            try:
                should_complete_requirements = (
                    self._should_prompt_discharge_date()
                    or self._should_prompt_discharge_sick_leave_number()
                    or self._manual_treatment_missing()
                    or self._hospitalization_details_missing()
                    or self._case_number_missing()
                )
            except Exception:
                should_complete_requirements = False
            if should_complete_requirements:
                self._prompt_discharge_output_requirements()
                self._update_selected_outputs_status()
                self._redraw_selection_controls()
                return

        var.set(not currently_selected)
        self._on_output_toggle(kind)

    def _draw_tile_icon(self, canvas: tk.Canvas, kind: str, x: int, y: int, *, color: str = ACCENT, scale: float = 1.0) -> None:
        """Line icons for document tiles. Coordinates are scaled for compact 1/3-window mode."""
        def xx(v: float) -> float:
            return x + v * scale

        def yy(v: float) -> float:
            return y + v * scale

        w = max(1.0, 1.25 * scale)
        if kind == "doc":
            canvas.create_rectangle(xx(0), yy(0), xx(20), yy(26), outline=color, width=w)
            canvas.create_line(xx(14), yy(0), xx(25), yy(9), xx(25), yy(26), fill=color, width=w)
            canvas.create_line(xx(8), yy(13), xx(16), yy(13), fill=color, width=w)
            canvas.create_line(xx(12), yy(9), xx(12), yy(17), fill=color, width=w)
        elif kind == "stethoscope":
            canvas.create_arc(xx(0), yy(-2), xx(22), yy(23), start=180, extent=180, outline=color, width=w, style="arc")
            canvas.create_line(xx(0), yy(7), xx(0), yy(1), fill=color, width=w)
            canvas.create_line(xx(22), yy(7), xx(22), yy(1), fill=color, width=w)
            canvas.create_line(xx(11), yy(23), xx(11), yy(29), fill=color, width=w)
            canvas.create_oval(xx(17), yy(25), xx(27), yy(35), outline=color, width=w)
        elif kind == "people":
            canvas.create_oval(xx(0), yy(1), xx(9), yy(10), outline=color, width=w)
            canvas.create_oval(xx(13), yy(1), xx(22), yy(10), outline=color, width=w)
            canvas.create_arc(xx(-5), yy(10), xx(14), yy(29), start=0, extent=180, outline=color, width=w, style="arc")
            canvas.create_arc(xx(8), yy(10), xx(27), yy(29), start=0, extent=180, outline=color, width=w, style="arc")
        elif kind == "wheelchair":
            canvas.create_oval(xx(1), yy(16), xx(18), yy(33), outline=color, width=w)
            canvas.create_line(xx(9), yy(0), xx(9), yy(17), xx(23), yy(17), fill=color, width=w)
            canvas.create_line(xx(11), yy(8), xx(22), yy(8), fill=color, width=w)
            canvas.create_line(xx(22), yy(17), xx(28), yy(29), fill=color, width=w)
            canvas.create_oval(xx(7), yy(-4), xx(12), yy(1), outline=color, fill=color)
        elif kind == "clipboard":
            canvas.create_rectangle(xx(3), yy(0), xx(21), yy(28), outline=color, width=w)
            canvas.create_rectangle(xx(8), yy(-4), xx(16), yy(3), outline=color, width=w)
            for pos in (8, 15, 22):
                canvas.create_line(xx(8), yy(pos), xx(18), yy(pos), fill=color, width=max(1.0, 1.2 * scale))
        elif kind == "shield":
            canvas.create_polygon(xx(13), yy(-1), xx(25), yy(4), xx(24), yy(17), xx(13), yy(29), xx(2), yy(17), xx(1), yy(4), fill="", outline=color, width=w)
            canvas.create_line(xx(8), yy(14), xx(12), yy(18), xx(19), yy(10), fill=color, width=w, capstyle="round", joinstyle="round")
        elif kind == "book":
            canvas.create_line(xx(0), yy(4), xx(11), yy(0), xx(14), yy(4), xx(17), yy(0), xx(28), yy(4), xx(28), yy(28), xx(17), yy(24), xx(14), yy(28), xx(11), yy(24), xx(0), yy(28), xx(0), yy(4), fill=color, width=w)
            canvas.create_line(xx(14), yy(4), xx(14), yy(28), fill=color, width=max(1.0, 1.2 * scale))
