"""Detection of explicit treatment section markers in primary DOCX text."""
from __future__ import annotations

import re

from medical_text_utils import normalize_match, normalize_text

# Treat only explicit section labels as evidence that the primary document has
# its own treatment field. Ordinary phrases like "за время лечения" or
# "находится на лечении" must not suppress the doctor popup.
_TREATMENT_MARKER_RE = re.compile(
    # Supports both strict label rows ("Лечение:") and common DOCX table rows
    # where the label and value are merged without punctuation: "Лечение терапия...".
    r"^\s*(?:назначенное\s+лечение|план\s+лечения|лечение)\b\s*(?:[:№#Nn.\-–—]|$|\S)",
    flags=re.IGNORECASE,
)


def line_has_treatment_marker(line: str) -> bool:
    """Return True when a single text line is an explicit treatment label."""
    cleaned = normalize_text(line or "").strip()
    if not cleaned:
        return False
    normalized = normalize_match(cleaned)
    # Guard against prose sentences that only contain the word treatment.
    if normalized.startswith(("за время лечения", "находится на лечении", "получал лечение", "получает лечение")):
        return False
    return bool(_TREATMENT_MARKER_RE.match(cleaned))


def has_treatment_section_marker(text: str) -> bool:
    """Scan the full parsed primary-document text for a treatment section row."""
    for line in normalize_text(text or "").splitlines():
        if line_has_treatment_marker(line):
            return True
    return False
