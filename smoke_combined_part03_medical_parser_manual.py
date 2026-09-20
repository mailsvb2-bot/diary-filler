compact_data = service.parser.parse_text("""
10.06.2026 Первичный осмотр
Ф.И.О.: Петрова Анна Сергеевна, Возраст: 45 лет, Место жительства: Н. Новгород, Ленинский район
Жалобы: тревога
Анамнез жизни: тест
Анамнез заболевания: тест
Психический статус: тест
План лечения: тест
Диагноз: F41.2 тест
""")
assert compact_data.fio == "Петрова Анна Сергеевна", compact_data.fio
assert compact_data.birth == "45 лет", compact_data.birth
assert compact_data.registered == "Н. Новгород, Ленинский район", compact_data.registered

compact_data2 = service.parser.parse_text("""
10.06.2026 Направление на госпитализацию
ФИО: Сидоров Сергей Петрович, 1980 г.р., проживает: Нижний Новгород, ул. Тестовая, д. 1
Жалобы: тревога
Анамнез жизни: тест
Анамнез заболевания: тест
Психический статус: тест
План лечения: тест
Диагноз: F41.2 тест
""")
assert compact_data2.fio == "Сидоров Сергей Петрович", compact_data2.fio
assert compact_data2.birth == "1980 г.р", compact_data2.birth
assert compact_data2.registered == "Нижний Новгород, ул. Тестовая, д. 1", compact_data2.registered

# --- DOCX table regression: FIO label and value can live in adjacent cells ---
split_fio_doc = OUT / "ФИО_раздельные_ячейки.docx"
split_doc = Document()
split_doc.add_paragraph("28.05.2026 Первичный осмотр")
split_table = split_doc.add_table(rows=2, cols=2)
split_table.cell(0, 0).text = "Ф.И.О."
split_table.cell(0, 1).text = "Тестов М.А."
split_table.cell(1, 0).text = "Год рождения"
split_table.cell(1, 1).text = "1980"
split_doc.add_paragraph("Жалобы: тревога")
split_doc.add_paragraph("Психический статус: контактен")
split_doc.add_paragraph("Диагноз: F41.2 Тестовый диагноз")
split_doc.save(split_fio_doc)
split_fio_data = service.parse_primary_document(split_fio_doc)
assert split_fio_data.fio == "Тестов М.А.", split_fio_data.fio
assert "Ф.И.О." not in split_fio_data.fio, split_fio_data.fio

# A generated «Осмотр врача приёмного покоя» is also a valid patient source.
# Its first-line date is the hospitalization date and must win over the birth
# date on the next line when that generated document is loaded again.
admission_doctor_source = OUT / "Осмотр_врача_приёмного_покоя_повторный_ввод.docx"
admission_doctor_doc = Document()
admission_doctor_doc.add_paragraph("30.09.2025 10:00 Осмотр врача приёмного покоя.")
admission_doctor_doc.add_paragraph(
    "Тестова Анна Сергеевна, 24.07.1997, по адресу: Н. Новгород, ул. Тестовая, д. 1."
)
admission_doctor_doc.add_paragraph("Работает в организации: ООО Тест")
admission_doctor_doc.add_paragraph("Должность: инженер")
admission_doctor_doc.add_paragraph("В 3 отделение КДП поступает повторно")
admission_doctor_doc.add_paragraph("Психический статус: контакту доступна")
admission_doctor_doc.add_paragraph("Диагноз: F20.0 Тестовый диагноз")
admission_doctor_doc.save(admission_doctor_source)
admission_doctor_data = service.parse_primary_document(admission_doctor_source)
assert admission_doctor_data.admission_date == "30.09.2025", admission_doctor_data.admission_date
assert admission_doctor_data.birth == "24.07.1997", admission_doctor_data.birth
assert admission_doctor_data.input_document_kind == "осмотр врача приёмного покоя", admission_doctor_data.input_document_kind
assert service.parser.parse_text(
    "30.09.2025 10:00 Осмотр врача приёмного покоя.\n"
    "Тестова Анна Сергеевна, 24.07.1997, по адресу: Н. Новгород, ул. Тестовая, д. 1."
).admission_date == "30.09.2025"

