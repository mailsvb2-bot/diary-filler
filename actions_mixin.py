from __future__ import annotations

from actions_selection import ActionsSelectionMixin
from actions_reports import ActionsReportsMixin
from actions_creation import ActionsCreationMixin
from actions_ui_state import ActionsUiStateMixin


class ActionsMixin(ActionsSelectionMixin, ActionsReportsMixin, ActionsCreationMixin, ActionsUiStateMixin):
    pass
