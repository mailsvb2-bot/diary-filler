# --- Diary columns regression: no birth year, month/year from admission title date ---
column_dir = OUT / "diary_column_regression"
column_dir.mkdir(parents=True, exist_ok=True)
column_texts = column_dir / "texts.docx"
column_text_doc = Document()
column_text_doc.add_paragraph("01.01.2026 Пациент был спокоен, жалоб не предъявлял, в беседе доступен, инструкции выполнял.")
column_text_doc.save(column_texts)
column_template = column_dir / "13.docx"
column_template_doc = Document()
column_table = column_template_doc.add_table(rows=1, cols=4)
for i, h in enumerate(["День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения"]):
    column_table.rows[0].cells[i].text = h
for day in [13, 14, 15, 1]:
    row = column_table.add_row()
    row.cells[0].text = ""
    row.cells[1].text = f"{day:02d}"
    row.cells[2].text = ""
    row.cells[3].text = "Лечащий врач Балаганин С.В."
column_template_doc.save(column_template)
column_result = fill_diary_batch(
    status_files=[column_texts],
    diary_files=[column_template],
    output_dir=column_dir / "out",
    patient_name="Сидоров Иван Михайлович",
    gender_source_name="Сидоров Иван Михайлович",
    admission_value="12.01.2026",
    discharge_value="",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=True,
    remove_holiday_rows=True,
)
column_out_doc = Document(column_result.created_files[0])
column_values = [(row.cells[1].text.strip(), row.cells[2].text.strip()) for row in column_out_doc.tables[0].rows[1:]]
assert column_values[:4] == [("13", "01.2026"), ("14", "01.2026"), ("15", "01.2026"), ("01", "02.2026")]
assert "2000" not in "\n".join("\t".join(cell.text for cell in row.cells) for row in column_out_doc.tables[0].rows)


# --- Diary date columns regression: use admission date from title, never birth date ---
real_column_dir = OUT / "diary_real_date_columns"
real_column_dir.mkdir(parents=True, exist_ok=True)
real_texts = real_column_dir / "texts.docx"
real_text_doc = Document()
real_text_doc.add_paragraph("Состояние стабильное. Жалоб активно не предъявляет. Поведение упорядочено. Сон и аппетит достаточные.")
real_text_doc.save(real_texts)
real_template = real_column_dir / "15.docx"
real_template_doc = Document()
real_table = real_template_doc.add_table(rows=1, cols=4)
for i, h in enumerate(["День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения"]):
    real_table.rows[0].cells[i].text = h
for hospital_day, old_day, old_month in [(2, "05", "01.2000"), (3, "06", "01.2000"), (4, "07", "01.2000"), (7, "09", "01.2000"), (11, "14", "01.2000")]:
    row = real_table.add_row()
    row.cells[0].text = str(hospital_day)
    row.cells[1].text = old_day
    row.cells[2].text = old_month
    row.cells[3].text = "Лечащий врач Балаганин С.В."
real_template_doc.save(real_template)
real_result = fill_diary_batch(
    status_files=[real_texts],
    diary_files=[real_template],
    output_dir=real_column_dir / "out",
    patient_name="Сидоров Иван Михайлович",
    gender_source_name="Сидоров Иван Михайлович",
    admission_value="15.04.2026",
    discharge_value="",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=False,
    remove_holiday_rows=False,
)
real_out_doc = Document(real_result.created_files[0])
real_values = [(row.cells[0].text.strip(), row.cells[1].text.strip(), row.cells[2].text.strip()) for row in real_out_doc.tables[0].rows[1:]]
assert real_values[:5] == [("2", "16", "04.2026"), ("3", "17", "04.2026"), ("4", "18", "04.2026"), ("7", "21", "04.2026"), ("11", "25", "04.2026")]
assert "01.2000" not in "\n".join("\t".join(cell.text for cell in row.cells) for row in real_out_doc.tables[0].rows)

assert any(item.code == "F41.2" for item in search_icd10_f("41"))
assert any(item.code == "F41.2" for item in search_icd10_f("трев деп"))

# --- Diary columns regression: rows with empty calendar-day column but filled hospitalization-day column are filled ---
blank_day_dir = OUT / "diary_blank_calendar_day_regression"
blank_day_dir.mkdir(parents=True, exist_ok=True)
blank_texts = blank_day_dir / "texts.docx"
blank_text_doc = Document()
blank_text_doc.add_paragraph("Пациент спокоен, жалоб не предъявляет, контакт доступен, сон и аппетит достаточные.")
blank_text_doc.save(blank_texts)
blank_template = blank_day_dir / "15.docx"
blank_template_doc = Document()
blank_table = blank_template_doc.add_table(rows=1, cols=4)
for i, h in enumerate(["День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения"]):
    blank_table.rows[0].cells[i].text = h
