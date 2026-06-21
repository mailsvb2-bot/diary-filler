from __future__ import annotations

import re
import zipfile
from pathlib import Path

from app_config import *


class DiaryTemplateDiscoveryMixin:
    @staticmethod
    def _is_docx_like_template_file(path: str | Path) -> bool:
        """True для DOCX/DOCM-шаблона, включая файл без расширения.

        На Windows расширения часто скрыты, а иногда файл реально может
        называться просто ``01``. Для автопоиска шаблонов это допустимо:
        если расширения нет, проверяем ZIP-содержимое Word-документа.
        """
        try:
            p = Path(path)
            if not p.is_file():
                return False
            if p.name.startswith("~$"):
                return False
            suffix = p.suffix.lower()
            if suffix in {".docx", ".docm"}:
                return True
            if suffix:
                return False
            # Файл без расширения: принимаем только если это настоящий DOCX zip.
            try:
                with zipfile.ZipFile(p) as zf:
                    names = set(zf.namelist())
                return "[Content_Types].xml" in names and "word/document.xml" in names
            except Exception:
                return False
        except Exception:
            return False

    @staticmethod
    def _template_filename_day(path: str | Path) -> int | None:
        """Вернуть номер дневникового шаблона из имени файла.

        Приоритет — точные имена 1/01 … 31. Допускаются копии и служебные
        слова, но год/даты в имени не должны ошибочно превращаться в номер
        шаблона.
        """
        try:
            p = Path(path)
            if not p.is_file():
                return None
            if not DiaryTemplateDiscoveryMixin._is_docx_like_template_file(p):
                return None
            # Path.stem для файла без расширения вернёт всё имя, т.е. "01".
            stem = p.stem.strip().lower().replace("ё", "е")
            stem = re.sub(r"[№#]", " ", stem)
            stem = re.sub(r"[._–—-]+", " ", stem)
            stem = re.sub(r"\s+", " ", stem).strip()

            # 1, 01, 1 (2), 01(2).
            m = re.fullmatch(r"0?([1-9]|[12]\d|3[01])(?:\s*\(\d+\))?", stem)
            if m:
                return int(m.group(1))

            # 15 дневник, дневник 15, шаблон 15.
            m = re.match(r"^0?([1-9]|[12]\d|3[01])(?:\s|$)", stem)
            if m:
                return int(m.group(1))
            m = re.search(r"(?:^|\s)(?:шаблон|дневник|таблица|template)\s+0?([1-9]|[12]\d|3[01])(?:\s|$)", stem)
            if m:
                return int(m.group(1))

            # Если в имени ровно одно число 1–31, это можно считать номером.
            numbers = re.findall(r"(?<!\d)0?([1-9]|[12]\d|3[01])(?!\d)", stem)
            if len(numbers) == 1:
                # Не принимаем очевидные даты/годы в названии.
                all_numbers = re.findall(r"\d+", stem)
                if len(all_numbers) == 1:
                    return int(numbers[0])
            return None
        except Exception:
            return None

    def _is_numbered_diary_template_file(self, path: str | Path, day: int | None = None) -> bool:
        """Проверить файл шаблона 01.docx–31.docx без изменения diary_filler.py."""
        number = self._template_filename_day(path)
        if number is None:
            return False
        return day is None or number == int(day)

    def _iter_diary_template_docx_files(self, folder: str | Path) -> list[Path]:
        """Собрать DOCX-шаблоны из папки «шаблоны дневников».

        Практический Windows-сценарий: врач выбирает видимую папку
        «шаблоны дневников», но внутри могут быть подпапки, копии, архивные
        наборы или файлы с верхним/нижним регистром расширения. Поэтому ищем
        не только в корне, а рекурсивно, но с ограничением глубины, чтобы не
        шерстить весь компьютер. Сам diary_filler.py не меняется.
        """
        try:
            root = Path(folder).expanduser()
            if not root.exists() or not root.is_dir():
                return []
            try:
                cache_key = (str(root.resolve()), root.stat().st_mtime_ns)
            except Exception:
                cache_key = (str(root), 0)
            cache = getattr(self, "_diary_template_files_cache", None)
            if isinstance(cache, dict) and cache_key in cache:
                return list(cache[cache_key])

            files: list[Path] = []
            seen: set[str] = set()

            def add_file(path: Path) -> None:
                try:
                    if not path.is_file():
                        return
                    if not self._is_docx_like_template_file(path):
                        return
                    # Игнорируем временные файлы Word вида ~$15.docx.
                    if path.name.startswith("~$"):
                        return
                    key = str(path.resolve())
                except Exception:
                    key = str(path)
                if key not in seen:
                    seen.add(key)
                    files.append(path)

            def walk(current: Path, depth: int) -> None:
                if depth > 4:
                    return
                try:
                    children = list(current.iterdir())
                except Exception:
                    return
                for child in children:
                    name_low = child.name.strip().lower()
                    if name_low.startswith(".") or name_low in {"__pycache__", ".venv", "venv", "build", "dist"}:
                        continue
                    if child.is_file():
                        add_file(child)
                    elif child.is_dir():
                        walk(child, depth + 1)

            walk(root, 0)
            result = sorted(files, key=lambda item: str(item).lower())
            if isinstance(cache, dict):
                cache[cache_key] = list(result)
                if len(cache) > 24:
                    for old_key in list(cache)[:-24]:
                        cache.pop(old_key, None)
            return result
        except Exception:
            return []

    def _template_content_first_day(self, path: str | Path) -> int | None:
        """Попытаться понять номер шаблона по содержимому DOCX.

        Это запасной контур для случаев, когда файл в папке назван
        нестандартно, но внутри таблицы есть типовая первая строка вида
        «2 15 ...». Он нужен только для выбора файла из папки; заполнение
        дневников остаётся старым.
        """
        try:
            p = Path(path)
            stat = p.stat()
            cache_key = (str(p.resolve()), stat.st_mtime_ns, stat.st_size)
        except Exception:
            p = Path(path)
            cache_key = (str(p), 0, -1)
        cache = getattr(self, "_diary_template_day_cache", None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]
        try:
            from medical_docx_reader import extract_docx_text
            text = extract_docx_text(str(path))
        except Exception:
            if isinstance(cache, dict):
                cache[cache_key] = None
            return None
        if not text:
            return None
        flat = re.sub(r"\s+", " ", text).strip()[:1200]
        # В типовом шаблоне после заголовков первая строка таблицы начинается
        # с «2 <число>», где <число> — день месяца шаблона.
        for pattern in (
            r"(?:Дневник наблюдения|Месяц/\s*Год|День\s*госпит)[^0-9]{0,120}2\s+0?([1-9]|[12]\d|3[01])\b",
            r"\b2\s+0?([1-9]|[12]\d|3[01])\b",
        ):
            match = re.search(pattern, flat, flags=re.IGNORECASE)
            if match:
                try:
                    result = int(match.group(1))
                    if isinstance(cache, dict):
                        cache[cache_key] = result
                    return result
                except Exception:
                    if isinstance(cache, dict):
                        cache[cache_key] = None
                    return None
        if isinstance(cache, dict):
            cache[cache_key] = None
            if len(cache) > 128:
                for old_key in list(cache)[:-128]:
                    cache.pop(old_key, None)
        return None

    def _folder_contains_numbered_diary_templates(self, folder: str | Path) -> bool:
        """True, если папка реально содержит шаблоны дневников 01–31.

        Проверяем не только имя файла, но и содержимое DOCX. Это закрывает
        случаи, когда шаблон назван нестандартно, но первая строка таблицы
        внутри документа показывает номер дня месяца.
        """
        try:
            root = Path(folder).expanduser()
            try:
                cache_key = (str(root.resolve()), root.stat().st_mtime_ns)
            except Exception:
                cache_key = (str(root), 0)
            cache = getattr(self, "_diary_template_folder_contains_cache", None)
            if isinstance(cache, dict) and cache_key in cache:
                return bool(cache[cache_key])
            result = False
            for path in self._iter_diary_template_docx_files(root):
                if self._is_numbered_diary_template_file(path):
                    result = True
                    break
                if self._template_content_first_day(path) is not None:
                    result = True
                    break
            if isinstance(cache, dict):
                cache[cache_key] = result
                if len(cache) > 48:
                    for old_key in list(cache)[:-48]:
                        cache.pop(old_key, None)
            return result
        except Exception:
            return False

    @staticmethod
    def _is_named_diary_templates_folder(folder: str | Path) -> bool:
        """True only for the canonical auto folder: «шаблоны дневников»."""
        try:
            name = Path(folder).name.strip().lower().replace("ё", "е")
        except Exception:
            name = str(folder).strip().lower().replace("ё", "е")
        name = re.sub(r"[\s_\-–—]+", " ", name).strip()
        return name == "шаблоны дневников"

    def _named_diary_template_dirs_near(self, root: str | Path) -> list[Path]:
        """Find nearby folders named exactly «шаблоны дневников».

        Автоматический режим больше не шерстит произвольные папки с DOCX,
        чтобы не подхватить старый/чужой шаблон. Он ищет именно папку с
        пользовательским контрактом: «шаблоны дневников».
        """
        try:
            base = Path(root).expanduser()
            if base.is_file():
                base = base.parent
        except Exception:
            return []

        starts: list[Path] = []
        for candidate in (base, base.parent, Path(__file__).resolve().parent, Path.cwd()):
            try:
                if candidate.exists() and candidate.is_dir():
                    starts.append(candidate)
            except Exception:
                pass

        result: list[Path] = []
        seen: set[str] = set()
        for start in starts:
            candidates = [start]
            # Exact spelling first. Then a case-insensitive pass through direct children.
            candidates.append(start / "шаблоны дневников")
            candidates.append(start / "Шаблоны дневников")
            try:
                for child in list(start.iterdir())[:200]:
                    if child.is_dir() and self._is_named_diary_templates_folder(child):
                        candidates.append(child)
            except Exception:
                pass
            for candidate in candidates:
                try:
                    key = str(candidate.resolve())
                except Exception:
                    key = str(candidate)
                if key in seen:
                    continue
                seen.add(key)
                if self._is_named_diary_templates_folder(candidate) and self._folder_contains_numbered_diary_templates(candidate):
                    result.append(candidate)
        return result

    def _discover_numbered_diary_template_dirs_near(self, root: str | Path) -> list[Path]:
        """Быстро найти папку 01–31 рядом с первичным документом.

        Не сканируем весь компьютер: только папку первичного документа, её
        ближайшие подпапки и папку уровнем выше. Это даёт программе шанс
        понять структуру пользователя, но не делает запуск тяжёлым.
        """
        try:
            base = Path(root).expanduser()
            if base.is_file():
                base = base.parent
        except Exception:
            return []

        candidates: list[Path] = []
        for start in (base, base.parent):
            if not start.exists() or not start.is_dir():
                continue
            candidates.append(start)
            try:
                for child in list(start.iterdir())[:120]:
                    if child.is_dir():
                        candidates.append(child)
            except Exception:
                pass
        result: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                key = str(candidate.resolve())
            except Exception:
                key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if self._folder_contains_numbered_diary_templates(candidate):
                result.append(candidate)
        return result

    def _remember_numbered_diary_template_dir(self, folder: str | Path) -> None:
        self._remember_dialog_directory(DIR_NUMBERED_DIARY_TEMPLATES, str(folder), selected_is_dir=True)
        # Старое поле "Шаблоны дневников" продолжает жить как раньше: мы
        # просто запоминаем папку, из которой позже автоматически выберем
        # один конкретный DOCX-файл и передадим его в прежний fill_diary_batch.
        self._remember_dialog_directory(DIR_DIARY_TEMPLATES, str(folder), selected_is_dir=True)

    def _candidate_numbered_diary_template_dirs(self) -> list[Path]:
        """Candidate folders for automatic diary-template selection.

        Contract for auto mode: after reading the primary document/referral,
        the program looks for a nearby folder named exactly «шаблоны дневников»
        and then chooses the DOCX whose number matches the hospitalization date.

        A manually selected folder is still respected through self.diary_template_dir.
        """
        result: list[Path] = []
        seen: set[str] = set()

        def add_folder(candidate: str | Path, *, require_name: bool = True) -> None:
            if not candidate:
                return
            try:
                folder = Path(candidate).expanduser()
                if folder.is_file():
                    folder = folder.parent
                if require_name and not self._is_named_diary_templates_folder(folder):
                    return
                if not self._folder_contains_numbered_diary_templates(folder):
                    return
                key = str(folder.resolve())
            except Exception:
                return
            if key not in seen:
                seen.add(key)
                result.append(folder)

        # 1) Explicit/manual folder from the current session is allowed even if
        # the doctor picked a folder with another name.
        if getattr(self, "diary_template_dir", ""):
            add_folder(self.diary_template_dir, require_name=False)

        # 2) Saved folders are used only if they are the canonical named folder.
        for value in (
            self._get_saved_directory(DIR_NUMBERED_DIARY_TEMPLATES),
            self._get_saved_directory(DIR_DIARY_TEMPLATES),
        ):
            add_folder(value, require_name=True)

        # 3) Main auto-search: near the loaded primary document/referral and
        # near the output/app folders, look only for «шаблоны дневников».
        roots: list[str] = []
        if self.navigation_path_var.get().strip():
            roots.append(self.navigation_path_var.get().strip())
        if self.output_dir_var.get().strip():
            roots.append(self.output_dir_var.get().strip())
        roots.append(str(Path(__file__).resolve().parent))
        roots.append(str(Path.cwd()))
        for root in roots:
            for folder in self._named_diary_template_dirs_near(root):
                add_folder(folder, require_name=True)

        return result
