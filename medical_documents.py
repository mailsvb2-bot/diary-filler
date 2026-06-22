"""Публичный facade медицинского слоя.

Исторически весь domain/DOCX/render/service-код лежал в одном файле. Теперь
код разложен по специализированным модулям, а этот файл сохраняет старый
импортный контракт: `from medical_documents import MedicalDocumentService` и
другие публичные имена продолжают работать.
"""

from __future__ import annotations

from medical_constants import *
from medical_docx_editor import *
from medical_docx_reader import *
from medical_expert import *
from medical_formatting import *
from medical_gender import *
from medical_markers import *
from medical_models import *
from medical_parser import *
from medical_paths import *
from medical_preview import *
from medical_renderer import *
from medical_service import *
from medical_text_utils import *