# Universal source regression: a discharge epicrisis is a first-class source.
# Admission/discharge dates must come from the current treatment period, while
# the header date remains the discharge date and never replaces admission.
universal_discharge = service.parser.parse_text("""
11.06.2026      Выписной эпикриз № К-900
Петров Пётр Петрович, 04.01.1980, зарегистрирован по адресу: Нижний Новгород, ул. Тестовая, 1
Находился на лечении в ГБУЗ НО «НКЦПЗ» диспансер №2 с 10.06.2026 по 11.06.2026
В 3 отделение КДП поступает повторно добровольно
Жалобы при поступлении: тревога
Анамнез жизни: тест
Анамнез заболевания: тест
Психический статус при поступлении: контактен
Диагноз: F41.2 тест
Лечение: терапия
""")
assert universal_discharge.input_document_kind == "выписной эпикриз", universal_discharge.input_document_kind
assert universal_discharge.admission_date == "10.06.2026", universal_discharge.admission_date
assert universal_discharge.discharge_date == "11.06.2026", universal_discharge.discharge_date
assert universal_discharge.case_number == "К-900", universal_discharge.case_number
assert universal_discharge.treatment_plan == "терапия", universal_discharge.treatment_plan

# Strong type signatures must win over clinical words embedded in the body.
assert service.parser._detect_document_kind("20.06.2026 Совместный осмотр с зам глав врача № 7\nПервичный осмотр упомянут в анамнезе") == "совместный осмотр"
assert service.parser._detect_document_kind("О СОСТОЯНИИ ЗДОРОВЬЯ ГРАЖДАНИНА № 5\nГоспитализируется по направлению военного комиссариата Ленинского района") == "акт для РВК"
assert service.parser._detect_document_kind("Ф.И.О.: Тестов Т.Т.\nДиагноз: F20.0 тест", "Тестов ВК на МСЭ.docx") == "ВК на МСЭ"

# Repeated UI requests for the same admission-title date must not reopen the
# unchanged Word file. Editing/replacing the file must invalidate that cache.
import os as _title_cache_os
import medical_docx_title_finder as _title_finder
_title_finder._TITLE_DATE_CACHE.clear()
assert _title_finder.extract_admission_date_from_title_docx(split_fio_doc) == "28.05.2026"
_original_title_reader = _title_finder._extract_admission_date_from_title_docx_uncached
_title_reader_calls = [0]
def _counting_title_reader(path):
    _title_reader_calls[0] += 1
    return _original_title_reader(path)
_title_finder._extract_admission_date_from_title_docx_uncached = _counting_title_reader
try:
    assert _title_finder.extract_admission_date_from_title_docx(split_fio_doc) == "28.05.2026"
    assert _title_reader_calls == [0], _title_reader_calls
    _title_stat = split_fio_doc.stat()
    _title_cache_os.utime(
        split_fio_doc,
        ns=(_title_stat.st_atime_ns, _title_stat.st_mtime_ns + 1_000_000_000),
    )
    assert _title_finder.extract_admission_date_from_title_docx(split_fio_doc) == "28.05.2026"
    assert _title_reader_calls == [1], _title_reader_calls
finally:
    _title_finder._extract_admission_date_from_title_docx_uncached = _original_title_reader
    _title_finder._TITLE_DATE_CACHE.clear()

# Real-world label variants from primary DOCX forms must remain explicit;
# never infer FIO from the filename.
for fio_label in ("Ф.И.О. пациента", "ФИО пациента", "Ф.И.О. больного", "Фамилия, имя, отчество"):
    parsed_fio_variant = service.parser.parse_text(f"{fio_label}: Васин М.В.\nДиагноз: F21 Шизотипическое расстройство")
    assert parsed_fio_variant.fio == "Васин М.В.", (fio_label, parsed_fio_variant.fio)

# Word can concatenate the next narrative sentence directly to diagnosis.
assert sanitize_diagnosis(
    "F21 Шизотипическое расстройствоНаходится на лечении в круглосуточном стационаре ПБ №2 "
    "с 23.01.2026 по 10.03.2026Госпитализируется в стационар"
) == "F21 Шизотипическое расстройство"

