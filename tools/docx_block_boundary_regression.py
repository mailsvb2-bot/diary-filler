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
from medical_docx_editor_utils import paragraph_matches_marker
from medical_parser import MedicalTextParser
from medical_paths import bundled_template_path
from medical_service import MedicalDocumentService
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


def _assert_dated_historical_diagnoses_stay_inside_disease_anamnesis() -> None:
    """Historical inline diagnoses must not cut off the current anamnesis.

    This mirrors real referral documents where years of dated neurology/
    psychiatry history are written inside one «Анамнез заболевания» block.
    Only the later true top-level Diagnosis section may terminate/reclassify
    clinical text.
    """
    source = """Анамнез заболевания:
Родился от 1 беременности, протекавшей без патологии. Роды срочные, хроническая гипоксия плода.
07.02.2013 Невролог. Диагноз: Неврозоподобный синдром. Наблюдался амбулаторно.
24.07.2015 Невролог. Диагноз: Неврозоподобный синдром. Состояние без ухудшения.
25.01.2024 ЭПИ (ДО №4): находился на лечении, состояние стабилизировалось.
В сентябре 2024 года обратился самостоятельно, далее наблюдался у психиатра.
ФИНАЛ_ИСТОРИЧЕСКОГО_АНАМНЕЗА_НЕ_ОБРЕЗАТЬ.
Психический статус:
Контактен, ориентирован, отвечает по существу.
Соматический статус:
Без существенных особенностей.
Диагноз:
F20.8 Другой тип шизофрении
"""
    data = MedicalTextParser().parse_text(source)
    for required in (
        "07.02.2013 Невролог. Диагноз: Неврозоподобный синдром",
        "24.07.2015 Невролог. Диагноз: Неврозоподобный синдром",
        "25.01.2024 ЭПИ (ДО №4): находился на лечении",
        "В сентябре 2024 года обратился самостоятельно",
        "ФИНАЛ_ИСТОРИЧЕСКОГО_АНАМНЕЗА_НЕ_ОБРЕЗАТЬ",
    ):
        assert required in data.disease_anamnesis, data.disease_anamnesis
    assert "Психический статус:" not in data.disease_anamnesis, data.disease_anamnesis
    assert "Контактен, ориентирован" in data.mental_status, data.mental_status
    assert data.diagnosis == "F20.8 Другой тип шизофрении", data.diagnosis


def _assert_dated_historical_clinical_sublabels_stay_inside_disease_anamnesis() -> None:
    """Dated historical sublabels are event details, not current top-level sections."""
    source = """Анамнез заболевания:
Начало заболевания постепенное.
07.02.2013 Невролог. Диагноз: F06.8 Исторический диагноз. Жалобы: головные боли. Психический статус: спокоен. Соматический статус: без особенностей. Лечение: магний.
24.07.2015 Психиатр. Жалобы: тревога. Психический статус: напряжён. Лечение: амбулаторная терапия.
Ноябрь 2024 Психиатр. Диагноз: F20.8 Историческая формулировка. Лечение: скорректировано амбулаторно.
В сентябре 2025 года Психиатр. Жалобы: нарушения сна. Психический статус: без психотической симптоматики.
25.01.2024 Контроль. Результаты обследований: ЭЭГ без отрицательной динамики.
ФИНАЛ_ДАТИРОВАННОЙ_ИСТОРИИ_НЕ_ОБРЕЗАТЬ.
Психический статус:
Контактен, ориентирован, отвечает по существу.
Соматический статус:
Состояние удовлетворительное.
План лечения:
Рисперидон 2 мг вечером.
Диагноз:
F20.8 Другой тип шизофрении
"""
    data = MedicalTextParser().parse_text(source)
    for required in (
        "07.02.2013 Невролог. Диагноз: F06.8 Исторический диагноз.",
        "Жалобы: головные боли.",
        "Психический статус: спокоен.",
        "Соматический статус: без особенностей.",
        "Лечение: магний.",
        "24.07.2015 Психиатр. Жалобы: тревога.",
        "Психический статус: напряжён.",
        "Лечение: амбулаторная терапия.",
        "Ноябрь 2024 Психиатр. Диагноз: F20.8 Историческая формулировка.",
        "Лечение: скорректировано амбулаторно.",
        "В сентябре 2025 года Психиатр. Жалобы: нарушения сна.",
        "Психический статус: без психотической симптоматики.",
        "25.01.2024 Контроль. Результаты обследований: ЭЭГ без отрицательной динамики.",
        "ФИНАЛ_ДАТИРОВАННОЙ_ИСТОРИИ_НЕ_ОБРЕЗАТЬ.",
    ):
        assert required in data.disease_anamnesis, (required, data.disease_anamnesis)
    assert data.mental_status == "Контактен, ориентирован, отвечает по существу.", data.mental_status
    assert data.somatic_status == "Состояние удовлетворительное.", data.somatic_status
    assert data.treatment_plan == "Рисперидон 2 мг вечером.", data.treatment_plan
    assert data.diagnosis == "F20.8 Другой тип шизофрении", data.diagnosis


