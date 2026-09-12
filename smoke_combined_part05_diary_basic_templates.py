# --- Diary filler smoke ---
source = OUT / "texts.docx"
doc = Document()
doc.add_paragraph("01.06.2026 Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял.")
doc.add_paragraph("02.06.2026 Пациент сообщил об улучшении сна, фон настроения ровный, поведение упорядоченное.")
doc.save(source)
assert len(extract_statuses_from_docx(source)) == 2

merged_status = OUT / "merged_status.docx"
merged_doc = Document()
merged_table = merged_doc.add_table(rows=1, cols=2)
merged_cell = merged_table.cell(0, 0).merge(merged_table.cell(0, 1))
merged_cell.text = "Пациент был спокоен, жалоб активно не предъявлял, в беседе доступен, инструкции выполнял."
merged_doc.save(merged_status)
assert len(extract_statuses_from_docx(merged_status)) == 1
assert extract_docx_text(merged_status).count("Пациент был спокоен") == 1

table_file = OUT / "diary_table.docx"
doc = Document()
table = doc.add_table(rows=1, cols=4)
headers = ["№", "Число", "Месяц/год", "Дневник наблюдения"]
for i, h in enumerate(headers):
    table.rows[0].cells[i].text = h
for day in [10, 11, 12, 13, 14, 15]:
    row = table.add_row()
    row.cells[0].text = str(day)
    row.cells[1].text = str(day)
    row.cells[2].text = ""
    row.cells[3].text = "Лечащий врач Балаганин С.В."
doc.save(table_file)

result = fill_diary_batch(
    status_files=[source],
    diary_files=[table_file],
    output_dir=OUT / "diaries",
    patient_name="Иванова И.И.",
    admission_value="10.06.2026",
    discharge_value="12.06.2026",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=True,
    remove_holiday_rows=True,
)
assert result.processed_files == 1
assert result.created_files[0].exists()
assert result.report_path is None
assert not any(path.name.startswith("ОТЧЁТ_") for path in (OUT / "diaries").glob("*.txt"))
assert result.filled_rows >= 1
assert result.final_rows_filled == 1
assert result.removed_after_discharge_rows >= 3
diary_text = "\n".join("\t".join(cell.text for cell in row.cells) for row in Document(result.created_files[0]).tables[0].rows)
assert "Пациентка была спокойна" in diary_text
assert "не предъявляла" in diary_text

# Compact diary print layout: exact margins, 8 pt text, about three compact lines after each signature block.
table_diary_doc = Document(result.created_files[0])
for section in table_diary_doc.sections:
    assert abs(section.left_margin.cm - 1.5) < 0.03, section.left_margin.cm
    assert abs(section.right_margin.cm - 1.0) < 0.03, section.right_margin.cm
    assert abs(section.top_margin.cm - 1.0) < 0.03, section.top_margin.cm
    assert abs(section.bottom_margin.cm - 1.0) < 0.03, section.bottom_margin.cm
for table in table_diary_doc.tables:
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    if run.text.strip():
                        assert run.font.size is not None and abs(run.font.size.pt - 8.0) < 0.05, (run.text, run.font.size)
            signature_paragraphs = [p for p in cell.paragraphs if "лечащий врач" in p.text.lower() or "зав.отделением" in p.text.lower()]
            if signature_paragraphs:
                last_signature = signature_paragraphs[-1]
                assert last_signature.paragraph_format.space_after is not None
                assert 0 <= last_signature.paragraph_format.space_after.pt <= 24.1, last_signature.paragraph_format.space_after.pt

