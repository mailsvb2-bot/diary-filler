from __future__ import annotations

from dialog_fields_core import prompt_fields_dialog


class DialogFieldsMixin:
    def _prompt_fields(self, *, title: str, rows: list[tuple[str, str]], width: int = 28, linked_groups: list[tuple[int, list[int]]] | None = None) -> list[str] | None:
        return prompt_fields_dialog(
            self,
            title=title,
            rows=rows,
            width=width,
            linked_groups=linked_groups,
        )
