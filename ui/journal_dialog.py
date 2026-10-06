"""
ui/journal_dialog.py
Double-Entry Journal & General Ledger Interface for Voucher Machine SME Bookkeeping v3.5.

Provides:
- JournalEntryDialog: Create & Edit manual journal entries with live balance validation.
- GeneralLedgerDialog: Comprehensive General Ledger viewer and Trial Balance verification.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db


class JournalEntryDialog(tb.Toplevel):
    """
    Dialog to record or edit a balanced double-entry Journal Entry.
    Enforces strict accounting invariant: sum(Debits) == sum(Credits).
    """

    ENTRY_TYPES = ["Manual", "Adjustment", "Opening", "Closing"]

    def __init__(self, parent, company_id=None, entry_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.entry_id = entry_id
        self.is_edit = bool(self.entry_id)
        self.on_saved = on_saved

        self.title("Edit Journal Entry" if self.is_edit else "New Double-Entry Journal Entry")
        self.geometry("860x640")
        self.minsize(740, 520)
        self.transient(parent)
        self.grab_set()

        self.accounts = db.get_chart_of_accounts(company_id=self.company_id, active_only=True)
        self.account_lookup = {f"{a['account_code']} - {a['account_name']} ({a['account_type']})": a for a in self.accounts}
        self.account_id_to_account = {a["id"]: a for a in self.accounts}

        self.lines_data = []  # list of dicts: {"account_id", "account_label", "description", "debit_amount", "credit_amount"}

        self._build_ui()
        if self.is_edit:
            self._load_entry_data()
        else:
            self._init_new_entry()

        self._recalculate_balance()
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

        # Header Frame
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(
            hdr,
            text="Double-Entry Journal Entry",
            font=("Segoe UI", 15, "bold")
        ).pack(anchor=W)

        tb.Label(
            hdr,
            text="Every transaction requires balanced debits and credits.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # Entry Details Form
        form_box = tb.Labelframe(root, text="Entry Details", padding=12)
        form_box.pack(fill=X, pady=(0, 12))

        # Row 1: Entry Number, Date, Type
        r1 = tb.Frame(form_box)
        r1.pack(fill=X, pady=4)

        tb.Label(r1, text="Entry #:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.entry_num_var = tk.StringVar()
        self.entry_num_entry = tb.Entry(r1, textvariable=self.entry_num_var, width=16)
        self.entry_num_entry.pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(r1, textvariable=self.date_var, width=14).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Type:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.type_var = tk.StringVar(value="Manual")
        tb.Combobox(r1, textvariable=self.type_var, values=self.ENTRY_TYPES, state="readonly", width=12).pack(side=LEFT)

        # Row 2: Reference, Description
        r2 = tb.Frame(form_box)
        r2.pack(fill=X, pady=4)

        tb.Label(r2, text="Reference:").pack(side=LEFT, padx=(0, 4))
        self.ref_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.ref_var, width=20).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Memo / Description:").pack(side=LEFT, padx=(0, 4))
        self.desc_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.desc_var, width=42).pack(side=LEFT, fill=X, expand=True)

        # Line Items Container
        lines_box = tb.Labelframe(root, text="Journal Lines", padding=10)
        lines_box.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Add line input strip
        add_bar = tb.Frame(lines_box)
        add_bar.pack(fill=X, pady=(0, 8))

        tb.Label(add_bar, text="Account:").pack(side=LEFT, padx=(0, 4))
        self.line_acct_var = tk.StringVar()
        acct_labels = list(self.account_lookup.keys())
        self.acct_combo = tb.Combobox(add_bar, textvariable=self.line_acct_var, values=acct_labels, width=32)
        self.acct_combo.pack(side=LEFT, padx=(0, 8))

        tb.Label(add_bar, text="Desc:").pack(side=LEFT, padx=(0, 4))
        self.line_desc_var = tk.StringVar()
        tb.Entry(add_bar, textvariable=self.line_desc_var, width=18).pack(side=LEFT, padx=(0, 8))

        tb.Label(add_bar, text="Debit:").pack(side=LEFT, padx=(0, 4))
        self.line_debit_var = tk.StringVar()
        self.line_debit_entry = tb.Entry(add_bar, textvariable=self.line_debit_var, width=10)
        self.line_debit_entry.pack(side=LEFT, padx=(0, 8))

        tb.Label(add_bar, text="Credit:").pack(side=LEFT, padx=(0, 4))
        self.line_credit_var = tk.StringVar()
        self.line_credit_entry = tb.Entry(add_bar, textvariable=self.line_credit_var, width=10)
        self.line_credit_entry.pack(side=LEFT, padx=(0, 8))

        tb.Button(add_bar, text="➕ Add Line", bootstyle="success-outline", command=self._add_line).pack(side=LEFT)

        # Table of lines
        table_frame = tb.Frame(lines_box)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("num", "account", "desc", "debit", "credit")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse", height=7)

        self.tree.heading("num", text="#", anchor=CENTER)
        self.tree.heading("account", text="Account", anchor=W)
        self.tree.heading("desc", text="Description / Memo", anchor=W)
        self.tree.heading("debit", text="Debit (LKR)", anchor=E)
        self.tree.heading("credit", text="Credit (LKR)", anchor=E)

        self.tree.column("num", width=40, anchor=CENTER)
        self.tree.column("account", width=300, anchor=W)
        self.tree.column("desc", width=220, anchor=W)
        self.tree.column("debit", width=120, anchor=E)
        self.tree.column("credit", width=120, anchor=E)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        # Remove line button
        line_actions = tb.Frame(lines_box)
        line_actions.pack(fill=X, pady=(6, 0))
        tb.Button(
            line_actions,
            text="🗑️ Remove Selected Line",
            bootstyle="danger-outline",
            command=self._remove_selected_line
        ).pack(side=LEFT)

        # Balance Status Card
        balance_card = tb.Frame(root, padding=8)
        balance_card.pack(fill=X, pady=(0, 12))

        self.total_debit_label = tb.Label(balance_card, text="Total Debits: LKR 0.00", font=("Segoe UI", 10, "bold"))
        self.total_debit_label.pack(side=LEFT, padx=(0, 20))

        self.total_credit_label = tb.Label(balance_card, text="Total Credits: LKR 0.00", font=("Segoe UI", 10, "bold"))
        self.total_credit_label.pack(side=LEFT, padx=(0, 20))

        self.balance_status_badge = tb.Label(
            balance_card,
            text="⚖️ OUT OF BALANCE",
            font=("Segoe UI", 10, "bold"),
            bootstyle="danger"
        )
        self.balance_status_badge.pack(side=RIGHT)

        # Footer Action Buttons
        footer = tb.Frame(root)
        footer.pack(fill=X)

        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        self.save_btn = tb.Button(footer, text="Post Journal Entry", bootstyle="primary", command=self._save_entry)
        self.save_btn.pack(side=RIGHT)

    def _init_new_entry(self):
        next_num = db.get_next_journal_entry_number(company_id=self.company_id)
        self.entry_num_var.set(next_num)

    def _load_entry_data(self):
        entry_dict = db.get_journal_entry(self.entry_id)
        if not entry_dict:
            messagebox.showerror("Error", "Journal entry not found.", parent=self)
            self.destroy()
            return

        header = entry_dict["entry"]
        lines = entry_dict["lines"]

        self.entry_num_var.set(header["entry_number"])
        self.date_var.set(header["entry_date"])
        self.ref_var.set(header.get("reference") or "")
        self.desc_var.set(header.get("description") or "")
        self.type_var.set(header.get("entry_type") or "Manual")

        for l in lines:
            acct = self.account_id_to_account.get(l["account_id"])
            if acct:
                label = f"{acct['account_code']} - {acct['account_name']} ({acct['account_type']})"
            else:
                label = f"Account #{l['account_id']}"

            self.lines_data.append({
                "account_id": l["account_id"],
                "account_label": label,
                "description": l.get("description") or "",
                "debit_amount": float(l.get("debit_amount") or 0.0),
                "credit_amount": float(l.get("credit_amount") or 0.0)
            })

        self._refresh_lines_table()

    def _add_line(self):
        acct_label = self.line_acct_var.get().strip()
        if not acct_label or acct_label not in self.account_lookup:
            messagebox.showwarning("Validation", "Please select a valid account from the dropdown list.", parent=self)
            return

        acct = self.account_lookup[acct_label]
        desc = self.line_desc_var.get().strip() or self.desc_var.get().strip()

        debit_str = self.line_debit_var.get().strip().replace(",", "")
        credit_str = self.line_credit_var.get().strip().replace(",", "")

        debit_val = 0.0
        credit_val = 0.0

        if debit_str:
            try:
                debit_val = float(debit_str)
                if debit_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Validation", "Debit amount must be a positive number.", parent=self)
                return

        if credit_str:
            try:
                credit_val = float(credit_str)
                if credit_val < 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Validation", "Credit amount must be a positive number.", parent=self)
                return

        if debit_val == 0.0 and credit_val == 0.0:
            messagebox.showwarning("Validation", "Either Debit or Credit must have an amount greater than 0.", parent=self)
            return

        if debit_val > 0.0 and credit_val > 0.0:
            messagebox.showwarning("Validation", "A single line item cannot have both Debit and Credit amounts.", parent=self)
            return

        self.lines_data.append({
            "account_id": acct["id"],
            "account_label": acct_label,
            "description": desc,
            "debit_amount": debit_val,
            "credit_amount": credit_val
        })

        # Clear inputs
        self.line_debit_var.set("")
        self.line_credit_var.set("")
        self.line_desc_var.set("")

        self._refresh_lines_table()
        self._recalculate_balance()

    def _remove_selected_line(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a line to remove.", parent=self)
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.lines_data):
            self.lines_data.pop(idx)
            self._refresh_lines_table()
            self._recalculate_balance()

    def _refresh_lines_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        for idx, l in enumerate(self.lines_data):
            deb_txt = f"{l['debit_amount']:,.2f}" if l["debit_amount"] > 0 else "—"
            cred_txt = f"{l['credit_amount']:,.2f}" if l["credit_amount"] > 0 else "—"
            self.tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    str(idx + 1),
                    l["account_label"],
                    l["description"],
                    deb_txt,
                    cred_txt
                )
            )

    def _recalculate_balance(self):
        tot_deb = sum(l["debit_amount"] for l in self.lines_data)
        tot_cred = sum(l["credit_amount"] for l in self.lines_data)
        diff = abs(tot_deb - tot_cred)

        self.total_debit_label.config(text=f"Total Debits: LKR {tot_deb:,.2f}")
        self.total_credit_label.config(text=f"Total Credits: LKR {tot_cred:,.2f}")

        is_balanced = (diff < 0.001 and tot_deb > 0.0 and len(self.lines_data) >= 2)

        if is_balanced:
            self.balance_status_badge.config(
                text="✅ BALANCED",
                bootstyle="success"
            )
            self.save_btn.configure(state="normal")
        else:
            if tot_deb == 0.0 and tot_cred == 0.0:
                msg = "⚠️ NO AMOUNTS ENTERED"
            elif len(self.lines_data) < 2:
                msg = "⚠️ MINIMUM 2 LINES REQUIRED"
            else:
                msg = f"⚠️ OUT OF BALANCE: LKR {diff:,.2f}"
            self.balance_status_badge.config(
                text=msg,
                bootstyle="danger"
            )

    def _save_entry(self):
        tot_deb = sum(l["debit_amount"] for l in self.lines_data)
        tot_cred = sum(l["credit_amount"] for l in self.lines_data)
        diff = abs(tot_deb - tot_cred)

        if diff >= 0.001 or tot_deb <= 0.0 or len(self.lines_data) < 2:
            messagebox.showerror(
                "Unbalanced Entry",
                f"Double-entry bookkeeping requires total Debits to equal total Credits.\n"
                f"Current Debits: LKR {tot_deb:,.2f}\n"
                f"Current Credits: LKR {tot_cred:,.2f}\n"
                f"Difference: LKR {diff:,.2f}",
                parent=self
            )
            return

        entry_num = self.entry_num_var.get().strip()
        entry_date = self.date_var.get().strip()
        ref = self.ref_var.get().strip()
        desc = self.desc_var.get().strip()
        etype = self.type_var.get().strip()

        if not entry_num:
            messagebox.showwarning("Validation", "Entry Number is required.", parent=self)
            return
        if not entry_date:
            messagebox.showwarning("Validation", "Entry Date is required.", parent=self)
            return

        header_data = {
            "company_id": self.company_id,
            "entry_number": entry_num,
            "entry_date": entry_date,
            "reference": ref,
            "description": desc,
            "entry_type": etype,
            "source_module": "manual",
            "source_id": None,
            "is_posted": 1,
            "created_by": "User"
        }

        try:
            if self.is_edit:
                db.update_journal_entry(self.entry_id, header_data, self.lines_data)
            else:
                db.create_journal_entry(header_data, self.lines_data)

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error Posting Journal Entry", str(e), parent=self)


class GeneralLedgerDialog(tb.Toplevel):
    """
    Comprehensive General Ledger & Trial Balance Interface.
    Features:
    - Tab 1: General Ledger transaction register with calculated running balance.
    - Tab 2: Trial Balance verification with instant debits = credits validation.
    - CSV export and filtering by account and date range.
    """

    def __init__(self, parent, company_id=None, initial_account_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.initial_account_id = initial_account_id

        self.title("General Ledger & Trial Balance — Financial Audit")
        self.geometry("1100x700")
        self.minsize(920, 560)
        self.transient(parent)

        self.accounts = db.get_chart_of_accounts(company_id=self.company_id, active_only=False)
        self.account_map = {f"{a['account_code']} - {a['account_name']}": a["id"] for a in self.accounts}

        self.gl_data_cache = []
        self.tb_data_cache = {}

        self._build_ui()
        self.refresh_gl()
        self.refresh_tb()
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

        # Header Bar
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(hdr)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="📖 General Ledger & Trial Balance", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        tb.Label(
            title_box,
            text=f"Company #{self.company_id} — Financial Record Book",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        top_actions = tb.Frame(hdr)
        top_actions.pack(side=RIGHT)

        tb.Button(
            top_actions,
            text="📒 Chart of Accounts",
            bootstyle="info-outline",
            command=self._open_coa
        ).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_actions,
            text="➕ New Journal Entry",
            bootstyle="primary",
            command=self._new_journal_entry
        ).pack(side=LEFT)

        # Notebook tabs
        self.notebook = tb.Notebook(root, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True)

        self.gl_tab = tb.Frame(self.notebook, padding=12)
        self.tb_tab = tb.Frame(self.notebook, padding=12)

        self.notebook.add(self.gl_tab, text="📖 General Ledger")
        self.notebook.add(self.tb_tab, text="⚖️ Trial Balance")

        self._build_gl_tab()
        self._build_tb_tab()

    def _build_gl_tab(self):
        # Filters toolbar
        tb_bar = tb.Labelframe(self.gl_tab, text="Filters", padding=10)
        tb_bar.pack(fill=X, pady=(0, 10))

        tb.Label(tb_bar, text="Account:").pack(side=LEFT, padx=(0, 4))
        self.gl_acct_var = tk.StringVar(value="All Accounts")
        acct_choices = ["All Accounts"] + list(self.account_map.keys())
        self.gl_acct_combo = tb.Combobox(tb_bar, textvariable=self.gl_acct_var, values=acct_choices, width=28, state="readonly")
        self.gl_acct_combo.pack(side=LEFT, padx=(0, 14))
        self.gl_acct_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_gl())

        # If initial account provided, select it
        if self.initial_account_id:
            for lbl, aid in self.account_map.items():
                if aid == self.initial_account_id:
                    self.gl_acct_var.set(lbl)
                    break

        tb.Label(tb_bar, text="Start Date:").pack(side=LEFT, padx=(0, 4))
        self.gl_start_var = tk.StringVar()
        tb.Entry(tb_bar, textvariable=self.gl_start_var, width=12).pack(side=LEFT, padx=(0, 10))

        tb.Label(tb_bar, text="End Date:").pack(side=LEFT, padx=(0, 4))
        self.gl_end_var = tk.StringVar()
        tb.Entry(tb_bar, textvariable=self.gl_end_var, width=12).pack(side=LEFT, padx=(0, 14))

        tb.Button(tb_bar, text="Filter", bootstyle="primary", command=self.refresh_gl).pack(side=LEFT, padx=(0, 6))
        tb.Button(tb_bar, text="Reset", bootstyle="secondary-outline", command=self._reset_gl_filters).pack(side=LEFT)

        tb.Button(tb_bar, text="📥 Export Ledger CSV", bootstyle="outline", command=self._export_gl_csv).pack(side=RIGHT)

        # GL Table
        table_frame = tb.Frame(self.gl_tab)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("date", "entry_num", "ref", "account", "desc", "debit", "credit", "balance")
        self.gl_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.gl_tree.heading("date", text="Date", anchor=CENTER)
        self.gl_tree.heading("entry_num", text="Entry #", anchor=W)
        self.gl_tree.heading("ref", text="Reference", anchor=W)
        self.gl_tree.heading("account", text="Account", anchor=W)
        self.gl_tree.heading("desc", text="Description / Memo", anchor=W)
        self.gl_tree.heading("debit", text="Debit (LKR)", anchor=E)
        self.gl_tree.heading("credit", text="Credit (LKR)", anchor=E)
        self.gl_tree.heading("balance", text="Balance (LKR)", anchor=E)

        self.gl_tree.column("date", width=95, anchor=CENTER)
        self.gl_tree.column("entry_num", width=110, anchor=W)
        self.gl_tree.column("ref", width=100, anchor=W)
        self.gl_tree.column("account", width=180, anchor=W)
        self.gl_tree.column("desc", width=220, anchor=W)
        self.gl_tree.column("debit", width=110, anchor=E)
        self.gl_tree.column("credit", width=110, anchor=E)
        self.gl_tree.column("balance", width=120, anchor=E)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.gl_tree.yview)
        self.gl_tree.configure(yscrollcommand=scroll.set)
        self.gl_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        # Double-click to view/edit entry
        self.gl_tree.bind("<Double-1>", lambda e: self._on_gl_double_click())

        # Summary footer bar
        gl_footer = tb.Frame(self.gl_tab, padding=(0, 10, 0, 0))
        gl_footer.pack(fill=X)

        self.gl_total_debit_lbl = tb.Label(gl_footer, text="Total Debits: LKR 0.00", font=("Segoe UI", 10, "bold"))
        self.gl_total_debit_lbl.pack(side=LEFT, padx=(0, 24))

        self.gl_total_credit_lbl = tb.Label(gl_footer, text="Total Credits: LKR 0.00", font=("Segoe UI", 10, "bold"))
        self.gl_total_credit_lbl.pack(side=LEFT, padx=(0, 24))

        self.gl_count_lbl = tb.Label(gl_footer, text="0 transaction(s)", font=("Segoe UI", 9), bootstyle="secondary")
        self.gl_count_lbl.pack(side=RIGHT)

    def _build_tb_tab(self):
        # TB Toolbar
        tb_bar = tb.Labelframe(self.tb_tab, text="Parameters", padding=10)
        tb_bar.pack(fill=X, pady=(0, 10))

        tb.Label(tb_bar, text="As of Date:").pack(side=LEFT, padx=(0, 4))
        self.tb_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(tb_bar, textvariable=self.tb_date_var, width=14).pack(side=LEFT, padx=(0, 14))

        tb.Button(tb_bar, text="Calculate Trial Balance", bootstyle="primary", command=self.refresh_tb).pack(side=LEFT, padx=(0, 6))

        tb.Button(tb_bar, text="📥 Export Trial Balance CSV", bootstyle="outline", command=self._export_tb_csv).pack(side=RIGHT)

        # TB Table
        table_frame = tb.Frame(self.tb_tab)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "type", "normal_balance", "debit", "credit")
        self.tb_tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tb_tree.heading("code", text="Account Code", anchor=W)
        self.tb_tree.heading("name", text="Account Name", anchor=W)
        self.tb_tree.heading("type", text="Type", anchor=W)
        self.tb_tree.heading("normal_balance", text="Normal Balance", anchor=CENTER)
        self.tb_tree.heading("debit", text="Debit Balance (LKR)", anchor=E)
        self.tb_tree.heading("credit", text="Credit Balance (LKR)", anchor=E)

        self.tb_tree.column("code", width=110, anchor=W)
        self.tb_tree.column("name", width=260, anchor=W)
        self.tb_tree.column("type", width=120, anchor=W)
        self.tb_tree.column("normal_balance", width=120, anchor=CENTER)
        self.tb_tree.column("debit", width=150, anchor=E)
        self.tb_tree.column("credit", width=150, anchor=E)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tb_tree.yview)
        self.tb_tree.configure(yscrollcommand=scroll.set)
        self.tb_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        # TB Footer with Debits vs Credits and balanced verification badge
        tb_footer = tb.Labelframe(self.tb_tab, text="Trial Balance Audit Verification", padding=10)
        tb_footer.pack(fill=X, pady=(10, 0))

        self.tb_debit_lbl = tb.Label(tb_footer, text="Total Debits: LKR 0.00", font=("Segoe UI", 11, "bold"))
        self.tb_debit_lbl.pack(side=LEFT, padx=(10, 24))

        self.tb_credit_lbl = tb.Label(tb_footer, text="Total Credits: LKR 0.00", font=("Segoe UI", 11, "bold"))
        self.tb_credit_lbl.pack(side=LEFT, padx=(0, 24))

        self.tb_diff_lbl = tb.Label(tb_footer, text="Difference: LKR 0.00", font=("Segoe UI", 10))
        self.tb_diff_lbl.pack(side=LEFT, padx=(0, 24))

        self.tb_status_badge = tb.Label(
            tb_footer,
            text="✅ TRIAL BALANCE BALANCED",
            font=("Segoe UI", 11, "bold"),
            bootstyle="success"
        )
        self.tb_status_badge.pack(side=RIGHT, padx=10)

    def _reset_gl_filters(self):
        self.gl_acct_var.set("All Accounts")
        self.gl_start_var.set("")
        self.gl_end_var.set("")
        self.refresh_gl()

    def refresh_gl(self):
        acct_selection = self.gl_acct_var.get()
        account_id = None
        if acct_selection and acct_selection != "All Accounts":
            account_id = self.account_map.get(acct_selection)

        start_date = self.gl_start_var.get().strip() or None
        end_date = self.gl_end_var.get().strip() or None

        rows = db.get_general_ledger(
            company_id=self.company_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )
        self.gl_data_cache = rows

        for r in self.gl_tree.get_children():
            self.gl_tree.delete(r)

        tot_deb = 0.0
        tot_cred = 0.0

        for idx, row in enumerate(rows):
            deb = float(row.get("debit_amount") or 0.0)
            cred = float(row.get("credit_amount") or 0.0)
            tot_deb += deb
            tot_cred += cred

            deb_str = f"{deb:,.2f}" if deb > 0 else "—"
            cred_str = f"{cred:,.2f}" if cred > 0 else "—"
            bal_str = f"{float(row.get('running_balance') or 0.0):,.2f}"

            acct_display = f"{row['account_code']} - {row['account_name']}"
            desc = row.get("line_description") or row.get("entry_description") or ""

            self.gl_tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    row["entry_date"],
                    row["entry_number"],
                    row.get("reference") or "—",
                    acct_display,
                    desc,
                    deb_str,
                    cred_str,
                    bal_str
                )
            )

        self.gl_total_debit_lbl.config(text=f"Total Debits: LKR {tot_deb:,.2f}")
        self.gl_total_credit_lbl.config(text=f"Total Credits: LKR {tot_cred:,.2f}")
        self.gl_count_lbl.config(text=f"{len(rows)} transaction line(s)")

    def refresh_tb(self):
        as_of = self.tb_date_var.get().strip() or None
        res = db.get_trial_balance(company_id=self.company_id, as_of_date=as_of)
        self.tb_data_cache = res

        for r in self.tb_tree.get_children():
            self.tb_tree.delete(r)

        for a in res.get("accounts", []):
            deb = float(a.get("debit_balance") or 0.0)
            cred = float(a.get("credit_balance") or 0.0)

            deb_str = f"{deb:,.2f}" if deb > 0 else "—"
            cred_str = f"{cred:,.2f}" if cred > 0 else "—"

            self.tb_tree.insert(
                "",
                END,
                iid=str(a["id"]),
                values=(
                    a["account_code"],
                    a["account_name"],
                    a["account_type"],
                    a["normal_balance"],
                    deb_str,
                    cred_str
                )
            )

        tot_deb = float(res.get("total_debit") or 0.0)
        tot_cred = float(res.get("total_credit") or 0.0)
        diff = float(res.get("difference") or 0.0)
        is_balanced = bool(res.get("is_balanced", False))

        self.tb_debit_lbl.config(text=f"Total Debits: LKR {tot_deb:,.2f}")
        self.tb_credit_lbl.config(text=f"Total Credits: LKR {tot_cred:,.2f}")
        self.tb_diff_lbl.config(text=f"Difference: LKR {diff:,.2f}")

        if is_balanced:
            self.tb_status_badge.config(
                text="✅ TRIAL BALANCE BALANCED",
                bootstyle="success"
            )
        else:
            self.tb_status_badge.config(
                text=f"⚠️ MISMATCH BY LKR {diff:,.2f}",
                bootstyle="danger"
            )

    def _on_gl_double_click(self):
        sel = self.gl_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.gl_data_cache):
            entry_id = self.gl_data_cache[idx]["entry_id"]
            JournalEntryDialog(self, company_id=self.company_id, entry_id=entry_id, on_saved=self._on_journal_saved)

    def _on_journal_saved(self):
        self.refresh_gl()
        self.refresh_tb()

    def _new_journal_entry(self):
        JournalEntryDialog(self, company_id=self.company_id, on_saved=self._on_journal_saved)

    def _open_coa(self):
        from ui.coa_dialog import ChartOfAccountsDialog
        ChartOfAccountsDialog(self, company_id=self.company_id)

    def _export_gl_csv(self):
        if not self.gl_data_cache:
            messagebox.showinfo("Export", "No ledger records to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export General Ledger",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"general_ledger_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date", "Entry #", "Reference", "Account Code", "Account Name",
                    "Account Type", "Description", "Debit (LKR)", "Credit (LKR)", "Running Balance (LKR)"
                ])
                for r in self.gl_data_cache:
                    desc = r.get("line_description") or r.get("entry_description") or ""
                    writer.writerow([
                        r["entry_date"],
                        r["entry_number"],
                        r.get("reference") or "",
                        r["account_code"],
                        r["account_name"],
                        r["account_type"],
                        desc,
                        f"{float(r.get('debit_amount') or 0.0):.2f}",
                        f"{float(r.get('credit_amount') or 0.0):.2f}",
                        f"{float(r.get('running_balance') or 0.0):.2f}"
                    ])
            messagebox.showinfo("Export Successful", f"Exported General Ledger to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)

    def _export_tb_csv(self):
        accounts = self.tb_data_cache.get("accounts", [])
        if not accounts:
            messagebox.showinfo("Export", "No trial balance data to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Trial Balance",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"trial_balance_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Account Code", "Account Name", "Account Type",
                    "Normal Balance", "Debit Balance (LKR)", "Credit Balance (LKR)"
                ])
                for a in accounts:
                    writer.writerow([
                        a["account_code"],
                        a["account_name"],
                        a["account_type"],
                        a["normal_balance"],
                        f"{float(a.get('debit_balance') or 0.0):.2f}",
                        f"{float(a.get('credit_balance') or 0.0):.2f}"
                    ])
                writer.writerow([])
                writer.writerow([
                    "TOTALS", "", "", "",
                    f"{float(self.tb_data_cache.get('total_debit') or 0.0):.2f}",
                    f"{float(self.tb_data_cache.get('total_credit') or 0.0):.2f}"
                ])
                writer.writerow([
                    "AUDIT STATUS",
                    "BALANCED" if self.tb_data_cache.get("is_balanced") else "MISMATCH",
                    f"Difference: {float(self.tb_data_cache.get('difference') or 0.0):.2f}"
                ])
            messagebox.showinfo("Export Successful", f"Exported Trial Balance to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)