# Blank paragraphs between doctor/head signatures must not receive the inter-diary gap.
from diary_table_cells import _format_paragraphs
separated_signature_doc = Document()
first_signature = separated_signature_doc.add_paragraph("Лечащий врач Балаганин С.В.")
separated_signature_doc.add_paragraph("")
last_signature = separated_signature_doc.add_paragraph("Зав.отделением Можарова Е.А.")
_format_paragraphs(separated_signature_doc.paragraphs)
assert first_signature.paragraph_format.space_after is not None
assert abs(first_signature.paragraph_format.space_after.pt) < 0.05, first_signature.paragraph_format.space_after.pt
assert last_signature.paragraph_format.space_after is not None
assert abs(last_signature.paragraph_format.space_after.pt - 24.0) < 0.1, last_signature.paragraph_format.space_after.pt

# Legacy templates may already contain many empty paragraphs. The formatter must
# cap the physical + synthetic gap at three compact lines instead of preserving
# a large hole after signatures.
excess_blank_doc = Document()
excess_signature = excess_blank_doc.add_paragraph("Лечащий врач Балаганин С.В.")
for _ in range(5):
    excess_blank_doc.add_paragraph("")
excess_blank_doc.add_paragraph("12.06.26 следующий дневник")
_format_paragraphs(excess_blank_doc.paragraphs)
paragraphs_after_trim = excess_blank_doc.paragraphs
excess_index = next(i for i, p in enumerate(paragraphs_after_trim) if "Лечащий врач" in p.text)
physical_blanks = 0
for p in paragraphs_after_trim[excess_index + 1:]:
    if p.text.strip():
        break
    physical_blanks += 1
assert physical_blanks == 3, physical_blanks
assert abs(excess_signature.paragraph_format.space_after.pt) < 0.05, excess_signature.paragraph_format.space_after.pt

# --- Diary gender source smoke: UI filename may be male, source document is female ---
result_filename_male = fill_diary_batch(
    status_files=[source],
    diary_files=[table_file],
    output_dir=OUT / "diaries_gender_source",
    patient_name="Иванов Иван Иванович",
    gender_source_name="Иванова Ирина Ивановна",
    admission_value="10.06.2026",
    discharge_value="12.06.2026",
    repeat_statuses=True,
    reset_each_file=True,
    keep_signature=True,
    fill_months=True,
    force_final_diary=True,
    remove_holiday_rows=True,
)
diary_text2 = "\n".join("\t".join(cell.text for cell in row.cells) for row in Document(result_filename_male.created_files[0]).tables[0].rows)
assert "Пациентка была спокойна" in diary_text2
assert "не предъявляла" in diary_text2
assert result_filename_male.created_files[0].name.startswith("Иванов Иван Иванович")

# --- Production text diaries: clinical entries come from diagnosis template; discharge is universal ---
from diary_service import DiaryService
contract_texts = OUT / "F20 Параноидная шизофрения.docx"
contract_doc = Document()
contract_doc.add_paragraph("TEMPLATE_STATUS_ONE пациент пришел спокойно.")
contract_doc.add_paragraph("TEMPLATE_STATUS_TWO пациент оставался спокоен.")
contract_doc.add_paragraph("TEMPLATE_STATUS_THREE пациент сохранял спокойствие.")
contract_doc.save(contract_texts)
contract_dates = OUT / "contract_dates.docx"
contract_dates_doc = Document()
contract_dates_table = contract_dates_doc.add_table(rows=1, cols=4)
for i, h in enumerate(("День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения")):
    contract_dates_table.rows[0].cells[i].text = h
for hospital_day in (1, 2, 3, 7):
    row = contract_dates_table.add_row()
    row.cells[0].text = str(hospital_day)
    row.cells[3].text = "Лечащий врач Балаганин С.В.\nЗав.отделением Можарова Е.А."
