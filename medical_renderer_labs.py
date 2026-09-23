from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict

from docx import Document

from medical_constants import TARGET_MEDICAL_FACILITY
from medical_docx_editor import (
    DocxBlockEditor,
    insert_paragraph_after,
    iter_all_paragraphs,
    remove_exact_paragraphs,
    remove_paragraph,
    replace_paragraph_regex_preserving_runs,
    set_paragraph_text,
)
from medical_expert import put_expert_anamnesis
from medical_formatting import (
    format_birth_for_person_line,
    format_date_with_russian_year_suffix,
    format_military_commissariat_area,
    format_psych_account_value,
    treatment_period_text,
)
from medical_gender import finalize_medical_document
from medical_markers import (
    COMMISSION_MARKERS,
    DISCHARGE_MARKERS,
    PRIMARY_MARKERS,
    RVK_MARKERS,
    SICK_LEAVE_VK_MARKERS,
    VK_MSE_MARKERS,
)
from medical_models import PatientData
from medical_parser_sanitize import sanitize_diagnosis
from medical_text_utils import normalize_match


class MedicalRendererLabsMixin:
    @staticmethod
    def _psych_account_line(data: PatientData) -> str:
        value = format_psych_account_value(
            data.psych_account_status, data.psych_account_since_year, data.psych_account
        )
        return f"На учёте у психиатров: {value}".rstrip()

    def _place_psych_account_after_registration(
        self, editor: DocxBlockEditor, data: PatientData, registration_markers, *, fallback_markers=()
    ) -> bool:
        # Always own this line at render time so template placeholders or a legacy
        # copy elsewhere in the document cannot survive.  Registration is optional
        # source data, therefore an empty address must not make the mandatory
        # psychiatric-account decision disappear from the generated document.
        editor.remove_all_matching_paragraphs(["На учёте у психиатров", "На учете у психиатров", "На учёте", "На учете"])
        idx = editor.find_paragraph_index(registration_markers)
        if idx is None and fallback_markers:
            idx = editor.find_paragraph_index(fallback_markers)
        if idx is None:
            return False
        insert_paragraph_after(editor.paragraphs[idx], self._psych_account_line(data))
        return True

    _HOSPITALIZATION_RECOMMENDATION_RE = re.compile(
        r"(?i)\s*\bцелесообразна\s+госпитализация\b"
        r"(?:[^.!?;\r\n]*?\bКДП\b[,.!?;]?|[^.!?;\r\n]*(?:[.!?;]+|$))\s*"
    )

    _TRAILING_COMPLAINT_RE = re.compile(
        r"(?is)\s*\bпациент(?:ка)?\s+предъявляет\s+жалобы\s+на\s+(?P<body>.+?)\s*$"
    )

    @staticmethod
    def _complaint_core(value: str) -> str:
        text = normalize_match(value).strip(" .,!?:;–—-")
        for prefix in (
            "жалобы на момент осмотра:",
            "жалобы при поступлении:",
            "жалобы:",
            "пациентка предъявляет жалобы на ",
            "пациент предъявляет жалобы на ",
        ):
            if text.startswith(prefix):
                text = text[len(prefix):].strip(" .,!?:;–—-")
                break
        return text

    @staticmethod
    def _complaints_equivalent(left: str, right: str) -> bool:
        left = MedicalRendererLabsMixin._complaint_core(left)
        right = MedicalRendererLabsMixin._complaint_core(right)
        if not left or not right:
            return False
        if left == right:
            return True
        # Legacy source documents sometimes switch grammatical case in the
        # duplicated prose sentence (e.g. «апатия» -> «апатию»).  A very high
        # similarity threshold is used only for the explicit trailing
        # «Пациент(ка) предъявляет жалобы на ...» form.
        return SequenceMatcher(None, left, right).ratio() >= 0.92

    @classmethod
    def _remove_trailing_clinical_leakage(cls, doc, data: PatientData) -> None:
        complaint_core = cls._complaint_core(data.complaints)
        for paragraph in list(iter_all_paragraphs(doc)):
            text = normalize_match(paragraph.text)
            if not text:
                continue
            if cls._HOSPITALIZATION_RECOMMENDATION_RE.search(paragraph.text):
                def _preserve_spacing(match: re.Match[str]) -> str:
                    before = match.string[:match.start()].strip()
                    after = match.string[match.end():].strip()
                    return " " if before and after else ""

                replace_paragraph_regex_preserving_runs(
                    paragraph, cls._HOSPITALIZATION_RECOMMENDATION_RE, _preserve_spacing
                )
                if not normalize_match(paragraph.text):
                    remove_paragraph(paragraph)
                    continue
                text = normalize_match(paragraph.text)

            # Keep the canonical «Жалобы...:» block.  Legacy templates can also
            # contain a second, standalone prose sentence at the document tail:
            # «Пациент(ка) предъявляет жалобы на ...».  That sentence is never a
            # canonical field in generated documents, so remove a standalone copy
            # deterministically instead of depending on similarity to current data.
            if text.startswith(("жалобы на момент осмотра:", "жалобы при поступлении:", "жалобы:")):
                continue
            if cls._TRAILING_COMPLAINT_RE.fullmatch(paragraph.text or ""):
                remove_paragraph(paragraph)
                continue
            if complaint_core and cls._complaint_core(paragraph.text) == complaint_core:
                remove_paragraph(paragraph)
                continue

            # For a legacy sentence embedded at the end of a larger paragraph,
            # preserve the old conservative behavior: remove it only when it is
            # equivalent to the canonical complaints value.
            trailing = cls._TRAILING_COMPLAINT_RE.search(paragraph.text)
            if trailing and complaint_core and cls._complaints_equivalent(trailing.group("body"), complaint_core):
                replace_paragraph_regex_preserving_runs(paragraph, cls._TRAILING_COMPLAINT_RE, "")
                if not normalize_match(paragraph.text):
                    remove_paragraph(paragraph)

    @staticmethod
    def _move_discharge_outcome_before_signatures(doc) -> bool:
        paragraphs = list(doc.paragraphs)
        outcome = next((p for p in paragraphs if normalize_match(p.text).startswith("за время лечения")), None)
        recommendation = next((p for p in paragraphs if normalize_match(p.text).startswith("рекомендовано")), None)
        signature = next((p for p in paragraphs if "врач-психиатр" in normalize_match(p.text) or normalize_match(p.text).startswith("зав. отд")), None)
        if signature is None or recommendation is None:
            return False
        if outcome is not None:
            signature._p.addprevious(outcome._p)
        signature._p.addprevious(recommendation._p)
        return True

    _LAB_RESULT_MARKERS = (
        "ОАК", "ОАМ", "RW", "HCV", "HBsAg", "ВИЧ", "Биохимия крови",
        "Глюкоза крови", "Кал на яйца глист", "Флюорография", "ЭКГ", "ЭЭГ",
    )

    @classmethod
    def _remove_template_lab_lines(cls, editor: DocxBlockEditor) -> None:
        """Never fabricate examination results from bundled template examples.

        Historical templates contain example values ("в норме", glucose 3.40,
        fixed ECG/EEG phrases and old dates). Until an explicit structured
        investigation source is wired into PatientData, publishing those rows
        would turn template examples into patient facts.
        """
        editor.remove_all_matching_paragraphs(cls._LAB_RESULT_MARKERS)

    @classmethod
    def _replace_lab_lines(cls, editor: DocxBlockEditor, dates: Dict[str, str]) -> None:
        # Compatibility entry point used by discharge/RVK renderers. Dates alone
        # are not evidence of a laboratory or instrumental result.
        cls._remove_template_lab_lines(editor)
