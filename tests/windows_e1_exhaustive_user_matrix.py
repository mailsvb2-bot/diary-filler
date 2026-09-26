"""Exhaustive finite user-selection matrix for the Windows E1 contour.

This does not invent a second generator. It drives the production
ActionsCreationOrchestratorMixin through every non-empty subset of the seven
medical outputs plus diaries (2^8 - 1 = 255 user selections), using the same
staging/commit/retry path as the desktop application.

Real DOCX semantics are verified separately by full_patient_replay_check.py and
golden/clinical round-trip gates in the same mandatory Windows workflow.
"""
from __future__ import annotations

from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app_config import DIARY_KIND
from medical_constants import DOCUMENT_ORDER
from full_user_journey_regression import JourneyApp, Var, _messagebox_recorder


ALL_OUTPUTS = (*DOCUMENT_ORDER, DIARY_KIND)


class E1JourneyApp(JourneyApp):
    """Complete narrow harness for every document-specific orchestration branch."""

    def __init__(self, root: Path, *, selected=()):
        super().__init__(root, selected=selected)
        # Populate every field read before a document-specific popup decision.
        self.commission_date_var = Var("21.06.2026")
        self.commission_number_var = Var("К-01")
        self.rvk_act_number_var = Var("РВК-01")
        self.rvk_military_commissariat_var = Var("Ленинский")
        self.vk_date_var = Var("21.06.2026")
        self.vk_protocol_number_var = Var("МСЭ-01")
        self.vk_protocol_date_var = Var("21.06.2026")
        self.vk_mse_work_org_var = Var("Организация")
        self.sick_leave_vk_date_var = Var("21.06.2026")
        self.sick_leave_vk_protocol_number_var = Var("БЛ-01")
        self.sick_leave_vk_protocol_date_var = Var("21.06.2026")
        self.sick_leave_vk_commission_date_var = Var("21.06.2026")
        self.sick_leave_vk_work_org_var = Var("Организация")
        self.sick_leave_vk_position_var = Var("Должность")

    def _selected_output_names(self, selected_medical, selected_diaries):
        names = list(selected_medical)
        if selected_diaries:
            names.append(DIARY_KIND)
        return names


def _all_non_empty_selections():
    for size in range(1, len(ALL_OUTPUTS) + 1):
        yield from combinations(ALL_OUTPUTS, size)


def assert_every_output_selection_commits_exactly_once() -> int:
    executed = 0
    for selected in _all_non_empty_selections():
        with TemporaryDirectory(prefix="windows-e1-matrix-") as raw:
            app = E1JourneyApp(Path(raw), selected=selected)
            events, record = _messagebox_recorder()
            with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")), \
                 patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
                app.create_selected_outputs()

            expected_medical = [kind for kind in DOCUMENT_ORDER if kind in selected]
            expected_diary = DIARY_KIND in selected
            assert app.medical_calls == (1 if expected_medical else 0), selected
            assert app.diary_calls == (1 if expected_diary else 0), selected
            assert not [event for event in events if event[0] in {"warning", "error"}], (selected, events)
            assert app.statuses[-1] == "Готово: файлы сохранены", (selected, app.statuses)

            actual = {path.name for path in app._output.glob("*") if path.is_file()}
            expected = {f"{kind}.docx" for kind in expected_medical}
            if expected_diary:
                expected.add("Дневники.docx")
            assert actual == expected, (selected, actual, expected)
            executed += 1
    return executed


def assert_empty_selection_is_the_only_zero-output_selection() -> None:
    with TemporaryDirectory(prefix="windows-e1-empty-") as raw:
        app = E1JourneyApp(Path(raw), selected=())
        events, record = _messagebox_recorder()
        with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")):
            app.create_selected_outputs()
        assert app.medical_calls == 0 and app.diary_calls == 0
        assert not app._output.exists()
        assert events and events[-1][1] == "Ничего не выбрано", events


def main() -> None:
    count = assert_every_output_selection_commits_exactly_once()
    assert count == 255, count
    assert_empty_selection_is_the_only_zero_output_selection()
    print(
        "WINDOWS E1 EXHAUSTIVE USER MATRIX OK: "
        f"{count} non-empty output selections + empty selection; "
        "production orchestration/staging/commit path exercised"
    )


if __name__ == "__main__":
    main()