contract_dates_doc.save(contract_dates)
contract_result = DiaryService().create_text_diaries(
    status_files=[contract_texts],
    diary_files=[contract_dates],
    output_dir=OUT / "diagnosis_template_contract",
    patient_name="Иванова Анна Сергеевна",
    gender_source_name="Иванова Анна Сергеевна",
    admission_value="10.06.2026",
    discharge_value="13.06.2026",
)
contract_output = Document(contract_result.created_files[0])
contract_lines = [p.text for p in contract_output.paragraphs if p.text.strip()]
contract_joined = "\n".join(contract_lines)
assert "TEMPLATE_STATUS_ONE пациентка пришла спокойно." in contract_joined, contract_joined
assert "TEMPLATE_STATUS_TWO пациентка оставалась спокойна." in contract_joined, contract_joined
# The discharge diary is the third generated observation here, so the universal
# final text remains diagnosis-independent but is rendered as a joint exam.
assert "13.06.26 Совместный осмотр с зав. отделением" in contract_joined, contract_joined
joint_index = contract_lines.index("13.06.26 Совместный осмотр с зав. отделением")
assert contract_lines[joint_index + 1].startswith("Состояние улучшилось."), contract_lines
assert contract_lines[joint_index + 2] == "Лечащий врач Балаганин С.В.", contract_lines
assert contract_lines[joint_index + 3] == "Зав.отделением Можарова Е.А.", contract_lines
assert contract_joined.count("Лечащий врач Балаганин С.В.") == 3, contract_joined
assert contract_joined.count("Зав.отделением Можарова Е.А.") == 1, contract_joined
assert "TEMPLATE_STATUS_THREE" not in contract_joined, contract_joined
assert contract_result.final_rows_filled == 1
for section in contract_output.sections:
    assert abs(section.left_margin.cm - 1.5) < 0.03
    assert abs(section.right_margin.cm - 1.0) < 0.03
    assert abs(section.top_margin.cm - 1.0) < 0.03
    assert abs(section.bottom_margin.cm - 1.0) < 0.03
for paragraph in contract_output.paragraphs:
    for run in paragraph.runs:
        if run.text.strip():
            assert run.font.size is not None and abs(run.font.size.pt - 8.0) < 0.05, (run.text, run.font.size)
text_signature_blocks = [p for p in contract_output.paragraphs if "Лечащий врач" in p.text or "Зав.отделением" in p.text]
assert text_signature_blocks, contract_lines
for index, paragraph in enumerate(contract_output.paragraphs):
    if "Лечащий врач" not in paragraph.text and "Зав.отделением" not in paragraph.text:
        continue
    next_is_signature = index + 1 < len(contract_output.paragraphs) and ("Лечащий врач" in contract_output.paragraphs[index + 1].text or "Зав.отделением" in contract_output.paragraphs[index + 1].text)
    if not next_is_signature:
        assert paragraph.paragraph_format.space_after is not None
        assert 0 <= paragraph.paragraph_format.space_after.pt <= 24.1, paragraph.paragraph_format.space_after.pt


# --- Admission date regression: title date is admission, FIO-near date is birth ---
title_date_doc = OUT / "title_date_primary.docx"
title_doc = Document()
title_doc.add_paragraph("12.01.2026 Первичный осмотр")
title_doc.add_paragraph("Ф.И.О.: Сидоров Иван Михайлович, Дата рождения: 09.01.1980")
title_doc.add_paragraph("Жалобы: тест")
title_doc.add_paragraph("Психический статус: тест")
title_doc.add_paragraph("Диагноз: F41.2 тест")
title_doc.save(title_date_doc)
title_data = MedicalDocumentService().parse_primary_document(title_date_doc)
assert title_data.admission_date == "12.01.2026", title_data.admission_date
assert title_data.birth == "09.01.1980", title_data.birth

# --- Numbered diary template auto-selection smoke without touching diary_filler.py ---
from main import CombinedMedicalDiaryApp, DIR_NUMBERED_DIARY_TEMPLATES

class _Var:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value

# --- One-generation PatientData snapshot must override live UI drift for diaries ---
snapshot_dates = OUT / "snapshot_dates.docx"
snapshot_dates_doc = Document()
snapshot_table = snapshot_dates_doc.add_table(rows=1, cols=4)
for i, h in enumerate(["День госпитализации", "Число", "Месяц/Год", "Дневник наблюдения"]):
    snapshot_table.rows[0].cells[i].text = h
