"""Публичный facade заполнителя дневников.

Старый импортный контракт сохранён, а реализация разложена по parser/date/table/
writer/batch-модулям.
"""

from __future__ import annotations

from diary_batch import *
from diary_constants import *
from diary_dates import *
from diary_gender import *
from diary_models import *
from diary_paths import *
from diary_table import *
from diary_text_parser import *
from diary_writer import *