for hosp_day in [2, 3, 4, 7, 11]:
    row = blank_table.add_row()
    row.cells[0].text = str(hosp_day)
    row.cells[1].text = ""
    row.cells[2].text = ""
    row.cells[3].text = "Лечащий врач Балаганин С.В."
blank_template_doc.save(blank_template)
blank_result = fill_diary_batch(
    status_files=[blank_texts],
    diary_files=[blank_template],
    output_dir=blank_day_dir / "out",
    patient_name="Сидоров Иван Михайлович",
    gender_source_name="Сидоров Иван Михайлович",
    admission_value="15.04.2026",
    discharge_value="",
    repeat_statuses=True,
    reset_each_file=True,
    fill_months=True,
    force_final_diary=False,
    open_result_folder=False,
)
blank_doc = Document(blank_result.created_files[0])
blank_values = [(row.cells[1].text.strip(), row.cells[2].text.strip()) for row in blank_doc.tables[0].rows[1:]]
assert blank_values[:5] == [("16", "04.2026"), ("17", "04.2026"), ("18", "04.2026"), ("21", "04.2026"), ("25", "04.2026")], blank_values[:5]


# --- Numbered diary template lookup regression: extensionless filenames 1/01 are accepted ---
extless_dir = OUT / "extensionless_numbered_templates"
extless_dir.mkdir(parents=True, exist_ok=True)
extless_template = extless_dir / "02"
extless_doc = Document()
extless_table = extless_doc.add_table(rows=1, cols=4)
for i, h in enumerate(["День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения"]):
    extless_table.rows[0].cells[i].text = h
extless_row = extless_table.add_row()
extless_row.cells[0].text = "2"
extless_row.cells[1].text = ""
extless_row.cells[2].text = ""
extless_row.cells[3].text = "Лечащий врач Балаганин С.В."
extless_doc.save(extless_template)
lookup_app = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
found_extless = lookup_app._find_numbered_diary_template(extless_dir, 2)
assert found_extless is not None and found_extless.name == "02", found_extless
assert _main_module.CombinedMedicalDiaryApp._template_filename_day(extless_template) == 2



# --- Production settings regression: corrupted settings are quarantined, patient data is never persisted ---
settings_app = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
settings_app._settings_path = OUT / "settings.json"
settings_app._settings_path.write_text("{broken", encoding="utf-8")
loaded_settings = settings_app._load_settings()
assert loaded_settings == {}, loaded_settings
assert list(OUT.glob("settings.broken.*.json")), "broken settings copy was not created"
settings_app._settings = {
    "folders": {"primary_documents_dir": str(OUT), "empty": ""},
    "printer": "Test Printer",
    "patient_name": "Иванов Иван Иванович",
    "diagnosis": "F41.2 Тестовый диагноз",
    "discharge_date": "11.06.2026",
}
settings_app._save_settings()
saved_settings_text = settings_app._settings_path.read_text(encoding="utf-8")
assert "Test Printer" in saved_settings_text
assert "primary_documents_dir" in saved_settings_text
assert "Иванов" not in saved_settings_text
assert "F41.2" not in saved_settings_text
assert "11.06.2026" not in saved_settings_text
assert not settings_app._settings_path.with_name(settings_app._settings_path.name + ".tmp").exists()


# --- Service hardening regression: unknown/duplicate document kinds, bad dates and cp1251 TXT EPI ---
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "invalid_kind",
        selected_docs=["primary", "unknown_kind"],
    )
    raise AssertionError("unknown document kind must fail with ValueError")
except ValueError as exc:
    assert "unknown_kind" in str(exc)

try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "bad_discharge_date",
        selected_docs=["discharge"],
        discharge_date="99.99.2026",
    )
    raise AssertionError("bad discharge date must fail before rendering")
except ValueError as exc:
    assert "Дата выписки" in str(exc)


try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_discharge_required",
        selected_docs=["discharge"],
    )
    raise AssertionError("discharge document must require discharge date at service boundary")
except ValueError as exc:
    assert "Дата выписки" in str(exc), str(exc)

try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_commission_fields",
        selected_docs=["commission"],
    )
    raise AssertionError("commission document must require commission date/number at service boundary")