for hospital_day in [2, 3, 4, 7]:
    row = snapshot_table.add_row()
    row.cells[0].text = str(hospital_day)
    row.cells[3].text = "Лечащий врач Балаганин С.В.\nЗав.отделением Можарова Е.А."
snapshot_dates_doc.save(snapshot_dates)

snapshot_app = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
snapshot_app.navigation_path_var = _Var("")
snapshot_app.patient_name_var = _Var("Чужое ФИО из живого UI")
snapshot_app.admission_date_var = _Var("31.12.2099")
snapshot_app.discharge_date_var = _Var("31.12.2099")
snapshot_app.status_files = [str(source)]
snapshot_app.diary_files = [str(snapshot_dates)]
snapshot_app._diary_files_auto_selected = False
snapshot_app.repeat_statuses_var = _Var(True)
snapshot_app.force_final_diary_var = _Var(True)
snapshot_app._diagnostic_reports_enabled = lambda: False
snapshot_app._log = lambda _text: None
snapshot_patient = PatientData(
    fio="Иванова Ирина Ивановна",
    output_fio="Снимок Пациента",
    admission_date="10.06.2026",
    discharge_date="17.06.2026",
)
snapshot_result = snapshot_app._create_diaries_impl(
    output_dir_override=OUT / "snapshot_diary_output",
    log_created=False,
    patient_data_snapshot=snapshot_patient,
)
assert snapshot_result.created_files[0].name.startswith("Снимок Пациента"), snapshot_result.created_files[0]
snapshot_doc = Document(snapshot_result.created_files[0])
snapshot_text = "\n".join(paragraph.text for paragraph in snapshot_doc.paragraphs)
for expected_date in ("11.06.26", "12.06.26", "13.06.26", "17.06.26"):
    assert expected_date in snapshot_text, (expected_date, snapshot_text)
assert "31.12.99" not in snapshot_text, snapshot_text
assert "Чужое ФИО из живого UI" not in snapshot_result.created_files[0].name

numbered_dir = OUT / "шаблоны дневников"
numbered_dir.mkdir(parents=True, exist_ok=True)
Document().save(numbered_dir / "12.docx")
app = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
app.admission_date_var = _Var("12.01.2026")
app.navigation_path_var = _Var("")
app.output_dir_var = _Var("")
app.status_files = []
app.diary_files = []
app.diary_template_dir = ""
app._settings = {"folders": {DIR_NUMBERED_DIARY_TEMPLATES: str(numbered_dir)}}
app._settings_folders = lambda: app._settings.setdefault("folders", {})
app._save_settings = lambda: None
app._log = lambda _text: None
app._short_file_list = lambda paths: "\n".join(Path(path).name for path in paths)
app.service = None
assert app._auto_select_numbered_diary_template(ask_folder=False) is True
assert Path(app.diary_files[0]).name == "12.docx"

# Snapshot admission override must beat a conflicting live admission date.
Document().save(numbered_dir / "31.docx")
app.diary_files = []
app._diary_files_auto_selected = False
app.diary_template_dir = str(numbered_dir)
app.admission_date_var.set("31.01.2026")
assert app._auto_select_numbered_diary_template(
    ask_folder=False,
    admission_value_override="12.01.2026",
) is True
assert Path(app.diary_files[0]).name == "12.docx"
# An explicitly empty snapshot admission must not fall back to the conflicting live UI.
app.diary_files = []
app._diary_files_auto_selected = False
assert app._auto_select_numbered_diary_template(
    ask_folder=False,
    admission_value_override="",
) is False
assert app.diary_files == []

