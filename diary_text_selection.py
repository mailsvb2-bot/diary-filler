from __future__ import annotations

import re
import zipfile
from pathlib import Path


SUPPORTED_DIARY_TEXT_SUFFIXES = {".doc", ".docx", ".docm"}


def _is_supported_word_file(path: str | Path) -> bool:
    try:
        p = Path(path)
        if not p.is_file() or p.name.startswith("~$"):
            return False
        if p.suffix.lower() in SUPPORTED_DIARY_TEXT_SUFFIXES:
            return True
        if p.suffix:
            return False
        with zipfile.ZipFile(p) as zf:
            names = set(zf.namelist())
        return "[Content_Types].xml" in names and "word/document.xml" in names
    except Exception:
        return False


def _is_docx_file(path: str | Path) -> bool:
    """Compatibility alias: all supported Word diagnosis-text files."""
    return _is_supported_word_file(path)


# ICD codes are metadata for medical documents. They are deliberately excluded
# from diary-text filename matching. The real folder contains names such as
# «дневники на шизофреника.doc» and «дневники на органичку.docx».
_ICD_CODE_RE = re.compile(
    r"(?<![A-ZА-Я0-9])[FФ]?\s*\d{1,3}\s*(?:[.,]\s*\d+)?(?![A-ZА-Я0-9])",
    re.IGNORECASE,
)
_COMMON_DIARY_NAME_WORDS = {
    "дневник", "дневники", "дневников", "дневниковые", "запись", "записи",
    "вэ", "ве", "веи", "текст", "тексты", "текстов", "даты", "датами",
    "с", "со", "на", "для",
    "шаблон", "шаблоны", "пациент", "пациента", "больной", "больного",
}
_STOP_DIARY_NAME_WORDS = {
    "и", "с", "со", "на", "по", "под", "при", "для", "из", "в", "во",
    "без", "к", "г", "год", "лет", "расстройство", "расстройства",
    "синдром", "синдромом", "состояние", "болезнь", "болезни",
}

# Verbal families bridge normal clinical wording and informal physician file
# names. No number/code can create any of these keys.
_FAMILY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("schizophrenia", ("шизофрен",)),
    ("organic", ("органичес", "органич", "органик", "резидуал")),
    ("depression", ("депресс",)),
    ("oligophrenia", ("олигофрен", "умствен")),
    ("asthenia", ("астен",)),
    ("psychopathy", ("психопат",)),
    ("anxiety", ("тревож",)),
    ("panic", ("панич",)),
    ("bipolar", ("биполяр",)),
    ("mania", ("маниак", "мания")),
    ("dementia", ("деменц",)),
    ("autism", ("аутиз", "аутист")),
    ("alcohol", ("алкогол",)),
    ("epilepsy", ("эпилепт",)),
    ("neurosis", ("невроз",)),
    ("ptsd", ("посттравмат", "птср")),
    ("somatoform", ("соматоформ",)),
    ("obsessive", ("обсесс", "навязчив")),
    ("personality", ("личност",)),
    ("healthy", ("здоров", "норма")),
    ("observation", ("обследован", "наблюден")),
)

# Mutually exclusive verbal schizophrenia subtypes. A generic filename such as
# «на шизофреника» intentionally has no subtype and may match; a specifically
# wrong subtype must never be selected automatically.
_SCHIZOPHRENIA_SUBTYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("paranoid", ("параноид",)),
    ("catatonic", ("кататон",)),
    ("hebephrenic", ("гебефрен",)),
    ("simple", ("простая форма", "простую форму")),
)


