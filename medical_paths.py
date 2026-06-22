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

    data = base64.b64decode(raw.encode("ascii") if isinstance(raw, str) else raw, validate=True)
    cache_dir = Path(tempfile.gettempdir()) / "medical_diary_autofill_templates"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / filename
    # Never trust an already-present temp file blindly: a previous crashed run
    # can leave a truncated DOCX in %TEMP%, and PyInstaller onefile runs reuse
    # this folder between launches. Validate the expected size and replace
    # atomically when needed.
    if not out.exists() or out.stat().st_size != len(data):
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(out)
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
