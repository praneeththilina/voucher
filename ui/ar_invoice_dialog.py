"""Customer-centred Accounts Receivable, invoicing and payment workflow."""

from __future__ import annotations

import csv
import os
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import invoice_printer
import sales_database as sales_db
from ui.item_manager import ItemEditDialog, ProductsServicesDialog
from ui.pdf_viewer import PdfViewerDialog


def _money(value: object) -> str:
    return f"{float(value or 0):,.2f}"


class ARInvoiceEntryDialog(tb.Toplevel):
    """Create or edit an item-aware customer invoice."""

    def __init__(
        self,
        parent,
        company_id: int | None = None,
        invoice_id: int | None = None,
        on_saved=None,
        customer_id: int | None = None,
        on_customer_changed=None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.invoice_id = invoice_id
        self.on_saved = on_saved
        self.on_customer_changed = on_customer_changed
        self._close_after_save = True
        self.preselected_customer_id = customer_id
        self.preferences = sales_db.get_sales_preferences(self.company_id)
        self.home_currency = db.get_company_base_currency(self.company_id).upper()
        self.currency_values = [self.home_currency]
        if db.is_multicurrency_enabled(self.company_id):
            self.currency_values = [
                row["code"] for row in db.get_currencies(active_only=True)
            ]
        self.lines_data: list[dict] = []
        self.customers: list[dict] = []
        self.items: list[dict] = []
        self.customer_lookup: dict[str, dict] = {}
        self.item_lookup: dict[str, dict] = {}
        self.title("Edit Invoice" if invoice_id else "Create Invoice")
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.transient(parent)
        self.grab_set()
        self._reload_reference_data()
        self._build_ui()
        if invoice_id:
            self._load_invoice()
        else:
            self._set_defaults()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (self.winfo_screenwidth() - width) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - height) // 2)}"
        )

    def _reload_reference_data(self) -> None:
        self.customers = db.get_customers(
            company_id=self.company_id, active_only=True
        )
        self.customer_lookup = {
            customer["name"]: customer for customer in self.customers
        }
        self.items = sales_db.get_sales_items(company_id=self.company_id)
        self.item_lookup = {
            self._item_display(item): item for item in self.items
        }

    @staticmethod
    def _item_display(item: dict) -> str:
        suffix = f" [{item['sku']}]" if item.get("sku") else ""
        return f"{item['name']}{suffix}"

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=14)
        root.pack(fill=BOTH, expand=True)

        footer = tb.Frame(root)
        footer.pack(side=BOTTOM, fill=X, pady=(10, 0))
        tb.Button(
            footer,
            text="Back to Customer Centre",
            bootstyle="secondary-outline",
            command=self._cancel,
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            footer,
            text="Save & Issue",
            bootstyle="success",
            command=lambda: self._save(issue=True),
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            footer,
            text="Save Draft",
            bootstyle="primary-outline",
            command=lambda: self._save(issue=False),
        ).pack(side=RIGHT)
        if self.invoice_id:
            tb.Button(
                footer,
                text="Print / Preview",
                bootstyle="info-outline",
                command=self._preview,
            ).pack(side=LEFT)

        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 10))
        tb.Label(
            header,
            text="Invoice",
            font=("Segoe UI", 18, "bold"),
        ).pack(side=LEFT)
        tb.Button(
            header,
            text="Products & Services",
            bootstyle="secondary-outline",
            command=self._open_items,
        ).pack(side=RIGHT)

        info = tb.Labelframe(root, text="Customer and invoice", padding=10)
        info.pack(fill=X, pady=(0, 9))
        for index in (1, 3, 5, 7):
            info.columnconfigure(index, weight=1)

        self.customer_var = tk.StringVar()
        tb.Label(info, text="Customer *").grid(row=0, column=0, sticky=W)
        self.customer_combo = tb.Combobox(
            info,
            textvariable=self.customer_var,
            values=list(self.customer_lookup),
        )
        self.customer_combo.grid(
            row=0, column=1, sticky=EW, padx=(6, 6), pady=4
        )
        self.customer_combo.bind(
            "<<ComboboxSelected>>", self._customer_selected
        )
        tb.Button(
            info,
            text="+",
            width=3,
            bootstyle="success-outline",
            command=self._new_customer,
        ).grid(row=0, column=2, sticky=W, padx=(0, 12))

        self.number_var = tk.StringVar()
        tb.Label(info, text="Invoice # *").grid(row=0, column=3, sticky=W)
        tb.Entry(info, textvariable=self.number_var).grid(
            row=0, column=4, sticky=EW, padx=(6, 14), pady=4
        )

        self.reference_var = tk.StringVar()
        tb.Label(info, text="Customer PO / ref").grid(
            row=0, column=5, sticky=W
        )
        tb.Entry(info, textvariable=self.reference_var).grid(
            row=0, column=6, columnspan=2, sticky=EW, padx=(6, 0), pady=4
        )

        self.date_var = tk.StringVar()
        self.terms_days_var = tk.StringVar(value="30")
        self.due_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Draft")
        tb.Label(info, text="Invoice date").grid(row=1, column=0, sticky=W)
        tb.Entry(info, textvariable=self.date_var).grid(
            row=1, column=1, sticky=EW, padx=(6, 14), pady=4
        )
        tb.Label(info, text="Terms").grid(row=1, column=2, sticky=E)
        terms = tb.Spinbox(
            info,
            from_=0,
            to=365,
            textvariable=self.terms_days_var,
            width=8,
        )
        terms.grid(row=1, column=3, sticky=W, padx=(6, 14), pady=4)
        tb.Label(info, text="Due date").grid(row=1, column=4, sticky=E)
        tb.Entry(info, textvariable=self.due_var).grid(
            row=1, column=5, sticky=EW, padx=(6, 14), pady=4
        )
        tb.Label(info, text="Status").grid(row=1, column=6, sticky=E)
        tb.Combobox(
            info,
            textvariable=self.status_var,
            values=[
                "Draft", "Unpaid", "Partially Paid", "Paid", "Cancelled"
            ],
            state="readonly",
            width=16,
        ).grid(row=1, column=7, sticky=EW, padx=(6, 0), pady=4)
        self.date_var.trace_add("write", lambda *_args: self._due_date())
        self.terms_days_var.trace_add(
            "write", lambda *_args: self._due_date()
        )
        self.currency_var = tk.StringVar(value=self.home_currency)
        self.rate_var = tk.StringVar(value="1.000000")
        tb.Label(info, text="Currency").grid(row=2, column=0, sticky=W)
        self.currency_combo = tb.Combobox(
            info, textvariable=self.currency_var, values=self.currency_values,
            state="readonly" if len(self.currency_values) > 1 else "disabled"
        )
        self.currency_combo.grid(row=2, column=1, sticky=EW, padx=(6, 14), pady=4)
        self.currency_combo.bind("<<ComboboxSelected>>", self._currency_changed)
        tb.Label(info, text="Exchange rate").grid(row=2, column=2, sticky=E)
        self.rate_entry = tb.Entry(info, textvariable=self.rate_var)
        self.rate_entry.grid(row=2, column=3, sticky=EW, padx=(6, 14), pady=4)
        self.rate_entry.configure(state="disabled")
        tb.Label(
            info,
            text=f"1 foreign currency unit = X {self.home_currency}",
            bootstyle="secondary",
        ).grid(row=2, column=4, columnspan=4, sticky=W, pady=4)

        lines_box = tb.Labelframe(root, text="Products and services", padding=8)
        lines_box.pack(fill=BOTH, expand=True)
        columns = (
            "row", "type", "item", "description", "qty", "rate",
            "vat", "amount",
        )
        self.tree = ttk.Treeview(
            lines_box, columns=columns, show="headings", height=10
        )
        headings = {
            "row": "#",
            "type": "Line",
            "item": "Product / service",
            "description": "Description",
            "qty": "Qty",
            "rate": "Rate",
            "vat": "VAT",
            "amount": "Amount",
        }
        widths = {
            "row": 40,
            "type": 80,
            "item": 180,
            "description": 310,
            "qty": 70,
            "rate": 100,
            "vat": 90,
            "amount": 120,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                stretch=column in {"item", "description"},
                anchor=E if column in {"qty", "rate", "vat", "amount"} else W,
            )
        scrollbar = tb.Scrollbar(
            lines_box, orient=VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.bind("<Double-1>", lambda _event: self._edit_line())

        line_bar = tb.Frame(root)
        line_bar.pack(fill=X, pady=(8, 6))
        tb.Button(
            line_bar,
            text="+ Product / Service",
            bootstyle="success-outline",
            command=self._add_item,
        ).pack(side=LEFT, padx=(0, 5))
        if self.preferences["discounts_enabled"]:
            tb.Button(
                line_bar,
                text="+ Subtotal",
                bootstyle="secondary-outline",
                command=self._add_subtotal,
            ).pack(side=LEFT, padx=5)
            tb.Button(
                line_bar,
                text="+ Discount",
                bootstyle="warning-outline",
                command=self._add_discount,
            ).pack(side=LEFT, padx=5)
        tb.Button(
            line_bar,
            text="Edit line",
            bootstyle="primary-outline",
            command=self._edit_line,
        ).pack(side=LEFT, padx=5)
        tb.Button(
            line_bar,
            text="Remove",
            bootstyle="danger-outline",
            command=self._remove_line,
        ).pack(side=LEFT, padx=5)

        bottom = tb.Frame(root)
        bottom.pack(fill=X)
        notes = tb.Frame(bottom)
        notes.pack(side=LEFT, fill=X, expand=True, padx=(0, 20))
        self.notes_var = tk.StringVar()
        self.terms_text_var = tk.StringVar(
            value="Payment due within the agreed terms."
        )
        tb.Label(notes, text="Customer message").pack(anchor=W)
        tb.Entry(notes, textvariable=self.notes_var).pack(
            fill=X, pady=(2, 7)
        )
        tb.Label(notes, text="Terms and instructions").pack(anchor=W)
        tb.Entry(notes, textvariable=self.terms_text_var).pack(
            fill=X, pady=(2, 0)
        )

        totals = tb.Frame(bottom, padding=10, bootstyle="light")
        totals.pack(side=RIGHT)
        self.discount_type_var = tk.StringVar(value="Amount")
        self.discount_value_var = tk.StringVar(value="0.00")
        self.discount_value_var.trace_add(
            "write", lambda *_args: self._refresh_lines()
        )
        self.discount_type_var.trace_add(
            "write", lambda *_args: self._refresh_lines()
        )
        self.subtotal_label = tb.Label(totals, text="0.00")
        self.tax_label = tb.Label(totals, text="0.00")
        self.discount_label = tb.Label(totals, text="0.00")
        self.total_label = tb.Label(
            totals, text="LKR 0.00", font=("Segoe UI", 12, "bold")
        )
        tb.Label(totals, text="Subtotal").grid(row=0, column=0, sticky=W)
        self.subtotal_label.grid(row=0, column=1, sticky=E, padx=(18, 0))
        tb.Label(totals, text="Header discount").grid(
            row=1, column=0, sticky=W
        )
        disc = tb.Frame(totals)
        disc.grid(row=1, column=1, sticky=E, padx=(18, 0), pady=2)
        tb.Combobox(
            disc,
            textvariable=self.discount_type_var,
            values=["Amount", "Percent"],
            state="readonly",
            width=9,
        ).pack(side=LEFT)
        tb.Entry(
            disc, textvariable=self.discount_value_var, width=10
        ).pack(side=LEFT, padx=(4, 0))
        tb.Label(totals, text="Total discounts").grid(
            row=2, column=0, sticky=W
        )
        self.discount_label.grid(row=2, column=1, sticky=E)
        tb.Label(totals, text="VAT / tax").grid(row=3, column=0, sticky=W)
        self.tax_label.grid(row=3, column=1, sticky=E)
        ttk.Separator(totals).grid(
            row=4, column=0, columnspan=2, sticky=EW, pady=5
        )
        tb.Label(
            totals, text="Total", font=("Segoe UI", 11, "bold")
        ).grid(row=5, column=0, sticky=W)
        self.total_label.grid(row=5, column=1, sticky=E, padx=(18, 0))

    def _currency_changed(self, _event=None) -> None:
        code = self.currency_var.get() or self.home_currency
        if code == self.home_currency:
            self.rate_var.set("1.000000")
            self.rate_entry.configure(state="disabled")
        else:
            rate = db.get_exchange_rate(code, self.home_currency)
            self.rate_var.set(f"{float(rate['rate']):.6f}" if rate else "")
            self.rate_entry.configure(state="normal")
        self._refresh_lines()

    def _set_defaults(self) -> None:
        self._currency_changed()
        self.number_var.set(
            db.get_next_ar_invoice_number(company_id=self.company_id)
        )
        self.date_var.set(datetime.now().strftime("%Y-%m-%d"))
        if self.preselected_customer_id:
            for customer in self.customers:
                if customer["id"] == self.preselected_customer_id:
                    self.customer_var.set(customer["name"])
                    self._customer_selected()
                    break
        self._due_date()
        self._refresh_lines()

    def _due_date(self) -> None:
        try:
            date = datetime.strptime(self.date_var.get(), "%Y-%m-%d")
            days = int(self.terms_days_var.get() or 0)
            self.due_var.set((date + timedelta(days=days)).strftime("%Y-%m-%d"))
        except (ValueError, TypeError):
            return

    def _customer_selected(self, _event=None) -> None:
        customer = self.customer_lookup.get(self.customer_var.get())
        if customer:
            self.terms_days_var.set(str(customer.get("payment_terms") or 30))

    def _new_customer(self) -> None:
        from ui.customer_manager import CustomerEditModal

        def saved(customer_id: int) -> None:
            self._reload_reference_data()
            self.customer_combo.configure(values=list(self.customer_lookup))
            customer = db.get_customer_by_id(customer_id)
            if customer:
                self.customer_var.set(customer["name"])
                self._customer_selected()
            if self.on_customer_changed:
                self.on_customer_changed(customer_id)

        CustomerEditModal(self, self.company_id, on_saved=saved)

    def _open_items(self) -> None:
        dialog = ProductsServicesDialog(self, self.company_id)
        self.wait_window(dialog)
        self._reload_reference_data()

    def _add_item(self) -> None:
        if not self.items:
            if messagebox.askyesno(
                "Products & Services",
                "Create your first product or service now?",
                parent=self,
            ):
                ItemEditDialog(
                    self,
                    self.company_id,
                    on_saved=lambda _item_id: self._after_item_created(),
                )
            return
        self._item_line_dialog()

    def _after_item_created(self) -> None:
        self._reload_reference_data()
        self._item_line_dialog()

    def _selected_line_index(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return int(self.tree.item(selection[0], "values")[0]) - 1

    def _edit_line(self) -> None:
        index = self._selected_line_index()
        if index is None:
            messagebox.showinfo(
                "Select line", "Select a line to edit.", parent=self
            )
            return
        line = self.lines_data[index]
        if line.get("line_type", "Item") == "Item":
            self._item_line_dialog(index)
        elif line.get("line_type") == "Discount":
            self._discount_dialog(index)
        else:
            messagebox.showinfo(
                "Subtotal",
                "Subtotal lines calculate automatically and do not need editing.",
                parent=self,
            )

    def _item_line_dialog(self, index: int | None = None) -> None:
        current = self.lines_data[index] if index is not None else {}
        dialog = tb.Toplevel(self)
        dialog.title("Invoice product / service")
        dialog.geometry("620x410")
        dialog.transient(self)
        dialog.grab_set()
        frame = tb.Frame(dialog, padding=16)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        item_var = tk.StringVar()
        description_var = tk.StringVar()
        quantity_var = tk.StringVar(value="1.00")
        rate_var = tk.StringVar(value="0.00")
        tax_var = tk.StringVar(value="0")

        tb.Label(frame, text="Product / service *").grid(
            row=0, column=0, sticky=W, pady=6
        )
        combo = tb.Combobox(
            frame,
            textvariable=item_var,
            values=list(self.item_lookup),
            state="readonly",
        )
        combo.grid(row=0, column=1, sticky=EW, padx=(10, 0), pady=6)
        tb.Label(frame, text="Description").grid(
            row=1, column=0, sticky=W, pady=6
        )
        tb.Entry(frame, textvariable=description_var).grid(
            row=1, column=1, sticky=EW, padx=(10, 0), pady=6
        )
        tb.Label(frame, text="Quantity").grid(
            row=2, column=0, sticky=W, pady=6
        )
        tb.Entry(frame, textvariable=quantity_var).grid(
            row=2, column=1, sticky=EW, padx=(10, 0), pady=6
        )
        tb.Label(frame, text=f"Rate ({self.currency_var.get() or self.home_currency})").grid(
            row=3, column=0, sticky=W, pady=6
        )
        tb.Entry(frame, textvariable=rate_var).grid(
            row=3, column=1, sticky=EW, padx=(10, 0), pady=6
        )
        tb.Label(frame, text="VAT / tax %").grid(
            row=4, column=0, sticky=W, pady=6
        )
        tax_values = sorted({
            f"{float(rate.get('rate') or 0) * 100:g}"
            for rate in db.get_tax_rates(
                company_id=self.company_id, active_only=True
            )
        })
        if "0" not in tax_values:
            tax_values.insert(0, "0")
        tax_combo = tb.Combobox(
            frame,
            textvariable=tax_var,
            values=tax_values,
            state="readonly",
        )
        tax_combo.grid(row=4, column=1, sticky=EW, padx=(10, 0), pady=6)
        if not self.preferences["sales_tax_enabled"]:
            tax_var.set("0")
            tax_combo.configure(state="disabled")

        def choose(_event=None) -> None:
            item = self.item_lookup.get(item_var.get())
            if not item:
                return
            description_var.set(item.get("description") or item["name"])
            rate_var.set(f"{float(item.get('sales_price') or 0):.2f}")
            tax_var.set(
                f"{float(item.get('tax_rate') or 0) * 100:g}"
                if item.get("taxable") and self.preferences["sales_tax_enabled"]
                else "0"
            )

        combo.bind("<<ComboboxSelected>>", choose)
        if current:
            for name, item in self.item_lookup.items():
                if item["id"] == current.get("item_id"):
                    item_var.set(name)
                    break
            description_var.set(current.get("description", ""))
            quantity_var.set(str(current.get("quantity", 1)))
            rate_var.set(str(current.get("unit_price", 0)))
            tax_var.set(
                f"{float(current.get('tax_rate') or 0) * 100:g}"
            )
        elif self.item_lookup:
            item_var.set(next(iter(self.item_lookup)))
            choose()

        buttons = tb.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky=EW, pady=(18, 0))

        def save_line() -> None:
            try:
                item = self.item_lookup.get(item_var.get())
                if not item:
                    raise ValueError("Select a product or service.")
                quantity = float(quantity_var.get())
                rate = float(rate_var.get())
                tax_rate = float(tax_var.get() or 0) / 100
                if quantity <= 0:
                    raise ValueError("Quantity must be greater than zero.")
                payload = {
                    "line_type": "Item",
                    "item_id": item["id"],
                    "item_name": item["name"],
                    "description": description_var.get().strip() or item["name"],
                    "account_id": item.get("income_account_id"),
                    "quantity": quantity,
                    "unit_price": rate,
                    "tax_rate": tax_rate,
                }
                if index is None:
                    self.lines_data.append(payload)
                else:
                    self.lines_data[index] = payload
                self._refresh_lines()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showwarning("Check line", str(exc), parent=dialog)

        tb.Button(
            buttons,
            text="Cancel",
            bootstyle="secondary-outline",
            command=dialog.destroy,
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            buttons,
            text="Done",
            bootstyle="success",
            command=save_line,
        ).pack(side=RIGHT)

    def _add_subtotal(self) -> None:
        if not any(
            line.get("line_type", "Item") == "Item"
            for line in self.lines_data
        ):
            messagebox.showinfo(
                "Subtotal", "Add an item before a subtotal.", parent=self
            )
            return
        self.lines_data.append({
            "line_type": "Subtotal",
            "description": "Subtotal",
            "quantity": 0,
            "unit_price": 0,
            "tax_rate": 0,
        })
        self._refresh_lines()

    def _add_discount(self) -> None:
        if not self.lines_data:
            messagebox.showinfo(
                "Discount", "Add an item before a discount.", parent=self
            )
            return
        self._discount_dialog()

    def _discount_dialog(self, index: int | None = None) -> None:
        current = self.lines_data[index] if index is not None else {}
        dialog = tb.Toplevel(self)
        dialog.title("Discount line")
        dialog.geometry("460x250")
        dialog.transient(self)
        dialog.grab_set()
        frame = tb.Frame(dialog, padding=18)
        frame.pack(fill=BOTH, expand=True)
        frame.columnconfigure(1, weight=1)
        kind_var = tk.StringVar(
            value=current.get("discount_type", "Percent")
        )
        value_var = tk.StringVar(
            value=str(current.get("discount_value", 0))
        )
        description_var = tk.StringVar(
            value=current.get("description", "Discount")
        )
        tb.Label(frame, text="Description").grid(
            row=0, column=0, sticky=W, pady=6
        )
        tb.Entry(frame, textvariable=description_var).grid(
            row=0, column=1, sticky=EW, padx=(8, 0), pady=6
        )
        tb.Label(frame, text="Discount type").grid(
            row=1, column=0, sticky=W, pady=6
        )
        tb.Combobox(
            frame,
            textvariable=kind_var,
            values=["Percent", "Amount"],
            state="readonly",
        ).grid(row=1, column=1, sticky=EW, padx=(8, 0), pady=6)
        tb.Label(frame, text="Value").grid(
            row=2, column=0, sticky=W, pady=6
        )
        tb.Entry(frame, textvariable=value_var).grid(
            row=2, column=1, sticky=EW, padx=(8, 0), pady=6
        )

        def save_discount() -> None:
            try:
                value = float(value_var.get())
                if value <= 0:
                    raise ValueError("Discount must be greater than zero.")
                payload = {
                    "line_type": "Discount",
                    "description": description_var.get().strip() or "Discount",
                    "discount_type": kind_var.get(),
                    "discount_value": value,
                    "quantity": 0,
                    "unit_price": 0,
                    "tax_rate": 0,
                }
                if index is None:
                    self.lines_data.append(payload)
                else:
                    self.lines_data[index] = payload
                self._refresh_lines()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showwarning(
                    "Check discount", str(exc), parent=dialog
                )

        buttons = tb.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky=EW, pady=(16, 0))
        tb.Button(
            buttons, text="Cancel", command=dialog.destroy,
            bootstyle="secondary-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            buttons, text="Done", command=save_discount,
            bootstyle="success",
        ).pack(side=RIGHT)

    def _remove_line(self) -> None:
        index = self._selected_line_index()
        if index is None:
            return
        del self.lines_data[index]
        self._refresh_lines()

    def _invoice_payload(self) -> dict:
        customer = self.customer_lookup.get(self.customer_var.get())
        if not customer:
            raise ValueError("Select a customer.")
        if not self.number_var.get().strip():
            raise ValueError("Invoice number is required.")
        if not any(
            line.get("line_type", "Item") == "Item"
            for line in self.lines_data
        ):
            raise ValueError("Add at least one product or service.")
        return {
            "company_id": self.company_id,
            "customer_id": customer["id"],
            "invoice_number": self.number_var.get().strip(),
            "internal_ref": self.reference_var.get().strip(),
            "invoice_date": self.date_var.get().strip(),
            "due_date": self.due_var.get().strip(),
            "discount_type": self.discount_type_var.get(),
            "discount_value": float(self.discount_value_var.get() or 0),
            "currency": self.currency_var.get(),
            "exchange_rate": self.rate_var.get(),
            "status": self.status_var.get(),
            "notes": self.notes_var.get().strip(),
            "terms": self.terms_text_var.get().strip(),
            "footer_text": "",
            "created_by": "User",
        }

    def _refresh_lines(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            header = {
                "discount_type": self.discount_type_var.get(),
                "discount_value": float(
                    self.discount_value_var.get().replace(",", "") or 0
                ),
            }
            totals = sales_db.invoice_totals(self.lines_data, header)
            prepared = totals["lines"]
        except (ValueError, TypeError):
            prepared = self.lines_data
            totals = {"subtotal": 0, "tax": 0, "discount": 0, "total": 0}
        for index, line in enumerate(prepared, 1):
            kind = line.get("line_type", "Item")
            item_name = line.get("item_name", "")
            if line.get("item_id") and not item_name:
                item = sales_db.get_sales_item(line["item_id"])
                item_name = item["name"] if item else ""
            quantity = (
                _money(line.get("quantity"))
                if kind == "Item" else ""
            )
            rate = (
                _money(line.get("unit_price"))
                if kind == "Item" else ""
            )
            vat = (
                _money(line.get("tax_amount"))
                if float(line.get("tax_amount") or 0) else "-"
            )
            self.tree.insert("", END, values=(
                index,
                kind,
                item_name,
                line.get("description", ""),
                quantity,
                rate,
                vat,
                _money(line.get("line_total")),
            ))
        self.subtotal_label.configure(text=_money(totals["subtotal"]))
        self.tax_label.configure(text=_money(totals["tax"]))
        self.discount_label.configure(text=_money(totals["discount"]))
        self.total_label.configure(text=f"{self.currency_var.get() or self.home_currency} {_money(totals['total'])}")

    def _load_invoice(self) -> None:
        data = db.get_ar_invoice(self.invoice_id)
        if not data:
            messagebox.showerror(
                "Invoice", "Invoice could not be found.", parent=self
            )
            self.destroy()
            return
        invoice = data["invoice"]
        self.customer_var.set(invoice.get("customer_name", ""))
        self.number_var.set(invoice.get("invoice_number", ""))
        self.reference_var.set(invoice.get("internal_ref", ""))
        self.date_var.set(invoice.get("invoice_date", ""))
        self.due_var.set(invoice.get("due_date", ""))
        self.status_var.set(invoice.get("status", "Draft"))
        self.currency_var.set(invoice.get("currency") or self.home_currency)
        self._currency_changed()
        self.rate_var.set(f"{float(invoice.get('exchange_rate') or 1):.6f}")
        self.notes_var.set(invoice.get("notes", ""))
        self.terms_text_var.set(invoice.get("terms", ""))
        discount_type = invoice.get("discount_type") or "Amount"
        discount_value = float(invoice.get("discount_value") or 0.0)
        # Migration 33 initializes the new value column to zero. Preserve the
        # amount from invoices created before typed discounts were available.
        if discount_value == 0.0 and float(invoice.get("discount_amount") or 0.0) > 0.0:
            discount_type = "Amount"
            discount_value = float(invoice.get("discount_amount") or 0.0)
        self.discount_type_var.set(discount_type)
        self.discount_value_var.set(str(discount_value))
        self.lines_data = []
        for row in data["lines"]:
            line = dict(row)
            line["line_type"] = line.get("line_type") or "Item"
            item = (
                sales_db.get_sales_item(line["item_id"])
                if line.get("item_id") else None
            )
            line["item_name"] = item["name"] if item else ""
            self.lines_data.append(line)
        try:
            invoice_date = datetime.strptime(
                invoice["invoice_date"], "%Y-%m-%d"
            )
            due_date = datetime.strptime(invoice["due_date"], "%Y-%m-%d")
            self.terms_days_var.set(str((due_date - invoice_date).days))
        except (ValueError, TypeError):
            self.terms_days_var.set("30")
        self._refresh_lines()

    def _save(self, issue: bool) -> None:
        try:
            payload = self._invoice_payload()
            payload["status"] = (
                "Unpaid"
                if issue and payload["status"] == "Draft"
                else payload["status"]
            )
            if not issue:
                payload["status"] = "Draft"
            if self.invoice_id:
                sales_db.update_ar_invoice(
                    self.invoice_id, payload, self.lines_data
                )
                saved_id = self.invoice_id
            else:
                saved_id = sales_db.create_ar_invoice(
                    payload, self.lines_data
                )
                self.invoice_id = saved_id
            if self.on_saved:
                self.on_saved(saved_id)
            if self._close_after_save:
                self.destroy()
        except Exception as exc:
            messagebox.showerror(
                "Save invoice", f"Could not save invoice:\\n{exc}", parent=self
            )

    def _cancel(self) -> None:
        """Close the modal or return from an embedded invoice workspace."""
        callback = getattr(self, "on_cancel", None)
        if callback:
            callback()
        else:
            self.destroy()
    def _preview(self) -> None:
        if not self.invoice_id:
            return
        try:
            path = invoice_printer.generate_ar_invoice_pdf(self.invoice_id)
            if path and os.path.exists(path) and os.path.getsize(path) > 0:
                PdfViewerDialog(self, path, title="Invoice PDF Preview")
            else:
                raise ValueError("The invoice PDF was not generated.")
        except Exception as exc:
            messagebox.showerror(
                "Invoice PDF", f"Could not create the invoice PDF:\\n{exc}",
                parent=self,
            )


class CustomerPaymentDialog(tb.Toplevel):
    """Receive a payment and allocate it across a customer's open invoices."""

    def __init__(self, parent, company_id: int, customer_id: int, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id
        self.customer_id = customer_id
        self.customer = db.get_customer_by_id(customer_id)
        self.on_saved = on_saved
        self.home_currency = db.get_company_base_currency(company_id).upper()
        self.currency = (
            self.customer.get("currency") or self.home_currency
        ).upper()
        currency_accounts = db.get_currency_accounts(company_id, self.currency)
        self.account_lookup = {
            f"{row['account_code']} - {row['account_name']} ({row['currency']})": row["id"]
            for row in currency_accounts
        }
        self.open_invoices = [
            row
            for row in db.get_ar_invoices(
                company_id=company_id, customer_id=customer_id
            )
            if float(row.get("balance_due") or 0) > 0.001
            and row.get("status") != "Cancelled"
        ]
        self.bank_receipts = [
            row for row in sales_db.get_unapplied_bank_receipts(company_id)
            if (row.get("currency") or self.home_currency).upper() == self.currency
        ]
        self.bank_lookup = {
            (
                f"{row['transaction_date']} | {_money(row['credit_amount'])} | "
                f"{row.get('reference') or row.get('description') or 'Bank receipt'}"
            ): row
            for row in self.bank_receipts
        }
        self.allocations: dict[int, float] = {}
        self.title("Receive Customer Payment")
        self.geometry("860x650")
        self.minsize(760, 560)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._refresh()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (self.winfo_screenwidth() - width) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - height) // 2)}"
        )

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)
        footer = tb.Frame(root)
        footer.pack(side=BOTTOM, fill=X, pady=(12, 0))
        tb.Button(
            footer, text="Cancel", command=self.destroy,
            bootstyle="secondary-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            footer, text="Save payment", command=self._save,
            bootstyle="success",
        ).pack(side=RIGHT)

        tb.Label(
            root,
            text=f"Receive payment - {self.customer['name']}",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor=W)
        tb.Label(
            root,
            text="Apply across open invoices; any remainder stays as customer credit.",
            bootstyle="secondary",
        ).pack(anchor=W, pady=(0, 12))

        form = tb.Labelframe(root, text="Payment", padding=10)
        form.pack(fill=X, pady=(0, 10))
        for column in (1, 3):
            form.columnconfigure(column, weight=1)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.amount_var = tk.StringVar(value="0.00")
        self.method_var = tk.StringVar(value="Cash")
        self.reference_var = tk.StringVar()
        self.bank_var = tk.StringVar(value="New receipt / cash")
        tb.Label(form, text="Date").grid(row=0, column=0, sticky=W)
        tb.Entry(form, textvariable=self.date_var).grid(
            row=0, column=1, sticky=EW, padx=(6, 16), pady=4
        )
        tb.Label(form, text="Amount *").grid(row=0, column=2, sticky=W)
        tb.Entry(form, textvariable=self.amount_var).grid(
            row=0, column=3, sticky=EW, padx=(6, 0), pady=4
        )
        tb.Label(form, text="Method").grid(row=1, column=0, sticky=W)
        tb.Combobox(
            form,
            textvariable=self.method_var,
            values=[
                "Cash", "Cheque", "Bank Transfer", "Credit Card",
                "Undeposited Funds", "Online/Other",
            ],
            state="readonly",
        ).grid(row=1, column=1, sticky=EW, padx=(6, 16), pady=4)
        tb.Label(form, text="Reference").grid(row=1, column=2, sticky=W)
        tb.Entry(form, textvariable=self.reference_var).grid(
            row=1, column=3, sticky=EW, padx=(6, 0), pady=4
        )
        tb.Label(form, text=f"Currency: {self.currency}").grid(
            row=2, column=0, sticky=W
        )
        rate = db.get_exchange_rate(self.currency, self.home_currency)
        initial_rate = 1.0 if self.currency == self.home_currency else float(
            rate["rate"] if rate else 0
        )
        self.rate_var = tk.StringVar(
            value=f"{initial_rate:.6f}" if initial_rate else ""
        )
        tb.Label(form, text="Exchange rate").grid(row=2, column=2, sticky=W)
        rate_entry = tb.Entry(form, textvariable=self.rate_var)
        rate_entry.grid(row=2, column=3, sticky=EW, padx=(6, 0), pady=4)
        if self.currency == self.home_currency:
            rate_entry.configure(state="disabled")

        tb.Label(form, text="Deposit to account *").grid(
            row=3, column=0, sticky=W
        )
        self.account_var = tk.StringVar(value=next(iter(self.account_lookup), ""))
        tb.Combobox(
            form, textvariable=self.account_var,
            values=list(self.account_lookup), state="readonly"
        ).grid(row=3, column=1, columnspan=3, sticky=EW, padx=(6, 0), pady=4)

        tb.Label(form, text="Use imported bank receipt").grid(
            row=4, column=0, sticky=W
        )
        bank_combo = tb.Combobox(
            form,
            textvariable=self.bank_var,
            values=["New receipt / cash"] + list(self.bank_lookup),
            state="readonly",
        )
        bank_combo.grid(
            row=4, column=1, columnspan=3, sticky=EW, padx=(6, 0), pady=4
        )
        bank_combo.bind("<<ComboboxSelected>>", self._bank_selected)

        toolbar = tb.Frame(root)
        toolbar.pack(fill=X, pady=(0, 6))
        tb.Label(
            toolbar, text="Open invoices", font=("Segoe UI", 10, "bold")
        ).pack(side=LEFT)
        tb.Button(
            toolbar,
            text="Auto-apply oldest first",
            command=self._auto_allocate,
            bootstyle="primary-outline",
        ).pack(side=RIGHT)

        columns = ("id", "number", "date", "due", "balance", "apply")
        self.tree = ttk.Treeview(root, columns=columns, show="headings")
        labels = {
            "id": "#", "number": "Invoice", "date": "Date",
            "due": "Due", "balance": "Open balance", "apply": "Apply",
        }
        for column in columns:
            self.tree.heading(column, text=labels[column])
            self.tree.column(
                column,
                width=90 if column != "number" else 150,
                anchor=E if column in {"balance", "apply"} else W,
            )
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda _event: self._edit_allocation())
        action = tb.Frame(root)
        action.pack(fill=X, pady=(8, 0))
        tb.Button(
            action,
            text="Set selected allocation",
            command=self._edit_allocation,
            bootstyle="secondary-outline",
        ).pack(side=LEFT)
        self.summary_label = tb.Label(
            action, text="Applied 0.00 | Unapplied 0.00",
            font=("Segoe UI", 10, "bold"),
        )
        self.summary_label.pack(side=RIGHT)

    def _bank_selected(self, _event=None) -> None:
        row = self.bank_lookup.get(self.bank_var.get())
        if not row:
            return
        self.date_var.set(row["transaction_date"])
        self.amount_var.set(f"{float(row['credit_amount']):.2f}")
        self.reference_var.set(
            row.get("reference") or row.get("description") or ""
        )
        self.method_var.set("Bank Transfer")
        self._auto_allocate()

    def _auto_allocate(self) -> None:
        try:
            remaining = float(self.amount_var.get().replace(",", "") or 0)
        except ValueError:
            return
        self.allocations = {}
        for invoice in sorted(
            self.open_invoices, key=lambda row: (row["due_date"], row["id"])
        ):
            if remaining <= 0:
                break
            amount = min(remaining, float(invoice["balance_due"]))
            self.allocations[invoice["id"]] = round(amount, 2)
            remaining = round(remaining - amount, 2)
        self._refresh()

    def _edit_allocation(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0], "values")
        invoice_id = int(values[0])
        invoice = next(
            row for row in self.open_invoices if row["id"] == invoice_id
        )
        current = self.allocations.get(invoice_id, 0)
        from tkinter import simpledialog

        value = simpledialog.askfloat(
            "Apply payment",
            f"Amount for {invoice['invoice_number']} "
            f"(maximum {_money(invoice['balance_due'])})",
            initialvalue=current,
            minvalue=0,
            maxvalue=float(invoice["balance_due"]),
            parent=self,
        )
        if value is not None:
            self.allocations[invoice_id] = round(value, 2)
            self._refresh()

    def _refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for invoice in self.open_invoices:
            self.tree.insert("", END, values=(
                invoice["id"],
                invoice["invoice_number"],
                invoice["invoice_date"],
                invoice["due_date"],
                _money(invoice["balance_due"]),
                _money(self.allocations.get(invoice["id"], 0)),
            ))
        applied = sum(self.allocations.values())
        try:
            amount = float(self.amount_var.get().replace(",", "") or 0)
        except ValueError:
            amount = 0
        self.summary_label.configure(
            text=(
                f"Applied {_money(applied)} | "
                f"Unapplied {_money(max(0, amount - applied))}"
            )
        )

    def _save(self) -> None:
        try:
            amount = float(self.amount_var.get().replace(",", ""))
            if not self.allocations and self.open_invoices:
                self._auto_allocate()
            bank_row = self.bank_lookup.get(self.bank_var.get())
            payment_id = sales_db.create_customer_payment({
                "company_id": self.company_id,
                "customer_id": self.customer_id,
                "payment_date": self.date_var.get().strip(),
                "amount": amount,
                "payment_method": self.method_var.get(),
                "reference": self.reference_var.get().strip(),
                "bank_transaction_id": (
                    bank_row["id"] if bank_row else None
                ),
                "bank_account_id": (
                    bank_row["bank_account_id"] if bank_row else None
                ),
                "currency": self.currency,
                "exchange_rate": self.rate_var.get(),
                "payment_account_id": self.account_lookup.get(
                    self.account_var.get()
                ),
                "created_by": "User",
            }, [
                {"invoice_id": invoice_id, "amount": allocation}
                for invoice_id, allocation in self.allocations.items()
                if allocation > 0
            ])
            if self.on_saved:
                self.on_saved(payment_id)
            self.destroy()
        except Exception as exc:
            messagebox.showerror(
                "Receive payment", f"Could not record payment:\\n{exc}",
                parent=self,
            )


