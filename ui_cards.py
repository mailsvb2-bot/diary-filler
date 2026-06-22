from __future__ import annotations

import tkinter as tk

from app_config import *
from ui_components import RoundedPanel


class UiCardsMixin:
    def _card(self, parent) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=PANEL,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER,
            highlightthickness=1,
            padx=12,
            pady=10,
        )

    def _section(self, parent, number: str, icon: str, label: str) -> tuple[tk.Frame, tk.Frame]:
        """Секция в стиле референса, но масштабированная под окно 1/3 экрана."""
        if self._compact_ui:
            # Баланс секций: 01 получает больше воздуха для drop-зоны, дат и
            # кнопок больничного; 02 сжимается, потому что там только ЭПИ +
            # два выбора дневников. Суммарная высота 01+02 сохранена, поэтому
            # блоки 03/04 не уезжают вниз.
            heights = {"01": 232, "02": 100, "03": 98, "04": 156}
        else:
            heights = {"01": 318, "02": 150, "03": 178, "04": 220}
        outer = RoundedPanel(
            parent,
            bg=PANEL,
            parent_bg=DEEP,
            border=BORDER_SOFT,
            radius=self._px(12, 8),
            padding=(2, 2),
            height=heights.get(number, self._px(180, 96)),
        )
        inner = outer.body
        rail_width = self._px(146, 94)
        inner.grid_columnconfigure(0, minsize=rail_width)
        inner.grid_columnconfigure(1, minsize=1)
        inner.grid_columnconfigure(2, weight=1)
        inner.grid_rowconfigure(0, weight=1)

        side_pady = 3 if self._compact_ui else self._px(24 if number in {"01", "02"} else 16, 5)
        side = tk.Frame(
            inner,
            bg=SECTION_SIDE,
            width=rail_width,
            padx=(self._px(12, 8) if self._compact_ui else self._px(26, 12)),
            pady=side_pady,
        )
        side.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        side.grid_propagate(False)
        side.grid_rowconfigure(0, weight=1)
        side.grid_columnconfigure(0, weight=1)

        side_content = tk.Frame(side, bg=SECTION_SIDE)
        side_content.grid(row=0, column=0)

        sep = tk.Frame(inner, bg=BORDER, width=1)
        sep.grid(row=0, column=1, sticky="ns", pady=1)

        tk.Label(
            side_content,
            text=number,
            bg=SECTION_SIDE,
            fg=ACCENT,
            font=self._font(20 if self._compact_ui else 22, "bold"),
            anchor="center",
            justify="center",
        ).pack(anchor="center")
        icon_size = 16 if self._compact_ui else self._px(36 if number in {"01", "02"} else 32, 18)
        icon_pady = ((0, 1) if self._compact_ui else ((self._px(13, 3), self._px(7, 1)) if number in {"01", "02"} else (self._px(8, 2), self._px(4, 1))))
        self._icon_canvas(side_content, icon, size=icon_size, bg=SECTION_SIDE, color=ACCENT).pack(anchor="center", pady=icon_pady)
        sidebar_label_font = self._font(7 if self._compact_ui and number in {"03", "04"} else (9 if self._compact_ui else 12))
        sidebar_wrap = self._px(120 if self._compact_ui and number in {"03", "04"} else 84, 70)
        sidebar_label_text = label
        if self._compact_ui and number == "03":
            sidebar_label_text = "Документы\nдля создания"
        elif self._compact_ui and number == "04":
            sidebar_label_text = "Сохранение\nи печать"
        tk.Label(
            side_content,
            text=sidebar_label_text,
            bg=SECTION_SIDE,
            fg=TEXT,
            justify="center",
            anchor="center",
            font=sidebar_label_font,
            wraplength=sidebar_wrap,
        ).pack(anchor="center")

        body_pady = (
            {"01": 7, "02": 3, "03": 5, "04": 7}
            if self._compact_ui
            else {"01": 26, "02": 14, "03": 14, "04": 18}
        ).get(number, 18)
        # Единые боковые отступы у всех блоков: левый/правый край контента
        # совпадает, а баланс меняется только высотой секций и вертикальным pady.
        body = tk.Frame(inner, bg=PANEL, padx=self._px(24 if self._compact_ui else 28, 12), pady=self._px(body_pady, 4))
        body.grid(row=0, column=2, sticky="nsew", padx=(0, 1), pady=1)
        return outer, body

    def _round_rect(self, canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
        """Canvas rounded-rect helper. Радиус намеренно заметный: ближе к референсу."""
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _hex_rgb(self, color: str) -> tuple[int, int, int]:
        color = color.lstrip("#")
        return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)

    def _rgb_hex(self, rgb: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % rgb

    def _mix(self, a: str, b: str, t: float) -> str:
        ar, ag, ab = self._hex_rgb(a)
        br, bg, bb = self._hex_rgb(b)
        return self._rgb_hex((
            int(ar + (br - ar) * t),
            int(ag + (bg - ag) * t),
            int(ab + (bb - ab) * t),
        ))

    def _gradient_round_rect(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        radius: int,
        top: str,
        bottom: str,
        *,
        outline: str | None = None,
        width: int = 1,
        glow: bool = False,
    ) -> None:
        """Rounded rectangle with a small vertical gradient, drawn without external UI libs."""
        h = max(1, y2 - y1)
        r = max(1, radius)
        for yy in range(y1, y2 + 1):
            t = (yy - y1) / h
            color = self._mix(top, bottom, t)
            dy_top = yy - y1
            dy_bottom = y2 - yy
            dx = 0
            if dy_top < r:
                # circle clipping for top rounded corners
                dx = int(r - (r * r - (r - dy_top) * (r - dy_top)) ** 0.5)
            elif dy_bottom < r:
                dx = int(r - (r * r - (r - dy_bottom) * (r - dy_bottom)) ** 0.5)
            canvas.create_line(x1 + dx, yy, x2 - dx, yy, fill=color)
        if glow and outline:
            self._round_rect(canvas, x1 + 1, y1 + 1, x2 - 1, y2 - 1, radius, fill="", outline=self._mix(outline, bottom, 0.45), width=1)
        if outline:
            self._round_rect(canvas, x1, y1, x2, y2, radius, fill="", outline=outline, width=width)
