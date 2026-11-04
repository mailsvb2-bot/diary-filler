"""Regression tests for VK MSE and intake backlog corrections."""
from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

import dialog_document_details as ddd
import startup


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def vk_app(answers, status=""):
    app = ddd.DialogDocumentDetailsMixin.__new__(ddd.DialogDocumentDetailsMixin)
    for name in ("vk_date_var", "vk_protocol_date_var", "vk_protocol_number_var",
                 "vk_mse_work_org_var", "vk_mse_position_var", "vk_epicrisis_number_var",
                 "expert_work_org_var", "expert_position_var"):
        setattr(app, name, Var(""))
    app.vk_mse_work_org_var.set("ООО Старое")
    app.expert_work_status_var = Var(status)
    app._shared_work_defaults = lambda: ("", "")
    app._normalize_yes_no = lambda v: str(v or "").strip().lower()
    app._case_number_popup_default = lambda: ""
    app._store_case_number_value = lambda v: bool(v)
    app._normalize_required_date_for_ui = lambda v, label: v or None
    app._sync_shared_work_details = lambda org, pos: app.synced.append((org, pos))
    app._remember_committee_dates = lambda **kwargs: None
    app.synced = []
    app._prompt_fields = lambda **kwargs: list(answers)
    return app


def test_nonworking_patient_vk_mse(monkeypatch):
    warnings = []
    monkeypatch.setattr(ddd.messagebox, "showwarning", lambda *a, **k: warnings.append(a))
    app = vk_app(["123", "01.11.2026", "7", "01.11.2026", "не работает", "", ""])
    assert app._prompt_vk_mse_details() is True
    assert app.expert_work_status_var.get() == "нет"
    assert app.vk_mse_work_org_var.get() == ""
    assert not warnings


def test_working_patient_requires_position(monkeypatch):
    warnings = []
    monkeypatch.setattr(ddd.messagebox, "showwarning", lambda *a, **k: warnings.append(a))
    app = vk_app(["123", "01.11.2026", "7", "01.11.2026", "ООО Ромашка", "", ""])
    assert app._prompt_vk_mse_details() is False
    assert "не работает" in warnings[0][1]
    app = vk_app(["123", "01.11.2026", "7", "01.11.2026", "ООО Ромашка", "слесарь", ""])
    assert app._prompt_vk_mse_details() is True
    assert app.synced == [("ООО Ромашка", "слесарь")]


def test_shared_vk_mse_work_dialog():
    root = Path(__file__).resolve().parents[1]
    assert '"admission_doctor_referral", "vk_mse"}' in (root / "dialog_expert.py").read_text(encoding="utf-8")
    assert 'data.vk_mse_work_org = ""' in (root / "actions_medical_flow.py").read_text(encoding="utf-8")


def test_intake_backlog_oldest(monkeypatch, tmp_path):
    old, new = tmp_path / "old.docx", tmp_path / "new.docx"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    past = time.time() - 3600
    os.utime(old, (past, past))
    assert startup._desktop_pending_backlog_key({"old": (old, "s1"), "new": (new, "s2")}) == "old"
    assert startup._desktop_pending_backlog_key({}) is None
    asked = []
    monkeypatch.setattr(startup.messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
    assert startup._desktop_confirm_backlog(SimpleNamespace(root=None), old, 2)
    assert "old.docx" in asked[0][1]


def test_rejected_primary_warns(monkeypatch, tmp_path):
    src = tmp_path / "Иванов первичный.docx"
    src.write_bytes(b"x")
    moved = tmp_path / "Иванов И.И. ноябрь 2026" / src.name
    monkeypatch.setattr(startup, "desktop_intake_file_is_quiet", lambda p: True)
    monkeypatch.setattr(startup, "desktop_intake_is_primary_document", lambda p: True)
    monkeypatch.setattr(startup, "desktop_intake_prepare_patient_folder", lambda *a, **k: moved)
    shown = []
    monkeypatch.setattr(startup, "_desktop_show_intake_warning", lambda app, text: shown.append(text))
    app = SimpleNamespace(_apply_primary_document_path=lambda *a, **k: False)
    assert startup._desktop_process_primary(app, src) is False
    assert shown and "Иванов И.И. ноябрь 2026" in shown[0]
