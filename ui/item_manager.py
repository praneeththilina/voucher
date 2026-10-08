"""Product and service item centre with ledger and inventory links."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk

import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import sales_database as sales_db


class ItemEditDialog(tb.Toplevel):
    """Create or edit one service, non-inventory, or inventory item."""

    def __init__(
        self,
        parent,
        company_id: int,
        item_id: int | None = None,
        on_saved=None,
    ):
        super().__init__(parent)
        self.company_id = company_id
        self.item_id = item_id
        self.on_saved = on_saved
        self.item = sales_db.get_sales_item(item_id) if item_id else {}
        self.preferences = sales_db.get_sales_preferences(company_id)
        self.accounts = db.get_chart_of_accounts(
            company_id=company_id, active_only=True
        )
        self.tax_rates = db.get_tax_rates(
            company_id=company_id, active_only=True
        )
        self.account_lookup = {
            f"{row['account_code']} - {row['account_name']}": row
            for row in self.accounts
        }
        self.tax_lookup = {
            f"{row['name']} ({float(row['rate']) * 100:g}%)": row
            for row in self.tax_rates
        }

        self.title("Edit Product / Service" if item_id else "New Product / Service")
        self.geometry("760x650")
        self.minsize(680, 580)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._load_item()
        self._toggle_inventory_fields()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x_pos = max(0, (self.winfo_screenwidth() - width) // 2)
        y_pos = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=18)
        root.pack(fill=BOTH, expand=True)

        footer = tb.Frame(root)
        footer.pack(side=BOTTOM, fill=X, pady=(14, 0))
        tb.Button(
            footer,
            text="Cancel",
            bootstyle="secondary-outline",
            command=self.destroy,
        ).pack(side=RIGHT, padx=(6, 0))
        tb.Button(
            footer,
            text="Save Item",
            bootstyle="success",
            command=self._save,
        ).pack(side=RIGHT)

        tb.Label(
            root,
            text="Product & Service Item",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor=W)
        tb.Label(
            root,
            text=(
                "Link every sales item to its revenue ledger, tax rate, and "
                "inventory accounts where applicable."
            ),
            bootstyle="secondary",
        ).pack(anchor=W, pady=(0, 14))

        form = tb.Frame(root)
        form.pack(fill=BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        self.type_var = tk.StringVar(value="Service")
        types = ["Service", "Non-inventory"]
        if (
            self.preferences["inventory_enabled"]
            or self.item.get("item_type") == "Inventory"
        ):
            types.append("Inventory")
        tb.Label(form, text="Type *").grid(row=0, column=0, sticky=W, pady=5)
        self.type_combo = tb.Combobox(
            form,
            textvariable=self.type_var,
            values=types,
            state="readonly",
            width=22,
        )
        self.type_combo.grid(row=0, column=1, sticky=EW, padx=(8, 18), pady=5)
        self.type_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._toggle_inventory_fields()
        )

        self.name_var = tk.StringVar()
        tb.Label(form, text="Name *").grid(row=0, column=2, sticky=W, pady=5)
        self.name_entry = tb.Entry(form, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=3, sticky=EW, padx=(8, 0), pady=5)

        self.sku_var = tk.StringVar()
        tb.Label(form, text="SKU / Code").grid(row=1, column=0, sticky=W, pady=5)
        tb.Entry(form, textvariable=self.sku_var).grid(
            row=1, column=1, sticky=EW, padx=(8, 18), pady=5
        )

        self.price_var = tk.StringVar(value="0.00")
        tb.Label(form, text="Sales price").grid(row=1, column=2, sticky=W, pady=5)
        tb.Entry(form, textvariable=self.price_var).grid(
            row=1, column=3, sticky=EW, padx=(8, 0), pady=5
        )

        self.description_var = tk.StringVar()
        tb.Label(form, text="Sales description").grid(
            row=2, column=0, sticky=W, pady=5
        )
        tb.Entry(form, textvariable=self.description_var).grid(
            row=2, column=1, columnspan=3, sticky=EW, padx=(8, 0), pady=5
        )

        income_accounts = [
            name
            for name, row in self.account_lookup.items()
            if row["account_type"] in ("Income", "Revenue")
        ]
        self.income_var = tk.StringVar()
        tb.Label(form, text="Income account *").grid(
            row=3, column=0, sticky=W, pady=5
        )
        self.income_combo = tb.Combobox(
            form,
            textvariable=self.income_var,
            values=income_accounts,
            state="readonly",
        )
        self.income_combo.grid(
            row=3, column=1, columnspan=3, sticky=EW, padx=(8, 0), pady=5
        )
        if income_accounts:
            self.income_var.set(income_accounts[0])

        self.taxable_var = tk.BooleanVar(value=True)
        tb.Checkbutton(
            form,
            text="Taxable sale",
            variable=self.taxable_var,
            bootstyle="round-toggle",
        ).grid(row=4, column=0, sticky=W, pady=7)
        self.tax_var = tk.StringVar()
        tb.Label(form, text="Default VAT / tax").grid(
            row=4, column=2, sticky=W, pady=5
        )
        self.tax_combo = tb.Combobox(
            form,
            textvariable=self.tax_var,
            values=list(self.tax_lookup),
            state="readonly",
        )
        self.tax_combo.grid(row=4, column=3, sticky=EW, padx=(8, 0), pady=5)
        if self.tax_lookup:
            default_name = next(
                (
                    name
                    for name, row in self.tax_lookup.items()
                    if row.get("is_default")
                ),
                next(iter(self.tax_lookup)),
            )
            self.tax_var.set(default_name)

        ttk.Separator(form).grid(
            row=5, column=0, columnspan=4, sticky=EW, pady=12
        )
        self.inventory_title = tb.Label(
            form,
            text="Inventory & purchasing",
            font=("Segoe UI", 10, "bold"),
        )
        self.inventory_title.grid(row=6, column=0, columnspan=4, sticky=W)

        self.cost_var = tk.StringVar(value="0.00")
        self.qty_var = tk.StringVar(value="0.00")
        self.reorder_var = tk.StringVar(value="0.00")
        self.as_of_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.asset_var = tk.StringVar()
        self.cogs_var = tk.StringVar()

        asset_accounts = [
            name
            for name, row in self.account_lookup.items()
            if row["account_type"] == "Asset"
        ]
        expense_accounts = [
            name
            for name, row in self.account_lookup.items()
            if row["account_type"] == "Expense"
        ]

        self.inventory_widgets = []
        for label, row, column in (
            ("Purchase cost", 7, 0),
            ("Quantity on hand", 7, 2),
            ("Reorder point", 8, 0),
            ("Quantity as of", 8, 2),
            ("Inventory asset account", 9, 0),
            ("COGS account", 10, 0),
        ):
            widget = tb.Label(form, text=label)
            widget.grid(row=row, column=column, sticky=W, pady=5)
            self.inventory_widgets.append(widget)

        self.cost_entry = tb.Entry(form, textvariable=self.cost_var)
        self.cost_entry.grid(row=7, column=1, sticky=EW, padx=(8, 18), pady=5)
        self.qty_entry = tb.Entry(form, textvariable=self.qty_var)
        self.qty_entry.grid(row=7, column=3, sticky=EW, padx=(8, 0), pady=5)
        self.reorder_entry = tb.Entry(form, textvariable=self.reorder_var)
        self.reorder_entry.grid(row=8, column=1, sticky=EW, padx=(8, 18), pady=5)
        self.as_of_entry = tb.Entry(form, textvariable=self.as_of_var)
        self.as_of_entry.grid(row=8, column=3, sticky=EW, padx=(8, 0), pady=5)
        self.asset_combo = tb.Combobox(
            form,
            textvariable=self.asset_var,
            values=asset_accounts,
            state="readonly",
        )
        self.asset_combo.grid(
            row=9, column=1, columnspan=3, sticky=EW, padx=(8, 0), pady=5
        )
        self.cogs_combo = tb.Combobox(
            form,
            textvariable=self.cogs_var,
            values=expense_accounts,
            state="readonly",
        )
        self.cogs_combo.grid(
            row=10, column=1, columnspan=3, sticky=EW, padx=(8, 0), pady=5
        )
        self.inventory_widgets.extend(
            [
                self.cost_entry,
                self.qty_entry,
                self.reorder_entry,
                self.as_of_entry,
                self.asset_combo,
                self.cogs_combo,
            ]
        )
        self.active_var = tk.BooleanVar(value=True)
        tb.Checkbutton(
            form,
            text="Active item",
            variable=self.active_var,
            bootstyle="round-toggle",
        ).grid(row=11, column=1, sticky=W, pady=(12, 0))

    def _select_account(self, variable: tk.StringVar, account_id: object) -> None:
        for name, account in self.account_lookup.items():
            if account["id"] == account_id:
                variable.set(name)
                return

    def _load_item(self) -> None:
        if not self.item:
            self._select_account(
                self.asset_var,
                (db.get_account_by_code("1310", self.company_id) or {}).get("id"),
            )
            self._select_account(
                self.cogs_var,
                (db.get_account_by_code("5110", self.company_id) or {}).get("id"),
            )
            self.name_entry.focus_set()
            return
        self.type_var.set(self.item.get("item_type", "Service"))
        self.name_var.set(self.item.get("name", ""))
        self.sku_var.set(self.item.get("sku", ""))
        self.description_var.set(self.item.get("description", ""))
        self.price_var.set(f"{float(self.item.get('sales_price') or 0):.2f}")
        self.cost_var.set(f"{float(self.item.get('purchase_cost') or 0):.2f}")
        self.qty_var.set(f"{float(self.item.get('quantity_on_hand') or 0):.2f}")
        self.reorder_var.set(f"{float(self.item.get('reorder_point') or 0):.2f}")
        self.as_of_var.set(self.item.get("as_of_date", ""))
        self.taxable_var.set(bool(self.item.get("taxable", 1)))
        self.active_var.set(bool(self.item.get("is_active", 1)))
        self._select_account(self.income_var, self.item.get("income_account_id"))
        self._select_account(
            self.asset_var, self.item.get("inventory_asset_account_id")
        )
        self._select_account(self.cogs_var, self.item.get("cogs_account_id"))
        for name, rate in self.tax_lookup.items():
            if rate["id"] == self.item.get("tax_rate_id"):
                self.tax_var.set(name)
                break

    def _toggle_inventory_fields(self) -> None:
        state = "normal" if self.type_var.get() == "Inventory" else "disabled"
        for widget in self.inventory_widgets:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _save(self) -> None:
        try:
            income = self.account_lookup.get(self.income_var.get())
            if not income:
                raise ValueError("Select an income account.")
            tax_rate = self.tax_lookup.get(self.tax_var.get())
            asset = self.account_lookup.get(self.asset_var.get())
            cogs = self.account_lookup.get(self.cogs_var.get())
            payload = {
                "company_id": self.company_id,
                "name": self.name_var.get().strip(),
                "sku": self.sku_var.get().strip(),
                "item_type": self.type_var.get(),
                "description": self.description_var.get().strip(),
                "sales_price": float(self.price_var.get() or 0),
                "income_account_id": income["id"],
                "taxable": self.taxable_var.get(),
                "tax_rate_id": tax_rate["id"] if tax_rate else None,
                "purchase_cost": float(self.cost_var.get() or 0),
                "inventory_asset_account_id": (
                    asset["id"] if asset and self.type_var.get() == "Inventory"
                    else None
                ),
                "cogs_account_id": (
                    cogs["id"] if cogs and self.type_var.get() == "Inventory"
                    else None
                ),
                "quantity_on_hand": float(self.qty_var.get() or 0),
                "reorder_point": float(self.reorder_var.get() or 0),
                "as_of_date": self.as_of_var.get().strip(),
                "is_active": self.active_var.get(),
            }
            saved_id = sales_db.save_sales_item(
                payload, item_id=self.item_id
            )
            if self.on_saved:
                self.on_saved(saved_id)
            self.destroy()
        except (ValueError, TypeError) as exc:
            messagebox.showwarning("Check item", str(exc), parent=self)
        except Exception as exc:
            messagebox.showerror(
                "Save item", f"Could not save item: {exc}", parent=self
            )


class ProductsServicesDialog(tb.Toplevel):
    """QuickBooks-style product and service item centre."""

    def __init__(self, parent, company_id: int | None = None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Products & Services")
        self.geometry("1120x660")
        self.minsize(900, 520)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._load_items()
        self._center()

    def _center(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        self.geometry(
            f"{width}x{height}+"
            f"{max(0, (self.winfo_screenwidth() - width) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - height) // 2)}"
        )

    def _build_ui(self) -> None:
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)
        footer = tb.Frame(root)
        footer.pack(side=BOTTOM, fill=X, pady=(10, 0))
        tb.Button(
            footer,
            text="Close",
            bootstyle="secondary",
            command=self.destroy,
        ).pack(side=RIGHT)
        tb.Button(
            footer,
            text="Edit",
            bootstyle="primary-outline",
            command=self._edit,
        ).pack(side=LEFT, padx=(0, 6))
        tb.Button(
            footer,
            text="Make inactive",
            bootstyle="danger-outline",
            command=self._deactivate,
        ).pack(side=LEFT)

        header = tb.Frame(root)
        header.pack(fill=X, pady=(0, 12))
        tb.Label(
            header,
            text="Products & Services",
            font=("Segoe UI", 16, "bold"),
        ).pack(side=LEFT)
        tb.Button(
            header,
            text="+ New item",
            bootstyle="success",
            command=self._new,
        ).pack(side=RIGHT)

        toolbar = tb.Frame(root)
        toolbar.pack(fill=X, pady=(0, 10))
        tb.Label(toolbar, text="Find").pack(side=LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._load_items())
        tb.Entry(toolbar, textvariable=self.search_var, width=30).pack(
            side=LEFT, padx=(6, 16)
        )
        tb.Label(toolbar, text="Type").pack(side=LEFT)
        self.type_var = tk.StringVar(value="All")
        type_combo = tb.Combobox(
            toolbar,
            textvariable=self.type_var,
            values=["All", "Service", "Non-inventory", "Inventory"],
            state="readonly",
            width=18,
        )
        type_combo.pack(side=LEFT, padx=6)
        type_combo.bind("<<ComboboxSelected>>", lambda _event: self._load_items())
        prefs = sales_db.get_sales_preferences(self.company_id)
        state_text = (
            "Inventory tracking: ON"
            if prefs["inventory_enabled"]
            else "Inventory tracking: OFF (enable in Preferences)"
        )
        tb.Label(
            toolbar,
            text=state_text,
            bootstyle="success" if prefs["inventory_enabled"] else "warning",
        ).pack(side=RIGHT)

        frame = tb.Frame(root)
        frame.pack(fill=BOTH, expand=True)
        columns = (
            "id", "name", "sku", "type", "price", "income",
            "tax", "onhand", "reorder", "status",
        )
        self.tree = ttk.Treeview(
            frame, columns=columns, show="headings", selectmode="browse"
        )
        headers = {
            "id": "#",
            "name": "Name",
            "sku": "SKU",
            "type": "Type",
            "price": "Sales price",
            "income": "Income account",
            "tax": "VAT / tax",
            "onhand": "On hand",
            "reorder": "Reorder",
            "status": "Status",
        }
        widths = {
            "id": 45, "name": 190, "sku": 90, "type": 110, "price": 100,
            "income": 190, "tax": 115, "onhand": 85, "reorder": 80,
            "status": 70,
        }
        for column in columns:
            self.tree.heading(column, text=headers[column])
            self.tree.column(
                column,
                width=widths[column],
                stretch=column in {"name", "income"},
                anchor=E if column in {"price", "onhand", "reorder"} else W,
            )
        scrollbar = tb.Scrollbar(
            frame, orient=VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.tree.bind("<Double-1>", lambda _event: self._edit())

    def _load_items(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        item_type = None if self.type_var.get() == "All" else self.type_var.get()
        rows = sales_db.get_sales_items(
            company_id=self.company_id,
            active_only=False,
            search=self.search_var.get().strip() or None,
            item_type=item_type,
        )
        for item in rows:
            tax_text = (
                f"{float(item.get('tax_rate') or 0) * 100:g}%"
                if item.get("taxable")
                else "Non-taxable"
            )
            self.tree.insert("", END, values=(
                item["id"],
                item["name"],
                item.get("sku") or "",
                item["item_type"],
                f"{float(item.get('sales_price') or 0):,.2f}",
                (
                    f"{item.get('income_account_code') or ''} "
                    f"{item.get('income_account_name') or ''}"
                ).strip(),
                tax_text,
                (
                    f"{float(item.get('quantity_on_hand') or 0):,.2f}"
                    if item["item_type"] == "Inventory" else "-"
                ),
                (
                    f"{float(item.get('reorder_point') or 0):,.2f}"
                    if item["item_type"] == "Inventory" else "-"
                ),
                "Active" if item.get("is_active") else "Inactive",
            ))

    def _selected_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Select item", "Select a product or service first.", parent=self
            )
            return None
        return int(self.tree.item(selection[0], "values")[0])

    def _new(self) -> None:
        ItemEditDialog(
            self,
            self.company_id,
            on_saved=lambda _item_id: self._load_items(),
        )

    def _edit(self) -> None:
        item_id = self._selected_id()
        if item_id:
            ItemEditDialog(
                self,
                self.company_id,
                item_id=item_id,
                on_saved=lambda _item_id: self._load_items(),
            )

    def _deactivate(self) -> None:
        item_id = self._selected_id()
        if not item_id:
            return
        if messagebox.askyesno(
            "Make inactive",
            "Hide this item from new invoices? Existing invoices remain unchanged.",
            parent=self,
        ):
            sales_db.deactivate_sales_item(item_id)
            self._load_items()
