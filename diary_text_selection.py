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
        # Preserve legacy extensionless OOXML support.
        with zipfile.ZipFile(p) as zf:
            names = set(zf.namelist())
        return "[Content_Types].xml" in names and "word/document.xml" in names
    except Exception:
        return False


# Compatibility alias for older tests/imports. The function recognizes all
# supported Word diagnosis-text files, including legacy .doc.
def _is_docx_file(path: str | Path) -> bool:
    return _is_supported_word_file(path)


# ICD codes are metadata for the medical document. They are intentionally NOT
# part of diary-text filename matching. The doctor's real folders contain names
# such as «дневники на шизофреника.doc» and «дневники на органичку.docx».
_ICD_CODE_RE = re.compile(
    r"(?<![A-ZА-Я0-9])[FФ]?\s*\d{1,3}\s*(?:[.,]\s*\d+)?(?![A-ZА-Я0-9])",
    re.IGNORECASE,
)
_COMMON_DIARY_NAME_WORDS = {
    "дневник",
    "дневники",
    "дневников",
    "дневниковые",
    "запись",
    "записи",
    "вэ",
    "ве",
    "веи",
    "текст",
    "тексты",
    "текстов",
    "даты",
    "датами",
    "шаблон",
    "шаблоны",
    "пациент",
    "пациента",
    "больной",
    "больного",
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
    "к",
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
}

# These keys bridge normal medical wording and the informal names that are
# already present in the doctor's folder. Numbers/codes never create a key.
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


def _stem_russian_word(word: str) -> str:
    word = re.sub(r"[^a-zа-я]+", "", word.lower().replace("ё", "е"))
    if len(word) <= 4:
        return word
    # Small deterministic stemmer. It is deliberately conservative; informal
    # aliases are handled separately by _family_key_for_word.
    for suffix in (
        "иями",
        "ями",
        "ами",
        "остью",
        "ости",
        "ость",
        "ение",
        "ения",
        "ении",
        "скими",
        "ского",
        "скому",
        "ский",
        "ская",
        "ское",
        "ские",
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
        "ами",
        "ями",
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
    """Return only the verbal part used for diary-text filename matching.

    Examples:
    ``F06.8 Органическое расстройство личности`` ->
    ``органическое расстройство личности``.

    ``дневники на органичку 2022.docx`` -> ``органичку``.

    Every ICD code and every standalone number is discarded on purpose. The
    lookup is a words-only operation; date-template numbers belong to a separate
    input source and must never influence this matcher.
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
    # Remove F-codes and bare numeric fragments before tokenization. A plain
    # numeric diagnosis such as F20.0 therefore normalizes to an empty string.
    text = _ICD_CODE_RE.sub(" ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)*\b", " ", text)
    text = re.sub(
        r"\b(?:диагноз|основной\s+диагноз|заключение|дневниковые\s+записи)\b",
        " ",
        text,
        flags=re.IGNORECASE,
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
    # Covers common real-folder forms such as «органическое» / «органичку».
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
    """Score a WORD-ONLY relation between visible diagnosis and file name."""
    diag = normalize_diary_diagnosis_name(diagnosis)
    name = normalize_diary_diagnosis_name(filename)
    if not diag or not name:
        return 0
    if _contradictory_depression_severity(diagnosis, filename):
        return 0
    if diag == name:
        return 300
    if diag in name or name in diag:
        return 250

    matched, diag_count, name_count, strongest = _verbal_match_stats(diagnosis, filename)
    if matched <= 0 or strongest < 5:
        return 0

    # One distinctive verbal hit is intentionally sufficient. This is the real
    # folder contract: «Органическое ...» may map to «дневники на органичку».
    coverage_diag = matched / max(1, diag_count)
    coverage_name = matched / max(1, name_count)
    score = 100 + matched * 35 + int(coverage_diag * 35) + int(coverage_name * 40)

    diag_families = {key for key in _semantic_keys(diagnosis) if key in {item[0] for item in _FAMILY_PATTERNS}}
    name_families = {key for key in _semantic_keys(filename) if key in {item[0] for item in _FAMILY_PATTERNS}}
    if diag_families & name_families:
        score += 30
    # Prefer the most specific filename and avoid choosing a file carrying many
    # unrelated extra diagnostic words when a cleaner verbal match exists.
    score -= max(0, name_count - matched) * 6
    return max(0, score)


def _safe_verbal_lexical_match(diagnosis: str, filename: str) -> bool:
    """Compatibility helper: accept one strong word/family match, never a code."""
    matched, _diag_count, _name_count, strongest = _verbal_match_stats(diagnosis, filename)
    return matched >= 1 and strongest >= 5 and not _contradictory_depression_severity(diagnosis, filename)


def _safe_legacy_diagnosis_fallback(diagnosis: str, filename: str, score: int) -> bool:
    """Compatibility helper for old callers/tests using informal folder names."""
    if score <= 0:
        return False
    diag_families = {key for key in _semantic_keys(diagnosis) if key in {item[0] for item in _FAMILY_PATTERNS}}
    name_families = {key for key in _semantic_keys(filename) if key in {item[0] for item in _FAMILY_PATTERNS}}
    if diag_families and name_families and not (diag_families & name_families):
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
    """Find a diary-text Word file by WORDS from the visible diagnosis only.

    ICD codes, dates and other numbers are stripped before matching. The best
    verbal filename wins; informal forms such as «шизофреника» and «органичку»
    are supported. Numeric 01–31 diary-date templates are a different source and
    are never selected by this function.
    """
    diagnosis_norm = normalize_diary_diagnosis_name(diagnosis)
    if not diagnosis_norm:
        return None

    candidates: list[tuple[int, int, int, str, Path]] = []
    for path in iter_diary_text_docx_files(folder):
        name_norm = normalize_diary_diagnosis_name(path.stem)
        if not name_norm:
            continue
        score = diary_diagnosis_match_score(diagnosis, path.stem)
        if score <= 0:
            continue
        direct_rank = _direct_diagnosis_name_rank(diagnosis, path.stem)
        matched, _diag_count, name_count, _strongest = _verbal_match_stats(diagnosis, path.stem)
        if direct_rank == 0 and not _safe_verbal_lexical_match(diagnosis, path.stem):
            continue
        extra_words = max(0, name_count - matched)
        length_gap = abs(len(name_norm) - len(diagnosis_norm))
        candidates.append((-score, -direct_rank, extra_words, length_gap, path.name.lower(), path))

    if not candidates:
        return None
    return sorted(candidates)[0][5]


def folder_has_diary_text_candidates(folder: str | Path) -> bool:
    return bool(iter_diary_text_docx_files(folder, max_depth=1))
