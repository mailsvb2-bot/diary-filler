from __future__ import annotations

import copy
from pathlib import Path
import tkinter as tk
from typing import Dict, List

from app_config import *
from medical_constants import DOCUMENT_ORDER
from medical_models import PatientData


class _LazyMedicalDocumentService:
    """Create the DOCX service only when a file operation really needs it.

    Startup should paint the UI quickly. Importing python-docx/renderers/templates
    is deferred until the first primary-document parse or document generation.
    """
    __slots__ = ("_service",)

    def __init__(self) -> None:
        self._service = None

    def _get(self):
        if self._service is None:
            from medical_service import MedicalDocumentService
            self._service = MedicalDocumentService()
        return self._service

    def __getattr__(self, name: str):
        return getattr(self._get(), name)


class AppInitializationMixin:
    def _initialize_app(self, root: tk.Tk) -> None:
        self._init_core_state(root)
        self._init_primary_and_expert_state()
        self._init_document_detail_state()
        self._init_medical_output_state()
        self._init_diary_state()
        self._init_runtime_visual_state()
        self._configure_root_window()
        self._bootstrap_ui()


    def _parse_primary_document(self, path: str | Path) -> PatientData:
        """Parse a primary DOCX with a small mtime/size cache for UI responsiveness.

        Selecting a file, updating the preview, opening dialogs and creating files
        can ask for the same primary document several times. Re-reading DOCX each
        time makes the interface feel sticky. The cache is invalidated by size or
        modification time and returns a deep copy so callers may safely mutate the
        PatientData for their own document flow.
        """
        p = Path(path)
        key = str(p.resolve()) if p.exists() else str(p)
        try:
            stat = p.stat()
            signature = (stat.st_mtime, stat.st_size)
        except Exception:
            signature = (0.0, -1)
        cached = self._primary_parse_cache.get(key)
        if cached and cached[0] == signature[0] and cached[1] == signature[1]:
            return copy.deepcopy(cached[2])
        data = self.service.parse_primary_document(p)
        self._primary_parse_cache[key] = (signature[0], signature[1], copy.deepcopy(data))
        # Keep cache tiny: the UI works with one current patient document.
        if len(self._primary_parse_cache) > 3:
            for old_key in list(self._primary_parse_cache)[:-3]:
                self._primary_parse_cache.pop(old_key, None)
        return data

    def _init_core_state(self, root: tk.Tk) -> None:
        self.root = root
        self.service = _LazyMedicalDocumentService()
        self._primary_parse_cache: dict[str, tuple[float, int, PatientData]] = {}
        self._diary_template_files_cache: dict[tuple[str, int], list[Path]] = {}
        self._diary_template_day_cache: dict[tuple[str, int, int], int | None] = {}
        self._diary_template_folder_contains_cache: dict[tuple[str, int], bool] = {}
        self.data = PatientData()

        # Общая карточка пациента. ФИО в UI используется для названия файлов.
        # ФИО внутри документов всегда берётся из выбранного первичного документа.
        # На старте интерфейс всегда открывается «с чистого листа».
        # Никакие данные пациента, даты, диагноз, папка результата или принтер
        # не подставляются из прошлых запусков: пользователь явно выбирает файлы
        # и вводит/подтверждает значения для текущего пациента.
        self.patient_name_var = tk.StringVar()
        self.admission_date_var = tk.StringVar()
        self.discharge_date_var = tk.StringVar()
        self.diagnosis_var = tk.StringVar()
        # Диагноз и дата выписки, выбранные/введённые врачом в popup
        # направления, имеют абсолютный приоритет над данными, распознанными
        # из первичного DOCX. Особенно важно не дать повторному reparse_navigation()
        # заменить дату выписки датой поступления.
        self._popup_diagnosis_override = ""
        self._popup_discharge_date_override = ""
        self.output_dir_var = tk.StringVar()
        # Папка результата по умолчанию должна следовать за первичным
        # документом пациента. Ручной выбор через кнопку/ручной ввод
        # сохраняется и не перетирается автоматикой.
        self._suspend_output_dir_tracking = False
        self._manual_output_dir = False
        self.output_dir_var.trace_add("write", lambda *_: self._mark_manual_output_dir())

        # Печать: выбор принтера и сценарий "создать + сохранить + распечатать".
        self.printer_var = tk.StringVar()
        self.available_printers: list[str] = []
        self._printer_refresh_in_progress = False
        self._settings_path = self._get_settings_path()
        self._settings = self._load_settings()

    def _init_primary_and_expert_state(self) -> None:
        # Тип входного первичного документа.
        # - направление на госпитализацию: номер истории болезни, лечение и
        #   диагноз подтверждаются вручную в popup;
        # - первичный осмотр: popup не открывается, данные берутся из DOCX.
        self.primary_document_type_var = tk.StringVar(value="primary_exam")
        self.primary_document_type_display_var = tk.StringVar(value="Первичный осмотр")
        self.assigned_treatment_var = tk.StringVar()
        self.case_number_var = tk.StringVar()

        # Экспертный анамнез / больничный лист.
        # Видимый старт всегда пустой: значения задаются врачом для текущего случая
        # через popup и затем идут в первичный осмотр, выписной эпикриз и комиссионный осмотр.
        self.expert_work_status_var = tk.StringVar()  # да/нет: работает ли пациент
        self.expert_work_org_var = tk.StringVar()
        self.expert_position_var = tk.StringVar()
        self.expert_sick_leave_needed_var = tk.StringVar(value="нет")  # да/нет
        self.expert_sick_leave_from_var = tk.StringVar()
        self.expert_sick_leave_number_var = tk.StringVar()
        self.expert_sick_leave_display_var = tk.StringVar(value="нет")
        self._primary_work_org_default = ""
        self._primary_work_position_default = ""
        self._work_details_manually_edited = False

        # Защита ручного ввода UI. Некоторые файлы умеют подтягивать ФИО/дату/диагноз
        # автоматически, но уже набранные врачом значения нельзя перетирать при выборе
        # направления, ЭПИ или таблиц дневников.
        self._suspend_user_edit_tracking = False
        self._manual_patient_name = False
        self._manual_admission_date = False
        self._manual_discharge_date = False
        self._manual_diagnosis = False
        self.patient_name_var.trace_add("write", lambda *_: self._mark_manual_field("patient_name"))
        self.admission_date_var.trace_add("write", lambda *_: self._mark_manual_field("admission_date"))
        self.discharge_date_var.trace_add("write", lambda *_: self._mark_manual_field("discharge_date"))
        self.diagnosis_var.trace_add("write", lambda *_: self._mark_manual_field("diagnosis"))

    def _init_document_detail_state(self) -> None:
        # Ручные реквизиты для отдельных документов. В UI они не занимают место:
        # появляются маленькие окна при включении соответствующих галочек.
        self.rvk_act_number_var = tk.StringVar()
        self.rvk_military_commissariat_var = tk.StringVar()
        self.rvk_work_position_var = tk.StringVar()
        self.vk_date_var = tk.StringVar()
        self.vk_protocol_number_var = tk.StringVar()
        self.vk_protocol_date_var = tk.StringVar()
        self.vk_mse_work_org_var = tk.StringVar()
        self.vk_mse_position_var = tk.StringVar()
        self.sick_leave_vk_date_var = tk.StringVar()
        self.sick_leave_vk_protocol_number_var = tk.StringVar()
        self.sick_leave_vk_protocol_date_var = tk.StringVar()
        self.sick_leave_vk_commission_date_var = tk.StringVar()
        self.sick_leave_vk_work_org_var = tk.StringVar()
        self.sick_leave_vk_position_var = tk.StringVar()
        # Старое объединённое поле оставлено как внутренний fallback/совместимость.
        self.sick_leave_vk_work_position_var = tk.StringVar()
        self.commission_date_var = tk.StringVar()
        self.commission_number_var = tk.StringVar()

        # Даты popup-окон ВК/комиссий не должны переноситься между разными
        # документами. Например, дата комиссионного осмотра и дата Акта/ВК
        # могут быть разными, поэтому каждое popup-окно хранит только своё
        # собственное значение. Эти поля оставлены пустыми как совместимость,
        # но больше не используются для межоконного автодублирования.
        self._last_committee_date = ""
        self._last_protocol_date = ""

    def _init_medical_output_state(self) -> None:
        # Медицинские документы.
        self.navigation_path_var = tk.StringVar()
        self.epi_path_var = tk.StringVar()
        self.strict_mode_var = tk.BooleanVar(value=True)

        # Общий список создаваемых сущностей: медицинские документы + дневники.
        # В продовом UI ничего не включаем по умолчанию: врач явно выбирает
        # нужные документы, чтобы случайно не создать лишний выписной эпикриз
        # или дневники наблюдения.
        self.output_vars: Dict[str, tk.BooleanVar] = {
            kind: tk.BooleanVar(value=False) for kind in DOCUMENT_ORDER
        }
        self.output_vars[DIARY_KIND] = tk.BooleanVar(value=False)

    def _init_diary_state(self) -> None:
        # Дневники.
        self.status_files: List[str] = []
        # Папка с текстами дневников. В новом сценарии файлы внутри названы
        # диагнозами, поэтому после чтения первичного документа программа
        # может автоматически выбрать нужный DOCX по diagnosis_var.
        self.diary_texts_dir: str = ""
        self._diary_text_files_auto_selected = False
        self.diary_files: List[str] = []
        # Папка, выбранная кнопкой «Шаблоны дневников». Сама кнопка теперь
        # выбирает именно папку 01–31, а не отдельный DOCX-файл. Конкретный
        # шаблон затем автоматически подставляется в прежний fill_diary_batch.
        self.diary_template_dir: str = ""
        # True only when the numbered 01–31 template was selected by the program.
        # Manual template selection by the doctor is still respected.
        self._diary_files_auto_selected = False
        self.repeat_statuses_var = tk.BooleanVar(value=True)
        self.reset_each_file_var = tk.BooleanVar(value=True)
        self.keep_signature_var = tk.BooleanVar(value=True)
        self.fill_months_var = tk.BooleanVar(value=True)
        self.force_final_diary_var = tk.BooleanVar(value=True)
        self.remove_holiday_rows_var = tk.BooleanVar(value=True)
        self.open_result_folder_var = tk.BooleanVar(value=True)

    def _init_runtime_visual_state(self) -> None:
        # Скрытые служебные данные вместо прежних видимых блоков "Предпросмотр" и "Журнал".
        # Функционал остаётся: данные пациента хранятся, ошибки показываются в messagebox,
        # а короткий статус выводится в нижней панели.
        self._last_preview_text = ""
        self._log_buffer: List[str] = []

        # Визуальные состояния выбранных кнопок/плиток. Пользователь должен сразу
        # видеть, какие документы, тексты и даты уже включены, а не искать
        # маленькую галочку внутри тёмной карточки.
        self._check_tile_redrawers: Dict[str, object] = {}
        self._state_button_redrawers: List[object] = []

        # Собственный быстрый список диагноза, встроенный прямо в карточку пациента.
        # Не используется плавающее окно: оно могло сбивать фокус и положение UI.
        self._diagnosis_popup: tk.Frame | None = None
        self._diagnosis_listbox: tk.Listbox | None = None
        self._diagnosis_popup_matches: list[str] = []

    def _configure_root_window(self) -> None:
        self.root.title(APP_TITLE)
        # Стартовый размер окна — примерно 1/3 площади экрана.
        # Берём коэффициент sqrt(1/3) ≈ 0.577 по ширине и высоте,
        # чтобы сохранить внешний вид референса, но не открывать окно слишком большим.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        target_w = max(900, int(screen_w * 0.577))
        target_h = max(700, int(screen_h * 0.63))
        start_x = max(0, (screen_w - target_w) // 2)
        start_y = max(0, (screen_h - target_h) // 2)
        self.root.geometry(f"{target_w}x{target_h}+{start_x}+{start_y}")
        self.root.minsize(980, 700)
        # Масштабируем не только окно, но и сам UI. Иначе при 1/3 экрана
        # карточки 03/04 уезжали вниз, а часть полей визуально обрезалась.
        self._ui_scale = max(0.57, min(1.0, target_w / 1408, target_h / 1056))
        self._font_scale = max(0.72, self._ui_scale)
        self._compact_ui = self._ui_scale < 0.82
        self.root.configure(bg=DEEP)
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._normal_geometry = f"{target_w}x{target_h}+{start_x}+{start_y}"
        self._is_maximized = False
        self._custom_chrome_restore_pending = False
        self.root.bind("<Map>", self._on_root_mapped, add="+")

    def _bootstrap_ui(self) -> None:
        self._apply_custom_window_chrome()
        self._install_text_shortcuts()
        self._build_ui()
        # Drag-and-drop включается только через безопасный TkDND-путь.
        # Нативная подмена Windows WndProc была рискованной: на некоторых ПК
        # приложение могло не стартовать или закрываться сразу после запуска.
        self.root.after(150, self._install_file_drop_support)
        self._check_templates()
        self._set_status("Готов к работе")
        self.root.after(250, lambda: self.refresh_printers(silent=True))
