from __future__ import annotations

from pathlib import Path
from typing import Dict

from docx import Document

from medical_constants import TARGET_MEDICAL_FACILITY
from medical_docx_editor import (
    DocxBlockEditor,
    iter_all_paragraphs,
    remove_exact_paragraphs,
    set_paragraph_text,
)
from medical_expert import put_expert_anamnesis
from medical_formatting import (
    format_birth_for_person_line,
    format_date_with_russian_year_suffix,
    format_military_commissariat_area,
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