# --- Auto-search must use a nearby folder named exactly "шаблоны дневников" ---
auto_near_dir = OUT / "auto_named_folder"
auto_near_dir.mkdir(parents=True, exist_ok=True)
auto_primary = auto_near_dir / "patient_referral.docx"
auto_primary_doc = Document()
auto_primary_doc.add_paragraph("15.04.2026 Направление на госпитализацию")
auto_primary_doc.add_paragraph("Сидоров Иван Михайлович, 04.01.2000")
auto_primary_doc.save(auto_primary)
auto_templates = auto_near_dir / "шаблоны дневников"
auto_templates.mkdir(parents=True, exist_ok=True)
Document().save(auto_templates / "15.docx")
app2 = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
app2.admission_date_var = _Var("")
app2.navigation_path_var = _Var(str(auto_primary))
app2.output_dir_var = _Var("")
app2.status_files = []
app2.diary_files = []
app2.diary_template_dir = ""
app2._manual_admission_date = False
app2._suspend_user_edit_tracking = False
app2._settings = {"folders": {}}
app2._settings_folders = lambda: app2._settings.setdefault("folders", {})
app2._save_settings = lambda: None
app2._log = lambda _text: None
app2._short_file_list = lambda paths: "\n".join(Path(path).name for path in paths)
app2._set_ui_var = lambda var, value: var.set(value)
app2.service = None
assert app2._auto_select_numbered_diary_template(ask_folder=False) is True
assert Path(app2.diary_files[0]).name == "15.docx"
assert app2.admission_date_var.get() == "15.04.2026"

# --- Loading a new primary document must refresh the exact diary-date template in UI ---
class _Label:
    def __init__(self):
        self.kwargs = {}
    def config(self, **kwargs):
        self.kwargs.update(kwargs)

refresh_dir = OUT / "refresh_diary_template" / "шаблоны дневников"
refresh_dir.mkdir(parents=True, exist_ok=True)
Document().save(refresh_dir / "15.docx")
Document().save(refresh_dir / "16.docx")
app4 = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
app4.assigned_treatment_var = _Var("old")
app4.admission_occurrence_var = _Var("old")
app4.case_number_var = _Var("old")
app4.expert_work_status_var = _Var("да")
app4.expert_work_org_var = _Var("ООО")
app4.expert_position_var = _Var("врач")
app4.expert_sick_leave_needed_var = _Var("да")
app4.disability_needed_var = _Var("нет")
app4.expert_sick_leave_from_var = _Var("15.04.2026")
app4.expert_sick_leave_number_var = _Var("1")
app4.vk_mse_work_org_var = _Var("ООО")
app4.vk_mse_position_var = _Var("врач")
app4.sick_leave_vk_work_org_var = _Var("ООО")
app4.sick_leave_vk_position_var = _Var("врач")
app4.sick_leave_vk_work_position_var = _Var("ООО, врач")
app4.patient_name_var = _Var("Пациент старый")
app4.admission_date_var = _Var("15.04.2026")
app4.discharge_date_var = _Var("")
app4.diagnosis_var = _Var("F41.2 тест")
app4.navigation_path_var = _Var("")
app4.output_dir_var = _Var("")
app4.status_files = []
app4.diary_files = [str(refresh_dir / "15.docx")]
app4.diary_template_dir = str(refresh_dir)
app4._diary_files_auto_selected = False
app4._diary_text_files_auto_selected = False
app4._diary_template_files_cache = {}
app4._diary_template_day_cache = {}
app4._diary_template_folder_contains_cache = {}
app4._suspend_user_edit_tracking = False
app4._settings = {"folders": {DIR_NUMBERED_DIARY_TEMPLATES: str(refresh_dir)}}
app4._settings_folders = lambda: app4._settings.setdefault("folders", {})
app4._save_settings = lambda: None
app4._update_expert_sick_leave_display = lambda: None
app4._set_ui_var = lambda var, value: var.set(value)
app4._update_diary_text_label = lambda success=None: None
app4.diary_files_label = _Label()
app4.primary_selected_status_var = _Var(" ")
app4.data = PatientData()
app4._reset_primary_document_runtime_state()
assert app4.diary_files == []
assert app4._diary_files_auto_selected is True
app4.admission_date_var.set("16.04.2026")
assert app4._auto_select_numbered_diary_template(ask_folder=False) is True
assert Path(app4.diary_files[0]).name == "16.docx"
assert "16.docx" in app4.diary_files_label.kwargs.get("text", "")

