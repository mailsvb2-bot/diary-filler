"""Regression lock for DOCX section-boundary integrity.

Generated patient text must never become template structure, and every renderer
alias used to locate a block must also be a valid boundary marker.
"""
from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document

from medical_constants import DOCUMENT_ORDER
from medical_docx_blocks import extract_docx_text
from medical_docx_editor import DocxBlockEditor
from medical_parser import MedicalTextParser
from generation_performance_profile import _make_fixture
from medical_markers import (
    COMMISSION_MARKERS,
    DISCHARGE_MARKERS,
    PRIMARY_MARKERS,
    RVK_MARKERS,
    SICK_LEAVE_VK_MARKERS,
    VK_MSE_MARKERS,
)
from medical_text_utils import normalize_match


REQUIRED_ALIASES = {
    "PRIMARY_MARKERS": {
        "ФИО",
        "Дата рождения",
        "Жалобы",
        "Диагноз",
        "Врач-психиатр",
        "Зав. отд.",
    },
    "DISCHARGE_MARKERS": {
        "Жалобы",
        "Психический статус",
        "Соматический статус",
    },
    "COMMISSION_MARKERS": {
        "Жалобы",
        "Психический статус",
        "Сомато-неврологический статус",
        "Диагноз",
    },
    "VK_MSE_MARKERS": {
        "Психический статус",
        "Соматический статус",
    },
    "SICK_LEAVE_VK_MARKERS": {
        "Психический статус",
        "Соматический статус",
    },
    "RVK_MARKERS": {
        "ФИО",
        "Соматический статус",
    },
}

MARKER_SETS = {
    "PRIMARY_MARKERS": PRIMARY_MARKERS,
    "DISCHARGE_MARKERS": DISCHARGE_MARKERS,
    "COMMISSION_MARKERS": COMMISSION_MARKERS,
    "VK_MSE_MARKERS": VK_MSE_MARKERS,
    "SICK_LEAVE_VK_MARKERS": SICK_LEAVE_VK_MARKERS,
    "RVK_MARKERS": RVK_MARKERS,
}


def _assert_alias_coverage() -> None:
    for name, required in REQUIRED_ALIASES.items():
        actual = {normalize_match(item) for item in MARKER_SETS[name]}
        missing = sorted(item for item in required if normalize_match(item) not in actual)
        if missing:
            raise AssertionError(f"{name} misses renderer boundary aliases: {missing}")


def _assert_inserted_marker_like_patient_text_never_becomes_structure() -> None:
    doc = Document()
    doc.add_paragraph("Жалобы")
    doc.add_paragraph("старые жалобы шаблона")
    doc.add_paragraph("Анамнез жизни")
    doc.add_paragraph("старый анамнез шаблона")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый психический статус шаблона")

    editor = DocxBlockEditor(doc)
    assert editor.replace_block(
        ["Жалобы"],
        "Жалобы:",
        "нарушение сна\nАнамнез жизни: эта строка является частью жалоб пациента",
        PRIMARY_MARKERS,
    )
    assert editor.replace_block(
        ["Анамнез жизни"],
        "Анамнез жизни:",
        "реальный анамнез жизни пациента",
        PRIMARY_MARKERS,
    )

    lines = [paragraph.text for paragraph in doc.paragraphs]
    assert "Жалобы: нарушение сна" in lines, lines
    assert "Анамнез жизни: эта строка является частью жалоб пациента" in lines, lines
    assert "Анамнез жизни: реальный анамнез жизни пациента" in lines, lines
    assert "старый анамнез шаблона" not in lines, lines
    assert "Психический статус" in lines, lines
    assert "старый психический статус шаблона" in lines, lines


