"""
ui/tax_manager_dialog.py
Tax Rates Configuration & VAT / GST Statutory Return Dashboard (v4.0).

Features:
- Tab 1: Tax Rates Master Registry (Add, Edit, Set Default, Deactivate)
- Tab 2: VAT Return Calculator & Statement (Box 1-5 computation, transaction breakdown, PDF & CSV export)
"""

import os
import csv
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from reports.vat_return import generate_vat_return_pdf
from ui.dialogs import PdfViewerDialog


# =========================================================================
# 1. TAX RATE ENTRY DIALOG
# =========================================================================

class TaxRateEntryDialog(tb.Toplevel):
    """Modal dialog to create or edit a tax rate preset."""

    def __init__(self, parent, company_id=None, tax_rate_id=None, on_saved_callback=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.tax_rate_id = tax_rate_id
        self.on_saved_callback = on_saved_callback

        self.title("Edit Tax Rate" if tax_rate_id else "Add New Tax Rate")
        self.geometry("460x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._load_data()
        self._build_ui()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _load_data(self):
        if self.tax_rate_id:
            self.tax = db.get_tax_rate(self.tax_rate_id) or {}
        else:
            self.tax = {
                "name": "",
                "code": "",
                "rate": 0.18,
                "tax_type": "VAT",
                "is_default": 0,
                "is_active": 1,
            }

    def _build_ui(self):
        pad = tb.Frame(self, padding=20)
        pad.pack(fill=BOTH, expand=True)

        tb.Label(pad, text="🏛️ Tax Rate Configuration", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 14))

        # Row 1: Name and Code
        r1 = tb.Frame(pad)
        r1.pack(fill=X, pady=(0, 10))

        c1 = tb.Frame(r1)
        c1.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c1, text="Tax Name *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.name_var = tk.StringVar(value=self.tax.get("name", ""))
        tb.Entry(c1, textvariable=self.name_var).pack(fill=X, pady=(2, 0))

        c2 = tb.Frame(r1)
        c2.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c2, text="Tax Code * (e.g. VAT18):", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.code_var = tk.StringVar(value=self.tax.get("code", ""))
        tb.Entry(c2, textvariable=self.code_var).pack(fill=X, pady=(2, 0))

        # Row 2: Rate % and Tax Type
        r2 = tb.Frame(pad)
        r2.pack(fill=X, pady=(0, 10))

        c3 = tb.Frame(r2)
        c3.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c3, text="Tax Rate (%) *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        # Display as e.g. 18.0
        rate_pct = float(self.tax.get("rate") or 0.0) * 100.0 if float(self.tax.get("rate") or 0.0) <= 1.0 else float(self.tax.get("rate") or 0.0)
        self.rate_var = tk.StringVar(value=f"{rate_pct:.2f}")
        tb.Entry(c3, textvariable=self.rate_var).pack(fill=X, pady=(2, 0))

        c4 = tb.Frame(r2)
        c4.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c4, text="Tax Type:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.type_var = tk.StringVar(value=self.tax.get("tax_type", "VAT"))
        tb.Combobox(c4, textvariable=self.type_var, values=["VAT", "GST", "WHT", "Custom"], state="readonly").pack(fill=X, pady=(2, 0))

        # Row 3: Notes
        tb.Label(pad, text="Description / Notes:", font=("Segoe UI", 8)).pack(anchor=W, pady=(4, 0))
        self.notes_var = tk.StringVar(value=self.tax.get("notes", ""))
        tb.Entry(pad, textvariable=self.notes_var).pack(fill=X, pady=(2, 12))

        # Row 4: Switches
        r4 = tb.Frame(pad)
        r4.pack(fill=X, pady=(0, 16))

        self.def_var = tk.BooleanVar(value=bool(self.tax.get("is_default", 0)))
        tb.Checkbutton(r4, text="Set as Default Tax Rate", variable=self.def_var, bootstyle="round-toggle").pack(side=LEFT, padx=(0, 16))

        self.act_var = tk.BooleanVar(value=bool(self.tax.get("is_active", 1)))
        tb.Checkbutton(r4, text="Active", variable=self.act_var, bootstyle="round-toggle").pack(side=LEFT)

        # Buttons
        btns = tb.Frame(pad)
        btns.pack(fill=X, side=BOTTOM)

        tb.Button(btns, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btns, text="Save Tax Rate", bootstyle="success", command=self._save).pack(side=RIGHT)

    def _save(self):
        name = self.name_var.get().strip()
        code = self.code_var.get().strip().upper()
        if not name or not code:
            messagebox.showwarning("Missing Fields", "Please enter both Tax Name and Tax Code.", parent=self)
            return

        try:
            rate_val = float(self.rate_var.get().replace("%", "").strip())
        except ValueError:
            messagebox.showwarning("Invalid Rate", "Please enter a valid numeric tax percentage.", parent=self)
            return

        data = {
            "company_id": self.company_id,
            "name": name,
            "code": code,
            "rate": rate_val,
            "tax_type": self.type_var.get().strip(),
            "is_default": 1 if self.def_var.get() else 0,
            "is_active": 1 if self.act_var.get() else 0,
            "notes": self.notes_var.get().strip(),
        }

        try:
            if self.tax_rate_id:
                db.update_tax_rate(self.tax_rate_id, data)
                messagebox.showinfo("Success", f"Tax rate {code} updated successfully.", parent=self)
            else:
                db.create_tax_rate(data)
                messagebox.showinfo("Success", f"Tax rate {code} created successfully.", parent=self)

            if self.on_saved_callback:
                self.on_saved_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save tax rate:\n{e}", parent=self)


# =========================================================================
# 2. MAIN TAX & VAT MANAGER DIALOG
# =========================================================================

class TaxManagerDialog(tb.Toplevel):
    """
    Unified Tax Management Dashboard:
    - Tab 1: 🏛️ Tax Rates & Presets Registry
    - Tab 2: 📊 VAT / GST Statutory Return Calculator & Statement
    """

    def __init__(self, parent, company_id=None, initial_tab=0):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Tax Management & VAT / GST Statutory Returns (v4.0)")
        self.geometry("1100x680")
        self.minsize(920, 520)
        self.transient(parent)

        self._build_tabs(initial_tab)
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_tabs(self, initial_tab=0):
        nb = tb.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=12, pady=12)

        # Tab 1: Tax Rates Registry
        t1 = tb.Frame(nb, padding=12)
        nb.add(t1, text="  🏛️ Tax Rates & Presets  ")
        self._build_rates_tab(t1)

        # Tab 2: VAT Return Dashboard
        t2 = tb.Frame(nb, padding=12)
        nb.add(t2, text="  📊 VAT / GST Statutory Return  ")
        self._build_vat_return_tab(t2)

        nb.select(initial_tab)

    # ---------------------------------------------------------------------
    # TAB 1: TAX RATES
    # ---------------------------------------------------------------------
    def _build_rates_tab(self, frame):
        hdr = tb.Frame(frame)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="🏛️ Configured Tax Rates & Presets", font=("Segoe UI", 13, "bold")).pack(side=LEFT)
        tb.Button(hdr, text="➕ Add Tax Rate", bootstyle="success", command=self._add_tax_rate).pack(side=RIGHT)

        tree_frame = tb.Frame(frame)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "code", "name", "rate", "type", "default", "status")
        self.rates_tree = tb.Treeview(tree_frame, columns=cols, show="headings", height=14)

        col_heads = [
            ("id", "ID", 50, "center"),
            ("code", "Tax Code", 100, "center"),
            ("name", "Tax Name", 220, "w"),
            ("rate", "Rate (%)", 110, "e"),
            ("type", "Type", 90, "center"),
            ("default", "Default", 90, "center"),
            ("status", "Status", 90, "center"),
        ]
        for c, h, w, anch in col_heads:
            self.rates_tree.heading(c, text=h)
            self.rates_tree.column(c, width=w, anchor=anch)

        sb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.rates_tree.yview)
        self.rates_tree.configure(yscrollcommand=sb.set)
        self.rates_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        self.rates_tree.bind("<Double-1>", lambda e: self._edit_tax_rate())

        # Buttons
        act = tb.Frame(frame)
        act.pack(fill=X, pady=(10, 0))

        tb.Button(act, text="✏️ Edit", bootstyle="primary-outline", command=self._edit_tax_rate).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="⭐ Set as Default", bootstyle="warning-outline", command=self._set_default_rate).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🔄 Toggle Status", bootstyle="secondary-outline", command=self._toggle_rate_status).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=self._delete_tax_rate).pack(side=LEFT)

        self._refresh_rates()

    def _refresh_rates(self):
        for i in self.rates_tree.get_children():
            self.rates_tree.delete(i)

        rates = db.get_tax_rates(company_id=self.company_id)
        for r in rates:
            rp = float(r.get("rate") or 0.0) * 100.0
            def_str = "⭐ Yes" if r.get("is_default") else "No"
            st_str = "Active" if r.get("is_active") else "Inactive"
            self.rates_tree.insert("", END, values=(
                r["id"],
                r["code"],
                r["name"],
                f"{rp:.1f}%",
                r.get("tax_type", "VAT"),
                def_str,
                st_str
            ))

    def _add_tax_rate(self):
        TaxRateEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_rates)

    def _edit_tax_rate(self):
        sel = self.rates_tree.selection()
        if not sel:
            return
        tid = int(self.rates_tree.item(sel[0])["values"][0])
        TaxRateEntryDialog(self, company_id=self.company_id, tax_rate_id=tid, on_saved_callback=self._refresh_rates)

    def _set_default_rate(self):
        sel = self.rates_tree.selection()
        if not sel:
            return
        tid = int(self.rates_tree.item(sel[0])["values"][0])
        db.set_default_tax_rate(self.company_id, tid)
        self._refresh_rates()

    def _toggle_rate_status(self):
        sel = self.rates_tree.selection()
        if not sel:
            return
        tid = int(self.rates_tree.item(sel[0])["values"][0])
        tr = db.get_tax_rate(tid)
        if tr:
            new_st = 0 if tr.get("is_active") else 1
            db.update_tax_rate(tid, {**tr, "is_active": new_st})
            self._refresh_rates()

    def _delete_tax_rate(self):
        sel = self.rates_tree.selection()
        if not sel:
            return
        tid = int(self.rates_tree.item(sel[0])["values"][0])
        code = self.rates_tree.item(sel[0])["values"][1]
        if messagebox.askyesno("Confirm Delete", f"Delete tax rate preset '{code}'?", parent=self):
            ok, msg = db.delete_tax_rate(tid)
            if ok:
                messagebox.showinfo("Deleted", msg, parent=self)
                self._refresh_rates()
            else:
                messagebox.showwarning("Cannot Delete", msg, parent=self)

    # ---------------------------------------------------------------------
    # TAB 2: VAT RETURN CALCULATOR
    # ---------------------------------------------------------------------
    def _build_vat_return_tab(self, frame):
        # Top Period Selection
        flt = tb.Frame(frame)
        flt.pack(fill=X, pady=(0, 10))

        tb.Label(flt, text="Filing Period Preset:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 6))
        self.preset_combo = tb.Combobox(
            flt,
            values=["Current Month", "Last Month", "Q1 (Jan - Mar)", "Q2 (Apr - Jun)", "Q3 (Jul - Sep)", "Q4 (Oct - Dec)", "Year to Date (YTD)"],
            state="readonly",
            width=18
        )
        self.preset_combo.current(0)
        self.preset_combo.pack(side=LEFT, padx=(0, 14))
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        tb.Label(flt, text="Start:").pack(side=LEFT, padx=(0, 4))
        self.start_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-01"))
        tb.Entry(flt, textvariable=self.start_var, width=11).pack(side=LEFT, padx=(0, 8))

        tb.Label(flt, text="End:").pack(side=LEFT, padx=(0, 4))
        self.end_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(flt, textvariable=self.end_var, width=11).pack(side=LEFT, padx=(0, 12))

        tb.Button(flt, text="🔄 Calculate Return", bootstyle="primary", command=self._compute_vat_return).pack(side=LEFT)

        # KPI Summary Cards (Box 1 - 5)
        kpi_frame = tb.Frame(frame, padding=(0, 6))
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.box1_kpi = self._create_kpi_card(kpi_frame, "BOX 1: SALES", "0.00", "info")
        self.box2_kpi = self._create_kpi_card(kpi_frame, "BOX 2: OUTPUT VAT", "0.00", "primary")
        self.box3_kpi = self._create_kpi_card(kpi_frame, "BOX 3: PURCHASES", "0.00", "secondary")
        self.box4_kpi = self._create_kpi_card(kpi_frame, "BOX 4: INPUT VAT", "0.00", "warning")
        self.box5_kpi = self._create_kpi_card(kpi_frame, "BOX 5: NET PAYABLE", "0.00", "danger")

        # Sub-Notebook for Output Tax and Input Tax transactions
        sub_nb = tb.Notebook(frame)
        sub_nb.pack(fill=BOTH, expand=True)

        # Sub-Tab A: Sales Invoices (Output Tax)
        st_a = tb.Frame(sub_nb, padding=6)
        sub_nb.add(st_a, text="  Schedule A: Output Tax (Sales Invoices)  ")
        self._build_sales_tree(st_a)

        # Sub-Tab B: Purchases (Input Tax)
        st_b = tb.Frame(sub_nb, padding=6)
        sub_nb.add(st_b, text="  Schedule B: Input Tax (Supplier Bills)  ")
        self._build_purch_tree(st_b)

        # Bottom Export Actions
        bot = tb.Frame(frame)
        bot.pack(fill=X, pady=(10, 0))

        tb.Button(bot, text="📄 Export Official VAT Return (PDF)", bootstyle="success", command=self._export_vat_pdf).pack(side=LEFT, padx=(0, 6))
        tb.Button(bot, text="📊 Export Transactions (CSV)", bootstyle="info-outline", command=self._export_vat_csv).pack(side=LEFT)

        tb.Button(bot, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

        # Compute initial
        self._compute_vat_return()

    def _create_kpi_card(self, parent, title, val, style):
        card = tb.Frame(parent, bootstyle=f"{style}", padding=8)
        card.pack(side=LEFT, fill=X, expand=True, padx=3)
        tb.Label(card, text=title, font=("Segoe UI", 7, "bold"), bootstyle=f"inverse-{style}").pack(anchor=W)
        lbl = tb.Label(card, text=f"{self.currency} {val}", font=("Segoe UI", 11, "bold"), bootstyle=f"inverse-{style}")
        lbl.pack(anchor=W, pady=(2, 0))
        return lbl

    def _build_sales_tree(self, parent):
        cols = ("date", "invoice_num", "customer", "taxable", "tax", "total")
        self.sales_tree = tb.Treeview(parent, columns=cols, show="headings", height=8)
        self.sales_tree.heading("date", text="Date")
        self.sales_tree.heading("invoice_num", text="Invoice #")
        self.sales_tree.heading("customer", text="Customer Name")
        self.sales_tree.heading("taxable", text="Taxable Value (LKR)")
        self.sales_tree.heading("tax", text="Output VAT (LKR)")
        self.sales_tree.heading("total", text="Total Invoice (LKR)")

        self.sales_tree.column("date", width=90, anchor="center")
        self.sales_tree.column("invoice_num", width=120, anchor="center")
        self.sales_tree.column("customer", width=240, anchor="w")
        self.sales_tree.column("taxable", width=130, anchor="e")
        self.sales_tree.column("tax", width=130, anchor="e")
        self.sales_tree.column("total", width=130, anchor="e")

        sb = tb.Scrollbar(parent, orient=VERTICAL, command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=sb.set)
        self.sales_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

    def _build_purch_tree(self, parent):
        cols = ("date", "invoice_num", "supplier", "taxable", "tax", "total")
        self.purch_tree = tb.Treeview(parent, columns=cols, show="headings", height=8)
        self.purch_tree.heading("date", text="Date")
        self.purch_tree.heading("invoice_num", text="Bill / Ref #")
        self.purch_tree.heading("supplier", text="Supplier Name")
        self.purch_tree.heading("taxable", text="Taxable Value (LKR)")
        self.purch_tree.heading("tax", text="Input VAT (LKR)")
        self.purch_tree.heading("total", text="Total Bill (LKR)")

        self.purch_tree.column("date", width=90, anchor="center")
        self.purch_tree.column("invoice_num", width=120, anchor="center")
        self.purch_tree.column("supplier", width=240, anchor="w")
        self.purch_tree.column("taxable", width=130, anchor="e")
        self.purch_tree.column("tax", width=130, anchor="e")
        self.purch_tree.column("total", width=130, anchor="e")

        sb = tb.Scrollbar(parent, orient=VERTICAL, command=self.purch_tree.yview)
        self.purch_tree.configure(yscrollcommand=sb.set)
        self.purch_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

    def _on_preset_selected(self, event=None):
        val = self.preset_combo.get()
        today = datetime.now()
        year = today.year

        if val == "Current Month":
            self.start_var.set(today.strftime("%Y-%m-01"))
            self.end_var.set(today.strftime("%Y-%m-%d"))
        elif val == "Last Month":
            first = today.replace(day=1)
            prev_last = first - datetime.resolution
            self.start_var.set(prev_last.strftime("%Y-%m-01"))
            self.end_var.set(prev_last.strftime("%Y-%m-%d"))
        elif val == "Q1 (Jan - Mar)":
            self.start_var.set(f"{year}-01-01")
            self.end_var.set(f"{year}-03-31")
        elif val == "Q2 (Apr - Jun)":
            self.start_var.set(f"{year}-04-01")
            self.end_var.set(f"{year}-06-30")
        elif val == "Q3 (Jul - Sep)":
            self.start_var.set(f"{year}-07-01")
            self.end_var.set(f"{year}-09-30")
        elif val == "Q4 (Oct - Dec)":
            self.start_var.set(f"{year}-10-01")
            self.end_var.set(f"{year}-12-31")
        elif val == "Year to Date (YTD)":
            self.start_var.set(f"{year}-01-01")
            self.end_var.set(today.strftime("%Y-%m-%d"))

        self._compute_vat_return()

    def _compute_vat_return(self):
        s = self.start_var.get().strip()
        e = self.end_var.get().strip()
        if not s or not e:
            return

        self.vat_res = db.generate_vat_return(self.company_id, s, e)

        # Update KPI Cards
        b1 = self.vat_res["box1_sales"]
        b2 = self.vat_res["box2_output_vat"]
        b3 = self.vat_res["box3_purchases"]
        b4 = self.vat_res["box4_input_vat"]
        b5 = self.vat_res["box5_net_payable"]

        self.box1_kpi.configure(text=f"{self.currency} {b1:,.2f}")
        self.box2_kpi.configure(text=f"{self.currency} {b2:,.2f}")
        self.box3_kpi.configure(text=f"{self.currency} {b3:,.2f}")
        self.box4_kpi.configure(text=f"{self.currency} {b4:,.2f}")

        if b5 < 0:
            self.box5_kpi.configure(text=f"({self.currency} {abs(b5):,.2f}) Credit")
        else:
            self.box5_kpi.configure(text=f"{self.currency} {b5:,.2f} Payable")

        # Update Sales Tree
        for i in self.sales_tree.get_children():
            self.sales_tree.delete(i)
        for row in self.vat_res.get("sales_transactions", []):
            self.sales_tree.insert("", END, values=(
                row["invoice_date"],
                row["invoice_number"],
                row["customer_name"],
                f"{float(row['taxable_amount']):,.2f}",
                f"{float(row['tax_amount']):,.2f}",
                f"{float(row['total_amount']):,.2f}"
            ))

        # Update Purchase Tree
        for i in self.purch_tree.get_children():
            self.purch_tree.delete(i)
        for row in self.vat_res.get("purchase_transactions", []):
            self.purch_tree.insert("", END, values=(
                row["invoice_date"],
                row["invoice_number"],
                row["supplier_name"],
                f"{float(row['taxable_amount']):,.2f}",
                f"{float(row['tax_amount']):,.2f}",
                f"{float(row['total_amount']):,.2f}"
            ))

    def _export_vat_pdf(self):
        if not hasattr(self, "vat_res"):
            return
        pdf_path = generate_vat_return_pdf(self.vat_res)
        PdfViewerDialog(self.master, pdf_path, title=f"VAT Return — {self.vat_res['period_start']} to {self.vat_res['period_end']}")

    def _export_vat_csv(self):
        if not hasattr(self, "vat_res"):
            return
        fp = filedialog.asksaveasfilename(
            parent=self,
            title="Export VAT Statement to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")],
            initialfile=f"vat_statement_{self.vat_res['period_start']}_{self.vat_res['period_end']}.csv"
        )
        if not fp:
            return

        with open(fp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["STATUTORY VAT RETURN STATEMENT"])
            w.writerow(["Company", self.vat_res["company_name"]])
            w.writerow(["Filing Period", f"{self.vat_res['period_start']} to {self.vat_res['period_end']}"])
            w.writerow(["Currency", self.vat_res["currency"]])
            w.writerow([])
            w.writerow(["SUMMARY SCHEDULE (BOX 1 - 5)"])
            w.writerow(["Box 1: Total Taxable Sales (Supplies)", f"{self.vat_res['box1_sales']:.2f}"])
            w.writerow(["Box 2: Output VAT Charged", f"{self.vat_res['box2_output_vat']:.2f}"])
            w.writerow(["Box 3: Total Taxable Purchases (Inputs)", f"{self.vat_res['box3_purchases']:.2f}"])
            w.writerow(["Box 4: Input VAT Paid", f"{self.vat_res['box4_input_vat']:.2f}"])
            w.writerow(["Box 5: Net VAT Payable / (Credit Due)", f"{self.vat_res['box5_net_payable']:.2f}"])
            w.writerow([])
            w.writerow(["SCHEDULE A: OUTPUT TAX TRANSACTIONS (SALES)"])
            w.writerow(["Date", "Invoice #", "Customer", "Taxable Value", "Output VAT", "Total"])
            for r in self.vat_res.get("sales_transactions", []):
                w.writerow([r["invoice_date"], r["invoice_number"], r["customer_name"], r["taxable_amount"], r["tax_amount"], r["total_amount"]])
            w.writerow([])
            w.writerow(["SCHEDULE B: INPUT TAX TRANSACTIONS (PURCHASES)"])
            w.writerow(["Date", "Bill #", "Supplier", "Taxable Value", "Input VAT", "Total"])
            for r in self.vat_res.get("purchase_transactions", []):
                w.writerow([r["invoice_date"], r["invoice_number"], r["supplier_name"], r["taxable_amount"], r["tax_amount"], r["total_amount"]])

        messagebox.showinfo("Exported", f"VAT statement successfully exported to:\n{fp}", parent=self)
