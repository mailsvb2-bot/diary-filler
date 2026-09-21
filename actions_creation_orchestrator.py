from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
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

    def _prepare_generation_output_dir(self) -> Path:
        output_dir = Path(self._result_output_dir()).expanduser()
        if output_dir.exists() and not output_dir.is_dir():
            raise ValueError(f"Папка результата указывает на файл, а не на папку: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _commit_staged_generation(
        self,
        *,
        final_output_dir: Path,
        staged_medical: List[Path],
        diary_result,
    ):
        """Commit one complete generated set or roll back files moved by this call."""
        from shared_paths import resolve_available_path

        committed: List[Path] = []
        final_medical: List[Path] = []
        final_diaries: List[Path] = []
        final_diary_report: Path | None = None

        def commit_one(staged_path: Path, *, style: str) -> Path:
            staged_path = Path(staged_path)
            if not staged_path.exists() or not staged_path.is_file():
                raise FileNotFoundError(f"Не найден подготовленный файл комплекта: {staged_path}")
            target = resolve_available_path(final_output_dir / staged_path.name, style=style)
            os.replace(staged_path, target)
            committed.append(target)
            return target

        try:
            for staged_path in staged_medical:
                final_medical.append(commit_one(Path(staged_path), style="paren"))
            if diary_result is not None:
                for staged_path in diary_result.created_files:
                    final_diaries.append(commit_one(Path(staged_path), style="underscore"))
                if diary_result.report_path is not None:
                    final_diary_report = commit_one(Path(diary_result.report_path), style="underscore")
        except Exception:
            for path in reversed(committed):
                try:
                    path.unlink()
                except OSError:
                    pass
            raise

        if diary_result is not None:
            diary_result.created_files = final_diaries
            diary_result.report_path = final_diary_report
        return final_medical, diary_result

    def _focus_retry_on_failed_outputs(
        self,
        *,
        selected_medical: List[str],
        selected_diaries: bool,
        created_medical: List[Path],
        diary_result,
        errors: List[str],
    ) -> None:
        """After partial success, leave only the failed part selected for retry."""
        if not errors:
            return
        output_vars = getattr(self, "output_vars", {})
        changed = False
        if created_medical:
            for kind in selected_medical:
                var = output_vars.get(kind) if isinstance(output_vars, dict) else None
                if var is not None:
                    try:
                        var.set(False)
                        changed = True
                    except Exception:
                        pass
        # Diaries remain selected when they were requested but failed. If they
        # succeeded, clear them too so a later click cannot duplicate them.
        if selected_diaries and diary_result is not None:
            var = output_vars.get("diaries") if isinstance(output_vars, dict) else None
            if var is not None:
                try:
                    var.set(False)
                    changed = True
                except Exception:
                    pass
        if changed and hasattr(self, "_redraw_selection_controls"):
            try:
                self._redraw_selection_controls()
            except Exception:
                pass

    def _clear_output_selections_for_print_retry(
        self,
        *,
        selected_medical: List[str],
        selected_diaries: bool,
    ) -> None:
        """Clear already-created outputs so print retry cannot regenerate duplicates."""
        output_vars = getattr(self, "output_vars", {})
        if not isinstance(output_vars, dict):
            return
        changed = False
        for kind in selected_medical:
            var = output_vars.get(kind)
            if var is not None:
                try:
                    var.set(False)
                    changed = True
                except Exception:
                    pass
        if selected_diaries:
            var = output_vars.get("diaries")
            if var is not None:
                try:
                    var.set(False)
                    changed = True
                except Exception:
                    pass
        if changed and hasattr(self, "_redraw_selection_controls"):
            try:
                self._redraw_selection_controls()
            except Exception:
                pass

    def _set_pending_print_retry_files(self, paths: List[Path]) -> None:
        pending: List[Path] = []
        seen: set[str] = set()
        for value in paths:
            path = Path(value)
            key = str(path)
            if key in seen or not path.exists() or not path.is_file():
                continue
            seen.add(key)
            pending.append(path)
        self._pending_print_retry_files = pending

    def _run_print_files_safely(self, paths: List[Path]):
        """Return a structured print result even if the print backend itself crashes."""
        from printer_support import PrintResult, print_files

        try:
            return print_files(paths, self.printer_var.get().strip())
        except Exception as exc:
            return PrintResult([], [f"Сбой подсистемы печати: {exc}"])

    def _retry_pending_print_if_requested(
        self,
        *,
        print_after: bool,
        selected_medical: List[str],
        selected_diaries: bool,
    ) -> bool:
        """Retry only saved files when the previous print attempt was incomplete."""
        if not print_after or selected_medical or selected_diaries:
            return False
        pending = [
            Path(path)
            for path in getattr(self, "_pending_print_retry_files", [])
            if Path(path).exists() and Path(path).is_file()
        ]
        self._pending_print_retry_files = pending
        if not pending:
            return False

        if not self.printer_var.get().strip() and not self._select_default_printer_sync():
            messagebox.showwarning(
                "Принтер не выбран",
                "Документы уже сохранены. Выберите принтер и нажмите кнопку печати ещё раз — "
                "повторно создавать документы не нужно.",
            )
            self._set_status("Печать ожидает повторной попытки")
            return True

        self._set_status("Повторно отправляю сохранённые документы на печать...")
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        result = self._run_print_files_safely(pending)
        printed = {Path(path) for path in result.printed_files}
        remaining = [path for path in pending if path not in printed]
        self._set_pending_print_retry_files(remaining)

        if result.errors:
            messagebox.showwarning(
                "Печать снова не завершена",
                "Документы уже сохранены и повторно не создавались. "
                "Не удалось отправить на печать:\n\n"
                + "\n".join(result.errors[:10])
                + "\n\nИсправьте принтер и нажмите кнопку печати ещё раз.",
            )
            self._set_status(f"Печать не завершена: ожидают повтора {len(self._pending_print_retry_files)} файл(ов)")
            self._log("\n⚠️ Повторная печать завершилась с ошибками; генерация документов не запускалась.\n")
        else:
            self._pending_print_retry_files = []
            self._set_status("Готово: сохранённые документы отправлены на печать")
            self._log("\n✅ Повторная печать сохранённых документов отправлена без повторной генерации.\n")
        return True

    def _ensure_staff_profile_for_generation(self) -> bool:
        """Fail closed before creating documents with unconfirmed staff names."""
        is_configured = getattr(self, "_staff_profile_is_configured", None)
        prompt = getattr(self, "_prompt_staff_profile", None)
        # Small test/embedding harnesses that do not own SettingsMixin keep the
        # historical contract; the production app always provides both methods.
        if not callable(is_configured) or not callable(prompt):
            return True
        try:
            if is_configured():
                return True
        except Exception:
            pass

        try:
            messagebox.showwarning(
                "Сотрудники не настроены",
                "Перед созданием документов укажите лечащего врача, заведующего "
                "отделением и начмеда / заместителя главного врача.\n\n"
                "Программа не будет подставлять неподтверждённые ФИО в медицинские документы.",
                parent=getattr(self, "root", None),
            )
        except Exception:
            pass

        try:
            if not prompt(first_run=False):
                return False
            return bool(is_configured())
        except Exception:
            return False

    def create_selected_outputs(self, *, print_after: bool = False) -> None:
        selected_medical = self.selected_medical_docs()
        selected_diaries = self.diaries_selected()
        if self._retry_pending_print_if_requested(
            print_after=print_after,
            selected_medical=selected_medical,
            selected_diaries=selected_diaries,
        ):
            return
        if not selected_medical and not selected_diaries:
            messagebox.showwarning("Ничего не выбрано", "Отметьте хотя бы один документ или «Дневники наблюдения».")
            return
        if not self._ensure_staff_profile_for_generation():
            self._set_status("Создание отменено: укажите сотрудников")
            return
        self._log("\n▶ Выбрано для создания: " + ", ".join(self._selected_output_names(selected_medical, selected_diaries)) + "\n")
        # A universal source may contain rich clinical text but omit FIO or
        # birth. Ask only for the missing identity facts before any document-
        # specific popup so generation never reaches the strict boundary with a
        # blank patient identity.
        if selected_medical and not self._prompt_missing_patient_identity_if_needed():
            return
        if selected_medical and not self._prompt_shared_clinical_options_if_needed(selected_medical):
            return
        occurrence_docs = {"primary", "discharge", "commission", "admission_doctor_referral", "rvk"}
        occurrence_selected = any(kind in occurrence_docs for kind in selected_medical)
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
                include_admission_occurrence=occurrence_selected,
                include_admission_date=bool(selected_medical or selected_diaries),
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
                or not self._current_admission_occurrence()
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
            try:
                final_output_dir = self._prepare_generation_output_dir()
                try:
                    generation_patient_data = self._capture_generation_patient_data(
                        require_primary=bool(selected_medical),
                    )
                except Exception as exc:
                    label = "Медицинские документы" if selected_medical else "Дневники"
                    errors.append(f"{label}: {exc}")
                    self._log(f"\n❌ Не удалось зафиксировать данные пациента для комплекта: {exc}\n")
                    self._write_creation_report(
                        selected_medical=selected_medical,
                        selected_diaries=selected_diaries,
                        created_medical=[],
                        diary_result=None,
                        errors=errors,
                    )
                    messagebox.showerror(
                        f"{label} не созданы",
                        f"Не удалось подготовить единый снимок данных пациента:\n\n{exc}",
                    )
                    return
                with TemporaryDirectory(prefix=".medical-autofill-set-", dir=str(final_output_dir)) as temp_dir:
                    staging_dir = Path(temp_dir)
                    staged_medical: List[Path] = []
                    staged_diary_result = None

                    if selected_medical:
                        try:
                            staged_medical = self._create_medical_documents_impl(
                                selected_medical,
                                output_dir_override=staging_dir,
                                log_created=False,
                                patient_data_snapshot=generation_patient_data,
                            )
                        except Exception as exc:
                            errors.append(f"Медицинские документы: {exc}")
                            self._log(f"\n❌ Медицинские документы не созданы: {exc}\n")
                            self._write_creation_report(
                                selected_medical=selected_medical,
                                selected_diaries=selected_diaries,
                                created_medical=[],
                                diary_result=None,
                                errors=errors,
                            )
                            messagebox.showerror(
                                "Медицинские документы не созданы",
                                "Вы отметили медицинские документы, но их создание остановилось с ошибкой:\n\n"
                                f"{exc}\n\n"
                                "Дневники после этого не запускались. Новые файлы комплекта не сохранены.",
                            )
                            return

                    if selected_diaries:
                        try:
                            staged_diary_result = self._create_diaries_impl(
                                output_dir_override=staging_dir,
                                log_created=False,
                                patient_data_snapshot=generation_patient_data,
                            )
                        except Exception as exc:
                            errors.append(f"Дневники: {exc}")
                            self._log(f"\n❌ Дневники: {exc}\n")

                    # A diary-specific failure must not destroy medical documents
                    # that were generated successfully in the same run. Commit the
                    # available medical part and report the diary failure as partial
                    # success. If nothing at all was prepared, keep the old hard fail.
                    if errors and not staged_medical and staged_diary_result is None:
                        self._write_creation_report(
                            selected_medical=selected_medical,
                            selected_diaries=selected_diaries,
                            created_medical=[],
                            diary_result=None,
                            errors=errors,
                        )
                        messagebox.showerror(
                            "Ничего не создано",
                            "Создание выбранных документов остановилось с ошибкой:\n\n"
                            + "\n".join(errors)
                            + "\n\nНовых файлов нет.",
                        )
                        return

                    try:
                        created_medical, diary_result = self._commit_staged_generation(
                            final_output_dir=final_output_dir,
                            staged_medical=staged_medical,
                            diary_result=staged_diary_result,
                        )
                    except Exception as exc:
                        errors.append(f"Сохранение комплекта: {exc}")
                        self._log(f"\n❌ Комплект не сохранён: {exc}\n")
                        self._write_creation_report(
                            selected_medical=selected_medical,
                            selected_diaries=selected_diaries,
                            created_medical=[],
                            diary_result=None,
                            errors=errors,
                        )
                        messagebox.showerror(
                            "Комплект не сохранён",
                            f"Не удалось сохранить подготовленный комплект:\n\n{exc}\n\n"
                            "Файлы, уже перенесённые этой попыткой, удалены.",
                        )
                        return
            except Exception as exc:
                errors.append(f"Папка результата: {exc}")
                self._log(f"\n❌ Не удалось подготовить папку результата: {exc}\n")
                messagebox.showerror("Комплект не создан", str(exc))
                return
        finally:
            self._stop_progress()

        if created_medical:
            self._log("\n✅ Созданы медицинские документы:\n")
            for path in created_medical:
                self._log(f"- {path}\n")
        if diary_result is not None:
            self._log("\n✅ Дневники заполнены:\n")
            for path in diary_result.created_files:
                self._log(f"- {path}\n")
            if diary_result.report_path is not None:
                self._log(f"Отчёт: {diary_result.report_path}\n")
            self._log(
                f"Итого: файлов {diary_result.processed_files}, дневников {diary_result.filled_rows}, "
                f"дат {diary_result.month_cells_filled}, финальных записей {diary_result.final_rows_filled}, "
                f"удалено после выписки {diary_result.removed_after_discharge_rows}.\n"
            )

        created_files: List[Path] = list(created_medical)
        if diary_result is not None:
            created_files.extend(list(diary_result.created_files))

        # Any newly saved set supersedes an older print-retry queue. This keeps
        # retry patient-scoped and prevents an old set from being printed later.
        if created_files:
            self._pending_print_retry_files = []

        print_result = None
        if print_after and errors:
            # Never auto-print an incomplete selected set. The successful files
            # stay saved, but the doctor must see the partial-generation warning
            # before deciding what to print. Sending paper first and warning
            # afterwards can create an incomplete physical chart by surprise.
            self._log("\n⚠️ Автоматическая печать отменена: комплект создан не полностью.\n")
        elif print_after:
            self._set_status("Отправляю документы на печать...")
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            print_result = self._run_print_files_safely(created_files)
            if print_result.errors:
                printed = {Path(path) for path in print_result.printed_files}
                pending = [path for path in created_files if path not in printed]
                self._set_pending_print_retry_files(pending)
                self._clear_output_selections_for_print_retry(
                    selected_medical=selected_medical,
                    selected_diaries=selected_diaries,
                )
                messagebox.showwarning(
                    "Создано, но печать с ошибками",
                    "Файлы сохранены, но часть документов не удалось отправить на печать:\n\n"
                    + "\n".join(print_result.errors[:10])
                    + "\n\nУже созданные пункты сняты с выбора. Исправьте принтер и снова нажмите "
                    "«Создать, сохранить, распечатать» — программа повторит только печать "
                    "неотправленных файлов, без создания копий."
                )
            else:
                self._pending_print_retry_files = []

        creation_report = self._write_creation_report(
            selected_medical=selected_medical,
            selected_diaries=selected_diaries,
            created_medical=created_medical,
            diary_result=diary_result,
            errors=errors or None,
        )

        if errors and created_files:
            self._focus_retry_on_failed_outputs(
                selected_medical=selected_medical,
                selected_diaries=selected_diaries,
                created_medical=created_medical,
                diary_result=diary_result,
                errors=errors,
            )
            messagebox.showwarning(
                "Комплект создан частично",
                "Созданы и сохранены все документы, которые удалось подготовить.\n\n"
                "Не создано:\n" + "\n".join(errors) +
                ("\n\nАвтоматическая печать не запускалась, потому что комплект неполный." if print_after else "") +
                "\n\nУже созданные пункты сняты с выбора. Исправьте источник дневников и повторите создание.",
            )

        opened_folder = self._open_output_folder_after_creation(
            created_files=created_files,
            creation_report=creation_report,
        )
        if errors:
            self._set_status("Готово частично: доступные документы сохранены")
            self._log("\n⚠️ Готово частично: доступные документы сохранены.{}\n".format(" Папка результата открыта." if opened_folder else ""))
        elif print_result is not None and print_result.errors:
            pending_count = len(getattr(self, "_pending_print_retry_files", []))
            self._set_status(f"Файлы сохранены; печать не завершена: ожидают повтора {pending_count} файл(ов)")
            self._log("\n⚠️ Файлы сохранены, но печать не завершена; доступен безопасный повтор без генерации копий.\n")
        else:
            self._set_status("Готово: файлы сохранены")
            self._log("\n✅ Готово: файлы сохранены.{}\n".format(" Папка результата открыта." if opened_folder else ""))
