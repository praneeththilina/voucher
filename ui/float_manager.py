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

        self._build_ui()
        self._load_floats()

    def set_company_id(self, company_id):
        """Update active company ID and reload floats ledger."""
        if self._company_id != company_id:
            self._company_id = company_id
            comp = db.get_company(self._company_id) or {}
            comp_name = comp.get("name", f"Company {self._company_id}")
            if hasattr(self, "_header_subtitle_var"):
                self._header_subtitle_var.set(
                    f"Active Profile: {comp_name}  |  Real-time cash replenishment & voucher outflow tracking"
                )
            self._load_floats()

    def refresh(self):
        """Refresh floats cache and current ledger."""
        active_comp = db.get_active_company_id()
        if self._company_id != active_comp:
            self.set_company_id(active_comp)
        else:
            self._load_floats(select_float_id=self._selected_float_id)

    def _on_close(self):
        """Handle close / back navigation."""
        if self._on_close_callback:
            try:
                self._on_close_callback()
            except Exception:
                pass

    def _build_ui(self):
        comp = db.get_company(self._company_id) or {}
        comp_name = comp.get("name", f"Company {self._company_id}")

        # Top Header Banner
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)

        top_row = tk.Frame(header, bg="#0f172a")
        top_row.pack(fill=tk.X)

        title_box = tk.Frame(top_row, bg="#0f172a")
        title_box.pack(side=tk.LEFT)

        tk.Label(
            title_box, text="💰 Company Money Float & Cash Drawer Tracking",
            font=("Segoe UI", 13, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        self._header_subtitle_var = tk.StringVar(
            value=f"Active Profile: {comp_name}  |  Real-time cash replenishment & voucher outflow tracking"
        )
        tk.Label(
            title_box, textvariable=self._header_subtitle_var,
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Float Selector & Controls on Right of Header
        float_ctrl = tk.Frame(top_row, bg="#0f172a")
        float_ctrl.pack(side=tk.RIGHT)

        tk.Label(
            float_ctrl, text="Select Float:",
            font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#cbd5e1"
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._float_selector_var = tk.StringVar()
        self._float_combo = ttk.Combobox(
            float_ctrl, textvariable=self._float_selector_var,
            width=22, state="readonly"
        )
        self._float_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._float_combo.bind("<<ComboboxSelected>>", self._on_float_selected)

        new_flt_btn = ttk.Button(
            float_ctrl, text="➕ New Float (Ctrl+Shift+N)",
            command=self._open_new_float_dialog, bootstyle="success-outline"
        )
        new_flt_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(new_flt_btn, text="Create a new money float or cash drawer profile (Ctrl+Shift+N)")

        edit_flt_btn = ttk.Button(
            float_ctrl, text="✏️ Edit Float",
            command=self._open_edit_float_dialog, bootstyle="secondary-outline"
        )
        edit_flt_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(edit_flt_btn, text="Edit selected cash float settings and custodian")

        hdr_close_btn = ttk.Button(
            float_ctrl, text="📋 Back to Vouchers (Ctrl+1)",
            command=self._on_close, bootstyle="info-outline"
        )
        hdr_close_btn.pack(side=tk.LEFT, padx=(6, 0))
        ToolTip(hdr_close_btn, text="Return to Voucher List (Ctrl+1 or Esc)")

        # ------------------------------------------------------------------
        # KPI Summary Cards Row
        # ------------------------------------------------------------------
        cards_frame = tk.Frame(self, bg="#f8fafc", padx=14, pady=8)
        cards_frame.pack(fill=tk.X)

        self._kpi_vars = {
            "current_balance": tk.StringVar(value="LKR 0.00"),
            "opening_balance": tk.StringVar(value="LKR 0.00"),
            "total_inflows": tk.StringVar(value="LKR 0.00"),
            "total_outflows": tk.StringVar(value="LKR 0.00"),
            "custodian": tk.StringVar(value="-"),
            "opening_date": tk.StringVar(value="-"),
            "unreimbursed_total": tk.StringVar(value="LKR 0.00"),
            "unreimbursed_count": tk.StringVar(value="0 Pending Vouchers"),
        }

        # Card 1: Current Balance (Large hero card)
        c1 = tk.Frame(cards_frame, bg="#ecfdf5", highlightbackground="#a7f3d0", highlightthickness=1, padx=12, pady=6)
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(c1, text="💵 Current Float Balance", font=("Segoe UI", 8, "bold"), bg="#ecfdf5", fg="#047857").pack(anchor="w")
        self._cur_bal_lbl = tk.Label(c1, textvariable=self._kpi_vars["current_balance"], font=("Segoe UI", 15, "bold"), bg="#ecfdf5", fg="#065f46")
        self._cur_bal_lbl.pack(anchor="w", pady=(1, 0))
        tk.Label(c1, text="Available Cash in Hand", font=("Segoe UI", 7, "italic"), bg="#ecfdf5", fg="#059669").pack(anchor="w")

        # Card 2: Opening Balance
        c2 = tk.Frame(cards_frame, bg="#eff6ff", highlightbackground="#bfdbfe", highlightthickness=1, padx=12, pady=6)
        c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(c2, text="🏁 Opening Balance", font=("Segoe UI", 8, "bold"), bg="#eff6ff", fg="#1d4ed8").pack(anchor="w")
        tk.Label(c2, textvariable=self._kpi_vars["opening_balance"], font=("Segoe UI", 13, "bold"), bg="#eff6ff", fg="#1e40af").pack(anchor="w", pady=(1, 0))
        self._op_date_lbl = tk.Label(c2, textvariable=self._kpi_vars["opening_date"], font=("Segoe UI", 7), bg="#eff6ff", fg="#60a5fa")
        self._op_date_lbl.pack(anchor="w")

        # Card 3: Inflows (Top-Ups)
        c3 = tk.Frame(cards_frame, bg="#f0fdf4", highlightbackground="#bbf7d0", highlightthickness=1, padx=12, pady=6)
        c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(c3, text="🟢 Total Inflows (Top-Ups)", font=("Segoe UI", 8, "bold"), bg="#f0fdf4", fg="#15803d").pack(anchor="w")
        tk.Label(c3, textvariable=self._kpi_vars["total_inflows"], font=("Segoe UI", 13, "bold"), bg="#f0fdf4", fg="#166534").pack(anchor="w", pady=(1, 0))
        tk.Label(c3, text="Cash Replenishments", font=("Segoe UI", 7), bg="#f0fdf4", fg="#22c55e").pack(anchor="w")

        # Card 4: Outflows (Vouchers)
        c4 = tk.Frame(cards_frame, bg="#fff1f2", highlightbackground="#fecdd3", highlightthickness=1, padx=12, pady=6)
        c4.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(c4, text="🔴 Total Outflows (Vouchers)", font=("Segoe UI", 8, "bold"), bg="#fff1f2", fg="#be123c").pack(anchor="w")
        tk.Label(c4, textvariable=self._kpi_vars["total_outflows"], font=("Segoe UI", 13, "bold"), bg="#fff1f2", fg="#9f1239").pack(anchor="w", pady=(1, 0))
        tk.Label(c4, text="Spent via Cash Vouchers", font=("Segoe UI", 7), bg="#fff1f2", fg="#f43f5e").pack(anchor="w")

        # Card 5: Pending Reimbursement (Unreimbursed Spent)
        c5 = tk.Frame(cards_frame, bg="#fffbeb", highlightbackground="#fde68a", highlightthickness=1, padx=12, pady=6)
        c5.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
        tk.Label(c5, text="⏳ Unreimbursed Spent", font=("Segoe UI", 8, "bold"), bg="#fffbeb", fg="#b45309").pack(anchor="w")
        self._unreimb_lbl = tk.Label(c5, textvariable=self._kpi_vars["unreimbursed_total"], font=("Segoe UI", 13, "bold"), bg="#fffbeb", fg="#92400e")
        self._unreimb_lbl.pack(anchor="w", pady=(1, 0))
        self._unreimb_sub_lbl = tk.Label(c5, textvariable=self._kpi_vars["unreimbursed_count"], font=("Segoe UI", 7), bg="#fffbeb", fg="#d97706")
        self._unreimb_sub_lbl.pack(anchor="w")

        # ------------------------------------------------------------------
        # Action Bar & Period Filters
        # ------------------------------------------------------------------
        action_bar = tk.Frame(self, bg="#ffffff", padx=14, pady=6, highlightbackground="#e2e8f0", highlightthickness=1)
        action_bar.pack(fill=tk.X)

        # Left action buttons
        left_actions = tk.Frame(action_bar, bg="#ffffff")
        left_actions.pack(side=tk.LEFT)

        reimb_btn = ttk.Button(
            left_actions, text="🔄 Reimburse Float (Alt+R)",
            command=self._open_fund_reimbursement_dialog,
            bootstyle="primary"
        )
        reimb_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(reimb_btn, text="Replenish float by settling spent petty cash vouchers (Alt+R)")

        add_btn = ttk.Button(
            left_actions, text="➕ Add Cash / Top-Up (Alt+A)",
            command=lambda: self._open_add_transaction_dialog("Inflow"),
            bootstyle="success"
        )
        add_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(add_btn, text="Record cash replenishment or top-up inflow into this float (Alt+A)")

        outflow_btn = ttk.Button(
            left_actions, text="➖ Cash Outflow / Adj. (Alt+O)",
            command=lambda: self._open_add_transaction_dialog("Outflow"),
            bootstyle="secondary-outline"
        )
        outflow_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(outflow_btn, text="Record cash withdrawal, petty cash payout, or manual outflow (Alt+O)")

        export_btn = ttk.Button(
            left_actions, text="📊 Export Ledger CSV (Ctrl+Shift+E)",
            command=self._export_ledger_csv,
            bootstyle="info-outline"
        )
        export_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(export_btn, text="Export transaction ledger and running balance to CSV spreadsheet (Ctrl+Shift+E)")

        ref_btn = ttk.Button(
            left_actions, text="🔄 Refresh (F5)",
            command=self._refresh_ledger,
            bootstyle="secondary-outline"
        )
        ref_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(ref_btn, text="Reload latest float transactions and balances (F5)")

        # Right filters
        right_filter = tk.Frame(action_bar, bg="#ffffff")
        right_filter.pack(side=tk.RIGHT)

        tk.Label(
            right_filter, text="Period:",
            font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#475569"
        ).pack(side=tk.LEFT, padx=(0, 4))

        self._period_filter_var = tk.StringVar(value="All Time")
        period_combo = ttk.Combobox(
            right_filter, textvariable=self._period_filter_var,
            values=["All Time", "Today", "Yesterday", "This Week", "This Month", "Last Month", "This Year"],
            width=13, state="readonly"
        )
        period_combo.pack(side=tk.LEFT, padx=(0, 8))
        period_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_ledger())

        # Custodian Info Badge
        self._custodian_badge_var = tk.StringVar(value="Custodian: -")
        tk.Label(
            right_filter, textvariable=self._custodian_badge_var,
            font=("Segoe UI", 8, "bold"), bg="#f1f5f9", fg="#334155",
            padx=8, pady=3, highlightbackground="#cbd5e1", highlightthickness=1
        ).pack(side=tk.LEFT)

        close_btn = ttk.Button(
            right_filter, text="✕ Back to List (Esc)",
            command=self._on_close,
            bootstyle="secondary"
        )
        close_btn.pack(side=tk.LEFT, padx=(8, 0))
        ToolTip(close_btn, text="Return to Voucher List (Ctrl+1 or Esc)")

        # ------------------------------------------------------------------
        # Running Balance Audit Ledger Table
        # ------------------------------------------------------------------
        table_frame = tk.Frame(self, padx=14, pady=6)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = (
            "date", "type", "ref", "description",
            "handed_by", "spent_by", "inflow", "outflow", "running_balance"
        )
        self._tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="browse"
        )

        col_defs = [
            ("date", "Date", 85, "center", False),
            ("type", "Transaction Type", 135, "w", False),
            ("ref", "Reference / Voucher #", 120, "center", False),
            ("description", "Description / Purpose", 240, "w", True),
            ("handed_by", "Handed By", 100, "w", False),
            ("spent_by", "Spent / Received By", 110, "w", False),
            ("inflow", "Inflow (LKR)", 100, "e", False),
            ("outflow", "Outflow (LKR)", 100, "e", False),
            ("running_balance", "Running Balance (LKR)", 135, "e", False),
        ]

        for col_id, col_text, col_width, col_align, col_stretch in col_defs:
            self._base_headings[col_id] = col_text
            self._tree.heading(
                col_id,
                text=col_text + (" ▼" if col_id == "date" else ""),
                anchor=col_align,
                command=lambda c=col_id: self._sort_by_column(c)
            )
            self._tree.column(col_id, width=col_width, anchor=col_align, minwidth=60, stretch=col_stretch)

        # Colorful tag styling
        self._tree.tag_configure("opening_tag", background="#f0f7ff", foreground="#1d4ed8", font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("inflow_tag", background="#f0fdf4", foreground="#15803d", font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("reimb_tag", background="#ecfeff", foreground="#0891b2", font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("cash_rec_tag", background="#f0fdfa", foreground="#0d9488", font=("Segoe UI", 9, "bold"))
        self._tree.tag_configure("outflow_pending_tag", background="#fff1f2", foreground="#be123c")
        self._tree.tag_configure("outflow_reimbursed_tag", background="#f8fafc", foreground="#64748b")
        self._tree.tag_configure("outflow_tag", background="#fff1f2", foreground="#be123c")
        self._tree.tag_configure("adj_outflow_tag", background="#fff7ed", foreground="#c2410c")

        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        tree_scroll_x.grid(row=1, column=0, sticky="ew")

        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        # Right-click context menu (dynamic based on entry type)
        self._tree_menu = tk.Menu(self, tearoff=0)

        def _on_context_menu(event):
            item = self._tree.identify_row(event.y)
            if not item:
                return
            self._tree.selection_set(item)
            item_data = self._tree_data_map.get(item, {})
            entry_type = item_data.get("entry_type")

            self._tree_menu.delete(0, tk.END)
            self._tree_menu.add_command(label="📋 Copy Reference", command=self._copy_selected_ref)
            self._tree_menu.add_separator()

            if entry_type == "voucher":
                self._tree_menu.add_command(label="📄 View Voucher (PDF)", command=self._view_linked_voucher)
            elif entry_type == "reimbursement":
                self._tree_menu.add_command(label="🔄 View Reimbursement Details", command=lambda: self._view_reimbursement_details(item_data.get("id")))
                self._tree_menu.add_command(label="🗑️ Delete Reimbursement", command=self._delete_selected_transaction)
            elif entry_type in ("top_up", "cash_received", "adjustment"):
                self._tree_menu.add_command(label="✏️ View / Edit Transaction", command=lambda: self._view_or_edit_transaction(item_data.get("id")))
                self._tree_menu.add_command(label="🗑️ Delete Transaction", command=self._delete_selected_transaction)
            elif entry_type == "opening":
                self._tree_menu.add_command(label="⚙️ Edit Float Settings", command=self._open_edit_float_dialog)

            self._tree_menu.post(event.x_root, event.y_root)

        self._tree.bind("<Button-3>", _on_context_menu)
        self._tree.bind("<Double-1>", self._on_tree_double_click)

        # ------------------------------------------------------------------
        # Bottom Status / Movement Summary Bar
        # ------------------------------------------------------------------
        status_bar = tk.Frame(self, bg="#f1f5f9", padx=14, pady=5, highlightbackground="#cbd5e1", highlightthickness=1)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_left_var = tk.StringVar(value="Ready")
        tk.Label(
            status_bar, textvariable=self._status_left_var,
            font=("Segoe UI", 8), bg="#f1f5f9", fg="#475569"
        ).pack(side=tk.LEFT)

        tk.Label(
            status_bar,
            text="⌨️  [Alt+R] Reimburse Float   [Alt+A] Add Cash   [Alt+O] Outflow   [Ctrl+Shift+N] New Float   [Ctrl+Shift+E] Export CSV   [F5] Refresh   [Esc] Close",
            font=("Segoe UI", 8), bg="#f1f5f9", fg="#64748b"
        ).pack(side=tk.LEFT, padx=16)

        self._status_right_var = tk.StringVar(value="")
        tk.Label(
            status_bar, textvariable=self._status_right_var,
            font=("Segoe UI", 8, "bold"), bg="#f1f5f9", fg="#1e293b"
        ).pack(side=tk.RIGHT)

        self._tree_data_map = {}

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

    def _sort_by_column(self, col):
        """Toggle sort order for clicked column header."""
        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            # Numbers and dates default to descending (newest/highest first), text defaults to ascending
            self._sort_desc = True if col in ("date", "inflow", "outflow", "running_balance") else False

        self._update_header_arrows()
        self._populate_treeview()

    def _update_header_arrows(self):
        """Update column headings with directional sort indicators (▲ / ▼)."""
        for c, base_title in self._base_headings.items():
            if c == self._sort_col:
                arrow = " ▼" if self._sort_desc else " ▲"
                self._tree.heading(c, text=base_title + arrow)
            else:
                self._tree.heading(c, text=base_title)

    def _populate_treeview(self):
        """Populate treeview rows according to active sort column and direction."""
        # Clear existing items
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)
        self._tree_data_map.clear()

        if not self._raw_entries:
            return

        def sort_key(e):
            if self._sort_col == "date":
                return (e.get("date", ""), e.get("sort_priority", 0), e.get("id", 0))
            elif self._sort_col in ("inflow", "outflow", "running_balance"):
                return float(e.get(self._sort_col, 0.0))
            elif self._sort_col == "type":
                return str(e.get("type_label", "")).lower()
            elif self._sort_col == "ref":
                return str(e.get("ref", "")).lower()
            elif self._sort_col == "description":
                return str(e.get("description", "")).lower()
            elif self._sort_col == "handed_by":
                return str(e.get("handed_by", "")).lower()
            elif self._sort_col == "spent_by":
                return str(e.get("spent_by") or e.get("received_by", "")).lower()
            return e.get("id", 0)

        # Default order: latest transactions at the top!
        sorted_entries = sorted(self._raw_entries, key=sort_key, reverse=self._sort_desc)

        for e in sorted_entries:
            in_str = f"{e['inflow']:,.2f}" if e['inflow'] > 0 else "-"
            out_str = f"{e['outflow']:,.2f}" if e['outflow'] > 0 else "-"
            bal_str = f"{e['running_balance']:,.2f}"

            tag = "opening_tag"
            if e["entry_type"] == "reimbursement":
                tag = "reimb_tag"
            elif e["entry_type"] == "cash_received":
                tag = "cash_rec_tag"
            elif e["entry_type"] == "top_up":
                tag = "inflow_tag"
            elif e["entry_type"] == "voucher":
                tag = "outflow_reimbursed_tag" if e.get("is_reimbursed") else "outflow_pending_tag"
            elif e["entry_type"] == "adjustment":
                tag = "adj_outflow_tag"

            item_id = self._tree.insert(
                "", tk.END,
                values=(
                    e["date"],
                    e["type_label"],
                    e["ref"],
                    e["description"],
                    e["handed_by"],
                    e.get("spent_by") or e.get("received_by", ""),
                    in_str,
                    out_str,
                    bal_str
                ),
                tags=(tag,)
            )
            self._tree_data_map[item_id] = e

    def _refresh_ledger(self):
        """Reload running balance ledger for the selected float."""
        if not self._selected_float_id:
            return

        date_filt = self._period_filter_var.get()
        entries, stats = db.get_float_ledger(self._selected_float_id, date_filter=date_filt)
        self._raw_entries = entries

        # Update KPI cards
        cur_bal = stats.get("current_balance", 0.0)
        op_bal = stats.get("opening_balance", 0.0)
        tot_in = stats.get("total_inflows", 0.0)
        tot_out = stats.get("total_outflows", 0.0)
        custodian = stats.get("custodian") or "None Assigned"
        op_date = stats.get("opening_date") or "-"
        unreimb_tot = stats.get("unreimbursed_total", 0.0)
        unreimb_cnt = stats.get("unreimbursed_count", 0)

        self._kpi_vars["current_balance"].set(f"LKR {cur_bal:,.2f}")
        self._kpi_vars["opening_balance"].set(f"LKR {op_bal:,.2f}")
        self._kpi_vars["total_inflows"].set(f"+LKR {tot_in:,.2f}")
        self._kpi_vars["total_outflows"].set(f"-LKR {tot_out:,.2f}")
        self._kpi_vars["opening_date"].set(f"As of {op_date}")
        self._kpi_vars["unreimbursed_total"].set(f"LKR {unreimb_tot:,.2f}")
        self._kpi_vars["unreimbursed_count"].set(f"{unreimb_cnt} Pending Voucher(s)")
        self._custodian_badge_var.set(f"Custodian: {custodian}")

        # Color-code hero current balance
        if cur_bal >= 0:
            self._cur_bal_lbl.config(fg="#065f46")
        else:
            self._cur_bal_lbl.config(fg="#dc2626")  # Alert overdrawn

        # Update header arrows and render rows sorted (default: latest transactions top)
        self._update_header_arrows()
        self._populate_treeview()

        # Update status bar
        filt_in = stats.get("filtered_inflows", 0.0)
        filt_out = stats.get("filtered_outflows", 0.0)
        net_movement = filt_in - filt_out
        net_sign = "+" if net_movement >= 0 else ""

        self._status_left_var.set(
            f"Showing {len(entries)} transaction(s) | Filter: {date_filt} | Click headers to sort (Default: Latest top)"
        )
        self._status_right_var.set(
            f"Period Inflows: +LKR {filt_in:,.2f}  |  Outflows: -LKR {filt_out:,.2f}  |  Net Movement: {net_sign}LKR {net_movement:,.2f}"
        )

        # Notify parent if callback provided
        if self._on_update_callback:
            try:
                self._on_update_callback()
            except Exception:
                pass

    def _open_new_float_dialog(self):
        """Open modal to create a new money float."""
        top = self.winfo_toplevel()
        dlg = FloatEditDialog(top, company_id=self._company_id, float_id=None)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=dlg.saved_float_id)

    def _open_edit_float_dialog(self):
        """Open modal to edit selected float."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = FloatEditDialog(top, company_id=self._company_id, float_id=self._selected_float_id)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=self._selected_float_id)

    def _open_fund_reimbursement_dialog(self):
        """Open fund reimbursement modal to replenish float by settling spent vouchers."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = FundReimbursementDialog(top, float_id=self._selected_float_id, company_id=self._company_id)
        self.wait_window(dlg)
        if dlg.saved:
            self._refresh_ledger()

    def _open_add_transaction_dialog(self, trans_type="Inflow"):
        """Open modal to add a top-up inflow or cash adjustment."""
        if not self._selected_float_id:
            return
        top = self.winfo_toplevel()
        dlg = AddTopUpDialog(top, float_id=self._selected_float_id, trans_type=trans_type)
        self.wait_window(dlg)
        if dlg.saved:
            self._refresh_ledger()

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
        elif entry_type == "opening":
            self._open_edit_float_dialog()

    def _view_linked_voucher(self):
        """Open voucher in PDF preview dialog."""
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        if entry.get("entry_type") == "voucher":
            v_id = entry.get("id")
            if v_id:
                top = self.winfo_toplevel()
                if hasattr(top, "_generate_and_preview_pdf"):
                    top._generate_and_preview_pdf(v_id)
                elif hasattr(self._parent, "_generate_and_preview_pdf"):
                    self._parent._generate_and_preview_pdf(v_id)
                else:
                    try:
                        pdf_path = printer.generate_voucher_pdf([v_id])
                        PdfViewerDialog(top, pdf_path, voucher_ids=[v_id])
                    except Exception as ex:
                        messagebox.showinfo(
                            "Voucher Details",
                            f"Voucher Number: {entry.get('ref')}\n"
                            f"Amount: LKR {entry.get('outflow', 0.0):,.2f}\n"
                            f"Description: {entry.get('description')}\n"
                            f"Date: {entry.get('date')}\n\n"
                            f"(PDF preview error: {ex})",
                            parent=top
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

        if self._float_id:
            db.update_float(self._float_id, {
                "name": name,
                "custodian": custodian,
                "opening_balance": ob,
                "opening_date": ob_date,
                "notes": notes,
                "is_default": 1 if is_def else 0,
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
                is_default=is_def
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

