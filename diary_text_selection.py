from __future__ import annotations

import re
import zipfile
from pathlib import Path


def _is_docx_file(path: str | Path) -> bool:
    try:
        p = Path(path)
        if not p.is_file() or p.name.startswith("~$"):
            return False
        if p.suffix.lower() in {".docx", ".docm"}:
            return True
        if p.suffix:
            return False
        with zipfile.ZipFile(p) as zf:
            names = set(zf.namelist())
        return "[Content_Types].xml" in names and "word/document.xml" in names
    except Exception:
        return False


_ICD_PREFIX_RE = re.compile(r"^\s*[A-ZА-Я]\s*\d{1,3}\s*(?:[.,]\s*\d+)?\s*[-—–.:;)]*\s*", re.IGNORECASE)
_COMMON_DIARY_NAME_WORDS = {
    "дневник",
    "дневники",
    "дневников",
    "дневниковые",
    "вэ",
    "ве",
    "веи",
    "текст",
    "тексты",
    "текстов",
    "даты",
    "датами",
    "с",
    "со",
    "на",
    "шаблон",
    "шаблоны",
}
_STOP_DIARY_NAME_WORDS = {
    "и",
    "с",
    "со",
    "на",
    "по",
    "под",
    "при",
    "для",
    "из",
    "в",
    "во",
    "без",
    "г",
    "год",
    "лет",
    "расстройство",
    "расстройства",
    "синдром",
    "синдромом",
    "состояние",
    "болезнь",
    "болезни",
    "легкое",
    "легкая",
    "легкой",
    "умеренное",
    "умеренная",
    "смешанное",
    "органическое",
    "депрессивное",
}
_SPECIFIC_DIARY_KEYS = {"asthenia", "psychopathy", "observation"}


