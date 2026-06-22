from __future__ import annotations

import re

from medical_text_utils import DIAGNOSIS_STOP_MARKERS, clean_value, looks_like_label

def sanitize_diagnosis(value: str) -> str:
    """Вернуть только медицинскую формулировку диагноза без соседних блоков.

    В реальных первичных DOCX диагноз встречается в разных стилях:
    "Диагноз: F...", "был выставлен диагноз: F...", "установлен диагноз: F...".
    Раньше при однострочной записи парсер мог захватить следующий раздел
    (например, "Жалобы"/"Лечение"/"Врач") и подставить его в строку диагноза.
    Здесь диагноз жёстко очищается перед показом в UI и перед рендерингом.
    """
    value = clean_value(value)
    if not value:
        return ""

    # Если в значение попала вся фраза "На основании... установлен диагноз:",
    # оставляем только хвост после служебной формулы. Не режем диагнозы, где
    # слово "диагноз" является частью пользовательского текста после кода F.
    value = re.sub(
        r"^\s*(?:на\s+основании\s+данных.*?\s+)?(?:был\s+выставлен|выставлен|установлен)?\s*диагноз\s*[:.-]?\s*",
        "",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    value = clean_value(value)

    # Обрезаем всё, что начинается как следующий раздел документа. Поддерживаем
    # и перенос строки, и компактную запись в одну строку: "F20... Жалобы: ...".
    best = len(value)
    for marker in DIAGNOSIS_STOP_MARKERS:
        marker_pattern = re.escape(marker).replace(r"\ ", r"\s+")
        patterns = (
            rf"\n\s*{marker_pattern}\s*(?:[:№N#.-]|$)",
            rf"(?<![А-Яа-яA-Za-z0-9]){marker_pattern}(?![А-Яа-яA-Za-z0-9])\s*[:№N#.-]",
        )
        for pattern in patterns:
            m = re.search(pattern, value, flags=re.IGNORECASE)
            if m and 0 < m.start() < best:
                best = m.start()
    value = clean_value(value[:best])

    # Частые шаблонные остатки. "F" в пустом шаблоне — не диагноз.
    if re.fullmatch(r"F\s*\.?", value, flags=re.IGNORECASE):
        return ""
    if looks_like_label(value):
        return ""
    return value
