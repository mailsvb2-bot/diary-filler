from __future__ import annotations

APP_TITLE = "Медицинский автозаполнитель"
APP_VERSION = "v1.3.14-ci-contract-fix"

# Цветовая схема точно по референсу: глубокий navy-midnight, cyan-акцент, card-стиль блоков.
BG = "#07111d"
BG_2 = "#050d18"
PANEL = "#071827"      # фон карточек секций (блоки 01-04)
PANEL_2 = "#0a1b2b"   # фон элементов внутри карточек (чекбоксы)
PANEL_3 = "#0c2b47"   # кнопки «Выбрать», активные состояния
SECTION_SIDE = "#071626"  # левая боковая колонка
SECTION_SIDE_2 = "#09243a"
BORDER = "#126493"
BORDER_SOFT = "#153e5f"
BORDER_FAINT = "#15314a"
ACCENT = "#5bd0ff"    # cyan-blue из референса
ACCENT_2 = "#08a7df"  # кнопка «печать» — ярче
ACCENT_3 = "#94bdd7"
TEXT = "#e8f4ff"
MUTED = "#92a8bc"
MUTED_2 = "#5e7a91"
WARN = "#ffd166"
ERROR = "#ff7a9c"
SUCCESS = "#6fd4a8"
SAVE_ACCENT = "#0f3354"   # тёмная кнопка «сохранить без печати»
SAVE_ACCENT_ACTIVE = "#173f66"
PRINT_ACCENT = "#1096cc"  # синяя кнопка «печатать»
PRINT_ACCENT_ACTIVE = "#18a8dd"
FIELD = "#06101b"     # поля ввода — очень тёмные
FIELD_BORDER = "#193a56"
GLOW = "#39c9ff"
DEEP = "#030912"      # самый тёмный — фон окна и шапка

DIARY_KIND = "diaries"
DIARY_LABEL = "Дневники наблюдения"

# Отдельная память папок для каждой кнопки «Выбрать».
# Это удобнее одной общей last_dir: истории болезни, ЭПИ, тексты дневников,
# шаблоны дневников и папка результата часто лежат в разных постоянных местах.
DIR_OUTPUT = "output_dir"
DIR_PRIMARY_DOCUMENTS = "primary_documents_dir"
DIR_EPI = "epi_dir"
DIR_DIARY_TEXTS = "diary_texts_dir"
DIR_DIARY_TEMPLATES = "diary_templates_dir"
DIR_NUMBERED_DIARY_TEMPLATES = "numbered_diary_templates_dir"
