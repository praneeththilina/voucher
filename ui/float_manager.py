"""
Money Float Manager Dialog for company cash float and cash drawer management.
Allows users to track multiple floats per company, opening balances, inflows (top-ups),
voucher outflows, and view/export real-time running balance ledgers.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap import ToolTip
from ttkbootstrap.constants import *
from tkinter import messagebox, filedialog
from datetime import datetime, timedelta
import database as db
import printer
from ui.pdf_viewer import PdfViewerDialog
from ui.widgets import SearchableAccountSelector
import firebase_client


class MoneyFloatView(ttk.Frame):
    """
    Comprehensive Money Float & Cash Drawer Tracking View Frame.
    Provides real-time running balance audit ledger, multi-float switching,
    top-up recording, and CSV ledger exports directly embedded in the main app screen.
    """

    def __init__(self, parent, company_id=None, on_update_callback=None, on_close_callback=None):
        super().__init__(parent)
        self._parent = parent
        self._on_update_callback = on_update_callback
        self._on_close_callback = on_close_callback
        self._company_id = company_id if company_id is not None else db.get_active_company_id()
        self._selected_float_id = None
        self._floats_cache = []
        self._raw_entries = []
        self._sort_col = "date"
        self._sort_desc = True  # Default: latest transactions top!
        self._base_headings = {}
        self._dirty = False
        self._filter_after_id = None
        self._ledger_stats = {}

        self._build_ui()
        self._load_floats()

    def mark_dirty(self):
        """Flag that float data in DB changed and needs reloading on next view."""
        self._dirty = True

    def destroy(self) -> None:
        """Cancel pending register filter work before destroying the view."""
        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
            self._filter_after_id = None
        super().destroy()

    def _notify_update(self):
        """Notify parent window that a database mutation occurred."""
        if self._on_update_callback:
            try:
                self._on_update_callback()
            except Exception:
                pass

    def set_company_id(self, company_id):
        """Update active company ID and reload floats ledger."""
        if self._company_id != company_id:
            self._company_id = company_id
            comp = db.get_company(self._company_id) or {}
            comp_name = comp.get("name", f"Company {self._company_id}")
            if hasattr(self, "_header_subtitle_var"):
                self._header_subtitle_var.set(
                    f"{comp_name}  •  Cash on hand account history"
                )
            self._dirty = True
            # If this view is currently visible on screen, reload immediately
            try:
                if self.winfo_ismapped():
                    self._load_floats()
                    self._dirty = False
            except Exception:
                pass

    def refresh(self, force=False):
        """Refresh floats cache and current ledger only if dirty or company changed."""
        active_comp = db.get_active_company_id()
        if self._company_id != active_comp:
            self.set_company_id(active_comp)
            self._load_floats(select_float_id=self._selected_float_id)
            self._dirty = False
        elif self._dirty or force:
            self._load_floats(select_float_id=self._selected_float_id)
            self._dirty = False

    def _on_close(self):
        """Handle close / back navigation."""
        if self._on_close_callback:
            try:
                self._on_close_callback()
            except Exception:
                pass

    def _build_ui(self) -> None:
        """Build a QuickBooks-style cash account register."""
        company = db.get_company(self._company_id) or {}
        company_name = company.get("name", f"Company {self._company_id}")

        self._kpi_vars = {
            "current_balance": tk.StringVar(value="LKR 0.00"),
            "opening_balance": tk.StringVar(value="LKR 0.00"),
            "total_inflows": tk.StringVar(value="LKR 0.00"),
            "total_outflows": tk.StringVar(value="LKR 0.00"),
            "custodian": tk.StringVar(value="-"),
            "opening_date": tk.StringVar(value="-"),
            "unreimbursed_total": tk.StringVar(value="LKR 0.00"),
            "unreimbursed_count": tk.StringVar(value="0 pending"),
        }
        self._tree_data_map = {}

        page = tk.Frame(self, bg="#f4f5f7")
        page.pack(fill=tk.BOTH, expand=True)

        # Account register header: account selector, ending balance, and primary action.
        header = tk.Frame(
            page,
            bg="#ffffff",
            padx=18,
            pady=11,
            highlightbackground="#d1d5db",
            highlightthickness=1,
        )
        header.pack(fill=tk.X, padx=10, pady=(8, 0))

        identity = tk.Frame(header, bg="#ffffff")
        identity.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(
            identity,
            text="Cash Register",
            font=("Segoe UI", 17, "bold"),
            bg="#ffffff",
            fg="#1f2937",
        ).pack(anchor="w")
        self._header_subtitle_var = tk.StringVar(
            value=f"{company_name}  •  Cash on hand account history"
        )
        tk.Label(
            identity,
            textvariable=self._header_subtitle_var,
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#6b7280",
        ).pack(anchor="w", pady=(0, 7))

        account_row = tk.Frame(identity, bg="#ffffff")
        account_row.pack(anchor="w")
        tk.Label(
            account_row,
            text="ACCOUNT",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(side=tk.LEFT, padx=(0, 7))
        self._float_selector_var = tk.StringVar()
        self._float_combo = ttk.Combobox(
            account_row,
            textvariable=self._float_selector_var,
            width=31,
            state="readonly",
        )
        self._float_combo.pack(side=tk.LEFT)
        self._float_combo.bind("<<ComboboxSelected>>", self._on_float_selected)

        edit_float_btn = ttk.Button(
            account_row,
            text="Edit",
            command=self._open_edit_float_dialog,
            bootstyle="secondary-outline",
            width=7,
        )
        edit_float_btn.pack(side=tk.LEFT, padx=(6, 3))
        ToolTip(edit_float_btn, text="Edit this cash account, custodian, and opening balance")

        new_float_btn = ttk.Button(
            account_row,
            text="+ New account",
            command=self._open_new_float_dialog,
            bootstyle="secondary-outline",
        )
        new_float_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(new_float_btn, text="Create another cash float or drawer (Ctrl+Shift+N)")

        account_summary = tk.Frame(header, bg="#ffffff")
        account_summary.pack(side=tk.RIGHT, padx=(18, 0))
        tk.Label(
            account_summary,
            text="ENDING BALANCE",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#6b7280",
        ).pack(anchor="e")
        self._cur_bal_lbl = tk.Label(
            account_summary,
            textvariable=self._kpi_vars["current_balance"],
            font=("Segoe UI", 18, "bold"),
            bg="#ffffff",
            fg="#166534",
        )
        self._cur_bal_lbl.pack(anchor="e")
        self._custodian_badge_var = tk.StringVar(value="Custodian: -")
        tk.Label(
            account_summary,
            textvariable=self._custodian_badge_var,
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#6b7280",
        ).pack(anchor="e", pady=(0, 6))

        header_actions = tk.Frame(account_summary, bg="#ffffff")
        header_actions.pack(anchor="e")
        reimburse_btn = ttk.Button(
            header_actions,
            text="Reimburse float",
            command=self._open_fund_reimbursement_dialog,
            bootstyle="success",
        )
        reimburse_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(reimburse_btn, text="Settle unreimbursed vouchers and replenish this float")
        back_btn = ttk.Button(
            header_actions,
            text="Back to vouchers",
            command=self._on_close,
            bootstyle="secondary-outline",
        )
        back_btn.pack(side=tk.LEFT)

        # Compact account totals replace the oversized dashboard cards.
        metrics = tk.Frame(
            page,
            bg="#ffffff",
            padx=12,
            pady=7,
            highlightbackground="#d1d5db",
            highlightthickness=1,
        )
        metrics.pack(fill=tk.X, padx=10, pady=(6, 0))

        def _metric_card(title, variable, caption, color):
            card = tk.Frame(metrics, bg="#ffffff", padx=12, pady=2)
            card.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                card,
                text=title,
                font=("Segoe UI", 8, "bold"),
                bg="#ffffff",
                fg="#6b7280",
            ).pack(anchor="w")
            tk.Label(
                card,
                textvariable=variable,
                font=("Segoe UI", 12, "bold"),
                bg="#ffffff",
                fg=color,
            ).pack(anchor="w")
            tk.Label(
                card,
                text=caption,
                font=("Segoe UI", 7),
                bg="#ffffff",
                fg="#9ca3af",
            ).pack(anchor="w")
            return card

        _metric_card(
            "OPENING BALANCE",
            self._kpi_vars["opening_balance"],
            "Account starting amount",
            "#1d4ed8",
        )
        _metric_card(
            "MONEY IN",
            self._kpi_vars["total_inflows"],
            "Deposits and reimbursements",
            "#15803d",
        )
        _metric_card(
            "MONEY OUT",
            self._kpi_vars["total_outflows"],
            "Vouchers and adjustments",
            "#b91c1c",
        )
        _metric_card(
            "TO REIMBURSE",
            self._kpi_vars["unreimbursed_total"],
            "Unsettled voucher spending",
            "#b45309",
        )

        # Transaction actions and register filters.
        tools = tk.Frame(
            page,
            bg="#ffffff",
            padx=12,
            pady=7,
            highlightbackground="#d1d5db",
            highlightthickness=1,
        )
        tools.pack(fill=tk.X, padx=10, pady=(6, 0))

        action_row = tk.Frame(tools, bg="#ffffff")
        action_row.pack(fill=tk.X)
        new_expense_btn = ttk.Button(
            action_row,
            text="+ New expense",
            command=lambda: self._open_add_transaction_dialog("Outflow"),
            bootstyle="primary",
        )
        new_expense_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(new_expense_btn, text="Record a manual cash payment or adjustment (Alt+O)")
        new_deposit_btn = ttk.Button(
            action_row,
            text="+ New deposit",
            command=lambda: self._open_add_transaction_dialog("Inflow"),
            bootstyle="success-outline",
        )
        new_deposit_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(new_deposit_btn, text="Record cash added to this account (Alt+A)")
        transfer_btn = ttk.Button(
            action_row,
            text="Transfer",
            command=self._open_transfer_dialog,
            bootstyle="info-outline",
        )
        transfer_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(transfer_btn, text="Transfer cash between floats or drawers (Alt+T)")

        refresh_btn = ttk.Button(
            action_row,
            text="Refresh",
            command=self._refresh_ledger,
            bootstyle="secondary-outline",
        )
        refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        export_btn = ttk.Button(
            action_row,
            text="Export CSV",
            command=self._export_ledger_csv,
            bootstyle="secondary-outline",
        )
        export_btn.pack(side=tk.RIGHT, padx=5)

        filter_row = tk.Frame(tools, bg="#ffffff")
        filter_row.pack(fill=tk.X, pady=(7, 0))
        tk.Label(
            filter_row,
            text="Find",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(side=tk.LEFT, padx=(0, 5))
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(
            filter_row,
            textvariable=self._search_var,
            width=29,
        )
        self._search_entry.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(
            self._search_entry,
            text="Search reference, type, payee, account, memo, or amount",
        )

        tk.Label(
            filter_row,
            text="Type",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(side=tk.LEFT, padx=(0, 5))
        self._type_filter_var = tk.StringVar(value="All transactions")
        type_combo = ttk.Combobox(
            filter_row,
            textvariable=self._type_filter_var,
            values=[
                "All transactions",
                "Money in",
                "Money out",
                "Vouchers",
                "Reimbursements",
                "Transfers",
                "Adjustments",
                "Opening balance",
            ],
            width=18,
            state="readonly",
        )
        type_combo.pack(side=tk.LEFT, padx=(0, 10))
        type_combo.bind("<<ComboboxSelected>>", self._schedule_filter_refresh)

        tk.Label(
            filter_row,
            text="Date",
            font=("Segoe UI", 8, "bold"),
            bg="#ffffff",
            fg="#4b5563",
        ).pack(side=tk.LEFT, padx=(0, 5))
        self._period_filter_var = tk.StringVar(value="All Time")
        period_combo = ttk.Combobox(
            filter_row,
            textvariable=self._period_filter_var,
            values=[
                "All Time",
                "Today",
                "Yesterday",
                "This Week",
                "This Month",
                "Last Month",
                "This Year",
            ],
            width=14,
            state="readonly",
        )
        period_combo.pack(side=tk.LEFT, padx=(0, 7))
        period_combo.bind("<<ComboboxSelected>>", lambda event: self._refresh_ledger())

        clear_btn = ttk.Button(
            filter_row,
            text="Clear filters",
            command=self._clear_register_filters,
            bootstyle="secondary-link",
        )
        clear_btn.pack(side=tk.LEFT)
        self._search_entry.bind("<KeyRelease>", self._schedule_filter_refresh)
        self._search_entry.bind("<Return>", lambda event: self._populate_treeview())

        # QuickBooks-style account register.
        register = tk.Frame(
            page,
            bg="#ffffff",
            padx=10,
            pady=7,
            highlightbackground="#d1d5db",
            highlightthickness=1,
        )
        register.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))

        register_heading = tk.Frame(register, bg="#ffffff")
        register_heading.pack(fill=tk.X, pady=(0, 5))
        tk.Label(
            register_heading,
            text="ACCOUNT ACTIVITY",
            font=("Segoe UI", 9, "bold"),
            bg="#ffffff",
            fg="#374151",
        ).pack(side=tk.LEFT)
        tk.Label(
            register_heading,
            text="Double-click a row to open the source transaction",
            font=("Segoe UI", 8),
            bg="#ffffff",
            fg="#6b7280",
        ).pack(side=tk.RIGHT)

        table_frame = tk.Frame(register, bg="#ffffff")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = (
            "date",
            "ref",
            "type",
            "payee",
            "description",
            "outflow",
            "inflow",
            "status",
            "running_balance",
        )
        register_style = ttk.Style()
        register_style.configure(
            "FloatRegister.Treeview",
            rowheight=27,
            font=("Segoe UI", 9),
        )
        register_style.configure(
            "FloatRegister.Treeview.Heading",
            font=("Segoe UI", 8, "bold"),
        )
        self._tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="FloatRegister.Treeview",
        )
        col_defs = [
            ("date", "DATE", 90, "center", False),
            ("ref", "REF NO.", 105, "w", False),
            ("type", "TYPE", 140, "w", False),
            ("payee", "PAYEE / ACCOUNT", 155, "w", False),
            ("description", "MEMO", 310, "w", True),
            ("outflow", "PAYMENT", 105, "e", False),
            ("inflow", "DEPOSIT", 105, "e", False),
            ("status", "STATUS", 105, "center", False),
            ("running_balance", "BALANCE", 130, "e", False),
        ]
        for col_id, heading, width, anchor, stretch in col_defs:
            self._base_headings[col_id] = heading
            self._tree.heading(
                col_id,
                text=heading + (" ▼" if col_id == "date" else ""),
                anchor=anchor,
                command=lambda column=col_id: self._sort_by_column(column),
            )
            self._tree.column(
                col_id,
                width=width,
                minwidth=65,
                anchor=anchor,
                stretch=stretch,
            )

        self._tree.tag_configure("opening_tag", background="#eff6ff", foreground="#1d4ed8")
        self._tree.tag_configure("inflow_tag", background="#f0fdf4", foreground="#166534")
        self._tree.tag_configure("reimb_tag", background="#ecfeff", foreground="#0e7490")
        self._tree.tag_configure("cash_rec_tag", background="#f0fdfa", foreground="#0f766e")
        self._tree.tag_configure("transfer_in_tag", background="#eff6ff", foreground="#1d4ed8")
        self._tree.tag_configure("transfer_out_tag", background="#fff7ed", foreground="#9a3412")
        self._tree.tag_configure("outflow_pending_tag", background="#fff7ed", foreground="#9a3412")
        self._tree.tag_configure("outflow_reimbursed_tag", background="#f9fafb", foreground="#4b5563")
        self._tree.tag_configure("outflow_tag", background="#fef2f2", foreground="#991b1b")
        self._tree.tag_configure("adj_outflow_tag", background="#fffbeb", foreground="#92400e")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self._tree_menu = tk.Menu(self, tearoff=0)

        def _on_context_menu(event):
            item_id = self._tree.identify_row(event.y)
            if not item_id:
                return
            self._tree.selection_set(item_id)
            self._on_tree_selection()
            entry = self._tree_data_map.get(item_id, {})
            entry_type = entry.get("entry_type")
            self._tree_menu.delete(0, tk.END)
            self._tree_menu.add_command(
                label="Copy reference",
                command=self._copy_selected_ref,
            )
            self._tree_menu.add_separator()
            if entry_type == "voucher":
                self._tree_menu.add_command(
                    label="Open voucher PDF",
                    command=self._view_linked_voucher,
                )
            elif entry_type == "reimbursement":
                self._tree_menu.add_command(
                    label="View reimbursement",
                    command=lambda: self._view_reimbursement_details(entry.get("id")),
                )
                self._tree_menu.add_command(
                    label="Delete reimbursement",
                    command=self._delete_selected_transaction,
                )
            elif entry_type in ("top_up", "cash_received", "adjustment"):
                self._tree_menu.add_command(
                    label="View / edit transaction",
                    command=lambda: self._view_or_edit_transaction(entry.get("id")),
                )
                self._tree_menu.add_command(
                    label="Delete transaction",
                    command=self._delete_selected_transaction,
                )
            elif entry_type in ("transfer_in", "transfer_out"):
                self._tree_menu.add_command(
                    label="View transfer details",
                    command=lambda: self._show_transfer_details(entry),
                )
            elif entry_type == "opening":
                self._tree_menu.add_command(
                    label="Edit opening balance",
                    command=self._open_edit_float_dialog,
                )
            self._tree_menu.post(event.x_root, event.y_root)

        self._tree.bind("<Button-3>", _on_context_menu)
        self._tree.bind("<Double-1>", self._on_tree_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_selection)
        self._tree.bind("<Return>", self._on_tree_double_click)

        # Selection tray mirrors QuickBooks' expandable register row action.
        detail = tk.Frame(
            page,
            bg="#f8fafc",
            padx=14,
            pady=6,
            highlightbackground="#d1d5db",
            highlightthickness=1,
        )
        detail.pack(fill=tk.X, padx=10, pady=(5, 0))
        detail_text = tk.Frame(detail, bg="#f8fafc")
        detail_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._detail_title_var = tk.StringVar(value="Select a transaction to review it")
        self._detail_meta_var = tk.StringVar(
            value="Search, filter, or sort the register without changing accounting data."
        )
        tk.Label(
            detail_text,
            textvariable=self._detail_title_var,
            font=("Segoe UI", 9, "bold"),
            bg="#f8fafc",
            fg="#1f2937",
        ).pack(anchor="w")
        tk.Label(
            detail_text,
            textvariable=self._detail_meta_var,
            font=("Segoe UI", 8),
            bg="#f8fafc",
            fg="#6b7280",
        ).pack(anchor="w")
        self._detail_action_btn = ttk.Button(
            detail,
            text="Open transaction",
            command=self._open_selected_transaction,
            bootstyle="primary-outline",
            state=tk.DISABLED,
        )
        self._detail_action_btn.pack(side=tk.RIGHT, padx=(10, 0))

        status = tk.Frame(page, bg="#eef2f7", padx=14, pady=4)
        status.pack(fill=tk.X, padx=10, pady=(0, 8))
        self._status_left_var = tk.StringVar(value="Ready")
        self._status_right_var = tk.StringVar(value="")
        tk.Label(
            status,
            textvariable=self._status_left_var,
            font=("Segoe UI", 8),
            bg="#eef2f7",
            fg="#4b5563",
        ).pack(side=tk.LEFT)
        tk.Label(
            status,
            textvariable=self._status_right_var,
            font=("Segoe UI", 8, "bold"),
            bg="#eef2f7",
            fg="#1f2937",
        ).pack(side=tk.RIGHT)
    def _load_floats(self, select_float_id=None):
        """Fetch all floats for current company and populate combobox."""
        floats = db.get_floats(self._company_id, active_only=True)
        if not floats:
            # Create a default float if none exists
            today_str = datetime.now().strftime("%Y-%m-%d")
            new_id = db.create_float(
                company_id=self._company_id,
                name="Main Cash Float",
                opening_balance=0.0,
                opening_date=today_str,
                custodian="",
                notes="Primary Cash Drawer",
                is_default=True
            )
            floats = db.get_floats(self._company_id, active_only=True)

        self._floats_cache = floats
        combo_vals = []
        target_idx = 0

        for idx, flt in enumerate(floats):
            name_str = flt["name"]
            if flt.get("is_default"):
                name_str += " ★ (Default)"
            combo_vals.append(name_str)

            if select_float_id and flt["id"] == select_float_id:
                target_idx = idx
            elif select_float_id is None and flt.get("is_default"):
                target_idx = idx

        self._float_combo["values"] = combo_vals
        if combo_vals:
            self._float_combo.current(target_idx)
            self._selected_float_id = floats[target_idx]["id"]
            self._refresh_ledger()

    def _on_float_selected(self, event=None):
        idx = self._float_combo.current()
        if 0 <= idx < len(self._floats_cache):
            self._selected_float_id = self._floats_cache[idx]["id"]
            self._refresh_ledger()

    def _sort_by_column(self, col: str) -> None:
        """Toggle register sorting while keeping balance values auditable."""
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = col in (
                "date",
                "inflow",
                "outflow",
                "running_balance",
            )
        self._update_header_arrows()
        self._populate_treeview()

    def _update_header_arrows(self) -> None:
        """Show the active register sort direction."""
        for column, title in self._base_headings.items():
            if column == self._sort_col:
                arrow = " ▼" if self._sort_desc else " ▲"
                self._tree.heading(column, text=title + arrow)
            else:
                self._tree.heading(column, text=title)

    @staticmethod
    def _entry_payee(entry: dict) -> str:
        """Return the most useful register counterparty for an entry."""
        return str(
            entry.get("spent_by")
            or entry.get("received_by")
            or entry.get("handed_by")
            or "—"
        )

    @staticmethod
    def _entry_status(entry: dict) -> str:
        """Return a concise accounting status for the register."""
        entry_type = entry.get("entry_type")
        if entry_type == "voucher":
            return "Reimbursed" if entry.get("is_reimbursed") else "To reimburse"
        if entry_type == "opening":
            return "Opening"
        if entry_type == "reimbursement":
            return "Settled"
        return "Posted"

    def _filtered_register_entries(self) -> list[dict]:
        """Apply fast in-memory search and type filters to the loaded period."""
        entries = list(self._raw_entries)
        search_text = self._search_var.get().strip().casefold()
        if search_text:
            def _matches(entry):
                amount_text = (
                    f"{float(entry.get('inflow') or 0):.2f} "
                    f"{float(entry.get('outflow') or 0):.2f} "
                    f"{float(entry.get('running_balance') or 0):.2f}"
                )
                fields = (
                    entry.get("date"),
                    entry.get("ref"),
                    entry.get("type_label"),
                    entry.get("description"),
                    entry.get("handed_by"),
                    entry.get("spent_by"),
                    entry.get("received_by"),
                    amount_text,
                )
                haystack = " ".join(str(value or "") for value in fields).casefold()
                return search_text in haystack

            entries = [entry for entry in entries if _matches(entry)]

        type_filter = self._type_filter_var.get()
        if type_filter == "Money in":
            entries = [entry for entry in entries if float(entry.get("inflow") or 0) > 0]
        elif type_filter == "Money out":
            entries = [entry for entry in entries if float(entry.get("outflow") or 0) > 0]
        elif type_filter == "Vouchers":
            entries = [entry for entry in entries if entry.get("entry_type") == "voucher"]
        elif type_filter == "Reimbursements":
            entries = [entry for entry in entries if entry.get("entry_type") == "reimbursement"]
        elif type_filter == "Transfers":
            entries = [
                entry
                for entry in entries
                if entry.get("entry_type") in ("transfer_in", "transfer_out")
            ]
        elif type_filter == "Adjustments":
            entries = [entry for entry in entries if entry.get("entry_type") == "adjustment"]
        elif type_filter == "Opening balance":
            entries = [entry for entry in entries if entry.get("entry_type") == "opening"]
        return entries

    def _schedule_filter_refresh(self, event=None) -> None:
        """Debounce local register filtering for responsive typing."""
        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
        self._filter_after_id = self.after(120, self._run_scheduled_filter)

    def _run_scheduled_filter(self) -> None:
        """Apply a scheduled local register filter."""
        self._filter_after_id = None
        if self.winfo_exists():
            self._populate_treeview()

    def _clear_register_filters(self) -> None:
        """Restore the complete account register."""
        self._search_var.set("")
        self._type_filter_var.set("All transactions")
        if self._period_filter_var.get() != "All Time":
            self._period_filter_var.set("All Time")
            self._refresh_ledger()
        else:
            self._populate_treeview()
        self._search_entry.focus_set()

    def _populate_treeview(self) -> None:
        """Render the filtered register using the active sort order."""
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)
        self._tree_data_map.clear()

        entries = self._filtered_register_entries()

        def sort_key(entry):
            if self._sort_col == "date":
                return (
                    entry.get("date", ""),
                    entry.get("sort_priority", 0),
                    entry.get("id", 0),
                )
            if self._sort_col in ("inflow", "outflow", "running_balance"):
                return float(entry.get(self._sort_col, 0.0))
            if self._sort_col == "type":
                return str(entry.get("type_label", "")).casefold()
            if self._sort_col == "ref":
                return str(entry.get("ref", "")).casefold()
            if self._sort_col == "description":
                return str(entry.get("description", "")).casefold()
            if self._sort_col == "payee":
                return self._entry_payee(entry).casefold()
            if self._sort_col == "status":
                return self._entry_status(entry).casefold()
            return entry.get("id", 0)

        entries = sorted(entries, key=sort_key, reverse=self._sort_desc)
        for entry in entries:
            inflow = float(entry.get("inflow") or 0)
            outflow = float(entry.get("outflow") or 0)
            balance = float(entry.get("running_balance") or 0)
            entry_type = entry.get("entry_type")
            tag = "opening_tag"
            if entry_type == "reimbursement":
                tag = "reimb_tag"
            elif entry_type == "cash_received":
                tag = "cash_rec_tag"
            elif entry_type == "transfer_in":
                tag = "transfer_in_tag"
            elif entry_type == "transfer_out":
                tag = "transfer_out_tag"
            elif entry_type == "top_up":
                tag = "inflow_tag"
            elif entry_type == "voucher":
                tag = (
                    "outflow_reimbursed_tag"
                    if entry.get("is_reimbursed")
                    else "outflow_pending_tag"
                )
            elif entry_type == "adjustment":
                tag = "adj_outflow_tag"

            item_id = self._tree.insert(
                "",
                tk.END,
                values=(
                    entry.get("date", ""),
                    entry.get("ref", ""),
                    entry.get("type_label", ""),
                    self._entry_payee(entry),
                    entry.get("description", ""),
                    f"{outflow:,.2f}" if outflow else "—",
                    f"{inflow:,.2f}" if inflow else "—",
                    self._entry_status(entry),
                    f"{balance:,.2f}",
                ),
                tags=(tag,),
            )
            self._tree_data_map[item_id] = entry

        visible_in = sum(float(entry.get("inflow") or 0) for entry in entries)
        visible_out = sum(float(entry.get("outflow") or 0) for entry in entries)
        net_movement = visible_in - visible_out
        qualifiers = [f"Date: {self._period_filter_var.get()}"]
        if self._type_filter_var.get() != "All transactions":
            qualifiers.append(f"Type: {self._type_filter_var.get()}")
        if self._search_var.get().strip():
            qualifiers.append(f"Find: {self._search_var.get().strip()}")
        self._status_left_var.set(
            f"Showing {len(entries)} of {len(self._raw_entries)}  •  "
            + "  •  ".join(qualifiers)
        )
        self._status_right_var.set(
            f"Visible deposits LKR {visible_in:,.2f}  |  "
            f"payments LKR {visible_out:,.2f}  |  "
            f"net {net_movement:+,.2f}"
        )
        if not entries:
            self._detail_title_var.set("No transactions match these filters")
            self._detail_meta_var.set("Clear filters or change the account and date range.")
            self._detail_action_btn.configure(state=tk.DISABLED)

    def _on_tree_selection(self, event=None) -> None:
        """Update the selected-transaction tray."""
        selected = self._tree.selection()
        if not selected:
            self._detail_action_btn.configure(state=tk.DISABLED)
            return
        entry = self._tree_data_map.get(selected[0])
        if not entry:
            self._detail_action_btn.configure(state=tk.DISABLED)
            return

        entry_type = entry.get("entry_type")
        amount = float(entry.get("outflow") or entry.get("inflow") or 0)
        direction = "Payment" if float(entry.get("outflow") or 0) else "Deposit"
        self._detail_title_var.set(
            f"{entry.get('ref') or 'No reference'}  —  {entry.get('type_label') or 'Transaction'}"
        )
        self._detail_meta_var.set(
            f"{entry.get('date') or 'No date'}  •  {self._entry_payee(entry)}  •  "
            f"{direction} LKR {amount:,.2f}  •  {self._entry_status(entry)}"
        )
        button_text = "Open transaction"
        if entry_type == "voucher":
            button_text = "Open voucher PDF"
        elif entry_type == "opening":
            button_text = "Edit account"
        elif entry_type in ("transfer_in", "transfer_out"):
            button_text = "View transfer"
        elif entry_type == "reimbursement":
            button_text = "View reimbursement"
        self._detail_action_btn.configure(text=button_text, state=tk.NORMAL)

    def _open_selected_transaction(self) -> None:
        """Open the source record for the selected register row."""
        self._on_tree_double_click()

    def _show_transfer_details(self, entry: dict) -> None:
        """Show a read-only transfer summary without risking one-sided edits."""
        amount = float(entry.get("outflow") or entry.get("inflow") or 0)
        messagebox.showinfo(
            "Cash Transfer",
            f"Reference: {entry.get('ref') or '—'}\n"
            f"Date: {entry.get('date') or '—'}\n"
            f"Amount: LKR {amount:,.2f}\n"
            f"Direction: {entry.get('type_label') or 'Transfer'}\n"
            f"Memo: {entry.get('description') or '—'}",
            parent=self.winfo_toplevel(),
        )
    def _refresh_ledger(self) -> None:
        """Reload the selected account register and summary balances."""
        if not self._selected_float_id:
            return

        date_filter = self._period_filter_var.get()
        entries, stats = db.get_float_ledger(
            self._selected_float_id,
            date_filter=date_filter,
        )
        self._raw_entries = entries
        self._ledger_stats = stats

        current_balance = float(stats.get("current_balance") or 0)
        opening_balance = float(stats.get("opening_balance") or 0)
        total_inflows = float(stats.get("total_inflows") or 0)
        total_outflows = float(stats.get("total_outflows") or 0)
        custodian = stats.get("custodian") or "None assigned"
        opening_date = stats.get("opening_date") or "—"
        unreimbursed_total = float(stats.get("unreimbursed_total") or 0)
        unreimbursed_count = int(stats.get("unreimbursed_count") or 0)

        self._kpi_vars["current_balance"].set(f"LKR {current_balance:,.2f}")
        self._kpi_vars["opening_balance"].set(f"LKR {opening_balance:,.2f}")
        self._kpi_vars["total_inflows"].set(f"LKR {total_inflows:,.2f}")
        self._kpi_vars["total_outflows"].set(f"LKR {total_outflows:,.2f}")
        self._kpi_vars["opening_date"].set(str(opening_date))
        self._kpi_vars["custodian"].set(str(custodian))
        self._kpi_vars["unreimbursed_total"].set(f"LKR {unreimbursed_total:,.2f}")
        self._kpi_vars["unreimbursed_count"].set(
            f"{unreimbursed_count} pending voucher(s)"
        )
        self._custodian_badge_var.set(f"Custodian: {custodian}")

        selected_float = next(
            (
                item
                for item in self._floats_cache
                if item["id"] == self._selected_float_id
            ),
            None,
        )
        account_text = "Unlinked ledger account"
        if selected_float and selected_float.get("linked_account_code"):
            account_text = (
                f"[{selected_float['linked_account_code']}] "
                f"{selected_float.get('linked_account_name') or ''}"
            )
        company = db.get_company(self._company_id) or {}
        company_name = company.get("name", f"Company {self._company_id}")
        self._header_subtitle_var.set(
            f"{company_name}  •  Ledger {account_text}  •  Opened {opening_date}"
        )

        self._cur_bal_lbl.configure(
            fg="#166534" if current_balance >= 0 else "#b91c1c"
        )
        self._update_header_arrows()
        self._populate_treeview()
    def _open_new_float_dialog(self):
        """Open modal to create a new money float."""
        top = self.winfo_toplevel()
        dlg = FloatEditDialog(top, company_id=self._company_id, float_id=None)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=dlg.saved_float_id)
            self._dirty = False
            self._notify_update()

    def _open_edit_float_dialog(self):
        """Open modal to edit selected float."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = FloatEditDialog(top, company_id=self._company_id, float_id=self._selected_float_id)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=self._selected_float_id)
            self._dirty = False
            self._notify_update()

    def _open_fund_reimbursement_dialog(self):
        """Open fund reimbursement modal to replenish float by settling spent vouchers."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = FundReimbursementDialog(top, float_id=self._selected_float_id, company_id=self._company_id)
        self.wait_window(dlg)
        if dlg.saved:
            self._refresh_ledger()
            self._dirty = False
            self._notify_update()

    def _open_add_transaction_dialog(self, trans_type="Inflow"):
        """Open modal to add a top-up inflow or cash adjustment."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = AddTopUpDialog(top, float_id=self._selected_float_id, trans_type=trans_type)
        self.wait_window(dlg)
        if dlg.saved:
            self._refresh_ledger()
            self._dirty = False
            self._notify_update()

    def _open_transfer_dialog(self):
        """Open inter-float transfer modal to transfer funds between drawers."""
        top = self.winfo_toplevel()
        dlg = InterFloatTransferDialog(top, company_id=self._company_id, source_float_id=self._selected_float_id)
        self.wait_window(dlg)
        if dlg.saved:
            self._refresh_ledger()
            self._dirty = False
            self._notify_update()

    def _export_ledger_csv(self):
        """Export current float ledger to CSV."""
        if not self._selected_float_id:
            return

        date_filt = self._period_filter_var.get()
        flt = db.get_float(self._selected_float_id)
        flt_name = flt.get("name", "Float").replace(" ", "_")
        default_name = f"Float_Ledger_{flt_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        top = self.winfo_toplevel()
        filepath = filedialog.asksaveasfilename(
            parent=top,
            title="Export Float Ledger to CSV",
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            db.export_float_ledger_to_csv(self._selected_float_id, filepath, date_filter=date_filt)
            messagebox.showinfo(
                "Export Successful",
                f"Float ledger successfully exported with running balances to:\n{filepath}",
                parent=top
            )
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}", parent=top)

    def _copy_selected_ref(self):
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        ref = entry.get("ref", "")
        if ref:
            self.clipboard_clear()
            self.clipboard_append(ref)

    def _on_tree_double_click(self, event=None):
        """Route double-click intelligently based on the transaction entry type."""
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        entry_type = entry.get("entry_type")

        if entry_type == "voucher":
            self._view_linked_voucher()
        elif entry_type == "reimbursement":
            self._view_reimbursement_details(entry.get("id"))
        elif entry_type in ("top_up", "cash_received", "adjustment"):
            self._view_or_edit_transaction(entry.get("id"))
        elif entry_type in ("transfer_in", "transfer_out"):
            self._show_transfer_details(entry)
        elif entry_type == "opening":
            self._open_edit_float_dialog()

    def _view_linked_voucher(self) -> None:
        """Generate, validate, and open the selected voucher PDF."""
        selected = self._tree.selection()
        if not selected:
            return
        entry = self._tree_data_map.get(selected[0], {})
        if entry.get("entry_type") != "voucher":
            return

        voucher_id = entry.get("id")
        top = self.winfo_toplevel()
        if not voucher_id or not db.get_voucher(voucher_id):
            messagebox.showerror(
                "Voucher Not Found",
                "The source voucher is not available in the active company file. "
                "Refresh the register and try again.",
                parent=top,
            )
            return

        try:
            pdf_path = printer.generate_voucher_pdf([voucher_id])
            PdfViewerDialog(
                top,
                pdf_path,
                title=f"Voucher {entry.get('ref') or voucher_id}",
                voucher_ids=[voucher_id],
            )
        except Exception as exc:
            messagebox.showerror(
                "Voucher Preview Error",
                f"Could not generate the voucher PDF:\n\n{exc}",
                parent=top,
            )
    def _view_reimbursement_details(self, trans_id=None):
        """Open modal showing reimbursement claim breakdown and linked vouchers."""
        if not trans_id:
            selected = self._tree.selection()
            if not selected:
                return
            item_id = selected[0]
            entry = self._tree_data_map.get(item_id, {})
            if entry.get("entry_type") != "reimbursement":
                return
            trans_id = entry.get("id")

        top = self.winfo_toplevel()
        dlg = ViewReimbursementDialog(top, trans_id=trans_id)
        self.wait_window(dlg)
        if dlg.modified:
            self._refresh_ledger()
            self._dirty = False
            self._notify_update()

    def _view_or_edit_transaction(self, trans_id=None):
        """Open modal to view, edit, or delete a cash transaction."""
        if not trans_id:
            selected = self._tree.selection()
            if not selected:
                return
            item_id = selected[0]
            entry = self._tree_data_map.get(item_id, {})
            if entry.get("entry_type") not in ("top_up", "cash_received", "adjustment"):
                return
            trans_id = entry.get("id")

        top = self.winfo_toplevel()
        dlg = ViewTransactionDialog(top, trans_id=trans_id)
        self.wait_window(dlg)
        if dlg.modified:
            self._refresh_ledger()
            self._dirty = False
            self._notify_update()

    def _delete_selected_transaction(self):
        """Delete selected transaction with safety confirmations."""
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        entry_type = entry.get("entry_type")
        trans_id = entry.get("id")
        top = self.winfo_toplevel()

        if entry_type == "reimbursement":
            confirm = messagebox.askyesno(
                "Delete Fund Reimbursement",
                f"Deleting this reimbursement will remove the cash inflow of LKR {entry.get('inflow', 0.0):,.2f} "
                f"and restore all associated vouchers back to 'Unreimbursed' status.\n\n"
                f"Date: {entry.get('date')}\n"
                f"Ref: {entry.get('ref')}\n\n"
                f"Do you wish to proceed?",
                parent=top,
                icon="warning"
            )
            if confirm:
                details = db.get_reimbursement_details(trans_id)
                v_ids = [v["id"] for v in details["vouchers"]] if details else []
                comp_id = entry.get("company_id", self._company_id)
                flt_id = self._selected_float_id

                db.delete_float_transaction(trans_id)
                if firebase_client.is_enabled():
                    firebase_client.delete_float_transaction_from_cloud(comp_id, trans_id, async_call=True)
                    if flt_id:
                        firebase_client.push_float_to_cloud(flt_id, async_call=True)
                    for vid in v_ids:
                        firebase_client.push_voucher_to_cloud(vid, async_call=True)
                self._refresh_ledger()
                self._dirty = False
                self._notify_update()
        elif entry_type in ("top_up", "cash_received", "adjustment"):
            amt = entry.get("inflow") if entry.get("inflow", 0.0) > 0 else entry.get("outflow", 0.0)
            confirm = messagebox.askyesno(
                "Delete Transaction",
                f"Are you sure you want to delete this {entry.get('type_label')}?\n\n"
                f"Date: {entry.get('date')}\n"
                f"Amount: LKR {amt:,.2f}\n"
                f"Ref: {entry.get('ref')}",
                parent=top,
                icon="warning"
            )
            if confirm:
                comp_id = entry.get("company_id", self._company_id)
                flt_id = self._selected_float_id

                db.delete_float_transaction(trans_id)
                if firebase_client.is_enabled():
                    firebase_client.delete_float_transaction_from_cloud(comp_id, trans_id, async_call=True)
                    if flt_id:
                        firebase_client.push_float_to_cloud(flt_id, async_call=True)
                self._refresh_ledger()
                self._dirty = False
                self._notify_update()


