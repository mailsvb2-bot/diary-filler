from __future__ import annotations

from pathlib import Path
from typing import List
from tkinter import messagebox
import os
import subprocess
import sys

from app_config import *


class ActionsCreationOrchestratorMixin:
    def _open_result_folder_silent(self, folder: Path) -> bool:
        """Открыть папку результата без дополнительного popup-уведомления."""
        try:
            folder = Path(folder).expanduser()
            if os.environ.get("CI") or not folder.exists() or not folder.is_dir():
                return False
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(folder)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
            else:
                if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                    return False
                subprocess.Popen(
                    ["xdg-open", str(folder)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
            return True
        except Exception:
            # Открытие папки — удобство, а не часть генерации документов.
            # Ошибка shell/Explorer не должна ломать созданные DOCX.
            return False

    def _open_output_folder_after_creation(
        self,
        *,
        created_files: List[Path],
        creation_report: Path | None,
    ) -> bool:
        if not getattr(self, "open_result_folder_var", None) or not self.open_result_folder_var.get():
            return False
        folder: Path | None = None
        if created_files:
            folder = created_files[0].parent
        elif creation_report is not None:
            folder = creation_report.parent
        else:
            folder = self._result_output_dir()
        return self._open_result_folder_silent(folder)

    def create_selected_outputs(self, *, print_after: bool = False) -> None:
        selected_medical = self.selected_medical_docs()
        selected_diaries = self.diaries_selected()
        if not selected_medical and not selected_diaries:
            messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы один документ или «Дневники наблюдения».")
            return
        self._log("\n▶ Выбрано для создания: " + ", ".join(self._selected_output_names(selected_medical, selected_diaries)) + "\n")
        special_merged_popup_selected = any(kind in selected_medical for kind in {"discharge", "rvk"})
        non_special_medical_selected = any(kind not in {"discharge", "rvk"} for kind in selected_medical)
        if not special_merged_popup_selected and (non_special_medical_selected or selected_diaries):
            # Programmatic selections/restored state must obey the same popup
            # contract as manual clicks. When neither выписной nor РВК is selected,
            # collect common missing fields (лечение/реквизиты направления/date for
            # diaries) in one window instead of opening treatment and discharge-date
            # popups one after another. Выписной and РВК have their own merged
            # popups below and therefore intentionally own these common questions.
            if not self._prompt_common_output_requirements(
                include_discharge_date=selected_diaries,
                include_case_number=non_special_medical_selected,
                include_medical_details=non_special_medical_selected,
            ):
                return
        if "commission" in selected_medical and not all([
            self.commission_date_var.get().strip(),
            self.commission_number_var.get().strip(),
        ]):
            if not self._prompt_commission_details():
                return
        if "rvk" in selected_medical:
            rvk_needs_popup = (
                not all([
                    self.rvk_act_number_var.get().strip(),
                    self.rvk_military_commissariat_var.get().strip(),
                ])
                or self._case_number_missing()
                or self._should_prompt_discharge_date()
                or self._manual_treatment_missing()
                or self._hospitalization_details_missing()
            )
            if rvk_needs_popup and not self._prompt_rvk_details():
                return
        if "vk_mse" in selected_medical and not all([
            self.vk_date_var.get().strip(),
            self.vk_protocol_number_var.get().strip(),
            self.vk_protocol_date_var.get().strip(),
            self.vk_mse_work_org_var.get().strip(),
        ]):
            if not self._prompt_vk_mse_details():
                return
        if "sick_leave_vk" in selected_medical and not all([
            self.sick_leave_vk_date_var.get().strip(),
            self.sick_leave_vk_protocol_number_var.get().strip(),
            self.sick_leave_vk_protocol_date_var.get().strip(),
            self.sick_leave_vk_commission_date_var.get().strip(),
            self.sick_leave_vk_work_org_var.get().strip(),
            self.sick_leave_vk_position_var.get().strip(),
        ]):
            if not self._prompt_sick_leave_vk_details():
                return
        if (
            selected_medical
            and self._selected_docs_need_expert_anamnesis(selected_medical)
            and self._normalize_yes_no(self.expert_sick_leave_needed_var.get()) == "да"
        ):
            if not self._prompt_expert_anamnesis_details(force=False):
                return
        if "discharge" in selected_medical:
            if not self._prompt_discharge_output_requirements():
                return
        remaining_medical_for_referral_popup = [
            kind for kind in selected_medical
            if kind not in {"discharge", "rvk"}
        ]
        if remaining_medical_for_referral_popup:
            # Для первичного осмотра popup не открывается: программа берёт
            # данные из самого DOCX. Для направления на госпитализацию врач
            # подтверждает номер истории болезни, лечение и диагноз.
            if not self._prompt_assigned_treatment_if_needed(force=False):
                return

        if print_after and not self.printer_var.get().strip():
            # refresh_printers() is asynchronous for UI responsiveness. For the
            # explicit "создать и распечатать" path we need a concrete printer
            # before continuing, otherwise the old code warned immediately while
            # the background discovery was still running.
            if not self._select_default_printer_sync():
                messagebox.showwarning("Принтер не выбран", "Выберите принтер перед печатью или используйте кнопку сохранения без печати.")
                return

        self._start_progress()
        created_medical: List[Path] = []
        diary_result = None
        errors: List[str] = []

        try:
            if selected_medical:
                try:
                    created_medical = self._create_medical_documents_impl(selected_medical)
                except Exception as exc:
                    errors.append(f"Медицинские документы: {exc}")
                    self._log(f"\n❌ Медицинские документы не созданы: {exc}\n")
                    self._write_creation_report(
                        selected_medical=selected_medical,
                        selected_diaries=selected_diaries,
                        created_medical=created_medical,
                        diary_result=None,
                        errors=errors,
                    )
                    messagebox.showerror(
                        "Медицинские документы не созданы",
                        "Вы отметили медицинские документы, но их создание остановилось с ошибкой:\n\n"
                        f"{exc}\n\n"
                        "Дневники после этого не запускались, чтобы не получилось частичное создание только одного типа документов.",
                    )
                    return

            if selected_diaries:
                try:
                    diary_result = self._create_diaries_impl()
                except Exception as exc:
                    errors.append(f"Дневники: {exc}")
                    self._log(f"\n❌ Дневники: {exc}\n")
        finally:
            self._stop_progress()

        if errors:
            self._write_creation_report(
                selected_medical=selected_medical,
                selected_diaries=selected_diaries,
                created_medical=created_medical,
                diary_result=diary_result,
                errors=errors,
            )
            messagebox.showwarning("Готово с ошибками", "Часть задач не выполнена:\n\n" + "\n".join(errors))
            return

        created_files: List[Path] = list(created_medical)
        if diary_result is not None:
            created_files.extend(list(diary_result.created_files))

        print_result = None
        if print_after:
            self._set_status("Отправляю документы на печать...")
            self.root.update_idletasks()
            from printer_support import print_files
            print_result = print_files(created_files, self.printer_var.get().strip())
            if print_result.errors:
                messagebox.showwarning(
                    "Создано, но печать с ошибками",
                    "Файлы сохранены, но часть документов не удалось отправить на печать:\n\n"
                    + "\n".join(print_result.errors[:10])
                )

        creation_report = self._write_creation_report(
            selected_medical=selected_medical,
            selected_diaries=selected_diaries,
            created_medical=created_medical,
            diary_result=diary_result,
            errors=None,
        )

        opened_folder = self._open_output_folder_after_creation(
            created_files=created_files,
            creation_report=creation_report,
        )
        self._set_status("Готово: файлы сохранены")
        self._log("\n✅ Готово: файлы сохранены.{}\n".format(" Папка результата открыта." if opened_folder else ""))
