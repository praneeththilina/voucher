"""Full-window Vendor Centre and Enter Bills workspaces."""

from __future__ import annotations

import csv
import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import vendor_payments as vp
from ui.ap_invoice_dialog import APInvoiceEntryDialog, APAgingDialog
from ui.merge_dialog import choose_merge_target
from ui.pay_bills_dialog import PayBillsDialog, VendorCreditDialog
from ui.supplier_manager import SupplierEditModal


class APBillEntryFrame(tb.Frame):
    """Full-page supplier-bill editor using the established AP posting logic."""

    def __init__(
        self, parent, company_id=None, invoice_id=None, supplier_id=None,
        on_saved=None, on_cancel=None, on_supplier_changed=None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.invoice_id = invoice_id
        self.is_edit = bool(invoice_id)
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.on_supplier_changed = on_supplier_changed
        self.home_currency = db.get_company_base_currency(self.company_id).upper()
        self.currency_values = [self.home_currency]
        if db.is_multicurrency_enabled(self.company_id):
            self.currency_values = [
                row["code"] for row in db.get_currencies(active_only=True)
            ]
        self.suppliers = db.get_suppliers(self.company_id, active_only=True)
        self.supplier_lookup = {row["name"]: row for row in self.suppliers}
        self.coa_accounts = db.get_chart_of_accounts(
            self.company_id, account_type="Expense", active_only=True
        )
        self.coa_lookup = {
            f"{row['account_code']} - {row['account_name']}": row
            for row in self.coa_accounts
        }
        self.lines_data = []
        APInvoiceEntryDialog._build_ui(self)
        self._wire_embedded_actions()
        if self.is_edit:
            self._load_invoice_data()
        else:
            self._init_defaults()
            selected = next(
                (row for row in self.suppliers if row["id"] == supplier_id), None
            )
            if selected:
                self.supplier_var.set(selected["name"])
                self._on_supplier_selected()

    def _walk(self, parent):
        widgets = [parent]
        for child in parent.winfo_children():
            widgets.extend(self._walk(child))
        return widgets

    def _wire_embedded_actions(self):
        for widget in self._walk(self):
            if isinstance(widget, tb.Button) and widget.cget("text") == "Cancel":
                widget.configure(
                    text="Back to Vendor Centre", command=self._cancel
                )
            widget.bind(
                "<Control-s>", lambda _event: self._save_invoice(), add="+"
            )

    def _cancel(self):
        if self.on_cancel:
            self.on_cancel()

    def _quick_add_supplier(self):
        def saved():
            self.suppliers = db.get_suppliers(self.company_id, active_only=True)
            self.supplier_lookup = {row["name"]: row for row in self.suppliers}
            self.sup_combo["values"] = list(self.supplier_lookup)
            if self.on_supplier_changed:
                self.on_supplier_changed()

        SupplierEditModal(self, self.company_id, on_saved=saved)

    def _save_invoice(self):
        supplier = self.supplier_lookup.get(self.supplier_var.get().strip())
        if not supplier:
            messagebox.showwarning(
                "Validation", "Select a valid vendor.", parent=self
            )
            return
        number = self.inv_num_var.get().strip()
        if not number:
            messagebox.showwarning(
                "Validation", "Vendor bill number is required.", parent=self
            )
            return
        try:
            datetime.strptime(self.inv_date_var.get().strip(), "%Y-%m-%d")
            datetime.strptime(self.due_date_var.get().strip(), "%Y-%m-%d")
            discount = float(
                self.discount_var.get().strip().replace(",", "") or 0
            )
        except ValueError:
            messagebox.showwarning(
                "Validation",
                "Dates must use YYYY-MM-DD and discount must be numeric.",
                parent=self,
            )
            return
        if not self.lines_data:
            messagebox.showwarning(
                "Validation", "Add at least one bill line.", parent=self
            )
            return
        payload = {
            "company_id": self.company_id,
            "supplier_id": supplier["id"],
            "invoice_number": number,
            "internal_ref": self.ref_var.get().strip(),
            "invoice_date": self.inv_date_var.get().strip(),
            "due_date": self.due_date_var.get().strip(),
            "discount_amount": discount,
            "currency": self.curr_var.get(),
            "exchange_rate": self.rate_var.get(),
            "notes": self.notes_entry.get().strip(),
        }
        try:
            if self.is_edit:
                db.update_ap_invoice(self.invoice_id, payload, self.lines_data)
                bill_id = self.invoice_id
            else:
                bill_id = db.create_ap_invoice(payload, self.lines_data)
            if self.on_saved:
                self.on_saved(bill_id, supplier["id"])
        except Exception as exc:
            messagebox.showerror("Error Saving Bill", str(exc), parent=self)


for _name in (
    "_currency_changed", "_init_defaults", "_on_supplier_selected",
    "_recalc_due_date", "_load_invoice_data", "_add_line", "_remove_line",
    "_refresh_lines_table", "_recalculate_totals",
):
    setattr(APBillEntryFrame, _name, APInvoiceEntryDialog.__dict__[_name])


class APVendorCentreFrame(tb.Frame):
    """Vendor-focused transaction centre with the vendor list on the right."""

    def __init__(
        self, parent, company_id=None, supplier_id=None,
        open_bill_callback=None, on_close=None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.home_currency = db.get_company_base_currency(self.company_id).upper()
        self.selected_supplier_id = supplier_id
        self.open_bill_callback = open_bill_callback
        self.on_close = on_close
        self.suppliers = []
        self.transaction_rows = []
        self._build_ui()
        self.refresh(supplier_id)

    def _build_ui(self):
        root = tb.Frame(self, padding=14)
        root.pack(fill=BOTH, expand=True)
        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 10))
        titles = tb.Frame(header)
        titles.pack(side=LEFT)
        tb.Label(
            titles, text="Vendor Centre", font=("Segoe UI", 18, "bold")
        ).pack(anchor=W)
        tb.Label(
            titles,
            text="Vendor activity, bills, credits, payments and purchase orders.",
            bootstyle="secondary",
        ).pack(anchor=W)
        actions = tb.Frame(header)
        actions.pack(side=RIGHT)
        for text, style, command in (
            ("A/P Aging", "info-outline", self._aging),
            ("Purchase Order", "info-outline", self._purchase_order),
            ("Vendor Credit", "warning-outline", self._vendor_credit),
            ("Pay Bills", "success", self._pay_bills),
            ("Enter Bill", "primary", self._new_bill),
        ):
            tb.Button(
                actions, text=text, bootstyle=style, command=command
            ).pack(side=LEFT, padx=(6, 0))

        panes = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        panes.pack(fill=BOTH, expand=True)
        activity = tb.Frame(panes, padding=(0, 0, 10, 0))
        vendors = tb.Frame(panes, padding=(10, 0, 0, 0))
        panes.add(activity, weight=4)
        panes.add(vendors, weight=1)
        self._build_activity(activity)
        self._build_vendors(vendors)

    def _build_vendors(self, parent):
        heading = tb.Frame(parent)
        heading.pack(fill=X, pady=(0, 6))
        tb.Label(
            heading, text="Vendors", font=("Segoe UI", 12, "bold")
        ).pack(side=LEFT)
        tb.Button(
            heading, text="+ New", bootstyle="success-outline",
            command=self._new_vendor,
        ).pack(side=RIGHT)
        self.vendor_search = tk.StringVar()
        search = tb.Entry(parent, textvariable=self.vendor_search)
        search.pack(fill=X, pady=(0, 6))
        search.bind("<KeyRelease>", lambda _event: self._load_vendors())
        frame = tb.Frame(parent)
        frame.pack(fill=BOTH, expand=True)
        self.vendor_tree = ttk.Treeview(
            frame, columns=("name", "balance"), show="headings",
            selectmode="browse",
        )
        self.vendor_tree.heading("name", text="Vendor", anchor=W)
        self.vendor_tree.heading(
            "balance", text=f"Open ({self.home_currency})", anchor=E
        )
        self.vendor_tree.column("name", width=175, anchor=W)
        self.vendor_tree.column("balance", width=105, anchor=E)
        scroll = tb.Scrollbar(
            frame, orient=VERTICAL, command=self.vendor_tree.yview
        )
        self.vendor_tree.configure(yscrollcommand=scroll.set)
        self.vendor_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.vendor_tree.bind("<<TreeviewSelect>>", self._vendor_selected)
        self.vendor_tree.bind(
            "<Double-1>", lambda _event: self._edit_vendor()
        )
        buttons = tb.Frame(parent)
        buttons.pack(fill=X, pady=(6, 0))
        tb.Button(
            buttons, text="Edit", bootstyle="primary-outline",
            command=self._edit_vendor,
        ).pack(side=LEFT)
        tb.Button(
            buttons, text="Merge", bootstyle="danger-outline",
            command=self._merge_vendor,
        ).pack(side=LEFT, padx=5)
        tb.Button(
            buttons, text="Export", bootstyle="secondary-outline",
            command=self._export,
        ).pack(side=RIGHT)

    def _build_activity(self, parent):
        self.vendor_name = tb.Label(
            parent, text="Select a vendor", font=("Segoe UI", 15, "bold")
        )
        self.vendor_name.pack(anchor=W)
        self.vendor_details = tb.Label(
            parent, text="", bootstyle="secondary"
        )
        self.vendor_details.pack(anchor=W, pady=(0, 8))
        cards = tb.Frame(parent)
        cards.pack(fill=X, pady=(0, 10))
        self.open_value = self._card(cards, "Open bills", "danger")
        self.overdue_value = self._card(cards, "Overdue", "warning")
        self.credit_value = self._card(cards, "Available credit", "info")
        self.paid_value = self._card(cards, "Paid last 30 days", "success")
        self.po_value = self._card(cards, "Open POs", "primary")

        filters = tb.Frame(parent)
        filters.pack(fill=X, pady=(0, 7))
        self.type_var = tk.StringVar(value="All transactions")
        type_box = tb.Combobox(
            filters, textvariable=self.type_var,
            values=(
                "All transactions", "Bills", "Payments",
                "Vendor credits", "Purchase orders",
            ),
            state="readonly", width=18,
        )
        type_box.pack(side=LEFT)
        type_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._load_transactions()
        )
        self.status_var = tk.StringVar(value="All statuses")
        status_box = tb.Combobox(
            filters, textvariable=self.status_var,
            values=("All statuses", "Open", "Overdue", "Paid", "Cancelled"),
            state="readonly", width=14,
        )
        status_box.pack(side=LEFT, padx=6)
        status_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._load_transactions()
        )
        self.period_var = tk.StringVar(value="All dates")
        period_box = tb.Combobox(
            filters, textvariable=self.period_var,
            values=("All dates", "This month", "This year", "Last year"),
            state="readonly", width=13,
        )
        period_box.pack(side=LEFT)
        period_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._load_transactions()
        )
        self.find_var = tk.StringVar()
        find = tb.Entry(filters, textvariable=self.find_var, width=22)
        find.pack(side=RIGHT)
        find.bind("<KeyRelease>", lambda _event: self._load_transactions())
        tb.Label(filters, text="Find:").pack(side=RIGHT, padx=(0, 4))

        frame = tb.Frame(parent)
        frame.pack(fill=BOTH, expand=True)
        columns = (
            "date", "type", "number", "memo", "amount", "open", "status"
        )
        self.transaction_tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="browse"
        )
        labels = (
            "Date", "Type", "No. / Ref", "Memo", "Amount",
            "Open balance", "Status",
        )
        widths = (90, 110, 125, 235, 115, 115, 95)
        for column, label, width in zip(columns, labels, widths):
            anchor = E if column in {"amount", "open"} else W
            self.transaction_tree.heading(column, text=label, anchor=anchor)
            self.transaction_tree.column(column, width=width, anchor=anchor)
        scroll = tb.Scrollbar(
            frame, orient=VERTICAL, command=self.transaction_tree.yview
        )
        self.transaction_tree.configure(yscrollcommand=scroll.set)
        self.transaction_tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.transaction_tree.bind(
            "<Double-1>", lambda _event: self._open_transaction()
        )

    @staticmethod
    def _card(parent, title, style):
        box = tb.Labelframe(
            parent, text=title, padding=8, bootstyle=style
        )
        box.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        value = tb.Label(box, text="0.00", font=("Segoe UI", 11, "bold"))
        value.pack(anchor=W)
        return value

    def refresh(self, supplier_id=None):
        if supplier_id is not None:
            self.selected_supplier_id = supplier_id
        self._load_vendors()

    def _load_vendors(self):
        self.suppliers = db.get_suppliers(
            self.company_id, active_only=False,
            search=self.vendor_search.get().strip() or None,
        )
        self.vendor_tree.delete(*self.vendor_tree.get_children())
        for row in self.suppliers:
            suffix = "" if row.get("is_active") else " (inactive)"
            self.vendor_tree.insert(
                "", END, iid=str(row["id"]),
                values=(
                    f"{row['name']}{suffix}",
                    f"{float(row.get('balance_due') or 0):,.2f}",
                ),
            )
        ids = {row["id"] for row in self.suppliers}
        if self.selected_supplier_id not in ids:
            self.selected_supplier_id = (
                self.suppliers[0]["id"] if self.suppliers else None
            )
        if (
            self.selected_supplier_id
            and self.vendor_tree.exists(str(self.selected_supplier_id))
        ):
            key = str(self.selected_supplier_id)
            self.vendor_tree.selection_set(key)
            self.vendor_tree.focus(key)
            self.vendor_tree.see(key)
        self._load_summary()

    def _vendor_selected(self, _event=None):
        selected = self.vendor_tree.selection()
        if selected:
            self.selected_supplier_id = int(selected[0])
            self._load_summary()

    def _selected_vendor(self):
        return next(
            (
                row for row in self.suppliers
                if row["id"] == self.selected_supplier_id
            ),
            None,
        )

    def _load_summary(self):
        supplier = self._selected_vendor()
        if not supplier:
            self.vendor_name.configure(text="No vendors found")
            self.vendor_details.configure(
                text="Create a vendor to begin entering bills."
            )
            self.transaction_tree.delete(*self.transaction_tree.get_children())
            return
        self.vendor_name.configure(text=supplier["name"])
        details = (
            supplier.get("contact_person"), supplier.get("phone"),
            supplier.get("email"),
            f"Terms: {supplier.get('payment_terms') or 30} days",
            f"Currency: {supplier.get('currency') or self.home_currency}",
        )
        self.vendor_details.configure(
            text="  •  ".join(str(value) for value in details if value)
        )
        bills = db.get_ap_invoices(
            self.company_id, supplier_id=supplier["id"]
        )
        base_open = sum(
            float(row.get("balance_due") or 0)
            * float(row.get("exchange_rate") or 1)
            for row in bills
            if row.get("status") not in ("Paid", "Cancelled")
        )
        base_overdue = sum(
            float(row.get("balance_due") or 0)
            * float(row.get("exchange_rate") or 1)
            for row in bills if row.get("is_overdue")
        )
        pos = db.get_purchase_orders(
            self.company_id, supplier_id=supplier["id"]
        )
        open_po = sum(
            float(row.get("total_amount") or 0)
            for row in pos
            if row.get("status") not in ("Closed", "Cancelled", "Billed")
        )
        paid = self._paid_last_30_days(supplier["id"])
        self.open_value.configure(
            text=f"{self.home_currency} {base_open:,.2f}"
        )
        self.overdue_value.configure(
            text=f"{self.home_currency} {base_overdue:,.2f}"
        )
        self.credit_value.configure(
            text=f"{self.home_currency} "
            f"{float(supplier.get('available_credit') or 0):,.2f}"
        )
        self.paid_value.configure(
            text=f"{self.home_currency} {paid:,.2f}"
        )
        self.po_value.configure(
            text=f"{self.home_currency} {open_po:,.2f}"
        )
        self._load_transactions()

    def _paid_last_30_days(self, supplier_id):
        connection = db.get_connection()
        try:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(COALESCE(
                    base_cash_amount,
                    total_cash_amount * COALESCE(exchange_rate, 1)
                )), 0)
                FROM ap_payment_batches
                WHERE company_id=? AND supplier_id=? AND payment_date>=?
                """,
                (
                    self.company_id, supplier_id,
                    (date.today() - timedelta(days=30)).isoformat(),
                ),
            ).fetchone()
            return float(row[0] or 0)
        finally:
            connection.close()

    def _date_bounds(self):
        today = date.today()
        period = self.period_var.get()
        if period == "This month":
            return today.replace(day=1).isoformat(), today.isoformat()
        if period == "This year":
            return today.replace(month=1, day=1).isoformat(), today.isoformat()
        if period == "Last year":
            year = today.year - 1
            return f"{year}-01-01", f"{year}-12-31"
        return None, None

    def _load_transactions(self):
        supplier = self._selected_vendor()
        self.transaction_tree.delete(*self.transaction_tree.get_children())
        if not supplier:
            return
        start, end = self._date_bounds()
        selected_type = self.type_var.get()
        rows = []
        if selected_type in ("All transactions", "Bills"):
            for bill in db.get_ap_invoices(
                self.company_id, supplier_id=supplier["id"],
                start_date=start, end_date=end,
            ):
                rows.append({
                    "key": f"bill:{bill['id']}",
                    "date": bill["invoice_date"], "type": "Bill",
                    "number": bill["invoice_number"],
                    "memo": bill.get("internal_ref") or bill.get("notes") or "",
                    "amount": float(bill.get("total_amount") or 0),
                    "open": float(bill.get("balance_due") or 0),
                    "currency": bill.get("currency") or self.home_currency,
                    "status": (
                        "Overdue" if bill.get("is_overdue")
                        else bill.get("status") or "Unpaid"
                    ),
                })
        if selected_type in ("All transactions", "Vendor credits"):
            for credit in vp.credits(self.company_id, supplier["id"]):
                if start and credit["credit_date"] < start:
                    continue
                if end and credit["credit_date"] > end:
                    continue
                rows.append({
                    "key": f"credit:{credit['id']}",
                    "date": credit["credit_date"], "type": "Vendor credit",
                    "number": credit["credit_number"],
                    "memo": credit.get("reference") or credit.get("notes") or "",
                    "amount": -float(credit.get("amount") or 0),
                    "open": -float(credit.get("remaining_amount") or 0),
                    "currency": credit.get("currency") or self.home_currency,
                    "status": credit.get("status") or "Open",
                })
        if selected_type in ("All transactions", "Purchase orders"):
            for po in db.get_purchase_orders(
                self.company_id, supplier_id=supplier["id"],
                start_date=start, end_date=end,
            ):
                rows.append({
                    "key": f"po:{po['id']}", "date": po["po_date"],
                    "type": "Purchase order", "number": po["po_number"],
                    "memo": po.get("notes") or "",
                    "amount": float(po.get("total_amount") or 0),
                    "open": 0.0,
                    "currency": po.get("currency") or self.home_currency,
                    "status": po.get("status") or "Open",
                })
        if selected_type in ("All transactions", "Payments"):
            rows.extend(self._payment_rows(supplier["id"], start, end))
        self.transaction_rows = rows
        find = self.find_var.get().strip().casefold()
        wanted_status = self.status_var.get()
        for row in sorted(
            rows, key=lambda item: (item["date"], item["key"]), reverse=True
        ):
            searchable = " ".join(
                str(row.get(key, ""))
                for key in ("type", "number", "memo", "status")
            ).casefold()
            if find and find not in searchable:
                continue
            normalized = str(row["status"]).casefold()
            if wanted_status != "All statuses":
                wanted = wanted_status.casefold()
                if wanted == "open":
                    if normalized in {
                        "paid", "closed", "cancelled", "applied"
                    }:
                        continue
                elif normalized != wanted:
                    continue
            code = row["currency"]
            self.transaction_tree.insert(
                "", END, iid=row["key"],
                values=(
                    row["date"], row["type"], row["number"],
                    row["memo"] or "—",
                    f"{code} {row['amount']:,.2f}",
                    f"{code} {row['open']:,.2f}" if row["open"] else "—",
                    row["status"],
                ),
            )

    def _payment_rows(self, supplier_id, start, end):
        connection = db.get_connection()
        try:
            query = """
                SELECT id,payment_date,payment_method,reference,check_number,
                       total_cash_amount,total_credit_amount,currency
                FROM ap_payment_batches
                WHERE company_id=? AND supplier_id=?
            """
            params = [self.company_id, supplier_id]
            if start:
                query += " AND payment_date>=?"
                params.append(start)
            if end:
                query += " AND payment_date<=?"
                params.append(end)
            result = []
            for item in connection.execute(query, params).fetchall():
                row = dict(item)
                amount = (
                    float(row.get("total_cash_amount") or 0)
                    + float(row.get("total_credit_amount") or 0)
                )
                result.append({
                    "key": f"payment:{row['id']}",
                    "date": row["payment_date"], "type": "Bill payment",
                    "number": (
                        row.get("check_number") or row.get("reference")
                        or f"PAY-{row['id']}"
                    ),
                    "memo": row.get("payment_method") or "Payment",
                    "amount": -amount, "open": 0.0,
                    "currency": row.get("currency") or self.home_currency,
                    "status": "Paid",
                })
            return result
        finally:
            connection.close()

    def _require_vendor(self):
        supplier = self._selected_vendor()
        if not supplier:
            messagebox.showinfo(
                "Vendor Centre", "Select or create a vendor first.",
                parent=self,
            )
        return supplier

    def _new_vendor(self):
        SupplierEditModal(self, self.company_id, on_saved=self.refresh)

    def _edit_vendor(self):
        supplier = self._require_vendor()
        if supplier:
            SupplierEditModal(
                self, self.company_id, supplier,
                on_saved=lambda: self.refresh(supplier["id"]),
            )

    def _merge_vendor(self):
        source = self._require_vendor()
        if not source:
            return
        candidates = [
            row for row in db.get_suppliers(
                self.company_id, active_only=False
            )
            if row["id"] != source["id"]
            and (row.get("currency") or "").upper()
            == (source.get("currency") or "").upper()
        ]
        if not candidates:
            messagebox.showinfo(
                "Merge vendor",
                "No same-currency vendor is available to keep.",
                parent=self,
            )
            return
        target = choose_merge_target(self, "vendor", source, candidates)
        if target is not None:
            try:
                db.merge_suppliers(source["id"], target)
                self.refresh(target)
            except Exception as exc:
                messagebox.showerror("Merge vendor", str(exc), parent=self)

    def _new_bill(self):
        if self.open_bill_callback:
            self.open_bill_callback(supplier_id=self.selected_supplier_id)

    def _open_transaction(self):
        selected = self.transaction_tree.selection()
        if not selected:
            return
        kind, value = selected[0].split(":", 1)
        if kind == "bill" and self.open_bill_callback:
            self.open_bill_callback(
                invoice_id=int(value),
                supplier_id=self.selected_supplier_id,
            )
        elif kind == "po":
            from ui.purchase_order_dialog import PurchaseOrderEntryDialog
            PurchaseOrderEntryDialog(
                self, self.company_id, po_id=int(value),
                on_saved=lambda _value: self.refresh(
                    self.selected_supplier_id
                ),
            )

    def _pay_bills(self):
        supplier = self._require_vendor()
        if supplier:
            dialog = PayBillsDialog(
                self, self.company_id, supplier["id"],
                lambda: self.refresh(supplier["id"]),
            )
            self.wait_window(dialog)

    def _vendor_credit(self):
        supplier = self._require_vendor()
        if supplier:
            VendorCreditDialog(
                self, self.company_id, supplier["id"],
                lambda: self.refresh(supplier["id"]),
            )

    def _purchase_order(self):
        supplier = self._require_vendor()
        if supplier:
            from ui.purchase_order_dialog import PurchaseOrderEntryDialog
            PurchaseOrderEntryDialog(
                self, self.company_id,
                on_saved=lambda _value: self.refresh(supplier["id"]),
            )

    def _aging(self):
        APAgingDialog(self, self.company_id)

    def _export(self):
        if not self.suppliers:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Export vendor list",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="vendor_centre.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "Vendor", "Contact", "Phone", "Email", "Currency",
                "Bills", "Open balance", "Available credit", "Status",
            ])
            for row in self.suppliers:
                writer.writerow(db._sanitize_csv_row([
                    row["name"], row.get("contact_person") or "",
                    row.get("phone") or "", row.get("email") or "",
                    row.get("currency") or self.home_currency,
                    row.get("invoice_count") or 0,
                    f"{float(row.get('balance_due') or 0):.2f}",
                    f"{float(row.get('available_credit') or 0):.2f}",
                    "Active" if row.get("is_active") else "Inactive",
                ]))