class MoneyFloatDialog(tk.Toplevel):
    """
    Standalone Toplevel dialog wrapper for MoneyFloatView.
    Maintained for modal popups and test backwards-compatibility.
    """

    def __init__(self, parent, company_id=None, on_update_callback=None):
        super().__init__(parent)
        self.title("💰 Company Money Float & Cash Drawer Tracking")
        self._parent = parent

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = max(1160, min(1440, screen_w - 40))
        target_h = max(680, min(900, screen_h - 60))
        self.geometry(f"{target_w}x{target_h}")
        try:
            self.grab_set()
        except Exception:
            pass

        self._view = MoneyFloatView(
            self,
            company_id=company_id,
            on_update_callback=on_update_callback,
            on_close_callback=self.destroy
        )
        self._view.pack(fill=tk.BOTH, expand=True)

        # Center on parent / screen
        self.update_idletasks()
        px = max(10, parent.winfo_rootx() + max(0, (parent.winfo_width() - target_w) // 2))
        py = max(10, parent.winfo_rooty() + max(0, (parent.winfo_height() - target_h) // 2))
        self.geometry(f"{target_w}x{target_h}+{px}+{py}")

        try:
            self.state("zoomed")
        except Exception:
            pass

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F5>", lambda e: self._view._refresh_ledger())
        self.bind("<Alt-r>", lambda e: self._view._open_fund_reimbursement_dialog())
        self.bind("<Alt-R>", lambda e: self._view._open_fund_reimbursement_dialog())
        self.bind("<Alt-a>", lambda e: self._view._open_add_transaction_dialog("Inflow"))
        self.bind("<Alt-A>", lambda e: self._view._open_add_transaction_dialog("Inflow"))
        self.bind("<Control-a>", lambda e: self._view._open_add_transaction_dialog("Inflow"))
        self.bind("<Control-A>", lambda e: self._view._open_add_transaction_dialog("Inflow"))
        self.bind("<Alt-o>", lambda e: self._view._open_add_transaction_dialog("Outflow"))
        self.bind("<Alt-O>", lambda e: self._view._open_add_transaction_dialog("Outflow"))
        self.bind("<Alt-t>", lambda e: self._view._open_transfer_dialog())
        self.bind("<Alt-T>", lambda e: self._view._open_transfer_dialog())
        self.bind("<Control-Shift-N>", lambda e: self._view._open_new_float_dialog())
        self.bind("<Control-Shift-n>", lambda e: self._view._open_new_float_dialog())
        self.bind("<Control-Shift-E>", lambda e: self._view._export_ledger_csv())
        self.bind("<Control-Shift-e>", lambda e: self._view._export_ledger_csv())

    def __getattr__(self, name):
        """Proxy any attributes or methods to underlying MoneyFloatView instance."""
        return getattr(self._view, name)


class AddTopUpDialog(tk.Toplevel):
    """Dialog to record a cash top-up / replenishment inflow or manual adjustment outflow."""

    def __init__(self, parent, float_id, trans_type="Inflow"):
        super().__init__(parent)
        self.saved = False
        self._float_id = float_id
        self._trans_type = trans_type

        title_text = "➕ Add Float Top-Up / Cash Inflow" if trans_type == "Inflow" else "➖ Add Manual Cash Outflow"
        self.title(title_text)
        self.geometry("540x580")
        self.minsize(480, 520)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        flt = db.get_float(self._float_id) or {}
        flt_name = flt.get("name", "Float")

        header_bg = "#0f172a" if self._trans_type == "Inflow" else "#1e1e2d"
        header = tk.Frame(self, bg=header_bg, padx=16, pady=12)
        header.pack(fill=tk.X)

        h_title = "➕ Cash Top-Up / Replenishment" if self._trans_type == "Inflow" else "➖ Manual Cash Outflow / Adjustment"
        tk.Label(
            header, text=h_title,
            font=("Segoe UI", 12, "bold"), bg=header_bg, fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header, text=f"Float: {flt_name}  |  Current Balance: LKR {flt.get('current_balance', 0.0):,.2f}",
            font=("Segoe UI", 8), bg=header_bg, fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Bottom Buttons Bar - Pack FIRST at side=BOTTOM before any expandable frame
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        save_style = "success" if self._trans_type == "Inflow" else "warning"
        ttk.Button(btn_bar, text="💾 Save Transaction", command=self._save, bootstyle=save_style).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)

        # Form content
        form = tk.Frame(self, padx=18, pady=12)
        form.pack(fill=tk.BOTH, expand=True)

        row = 0
        # Transaction Type
        tk.Label(form, text="Transaction Type:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._type_var = tk.StringVar(value=self._trans_type)
        type_combo = ttk.Combobox(form, textvariable=self._type_var, values=["Inflow", "Outflow"], width=20, state="readonly")
        type_combo.grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Category / Sub-Type
        tk.Label(form, text="Transaction Category:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        default_sub = "Top-Up" if self._trans_type == "Inflow" else "Adjustment"
        self._sub_type_var = tk.StringVar(value=default_sub)
        self._sub_type_combo = ttk.Combobox(form, textvariable=self._sub_type_var, width=20, state="readonly")
        self._sub_type_combo.grid(row=row, column=1, sticky="w", pady=4)

        def _on_type_change(e=None):
            t = self._type_var.get()
            if t == "Inflow":
                self._sub_type_combo["values"] = ["Top-Up", "Cash Received"]
                if self._sub_type_var.get() not in ["Top-Up", "Cash Received"]:
                    self._sub_type_var.set("Top-Up")
            else:
                self._sub_type_combo["values"] = ["Adjustment"]
                self._sub_type_var.set("Adjustment")

        type_combo.bind("<<ComboboxSelected>>", _on_type_change)
        _on_type_change()

        row += 1
        # Date
        tk.Label(form, text="Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form, textvariable=self._date_var, width=22).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Amount
        tk.Label(form, text="Amount (LKR): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._amt_var = tk.StringVar()
        amt_entry = ttk.Entry(form, textvariable=self._amt_var, width=22, font=("Segoe UI", 10, "bold"))
        amt_entry.grid(row=row, column=1, sticky="w", pady=4)
        amt_entry.focus_set()

        row += 1
        # Source / Reference
        ref_label = "Source / Cheque # / Ref:" if self._trans_type == "Inflow" else "Reference / Purpose:"
        tk.Label(form, text=ref_label, font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._ref_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._ref_var, width=32).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Handed By
        tk.Label(form, text="Handed / Issued By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._handed_var = tk.StringVar()
        people = db.get_people(active_only=True)
        handed_combo = ttk.Combobox(form, textvariable=self._handed_var, values=people, width=30)
        handed_combo.grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Received By
        tk.Label(form, text="Received By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._received_var = tk.StringVar(value=flt.get("custodian", ""))
        received_combo = ttk.Combobox(form, textvariable=self._received_var, values=people, width=30)
        received_combo.grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Notes / Remarks
        tk.Label(form, text="Notes / Remarks:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=4)
        self._notes_text = tk.Text(form, width=32, height=2, font=("Segoe UI", 9))
        self._notes_text.grid(row=row, column=1, sticky="w", pady=4)

    def _save(self):
        amt_str = self._amt_var.get().strip().replace(",", "")
        try:
            amt = float(amt_str)
            if amt <= 0:
                raise ValueError()
        except Exception:
            messagebox.showwarning("Invalid Amount", "Please enter a valid positive number for amount.", parent=self)
            return

        date_val = self._date_var.get().strip()
        if not date_val:
            date_val = datetime.now().strftime("%Y-%m-%d")

        st_val = self._sub_type_var.get()
        if st_val == "Cash Received":
            sub_type = "cash_received"
        elif st_val == "Adjustment":
            sub_type = "adjustment"
        else:
            sub_type = "top_up"

        trans_id = db.add_float_transaction(
            float_id=self._float_id,
            amount=amt,
            date=date_val,
            trans_type=self._type_var.get(),
            source_ref=self._ref_var.get().strip(),
            handed_by=self._handed_var.get().strip(),
            received_by=self._received_var.get().strip(),
            notes=self._notes_text.get("1.0", tk.END).strip(),
            sub_type=sub_type,
        )

        if firebase_client.is_enabled():
            firebase_client.push_float_transaction_to_cloud(trans_id, async_call=True)
            firebase_client.push_float_to_cloud(self._float_id, async_call=True)

        self.saved = True
        self.destroy()


class FloatEditDialog(tk.Toplevel):
    """Dialog to create or edit a Money Float profile."""

    def __init__(self, parent, company_id, float_id=None):
        super().__init__(parent)
        self.saved_float_id = None
        self._company_id = company_id
        self._float_id = float_id

        title_text = "➕ Create New Money Float" if float_id is None else "✏️ Edit Money Float"
        self.title(title_text)
        self.geometry("520x540")
        self.minsize(460, 480)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        h_title = "➕ New Money Float / Drawer" if self._float_id is None else "✏️ Edit Money Float Settings"
        tk.Label(
            header, text=h_title,
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header, text="Set up cash float opening balances and custodians.",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        existing = {}
        if self._float_id:
            existing = db.get_float(self._float_id) or {}

        # Bottom Buttons Bar - Pack FIRST at side=BOTTOM before expandable form
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_bar, text="💾 Save Float", command=self._save, bootstyle="success").pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)

        form = tk.Frame(self, padx=18, pady=12)
        form.pack(fill=tk.BOTH, expand=True)

        row = 0
        # Float Name
        tk.Label(form, text="Float Name: *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._name_var = tk.StringVar(value=existing.get("name", ""))
        name_entry = ttk.Entry(form, textvariable=self._name_var, width=28)
        name_entry.grid(row=row, column=1, sticky="w", pady=4)
        name_entry.focus_set()

        row += 1
        # Custodian
        tk.Label(form, text="Custodian / Responsible:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._custodian_var = tk.StringVar(value=existing.get("custodian", ""))
        people = db.get_people(active_only=True)
        ttk.Combobox(form, textvariable=self._custodian_var, values=people, width=26).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Opening Balance
        tk.Label(form, text="Opening Balance (LKR):", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        op_val = f"{existing.get('opening_balance', 0.0):.2f}" if self._float_id else "0.00"
        self._ob_var = tk.StringVar(value=op_val)
        ttk.Entry(form, textvariable=self._ob_var, width=22).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Opening Date
        tk.Label(form, text="Opening Date (YYYY-MM-DD):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        def_date = existing.get("opening_date") or datetime.now().strftime("%Y-%m-%d")
        self._ob_date_var = tk.StringVar(value=def_date)
        ttk.Entry(form, textvariable=self._ob_date_var, width=22).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Linked Ledger Account (COA Cash / Asset Account)
        tk.Label(form, text="Linked Ledger Account: *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        
        self.account_selector = SearchableAccountSelector(
            form,
            company_id=self._company_id,
            default_account_type="Asset",
            allowed_types=["Asset"],
            include_unlinked=False
        )
        self.account_selector.grid(row=row, column=1, sticky="w", pady=4)
        if existing.get("account_id"):
            self.account_selector.set_account_id(existing["account_id"])

        row += 1
        # Is Default Checkbox
        self._is_default_var = tk.BooleanVar(value=bool(existing.get("is_default", False)))
        ttk.Checkbutton(
            form, text="Set as Default Float for Cash Vouchers",
            variable=self._is_default_var, bootstyle="round-toggle"
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=6)

        row += 1
        # Notes
        tk.Label(form, text="Notes / Description:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=4)
        self._notes_text = tk.Text(form, width=28, height=3, font=("Segoe UI", 9))
        if existing.get("notes"):
            self._notes_text.insert("1.0", existing["notes"])
        self._notes_text.grid(row=row, column=1, sticky="w", pady=4)

    @property
    def _account_var(self):
        return self.account_selector.entry_var

    @property
    def _acct_combo(self):
        return self.account_selector.entry

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Required Field", "Please enter a Float Name.", parent=self)
            return

        try:
            ob = float(self._ob_var.get().strip().replace(",", "") or 0.0)
        except Exception:
            messagebox.showwarning("Invalid Amount", "Please enter a valid number for Opening Balance.", parent=self)
            return

        ob_date = self._ob_date_var.get().strip() or datetime.now().strftime("%Y-%m-%d")
        custodian = self._custodian_var.get().strip()
        notes = self._notes_text.get("1.0", tk.END).strip()
        is_def = self._is_default_var.get()
        acct_id = self.account_selector.get_account_id()

        if self._float_id:
            db.update_float(self._float_id, {
                "name": name,
                "custodian": custodian,
                "opening_balance": ob,
                "opening_date": ob_date,
                "notes": notes,
                "is_default": 1 if is_def else 0,
                "account_id": acct_id,
            })
            self.saved_float_id = self._float_id
        else:
            new_id = db.create_float(
                company_id=self._company_id,
                name=name,
                opening_balance=ob,
                opening_date=ob_date,
                custodian=custodian,
                notes=notes,
                is_default=is_def,
                account_id=acct_id,
            )
            self.saved_float_id = new_id

        if self.saved_float_id and firebase_client.is_enabled():
            firebase_client.push_float_to_cloud(self.saved_float_id, async_call=True)

        self.destroy()


class FundReimbursementDialog(tk.Toplevel):
    """
    Dialog for Petty Cash Fund Reimbursement / Replenishment.
    Allows custodians to select spent unreimbursed vouchers, calculate reimbursement claim,
    record replenish inflow, and atomically mark selected vouchers as Reimbursed.
    """

    def __init__(self, parent, float_id, company_id=None):
        super().__init__(parent)
        self.saved = False
        self._float_id = float_id
        self._company_id = company_id or db.get_active_company_id()
        self._selected_voucher_ids = set()
        self._unreimbursed_vouchers = []
        self._sync_amount_with_selection = True

        self.title("🔄 Petty Cash Fund Reimbursement / Replenishment")
        self.geometry("920x690")
        self.minsize(820, 600)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_unreimbursed_vouchers()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        flt = db.get_float(self._float_id) or {}
        flt_name = flt.get("name", "Float")
        cur_bal = flt.get("current_balance", 0.0)
        custodian = flt.get("custodian") or "None Assigned"

        # Top Header Banner
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="🔄 Petty Cash Fund Reimbursement & Replenishment",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Float: {flt_name}   |   Current Balance: LKR {cur_bal:,.2f}   |   Custodian: {custodian}",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Bottom Buttons Bar - Pack FIRST at side=BOTTOM before expandable content
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        save_btn = ttk.Button(btn_bar, text="💾 Approve & Replenish Float", command=self._save, bootstyle="success")
        save_btn.pack(side=tk.RIGHT, padx=4)

        cancel_btn = ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline")
        cancel_btn.pack(side=tk.RIGHT, padx=4)

        content = tk.Frame(self, padx=14, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # Instruction & Action Bar above table
        top_bar = tk.Frame(content)
        top_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            top_bar,
            text="1. Select spent vouchers to claim reimbursement for:",
            font=("Segoe UI", 9, "bold"), fg="#1e293b"
        ).pack(side=tk.LEFT)

        btn_select_all = ttk.Button(
            top_bar, text="☑️ Select All",
            command=self._select_all_vouchers, bootstyle="secondary-outline"
        )
        btn_select_all.pack(side=tk.RIGHT, padx=2)

        btn_clear_all = ttk.Button(
            top_bar, text="◻️ Clear All",
            command=self._clear_all_vouchers, bootstyle="secondary-outline"
        )
        btn_clear_all.pack(side=tk.RIGHT, padx=2)

        # Vouchers Treeview Frame
        tree_frame = tk.Frame(content)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        columns = ("select", "voucher_num", "date", "paid_to", "spent_by", "method", "amount")
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse", height=9)

        col_defs = [
            ("select", "Claim?", 60, "center"),
            ("voucher_num", "Voucher #", 110, "center"),
            ("date", "Date", 85, "center"),
            ("paid_to", "Paid To / Beneficiary", 220, "w"),
            ("spent_by", "Spent By", 120, "w"),
            ("method", "Method", 90, "center"),
            ("amount", "Amount (LKR)", 115, "e"),
        ]

        for col_id, col_name, width, align in col_defs:
            self._tree.heading(col_id, text=col_name, anchor=align)
            self._tree.column(col_id, width=width, anchor=align)

        self._tree.tag_configure("selected_row", background="#f0fdf4", foreground="#166534")
        self._tree.tag_configure("unselected_row", background="#ffffff", foreground="#334155")

        tree_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._tree.bind("<Button-1>", self._on_tree_click)
        self._tree.bind("<space>", lambda e: self._toggle_highlighted_row())
        self._tree.bind("<Double-1>", lambda e: self._on_tree_double_click())

        # Claim Summary Bar
        self._claim_summary_var = tk.StringVar(value="Selected: 0 voucher(s) | Total Selected Claim: LKR 0.00")
        summary_bar = tk.Frame(content, bg="#eff6ff", padx=10, pady=6, highlightbackground="#bfdbfe", highlightthickness=1)
        summary_bar.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            summary_bar, textvariable=self._claim_summary_var,
            font=("Segoe UI", 9, "bold"), bg="#eff6ff", fg="#1d4ed8"
        ).pack(side=tk.LEFT)

        tk.Label(
            summary_bar, text="💡 Tip: Click row or press Space to select / deselect. Double-click to preview voucher.",
            font=("Segoe UI", 8), bg="#eff6ff", fg="#3b82f6"
        ).pack(side=tk.RIGHT)

        # Section 2: Reimbursement Inflow Details
        tk.Label(
            content, text="2. Reimbursement & Replenishment Details:",
            font=("Segoe UI", 9, "bold"), fg="#1e293b"
        ).pack(anchor="w", pady=(0, 4))

        form_frame = tk.Frame(content, bg="#f8fafc", padx=14, pady=10, highlightbackground="#e2e8f0", highlightthickness=1)
        form_frame.pack(fill=tk.X)

        # Row 0
        tk.Label(form_frame, text="Reimbursement Amount (LKR): *", font=("Segoe UI", 9, "bold"), bg="#f8fafc").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 6))
        self._amt_var = tk.StringVar()
        self._amt_entry = ttk.Entry(form_frame, textvariable=self._amt_var, width=20, font=("Segoe UI", 10, "bold"))
        self._amt_entry.grid(row=0, column=1, sticky="w", pady=4, padx=(0, 16))

        tk.Label(form_frame, text="Date (YYYY-MM-DD): *", font=("Segoe UI", 9, "bold"), bg="#f8fafc").grid(row=0, column=2, sticky="w", pady=4, padx=(0, 6))
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form_frame, textvariable=self._date_var, width=18).grid(row=0, column=3, sticky="w", pady=4)

        # Row 1
        tk.Label(form_frame, text="Replenishment Ref / Cheque #:", font=("Segoe UI", 9), bg="#f8fafc").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 6))
        self._ref_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self._ref_var, width=28).grid(row=1, column=1, sticky="w", pady=4, padx=(0, 16))

        tk.Label(form_frame, text="Handed / Approved By:", font=("Segoe UI", 9), bg="#f8fafc").grid(row=1, column=2, sticky="w", pady=4, padx=(0, 6))
        self._handed_var = tk.StringVar()
        people = db.get_people(active_only=True)
        ttk.Combobox(form_frame, textvariable=self._handed_var, values=people, width=24).grid(row=1, column=3, sticky="w", pady=4)

        # Row 2
        tk.Label(form_frame, text="Received By (Custodian):", font=("Segoe UI", 9), bg="#f8fafc").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 6))
        self._received_var = tk.StringVar(value=flt.get("custodian", ""))
        ttk.Combobox(form_frame, textvariable=self._received_var, values=people, width=28).grid(row=2, column=1, sticky="w", pady=4, padx=(0, 16))

        tk.Label(form_frame, text="Notes / Claim Remarks:", font=("Segoe UI", 9), bg="#f8fafc").grid(row=2, column=2, sticky="w", pady=4, padx=(0, 6))
        self._notes_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self._notes_var, width=26).grid(row=2, column=3, sticky="w", pady=4)

    def _load_unreimbursed_vouchers(self):
        vouchers = db.get_unreimbursed_vouchers(float_id=self._float_id, company_id=self._company_id)
        self._unreimbursed_vouchers = vouchers
        # Default: select all pending vouchers for smooth 1-click replenishment!
        self._selected_voucher_ids = {v["id"] for v in vouchers}
        self._render_treeview()

    def _render_treeview(self):
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)

        for v in self._unreimbursed_vouchers:
            v_id = v["id"]
            is_sel = v_id in self._selected_voucher_ids
            mark = "☑ [✓]" if is_sel else "☐ [  ]"
            tag = "selected_row" if is_sel else "unselected_row"
            self._tree.insert(
                "", tk.END, iid=str(v_id),
                values=(
                    mark,
                    v.get("voucher_number", ""),
                    v.get("date", ""),
                    v.get("paid_to", ""),
                    v.get("spent_by") or "—",
                    v.get("payment_method") or "Cash",
                    f"{float(v.get('total_amount', 0.0)):,.2f}"
                ),
                tags=(tag,)
            )

        self._update_selection_summary()

    def _update_selection_summary(self):
        sel_vouchers = [v for v in self._unreimbursed_vouchers if v["id"] in self._selected_voucher_ids]
        sel_count = len(sel_vouchers)
        sel_total = sum(float(v.get("total_amount", 0.0)) for v in sel_vouchers)
        all_count = len(self._unreimbursed_vouchers)
        all_total = sum(float(v.get("total_amount", 0.0)) for v in self._unreimbursed_vouchers)

        self._claim_summary_var.set(
            f"Selected: {sel_count} of {all_count} voucher(s)  |  "
            f"Total Selected Claim: LKR {sel_total:,.2f}  |  "
            f"Total Unreimbursed Pool: LKR {all_total:,.2f}"
        )

        if self._sync_amount_with_selection:
            self._amt_var.set(f"{sel_total:,.2f}")

    def _select_all_vouchers(self):
        self._selected_voucher_ids = {v["id"] for v in self._unreimbursed_vouchers}
        self._render_treeview()

    def _clear_all_vouchers(self):
        self._selected_voucher_ids.clear()
        self._render_treeview()

    def _toggle_voucher(self, v_id):
        if v_id in self._selected_voucher_ids:
            self._selected_voucher_ids.remove(v_id)
        else:
            self._selected_voucher_ids.add(v_id)
        self._render_treeview()

    def _on_tree_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            try:
                v_id = int(item)
                self._toggle_voucher(v_id)
            except Exception:
                pass

    def _toggle_highlighted_row(self):
        sel = self._tree.selection()
        if sel:
            try:
                v_id = int(sel[0])
                self._toggle_voucher(v_id)
            except Exception:
                pass

    def _on_tree_double_click(self):
        sel = self._tree.selection()
        if sel:
            try:
                v_id = int(sel[0])
                pdf_path = printer.generate_voucher_pdf([v_id])
                PdfViewerDialog(self, pdf_path, voucher_ids=[v_id])
            except Exception as ex:
                messagebox.showinfo("Preview Voucher", f"Could not preview PDF: {ex}", parent=self)

    def _save(self):
        amt_str = self._amt_var.get().strip().replace(",", "")
        try:
            amt = float(amt_str)
            if amt <= 0:
                raise ValueError()
        except Exception:
            messagebox.showwarning("Invalid Amount", "Please enter a valid positive reimbursement amount.", parent=self)
            return

        date_val = self._date_var.get().strip() or datetime.now().strftime("%Y-%m-%d")
        ref_val = self._ref_var.get().strip() or "Fund Reimbursement"
        handed_val = self._handed_var.get().strip()
        received_val = self._received_var.get().strip()
        notes_val = self._notes_var.get().strip()

        v_ids = list(self._selected_voucher_ids)
        if not v_ids:
            confirm = messagebox.askyesno(
                "No Vouchers Selected",
                "No vouchers are selected to link to this replenishment.\n\n"
                "Do you want to proceed with recording an unlinked cash replenishment?",
                parent=self
            )
            if not confirm:
                return

        trans_id = db.create_fund_reimbursement(
            float_id=self._float_id,
            amount=amt,
            voucher_ids=v_ids,
            date=date_val,
            source_ref=ref_val,
            handed_by=handed_val,
            received_by=received_val,
            notes=notes_val,
            company_id=self._company_id
        )

        if firebase_client.is_enabled():
            firebase_client.push_float_transaction_to_cloud(trans_id, async_call=True)
            firebase_client.push_float_to_cloud(self._float_id, async_call=True)
            for vid in v_ids:
                firebase_client.push_voucher_to_cloud(vid, async_call=True)

        messagebox.showinfo(
            "Reimbursement Recorded",
            f"Successfully recorded replenishment of LKR {amt:,.2f}.\n"
            f"{len(v_ids)} voucher(s) have been marked as Reimbursed.",
            parent=self
        )
        self.saved = True
        self.destroy()


class ViewReimbursementDialog(tk.Toplevel):
    """Dialog to inspect a fund reimbursement claim and all covered vouchers."""

    def __init__(self, parent, trans_id):
        super().__init__(parent)
        self.modified = False
        self._trans_id = trans_id

        self.title("🔄 Fund Reimbursement Details")
        self.geometry("820x560")
        self.minsize(720, 480)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        details = db.get_reimbursement_details(self._trans_id)
        if not details:
            tk.Label(self, text="Reimbursement transaction not found.").pack(padx=20, pady=20)
            return

        tr = details["transaction"]
        vouchers = details["vouchers"]
        tot_amt = float(tr.get("amount", 0.0))
        ref = tr.get("source_ref") or "Reimbursement"
        d_val = tr.get("date") or ""

        # Header
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=f"🔄 Fund Reimbursement: {ref}",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header,
            text=f"Date: {d_val}   |   Amount Replenished: LKR {tot_amt:,.2f}   |   Vouchers Settled: {len(vouchers)}",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Bottom Buttons Bar - Pack FIRST at side=BOTTOM before expandable content
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        del_btn = ttk.Button(btn_bar, text="🗑️ Delete Reimbursement", command=self._delete_reimbursement, bootstyle="danger-outline")
        del_btn.pack(side=tk.LEFT)

        close_btn = ttk.Button(btn_bar, text="Close", command=self.destroy, bootstyle="secondary")
        close_btn.pack(side=tk.RIGHT)

        content = tk.Frame(self, padx=14, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # Overview Grid
        card = tk.Frame(content, bg="#f8fafc", padx=12, pady=8, highlightbackground="#e2e8f0", highlightthickness=1)
        card.pack(fill=tk.X, pady=(0, 10))

        info_items = [
            ("Date:", d_val),
            ("Replenishment Amount:", f"+LKR {tot_amt:,.2f}"),
            ("Reference / Cheque #:", ref),
            ("Handed / Approved By:", tr.get("handed_by") or "—"),
            ("Received By (Custodian):", tr.get("received_by") or "—"),
            ("Notes / Remarks:", tr.get("notes") or "—"),
        ]

        for i, (label, val) in enumerate(info_items):
            r = i // 2
            c = (i % 2) * 2
            tk.Label(card, text=label, font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569").grid(row=r, column=c, sticky="w", padx=(0, 6), pady=2)
            tk.Label(card, text=val, font=("Segoe UI", 8), bg="#f8fafc", fg="#0f172a").grid(row=r, column=c+1, sticky="w", padx=(0, 20), pady=2)

        # Vouchers Table
        tk.Label(
            content, text=f"Reimbursed Vouchers ({len(vouchers)} linked):",
            font=("Segoe UI", 9, "bold"), fg="#1e293b"
        ).pack(anchor="w", pady=(0, 4))

        tree_frame = tk.Frame(content)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("voucher_num", "date", "paid_to", "spent_by", "method", "amount")
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        col_defs = [
            ("voucher_num", "Voucher #", 110, "center"),
            ("date", "Date", 85, "center"),
            ("paid_to", "Paid To", 220, "w"),
            ("spent_by", "Spent By", 120, "w"),
            ("method", "Method", 90, "center"),
            ("amount", "Amount (LKR)", 110, "e"),
        ]
        for col_id, col_name, width, align in col_defs:
            self._tree.heading(col_id, text=col_name, anchor=align)
            self._tree.column(col_id, width=width, anchor=align)

        tree_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        tree_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        tree_y.grid(row=0, column=1, sticky="ns")
        tree_x.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        for v in vouchers:
            v_id = v["id"]
            self._tree.insert(
                "", tk.END, iid=str(v_id),
                values=(
                    v.get("voucher_number", ""),
                    v.get("date", ""),
                    v.get("paid_to", ""),
                    v.get("spent_by") or "—",
                    v.get("payment_method") or "Cash",
                    f"{float(v.get('total_amount', 0.0)):,.2f}"
                )
            )

        self._tree.bind("<Double-1>", self._on_double_click_voucher)

        # Tip
        tk.Label(
            content, text="💡 Tip: Double-click any voucher row to preview its full PDF voucher.",
            font=("Segoe UI", 8), fg="#64748b"
        ).pack(anchor="w", pady=(4, 0))

    def _on_double_click_voucher(self, event=None):
        sel = self._tree.selection()
        if not sel:
            return
        v_id = int(sel[0])
        try:
            pdf_path = printer.generate_voucher_pdf([v_id])
            PdfViewerDialog(self, pdf_path, voucher_ids=[v_id])
        except Exception as ex:
            messagebox.showinfo("Voucher Preview", f"Could not generate PDF: {ex}", parent=self)

    def _delete_reimbursement(self):
        details = db.get_reimbursement_details(self._trans_id)
        if not details:
            return
        v_count = len(details["vouchers"])
        amt = float(details["transaction"].get("amount", 0.0))

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Deleting this reimbursement will remove the cash inflow of LKR {amt:,.2f} "
            f"and reset {v_count} linked voucher(s) back to Unreimbursed status.\n\n"
            f"Are you sure you want to proceed?",
            parent=self,
            icon="warning"
        )
        if confirm:
            v_ids = [v["id"] for v in details["vouchers"]]
            tr = details["transaction"]
            comp_id = tr.get("company_id", 1)
            flt_id = tr.get("float_id")

            db.delete_float_transaction(self._trans_id)
            if firebase_client.is_enabled():
                firebase_client.delete_float_transaction_from_cloud(comp_id, self._trans_id, async_call=True)
                if flt_id:
                    firebase_client.push_float_to_cloud(flt_id, async_call=True)
                for vid in v_ids:
                    firebase_client.push_voucher_to_cloud(vid, async_call=True)

            self.modified = True
            messagebox.showinfo("Deleted", "Reimbursement deleted and vouchers restored to unreimbursed status.", parent=self)
            self.destroy()


class ViewTransactionDialog(tk.Toplevel):
    """Dialog to view, edit, or delete a general float transaction (Top-Up, Cash Received, Adjustment)."""

    def __init__(self, parent, trans_id):
        super().__init__(parent)
        self.modified = False
        self._trans_id = trans_id

        self.title("✏️ Cash Transaction Details")
        self.geometry("550x590")
        self.minsize(480, 520)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        tr = db.get_float_transaction(self._trans_id)
        if not tr:
            tk.Label(self, text="Transaction not found.").pack(padx=20, pady=20)
            return

        is_inflow = tr.get("type") == "Inflow"
        sub_type = tr.get("sub_type") or ("top_up" if is_inflow else "adjustment")
        amt = float(tr.get("amount", 0.0))

        header_bg = "#0f172a" if is_inflow else "#1e1e2d"
        header = tk.Frame(self, bg=header_bg, padx=16, pady=12)
        header.pack(fill=tk.X)

        title_text = "📥 Cash Transaction Details" if is_inflow else "➖ Cash Outflow Details"
        tk.Label(
            header, text=title_text,
            font=("Segoe UI", 12, "bold"), bg=header_bg, fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header, text=f"Transaction ID: #{tr['id']}   |   Type: {tr.get('type')}",
            font=("Segoe UI", 8), bg=header_bg, fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Bottom Buttons Bar - Pack FIRST at side=BOTTOM before expandable form
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        del_btn = ttk.Button(btn_bar, text="🗑️ Delete", command=self._delete, bootstyle="danger-outline")
        del_btn.pack(side=tk.LEFT)

        cancel_btn = ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline")
        cancel_btn.pack(side=tk.RIGHT, padx=4)

        save_btn = ttk.Button(btn_bar, text="💾 Save Changes", command=self._save, bootstyle="success")
        save_btn.pack(side=tk.RIGHT, padx=4)

        form = tk.Frame(self, padx=18, pady=12)
        form.pack(fill=tk.BOTH, expand=True)

        row = 0
        # Transaction Type
        tk.Label(form, text="Transaction Type:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._type_var = tk.StringVar(value=tr.get("type", "Inflow"))
        type_combo = ttk.Combobox(form, textvariable=self._type_var, values=["Inflow", "Outflow"], width=20, state="readonly")
        type_combo.grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Sub-Type
        tk.Label(form, text="Category:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        sub_map = {"top_up": "Top-Up", "cash_received": "Cash Received", "adjustment": "Adjustment"}
        self._sub_type_var = tk.StringVar(value=sub_map.get(sub_type, "Top-Up"))
        self._sub_type_combo = ttk.Combobox(form, textvariable=self._sub_type_var, width=20, state="readonly")
        self._sub_type_combo.grid(row=row, column=1, sticky="w", pady=4)

        def _on_type_change(e=None):
            t = self._type_var.get()
            if t == "Inflow":
                self._sub_type_combo["values"] = ["Top-Up", "Cash Received"]
                if self._sub_type_var.get() not in ["Top-Up", "Cash Received"]:
                    self._sub_type_var.set("Cash Received")
            else:
                self._sub_type_combo["values"] = ["Adjustment"]
                self._sub_type_var.set("Adjustment")

        type_combo.bind("<<ComboboxSelected>>", _on_type_change)
        if is_inflow:
            self._sub_type_combo["values"] = ["Top-Up", "Cash Received"]
        else:
            self._sub_type_combo["values"] = ["Adjustment"]

        row += 1
        # Date
        tk.Label(form, text="Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._date_var = tk.StringVar(value=tr.get("date", ""))
        ttk.Entry(form, textvariable=self._date_var, width=20).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Amount
        tk.Label(form, text="Amount (LKR): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=4)
        self._amt_var = tk.StringVar(value=f"{amt:.2f}")
        ttk.Entry(form, textvariable=self._amt_var, width=20, font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Reference
        tk.Label(form, text="Source / Cheque # / Ref:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._ref_var = tk.StringVar(value=tr.get("source_ref", ""))
        ttk.Entry(form, textvariable=self._ref_var, width=30).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Handed By
        tk.Label(form, text="Handed / Issued By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._handed_var = tk.StringVar(value=tr.get("handed_by", ""))
        people = db.get_people(active_only=True)
        ttk.Combobox(form, textvariable=self._handed_var, values=people, width=28).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Received By
        tk.Label(form, text="Received By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=4)
        self._received_var = tk.StringVar(value=tr.get("received_by", ""))
        ttk.Combobox(form, textvariable=self._received_var, values=people, width=28).grid(row=row, column=1, sticky="w", pady=4)

        row += 1
        # Notes
        tk.Label(form, text="Notes / Remarks:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=4)
        self._notes_text = tk.Text(form, width=30, height=2, font=("Segoe UI", 9))
        if tr.get("notes"):
            self._notes_text.insert("1.0", tr["notes"])
        self._notes_text.grid(row=row, column=1, sticky="w", pady=4)

    def _save(self):
        amt_str = self._amt_var.get().strip().replace(",", "")
        try:
            amt = float(amt_str)
            if amt <= 0:
                raise ValueError()
        except Exception:
            messagebox.showwarning("Invalid Amount", "Please enter a valid positive number for amount.", parent=self)
            return

        date_val = self._date_var.get().strip() or datetime.now().strftime("%Y-%m-%d")
        st_val = self._sub_type_var.get()
        if st_val == "Cash Received":
            sub_type = "cash_received"
        elif st_val == "Adjustment":
            sub_type = "adjustment"
        else:
            sub_type = "top_up"

        db.update_float_transaction(self._trans_id, {
            "date": date_val,
            "type": self._type_var.get(),
            "amount": amt,
            "sub_type": sub_type,
            "source_ref": self._ref_var.get().strip(),
            "handed_by": self._handed_var.get().strip(),
            "received_by": self._received_var.get().strip(),
            "notes": self._notes_text.get("1.0", tk.END).strip()
        })

        if firebase_client.is_enabled():
            firebase_client.push_float_transaction_to_cloud(self._trans_id, async_call=True)
            tr = db.get_float_transaction(self._trans_id)
            if tr:
                firebase_client.push_float_to_cloud(tr["float_id"], async_call=True)

        self.modified = True
        self.destroy()

    def _delete(self):
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete this transaction?",
            parent=self,
            icon="warning"
        )
        if confirm:
            tr = db.get_float_transaction(self._trans_id)
            comp_id = tr.get("company_id", 1) if tr else 1
            flt_id = tr.get("float_id") if tr else None

            db.delete_float_transaction(self._trans_id)
            if firebase_client.is_enabled():
                firebase_client.delete_float_transaction_from_cloud(comp_id, self._trans_id, async_call=True)
                if flt_id:
                    firebase_client.push_float_to_cloud(flt_id, async_call=True)

            self.modified = True
            self.destroy()


class InterFloatTransferDialog(tk.Toplevel):
    """
    Dialog to transfer cash balance between two money floats / drawers.
    """

    def __init__(self, parent, company_id=None, source_float_id=None):
        super().__init__(parent)
        self.saved = False
        self._company_id = company_id or db.get_active_company_id()
        self._source_float_id = source_float_id

        self.title("↔️ Inter-Float Cash Transfer")
        self.geometry("560x600")
        self.minsize(500, 540)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="↔️ Inter-Float Cash Transfer",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header, text="Transfer funds directly between company petty cash drawers.",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Bottom Buttons Bar
        btn_bar = tk.Frame(self, padx=16, pady=12, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_bar, text="↔️ Transfer Cash", command=self._save, bootstyle="info").pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)

        form = tk.Frame(self, padx=18, pady=12)
        form.pack(fill=tk.BOTH, expand=True)

        floats = db.get_floats(self._company_id, active_only=True)
        if len(floats) < 2:
            tk.Label(
                form,
                text="⚠️ At least two active cash floats are required to perform an inter-float transfer.\nCreate a new float first.",
                font=("Segoe UI", 9, "bold"), fg="#dc2626", justify="left"
            ).pack(anchor="w", pady=10)
            return

        self._floats_map = {f["id"]: f for f in floats}
        float_names = [f["name"] for f in floats]

        row = 0
        # Source Float
        tk.Label(form, text="Source Float (From): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._source_combo = ttk.Combobox(form, values=float_names, width=28, state="readonly")
        self._source_combo.grid(row=row, column=1, sticky="w", pady=6)

        # Set default source float
        s_idx = 0
        if self._source_float_id:
            for i, f in enumerate(floats):
                if f["id"] == self._source_float_id:
                    s_idx = i
                    break
        self._source_combo.current(s_idx)

        row += 1
        # Target Float
        tk.Label(form, text="Target Float (To): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._target_combo = ttk.Combobox(form, width=28, state="readonly")
        self._target_combo.grid(row=row, column=1, sticky="w", pady=6)

        def _update_target_combobox(e=None):
            curr_s_idx = self._source_combo.current()
            if 0 <= curr_s_idx < len(floats):
                s_id = floats[curr_s_idx]["id"]
                valid_targets = [f["name"] for f in floats if f["id"] != s_id]
                self._target_combo["values"] = valid_targets
                if valid_targets:
                    self._target_combo.current(0)

        self._source_combo.bind("<<ComboboxSelected>>", _update_target_combobox)
        _update_target_combobox()

        row += 1
        # Transfer Amount
        tk.Label(form, text="Transfer Amount (LKR): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._amt_var = tk.StringVar()
        amt_entry = ttk.Entry(form, textvariable=self._amt_var, width=22, font=("Segoe UI", 10, "bold"))
        amt_entry.grid(row=row, column=1, sticky="w", pady=6)
        amt_entry.focus_set()

        row += 1
        # Date
        tk.Label(form, text="Transfer Date (YYYY-MM-DD):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form, textvariable=self._date_var, width=22).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Handed By
        tk.Label(form, text="Handed / Released By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._handed_var = tk.StringVar()
        people = db.get_people(active_only=True)
        ttk.Combobox(form, textvariable=self._handed_var, values=people, width=28).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Received By
        tk.Label(form, text="Received By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._received_var = tk.StringVar()
        ttk.Combobox(form, textvariable=self._received_var, values=people, width=28).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Notes
        tk.Label(form, text="Notes / Purpose:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=6)
        self._notes_text = tk.Text(form, width=30, height=3, font=("Segoe UI", 9))
        self._notes_text.grid(row=row, column=1, sticky="w", pady=6)

    def _save(self):
        floats = list(self._floats_map.values())
        s_idx = self._source_combo.current()
        if not (0 <= s_idx < len(floats)):
            messagebox.showwarning("Selection Error", "Please select a valid Source Float.", parent=self)
            return

        s_float = floats[s_idx]
        t_name = self._target_combo.get().strip()

        t_float = next((f for f in floats if f["name"] == t_name), None)
        if not t_float:
            messagebox.showwarning("Selection Error", "Please select a valid Target Float.", parent=self)
            return

        if s_float["id"] == t_float["id"]:
            messagebox.showwarning("Selection Error", "Source float and Target float must be different.", parent=self)
            return

        amt_str = self._amt_var.get().strip().replace(",", "")
        try:
            amt = float(amt_str)
            if amt <= 0:
                raise ValueError()
        except Exception:
            messagebox.showwarning("Invalid Amount", "Please enter a valid positive number for transfer amount.", parent=self)
            return

        date_val = self._date_var.get().strip() or datetime.now().strftime("%Y-%m-%d")
        handed_val = self._handed_var.get().strip()
        received_val = self._received_var.get().strip()
        notes_val = self._notes_text.get("1.0", tk.END).strip()

        try:
            s_txn_id, t_txn_id = db.transfer_float_balance(
                source_float_id=s_float["id"],
                target_float_id=t_float["id"],
                amount=amt,
                date=date_val,
                handed_by=handed_val,
                received_by=received_val,
                notes=notes_val,
                company_id=self._company_id
            )

            if firebase_client.is_enabled():
                firebase_client.push_float_transaction_to_cloud(s_txn_id, async_call=True)
                firebase_client.push_float_transaction_to_cloud(t_txn_id, async_call=True)
                firebase_client.push_float_to_cloud(s_float["id"], async_call=True)
                firebase_client.push_float_to_cloud(t_float["id"], async_call=True)

            messagebox.showinfo(
                "Transfer Successful",
                f"Successfully transferred LKR {amt:,.2f} from '{s_float['name']}' to '{t_float['name']}'.",
                parent=self
            )
            self.saved = True
            self.destroy()
        except Exception as e:
            messagebox.showerror("Transfer Error", f"Failed to perform transfer: {e}", parent=self)
