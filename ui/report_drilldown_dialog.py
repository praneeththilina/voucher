"""Read-only transaction detail windows used by financial report drill-downs."""

from __future__ import annotations

from collections.abc import Iterable
import tkinter as tk
from tkinter import messagebox, ttk

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, E, END, LEFT, RIGHT, W, X, Y

import database as db


class JournalEntryDetailDialog(tb.Toplevel):
    """Show every line in a posted journal entry without allowing mutation."""

    def __init__(self, parent, entry_id: int, currency: str = "LKR") -> None:
        super().__init__(parent)
        self.entry_id = int(entry_id)
        self.currency = currency
        payload = db.get_journal_entry(self.entry_id)
        if not payload:
            self.withdraw()
            messagebox.showerror(
                "Entry not found",
                "The selected journal entry no longer exists.",
                parent=parent,
            )
            self.destroy()
            return

        self.title("Journal Entry Detail")
        self.geometry("900x520")
        self.minsize(760, 430)
        self.transient(parent)
        self._build_ui(payload["entry"], payload["lines"])
        self.bind("<Escape>", lambda _event: self.destroy())
        self._center(parent)

    def _build_ui(self, entry: dict, lines: list[dict]) -> None:
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        title_row = tb.Frame(root)
        title_row.pack(fill=X, pady=(0, 12))
        tb.Label(
            title_row,
            text=f"Journal Entry {entry.get('entry_number') or self.entry_id}",
            font=("Segoe UI", 16, "bold"),
        ).pack(side=LEFT)
        status = "Posted" if entry.get("is_posted") else "Unposted"
        tb.Label(
            title_row,
            text=status,
            bootstyle="success" if entry.get("is_posted") else "warning",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=RIGHT)

        info = tb.Labelframe(root, text="Transaction", padding=10)
        info.pack(fill=X, pady=(0, 10))
        fields = (
            ("Date", entry.get("entry_date") or "—"),
            ("Type", entry.get("entry_type") or "Journal"),
            ("Reference", entry.get("reference") or "—"),
            ("Source", entry.get("source_module") or "Manual"),
        )
        for column, (label, value) in enumerate(fields):
            box = tb.Frame(info)
            box.grid(row=0, column=column, sticky="ew", padx=8)
            info.columnconfigure(column, weight=1)
            tb.Label(box, text=label, bootstyle="secondary").pack(anchor=W)
            tb.Label(box, text=str(value), font=("Segoe UI", 10, "bold")).pack(anchor=W)
        description = entry.get("description") or "No description"
        tb.Label(info, text=description, wraplength=820).grid(
            row=1, column=0, columnspan=4, sticky=W, padx=8, pady=(10, 0)
        )

        table_box = tb.Frame(root)
        table_box.pack(fill=BOTH, expand=True)
        columns = ("code", "account", "memo", "debit", "credit")
        tree = ttk.Treeview(table_box, columns=columns, show="headings")
        headings = {
            "code": "Account",
            "account": "Account Name",
            "memo": "Line Description",
            "debit": f"Debit ({self.currency})",
            "credit": f"Credit ({self.currency})",
        }
        widths = {"code": 100, "account": 230, "memo": 280, "debit": 120, "credit": 120}
        for column in columns:
            anchor = E if column in ("debit", "credit") else W
            tree.heading(column, text=headings[column], anchor=anchor)
            tree.column(column, width=widths[column], anchor=anchor)
        scroll = tb.Scrollbar(table_box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        total_debit = 0.0
        total_credit = 0.0
        for line in lines:
            debit = float(line.get("debit_amount") or 0.0)
            credit = float(line.get("credit_amount") or 0.0)
            total_debit += debit
            total_credit += credit
            tree.insert(
                "",
                END,
                values=(
                    line.get("account_code") or "",
                    line.get("account_name") or "",
                    line.get("description") or "",
                    f"{debit:,.2f}" if debit else "—",
                    f"{credit:,.2f}" if credit else "—",
                ),
            )

        footer = tb.Frame(root, padding=(0, 10, 0, 0))
        footer.pack(fill=X)
        tb.Label(
            footer,
            text=f"Debit {self.currency} {total_debit:,.2f}    •    "
            f"Credit {self.currency} {total_credit:,.2f}",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=LEFT)
        tb.Button(footer, text="Close", command=self.destroy).pack(side=RIGHT)

    def _center(self, parent) -> None:
        self.update_idletasks()
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")


class ReportDrilldownDialog(tb.Toplevel):
    """Display the journal lines included in a financial report amount."""

    def __init__(
        self,
        parent,
        *,
        company_id: int,
        title: str,
        account_ids: Iterable[int] | None = None,
        entry_ids: Iterable[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        currency: str = "LKR",
    ) -> None:
        super().__init__(parent)
        self.company_id = int(company_id)
        self.report_title = title
        self.account_ids = tuple(sorted({int(value) for value in account_ids or ()}))
        self.entry_ids = tuple(sorted({int(value) for value in entry_ids or ()}))
        self.start_date = start_date
        self.end_date = end_date
        self.currency = currency
        self.rows: list[dict] = []
        self._rows_by_iid: dict[str, dict] = {}

        self.title(f"Transaction Detail — {title}")
        self.geometry("1180x680")
        self.minsize(940, 520)
        self.transient(parent)
        self._build_ui()
        self._load_rows()
        self.bind("<Escape>", lambda _event: self.destroy())
        self._center(parent)

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 10))
        title_box = tb.Frame(header)
        title_box.pack(side=LEFT, fill=X, expand=True)
        tb.Label(
            title_box,
            text=self.report_title,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor=W)
        period = self._period_text()
        tb.Label(
            title_box,
            text=f"Transaction detail by account  •  {period}",
            bootstyle="secondary",
        ).pack(anchor=W)
        tb.Button(
            header,
            text="Refresh",
            command=self._load_rows,
            bootstyle="primary-outline",
        ).pack(side=RIGHT)

        hint = tb.Label(
            root,
            text="Double-click a transaction, or press Enter, to see the complete journal entry.",
            bootstyle="info",
        )
        hint.pack(fill=X, pady=(0, 8))

        table_box = tb.Frame(root)
        table_box.pack(fill=BOTH, expand=True)
        columns = (
            "date",
            "number",
            "type",
            "reference",
            "account",
            "description",
            "debit",
            "credit",
            "balance",
        )
        self.tree = ttk.Treeview(
            table_box,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        labels = {
            "date": "Date",
            "number": "Entry #",
            "type": "Type",
            "reference": "Reference",
            "account": "Account",
            "description": "Description / Memo",
            "debit": f"Debit ({self.currency})",
            "credit": f"Credit ({self.currency})",
            "balance": f"Balance ({self.currency})",
        }
        widths = {
            "date": 95,
            "number": 110,
            "type": 95,
            "reference": 105,
            "account": 190,
            "description": 260,
            "debit": 105,
            "credit": 105,
            "balance": 115,
        }
        for column in columns:
            anchor = E if column in ("debit", "credit", "balance") else W
            self.tree.heading(column, text=labels[column], anchor=anchor)
            self.tree.column(column, width=widths[column], anchor=anchor)
        y_scroll = tb.Scrollbar(table_box, orient="vertical", command=self.tree.yview)
        x_scroll = tb.Scrollbar(table_box, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", self._open_selected_entry)
        self.tree.bind("<Return>", self._open_selected_entry)

        footer = tb.Frame(root, padding=(0, 10, 0, 0))
        footer.pack(fill=X)
        self.summary_var = tk.StringVar(value="Loading transaction detail…")
        tb.Label(
            footer,
            textvariable=self.summary_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(side=LEFT)
        tb.Button(footer, text="Close", command=self.destroy).pack(side=RIGHT)

    def _period_text(self) -> str:
        if self.start_date and self.end_date:
            return f"{self.start_date} to {self.end_date}"
        if self.end_date:
            return f"Through {self.end_date}"
        return "All dates"

    def _load_rows(self) -> None:
        try:
            self.rows = db.get_general_ledger(
                company_id=self.company_id,
                start_date=self.start_date,
                end_date=self.end_date,
                account_ids=self.account_ids or None,
                entry_ids=self.entry_ids or None,
            )
        except Exception as exc:
            messagebox.showerror(
                "Unable to load transaction detail",
                str(exc),
                parent=self,
            )
            return

        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self._rows_by_iid.clear()
        total_debit = 0.0
        total_credit = 0.0
        for index, row in enumerate(self.rows):
            debit = float(row.get("debit_amount") or 0.0)
            credit = float(row.get("credit_amount") or 0.0)
            total_debit += debit
            total_credit += credit
            iid = f"line-{index}"
            self._rows_by_iid[iid] = row
            description = row.get("line_description") or row.get("entry_description") or ""
            self.tree.insert(
                "",
                END,
                iid=iid,
                values=(
                    row.get("entry_date") or "",
                    row.get("entry_number") or "",
                    row.get("entry_type") or "Journal",
                    row.get("reference") or "—",
                    f"{row.get('account_code', '')} - {row.get('account_name', '')}",
                    description,
                    f"{debit:,.2f}" if debit else "—",
                    f"{credit:,.2f}" if credit else "—",
                    f"{float(row.get('running_balance') or 0.0):,.2f}",
                ),
            )

        self.summary_var.set(
            f"{len(self.rows)} line(s)  •  Debit {self.currency} {total_debit:,.2f}  •  "
            f"Credit {self.currency} {total_credit:,.2f}"
        )

    def _open_selected_entry(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        row = self._rows_by_iid.get(selection[0])
        if row:
            JournalEntryDetailDialog(
                self,
                entry_id=int(row["entry_id"]),
                currency=self.currency,
            )

    def _center(self, parent) -> None:
        self.update_idletasks()
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")