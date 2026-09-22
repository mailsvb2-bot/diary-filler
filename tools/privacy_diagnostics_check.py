"""Prove that support diagnostics stay technical and do not expose patient paths."""
from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


_TEXT_SUFFIXES = {".py", ".json", ".md", ".ps1", ".txt", ".toml", ".yml", ".yaml"}
_PERSON_FULL_RE = re.compile(r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}\b")
_PERSON_INITIALS_RE = re.compile(r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.?")

_ALLOWED_FULL_NAMES = {
    "Фамилия Имя Отчество",
    "Можарова Елена Александровна",
}
_ALLOWED_STAFF_TEST_FULL_NAMES = {
    "Орлов Олег Олегович",
    "Соколова Светлана Сергеевна",
    "Кузнецова Кира Константиновна",
    "Иванов Иван Иванович",
    "Петрова Анна Сергеевна",
}
_ALLOWED_STAFF_INITIALS = {
    "Балаганин С.В.", "Балаганин С.В",
    "Можарова Е.А.", "Можарова Е.А",
    "Можаровой Е.А.", "Можаровой Е.А",
    "Зуйкова А.А.", "Зуйкова А.А",
    "Зуйковой А.А.", "Зуйковой А.А",
    "Орлов О.О.", "Соколова С.С.", "Кузнецова К.К.",
    "Кузнецовой К.К.", "Соколовой С.С.", "Петровой А.С.",
    "Иванов И.И.", "Ивановым И.И.",
    "Врач В.В.", "Заведующий З.З.",
    "Автоврач А.А.", "Автозаведующая З.З.", "Автозам Д.Д.",
}


def _assert_no_patient_names_in_source() -> None:
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        if any(part in {".git", "build", "dist", "__pycache__"} for part in path.parts):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT).as_posix()
        for match in _PERSON_FULL_RE.finditer(content):
            value = match.group(0)
            if value.startswith("Маркер "):
                continue
            if value in _ALLOWED_FULL_NAMES:
                continue
            if rel == "tools/staff_profile_regression.py" and value in _ALLOWED_STAFF_TEST_FULL_NAMES:
                continue
            violations.append(f"{rel}: {value}")
        for match in _PERSON_INITIALS_RE.finditer(content):
            value = re.sub(r"\s+", " ", match.group(0)).strip()
            if value.startswith("Маркер "):
                continue
            if value in _ALLOWED_STAFF_INITIALS:
                continue
            # Labels such as «Фамилия И.О.» describe a format, not a person.
            if value.startswith("Фамилия "):
                continue
            violations.append(f"{rel}: {value}")
    if violations:
        preview = "\n".join(sorted(set(violations))[:40])
        raise SystemExit(
            "PRIVACY DIAGNOSTICS FAILED: patient-like names found in source:\n" + preview
        )



def main_check() -> None:
    _assert_no_patient_names_in_source()
    fake_patient = "Маркер Секретный Тестовый"
    with tempfile.TemporaryDirectory(prefix="medical-autofill-privacy-") as tmp:
        private_path = Path(tmp) / fake_patient / "Первичный осмотр.docx"
        raw = (
            f'RuntimeError: failed for --intake-primary "{private_path}"\n'
            f'home={Path.home()}\\private\\thing\n'
        )
        safe = main._support_sanitize_diagnostics(raw)
        if fake_patient in safe or str(private_path) in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: patient path leaked")
        if str(Path.home()) in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: home path leaked")
        if "<REDACTED_PRIMARY>" not in safe:
            raise SystemExit("PRIVACY DIAGNOSTICS FAILED: intake path was not redacted")

    exc = RuntimeError(f"synthetic error for {fake_patient}")
    code = main._support_error_code("startup", exc)
    if not code.startswith("MDA-STARTUP-RUNTIMEERROR"):
        raise SystemExit(f"PRIVACY DIAGNOSTICS FAILED: unstable support code {code}")

    source = Path(main.__file__).read_text(encoding="utf-8", errors="replace")
    if "Код ошибки: {code}" not in source:
        raise SystemExit("PRIVACY DIAGNOSTICS FAILED: user-visible error lacks support code")
    if "{exc}" in source:
        raise SystemExit("PRIVACY DIAGNOSTICS FAILED: raw exception is shown to user")

    print("PRIVACY DIAGNOSTICS OK")


if __name__ == "__main__":
    main_check()