# --- UI contract: «Даты» is one direct folder-selection action, not a two-dialog flow ---
choose_src_start = main_source.index("    def choose_diary_files")
choose_src_end = main_source.index("    def _short_file_list", choose_src_start)
choose_src = main_source[choose_src_start:choose_src_end]
assert "filedialog.askdirectory" in choose_src
assert "filedialog.askopenfilename" not in choose_src
assert "filedialog.askopenfilenames" not in choose_src
assert "Выберите папку «Даты» с шаблонами 01–31" in choose_src

status_start = main_source.index("    def choose_status_files")
status_end = main_source.index("    def _diary_template_label_text", status_start)
status_src = main_source[status_start:status_end]
assert "filedialog.askdirectory" in status_src
assert "filedialog.askopenfilename" not in status_src
assert "filedialog.askopenfilenames" not in status_src
assert "Выберите папку «Тексты» с DOCX по диагнозам" in status_src

# --- Diary text auto-selection by diagnosis filename ---
from diary_text_selection import (
    normalize_diary_diagnosis_name,
    diary_diagnosis_match_score,
    find_diary_text_file_for_diagnosis,
)

texts_by_diagnosis = OUT / "тексты по диагнозам"
texts_by_diagnosis.mkdir(parents=True, exist_ok=True)
Document().save(texts_by_diagnosis / "Смешанное тревожное и депрессивное расстройство.docx")
Document().save(texts_by_diagnosis / "Органическое эмоционально лабильное расстройство.docx")
assert normalize_diary_diagnosis_name("F 41.2 Смешанное тревожное и депрессивное расстройство.") == "смешанное тревожное и депрессивное расстройство"
assert diary_diagnosis_match_score(
    "F 41.2 Смешанное тревожное и депрессивное расстройство.",
    "Смешанное тревожное и депрессивное расстройство.docx",
) >= 90
matched_text = find_diary_text_file_for_diagnosis(
    texts_by_diagnosis,
    "F 41.2 Смешанное тревожное и депрессивное расстройство.",
)
assert matched_text is not None
assert matched_text.name == "Смешанное тревожное и депрессивное расстройство.docx"

app3 = CombinedMedicalDiaryApp.__new__(CombinedMedicalDiaryApp)
app3.diagnosis_var = _Var("F 41.2 Смешанное тревожное и депрессивное расстройство.")
app3.navigation_path_var = _Var("")
app3.output_dir_var = _Var("")
app3.status_files = []
app3.diary_texts_dir = str(texts_by_diagnosis)
app3._diary_text_files_auto_selected = False
app3._settings = {"folders": {}}
app3._settings_folders = lambda: app3._settings.setdefault("folders", {})
app3._save_settings = lambda: None
app3._get_saved_directory = lambda _key: ""
app3._update_diary_text_label = lambda success=None: None
app3._redraw_selection_controls = lambda: None
app3._log = lambda _text: None
app3.data = None
assert app3._auto_select_diary_text_by_diagnosis(ask_folder=False) is True
assert Path(app3.status_files[0]).name == "Смешанное тревожное и депрессивное расстройство.docx"
assert app3._diary_text_files_auto_selected is True

