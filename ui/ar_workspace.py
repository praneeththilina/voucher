"""Embedded full-window AR workspaces used by the main application notebook."""

from __future__ import annotations

import ttkbootstrap as tb
from ttkbootstrap.constants import BOTH

import database as db
import sales_database as sales_db
from ui.ar_invoice_dialog import ARInvoiceEntryDialog, ARInvoiceListDialog


class ARInvoiceEntryFrame(tb.Frame):
    """Full-size invoice editor that shares the proven dialog implementation."""

    def __init__(
        self,
        parent,
        company_id: int | None = None,
        invoice_id: int | None = None,
        customer_id: int | None = None,
        on_saved=None,
        on_cancel=None,
        on_customer_changed=None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.invoice_id = invoice_id
        self.on_saved = on_saved
        self.on_cancel = on_cancel
        self.on_customer_changed = on_customer_changed
        self._close_after_save = False
        self.preselected_customer_id = customer_id
        self.preferences = sales_db.get_sales_preferences(self.company_id)
        self.home_currency = db.get_company_base_currency(
            self.company_id
        ).upper()
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
        self._reload_reference_data()
        self._build_ui()
        if invoice_id:
            self._load_invoice()
        else:
            self._set_defaults()

    @staticmethod
    def _item_display(item: dict) -> str:
        return ARInvoiceEntryDialog._item_display(item)


_INVOICE_METHODS = (
    "_reload_reference_data",
    "_build_ui",
    "_currency_changed",
    "_set_defaults",
    "_due_date",
    "_customer_selected",
    "_new_customer",
    "_open_items",
    "_add_item",
    "_after_item_created",
    "_selected_line_index",
    "_edit_line",
    "_item_line_dialog",
    "_add_subtotal",
    "_add_discount",
    "_discount_dialog",
    "_remove_line",
    "_invoice_payload",
    "_refresh_lines",
    "_load_invoice",
    "_save",
    "_cancel",
    "_preview",
)
for _method_name in _INVOICE_METHODS:
    setattr(
        ARInvoiceEntryFrame,
        _method_name,
        ARInvoiceEntryDialog.__dict__[_method_name],
    )


class ARCustomerCentreFrame(tb.Frame):
    """Full-size Customer Centre embedded in the authenticated workspace."""

    def __init__(
        self,
        parent,
        company_id: int | None = None,
        customer_id: int | None = None,
        open_invoice_callback=None,
        on_close=None,
        on_customer_changed=None,
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.initial_customer_id = customer_id
        self.selected_customer_id: int | None = None
        self.open_invoice_callback = open_invoice_callback
        self.on_close = on_close
        self.on_customer_changed = on_customer_changed
        self.customers: list[dict] = []
        self._build_ui()
        self._load_customers()

    def refresh(self, customer_id: int | None = None) -> None:
        """Reload customers and invoices, optionally selecting a customer."""
        if customer_id is not None:
            self.initial_customer_id = customer_id
            self.selected_customer_id = customer_id
        self._load_customers()


_CUSTOMER_METHODS = (
    "_build_ui",
    "_kpi",
    "_load_customers",
    "_customer_changed",
    "_date_range",
    "_load_invoices",
    "_selected_invoice_id",
    "_new_invoice",
    "_edit_invoice",
    "_new_customer",
    "_edit_customer",
    "_merge_customer",
    "_close",
    "_receive_payment",
    "_apply_credit",
    "_items",
    "_print_invoice",
    "_delete_invoice",
    "_aging",
    "_reload_all",
)
for _method_name in _CUSTOMER_METHODS:
    setattr(
        ARCustomerCentreFrame,
        _method_name,
        ARInvoiceListDialog.__dict__[_method_name],
    )
