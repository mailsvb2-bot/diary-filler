from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from actions_creation_orchestrator import ActionsCreationOrchestratorMixin
from actions_selection import ActionsSelectionMixin
from medical_constants import DOCUMENT_ORDER
from app_config import DIARY_KIND


class Var:
    def __init__(self, value=None):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class Root:
    def update_idletasks(self):
        pass


class JourneyApp(ActionsCreationOrchestratorMixin, ActionsSelectionMixin):
    def __init__(self, root: Path, *, selected=(), diary_failure: Exception | None = None):
        self.root = Root()
        self._root = Path(root)
        self._output = self._root / "out"
        self.navigation_path_var = Var(str(self._root / "primary.docx"))
        self.epi_path_var = Var("")
        self.epi_present_var = Var("нет")
        self.printer_var = Var("")
        self.open_result_folder_var = Var(False)
        self.expert_sick_leave_needed_var = Var("нет")
        self.output_vars = {kind: Var(kind in selected) for kind in DOCUMENT_ORDER}
        self.output_vars[DIARY_KIND] = Var(DIARY_KIND in selected)
        self._pending_print_retry_files = []
        self._loaded_primary_source_signature = None
        self._loaded_epi_source_signature = None
        self._loaded_diary_text_source_signatures = None
        self._loaded_diary_date_source_signatures = None
        self._generation_action_in_progress = False
        self._generation_action_cooldown_until = 0.0
        self._generation_action_last_fingerprint = None
        self.diary_failure = diary_failure
        self.medical_calls = 0
        self.diary_calls = 0
        self.statuses: list[str] = []
        self.logs: list[str] = []
        self.redraws = 0
        self._root.joinpath("primary.docx").write_bytes(b"journey-primary")

    def _result_output_dir(self):
        return self._output

    def _set_status(self, value):
        self.statuses.append(value)

    def _log(self, value):
        self.logs.append(value)

    def _start_progress(self):
        pass

    def _stop_progress(self):
        pass

    def _redraw_selection_controls(self):
        self.redraws += 1

    def _write_creation_report(self, **_kwargs):
        return None

    def _capture_generation_patient_data(self, *, require_primary: bool):
        assert require_primary is bool(self.selected_medical_docs())
        return SimpleNamespace(output_fio="Тестовый Пациент", fio="Тестовый Пациент")

    def _create_medical_documents_impl(self, selected_docs, *, output_dir_override, log_created, patient_data_snapshot):
        self.medical_calls += 1
        assert selected_docs
        assert log_created is False
        assert patient_data_snapshot.output_fio == "Тестовый Пациент"
        created = []
        for kind in selected_docs:
            path = Path(output_dir_override) / f"{kind}.docx"
            path.write_bytes(f"medical:{kind}".encode())
            created.append(path)
        return created

    def _create_diaries_impl(self, *, output_dir_override, log_created, patient_data_snapshot):
        self.diary_calls += 1
        assert log_created is False
        assert patient_data_snapshot.output_fio == "Тестовый Пациент"
        if self.diary_failure is not None:
            raise self.diary_failure
        path = Path(output_dir_override) / "Дневники.docx"
        path.write_bytes(b"diary")
        return SimpleNamespace(
            created_files=[path],
            report_path=None,
            processed_files=1,
            filled_rows=1,
            month_cells_filled=1,
            final_rows_filled=1,
            removed_after_discharge_rows=0,
        )

    # User-input prompts are outside this orchestration test. They are covered by
    # the real popup->DOCX contracts. Here we verify ordering, aborts and retry state.
    def _prompt_missing_patient_identity_if_needed(self): return True
    def _prompt_shared_clinical_options_if_needed(self, _selected): return True
    def _prompt_common_output_requirements(self, **_kwargs): return True
    def _prompt_commission_details(self): return True
    def _prompt_rvk_details(self): return True
    def _prompt_vk_mse_details(self): return True
    def _prompt_sick_leave_vk_details(self): return True
    def _selected_docs_need_expert_anamnesis(self, _selected): return False
    def _prompt_expert_anamnesis_details(self, force=False): return True
    def _prompt_discharge_output_requirements(self): return True
    def _prompt_assigned_treatment_if_needed(self, force=False): return True
    def _select_default_printer_sync(self): return False


def _messagebox_recorder():
    events = []
    def record(kind):
        def fn(title, message, **_kwargs):
            events.append((kind, title, message))
            return True
        return fn
    return events, record


