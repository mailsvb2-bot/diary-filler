"""Локальный справочник МКБ-10, класс V (F00-F99).

Назначение внутри программы:
- дать врачу быстрый выбор шифра и названия диагноза в UI;
- искать по коду, цифрам кода и фрагментам русского названия;
- не требовать интернет при работе программы.

Справочник содержит базовые рубрики и наиболее употребимые подрубрики F00-F99.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ICD10Diagnosis:
    code: str
    title: str

    @property
    def display(self) -> str:
        return f"{self.code} {self.title}"
