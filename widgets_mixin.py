from __future__ import annotations

from ui_cards import UiCardsMixin
from ui_icons import UiIconsMixin
from ui_buttons import UiButtonsMixin
from ui_fields import UiFieldsMixin
from diagnosis_widget import DiagnosisWidgetMixin
from ui_file_rows import UiFileRowsMixin


class WidgetsMixin(UiCardsMixin, UiIconsMixin, UiButtonsMixin, UiFieldsMixin, DiagnosisWidgetMixin, UiFileRowsMixin):
    pass