except ValueError as exc:
    assert "Дата совместного" in str(exc) or "номер совместного" in str(exc), str(exc)

try:
    bad_vk_data = service.parse_primary_document(nav)
    bad_vk_data.vk_date = "99.99.2026"
    bad_vk_data.vk_protocol_number = "12"
    bad_vk_data.vk_protocol_date = "99.99.2026"
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "bad_vk_dates",
        selected_docs=["vk_mse"],
        override_data=bad_vk_data,
    )
    raise AssertionError("VK MSE document must reject invalid popup dates at service boundary")
except ValueError as exc:
    assert "Дата ВК" in str(exc), str(exc)

try:
    bad_sick_vk_data = service.parse_primary_document(nav)
    bad_sick_vk_data.sick_leave_vk_date = "18.06.2026"
    bad_sick_vk_data.sick_leave_vk_protocol_number = ""
    bad_sick_vk_data.sick_leave_vk_protocol_date = "18.06.2026"
    bad_sick_vk_data.sick_leave_vk_commission_date = "18.06.2026"
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "bad_sick_vk_protocol",
        selected_docs=["sick_leave_vk"],
        override_data=bad_sick_vk_data,
    )
    raise AssertionError("sick-leave VK document must require protocol number at service boundary")
except ValueError as exc:
    assert "номер протокола ВК больничного" in str(exc), str(exc)

try:
    bad_rvk_data = service.parse_primary_document(nav)
    bad_rvk_data.discharge_date = "11.06.2026"
    bad_rvk_data.rvk_act_number = "77-А"
    bad_rvk_data.rvk_military_commissariat = ""
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "bad_rvk_military",
        selected_docs=["rvk"],
        override_data=bad_rvk_data,
    )
    raise AssertionError("RVK document must require military commissariat at service boundary")
except ValueError as exc:
    assert "военкомат" in str(exc), str(exc)

compact_popup_data = service.parse_primary_document(nav)
compact_popup_data.discharge_date = "11062026"
compact_popup_data.commission_date = "18062026"
compact_popup_data.commission_number = "12"
compact_popup_data.vk_date = "19062026"
compact_popup_data.vk_protocol_number = "13"
compact_popup_data.vk_protocol_date = "19062026"
compact_popup_data.sick_leave_vk_date = "20062026"
compact_popup_data.sick_leave_vk_protocol_number = "14"
compact_popup_data.sick_leave_vk_protocol_date = "20062026"
compact_popup_data.sick_leave_vk_commission_date = "20062026"
compact_popup_data.rvk_act_number = "15"
compact_popup_data.rvk_military_commissariat = "Ленинский"
compact_created, compact_used = service.create_documents(
    navigation_path=nav,
    output_dir=OUT / "compact_required_dates",
    selected_docs=["discharge", "commission", "vk_mse", "sick_leave_vk", "rvk"],
    override_data=compact_popup_data,
)
assert compact_used.discharge_date == "11.06.2026"
assert compact_used.commission_date == "18.06.2026"
assert compact_used.vk_date == "19.06.2026"
assert compact_used.sick_leave_vk_commission_date == "20.06.2026"
compact_text = "\n".join(extract_docx_text(path) for path in compact_created)
assert "18062026" not in compact_text and "19062026" not in compact_text and "20062026" not in compact_text
assert "18.06.2026" in compact_text and "19.06.2026" in compact_text and "20.06.2026" in compact_text

dupe_out = OUT / "duplicate_selected_docs"
dupe_data = service.parse_primary_document(nav)
dupe_data.commission_date = "18062026"
dupe_data.commission_number = "12"
dupe_created, _dupe_data = service.create_documents(
    navigation_path=nav,
    output_dir=dupe_out,
    selected_docs=["primary", "primary", "commission"],
    override_data=dupe_data,
)
assert [path.name for path in dupe_created] == [
    "Иванова Ирина Ивановна Первичный осмотр.docx",
    "Иванова Ирина Ивановна Совместный осмотр.docx",
]

cp1251_epi = OUT / "epi_cp1251.txt"
cp1251_epi.write_bytes("ЭПИ: Пациент контактен".encode("cp1251"))
assert service.load_epi_text(cp1251_epi) == "Пациент контактен"

# --- Drag-and-drop fallback regression: multiple braced Windows paths without Tcl splitlist ---
class _BrokenTk:
    def splitlist(self, _data):
        raise RuntimeError("Tcl splitlist unavailable")

