"""
ui/ar_invoice_dialog.py
Accounts Receivable (AR) Customer Invoicing, Billing & Aging Interface (v3.8).

Provides:
- ARInvoiceEntryDialog: Create & Edit customer invoices with line items and COA revenue mapping.
- ARInvoiceListDialog: Main AR register with KPIs, filters, status tracking, and PDF printing.
- ARReceiptDialog: Record customer payment receipts with auto double-entry journal linkage.
- ARAgingDialog: Multi-bucket visual aging report (Current, 1-30d, 31-60d, 61-90d, >90d).
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


class ARInvoiceEntryDialog(tb.Toplevel):
    """Dialog for creating or editing an Accounts Receivable customer invoice."""

    def __init__(self, parent, company_id=None, invoice_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.invoice_id = invoice_id
        self.is_edit = bool(self.invoice_id)
        self.on_saved = on_saved

        self.title("Edit Customer Invoice" if self.is_edit else "New Customer Tax Invoice (AR)")
        self.geometry("940x700")
        self.minsize(800, 580)
        self.transient(parent)
        self.grab_set()

        self.customers = db.get_customers(company_id=self.company_id, active_only=True)
        self.customer_lookup = {c["name"]: c for c in self.customers}

        self.coa_accounts = db.get_chart_of_accounts(company_id=self.company_id, account_type="Income", active_only=True)
        if not self.coa_accounts:
            self.coa_accounts = db.get_chart_of_accounts(company_id=self.company_id, account_type="Revenue", active_only=True)
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

        tb.Label(hdr, text="Customer Tax Invoice (AR Billing)", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(
            hdr,
            text="Generate customer invoices, line item sales, revenue classification, and track receivables.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # Invoice Header Details Box
        form_box = tb.Labelframe(root, text="Invoice Information", padding=12)
        form_box.pack(fill=X, pady=(0, 10))

        # Row 1: Customer, Invoice Number, Customer PO / Ref
        r1 = tb.Frame(form_box)
        r1.pack(fill=X, pady=4)

        tb.Label(r1, text="Customer *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.customer_var = tk.StringVar()
        cust_names = list(self.customer_lookup.keys())
        self.cust_combo = tb.Combobox(r1, textvariable=self.customer_var, values=cust_names, width=28)
        self.cust_combo.pack(side=LEFT, padx=(0, 6))
        self.cust_combo.bind("<<ComboboxSelected>>", self._on_customer_selected)

        tb.Button(r1, text="➕", bootstyle="outline", width=3, command=self._quick_add_customer).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Invoice # *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.inv_num_var = tk.StringVar()
        self.inv_num_entry = tb.Entry(r1, textvariable=self.inv_num_var, width=18)
        self.inv_num_entry.pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Customer PO / Ref:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.ref_var = tk.StringVar()
        tb.Entry(r1, textvariable=self.ref_var, width=18).pack(side=LEFT)

        # Row 2: Date, Payment Terms, Due Date, Status
        r2 = tb.Frame(form_box)
        r2.pack(fill=X, pady=4)

        tb.Label(r2, text="Invoice Date *:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.date_entry = tb.Entry(r2, textvariable=self.date_var, width=14)
        self.date_entry.pack(side=LEFT, padx=(0, 16))
        self.date_var.trace_add("write", lambda *args: self._recalc_due_date())

        tb.Label(r2, text="Terms (Days):", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.terms_var = tk.StringVar(value="30")
        terms_spin = tb.Spinbox(r2, from_=0, to=365, textvariable=self.terms_var, width=8)
        terms_spin.pack(side=LEFT, padx=(0, 16))
        self.terms_var.trace_add("write", lambda *args: self._recalc_due_date())

        tb.Label(r2, text="Due Date *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.due_date_var = tk.StringVar()
        self.due_entry = tb.Entry(r2, textvariable=self.due_date_var, width=14)
        self.due_entry.pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Status:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.status_var = tk.StringVar(value="Draft")
        status_combo = tb.Combobox(r2, textvariable=self.status_var, values=["Draft", "Sent", "Unpaid", "Partially Paid", "Paid", "Cancelled"], width=12, state="readonly")
        status_combo.pack(side=LEFT)

        # Line Items Table Frame
        lines_box = tb.Labelframe(root, text="Invoice Line Items (Products & Services)", padding=10)
        lines_box.pack(fill=BOTH, expand=True, pady=(0, 8))

        cols = ("idx", "desc", "account", "qty", "price", "tax_rate", "tax_amt", "total")
        self.tree_lines = ttk.Treeview(lines_box, columns=cols, show="headings", height=6)
        self.tree_lines.heading("idx", text="#", anchor=W)
        self.tree_lines.heading("desc", text="Description / Item Name", anchor=W)
        self.tree_lines.heading("account", text="Revenue Account (COA)", anchor=W)
        self.tree_lines.heading("qty", text="Qty", anchor=E)
        self.tree_lines.heading("price", text="Unit Price (LKR)", anchor=E)
        self.tree_lines.heading("tax_rate", text="VAT %", anchor=E)
        self.tree_lines.heading("tax_amt", text="VAT Amt", anchor=E)
        self.tree_lines.heading("total", text="Line Total (LKR)", anchor=E)

        self.tree_lines.column("idx", width=35, stretch=False)
        self.tree_lines.column("desc", width=240)
        self.tree_lines.column("account", width=190)
        self.tree_lines.column("qty", width=65, anchor=E)
        self.tree_lines.column("price", width=105, anchor=E)
        self.tree_lines.column("tax_rate", width=65, anchor=E)
        self.tree_lines.column("tax_amt", width=85, anchor=E)
        self.tree_lines.column("total", width=110, anchor=E)

        tree_sb = tb.Scrollbar(lines_box, orient=VERTICAL, command=self.tree_lines.yview)
        self.tree_lines.configure(yscrollcommand=tree_sb.set)
        self.tree_lines.pack(side=LEFT, fill=BOTH, expand=True)
        tree_sb.pack(side=RIGHT, fill=Y)

        # Line Edit Action Bar
        line_act = tb.Frame(root)
        line_act.pack(fill=X, pady=(0, 8))

        tb.Button(line_act, text="➕ Add Line Item", bootstyle="success-outline", command=self._add_line_item).pack(side=LEFT, padx=(0, 6))
        tb.Button(line_act, text="✏️ Edit Selected", bootstyle="secondary-outline", command=self._edit_selected_line).pack(side=LEFT, padx=(0, 6))
        tb.Button(line_act, text="🗑️ Remove Line", bootstyle="danger-outline", command=self._remove_selected_line).pack(side=LEFT)

        # Financial Summary & Notes
        bottom_grid = tb.Frame(root)
        bottom_grid.pack(fill=X, pady=(0, 8))

        # Left: Notes, Terms, and Footer text
        notes_f = tb.Frame(bottom_grid)
        notes_f.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 20))

        tb.Label(notes_f, text="Customer Notes:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.notes_var = tk.StringVar()
        tb.Entry(notes_f, textvariable=self.notes_var).pack(fill=X, pady=(0, 4))

        tb.Label(notes_f, text="Payment Terms & Instructions:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.terms_text_var = tk.StringVar(value="Payment due within 30 days. Remit via Bank Transfer.")
        tb.Entry(notes_f, textvariable=self.terms_text_var).pack(fill=X)

        # Right: Financial Calculations Panel
        calc_f = tb.Frame(bottom_grid, padding=8, bootstyle="light")
        calc_f.pack(side=RIGHT, fill=Y)

        tb.Label(calc_f, text="Subtotal:").grid(row=0, column=0, sticky=W, pady=2)
        self.lbl_subtotal = tb.Label(calc_f, text="LKR 0.00", font=("Segoe UI", 9, "bold"))
        self.lbl_subtotal.grid(row=0, column=1, sticky=E, pady=2, padx=(20, 0))

        tb.Label(calc_f, text="Discount (LKR):").grid(row=1, column=0, sticky=W, pady=2)
        self.discount_var = tk.StringVar(value="0.00")
        self.discount_var.trace_add("write", lambda *args: self._recalc_totals())
        tb.Entry(calc_f, textvariable=self.discount_var, width=12).grid(row=1, column=1, sticky=E, pady=2, padx=(20, 0))

        tb.Label(calc_f, text="VAT / Tax Total:").grid(row=2, column=0, sticky=W, pady=2)
        self.lbl_tax = tb.Label(calc_f, text="LKR 0.00", font=("Segoe UI", 9, "bold"))
        self.lbl_tax.grid(row=2, column=1, sticky=E, pady=2, padx=(20, 0))

        sep = tb.Separator(calc_f)
        sep.grid(row=3, column=0, columnspan=2, sticky=EW, pady=4)

        tb.Label(calc_f, text="Total Amount Due:", font=("Segoe UI", 10, "bold"), bootstyle="primary").grid(row=4, column=0, sticky=W, pady=2)
        self.lbl_total = tb.Label(calc_f, text="LKR 0.00", font=("Segoe UI", 12, "bold"), bootstyle="primary")
        self.lbl_total.grid(row=4, column=1, sticky=E, pady=2, padx=(20, 0))

        # Dialog Footer Buttons
        btn_bar = tb.Frame(root)
        btn_bar.pack(fill=X, pady=(6, 0))

        tb.Button(btn_bar, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        save_btn_lbl = "Save & Update Invoice" if self.is_edit else "Save & Issue Invoice"
        tb.Button(btn_bar, text=save_btn_lbl, bootstyle="primary", command=self._on_save).pack(side=RIGHT)

        if self.is_edit:
            tb.Button(btn_bar, text="🖨️ Print / Preview PDF", bootstyle="info-outline", command=self._on_preview_pdf).pack(side=LEFT)

    def _init_defaults(self):
        self.inv_num_var.set(db.get_next_ar_invoice_number(company_id=self.company_id))
        self._recalc_due_date()

        # Add initial blank line item for convenience
        default_acct = self.coa_accounts[0] if self.coa_accounts else None
        self.lines_data.append({
            "description": "Standard Services",
            "account_id": default_acct["id"] if default_acct else None,
            "quantity": 1.0,
            "unit_price": 0.0,
            "tax_rate": 0.0,
            "tax_amount": 0.0,
            "line_total": 0.0
        })
        self._refresh_lines_table()

    def _recalc_due_date(self):
        try:
            d_str = self.date_var.get().strip()
            terms = int(self.terms_var.get().strip())
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            due_dt = dt + timedelta(days=terms)
            self.due_date_var.set(due_dt.strftime("%Y-%m-%d"))
        except Exception:
            pass

    def _on_customer_selected(self, event=None):
        cust_name = self.customer_var.get().strip()
        cust = self.customer_lookup.get(cust_name)
        if cust:
            p_terms = cust.get("payment_terms") or 30
            self.terms_var.set(str(p_terms))
            self._recalc_due_date()

    def _quick_add_customer(self):
        from ui.customer_manager import CustomerEditModal
        def _on_created(cid):
            self.customers = db.get_customers(company_id=self.company_id, active_only=True)
            self.customer_lookup = {c["name"]: c for c in self.customers}
            self.cust_combo.config(values=list(self.customer_lookup.keys()))
            new_cust = db.get_customer_by_id(cid)
            if new_cust:
                self.customer_var.set(new_cust["name"])
                self._on_customer_selected()
        CustomerEditModal(self, company_id=self.company_id, on_saved=_on_created)

    def _add_line_item(self):
        self._open_line_item_modal()

    def _edit_selected_line(self):
        sel = self.tree_lines.selection()
        if not sel:
            messagebox.showinfo("Selection", "Select a line item to edit.", parent=self)
            return
        idx = int(self.tree_lines.item(sel[0], "values")[0]) - 1
        if 0 <= idx < len(self.lines_data):
            self._open_line_item_modal(line_idx=idx)

    def _remove_selected_line(self):
        sel = self.tree_lines.selection()
        if not sel:
            messagebox.showinfo("Selection", "Select a line item to remove.", parent=self)
            return
        idx = int(self.tree_lines.item(sel[0], "values")[0]) - 1
        if 0 <= idx < len(self.lines_data):
            del self.lines_data[idx]
            self._refresh_lines_table()

    def _open_line_item_modal(self, line_idx=None):
        dlg = tb.Toplevel(self)
        dlg.title("Edit Line Item" if line_idx is not None else "Add Line Item")
        dlg.geometry("480x360")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        curr = self.lines_data[line_idx] if line_idx is not None else {
            "description": "",
            "account_id": self.coa_accounts[0]["id"] if self.coa_accounts else None,
            "quantity": 1.0,
            "unit_price": 0.0,
            "tax_rate": 0.0,
            "tax_amount": 0.0,
            "line_total": 0.0
        }

        f = tb.Frame(dlg, padding=16)
        f.pack(fill=BOTH, expand=True)

        tb.Label(f, text="Item Description *:").grid(row=0, column=0, sticky=W, pady=6)
        desc_var = tk.StringVar(value=curr.get("description", ""))
        tb.Entry(f, textvariable=desc_var, width=32).grid(row=0, column=1, sticky=EW, pady=6, padx=(10, 0))

        tb.Label(f, text="Revenue Account:").grid(row=1, column=0, sticky=W, pady=6)
        acct_var = tk.StringVar()
        acct_names = list(self.coa_lookup.keys())
        acct_combo = tb.Combobox(f, textvariable=acct_var, values=acct_names, width=30, state="readonly")
        acct_combo.grid(row=1, column=1, sticky=EW, pady=6, padx=(10, 0))
        for name, a in self.coa_lookup.items():
            if a["id"] == curr.get("account_id"):
                acct_var.set(name)
                break
        if not acct_var.get() and acct_names:
            acct_var.set(acct_names[0])

        tb.Label(f, text="Quantity:").grid(row=2, column=0, sticky=W, pady=6)
        qty_var = tk.StringVar(value=str(curr.get("quantity", 1.0)))
        tb.Entry(f, textvariable=qty_var, width=14).grid(row=2, column=1, sticky=W, pady=6, padx=(10, 0))

        tb.Label(f, text="Unit Price (LKR) *:").grid(row=3, column=0, sticky=W, pady=6)
        price_var = tk.StringVar(value=f"{float(curr.get('unit_price') or 0.0):.2f}")
        tb.Entry(f, textvariable=price_var, width=14).grid(row=3, column=1, sticky=W, pady=6, padx=(10, 0))

        tb.Label(f, text="VAT / Tax Rate (%):").grid(row=4, column=0, sticky=W, pady=6)
        tax_var = tk.StringVar(value=str(float(curr.get("tax_rate", 0.0)) * 100))
        tb.Combobox(f, textvariable=tax_var, values=["0", "8", "18"], width=12).grid(row=4, column=1, sticky=W, pady=6, padx=(10, 0))

        btn_box = tb.Frame(f)
        btn_box.grid(row=5, column=0, columnspan=2, sticky=EW, pady=(20, 0))

        def _save_line():
            desc = desc_var.get().strip()
            if not desc:
                messagebox.showwarning("Validation", "Description is required.", parent=dlg)
                return
            try:
                qty = float(qty_var.get().strip() or 1.0)
                price = float(price_var.get().strip() or 0.0)
                rate = float(tax_var.get().strip() or 0.0) / 100.0
            except ValueError:
                messagebox.showwarning("Validation", "Invalid numeric value for quantity, price, or tax.", parent=dlg)
                return

            tax_amt = round(qty * price * rate, 2)
            l_tot = round(qty * price + tax_amt, 2)
            sel_acct = self.coa_lookup.get(acct_var.get())

            line_payload = {
                "description": desc,
                "account_id": sel_acct["id"] if sel_acct else None,
                "quantity": qty,
                "unit_price": price,
                "tax_rate": rate,
                "tax_amount": tax_amt,
                "line_total": l_tot
            }

            if line_idx is not None:
                self.lines_data[line_idx] = line_payload
            else:
                self.lines_data.append(line_payload)

            self._refresh_lines_table()
            dlg.destroy()

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=dlg.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btn_box, text="Done", bootstyle="primary", command=_save_line).pack(side=RIGHT)

    def _refresh_lines_table(self):
        for item in self.tree_lines.get_children():
            self.tree_lines.delete(item)

        for idx, line in enumerate(self.lines_data, 1):
            acct_name = "—"
            for name, a in self.coa_lookup.items():
                if a["id"] == line.get("account_id"):
                    acct_name = name
                    break

            rate_pct = f"{float(line.get('tax_rate', 0.0)) * 100:.1f}%"
            self.tree_lines.insert("", END, values=(
                idx,
                line.get("description", ""),
                acct_name,
                f"{float(line.get('quantity', 1.0)):.2f}",
                f"{float(line.get('unit_price', 0.0)):,.2f}",
                rate_pct,
                f"{float(line.get('tax_amount', 0.0)):,.2f}",
                f"{float(line.get('line_total', 0.0)):,.2f}"
            ))

        self._recalc_totals()

    def _recalc_totals(self):
        subtotal = sum(float(l.get("quantity", 1)) * float(l.get("unit_price", 0)) for l in self.lines_data)
        tax_total = sum(float(l.get("tax_amount", 0)) for l in self.lines_data)
        try:
            disc = float(self.discount_var.get().replace(",", "").strip() or 0.0)
        except ValueError:
            disc = 0.0

        total = round(subtotal + tax_total - disc, 2)
        total = max(0.0, total)

        self.lbl_subtotal.config(text=f"LKR {subtotal:,.2f}")
        self.lbl_tax.config(text=f"LKR {tax_total:,.2f}")
        self.lbl_total.config(text=f"LKR {total:,.2f}")

    def _load_invoice_data(self):
        data = db.get_ar_invoice(self.invoice_id)
        if not data:
            return
        inv = data["invoice"]
        self.customer_var.set(inv.get("customer_name", ""))
        self.inv_num_var.set(inv.get("invoice_number", ""))
        self.ref_var.set(inv.get("internal_ref", ""))
        self.date_var.set(inv.get("invoice_date", ""))
        self.due_date_var.set(inv.get("due_date", ""))
        self.status_var.set(inv.get("status", "Draft"))
        self.discount_var.set(f"{float(inv.get('discount_amount') or 0.0):.2f}")
        self.notes_var.set(inv.get("notes", ""))
        self.terms_text_var.set(inv.get("terms", ""))

        self.lines_data = data["lines"]
        self._refresh_lines_table()

    def _on_save(self):
        cust_name = self.customer_var.get().strip()
        cust = self.customer_lookup.get(cust_name)
        if not cust:
            messagebox.showwarning("Validation", "Please select a valid customer.", parent=self)
            self.cust_combo.focus_set()
            return

        inv_num = self.inv_num_var.get().strip()
        if not inv_num:
            messagebox.showwarning("Validation", "Invoice number is required.", parent=self)
            self.inv_num_entry.focus_set()
            return

        if not self.lines_data:
            messagebox.showwarning("Validation", "Please add at least one line item.", parent=self)
            return

        try:
            disc = float(self.discount_var.get().replace(",", "").strip() or 0.0)
        except ValueError:
            disc = 0.0

        subtotal = sum(float(l.get("quantity", 1)) * float(l.get("unit_price", 0)) for l in self.lines_data)
        tax_total = sum(float(l.get("tax_amount", 0)) for l in self.lines_data)
        total = round(subtotal + tax_total - disc, 2)
        if total <= 0.0:
            messagebox.showwarning("Validation", "Total invoice amount must be greater than zero.", parent=self)
            return

        invoice_payload = {
            "company_id": self.company_id,
            "customer_id": cust["id"],
            "invoice_number": inv_num,
            "internal_ref": self.ref_var.get().strip(),
            "invoice_date": self.date_var.get().strip(),
            "due_date": self.due_date_var.get().strip(),
            "discount_amount": disc,
            "status": self.status_var.get().strip(),
            "notes": self.notes_var.get().strip(),
            "terms": self.terms_text_var.get().strip(),
            "created_by": "User"
        }

        try:
            if self.is_edit:
                db.update_ar_invoice(self.invoice_id, invoice_payload, self.lines_data)
                res_id = self.invoice_id
            else:
                res_id = db.create_ar_invoice(invoice_payload, self.lines_data)

            if self.on_saved:
                self.on_saved(res_id)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save customer invoice: {e}", parent=self)

    def _on_preview_pdf(self):
        try:
            pdf_path = invoice_printer.generate_ar_invoice_pdf([self.invoice_id])
            PdfViewerDialog(self, pdf_path, title=f"Tax Invoice #{self.inv_num_var.get()}")
        except Exception as e:
            messagebox.showerror("PDF Preview Error", f"Could not generate invoice PDF:\n{e}", parent=self)


class ARReceiptDialog(tb.Toplevel):
    """Dialog for recording customer payment receipts against an Accounts Receivable invoice."""

    def __init__(self, parent, invoice_id: int, on_saved=None):
        super().__init__(parent)
        self.invoice_id = invoice_id
        self.on_saved = on_saved
        self.inv_data = db.get_ar_invoice(self.invoice_id)
        if not self.inv_data:
            messagebox.showerror("Error", "Invoice not found.", parent=parent)
            self.destroy()
            return

        h = self.inv_data["invoice"]
        self.company_id = h["company_id"]
        self.title(f"Record Customer Receipt — Inv #{h['invoice_number']}")
        self.geometry("520x460")
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
        f = tb.Frame(self, padding=20)
        f.pack(fill=BOTH, expand=True)

        h = self.inv_data["invoice"]
        tb.Label(f, text="Customer Receipt Settlement", font=("Segoe UI", 13, "bold")).pack(anchor=W)
        tb.Label(f, text=f"Record incoming payment for {h['customer_name']}.", font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 12))

        # Invoice summary banner
        box = tb.Frame(f, padding=10, bootstyle="light")
        box.pack(fill=X, pady=(0, 14))

        tb.Label(box, text=f"Invoice #: {h['invoice_number']}", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W)
        tb.Label(box, text=f"Total: LKR {float(h['total_amount']):,.2f}").grid(row=0, column=1, sticky=E, padx=(20, 0))
        tb.Label(box, text=f"Balance Remaining: LKR {float(h['balance_due']):,.2f}", font=("Segoe UI", 9, "bold"), bootstyle="danger" if float(h['balance_due']) > 0 else "success").grid(row=1, column=0, columnspan=2, sticky=W, pady=(4, 0))
        box.columnconfigure(1, weight=1)

        # Receipt Form
        form = tb.Frame(f)
        form.pack(fill=BOTH, expand=True)

        # Receipt Date
        tb.Label(form, text="Receipt Date *:").grid(row=0, column=0, sticky=W, pady=6)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(form, textvariable=self.date_var, width=16).grid(row=0, column=1, sticky=W, pady=6, padx=(10, 0))

        # Amount
        tb.Label(form, text="Amount Received (LKR) *:").grid(row=1, column=0, sticky=W, pady=6)
        self.amount_var = tk.StringVar(value=f"{float(h['balance_due']):.2f}")
        tb.Entry(form, textvariable=self.amount_var, width=18).grid(row=1, column=1, sticky=W, pady=6, padx=(10, 0))

        # Payment Method
        tb.Label(form, text="Payment Method:").grid(row=2, column=0, sticky=W, pady=6)
        self.method_var = tk.StringVar(value="Bank Transfer")
        tb.Combobox(form, textvariable=self.method_var, values=["Cash", "Cheque", "Bank Transfer", "Credit Card", "Online/Other"], width=16, state="readonly").grid(row=2, column=1, sticky=W, pady=6, padx=(10, 0))

        # Reference
        tb.Label(form, text="Reference / Deposit Slip #:").grid(row=3, column=0, sticky=W, pady=6)
        self.ref_var = tk.StringVar()
        tb.Entry(form, textvariable=self.ref_var, width=24).grid(row=3, column=1, sticky=W, pady=6, padx=(10, 0))

        # Bank Account (Optional)
        tb.Label(form, text="Deposited To Bank:").grid(row=4, column=0, sticky=W, pady=6)
        bank_accounts = db.get_bank_accounts(company_id=self.company_id, active_only=True) if hasattr(db, "get_bank_accounts") else []
        self.bank_lookup = {b["account_name"]: b["id"] for b in bank_accounts}
        self.bank_var = tk.StringVar()
        b_names = list(self.bank_lookup.keys())
        b_combo = tb.Combobox(form, textvariable=self.bank_var, values=b_names, width=24, state="readonly" if b_names else "disabled")
        b_combo.grid(row=4, column=1, sticky=W, pady=6, padx=(10, 0))
        if b_names:
            self.bank_var.set(b_names[0])

        # Notes
        tb.Label(form, text="Notes:").grid(row=5, column=0, sticky=W, pady=6)
        self.notes_var = tk.StringVar()
        tb.Entry(form, textvariable=self.notes_var, width=28).grid(row=5, column=1, sticky=W, pady=6, padx=(10, 0))

        # Button Bar
        btn_bar = tb.Frame(f)
        btn_bar.pack(fill=X, pady=(15, 0))

        tb.Button(btn_bar, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btn_bar, text="Record Receipt", bootstyle="success", command=self._on_save).pack(side=RIGHT)

    def _on_save(self):
        try:
            amt = float(self.amount_var.get().replace(",", "").strip() or 0.0)
            if amt <= 0.0:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Validation", "Please enter a valid positive payment amount.", parent=self)
            return

        h = self.inv_data["invoice"]
        bal = float(h["balance_due"])
        if amt > (bal + 0.01):
            if not messagebox.askyesno("Overpayment Warning", f"Amount received (LKR {amt:,.2f}) exceeds balance due (LKR {bal:,.2f}). Continue anyway?", parent=self):
                return

        payload = {
            "invoice_id": self.invoice_id,
            "receipt_date": self.date_var.get().strip(),
            "amount": amt,
            "payment_method": self.method_var.get().strip(),
            "reference": self.ref_var.get().strip(),
            "bank_account_id": self.bank_lookup.get(self.bank_var.get()),
            "notes": self.notes_var.get().strip(),
            "created_by": "User"
        }

        try:
            r_id = db.record_ar_receipt(payload)
            messagebox.showinfo("Receipt Recorded", f"Payment of LKR {amt:,.2f} recorded successfully (Receipt #{r_id}).", parent=self)
            if self.on_saved:
                self.on_saved(r_id)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to record receipt: {e}", parent=self)


class ARInvoiceListDialog(tb.Toplevel):
    """
    Accounts Receivable (AR) Invoices Register Dialog.
    Allows searching, filtering by status, recording receipts, viewing aging, and PDF printing.
    """

    def __init__(self, parent, company_id=None, customer_id_filter=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.customer_id_filter = customer_id_filter

        comp = db.get_company(self.company_id)
        comp_name = comp.get("name", "Company") if comp else "Company"

        self.title(f"Customer Invoices & AR Register — {comp_name}")
        self.geometry("1140x660")
        self.minsize(920, 520)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_invoices()
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
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header Title Bar
        header = tb.Frame(container)
        header.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(header)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="🧾 Accounts Receivable & Customer Invoices", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(title_box, text="Track customer billing, monitor settlement progress, and issue professional tax invoices.", font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)

        # Metric KPI Summary Cards
        self.kpi_frame = tb.Frame(container)
        self.kpi_frame.pack(fill=X, pady=(0, 12))

        self.card_total_inv = self._create_kpi_card(self.kpi_frame, "Total Invoiced", "LKR 0.00", "primary")
        self.card_total_inv.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))

        self.card_total_rec = self._create_kpi_card(self.kpi_frame, "Total Received", "LKR 0.00", "success")
        self.card_total_rec.pack(side=LEFT, fill=X, expand=True, padx=6)

        self.card_balance_due = self._create_kpi_card(self.kpi_frame, "Total Due (Receivables)", "LKR 0.00", "warning")
        self.card_balance_due.pack(side=LEFT, fill=X, expand=True, padx=6)

        self.card_overdue_count = self._create_kpi_card(self.kpi_frame, "Overdue Invoices", "0", "danger")
        self.card_overdue_count.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))

        # Filter Toolbar
        toolbar = tb.Frame(container)
        toolbar.pack(fill=X, pady=(0, 10))

        tb.Label(toolbar, text="Status:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.status_filter_var = tk.StringVar(value="All")
        status_opts = ["All", "Draft", "Sent", "Unpaid", "Partially Paid", "Paid", "Overdue", "Cancelled"]
        combo_status = tb.Combobox(toolbar, textvariable=self.status_filter_var, values=status_opts, width=13, state="readonly")
        combo_status.pack(side=LEFT, padx=(0, 14))
        combo_status.bind("<<ComboboxSelected>>", lambda e: self._load_invoices())

        tb.Label(toolbar, text="Search:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._load_invoices())
        tb.Entry(toolbar, textvariable=self.search_var, width=24).pack(side=LEFT, padx=(0, 14))

        # Action Buttons
        tb.Button(toolbar, text="📊 AR Aging Report", bootstyle="info-outline", command=self._open_ar_aging).pack(side=RIGHT, padx=(6, 0))
        tb.Button(toolbar, text="➕ New Invoice", bootstyle="success", command=self._new_invoice).pack(side=RIGHT)

        # Treeview Table
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "inv_num", "date", "customer", "due_date", "total", "paid", "balance", "status")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("id", text="#", anchor=W)
        self.tree.heading("inv_num", text="Invoice #", anchor=W)
        self.tree.heading("date", text="Invoice Date", anchor=CENTER)
        self.tree.heading("customer", text="Customer Name", anchor=W)
        self.tree.heading("due_date", text="Due Date", anchor=CENTER)
        self.tree.heading("total", text="Total Amount", anchor=E)
        self.tree.heading("paid", text="Paid Amount", anchor=E)
        self.tree.heading("balance", text="Balance Due", anchor=E)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("id", width=40, stretch=False)
        self.tree.column("inv_num", width=120)
        self.tree.column("date", width=95, anchor=CENTER)
        self.tree.column("customer", width=200)
        self.tree.column("due_date", width=95, anchor=CENTER)
        self.tree.column("total", width=115, anchor=E)
        self.tree.column("paid", width=115, anchor=E)
        self.tree.column("balance", width=115, anchor=E)
        self.tree.column("status", width=95, anchor=CENTER)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        hsb = tb.Scrollbar(tree_frame, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=NSEW)
        vsb.grid(row=0, column=1, sticky=NS)
        hsb.grid(row=1, column=0, sticky=EW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda e: self._edit_invoice())

        # Tag configurations for colors
        self.tree.tag_configure("paid", foreground="#15803d")
        self.tree.tag_configure("partially_paid", foreground="#b45309")
        self.tree.tag_configure("overdue", foreground="#b91c1c")
        self.tree.tag_configure("cancelled", foreground="#94a3b8")

        # Bottom Action Bar
        bottom = tb.Frame(container)
        bottom.pack(fill=X, pady=(10, 0))

        tb.Button(bottom, text="✏️ Edit Invoice", bootstyle="primary-outline", command=self._edit_invoice).pack(side=LEFT, padx=(0, 6))
        tb.Button(bottom, text="💵 Record Receipt", bootstyle="success", command=self._record_receipt).pack(side=LEFT, padx=(0, 6))
        tb.Button(bottom, text="🖨️ Print / Preview PDF", bootstyle="info-outline", command=self._print_pdf).pack(side=LEFT, padx=(0, 6))
        tb.Button(bottom, text="🗑️ Delete", bootstyle="danger-outline", command=self._delete_invoice).pack(side=LEFT)

        tb.Button(bottom, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _create_kpi_card(self, parent, title, value, bootstyle):
        card = tb.Frame(parent, bootstyle=bootstyle, padding=10)
        tb.Label(card, text=title, font=("Segoe UI", 8, "bold"), bootstyle=f"{bootstyle}-inverse").pack(anchor=W)
        lbl_val = tb.Label(card, text=value, font=("Segoe UI", 12, "bold"), bootstyle=f"{bootstyle}-inverse")
        lbl_val.pack(anchor=W, pady=(2, 0))
        card.value_label = lbl_val
        return card

    def _load_invoices(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        status = self.status_filter_var.get()
        search = self.search_var.get().strip() or None

        invoices = db.get_ar_invoices(
            company_id=self.company_id,
            status=status,
            customer_id=self.customer_id_filter,
            search=search
        )

        tot_invoiced = 0.0
        tot_received = 0.0
        tot_balance = 0.0
        overdue_cnt = 0

        for inv in invoices:
            tot = float(inv.get("total_amount") or 0.0)
            paid = float(inv.get("paid_amount") or 0.0)
            bal = float(inv.get("balance_due") or 0.0)

            if inv.get("status") != "Cancelled":
                tot_invoiced += tot
                tot_received += paid
                tot_balance += bal

            if inv.get("is_overdue"):
                overdue_cnt += 1
                row_tag = "overdue"
            elif inv.get("status") == "Paid":
                row_tag = "paid"
            elif inv.get("status") == "Partially Paid":
                row_tag = "partially_paid"
            elif inv.get("status") == "Cancelled":
                row_tag = "cancelled"
            else:
                row_tag = ""

            self.tree.insert("", END, values=(
                inv["id"],
                inv["invoice_number"],
                inv["invoice_date"],
                inv["customer_name"],
                inv["due_date"],
                f"{tot:,.2f}",
                f"{paid:,.2f}",
                f"{bal:,.2f}",
                inv["status"]
            ), tags=(row_tag,) if row_tag else ())

        self.card_total_inv.value_label.config(text=f"LKR {tot_invoiced:,.2f}")
        self.card_total_rec.value_label.config(text=f"LKR {tot_received:,.2f}")
        self.card_balance_due.value_label.config(text=f"LKR {tot_balance:,.2f}")
        self.card_overdue_count.value_label.config(text=str(overdue_cnt))

    def _get_selected_invoice_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select an invoice from the table.", parent=self)
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def _new_invoice(self):
        ARInvoiceEntryDialog(self, company_id=self.company_id, on_saved=lambda iid: self._load_invoices())

    def _edit_invoice(self):
        iid = self._get_selected_invoice_id()
        if not iid:
            return
        ARInvoiceEntryDialog(self, company_id=self.company_id, invoice_id=iid, on_saved=lambda iid: self._load_invoices())

    def _record_receipt(self):
        iid = self._get_selected_invoice_id()
        if not iid:
            return
        inv = db.get_ar_invoice(iid)
        if not inv:
            return
        if inv["invoice"]["status"] == "Paid":
            messagebox.showinfo("Already Settled", "This invoice is already fully paid.", parent=self)
            return
        ARReceiptDialog(self, invoice_id=iid, on_saved=lambda rid: self._load_invoices())

    def _print_pdf(self):
        iid = self._get_selected_invoice_id()
        if not iid:
            return
        inv = db.get_ar_invoice(iid)
        try:
            pdf_path = invoice_printer.generate_ar_invoice_pdf([iid])
            PdfViewerDialog(self, pdf_path, title=f"Tax Invoice #{inv['invoice']['invoice_number']}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate invoice PDF:\n{e}", parent=self)

    def _delete_invoice(self):
        iid = self._get_selected_invoice_id()
        if not iid:
            return
        inv = db.get_ar_invoice(iid)
        if not inv:
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete invoice #{inv['invoice']['invoice_number']}?\n"
            "This will remove the invoice, line items, and journal entry.",
            parent=self
        )
        if not confirm:
            return

        ok, msg = db.delete_ar_invoice(iid)
        if ok:
            messagebox.showinfo("Deleted", msg, parent=self)
            self._load_invoices()
        else:
            messagebox.showwarning("Deletion Blocked", msg, parent=self)

    def _open_ar_aging(self):
        ARAgingDialog(self, company_id=self.company_id)


class ARAgingDialog(tb.Toplevel):
    """Accounts Receivable (AR) Aging Report Dialog."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        comp = db.get_company(self.company_id)
        comp_name = comp.get("name", "Company") if comp else "Company"

        self.title(f"Accounts Receivable Aging Report — {comp_name}")
        self.geometry("1060x600")
        self.minsize(860, 480)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_report()
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
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header
        hdr = tb.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        title_box = tb.Frame(hdr)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="📊 Accounts Receivable (AR) Aging Report", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(title_box, text="Receivables categorized by overdue duration to monitor cash collection and credit risk.", font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)

        # Date selector
        date_box = tb.Frame(hdr)
        date_box.pack(side=RIGHT)
        tb.Label(date_box, text="As of Date:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.as_of_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(date_box, textvariable=self.as_of_var, width=12).pack(side=LEFT, padx=(0, 6))
        tb.Button(date_box, text="Refresh", bootstyle="outline", command=self._load_report).pack(side=LEFT)

        # Aging Buckets KPI Cards
        self.bucket_frame = tb.Frame(container)
        self.bucket_frame.pack(fill=X, pady=(0, 12))

        self.card_current = self._create_card("Current (Not Due)", "LKR 0.00", "success")
        self.card_1_30 = self._create_card("1 - 30 Days", "LKR 0.00", "info")
        self.card_31_60 = self._create_card("31 - 60 Days", "LKR 0.00", "warning")
        self.card_61_90 = self._create_card("61 - 90 Days", "LKR 0.00", "danger")
        self.card_over_90 = self._create_card("> 90 Days", "LKR 0.00", "danger")
        self.card_total = self._create_card("Total AR Due", "LKR 0.00", "primary")

        cards = [self.card_current, self.card_1_30, self.card_31_60, self.card_61_90, self.card_over_90, self.card_total]
        for idx, c in enumerate(cards):
            c.pack(side=LEFT, fill=X, expand=True, padx=(0 if idx == 0 else 4, 0 if idx == len(cards) - 1 else 4))

        # Aging Table
        table_f = tb.Frame(container)
        table_f.pack(fill=BOTH, expand=True)

        cols = ("customer", "contact", "phone", "current", "d1_30", "d31_60", "d61_90", "d_over90", "total")
        self.tree = ttk.Treeview(table_f, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("customer", text="Customer Name", anchor=W)
        self.tree.heading("contact", text="Contact", anchor=W)
        self.tree.heading("phone", text="Phone", anchor=W)
        self.tree.heading("current", text="Current", anchor=E)
        self.tree.heading("d1_30", text="1-30 Days", anchor=E)
        self.tree.heading("d31_60", text="31-60 Days", anchor=E)
        self.tree.heading("d61_90", text="61-90 Days", anchor=E)
        self.tree.heading("d_over90", text=">90 Days", anchor=E)
        self.tree.heading("total", text="Total Due", anchor=E)

        self.tree.column("customer", width=180)
        self.tree.column("contact", width=110)
        self.tree.column("phone", width=100)
        self.tree.column("current", width=95, anchor=E)
        self.tree.column("d1_30", width=95, anchor=E)
        self.tree.column("d31_60", width=95, anchor=E)
        self.tree.column("d61_90", width=95, anchor=E)
        self.tree.column("d_over90", width=95, anchor=E)
        self.tree.column("total", width=110, anchor=E)

        vsb = tb.Scrollbar(table_f, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        # Footer Actions
        btn_bar = tb.Frame(container)
        btn_bar.pack(fill=X, pady=(10, 0))

        tb.Button(btn_bar, text="📊 Export CSV", bootstyle="secondary-outline", command=self._export_csv).pack(side=LEFT)
        tb.Button(btn_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _create_card(self, title, val, style):
        f = tb.Frame(self.bucket_frame, bootstyle=style, padding=8)
        tb.Label(f, text=title, font=("Segoe UI", 7, "bold"), bootstyle=f"{style}-inverse").pack(anchor=W)
        lbl = tb.Label(f, text=val, font=("Segoe UI", 10, "bold"), bootstyle=f"{style}-inverse")
        lbl.pack(anchor=W, pady=(2, 0))
        f.val_lbl = lbl
        return f

    def _load_report(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        as_of = self.as_of_var.get().strip() or None
        report = db.get_ar_aging_report(company_id=self.company_id, as_of_date=as_of)
        t = report["totals"]

        self.card_current.val_lbl.config(text=f"LKR {t['current']:,.2f}")
        self.card_1_30.val_lbl.config(text=f"LKR {t['days_1_30']:,.2f}")
        self.card_31_60.val_lbl.config(text=f"LKR {t['days_31_60']:,.2f}")
        self.card_61_90.val_lbl.config(text=f"LKR {t['days_61_90']:,.2f}")
        self.card_over_90.val_lbl.config(text=f"LKR {t['days_over_90']:,.2f}")
        self.card_total.val_lbl.config(text=f"LKR {t['total_due']:,.2f}")

        for s in report["by_customer"]:
            self.tree.insert("", END, values=(
                s["customer_name"],
                s.get("contact_person") or "—",
                s.get("customer_phone") or "—",
                f"{s['current']:,.2f}",
                f"{s['days_1_30']:,.2f}",
                f"{s['days_31_60']:,.2f}",
                f"{s['days_61_90']:,.2f}",
                f"{s['days_over_90']:,.2f}",
                f"{s['total_due']:,.2f}"
            ))

    def _export_csv(self):
        report = db.get_ar_aging_report(company_id=self.company_id, as_of_date=self.as_of_var.get().strip())
        if not report["by_customer"]:
            messagebox.showinfo("Export", "No aging data to export.", parent=self)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export AR Aging Report",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")]
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Accounts Receivable (AR) Aging Report"])
                writer.writerow([f"As of Date: {report['as_of_date']}"])
                writer.writerow([])
                writer.writerow(["Customer Name", "Contact", "Phone", "Current", "1-30 Days", "31-60 Days", "61-90 Days", ">90 Days", "Total Due"])
                for s in report["by_customer"]:
                    writer.writerow([
                        s["customer_name"], s.get("contact_person", ""), s.get("customer_phone", ""),
                        s["current"], s["days_1_30"], s["days_31_60"], s["days_61_90"], s["days_over_90"], s["total_due"]
                    ])
                t = report["totals"]
                writer.writerow(["TOTALS", "", "", t["current"], t["days_1_30"], t["days_31_60"], t["days_61_90"], t["days_over_90"], t["total_due"]])

            messagebox.showinfo("Success", f"AR Aging Report exported to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export CSV: {e}", parent=self)
