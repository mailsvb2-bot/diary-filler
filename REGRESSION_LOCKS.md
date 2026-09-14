# Regression locks

This repository treats the current working document generation and Windows user lifecycle as a protected production contract.

## What is locked

`tools/regression_lock_check.py` compares the current tree with the exact tested commit named by `tests/regression_lock_baseline.json`.

The locked surface includes:

- document generation, parsers, renderers, dialogs and embedded templates;
- diary generation and diary template logic;
- startup/watcher and desktop intake code;
- UI/settings/path/DnD support used by the production flow;
- installer/build/version files;
- golden manifests, smoke/regression tests and safety gates;
- GitHub Actions build and release workflows themselves.

A changed, added or deleted locked file fails CI by default.

## Intentional changes

For an intentional change to the locked surface:

1. Create `tools/regression_lock_change_approval.json` on the feature branch.
2. Bind it to the exact `baseline_ref` from `tests/regression_lock_baseline.json`.
3. List every changed locked path and its exact candidate Git blob SHA in `approved_blobs` (`<deleted>` for an intentional deletion).
4. Give a concrete `reason` and include every required evidence name from the baseline config.
5. Run the entire Windows CI. A green lock alone is never sufficient.
6. After the exact candidate has passed all required regressions, remove the temporary approval and advance `baseline_ref` in a separate metadata-only commit to that exact tested candidate commit.
7. Run CI again. The final merge candidate must pass without a standing approval file.

This makes a baseline move visible and deliberate; silently changing the golden file, a generator, a watcher test, or the CI workflow is not enough to regain a green build.

## Local commands

Fast source/lifecycle contour:

```text
python tools/run_regression_suite.py --quick
```

Full source/generation contour:

```text
python tools/run_regression_suite.py --full
```

The real packaged Windows auto-launch E2E and installed/uninstalled application smoke remain mandatory GitHub Actions gates because they require a built Windows EXE and installer.

## CI topology lock

`tools/ci_gate_lock.py` verifies that mandatory gates are still present and ordered before packaging/publishing. Both the normal Windows build and the official signed release are checked.

`tests/regression_surface_inventory.py` self-tests the lock coverage so the protection cannot accidentally be narrowed away from major source families such as `medical_*`, `diary_*`, `startup.py`, installer files, workflows, or golden manifests.