class ApplyCustomerCreditDialog(tb.Toplevel):
    """Apply an existing unapplied receipt to a selected customer's invoice."""

    def __init__(self, parent, company_id: int, customer_id: int, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id
        self.customer_id = customer_id
        self.on_saved = on_saved
        self.payments = sales_db.get_customer_payments(
            company_id, customer_id, unapplied_only=True
        )
        self.invoices = [
            row for row in db.get_ar_invoices(
                company_id=company_id, customer_id=customer_id
            )
            if float(row.get("balance_due") or 0) > 0.001
            and row.get("status") != "Cancelled"
        ]
        self.payment_lookup = {
            (
                f"{row['payment_date']} | {row.get('reference') or 'Receipt'} | "
                f"Credit {_money(row['unapplied_amount'])}"
            ): row
            for row in self.payments
        }
        self.invoice_lookup = {
            (
                f"{row['invoice_number']} | Due {_money(row['balance_due'])}"
            ): row
            for row in self.invoices
        }
        self.title("Apply Customer Credit")
        self.geometry("640x330")
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (self.winfo_screenwidth() - width) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - height) // 2)}"
        )

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=18)
        root.pack(fill=BOTH, expand=True)
        tb.Label(
            root, text="Apply unapplied customer receipt",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor=W)
        tb.Label(
            root,
            text="Move an existing customer credit to an open invoice.",
            bootstyle="secondary",
        ).pack(anchor=W, pady=(0, 15))
        form = tb.Frame(root)
        form.pack(fill=X)
        form.columnconfigure(1, weight=1)
        self.payment_var = tk.StringVar()
        self.invoice_var = tk.StringVar()
        self.amount_var = tk.StringVar(value="0.00")
        tb.Label(form, text="Available credit").grid(
            row=0, column=0, sticky=W, pady=7
        )
        payment_combo = tb.Combobox(
            form,
            textvariable=self.payment_var,
            values=list(self.payment_lookup),
            state="readonly",
        )
        payment_combo.grid(row=0, column=1, sticky=EW, padx=(10, 0), pady=7)
        tb.Label(form, text="Open invoice").grid(
            row=1, column=0, sticky=W, pady=7
        )
        invoice_combo = tb.Combobox(
            form,
            textvariable=self.invoice_var,
            values=list(self.invoice_lookup),
            state="readonly",
        )
        invoice_combo.grid(row=1, column=1, sticky=EW, padx=(10, 0), pady=7)
        tb.Label(form, text="Amount").grid(
            row=2, column=0, sticky=W, pady=7
        )
        tb.Entry(form, textvariable=self.amount_var).grid(
            row=2, column=1, sticky=EW, padx=(10, 0), pady=7
        )
        if self.payment_lookup:
            self.payment_var.set(next(iter(self.payment_lookup)))
        if self.invoice_lookup:
            self.invoice_var.set(next(iter(self.invoice_lookup)))
        buttons = tb.Frame(root)
        buttons.pack(side=BOTTOM, fill=X)
        tb.Button(
            buttons, text="Cancel", command=self.destroy,
            bootstyle="secondary-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            buttons, text="Apply credit", command=self._apply,
            bootstyle="success",
        ).pack(side=RIGHT)

    def _apply(self) -> None:
        try:
            payment = self.payment_lookup.get(self.payment_var.get())
            invoice = self.invoice_lookup.get(self.invoice_var.get())
            if not payment or not invoice:
                raise ValueError("Select a credit and an open invoice.")
            amount = float(self.amount_var.get().replace(",", ""))
            sales_db.apply_customer_payment(
                payment["id"],
                [{"invoice_id": invoice["id"], "amount": amount}],
            )
            if self.on_saved:
                self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror(
                "Apply credit", f"Could not apply credit:\\n{exc}", parent=self
            )


