from __future__ import annotations

import re
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

    @classmethod
    def _remove_trailing_clinical_leakage(cls, doc, data: PatientData) -> None:
        complaint = normalize_match(data.complaints)
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
            # A legitimate complaint block starts with «Жалобы...:». A bare copy
            # of the complaint text elsewhere is leakage from the source/template.
            if complaint and text == complaint:
                remove_paragraph(paragraph)

    @staticmethod
    def _move_discharge_outcome_before_signatures(doc) -> bool:
        paragraphs = list(doc.paragraphs)
        outcome = next((p for p in paragraphs if normalize_match(p.text).startswith("за время лечения")), None)
        recommendation = next((p for p in paragraphs if normalize_match(p.text).startswith("рекомендовано")), None)
        signature = next((p for p in paragraphs if "врач-психиатр" in normalize_match(p.text) or normalize_match(p.text).startswith("зав. отд")), None)
        if signature is None or outcome is None or recommendation is None:
            return False
        signature._p.addprevious(outcome._p)
        signature._p.addprevious(recommendation._p)
        return True

    @staticmethod
    def _replace_lab_lines(editor: DocxBlockEditor, dates: Dict[str, str]) -> None:
        replacements = [
            (["ОАК"], f"ОАК - в норме - {dates['day1']}"),
            (["ОАМ"], f"ОАМ - в норме - {dates['day1']}"),
            (["RW"], f"RW - в норме - {dates['day1']}"),
            (["HCV"], f"HCV - в норме - {dates['day1']}"),
            (["HBsAg"], f"HBsAg - в норме - {dates['day1']}"),
            (["ВИЧ"], f"ВИЧ - в норме - {dates['day2']}"),
            (["Биохимия крови"], f"Биохимия крови - в норме - {dates['day1']}"),
            (["Глюкоза крови"], f"Глюкоза крови - 3,40 ммоль/л - {dates['day1']}"),
            (["Кал на яйца глист"], f"Кал на яйца глист - не обнаружены - {dates['day1']}"),
            (["Флюорография"], f"Флюорография - патологии не выявлено - {dates['flg']}"),
            (["ЭКГ"], f"ЭКГ - ритм синусовый, ЧСС 65 ударов в минуту, рисунок ЭКГ в пределах нормы, ЭОС нормальная - {dates['day1']}"),
        ]
        for markers, text in replacements:
            editor.replace_first_matching_paragraph(markers, text)
