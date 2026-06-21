from __future__ import annotations

import tkinter as tk

from app_config import *


class UiButtonsMixin:
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
        """Спокойный заголовок блока: номер + название, без яркого свечения."""
        frame = tk.Frame(parent, bg=PANEL)
        frame.grid_columnconfigure(1, weight=1)
        number = ""
        label = title
        if "·" in title:
            number, label = [part.strip() for part in title.split("·", 1)]
            number = number.lstrip("0") or "0"

        badge = tk.Label(
            frame,
            text=number,
            bg=PANEL_3,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            width=3,
            padx=3,
            pady=3,
        )
        badge.grid(row=0, column=0, sticky="w", padx=(0, 10))

        label_box = tk.Frame(frame, bg=PANEL)
        label_box.grid(row=0, column=1, sticky="ew")
        label_box.grid_columnconfigure(0, weight=1)
        tk.Label(label_box, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        tk.Frame(label_box, bg=BORDER_SOFT, height=1).grid(row=1, column=0, sticky="ew", pady=(5, 0))
        return frame

    def _small_neon_button(self, parent, *, text: str, command, selected=None) -> tk.Canvas:
        """Rounded cyan button with a persistent selected state when needed."""
        if text == "Выбрать":
            width = self._px(154, 124)
        elif text.startswith("МКБ-10"):
            width = self._px(154, 124)
        else:
            width = max(self._px(154, 124), min(self._px(190, 154), self._px(10 * len(text) + 36, 118)))
        height = self._px(40, 30)
        scale = height / 40
        canvas = tk.Canvas(parent, width=width, height=height, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        pointer = {"hover": False, "pressed": False}

        def is_selected() -> bool:
            try:
                return bool(selected()) if callable(selected) else bool(selected)
            except Exception:
                return False

        def draw(active: bool = False) -> None:
            chosen = is_selected()
            pressed = bool(pointer["pressed"])
            canvas.delete("all")
            if chosen:
                # Выбранное состояние без грубой заливки и без галочки:
                # нажатые кнопки получают лёгкий цветовой градиент,
                # мягкую cyan-обводку и тонкую левую метку.
                if pressed:
                    top, bottom, border = "#2a7891", "#0d334d", "#a5eefb"
                elif active:
                    top, bottom, border = "#1d637f", "#0b3049", "#8be6f5"
                else:
                    top, bottom, border = "#15536e", "#08273e", "#63cfe4"
                text_color = TEXT
                icon_color = "#c8f5ff"
                inner = "#93e5f4"
                marker = "#77def1"
                glow = False
                line_width = 1
            else:
                if pressed:
                    top, bottom, border = "#16415f", "#061b2c", "#55c8ec"
                elif active:
                    top, bottom, border = "#0f314a", "#092236", "#2aa4d0"
                else:
                    top, bottom, border = "#0b283f", "#081f33", "#197db3"
                text_color = ACCENT
                icon_color = ACCENT
                inner = "#49bfe0"
                marker = "#58bdd5"
                glow = False
                line_width = 1
            self._gradient_round_rect(
                canvas,
                1,
                1,
                width - 1,
                height - 1,
                self._px(7, 5),
                top,
                bottom,
                outline=border,
                width=line_width,
                glow=glow,
            )
            if chosen:
                self._round_rect(
                    canvas,
                    3,
                    3,
                    width - 3,
                    height - 3,
                    self._px(6, 4),
                    fill="",
                    outline=self._mix(inner, bottom, 0.50),
                    width=1,
                )
                self._round_rect(
                    canvas,
                    self._px(5, 4),
                    self._px(7, 5),
                    self._px(9, 7),
                    height - self._px(7, 5),
                    self._px(3, 2),
                    fill=marker,
                    outline="",
                    width=0,
                )
                canvas.create_line(
                    self._px(13, 10),
                    self._px(5, 4),
                    width - self._px(13, 10),
                    self._px(5, 4),
                    fill=self._mix("#d5fbff", top, 0.45),
                )
            if text == "Выбрать":
                self._draw_folder_icon(canvas, int(25 * scale), int(10 * scale), scale=0.72 * scale, color=icon_color)
                canvas.create_text(
                    int(58 * scale),
                    height // 2,
                    text=text,
                    fill=text_color,
                    font=self._font(12, "bold"),
                    anchor="w",
                )
            else:
                canvas.create_text(
                    width // 2,
                    height // 2,
                    text=text,
                    fill=text_color,
                    font=self._font(12, "bold"),
                    anchor="center",
                )
            # Галочки на выбранных кнопках намеренно не рисуем: состояние
            # видно по лёгкому цветному градиенту, обводке и левой cyan-метке.

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

        draw(False)
        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas._redraw_state = draw  # type: ignore[attr-defined]
        if selected is not None:
            self._state_button_redrawers.append(draw)
        return canvas

    def _big_neon_button(self, parent, *, text: str, command, accent: str) -> tk.Button:
        if accent == PRINT_ACCENT:
            bg = PRINT_ACCENT
            fg = TEXT
            active_bg = PRINT_ACCENT_ACTIVE
            active_fg = TEXT
            border = "#6ed7ff"
        elif accent == SAVE_ACCENT:
            bg = SAVE_ACCENT
            fg = TEXT
            active_bg = SAVE_ACCENT_ACTIVE
            active_fg = TEXT
            border = BORDER
        else:
            bg = PANEL_3
            fg = TEXT
            active_bg = "#173b5a"
            active_fg = TEXT
            border = BORDER_SOFT
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=border,
            padx=14,
            pady=8,
            font=("Segoe UI", 8, "bold"),
            justify="center",
            anchor="center",
            cursor="hand2",
        )
