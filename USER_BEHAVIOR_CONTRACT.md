# User behavior contract — diary-filler

This file freezes the currently working user-visible behavior of `diary-filler` as the baseline for infrastructure, reliability and convenience work.

## Non-negotiable rule

Production-safety, installer, watcher, diagnostics, update, support and UX work must **not replace, fork or silently alter the document-creation mechanics**.

The canonical document mechanics remain the existing `diary-filler` parser / popup / medical generation / diary generation routes. A convenience layer may hand a primary document into the existing route, but must not create a second parser, second renderer or second generation workflow.

## Preserved user flow

1. The doctor selects or drops a primary DOCX/DOCM, or the desktop intake layer hands that same file to the existing primary-document entry point.
2. The existing primary parser extracts the available patient and episode data.
3. Existing UI/popup rules collect or correct missing values.
4. The doctor selects one or more medical documents and/or diaries.
5. One generation action uses one captured patient-data snapshot.
6. Medical documents are produced by the existing medical flow/renderers.
7. Diaries are produced by the existing diary flow/service.
8. The selected set is staged before publication and is committed only after preparation succeeds.
9. Result files are saved to the current output/patient folder; optional printing happens only after files are created.

## Data priority

The current priority remains:

1. doctor-confirmed UI/popup values;
2. values explicitly selected in the current session;
3. values extracted from the primary document;
4. only the safe defaults already allowed by the existing scenario.

Infrastructure work must not introduce a new source that silently overwrites doctor-confirmed values.

## Desktop intake boundary

`Выписанные пациенты` is an outer convenience layer only. It may detect a primary document, wait until the file is stable, create/select a patient subfolder, move the primary there, launch/focus the GUI and call the pre-existing `_apply_primary_document_path(...)` route.

It must not render or edit medical documents itself.

## Patient privacy

Technical settings and diagnostics must not become a patient history. Do not persist clinical text, diagnosis, treatment, case numbers, patient FIO or generated-document contents in technical telemetry/logs. No telemetry or patient upload is allowed.

## Release rule

A new version is acceptable only when:

- the document-mechanics guard is green;
- the production audit is green;
- the release gate is green;
- Windows GUI/EXE checks are green;
- the change is outside the protected document mechanics unless the user explicitly authorizes a document-mechanics change.

For the current safety/support program there is **no such authorization**. Protected mechanics must remain unchanged.
