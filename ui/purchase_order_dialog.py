"""
ui/purchase_order_dialog.py
Purchase Orders (PO) & Goods Received Notes (GRN) Management Interface (v4.0).

Provides:
- PurchaseOrderEntryDialog: Create & Edit purchase orders with dynamic line items and tax calculations.
- PurchaseOrderListDialog: Main Purchase Order register with KPIs, filters, receipt tracking, and actions.
- GRNEntryDialog: Warehouse receiving inspection dialog to record goods arrival against a PO.
- GRNListDialog: Register of all Goods Received Notes with item counts and PDF printing.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import po_printer
from ui.pdf_viewer import PdfViewerDialog
from ui.supplier_manager import SupplierEditModal


class PurchaseOrderEntryDialog(tb.Toplevel):
    """Dialog for creating or editing a Purchase Order."""

    def __init__(self, parent, company_id=None, po_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.po_id = po_id
        self.is_edit = bool(self.po_id)
        self.on_saved = on_saved

        self.title("Edit Purchase Order" if self.is_edit else "Create New Purchase Order (PO)")
        self.geometry("960x720")
        self.minsize(820, 600)
        self.transient(parent)
        self.grab_set()

        self.suppliers = db.get_suppliers(company_id=self.company_id, active_only=True)
        self.supplier_lookup = {s["name"]: s for s in self.suppliers}

        self.lines_data = []

        self._build_ui()
        if self.is_edit:
            self._load_po_data()
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

        tb.Label(hdr, text="Purchase Order Management", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(
            hdr,
            text="Issue official purchase orders to vendors, specify items & delivery dates, and track fulfillment.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # PO Header Details Frame
        form_box = tb.Labelframe(root, text="Order Header Details", padding=12)
        form_box.pack(fill=X, pady=(0, 10))

        # Row 1: Supplier, PO Number, Status
        r1 = tb.Frame(form_box)
        r1.pack(fill=X, pady=4)

        tb.Label(r1, text="Supplier *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.supplier_var = tk.StringVar()
        sup_names = list(self.supplier_lookup.keys())
        self.sup_combo = tb.Combobox(r1, textvariable=self.supplier_var, values=sup_names, width=28)
        self.sup_combo.pack(side=LEFT, padx=(0, 6))
        self.sup_combo.bind("<<ComboboxSelected>>", self._on_supplier_selected)

        tb.Button(r1, text="➕", bootstyle="outline", width=3, command=self._quick_add_supplier).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="PO Number *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.po_num_var = tk.StringVar()
        self.po_num_entry = tb.Entry(r1, textvariable=self.po_num_var, width=18)
        self.po_num_entry.pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Status:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.status_var = tk.StringVar(value="Draft")
        self.status_combo = tb.Combobox(r1, textvariable=self.status_var, values=["Draft", "Sent", "Partially Received", "Fully Received", "Cancelled"], state="readonly", width=16)
        self.status_combo.pack(side=LEFT)

        # Row 2: Dates, Currency, Exchange Rate
        r2 = tb.Frame(form_box)
        r2.pack(fill=X, pady=4)

        tb.Label(r2, text="Order Date *:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(r2, textvariable=self.date_var, width=12).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Expected Delivery:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.expected_date_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.expected_date_var, width=12).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Currency:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.curr_var = tk.StringVar(value=db.get_company_base_currency(self.company_id) or "LKR")
        tb.Entry(r2, textvariable=self.curr_var, width=6).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Delivery / Shipping To:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.ship_var = tk.StringVar(value="Company Main Warehouse")
        tb.Entry(r2, textvariable=self.ship_var, width=28).pack(side=LEFT)

        # Row 3: Terms & Approver
        r3 = tb.Frame(form_box)
        r3.pack(fill=X, pady=4)

        tb.Label(r3, text="Payment Terms:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.terms_var = tk.StringVar(value="Net 30 Days")
        tb.Entry(r3, textvariable=self.terms_var, width=30).pack(side=LEFT, padx=(0, 20))

        tb.Label(r3, text="Authorized / Approved By:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.approved_by_var = tk.StringVar()
        tb.Entry(r3, textvariable=self.approved_by_var, width=24).pack(side=LEFT)

        # Line Items Section
        items_box = tb.Labelframe(root, text="Line Items & Specifications", padding=10)
        items_box.pack(fill=BOTH, expand=True, pady=(0, 8))

        # Action bar for line items
        bar = tb.Frame(items_box)
        bar.pack(fill=X, pady=(0, 6))
        tb.Button(bar, text="➕ Add Line Item", bootstyle="primary-outline", command=self._add_line_item).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="🗑️ Remove Selected", bootstyle="danger-outline", command=self._remove_selected_line).pack(side=LEFT)

        # Treeview for line items
        cols = ("idx", "desc", "unit", "qty", "uprice", "tax_rate", "total")
        self.tree = ttk.Treeview(items_box, columns=cols, show="headings", selectmode="browse", height=7)
        self.tree.heading("idx", text="#")
        self.tree.heading("desc", text="Item Description / Specification")
        self.tree.heading("unit", text="Unit")
        self.tree.heading("qty", text="Quantity")
        self.tree.heading("uprice", text="Unit Price")
        self.tree.heading("tax_rate", text="Tax Rate")
        self.tree.heading("total", text="Line Total")

        self.tree.column("idx", width=35, anchor=CENTER)
        self.tree.column("desc", width=360, anchor=W)
        self.tree.column("unit", width=65, anchor=CENTER)
        self.tree.column("qty", width=80, anchor=E)
        self.tree.column("uprice", width=105, anchor=E)
        self.tree.column("tax_rate", width=80, anchor=E)
        self.tree.column("total", width=120, anchor=E)

        vsb = tb.Scrollbar(items_box, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_selected_line())

        # Bottom Totals & Notes Section
        bottom_box = tb.Frame(root)
        bottom_box.pack(fill=X, pady=(0, 8))

        # Notes Frame
        notes_frame = tb.Labelframe(bottom_box, text="Order Notes & Special Instructions", padding=8)
        notes_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))

        self.notes_text = tk.Text(notes_frame, height=3, font=("Segoe UI", 9))
        self.notes_text.pack(fill=BOTH, expand=True)
        self.notes_text.insert("1.0", "Please inspect all packages upon delivery and quote PO number on invoice.")

        # Financial Summary Frame
        sum_frame = tb.Labelframe(bottom_box, text="Financial Summary", padding=10)
        sum_frame.pack(side=RIGHT, fill=Y)

        grid = tb.Frame(sum_frame)
        grid.pack(fill=BOTH, expand=True)

        tb.Label(grid, text="Subtotal:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky=W, pady=2)
        self.lbl_subtotal = tb.Label(grid, text="0.00", font=("Segoe UI", 9, "bold"))
        self.lbl_subtotal.grid(row=0, column=1, sticky=E, padx=(16, 0), pady=2)

        tb.Label(grid, text="VAT / Tax Amount:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky=W, pady=2)
        self.lbl_tax = tb.Label(grid, text="0.00", font=("Segoe UI", 9))
        self.lbl_tax.grid(row=1, column=1, sticky=E, padx=(16, 0), pady=2)

        tb.Separator(grid, orient=HORIZONTAL).grid(row=2, column=0, columnspan=2, sticky=EW, pady=4)

        tb.Label(grid, text="Total Order Value:", font=("Segoe UI", 10, "bold"), bootstyle="primary").grid(row=3, column=0, sticky=W, pady=2)
        self.lbl_total = tb.Label(grid, text="0.00", font=("Segoe UI", 11, "bold"), bootstyle="primary")
        self.lbl_total.grid(row=3, column=1, sticky=E, padx=(16, 0), pady=2)

        # Action Buttons Footer
        footer = tb.Frame(root)
        footer.pack(fill=X, pady=(6, 0))

        tb.Button(footer, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(footer, text="Save & Print PDF", bootstyle="info", command=lambda: self._save_po(print_pdf=True)).pack(side=RIGHT, padx=(6, 0))
        tb.Button(footer, text="Save & Send", bootstyle="success", command=lambda: self._save_po(status="Sent")).pack(side=RIGHT, padx=(6, 0))
        tb.Button(footer, text="Save Draft", bootstyle="primary", command=lambda: self._save_po(status="Draft")).pack(side=RIGHT)

    def _init_defaults(self):
        next_po = db.get_next_po_number(company_id=self.company_id)
        self.po_num_var.set(next_po)
        # Default expected delivery: 14 days
        exp = datetime.now() + timedelta(days=14)
        self.expected_date_var.set(exp.strftime("%Y-%m-%d"))

    def _load_po_data(self):
        po = db.get_purchase_order(self.po_id)
        if not po:
            return

        self.po_num_var.set(po.get("po_number", ""))
        self.date_var.set(po.get("po_date", ""))
        self.expected_date_var.set(po.get("expected_date", ""))
        self.curr_var.set(po.get("currency", "LKR"))
        self.ship_var.set(po.get("shipping_address", ""))
        self.terms_var.set(po.get("terms", ""))
        self.approved_by_var.set(po.get("approved_by", ""))
        self.status_var.set(po.get("status", "Draft"))

        if po.get("supplier_name"):
            self.supplier_var.set(po["supplier_name"])

        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", po.get("notes", ""))

        self.lines_data = []
        for pl in po.get("lines", []):
            self.lines_data.append({
                "description": pl.get("description", ""),
                "quantity": float(pl.get("quantity", 1.0)),
                "unit_price": float(pl.get("unit_price", 0.0)),
                "unit": pl.get("unit", "pcs"),
                "tax_rate": float(pl.get("tax_rate", 0.0)),
            })
        self._refresh_lines_table()

    def _on_supplier_selected(self, event=None):
        name = self.supplier_var.get()
        sup = self.supplier_lookup.get(name)
        if sup and sup.get("payment_terms"):
            self.terms_var.set(f"Net {sup['payment_terms']} Days")

    def _quick_add_supplier(self):
        def _on_supplier_created(new_sup_id):
            self.suppliers = db.get_suppliers(company_id=self.company_id, active_only=True)
            self.supplier_lookup = {s["name"]: s for s in self.suppliers}
            self.sup_combo["values"] = list(self.supplier_lookup.keys())
            created_sup = db.get_supplier(new_sup_id)
            if created_sup:
                self.supplier_var.set(created_sup["name"])
                self._on_supplier_selected()

        SupplierEditModal(self, company_id=self.company_id, on_saved=_on_supplier_created)

    def _add_line_item(self):
        modal = LineItemEditModal(self, on_saved=self._append_line)

    def _append_line(self, line_dict):
        self.lines_data.append(line_dict)
        self._refresh_lines_table()

    def _edit_selected_line(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(self.tree.item(sel[0])["values"][0]) - 1
        item = self.lines_data[idx]

        def _on_updated(updated_dict):
            self.lines_data[idx] = updated_dict
            self._refresh_lines_table()

        LineItemEditModal(self, line_data=item, on_saved=_on_updated)

    def _remove_selected_line(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(self.tree.item(sel[0])["values"][0]) - 1
        self.lines_data.pop(idx)
        self._refresh_lines_table()

    def _refresh_lines_table(self):
        self.tree.delete(*self.tree.get_children())
        subtotal = 0.0
        tax_total = 0.0

        for i, line in enumerate(self.lines_data, 1):
            qty = float(line.get("quantity", 1.0))
            uprice = float(line.get("unit_price", 0.0))
            trate = float(line.get("tax_rate", 0.0))
            ltotal = round(qty * uprice, 2)
            ltax = round(ltotal * trate, 2)
            subtotal += ltotal
            tax_total += ltax

            tax_lbl = f"{trate * 100:.0f}%" if trate > 0 else "0%"
            self.tree.insert("", tk.END, values=(
                i,
                line.get("description", ""),
                line.get("unit", "pcs"),
                f"{qty:,.2f}".rstrip('0').rstrip('.'),
                f"{uprice:,.2f}",
                tax_lbl,
                f"{ltotal:,.2f}"
            ))

        total = round(subtotal + tax_total, 2)
        curr = self.curr_var.get()
        self.lbl_subtotal.config(text=f"{curr} {subtotal:,.2f}")
        self.lbl_tax.config(text=f"{curr} {tax_total:,.2f}")
        self.lbl_total.config(text=f"{curr} {total:,.2f}")

    def _save_po(self, status=None, print_pdf=False):
        sup_name = self.supplier_var.get().strip()
        supplier = self.supplier_lookup.get(sup_name)
        if not supplier:
            messagebox.showwarning("Validation Error", "Please select a valid supplier.", parent=self)
            return

        po_num = self.po_num_var.get().strip()
        if not po_num:
            messagebox.showwarning("Validation Error", "PO number cannot be blank.", parent=self)
            return

        if not self.lines_data:
            messagebox.showwarning("Validation Error", "Please add at least one line item to the purchase order.", parent=self)
            return

        header = {
            "company_id": self.company_id,
            "supplier_id": supplier["id"],
            "po_number": po_num,
            "po_date": self.date_var.get().strip(),
            "expected_date": self.expected_date_var.get().strip(),
            "currency": self.curr_var.get().strip(),
            "status": status or self.status_var.get(),
            "shipping_address": self.ship_var.get().strip(),
            "terms": self.terms_var.get().strip(),
            "notes": self.notes_text.get("1.0", tk.END).strip(),
            "approved_by": self.approved_by_var.get().strip()
        }

        try:
            if self.is_edit:
                saved_id = db.update_purchase_order(self.po_id, header, self.lines_data)
            else:
                saved_id = db.create_purchase_order(header, self.lines_data)

            if print_pdf:
                pdf_path = po_printer.generate_purchase_order_pdf(saved_id)
                PdfViewerDialog(self.master, pdf_path, title=f"Purchase Order — {po_num}")

            if self.on_saved:
                self.on_saved(saved_id)

            self.destroy()
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save Purchase Order:\n{e}", parent=self)


class LineItemEditModal(tb.Toplevel):
    """Modal dialog to add or edit a Purchase Order line item."""

    COMMON_UNITS = ["pcs", "units", "kg", "g", "L", "mL", "m", "cm", "boxes", "packs", "hours", "days"]

    def __init__(self, parent, line_data=None, on_saved=None):
        super().__init__(parent)
        self.line_data = line_data or {}
        self.is_edit = bool(line_data)
        self.on_saved = on_saved

        self.title("Edit Line Item" if self.is_edit else "Add Purchase Order Line")
        self.geometry("480x360")
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

        tb.Label(container, text="Item Specification", font=("Segoe UI", 12, "bold")).pack(anchor=W, pady=(0, 10))

        # Description
        tb.Label(container, text="Description / Item Name *:", font=("Segoe UI", 9, "bold")).pack(anchor=W)
        self.desc_var = tk.StringVar(value=self.line_data.get("description", ""))
        tb.Entry(container, textvariable=self.desc_var).pack(fill=X, pady=(2, 10))

        # Quantity and Unit
        row1 = tb.Frame(container)
        row1.pack(fill=X, pady=(0, 10))

        col1 = tb.Frame(row1)
        col1.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        tb.Label(col1, text="Quantity *:", font=("Segoe UI", 9, "bold")).pack(anchor=W)
        self.qty_var = tk.StringVar(value=str(self.line_data.get("quantity", 1.0)))
        tb.Entry(col1, textvariable=self.qty_var).pack(fill=X, pady=(2, 0))

        col2 = tb.Frame(row1)
        col2.pack(side=LEFT, fill=X, expand=True)
        tb.Label(col2, text="Unit:", font=("Segoe UI", 9)).pack(anchor=W)
        self.unit_var = tk.StringVar(value=self.line_data.get("unit", "pcs"))
        tb.Combobox(col2, textvariable=self.unit_var, values=self.COMMON_UNITS).pack(fill=X, pady=(2, 0))

        # Price and Tax
        row2 = tb.Frame(container)
        row2.pack(fill=X, pady=(0, 16))

        col3 = tb.Frame(row2)
        col3.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        tb.Label(col3, text="Unit Price *:", font=("Segoe UI", 9, "bold")).pack(anchor=W)
        self.price_var = tk.StringVar(value=str(self.line_data.get("unit_price", 0.0)))
        tb.Entry(col3, textvariable=self.price_var).pack(fill=X, pady=(2, 0))

        col4 = tb.Frame(row2)
        col4.pack(side=LEFT, fill=X, expand=True)
        tb.Label(col4, text="Tax Rate (e.g. 0.18):", font=("Segoe UI", 9)).pack(anchor=W)
        self.tax_var = tk.StringVar(value=str(self.line_data.get("tax_rate", 0.0)))
        tb.Entry(col4, textvariable=self.tax_var).pack(fill=X, pady=(2, 0))

        # Buttons
        btns = tb.Frame(container)
        btns.pack(fill=X)
        tb.Button(btns, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btns, text="Apply Item", bootstyle="primary", command=self._save_item).pack(side=RIGHT)

    def _save_item(self):
        desc = self.desc_var.get().strip()
        if not desc:
            messagebox.showwarning("Validation Error", "Description is required.", parent=self)
            return

        try:
            qty = float(self.qty_var.get().strip())
            price = float(self.price_var.get().strip())
            tax = float(self.tax_var.get().strip())
        except ValueError:
            messagebox.showwarning("Validation Error", "Quantity, Unit Price, and Tax Rate must be numeric.", parent=self)
            return

        res = {
            "description": desc,
            "unit": self.unit_var.get().strip() or "pcs",
            "quantity": qty,
            "unit_price": price,
            "tax_rate": tax
        }
        if self.on_saved:
            self.on_saved(res)
        self.destroy()


# =========================================================================
# GOODS RECEIVED NOTE (GRN) ENTRY DIALOG
# =========================================================================

class GRNEntryDialog(tb.Toplevel):
    """Warehouse receiving inspection modal to record items received against a Purchase Order."""

    def __init__(self, parent, po_id, on_saved=None):
        super().__init__(parent)
        self.po_id = po_id
        self.on_saved = on_saved
        self.po = db.get_purchase_order(self.po_id)
        if not self.po:
            raise ValueError(f"Purchase Order #{self.po_id} not found.")

        self.title(f"Record Goods Received Note — {self.po['po_number']}")
        self.geometry("900x600")
        self.minsize(750, 480)
        self.transient(parent)
        self.grab_set()

        self.line_entries = []

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
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        # Header Info Banner
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text=f"📦 Goods Received Note (GRN) for {self.po['po_number']}", font=("Segoe UI", 14, "bold")).pack(anchor=W)
        tb.Label(
            hdr,
            text=f"Vendor: {self.po.get('supplier_name', '')}  |  Order Date: {self.po.get('po_date', '')}",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # GRN Header Form
        form = tb.Labelframe(root, text="Shipment & Carrier Details", padding=10)
        form.pack(fill=X, pady=(0, 10))

        r1 = tb.Frame(form)
        r1.pack(fill=X, pady=2)

        tb.Label(r1, text="GRN Number *:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 4))
        self.grn_num_var = tk.StringVar(value=db.get_next_grn_number(self.po["company_id"]))
        tb.Entry(r1, textvariable=self.grn_num_var, width=18).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Receipt Date *:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.grn_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(r1, textvariable=self.grn_date_var, width=12).pack(side=LEFT, padx=(0, 16))

        tb.Label(r1, text="Received By Officer:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.received_by_var = tk.StringVar(value="Warehouse Storekeeper")
        tb.Entry(r1, textvariable=self.received_by_var, width=22).pack(side=LEFT)

        r2 = tb.Frame(form)
        r2.pack(fill=X, pady=4)

        tb.Label(r2, text="Delivery Note / Waybill Ref:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.delivery_ref_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.delivery_ref_var, width=28).pack(side=LEFT, padx=(0, 16))

        tb.Label(r2, text="Storage Remarks:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.notes_var = tk.StringVar()
        tb.Entry(r2, textvariable=self.notes_var, width=40).pack(side=LEFT)

        # Items Receiving Table
        items_frame = tb.Labelframe(root, text="Line Items Receipt Inspection", padding=10)
        items_frame.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Table Canvas for scrollable rows
        canvas = tk.Canvas(items_frame, highlightthickness=0)
        vsb = tb.Scrollbar(items_frame, orient=VERTICAL, command=canvas.yview)
        scrollable_frame = tb.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        # Table Header
        hdr_row = tb.Frame(scrollable_frame, padding=(4, 4))
        hdr_row.pack(fill=X)
        tb.Label(hdr_row, text="#", width=4, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        tb.Label(hdr_row, text="Item Description", width=34, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        tb.Label(hdr_row, text="Ordered", width=10, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        tb.Label(hdr_row, text="Prev. Recv.", width=10, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        tb.Label(hdr_row, text="Remaining", width=10, font=("Segoe UI", 8, "bold")).pack(side=LEFT)
        tb.Label(hdr_row, text="Recv. Now *", width=12, font=("Segoe UI", 8, "bold"), bootstyle="success").pack(side=LEFT)
        tb.Label(hdr_row, text="Rejected", width=10, font=("Segoe UI", 8, "bold"), bootstyle="danger").pack(side=LEFT)
        tb.Label(hdr_row, text="Condition / Inspection Notes", width=24, font=("Segoe UI", 8, "bold")).pack(side=LEFT)

        tb.Separator(scrollable_frame, orient=HORIZONTAL).pack(fill=X, pady=2)

        # Populate rows
        for idx, pl in enumerate(self.po.get("lines", []), 1):
            row = tb.Frame(scrollable_frame, padding=(4, 3))
            row.pack(fill=X)

            rem_qty = pl.get("remaining_qty", 0.0)

            tb.Label(row, text=str(idx), width=4).pack(side=LEFT)
            tb.Label(row, text=pl.get("description", "")[:35], width=34, anchor=W).pack(side=LEFT)
            tb.Label(row, text=f"{pl.get('quantity', 0):,.1f} {pl.get('unit', '')}", width=10, anchor=E).pack(side=LEFT)
            tb.Label(row, text=f"{pl.get('received_qty', 0):,.1f}", width=10, anchor=E).pack(side=LEFT)
            tb.Label(row, text=f"{rem_qty:,.1f}", width=10, anchor=E, font=("Segoe UI", 8, "bold")).pack(side=LEFT)

            recv_var = tk.StringVar(value=str(rem_qty if rem_qty > 0 else 0.0))
            recv_ent = tb.Entry(row, textvariable=recv_var, width=10)
            recv_ent.pack(side=LEFT, padx=4)

            rej_var = tk.StringVar(value="0.0")
            rej_ent = tb.Entry(row, textvariable=rej_var, width=8)
            rej_ent.pack(side=LEFT, padx=4)

            note_var = tk.StringVar(value="Inspected & Good condition")
            note_ent = tb.Entry(row, textvariable=note_var, width=24)
            note_ent.pack(side=LEFT, padx=4)

            self.line_entries.append({
                "po_line_id": pl["id"],
                "recv_var": recv_var,
                "rej_var": rej_var,
                "note_var": note_var,
                "remaining_qty": rem_qty
            })

        # Footer Buttons
        footer = tb.Frame(root)
        footer.pack(fill=X)

        tb.Button(footer, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(footer, text="Confirm & Print GRN Slip", bootstyle="info", command=lambda: self._submit_grn(print_pdf=True)).pack(side=RIGHT, padx=(6, 0))
        tb.Button(footer, text="Confirm & Record GRN", bootstyle="success", command=lambda: self._submit_grn(print_pdf=False)).pack(side=RIGHT)

    def _submit_grn(self, print_pdf=False):
        grn_num = self.grn_num_var.get().strip()
        if not grn_num:
            messagebox.showwarning("Validation Error", "GRN Number cannot be blank.", parent=self)
            return

        lines_to_save = []
        has_any_positive = False

        for item in self.line_entries:
            try:
                r_qty = float(item["recv_var"].get().strip())
                rej_qty = float(item["rej_var"].get().strip())
            except ValueError:
                messagebox.showwarning("Validation Error", "Quantities must be numeric.", parent=self)
                return

            if r_qty > 0.0:
                has_any_positive = True

            lines_to_save.append({
                "po_line_id": item["po_line_id"],
                "received_qty": r_qty,
                "rejected_qty": rej_qty,
                "condition_notes": item["note_var"].get().strip()
            })

        if not has_any_positive:
            messagebox.showwarning("Validation Error", "At least one item must have a received quantity greater than zero.", parent=self)
            return

        header = {
            "company_id": self.po["company_id"],
            "po_id": self.po_id,
            "grn_number": grn_num,
            "grn_date": self.grn_date_var.get().strip(),
            "received_by": self.received_by_var.get().strip(),
            "delivery_note_ref": self.delivery_ref_var.get().strip(),
            "notes": self.notes_var.get().strip()
        }

        try:
            grn_id = db.create_goods_received_note(header, lines_to_save)
            messagebox.showinfo("Receipt Recorded", f"Goods Received Note {grn_num} recorded successfully!", parent=self)

            if print_pdf:
                pdf_path = po_printer.generate_grn_pdf(grn_id)
                PdfViewerDialog(self.master, pdf_path, title=f"GRN — {grn_num}")

            if self.on_saved:
                self.on_saved(grn_id)

            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to record GRN:\n{e}", parent=self)


# =========================================================================
# GOODS RECEIVED NOTE (GRN) LIST DIALOG
# =========================================================================

class GRNListDialog(tb.Toplevel):
    """Register of Goods Received Notes (GRN)."""

    def __init__(self, parent, company_id=None, po_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.po_id = po_id

        title_suffix = f"for PO #{po_id}" if po_id else "Register"
        self.title(f"Goods Received Notes (GRN) {title_suffix}")
        self.geometry("900x520")
        self.minsize(750, 400)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_list()

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

        tb.Label(container, text="Goods Received Notes (GRN) Warehouse Log", font=("Segoe UI", 14, "bold")).pack(anchor=W)

        # Treeview
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True, pady=10)

        cols = ("id", "grn_num", "date", "po_num", "supplier", "received_by", "qty")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("grn_num", text="GRN Number")
        self.tree.heading("date", text="Received Date")
        self.tree.heading("po_num", text="PO Number")
        self.tree.heading("supplier", text="Supplier")
        self.tree.heading("received_by", text="Received By")
        self.tree.heading("qty", text="Total Qty Recv.")

        self.tree.column("id", width=40, anchor=CENTER)
        self.tree.column("grn_num", width=140, anchor=W)
        self.tree.column("date", width=110, anchor=W)
        self.tree.column("po_num", width=130, anchor=W)
        self.tree.column("supplier", width=220, anchor=W)
        self.tree.column("received_by", width=140, anchor=W)
        self.tree.column("qty", width=100, anchor=E)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        # Buttons
        btns = tb.Frame(container)
        btns.pack(fill=X)

        tb.Button(btns, text="📄 Print GRN Slip", bootstyle="primary", command=self._print_selected).pack(side=LEFT, padx=(0, 6))
        tb.Button(btns, text="🗑️ Delete / Revert GRN", bootstyle="danger-outline", command=self._delete_selected).pack(side=LEFT)
        tb.Button(btns, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        rows = db.get_all_goods_received_notes(self.company_id, po_id=self.po_id)
        for r in rows:
            self.tree.insert("", tk.END, values=(
                r["id"],
                r["grn_number"],
                r["grn_date"],
                r["po_number"],
                r["supplier_name"],
                r["received_by"],
                f"{r.get('total_received_qty', 0):,.1f}"
            ))

    def _print_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select GRN", "Please select a GRN to print.", parent=self)
            return
        grn_id = int(self.tree.item(sel[0])["values"][0])
        pdf = po_printer.generate_grn_pdf(grn_id)
        PdfViewerDialog(self.master, pdf, title="Goods Received Note")

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select GRN", "Please select a GRN to delete.", parent=self)
            return
        grn_id = int(self.tree.item(sel[0])["values"][0])
        grn_num = self.tree.item(sel[0])["values"][1]

        if messagebox.askyesno("Confirm Reversal", f"Are you sure you want to delete and revert GRN {grn_num}?\n\nThis will reverse received quantities on the Purchase Order.", parent=self):
            try:
                db.delete_goods_received_note(grn_id)
                messagebox.showinfo("Success", f"GRN {grn_num} reverted.", parent=self)
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete GRN:\n{e}", parent=self)


# =========================================================================
# PURCHASE ORDER LIST / REGISTER DIALOG
# =========================================================================

class PurchaseOrderListDialog(tb.Toplevel):
    """Main Purchase Order Register & Dashboard."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Purchase Orders (PO) & Receiving Register")
        self.geometry("1120x680")
        self.minsize(920, 520)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_list()

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

        tb.Label(hdr, text="📦 Purchase Orders & Vendor Fulfillment", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(
            hdr,
            text="Manage vendor purchase orders, receive shipments (GRN), and perform 3-way matching to Accounts Payable.",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        ).pack(anchor=W)

        # Top KPI Cards
        kpi_frame = tb.Frame(container)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.kpi_total = self._create_kpi_card(kpi_frame, "Total Orders", "0", "primary")
        self.kpi_open = self._create_kpi_card(kpi_frame, "Pending Delivery", "0", "warning")
        self.kpi_recv = self._create_kpi_card(kpi_frame, "Delivered / Fulfilled", "0", "success")
        self.kpi_val = self._create_kpi_card(kpi_frame, "Total Order Value", "0.00", "info")

        # Filter Toolbar
        filters = tb.Labelframe(container, text="Search & Filter", padding=10)
        filters.pack(fill=X, pady=(0, 10))

        tb.Label(filters, text="Search:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        s_ent = tb.Entry(filters, textvariable=self.search_var, width=22)
        s_ent.pack(side=LEFT, padx=(0, 14))
        s_ent.bind("<Return>", lambda e: self._refresh_list())

        tb.Label(filters, text="Status:", font=("Segoe UI", 9)).pack(side=LEFT, padx=(0, 4))
        self.status_filter_var = tk.StringVar(value="All")
        status_cb = tb.Combobox(filters, textvariable=self.status_filter_var, values=["All", "Draft", "Sent", "Partially Received", "Fully Received", "Cancelled"], state="readonly", width=18)
        status_cb.pack(side=LEFT, padx=(0, 14))
        status_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tb.Button(filters, text="Filter", bootstyle="outline", command=self._refresh_list).pack(side=LEFT, padx=4)
        tb.Button(filters, text="Reset", bootstyle="secondary-outline", command=self._reset_filters).pack(side=LEFT, padx=4)

        # Action Buttons Top Bar
        bar = tb.Frame(container)
        bar.pack(fill=X, pady=(0, 8))

        tb.Button(bar, text="➕ New Purchase Order", bootstyle="primary", command=self._new_po).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="✏️ Edit Order", bootstyle="secondary-outline", command=self._edit_po).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="📥 Receive Goods (GRN)", bootstyle="success", command=self._record_grn).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="🧾 Convert to AP Invoice", bootstyle="info", command=self._convert_to_ap).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="📄 Print PO PDF", bootstyle="info-outline", command=self._print_po).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="📜 View GRN Logs", bootstyle="secondary-outline", command=self._view_grns).pack(side=LEFT, padx=(0, 6))
        tb.Button(bar, text="❌ Delete Order", bootstyle="danger-outline", command=self._delete_po).pack(side=LEFT)

        # Treeview
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "po_num", "po_date", "exp_date", "supplier", "status", "val", "recv_pct")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("po_num", text="PO Number")
        self.tree.heading("po_date", text="Order Date")
        self.tree.heading("exp_date", text="Expected Date")
        self.tree.heading("supplier", text="Supplier / Vendor")
        self.tree.heading("status", text="Order Status")
        self.tree.heading("val", text=f"Total Value ({self.currency})")
        self.tree.heading("recv_pct", text="Received %")

        self.tree.column("id", width=40, anchor=CENTER)
        self.tree.column("po_num", width=130, anchor=W)
        self.tree.column("po_date", width=105, anchor=W)
        self.tree.column("exp_date", width=110, anchor=W)
        self.tree.column("supplier", width=260, anchor=W)
        self.tree.column("status", width=140, anchor=CENTER)
        self.tree.column("val", width=140, anchor=E)
        self.tree.column("recv_pct", width=95, anchor=CENTER)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        vsb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_po())

        # Status row tags
        self.tree.tag_configure("fully_received", foreground="#15803D")
        self.tree.tag_configure("partially_received", foreground="#B45309")
        self.tree.tag_configure("sent", foreground="#1D4ED8")
        self.tree.tag_configure("cancelled", foreground="#94A3B8")

    def _create_kpi_card(self, parent, label_text, default_val, bootstyle):
        frame = tb.Frame(parent, bootstyle=bootstyle, padding=(12, 8))
        frame.pack(side=LEFT, fill=X, expand=True, padx=4)
        tb.Label(frame, text=label_text, font=("Segoe UI", 8), bootstyle=f"{bootstyle}-inverse").pack(anchor=W)
        val_lbl = tb.Label(frame, text=default_val, font=("Segoe UI", 12, "bold"), bootstyle=f"{bootstyle}-inverse")
        val_lbl.pack(anchor=W, pady=(2, 0))
        return val_lbl

    def _reset_filters(self):
        self.search_var.set("")
        self.status_filter_var.set("All")
        self._refresh_list()

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        search = self.search_var.get().strip()
        status = self.status_filter_var.get()

        orders = db.get_purchase_orders(
            company_id=self.company_id,
            status=status if status != "All" else None,
            search=search or None
        )

        tot_orders = len(orders)
        open_orders = 0
        recv_orders = 0
        total_val = 0.0

        for po in orders:
            val = float(po.get("total_amount") or 0.0)
            total_val += val
            st = po.get("status", "Draft")

            if st in ("Draft", "Sent"):
                open_orders += 1
            elif st in ("Partially Received", "Fully Received"):
                recv_orders += 1

            tag = "default"
            if st == "Fully Received":
                tag = "fully_received"
            elif st == "Partially Received":
                tag = "partially_received"
            elif st == "Sent":
                tag = "sent"
            elif st == "Cancelled":
                tag = "cancelled"

            self.tree.insert("", tk.END, values=(
                po["id"],
                po["po_number"],
                po["po_date"],
                po.get("expected_date") or "-",
                po.get("supplier_name", "Supplier Not Set"),
                st,
                f"{val:,.2f}",
                f"{po.get('received_percentage', 0.0):.0f}%"
            ), tags=(tag,))

        self.kpi_total.config(text=str(tot_orders))
        self.kpi_open.config(text=str(open_orders))
        self.kpi_recv.config(text=str(recv_orders))
        self.kpi_val.config(text=f"{self.currency} {total_val:,.2f}")

    def _new_po(self):
        PurchaseOrderEntryDialog(self, company_id=self.company_id, on_saved=lambda id: self._refresh_list())

    def _edit_po(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select a purchase order to view or edit.", parent=self)
            return
        po_id = int(self.tree.item(sel[0])["values"][0])
        PurchaseOrderEntryDialog(self, company_id=self.company_id, po_id=po_id, on_saved=lambda id: self._refresh_list())

    def _record_grn(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select a purchase order to record received goods.", parent=self)
            return
        po_id = int(self.tree.item(sel[0])["values"][0])
        GRNEntryDialog(self, po_id=po_id, on_saved=lambda id: self._refresh_list())

    def _convert_to_ap(self):
        """Three-way match: convert PO directly into AP supplier invoice."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select a purchase order to convert to an AP Invoice.", parent=self)
            return
        po_id = int(self.tree.item(sel[0])["values"][0])
        po_num = self.tree.item(sel[0])["values"][1]

        if messagebox.askyesno(
            "Three-Way Matching",
            f"Convert Purchase Order {po_num} to an Accounts Payable Supplier Invoice?\n\n"
            f"This will generate an AP invoice with all line items linked to this PO.",
            parent=self
        ):
            try:
                inv_id = db.create_ap_invoice_from_po(po_id)
                messagebox.showinfo(
                    "3-Way Match Success",
                    f"Successfully created Accounts Payable Invoice #{inv_id} linked to PO {po_num}!",
                    parent=self
                )
            except Exception as e:
                messagebox.showerror("Conversion Error", f"Failed to convert PO to AP Invoice:\n{e}", parent=self)

    def _print_po(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select a purchase order to print.", parent=self)
            return
        po_id = int(self.tree.item(sel[0])["values"][0])
        pdf = po_printer.generate_purchase_order_pdf(po_id)
        PdfViewerDialog(self.master, pdf, title="Purchase Order Document")

    def _view_grns(self):
        sel = self.tree.selection()
        po_id = int(self.tree.item(sel[0])["values"][0]) if sel else None
        GRNListDialog(self, company_id=self.company_id, po_id=po_id)

    def _delete_po(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Order", "Please select a purchase order to delete.", parent=self)
            return
        po_id = int(self.tree.item(sel[0])["values"][0])
        po_num = self.tree.item(sel[0])["values"][1]

        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete Purchase Order {po_num}?", parent=self):
            try:
                db.delete_purchase_order(po_id)
                messagebox.showinfo("Success", f"Purchase Order {po_num} deleted successfully.", parent=self)
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Cannot delete order:\n{e}", parent=self)