# Snapshot override must beat a conflicting live diagnosis during generation.
app3.status_files = []
app3._diary_text_files_auto_selected = False
app3.diagnosis_var.set("F06.6 Органическое эмоционально лабильное расстройство")
assert app3._auto_select_diary_text_by_diagnosis(
    ask_folder=False,
    diagnosis_override="F41.2 Смешанное тревожное и депрессивное расстройство",
) is True
assert Path(app3.status_files[0]).name == "Смешанное тревожное и депрессивное расстройство.docx"
# An explicitly empty snapshot diagnosis must not fall back to the conflicting live UI.
app3.status_files = []
app3._diary_text_files_auto_selected = False
assert app3._auto_select_diary_text_by_diagnosis(
    ask_folder=False,
    diagnosis_override="",
) is False
assert app3.status_files == []


# --- Real diary-text filenames from physician folders ---
real_names = {
    "дневники ВЭ олигофрены.docx": "F70.0 Легкая умственная отсталость",
    "дневники ВЭ олигофрены с астенией.docx": "F70.0 Легкая умственная отсталость с астеническим синдромом",
    "дневники ВЭ олигофрены с психопатизацией.docx": "F70 Умственная отсталость с психопатизацией",
    "дневники ВЭ легкая депрессия с датами.docx": "F32.0 Легкий депрессивный эпизод",
    "дневники ВЭ легкая органика.docx": "F06.6 Органическое эмоционально лабильное расстройство",
    "дневники ВЭ здоровые2.docx": "Психически здоров",
}
real_text_dir = OUT / "реальные имена текстов"
real_text_dir.mkdir(parents=True, exist_ok=True)
for filename in real_names:
    Document().save(real_text_dir / filename)
for expected_name, diagnosis in real_names.items():
    matched = find_diary_text_file_for_diagnosis(real_text_dir, diagnosis)
    assert matched is not None, diagnosis
    assert matched.name == expected_name, (diagnosis, matched.name)
assert normalize_diary_diagnosis_name("дневники ВЭ легкая депрессия с датами.docx") == "легкая депрессия"
assert normalize_diary_diagnosis_name("F70.0 Легкая умственная отсталость") == "легкая умственная отсталость"

# A merely related diagnosis must never be auto-selected when the requested
# diagnosis/name relation is absent. The doctor should be asked for the correct
# template instead of silently getting another clinical condition.
wrong_only_dir = OUT / "только похожие диагнозы"
wrong_only_dir.mkdir(parents=True, exist_ok=True)
for filename in (
    "Тяжелая депрессия.docx",
    "Смешанное тревожное и депрессивное расстройство.docx",
    "Органическая депрессия.docx",
):
    Document().save(wrong_only_dir / filename)
assert find_diary_text_file_for_diagnosis(
    wrong_only_dir, "F32.0 Легкий депрессивный эпизод"
) is None
assert find_diary_text_file_for_diagnosis(
    wrong_only_dir, "F06.6 Органическое эмоционально лабильное расстройство"
) is None

# Direct filename relation beats any semantic fallback.
direct_dir = OUT / "прямое совпадение диагноза"
direct_dir.mkdir(parents=True, exist_ok=True)
for filename in ("Шизофрения.docx", "Шизофрения с астенией.docx", "Органическое расстройство.docx"):
    Document().save(direct_dir / filename)
direct_match = find_diary_text_file_for_diagnosis(direct_dir, "F20 Шизофрения")
assert direct_match is not None and direct_match.name == "Шизофрения.docx", direct_match

# --- UI defaults and service-line regression ---
source_all = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(ROOT.glob("*.py"))
    if not path.name.startswith(("smoke_test", "smoke_combined_"))
)
assert 'kind: tk.BooleanVar(value=False) for kind in DOCUMENT_ORDER' in source_all
assert 'self.output_vars[DIARY_KIND] = tk.BooleanVar(value=False)' in source_all
assert 'Служебный отчёт создания документов не сохранён' not in source_all
assert 'Служебный отчёт дневников не сохранён' not in source_all
assert 'font=self._font(12, "bold" if checked else None)' in source_all
assert 'Автоматически выбран текст дневников по диагнозу' in source_all
