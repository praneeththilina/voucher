"""Accountant Centre landing workspace for daily bookkeeping and review."""

from __future__ import annotations

from datetime import date, datetime
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH, E, END, LEFT, RIGHT, W, X, Y

import database as db
from reports import generate_cash_flow, generate_profit_loss
from ui.report_drilldown_dialog import ReportDrilldownDialog


class AccountantCenterFrame(tb.Frame):
    """Fast, action-oriented accounting home screen for the active company."""

    def __init__(
        self,
        parent,
        *,
        company_id: int,
        callbacks: dict[str, Callable],
    ) -> None:
        super().__init__(parent, padding=14)
        self.company_id = int(company_id)
        self.callbacks = callbacks
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"
        self._refresh_pending = False
        self._refresh_after_id = None
        self._load_after_id = None
        self._last_refresh = 0.0
        self._recent_entries: dict[str, dict] = {}
        self._attention_actions: dict[str, str] = {}
        self._kpi_vars = {
            "cash": tk.StringVar(value="Loading…"),
            "receivable": tk.StringVar(value="Loading…"),
            "payable": tk.StringVar(value="Loading…"),
            "profit": tk.StringVar(value="Loading…"),
        }
        self.status_var = tk.StringVar(value="Preparing accounting overview…")
        self._build_ui()
        self._refresh_after_id = self.after(50, self._initial_refresh)

    def _initial_refresh(self) -> None:
        """Load figures after the first paint without leaving orphan callbacks."""
        self._refresh_after_id = None
        if self.winfo_exists():
            self.refresh(force=True)

    def destroy(self) -> None:
        """Cancel pending Tk callbacks before destroying the dashboard."""
        for timer_id in (self._refresh_after_id, self._load_after_id):
            if timer_id:
                try:
                    self.after_cancel(timer_id)
                except (tk.TclError, ValueError):
                    pass
        self._refresh_after_id = None
        self._load_after_id = None
        super().destroy()
    def _build_ui(self) -> None:
        header = tb.Frame(self)
        header.pack(fill=X, pady=(0, 10))
        title_box = tb.Frame(header)
        title_box.pack(side=LEFT, fill=X, expand=True)
        company = db.get_company(self.company_id) or {}
        tb.Label(
            title_box,
            text="Accountant Centre",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor=W)
        tb.Label(
            title_box,
            text=f"{company.get('name') or 'Company'}  •  Books, reports, and work that needs attention",
            bootstyle="secondary",
        ).pack(anchor=W)
        tb.Button(
            header,
            text="Refresh",
            bootstyle="primary-outline",
            command=lambda: self.refresh(force=True),
        ).pack(side=RIGHT)

        cards = tb.Frame(self)
        cards.pack(fill=X, pady=(0, 10))
        self._create_kpi_button(
            cards,
            "Cash & Bank",
            self._kpi_vars["cash"],
            "Cash flow statement",
            "info-outline",
            lambda: self._invoke("financial_reports", 3),
        )
        self._create_kpi_button(
            cards,
            "Money Owed to You",
            self._kpi_vars["receivable"],
            "Open receivables",
            "success-outline",
            lambda: self._invoke("ar_aging"),
        )
        self._create_kpi_button(
            cards,
            "Bills to Pay",
            self._kpi_vars["payable"],
            "Open payables",
            "warning-outline",
            lambda: self._invoke("ap_aging"),
        )
        self._create_kpi_button(
            cards,
            "Net Profit This Month",
            self._kpi_vars["profit"],
            "Profit & Loss",
            "primary-outline",
            lambda: self._invoke("financial_reports", 0),
        )

        workspace = tb.Panedwindow(self, orient=tk.HORIZONTAL)
        workspace.pack(fill=BOTH, expand=True)

        left = tb.Frame(workspace, padding=(0, 0, 8, 0))
        right = tb.Frame(workspace, padding=(8, 0, 0, 0))
        workspace.add(left, weight=2)
        workspace.add(right, weight=3)

        self._build_quick_actions(left)
        self._build_attention_panel(right)
        self._build_recent_activity(right)

        status = tb.Frame(self, padding=(0, 8, 0, 0))
        status.pack(fill=X)
        tb.Label(status, textvariable=self.status_var, bootstyle="secondary").pack(side=LEFT)
        tb.Label(
            status,
            text="Tip: double-click report amounts to see their transactions.",
            bootstyle="info",
        ).pack(side=RIGHT)

    def _create_kpi_button(
        self,
        parent,
        title: str,
        value_var: tk.StringVar,
        footer: str,
        style: str,
        command: Callable,
    ) -> None:
        card = tb.Button(
            parent,
            textvariable=value_var,
            command=command,
            bootstyle=style,
            width=25,
        )
        card.pack(side=LEFT, fill=X, expand=True, padx=4, ipady=12)
        value_var.set(f"{title}\nLoading…\n{footer}")

    def _build_quick_actions(self, parent) -> None:
        actions = tb.Labelframe(parent, text="Create & Record", padding=10)
        actions.pack(fill=X, pady=(0, 10))
        self._action_button(actions, "New Payment Voucher", "new_voucher", "success")
        self._action_button(actions, "New Journal Entry", "new_journal", "primary")
        self._action_button(actions, "Customer Invoice", "ar_invoices", "info-outline")
        self._action_button(actions, "Supplier Bill", "ap_invoices", "warning-outline")

        books = tb.Labelframe(parent, text="Review the Books", padding=10)
        books.pack(fill=X, pady=(0, 10))
        self._action_button(books, "Chart of Accounts", "chart_of_accounts", "secondary-outline")
        self._action_button(books, "General Ledger", "general_ledger", "secondary-outline")
        self._action_button(books, "Financial Statements", "financial_reports", "primary-outline")
        self._action_button(books, "Bank Reconciliation", "bank_reconciliation", "info-outline")
        self._action_button(books, "Close the Books", "period_close", "danger-outline")

        lists = tb.Labelframe(parent, text="Daily Work", padding=10)
        lists.pack(fill=X)
        self._action_button(lists, "Voucher List", "voucher_list", "secondary-outline")
        self._action_button(lists, "Accounts Receivable", "ar_invoices", "success-outline")
        self._action_button(lists, "Accounts Payable", "ap_invoices", "warning-outline")
        self._action_button(lists, "Alerts & Exceptions", "alerts", "danger-outline")

    def _action_button(self, parent, text: str, callback: str, style: str) -> None:
        tb.Button(
            parent,
            text=text,
            bootstyle=style,
            command=lambda name=callback: self._invoke(name),
        ).pack(fill=X, pady=3, ipady=3)

    def _build_attention_panel(self, parent) -> None:
        box = tb.Labelframe(parent, text="Needs Attention", padding=8)
        box.pack(fill=BOTH, expand=True, pady=(0, 8))
        columns = ("item", "count", "amount")
        self.attention_tree = ttk.Treeview(
            box,
            columns=columns,
            show="headings",
            height=6,
            selectmode="browse",
        )
        self.attention_tree.heading("item", text="Item", anchor=W)
        self.attention_tree.heading("count", text="Count", anchor=E)
        self.attention_tree.heading("amount", text=f"Amount ({self.currency})", anchor=E)
        self.attention_tree.column("item", width=280, anchor=W)
        self.attention_tree.column("count", width=70, anchor=E)
        self.attention_tree.column("amount", width=130, anchor=E)
        self.attention_tree.pack(fill=BOTH, expand=True)
        self.attention_tree.bind("<Double-Button-1>", self._open_attention_item)
        self.attention_tree.bind("<Return>", self._open_attention_item)

    def _build_recent_activity(self, parent) -> None:
        box = tb.Labelframe(parent, text="Recent Accounting Activity", padding=8)
        box.pack(fill=BOTH, expand=True)
        columns = ("date", "number", "type", "description", "amount")
        self.recent_tree = ttk.Treeview(
            box,
            columns=columns,
            show="headings",
            height=7,
            selectmode="browse",
        )
        labels = {
            "date": "Date",
            "number": "Entry #",
            "type": "Type",
            "description": "Description",
            "amount": f"Amount ({self.currency})",
        }
        widths = {"date": 85, "number": 105, "type": 95, "description": 260, "amount": 115}
        for column in columns:
            anchor = E if column == "amount" else W
            self.recent_tree.heading(column, text=labels[column], anchor=anchor)
            self.recent_tree.column(column, width=widths[column], anchor=anchor)
        scroll = tb.Scrollbar(box, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scroll.set)
        self.recent_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.recent_tree.bind("<Double-Button-1>", self._open_recent_entry)
        self.recent_tree.bind("<Return>", self._open_recent_entry)

    def refresh(self, force: bool = False) -> None:
        """Refresh at most every 15 seconds unless the user explicitly requests it."""
        if self._refresh_pending:
            return
        if not force and time.monotonic() - self._last_refresh < 15:
            return
        self._refresh_pending = True
        self.status_var.set("Refreshing accounting overview…")
        self._load_after_id = self.after_idle(self._load_data)

    def mark_dirty(self) -> None:
        """Ensure the next visit reloads figures changed elsewhere in the app."""
        self._last_refresh = 0.0

    def _load_data(self) -> None:
        self._load_after_id = None
        today = date.today()
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        try:
            conn = db.get_connection()
            try:
                db.backfill_vouchers_to_journal(self.company_id, conn=conn)
                profit_loss = generate_profit_loss(
                    self.company_id,
                    start_date=start_date,
                    end_date=end_date,
                    conn=conn,
                )
                cash_flow = generate_cash_flow(
                    self.company_id,
                    start_date=start_date,
                    end_date=end_date,
                    conn=conn,
                )
                receivables = db.get_ar_aging_report(
                    self.company_id,
                    as_of_date=end_date,
                    conn=conn,
                )
                payables = db.get_ap_aging_report(
                    self.company_id,
                    as_of_date=end_date,
                    conn=conn,
                )
                alerts = db.get_active_alerts(self.company_id, conn=conn)
                recent = db.get_journal_entries(
                    self.company_id,
                    end_date=end_date,
                    conn=conn,
                )[:12]
            finally:
                conn.close()

            self._set_kpi(
                "cash",
                "Cash & Bank",
                cash_flow["ending_cash"],
                "Cash flow statement",
            )
            self._set_kpi(
                "receivable",
                "Money Owed to You",
                receivables["totals"]["total_due"],
                f"{sum(len(row['invoices']) for row in receivables['by_customer'])} open invoice(s)",
            )
            self._set_kpi(
                "payable",
                "Bills to Pay",
                payables["totals"]["total_due"],
                f"{sum(len(row['invoices']) for row in payables['by_supplier'])} open bill(s)",
            )
            self._set_kpi(
                "profit",
                "Net Profit This Month",
                profit_loss["net_profit"],
                "Profit & Loss",
            )
            self._render_attention(receivables, payables, alerts)
            self._render_recent(recent)
            self._last_refresh = time.monotonic()
            self.status_var.set(f"Updated {datetime.now().strftime('%H:%M')}  •  Period through {end_date}")
        except Exception as exc:
            self.status_var.set(f"Could not refresh the overview: {exc}")
        finally:
            self._refresh_pending = False

    def _set_kpi(self, key: str, title: str, amount: float, footer: str) -> None:
        self._kpi_vars[key].set(
            f"{title}\n{self.currency} {float(amount):,.2f}\n{footer}"
        )

    def _render_attention(self, receivables: dict, payables: dict, alerts: list[dict]) -> None:
        children = self.attention_tree.get_children()
        if children:
            self.attention_tree.delete(*children)
        self._attention_actions.clear()
        rows = (
            (
                "Overdue customer invoices",
                self._overdue_invoice_count(receivables, "by_customer"),
                self._overdue_total(receivables),
                "ar_aging",
            ),
            (
                "Overdue supplier bills",
                self._overdue_invoice_count(payables, "by_supplier"),
                self._overdue_total(payables),
                "ap_aging",
            ),
            ("Active alerts and exceptions", len(alerts), 0.0, "alerts"),
        )
        for index, (label, count, amount, callback) in enumerate(rows):
            iid = f"attention-{index}"
            self._attention_actions[iid] = callback
            self.attention_tree.insert(
                "",
                END,
                iid=iid,
                values=(label, count, f"{amount:,.2f}" if amount else "—"),
            )

    @staticmethod
    def _overdue_total(report: dict) -> float:
        totals = report.get("totals", {})
        return sum(
            float(totals.get(bucket) or 0.0)
            for bucket in ("days_1_30", "days_31_60", "days_61_90", "days_over_90")
        )

    @staticmethod
    def _overdue_invoice_count(report: dict, group_key: str) -> int:
        return sum(
            1
            for group in report.get(group_key, [])
            for invoice in group.get("invoices", [])
            if int(invoice.get("days_overdue") or 0) > 0
        )

    def _render_recent(self, rows: list[dict]) -> None:
        children = self.recent_tree.get_children()
        if children:
            self.recent_tree.delete(*children)
        self._recent_entries.clear()
        for index, row in enumerate(rows):
            iid = f"entry-{index}"
            self._recent_entries[iid] = row
            amount = float(row.get("total_debit") or 0.0)
            self.recent_tree.insert(
                "",
                END,
                iid=iid,
                values=(
                    row.get("entry_date") or "",
                    row.get("entry_number") or "",
                    row.get("entry_type") or "Journal",
                    row.get("description") or "",
                    f"{amount:,.2f}",
                ),
            )

    def _open_attention_item(self, _event=None) -> None:
        selected = self.attention_tree.selection()
        if selected:
            callback = self._attention_actions.get(selected[0])
            if callback:
                self._invoke(callback)

    def _open_recent_entry(self, _event=None) -> None:
        selected = self.recent_tree.selection()
        if not selected:
            return
        row = self._recent_entries.get(selected[0])
        if not row:
            return
        ReportDrilldownDialog(
            self,
            company_id=self.company_id,
            title=f"Journal Entry {row.get('entry_number') or row['id']}",
            entry_ids=[row["id"]],
            currency=self.currency,
        )

    def _invoke(self, name: str, *args) -> None:
        callback = self.callbacks.get(name)
        if callback:
            callback(*args)