class _BrokenRoot:
    tk = _BrokenTk()

dnd_app = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
dnd_app.root = _BrokenRoot()
parsed_drop = dnd_app._parse_drop_event_data(r"{C:\Temp\один файл.docx} {D:\Work\второй файл.docx}")
assert parsed_drop == [r"C:\Temp\один файл.docx", r"D:\Work\второй файл.docx"], parsed_drop

# --- Settings regression: syntactically valid JSON with wrong top-level type is quarantined ---
wrong_type_app = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
wrong_type_app._settings_path = OUT / "settings_wrong_type.json"
wrong_type_app._settings_path.write_text("[]", encoding="utf-8")
assert wrong_type_app._load_settings() == {}
assert list(OUT.glob("settings.broken.*.json")), "wrong-type settings copy was not created"


# --- Additional hardening regression: service rejects wrong file types and unsafe dates ---
non_docx_primary = OUT / "primary_wrong_type.txt"
non_docx_primary.write_text("Первичный осмотр", encoding="utf-8")
try:
    service.parse_primary_document(non_docx_primary)
    raise AssertionError("primary parser must reject non-DOCX files before python-docx")
except ValueError as exc:
    assert "первичный документ" in str(exc) and ".docx" in str(exc), str(exc)

bad_epi = OUT / "epi_wrong_type.rtf"
bad_epi.write_text("ЭПИ: текст", encoding="utf-8")
try:
    service.load_epi_text(bad_epi)
    raise AssertionError("EPI loader must reject unsupported extensions")
except ValueError as exc:
    assert "ЭПИ" in str(exc) and ".txt" in str(exc), str(exc)

try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "bad_date_order",
        selected_docs=["discharge"],
        discharge_date="09.06.2026",
    )
    raise AssertionError("service must reject discharge date before admission date")
except ValueError as exc:
    assert "раньше" in str(exc), str(exc)

single_kind_created, _single_kind_data = service.create_documents(
    navigation_path=nav,
    output_dir=OUT / "single_kind_string",
    selected_docs="primary",
)
assert len(single_kind_created) == 1 and single_kind_created[0].name.endswith("Первичный осмотр.docx")

none_output_created, _none_output_data = service.create_documents(
    navigation_path=nav,
    output_dir=None,
    selected_docs="primary",
)
assert none_output_created[0].parent == nav.parent

override_data = service.parse_primary_document(nav)
override_data.discharge_date = ""
_mutation_created, used_override = service.create_documents(
    navigation_path=nav,
    output_dir=OUT / "override_copy",
    selected_docs="discharge",
    discharge_date="11.06.2026",
    override_data=override_data,
)
assert used_override.discharge_date == "11.06.2026"
assert override_data.discharge_date == "", "create_documents must not mutate caller-owned override_data"

assert parse_date("01.01.1899") is None
assert parse_date("01.01.2201") is None
assert parse_date("01.01.1900") is not None
assert parse_date("31.12.2200") is not None


# --- Deep audit v1.3.17: service boundary must reject incomplete/illogical medical documents ---
missing_case_data = service.parse_primary_document(nav)
missing_case_data.case_number = ""
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_case_number_service_boundary",
        selected_docs=["primary"],
        override_data=missing_case_data,
    )
    raise AssertionError("medical service must require case number for every medical document")
except ValueError as exc:
    assert "номер истории болезни" in str(exc), str(exc)

missing_treatment_data = service.parse_primary_document(nav)
missing_treatment_data.treatment_plan = ""
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_treatment_service_boundary",
        selected_docs=["primary"],
        override_data=missing_treatment_data,
    )
    raise AssertionError("medical service must require treatment for treatment-bearing documents")
except ValueError as exc:
    assert "лечение" in str(exc), str(exc)

missing_diagnosis_data = service.parse_primary_document(nav)
missing_diagnosis_data.diagnosis = ""
missing_diagnosis_data.discharge_date = "11.06.2026"
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_diagnosis_service_boundary",
        selected_docs=["discharge"],
        override_data=missing_diagnosis_data,
    )
    raise AssertionError("medical service must require diagnosis before rendering medical DOCX")
except ValueError as exc:
    assert "диагноз" in str(exc), str(exc)

missing_fio_data = service.parse_primary_document(nav)
missing_fio_data.fio = ""
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_fio_service_boundary",
        selected_docs=["primary"],
        override_data=missing_fio_data,
    )
    raise AssertionError("medical service must require patient FIO")
except ValueError as exc:
    assert "Ф.И.О" in str(exc), str(exc)

