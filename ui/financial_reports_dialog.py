"""
ui/financial_reports_dialog.py
Interactive Financial Reports Dashboard & Reporting Suite for Voucher Manager SME Bookkeeping v3.8.

Provides:
- Profit & Loss (Income Statement) with live KPI margins and cost breakdowns
- Balance Sheet (Financial Position) with live equation balance verification
- Trial Balance with double-entry debit/credit reconciliation
- Cash Flow Statement with cash & bank inflows/outflows tracking
- Integrated multi-page PDF generation via ReportLab Platypus
- CSV exports and direct printing
"""

import os
import tempfile
import subprocess
from datetime import datetime, date, timedelta
import calendar
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from ui.report_drilldown_dialog import ReportDrilldownDialog

from reports import (
    generate_profit_loss,
    export_profit_loss_csv,
    generate_balance_sheet,
    export_balance_sheet_csv,
    generate_cash_flow,
    export_cash_flow_csv,
    generate_profit_loss_pdf,
    generate_balance_sheet_pdf,
    generate_trial_balance_pdf,
    generate_cash_flow_pdf,
)


class FinancialReportsDialog(tb.Toplevel):
    """Interactive multi-tab financial report explorer and generator."""

    PRESETS = [
        "This Month",
        "Last Month",
        "This Quarter",
        "This Year (YTD)",
        "Last Year",
        "All Time",
        "Custom"
    ]

    def __init__(self, parent, company_id=None, initial_tab=0):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.comp_profile = db.get_company(self.company_id) or {}
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Financial Statements & Reports — Voucher Manager Bookkeeping")
        self.geometry("1100x740")
        self.minsize(950, 620)
        self.transient(parent)

        # State cache for active reports
        self.pl_data = None
        self.bs_data = None
        self.tb_data = None
        self.cf_data = None
        self._drilldown_rows: dict[tuple[object, str], dict] = {}

        self._init_date_defaults()
        self._build_ui(initial_tab)
        self.center_window()
        self._refresh_all_reports()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _init_date_defaults(self):
        """Initialize default date ranges to current calendar month."""
        today = date.today()
        first_day = today.replace(day=1)
        self.start_date_var = tk.StringVar(value=first_day.strftime("%Y-%m-%d"))
        self.end_date_var = tk.StringVar(value=today.strftime("%Y-%m-%d"))
        self.preset_var = tk.StringVar(value="This Month")

    def _build_ui(self, initial_tab):
        container = tb.Frame(self, padding=(16, 12, 16, 12))
        container.pack(fill=BOTH, expand=True)

        # Header Bar
        hdr_frame = tb.Frame(container)
        hdr_frame.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(hdr_frame)
        title_box.pack(side=LEFT)
        comp_name = self.comp_profile.get("name", "Main Enterprise")
        tb.Label(title_box, text="📊 Financial Reports & Bookkeeping Statements", font=("Segoe UI", 14, "bold")).pack(anchor=W)
        tb.Label(title_box, text=f"Company: {comp_name}  |  Base Currency: {self.currency}", font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)

        # Action Buttons in Top Header
        act_box = tb.Frame(hdr_frame)
        act_box.pack(side=RIGHT, anchor=E)

        if getattr(self, "on_close", None):
            tb.Button(
                act_box, text="← Back", bootstyle="secondary-outline",
                command=self.on_close,
            ).pack(side=RIGHT, padx=(8, 0))

        self.btn_refresh = tb.Button(act_box, text="🔄 Refresh", bootstyle="primary", command=self._refresh_all_reports)
        self.btn_refresh.pack(side=LEFT, padx=3)

        self.btn_pdf = tb.Button(act_box, text="📄 Export PDF", bootstyle="success-outline", command=self._export_pdf)
        self.btn_pdf.pack(side=LEFT, padx=3)

        self.btn_csv = tb.Button(act_box, text="📊 Export CSV", bootstyle="info-outline", command=self._export_csv)
        self.btn_csv.pack(side=LEFT, padx=3)

        self.btn_print = tb.Button(act_box, text="🖨️ Print", bootstyle="secondary-outline", command=self._print_report)
        self.btn_print.pack(side=LEFT, padx=3)

        # Filter / Preset Toolbar
        filter_bar = tb.Labelframe(container, text="Reporting Period Controls", padding=(12, 8))
        filter_bar.pack(fill=X, pady=(0, 10))

        tb.Label(filter_bar, text="Period Preset:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 6))
        self.preset_combo = tb.Combobox(filter_bar, textvariable=self.preset_var, values=self.PRESETS, state="readonly", width=16)
        self.preset_combo.pack(side=LEFT, padx=(0, 16))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_changed)

        tb.Label(filter_bar, text="Start Date:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.start_entry = tb.Entry(filter_bar, textvariable=self.start_date_var, width=12)
        self.start_entry.pack(side=LEFT, padx=(0, 14))

        tb.Label(filter_bar, text="End Date / As of:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.end_entry = tb.Entry(filter_bar, textvariable=self.end_date_var, width=12)
        self.end_entry.pack(side=LEFT, padx=(0, 14))

        tb.Button(filter_bar, text="Apply Date Filter", bootstyle="outline", command=self._refresh_all_reports).pack(side=LEFT, padx=4)

        tb.Label(
            container,
            text="Double-click an account or total to open the transactions included in that amount.",
            bootstyle="info",
        ).pack(fill=X, pady=(0, 6))

        # Notebook with Financial Statement Tabs
        self.notebook = tb.Notebook(container)
        self.notebook.pack(fill=BOTH, expand=True)

        self._build_pl_tab()
        self._build_bs_tab()
        self._build_tb_tab()
        self._build_cf_tab()

        if 0 <= initial_tab < 4:
            self.notebook.select(initial_tab)

        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._update_kpis_for_active_tab())

    # =========================================================================
    # TAB 1: PROFIT & LOSS
    # =========================================================================
    def _build_pl_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  📈 Profit & Loss  ")

        # Top KPI Banner
        kpi_frame = tb.Frame(tab)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.pl_kpi_rev = self._create_kpi_card(kpi_frame, "Total Revenue", "0.00", "success")
        self.pl_kpi_cogs = self._create_kpi_card(kpi_frame, "Cost of Goods Sold", "0.00", "secondary")
        self.pl_kpi_exp = self._create_kpi_card(kpi_frame, "Operating Expenses", "0.00", "warning")
        self.pl_kpi_net = self._create_kpi_card(kpi_frame, "Net Profit / (Loss)", "0.00", "primary")

        # Data Treeview
        tree_frame = tb.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "pct", "amount")
        self.pl_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.pl_tree.heading("code", text="Account Code")
        self.pl_tree.heading("name", text="Account / Category Description")
        self.pl_tree.heading("pct", text="% of Revenue")
        self.pl_tree.heading("amount", text=f"Amount ({self.currency})")

        self.pl_tree.column("code", width=120, anchor=W)
        self.pl_tree.column("name", width=480, anchor=W)
        self.pl_tree.column("pct", width=130, anchor=E)
        self.pl_tree.column("amount", width=170, anchor=E)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.pl_tree.yview)
        self.pl_tree.configure(yscrollcommand=vsb.set)
        self.pl_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self._configure_tree_tags(self.pl_tree)

    # =========================================================================
    # TAB 2: BALANCE SHEET
    # =========================================================================
    def _build_bs_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  ⚖️ Balance Sheet  ")

        kpi_frame = tb.Frame(tab)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.bs_kpi_assets = self._create_kpi_card(kpi_frame, "Total Assets", "0.00", "info")
        self.bs_kpi_liab = self._create_kpi_card(kpi_frame, "Total Liabilities", "0.00", "warning")
        self.bs_kpi_eq = self._create_kpi_card(kpi_frame, "Total Equity", "0.00", "secondary")
        self.bs_kpi_status = self._create_kpi_card(kpi_frame, "Accounting Equation", "Balanced ✓", "success")

        tree_frame = tb.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "category", "amount")
        self.bs_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.bs_tree.heading("code", text="Account Code")
        self.bs_tree.heading("name", text="Account / Line Description")
        self.bs_tree.heading("category", text="Subcategory")
        self.bs_tree.heading("amount", text=f"Amount ({self.currency})")

        self.bs_tree.column("code", width=120, anchor=W)
        self.bs_tree.column("name", width=480, anchor=W)
        self.bs_tree.column("category", width=140, anchor=W)
        self.bs_tree.column("amount", width=170, anchor=E)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.bs_tree.yview)
        self.bs_tree.configure(yscrollcommand=vsb.set)
        self.bs_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self._configure_tree_tags(self.bs_tree)

    # =========================================================================
    # TAB 3: TRIAL BALANCE
    # =========================================================================
    def _build_tb_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  📋 Trial Balance  ")

        kpi_frame = tb.Frame(tab)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.tb_kpi_deb = self._create_kpi_card(kpi_frame, "Total Debits", "0.00", "primary")
        self.tb_kpi_cred = self._create_kpi_card(kpi_frame, "Total Credits", "0.00", "info")
        self.tb_kpi_diff = self._create_kpi_card(kpi_frame, "Difference", "0.00", "secondary")
        self.tb_kpi_status = self._create_kpi_card(kpi_frame, "Double-Entry Status", "Balanced ✓", "success")

        tree_frame = tb.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "debit", "credit")
        self.tb_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tb_tree.heading("code", text="Account Code")
        self.tb_tree.heading("name", text="Account Name & Classification")
        self.tb_tree.heading("debit", text=f"Debit Balance ({self.currency})")
        self.tb_tree.heading("credit", text=f"Credit Balance ({self.currency})")

        self.tb_tree.column("code", width=120, anchor=W)
        self.tb_tree.column("name", width=480, anchor=W)
        self.tb_tree.column("debit", width=150, anchor=E)
        self.tb_tree.column("credit", width=150, anchor=E)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tb_tree.yview)
        self.tb_tree.configure(yscrollcommand=vsb.set)
        self.tb_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self._configure_tree_tags(self.tb_tree)

    # =========================================================================
    # TAB 4: CASH FLOW STATEMENT
    # =========================================================================
    def _build_cf_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="  💵 Cash Flow  ")

        kpi_frame = tb.Frame(tab)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.cf_kpi_beg = self._create_kpi_card(kpi_frame, "Beginning Cash", "0.00", "secondary")
        self.cf_kpi_in = self._create_kpi_card(kpi_frame, "Total Inflows (+)", "0.00", "success")
        self.cf_kpi_out = self._create_kpi_card(kpi_frame, "Total Outflows (-)", "0.00", "danger")
        self.cf_kpi_end = self._create_kpi_card(kpi_frame, "Ending Cash & Bank", "0.00", "primary")

        tree_frame = tb.Frame(tab)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("date", "desc", "account", "amount")
        self.cf_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.cf_tree.heading("date", text="Date / Entry #")
        self.cf_tree.heading("desc", text="Transaction Details")
        self.cf_tree.heading("account", text="Cash/Bank Account")
        self.cf_tree.heading("amount", text=f"Amount ({self.currency})")

        self.cf_tree.column("date", width=130, anchor=W)
        self.cf_tree.column("desc", width=470, anchor=W)
        self.cf_tree.column("account", width=160, anchor=W)
        self.cf_tree.column("amount", width=150, anchor=E)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.cf_tree.yview)
        self.cf_tree.configure(yscrollcommand=vsb.set)
        self.cf_tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self._configure_tree_tags(self.cf_tree)

    # =========================================================================
    # Helpers: KPI Cards and Treeview Tagging
    # =========================================================================
    def _create_kpi_card(self, parent, label_text, default_val, bootstyle):
        frame = tb.Frame(parent, bootstyle=bootstyle, padding=(12, 8))
        frame.pack(side=LEFT, fill=X, expand=True, padx=4)

        tb.Label(frame, text=label_text, font=("Segoe UI", 8), bootstyle=f"{bootstyle}-inverse").pack(anchor=W)
        val_lbl = tb.Label(frame, text=default_val, font=("Segoe UI", 12, "bold"), bootstyle=f"{bootstyle}-inverse")
        val_lbl.pack(anchor=W, pady=(2, 0))
        return val_lbl

    def _configure_tree_tags(self, tree):
        tree.tag_configure("section", font=("Segoe UI", 9, "bold"), background="#F1F5F9", foreground="#0F172A")
        tree.tag_configure("subtotal", font=("Segoe UI", 9, "bold"), background="#F8FAFC", foreground="#1E293B")
        tree.tag_configure("grand_total", font=("Segoe UI", 10, "bold"), background="#EFF6FF", foreground="#1E3A8A")
        tree.tag_configure("profit", font=("Segoe UI", 10, "bold"), background="#ECFDF5", foreground="#047857")
        tree.tag_configure("loss", font=("Segoe UI", 10, "bold"), background="#FEF2F2", foreground="#B91C1C")
        tree.tag_configure("item", font=("Segoe UI", 9))
        tree.bind(
            "<Double-Button-1>",
            lambda _event, report_tree=tree: self._open_report_drilldown(report_tree),
        )
        tree.bind(
            "<Return>",
            lambda _event, report_tree=tree: self._open_report_drilldown(report_tree),
        )

    def _insert_report_row(
        self,
        tree,
        values,
        tags,
        *,
        title=None,
        account_ids=None,
        entry_ids=None,
        start_date=None,
        end_date=None,
    ):
        """Insert a report row and attach its transaction-detail definition."""
        iid = tree.insert("", END, values=values, tags=tags)
        normalized_accounts = tuple(
            sorted({int(value) for value in account_ids or () if value is not None})
        )
        normalized_entries = tuple(
            sorted({int(value) for value in entry_ids or () if value is not None})
        )
        if title and (normalized_accounts or normalized_entries):
            self._drilldown_rows[(tree, iid)] = {
                "title": title,
                "account_ids": normalized_accounts,
                "entry_ids": normalized_entries,
                "start_date": start_date,
                "end_date": end_date,
            }
        return iid

    def _clear_report_tree(self, tree):
        """Clear a report tree and discard stale row navigation metadata."""
        for key in [key for key in self._drilldown_rows if key[0] is tree]:
            del self._drilldown_rows[key]
        children = tree.get_children()
        if children:
            tree.delete(*children)

    def _open_report_drilldown(self, tree):
        """Open transaction detail for the selected report amount."""
        selection = tree.selection()
        if not selection:
            return
        detail = self._drilldown_rows.get((tree, selection[0]))
        if not detail:
            return
        ReportDrilldownDialog(
            self,
            company_id=self.company_id,
            title=detail["title"],
            account_ids=detail["account_ids"],
            entry_ids=detail["entry_ids"],
            start_date=detail["start_date"],
            end_date=detail["end_date"],
            currency=self.currency,
        )

    @staticmethod
    def _account_ids(items):
        return [item.get("account_id") for item in items if item.get("account_id")]
    # =========================================================================
    # Date Preset Handlers
    # =========================================================================
    def _on_preset_changed(self, event=None):
        preset = self.preset_var.get()
        today = date.today()

        if preset == "This Month":
            start = today.replace(day=1)
            end = today
        elif preset == "Last Month":
            first_this_month = today.replace(day=1)
            end = first_this_month - timedelta(days=1)
            start = end.replace(day=1)
        elif preset == "This Quarter":
            cur_q = (today.month - 1) // 3
            start = date(today.year, 3 * cur_q + 1, 1)
            end = today
        elif preset == "This Year (YTD)":
            start = date(today.year, 1, 1)
            end = today
        elif preset == "Last Year":
            start = date(today.year - 1, 1, 1)
            end = date(today.year - 1, 12, 31)
        elif preset == "All Time":
            start = date(2000, 1, 1)
            end = today
        else:
            return

        self.start_date_var.set(start.strftime("%Y-%m-%d"))
        self.end_date_var.set(end.strftime("%Y-%m-%d"))
        self._refresh_all_reports()

    # =========================================================================
    # Report Refreshes
    # =========================================================================
    def _refresh_all_reports(self):
        s_date = self.start_date_var.get().strip()
        e_date = self.end_date_var.get().strip()

        try:
            # 1. Profit & Loss
            self.pl_data = generate_profit_loss(self.company_id, start_date=s_date, end_date=e_date)
            self._render_pl()

            # 2. Balance Sheet
            self.bs_data = generate_balance_sheet(self.company_id, as_of_date=e_date)
            self._render_bs()

            # 3. Trial Balance
            self.tb_data = db.get_trial_balance(self.company_id, as_of_date=e_date)
            self.tb_data["company_name"] = self.comp_profile.get("name", "Main Enterprise")
            self._render_tb()

            # 4. Cash Flow Statement
            self.cf_data = generate_cash_flow(self.company_id, start_date=s_date, end_date=e_date)
            self._render_cf()

        except Exception as e:
            messagebox.showerror("Report Generation Error", f"Failed to compute financial reports:\n{e}", parent=self)

    def _render_pl(self):
        self._clear_report_tree(self.pl_tree)
        d = self.pl_data
        if not d:
            return

        start_date = d["period"]["start_date"]
        end_date = d["period"]["end_date"]
        revenue_ids = self._account_ids(d["operating_revenue"])
        cost_ids = self._account_ids(d["cost_of_sales"])
        expense_ids = self._account_ids(d["operating_expenses"])
        other_income_ids = self._account_ids(d["other_income"])

        self.pl_kpi_rev.config(text=f"{self.currency} {d['total_operating_revenue']:,.2f}")
        self.pl_kpi_cogs.config(text=f"{self.currency} {d['total_cost_of_sales']:,.2f}")
        self.pl_kpi_exp.config(text=f"{self.currency} {d['total_operating_expenses']:,.2f}")
        self.pl_kpi_net.config(
            text=f"{self.currency} {d['net_profit']:,.2f} "
            f"({d['net_profit_margin_pct']:.1f}%)"
        )

        self._insert_report_row(
            self.pl_tree, ("", "OPERATING REVENUE", "", ""), ("section",)
        )
        for item in d["operating_revenue"]:
            self._insert_report_row(
                self.pl_tree,
                (
                    item["account_code"],
                    item["account_name"],
                    f"{item['pct_of_revenue']:.2f}%",
                    f"{item['amount']:,.2f}",
                ),
                ("item",),
                title=f"{item['account_code']} — {item['account_name']}",
                account_ids=[item["account_id"]],
                start_date=start_date,
                end_date=end_date,
            )
        self._insert_report_row(
            self.pl_tree,
            ("", "TOTAL OPERATING REVENUE", "100.00%", f"{d['total_operating_revenue']:,.2f}"),
            ("subtotal",),
            title="Total Operating Revenue",
            account_ids=revenue_ids,
            start_date=start_date,
            end_date=end_date,
        )

        if d["cost_of_sales"]:
            self._insert_report_row(
                self.pl_tree, ("", "COST OF GOODS SOLD", "", ""), ("section",)
            )
            for item in d["cost_of_sales"]:
                self._insert_report_row(
                    self.pl_tree,
                    (
                        item["account_code"],
                        item["account_name"],
                        f"{item['pct_of_revenue']:.2f}%",
                        f"{item['amount']:,.2f}",
                    ),
                    ("item",),
                    title=f"{item['account_code']} — {item['account_name']}",
                    account_ids=[item["account_id"]],
                    start_date=start_date,
                    end_date=end_date,
                )
            self._insert_report_row(
                self.pl_tree,
                ("", "TOTAL COST OF GOODS SOLD", "", f"{d['total_cost_of_sales']:,.2f}"),
                ("subtotal",),
                title="Total Cost of Goods Sold",
                account_ids=cost_ids,
                start_date=start_date,
                end_date=end_date,
            )

        self._insert_report_row(
            self.pl_tree,
            ("", "GROSS PROFIT", f"{d['gross_profit_margin_pct']:.2f}%", f"{d['gross_profit']:,.2f}"),
            ("subtotal",),
            title="Gross Profit Detail",
            account_ids=revenue_ids + cost_ids,
            start_date=start_date,
            end_date=end_date,
        )

        self._insert_report_row(
            self.pl_tree, ("", "OPERATING EXPENSES", "", ""), ("section",)
        )
        for category, items in d["expenses_by_category"].items():
            for item in items:
                self._insert_report_row(
                    self.pl_tree,
                    (
                        item["account_code"],
                        f"{item['account_name']} ({category})",
                        f"{item['pct_of_revenue']:.2f}%",
                        f"{item['amount']:,.2f}",
                    ),
                    ("item",),
                    title=f"{item['account_code']} — {item['account_name']}",
                    account_ids=[item["account_id"]],
                    start_date=start_date,
                    end_date=end_date,
                )
        self._insert_report_row(
            self.pl_tree,
            ("", "TOTAL OPERATING EXPENSES", "", f"{d['total_operating_expenses']:,.2f}"),
            ("subtotal",),
            title="Total Operating Expenses",
            account_ids=expense_ids,
            start_date=start_date,
            end_date=end_date,
        )
        self._insert_report_row(
            self.pl_tree,
            ("", "OPERATING PROFIT (EBIT)", "", f"{d['operating_profit']:,.2f}"),
            ("subtotal",),
            title="Operating Profit Detail",
            account_ids=revenue_ids + cost_ids + expense_ids,
            start_date=start_date,
            end_date=end_date,
        )

        if d["other_income"]:
            self._insert_report_row(
                self.pl_tree,
                ("", "OTHER INCOME & DISCOUNTS RECEIVED", "", ""),
                ("section",),
            )
            for item in d["other_income"]:
                self._insert_report_row(
                    self.pl_tree,
                    (
                        item["account_code"],
                        item["account_name"],
                        f"{item['pct_of_revenue']:.2f}%",
                        f"{item['amount']:,.2f}",
                    ),
                    ("item",),
                    title=f"{item['account_code']} — {item['account_name']}",
                    account_ids=[item["account_id"]],
                    start_date=start_date,
                    end_date=end_date,
                )
            self._insert_report_row(
                self.pl_tree,
                ("", "TOTAL OTHER INCOME", "", f"{d['total_other_income']:,.2f}"),
                ("subtotal",),
                title="Total Other Income",
                account_ids=other_income_ids,
                start_date=start_date,
                end_date=end_date,
            )

        status = "NET PROFIT FOR THE PERIOD" if d["is_profit"] else "NET LOSS FOR THE PERIOD"
        tag = "profit" if d["is_profit"] else "loss"
        self._insert_report_row(
            self.pl_tree,
            ("", status, f"{d['net_profit_margin_pct']:.2f}%", f"{d['net_profit']:,.2f}"),
            (tag,),
            title=status.title(),
            account_ids=revenue_ids + cost_ids + expense_ids + other_income_ids,
            start_date=start_date,
            end_date=end_date,
        )
    def _render_bs(self):
        self._clear_report_tree(self.bs_tree)
        d = self.bs_data
        if not d:
            return

        end_date = d["as_of_date"]
        current_asset_ids = self._account_ids(d["current_assets"])
        non_current_asset_ids = self._account_ids(d["non_current_assets"])
        current_liability_ids = self._account_ids(d["current_liabilities"])
        long_term_liability_ids = self._account_ids(d["long_term_liabilities"])
        equity_ids = self._account_ids(d["equity_items"])
        earnings_ids = [
            account["id"]
            for account in db.get_chart_of_accounts(
                company_id=self.company_id,
                active_only=False,
            )
            if account.get("account_type") in ("Income", "Expense")
        ]

        self.bs_kpi_assets.config(text=f"{self.currency} {d['total_assets']:,.2f}")
        self.bs_kpi_liab.config(text=f"{self.currency} {d['total_liabilities']:,.2f}")
        self.bs_kpi_eq.config(text=f"{self.currency} {d['total_equity']:,.2f}")
        self.bs_kpi_status.config(
            text="Balanced ✓ (A = L + E)"
            if d["is_balanced"]
            else f"Diff: {d['difference']:,.2f}"
        )

        def add_account_rows(items):
            for item in items:
                account_ids = (
                    [item["account_id"]]
                    if item.get("account_id")
                    else earnings_ids
                )
                self._insert_report_row(
                    self.bs_tree,
                    (
                        item.get("account_code") or "",
                        item["account_name"],
                        item["sub_category"],
                        f"{item['amount']:,.2f}",
                    ),
                    ("item",),
                    title=f"{item.get('account_code') or 'Earnings'} — {item['account_name']}",
                    account_ids=account_ids,
                    end_date=end_date,
                )

        self._insert_report_row(self.bs_tree, ("", "1. ASSETS", "", ""), ("section",))
        self._insert_report_row(self.bs_tree, ("", "Current Assets", "", ""), ("section",))
        add_account_rows(d["current_assets"])
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL CURRENT ASSETS", "", f"{d['total_current_assets']:,.2f}"),
            ("subtotal",),
            title="Total Current Assets",
            account_ids=current_asset_ids,
            end_date=end_date,
        )
        if d["non_current_assets"]:
            self._insert_report_row(
                self.bs_tree, ("", "Non-Current Assets", "", ""), ("section",)
            )
            add_account_rows(d["non_current_assets"])
            self._insert_report_row(
                self.bs_tree,
                ("", "TOTAL NON-CURRENT ASSETS", "", f"{d['total_non_current_assets']:,.2f}"),
                ("subtotal",),
                title="Total Non-Current Assets",
                account_ids=non_current_asset_ids,
                end_date=end_date,
            )
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL ASSETS", "", f"{d['total_assets']:,.2f}"),
            ("grand_total",),
            title="Total Assets",
            account_ids=current_asset_ids + non_current_asset_ids,
            end_date=end_date,
        )

        self._insert_report_row(self.bs_tree, ("", "2. LIABILITIES", "", ""), ("section",))
        self._insert_report_row(
            self.bs_tree, ("", "Current Liabilities", "", ""), ("section",)
        )
        add_account_rows(d["current_liabilities"])
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL CURRENT LIABILITIES", "", f"{d['total_current_liabilities']:,.2f}"),
            ("subtotal",),
            title="Total Current Liabilities",
            account_ids=current_liability_ids,
            end_date=end_date,
        )
        if d["long_term_liabilities"]:
            self._insert_report_row(
                self.bs_tree, ("", "Long-Term Liabilities", "", ""), ("section",)
            )
            add_account_rows(d["long_term_liabilities"])
            self._insert_report_row(
                self.bs_tree,
                ("", "TOTAL LONG-TERM LIABILITIES", "", f"{d['total_long_term_liabilities']:,.2f}"),
                ("subtotal",),
                title="Total Long-Term Liabilities",
                account_ids=long_term_liability_ids,
                end_date=end_date,
            )
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL LIABILITIES", "", f"{d['total_liabilities']:,.2f}"),
            ("subtotal",),
            title="Total Liabilities",
            account_ids=current_liability_ids + long_term_liability_ids,
            end_date=end_date,
        )

        self._insert_report_row(self.bs_tree, ("", "3. EQUITY", "", ""), ("section",))
        add_account_rows(d["equity_items"])
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL EQUITY", "", f"{d['total_equity']:,.2f}"),
            ("subtotal",),
            title="Total Equity",
            account_ids=equity_ids + earnings_ids,
            end_date=end_date,
        )
        tag = "profit" if d["is_balanced"] else "loss"
        self._insert_report_row(
            self.bs_tree,
            ("", "TOTAL LIABILITIES & EQUITY", "", f"{d['total_liabilities_and_equity']:,.2f}"),
            (tag,),
            title="Total Liabilities and Equity",
            account_ids=current_liability_ids + long_term_liability_ids + equity_ids + earnings_ids,
            end_date=end_date,
        )
    def _render_tb(self):
        self._clear_report_tree(self.tb_tree)
        d = self.tb_data
        if not d:
            return

        total_debit = float(d.get("total_debit", 0.0))
        total_credit = float(d.get("total_credit", 0.0))
        difference = float(d.get("difference", 0.0))
        is_balanced = bool(d.get("is_balanced", False))
        end_date = d.get("as_of_date")

        self.tb_kpi_deb.config(text=f"{self.currency} {total_debit:,.2f}")
        self.tb_kpi_cred.config(text=f"{self.currency} {total_credit:,.2f}")
        self.tb_kpi_diff.config(text=f"{self.currency} {difference:,.2f}")
        self.tb_kpi_status.config(
            text="Balanced ✓" if is_balanced else f"Out of Balance ({difference:,.2f})"
        )

        visible_account_ids = []
        for account in d.get("accounts", []):
            debit = float(account.get("debit", 0.0))
            credit = float(account.get("credit", 0.0))
            if debit == 0.0 and credit == 0.0:
                continue
            visible_account_ids.append(account["id"])
            self._insert_report_row(
                self.tb_tree,
                (
                    account.get("account_code", ""),
                    f"{account.get('account_name', '')} ({account.get('account_type', '')})",
                    f"{debit:,.2f}" if debit > 0 else "-",
                    f"{credit:,.2f}" if credit > 0 else "-",
                ),
                ("item",),
                title=f"{account.get('account_code', '')} — {account.get('account_name', '')}",
                account_ids=[account["id"]],
                end_date=end_date,
            )

        tag = "profit" if is_balanced else "loss"
        self._insert_report_row(
            self.tb_tree,
            ("", "TOTAL TRIAL BALANCE", f"{total_debit:,.2f}", f"{total_credit:,.2f}"),
            (tag,),
            title="Total Trial Balance",
            account_ids=visible_account_ids,
            end_date=end_date,
        )
    def _render_cf(self):
        self._clear_report_tree(self.cf_tree)
        d = self.cf_data
        if not d:
            return

        start_date = d["period"]["start_date"]
        end_date = d["period"]["end_date"]
        prior_date = (
            datetime.strptime(start_date, "%Y-%m-%d").date() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        cash_account_ids = self._account_ids(d["account_breakdown"])
        inflow_entry_ids = [item["entry_id"] for item in d["inflows"]]
        outflow_entry_ids = [item["entry_id"] for item in d["outflows"]]

        self.cf_kpi_beg.config(text=f"{self.currency} {d['beginning_cash']:,.2f}")
        self.cf_kpi_in.config(text=f"{self.currency} {d['total_inflows']:,.2f}")
        self.cf_kpi_out.config(text=f"{self.currency} {d['total_outflows']:,.2f}")
        self.cf_kpi_end.config(text=f"{self.currency} {d['ending_cash']:,.2f}")

        self._insert_report_row(
            self.cf_tree,
            ("", "BEGINNING CASH & BANK POSITION", "", f"{d['beginning_cash']:,.2f}"),
            ("section",),
            title="Beginning Cash and Bank Position",
            account_ids=cash_account_ids,
            end_date=prior_date,
        )
        self._insert_report_row(
            self.cf_tree,
            ("", "CASH INFLOWS (COLLECTIONS & RECEIPTS)", "", ""),
            ("section",),
        )
        for item in d["inflows"]:
            self._insert_report_row(
                self.cf_tree,
                (
                    f"{item['date']} ({item['entry_number']})",
                    item["description"],
                    item["account"],
                    f"{item['amount']:,.2f}",
                ),
                ("item",),
                title=f"Cash Inflow — {item['entry_number']}",
                entry_ids=[item["entry_id"]],
                start_date=start_date,
                end_date=end_date,
            )
        self._insert_report_row(
            self.cf_tree,
            ("", "TOTAL CASH INFLOWS", "", f"{d['total_inflows']:,.2f}"),
            ("subtotal",),
            title="Total Cash Inflows",
            entry_ids=inflow_entry_ids,
            start_date=start_date,
            end_date=end_date,
        )

        self._insert_report_row(
            self.cf_tree,
            ("", "CASH OUTFLOWS (DISBURSEMENTS & EXPENSES)", "", ""),
            ("section",),
        )
        for item in d["outflows"]:
            self._insert_report_row(
                self.cf_tree,
                (
                    f"{item['date']} ({item['entry_number']})",
                    item["description"],
                    item["account"],
                    f"{item['amount']:,.2f}",
                ),
                ("item",),
                title=f"Cash Outflow — {item['entry_number']}",
                entry_ids=[item["entry_id"]],
                start_date=start_date,
                end_date=end_date,
            )
        self._insert_report_row(
            self.cf_tree,
            ("", "TOTAL CASH OUTFLOWS", "", f"{d['total_outflows']:,.2f}"),
            ("subtotal",),
            title="Total Cash Outflows",
            entry_ids=outflow_entry_ids,
            start_date=start_date,
            end_date=end_date,
        )
        self._insert_report_row(
            self.cf_tree,
            ("", "NET CHANGE IN CASH & BANK", "", f"{d['net_change']:,.2f}"),
            ("subtotal",),
            title="Net Change in Cash and Bank",
            entry_ids=inflow_entry_ids + outflow_entry_ids,
            start_date=start_date,
            end_date=end_date,
        )
        self._insert_report_row(
            self.cf_tree,
            ("", "ENDING CASH & BANK POSITION", "", f"{d['ending_cash']:,.2f}"),
            ("grand_total",),
            title="Ending Cash and Bank Position",
            account_ids=cash_account_ids,
            end_date=end_date,
        )

        self._insert_report_row(
            self.cf_tree,
            ("", "ACCOUNT BREAKDOWN AT PERIOD END", "", ""),
            ("section",),
        )
        for account in d["account_breakdown"]:
            self._insert_report_row(
                self.cf_tree,
                (
                    account["code"],
                    account["name"],
                    "",
                    f"{account['balance']:,.2f}",
                ),
                ("item",),
                title=f"{account['code']} — {account['name']}",
                account_ids=[account["account_id"]],
                end_date=end_date,
            )
    def _update_kpis_for_active_tab(self):
        pass

    # =========================================================================
    # PDF & CSV Export Handlers
    # =========================================================================
    def _export_pdf(self):
        tab_idx = self.notebook.index(self.notebook.select())
        names = ["Profit & Loss Statement", "Balance Sheet", "Trial Balance", "Cash Flow Statement"]
        report_name = names[tab_idx]

        file_types = [("PDF Document", "*.pdf")]
        default_file = f"{report_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
        out_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save {report_name} PDF",
            defaultextension=".pdf",
            initialfile=default_file,
            filetypes=file_types
        )
        if not out_path:
            return

        try:
            if tab_idx == 0:
                generate_profit_loss_pdf(self.pl_data, output_path=out_path)
            elif tab_idx == 1:
                generate_balance_sheet_pdf(self.bs_data, output_path=out_path)
            elif tab_idx == 2:
                generate_trial_balance_pdf(self.tb_data, output_path=out_path)
            elif tab_idx == 3:
                generate_cash_flow_pdf(self.cf_data, output_path=out_path)

            if messagebox.askyesno("PDF Export Success", f"{report_name} exported successfully!\n\nLocation: {out_path}\n\nWould you like to open it now?", parent=self):
                self._open_file(out_path)
        except Exception as e:
            messagebox.showerror("PDF Export Error", f"Failed to generate {report_name} PDF:\n{e}", parent=self)

    def _export_csv(self):
        tab_idx = self.notebook.index(self.notebook.select())
        names = ["Profit & Loss", "Balance Sheet", "Trial Balance", "Cash Flow"]
        report_name = names[tab_idx]

        file_types = [("CSV Spreadsheet", "*.csv")]
        default_file = f"{report_name.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
        out_path = filedialog.asksaveasfilename(
            parent=self,
            title=f"Save {report_name} CSV",
            defaultextension=".csv",
            initialfile=default_file,
            filetypes=file_types
        )
        if not out_path:
            return

        try:
            if tab_idx == 0:
                export_profit_loss_csv(self.pl_data, output_path=out_path)
            elif tab_idx == 1:
                export_balance_sheet_csv(self.bs_data, output_path=out_path)
            elif tab_idx == 2:
                # Export trial balance CSV
                import csv
                with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow([self.comp_profile.get("name", "Main Enterprise")])
                    writer.writerow(["TRIAL BALANCE"])
                    writer.writerow([f"As of: {self.tb_data.get('as_of_date', '')}"])
                    writer.writerow([])
                    writer.writerow(["Account Code", "Account Name", f"Debit ({self.currency})", f"Credit ({self.currency})"])
                    for a in self.tb_data.get("accounts", []):
                        d_val = float(a.get("debit", 0.0))
                        c_val = float(a.get("credit", 0.0))
                        if d_val > 0 or c_val > 0:
                            writer.writerow([a.get("account_code", ""), a.get("account_name", ""), f"{d_val:.2f}", f"{c_val:.2f}"])
                    writer.writerow(["TOTAL", "", f"{self.tb_data.get('total_debit', 0.0):.2f}", f"{self.tb_data.get('total_credit', 0.0):.2f}"])
            elif tab_idx == 3:
                export_cash_flow_csv(self.cf_data, output_path=out_path)

            messagebox.showinfo("CSV Export Success", f"{report_name} exported successfully to:\n{out_path}", parent=self)
        except Exception as e:
            messagebox.showerror("CSV Export Error", f"Failed to export CSV:\n{e}", parent=self)

    def _print_report(self):
        tab_idx = self.notebook.index(self.notebook.select())
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()

        try:
            if tab_idx == 0:
                pdf_path = generate_profit_loss_pdf(self.pl_data, os.path.join(temp_dir, f"print_pl_{ts}.pdf"))
            elif tab_idx == 1:
                pdf_path = generate_balance_sheet_pdf(self.bs_data, os.path.join(temp_dir, f"print_bs_{ts}.pdf"))
            elif tab_idx == 2:
                pdf_path = generate_trial_balance_pdf(self.tb_data, os.path.join(temp_dir, f"print_tb_{ts}.pdf"))
            elif tab_idx == 3:
                pdf_path = generate_cash_flow_pdf(self.cf_data, os.path.join(temp_dir, f"print_cf_{ts}.pdf"))

            self._open_file(pdf_path)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to prepare report for printing:\n{e}", parent=self)

    def _open_file(self, file_path):
        if not os.path.exists(file_path):
            return
        try:
            if os.name == "nt":
                os.startfile(file_path)
            else:
                subprocess.Popen(["xdg-open", file_path])
        except Exception as e:
            messagebox.showinfo("Report Ready", f"File created at:\n{file_path}\n\nCould not launch viewer automatically: {e}", parent=self)


class FinancialReportsFrame(tb.Frame):
    """Full-page financial statements workspace embedded in the main window."""

    PRESETS = FinancialReportsDialog.PRESETS

    def __init__(self, parent, company_id=None, initial_tab=0, on_close=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.comp_profile = db.get_company(self.company_id) or {}
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"
        self.on_close = on_close
        self.pl_data = None
        self.bs_data = None
        self.tb_data = None
        self.cf_data = None
        self._drilldown_rows = {}
        self._init_date_defaults()
        self._build_ui(initial_tab)
        self._refresh_all_reports()

    def show_report(self, initial_tab=0):
        """Select a report tab and refresh all statement balances."""
        if 0 <= initial_tab < 4:
            self.notebook.select(initial_tab)
        self._refresh_all_reports()


_FINANCIAL_REPORT_FRAME_METHODS = tuple(
    name for name, value in FinancialReportsDialog.__dict__.items()
    if callable(value) and name not in {"__init__", "center_window"}
)
for _method_name in _FINANCIAL_REPORT_FRAME_METHODS:
    setattr(
        FinancialReportsFrame,
        _method_name,
        FinancialReportsDialog.__dict__[_method_name],
    )