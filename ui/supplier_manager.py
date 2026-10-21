"""
ui/supplier_manager.py
Supplier & Vendor Management Module for Voucher Machine SME Bookkeeping v3.5.

Provides:
- SupplierManagerDialog: Complete Supplier Directory with balance tracking,
  search, contact details, invoice linking, and CSV export.
- SupplierEditModal: Modal form for creating and editing supplier records.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from ui.merge_dialog import choose_merge_target


class SupplierEditModal(tb.Toplevel):
    """Modal for creating or editing a supplier/vendor profile."""

    def __init__(self, parent, company_id=None, supplier_data=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.supplier_data = supplier_data or {}
        self.on_saved = on_saved
        self.is_edit = bool(self.supplier_data.get("id"))

        self.title("Edit Supplier" if self.is_edit else "Add New Supplier")
        self.geometry("540x570")
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

        header_title = "Edit Supplier Profile" if self.is_edit else "Register New Supplier"
        header_desc = "Record vendor contact info, payment terms, and bank details for AP billing."
        tb.Label(container, text=header_title, font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(container, text=header_desc, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 14))

        form = tb.Frame(container)
        form.pack(fill=BOTH, expand=True)

        # Supplier Name
        tb.Label(form, text="Supplier Name *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=5)
        self.name_var = tk.StringVar()
        self.name_entry = tb.Entry(form, textvariable=self.name_var, width=32)
        self.name_entry.grid(row=0, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Contact Person
        tb.Label(form, text="Contact Person:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky=W, pady=5)
        self.contact_var = tk.StringVar()
        tb.Entry(form, textvariable=self.contact_var, width=32).grid(row=1, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Phone
        tb.Label(form, text="Phone / Mobile:", font=("Segoe UI", 9)).grid(row=2, column=0, sticky=W, pady=5)
        self.phone_var = tk.StringVar()
        tb.Entry(form, textvariable=self.phone_var, width=32).grid(row=2, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Email
        tb.Label(form, text="Email Address:", font=("Segoe UI", 9)).grid(row=3, column=0, sticky=W, pady=5)
        self.email_var = tk.StringVar()
        tb.Entry(form, textvariable=self.email_var, width=32).grid(row=3, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Address
        tb.Label(form, text="Postal Address:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky=W, pady=5)
        self.address_var = tk.StringVar()
        tb.Entry(form, textvariable=self.address_var, width=32).grid(row=4, column=1, sticky=EW, pady=5, padx=(10, 0))

        # VAT / Tax ID
        tb.Label(form, text="VAT / Tax Reg #:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky=W, pady=5)
        self.tax_id_var = tk.StringVar()
        tb.Entry(form, textvariable=self.tax_id_var, width=32).grid(row=5, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Payment Terms (Days)
        tb.Label(form, text="Payment Terms (Days):", font=("Segoe UI", 9)).grid(row=6, column=0, sticky=W, pady=5)
        self.terms_var = tk.StringVar(value="30")
        tb.Spinbox(form, from_=0, to=365, textvariable=self.terms_var, width=12).grid(row=6, column=1, sticky=W, pady=5, padx=(10, 0))

        # Bank Name & Account
        tb.Label(form, text="Bank Name:", font=("Segoe UI", 9)).grid(row=7, column=0, sticky=W, pady=5)
        self.bank_name_var = tk.StringVar()
        tb.Entry(form, textvariable=self.bank_name_var, width=32).grid(row=7, column=1, sticky=EW, pady=5, padx=(10, 0))

        tb.Label(form, text="Bank Account #:", font=("Segoe UI", 9)).grid(row=8, column=0, sticky=W, pady=5)
        self.bank_acct_var = tk.StringVar()
        tb.Entry(form, textvariable=self.bank_acct_var, width=32).grid(row=8, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Permanent vendor currency
        tb.Label(form, text="Vendor Currency:", font=("Segoe UI", 9)).grid(row=9, column=0, sticky=W, pady=5)
        home = db.get_company_base_currency(self.company_id)
        currencies = [home]
        if db.is_multicurrency_enabled(self.company_id):
            currencies = [row["code"] for row in db.get_currencies(active_only=True)]
        self.currency_var = tk.StringVar(value=home)
        tb.Combobox(form, textvariable=self.currency_var, values=currencies,
                    state="readonly", width=32).grid(row=9, column=1, sticky=EW, pady=5, padx=(10, 0))

        self.is_active_var = tk.BooleanVar(value=True)
        tb.Checkbutton(form, text="Active Supplier", variable=self.is_active_var,
                       bootstyle="round-toggle").grid(row=10, column=1, sticky=W, pady=8, padx=(10, 0))

        tb.Label(form, text="Notes / Memo:", font=("Segoe UI", 9)).grid(row=11, column=0, sticky=NW, pady=5)
        self.notes_entry = tb.Entry(form, width=32)
        self.notes_entry.grid(row=11, column=1, sticky=EW, pady=5, padx=(10, 0))
        form.columnconfigure(1, weight=1)

        # Buttons
        btn_box = tb.Frame(container)
        btn_box.pack(fill=X, pady=(16, 0))

        tb.Button(btn_box, text="Cancel", bootstyle="secondary-outline", command=self.destroy).pack(side=RIGHT, padx=(8, 0))
        save_btn = tb.Button(btn_box, text="Save Supplier", bootstyle="primary", command=self._save)
        save_btn.pack(side=RIGHT)

    def _populate_fields(self):
        if not self.supplier_data:
            return
        self.name_var.set(self.supplier_data.get("name", ""))
        self.contact_var.set(self.supplier_data.get("contact_person", ""))
        self.phone_var.set(self.supplier_data.get("phone", ""))
        self.email_var.set(self.supplier_data.get("email", ""))
        self.address_var.set(self.supplier_data.get("address", ""))
        self.tax_id_var.set(self.supplier_data.get("tax_id", ""))
        self.terms_var.set(str(self.supplier_data.get("payment_terms") or 30))
        self.bank_name_var.set(self.supplier_data.get("bank_name", ""))
        self.bank_acct_var.set(self.supplier_data.get("bank_account", ""))
        self.is_active_var.set(bool(self.supplier_data.get("is_active", 1)))
        self.currency_var.set(self.supplier_data.get("currency") or db.get_company_base_currency(self.company_id))
        if self.supplier_data.get("notes"):
            self.notes_entry.insert(0, self.supplier_data["notes"])

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Supplier Name is required.", parent=self)
            self.name_entry.focus_set()
            return

        try:
            terms = int(self.terms_var.get().strip() or 30)
        except ValueError:
            terms = 30

        payload = {
            "company_id": self.company_id,
            "name": name,
            "contact_person": self.contact_var.get().strip(),
            "phone": self.phone_var.get().strip(),
            "email": self.email_var.get().strip(),
            "address": self.address_var.get().strip(),
            "tax_id": self.tax_id_var.get().strip(),
            "payment_terms": terms,
            "bank_name": self.bank_name_var.get().strip(),
            "bank_account": self.bank_acct_var.get().strip(),
            "notes": self.notes_entry.get().strip(),
            "is_active": 1 if self.is_active_var.get() else 0,
            "currency": self.currency_var.get()
        }

        try:
            if self.is_edit:
                db.update_supplier(self.supplier_data["id"], payload)
            else:
                db.create_supplier(payload)

            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error Saving Supplier", str(e), parent=self)


class SupplierStatementDialog(tb.Toplevel):
    """Modal dialog for viewing supplier statement & accounts payable ledger."""

    def __init__(self, parent, initial_supplier_id=None, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.initial_supplier_id = initial_supplier_id

        self.title("📜 Supplier Statement & AP Ledger")
        self.geometry("940x630")
        self.minsize(800, 500)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._build_ui()
        self._load_suppliers_list()

        if self.initial_supplier_id:
            self._set_supplier_by_id(self.initial_supplier_id)

        self._refresh_statement()
        self.center_window()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F5>", lambda e: self._refresh_statement())
        self.bind("<Control-e>", lambda e: self._export_csv())
        self.bind("<Control-E>", lambda e: self._export_csv())

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

        # ── 1. Top Controls Bar ──
        top_bar = tb.Frame(container, bootstyle="light", padding=10)
        top_bar.pack(fill=X, pady=(0, 10))

        tb.Label(top_bar, text="🏢 Supplier:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 6))

        self.supplier_var = tk.StringVar()
        self.supplier_combo = ttk.Combobox(top_bar, textvariable=self.supplier_var, width=32)
        self.supplier_combo.pack(side=LEFT, padx=(0, 14))
        self.supplier_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_statement())
        self.supplier_combo.bind("<Return>", lambda e: self._refresh_statement())

        tb.Label(top_bar, text="📅 Date Filter:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 6))

        self.date_filter_var = tk.StringVar(value="All Time")
        date_combo = ttk.Combobox(
            top_bar, textvariable=self.date_filter_var,
            values=["All Time", "Today", "Yesterday", "This Week", "This Month", "Last Month", "This Year"],
            width=14, state="readonly"
        )
        date_combo.pack(side=LEFT, padx=(0, 10))
        date_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_statement())

        tb.Button(
            top_bar, text="⟳ Refresh", command=self._refresh_statement, bootstyle="secondary-outline"
        ).pack(side=LEFT)

        tb.Button(
            top_bar, text="📥 Export CSV", command=self._export_csv, bootstyle="success"
        ).pack(side=RIGHT)

        # ── 2. Stat Cards Bar ──
        stats_frame = tb.Frame(container)
        stats_frame.pack(fill=X, pady=(0, 12))

        self.stat_vars = {
            "total_billed": tk.StringVar(value="LKR 0.00"),
            "total_paid": tk.StringVar(value="LKR 0.00"),
            "total_credits": tk.StringVar(value="LKR 0.00"),
            "balance_due": tk.StringVar(value="LKR 0.00"),
            "total_entries": tk.StringVar(value="0"),
        }

        card1 = tb.Labelframe(stats_frame, text="Total Billed", padding=8, bootstyle="info")
        card1.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(card1, textvariable=self.stat_vars["total_billed"], font=("Segoe UI", 12, "bold"), bootstyle="info").pack()

        card2 = tb.Labelframe(stats_frame, text="Total Paid", padding=8, bootstyle="success")
        card2.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(card2, textvariable=self.stat_vars["total_paid"], font=("Segoe UI", 12, "bold"), bootstyle="success").pack()

        card3 = tb.Labelframe(stats_frame, text="Vendor Credits", padding=8, bootstyle="warning")
        card3.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(card3, textvariable=self.stat_vars["total_credits"], font=("Segoe UI", 12, "bold"), bootstyle="warning").pack()

        card4 = tb.Labelframe(stats_frame, text="Balance Due / AP", padding=8, bootstyle="danger")
        card4.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(card4, textvariable=self.stat_vars["balance_due"], font=("Segoe UI", 12, "bold"), bootstyle="danger").pack()

        card5 = tb.Labelframe(stats_frame, text="Entries", padding=8, bootstyle="secondary")
        card5.pack(side=LEFT, fill=X, expand=True)
        tb.Label(card5, textvariable=self.stat_vars["total_entries"], font=("Segoe UI", 12, "bold")).pack()

        # ── 3. Table Frame ──
        table_frame = tb.Frame(container)
        table_frame.pack(fill=BOTH, expand=True, pady=(0, 10))

        columns = ("type", "ref", "date", "description", "billed", "paid", "credits", "balance")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("type", text="Type", anchor=W)
        self.tree.heading("ref", text="Reference", anchor=W)
        self.tree.heading("date", text="Date", anchor=CENTER)
        self.tree.heading("description", text="Description", anchor=W)
        self.tree.heading("billed", text="Billed (LKR)", anchor=E)
        self.tree.heading("paid", text="Paid (LKR)", anchor=E)
        self.tree.heading("credits", text="Credit Note (LKR)", anchor=E)
        self.tree.heading("balance", text="Balance Due (LKR)", anchor=E)

        self.tree.column("type", width=90, anchor=W)
        self.tree.column("ref", width=100, anchor=W)
        self.tree.column("date", width=95, anchor=CENTER)
        self.tree.column("description", width=230, anchor=W)
        self.tree.column("billed", width=110, anchor=E)
        self.tree.column("paid", width=110, anchor=E)
        self.tree.column("credits", width=110, anchor=E)
        self.tree.column("balance", width=120, anchor=E)

        scrollbar = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # ── 4. Bottom Action Bar ──
        bottom_bar = tb.Frame(container)
        bottom_bar.pack(fill=X)

        tb.Button(bottom_bar, text="Close", command=self.destroy, bootstyle="secondary").pack(side=RIGHT)

    def _load_suppliers_list(self):
        suppliers = db.get_suppliers(company_id=self.company_id, active_only=False)
        self.suppliers_map = {f"{s['name']} (ID #{s['id']})": s["id"] for s in suppliers}
        self.supplier_combo["values"] = list(self.suppliers_map.keys())
        if self.suppliers_map and not self.supplier_var.get():
            first_key = list(self.suppliers_map.keys())[0]
            self.supplier_combo.set(first_key)

    def _set_supplier_by_id(self, supplier_id):
        for label, sid in self.suppliers_map.items():
            if sid == supplier_id:
                self.supplier_combo.set(label)
                break

    def _get_selected_supplier_id(self):
        val = self.supplier_var.get()
        return self.suppliers_map.get(val)

    def _refresh_statement(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        sid = self._get_selected_supplier_id()
        if not sid:
            self.stat_vars["total_billed"].set("LKR 0.00")
            self.stat_vars["total_paid"].set("LKR 0.00")
            self.stat_vars["total_credits"].set("LKR 0.00")
            self.stat_vars["balance_due"].set("LKR 0.00")
            self.stat_vars["total_entries"].set("0")
            return

        stmt = db.get_supplier_statement(
            supplier_id=sid,
            company_id=self.company_id,
            date_filter=self.date_filter_var.get()
        )

        self.stat_vars["total_billed"].set(f"LKR {stmt['total_billed']:,.2f}")
        self.stat_vars["total_paid"].set(f"LKR {stmt['total_paid']:,.2f}")
        self.stat_vars["total_credits"].set(f"LKR {stmt['total_credits']:,.2f}")
        self.stat_vars["balance_due"].set(f"LKR {stmt['balance_due']:,.2f}")
        self.stat_vars["total_entries"].set(str(stmt["filtered_entries_count"]))

        for entry in stmt["entries"]:
            self.tree.insert("", END, iid=f"{entry['entry_type']}_{entry['id']}", values=(
                entry["entry_type"],
                entry["ref"],
                entry["date"],
                entry["description"],
                f"{entry['billed']:,.2f}" if entry["billed"] > 0 else "0.00",
                f"{entry['paid']:,.2f}" if entry["paid"] > 0 else "0.00",
                f"{entry['credits']:,.2f}" if entry["credits"] > 0 else "0.00",
                f"{entry['running_balance']:,.2f}",
            ))

        # Auto-select and focus first row
        children = self.tree.get_children()
        if children:
            first = children[0]
            self.tree.selection_set(first)
            self.tree.focus(first)

    def _export_csv(self):
        sid = self._get_selected_supplier_id()
        if not sid:
            messagebox.showwarning("Select Supplier", "Please select a supplier first.", parent=self)
            return

        supp = db.get_supplier_by_id(sid)
        supp_name = supp.get("name", "Supplier") if supp else "Supplier"
        safe_name = "".join(c for c in supp_name if c.isalnum() or c in "_- ").strip().replace(" ", "_")
        default_fn = f"Supplier_Statement_{safe_name}.csv"

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Supplier Statement CSV",
            initialfile=default_fn,
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")]
        )
        if not filepath:
            return

        try:
            db.export_supplier_statement_to_csv(
                supplier_id=sid,
                filepath=filepath,
                company_id=self.company_id,
                date_filter=self.date_filter_var.get()
            )
            messagebox.showinfo("Export Success", f"Supplier Statement exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}", parent=self)


class SupplierManagerDialog(tb.Toplevel):
    """Supplier directory and vendor account management window."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Vendor Centre — Suppliers, Bills, Credits & Payments")
        self.geometry("1060x650")
        self.minsize(880, 520)
        self.transient(parent)

        self.suppliers_cache = []
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
        tb.Label(title_box, text="🏢 Suppliers & Vendors", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        self.subtitle_lbl = tb.Label(
            title_box,
            text=f"Company #{self.company_id} — Accounts Payable Trade Creditors",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        )
        self.subtitle_lbl.pack(anchor=W)

        top_btns = tb.Frame(hdr)
        top_btns.pack(side=RIGHT)

        tb.Button(top_btns, text="Pay Bills", bootstyle="success", command=self._pay_bills).pack(side=LEFT, padx=(0, 8))
        tb.Button(top_btns, text="Vendor Credit", bootstyle="warning-outline", command=self._new_vendor_credit).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_btns,
            text="📄 AP Invoices & Bills",
            bootstyle="info-outline",
            command=self._open_ap_invoices
        ).pack(side=LEFT, padx=(0, 8))

        tb.Button(
            top_btns,
            text="➕ New Supplier",
            bootstyle="success",
            command=self._create_supplier
        ).pack(side=LEFT)

        # Toolbar
        toolbar = tb.Labelframe(root, text="Search & Filter", padding=10)
        toolbar.pack(fill=X, pady=(0, 12))

        tb.Label(toolbar, text="Search:").pack(side=LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        search_entry = tb.Entry(toolbar, textvariable=self.search_var, width=28)
        search_entry.pack(side=LEFT, padx=(0, 14))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        self.active_only_var = tk.BooleanVar(value=False)
        tb.Checkbutton(
            toolbar,
            text="Active Suppliers Only",
            variable=self.active_only_var,
            bootstyle="round-toggle",
            command=self.refresh
        ).pack(side=LEFT, padx=(0, 14))

        tb.Button(toolbar, text="Reset", bootstyle="secondary-outline", command=self._reset_filters).pack(side=LEFT)
        tb.Button(toolbar, text="📥 Export CSV", bootstyle="outline", command=self._export_csv).pack(side=RIGHT)

        # Table
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("name", "contact", "phone", "email", "tax_id", "terms", "invoices", "total_invoiced", "credits", "balance_due", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("name", text="Supplier Name", anchor=W)
        self.tree.heading("contact", text="Contact Person", anchor=W)
        self.tree.heading("phone", text="Phone", anchor=W)
        self.tree.heading("email", text="Email", anchor=W)
        self.tree.heading("tax_id", text="VAT/Tax ID", anchor=W)
        self.tree.heading("terms", text="Terms (Days)", anchor=CENTER)
        self.tree.heading("invoices", text="Bills", anchor=CENTER)
        self.tree.heading("total_invoiced", text="Total Invoiced (LKR)", anchor=E)
        self.tree.heading("credits", text="Credits (LKR)", anchor=E)
        self.tree.heading("balance_due", text="Balance Due (LKR)", anchor=E)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("name", width=180, anchor=W)
        self.tree.column("contact", width=130, anchor=W)
        self.tree.column("phone", width=110, anchor=W)
        self.tree.column("email", width=130, anchor=W)
        self.tree.column("tax_id", width=100, anchor=W)
        self.tree.column("terms", width=80, anchor=CENTER)
        self.tree.column("invoices", width=60, anchor=CENTER)
        self.tree.column("total_invoiced", width=130, anchor=E)
        self.tree.column("credits", width=105, anchor=E)
        self.tree.column("balance_due", width=130, anchor=E)
        self.tree.column("status", width=70, anchor=CENTER)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_selected_supplier())

        # Footer Actions
        bottom_bar = tb.Frame(root, padding=(0, 10, 0, 0))
        bottom_bar.pack(fill=X)

        tb.Button(bottom_bar, text="✏️ Edit Supplier", bootstyle="primary-outline", command=self._edit_selected_supplier).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="Merge Vendor", bootstyle="danger-outline", command=self._merge_supplier).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="🔄 Toggle Active", bootstyle="secondary-outline", command=self._toggle_active).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="🗑️ Delete Supplier", bootstyle="danger-outline", command=self._delete_supplier).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="📄 View Supplier Invoices", bootstyle="info-outline", command=self._view_supplier_invoices).pack(side=LEFT, padx=(0, 8))
        tb.Button(bottom_bar, text="📜 Supplier Statement", bootstyle="info", command=self._view_supplier_statement).pack(side=LEFT)

        tb.Button(bottom_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _reset_filters(self):
        self.search_var.set("")
        self.active_only_var.set(False)
        self.refresh()

    def refresh(self):
        search_q = self.search_var.get().strip() or None
        active_only = self.active_only_var.get()

        suppliers = db.get_suppliers(
            company_id=self.company_id,
            active_only=active_only,
            search=search_q
        )
        self.suppliers_cache = suppliers

        for r in self.tree.get_children():
            self.tree.delete(r)

        tot_invoiced = 0.0
        tot_balance = 0.0

        for s in suppliers:
            inv_amt = float(s.get("total_invoiced") or 0.0)
            bal_amt = float(s.get("balance_due") or 0.0)
            credit_amt = float(s.get("available_credit") or 0.0)
            tot_invoiced += inv_amt
            tot_balance += bal_amt

            inv_str = f"{inv_amt:,.2f}" if inv_amt > 0 else "—"
            bal_str = f"{bal_amt:,.2f}" if bal_amt > 0 else "—"
            status_str = "Active" if s["is_active"] else "Inactive"

            self.tree.insert(
                "",
                END,
                iid=str(s["id"]),
                values=(
                    s["name"],
                    s.get("contact_person") or "—",
                    s.get("phone") or "—",
                    s.get("email") or "—",
                    s.get("tax_id") or "—",
                    f"{s.get('payment_terms') or 30}d",
                    str(s.get("invoice_count") or 0),
                    inv_str,
                    f"{credit_amt:,.2f}" if credit_amt > 0 else "—",
                    bal_str,
                    status_str
                )
            )

        self.subtitle_lbl.config(
            text=f"{len(suppliers)} supplier(s) | Total Outstanding AP: LKR {tot_balance:,.2f}"
        )

    def _get_selected_supplier(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a supplier from the list.", parent=self)
            return None
        sid = int(sel[0])
        return next((s for s in self.suppliers_cache if s["id"] == sid), None)

    def _create_supplier(self):
        SupplierEditModal(self, company_id=self.company_id, on_saved=self.refresh)

    def _edit_selected_supplier(self):
        s = self._get_selected_supplier()
        if not s:
            return
        SupplierEditModal(self, company_id=self.company_id, supplier_data=s, on_saved=self.refresh)

    def _merge_supplier(self):
        source = self._get_selected_supplier()
        if not source:
            return
        candidates = [
            row for row in db.get_suppliers(
                company_id=self.company_id, active_only=False
            )
            if row["id"] != source["id"]
            and (row.get("currency") or "").upper()
            == (source.get("currency") or "").upper()
        ]
        if not candidates:
            messagebox.showinfo(
                "Merge vendor",
                "No compatible vendor is available to keep. Vendors must use "
                "the same currency.",
                parent=self,
            )
            return
        target_id = choose_merge_target(self, "vendor", source, candidates)
        if target_id is None:
            return
        try:
            db.merge_suppliers(source["id"], target_id)
            self.refresh()
            if self.tree.exists(str(target_id)):
                self.tree.selection_set(str(target_id))
                self.tree.focus(str(target_id))
            messagebox.showinfo(
                "Vendor merged",
                "Bills, credits, purchase orders, and payment history now "
                "belong to the retained vendor.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Merge vendor", str(exc), parent=self)

    def _toggle_active(self):
        s = self._get_selected_supplier()
        if not s:
            return
        new_active = 0 if s["is_active"] else 1
        try:
            db.update_supplier(s["id"], {**s, "is_active": new_active})
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _delete_supplier(self):
        s = self._get_selected_supplier()
        if not s:
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete supplier '{s['name']}'?\n"
            "This action cannot be undone.",
            parent=self
        )
        if not confirm:
            return

        success, msg = db.delete_supplier(s["id"])
        if success:
            messagebox.showinfo("Deleted", msg, parent=self)
            self.refresh()
        else:
            messagebox.showerror("Cannot Delete", msg, parent=self)

    def _view_supplier_invoices(self):
        s = self._get_selected_supplier()
        if not s:
            return
        from ui.ap_invoice_dialog import APInvoiceListDialog
        APInvoiceListDialog(self, company_id=self.company_id, initial_supplier_id=s["id"])

    def _view_supplier_statement(self):
        s = self._get_selected_supplier() if self.tree.selection() else None
        SupplierStatementDialog(self, initial_supplier_id=s["id"] if s else None, company_id=self.company_id)

    def _pay_bills(self):
        from ui.pay_bills_dialog import PayBillsDialog
        selected = self._get_selected_supplier() if self.tree.selection() else None
        PayBillsDialog(self, self.company_id, selected["id"] if selected else None, self.refresh)

    def _new_vendor_credit(self):
        from ui.pay_bills_dialog import VendorCreditDialog
        selected = self._get_selected_supplier() if self.tree.selection() else None
        VendorCreditDialog(self, self.company_id, selected["id"] if selected else None, self.refresh)
    def _open_ap_invoices(self):
        from ui.ap_invoice_dialog import APInvoiceListDialog
        APInvoiceListDialog(self, company_id=self.company_id)

    def _export_csv(self):
        if not self.suppliers_cache:
            messagebox.showinfo("Export", "No suppliers to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Supplier Directory",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"suppliers_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Supplier Name", "Contact Person", "Phone", "Email", "Address",
                    "VAT/Tax Reg #", "Payment Terms (Days)", "Bank Name", "Bank Account",
                    "Total Invoiced (LKR)", "Balance Due (LKR)", "Status", "Notes"
                ])
                for s in self.suppliers_cache:
                    # Security: Sanitize user-supplied string inputs against CSV Formula Injection / DDE Injection (CWE-1236)
                    writer.writerow(db._sanitize_csv_row([
                        s["name"],
                        s.get("contact_person") or "",
                        s.get("phone") or "",
                        s.get("email") or "",
                        s.get("address") or "",
                        s.get("tax_id") or "",
                        s.get("payment_terms") or 30,
                        s.get("bank_name") or "",
                        s.get("bank_account") or "",
                        f"{float(s.get('total_invoiced') or 0.0):.2f}",
                        f"{float(s.get('balance_due') or 0.0):.2f}",
                        "Active" if s["is_active"] else "Inactive",
                        s.get("notes") or ""
                    ]))
            messagebox.showinfo("Export Successful", f"Suppliers exported successfully to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)