def _assert_alias_boundary_stops_destructive_span_deletion() -> None:
    doc = Document()
    doc.add_paragraph("Жалобы при поступлении")
    doc.add_paragraph("старый текст жалоб")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый текст психического статуса")
    doc.add_paragraph("Диагноз")
    doc.add_paragraph("старый диагноз")

    editor = DocxBlockEditor(doc)
    assert editor.replace_block(
        ["Жалобы при поступлении"],
        "Жалобы при поступлении:",
        "новые жалобы",
        DISCHARGE_MARKERS,
    )

    lines = [paragraph.text for paragraph in doc.paragraphs]
    assert "Жалобы при поступлении: новые жалобы" in lines, lines
    assert "старый текст жалоб" not in lines, lines
    assert "Психический статус" in lines, lines
    assert "старый текст психического статуса" in lines, lines
    assert "Диагноз" in lines, lines


def _assert_long_source_block_is_not_cut_by_narrative_marker_words() -> None:
    narrative_lines = [
        f"Клинический фрагмент {index:03d}: состояние и динамика описаны подробно."
        for index in range(1, 121)
    ]
    narrative_lines[24] = (
        "Лечение ранее проводилось амбулаторно, переносимость терапии описана без отдельного раздела."
    )
    narrative_lines[59] = (
        "Диагноз ранее формулировался иначе, затем был уточнён в ходе наблюдения."
    )
    narrative_lines[94] = (
        "Психический статус в динамике менялся постепенно, что здесь является частью анамнеза."
    )
    narrative_lines.append(
        "КОНЕЦ_ДЛИННОГО_АНАМНЕЗА: этот хвост обязан сохраниться полностью."
    )

    source = (
        "Анамнез заболевания:\n"
        + "\n".join(narrative_lines)
        + "\nПсихический статус:\n"
        + "Контактен, ориентирован, отвечает по существу."
    )
    data = MedicalTextParser().parse_text(source)

    for required in (
        narrative_lines[0],
        narrative_lines[24],
        narrative_lines[59],
        narrative_lines[94],
        narrative_lines[-1],
    ):
        assert required in data.disease_anamnesis, (
            "long disease anamnesis was truncated before required text: "
            + required
        )
    assert "Психический статус:" not in data.disease_anamnesis, data.disease_anamnesis[-500:]
    assert "Контактен, ориентирован" in data.mental_status, data.mental_status


def _assert_long_multiline_docx_roundtrip_preserves_full_tail() -> None:
    doc = Document()
    doc.add_paragraph("Анамнез заболевания")
    doc.add_paragraph("старый текст шаблона")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый психический статус")
    doc.add_paragraph("Соматический статус")
    doc.add_paragraph("старый соматический статус")

    editor = DocxBlockEditor(doc)
    long_lines = [
        (
            f"Подробный анамнез {index:03d}: "
            + "наблюдение продолжалось, сведения сохранены без сокращения. " * 3
        ).strip()
        for index in range(1, 181)
    ]
    long_lines[40] = "Лечение ранее проводилось длительно; это часть текста анамнеза, а не заголовок."
    long_lines[90] = "Диагноз ранее уточнялся; эта строка тоже должна остаться внутри анамнеза."
    long_lines[-1] = "ФИНАЛЬНЫЙ_ХВОСТ_АНАМНЕЗА_ДОЛЖЕН_ОСТАТЬСЯ_В_DOCX"

    assert editor.replace_block(
        ["Анамнез заболевания"],
        "Анамнез заболевания:",
        "\n".join(long_lines),
        PRIMARY_MARKERS,
    )
    assert editor.replace_block(
        ["Психический статус"],
        "Психический статус:",
        "Контактен. Ориентирован. Доступен продуктивному контакту.",
        PRIMARY_MARKERS,
    )

    with TemporaryDirectory(prefix="medical-autofill-long-block-") as temp_dir:
        output = Path(temp_dir) / "long-block.docx"
        doc.save(output)
        reread = Document(output)
        lines = [paragraph.text for paragraph in reread.paragraphs]

    assert lines[0] == f"Анамнез заболевания: {long_lines[0]}", lines[:3]
    assert long_lines[40] in lines, "marker-like treatment narrative line disappeared"
    assert long_lines[90] in lines, "marker-like diagnosis narrative line disappeared"
    assert long_lines[-1] in lines, "large clinical block tail was truncated"
    assert "Психический статус: Контактен. Ориентирован. Доступен продуктивному контакту." in lines, lines[-8:]
    assert "Соматический статус" in lines, lines[-8:]
    assert "старый соматический статус" in lines, lines[-8:]


