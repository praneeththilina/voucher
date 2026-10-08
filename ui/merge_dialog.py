"""Reusable confirmation dialog for irreversible master-record merges."""

from __future__ import annotations

import tkinter as tk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, EW, RIGHT, W


class MergeRecordsDialog(tb.Toplevel):
    """Choose the retained record and explicitly confirm a merge."""

    def __init__(
        self,
        parent,
        entity_label: str,
        source: dict,
        candidates: list[dict],
    ):
        super().__init__(parent)
        self.result: int | None = None
        self.entity_label = entity_label
        self.source = source
        self.candidates = candidates
        self._target_lookup = {
            f"{row['name']}  [#{row['id']}]": int(row["id"])
            for row in candidates
        }
        self.title(f"Merge {entity_label}")
        self.geometry("590x330")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._center()

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=20)
        root.pack(fill=BOTH, expand=True)
        root.columnconfigure(1, weight=1)

        tb.Label(
            root,
            text=f"Merge duplicate {self.entity_label}",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky=W)
        tb.Label(
            root,
            text=(
                "All transactions and history will move to the retained "
                "record. The selected duplicate will then be removed."
            ),
            wraplength=530,
            bootstyle="warning",
        ).grid(row=1, column=0, columnspan=2, sticky=W, pady=(5, 18))

        tb.Label(root, text="Remove duplicate").grid(row=2, column=0, sticky=W)
        tb.Label(
            root,
            text=f"{self.source['name']}  [#{self.source['id']}]",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=2, column=1, sticky=W, padx=(12, 0))

        tb.Label(root, text="Keep this record").grid(
            row=3, column=0, sticky=W, pady=(16, 0)
        )
        self.target_var = tk.StringVar()
        combo = tb.Combobox(
            root,
            textvariable=self.target_var,
            values=list(self._target_lookup),
            state="readonly",
        )
        combo.grid(row=3, column=1, sticky=EW, padx=(12, 0), pady=(16, 0))
        if self._target_lookup:
            combo.current(0)

        tb.Label(
            root,
            text="This operation cannot be undone. A backup is recommended.",
            bootstyle="danger",
        ).grid(row=4, column=0, columnspan=2, sticky=W, pady=(22, 0))

        actions = tb.Frame(root)
        actions.grid(row=5, column=0, columnspan=2, sticky=EW, pady=(22, 0))
        tb.Button(
            actions,
            text="Cancel",
            bootstyle="secondary-outline",
            command=self.destroy,
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            actions,
            text="Merge and keep selected record",
            bootstyle="danger",
            command=self._confirm,
        ).pack(side=RIGHT)

    def _confirm(self) -> None:
        target_id = self._target_lookup.get(self.target_var.get())
        if target_id is None:
            return
        self.result = target_id
        self.destroy()

    def _center(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x_pos = max(0, (self.winfo_screenwidth() - width) // 2)
        y_pos = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x_pos}+{y_pos}")


def choose_merge_target(
    parent,
    entity_label: str,
    source: dict,
    candidates: list[dict],
) -> int | None:
    """Show the merge chooser and return the retained record ID."""
    dialog = MergeRecordsDialog(parent, entity_label, source, candidates)
    parent.wait_window(dialog)
    return dialog.result