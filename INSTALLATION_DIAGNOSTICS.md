# Installation diagnostics

`MedicalDiaryAutofill.exe --self-check` runs a privacy-conscious technical self-check. It does not open, parse or inspect patient DOCX/DOCM files and does not create documents.

The check reports only technical readiness: application/runtime availability, `Выписанные пациенты`, safe settings JSON, TkDND availability, watcher Startup entry, watcher handoff state and presence of the bounded watcher log.

A copy of the result is written to the application's technical per-user runtime directory as `self-check.txt`. The report deliberately avoids patient names, document names, clinical values and case numbers.

The self-check is a support layer. Failure of an optional watcher/Startup convenience must never replace or disable the existing manual document workflow.

## Privacy-safe startup failures

Unexpected top-level startup failures receive a stable support code such as `MDA-STARTUP-RUNTIMEERROR`. The user-facing dialog shows the code and the technical report location instead of interpolating the raw exception text.

Before the traceback is persisted, user-profile/AppData/temp path prefixes are redacted and the private `--intake-primary` argument value is replaced with `<REDACTED_PRIMARY>`. The support layer does not open or parse a patient document to build diagnostics.

`python tools/privacy_diagnostics_check.py` is a CI contract that injects a synthetic patient name/path and fails if it appears in the sanitized diagnostics.

## Golden/replay safety

`python tools/full_patient_replay_check.py` runs the repository's existing canonical `smoke_test.py`; it does not implement another generator. It verifies popup-to-DOCX facts, atomic rollback, the production paragraph diary signatures and eight semantic/visual DOCX fingerprints stored in `tests/golden_docx_manifest.json`.
