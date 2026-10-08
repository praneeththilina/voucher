"""
ui/customer_manager.py
Customer Directory & Accounts Receivable (AR) Management for Voucher Machine SME Bookkeeping v3.8.

Provides:
- CustomerManagerDialog: Complete Customer Directory with balance tracking,
  credit limits, search, contact details, invoice linking, and CSV export.
- CustomerEditModal: Modal form for creating and editing customer profiles.
"""

import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db


class CustomerEditModal(tb.Toplevel):
    """Modal for creating or editing a customer profile."""

    def __init__(self, parent, company_id=None, customer_data=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.customer_data = customer_data or {}
        self.on_saved = on_saved
        self.is_edit = bool(self.customer_data.get("id"))

        self.title("Edit Customer" if self.is_edit else "Add New Customer")
        self.geometry("600x680")
        self.minsize(520, 560)
        self.resizable(True, True)
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

        # Keep the primary actions pinned to the bottom. Packing this before
        # the expanding form keeps Create/Save visible under Windows DPI scaling.
        btn_bar = tb.Frame(container)
        btn_bar.pack(side=BOTTOM, fill=X, pady=(15, 0))

        tb.Button(
            btn_bar,
            text="Cancel",
            bootstyle="secondary-outline",
            command=self.destroy,
        ).pack(side=RIGHT, padx=(6, 0))
        save_lbl = "Save Changes" if self.is_edit else "Create Customer"
        tb.Button(
            btn_bar,
            text=save_lbl,
            bootstyle="primary",
            command=self._on_save,
        ).pack(side=RIGHT)

        header_title = "Edit Customer Profile" if self.is_edit else "Register New Customer"
        header_desc = "Record customer contact info, credit limits, payment terms, and billing details."
        tb.Label(container, text=header_title, font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 2))
        tb.Label(container, text=header_desc, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 14))

        form = tb.Frame(container)
        form.pack(fill=BOTH, expand=True)

        # Customer Name
        tb.Label(form, text="Customer Name *:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky=W, pady=5)
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
        tb.Label(form, text="Billing Address:", font=("Segoe UI", 9)).grid(row=4, column=0, sticky=W, pady=5)
        self.address_var = tk.StringVar()
        tb.Entry(form, textvariable=self.address_var, width=32).grid(row=4, column=1, sticky=EW, pady=5, padx=(10, 0))

        # VAT / Tax ID
        tb.Label(form, text="VAT / Tax Reg #:", font=("Segoe UI", 9)).grid(row=5, column=0, sticky=W, pady=5)
        self.tax_id_var = tk.StringVar()
        tb.Entry(form, textvariable=self.tax_id_var, width=32).grid(row=5, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Credit Limit (LKR)
        tb.Label(form, text="Credit Limit (LKR):", font=("Segoe UI", 9)).grid(row=6, column=0, sticky=W, pady=5)
        self.credit_limit_var = tk.StringVar(value="0.00")
        tb.Entry(form, textvariable=self.credit_limit_var, width=18).grid(row=6, column=1, sticky=W, pady=5, padx=(10, 0))

        # Payment Terms (Days)
        tb.Label(form, text="Payment Terms (Days):", font=("Segoe UI", 9)).grid(row=7, column=0, sticky=W, pady=5)
        self.terms_var = tk.StringVar(value="30")
        tb.Spinbox(form, from_=0, to=365, textvariable=self.terms_var, width=12).grid(row=7, column=1, sticky=W, pady=5, padx=(10, 0))

        # Bank Name & Account
        tb.Label(form, text="Bank Name:", font=("Segoe UI", 9)).grid(row=8, column=0, sticky=W, pady=5)
        self.bank_name_var = tk.StringVar()
        tb.Entry(form, textvariable=self.bank_name_var, width=32).grid(row=8, column=1, sticky=EW, pady=5, padx=(10, 0))

        tb.Label(form, text="Bank Account #:", font=("Segoe UI", 9)).grid(row=9, column=0, sticky=W, pady=5)
        self.bank_acct_var = tk.StringVar()
        tb.Entry(form, textvariable=self.bank_acct_var, width=32).grid(row=9, column=1, sticky=EW, pady=5, padx=(10, 0))

        # Permanent customer currency
        tb.Label(form, text="Customer Currency:", font=("Segoe UI", 9)).grid(row=10, column=0, sticky=W, pady=5)
        home = db.get_company_base_currency(self.company_id)
        currencies = [home]
        if db.is_multicurrency_enabled(self.company_id):
            currencies = [row["code"] for row in db.get_currencies(active_only=True)]
        self.currency_var = tk.StringVar(value=home)
        tb.Combobox(form, textvariable=self.currency_var, values=currencies,
                    state="readonly", width=32).grid(row=10, column=1, sticky=EW, pady=5, padx=(10, 0))

        tb.Label(form, text="Internal Notes:", font=("Segoe UI", 9)).grid(row=11, column=0, sticky=W, pady=5)
        self.notes_var = tk.StringVar()
        tb.Entry(form, textvariable=self.notes_var, width=32).grid(row=11, column=1, sticky=EW, pady=5, padx=(10, 0))

        self.active_var = tk.BooleanVar(value=True)
        tb.Checkbutton(form, text="Customer is Active", variable=self.active_var,
                       bootstyle="round-toggle").grid(row=12, column=1, sticky=W, pady=(8, 0), padx=(10, 0))
        form.columnconfigure(1, weight=1)


    def _populate_fields(self):
        if not self.customer_data:
            return
        d = self.customer_data
        self.name_var.set(d.get("name", ""))
        self.contact_var.set(d.get("contact_person", ""))
        self.phone_var.set(d.get("phone", ""))
        self.email_var.set(d.get("email", ""))
        self.address_var.set(d.get("address", ""))
        self.tax_id_var.set(d.get("tax_id", ""))
        self.credit_limit_var.set(f"{float(d.get('credit_limit') or 0.0):,.2f}".replace(",", ""))
        self.terms_var.set(str(d.get("payment_terms", 30)))
        self.bank_name_var.set(d.get("bank_name", ""))
        self.bank_acct_var.set(d.get("bank_account", ""))
        self.notes_var.set(d.get("notes", ""))
        self.active_var.set(bool(d.get("is_active", 1)))
        self.currency_var.set(d.get("currency") or db.get_company_base_currency(self.company_id))

    def _on_save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Customer name is required.", parent=self)
            self.name_entry.focus_set()
            return

        try:
            terms = int(self.terms_var.get().strip())
        except ValueError:
            terms = 30

        try:
            credit_lim = float(self.credit_limit_var.get().replace(",", "").strip() or 0.0)
        except ValueError:
            credit_lim = 0.0

        payload = {
            "company_id": self.company_id,
            "name": name,
            "contact_person": self.contact_var.get().strip(),
            "phone": self.phone_var.get().strip(),
            "email": self.email_var.get().strip(),
            "address": self.address_var.get().strip(),
            "tax_id": self.tax_id_var.get().strip(),
            "credit_limit": credit_lim,
            "payment_terms": terms,
            "bank_name": self.bank_name_var.get().strip(),
            "bank_account": self.bank_acct_var.get().strip(),
            "notes": self.notes_var.get().strip(),
            "is_active": 1 if self.active_var.get() else 0,
            "currency": self.currency_var.get()
        }

        try:
            if self.is_edit:
                db.update_customer(self.customer_data["id"], payload)
                saved_id = self.customer_data["id"]
            else:
                saved_id = db.create_customer(payload)

            if self.on_saved:
                self.on_saved(saved_id)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save customer: {e}", parent=self)


class CustomerManagerDialog(tb.Toplevel):
    """
    Main Customer Directory Dialog.
    Allows viewing all customers, searching, viewing balances & credit limits,
    adding/editing profiles, and launching customer invoices.
    """

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        comp = db.get_company(self.company_id)
        comp_name = comp.get("name", "Company") if comp else "Company"

        self.title(f"Customer Directory & AR — {comp_name}")
        self.geometry("1100x640")
        self.minsize(900, 500)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_customers()
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
        header.pack(fill=X, pady=(0, 12))

        title_box = tb.Frame(header)
        title_box.pack(side=LEFT)
        tb.Label(title_box, text="👥 Customer Directory & Accounts Receivable", font=("Segoe UI", 15, "bold")).pack(anchor=W)
        tb.Label(title_box, text="Manage customer billing profiles, track receivables, and enforce credit terms.", font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)

        # KPI Summary Cards Bar
        self.kpi_frame = tb.Frame(container)
        self.kpi_frame.pack(fill=X, pady=(0, 14))

        self.card_total_cust = self._create_kpi_card(self.kpi_frame, "Total Customers", "0", "primary")
        self.card_total_cust.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))

        self.card_invoiced = self._create_kpi_card(self.kpi_frame, "Total Invoiced", "LKR 0.00", "info")
        self.card_invoiced.pack(side=LEFT, fill=X, expand=True, padx=6)

        self.card_received = self._create_kpi_card(self.kpi_frame, "Total Received", "LKR 0.00", "success")
        self.card_received.pack(side=LEFT, fill=X, expand=True, padx=6)

        self.card_balance = self._create_kpi_card(self.kpi_frame, "Total Outstanding (AR)", "LKR 0.00", "warning")
        self.card_balance.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))

        # Search & Filter Toolbar
        toolbar = tb.Frame(container)
        toolbar.pack(fill=X, pady=(0, 10))

        tb.Label(toolbar, text="Search:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._load_customers())
        search_entry = tb.Entry(toolbar, textvariable=self.search_var, width=28)
        search_entry.pack(side=LEFT, padx=(0, 15))

        self.active_only_var = tk.BooleanVar(value=False)
        tb.Checkbutton(toolbar, text="Active Only", variable=self.active_only_var, command=self._load_customers, bootstyle="round-toggle").pack(side=LEFT, padx=(0, 15))

        # Right Toolbar Actions
        tb.Button(toolbar, text="📊 Export CSV", bootstyle="secondary-outline", command=self._export_csv).pack(side=RIGHT, padx=(6, 0))
        tb.Button(toolbar, text="➕ New Customer", bootstyle="success", command=self._add_customer).pack(side=RIGHT)

        # Treeview Table
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ("id", "name", "contact", "phone", "email", "terms", "credit_limit", "invoiced", "received", "balance", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("id", text="#", anchor=W)
        self.tree.heading("name", text="Customer Name", anchor=W)
        self.tree.heading("contact", text="Contact Person", anchor=W)
        self.tree.heading("phone", text="Phone", anchor=W)
        self.tree.heading("email", text="Email", anchor=W)
        self.tree.heading("terms", text="Terms", anchor=CENTER)
        self.tree.heading("credit_limit", text="Credit Limit", anchor=E)
        self.tree.heading("invoiced", text="Total Invoiced", anchor=E)
        self.tree.heading("received", text="Total Received", anchor=E)
        self.tree.heading("balance", text="Balance Due", anchor=E)
        self.tree.heading("status", text="Status", anchor=CENTER)

        self.tree.column("id", width=40, stretch=False)
        self.tree.column("name", width=180)
        self.tree.column("contact", width=120)
        self.tree.column("phone", width=110)
        self.tree.column("email", width=130)
        self.tree.column("terms", width=70, stretch=False, anchor=CENTER)
        self.tree.column("credit_limit", width=105, anchor=E)
        self.tree.column("invoiced", width=110, anchor=E)
        self.tree.column("received", width=110, anchor=E)
        self.tree.column("balance", width=110, anchor=E)
        self.tree.column("status", width=75, stretch=False, anchor=CENTER)

        vsb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        hsb = tb.Scrollbar(tree_frame, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=NSEW)
        vsb.grid(row=0, column=1, sticky=NS)
        hsb.grid(row=1, column=0, sticky=EW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", lambda e: self._edit_customer())

        # Bottom Action Bar
        bottom_bar = tb.Frame(container)
        bottom_bar.pack(fill=X, pady=(12, 0))

        tb.Button(bottom_bar, text="✏️ Edit Customer", bootstyle="primary-outline", command=self._edit_customer).pack(side=LEFT, padx=(0, 6))
        tb.Button(bottom_bar, text="🧾 View Customer Invoices", bootstyle="info-outline", command=self._view_customer_invoices).pack(side=LEFT, padx=(0, 6))
        tb.Button(bottom_bar, text="❌ Delete / Deactivate", bootstyle="danger-outline", command=self._delete_customer).pack(side=LEFT)

        tb.Button(bottom_bar, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _create_kpi_card(self, parent, title, value, bootstyle):
        card = tb.Frame(parent, bootstyle=bootstyle, padding=10)
        tb.Label(card, text=title, font=("Segoe UI", 8, "bold"), bootstyle=f"{bootstyle}-inverse").pack(anchor=W)
        lbl_val = tb.Label(card, text=value, font=("Segoe UI", 12, "bold"), bootstyle=f"{bootstyle}-inverse")
        lbl_val.pack(anchor=W, pady=(2, 0))
        card.value_label = lbl_val
        return card

    def _load_customers(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        search_query = self.search_var.get().strip() or None
        active_only = self.active_only_var.get()

        customers = db.get_customers(
            company_id=self.company_id,
            active_only=active_only,
            search=search_query
        )

        tot_invoiced = 0.0
        tot_received = 0.0
        tot_balance = 0.0

        for c in customers:
            inv_amt = float(c.get("total_invoiced") or 0.0)
            rec_amt = float(c.get("total_paid") or 0.0)
            bal_amt = float(c.get("balance_due") or 0.0)
            lim_amt = float(c.get("credit_limit") or 0.0)

            tot_invoiced += inv_amt
            tot_received += rec_amt
            tot_balance += bal_amt

            status_str = "Active" if c.get("is_active") else "Inactive"
            terms_str = f"Net {c.get('payment_terms', 30)}d"
            lim_str = f"{lim_amt:,.2f}" if lim_amt > 0 else "—"

            self.tree.insert("", END, values=(
                c["id"],
                c["name"],
                c.get("contact_person", "") or "—",
                c.get("phone", "") or "—",
                c.get("email", "") or "—",
                terms_str,
                lim_str,
                f"{inv_amt:,.2f}",
                f"{rec_amt:,.2f}",
                f"{bal_amt:,.2f}",
                status_str
            ))

        # Update KPI cards
        self.card_total_cust.value_label.config(text=str(len(customers)))
        self.card_invoiced.value_label.config(text=f"LKR {tot_invoiced:,.2f}")
        self.card_received.value_label.config(text=f"LKR {tot_received:,.2f}")
        self.card_balance.value_label.config(text=f"LKR {tot_balance:,.2f}")

    def _get_selected_customer_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a customer from the table.", parent=self)
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def _add_customer(self):
        CustomerEditModal(self, company_id=self.company_id, on_saved=lambda cid: self._load_customers())

    def _edit_customer(self):
        cid = self._get_selected_customer_id()
        if not cid:
            return
        c_data = db.get_customer_by_id(cid)
        if not c_data:
            messagebox.showerror("Error", "Customer not found.", parent=self)
            return
        CustomerEditModal(self, company_id=self.company_id, customer_data=c_data, on_saved=lambda cid: self._load_customers())

    def _delete_customer(self):
        cid = self._get_selected_customer_id()
        if not cid:
            return
        c_data = db.get_customer_by_id(cid)
        if not c_data:
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete customer '{c_data['name']}'?\n"
            "If the customer has invoices on record, they will be protected from deletion.",
            parent=self
        )
        if not confirm:
            return

        ok, msg = db.delete_customer(cid)
        if ok:
            messagebox.showinfo("Deleted", msg, parent=self)
            self._load_customers()
        else:
            # Prompt deactivation if deletion was blocked
            deact = messagebox.askyesno("Delete Blocked", f"{msg}\n\nWould you like to deactivate this customer instead?", parent=self)
            if deact:
                c_data["is_active"] = 0
                db.update_customer(cid, c_data)
                self._load_customers()

    def _view_customer_invoices(self):
        cid = self._get_selected_customer_id()
        if not cid:
            return
        try:
            from ui.ar_invoice_dialog import ARInvoiceListDialog
            ARInvoiceListDialog(self, company_id=self.company_id, customer_id_filter=cid)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open AR invoices: {e}", parent=self)

    def _export_csv(self):
        customers = db.get_customers(company_id=self.company_id, active_only=False)
        if not customers:
            messagebox.showinfo("Export", "No customers to export.", parent=self)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Customers to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")]
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Customer Name", "Contact Person", "Phone", "Email", "Address", "VAT / Tax ID", "Credit Limit", "Payment Terms", "Bank Name", "Bank Account", "Total Invoiced", "Total Received", "Balance Due", "Status"])
                for c in customers:
                    # Security: Sanitize user-supplied string inputs against CSV Formula Injection / DDE Injection (CWE-1236)
                    writer.writerow(db._sanitize_csv_row([
                        c["id"], c["name"], c.get("contact_person", ""),
                        c.get("phone", ""), c.get("email", ""), c.get("address", ""),
                        c.get("tax_id", ""), c.get("credit_limit", 0.0), c.get("payment_terms", 30),
                        c.get("bank_name", ""), c.get("bank_account", ""),
                        c.get("total_invoiced", 0.0), c.get("total_paid", 0.0),
                        c.get("balance_due", 0.0),
                        "Active" if c.get("is_active") else "Inactive"
                    ]))
            messagebox.showinfo("Export Success", f"Successfully exported {len(customers)} customers to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}", parent=self)
