# Strict regression contour — diary-filler

The regression contour protects the working document mechanics while allowing reliability and convenience work around them.

## Hard document-mechanics guard

`tools/document_mechanics_guard.py` compares the current change with its base commit and fails when protected parser, renderer, medical/diary flow, popup/data-flow or document-publication files are modified.

This is intentionally stricter than a normal unit test: for safety/support work, a source change in the protected mechanics is itself a regression signal even if tests happen to stay green.

## Production-safety gate

`tools/production_safety_gate.py` verifies that:

- this behavior contract and regression contour remain present;
- the document-mechanics guard remains wired into Windows CI;
- the runtime Python-file architecture budget is not raised;
- desktop intake still ends at the existing `_apply_primary_document_path(...)` boundary;
- the diagnostic self-check remains technical-only and does not parse patient documents;
- the normal packaged GUI/EXE release checks are still present;
- startup/support diagnostics redact the private `--intake-primary` value and use stable technical error codes;
- the canonical smoke user flow is replayed and its generated medical + diary DOCX are compared with checked-in semantic/visual golden fingerprints.

## Commands

```bash
python tools/document_mechanics_guard.py
python tools/production_safety_gate.py
python tools/privacy_diagnostics_check.py
python prod_audit.py
python release_check.py
python tools/full_patient_replay_check.py
```

The existing Windows workflow additionally runs the real Tk GUI smoke, builds the EXE and verifies the packaged executable.

## Protected-mechanics principle

Do not "improve" this gate by deleting protected patterns or weakening the comparison because a safety/installer/diagnostics PR touches a core file. Move the new behavior outward instead.

If a future user request explicitly asks to change document generation itself, that must be a separate, clearly scoped task with its own regression evidence; it must not be smuggled into production-safety work.