def _assert_historical_chronology_variant_matrix() -> None:
    """Date-format and split-line history variants must not steal current fields."""
    variants = (
        "07.02.2013 Невролог. Диагноз: F06.8 Исторический диагноз.",
        "7/2/2013 Невролог. Диагноз: F06.8 Исторический диагноз.",
        "07-02-13 Невролог. Диагноз: F06.8 Исторический диагноз.",
        "02.2014 Невролог. Диагноз: F06.8 Исторический диагноз.",
        "02/2015 Невролог. Лечение: историческая терапия.",
        "12 февраля 2016 г. Психиатр. Диагноз: F06.8 Исторический диагноз.",
        "Февраль 2017 Психиатр. Жалобы: историческая тревога.",
        "В феврале 2018 года Психиатр. Психический статус: исторически напряжён.",
        "Осенью 2019 года Психиатр. Соматический статус: без особенностей.",
        "Начало наблюдения. В 2020 году был выставлен диагноз: F06.8 Исторический диагноз.",
        "Начало наблюдения. В 2020 г. был выставлен диагноз: F06.8 Исторический диагноз.",
        "Начало наблюдения. В 2020 был выставлен диагноз: F06.8 Исторический диагноз.",
        "07.02.2021 Невролог.\nДиагноз: F06.8 Исторический диагноз.",
        "Ноябрь 2022 Психиатр.\nЖалобы: историческая тревога.",
        "Ранее был выставлен диагноз: F06.8 Исторический диагноз.",
        "До настоящей госпитализации был выставлен диагноз: F06.8 Исторический диагноз.",
        "В анамнезе был выставлен диагноз: F06.8 Исторический диагноз.",
        "На предыдущем этапе был выставлен диагноз: F06.8 Исторический диагноз.",
        "При предыдущей госпитализации был выставлен диагноз: F06.8 Исторический диагноз.",
        "Амбулаторно был выставлен диагноз: F06.8 Исторический диагноз.",
    )
    for index, history_fragment in enumerate(variants):
        source = f"""Жалобы:
текущие жалобы
Анамнез заболевания:
Начало текущего анамнеза.
{history_fragment}
После исторического события наблюдение продолжалось.
ФИНАЛ_ВАРИАНТА_{index}_НЕ_ОБРЕЗАТЬ.
Психический статус:
Текущий психический статус.
Соматический статус:
Текущий соматический статус.
План лечения:
Текущее лечение.
Диагноз:
F20.8 Текущий диагноз
"""
        data = MedicalTextParser().parse_text(source)
        assert f"ФИНАЛ_ВАРИАНТА_{index}_НЕ_ОБРЕЗАТЬ" in data.disease_anamnesis, (
            history_fragment,
            data.disease_anamnesis,
        )
        assert data.complaints == "текущие жалобы", (history_fragment, data.complaints)
        assert data.mental_status == "Текущий психический статус.", (
            history_fragment,
            data.mental_status,
        )
        assert data.somatic_status == "Текущий соматический статус.", (
            history_fragment,
            data.somatic_status,
        )
        assert data.treatment_plan == "Текущее лечение.", (
            history_fragment,
            data.treatment_plan,
        )
        assert data.diagnosis == "F20.8 Текущий диагноз", (
            history_fragment,
            data.diagnosis,
        )

    # A completed historical sentence must not poison the *next* real current
    # section. The historical-context detector is intentionally scoped to the
    # unfinished sentence containing the marker, unlike strong date evidence.
    for completed_history in (
        "Ранее наблюдался амбулаторно.",
        "До настоящей госпитализации регулярно посещал психиатра.",
        "В анамнезе отмечались эпизоды тревоги.",
        "На предыдущем этапе состояние было нестабильным.",
    ):
        source = (
            "Анамнез заболевания: Начало болезни. "
            + completed_history
            + " Психический статус: Текущий психический статус. "
            "Соматический статус: Текущий соматический статус. "
            "План лечения: Текущее лечение. "
            "Диагноз: F20.8 Текущий диагноз"
        )
        data = MedicalTextParser().parse_text(source)
        assert completed_history in data.disease_anamnesis, (
            completed_history,
            data.disease_anamnesis,
        )
        assert data.mental_status == "Текущий психический статус.", (
            completed_history,
            data.mental_status,
        )
        assert data.somatic_status == "Текущий соматический статус.", (
            completed_history,
            data.somatic_status,
        )
        assert data.treatment_plan == "Текущее лечение.", (
            completed_history,
            data.treatment_plan,
        )
        assert data.diagnosis == "F20.8 Текущий диагноз", (
            completed_history,
            data.diagnosis,
        )