referral_kind = service.parser.parse_text("""
10.06.2026 Первичный осмотр
Целесообразна госпитализация пациентки в 3 отделение КДП
Ф.И.О.: Иванова Ирина Ивановна
Год рождения: 1980
Жалобы: тест
Психический статус: тест
Диагноз: F41.2 тест
""").input_document_kind
assert referral_kind == "направление на госпитализацию", referral_kind

# --- Primary exam parser: life anamnesis can be a questionnaire column block or a free narrative line ---
primary_style_column = service.parser.parse_text("""
Первичный осмотр
История болезни №: 777
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
Анамнез жизни:
наследственность -  не отягощена
Рождение в городе – нижний новгород
на момент рождения семья была- полной
В настоящее время семья- не полная
Братья/сёстры- есть
Беременность/роды проходили- без особенностей
ДДУ- посещал
Общение в ДДУ было- нормальное
В общеобразовательную школу –  в 7 лет
В коррекционной школе-  не учился
Во время учёбы в школе оценки- 4-5
В школе проучился-  11 классов
После школы-  ПИМУ
Специальность-  врач
Окончание учёбы- 2023
В настоящее время работа- врач
Брак-  женат
Дети- сын 2024 года рождения
Проживает- в семье
Анамнез заболевания: болен месяц
Психический статус: спокоен
Лечение: терапия Диагноз: F41.2 тест
Диагноз: F41.2 тест
""")
assert primary_style_column.case_number == "777", primary_style_column.case_number
assert primary_style_column.life_anamnesis.startswith("наследственность"), primary_style_column.life_anamnesis
assert "Специальность- врач" in primary_style_column.life_anamnesis, primary_style_column.life_anamnesis
assert primary_style_column.disease_anamnesis == "болен месяц", primary_style_column.disease_anamnesis
assert primary_style_column.treatment_plan == "терапия", primary_style_column.treatment_plan
assert primary_style_column.diagnosis == "F41.2 тест", primary_style_column.diagnosis

primary_style_line = service.parser.parse_text("""
Первичный осмотр
ФИО: Иванов Иван Иванович
возраст: 34 года
наследственность -  не отягощена Родился в нижнем новгороде в полной семье. Родители развелись когда пациенту было 4 года. Братьев сестёр нет. Беременность и роды проходили без особенностей. ДДУ посещал.
Анамнез заболевания: ухудшение состояния
Психический статус: контактен
Лечение: препараты по схеме. Диагноз: F20.0 Параноидная шизофрения Жалобы: нет
""")
assert "Родился в нижнем новгороде" in primary_style_line.life_anamnesis, primary_style_line.life_anamnesis
assert primary_style_line.treatment_plan == "препараты по схеме.", primary_style_line.treatment_plan
assert primary_style_line.diagnosis == "F20.0 Параноидная шизофрения", primary_style_line.diagnosis

# --- Russian day plural regression for VK sick leave text ---
assert "(1 день)" in treatment_period_text("01.01.2026", "01.01.2026")
assert "(3 дня)" in treatment_period_text("01.01.2026", "03.01.2026")
assert "(5 дней)" in treatment_period_text("01.01.2026", "05.01.2026")

assert parse_date("03.04.26").strftime("%d.%m.%Y") == "03.04.2026"
assert parse_date("3.4.26").strftime("%d.%m.%Y") == "03.04.2026"
assert format_military_commissariat_area("Автозаводский") == "Автозаводского района"
assert format_military_commissariat_area("Ленинский") == "Ленинского района"
assert format_military_commissariat_area("Ленинского района") == "Ленинского района"
assert format_military_commissariat_area("Сормовский и Московский") == "Сормовского и Московского района"
assert format_military_commissariat_area("военного комиссариата Нижегородской области") == "Нижегородской области"
assert format_military_commissariat_area("Нижегородской области") == "Нижегородской области"
assert format_military_commissariat_referral("военного комиссариата Нижегородской области") == "По направлению из военного комиссариата Нижегородской области"