def _assert_table_and_run_fragmented_source_roundtrip() -> None:
    with TemporaryDirectory(prefix="medical-autofill-real-word-long-block-") as temp_dir:
        root = Path(temp_dir)
        source = root / "real-word-like-source.docx"
        doc = Document()
        table = doc.add_table(rows=1, cols=1)
        cell = table.cell(0, 0)

        heading = cell.paragraphs[0]
        run = heading.add_run("Анамнез ")
        run.bold = True
        run = heading.add_run("заболевания")
        run.italic = True
        heading.add_run(":")

        long_lines = [
            (
                f"РЕАЛЬНЫЙ_WORD_ФРАГМЕНТ_{index:03d}: "
                + "подробное клиническое описание сохранено полностью; " * 3
            ).strip()
            for index in range(1, 221)
        ]
        long_lines[37] = "Лечение ранее проводилось амбулаторно; это часть анамнеза, а не новый раздел."
        long_lines[81] = "Диагноз ранее менялся; строка обязана остаться внутри анамнеза."
        long_lines[126] = "Психический статус в динамике улучшался; здесь это повествовательный текст."
        long_lines[167] = "ЭПИ проводилось ранее; это не служебный блок ЭПИ."
        long_lines[193] = "ЭЭГ ранее без эпилептиформной активности; это часть анамнеза."
        long_lines[-1] = "РЕАЛЬНЫЙ_WORD_ФИНАЛ_НЕ_ОБРЕЗАТЬ"

        for index, line in enumerate(long_lines):
            paragraph = cell.add_paragraph()
            midpoint = max(1, len(line) // 2)
            left = paragraph.add_run(line[:midpoint])
            right = paragraph.add_run(line[midpoint:])
            if index % 3 == 0:
                left.bold = True
            if index % 5 == 0:
                right.italic = True

        mental_heading = cell.add_paragraph()
        mental_heading.add_run("Психический ").bold = True
        mental_heading.add_run("статус:")
        cell.add_paragraph("Контактен, ориентирован, отвечает по существу.")
        cell.add_paragraph("Соматический статус:")
        cell.add_paragraph("Без существенных особенностей.")
        doc.save(source)

        parsed = MedicalTextParser().parse_docx(source)
        for required in (
            long_lines[0],
            long_lines[37],
            long_lines[81],
            long_lines[126],
            long_lines[167],
            long_lines[193],
            long_lines[-1],
        ):
            assert required in parsed.disease_anamnesis, (
                "table/run-fragmented source was truncated before: " + required
            )
        assert "Контактен, ориентирован" in parsed.mental_status, parsed.mental_status

        navigation, service, data = _make_fixture(root)
        data.disease_anamnesis = parsed.disease_anamnesis
        data.mental_status = parsed.mental_status
        output = root / "real-word-like-output"
        created, _ = service.create_documents(
            navigation_path=navigation,
            output_dir=output,
            discharge_date=data.discharge_date,
            selected_docs=DOCUMENT_ORDER,
            override_data=data,
        )
        assert len(created) == len(DOCUMENT_ORDER), created
        for path in created:
            text = extract_docx_text(path)
            assert long_lines[0] in text, f"{path.name}: fragmented source start missing"
            assert long_lines[81] in text, f"{path.name}: diagnosis-like narrative disappeared"
            assert long_lines[167] in text, f"{path.name}: EPI-like narrative disappeared"
            assert long_lines[193] in text, f"{path.name}: EEG-like narrative disappeared"
            assert long_lines[-1] in text, f"{path.name}: fragmented source tail truncated"


def _assert_all_medical_forms_keep_long_clinical_tails() -> None:
    with TemporaryDirectory(prefix="medical-autofill-all-forms-long-text-") as temp_dir:
        root = Path(temp_dir)
        navigation, service, data = _make_fixture(root)

        disease_lines = [
            (
                f"АНАМНЕЗ_СТРОКА_{index:03d}: "
                + "подробное клиническое описание без сокращения; " * 4
            ).strip()
            for index in range(1, 141)
        ]
        disease_lines[35] = "Лечение ранее проводилось амбулаторно; это повествовательная строка внутри анамнеза."
        disease_lines[78] = "Диагноз ранее уточнялся неоднократно; эта строка не является заголовком раздела."
        disease_lines[-1] = "АНАМНЕЗ_ФИНАЛ_7_ФОРМ_НЕ_ОБРЕЗАТЬ"

        mental_lines = [
            f"ПСИХСТАТУС_СТРОКА_{index:03d}: контакт и ориентировка описаны полностью."
            for index in range(1, 91)
        ]
        mental_lines[-1] = "ПСИХСТАТУС_ФИНАЛ_7_ФОРМ_НЕ_ОБРЕЗАТЬ"

        data.disease_anamnesis = "\n".join(disease_lines)
        data.mental_status = "\n".join(mental_lines)
        data.registered = "Н. Новгород, Ленинский район, ул. Тестовая 10"
        data.examination_plan = "ОАК, ОАМ, ЭКГ, ФЛГ, ЭПИ, ЭЭГ."
        data.disease_anamnesis += (
            "\nВ настоящее время проживает с сестрой. "
            "Это клинический текст анамнеза и не является адресом регистрации."
        )

        output = root / "all-medical-forms"
        created, _ = service.create_documents(
            navigation_path=navigation,
            output_dir=output,
            discharge_date=data.discharge_date,
            selected_docs=DOCUMENT_ORDER,
            override_data=data,
        )
        assert len(created) == len(DOCUMENT_ORDER), created

        for path in created:
            text = extract_docx_text(path)
            assert disease_lines[0] in text, f"{path.name}: disease anamnesis start missing"
            assert disease_lines[35] in text, f"{path.name}: treatment-like narrative line missing"
            assert disease_lines[78] in text, f"{path.name}: diagnosis-like narrative line missing"
            assert disease_lines[-1] in text, f"{path.name}: disease anamnesis tail truncated"
            assert "проживает с сестрой" in text.lower(), f"{path.name}: residence narrative disappeared"
            assert "Н. Новгород, Ленинский район, ул. Тестовая 10" in text, (
                f"{path.name}: registration address missing"
            )
            assert not re.search(
                r"(?i)регистрац(?:ия|ии).*?проживает\s+с\s+сестрой",
                text,
            ), f"{path.name}: anamnesis leaked into registration header"
            if "План обследования" in text:
                assert "ЭПИ" in text and "ЭЭГ" in text, (
                    f"{path.name}: examination-plan EPI/EEG item was removed"
                )
            assert mental_lines[0] in text, f"{path.name}: mental status start missing"
            assert mental_lines[-1] in text, f"{path.name}: mental status tail truncated"


def verify() -> None:
    _assert_alias_coverage()
    _assert_inserted_marker_like_patient_text_never_becomes_structure()
    _assert_alias_boundary_stops_destructive_span_deletion()
    _assert_long_source_block_is_not_cut_by_narrative_marker_words()
    _assert_long_multiline_docx_roundtrip_preserves_full_tail()
    _assert_table_and_run_fragmented_source_roundtrip()
    _assert_all_medical_forms_keep_long_clinical_tails()
    print("DOCX BLOCK BOUNDARY REGRESSION OK: structural aliases + table/run-fragmented long-text integrity across all medical forms")


if __name__ == "__main__":
    verify()
