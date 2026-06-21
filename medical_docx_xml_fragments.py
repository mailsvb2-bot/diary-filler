from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from medical_text_utils import normalize_text


def _docx_xml_text_fragments(path: str | Path) -> list[str]:
    """Return paragraph-like text fragments from DOCX XML, including text boxes.

    python-docx не всегда видит текст, лежащий в shape/textbox/header. Для
    даты заголовка это критично, поэтому читаем XML напрямую как запасной
    канал. Внутреннюю механику дневников это не затрагивает.
    """
    fragments: list[str] = []
    try:
        with zipfile.ZipFile(str(path)) as zf:
            names = [
                name for name in zf.namelist()
                if name.startswith("word/")
                and name.endswith(".xml")
                and (
                    name == "word/document.xml"
                    or name.startswith("word/header")
                    or name.startswith("word/footer")
                )
            ]
            # Сначала тело документа, затем колонтитулы.
            names.sort(key=lambda n: (0 if n == "word/document.xml" else 1, n))
            for name in names:
                try:
                    root = ET.fromstring(zf.read(name))
                except Exception:
                    continue
                for para in root.iter():
                    if not str(para.tag).endswith("}p"):
                        continue
                    parts: list[str] = []
                    for node in para.iter():
                        tag = str(node.tag)
                        if tag.endswith("}t") or tag.endswith("}instrText"):
                            if node.text:
                                parts.append(node.text)
                    value = normalize_text("".join(parts))
                    if value:
                        fragments.append(value)
    except Exception:
        return []
    return fragments
