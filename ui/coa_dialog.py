"""
ui/coa_dialog.py
Chart of Accounts (COA) Management Interface for Voucher Machine SME Bookkeeping v3.5.

Provides:
- ChartOfAccountsDialog: Full COA explorer with category grouping, filtering,
  search, account creation/editing, ledger navigation, and CSV export.
- AccountEditModal: Clean modal dialog for adding or editing accounts with
  normal balance auto-assignment.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db


class AccountEditModal(tb.Toplevel):
    """Modal for creating or editing an account in the Chart of Accounts."""

    ACCOUNT_TYPES = ["Asset", "Liability", "Equity", "Revenue", "Expense"]
    NORMAL_BALANCES = {
        "Asset": "Debit",
        "Expense": "Debit",
        "Liability": "Credit",
        "Equity": "Credit",
        "Revenue": "Credit"
    }

    STANDARD_SUB_CATEGORIES = {
        "Asset": [
            "Current Assets - Cash & Cash Equivalents",
            "Current Assets - Bank Accounts",
            "Current Assets - Accounts Receivable (Trade Debtors)",
            "Current Assets - Inventory / Stock",
            "Current Assets - Prepaid Expenses & Advances",
            "Current Assets - Short-Term Investments",
            "Current Assets - Other Current Assets",
            "Fixed Assets - Property, Plant & Equipment",
            "Fixed Assets - Land & Buildings",
            "Fixed Assets - Office Equipment & Computers",
            "Fixed Assets - Furniture & Fixtures",
            "Fixed Assets - Motor Vehicles",
            "Fixed Assets - Accumulated Depreciation (Contra)",
            "Non-Current Assets - Long-Term Investments",
            "Non-Current Assets - Intangible Assets & Goodwill",
            "Non-Current Assets - Other Non-Current Assets"
        ],
        "Liability": [
            "Current Liabilities - Accounts Payable (Trade Creditors)",
            "Current Liabilities - Short-Term Loans & Overdrafts",
            "Current Liabilities - Accrued Expenses",
            "Current Liabilities - Payroll Liabilities & Withholdings",
            "Current Liabilities - Taxes Payable (VAT / GST / Income Tax)",
            "Current Liabilities - Customer Advances / Unearned Revenue",
            "Current Liabilities - Other Current Liabilities",
            "Non-Current Liabilities - Long-Term Bank Loans",
            "Non-Current Liabilities - Mortgages Payable",
            "Non-Current Liabilities - Bonds / Debentures Payable",
            "Non-Current Liabilities - Deferred Tax Liabilities",
            "Non-Current Liabilities - Other Long-Term Liabilities"
        ],
        "Equity": [
            "Equity - Owner's Capital / Share Capital",
            "Equity - Retained Earnings",
            "Equity - Owner's Drawings / Dividends",
            "Equity - General & Statutory Reserves",
            "Equity - Additional Paid-in Capital",
            "Equity - Current Year Profit / Loss"
        ],
        "Revenue": [
            "Operating Revenue - Sales Revenue",
            "Operating Revenue - Service & Fee Income",
            "Operating Revenue - Commissions & Contracts",
            "Non-Operating Income - Interest & Investment Income",
            "Non-Operating Income - Discounts Received",
            "Non-Operating Income - Gain on Asset Disposal",
            "Non-Operating Income - Miscellaneous Income"
        ],
        "Expense": [
            "Cost of Goods Sold (COGS) - Direct Materials",
            "Cost of Goods Sold (COGS) - Direct Labor & Freight",
            "Operating Expenses - Salaries & Employee Benefits",
            "Operating Expenses - Rent & Occupancy Costs",
            "Operating Expenses - Utilities (Electricity, Water, Internet)",
            "Operating Expenses - Office Supplies & Stationery",
            "Operating Expenses - Advertising & Marketing",
            "Operating Expenses - Travel & Transportation",
            "Operating Expenses - Repairs & Maintenance",
            "Operating Expenses - Professional & Legal Fees",
            "Operating Expenses - Bank Charges & Payment Processing",
            "Operating Expenses - Insurance",
            "Operating Expenses - Depreciation & Amortization",
            "Operating Expenses - Taxes & Licenses",
            "Other Expenses - General & Miscellaneous"
        ]
    }

    def __init__(self, parent, company_id=None, account_data=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.account_data = account_data or {}
        self.on_saved = on_saved
        self.is_edit = bool(self.account_data.get("id"))
        self._parent_map = {}

        self.title("Edit Account" if self.is_edit else "Add New Account")
        self.geometry("560x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._populate_fields()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        container = tb.Frame(self, padding=20)
        container.pack(fill=BOTH, expand=True)

        header_title = "Edit Ledger Account" if self.is_edit else "Create New Ledger Account"
        header_desc = "Configure account classification, parent/sub-account hierarchy, and balance rules."
        tb.Label(container, text=header_title, font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(container, text=header_desc, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 14))

        form = tb.Frame(container)
        form.pack(fill=BOTH, expand=True)

        # 0. Account Type
        tb.Label(form, text="Account Type:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=5)
        self.type_var = tk.StringVar(value="Expense")
        self.type_combo = tb.Combobox(form, textvariable=self.type_var, values=self.ACCOUNT_TYPES, state="readonly", width=32)
        self.type_combo.grid(row=0, column=1, sticky=EW, pady=5, padx=(10, 0))
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_changed)

        # 1. Parent Account (Sub-account of)
        tb.Label(form, text="Sub-account of:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky=W, pady=5)
        self.parent_var = tk.StringVar(value="None (Top-Level Account)")
        self.parent_combo = tb.Combobox(form, textvariable=self.parent_var, state="readonly", width=32)
        self.parent_combo.grid(row=1, column=1, sticky=EW, pady=5, padx=(10, 0))

        # 2. Account Code
        tb.Label(form, text="Account Code:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky=W, pady=5)
        self.code_var = tk.StringVar()
        self.code_entry = tb.Entry(form, textvariable=self.code_var, width=32)
        self.code_entry.grid(row=2, column=1, sticky=EW, pady=5, padx=(10, 0))

        # 3. Account Name
        tb.Label(form, text="Account Name:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky=W, pady=5)
        self.name_var = tk.StringVar()
        self.name_entry = tb.Entry(form, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=3, column=1, sticky=EW, pady=5, padx=(10, 0))

        # 4. Classified Balance Sheet / Income Statement Sub-Category
        tb.Label(form, text="Sub-Category:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky=W, pady=5)
        self.subcat_var = tk.StringVar()
        init_subcats = self.STANDARD_SUB_CATEGORIES.get("Expense", [])
        self.subcat_combo = tb.Combobox(form, textvariable=self.subcat_var, values=init_subcats, width=32)
        self.subcat_combo.grid(row=4, column=1, sticky=EW, pady=5, padx=(10, 0))

        # 5. Normal Balance
        tb.Label(form, text="Normal Balance:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky=W, pady=5)
        self.normal_bal_var = tk.StringVar(value="Debit")
        self.normal_combo = tb.Combobox(form, textvariable=self.normal_bal_var, values=["Debit", "Credit"], state="readonly", width=32)
        self.normal_combo.grid(row=5, column=1, sticky=EW, pady=5, padx=(10, 0))

        # 6. Active Status
        self.is_active_var = tk.BooleanVar(value=True)
        self.active_check = tb.Checkbutton(form, text="Active Account", variable=self.is_active_var, bootstyle="round-toggle")
        self.active_check.grid(row=6, column=1, sticky=W, pady=8, padx=(10, 0))

        # 7. Notes / Memo
        tb.Label(form, text="Notes / Memo:", font=("Segoe UI", 9)).grid(row=7, column=0, sticky=NW, pady=5)
        self.notes_entry = tb.Entry(form, width=32)
        self.notes_entry.grid(row=7, column=1, sticky=EW, pady=5, padx=(10, 0))

        form.columnconfigure(1, weight=1)

        # Action Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        save_btn = tb.Button(btn_box, text="Save Account", bootstyle="primary", command=self._save)
        save_btn.pack(side=RIGHT)

        # Load initial parents
        self._reload_parent_accounts()

    def _reload_parent_accounts(self):
        """Reload parent accounts matching current account type from active company COA."""
        atype = self.type_var.get()
        exclude_id = self.account_data.get("id") if self.is_edit else None
        parents = db.get_available_parent_accounts(
            company_id=self.company_id,
            account_type=atype,
            exclude_account_id=exclude_id
        )

        self._parent_map = {"None (Top-Level Account)": None}
        items = ["None (Top-Level Account)"]
        for p in parents:
            label = f"[{p['account_code']}] {p['account_name']}"
            items.append(label)
            self._parent_map[label] = p["id"]

        self.parent_combo["values"] = items

        # Preserve selection or set default
        curr_label = self.parent_var.get()
        if curr_label not in self._parent_map:
            self.parent_var.set("None (Top-Level Account)")

    def _on_type_changed(self, event=None):
        atype = self.type_var.get()
        # Normal balance rules: Asset & Expense default + is Debit, Liability, Equity & Revenue default + is Credit
        rec_bal = self.NORMAL_BALANCES.get(atype, "Debit")
        self.normal_bal_var.set(rec_bal)

        # Update sub-category classified options
        subcats = self.STANDARD_SUB_CATEGORIES.get(atype, [])
        self.subcat_combo["values"] = subcats
        if subcats:
            self.subcat_var.set(subcats[0])

        # Reload available parent accounts of this type
        self._reload_parent_accounts()

    def _populate_fields(self):
        if not self.account_data:
            # New account defaults
            subcats = self.STANDARD_SUB_CATEGORIES.get(self.type_var.get(), [])
            if subcats:
                self.subcat_var.set(subcats[0])
            return

        self.code_var.set(self.account_data.get("account_code", ""))
        self.name_var.set(self.account_data.get("account_name", ""))
        self.type_var.set(self.account_data.get("account_type", "Expense"))

        # Sub-category values based on type
        atype = self.account_data.get("account_type", "Expense")
        self.subcat_combo["values"] = self.STANDARD_SUB_CATEGORIES.get(atype, [])
        self.subcat_var.set(self.account_data.get("sub_category", "") or "")

        self.normal_bal_var.set(self.account_data.get("normal_balance", "Debit"))
        self.is_active_var.set(bool(self.account_data.get("is_active", 1)))
        if self.account_data.get("notes"):
            self.notes_entry.insert(0, self.account_data["notes"])

        # Reload parents and select existing parent
        self._reload_parent_accounts()
        curr_parent_id = self.account_data.get("parent_id")
        if curr_parent_id:
            for lbl, pid in self._parent_map.items():
                if pid == curr_parent_id:
                    self.parent_var.set(lbl)
                    break

        if self.account_data.get("is_system"):
            self.code_entry.configure(state="disabled")
            self.type_combo.configure(state="disabled")

    def _save(self):
        code = self.code_var.get().strip()
        name = self.name_var.get().strip()
        atype = self.type_var.get().strip()
        subcat = self.subcat_var.get().strip()
        norm_bal = self.normal_bal_var.get().strip()
        is_active = 1 if self.is_active_var.get() else 0
        notes = self.notes_entry.get().strip()
        parent_label = self.parent_var.get()
        parent_id = self._parent_map.get(parent_label)

        if not code:
            messagebox.showwarning("Validation Error", "Account Code is required.", parent=self)
            self.code_entry.focus_set()
            return
        if not name:
            messagebox.showwarning("Validation Error", "Account Name is required.", parent=self)
            self.name_entry.focus_set()
            return

        payload = {
            "company_id": self.company_id,
            "account_code": code,
            "account_name": name,
            "account_type": atype,
            "sub_category": subcat,
            "parent_id": parent_id,
            "normal_balance": norm_bal,
            "is_active": is_active,
            "notes": notes
        }

        try:
            if self.is_edit:
                account_id = self.account_data["id"]
                db.update_account(account_id, payload)
            else:
                db.create_account(payload)

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error Saving Account", str(e), parent=self)


class ChartOfAccountsDialog(tb.Toplevel):
    """Full-featured Chart of Accounts Management Window."""

    TYPE_BADGES = {
        "Asset": "info",
        "Liability": "warning",
        "Equity": "primary",
        "Revenue": "success",
        "Expense": "danger"
    }

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Chart of Accounts — General Ledger Master")
        self.geometry("1020x640")
        self.minsize(860, 520)
        self.transient(parent)

        self._build_ui()
        self.refresh()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        # Header bar
        header_frame = tb.Frame(root)
        header_frame.pack(fill=X, pady=(0, 12))

        title_box = tb.Frame(header_frame)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="📒 Chart of Accounts", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        self.status_sublabel = tb.Label(
            title_box,
            text="Standard 5-group SME Double-Entry Chart of Accounts",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        )
        self.status_sublabel.pack(anchor=W)

        # Top Action Buttons
        top_btn_box = tb.Frame(header_frame)
        top_btn_box.pack(side=RIGHT)

        tb.Button(
            top_btn_box,
            text="📖 Open General Ledger",
            bootstyle="info-outline",
            command=self._open_general_ledger
        ).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_btn_box,
            text="➕ New Account",
            bootstyle="success",
            command=self._create_new_account
        ).pack(side=LEFT)

        # Search & Filter Toolbar
        toolbar = tb.Labelframe(root, text="Filter & Search", padding=10)
        toolbar.pack(fill=X, pady=(0, 12))

        tb.Label(toolbar, text="Search:").pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = tb.Entry(toolbar, textvariable=self.search_var, width=24)
        search_entry.pack(side=LEFT, padx=(0, 14))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        tb.Label(toolbar, text="Type:").pack(side=LEFT, padx=(0, 4))
        self.type_filter_var = tk.StringVar(value="All Types")
        type_options = ["All Types", "Asset", "Liability", "Equity", "Revenue", "Expense"]
        type_combo = tb.Combobox(toolbar, textvariable=self.type_filter_var, values=type_options, state="readonly", width=14)
        type_combo.pack(side=LEFT, padx=(0, 14))
        type_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        self.active_only_var = tk.BooleanVar(value=False)
        tb.Checkbutton(
            toolbar,
            text="Active Accounts Only",
            variable=self.active_only_var,
            bootstyle="round-toggle",
            command=self.refresh
        ).pack(side=LEFT, padx=(0, 14))

        tb.Button(toolbar, text="Reset", bootstyle="secondary-outline", command=self._reset_filters).pack(side=LEFT)
        tb.Button(toolbar, text="📥 Export CSV", bootstyle="outline", command=self._export_csv).pack(side=RIGHT)

        # Main Table (Treeview)
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "type", "sub_category", "parent", "normal_balance", "is_system", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("code", text="Account Code", anchor=W, command=lambda: self._sort_column("account_code"))
        self.tree.heading("name", text="Account Name", anchor=W, command=lambda: self._sort_column("account_name"))
        self.tree.heading("type", text="Type", anchor=W, command=lambda: self._sort_column("account_type"))
        self.tree.heading("sub_category", text="Sub-Category", anchor=W)
        self.tree.heading("parent", text="Parent Ledger", anchor=W)
        self.tree.heading("normal_balance", text="Normal Balance", anchor=CENTER)
        self.tree.heading("is_system", text="System", anchor=CENTER)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("code", width=100, minwidth=80, anchor=W)
        self.tree.column("name", width=220, minwidth=160, anchor=W)
        self.tree.column("type", width=95, minwidth=80, anchor=W)
        self.tree.column("sub_category", width=160, minwidth=110, anchor=W)
        self.tree.column("parent", width=160, minwidth=110, anchor=W)
        self.tree.column("normal_balance", width=105, minwidth=85, anchor=CENTER)
        self.tree.column("is_system", width=75, minwidth=60, anchor=CENTER)
        self.tree.column("status", width=85, minwidth=65, anchor=CENTER)

        v_scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=v_scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        v_scroll.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_selected_account())

        # Bottom Action Bar
        bottom_bar = tb.Frame(root, padding=(0, 10, 0, 0))
        bottom_bar.pack(fill=X)

        tb.Button(bottom_bar, text="✏️ Edit Account", bootstyle="primary-outline", command=self._edit_selected_account).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="🔄 Toggle Active", bootstyle="secondary-outline", command=self._toggle_active).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="🗑️ Delete Account", bootstyle="danger-outline", command=self._delete_account).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="📖 View Account Ledger", bootstyle="info", command=self._view_account_ledger).pack(side=LEFT)

        tb.Button(bottom_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

        self.accounts_cache = []
        self.sort_col = "account_code"
        self.sort_desc = False

    def _reset_filters(self):
        self.search_var.set("")
        self.type_filter_var.set("All Types")
        self.active_only_var.set(False)
        self.refresh()

    def refresh(self):
        type_flt = self.type_filter_var.get()
        if type_flt == "All Types":
            type_flt = None

        active_flt = self.active_only_var.get()
        accounts = db.get_chart_of_accounts(
            company_id=self.company_id,
            account_type=type_flt,
            active_only=active_flt
        )

        query = self.search_var.get().strip().lower()
        if query:
            accounts = [
                a for a in accounts
                if query in a["account_code"].lower()
                or query in a["account_name"].lower()
                or query in (a.get("sub_category") or "").lower()
            ]

        # Apply sorting
        accounts.sort(key=lambda x: str(x.get(self.sort_col, "")).lower(), reverse=self.sort_desc)
        self.accounts_cache = accounts

        # Populate tree
        for row in self.tree.get_children():
            self.tree.delete(row)

        for a in accounts:
            sys_str = "🔒 Yes" if a["is_system"] else "No"
            status_str = "Active" if a["is_active"] else "Inactive"
            subcat = a.get("sub_category") or "—"
            parent_code = a.get("parent_code")
            parent_name = a.get("parent_name")
            if parent_code and parent_name:
                parent_str = f"[{parent_code}] {parent_name}"
                disp_name = f"  ↳ {a['account_name']}"
            else:
                parent_str = "—"
                disp_name = a["account_name"]

            item_id = self.tree.insert(
                "",
                END,
                iid=str(a["id"]),
                values=(
                    a["account_code"],
                    disp_name,
                    a["account_type"],
                    subcat,
                    parent_str,
                    a["normal_balance"],
                    sys_str,
                    status_str
                )
            )

        self.status_sublabel.config(
            text=f"Displaying {len(accounts)} accounts for Company #{self.company_id}"
        )

    def _sort_column(self, col):
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = col
            self.sort_desc = False
        self.refresh()

    def _get_selected_account(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select an account first.", parent=self)
            return None
        acct_id = int(selected[0])
        return next((a for a in self.accounts_cache if a["id"] == acct_id), None)

    def _create_new_account(self):
        AccountEditModal(self, company_id=self.company_id, on_saved=self.refresh)

    def _edit_selected_account(self):
        acct = self._get_selected_account()
        if not acct:
            return
        AccountEditModal(self, company_id=self.company_id, account_data=acct, on_saved=self.refresh)

    def _toggle_active(self):
        acct = self._get_selected_account()
        if not acct:
            return
        new_active = 0 if acct["is_active"] else 1
        new_status_str = "Inactive" if new_active == 0 else "Active"
        try:
            db.update_account(acct["id"], {"is_active": new_active})
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _delete_account(self):
        acct = self._get_selected_account()
        if not acct:
            return

        if acct["is_system"]:
            messagebox.showerror(
                "Protected Account",
                f"'{acct['account_code']} - {acct['account_name']}' is a default system account and cannot be deleted.",
                parent=self
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete account '{acct['account_code']} - {acct['account_name']}'?\n\n"
            "This action cannot be undone.",
            parent=self
        )
        if not confirm:
            return

        success, msg = db.delete_account(acct["id"])
        if success:
            messagebox.showinfo("Deleted", msg, parent=self)
            self.refresh()
        else:
            messagebox.showerror("Cannot Delete", msg, parent=self)

    def _open_general_ledger(self):
        from ui.journal_dialog import GeneralLedgerDialog
        GeneralLedgerDialog(self, company_id=self.company_id)

    def _view_account_ledger(self):
        acct = self._get_selected_account()
        if not acct:
            return
        from ui.journal_dialog import GeneralLedgerDialog
        GeneralLedgerDialog(self, company_id=self.company_id, initial_account_id=acct["id"])

    def _export_csv(self):
        if not self.accounts_cache:
            messagebox.showinfo("Export", "No accounts to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Chart of Accounts",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"chart_of_accounts_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Account Code", "Account Name", "Account Type",
                    "Sub-Category", "Parent Account", "Normal Balance", "System Account", "Status", "Notes"
                ])
                for a in self.accounts_cache:
                    parent_str = f"[{a['parent_code']}] {a['parent_name']}" if a.get("parent_code") else ""
                    writer.writerow([
                        a["account_code"],
                        a["account_name"],
                        a["account_type"],
                        a.get("sub_category") or "",
                        parent_str,
                        a["normal_balance"],
                        "Yes" if a["is_system"] else "No",
                        "Active" if a["is_active"] else "Inactive",
                        a.get("notes") or ""
                    ])
            messagebox.showinfo("Export Successful", f"Successfully exported accounts to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)