def _assert_historical_diagnosis_phrase_never_becomes_current_fallback() -> None:
    """A historical «был выставлен диагноз» must not suppress current diagnosis input."""
    historical_only = """Анамнез заболевания:
Начало заболевания постепенное.
В 2020 году был выставлен диагноз: F06.8 Исторический диагноз.
После этого наблюдался амбулаторно.
Психический статус:
Контактен, ориентирован.
Соматический статус:
Без особенностей.
План лечения:
Терапия по схеме.
"""
    parsed = MedicalTextParser().parse_text(historical_only)
    assert parsed.diagnosis == "", parsed.diagnosis
    assert "В 2020 году был выставлен диагноз: F06.8 Исторический диагноз." in parsed.disease_anamnesis

    historical_wording_only = """Анамнез заболевания:
Ранее был выставлен диагноз F06.8 Исторический диагноз.
После этого наблюдался амбулаторно.
Психический статус:
Контактен.
"""
    parsed = MedicalTextParser().parse_text(historical_wording_only)
    assert parsed.diagnosis == "", parsed.diagnosis

    current_phrase = """Жалобы:
тревога
Анамнез заболевания:
Текущее ухудшение в течение месяца.
Психический статус:
Контактен, ориентирован.
План лечения:
Терапия по схеме.
По итогам настоящего обследования был выставлен диагноз F20.8 Текущий диагноз
"""
    parsed = MedicalTextParser().parse_text(current_phrase)
    assert parsed.diagnosis == "F20.8 Текущий диагноз", parsed.diagnosis


def _assert_real_referral_to_discharge_roundtrip_keeps_full_dated_history() -> None:
    """Lock the exact parser -> PatientData -> discharge path behind PR #333.

    Real referral documents commonly keep many years of dated neurology and
    psychiatry observations inside one disease-anamnesis section. Historical
    inline diagnosis phrases without an F-code belong to that history and must
    survive the generated discharge epicrisis byte-for-byte and in order.
    """

    with TemporaryDirectory(prefix="medical-autofill-source-fidelity-") as temp_dir:
        root = Path(temp_dir)
        source = root / "направление на госпитализацию.docx"
        doc = Document()
        doc.add_paragraph("09.05.2026 Первичный осмотр")
        doc.add_paragraph("История болезни № 353")
        doc.add_paragraph("Ф.И.О.: Маркер Истории Тестовый")
        doc.add_paragraph("Год рождения: 26.09.2008")
        doc.add_paragraph("Проживает: Нижний Новгород, тестовый район, дом 24-12")
        doc.add_paragraph("Место работы: не работает")
        doc.add_paragraph("На учёте у психиатров состоит с сентября 2024 года")
        doc.add_paragraph("В 3 отделение КДП поступает: повторно")
        complaints = "тревога, плохой сон"
        life = "Наследственность не отягощена. Рос и развивался соответственно возрасту."
        mental = "Контактен, ориентирован, отвечает по существу."
        somatic = "Состояние удовлетворительное."
        treatment = "Рисперидон 2 мг вечером."
        diagnosis = "F20.8 Другой тип шизофрении"

        doc.add_paragraph(f"Жалобы на момент осмотра: {complaints}")
        doc.add_paragraph("Анамнез жизни:")
        doc.add_paragraph(life)
        doc.add_paragraph("Анамнез заболевания:")
        history = [
            "Родился от 1 беременности, протекавшей без патологии. Роды срочные.",
            "Отец работает в ООО Чужой Завод, мать работает врачом. Это сведения о семье, не о пациенте.",
            "07.02.2013 Невролог. Диагноз: Неврозоподобный синдром. Наблюдался амбулаторно.",
            "24.07.2015 Невролог. Диагноз: Неврозоподобный синдром. Состояние без ухудшения.",
            "25.01.2024 ЭПИ (ДО №4): находился на лечении, состояние стабилизировалось.",
            "В сентябре 2024 года самостоятельно обратился к психиатру.",
            "После выписки продолжал наблюдение амбулаторно, рекомендации выполнял.",
            "ФИНАЛ_РЕАЛЬНОГО_АНАМНЕЗА_НЕ_ОБРЕЗАТЬ.",
        ]
        for line in history:
            doc.add_paragraph(line)
        doc.add_paragraph("Психический статус:")
        doc.add_paragraph(mental)
        doc.add_paragraph("Соматический статус:")
        doc.add_paragraph(somatic)
        doc.add_paragraph("План лечения:")
        doc.add_paragraph(treatment)
        doc.add_paragraph("Диагноз:")
        doc.add_paragraph(diagnosis)
        doc.save(source)

        service = MedicalDocumentService()
        parsed = service.parse_navigation(source)
        for line in history:
            assert parsed.disease_anamnesis.count(line) == 1, (
                "source parse lost/duplicated dated history: ",
                line,
                parsed.disease_anamnesis,
            )
        assert parsed.complaints == complaints, parsed.complaints
        assert parsed.life_anamnesis == life, parsed.life_anamnesis
        assert parsed.mental_status == mental, parsed.mental_status
        assert parsed.somatic_status == somatic, parsed.somatic_status
        assert parsed.treatment_plan == treatment, parsed.treatment_plan
        assert parsed.diagnosis == diagnosis, parsed.diagnosis
        assert parsed.psych_account == "состоит с сентября 2024 года", parsed.psych_account
        assert parsed.work_org == "", parsed.work_org
        assert parsed.position == "", parsed.position

        parsed.discharge_date = "05.10.2026"
        parsed.admission_occurrence = "повторно"
        parsed.psych_account_status = "да"
        parsed.psych_account_since_year = "2024"
        parsed.expert_work_status = "нет"
        parsed.expert_sick_leave_needed = "нет"

        created, _ = service.create_documents(
            navigation_path=source,
            output_dir=root / "generated",
            discharge_date=parsed.discharge_date,
            selected_docs=("discharge",),
            override_data=parsed,
        )
        assert len(created) == 1, created
        output_text = extract_docx_text(created[0])

        # Identity/episode facts were already stable in the v1.4.19/v1.4.20
        # production line. Keep that historical contract while hardening the
        # richer clinical-source path.
        for expected in (
            "Выписной эпикриз № 353",
            "Маркер Истории Тестовый",
            "26.09.2008 г.р.",
            "регистрация по адресу: Нижний Новгород, тестовый район, дом 24-12",
            "с 09.05.2026 по 05.10.2026",
            "В 3 отделение КДП поступает повторно",
        ):
            assert expected in output_text, (expected, output_text)

        positions = []
        for line in history:
            assert output_text.count(line) == 1, (
                f"generated discharge lost/duplicated dated history {line!r}; "
                f"count={output_text.count(line)}"
            )
            positions.append(output_text.find(line))
        assert positions == sorted(positions), positions
        assert "ФИНАЛ_РЕАЛЬНОГО_АНАМНЕЗА_НЕ_ОБРЕЗАТЬ." in output_text, output_text
        clinical_expectations = (
            f"Жалобы при поступлении: {complaints}",
            f"Анамнез жизни: {life}",
            f"Психический статус при поступлении: {mental}",
            f"Сомато-неврологический статус: {somatic}",
            f"Лечение: {treatment}",
            f"Диагноз: {diagnosis}",
            "На учёте у психиатров: состоит с сентября 2024 года",
        )
        for expected in clinical_expectations:
            assert output_text.count(expected) == 1, (
                f"generated discharge lost/duplicated clinical payload {expected!r}; "
                f"count={output_text.count(expected)}"
            )

        # The same real-world source explicitly says that the patient does not
        # work and contains no sick-leave fact. Once the doctor confirms
        # "больничный не нужен", the discharge must preserve that expert state
        # without inventing an opening date or silently dropping the expert
        # anamnesis from the document.
        assert "Экспертный анамнез: Не работает. В выдаче ЛН не нуждается." in output_text, output_text
        assert "Больничный лист открыт с" not in output_text, output_text
        assert "Больничный лист нужен" not in output_text, output_text


