from __future__ import annotations

from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from actions_diary_flow import ActionsDiaryFlowMixin
from actions_medical_flow import ActionsMedicalFlowMixin
from actions_navigation import ActionsNavigationMixin
from actions_template_checks import ActionsTemplateChecksMixin


class ActionsCreationMixin(
    ActionsCreationOrchestratorMixin,
    ActionsTemplateChecksMixin,
    ActionsNavigationMixin,
    ActionsMedicalFlowMixin,
    ActionsDiaryFlowMixin,
):
    pass
