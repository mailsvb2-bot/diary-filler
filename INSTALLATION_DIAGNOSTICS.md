# Installation diagnostics

`MedicalDiaryAutofill.exe --self-check` runs a privacy-conscious technical self-check. It does not open, parse or inspect patient DOCX/DOCM files and does not create documents.

The check reports only technical readiness: application/runtime availability, `Выписанные пациенты`, safe settings JSON, TkDND availability, watcher Startup entry, watcher handoff state and presence of the bounded watcher log.

A copy of the result is written to the application's technical per-user runtime directory as `self-check.txt`. The report deliberately avoids patient names, document names, clinical values and case numbers.

The self-check is a support layer. Failure of an optional watcher/Startup convenience must never replace or disable the existing manual document workflow.