def _assert_narrative_marker_words_never_replace_target_fields() -> None:
    source = """Анамнез заболевания:
Начало заболевания постепенное.
Лечение ранее проводилось амбулаторно и было малоэффективным.
Диагноз ранее формулировался иначе.
Психический статус в динамике менялся постепенно.
ФИНАЛ_АНАМНЕЗА_НЕ_СМЕШИВАТЬ.
Психический статус:
Контактен, ориентирован, отвечает по существу.
Соматический статус:
Без существенных особенностей.
Лечение:
Галоперидол 5 мг вечером.
Диагноз:
F41.2 Смешанное тревожное и депрессивное расстройство
"""
    data = MedicalTextParser().parse_text(source)

    for required in (
        "Лечение ранее проводилось амбулаторно",
        "Диагноз ранее формулировался иначе",
        "Психический статус в динамике менялся постепенно",
        "ФИНАЛ_АНАМНЕЗА_НЕ_СМЕШИВАТЬ",
    ):
        assert required in data.disease_anamnesis, data.disease_anamnesis

    assert data.mental_status == "Контактен, ориентирован, отвечает по существу.", data.mental_status
    assert data.treatment_plan == "Галоперидол 5 мг вечером.", data.treatment_plan
    assert data.diagnosis.startswith("F41.2"), data.diagnosis
    assert "Смешанное тревожное и депрессивное расстройство" in data.diagnosis, data.diagnosis

    assert "в динамике менялся" not in data.mental_status, data.mental_status
    assert "ранее проводилось" not in data.treatment_plan, data.treatment_plan
    assert "ранее формулировался" not in data.diagnosis, data.diagnosis


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