def _stem_russian_word(word: str) -> str:
    word = re.sub(r"[^a-zа-я]+", "", word.lower().replace("ё", "е"))
    if len(word) <= 4:
        return word
    for suffix in (
        "иями", "ями", "ами", "остью", "ости", "ость", "ение", "ения",
        "ении", "скими", "ского", "скому", "ский", "ская", "ское", "ские",
        "ыми", "ими", "ной", "ная", "ные", "ный", "ным", "ных", "ого",
        "его", "ему", "ая", "яя", "ое", "ее", "ия", "ий", "ый", "ые",
        "ой", "ей", "ам", "ям", "ах", "ях", "ов", "ев", "ом", "ем",
        "ою", "ею", "а", "я", "ы", "и", "у", "ю", "е", "о",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def normalize_diary_diagnosis_name(value: str) -> str:
    """Return only verbal content used for diary-text filename matching.

    ``F06.8 Органическое расстройство личности`` becomes
    ``органическое расстройство личности``. Every ICD code and every standalone
    number is discarded on purpose. Numeric 01–31 templates belong to a separate
    source type and can never help this matcher.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        p = Path(text)
        if p.suffix.lower() in SUPPORTED_DIARY_TEXT_SUFFIXES:
            text = p.stem
    except Exception:
        pass
    text = text.replace("ё", "е").lower()
    text = _ICD_CODE_RE.sub(" ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)*\b", " ", text)
    text = re.sub(
        r"\b(?:диагноз|основной\s+диагноз|заключение|дневниковые\s+записи)\b",
        " ", text, flags=re.IGNORECASE,
    )
    text = re.sub(r"[№#]", " ", text)
    text = re.sub(r"[()\[\]{}]", " ", text)
    text = re.sub(r"[.,;:!?'\"/\\|_+*=<>~`]+", " ", text)
    text = re.sub(r"[-–—]+", " ", text)
    words = [word for word in re.sub(r"\s+", " ", text).strip().split() if word]
    words = [word for word in words if word not in _COMMON_DIARY_NAME_WORDS]
    return " ".join(words).strip()


def _significant_words(value: str) -> list[str]:
    result: list[str] = []
    for word in normalize_diary_diagnosis_name(value).split():
        if len(word) < 3 or word in _COMMON_DIARY_NAME_WORDS or word in _STOP_DIARY_NAME_WORDS:
            continue
        if word not in result:
            result.append(word)
    return result


def _family_key_for_word(word: str) -> str:
    normalized = _stem_russian_word(word)
    raw = word.lower().replace("ё", "е")
    probe = f"{raw} {normalized}"
    for family, needles in _FAMILY_PATTERNS:
        if any(needle in probe for needle in needles):
            return family
    return ""


def _semantic_keys(value: str) -> set[str]:
    keys: set[str] = set()
    for word in _significant_words(value):
        stem = _stem_russian_word(word)
        if stem:
            keys.add(stem)
        family = _family_key_for_word(word)
        if family:
            keys.add(family)
    return keys


def _common_prefix_length(left: str, right: str) -> int:
    size = 0
    for a, b in zip(left, right):
        if a != b:
            break
        size += 1
    return size


def _words_equivalent(left: str, right: str) -> bool:
    if left == right:
        return True
    left_stem = _stem_russian_word(left)
    right_stem = _stem_russian_word(right)
    if left_stem == right_stem:
        return True
    if min(len(left_stem), len(right_stem)) >= 5 and (
        left_stem.startswith(right_stem) or right_stem.startswith(left_stem)
    ):
        return True
    if min(len(left_stem), len(right_stem)) >= 7 and _common_prefix_length(left_stem, right_stem) >= 6:
        return True
    left_family = _family_key_for_word(left)
    right_family = _family_key_for_word(right)
    return bool(left_family and left_family == right_family)


def _verbal_match_stats(diagnosis: str, filename: str) -> tuple[int, int, int, int]:
    diag_words = _significant_words(diagnosis)
    name_words = _significant_words(filename)
    if not diag_words or not name_words:
        return 0, len(diag_words), len(name_words), 0
    used: set[int] = set()
    matched = 0
    strongest = 0
    for diag_word in diag_words:
        best_index = -1
        best_strength = 0
        for index, name_word in enumerate(name_words):
            if index in used or not _words_equivalent(diag_word, name_word):
                continue
            family_match = bool(
                _family_key_for_word(diag_word)
                and _family_key_for_word(diag_word) == _family_key_for_word(name_word)
            )
            strength = max(
                len(_stem_russian_word(diag_word)),
                len(_stem_russian_word(name_word)),
                8 if family_match else 0,
            )
            if strength > best_strength:
                best_strength = strength
                best_index = index
        if best_index >= 0:
            used.add(best_index)
            matched += 1
            strongest = max(strongest, best_strength)
    return matched, len(diag_words), len(name_words), strongest


def _depression_severity(value: str) -> str:
    norm = normalize_diary_diagnosis_name(value)
    stems = {_stem_russian_word(word) for word in norm.split()}
    if any(stem.startswith("легк") for stem in stems):
        return "mild"
    if any(stem.startswith("умерен") for stem in stems):
        return "moderate"
    if any(stem.startswith("тяжел") for stem in stems):
        return "severe"
    return ""


def _contradictory_depression_severity(diagnosis: str, filename: str) -> bool:
    diag_keys = _semantic_keys(diagnosis)
    name_keys = _semantic_keys(filename)
    if "depression" not in diag_keys or "depression" not in name_keys:
        return False
    diag_severity = _depression_severity(diagnosis)
    name_severity = _depression_severity(filename)
    return bool(diag_severity and name_severity and diag_severity != name_severity)


def _schizophrenia_subtype(value: str) -> str:
    norm = normalize_diary_diagnosis_name(value)
    for subtype, needles in _SCHIZOPHRENIA_SUBTYPES:
        if any(needle in norm for needle in needles):
            return subtype
    return ""


def _contradictory_schizophrenia_subtype(diagnosis: str, filename: str) -> bool:
    if "schizophrenia" not in _semantic_keys(diagnosis) or "schizophrenia" not in _semantic_keys(filename):
        return False
    diag_subtype = _schizophrenia_subtype(diagnosis)
    name_subtype = _schizophrenia_subtype(filename)
    return bool(diag_subtype and name_subtype and diag_subtype != name_subtype)


def _direct_diagnosis_name_rank(diagnosis: str, filename: str) -> int:
    diag = normalize_diary_diagnosis_name(diagnosis)
    name = normalize_diary_diagnosis_name(filename)
    if not diag or not name:
        return 0
    if diag == name:
        return 2
    if diag in name or name in diag:
        return 1
    return 0


def diary_diagnosis_match_score(diagnosis: str, filename: str) -> int:
    """Score a WORD-ONLY relation between visible diagnosis and filename."""
    diag = normalize_diary_diagnosis_name(diagnosis)
    name = normalize_diary_diagnosis_name(filename)
    if not diag or not name:
        return 0
    if _contradictory_depression_severity(diagnosis, filename):
        return 0
    if _contradictory_schizophrenia_subtype(diagnosis, filename):
        return 0
    if diag == name:
        return 300
    if diag in name or name in diag:
        return 250

    matched, diag_count, name_count, strongest = _verbal_match_stats(diagnosis, filename)
    if matched <= 0 or strongest < 5:
        return 0
    coverage_diag = matched / max(1, diag_count)
    coverage_name = matched / max(1, name_count)
    score = 100 + matched * 35 + int(coverage_diag * 35) + int(coverage_name * 40)

    family_names = {item[0] for item in _FAMILY_PATTERNS}
    diag_families = {key for key in _semantic_keys(diagnosis) if key in family_names}
    name_families = {key for key in _semantic_keys(filename) if key in family_names}
    if diag_families & name_families:
        score += 30
    score -= max(0, name_count - matched) * 6
    return max(0, score)


def _safe_verbal_lexical_match(diagnosis: str, filename: str) -> bool:
    """One strong verbal/family hit is enough unless wording contradicts it."""
    matched, _diag_count, _name_count, strongest = _verbal_match_stats(diagnosis, filename)
    return bool(
        matched >= 1
        and strongest >= 5
        and not _contradictory_depression_severity(diagnosis, filename)
        and not _contradictory_schizophrenia_subtype(diagnosis, filename)
    )


def _safe_legacy_diagnosis_fallback(diagnosis: str, filename: str, score: int) -> bool:
    """Fail-closed verbal fallback for existing informal physician filenames."""
    if score <= 0:
        return False
    family_names = {item[0] for item in _FAMILY_PATTERNS}
    diag_families = {key for key in _semantic_keys(diagnosis) if key in family_names}
    name_families = {key for key in _semantic_keys(filename) if key in family_names}
    if diag_families and name_families and not (diag_families & name_families):
        return False
    # A filename may be generic («органичка», «шизофреника»), but it may not
    # introduce a different diagnostic family absent from the visible diagnosis.
    if diag_families and (name_families - diag_families):
        return False
    if _contradictory_schizophrenia_subtype(diagnosis, filename):
        return False
    return _safe_verbal_lexical_match(diagnosis, filename)


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
            if not _is_supported_word_file(child):
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
    """Find a Word diary text by WORDS from the visible diagnosis only."""
    diagnosis_norm = normalize_diary_diagnosis_name(diagnosis)
    if not diagnosis_norm:
        return None

    candidates: list[tuple[int, int, int, int, str, Path]] = []
    for path in iter_diary_text_docx_files(folder):
        name_norm = normalize_diary_diagnosis_name(path.stem)
        if not name_norm:
            continue
        score = diary_diagnosis_match_score(diagnosis, path.stem)
        if score <= 0:
            continue
        direct_rank = _direct_diagnosis_name_rank(diagnosis, path.stem)
        matched, _diag_count, name_count, _strongest = _verbal_match_stats(diagnosis, path.stem)
        if direct_rank == 0 and not _safe_legacy_diagnosis_fallback(diagnosis, path.stem, score):
            continue
        extra_words = max(0, name_count - matched)
        length_gap = abs(len(name_norm) - len(diagnosis_norm))
        candidates.append((-score, -direct_rank, extra_words, length_gap, path.name.lower(), path))

    if not candidates:
        return None
    return sorted(candidates)[0][5]


def folder_has_diary_text_candidates(folder: str | Path) -> bool:
    return bool(iter_diary_text_docx_files(folder, max_depth=1))