missing_admission_data = service.parse_primary_document(nav)
missing_admission_data.admission_date = ""
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_admission_date_service_boundary",
        selected_docs=["primary"],
        override_data=missing_admission_data,
    )
    raise AssertionError("medical service must require admission date")
except ValueError as exc:
    assert "дата госпитализации" in str(exc), str(exc)

bad_rvk_act_number_data = service.parse_primary_document(nav)
bad_rvk_act_number_data.discharge_date = "11.06.2026"
bad_rvk_act_number_data.rvk_act_number = ""
bad_rvk_act_number_data.rvk_military_commissariat = "Ленинский"
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "missing_rvk_act_number_service_boundary",
        selected_docs=["rvk"],
        override_data=bad_rvk_act_number_data,
    )
    raise AssertionError("RVK act must require its own medical conclusion number, not silently reuse case number")
except ValueError as exc:
    assert "номер медицинского заключения" in str(exc), str(exc)

bad_commission_order_data = service.parse_primary_document(nav)
bad_commission_order_data.commission_date = "09.06.2026"
bad_commission_order_data.commission_number = "77"
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "commission_before_admission_service_boundary",
        selected_docs=["commission"],
        override_data=bad_commission_order_data,
    )
    raise AssertionError("commission date before admission must be rejected")
except ValueError as exc:
    assert "раньше" in str(exc), str(exc)

bad_vk_order_data = service.parse_primary_document(nav)
bad_vk_order_data.vk_date = "09.06.2026"
bad_vk_order_data.vk_protocol_number = "78"
bad_vk_order_data.vk_protocol_date = "10.06.2026"
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "vk_before_admission_service_boundary",
        selected_docs=["vk_mse"],
        override_data=bad_vk_order_data,
    )
    raise AssertionError("VK MSE date before admission must be rejected")
except ValueError as exc:
    assert "раньше" in str(exc), str(exc)

bad_sick_vk_order_data = service.parse_primary_document(nav)
bad_sick_vk_order_data.sick_leave_vk_date = "10.06.2026"
bad_sick_vk_order_data.sick_leave_vk_protocol_number = "79"
bad_sick_vk_order_data.sick_leave_vk_protocol_date = "10.06.2026"
bad_sick_vk_order_data.sick_leave_vk_commission_date = "09.06.2026"
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=OUT / "sick_vk_before_admission_service_boundary",
        selected_docs=["sick_leave_vk"],
        override_data=bad_sick_vk_order_data,
    )
    raise AssertionError("sick-leave VK commission date before admission must be rejected")
except ValueError as exc:
    assert "раньше" in str(exc), str(exc)

assert format_military_commissariat_area("военного комиссариата Ленинского района") == "Ленинского района"
assert format_military_commissariat_area("Ленинского военкомата") == "Ленинского района"
assert format_military_commissariat_referral("по направлению из Ленинского военкомата") == "По направлению из Ленинского военкомата"
assert format_military_commissariat_referral("военного комиссариата Сормовского и Московского района") == "По направлению из Сормовского и Московского военкомата"

# --- Drag-and-drop TXT classifier must recognize Windows-1251 EPI files ---
dnd_cp1251_epi = OUT / "drag_epi_cp1251.txt"
dnd_cp1251_epi.write_bytes("ЭПИ: Пациент контактен".encode("cp1251"))
dnd_classifier = _main_module.CombinedMedicalDiaryApp.__new__(_main_module.CombinedMedicalDiaryApp)
assert dnd_classifier._classify_dropped_file(str(dnd_cp1251_epi)) == "epi"

# --- Diary batch hardening: clear validation, dedupe and safe output fallback ---
from diary_filler import read_statuses_from_files

dupe_status_a = OUT / "dupe_status_a.docx"
dupe_status_b = OUT / "dupe_status_b.docx"
for dupe_path in [dupe_status_a, dupe_status_b]:
    dupe_doc = Document()
    dupe_doc.add_paragraph("Пациент спокоен, жалоб не предъявляет, контакт доступен, сон достаточный.")
    dupe_doc.save(dupe_path)
deduped_statuses = read_statuses_from_files([dupe_status_a, dupe_status_b])
assert len(deduped_statuses) == 1, deduped_statuses

