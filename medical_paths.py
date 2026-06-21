"""Разделённый слой медицинских документов.

Файл создан при архитектурной нарезке бывшего medical_documents.py.
"""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path
from typing import Optional

from medical_constants import TEMPLATE_FILES

_EMBEDDED_TEMPLATE_CACHE: dict[str, Path | None] = {}
_BUNDLED_TEMPLATE_CACHE: dict[str, Path] = {}


def app_dir() -> Path:
    """Папка программы с учётом PyInstaller onefile."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def template_dir() -> Path:
    return app_dir() / "templates"


def embedded_template_path(filename: str) -> Optional[Path]:
    """Вернуть временный путь к DOCX-шаблону из embedded base64 storage.

    Base64 decoding is cached because one creation run may ask for the same
    bundled template several times through validation and rendering paths.
    """
    if filename in _EMBEDDED_TEMPLATE_CACHE:
        return _EMBEDDED_TEMPLATE_CACHE[filename]
    try:
        from embedded_templates import TEMPLATE_B64  # type: ignore
    except Exception:
        _EMBEDDED_TEMPLATE_CACHE[filename] = None
        return None
    raw = TEMPLATE_B64.get(filename)
    if not raw:
        _EMBEDDED_TEMPLATE_CACHE[filename] = None
        return None

    cache_dir = Path(tempfile.gettempdir()) / "medical_diary_autofill_templates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / filename
    if out.exists() and out.stat().st_size > 0:
        _EMBEDDED_TEMPLATE_CACHE[filename] = out
        return out
    data = base64.b64decode(raw.encode("ascii") if isinstance(raw, str) else raw)
    if not out.exists() or out.stat().st_size != len(data):
        out.write_bytes(data)
    _EMBEDDED_TEMPLATE_CACHE[filename] = out
    return out


def bundled_template_path(kind: str) -> Path:
    cached = _BUNDLED_TEMPLATE_CACHE.get(kind)
    if cached is not None and cached.exists():
        return cached
    try:
        filename = TEMPLATE_FILES[kind]
    except KeyError as exc:
        raise KeyError(f"Неизвестный тип документа: {kind}") from exc
    physical = template_dir() / filename
    if physical.exists():
        _BUNDLED_TEMPLATE_CACHE[kind] = physical
        return physical
    embedded = embedded_template_path(filename)
    result = embedded or physical
    if result.exists():
        _BUNDLED_TEMPLATE_CACHE[kind] = result
    return result