def _stem_russian_word(word: str) -> str:
    word = re.sub(r"[^a-zа-я0-9]+", "", word.lower().replace("ё", "е"))
    if len(word) <= 4:
        return word
    # Небольшой безопасный stemmer для выравнивания русских окончаний:
    # «олигофрены» и «олигофрения» должны стать близкими ключами.
    for suffix in (
        "иями",
        "ями",
        "ами",
        "ости",
        "ость",
        "ение",
        "ения",
        "ении",
        "остью",
        "ыми",
        "ими",
        "ной",
        "ная",
        "ные",
        "ный",
        "ным",
        "ных",
        "ого",
        "его",
        "ему",
        "ая",
        "яя",
        "ое",
        "ее",
        "ия",
        "ий",
        "ый",
        "ые",
        "ой",
        "ей",
        "ам",
        "ям",
        "ах",
        "ях",
        "ов",
        "ев",
        "ом",
        "ем",
        "ою",
        "ею",
        "а",
        "я",
        "ы",
        "и",
        "у",
        "ю",
        "е",
        "о",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def normalize_diary_diagnosis_name(value: str) -> str:
    """Normalize a diagnosis/file name for matching diary text DOCX files.

    Реальные файлы врача часто называются не ровно диагнозом, а так:
    ``дневники ВЭ легкая депрессия с датами.docx``. Поэтому здесь убираем
    технические слова и оставляем смысловую часть названия.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        p = Path(text)
        # Не считаем формальный диагноз вида "F70.0 ..." именем файла только
        # из-за точки в коде МКБ. Stem берём только для реальных DOCX/DOCM имён.
        if p.suffix.lower() in {".docx", ".docm"}:
            text = p.stem
    except Exception:
        pass
    text = text.replace("ё", "е").lower()
    text = _ICD_PREFIX_RE.sub("", text)
    text = re.sub(r"\b(?:диагноз|основной диагноз|заключение|дневниковые записи)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[№#]", " ", text)
    text = re.sub(r"[()\[\]{}]", " ", text)
    text = re.sub(r"[.,;:!?'\"/\\|_+*=<>~`]+", " ", text)
    text = re.sub(r"[-–—]+", " ", text)
    words = [w for w in re.sub(r"\s+", " ", text).strip().split() if w]
    words = [w for w in words if w not in _COMMON_DIARY_NAME_WORDS]
    return " ".join(words).strip()


def _significant_words(value: str) -> set[str]:
    return {
        word
        for word in normalize_diary_diagnosis_name(value).split()
        if len(word) >= 3 and word not in _COMMON_DIARY_NAME_WORDS and word not in _STOP_DIARY_NAME_WORDS
    }


def _semantic_keys(value: str) -> set[str]:
    raw = str(value or "")
    norm = normalize_diary_diagnosis_name(raw)
    text = " " + norm + " "
    keys: set[str] = set()
    stems = {_stem_russian_word(w) for w in norm.split() if len(w) >= 3}
    keys.update(stem for stem in stems if stem and stem not in _STOP_DIARY_NAME_WORDS)

    # Мосты между формальными диагнозами и реальными именами файлов из папки.
    if re.search(r"\bF\s*7[0-9]", raw, re.IGNORECASE) or "умствен" in text or "олигофрен" in text:
        keys.add("oligophrenia")
    if "астен" in text:
        keys.add("asthenia")
    if "психопат" in text or ("нарушен" in text and "поведен" in text):
        keys.add("psychopathy")
    if "депресс" in text or "депрессив" in text:
        keys.add("depression")
    if "органик" in text or "органичес" in text or "резидуаль" in text:
        keys.add("organic")
    if "здоров" in text or "норма" in text or "психически здоров" in text:
        keys.add("healthy")
    if "обследован" in text:
        keys.add("observation")
    return keys


def diary_diagnosis_match_score(diagnosis: str, filename: str) -> int:
    diag = normalize_diary_diagnosis_name(diagnosis)
    name = normalize_diary_diagnosis_name(filename)
    if not diag or not name:
        return 0
    if diag == name:
        return 120
    if diag in name or name in diag:
        return 104

    diag_keys = _semantic_keys(diagnosis)
    name_keys = _semantic_keys(name)
    semantic_overlap = diag_keys & name_keys
    score = 0
    if semantic_overlap:
        score = 78 + min(18, len(semantic_overlap) * 6)
        for key in ("asthenia", "psychopathy", "observation", "depression", "organic", "healthy"):
            if key in diag_keys and key in name_keys:
                score += 10
            elif key in name_keys and key not in diag_keys:
                score -= 8

    diag_words = _significant_words(diag)
    name_words = _significant_words(name)
    diag_stems = {_stem_russian_word(w) for w in diag_words}
    name_stems = {_stem_russian_word(w) for w in name_words}
    overlap = len((diag_words & name_words) | (diag_stems & name_stems))
    if diag_words and name_words and overlap:
        coverage_diag = overlap / max(1, len(diag_words))
        coverage_name = overlap / max(1, len(name_words))
        coverage = min(coverage_diag, coverage_name)
        lexical = 65 + int(coverage * 18) if (overlap >= 2 or coverage >= 0.5) else 0
        score = max(score, lexical)

    return max(0, score)


def iter_diary_text_docx_files(folder: str | Path, *, max_depth: int = 2) -> list[Path]:
    try:
        root = Path(folder).expanduser()
        if not root.exists() or not root.is_dir():
            return []
    except Exception:
        return []
    result: list[Path] = []
    seen: set[str] = set()

    def walk(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = list(current.iterdir())
        except Exception:
            return
        for child in children:
            name_low = child.name.strip().lower()
            if name_low.startswith(".") or name_low in {"__pycache__", ".venv", "venv", "build", "dist"}:
                continue
            if child.is_dir():
                walk(child, depth + 1)
                continue
            if not _is_docx_file(child):
                continue
            try:
                key = str(child.resolve())
            except Exception:
                key = str(child)
            if key in seen:
                continue
            seen.add(key)
            result.append(child)

    walk(root, 0)
    return sorted(result, key=lambda p: str(p).lower())


def find_diary_text_file_for_diagnosis(folder: str | Path, diagnosis: str) -> Path | None:
    """Find the best diary-text DOCX whose filename matches the parsed diagnosis."""
    diagnosis_norm = normalize_diary_diagnosis_name(diagnosis)
    if not diagnosis_norm:
        return None
    diagnosis_keys = _semantic_keys(diagnosis)
    candidates: list[tuple[int, int, int, str, Path]] = []
    for path in iter_diary_text_docx_files(folder):
        score = diary_diagnosis_match_score(diagnosis, path.stem)
        if score <= 0:
            continue
        name_norm = normalize_diary_diagnosis_name(path.stem)
        name_keys = _semantic_keys(name_norm)
        length_gap = abs(len(name_norm) - len(diagnosis_norm))
        extra_specificity_penalty = len((name_keys - diagnosis_keys) & _SPECIFIC_DIARY_KEYS) * 20
        candidates.append((-score, extra_specificity_penalty, length_gap, path.name.lower(), path))
    if not candidates:
        return None
    return sorted(candidates)[0][4]


def folder_has_diary_text_candidates(folder: str | Path) -> bool:
    return bool(iter_diary_text_docx_files(folder, max_depth=1))
