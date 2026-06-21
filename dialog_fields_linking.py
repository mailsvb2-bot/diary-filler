from __future__ import annotations

import tkinter as tk


def attach_linked_field_mirroring(
    entry_vars: list[tk.StringVar],
    entry_auto_values: list[str],
    linked_groups: list[tuple[int, list[int]]] | None,
) -> None:
    if not linked_groups:
        return

    def mirror_from(source_index: int, target_indices: list[int]) -> None:
        if source_index >= len(entry_vars):
            return
        source_value = entry_vars[source_index].get().strip()
        for target_index in target_indices:
            if target_index >= len(entry_vars):
                continue
            current_value = entry_vars[target_index].get().strip()
            previous_auto = entry_auto_values[target_index].strip()
            if not current_value or current_value == previous_auto:
                entry_vars[target_index].set(source_value)
                entry_auto_values[target_index] = source_value

    for source_index, target_indices in linked_groups:
        if source_index < len(entry_vars):
            entry_vars[source_index].trace_add(
                "write",
                lambda *_args, si=source_index, ti=target_indices: mirror_from(si, ti),
            )
            mirror_from(source_index, target_indices)
