from __future__ import annotations

import tkinter as tk

from app_config import *


class UiIconsMixin:
    def _draw_folder_icon(self, canvas: tk.Canvas, x: int, y: int, *, scale: float = 1.0, color: str = ACCENT) -> None:
        s = scale
        pts = [
            x, y + 8*s, x + 10*s, y + 8*s, x + 13*s, y + 12*s,
            x + 27*s, y + 12*s, x + 27*s, y + 23*s, x, y + 23*s, x, y + 8*s,
        ]
        canvas.create_line(*pts, fill=color, width=max(1, int(1.5*s)), joinstyle="round")
        canvas.create_line(x + 1*s, y + 13*s, x + 27*s, y + 13*s, fill=color, width=max(1, int(1.4*s)))

    def _draw_print_icon(self, canvas: tk.Canvas, cx: int, cy: int, *, color: str = TEXT, scale: float = 1.0) -> None:
        s = scale
        # more like the reference: white page + printer body + output tray
        w = max(1, int(2*s))
        canvas.create_rectangle(cx-10*s, cy-16*s, cx+10*s, cy-8*s, outline=color, fill="", width=w)
        canvas.create_line(cx-6*s, cy-12*s, cx+6*s, cy-12*s, fill=color, width=w)
        canvas.create_rectangle(cx-15*s, cy-8*s, cx+15*s, cy+5*s, outline=color, fill="", width=w)
        canvas.create_rectangle(cx-10*s, cy+5*s, cx+10*s, cy+15*s, outline=color, fill="", width=w)
        canvas.create_line(cx-8*s, cy+9*s, cx+8*s, cy+9*s, fill=color, width=w)
        canvas.create_oval(cx+10*s, cy-3*s, cx+13*s, cy, outline=color, fill=color)

    def _draw_save_icon(self, canvas: tk.Canvas, cx: int, cy: int, *, color: str = TEXT, scale: float = 1.0) -> None:
        s = scale
        w = max(2, int(2.4*s))
        # download arrow into tray, closer to the reference
        canvas.create_line(cx, cy-15*s, cx, cy+2*s, fill=color, width=w, capstyle="round")
        canvas.create_line(cx-8*s, cy-4*s, cx, cy+5*s, cx+8*s, cy-4*s, fill=color, width=w, capstyle="round", joinstyle="round")
        canvas.create_line(cx-12*s, cy+12*s, cx+12*s, cy+12*s, fill=color, width=w, capstyle="round")
        canvas.create_line(cx-12*s, cy+12*s, cx-12*s, cy+8*s, fill=color, width=w, capstyle="round")
        canvas.create_line(cx+12*s, cy+12*s, cx+12*s, cy+8*s, fill=color, width=w, capstyle="round")

    def _draw_calendar_icon(
        self,
        canvas: tk.Canvas,
        x: int,
        y: int,
        *,
        color: str = MUTED,
        accent: str = ACCENT,
        scale: float = 0.90,
    ) -> None:
        w = max(1.0, 1.0 * scale)
        canvas.create_rectangle(x, y + 4 * scale, x + 17 * scale, y + 21 * scale, outline=color, width=w)
        canvas.create_line(x, y + 9 * scale, x + 17 * scale, y + 9 * scale, fill=color, width=w)
        canvas.create_line(x + 4 * scale, y, x + 4 * scale, y + 7 * scale, fill=color, width=max(1.0, 1.7 * scale))
        canvas.create_line(x + 13 * scale, y, x + 13 * scale, y + 7 * scale, fill=color, width=max(1.0, 1.7 * scale))
        canvas.create_rectangle(x + 5 * scale, y + 13 * scale, x + 8 * scale, y + 16 * scale, outline=accent, fill=accent, width=w)
        canvas.create_rectangle(x + 10 * scale, y + 13 * scale, x + 13 * scale, y + 16 * scale, outline=color, width=w)

    def _canvas_icon_button(self, parent, kind: str, command, *, size: int = 36) -> tk.Canvas:
        c = tk.Canvas(parent, width=size, height=size, bg=DEEP, highlightthickness=0, bd=0, cursor="hand2")
        def draw(active: bool = False) -> None:
            c.delete("all")
            fg = ACCENT if active else MUTED
            if kind == "gear":
                c.create_oval(10, 10, size-10, size-10, outline=fg, width=1.5)
                c.create_oval(size//2-3, size//2-3, size//2+3, size//2+3, outline=fg, width=1.5)
                for dx, dy in ((0, -11), (0, 11), (-11, 0), (11, 0), (8, 8), (-8, -8), (8, -8), (-8, 8)):
                    c.create_line(size//2 + dx*0.8, size//2 + dy*0.8, size//2 + dx, size//2 + dy, fill=fg, width=1.5)
            else:
                c.create_oval(9, 9, size-9, size-9, outline=fg, width=1.5)
                c.create_text(size//2, size//2, text="?", fill=fg, font=("Segoe UI", 12, "bold"))
        draw(False)
        c.bind("<Enter>", lambda _e: draw(True))
        c.bind("<Leave>", lambda _e: draw(False))
        c.bind("<Button-1>", lambda _e: command())
        return c

    def _logo_canvas(self, parent, *, size: int = 56) -> tk.Canvas:
        c = tk.Canvas(parent, width=size, height=size, bg=DEEP, highlightthickness=0, bd=0)
        self._gradient_round_rect(c, 1, 1, size - 1, size - 1, 13, "#0cb5ea", "#0b5d9b", outline="#42d7ff", width=1, glow=True)
        self._round_rect(c, 5, 5, size - 5, size - 5, 10, fill="", outline="#38bdf6", width=1)
        # Документ
        c.create_rectangle(16, 12, 34, 40, outline=TEXT, width=2)
        c.create_line(22, 19, 30, 19, fill=TEXT, width=2)
        c.create_line(22, 26, 31, 26, fill=TEXT, width=2)
        # Медицинский плюс
        c.create_rectangle(35, 31, 48, 37, outline=TEXT, fill=TEXT, width=1)
        c.create_rectangle(39, 27, 44, 41, outline=TEXT, fill=TEXT, width=1)
        return c

    def _icon_canvas(self, parent, kind: str, *, size: int = 32, bg: str = PANEL, color: str = ACCENT) -> tk.Canvas:
        c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0)
        w = max(1, int(size / 17))
        def xy(a, b):
            return int(a * size / 32), int(b * size / 32)

        if kind == "patient":
            c.create_oval(*xy(12, 4), *xy(20, 12), outline=color, width=w+1)
            c.create_arc(*xy(6, 13), *xy(26, 30), start=0, extent=180, outline=color, width=w+1, style="arc")
            c.create_line(*xy(9, 22), *xy(23, 22), fill=color, width=w+1)
        elif kind == "folder":
            c.create_line(*xy(4, 11), *xy(12, 11), *xy(15, 15), *xy(28, 15), *xy(28, 25), *xy(4, 25), *xy(4, 11), fill=color, width=w+1)
        elif kind == "checklist":
            c.create_rectangle(*xy(9, 5), *xy(25, 29), outline=color, width=w+1)
            c.create_line(*xy(13, 12), *xy(15, 14), *xy(19, 9), fill=color, width=w+1)
            c.create_line(*xy(13, 21), *xy(15, 23), *xy(20, 17), fill=color, width=w+1)
            c.create_line(*xy(11, 5), *xy(23, 5), fill=color, width=w+2)
        elif kind == "printer":
            c.create_rectangle(*xy(8, 5), *xy(24, 13), outline=color, width=w+1)
            c.create_rectangle(*xy(5, 13), *xy(27, 24), outline=color, width=w+1)
            c.create_rectangle(*xy(9, 20), *xy(23, 29), outline=color, width=w+1)
            c.create_oval(*xy(23, 16), *xy(25, 18), outline=color, fill=color)
        elif kind == "doc":
            c.create_rectangle(*xy(8, 5), *xy(23, 28), outline=color, width=w+1)
            c.create_line(*xy(18, 5), *xy(26, 12), *xy(26, 28), fill=color, width=w+1)
            c.create_line(*xy(15, 14), *xy(20, 14), fill=color, width=w+1)
            c.create_line(*xy(17, 12), *xy(17, 17), fill=color, width=w+1)
        elif kind == "stethoscope":
            c.create_arc(*xy(7, 4), *xy(20, 21), start=180, extent=180, outline=color, width=w+1, style="arc")
            c.create_line(*xy(7, 12), *xy(7, 5), fill=color, width=w+1)
            c.create_line(*xy(20, 12), *xy(20, 5), fill=color, width=w+1)
            c.create_line(*xy(14, 21), *xy(14, 25), fill=color, width=w+1)
            c.create_oval(*xy(18, 22), *xy(26, 30), outline=color, width=w+1)
            c.create_line(*xy(14, 25), *xy(18, 26), fill=color, width=w+1)
        elif kind == "people":
            c.create_oval(*xy(6, 7), *xy(14, 15), outline=color, width=w+1)
            c.create_oval(*xy(18, 7), *xy(26, 15), outline=color, width=w+1)
            c.create_arc(*xy(1, 15), *xy(19, 31), start=0, extent=180, outline=color, width=w+1, style="arc")
            c.create_arc(*xy(13, 15), *xy(31, 31), start=0, extent=180, outline=color, width=w+1, style="arc")
        elif kind == "wheelchair":
            c.create_oval(*xy(7, 17), *xy(23, 31), outline=color, width=w+1)
            c.create_line(*xy(15, 5), *xy(15, 18), *xy(24, 18), fill=color, width=w+1)
            c.create_line(*xy(16, 11), *xy(24, 11), fill=color, width=w+1)
            c.create_line(*xy(23, 18), *xy(28, 27), fill=color, width=w+1)
            c.create_oval(*xy(13, 2), *xy(17, 6), outline=color, fill=color)
        elif kind == "clipboard":
            c.create_rectangle(*xy(9, 6), *xy(24, 29), outline=color, width=w+1)
            c.create_rectangle(*xy(13, 3), *xy(20, 8), outline=color, width=w+1)
            for y in (13, 18, 23):
                c.create_line(*xy(13, y), *xy(21, y), fill=color, width=w)
        elif kind == "shield":
            c.create_polygon(*xy(16, 4), *xy(26, 8), *xy(25, 19), *xy(16, 29), *xy(7, 19), *xy(6, 8), fill="", outline=color, width=w+1)
            c.create_line(*xy(12, 16), *xy(15, 19), *xy(21, 12), fill=color, width=w+1)
        elif kind == "book":
            c.create_line(*xy(5, 8), *xy(14, 5), *xy(16, 8), *xy(18, 5), *xy(27, 8), *xy(27, 27), *xy(18, 24), *xy(16, 27), *xy(14, 24), *xy(5, 27), *xy(5, 8), fill=color, width=w+1)
            c.create_line(*xy(16, 8), *xy(16, 27), fill=color, width=w)
        else:
            c.create_oval(*xy(6, 6), *xy(26, 26), outline=color, width=w+1)
        return c
