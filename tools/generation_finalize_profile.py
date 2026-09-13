from __future__ import annotations

import copy
import cProfile
import json
import pstats
import statistics
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import medical_gender
import medical_renderer
from medical_constants import DOCUMENT_ORDER
from tools.generation_performance_profile import Probe, _make_fixture


TARGETS = (
    (medical_renderer, "adapt_patient_data_to_gender"),
    (medical_gender, "normalize_facility_references_in_document"),
    (medical_gender, "adapt_document_to_patient_gender"),
    (medical_gender, "remove_epi_mentions_from_document"),
    (medical_gender, "apply_readable_section_spacing"),
    (medical_gender, "replace_paragraph_regex_preserving_runs"),
    (medical_gender, "patient_gender"),
)


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 3)


class HelperTimer:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)
        self._restorers: list[Any] = []

    def __enter__(self):
        for module, name in TARGETS:
            original = getattr(module, name)

            def wrapper(*args, __original=original, __name=name, **kwargs):
                started = time.perf_counter()
                try:
                    return __original(*args, **kwargs)
                finally:
                    self.seconds[__name] += time.perf_counter() - started
                    self.calls[__name] += 1

            setattr(module, name, wrapper)
            self._restorers.append(lambda m=module, n=name, f=original: setattr(m, n, f))
        return self

    def __exit__(self, exc_type, exc, tb):
        for restore in reversed(self._restorers):
            restore()

    def snapshot(self) -> dict[str, Any]:
        return {
            name: {"ms": _ms(self.seconds.get(name, 0.0)), "calls": self.calls.get(name, 0)}
            for _module, name in TARGETS
        }


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 3)


def _project_top_profile(profile: cProfile.Profile, limit: int = 40) -> list[dict[str, Any]]:
    stats = pstats.Stats(profile)
    rows: list[dict[str, Any]] = []
    for (filename, line, function), value in stats.stats.items():
        primitive_calls, total_calls, total_time, cumulative_time, _callers = value
        normalized = filename.replace("\\", "/")
        if "/diary-filler/" not in normalized:
            continue
        if "/tools/generation_" in normalized:
            continue
        rows.append(
            {
                "file": Path(filename).name,
                "line": line,
                "function": function,
                "primitive_calls": primitive_calls,
                "total_calls": total_calls,
                "self_ms": _ms(total_time),
                "cumulative_ms": _ms(cumulative_time),
            }
        )
    rows.sort(key=lambda row: (row["cumulative_ms"], row["self_ms"]), reverse=True)
    return rows[:limit]


def run_detailed_profile(measured_runs: int = 3) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="medical-autofill-finalize-perf-") as tmp:
        root = Path(tmp)
        nav, service, baseline_data = _make_fixture(root)

        service.create_documents(
            navigation_path=nav,
            output_dir=root / "warmup",
            selected_docs=DOCUMENT_ORDER,
            override_data=copy.deepcopy(baseline_data),
        )

        helper_runs: list[dict[str, Any]] = []
        wall_runs: list[float] = []
        for index in range(measured_runs):
            with HelperTimer() as timer, Probe(service):
                started = time.perf_counter()
                created, _ = service.create_documents(
                    navigation_path=nav,
                    output_dir=root / f"measured-{index + 1}",
                    selected_docs=DOCUMENT_ORDER,
                    override_data=copy.deepcopy(baseline_data),
                )
                wall = time.perf_counter() - started
            if len(created) != len(DOCUMENT_ORDER):
                raise RuntimeError(f"Expected {len(DOCUMENT_ORDER)} documents, got {len(created)}")
            helper_runs.append(timer.snapshot())
            wall_runs.append(_ms(wall))

        helper_median: dict[str, Any] = {}
        for _module, name in TARGETS:
            helper_median[name] = {
                "median_ms": _median([run[name]["ms"] for run in helper_runs]),
                "median_calls": _median([float(run[name]["calls"]) for run in helper_runs]),
            }

        profile = cProfile.Profile()
        profile.enable()
        created, _ = service.create_documents(
            navigation_path=nav,
            output_dir=root / "cprofile",
            selected_docs=DOCUMENT_ORDER,
            override_data=copy.deepcopy(baseline_data),
        )
        profile.disable()
        if len(created) != len(DOCUMENT_ORDER):
            raise RuntimeError("cProfile generation did not create the complete document set")

    return {
        "schema_version": 1,
        "documents_per_run": len(DOCUMENT_ORDER),
        "measured_runs": measured_runs,
        "wall_ms": wall_runs,
        "median_wall_ms": _median(wall_runs),
        "helper_runs": helper_runs,
        "helper_median": helper_median,
        "cprofile_top_project_functions": _project_top_profile(profile),
    }


def main() -> int:
    report = run_detailed_profile(3)
    output = Path("generation_finalize_profile.json")
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print("GENERATION FINALIZATION PROFILE")
    print(f"median wall: {report['median_wall_ms']:.3f} ms")
    for name, value in report["helper_median"].items():
        print(f"{name}: {value['median_ms']:.3f} ms / {value['median_calls']:.0f} calls")
    print("top project functions by cumulative time:")
    for row in report["cprofile_top_project_functions"][:20]:
        print(
            f"  {row['file']}:{row['line']} {row['function']} "
            f"cum={row['cumulative_ms']:.3f} ms self={row['self_ms']:.3f} ms calls={row['total_calls']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
