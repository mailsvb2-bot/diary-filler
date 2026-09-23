from __future__ import annotations

from pathlib import Path

from docx import Document

from medical_constants import TARGET_MEDICAL_FACILITY
from medical_docx_editor import (
    DocxBlockEditor,
    clear_paragraph_highlight,
    iter_all_paragraphs,
    set_paragraph_text,
)
from medical_expert import put_expert_anamnesis
from medical_formatting import (
    format_birth_for_person_line,
    format_date_with_russian_year_suffix,
    format_military_commissariat_area,
    format_registration_text,
    format_staff_short_name,
    treatment_period_text,
)
from medical_gender import finalize_medical_document, patient_gender
from medical_markers import (
    COMMISSION_MARKERS,
    DISCHARGE_MARKERS,
    PRIMARY_MARKERS,
    RVK_MARKERS,
    SICK_LEAVE_VK_MARKERS,
    VK_MSE_MARKERS,
)
from medical_models import PatientData, admission_occurrence_label, clean_admission_detail
from medical_parser_sanitize import sanitize_diagnosis
from medical_text_utils import normalize_match


class MedicalRendererSpecialMixin:
    @staticmethod
    def _clean_vk_purpose_instruction(editor: DocxBlockEditor) -> None:
        """Strip filling instructions only from the template-owned VK purpose row."""
        for paragraph in editor.paragraphs:
            if editor.template_paragraph_text(paragraph) is None:
                continue
            text = paragraph.text or ""
            if not normalize_match(text).startswith("цель направления на вк с обоснованием"):
                continue
            value = ""
            if "):" in text:
                value = text.split("):", 1)[1].strip()
            elif ":" in text:
                value = text.split(":", 1)[1].strip()
            set_paragraph_text(
                paragraph,
                f"Цель направления на ВК с обоснованием: {value}".rstrip(),
            )
            return

    @staticmethod
    def _finalize_vk_identity_lines(editor: DocxBlockEditor, data: PatientData) -> None:
        """Remove unresolved VK choices and fill upper signature placeholders."""
        editor.remove_exact_template_paragraphs(["(первичный, повторный)"])
        for paragraph in editor.paragraphs:
            if editor.template_paragraph_text(paragraph) is None:
                continue
            text = paragraph.text or ""
            if "_" not in text:
                continue
            normalized = normalize_match(text)
            if normalized.startswith("зав. отделением"):
                set_paragraph_text(
                    paragraph,
                    f"Зав. отделением {format_staff_short_name(data.head)}".rstrip(),
                )
            elif normalized.startswith("лечащий врач"):
                set_paragraph_text(
                    paragraph,
                    f"Лечащий врач {format_staff_short_name(data.doctor)}".rstrip(),
                )

    def render_vk_mse(self, template_path: str | Path, output_path: str | Path, data: PatientData) -> None:
        """ВК на МСЭ: заполняем факты пациента; прогнозы шаблона не публикуем."""
        doc = Document(str(template_path))
        editor = DocxBlockEditor(doc)

        if data.vk_date:
            editor.replace_first_matching_regex(r"^\s*\.?\s*\d{4}\s*$", data.vk_date)
        if data.vk_protocol_number:
            editor.replace_first_matching_paragraph(["Выписка из ПРОТОКОЛА"], f"Выписка из ПРОТОКОЛА № {data.vk_protocol_number}")
        if data.vk_protocol_date:
            editor.replace_first_matching_regex(r"^\s*От\s*\.?\s*\d{4}\s*г\.?\s*$", f"От {data.vk_protocol_date} г.")
            for paragraph in iter_all_paragraphs(doc):
                if normalize_match(paragraph.text).startswith("от "):
                    clear_paragraph_highlight(paragraph)

        editor.replace_all_matching_paragraphs(["Ф.И.О", "Ф.И.О:"], f"Ф.И.О: {data.fio}")
        editor.replace_all_matching_paragraphs(["Год рождения"], f"Год рождения: {data.birth}")
        editor.replace_all_matching_paragraphs(["Проживает", "Регистрация по адресу"], format_registration_text(data.registered))
        self._place_psych_account_after_registration(editor, data, ["Регистрация по адресу"], fallback_markers=["Ф.И.О", "Ф.И.О:"])
        vk_work_parts = [
            (data.vk_mse_work_org or data.work_org).strip(),
            (data.vk_mse_position or data.position).strip(),
        ]
        vk_work_line = ", ".join(part for part in vk_work_parts if part)
        editor.replace_all_matching_paragraphs(["Место работы"], f"Место работы: {vk_work_line}")
        editor.replace_all_matching_paragraphs(["Диагноз"], f"Диагноз: {sanitize_diagnosis(data.diagnosis)}")

        editor.replace_block(["Жалобы"], "Жалобы:", data.complaints, VK_MSE_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез жизни"], "Анамнез жизни:", data.life_anamnesis, VK_MSE_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез заболевания"], "Анамнез заболевания:", data.disease_anamnesis, VK_MSE_MARKERS, allow_empty=True)
        editor.replace_block(["Психический статус при поступлении", "Психический статус"], "Психический статус при поступлении:", data.mental_status, VK_MSE_MARKERS, allow_empty=True)
        if data.epi_text:
            editor.replace_block(["ЭПИ"], "ЭПИ -", data.epi_text, VK_MSE_MARKERS)
        else:
            editor.remove_all_matching_paragraphs(["ЭПИ"])
        editor.replace_block(["Сомато-неврологический статус", "Соматический статус"], "Сомато-неврологический статус:", data.somatic_status, VK_MSE_MARKERS, allow_empty=True)
        editor.replace_block(["Получает лечение"], "Получает лечение:", data.treatment_plan, VK_MSE_MARKERS)
        # The selected form itself proves only the routing decision to MSE.
        # Historical prognoses/functional-severity claims in the bundled template
        # are examples and must never become patient facts.
        editor.remove_all_matching_paragraphs([
            "Прогноз восстановления трудоспособности",
            "клинический:",
            "Клинический и трудовой прогноз",
        ])
        if not editor.replace_first_matching_paragraph(
            ["Цель направления на ВК"],
            "Цель направления на ВК с обоснованием: направление на МСЭ.",
        ):
            doc.add_paragraph("Цель направления на ВК с обоснованием: направление на МСЭ.")
        if not editor.replace_first_matching_paragraph(
            ["Решение ВК"],
            "Решение ВК: направить на МСЭ.",
        ):
            doc.add_paragraph("Решение ВК: направить на МСЭ.")
        self._clean_vk_purpose_instruction(editor)
        self._finalize_vk_identity_lines(editor, data)
        finalize_medical_document(doc, data)
        doc.save(str(output_path))

    def render_sick_leave_vk(self, template_path: str | Path, output_path: str | Path, data: PatientData) -> None:
        """ВК больничный: отдельная форма ВК для продления лечения/больничного."""
        doc = Document(str(template_path))
        editor = DocxBlockEditor(doc)

        # Верхняя дата, номер протокола и дата протокола работают так же, как в ВК на МСЭ.
        if data.sick_leave_vk_date:
            editor.replace_first_matching_regex(r"^\s*\.?\s*\d{4}\s*$", data.sick_leave_vk_date)
        if data.sick_leave_vk_protocol_number:
            editor.replace_first_matching_paragraph(["Выписка из ПРОТОКОЛА"], f"Выписка из ПРОТОКОЛА № {data.sick_leave_vk_protocol_number}")
        if data.sick_leave_vk_protocol_date:
            editor.replace_first_matching_regex(r"^\s*От\s*\.?\s*\d{4}\s*г\.?\s*$", f"От {data.sick_leave_vk_protocol_date} г.")
            for paragraph in iter_all_paragraphs(doc):
                if normalize_match(paragraph.text).startswith("от "):
                    clear_paragraph_highlight(paragraph)

        work_position = data.sick_leave_vk_work_position or ", ".join(
            part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part
        ).strip(", ") or ", ".join(part for part in [data.work_org, data.position] if part).strip(", ")
        treatment_line = treatment_period_text(data.admission_date, data.sick_leave_vk_commission_date or data.sick_leave_vk_date)

        editor.replace_all_matching_paragraphs(["Ф.И.О", "Ф.И.О:"], f"Ф.И.О: {data.fio}")
        editor.replace_all_matching_paragraphs(["Год рождения"], f"Год рождения: {data.birth}")
        editor.replace_all_matching_paragraphs(["Проживает", "Регистрация по адресу"], format_registration_text(data.registered))
        self._place_psych_account_after_registration(editor, data, ["Регистрация по адресу"], fallback_markers=["Ф.И.О", "Ф.И.О:"])
        editor.replace_all_matching_paragraphs(["Место работы"], f"Место работы, должность: {work_position}")
        editor.replace_all_matching_paragraphs(["Находится на лечении"], treatment_line)
        editor.replace_all_matching_paragraphs(["Диагноз"], f"Диагноз: {sanitize_diagnosis(data.diagnosis)}")

        editor.replace_block(["Жалобы"], "Жалобы:", data.complaints, SICK_LEAVE_VK_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез жизни"], "Анамнез жизни:", data.life_anamnesis, SICK_LEAVE_VK_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез заболевания"], "Анамнез заболевания:", data.disease_anamnesis, SICK_LEAVE_VK_MARKERS, allow_empty=True)
        editor.replace_block(["Психический статус при поступлении", "Психический статус"], "Психический статус при поступлении:", data.mental_status, SICK_LEAVE_VK_MARKERS, allow_empty=True)
        if data.epi_text:
            editor.replace_block(["ЭПИ"], "ЭПИ -", data.epi_text, SICK_LEAVE_VK_MARKERS)
        else:
            editor.remove_all_matching_paragraphs(["ЭПИ"])
        editor.replace_block(["Сомато-неврологический статус", "Соматический статус"], "Сомато-неврологический статус:", data.somatic_status, SICK_LEAVE_VK_MARKERS, allow_empty=True)
        editor.replace_block(["Получает лечение"], "Получает лечение:", data.treatment_plan, SICK_LEAVE_VK_MARKERS)
        editor.replace_first_matching_paragraph(
            ["Цель направления на ВК"],
            "Цель направления на ВК с обоснованием: продление лечения по листу нетрудоспособности.",
        )
        # Historical template text contains patient-specific prognoses and a
        # fixed 14-day commission decision. Those are examples, not evidence.
        # Remove prognosis rows and own the commission decision explicitly.
        editor.remove_all_matching_paragraphs([
            "Прогноз восстановления трудоспособности",
            "клинический:",
            "Клинический и трудовой прогноз",
        ])
        if not editor.replace_first_matching_paragraph(
            ["Решение ВК"],
            "Решение ВК: продлить лечение по листу нетрудоспособности.",
        ):
            doc.add_paragraph("Решение ВК: продлить лечение по листу нетрудоспособности.")
        self._finalize_vk_identity_lines(editor, data)
        finalize_medical_document(doc, data)
        doc.save(str(output_path))

    def render_rvk(self, template_path: str | Path, output_path: str | Path, data: PatientData) -> None:
        """Акт для РВК: нормативную шапку оставляем, заполняем поля ниже."""
        doc = Document(str(template_path))
        editor = DocxBlockEditor(doc)
        dates = data.lab_dates()

        act_number = data.rvk_act_number or data.case_number
        editor.replace_first_matching_paragraph(["О СОСТОЯНИИ"], f"О СОСТОЯНИИ ЗДОРОВЬЯ ГРАЖДАНИНА № {act_number}".rstrip())
        editor.replace_block(["История болезни №"], "История болезни №", data.case_number, RVK_MARKERS, preserve_when_empty=False, allow_empty=True)
        editor.replace_block(["Ф.И.О.", "ФИО"], "Ф.И.О.:", data.fio, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Год рождения"], "Год рождения:", data.birth, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Проживает", "Регистрация по адресу"], "Регистрация по адресу:", data.registered, RVK_MARKERS, allow_empty=True)
        self._place_psych_account_after_registration(editor, data, ["Регистрация по адресу"], fallback_markers=["Ф.И.О", "Ф.И.О:"])
        # В Акте для РВК строка "Место работы" не нужна: удаляем её из результата,
        # чтобы туда не попадали данные из направления или старые значения UI.
        editor.remove_all_matching_paragraphs(["Место работы"])
        gender = patient_gender(data)
        if gender == "female":
            period = f"Находилась на обследовании в {TARGET_MEDICAL_FACILITY} с {data.admission_date} по {data.discharge_date}".strip()
        elif gender == "male":
            period = f"Находился на обследовании в {TARGET_MEDICAL_FACILITY} с {data.admission_date} по {data.discharge_date}".strip()
        else:
            period = f"Период обследования в {TARGET_MEDICAL_FACILITY}: с {data.admission_date} по {data.discharge_date}".strip()
        editor.replace_first_matching_paragraph(["Находился на обследовании"], period)
        military_area = format_military_commissariat_area(data.rvk_military_commissariat)
        if military_area:
            editor.replace_first_matching_paragraph(
                ["Госпитализируется по направлению военного комиссариата"],
                f"Госпитализируется по направлению военного комиссариата {military_area}."
            )
        admission_label = admission_occurrence_label(data.admission_occurrence)
        if not editor.replace_block(
            ["В 3 отделение КДП поступает"],
            admission_label,
            clean_admission_detail(data.admission),
            RVK_MARKERS,
            allow_empty=True,
        ):
            admission_line = f"{admission_label} {clean_admission_detail(data.admission)}".strip()
            editor.insert_before_first_matching_paragraph(["Жалобы"], admission_line)
        editor.replace_block(["Жалобы"], "Жалобы:", data.complaints, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез жизни"], "Анамнез жизни:", data.life_anamnesis, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Анамнез заболевания"], "Анамнез заболевания:", data.disease_anamnesis, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Психический статус"], "Психический статус:", data.mental_status, RVK_MARKERS, allow_empty=True)
        editor.replace_block(["Сомато-неврологический статус", "Соматический статус"], "Сомато-неврологический статус:", data.somatic_status, RVK_MARKERS, allow_empty=True)
        self._replace_lab_lines(editor, dates)
        if data.epi_text:
            editor.replace_block(["ЭПИ"], "ЭПИ -", data.epi_text, RVK_MARKERS)
        else:
            editor.remove_all_matching_paragraphs(["ЭПИ"])
        # В шаблоне Акта РВК после блока ЭПИ/ЭЭГ есть служебная одиночная строка "ЭЭГ".
        # Она не относится к результату исследования и должна исчезать из итогового документа.
        editor.remove_exact_template_paragraphs(["ЭЭГ", "ЭПИ"])
        editor.replace_first_matching_paragraph(["Диагноз"], f"Диагноз: {sanitize_diagnosis(data.diagnosis)}")
        finalize_medical_document(doc, data)
        doc.save(str(output_path))
