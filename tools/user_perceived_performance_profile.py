from __future__ import annotations

import copy
import statistics
import tempfile
import time
from pathlib import Path

from medical_constants import DOCUMENT_ORDER
from medical_service import MedicalDocumentService
from tools.generation_performance_profile import _make_fixture


PARSE_MEDIAN_BUDGET_MS = 250.0
END_TO_END_MEDIAN_BUDGET_MS = 1500.0


def _median(values):
    return round(statistics.median(values), 3)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="medical-autofill-user-perf-") as raw:
        root = Path(raw)
        nav, service, baseline = _make_fixture(root)

        # Warm filesystem/parser/template caches once before measured runs.
        service.parse_primary_document(nav)
        service.create_documents(
            navigation_path=nav,
            output_dir=root / "warmup",
            selected_docs=DOCUMENT_ORDER,
            override_data=copy.deepcopy(baseline),
        )

        parse_ms = []
        e2e_ms = []
        for index in range(5):
            parser = MedicalDocumentService()
            started = time.perf_counter()
            parsed = parser.parse_primary_document(nav)
            parse_ms.append((time.perf_counter() - started) * 1000.0)

            parsed.discharge_date = baseline.discharge_date
            parsed.diagnosis = baseline.diagnosis
            for name, value in vars(baseline).items():
                if name in {"fio", "birth", "admission_date", "complaints", "life_anamnesis",
                            "disease_anamnesis", "mental_status", "somatic_status"}:
                    continue
                try:
                    setattr(parsed, name, copy.deepcopy(value))
                except Exception:
                    pass

            started = time.perf_counter()
            created, _ = parser.create_documents(
                navigation_path=nav,
                output_dir=root / f"e2e-{index}",
                selected_docs=DOCUMENT_ORDER,
                override_data=parsed,
            )
            e2e_ms.append((time.perf_counter() - started) * 1000.0)
            assert len(created) == len(DOCUMENT_ORDER), created

        parse_median = _median(parse_ms)
        e2e_median = _median(e2e_ms)
        print("USER-PERCEIVED PERFORMANCE PROFILE")
        print(f"parse primary median: {parse_median:.3f} ms")
        print(f"7-document end-to-end median: {e2e_median:.3f} ms")
        print("parse runs: " + ", ".join(f"{v:.3f}" for v in parse_ms))
        print("e2e runs: " + ", ".join(f"{v:.3f}" for v in e2e_ms))

        if parse_median > PARSE_MEDIAN_BUDGET_MS:
            raise SystemExit(
                f"PRIMARY PARSE PERFORMANCE REGRESSION: {parse_median:.3f} ms > "
                f"{PARSE_MEDIAN_BUDGET_MS:.0f} ms"
            )
        if e2e_median > END_TO_END_MEDIAN_BUDGET_MS:
            raise SystemExit(
                f"USER JOURNEY PERFORMANCE REGRESSION: {e2e_median:.3f} ms > "
                f"{END_TO_END_MEDIAN_BUDGET_MS:.0f} ms"
            )

        print("USER-PERCEIVED PERFORMANCE OK")


if __name__ == "__main__":
    main()
