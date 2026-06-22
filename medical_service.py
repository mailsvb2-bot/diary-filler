"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from medical_constants import DOCUMENT_LABELS, DOCUMENT_ORDER, OUTPUT_SUFFIXES
from medical_docx_reader import extract_docx_text
from medical_formatting import available_path, parse_date, safe_filename, strip_leading_epi_label
from medical_models import PatientData
from medical_parser import MedicalTextParser
from medical_paths import bundled_template_path
from medical_renderer import MedicalDocumentRenderer


_TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1251")
_PRIMARY_SUFFIXES = {".docx", ".docm"}
_EPI_TEXT_SUFFIXES = {".txt"}
_EPI_DOCX_SUFFIXES = {".docx", ".docm"}


class MedicalDocumentService:
    def __init__(self):
        self.parser = MedicalTextParser()
        self.renderer = MedicalDocumentRenderer()

    def parse_primary_document(self, path: str | Path) -> PatientData:
        """Прочитать входной первичный документ пациента.

Поддерживаются оба рабочих источника данных:
- направление на госпитализацию;
- уже заполненный первичный осмотр.

Оба документа приводятся к единой PatientData, из которой затем создаются
все отмеченные в UI документы.
        """
        primary_path = self._existing_file(path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES)
        return self.parser.parse_docx(primary_path)

    def parse_navigation(self, path: str | Path) -> PatientData:
        # Совместимость со старыми вызовами: раньше входной документ назывался
        # "направление". Теперь это общий первичный документ.
        return self.parse_primary_document(path)

    @staticmethod
    def _existing_file(
        path: str | Path | None,
        label: str,
        *,
        allowed_suffixes: set[str] | None = None,
    ) -> Path:
        if path is None or str(path).strip() == "":
            raise ValueError(f"Не выбран файл: {label}.")
        candidate = Path(path).expanduser()
        if not candidate.exists() or not candidate.is_file():
            raise FileNotFoundError(f"Не найден файл ({label}): {candidate}")
        if allowed_suffixes is not None and candidate.suffix.lower() not in allowed_suffixes:
            allowed_text = ", ".join(sorted(allowed_suffixes))
            raise ValueError(f"Неверный формат файла ({label}): {candidate.suffix or 'без расширения'}. Разрешено: {allowed_text}.")
        return candidate

    @staticmethod
    def _read_text_file(path: Path) -> str:
        """Read physician TXT snippets in UTF-8/UTF-8-BOM/Windows-1251.

        На Windows врач может сохранить ЭПИ/дополнительный текст в cp1251.
        Старое чтение через ``errors='ignore'`` могло тихо съедать кириллицу.
        """
        raw = path.read_bytes()
        for encoding in _TEXT_ENCODINGS:
            try:
                return raw.decode(encoding).strip()
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _normalize_selected_docs(selected_docs: Sequence[str] | str | None) -> tuple[str, ...]:
        allowed = set(DOCUMENT_ORDER)
        label_to_kind = {label: kind for kind, label in DOCUMENT_LABELS.items()}
        normalized: list[str] = []
        seen: set[str] = set()
        unknown: list[str] = []
        if selected_docs is None:
            selected_iterable: Sequence[str] = ()
        elif isinstance(selected_docs, str):
            selected_iterable = (selected_docs,)
        else:
            selected_iterable = selected_docs
        for raw_kind in selected_iterable:
            kind = str(raw_kind).strip()
            if not kind:
                continue
            # Public/service calls sometimes pass visible UI labels instead of
            # internal keys. Accepting labels keeps the boundary convenient while
            # still rejecting truly unknown values.
            kind = label_to_kind.get(kind, kind)
            if kind not in allowed:
                if kind not in unknown:
                    unknown.append(str(raw_kind).strip())
                continue
            if kind not in seen:
                seen.add(kind)
                normalized.append(kind)
        if unknown:
            labels = ", ".join(unknown)
            raise ValueError(f"Неизвестный тип медицинского документа: {labels}")
        if not normalized:
            raise ValueError("Не выбран ни один медицинский документ.")
        return tuple(normalized)

    @staticmethod
    def _resolve_output_dir(output_dir: str | Path | None, fallback_dir: Path) -> Path:
        if output_dir is None or str(output_dir).strip() == "":
            result = fallback_dir
        else:
            result = Path(output_dir).expanduser()
        if result.exists() and not result.is_dir():
            raise ValueError(f"Папка результата указывает на файл, а не на папку: {result}")
        result.mkdir(parents=True, exist_ok=True)
        return result

    @staticmethod
    def _normalize_discharge_date(value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""
        parsed = parse_date(value)
        if not parsed:
            raise ValueError("Дата выписки должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или ДМГГ.")
        return parsed.strftime("%d.%m.%Y")

    @staticmethod
    def _ensure_discharge_not_before_admission(admission_date: str, discharge_date: str) -> None:
        if not admission_date or not discharge_date:
            return
        admission = parse_date(admission_date)
        discharge = parse_date(discharge_date)
        if admission and discharge and discharge.date() < admission.date():
            raise ValueError("Дата выписки не может быть раньше даты госпитализации.")

    @staticmethod
    def _ensure_date_not_before_admission(admission_date: str, value: str, label: str) -> None:
        """Protect service-boundary dates from impossible episode chronology."""
        if not admission_date or not value:
            return
        admission = parse_date(admission_date)
        parsed = parse_date(value)
        if admission and parsed and parsed.date() < admission.date():
            raise ValueError(f"{label} не может быть раньше даты госпитализации.")

    @staticmethod
    def _require_core_text(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Не найдено обязательное поле пациента: {label}.")
        return normalized


    @staticmethod
    def _normalize_required_date(value: str, label: str) -> str:
        value = str(value or "").strip()
        parsed = parse_date(value)
        if not parsed:
            raise ValueError(f"{label} должна быть в формате ДД.ММ.ГГГГ, ДД.ММ.ГГ, ДДММГГГГ, ДДММГГ или коротко ДМГГ.")
        return parsed.strftime("%d.%m.%Y")

    @staticmethod
    def _require_text(value: str, label: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"Не заполнено обязательное поле: {label}.")
        return normalized

    def _validate_and_normalize_selected_data(self, data: PatientData, selected: Sequence[str]) -> None:
        selected_set = set(selected)

        # Service-layer is a hard boundary: direct programmatic calls must be as
        # safe as the UI path. Otherwise tests/automation can generate DOCX with
        # empty patient identity, missing history number or clinically impossible
        # dates even though the manual UI would have asked the doctor first.
        data.fio = self._require_core_text(data.fio, "Ф.И.О.")
        data.admission_date = self._require_core_text(data.admission_date, "дата госпитализации")
        data.case_number = self._require_text(data.case_number, "номер истории болезни")
        data.diagnosis = self._require_text(data.diagnosis, "диагноз")

        treatment_docs = {"primary", "discharge", "commission", "vk_mse", "sick_leave_vk"}
        if selected_set & treatment_docs:
            data.treatment_plan = self._require_text(data.treatment_plan, "лечение")

        if {"discharge", "rvk"} & selected_set:
            data.discharge_date = self._normalize_required_date(data.discharge_date, "Дата выписки")
            self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)

        if "commission" in selected_set:
            data.commission_date = self._normalize_required_date(data.commission_date, "Дата совместного осмотра")
            self._ensure_date_not_before_admission(data.admission_date, data.commission_date, "Дата совместного осмотра")
            data.commission_number = self._require_text(data.commission_number, "номер совместного осмотра")

        if "vk_mse" in selected_set:
            data.vk_date = self._normalize_required_date(data.vk_date, "Дата ВК на МСЭ")
            self._ensure_date_not_before_admission(data.admission_date, data.vk_date, "Дата ВК на МСЭ")
            data.vk_protocol_number = self._require_text(data.vk_protocol_number, "номер протокола ВК на МСЭ")
            data.vk_protocol_date = self._normalize_required_date(data.vk_protocol_date, "Дата протокола ВК на МСЭ")
            self._ensure_date_not_before_admission(data.admission_date, data.vk_protocol_date, "Дата протокола ВК на МСЭ")
            data.vk_mse_work_org = (data.vk_mse_work_org or data.work_org or "не работает").strip()
            data.vk_mse_position = (data.vk_mse_position or data.position).strip()

        if "sick_leave_vk" in selected_set:
            data.sick_leave_vk_date = self._normalize_required_date(data.sick_leave_vk_date, "Дата ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_date, "Дата ВК больничного")
            data.sick_leave_vk_protocol_number = self._require_text(data.sick_leave_vk_protocol_number, "номер протокола ВК больничного")
            data.sick_leave_vk_protocol_date = self._normalize_required_date(data.sick_leave_vk_protocol_date, "Дата протокола ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_protocol_date, "Дата протокола ВК больничного")
            data.sick_leave_vk_commission_date = self._normalize_required_date(data.sick_leave_vk_commission_date, "Дата проведения комиссии ВК больничного")
            self._ensure_date_not_before_admission(data.admission_date, data.sick_leave_vk_commission_date, "Дата проведения комиссии ВК больничного")
            data.sick_leave_vk_work_org = (data.sick_leave_vk_work_org or data.work_org or "не работает").strip()
            data.sick_leave_vk_position = (data.sick_leave_vk_position or data.position).strip()
            data.sick_leave_vk_work_position = data.sick_leave_vk_work_position or ", ".join(
                part for part in [data.sick_leave_vk_work_org, data.sick_leave_vk_position] if part
            )

        if "rvk" in selected_set:
            data.rvk_act_number = self._require_text(data.rvk_act_number, "номер медицинского заключения РВК")
            data.rvk_military_commissariat = self._require_text(data.rvk_military_commissariat, "военкомат для Акта РВК")

    def load_epi_text(self, path: str | Path) -> str:
        if not path:
            return ""
        path = self._existing_file(path, "ЭПИ", allowed_suffixes=_EPI_DOCX_SUFFIXES | _EPI_TEXT_SUFFIXES)
        if path.suffix.lower() in _EPI_DOCX_SUFFIXES:
            text = extract_docx_text(path)
        else:
            text = self._read_text_file(path)
        return strip_leading_epi_label(text)

    def available_templates(self) -> Dict[str, Path]:
        return {kind: bundled_template_path(kind) for kind in DOCUMENT_ORDER}

    def missing_templates(self) -> List[Path]:
        return [path for path in self.available_templates().values() if not path.exists()]

    def create_documents(
        self,
        *,
        navigation_path: str | Path,
        output_dir: str | Path | None,
        discharge_date: str = "",
        epi_path: str | Path | None = None,
        selected_docs: Sequence[str] | str | None = DOCUMENT_ORDER,
        override_data: Optional[PatientData] = None,
    ) -> Tuple[List[Path], PatientData]:
        selected = self._normalize_selected_docs(selected_docs)
        primary_path = self._existing_file(navigation_path, "первичный документ", allowed_suffixes=_PRIMARY_SUFFIXES)
        normalized_discharge_date = self._normalize_discharge_date(discharge_date)

        template_paths = {kind: bundled_template_path(kind) for kind in selected}
        missing = [path for path in template_paths.values() if not path.exists()]
        if missing:
            missing_text = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Не найдены встроенные шаблоны:\n{missing_text}")

        data = copy.deepcopy(override_data) if override_data is not None else self.parse_primary_document(primary_path)
        data.discharge_date = normalized_discharge_date or data.discharge_date
        self._ensure_discharge_not_before_admission(data.admission_date, data.discharge_date)
        if epi_path:
            data.epi_text = self.load_epi_text(epi_path)
        self._validate_and_normalize_selected_data(data, selected)

        output_path_root = self._resolve_output_dir(output_dir, primary_path.parent)
        stem = safe_filename(data.output_fio or data.fio or primary_path.stem)

        created: List[Path] = []
        for kind in selected:
            template_path = template_paths[kind]
            suffix = OUTPUT_SUFFIXES[kind]
            output_path = available_path(output_path_root / f"{stem} {suffix}.docx")
            self.renderer.render(kind, template_path, output_path, data)
            created.append(output_path)
        return created, data
