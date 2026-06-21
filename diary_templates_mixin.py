from __future__ import annotations

from diary_template_discovery import DiaryTemplateDiscoveryMixin
from diary_template_selection import DiaryTemplateSelectionMixin


class DiaryTemplateMixin(DiaryTemplateDiscoveryMixin, DiaryTemplateSelectionMixin):
    pass