from medical_models import parse_sick_leave_value
assert parse_sick_leave_value("не нужен") == ("нет", "")
assert parse_sick_leave_value("нужен с 12.06.2026") == ("да", "12.06.2026")
assert parse_sick_leave_value("НУЖЕН С 120626") == ("да", "120626")
from medical_models import clean_admission_detail
assert clean_admission_detail("нецелесообразна госпитализация в стационар") == "нецелесообразна госпитализация в стационар"
assert clean_admission_detail("добровольно нецелесообразна госпитализация в стационар") == "добровольно нецелесообразна госпитализация в стационар"
assert parse_sick_leave_value("неизвестно") == ("", "")

manual_data = service.parse_navigation(nav)
manual_data.discharge_date = "11.06.2026"
manual_data.diagnosis = "F99.9 Тестовый диагноз из UI"
manual_data.admission_occurrence = "повторно"
manual_data.rvk_act_number = "77-А"
manual_data.rvk_military_commissariat = "Ленинского"
manual_data.rvk_referral_present = "да"
manual_data.rvk_referral_commissariat = "Ленинского"
manual_data.rvk_work_position = "ООО РВК, программист"
manual_data.commission_date = "18.06.2026"
manual_data.commission_number = "9"
manual_data.vk_date = "16.06.2026"
manual_data.vk_protocol_number = "42"
manual_data.vk_protocol_date = "16.06.2026"
manual_data.vk_mse_work_org = "ГБУЗ НО Тест"
manual_data.vk_mse_position = "санитар"
manual_data.sick_leave_vk_date = "18.06.2026"
manual_data.sick_leave_vk_protocol_number = "55"
manual_data.sick_leave_vk_protocol_date = "18.06.2026"
manual_data.sick_leave_vk_commission_date = "18.06.2026"
manual_data.sick_leave_vk_work_org = "ООО Тест"
manual_data.sick_leave_vk_position = "инженер"
manual_data.sick_leave_vk_work_position = ""
manual_data.expert_work_status = "да"
manual_data.expert_work_org = "ООО Завод"
manual_data.expert_position = "инженер"
manual_data.expert_sick_leave_needed = "да"
manual_data.expert_sick_leave_from = "15.06.2026"
manual_data.disability_needed = "нет"
manual_data.disability = "не нужно"
manual_data.work_org = manual_data.expert_work_org
manual_data.position = manual_data.expert_position
manual_data.sick_leave = "нужен с 15.06.2026"
assert build_expert_anamnesis(manual_data) == "Работает в ООО Завод, в должности инженер. Больничный лист. Срок лечения с 10.06.2026 по 11.06.2026, 2 дня. К труду с 12.06.2026."
assert build_expert_anamnesis(manual_data, include_sick_leave_number=False) == "Работает в ООО Завод, в должности инженер. Больничный лист нужен с 15.06.2026."
assert build_expert_anamnesis(manual_data, include_sick_leave=False) == "Работает в ООО Завод, в должности инженер."
manual_data.expert_sick_leave_number = "123456789"
assert build_expert_anamnesis(manual_data) == "Работает в ООО Завод, в должности инженер. Больничный лист № 123456789. Срок лечения с 10.06.2026 по 11.06.2026, 2 дня. К труду с 12.06.2026."
manual_data.expert_sick_leave_number = ""

# --- Treatment section detection contract ---
without_treatment_marker = service.parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
Жалобы: тест
Психический статус: тест
За время лечения состояние без динамики.
Диагноз: F41.2 тест
""")
assert without_treatment_marker.has_treatment_section is False, without_treatment_marker.has_treatment_section
assert without_treatment_marker.treatment_plan == "", without_treatment_marker.treatment_plan

with_treatment_marker = service.parser.parse_text("""
Первичный осмотр
Ф.И.О.: Иванов Иван Иванович
Год рождения: 1990
Жалобы: тест
Психический статус: тест
Назначенное лечение: терапия по схеме.
Диагноз: F41.2 тест
""")
assert with_treatment_marker.has_treatment_section is True, with_treatment_marker.has_treatment_section
assert with_treatment_marker.treatment_plan == "терапия по схеме.", with_treatment_marker.treatment_plan