class ARReceiptDialog(CustomerPaymentDialog):
    """Compatibility wrapper for the former single-invoice receipt dialog."""

    def __init__(self, parent, invoice_id: int, on_saved=None):
        invoice = db.get_ar_invoice(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found.")
        header = invoice["invoice"]
        super().__init__(
            parent,
            header["company_id"],
            header["customer_id"],
            on_saved=on_saved,
        )


class ARInvoiceListDialog(tb.Toplevel):
    """Customer Centre with customer-specific invoice and payment activity."""

    def __init__(
        self,
        parent,
        company_id: int | None = None,
        customer_id_filter: int | None = None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.initial_customer_id = customer_id_filter
        self.open_invoice_callback = None
        self.on_customer_changed = None
        self.on_close = None
        self.selected_customer_id: int | None = None
        self.customers: list[dict] = []
        company = db.get_company(self.company_id) or {}
        self.title(
            f"Customer Centre - {company.get('name', 'Company')}"
        )
        self.geometry("1240x720")
        self.minsize(1020, 600)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._load_customers()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width, height = self.winfo_width(), self.winfo_height()
        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (self.winfo_screenwidth() - width) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - height) // 2)}"
        )

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=12)
        root.pack(fill=BOTH, expand=True)
        footer = tb.Frame(root)
        footer.pack(side=BOTTOM, fill=X, pady=(10, 0))
        tb.Button(
            footer, text="Close", command=self._close,
            bootstyle="secondary",
        ).pack(side=RIGHT)
        tb.Button(
            footer, text="Edit / View invoice", command=self._edit_invoice,
            bootstyle="primary-outline",
        ).pack(side=LEFT, padx=(0, 6))
        tb.Button(
            footer, text="Print / Preview", command=self._print_invoice,
            bootstyle="info-outline",
        ).pack(side=LEFT, padx=(0, 6))
        tb.Button(
            footer, text="Delete", command=self._delete_invoice,
            bootstyle="danger-outline",
        ).pack(side=LEFT)

        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 10))
        title = tb.Frame(header)
        title.pack(side=LEFT)
        tb.Label(
            title, text="Customer Centre", font=("Segoe UI", 17, "bold")
        ).pack(anchor=W)
        tb.Label(
            title,
            text="Customers, invoices, receipts and open balances in one place.",
            bootstyle="secondary",
        ).pack(anchor=W)
        tb.Button(
            header, text="+ New invoice", command=self._new_invoice,
            bootstyle="success",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            header, text="+ New customer", command=self._new_customer,
            bootstyle="success-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            header, text="Receive payment", command=self._receive_payment,
            bootstyle="primary",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            header, text="Apply credit", command=self._apply_credit,
            bootstyle="warning-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            header, text="Products & Services", command=self._items,
            bootstyle="secondary-outline",
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            header, text="AR Aging", command=self._aging,
            bootstyle="info-outline",
        ).pack(side=RIGHT)

        body = ttk.Panedwindow(root, orient=HORIZONTAL)
        body.pack(fill=BOTH, expand=True)

        customer_panel = tb.Frame(body, padding=(0, 0, 10, 0))
        body.add(customer_panel, weight=1)
        tb.Label(
            customer_panel, text="Customers", font=("Segoe UI", 11, "bold")
        ).pack(anchor=W)
        self.customer_search_var = tk.StringVar()
        self.customer_search_var.trace_add(
            "write", lambda *_args: self._load_customers()
        )
        tb.Entry(
            customer_panel,
            textvariable=self.customer_search_var,
        ).pack(fill=X, pady=(6, 8))
        customer_columns = ("id", "name", "balance")
        self.customer_tree = ttk.Treeview(
            customer_panel,
            columns=customer_columns,
            show="headings",
            selectmode="browse",
        )
        self.customer_tree.heading("id", text="#")
        self.customer_tree.heading("name", text="Customer")
        self.customer_tree.heading("balance", text="Open balance")
        self.customer_tree.column("id", width=38, stretch=False)
        self.customer_tree.column("name", width=170)
        self.customer_tree.column("balance", width=100, anchor=E)
        self.customer_tree.pack(fill=BOTH, expand=True)
        self.customer_tree.bind(
            "<<TreeviewSelect>>", lambda _event: self._customer_changed()
        )

        activity = tb.Frame(body)
        body.add(activity, weight=4)
        self.customer_heading = tb.Label(
            activity, text="Select a customer", font=("Segoe UI", 13, "bold")
        )
        self.customer_heading.pack(anchor=W)

        self.kpi_frame = tb.Frame(activity)
        self.kpi_frame.pack(fill=X, pady=(8, 10))
        self.invoiced_label = self._kpi(
            self.kpi_frame, "Invoiced", "LKR 0.00", "info"
        )
        self.received_label = self._kpi(
            self.kpi_frame, "Received", "LKR 0.00", "success"
        )
        self.due_label = self._kpi(
            self.kpi_frame, "Open balance", "LKR 0.00", "warning"
        )
        self.credit_label = self._kpi(
            self.kpi_frame, "Unapplied credit", "LKR 0.00", "primary"
        )

        toolbar = tb.Frame(activity)
        toolbar.pack(fill=X, pady=(0, 8))
        tb.Label(toolbar, text="Invoices").pack(side=LEFT)
        self.status_var = tk.StringVar(value="All")
        status_combo = tb.Combobox(
            toolbar,
            textvariable=self.status_var,
            values=["All", "Open", "Closed", "Overdue"],
            state="readonly",
            width=13,
        )
        status_combo.pack(side=LEFT, padx=(6, 12))
        status_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._load_invoices()
        )
        self.period_var = tk.StringVar(value="This Year")
        period_combo = tb.Combobox(
            toolbar,
            textvariable=self.period_var,
            values=["This Year", "This Month", "Last Year", "All Time"],
            state="readonly",
            width=14,
        )
        period_combo.pack(side=LEFT)
        period_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._load_invoices()
        )
        self.search_var = tk.StringVar()
        self.search_var.trace_add(
            "write", lambda *_args: self._load_invoices()
        )
        tb.Entry(
            toolbar,
            textvariable=self.search_var,
            width=24,
        ).pack(side=RIGHT)
        tb.Label(toolbar, text="Find").pack(side=RIGHT, padx=(0, 6))

        columns = (
            "id", "number", "date", "due", "amount",
            "paid", "balance", "status",
        )
        self.invoice_tree = ttk.Treeview(
            activity, columns=columns, show="headings", selectmode="browse"
        )
        headings = {
            "id": "#",
            "number": "Invoice",
            "date": "Date",
            "due": "Due date",
            "amount": "Amount",
            "paid": "Paid",
            "balance": "Open balance",
            "status": "Status",
        }
        for column in columns:
            self.invoice_tree.heading(column, text=headings[column])
            self.invoice_tree.column(
                column,
                width=80 if column == "id" else 115,
                anchor=E if column in {"amount", "paid", "balance"} else W,
            )
        self.invoice_tree.pack(fill=BOTH, expand=True)
        self.invoice_tree.bind(
            "<Double-1>", lambda _event: self._edit_invoice()
        )

    def _kpi(self, parent, title: str, value: str, style: str):
        card = tb.Frame(parent, bootstyle=style, padding=9)
        card.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(
            card, text=title, bootstyle=f"{style}-inverse"
        ).pack(anchor=W)
        label = tb.Label(
            card,
            text=value,
            font=("Segoe UI", 11, "bold"),
            bootstyle=f"{style}-inverse",
        )
        label.pack(anchor=W)
        return label

    def _load_customers(self) -> None:
        selected = self.selected_customer_id or self.initial_customer_id
        self.customers = db.get_customers(
            company_id=self.company_id,
            active_only=False,
            search=self.customer_search_var.get().strip() or None,
        )
        for item in self.customer_tree.get_children():
            self.customer_tree.delete(item)
        select_item = None
        for customer in self.customers:
            item = self.customer_tree.insert("", END, values=(
                customer["id"],
                customer["name"],
                _money(customer.get("balance_due")),
            ))
            if customer["id"] == selected:
                select_item = item
        if not select_item and self.customer_tree.get_children():
            select_item = self.customer_tree.get_children()[0]
        if select_item:
            self.customer_tree.selection_set(select_item)
            self.customer_tree.focus(select_item)
            self.customer_tree.see(select_item)
            self._customer_changed()
        else:
            self.selected_customer_id = None
            self._load_invoices()

    def _customer_changed(self) -> None:
        selection = self.customer_tree.selection()
        if not selection:
            return
        self.selected_customer_id = int(
            self.customer_tree.item(selection[0], "values")[0]
        )
        customer = next(
            (
                row for row in self.customers
                if row["id"] == self.selected_customer_id
            ),
            None,
        )
        self.customer_heading.configure(
            text=customer["name"] if customer else "Customer"
        )
        self._load_invoices()

    def _date_range(self) -> tuple[str | None, str | None]:
        today = datetime.now()
        period = self.period_var.get()
        if period == "This Year":
            return f"{today.year}-01-01", f"{today.year}-12-31"
        if period == "This Month":
            start = today.replace(day=1)
            next_month = (
                start.replace(year=start.year + 1, month=1)
                if start.month == 12
                else start.replace(month=start.month + 1)
            )
            return start.strftime("%Y-%m-%d"), (
                next_month - timedelta(days=1)
            ).strftime("%Y-%m-%d")
        if period == "Last Year":
            year = today.year - 1
            return f"{year}-01-01", f"{year}-12-31"
        return None, None

    def _load_invoices(self) -> None:
        for item in self.invoice_tree.get_children():
            self.invoice_tree.delete(item)
        if not self.selected_customer_id:
            rows = []
        else:
            start, end = self._date_range()
            rows = db.get_ar_invoices(
                company_id=self.company_id,
                customer_id=self.selected_customer_id,
                start_date=start,
                end_date=end,
                search=self.search_var.get().strip() or None,
            )
        status_filter = self.status_var.get()
        if status_filter == "Open":
            rows = [
                row for row in rows
                if row["status"] not in {"Paid", "Cancelled"}
                and float(row["balance_due"]) > 0.001
            ]
        elif status_filter == "Closed":
            rows = [
                row for row in rows
                if row["status"] in {"Paid", "Cancelled"}
                or float(row["balance_due"]) <= 0.001
            ]
        elif status_filter == "Overdue":
            rows = [row for row in rows if row.get("is_overdue")]
        for invoice in rows:
            display_status = (
                "Overdue" if invoice.get("is_overdue")
                else invoice["status"]
            )
            self.invoice_tree.insert("", END, values=(
                invoice["id"],
                invoice["invoice_number"],
                invoice["invoice_date"],
                invoice["due_date"],
                _money(invoice["total_amount"]),
                _money(invoice["paid_amount"]),
                _money(invoice["balance_due"]),
                display_status,
            ))
        all_rows = (
            db.get_ar_invoices(
                company_id=self.company_id,
                customer_id=self.selected_customer_id,
            )
            if self.selected_customer_id else []
        )
        invoiced = sum(
            float(row["total_amount"]) for row in all_rows
            if row["status"] != "Cancelled"
        )
        received = sum(
            float(row["paid_amount"]) for row in all_rows
            if row["status"] != "Cancelled"
        )
        due = sum(
            max(0, float(row["balance_due"])) for row in all_rows
            if row["status"] != "Cancelled"
        )
        credit = sum(
            float(row["unapplied_amount"])
            for row in sales_db.get_customer_payments(
                self.company_id,
                self.selected_customer_id,
                unapplied_only=True,
            )
        ) if self.selected_customer_id else 0
        self.invoiced_label.configure(text=f"LKR {_money(invoiced)}")
        self.received_label.configure(text=f"LKR {_money(received)}")
        self.due_label.configure(text=f"LKR {_money(due)}")
        self.credit_label.configure(text=f"LKR {_money(credit)}")

    def _selected_invoice_id(self) -> int | None:
        selection = self.invoice_tree.selection()
        if not selection:
            messagebox.showinfo(
                "Select invoice", "Select an invoice first.", parent=self
            )
            return None
        return int(self.invoice_tree.item(selection[0], "values")[0])

    def _new_invoice(self) -> None:
        if self.open_invoice_callback:
            self.open_invoice_callback(None, self.selected_customer_id)
            return
        ARInvoiceEntryDialog(
            self,
            company_id=self.company_id,
            customer_id=self.selected_customer_id,
            on_saved=lambda _invoice_id: self._reload_all(),
            on_customer_changed=lambda _customer_id: self._reload_all(),
        )

    def _edit_invoice(self) -> None:
        invoice_id = self._selected_invoice_id()
        if not invoice_id:
            return
        if self.open_invoice_callback:
            self.open_invoice_callback(invoice_id, self.selected_customer_id)
            return
        ARInvoiceEntryDialog(
            self,
            company_id=self.company_id,
            invoice_id=invoice_id,
            on_saved=lambda _invoice_id: self._reload_all(),
            on_customer_changed=lambda _customer_id: self._reload_all(),
        )

    def _new_customer(self) -> None:
        from ui.customer_manager import CustomerEditModal

        def saved(customer_id: int) -> None:
            self.initial_customer_id = customer_id
            self.selected_customer_id = customer_id
            self._load_customers()
            if self.on_customer_changed:
                self.on_customer_changed(customer_id)

        CustomerEditModal(self, company_id=self.company_id, on_saved=saved)

    def _close(self) -> None:
        if self.on_close:
            self.on_close()
        else:
            self.destroy()

    def _receive_payment(self) -> None:
        if not self.selected_customer_id:
            messagebox.showinfo(
                "Select customer", "Select a customer first.", parent=self
            )
            return
        CustomerPaymentDialog(
            self,
            self.company_id,
            self.selected_customer_id,
            on_saved=lambda _payment_id: self._reload_all(),
        )

    def _apply_credit(self) -> None:
        if not self.selected_customer_id:
            messagebox.showinfo(
                "Select customer", "Select a customer first.", parent=self
            )
            return
        payments = sales_db.get_customer_payments(
            self.company_id,
            self.selected_customer_id,
            unapplied_only=True,
        )
        if not payments:
            messagebox.showinfo(
                "Customer credit",
                "This customer has no unapplied receipts.",
                parent=self,
            )
            return
        ApplyCustomerCreditDialog(
            self,
            self.company_id,
            self.selected_customer_id,
            on_saved=self._reload_all,
        )

    def _items(self) -> None:
        ProductsServicesDialog(self, self.company_id)

    def _print_invoice(self) -> None:
        invoice_id = self._selected_invoice_id()
        if not invoice_id:
            return
        try:
            path = invoice_printer.generate_ar_invoice_pdf(invoice_id)
            if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
                raise ValueError("The invoice PDF was not generated.")
            PdfViewerDialog(self, path, title="Invoice PDF Preview")
        except Exception as exc:
            messagebox.showerror(
                "Invoice PDF", f"Could not create the invoice PDF:\\n{exc}",
                parent=self,
            )

    def _delete_invoice(self) -> None:
        invoice_id = self._selected_invoice_id()
        if not invoice_id:
            return
        if not messagebox.askyesno(
            "Delete invoice",
            "Delete this invoice? Posted receipts protect an invoice from deletion.",
            parent=self,
        ):
            return
        ok, message = sales_db.delete_ar_invoice(invoice_id)
        if not ok:
            messagebox.showwarning("Delete invoice", message, parent=self)
        self._reload_all()

    def _aging(self) -> None:
        ARAgingDialog(self, self.company_id)

    def _reload_all(self) -> None:
        self.initial_customer_id = self.selected_customer_id
        self._load_customers()


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
