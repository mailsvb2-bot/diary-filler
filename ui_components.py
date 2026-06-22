from __future__ import annotations

import tkinter as tk

from app_config import BORDER_SOFT

class RoundedPanel(tk.Frame):
    """Лёгкая rounded-карточка на Canvas без сторонних UI-зависимостей."""

    def __init__(
        self,
        parent,
        *,
        bg: str,
        parent_bg: str,
        border: str = BORDER_SOFT,
        radius: int = 14,
        padding: tuple[int, int] = (0, 0),
        height: int | None = None,
    ):
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0)
        self._panel_bg = bg
        self._parent_bg = parent_bg
        self._border = border
        self._radius = radius
        self._pad_x, self._pad_y = padding
        self.canvas = tk.Canvas(self, bg=parent_bg, highlightthickness=0, bd=0, height=height or 80)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=parent_bg, highlightthickness=0, bd=0)
        self._body_id = self.canvas.create_window(self._pad_x, self._pad_y, anchor="nw", window=self.body)
        self.canvas.bind("<Configure>", self._redraw)

    def _round_rect_points(self, x1: int, y1: int, x2: int, y2: int, r: int) -> list[int]:
        return [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]

    def _redraw(self, event=None) -> None:
        w = max(2, self.canvas.winfo_width())
        h = max(2, self.canvas.winfo_height())
        self.canvas.delete("panel")
        points = self._round_rect_points(1, 1, w - 1, h - 1, self._radius)
        self.canvas.create_polygon(points, smooth=True, fill=self._panel_bg, outline=self._border, width=1, tags="panel")
        self.canvas.coords(self._body_id, self._pad_x, self._pad_y)
        self.canvas.itemconfigure(
            self._body_id,
            width=max(1, w - self._pad_x * 2),
            height=max(1, h - self._pad_y * 2),
        )