def assert_empty_selection_stops_before_generation(tmp: Path) -> None:
    app = JourneyApp(tmp)
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")):
        app.create_selected_outputs()
    assert app.medical_calls == 0 and app.diary_calls == 0
    assert events and events[-1][1] == "Ничего не выбрано", events


def assert_missing_primary_stops_before_prompts(tmp: Path) -> None:
    app = JourneyApp(tmp, selected=("primary",))
    Path(app.navigation_path_var.get()).unlink()
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
        app.create_selected_outputs()
    assert app.medical_calls == 0
    assert events and events[-1][1] == "Источник пациента недоступен", events


def assert_invalid_output_path_stops_safely(tmp: Path) -> None:
    app = JourneyApp(tmp, selected=("primary",))
    app._output.write_bytes(b"not-a-directory")
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
        app.create_selected_outputs()
    assert app.medical_calls == 0
    assert events and events[-1][1] == "Папка результата недоступна", events


def assert_full_success_commits_all_selected(tmp: Path) -> None:
    app = JourneyApp(tmp, selected=("primary", DIARY_KIND))
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")), \
         patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
        app.create_selected_outputs()
    assert app.medical_calls == 1 and app.diary_calls == 1
    assert (app._output / "primary.docx").is_file()
    assert (app._output / "Дневники.docx").is_file()
    assert not [e for e in events if e[0] in {"warning", "error"}], events
    assert app.statuses[-1] == "Готово: файлы сохранены"


def assert_partial_diary_failure_keeps_only_failed_retry_selected(tmp: Path) -> None:
    app = JourneyApp(
        tmp,
        selected=("primary", "discharge", DIARY_KIND),
        diary_failure=ValueError("Дата выписки раньше даты поступления"),
    )
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")), \
         patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
        app.create_selected_outputs()

    assert app.medical_calls == 1 and app.diary_calls == 1
    assert (app._output / "primary.docx").is_file()
    assert (app._output / "discharge.docx").is_file()
    assert app.output_vars["primary"].get() is False
    assert app.output_vars["discharge"].get() is False
    assert app.output_vars[DIARY_KIND].get() is True
    warnings = [e for e in events if e[0] == "warning" and e[1] == "Комплект создан частично"]
    assert len(warnings) == 1, events
    message = warnings[0][2]
    assert "Дата выписки раньше даты поступления" in message, message
    assert "Исправьте указанную выше причину" in message, message
    assert "Исправьте источник дневников" not in message, message


def assert_partial_retry_does_not_duplicate_medical(tmp: Path) -> None:
    app = JourneyApp(
        tmp,
        selected=("primary", DIARY_KIND),
        diary_failure=RuntimeError("временная ошибка дневника"),
    )
    events, record = _messagebox_recorder()
    with patch("actions_creation_orchestrator.messagebox.showwarning", record("warning")), \
         patch("actions_creation_orchestrator.messagebox.showerror", record("error")):
        app.create_selected_outputs()
    assert app.medical_calls == 1
    first_medical = (app._output / "primary.docx").read_bytes()

    app.diary_failure = None
    app._generation_action_cooldown_until = 0.0
    app.create_selected_outputs()
    assert app.medical_calls == 1, "medical output regenerated during diary-only retry"
    assert app.diary_calls == 2
    assert (app._output / "primary.docx").read_bytes() == first_medical
    assert (app._output / "Дневники.docx").is_file()


def assert_double_click_guard_suppresses_identical_second_action(tmp: Path) -> None:
    app = JourneyApp(tmp, selected=("primary",))
    app.create_selected_outputs()
    assert app.medical_calls == 1
    app.create_selected_outputs()
    assert app.medical_calls == 1, "identical queued second click created duplicate output"
    assert app.statuses[-1] == "Предыдущее создание уже завершено"


def main() -> None:
    scenarios = [
        assert_empty_selection_stops_before_generation,
        assert_missing_primary_stops_before_prompts,
        assert_invalid_output_path_stops_safely,
        assert_full_success_commits_all_selected,
        assert_partial_diary_failure_keeps_only_failed_retry_selected,
        assert_partial_retry_does_not_duplicate_medical,
        assert_double_click_guard_suppresses_identical_second_action,
    ]
    for scenario in scenarios:
        with TemporaryDirectory(prefix=f"user-journey-{scenario.__name__}-") as raw:
            scenario(Path(raw))
    print(
        "FULL USER JOURNEY REGRESSION OK: empty/missing-source/bad-output preflight, "
        "full save, partial diary failure, retry without duplicate medical files, "
        "accurate retry guidance, and double-click suppression"
    )


if __name__ == "__main__":
    main()
