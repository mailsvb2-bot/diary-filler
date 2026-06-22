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
app4.case_number_var = _Var("old")
app4.expert_work_status_var = _Var("да")
app4.expert_work_org_var = _Var("ООО")
app4.expert_position_var = _Var("врач")
app4.expert_sick_leave_needed_var = _Var("да")
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

# --- UI contract: "Шаблоны дневников" lets user see DOCX files and also supports folder fallback ---
choose_src_start = main_source.index("    def choose_diary_files")
choose_src_end = main_source.index("    def _short_file_list", choose_src_start)
choose_src = main_source[choose_src_start:choose_src_end]
assert "filedialog.askopenfilename" in choose_src
assert "filedialog.askdirectory" in choose_src
assert "filedialog.askopenfilenames" not in choose_src
assert "Path(selected).parent" in choose_src



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
