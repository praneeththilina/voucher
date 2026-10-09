"""
ui/ap_invoice_dialog.py
Accounts Payable (AP) Supplier Invoicing, Bill Management & Aging Interface (v3.5).

Provides:
- APInvoiceEntryDialog: Create & Edit supplier invoices with line items and COA expense mapping.
- APInvoiceListDialog: Main AP register with KPIs, filters, status tracking, and PDF printing.
- APPaymentDialog: Record payment settlements with auto double-entry journal linkage.
- APAgingDialog: Multi-bucket visual aging report (Current, 1-30d, 31-60d, 61-90d, >90d).
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import invoice_printer
from ui.pdf_viewer import PdfViewerDialog


class APInvoiceEntryDialog(tb.Toplevel):
    """Dialog for creating or editing an Accounts Payable supplier invoice."""

    def __init__(self, parent, company_id=None, invoice_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.invoice_id = invoice_id
        self.is_edit = bool(self.invoice_id)
        self.on_saved = on_saved
        self.home_currency = db.get_company_base_currency(self.company_id).upper()
        self.currency_values = [self.home_currency]
        if db.is_multicurrency_enabled(self.company_id):
            self.currency_values = [
                row["code"] for row in db.get_currencies(active_only=True)
            ]

        self.title("Edit Supplier Invoice" if self.is_edit else "New Supplier Invoice (AP Bill)")
        self.geometry("920x680")
        self.minsize(780, 560)
        self.transient(parent)
        self.grab_set()

        self.suppliers = db.get_suppliers(company_id=self.company_id, active_only=True)
        self.supplier_lookup = {s["name"]: s for s in self.suppliers}

        self.coa_accounts = db.get_chart_of_accounts(company_id=self.company_id, account_type="Expense", active_only=True)
        self.coa_lookup = {f"{a['account_code']} - {a['account_name']}": a for a in self.coa_accounts}

        self.lines_data = []

        self._build_ui()
        if self.is_edit:
            self._load_invoice_data()
        else:
            self._init_defaults()

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
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="Supplier Invoice (AP Bill)", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(
            hdr,
            text="Enter vendor invoice details, expense categorization, and payment due terms.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # Invoice Header Details Box
        form_box = tb.Labelframe(root, text="Invoice Information", padding=12)
        form_box.pack(fill=X, pady=(0, 10))

        # Row 1: Supplier, Invoice Number, Internal Ref
        r1 = tb.Frame(form_box)
        r1.pack(fill=X, pady=4)

        tb.Label(r1, text="Supplier *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.supplier_var = tk.StringVar()
        sup_names = list(self.supplier_lookup.keys())
        self.sup_combo = tb.Combobox(r1, textvariable=self.supplier_var, values=sup_names, width=28)
        self.sup_combo.pack(side=LEFT, padx=(0, 6))
        self.sup_combo.bind("<<ComboboxSelected>>", self._on_supplier_selected)

        tb.Button(r1, text="➕", bootstyle="outline", width=3, command=self._quick_add_supplier).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Invoice # *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.inv_num_var = tk.StringVar()
        tb.Entry(r1, textvariable=self.inv_num_var, width=16).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Internal Ref / PO:").pack(side=LEFT, padx=(0, 4))
        self.ref_var = tk.StringVar()
        tb.Entry(r1, textvariable=self.ref_var, width=16).pack(side=LEFT)

        # Row 2: Invoice Date, Due Date, Currency
        r2 = tb.Frame(form_box)
        r2.pack(fill=X, pady=4)

        tb.Label(r2, text="Invoice Date (YYYY-MM-DD):").pack(side=LEFT, padx=(0, 4))
        self.inv_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.inv_date_entry = tb.Entry(r2, textvariable=self.inv_date_var, width=14)
        self.inv_date_entry.pack(side=LEFT, padx=(0, 16))
        self.inv_date_entry.bind("<KeyRelease>", lambda e: self._recalc_due_date())

        tb.Label(r2, text="Due Date (YYYY-MM-DD):").pack(side=LEFT, padx=(0, 4))
        self.due_date_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.due_date_var, width=14).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Currency:").pack(side=LEFT, padx=(0, 4))
        self.curr_var = tk.StringVar(value=self.home_currency)
        self.curr_combo = tb.Combobox(
            r2, textvariable=self.curr_var, values=self.currency_values,
            width=8, state="readonly" if len(self.currency_values) > 1 else "disabled"
        )
        self.curr_combo.pack(side=LEFT)
        self.curr_combo.bind("<<ComboboxSelected>>", self._currency_changed)
        tb.Label(r2, text="Rate:").pack(side=LEFT, padx=(8, 4))
        self.rate_var = tk.StringVar(value="1.000000")
        self.rate_entry = tb.Entry(r2, textvariable=self.rate_var, width=11)
        self.rate_entry.pack(side=LEFT)
        self.rate_entry.configure(state="disabled")

        # Line Items Grid
        lines_box = tb.Labelframe(root, text="Bill Line Items", padding=10)
        lines_box.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Add line strip
        add_strip = tb.Frame(lines_box)
        add_strip.pack(fill=X, pady=(0, 8))

        tb.Label(add_strip, text="Item Description:").pack(side=LEFT, padx=(0, 4))
        self.line_desc_var = tk.StringVar()
        tb.Entry(add_strip, textvariable=self.line_desc_var, width=22).pack(side=LEFT, padx=(0, 8))

        tb.Label(add_strip, text="Expense Account:").pack(side=LEFT, padx=(0, 4))
        self.line_acct_var = tk.StringVar()
        coa_names = list(self.coa_lookup.keys())
        self.acct_combo = tb.Combobox(add_strip, textvariable=self.line_acct_var, values=coa_names, width=24)
        self.acct_combo.pack(side=LEFT, padx=(0, 8))

        tb.Label(add_strip, text="Qty:").pack(side=LEFT, padx=(0, 4))
        self.line_qty_var = tk.StringVar(value="1.0")
        tb.Entry(add_strip, textvariable=self.line_qty_var, width=6).pack(side=LEFT, padx=(0, 8))

        tb.Label(add_strip, text="Price:").pack(side=LEFT, padx=(0, 4))
        self.line_price_var = tk.StringVar()
        tb.Entry(add_strip, textvariable=self.line_price_var, width=10).pack(side=LEFT, padx=(0, 8))

        tb.Label(add_strip, text="Tax (%):").pack(side=LEFT, padx=(0, 4))
        self.line_tax_var = tk.StringVar(value="0")
        tb.Combobox(add_strip, textvariable=self.line_tax_var, values=["0", "18", "8", "2.5"], width=6).pack(side=LEFT, padx=(0, 8))

        tb.Button(add_strip, text="➕ Add Line", bootstyle="success-outline", command=self._add_line).pack(side=LEFT)

        # Line items Treeview
        table_frame = tb.Frame(lines_box)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("num", "desc", "account", "qty", "price", "tax", "total")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse", height=5)

        self.tree.heading("num", text="#", anchor=CENTER)
        self.tree.heading("desc", text="Description", anchor=W)
        self.tree.heading("account", text="Expense Account", anchor=W)
        self.tree.heading("qty", text="Qty", anchor=E)
        self.tree.heading("price", text="Unit Price", anchor=E)
        self.tree.heading("tax", text="Tax (LKR)", anchor=E)
        self.tree.heading("total", text="Total (LKR)", anchor=E)

        self.tree.column("num", width=40, anchor=CENTER)
        self.tree.column("desc", width=220, anchor=W)
        self.tree.column("account", width=180, anchor=W)
        self.tree.column("qty", width=60, anchor=E)
        self.tree.column("price", width=95, anchor=E)
        self.tree.column("tax", width=85, anchor=E)
        self.tree.column("total", width=110, anchor=E)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        tb.Button(
            lines_box,
            text="🗑️ Remove Line",
            bootstyle="danger-outline",
            command=self._remove_line
        ).pack(anchor=W, pady=(6, 0))

        # Bottom Totals & Discount Card
        bottom_panel = tb.Frame(root)
        bottom_panel.pack(fill=X, pady=(0, 10))

        # Left: Notes
        left_notes = tb.Frame(bottom_panel)
        left_notes.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 20))
        tb.Label(left_notes, text="Notes / Memo:").pack(anchor=W)
        self.notes_entry = tb.Entry(left_notes, width=40)
        self.notes_entry.pack(fill=X, pady=(2, 0))

        # Right: Financial summary box
        totals_card = tb.Labelframe(bottom_panel, text="Financial Summary", padding=10)
        totals_card.pack(side=RIGHT)

        t_grid = tb.Frame(totals_card)
        t_grid.pack()

        tb.Label(t_grid, text="Subtotal:").grid(row=0, column=0, sticky=W, padx=4, pady=2)
        self.subtotal_lbl = tb.Label(t_grid, text="LKR 0.00", font=("Segoe UI", 9, "bold"))
        self.subtotal_lbl.grid(row=0, column=1, sticky=E, padx=4, pady=2)

        tb.Label(t_grid, text="Discount:").grid(row=1, column=0, sticky=W, padx=4, pady=2)
        self.discount_var = tk.StringVar(value="0.00")
        disc_entry = tb.Entry(t_grid, textvariable=self.discount_var, width=12)
        disc_entry.grid(row=1, column=1, sticky=E, padx=4, pady=2)
        disc_entry.bind("<KeyRelease>", lambda e: self._recalculate_totals())

        tb.Label(t_grid, text="VAT / Tax:").grid(row=2, column=0, sticky=W, padx=4, pady=2)
        self.tax_lbl = tb.Label(t_grid, text="LKR 0.00", font=("Segoe UI", 9, "bold"))
        self.tax_lbl.grid(row=2, column=1, sticky=E, padx=4, pady=2)

        tb.Label(t_grid, text="Grand Total:", font=("Segoe UI", 11, "bold")).grid(row=3, column=0, sticky=W, padx=4, pady=4)
        self.total_lbl = tb.Label(t_grid, text="LKR 0.00", font=("Segoe UI", 12, "bold"), bootstyle="primary")
        self.total_lbl.grid(row=3, column=1, sticky=E, padx=4, pady=4)

        # Footer Actions
        footer = tb.Frame(root)
        footer.pack(fill=X)

        tb.Button(footer, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        self.save_btn = tb.Button(footer, text="Save Supplier Invoice", bootstyle="primary", command=self._save_invoice)
        self.save_btn.pack(side=RIGHT)

    def _currency_changed(self, event=None):
        code = self.curr_var.get() or self.home_currency
        if code == self.home_currency:
            self.rate_var.set("1.000000")
            self.rate_entry.configure(state="disabled")
        else:
            rate = db.get_exchange_rate(code, self.home_currency)
            self.rate_var.set(f"{float(rate['rate']):.6f}" if rate else "")
            self.rate_entry.configure(state="normal")
        self._recalculate_totals()

    def _init_defaults(self):
        self._currency_changed()
        self._recalc_due_date()
        self._recalculate_totals()

    def _on_supplier_selected(self, event=None):
        self._recalc_due_date()

    def _recalc_due_date(self):
        try:
            inv_dt = datetime.strptime(self.inv_date_var.get().strip(), "%Y-%m-%d")
        except Exception:
            inv_dt = datetime.now()

        terms = 30
        sup_name = self.supplier_var.get().strip()
        if sup_name in self.supplier_lookup:
            terms = int(self.supplier_lookup[sup_name].get("payment_terms") or 30)

        due_dt = inv_dt + timedelta(days=terms)
        self.due_date_var.set(due_dt.strftime("%Y-%m-%d"))

    def _quick_add_supplier(self):
        from ui.supplier_manager import SupplierEditModal

        def on_saved():
            self.suppliers = db.get_suppliers(company_id=self.company_id, active_only=True)
            self.supplier_lookup = {s["name"]: s for s in self.suppliers}
            self.sup_combo["values"] = list(self.supplier_lookup.keys())

        SupplierEditModal(self, company_id=self.company_id, on_saved=on_saved)

    def _load_invoice_data(self):
        inv_data = db.get_ap_invoice(self.invoice_id)
        if not inv_data:
            messagebox.showerror("Error", "Invoice not found.", parent=self)
            self.destroy()
            return

        h = inv_data["invoice"]
        lines = inv_data["lines"]

        self.supplier_var.set(h.get("supplier_name", ""))
        self.inv_num_var.set(h.get("invoice_number", ""))
        self.ref_var.set(h.get("internal_ref", ""))
        self.inv_date_var.set(h.get("invoice_date", ""))
        self.due_date_var.set(h.get("due_date", ""))
        self.curr_var.set(h.get("currency") or self.home_currency)
        self.rate_var.set(f"{float(h.get('exchange_rate') or 1):.6f}")
        self._currency_changed()
        self.rate_var.set(f"{float(h.get('exchange_rate') or 1):.6f}")
        self.discount_var.set(f"{float(h.get('discount_amount') or 0.0):.2f}")
        if h.get("notes"):
            self.notes_entry.insert(0, h["notes"])

        for l in lines:
            acct_lbl = ""
            if l.get("account_id"):
                for name, a in self.coa_lookup.items():
                    if a["id"] == l["account_id"]:
                        acct_lbl = name
                        break

            self.lines_data.append({
                "description": l.get("description", ""),
                "account_id": l.get("account_id"),
                "account_label": acct_lbl,
                "quantity": float(l.get("quantity") or 1.0),
                "unit_price": float(l.get("unit_price") or 0.0),
                "tax_rate": float(l.get("tax_rate") or 0.0),
                "tax_amount": float(l.get("tax_amount") or 0.0),
                "line_total": float(l.get("line_total") or 0.0)
            })

        self._refresh_lines_table()
        self._recalculate_totals()

    def _add_line(self):
        desc = self.line_desc_var.get().strip()
        if not desc:
            messagebox.showwarning("Validation", "Item description is required.", parent=self)
            return

        try:
            qty = float(self.line_qty_var.get().strip() or 1.0)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation", "Quantity must be a positive number.", parent=self)
            return

        try:
            price = float(self.line_price_var.get().strip().replace(",", "") or 0.0)
            if price < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation", "Unit price must be a valid positive number.", parent=self)
            return

        try:
            tax_rate = float(self.line_tax_var.get().strip() or 0.0)
        except ValueError:
            tax_rate = 0.0

        sub = qty * price
        tax_amt = round(sub * (tax_rate / 100.0), 2)
        total = round(sub + tax_amt, 2)

        acct_id = None
        acct_lbl = self.line_acct_var.get().strip()
        if acct_lbl in self.coa_lookup:
            acct_id = self.coa_lookup[acct_lbl]["id"]

        self.lines_data.append({
            "description": desc,
            "account_id": acct_id,
            "account_label": acct_lbl,
            "quantity": qty,
            "unit_price": price,
            "tax_rate": tax_rate,
            "tax_amount": tax_amt,
            "line_total": total
        })

        self.line_desc_var.set("")
        self.line_price_var.set("")
        self.line_qty_var.set("1.0")

        self._refresh_lines_table()
        self._recalculate_totals()

    def _remove_line(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.lines_data):
            self.lines_data.pop(idx)
            self._refresh_lines_table()
            self._recalculate_totals()

    def _refresh_lines_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

        for idx, l in enumerate(self.lines_data):
            self.tree.insert(
                "",
                END,
                iid=str(idx),
                values=(
                    str(idx + 1),
                    l["description"],
                    l.get("account_label") or "—",
                    f"{l['quantity']:,.1f}",
                    f"{l['unit_price']:,.2f}",
                    f"{l['tax_amount']:,.2f}",
                    f"{l['line_total']:,.2f}"
                )
            )

    def _recalculate_totals(self):
        subtotal = sum(l["quantity"] * l["unit_price"] for l in self.lines_data)
        tax = sum(l["tax_amount"] for l in self.lines_data)

        try:
            discount = float(self.discount_var.get().strip().replace(",", "") or 0.0)
        except ValueError:
            discount = 0.0

        grand_total = max(0.0, round(subtotal + tax - discount, 2))

        code = self.curr_var.get() or self.home_currency
        self.subtotal_lbl.config(text=f"{code} {subtotal:,.2f}")
        self.tax_lbl.config(text=f"{code} {tax:,.2f}")
        self.total_lbl.config(text=f"{code} {grand_total:,.2f}")

    def _save_invoice(self):
        sup_name = self.supplier_var.get().strip()
        if not sup_name or sup_name not in self.supplier_lookup:
            messagebox.showwarning("Validation", "Please select a valid supplier from the list.", parent=self)
            return

        supplier = self.supplier_lookup[sup_name]
        inv_num = self.inv_num_var.get().strip()
        if not inv_num:
            messagebox.showwarning("Validation", "Supplier Invoice Number is required.", parent=self)
            return

        inv_date = self.inv_date_var.get().strip()
        due_date = self.due_date_var.get().strip()
        if not inv_date or not due_date:
            messagebox.showwarning("Validation", "Both Invoice Date and Due Date are required.", parent=self)
            return

        if not self.lines_data:
            messagebox.showwarning("Validation", "Please add at least one line item to this bill.", parent=self)
            return

        try:
            discount = float(self.discount_var.get().strip().replace(",", "") or 0.0)
        except ValueError:
            discount = 0.0

        invoice_data = {
            "company_id": self.company_id,
            "supplier_id": supplier["id"],
            "invoice_number": inv_num,
            "internal_ref": self.ref_var.get().strip(),
            "invoice_date": inv_date,
            "due_date": due_date,
            "discount_amount": discount,
            "currency": self.curr_var.get(),
            "exchange_rate": self.rate_var.get(),
            "notes": self.notes_entry.get().strip()
        }

        try:
            if self.is_edit:
                db.update_ap_invoice(self.invoice_id, invoice_data, self.lines_data)
            else:
                db.create_ap_invoice(invoice_data, self.lines_data)

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error Saving Invoice", str(e), parent=self)


class APPaymentDialog(tb.Toplevel):
    """Modal for recording a payment settlement against an AP invoice."""

    PAYMENT_METHODS = ["Cash", "Cheque", "Bank Transfer", "Credit Card", "Online/Other"]

    def __init__(self, parent, invoice_id, on_saved=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.on_saved = on_saved

        self.inv_data = db.get_ap_invoice(self.invoice_id)
        if not self.inv_data:
            messagebox.showerror("Error", "Invoice not found.", parent=self)
            self.destroy()
            return

        invoice = self.inv_data["invoice"]
        self.currency = (
            invoice.get("currency")
            or db.get_company_base_currency(invoice["company_id"])
        ).upper()
        accounts = db.get_currency_accounts(invoice["company_id"], self.currency)
        self.account_lookup = {
            f"{row['account_code']} - {row['account_name']} ({row['currency']})": row["id"]
            for row in accounts
        }
        self.title(f"Record Payment — Inv #{invoice['invoice_number']}")
        self.geometry("560x540")
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
        h = self.inv_data["invoice"]
        bal = float(h.get("balance_due") or 0.0)

        container = tb.Frame(self, padding=20)
        container.pack(fill=BOTH, expand=True)

        tb.Label(container, text="Record Bill Payment", font=("Segoe UI", 14, "bold")).pack(anchor=W)
        tb.Label(
            container,
            text=f"Settlement for {h['supplier_name']} (Invoice #{h['invoice_number']})",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 12))

        # Balance Info Box
        info_box = tb.Frame(container, padding=10)
        info_box.pack(fill=X, pady=(0, 12))

        tb.Label(info_box, text=f"Total Amount: {self.currency} {float(h['total_amount']):,.2f}").pack(anchor=W)
        tb.Label(info_box, text=f"Already Paid: {self.currency} {float(h['paid_amount']):,.2f}", bootstyle="success").pack(anchor=W)
        tb.Label(info_box, text=f"Balance Due: {self.currency} {bal:,.2f}", font=("Segoe UI", 10, "bold"), bootstyle="danger").pack(anchor=W)

        # Form
        form = tb.Frame(container)
        form.pack(fill=BOTH, expand=True)

        tb.Label(form, text=f"Payment Amount ({self.currency}) *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=6)
        self.amt_var = tk.StringVar(value=f"{bal:.2f}")
        tb.Entry(form, textvariable=self.amt_var, width=28).grid(row=0, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(form, text="Payment Date *:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky=W, pady=6)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(form, textvariable=self.date_var, width=28).grid(row=1, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(form, text="Payment Method *:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky=W, pady=6)
        self.pm_var = tk.StringVar(value="Bank Transfer")
        tb.Combobox(form, textvariable=self.pm_var, values=self.PAYMENT_METHODS, state="readonly", width=26).grid(row=2, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(form, text="Exchange Rate:").grid(row=3, column=0, sticky=W, pady=6)
        home = db.get_company_base_currency(h["company_id"]).upper()
        rate = db.get_exchange_rate(self.currency, home)
        initial_rate = 1.0 if self.currency == home else float(
            rate["rate"] if rate else h.get("exchange_rate") or 0
        )
        self.rate_var = tk.StringVar(value=f"{initial_rate:.6f}" if initial_rate else "")
        self.rate_entry = tb.Entry(form, textvariable=self.rate_var, width=28)
        self.rate_entry.grid(row=3, column=1, sticky=EW, pady=6, padx=(10, 0))
        if self.currency == home:
            self.rate_entry.configure(state="disabled")

        tb.Label(form, text="Pay From Account *:").grid(row=4, column=0, sticky=W, pady=6)
        self.account_var = tk.StringVar(
            value=next(iter(self.account_lookup), "")
        )
        tb.Combobox(
            form, textvariable=self.account_var,
            values=list(self.account_lookup), state="readonly", width=26
        ).grid(row=4, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(form, text="Reference / Cheque #:").grid(row=5, column=0, sticky=W, pady=6)
        self.ref_var = tk.StringVar()
        tb.Entry(form, textvariable=self.ref_var, width=28).grid(row=5, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(form, text="Notes / Memo:").grid(row=6, column=0, sticky=W, pady=6)
        self.notes_var = tk.StringVar()
        tb.Entry(form, textvariable=self.notes_var, width=28).grid(row=6, column=1, sticky=EW, pady=6, padx=(10, 0))

        form.columnconfigure(1, weight=1)

        # Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        tb.Button(btn_box, text="Confirm Payment", bootstyle="success", command=self._confirm_payment).pack(side=RIGHT)

    def _confirm_payment(self):
        try:
            amt = float(self.amt_var.get().strip().replace(",", ""))
            if amt <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation", "Payment amount must be greater than zero.", parent=self)
            return

        p_date = self.date_var.get().strip()
        if not p_date:
            messagebox.showwarning("Validation", "Payment date is required.", parent=self)
            return

        payload = {
            "invoice_id": self.invoice_id,
            "amount": amt,
            "payment_date": p_date,
            "payment_method": self.pm_var.get(),
            "reference": self.ref_var.get().strip(),
            "notes": self.notes_var.get().strip(),
            "currency": self.currency,
            "exchange_rate": self.rate_var.get(),
            "payment_account_id": self.account_lookup.get(self.account_var.get()),
            "created_by": "User"
        }

        try:
            db.record_ap_payment(payload)
            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


class APAgingDialog(tb.Toplevel):
    """Accounts Payable Aging Report dialog with 30-day buckets."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Accounts Payable Aging Analysis — Debt Overview")
        self.geometry("1000x620")
        self.minsize(820, 500)
        self.transient(parent)

        self.aging_cache = {}
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
        hdr.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(hdr)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="📊 Accounts Payable Aging Report", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        tb.Label(
            title_box,
            text=f"Company #{self.company_id} — Outstanding Vendor Liabilities by Due Date",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # Parameters Toolbar
        tb_bar = tb.Labelframe(root, text="Parameters", padding=10)
        tb_bar.pack(fill=X, pady=(0, 10))

        tb.Label(tb_bar, text="As of Date:").pack(side=LEFT, padx=(0, 4))
        self.as_of_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(tb_bar, textvariable=self.as_of_var, width=14).pack(side=LEFT, padx=(0, 12))

        tb.Button(tb_bar, text="Calculate Aging", bootstyle="primary", command=self.refresh).pack(side=LEFT, padx=(0, 6))
        tb.Button(tb_bar, text="📥 Export Aging CSV", bootstyle="outline", command=self._export_csv).pack(side=RIGHT)

        # Summary Cards
        cards_row = tb.Frame(root)
        cards_row.pack(fill=X, pady=(0, 12))

        self.card_current = self._create_card(cards_row, "Current (Not Due)", "0.00", "#16a34a")
        self.card_1_30 = self._create_card(cards_row, "1–30 Days Overdue", "0.00", "#f59e0b")
        self.card_31_60 = self._create_card(cards_row, "31–60 Days Overdue", "0.00", "#ea580c")
        self.card_61_90 = self._create_card(cards_row, "61–90 Days Overdue", "0.00", "#dc2626")
        self.card_over_90 = self._create_card(cards_row, "> 90 Days Overdue", "0.00", "#991b1b")
        self.card_total = self._create_card(cards_row, "Total AP Outstanding", "0.00", "#2563eb")

        # Table
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("supplier", "phone", "current", "days_1_30", "days_31_60", "days_61_90", "days_over_90", "total")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("supplier", text="Supplier / Vendor", anchor=W)
        self.tree.heading("phone", text="Phone", anchor=W)
        self.tree.heading("current", text="Current (LKR)", anchor=E)
        self.tree.heading("days_1_30", text="1–30d (LKR)", anchor=E)
        self.tree.heading("days_31_60", text="31–60d (LKR)", anchor=E)
        self.tree.heading("days_61_90", text="61–90d (LKR)", anchor=E)
        self.tree.heading("days_over_90", text=">90d (LKR)", anchor=E)
        self.tree.heading("total", text="Total Due (LKR)", anchor=E)

        self.tree.column("supplier", width=220, anchor=W)
        self.tree.column("phone", width=120, anchor=W)
        self.tree.column("current", width=110, anchor=E)
        self.tree.column("days_1_30", width=110, anchor=E)
        self.tree.column("days_31_60", width=110, anchor=E)
        self.tree.column("days_61_90", width=110, anchor=E)
        self.tree.column("days_over_90", width=110, anchor=E)
        self.tree.column("total", width=125, anchor=E)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        tb.Button(root, text="Close", bootstyle="secondary", command=self.destroy).pack(anchor=E, pady=(10, 0))

    def _create_card(self, parent, title, val, color):
        frame = tb.Frame(parent, padding=8)
        frame.pack(side=LEFT, fill=X, expand=True, padx=3)
        tb.Label(frame, text=title, font=("Segoe UI", 8), bootstyle="secondary").pack(anchor=CENTER)
        val_lbl = tb.Label(frame, text=f"LKR {val}", font=("Segoe UI", 10, "bold"), foreground=color)
        val_lbl.pack(anchor=CENTER)
        return val_lbl

    def refresh(self):
        as_of = self.as_of_var.get().strip() or None
        res = db.get_ap_aging_report(company_id=self.company_id, as_of_date=as_of)
        self.aging_cache = res

        totals = res.get("totals", {})
        self.card_current.config(text=f"LKR {totals.get('current', 0.0):,.2f}")
        self.card_1_30.config(text=f"LKR {totals.get('days_1_30', 0.0):,.2f}")
        self.card_31_60.config(text=f"LKR {totals.get('days_31_60', 0.0):,.2f}")
        self.card_61_90.config(text=f"LKR {totals.get('days_61_90', 0.0):,.2f}")
        self.card_over_90.config(text=f"LKR {totals.get('days_over_90', 0.0):,.2f}")
        self.card_total.config(text=f"LKR {totals.get('total_due', 0.0):,.2f}")

        for r in self.tree.get_children():
            self.tree.delete(r)

        for s in res.get("by_supplier", []):
            self.tree.insert(
                "",
                END,
                iid=str(s["supplier_id"]),
                values=(
                    s["supplier_name"],
                    s.get("supplier_phone") or "—",
                    f"{s['current']:,.2f}" if s["current"] > 0 else "—",
                    f"{s['days_1_30']:,.2f}" if s["days_1_30"] > 0 else "—",
                    f"{s['days_31_60']:,.2f}" if s["days_31_60"] > 0 else "—",
                    f"{s['days_61_90']:,.2f}" if s["days_61_90"] > 0 else "—",
                    f"{s['days_over_90']:,.2f}" if s["days_over_90"] > 0 else "—",
                    f"{s['total_due']:,.2f}"
                )
            )

    def _export_csv(self):
        suppliers = self.aging_cache.get("by_supplier", [])
        if not suppliers:
            messagebox.showinfo("Export", "No aging data to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export AP Aging Report",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"ap_aging_report_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Supplier Name", "Phone", "Current (LKR)", "1-30 Days (LKR)",
                    "31-60 Days (LKR)", "61-90 Days (LKR)", ">90 Days (LKR)", "Total Outstanding (LKR)"
                ])
                for s in suppliers:
                    writer.writerow(db._sanitize_csv_row([
                        s["supplier_name"],
                        s.get("supplier_phone") or "",
                        f"{s['current']:.2f}",
                        f"{s['days_1_30']:.2f}",
                        f"{s['days_31_60']:.2f}",
                        f"{s['days_61_90']:.2f}",
                        f"{s['days_over_90']:.2f}",
                        f"{s['total_due']:.2f}"
                    ]))
                totals = self.aging_cache.get("totals", {})
                writer.writerow([])
                writer.writerow([
                    "TOTALS", "",
                    f"{totals.get('current', 0.0):.2f}",
                    f"{totals.get('days_1_30', 0.0):.2f}",
                    f"{totals.get('days_31_60', 0.0):.2f}",
                    f"{totals.get('days_61_90', 0.0):.2f}",
                    f"{totals.get('days_over_90', 0.0):.2f}",
                    f"{totals.get('total_due', 0.0):.2f}"
                ])
            messagebox.showinfo("Export Successful", f"AP Aging Report saved to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)


class APInvoiceListDialog(tb.Toplevel):
    """Main Accounts Payable Register & Invoice Management Window."""

    STATUS_COLORS = {
        "Unpaid": "#dc2626",
        "Partially Paid": "#ea580c",
        "Paid": "#16a34a",
        "Cancelled": "#6b7280"
    }

    def __init__(self, parent, company_id=None, initial_supplier_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.initial_supplier_id = initial_supplier_id

        self.title("📄 Accounts Payable — Supplier Invoices & Bills")
        self.geometry("1120x680")
        self.minsize(920, 560)
        self.transient(parent)

        self.suppliers = db.get_suppliers(company_id=self.company_id, active_only=False)
        self.supplier_map = {s["name"]: s["id"] for s in self.suppliers}

        self.invoices_cache = []
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
        hdr.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(hdr)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="📄 Accounts Payable (AP) Invoices", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        self.subtitle_lbl = tb.Label(
            title_box,
            text=f"Company #{self.company_id} — Bill Records & Settlements",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        )
        self.subtitle_lbl.pack(anchor=W)

        top_btns = tb.Frame(hdr)
        top_btns.pack(side=RIGHT)

        tb.Button(
            top_btns,
            text="🏢 Suppliers Directory",
            bootstyle="info-outline",
            command=self._open_suppliers
        ).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_btns,
            text="📊 AP Aging Report",
            bootstyle="warning-outline",
            command=self._open_aging
        ).pack(side=LEFT, padx=(0, 8))

        tb.Button(top_btns, text="Pay Bills", bootstyle="success", command=self._pay_bills).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_btns,
            text="➕ New Supplier Invoice",
            bootstyle="primary",
            command=self._new_invoice
        ).pack(side=LEFT)

        # KPI Cards Row
        kpi_row = tb.Frame(root)
        kpi_row.pack(fill=X, pady=(0, 10))

        self.card_total_ap = self._create_kpi_card(kpi_row, "Outstanding AP", "0.00", "#dc2626")
        self.card_overdue = self._create_kpi_card(kpi_row, "Overdue Invoices", "0.00", "#991b1b")
        self.card_part_paid = self._create_kpi_card(kpi_row, "Partially Paid", "0.00", "#ea580c")
        self.card_settled = self._create_kpi_card(kpi_row, "Total Settled / Paid", "0.00", "#16a34a")

        # Filters Toolbar
        filter_bar = tb.Labelframe(root, text="Search & Filter", padding=10)
        filter_bar.pack(fill=X, pady=(0, 10))

        tb.Label(filter_bar, text="Search:").pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = tb.Entry(filter_bar, textvariable=self.search_var, width=20)
        search_entry.pack(side=LEFT, padx=(0, 12))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        tb.Label(filter_bar, text="Status:").pack(side=LEFT, padx=(0, 4))
        self.status_var = tk.StringVar(value="All")
        status_combo = tb.Combobox(filter_bar, textvariable=self.status_var, values=["All", "Unpaid", "Partially Paid", "Paid", "Overdue"], width=13, state="readonly")
        status_combo.pack(side=LEFT, padx=(0, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        tb.Label(filter_bar, text="Supplier:").pack(side=LEFT, padx=(0, 4))
        self.sup_filter_var = tk.StringVar(value="All Suppliers")
        sup_choices = ["All Suppliers"] + list(self.supplier_map.keys())
        self.sup_combo = tb.Combobox(filter_bar, textvariable=self.sup_filter_var, values=sup_choices, width=22, state="readonly")
        self.sup_combo.pack(side=LEFT, padx=(0, 12))
        self.sup_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        if self.initial_supplier_id:
            for name, sid in self.supplier_map.items():
                if sid == self.initial_supplier_id:
                    self.sup_filter_var.set(name)
                    break

        tb.Button(filter_bar, text="Reset", bootstyle="secondary-outline", command=self._reset_filters).pack(side=LEFT)
        tb.Button(filter_bar, text="📥 Export CSV", bootstyle="outline", command=self._export_csv).pack(side=RIGHT)

        # Table
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("date", "due_date", "inv_num", "supplier", "ref", "total", "paid", "balance", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("date", text="Invoice Date", anchor=CENTER)
        self.tree.heading("due_date", text="Due Date", anchor=CENTER)
        self.tree.heading("inv_num", text="Invoice #", anchor=W)
        self.tree.heading("supplier", text="Supplier / Vendor", anchor=W)
        self.tree.heading("ref", text="Internal Ref", anchor=W)
        self.tree.heading("total", text="Total (LKR)", anchor=E)
        self.tree.heading("paid", text="Paid (LKR)", anchor=E)
        self.tree.heading("balance", text="Balance Due (LKR)", anchor=E)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("date", width=95, anchor=CENTER)
        self.tree.column("due_date", width=95, anchor=CENTER)
        self.tree.column("inv_num", width=120, anchor=W)
        self.tree.column("supplier", width=220, anchor=W)
        self.tree.column("ref", width=110, anchor=W)
        self.tree.column("total", width=115, anchor=E)
        self.tree.column("paid", width=115, anchor=E)
        self.tree.column("balance", width=125, anchor=E)
        self.tree.column("status", width=95, anchor=CENTER)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._on_double_click())

        # Action Bar at bottom
        bottom_bar = tb.Frame(root, padding=(0, 10, 0, 0))
        bottom_bar.pack(fill=X)

        tb.Button(bottom_bar, text="💳 Record Payment", bootstyle="success", command=self._record_payment).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="✏️ Edit Invoice", bootstyle="primary-outline", command=self._edit_invoice).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="👁️ View PDF", bootstyle="info-outline", command=self._view_pdf).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="🗑️ Delete Invoice", bootstyle="danger-outline", command=self._delete_invoice).pack(side=LEFT, padx=(0, 8))

        tb.Button(bottom_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _create_kpi_card(self, parent, title, val, color):
        frame = tb.Frame(parent, padding=8)
        frame.pack(side=LEFT, fill=X, expand=True, padx=4)
        tb.Label(frame, text=title, font=("Segoe UI", 8), bootstyle="secondary").pack(anchor=CENTER)
        val_lbl = tb.Label(frame, text=f"LKR {val}", font=("Segoe UI", 11, "bold"), foreground=color)
        val_lbl.pack(anchor=CENTER)
        return val_lbl

    def _reset_filters(self):
        self.search_var.set("")
        self.status_var.set("All")
        self.sup_filter_var.set("All Suppliers")
        self.refresh()

    def refresh(self):
        st = self.status_var.get()
        sup_sel = self.sup_filter_var.get()
        sup_id = self.supplier_map.get(sup_sel) if sup_sel != "All Suppliers" else None
        sq = self.search_var.get().strip() or None

        invoices = db.get_ap_invoices(
            company_id=self.company_id,
            status=st,
            supplier_id=sup_id,
            search=sq
        )
        self.invoices_cache = invoices

        for r in self.tree.get_children():
            self.tree.delete(r)

        tot_ap = 0.0
        tot_overdue = 0.0
        tot_part = 0.0
        tot_settled = 0.0

        for inv in invoices:
            bal = float(inv.get("balance_due") or 0.0)
            paid = float(inv.get("paid_amount") or 0.0)
            tot = float(inv.get("total_amount") or 0.0)
            status_text = inv.get("status", "Unpaid")

            if status_text != "Cancelled":
                tot_ap += bal
                tot_settled += paid
                if inv.get("is_overdue"):
                    tot_overdue += bal
                if status_text == "Partially Paid":
                    tot_part += bal

            status_display = "⚠️ Overdue" if inv.get("is_overdue") else status_text

            self.tree.insert(
                "",
                END,
                iid=str(inv["id"]),
                values=(
                    inv["invoice_date"],
                    inv["due_date"],
                    inv["invoice_number"],
                    inv["supplier_name"],
                    inv.get("internal_ref") or "—",
                    f"{tot:,.2f}",
                    f"{paid:,.2f}",
                    f"{bal:,.2f}",
                    status_display
                )
            )

        self.card_total_ap.config(text=f"LKR {tot_ap:,.2f}")
        self.card_overdue.config(text=f"LKR {tot_overdue:,.2f}")
        self.card_part_paid.config(text=f"LKR {tot_part:,.2f}")
        self.card_settled.config(text=f"LKR {tot_settled:,.2f}")

        self.subtitle_lbl.config(
            text=f"{len(invoices)} invoice(s) | Outstanding Balance: LKR {tot_ap:,.2f}"
        )

    def _get_selected_invoice(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select an invoice from the list.", parent=self)
            return None
        inv_id = int(sel[0])
        return next((i for i in self.invoices_cache if i["id"] == inv_id), None)

    def _new_invoice(self):
        APInvoiceEntryDialog(self, company_id=self.company_id, on_saved=self.refresh)

    def _edit_invoice(self):
        inv = self._get_selected_invoice()
        if not inv:
            return
        APInvoiceEntryDialog(self, company_id=self.company_id, invoice_id=inv["id"], on_saved=self.refresh)

    def _record_payment(self):
        inv = self._get_selected_invoice()
        if not inv:
            return
        if inv["status"] == "Paid":
            messagebox.showinfo("Already Paid", "This invoice is already fully paid.", parent=self)
            return
        self._pay_bills(inv.get("supplier_id"))

    def _pay_bills(self, supplier_id=None):
        from ui.pay_bills_dialog import PayBillsDialog
        PayBillsDialog(self, self.company_id, supplier_id, self.refresh)

    def _view_pdf(self):
        inv = self._get_selected_invoice()
        if not inv:
            return
        try:
            pdf_path = invoice_printer.generate_ap_invoice_pdf([inv["id"]])
            PdfViewerDialog(self, pdf_path, title=f"Supplier Invoice — {inv['invoice_number']}")
        except Exception as e:
            messagebox.showerror("Error Generating PDF", str(e), parent=self)

    def _delete_invoice(self):
        inv = self._get_selected_invoice()
        if not inv:
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete invoice #{inv['invoice_number']} from {inv['supplier_name']}?\n"
            "This will delete its line items and double-entry general ledger journal lines.",
            parent=self
        )
        if not confirm:
            return

        success, msg = db.delete_ap_invoice(inv["id"])
        if success:
            messagebox.showinfo("Deleted", msg, parent=self)
            self.refresh()
        else:
            messagebox.showerror("Cannot Delete", msg, parent=self)

    def _open_suppliers(self):
        from ui.supplier_manager import SupplierManagerDialog
        SupplierManagerDialog(self, company_id=self.company_id)

    def _open_aging(self):
        APAgingDialog(self, company_id=self.company_id)

    def _on_double_click(self):
        inv = self._get_selected_invoice()
        if inv:
            if inv["status"] != "Paid":
                self._record_payment()
            else:
                self._view_pdf()

    def _export_csv(self):
        if not self.invoices_cache:
            messagebox.showinfo("Export", "No invoices to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Accounts Payable Invoices",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"ap_invoices_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Invoice Date", "Due Date", "Invoice Number", "Supplier Name",
                    "Internal Ref", "Subtotal (LKR)", "Tax Amount (LKR)",
                    "Discount (LKR)", "Total Amount (LKR)", "Paid Amount (LKR)",
                    "Balance Due (LKR)", "Status", "Notes"
                ])
                for i in self.invoices_cache:
                    writer.writerow([
                        i["invoice_date"],
                        i["due_date"],
                        i["invoice_number"],
                        i["supplier_name"],
                        i.get("internal_ref") or "",
                        f"{float(i.get('subtotal') or 0.0):.2f}",
                        f"{float(i.get('tax_amount') or 0.0):.2f}",
                        f"{float(i.get('discount_amount') or 0.0):.2f}",
                        f"{float(i.get('total_amount') or 0.0):.2f}",
                        f"{float(i.get('paid_amount') or 0.0):.2f}",
                        f"{float(i.get('balance_due') or 0.0):.2f}",
                        i.get("status") or "Unpaid",
                        i.get("notes") or ""
                    ])
            messagebox.showinfo("Export Successful", f"Invoices exported to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)
