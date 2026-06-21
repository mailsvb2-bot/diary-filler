from __future__ import annotations

import tkinter as tk

from settings_mixin import SettingsMixin
from window_mixin import WindowMixin
from layout_mixin import LayoutMixin
from dialogs_mixin import DialogsMixin
from widgets_mixin import WidgetsMixin
from files_mixin import FilesMixin
from diary_templates_mixin import DiaryTemplateMixin
from dnd_mixin import DragDropMixin
from actions_mixin import ActionsMixin
from app_initialization import AppInitializationMixin


class CombinedMedicalDiaryApp(AppInitializationMixin, SettingsMixin, WindowMixin, LayoutMixin, DialogsMixin, WidgetsMixin, FilesMixin, DiaryTemplateMixin, DragDropMixin, ActionsMixin):
    def __init__(self, root: tk.Tk):
        self._initialize_app(root)
