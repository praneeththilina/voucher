"""
ui/fixed_assets_dialog.py
Fixed Asset Register & Depreciation Management Module for Voucher Manager.

Provides:
- FixedAssetManagerDialog: Asset directory with cost, accumulated depreciation,
  net book value tracking, search, status filtering, and CSV export.
- FixedAssetEditModal: Modal form for creating and editing fixed assets.
- DepreciationWizardModal: Monthly straight-line depreciation wizard with auto-journals.
- AssetDisposalModal: Asset disposal and retirement modal with gain/loss calculation.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from ui.widgets import ToolTip


class FixedAssetEditModal(tb.Toplevel):
    """Modal for creating or editing a fixed asset record."""

    def __init__(self, parent, company_id=None, asset_data=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.asset_data = asset_data or {}
        self.on_saved = on_saved
        self.is_edit = bool(self.asset_data.get("id"))

        self.title("Edit Fixed Asset" if self.is_edit else "Register New Fixed Asset")
        self.geometry("560x640")
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

        header_title = "Edit Fixed Asset" if self.is_edit else "Register New Fixed Asset"
        header_desc = "Record asset acquisition, valuation, useful life, and Chart of Accounts ledgers."
        tb.Label(container, text=header_title, font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(container, text=header_desc, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 14))

        form = tb.Frame(container)
        form.pack(fill=BOTH, expand=True)

        # Asset Code & Name
        tb.Label(form, text="Asset Code *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=4)
        self.code_var = tk.StringVar(value=db.get_next_asset_code(self.company_id))
        self.code_entry = tb.Entry(form, textvariable=self.code_var, width=32)
        self.code_entry.grid(row=0, column=1, sticky=EW, pady=4, padx=(10, 0))

        tb.Label(form, text="Asset Name *:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky=W, pady=4)
        self.name_var = tk.StringVar()
        self.name_entry = tb.Entry(form, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=1, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Category & Serial #
        tb.Label(form, text="Category:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky=W, pady=4)
        self.category_var = tk.StringVar(value="Office Equipment")
        categories = ["Office Equipment", "IT Hardware & Software", "Vehicles", "Machinery & Plant", "Furniture & Fixtures", "Buildings", "Land"]
        tb.Combobox(form, textvariable=self.category_var, values=categories, width=30).grid(row=2, column=1, sticky=EW, pady=4, padx=(10, 0))

        tb.Label(form, text="Serial / Tag #:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky=W, pady=4)
        self.serial_var = tk.StringVar()
        tb.Entry(form, textvariable=self.serial_var, width=32).grid(row=3, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Purchase Date & Cost
        tb.Label(form, text="Purchase Date (YYYY-MM-DD) *:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky=W, pady=4)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(form, textvariable=self.date_var, width=32).grid(row=4, column=1, sticky=EW, pady=4, padx=(10, 0))

        tb.Label(form, text="Cost Basis (LKR) *:", font=("Segoe UI", 9, "bold")).grid(row=5, column=0, sticky=W, pady=4)
        self.cost_var = tk.StringVar(value="0.00")
        tb.Entry(form, textvariable=self.cost_var, width=32).grid(row=5, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Salvage Value & Useful Life
        tb.Label(form, text="Salvage Value (LKR):", font=("Segoe UI", 9)).grid(row=6, column=0, sticky=W, pady=4)
        self.salvage_var = tk.StringVar(value="0.00")
        tb.Entry(form, textvariable=self.salvage_var, width=32).grid(row=6, column=1, sticky=EW, pady=4, padx=(10, 0))

        tb.Label(form, text="Useful Life (Months) *:", font=("Segoe UI", 9)).grid(row=7, column=0, sticky=W, pady=4)
        self.life_var = tk.StringVar(value="36")
        tb.Spinbox(form, from_=1, to=600, textvariable=self.life_var, width=12).grid(row=7, column=1, sticky=W, pady=4, padx=(10, 0))

        # Depreciation Method
        tb.Label(form, text="Depreciation Method:", font=("Segoe UI", 9)).grid(row=8, column=0, sticky=W, pady=4)
        self.method_var = tk.StringVar(value="Straight Line")
        tb.Combobox(form, textvariable=self.method_var, values=["Straight Line"], state="readonly", width=30).grid(row=8, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Ledger Account Selections
        accounts = db.get_chart_of_accounts(self.company_id, active_only=True)
        acct_options = [f"{a['account_code']} - {a['account_name']}" for a in accounts]
        self.acct_map = {f"{a['account_code']} - {a['account_name']}": a["id"] for a in accounts}
        self.acct_id_map = {a["id"]: f"{a['account_code']} - {a['account_name']}" for a in accounts}

        # Asset Account (1410 default)
        tb.Label(form, text="Fixed Asset Account:", font=("Segoe UI", 9)).grid(row=9, column=0, sticky=W, pady=4)
        self.asset_acct_var = tk.StringVar()
        default_asset = next((k for k, v in self.acct_map.items() if "1410" in k or "Equipment" in k), acct_options[0] if acct_options else "")
        self.asset_acct_var.set(default_asset)
        tb.Combobox(form, textvariable=self.asset_acct_var, values=acct_options, state="readonly", width=30).grid(row=9, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Accum Deprec Account (1490 default)
        tb.Label(form, text="Accum. Deprec. Account:", font=("Segoe UI", 9)).grid(row=10, column=0, sticky=W, pady=4)
        self.accum_acct_var = tk.StringVar()
        default_accum = next((k for k, v in self.acct_map.items() if "1490" in k or "Accumulated" in k), acct_options[0] if acct_options else "")
        self.accum_acct_var.set(default_accum)
        tb.Combobox(form, textvariable=self.accum_acct_var, values=acct_options, state="readonly", width=30).grid(row=10, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Deprec Expense Account (5920 default)
        tb.Label(form, text="Deprec. Expense Account:", font=("Segoe UI", 9)).grid(row=11, column=0, sticky=W, pady=4)
        self.expense_acct_var = tk.StringVar()
        default_exp = next((k for k, v in self.acct_map.items() if "5920" in k or "Depreciation" in k), acct_options[0] if acct_options else "")
        self.expense_acct_var.set(default_exp)
        tb.Combobox(form, textvariable=self.expense_acct_var, values=acct_options, state="readonly", width=30).grid(row=11, column=1, sticky=EW, pady=4, padx=(10, 0))

        # Notes
        tb.Label(form, text="Notes / Location:", font=("Segoe UI", 9)).grid(row=12, column=0, sticky=W, pady=4)
        self.notes_var = tk.StringVar()
        tb.Entry(form, textvariable=self.notes_var, width=32).grid(row=12, column=1, sticky=EW, pady=4, padx=(10, 0))

        form.columnconfigure(1, weight=1)

        # Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        save_btn = tb.Button(btn_box, text="Save Asset", bootstyle="primary", command=self._save)
        save_btn.pack(side=RIGHT)

    def _populate_fields(self):
        if not self.asset_data:
            return
        self.code_var.set(self.asset_data.get("asset_code", ""))
        self.name_var.set(self.asset_data.get("asset_name", ""))
        self.category_var.set(self.asset_data.get("category", "Office Equipment"))
        self.serial_var.set(self.asset_data.get("serial_number", ""))
        self.date_var.set(self.asset_data.get("purchase_date", ""))
        self.cost_var.set(f"{float(self.asset_data.get('cost_basis') or 0.0):.2f}")
        self.salvage_var.set(f"{float(self.asset_data.get('salvage_value') or 0.0):.2f}")
        self.life_var.set(str(self.asset_data.get("useful_life_months") or 36))
        self.method_var.set(self.asset_data.get("depreciation_method", "Straight Line"))
        self.notes_var.set(self.asset_data.get("notes", ""))

        if self.asset_data.get("asset_account_id") in self.acct_id_map:
            self.asset_acct_var.set(self.acct_id_map[self.asset_data["asset_account_id"]])
        if self.asset_data.get("accum_deprec_account_id") in self.acct_id_map:
            self.accum_acct_var.set(self.acct_id_map[self.asset_data["accum_deprec_account_id"]])
        if self.asset_data.get("deprec_expense_account_id") in self.acct_id_map:
            self.expense_acct_var.set(self.acct_id_map[self.asset_data["deprec_expense_account_id"]])

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Asset Name is required.", parent=self)
            self.name_entry.focus_set()
            return

        try:
            cost = float(self.cost_var.get().strip() or 0.0)
            if cost < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation Error", "Please enter a valid non-negative cost basis.", parent=self)
            return

        try:
            salvage = float(self.salvage_var.get().strip() or 0.0)
            if salvage < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation Error", "Please enter a valid non-negative salvage value.", parent=self)
            return

        if cost > 0 and salvage >= cost:
            messagebox.showwarning("Validation Error", "Salvage value must be strictly less than original cost basis.", parent=self)
            return

        try:
            months = int(self.life_var.get().strip() or 36)
            if months <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation Error", "Useful life months must be a positive number.", parent=self)
            return

        payload = {
            "company_id": self.company_id,
            "asset_code": self.code_var.get().strip(),
            "asset_name": name,
            "category": self.category_var.get().strip(),
            "serial_number": self.serial_var.get().strip(),
            "purchase_date": self.date_var.get().strip(),
            "cost_basis": cost,
            "salvage_value": salvage,
            "useful_life_months": months,
            "depreciation_method": self.method_var.get().strip(),
            "asset_account_id": self.acct_map.get(self.asset_acct_var.get()),
            "accum_deprec_account_id": self.acct_map.get(self.accum_acct_var.get()),
            "deprec_expense_account_id": self.acct_map.get(self.expense_acct_var.get()),
            "notes": self.notes_var.get().strip()
        }

        try:
            if self.is_edit:
                db.update_fixed_asset(self.asset_data["id"], payload)
            else:
                db.create_fixed_asset(payload)

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error Saving Asset", str(e), parent=self)


class DepreciationWizardModal(tb.Toplevel):
    """Modal for running monthly straight-line depreciation wizard."""

    def __init__(self, parent, company_id=None, on_completed=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_completed = on_completed

        self.title("Run Monthly Depreciation Wizard")
        self.geometry("480x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
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

        tb.Label(container, text="⚙️ Monthly Depreciation Wizard", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(
            container,
            text="Calculates straight-line depreciation and posts auto-journals to General Ledger.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 16))

        form = tb.Frame(container)
        form.pack(fill=X, pady=10)

        tb.Label(form, text="Target Period (YYYY-MM) *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=6)
        self.period_var = tk.StringVar(value=datetime.now().strftime("%Y-%m"))
        tb.Entry(form, textvariable=self.period_var, width=16).grid(row=0, column=1, sticky=W, pady=6, padx=(10, 0))

        tb.Label(
            form,
            text="• Debit: Depreciation & Amortization Expense (5920)\n• Credit: Accumulated Depreciation — Fixed Assets (1490)",
            font=("Segoe UI", 8),
            bootstyle="info"
        ).grid(row=1, column=0, columnspan=2, sticky=W, pady=(8, 0))

        # Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, side=BOTTOM, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        run_btn = tb.Button(btn_box, text="⚡ Execute Depreciation", bootstyle="success", command=self._execute)
        run_btn.pack(side=RIGHT)

    def _execute(self):
        period = self.period_var.get().strip()
        if not period or len(period) != 7 or period[4] != "-":
            messagebox.showwarning("Invalid Period", "Please enter a period in YYYY-MM format (e.g. 2026-03).", parent=self)
            return

        try:
            res = db.run_depreciation_wizard(company_id=self.company_id, period=period)
            messagebox.showinfo(
                "Depreciation Complete",
                f"{res['message']}\n"
                f"Total Depreciation Posted: LKR {res['total_depreciation']:,.2f}",
                parent=self
            )
            if self.on_completed:
                self.on_completed()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Depreciation Error", str(e), parent=self)


class AssetDisposalModal(tb.Toplevel):
    """Modal for disposing or retiring a fixed asset."""

    def __init__(self, parent, asset_data, on_disposed=None):
        super().__init__(parent)
        self.asset_data = asset_data
        self.on_disposed = on_disposed

        self.title(f"Dispose Fixed Asset — {self.asset_data['asset_code']}")
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
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

        tb.Label(container, text="🏷️ Dispose / Retire Fixed Asset", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(
            container,
            text=f"Asset: {self.asset_data['asset_code']} — {self.asset_data['asset_name']}",
            font=("Segoe UI", 9, "bold"),
            bootstyle="primary"
        ).pack(anchor=W, pady=(0, 14))

        # Valuation summary
        val_box = tb.Labelframe(container, text="Valuation Summary", padding=10)
        val_box.pack(fill=X, pady=(0, 14))

        cost = float(self.asset_data["cost_basis"])
        accum = float(self.asset_data["accumulated_depreciation"])
        nbv = float(self.asset_data["net_book_value"])

        tb.Label(val_box, text=f"Original Cost: LKR {cost:,.2f}").grid(row=0, column=0, sticky=W, padx=8, pady=2)
        tb.Label(val_box, text=f"Accum. Deprec: LKR {accum:,.2f}").grid(row=0, column=1, sticky=W, padx=8, pady=2)
        tb.Label(val_box, text=f"Net Book Value: LKR {nbv:,.2f}", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, columnspan=2, sticky=W, padx=8, pady=4)

        # Disposal Inputs
        form = tb.Frame(container)
        form.pack(fill=X)

        tb.Label(form, text="Disposal Date *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=5)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(form, textvariable=self.date_var, width=28).grid(row=0, column=1, sticky=EW, pady=5, padx=(10, 0))

        tb.Label(form, text="Disposal Proceeds (LKR) *:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky=W, pady=5)
        self.proceeds_var = tk.StringVar(value="0.00")
        self.proceeds_entry = tb.Entry(form, textvariable=self.proceeds_var, width=28)
        self.proceeds_entry.grid(row=1, column=1, sticky=EW, pady=5, padx=(10, 0))
        self.proceeds_var.trace_add("write", lambda *args: self._update_gain_loss())

        self.gain_loss_lbl = tb.Label(form, text="Gain / (Loss) on Disposal: LKR 0.00", font=("Segoe UI", 9, "bold"))
        self.gain_loss_lbl.grid(row=2, column=0, columnspan=2, sticky=W, pady=6)

        tb.Label(form, text="Reason / Notes:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky=W, pady=5)
        self.notes_var = tk.StringVar()
        tb.Entry(form, textvariable=self.notes_var, width=28).grid(row=3, column=1, sticky=EW, pady=5, padx=(10, 0))

        form.columnconfigure(1, weight=1)

        # Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, side=BOTTOM, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        disp_btn = tb.Button(btn_box, text="Confirm Disposal", bootstyle="danger", command=self._confirm)
        disp_btn.pack(side=RIGHT)

        self._update_gain_loss()

    def _update_gain_loss(self):
        try:
            proceeds = float(self.proceeds_var.get().strip() or 0.0)
            nbv = float(self.asset_data["net_book_value"])
            gl = round(proceeds - nbv, 2)
            if gl > 0:
                self.gain_loss_lbl.config(text=f"Estimated Gain on Disposal: +LKR {gl:,.2f}", bootstyle="success")
            elif gl < 0:
                self.gain_loss_lbl.config(text=f"Estimated Loss on Disposal: -LKR {abs(gl):,.2f}", bootstyle="danger")
            else:
                self.gain_loss_lbl.config(text="Gain / Loss on Disposal: LKR 0.00", bootstyle="info")
        except ValueError:
            self.gain_loss_lbl.config(text="Invalid proceeds amount", bootstyle="warning")

    def _confirm(self):
        d_date = self.date_var.get().strip()
        if not d_date:
            messagebox.showwarning("Validation Error", "Disposal date is required.", parent=self)
            return

        try:
            proceeds = float(self.proceeds_var.get().strip() or 0.0)
            if proceeds < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation Error", "Please enter a valid disposal proceeds amount.", parent=self)
            return

        confirm = messagebox.askyesno(
            "Confirm Asset Disposal",
            f"Are you sure you want to dispose asset '{self.asset_data['asset_code']}'?\n"
            f"Proceeds: LKR {proceeds:,.2f}\n"
            "This will post a disposal journal entry to the General Ledger.",
            parent=self
        )
        if not confirm:
            return

        try:
            db.dispose_fixed_asset(
                self.asset_data["id"],
                disposal_date=d_date,
                disposal_amount=proceeds,
                notes=self.notes_var.get().strip()
            )
            messagebox.showinfo("Asset Disposed", f"Asset {self.asset_data['asset_code']} has been disposed.", parent=self)
            if self.on_disposed:
                self.on_disposed()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Disposal Error", str(e), parent=self)


class FixedAssetManagerDialog(tb.Toplevel):
    """Fixed Asset Register & Depreciation Management Main Window."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Fixed Assets Register & Depreciation Manager")
        self.geometry("1080x660")
        self.minsize(880, 520)
        self.transient(parent)

        self.assets_cache = []
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

        # Header
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 12))

        title_box = tb.Frame(hdr)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="🏢 Fixed Assets Register", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        self.subtitle_lbl = tb.Label(
            title_box,
            text=f"Company #{self.company_id} — Fixed Assets & Straight-Line Depreciation Schedule",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        )
        self.subtitle_lbl.pack(anchor=W)

        top_btns = tb.Frame(hdr)
        top_btns.pack(side=RIGHT)

        deprec_btn = tb.Button(top_btns, text="⚙️ Run Depreciation", bootstyle="success", command=self._run_depreciation)
        deprec_btn.pack(side=LEFT, padx=(0, 8))
        ToolTip(deprec_btn, text="Run monthly straight-line depreciation wizard and post GL journals")

        add_btn = tb.Button(top_btns, text="➕ New Asset", bootstyle="primary", command=self._create_asset)
        add_btn.pack(side=LEFT)
        ToolTip(add_btn, text="Register a new fixed asset")

        # Toolbar
        toolbar = tb.Labelframe(root, text="Search & Filter", padding=10)
        toolbar.pack(fill=X, pady=(0, 12))

        tb.Label(toolbar, text="Search:").pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = tb.Entry(toolbar, textvariable=self.search_var, width=28)
        search_entry.pack(side=LEFT, padx=(0, 14))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        tb.Label(toolbar, text="Status Filter:").pack(side=LEFT, padx=(0, 4))
        self.status_filter_var = tk.StringVar(value="Active")
        status_cb = tb.Combobox(toolbar, textvariable=self.status_filter_var, values=["Active", "Fully Depreciated", "Disposed", "All"], state="readonly", width=16)
        status_cb.pack(side=LEFT, padx=(0, 14))
        status_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        tb.Button(toolbar, text="Reset", bootstyle="secondary-outline", command=self._reset_filters).pack(side=LEFT)
        export_btn = tb.Button(toolbar, text="📥 Export CSV", bootstyle="outline", command=self._export_csv)
        export_btn.pack(side=RIGHT)
        ToolTip(export_btn, text="Export complete Fixed Asset Register to CSV")

        # Table
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "category", "purchase_date", "cost", "accum_deprec", "nbv", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("code", text="Asset Code", anchor=W)
        self.tree.heading("name", text="Asset Name", anchor=W)
        self.tree.heading("category", text="Category", anchor=W)
        self.tree.heading("purchase_date", text="Purchased", anchor=CENTER)
        self.tree.heading("cost", text="Cost Basis (LKR)", anchor=E)
        self.tree.heading("accum_deprec", text="Accum. Deprec. (LKR)", anchor=E)
        self.tree.heading("nbv", text="Net Book Value (LKR)", anchor=E)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("code", width=100, anchor=W)
        self.tree.column("name", width=220, anchor=W)
        self.tree.column("category", width=140, anchor=W)
        self.tree.column("purchase_date", width=100, anchor=CENTER)
        self.tree.column("cost", width=140, anchor=E)
        self.tree.column("accum_deprec", width=150, anchor=E)
        self.tree.column("nbv", width=150, anchor=E)
        self.tree.column("status", width=110, anchor=CENTER)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        # Keybindings & Selection
        self.tree.bind("<Double-1>", lambda e: self._edit_selected_asset())
        self.tree.bind("<Return>", lambda e: self._edit_selected_asset())
        self.tree.bind("<KP_Enter>", lambda e: self._edit_selected_asset())
        self.tree.bind("<Delete>", lambda e: self._delete_asset())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_button_states())

        # Footer Actions
        bottom_bar = tb.Frame(root, padding=(0, 10, 0, 0))
        bottom_bar.pack(fill=X)

        self.edit_btn = tb.Button(bottom_bar, text="✏️ Edit Asset", bootstyle="primary-outline", command=self._edit_selected_asset)
        self.edit_btn.pack(side=LEFT, padx=(0, 8))

        self.dispose_btn = tb.Button(bottom_bar, text="🏷️ Dispose Asset", bootstyle="warning-outline", command=self._dispose_selected_asset)
        self.dispose_btn.pack(side=LEFT, padx=(0, 8))

        self.delete_btn = tb.Button(bottom_bar, text="🗑️ Delete Asset", bootstyle="danger-outline", command=self._delete_asset)
        self.delete_btn.pack(side=LEFT, padx=(0, 8))

        tb.Button(bottom_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _reset_filters(self):
        self.search_var.set("")
        self.status_filter_var.set("Active")
        self.refresh()

    def refresh(self):
        search_q = self.search_var.get().strip() or None
        status = self.status_filter_var.get()

        assets = db.get_fixed_assets(
            company_id=self.company_id,
            status=status,
            search=search_q
        )
        self.assets_cache = assets

        for r in self.tree.get_children():
            self.tree.delete(r)

        tot_cost = 0.0
        tot_accum = 0.0
        tot_nbv = 0.0

        for a in assets:
            cost = float(a["cost_basis"])
            accum = float(a["accumulated_depreciation"])
            nbv = float(a["net_book_value"])

            tot_cost += cost
            tot_accum += accum
            tot_nbv += nbv

            self.tree.insert(
                "",
                END,
                iid=str(a["id"]),
                values=(
                    a["asset_code"],
                    a["asset_name"],
                    a["category"],
                    a["purchase_date"],
                    f"{cost:,.2f}",
                    f"{accum:,.2f}",
                    f"{nbv:,.2f}",
                    a["status"]
                )
            )

        self.subtitle_lbl.config(
            text=f"{len(assets)} asset(s) | Total Cost: LKR {tot_cost:,.2f} | Accum. Deprec: LKR {tot_accum:,.2f} | Net Book Value: LKR {tot_nbv:,.2f}"
        )

        # Auto-select first item
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)

        self._update_button_states()

    def _get_selected_asset(self):
        sel = self.tree.selection()
        if not sel:
            return None
        aid = int(sel[0])
        return db.get_fixed_asset(aid)

    def _update_button_states(self):
        asset = self._get_selected_asset()
        has_sel = asset is not None
        is_active = has_sel and asset.get("status") in ("Active", "Fully Depreciated")

        self.edit_btn.config(state=NORMAL if has_sel else DISABLED)
        self.dispose_btn.config(state=NORMAL if is_active else DISABLED)
        self.delete_btn.config(state=NORMAL if has_sel else DISABLED)

    def _create_asset(self):
        FixedAssetEditModal(self, company_id=self.company_id, on_saved=self.refresh)

    def _edit_selected_asset(self):
        asset = self._get_selected_asset()
        if not asset:
            messagebox.showinfo("Selection Required", "Please select a fixed asset from the list.", parent=self)
            return
        FixedAssetEditModal(self, company_id=self.company_id, asset_data=asset, on_saved=self.refresh)

    def _run_depreciation(self):
        DepreciationWizardModal(self, company_id=self.company_id, on_completed=self.refresh)

    def _dispose_selected_asset(self):
        asset = self._get_selected_asset()
        if not asset:
            messagebox.showinfo("Selection Required", "Please select a fixed asset to dispose.", parent=self)
            return
        if asset["status"] == "Disposed":
            messagebox.showinfo("Already Disposed", "The selected asset is already disposed.", parent=self)
            return
        AssetDisposalModal(self, asset_data=asset, on_disposed=self.refresh)

    def _delete_asset(self):
        asset = self._get_selected_asset()
        if not asset:
            messagebox.showinfo("Selection Required", "Please select a fixed asset to delete.", parent=self)
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete fixed asset '{asset['asset_code']} — {asset['asset_name']}'?\n"
            "This action cannot be undone.",
            parent=self
        )
        if not confirm:
            return

        success, msg = db.delete_fixed_asset(asset["id"])
        if success:
            messagebox.showinfo("Deleted", msg, parent=self)
            self.refresh()
        else:
            messagebox.showerror("Cannot Delete", msg, parent=self)

    def _export_csv(self):
        if not self.assets_cache:
            messagebox.showinfo("Export", "No fixed assets to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Fixed Asset Register",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"fixed_asset_register_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            db.export_fixed_asset_register_to_csv(path, company_id=self.company_id)
            messagebox.showinfo("Export Successful", f"Fixed Asset Register exported successfully to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)
