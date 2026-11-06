"""
Early Payment Discount Optimization & Early Settlement Dialog
Allows finance managers to identify, evaluate, and settle vendor bills offering early payment discounts.
"""

import os
import tkinter as tk
from tkinter import messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from ui.pay_bills_dialog import PayBillsDialog


class EarlyPaymentDiscountDialog(tb.Toplevel):
    """
    Interactive UI for evaluating AP early payment discounts and calculating annualized return (APR).
    """

    def __init__(self, parent, company_id=None, on_settled=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_settled = on_settled
        self.title("Early Payment Discount Optimizer")
        self.geometry("1100x680")
        self.minsize(950, 550)
        self.transient(parent)

        self.analysis_data = {}
        self.filtered_invoices = []

        # Filter Variables
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_and_populate())
        self.filter_var = tk.StringVar(value="Eligible Only")

        # KPI Variables
        self.kpi_savings_var = tk.StringVar(value="LKR 0.00")
        self.kpi_eligible_var = tk.StringVar(value="0")
        self.kpi_top_apr_var = tk.StringVar(value="0.0%")

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 1. Header Banner
        header = tb.Frame(self, bootstyle="dark", padding=(20, 15))
        header.pack(fill=X)

        title_lbl = tb.Label(
            header,
            text="Early Payment Discount & Settlement Optimizer",
            font=("Segoe UI", 16, "bold"),
            bootstyle="inverse-dark",
        )
        title_lbl.pack(anchor=W)

        sub_lbl = tb.Label(
            header,
            text="Identify vendor bills offering early settlement discounts to optimize cash returns (APR %).",
            font=("Segoe UI", 9),
            bootstyle="inverse-dark",
        )
        sub_lbl.pack(anchor=W, pady=(2, 0))

        # 2. KPI Summary Cards Frame
        kpi_frame = tb.Frame(self, padding=(20, 10))
        kpi_frame.pack(fill=X)

        self._create_kpi_card(
            kpi_frame, "Total Potential Savings", self.kpi_savings_var, "success", 0
        )
        self._create_kpi_card(
            kpi_frame, "Eligible Invoices", self.kpi_eligible_var, "info", 1
        )
        self._create_kpi_card(
            kpi_frame, "Highest Return (APR %)", self.kpi_top_apr_var, "warning", 2
        )

        kpi_frame.columnconfigure(0, weight=1)
        kpi_frame.columnconfigure(1, weight=1)
        kpi_frame.columnconfigure(2, weight=1)

        # 3. Filter Controls
        filter_frame = tb.Labelframe(self, text="Filter Invoices", padding=10)
        filter_frame.pack(fill=X, padx=20, pady=(5, 10))

        tb.Label(filter_frame, text="Search:").pack(side=LEFT, padx=(0, 5))
        search_entry = tb.Entry(filter_frame, textvariable=self.search_var, width=24)
        search_entry.pack(side=LEFT, padx=(0, 15))
        tb.ToolTip(search_entry, text="Search by invoice number or supplier name.")

        tb.Label(filter_frame, text="View Category:").pack(side=LEFT, padx=(0, 5))
        filter_cb = tb.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=[
                "Eligible Only",
                "Expiring Soon (<= 3 Days)",
                "High Return (>= 15% APR)",
                "All Open Invoices",
            ],
            state="readonly",
            width=22,
        )
        filter_cb.pack(side=LEFT)
        filter_cb.bind("<<ComboboxSelected>>", lambda e: self._filter_and_populate())
        tb.ToolTip(filter_cb, text="Filter listed invoices by discount availability and ROI.")

        btn_refresh = tb.Button(
            filter_frame,
            text="Refresh",
            command=self.refresh,
            bootstyle="secondary-outline",
        )
        btn_refresh.pack(side=RIGHT)
        tb.ToolTip(btn_refresh, text="Reload open vendor invoices from database.")

        # 4. Treeview Table
        tree_container = tb.Frame(self, padding=(20, 0))
        tree_container.pack(fill=BOTH, expand=True)

        columns = (
            "inv_num",
            "supplier",
            "inv_date",
            "due_date",
            "cutoff_date",
            "days_left",
            "terms",
            "balance",
            "discount",
            "net_payable",
            "apr",
            "status",
        )

        self.tree = tb.Treeview(
            tree_container,
            columns=columns,
            show="headings",
            selectmode="browse",
            bootstyle="primary",
        )

        definitions = [
            ("inv_num", "Invoice #", 100, W),
            ("supplier", "Supplier", 170, W),
            ("inv_date", "Inv Date", 85, W),
            ("due_date", "Due Date", 85, W),
            ("cutoff_date", "Cutoff Date", 85, W),
            ("days_left", "Days Left", 70, E),
            ("terms", "Terms", 90, W),
            ("balance", "Balance Due", 100, E),
            ("discount", "Discount", 95, E),
            ("net_payable", "Net Payable", 100, E),
            ("apr", "APR (%)", 80, E),
            ("status", "Status", 110, W),
        ]

        for col_id, title, width, align in definitions:
            self.tree.heading(col_id, text=title)
            self.tree.column(col_id, width=width, anchor=align)

        v_scroll = tb.Scrollbar(
            tree_container, orient=VERTICAL, command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=v_scroll.set)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        v_scroll.pack(side=RIGHT, fill=Y)

        # Bindings for double click and keyboard navigation
        self.tree.bind("<Double-1>", lambda e: self._on_pay_selected())
        self.tree.bind("<Return>", lambda e: self._on_pay_selected())
        self.tree.bind("<KP_Enter>", lambda e: self._on_pay_selected())

        # 5. Bottom Action Button Bar
        action_bar = tb.Frame(self, padding=20)
        action_bar.pack(fill=X)

        self.pay_btn = tb.Button(
            action_bar,
            text="Pay Selected Bill",
            command=self._on_pay_selected,
            bootstyle="success",
        )
        self.pay_btn.pack(side=LEFT, padx=(0, 10))
        tb.ToolTip(
            self.pay_btn,
            text="Open Pay Bills window for the selected supplier to record early settlement.",
        )

        self.export_btn = tb.Button(
            action_bar,
            text="Export CSV Report",
            command=self._on_export_csv,
            bootstyle="info-outline",
        )
        self.export_btn.pack(side=LEFT)
        tb.ToolTip(
            self.export_btn, text="Export early payment discount analysis report to CSV file."
        )

        close_btn = tb.Button(
            action_bar, text="Close", command=self.destroy, bootstyle="secondary"
        )
        close_btn.pack(side=RIGHT)

    def _create_kpi_card(self, parent, label, var, bootstyle, col):
        card = tb.Labelframe(parent, text=label, padding=12, bootstyle=bootstyle)
        card.grid(row=0, column=col, sticky="ew", padx=6)

        lbl = tb.Label(
            card,
            textvariable=var,
            font=("Segoe UI", 15, "bold"),
            bootstyle=bootstyle,
        )
        lbl.pack(anchor=W)

    def refresh(self):
        """Fetch early discount analysis data and update UI."""
        self.analysis_data = db.calculate_ap_early_payment_discounts(
            company_id=self.company_id
        )

        # Update KPI cards
        c_code = db.get_company_base_currency(self.company_id)
        sav = self.analysis_data.get("total_potential_savings", 0.0)
        self.kpi_savings_var.set(f"{c_code} {sav:,.2f}")
        self.kpi_eligible_var.set(str(self.analysis_data.get("eligible_count", 0)))
        top_apr = self.analysis_data.get("top_apr", 0.0)
        self.kpi_top_apr_var.set(f"{top_apr:.1f}%")

        self._filter_and_populate()

    def _filter_and_populate(self):
        """Filter invoices list and populate treeview table."""
        all_invoices = self.analysis_data.get("invoices", [])
        query = self.search_var.get().strip().lower()
        filter_mode = self.filter_var.get()

        self.filtered_invoices = []
        for inv in all_invoices:
            # Search filter
            if query:
                s_name = inv.get("supplier_name", "").lower()
                inv_no = inv.get("invoice_number", "").lower()
                if query not in s_name and query not in inv_no:
                    continue

            # Category filter
            if filter_mode == "Eligible Only" and not inv.get("is_eligible"):
                continue
            elif filter_mode == "Expiring Soon (<= 3 Days)":
                if not inv.get("is_eligible") or inv.get("days_remaining", 99) > 3:
                    continue
            elif filter_mode == "High Return (>= 15% APR)":
                if inv.get("annualized_apr", 0.0) < 15.0:
                    continue

            self.filtered_invoices.append(inv)

        # Populate treeview
        self.tree.delete(*self.tree.get_children())
        for idx, inv in enumerate(self.filtered_invoices):
            item_id = str(inv["id"])
            days_str = str(inv["days_remaining"]) if inv["discount_days"] > 0 else "—"
            apr_str = f"{inv['annualized_apr']:.1f}%" if inv["annualized_apr"] > 0 else "—"

            self.tree.insert(
                "",
                END,
                iid=item_id,
                values=(
                    inv["invoice_number"],
                    inv["supplier_name"],
                    inv["invoice_date"],
                    inv["due_date"],
                    inv["discount_cutoff_date"] if inv["discount_days"] > 0 else "—",
                    days_str,
                    inv["terms"],
                    f"{inv['balance_due']:,.2f}",
                    f"{inv['discount_amount']:,.2f}",
                    f"{inv['net_payable']:,.2f}",
                    apr_str,
                    inv["status"],
                ),
            )

        # Auto select and focus first row
        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    def _get_selected_invoice(self):
        selection = self.tree.selection()
        if not selection:
            return None
        inv_id = int(selection[0])
        for inv in self.filtered_invoices:
            if inv["id"] == inv_id:
                return inv
        return None

    def _on_pay_selected(self):
        inv = self._get_selected_invoice()
        if not inv:
            messagebox.showwarning(
                "No Selection",
                "Please select an invoice to settle.",
                parent=self,
            )
            return

        # Open PayBillsDialog pre-filtered for supplier
        dlg = PayBillsDialog(
            self.master,
            company_id=self.company_id,
            initial_supplier_id=inv["supplier_id"],
            on_saved=self._on_bill_settled,
        )

    def _on_bill_settled(self):
        self.refresh()
        if self.on_settled:
            self.on_settled()

    def _on_export_csv(self):
        default_filename = f"early_payment_discounts_{db.get_active_company_id()}.csv"
        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Early Payment Discount Analysis",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )

        if not filepath:
            return

        try:
            db.export_early_payment_discounts_to_csv(
                filepath, company_id=self.company_id
            )
            messagebox.showinfo(
                "Export Complete",
                f"Early payment discount analysis successfully exported to:\n{filepath}",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror(
                "Export Failed",
                f"An error occurred while exporting CSV:\n{e}",
                parent=self,
            )
