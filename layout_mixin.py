from __future__ import annotations

from layout_sources import LayoutSourcesMixin
from layout_checklist import LayoutChecklistMixin
from layout_action_bar import LayoutActionBarMixin


class LayoutMixin(LayoutSourcesMixin, LayoutChecklistMixin, LayoutActionBarMixin):
    pass
