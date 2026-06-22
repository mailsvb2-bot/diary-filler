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

manual_data = service.parse_navigation(nav)
manual_data.discharge_date = "11.06.2026"
manual_data.diagnosis = "F99.9 Тестовый диагноз из UI"
manual_data.rvk_act_number = "77-А"
manual_data.rvk_military_commissariat = "Ленинского"
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