bad_status_txt = OUT / "bad_status.txt"
bad_status_txt.write_text("Пациент спокоен", encoding="utf-8")
try:
    fill_diary_batch(
        status_files=[bad_status_txt],
        diary_files=[blank_template],
        output_dir=OUT / "bad_status_out",
        patient_name="Сидоров Иван Иванович",
        admission_value="15.04.2026",
        fill_months=True,
        force_final_diary=False,
    )
    raise AssertionError("diary status files must reject non-DOCX inputs")
except ValueError as exc:
    assert "тексты дневников" in str(exc) and ".docx" in str(exc), str(exc)

try:
    fill_diary_batch(
        status_files=[blank_texts],
        diary_files=[blank_template],
        output_dir=OUT / "bad_diary_date_order",
        patient_name="Сидоров Иван Иванович",
        admission_value="15.04.2026",
        discharge_value="14.04.2026",
        fill_months=True,
        force_final_diary=True,
    )
    raise AssertionError("diary batch must reject discharge date before admission date")
except ValueError as exc:
    assert "раньше" in str(exc), str(exc)

space_output_result = fill_diary_batch(
    status_files=[blank_texts],
    diary_files=[blank_template],
    output_dir="   ",
    patient_name="Сидоров Иван Иванович",
    admission_value="15.04.2026",
    discharge_value="",
    fill_months=True,
    force_final_diary=False,
    open_result_folder=False,
)
assert space_output_result.created_files[0].parent == blank_template.parent
assert all(path.parent == blank_template.parent for path in space_output_result.created_files)
# Windows/Win32 normalizes paths made only of trailing spaces in a platform-specific
# way, so checking Path("   ").exists() is not portable. The contract we need is
# stronger and user-visible: a blank/whitespace output_dir must fall back to the
# diary template folder and all generated files must be placed there.



# --- v1.3.18 production-quality gate: output dir/file hygiene, labels, archive and repo hygiene ---
file_output_target = OUT / "not_a_directory_output.txt"
file_output_target.write_text("I am a file, not an output directory", encoding="utf-8")
try:
    service.create_documents(
        navigation_path=nav,
        output_dir=file_output_target,
        selected_docs="Первичный осмотр",
    )
    raise AssertionError("medical service must reject output_dir pointing to a file")
except ValueError as exc:
    assert "Папка результата" in str(exc), str(exc)

label_selected_created, _label_selected_data = service.create_documents(
    navigation_path=nav,
    output_dir=OUT / "label_selected_docs",
    selected_docs=["Первичный осмотр"],
)
assert len(label_selected_created) == 1 and label_selected_created[0].name.endswith("Первичный осмотр.docx")

diary_file_output_target = OUT / "diary_not_a_directory_output.txt"
diary_file_output_target.write_text("I am a file, not an output directory", encoding="utf-8")
try:
    fill_diary_batch(
        status_files=[blank_texts],
        diary_files=[blank_template],
        output_dir=diary_file_output_target,
        patient_name="Сидоров Иван Иванович",
        admission_value="15.04.2026",
        fill_months=True,
        force_final_diary=False,
        open_result_folder=False,
    )
    raise AssertionError("diary batch must reject output_dir pointing to a file")
except ValueError as exc:
    assert "Папка результата" in str(exc), str(exc)

duplicate_diary_file_result = fill_diary_batch(
    status_files=[blank_texts],
    diary_files=[blank_template, blank_template],
    output_dir=OUT / "duplicate_diary_input",
    patient_name="Сидоров Иван Иванович",
    admission_value="15.04.2026",
    fill_months=True,
    force_final_diary=False,
    open_result_folder=False,
)
assert len(duplicate_diary_file_result.created_files) == 1, duplicate_diary_file_result.created_files

try:
    fill_diary_batch(
        status_files=["   "],
        diary_files=[blank_template],
        output_dir=OUT / "blank_status_path",
        patient_name="Сидоров Иван Иванович",
        admission_value="15.04.2026",
        fill_months=True,
        force_final_diary=False,
        open_result_folder=False,
    )
    raise AssertionError("diary batch must reject blank status file path")
except ValueError as exc:
    assert "Пустой путь" in str(exc), str(exc)

from diary_batch import open_folder
assert open_folder(OUT / "definitely_missing_folder") is False
assert (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()[0].startswith("# Keep repository")
assert "*.py text eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
assert "permissions:" in (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
assert "concurrency:" in (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")
assert "timeout-minutes:" in (ROOT / ".github/workflows/windows-build.yml").read_text(encoding="utf-8")

print("OK")
print("Medical docs with EPI:", len(created))
print("Medical docs without EPI:", len(created_no_epi))
print("Diary files:", len(result.created_files))
print("Output:", OUT)
