from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from app_config import *


_PERSISTENT_FOLDER_KEYS = {
    DIR_DIARY_TEXTS,
    DIR_DIARY_TEMPLATES,
    DIR_NUMBERED_DIARY_TEMPLATES,
}
_SESSION_ONLY_FOLDER_KEYS = {DIR_OUTPUT, DIR_PRIMARY_DOCUMENTS, DIR_EPI}

_STAFF_PROFILE_KEY = "staff_profile"
_STAFF_PROFILE_FIELDS = ("doctor", "department_head", "deputy_chief")
_STAFF_PROFILE_DEFAULTS = {
    "doctor": "Балаганин С.В",
    "department_head": "Можарова Е.А.",
    "deputy_chief": "Зуйкова А.А.",
}
_STAFF_PROFILE_MAX_LENGTH = 160
_DESKTOP_INTAKE_KEY = "desktop_intake_enabled"


class SettingsMixin:
    def _get_settings_path(self) -> Path:
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home()
        return root / "MedicalDiaryAutofill" / "settings.json"

    def _quarantine_broken_settings(self, details: Exception | str) -> None:
        """Сохранить битый settings.json рядом, чтобы новый запуск не падал.

        В settings.json хранятся только технические удобства: переиспользуемые
        технические настройки и профиль сотрудников отделения. Данные пациентов туда не пишутся. Если
        файл оказался повреждён из-за аварийного завершения Windows/диска,
        программа стартует с пустыми настройками и оставляет копию для разбора.
        """
        try:
            if not self._settings_path.exists():
                return
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            broken_path = self._settings_path.with_name(f"settings.broken.{stamp}.json")
            broken_path.write_text(
                self._settings_path.read_text(encoding="utf-8", errors="replace")
                + "\n\n/* settings.json был проигнорирован программой: "
                + str(details).replace("*/", "")
                + " */\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_settings(self) -> dict:
        try:
            if self._settings_path.exists():
                data = json.loads(self._settings_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    safe: dict = {}
                    folders_raw = data.get("folders")
                    if isinstance(folders_raw, dict):
                        folders = {
                            str(key).strip(): str(value).strip()
                            for key, value in folders_raw.items()
                            if str(key).strip() in _PERSISTENT_FOLDER_KEYS and str(value).strip()
                        }
                        if folders:
                            safe["folders"] = folders
                    printer = str(data.get("printer", "")).strip()
                    if printer:
                        safe["printer"] = printer
                    if isinstance(data.get(_DESKTOP_INTAKE_KEY), bool):
                        safe[_DESKTOP_INTAKE_KEY] = bool(data[_DESKTOP_INTAKE_KEY])
                    staff_raw = data.get(_STAFF_PROFILE_KEY)
                    if isinstance(staff_raw, dict):
                        profile = {}
                        for key in _STAFF_PROFILE_FIELDS:
                            value = " ".join(str(staff_raw.get(key, "")).split())[:_STAFF_PROFILE_MAX_LENGTH].strip()
                            if value:
                                profile[key] = value
                        if staff_raw.get("configured") is True and all(profile.get(k) for k in _STAFF_PROFILE_FIELDS):
                            profile["configured"] = True
                            safe[_STAFF_PROFILE_KEY] = profile
                    return safe
                # JSON может быть синтаксически валидным, но иметь неверный
                # тип (например, список после ручной правки). Такой файл тоже
                # изолируем, иначе программа будет стартовать с пустыми
                # настройками без объяснимого следа диагностики.
                self._quarantine_broken_settings(f"ожидался объект JSON, получено {type(data).__name__}")
        except json.JSONDecodeError as exc:
            self._quarantine_broken_settings(exc)
        except Exception:
            pass
        return {}

    def _settings_payload_for_disk(self) -> dict:
        """Вернуть только безопасные настройки для записи на диск.

        Production-контракт: история пациентов, диагнозы, даты лечения, пути
        созданных документов и содержимое медицинских файлов никогда не
        сохраняются в settings.json. На диск уходят только переиспользуемые
        технические настройки и профиль сотрудников отделения.
        """
        payload: dict = {}
        folders_raw = self._settings.get("folders")
        folders: dict[str, str] = {}
        if isinstance(folders_raw, dict):
            for key, value in folders_raw.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text in _PERSISTENT_FOLDER_KEYS and value_text:
                    folders[key_text] = value_text
                elif key_text in _SESSION_ONLY_FOLDER_KEYS:
                    # Preserve legacy settings schema without persisting the path itself.
                    folders[key_text] = ""
        if folders:
            payload["folders"] = folders
        printer = str(self._settings.get("printer", "")).strip()
        if printer:
            payload["printer"] = printer
        intake_enabled = self._settings.get(_DESKTOP_INTAKE_KEY)
        if isinstance(intake_enabled, bool):
            payload[_DESKTOP_INTAKE_KEY] = intake_enabled
        staff_raw = self._settings.get(_STAFF_PROFILE_KEY)
        if isinstance(staff_raw, dict) and staff_raw.get("configured") is True:
            profile = {"configured": True}
            for key in _STAFF_PROFILE_FIELDS:
                value = " ".join(str(staff_raw.get(key, "")).split())[:_STAFF_PROFILE_MAX_LENGTH].strip()
                if not value:
                    profile = {}
                    break
                profile[key] = value
            if profile:
                payload[_STAFF_PROFILE_KEY] = profile
        return payload

    def _save_settings(self) -> None:
        tmp_path = self._settings_path.with_name(self._settings_path.name + ".tmp")
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(self._settings_payload_for_disk(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp_path, self._settings_path)
        except Exception:
            # Настройки — удобство, не критичная функция. Ошибку не показываем врачу,
            # но не оставляем рядом битый settings.json.tmp после неудачной записи.
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _staff_profile_defaults(self) -> dict[str, str]:
        return dict(_STAFF_PROFILE_DEFAULTS)

    def _staff_profile_is_configured(self) -> bool:
        profile = self._settings.get(_STAFF_PROFILE_KEY)
        return bool(
            isinstance(profile, dict)
            and profile.get("configured") is True
            and all(str(profile.get(key, "")).strip() for key in _STAFF_PROFILE_FIELDS)
        )

    def _effective_staff_profile(self) -> dict[str, str]:
        result = self._staff_profile_defaults()
        profile = self._settings.get(_STAFF_PROFILE_KEY)
        if isinstance(profile, dict):
            for key in _STAFF_PROFILE_FIELDS:
                value = " ".join(str(profile.get(key, "")).split())[:_STAFF_PROFILE_MAX_LENGTH].strip()
                if value:
                    result[key] = value
        return result

    def _set_staff_profile(self, *, doctor: str, department_head: str, deputy_chief: str) -> bool:
        values = {
            "doctor": " ".join(str(doctor or "").split())[:_STAFF_PROFILE_MAX_LENGTH].strip(),
            "department_head": " ".join(str(department_head or "").split())[:_STAFF_PROFILE_MAX_LENGTH].strip(),
            "deputy_chief": " ".join(str(deputy_chief or "").split())[:_STAFF_PROFILE_MAX_LENGTH].strip(),
        }
        if not all(values.values()):
            return False
        self._settings[_STAFF_PROFILE_KEY] = {**values, "configured": True}
        self._save_settings()
        return True

    def _desktop_intake_preference(self) -> bool | None:
        value = self._settings.get(_DESKTOP_INTAKE_KEY)
        return value if isinstance(value, bool) else None

    def _set_desktop_intake_preference(self, enabled: bool) -> None:
        self._settings[_DESKTOP_INTAKE_KEY] = bool(enabled)
        self._save_settings()

    def _apply_staff_profile_to_patient_data(self, data):
        profile = self._effective_staff_profile()
        data.doctor = profile["doctor"]
        data.head = profile["department_head"]
        data.deputy_chief = profile["deputy_chief"]
        return data

    def _prompt_staff_profile(self, *, first_run: bool = False) -> bool:
        from tkinter import messagebox, simpledialog

        # Never prefill a fresh/unconfigured installation with somebody
        # else's legacy names. Existing confirmed profiles remain convenient to
        # edit, but a new user must consciously enter all three staff identities.
        defaults = (
            self._effective_staff_profile()
            if self._staff_profile_is_configured()
            else {key: "" for key in _STAFF_PROFILE_FIELDS}
        )
        if first_run:
            messagebox.showinfo(
                "Первый запуск — сотрудники",
                "Укажите сотрудников один раз. Эти данные будут использоваться "
                "в дневниках, эпикризах, актах, ВК и остальных создаваемых документах.\n\n"
                "Можно вводить полное ФИО или фамилию с инициалами.",
                parent=self.root,
            )
        prompts = (
            ("doctor", "ФИО лечащего врача", defaults["doctor"]),
            ("department_head", "ФИО заведующего отделением", defaults["department_head"]),
            ("deputy_chief", "ФИО начмеда / заместителя главного врача", defaults["deputy_chief"]),
        )
        values = {}
        for key, label, default in prompts:
            while True:
                value = simpledialog.askstring(
                    "Сотрудники отделения", f"{label}:", initialvalue=default, parent=self.root
                )
                if value is None:
                    return False
                value = " ".join(value.split()).strip()
                if value:
                    values[key] = value
                    break
                messagebox.showwarning(
                    "Сотрудники отделения", "Поле не должно быть пустым.", parent=self.root
                )
        if not self._set_staff_profile(
            doctor=values["doctor"],
            department_head=values["department_head"],
            deputy_chief=values["deputy_chief"],
        ):
            return False
        if not first_run:
            messagebox.showinfo(
                "Сотрудники отделения",
                "ФИО сотрудников сохранены. Новые значения будут использоваться "
                "во всех следующих создаваемых документах и дневниках.",
                parent=self.root,
            )
        return True

    def _settings_folders(self) -> dict:
        folders = self._settings.get("folders")
        if not isinstance(folders, dict):
            folders = {}
            self._settings["folders"] = folders
        return folders

    def _session_folders(self) -> dict:
        folders = getattr(self, "_session_dialog_folders", None)
        if not isinstance(folders, dict):
            folders = {}
            self._session_dialog_folders = folders
        return folders

    def _get_saved_directory(self, key: str) -> str:
        value = str(self._session_folders().get(key) or self._settings_folders().get(key, "")).strip()
        if not value:
            return ""
        try:
            path = Path(value).expanduser()
            if path.exists() and path.is_dir():
                return str(path)
        except Exception:
            return ""
        return ""

    def _dialog_initial_dir(self, key: str, *fallbacks: str) -> str:
        candidates = [self._get_saved_directory(key), *fallbacks, self.output_dir_var.get().strip(), str(Path.home())]
        for value in candidates:
            if not value:
                continue
            try:
                path = Path(value).expanduser()
                if path.is_file():
                    path = path.parent
                if path.exists() and path.is_dir():
                    return str(path)
            except Exception:
                continue
        return ""

    def _remember_dialog_directory(self, key: str, selected_path: str, *, selected_is_dir: bool = False) -> None:
        if not selected_path:
            return
        try:
            path = Path(selected_path).expanduser()
            folder = path if selected_is_dir else path.parent
            if folder.exists() and folder.is_dir():
                self._session_folders()[key] = str(folder)
                if key in _PERSISTENT_FOLDER_KEYS:
                    self._settings_folders()[key] = str(folder)
                else:
                    # Primary/EPI/output folders can contain a patient's FIO or
                    # history number in their directory name. Keep them session-only.
                    self._settings_folders().pop(key, None)
                self._save_settings()
        except Exception:
            # Память папок — удобство, не критичная функция.
            pass
