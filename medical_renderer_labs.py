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
    def _remove_trailing_clinical_leakage(cls, editor: DocxBlockEditor, data: PatientData) -> None:
        """Clean legacy template leakage without touching inserted patient prose."""
        complaint_core = cls._complaint_core(data.complaints)
        previous_nonempty_text = ""
        for paragraph in list(iter_all_paragraphs(editor.doc)):
            template_owned = editor.template_paragraph_text(paragraph) is not None
            text = normalize_match(paragraph.text)
            if not text:
                continue
            prior_nonempty_text = previous_nonempty_text
            previous_nonempty_text = text

            # The legacy parser can attach one trailing complaints sentence to the
            # epidemiology value when that sentence follows the epidemiology prose
            # in the source document.  This is the only source-owned cleanup done
            # here: remove that terminal duplicate only when it semantically
            # matches the already extracted complaints field.  Other patient prose
            # remains immutable.
            if not template_owned:
                trailing = cls._TRAILING_COMPLAINT_RE.search(paragraph.text)
                is_epi_paragraph = text.startswith("эпидемиологический анамнез:")
                is_epi_tail_paragraph = (
                    prior_nonempty_text.startswith("эпидемиологический анамнез:")
                    and cls._TRAILING_COMPLAINT_RE.fullmatch(paragraph.text or "") is not None
                )
                if (
                    trailing
                    and complaint_core
                    and (is_epi_paragraph or is_epi_tail_paragraph)
                    and cls._complaints_equivalent(trailing.group("body"), complaint_core)
                ):
                    replace_paragraph_regex_preserving_runs(
                        paragraph, cls._TRAILING_COMPLAINT_RE, ""
                    )
                    if not normalize_match(paragraph.text):
                        remove_paragraph(paragraph)
                        continue
                    text = normalize_match(paragraph.text)
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

    @staticmethod
    def _render_sourced_block(
        editor: DocxBlockEditor,
        *,
        aliases,
        label: str,
        value: str,
        all_markers,
        before_markers,
    ) -> bool:
        """Render a complete multiline source field with a structural fallback."""
        sourced = str(value or "").strip()
        if not sourced:
            editor.remove_all_matching_paragraphs(aliases)
            return False
        if editor.replace_block(
            aliases,
            label,
            sourced,
            all_markers,
            allow_empty=True,
        ):
            return True
        return editor.insert_block_before_first_matching_paragraph(
            before_markers,
            label,
            sourced,
        )

    @classmethod
    def _render_sourced_investigation_results(
        cls,
        editor: DocxBlockEditor,
        data: PatientData,
        all_markers,
        *,
        before_markers,
    ) -> bool:
        """Render only investigation text explicitly present in the source."""
        cls._remove_template_lab_lines(editor)
        aliases = ["Результаты обследований", "Результаты исследований"]
        value = str(getattr(data, "investigation_results", "") or "").strip()
        if not value:
            editor.remove_all_matching_paragraphs(aliases)
            return False
        return cls._render_sourced_block(
            editor,
            aliases=aliases,
            label="Результаты обследований:",
            value=value,
            all_markers=all_markers,
            before_markers=before_markers,
        )

    @classmethod
    def _replace_lab_lines(cls, editor: DocxBlockEditor, dates: Dict[str, str]) -> None:
        # Legacy compatibility only. Dates alone are not evidence of a result.
        cls._remove_template_lab_lines(editor)