def _assert_1250_line_clinical_block_survives_full_roundtrip() -> None:
    """A very large clinical block must have no hidden line-count truncation."""
    with TemporaryDirectory(prefix="medical-autofill-1250-line-stress-") as temp_dir:
        root = Path(temp_dir)
        source = root / "stress-1250-lines.docx"
        doc = Document()
        doc.add_paragraph("10.06.2026 Первичный осмотр")
        doc.add_paragraph("Ф.И.О.: Маркер Женская Тестовая")
        doc.add_paragraph("Дата рождения: 01.01.1980")
        doc.add_paragraph("Анамнез заболевания:")

        stress_lines = [
            (
                f"СТРЕСС_АНАМНЕЗ_СТРОКА_{index:04d}: "
                + "подробное клиническое описание должно сохраниться целиком без ограничения числа строк; " * 2
            ).strip()
            for index in range(1, 1251)
        ]
        stress_lines[249] = (
            "СТРЕСС_АНАМНЕЗ_СТРОКА_0250: Лечение ранее проводилось амбулаторно; "
            "это повествовательный текст, а не новый структурный раздел."
        )
        stress_lines[499] = (
            "СТРЕСС_АНАМНЕЗ_СТРОКА_0500: Диагноз ранее уточнялся; "
            "эта строка остаётся внутри длинного анамнеза."
        )
        stress_lines[749] = (
            "СТРЕСС_АНАМНЕЗ_СТРОКА_0750: Психический статус в динамике улучшался; "
            "это часть анамнеза, а не заголовок."
        )
        stress_lines[999] = (
            "СТРЕСС_АНАМНЕЗ_СТРОКА_1000: ЭПИ и ЭЭГ ранее выполнялись; "
            "эти слова внутри повествования не должны обрывать блок."
        )
        stress_tail = "СТРЕСС_АНАМНЕЗ_ФИНАЛ_1250_PLUS_НЕ_ОБРЕЗАТЬ"

        for index, line in enumerate(stress_lines):
            paragraph = doc.add_paragraph()
            split_at = max(1, len(line) // 2)
            paragraph.add_run(line[:split_at]).bold = index % 11 == 0
            paragraph.add_run(line[split_at:]).italic = index % 13 == 0
        doc.add_paragraph(stress_tail)
        doc.add_paragraph("Психический статус:")
        doc.add_paragraph("Контактен, ориентирован, отвечает по существу.")
        doc.add_paragraph("Соматический статус:")
        doc.add_paragraph("Без существенных особенностей.")
        doc.add_paragraph("План обследования:")
        doc.add_paragraph("ОАК, ОАМ, ЭКГ, ФЛГ.")
        doc.add_paragraph("План лечения:")
        doc.add_paragraph("Терапия по назначению врача.")
        doc.add_paragraph("Диагноз:")
        doc.add_paragraph("F41.2 Тестовый диагноз")
        doc.save(source)

        parsed = MedicalTextParser().parse_docx(source)
        parsed_lines = [
            line.strip()
            for line in parsed.disease_anamnesis.splitlines()
            if line.strip()
        ]
        assert len(parsed_lines) == 1251, (
            f"1250+ line source changed line count: {len(parsed_lines)}"
        )
        for required in (
            stress_lines[0],
            stress_lines[249],
            stress_lines[499],
            stress_lines[749],
            stress_lines[999],
            stress_lines[-1],
            stress_tail,
        ):
            assert required in parsed.disease_anamnesis, (
                "1250+ line source was truncated before required text: " + required
            )

        navigation, service, data = _make_fixture(root)
        data.disease_anamnesis = parsed.disease_anamnesis
        data.mental_status = parsed.mental_status
        data.somatic_status = parsed.somatic_status
        output = root / "stress-1250-line-output"
        created, _ = service.create_documents(
            navigation_path=navigation,
            output_dir=output,
            discharge_date=data.discharge_date,
            selected_docs=DOCUMENT_ORDER,
            override_data=data,
        )
        assert len(created) == len(DOCUMENT_ORDER), created

        expected_ids = {
            f"СТРЕСС_АНАМНЕЗ_СТРОКА_{index:04d}"
            for index in range(1, 1251)
        }
        for path in created:
            text = extract_docx_text(path)
            actual_ids = set(re.findall(r"СТРЕСС_АНАМНЕЗ_СТРОКА_\d{4}", text))
            assert actual_ids == expected_ids, (
                f"{path.name}: 1250-line clinical block lost IDs; "
                f"missing={sorted(expected_ids - actual_ids)[:10]}, "
                f"extra={sorted(actual_ids - expected_ids)[:10]}"
            )
            assert stress_tail in text, f"{path.name}: 1250+ line final tail was truncated"


def _assert_all_major_clinical_blocks_survive_long_roundtrip() -> None:
    """Large complaints/life/somatic blocks must survive parse + all 7 renderers."""
    with TemporaryDirectory(prefix="medical-autofill-all-major-long-blocks-") as temp_dir:
        root = Path(temp_dir)
        source = root / "all-major-clinical-blocks.docx"
        doc = Document()
        doc.add_paragraph("10.06.2026 Первичный осмотр")
        doc.add_paragraph("Ф.И.О.: Маркер Женская Тестовая")
        doc.add_paragraph("Дата рождения: 01.01.1980")

        complaints = [
            (
                f"ЖАЛОБЫ_СТРОКА_{index:03d}: "
                + "подробное описание жалоб сохранено без сокращения; " * 3
            ).strip()
            for index in range(1, 101)
        ]
        complaints[21] = (
            "Диагноз соматического заболевания ранее обсуждался с терапевтом; "
            "это часть жалоб, а не заголовок раздела."
        )
        complaints[57] = (
            "Лечение боли ранее давало кратковременный эффект; "
            "эта строка остаётся внутри жалоб."
        )
        complaints[-1] = "ЖАЛОБЫ_ФИНАЛ_НЕ_ОБРЕЗАТЬ"

        life = [
            (
                f"ЖИЗНЬ_СТРОКА_{index:03d}: "
                + "биографические сведения и социальный анамнез сохранены полностью; " * 3
            ).strip()
            for index in range(1, 111)
        ]
        life[29] = (
            "Психический статус родственников подробно не оценивался; "
            "это повествовательная строка анамнеза жизни."
        )
        life[72] = (
            "Лечение в детстве проводилось по поводу соматического заболевания; "
            "это не новый раздел лечения."
        )
        life[-1] = "АНАМНЕЗ_ЖИЗНИ_ФИНАЛ_НЕ_ОБРЕЗАТЬ"

        disease = [
            "Заболевание развивалось постепенно.",
            "Сведения о динамике состояния сохранены.",
        ]
        mental = [
            "Контактен, ориентирован, отвечает по существу.",
            "Эмоциональные реакции адекватны ситуации.",
        ]

        somatic = [
            (
                f"СОМАТИКА_СТРОКА_{index:03d}: "
                + "соматические данные описаны подробно и без сокращения; " * 3
            ).strip()
            for index in range(1, 121)
        ]
        somatic[33] = (
            "Диагноз терапевта ранее уточнялся амбулаторно; "
            "эта фраза является частью соматического статуса."
        )
        somatic[78] = (
            "ЭЭГ ранее выполнялась без патологической активности; "
            "эта строка не является служебным заголовком."
        )
        somatic[96] = (
            "Лечение сопутствующей патологии продолжается; "
            "это повествовательная строка соматического статуса."
        )
        somatic[-1] = "СОМАТИЧЕСКИЙ_ФИНАЛ_НЕ_ОБРЕЗАТЬ"

        def add_block(title: str, lines: list[str]) -> None:
            heading = doc.add_paragraph()
            midpoint = max(1, len(title) // 2)
            heading.add_run(title[:midpoint]).bold = True
            heading.add_run(title[midpoint:] + ":")
            for index, line in enumerate(lines):
                paragraph = doc.add_paragraph()
                split_at = max(1, len(line) // 2)
                paragraph.add_run(line[:split_at]).bold = index % 4 == 0
                paragraph.add_run(line[split_at:]).italic = index % 6 == 0

        add_block("Жалобы", complaints)
        add_block("Анамнез жизни", life)
        add_block("Анамнез заболевания", disease)
        add_block("Психический статус", mental)
        add_block("Соматический статус", somatic)
        add_block("План обследования", ["ОАК, ОАМ, ЭКГ, ФЛГ."])
        add_block("План лечения", ["Терапия по назначению врача."])
        add_block("Диагноз", ["F41.2 Тестовый диагноз"])
        doc.save(source)

        parsed = MedicalTextParser().parse_docx(source)
        parser_checks = (
            ("complaints", parsed.complaints, complaints),
            ("life_anamnesis", parsed.life_anamnesis, life),
            ("somatic_status", parsed.somatic_status, somatic),
        )
        for field_name, value, lines in parser_checks:
            for required in (lines[0], lines[len(lines) // 2], lines[-1]):
                assert required in value, (
                    f"{field_name} was truncated before required text: {required}"
                )

        navigation, service, data = _make_fixture(root)
        data.complaints = parsed.complaints
        data.life_anamnesis = parsed.life_anamnesis
        data.disease_anamnesis = parsed.disease_anamnesis
        data.mental_status = parsed.mental_status
        data.somatic_status = parsed.somatic_status

        output = root / "all-major-clinical-blocks-output"
        created, _ = service.create_documents(
            navigation_path=navigation,
            output_dir=output,
            discharge_date=data.discharge_date,
            selected_docs=DOCUMENT_ORDER,
            override_data=data,
        )
        assert len(created) == len(DOCUMENT_ORDER), created

        sentinels = (
            complaints[0],
            complaints[-1],
            life[0],
            life[-1],
            somatic[0],
            somatic[-1],
        )
        for path in created:
            text = extract_docx_text(path)
            for sentinel in sentinels:
                assert sentinel in text, f"{path.name}: lost long-block sentinel {sentinel}"


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



def _assert_cross_field_order_and_isolation_survive_full_roundtrip() -> None:
    """Clinical blocks must keep source order and must never absorb neighboring fields."""
    with TemporaryDirectory(prefix="medical-autofill-cross-field-order-") as temp_dir:
        root = Path(temp_dir)
        source = root / "cross-field-order.docx"
        doc = Document()
        doc.add_paragraph("10.06.2026 Первичный осмотр")
        doc.add_paragraph("Ф.И.О.: Маркер Женская Тестовая")
        doc.add_paragraph("Дата рождения: 01.01.1980")

        blocks = {
            "complaints": (
                "Жалобы",
                [
                    "ЖАЛОБЫ_ORDER_01 начало жалоб.",
                    "Диагноз ранее обсуждался соматическим врачом; это часть жалоб.",
                    "ЖАЛОБЫ_ORDER_03 конец жалоб.",
                ],
            ),
            "life_anamnesis": (
                "Анамнез жизни",
                [
                    "ЖИЗНЬ_ORDER_01 начало анамнеза жизни.",
                    "Лечение в детстве проводилось амбулаторно; это часть анамнеза жизни.",
                    "ЖИЗНЬ_ORDER_03 конец анамнеза жизни.",
                ],
            ),
            "disease_anamnesis": (
                "Анамнез заболевания",
                [
                    "БОЛЕЗНЬ_ORDER_01 начало анамнеза заболевания.",
                    "Психический статус в динамике менялся постепенно; это часть анамнеза заболевания.",
                    "БОЛЕЗНЬ_ORDER_03 конец анамнеза заболевания.",
                ],
            ),
            "mental_status": (
                "Психический статус",
                [
                    "ПСИХСТАТУС_ORDER_01 контактен и ориентирован.",
                    "Лечение обсуждает спокойно; это описание психического статуса.",
                    "ПСИХСТАТУС_ORDER_03 конец психического статуса.",
                ],
            ),
            "somatic_status": (
                "Соматический статус",
                [
                    "СОМАТИКА_ORDER_01 начало соматического статуса.",
                    "Диагноз терапевта уточнялся ранее; это часть соматического статуса.",
                    "СОМАТИКА_ORDER_03 конец соматического статуса.",
                ],
            ),
        }

        for _field_name, (heading, lines) in blocks.items():
            doc.add_paragraph(f"{heading}:")
            for line in lines:
                doc.add_paragraph(line)

        doc.add_paragraph("План обследования:")
        doc.add_paragraph("ОАК, ОАМ, ЭКГ, ФЛГ.")
        doc.add_paragraph("План лечения:")
        doc.add_paragraph("Терапия по назначению врача.")
        doc.add_paragraph("Диагноз:")
        doc.add_paragraph("F41.2 Тестовый диагноз")
        doc.save(source)

        parsed = MedicalTextParser().parse_docx(source)
        parsed_fields = {
            "complaints": parsed.complaints,
            "life_anamnesis": parsed.life_anamnesis,
            "disease_anamnesis": parsed.disease_anamnesis,
            "mental_status": parsed.mental_status,
            "somatic_status": parsed.somatic_status,
        }

        all_lines = {
            field_name: list(lines)
            for field_name, (_heading, lines) in blocks.items()
        }
        for field_name, value in parsed_fields.items():
            expected = all_lines[field_name]
            cursor = -1
            for line in expected:
                assert value.count(line) == 1, (
                    f"{field_name}: expected exactly one copy of {line!r}; got {value.count(line)}"
                )
                position = value.find(line)
                assert position > cursor, (
                    f"{field_name}: source order changed around {line!r}"
                )
                cursor = position

            foreign = [
                line
                for other_name, other_lines in all_lines.items()
                if other_name != field_name
                for line in other_lines
            ]
            for line in foreign:
                assert line not in value, (
                    f"{field_name}: absorbed foreign clinical text {line!r}"
                )

        navigation, service, data = _make_fixture(root)
        data.complaints = parsed.complaints
        data.life_anamnesis = parsed.life_anamnesis
        data.disease_anamnesis = parsed.disease_anamnesis
        data.mental_status = parsed.mental_status
        data.somatic_status = parsed.somatic_status

        output = root / "cross-field-order-output"
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
            for field_name, expected in all_lines.items():
                positions = []
                for line in expected:
                    assert text.count(line) == 1, (
                        f"{path.name}: {field_name} line duplicated/lost: {line!r}; "
                        f"count={text.count(line)}"
                    )
                    positions.append(text.find(line))
                assert all(position >= 0 for position in positions), (
                    f"{path.name}: {field_name} lost one or more ordered lines"
                )
                assert positions == sorted(positions), (
                    f"{path.name}: {field_name} line order changed: {positions}"
                )


def _assert_template_cleanup_never_deletes_inserted_patient_marker_lines() -> None:
    doc = Document()
    doc.add_paragraph("Анамнез заболевания")
    doc.add_paragraph("старый текст шаблона")
    doc.add_paragraph("ЭПИ - шаблонный пример, удалить")
    doc.add_paragraph("ЭКГ - шаблонный пример, удалить")
    doc.add_paragraph("ЭЭГ")
    doc.add_paragraph("Психический статус")
    doc.add_paragraph("старый статус")

    editor = DocxBlockEditor(doc)
    source_lines = (
        "Начало заболевания постепенное.\n"
        "ЭПИ - ранее проводилось по месту жительства; это часть анамнеза.\n"
        "ЭКГ - ранее описывалась без особенностей; это часть анамнеза.\n"
        "ЭЭГ\n"
        "Рекомендовано: ранее врачом амбулаторно; это исторический факт."
    )
    assert editor.replace_block(
        ["Анамнез заболевания"],
        "Анамнез заболевания:",
        source_lines,
        PRIMARY_MARKERS,
    )

    editor.remove_all_matching_paragraphs(["ЭПИ", "ЭКГ", "Рекомендовано"])
    editor.remove_exact_template_paragraphs(["ЭЭГ", "ЭПИ"])
    editor.replace_all_matching_paragraphs(["Диагноз"], "Диагноз: НЕ ДОЛЖНО ПОЯВИТЬСЯ")

    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ЭПИ - шаблонный пример" not in text, text
    assert "ЭКГ - шаблонный пример" not in text, text
    assert "ЭПИ - ранее проводилось по месту жительства" in text, text
    assert "ЭКГ - ранее описывалась без особенностей" in text, text
    assert "\nЭЭГ\n" in "\n" + text + "\n", text
    assert "Рекомендовано: ранее врачом амбулаторно" in text, text



def _assert_regex_replacement_never_targets_inserted_patient_text() -> None:
    doc = Document()
    doc.add_paragraph("Шаблонный заголовок")
    editor = DocxBlockEditor(doc)
    patient = doc.add_paragraph("2026")
    assert editor.template_paragraph_text(patient) is None
    assert editor.replace_first_matching_regex(r"^\d{4}$", "ПЕРЕПИСАНО") is False
    assert patient.text == "2026", patient.text



def _assert_sourced_investigation_block_survives_input_docx_parse() -> None:
    """Real sourced studies stay together and stop cleanly at the next section."""
    with TemporaryDirectory(prefix="medical-autofill-investigation-source-") as temp_dir:
        root = Path(temp_dir)
        source = root / "investigation-source.docx"
        doc = Document()
        doc.add_paragraph("12.06.2026 Первичный осмотр")
        doc.add_paragraph("История болезни № ИССЛ-001")
        doc.add_paragraph("Ф.И.О.: Маркер Исследований Тестовый")
        doc.add_paragraph("Год рождения: 01.01.1980")
        doc.add_paragraph("Результаты обследований:")
        expected = [
            "ОАК (13.06.2026): Hb 128 г/л; лейкоциты 6,1.",
            "ЭКГ (13.06.2026): синусовый ритм, ЧСС 72.",
            "ЭЭГ: без эпилептиформной активности.",
            "КОНЕЦ_ИССЛЕДОВАНИЙ_НЕ_ОБРЕЗАТЬ.",
        ]
        for line in expected:
            p = doc.add_paragraph()
            mid = max(1, len(line) // 2)
            p.add_run(line[:mid]).bold = True
            p.add_run(line[mid:]).italic = True
        doc.add_paragraph("Диагноз:")
        doc.add_paragraph("F99.9 Тестовый диагноз после исследований")
        doc.add_paragraph("План лечения:")
        doc.add_paragraph("Тестовая терапия после исследований")
        doc.save(source)

        parsed = MedicalTextParser().parse_docx(source)
        assert parsed.investigation_results, parsed
        positions = []
        for line in expected:
            assert parsed.investigation_results.count(line) == 1, (
                line,
                parsed.investigation_results,
            )
            positions.append(parsed.investigation_results.find(line))
        assert positions == sorted(positions), positions
        assert "F99.9 Тестовый диагноз после исследований" not in parsed.investigation_results
        assert "Тестовая терапия после исследований" not in parsed.investigation_results
        assert parsed.diagnosis == "F99.9 Тестовый диагноз после исследований", parsed.diagnosis
        assert parsed.treatment_plan == "Тестовая терапия после исследований", parsed.treatment_plan



def _assert_bundled_template_structure_is_editor_reachable() -> None:
    """Structural patient-field markers must not hide inside unsupported tables."""
    marker_map = {
        "primary": PRIMARY_MARKERS,
        "discharge": DISCHARGE_MARKERS,
        "commission": COMMISSION_MARKERS,
        "admission_doctor_referral": PRIMARY_MARKERS,
        "vk_mse": VK_MSE_MARKERS,
        "sick_leave_vk": SICK_LEAVE_VK_MARKERS,
        "rvk": RVK_MARKERS,
    }
    hidden = []
    for kind, markers in marker_map.items():
        doc = Document(str(bundled_template_path(kind)))
        for table_index, table in enumerate(doc.tables):
            for row_index, row in enumerate(table.rows):
                for cell_index, cell in enumerate(row.cells):
                    for paragraph in cell.paragraphs:
                        normalized = normalize_match(paragraph.text)
                        if not normalized:
                            continue
                        matched = [
                            marker
                            for marker in markers
                            if paragraph_matches_marker(normalized, marker)
                        ]
                        if matched:
                            hidden.append(
                                (kind, table_index, row_index, cell_index, paragraph.text, matched)
                            )
    assert not hidden, (
        "Bundled template contains structural markers in table cells that "
        "DocxBlockEditor cannot safely own/replace: "
        + repr(hidden)
    )


def verify() -> None:
    _assert_alias_coverage()
    _assert_inserted_marker_like_patient_text_never_becomes_structure()
    _assert_alias_boundary_stops_destructive_span_deletion()
    _assert_long_source_block_is_not_cut_by_narrative_marker_words()
    _assert_dated_historical_diagnoses_stay_inside_disease_anamnesis()
    _assert_dated_historical_clinical_sublabels_stay_inside_disease_anamnesis()
    _assert_historical_chronology_variant_matrix()
    _assert_historical_diagnosis_phrase_never_becomes_current_fallback()
    _assert_real_referral_to_discharge_roundtrip_keeps_full_dated_history()
    _assert_narrative_marker_words_never_replace_target_fields()
    _assert_long_multiline_docx_roundtrip_preserves_full_tail()
    _assert_table_and_run_fragmented_source_roundtrip()
    _assert_1250_line_clinical_block_survives_full_roundtrip()
    _assert_all_major_clinical_blocks_survive_long_roundtrip()
    _assert_all_medical_forms_keep_long_clinical_tails()
    _assert_template_cleanup_never_deletes_inserted_patient_marker_lines()
    _assert_sourced_investigation_block_survives_input_docx_parse()
    _assert_bundled_template_structure_is_editor_reachable()
    _assert_regex_replacement_never_targets_inserted_patient_text()
    print("DOCX BLOCK BOUNDARY REGRESSION OK: structural aliases + cross-field order/isolation + 1250-line stress + complaints/life/somatic + table/run-fragmented long-text integrity across all medical forms")


if __name__ == "__main__":
    verify()
