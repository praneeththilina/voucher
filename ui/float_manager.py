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


class MoneyFloatDialog(tk.Toplevel):
    """
    Comprehensive Money Float & Cash Drawer Tracking Dialog.
    Provides real-time running balance audit ledger, multi-float switching,
    top-up recording, and CSV ledger exports for accountants.
    """

    def __init__(self, parent, company_id=None, on_update_callback=None):
        super().__init__(parent)
        self.title("💰 Company Money Float & Cash Drawer Tracking")

        self._parent = parent
        self._on_update_callback = on_update_callback
        self._company_id = company_id if company_id is not None else db.get_active_company_id()
        self._selected_float_id = None
        self._floats_cache = []
        self._raw_entries = []
        self._sort_col = "date"
        self._sort_desc = True  # Default: latest transactions top!
        self._base_headings = {}

        # Determine optimal size covering the screen
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = max(1160, min(1440, screen_w - 40))
        target_h = max(680, min(900, screen_h - 60))
        self.geometry(f"{target_w}x{target_h}")
        self.minsize(980, 540)
        self.grab_set()

        self._build_ui()
        self._load_floats()

        # Center on parent / screen
        self.update_idletasks()
        px = max(10, parent.winfo_rootx() + max(0, (parent.winfo_width() - target_w) // 2))
        py = max(10, parent.winfo_rooty() + max(0, (parent.winfo_height() - target_h) // 2))
        self.geometry(f"{target_w}x{target_h}+{px}+{py}")

        # Maximize to fully cover the screen area so running balance is immediately in view
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

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

        ttk.Button(
            float_ctrl, text="➕ New Float",
            command=self._open_new_float_dialog, bootstyle="success-outline"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            float_ctrl, text="✏️ Edit Float",
            command=self._open_edit_float_dialog, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=3)

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

        # ------------------------------------------------------------------
        # Action Bar & Period Filters
        # ------------------------------------------------------------------
        action_bar = tk.Frame(self, bg="#ffffff", padx=14, pady=6, highlightbackground="#e2e8f0", highlightthickness=1)
        action_bar.pack(fill=tk.X)

        # Left action buttons
        left_actions = tk.Frame(action_bar, bg="#ffffff")
        left_actions.pack(side=tk.LEFT)

        ttk.Button(
            left_actions, text="➕ Add Cash / Top-Up...",
            command=lambda: self._open_add_transaction_dialog("Inflow"),
            bootstyle="success"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            left_actions, text="➖ Cash Outflow / Adjustment...",
            command=lambda: self._open_add_transaction_dialog("Outflow"),
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            left_actions, text="📊 Export Ledger CSV...",
            command=self._export_ledger_csv,
            bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            left_actions, text="🔄 Refresh",
            command=self._refresh_ledger,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))

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

        # Right-click context menu
        self._tree_menu = tk.Menu(self, tearoff=0)
        self._tree_menu.add_command(label="📋 Copy Reference", command=self._copy_selected_ref)
        self._tree_menu.add_command(label="📄 View Linked Voucher", command=self._view_linked_voucher)
        self._tree_menu.add_separator()
        self._tree_menu.add_command(label="🗑️ Delete Transaction", command=self._delete_selected_transaction)

        def _on_context_menu(event):
            item = self._tree.identify_row(event.y)
            if item:
                self._tree.selection_set(item)
                # Enable/disable items based on entry type
                vals = self._tree.item(item, "values")
                item_data = self._tree_data_map.get(item, {})
                entry_type = item_data.get("entry_type")
                if entry_type == "voucher":
                    self._tree_menu.entryconfigure("📄 View Linked Voucher", state="normal")
                    self._tree_menu.entryconfigure("🗑️ Delete Transaction", state="disabled")
                elif entry_type in ("top_up", "adjustment"):
                    self._tree_menu.entryconfigure("📄 View Linked Voucher", state="disabled")
                    self._tree_menu.entryconfigure("🗑️ Delete Transaction", state="normal")
                else:
                    self._tree_menu.entryconfigure("📄 View Linked Voucher", state="disabled")
                    self._tree_menu.entryconfigure("🗑️ Delete Transaction", state="disabled")
                self._tree_menu.post(event.x_root, event.y_root)

        self._tree.bind("<Button-3>", _on_context_menu)
        self._tree.bind("<Double-1>", lambda e: self._view_linked_voucher())

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
        for item in self._tree.get_children():
            self._tree.delete(item)
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
            if e["entry_type"] == "top_up":
                tag = "inflow_tag"
            elif e["entry_type"] == "voucher":
                tag = "outflow_tag"
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

        self._kpi_vars["current_balance"].set(f"LKR {cur_bal:,.2f}")
        self._kpi_vars["opening_balance"].set(f"LKR {op_bal:,.2f}")
        self._kpi_vars["total_inflows"].set(f"+LKR {tot_in:,.2f}")
        self._kpi_vars["total_outflows"].set(f"-LKR {tot_out:,.2f}")
        self._kpi_vars["opening_date"].set(f"As of {op_date}")
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
        dlg = FloatEditDialog(self, company_id=self._company_id, float_id=None)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=dlg.saved_float_id)

    def _open_edit_float_dialog(self):
        """Open modal to edit selected float."""
        if not self._selected_float_id:
            return
        dlg = FloatEditDialog(self, company_id=self._company_id, float_id=self._selected_float_id)
        self.wait_window(dlg)
        if dlg.saved_float_id:
            self._load_floats(select_float_id=self._selected_float_id)

    def _open_add_transaction_dialog(self, trans_type="Inflow"):
        """Open modal to add a top-up inflow or cash adjustment."""
        if not self._selected_float_id:
            return
        dlg = AddTopUpDialog(self, float_id=self._selected_float_id, trans_type=trans_type)
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

        filepath = filedialog.asksaveasfilename(
            parent=self,
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
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}", parent=self)

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

    def _view_linked_voucher(self):
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        if entry.get("entry_type") == "voucher":
            v_id = entry.get("id")
            if v_id:
                # Open PDF preview using parent's method if available
                if hasattr(self._parent, "_generate_and_preview_pdf"):
                    self._parent._generate_and_preview_pdf(v_id)
                elif hasattr(self._parent, "_preview_voucher_pdf"):
                    self._parent._preview_voucher_pdf(v_id)
                else:
                    messagebox.showinfo(
                        "Voucher Details",
                        f"Voucher Number: {entry.get('ref')}\n"
                        f"Amount: LKR {entry.get('outflow', 0.0):,.2f}\n"
                        f"Description: {entry.get('description')}\n"
                        f"Date: {entry.get('date')}",
                        parent=self
                    )

    def _delete_selected_transaction(self):
        selected = self._tree.selection()
        if not selected:
            return
        item_id = selected[0]
        entry = self._tree_data_map.get(item_id, {})
        if entry.get("entry_type") in ("top_up", "adjustment"):
            trans_id = entry.get("id")
            confirm = messagebox.askyesno(
                "Delete Transaction",
                f"Are you sure you want to delete this {entry.get('type_label')}?\n\n"
                f"Date: {entry.get('date')}\n"
                f"Amount: LKR {entry.get('inflow') or entry.get('outflow'):,.2f}\n"
                f"Ref: {entry.get('ref')}",
                parent=self,
                icon="warning"
            )
            if confirm:
                db.delete_float_transaction(trans_id)
                self._refresh_ledger()


class AddTopUpDialog(tk.Toplevel):
    """Dialog to record a cash top-up / replenishment inflow or manual adjustment outflow."""

    def __init__(self, parent, float_id, trans_type="Inflow"):
        super().__init__(parent)
        self.saved = False
        self._float_id = float_id
        self._trans_type = trans_type

        title_text = "➕ Add Float Top-Up / Cash Inflow" if trans_type == "Inflow" else "➖ Add Manual Cash Outflow"
        self.title(title_text)
        self.geometry("520x460")
        self.minsize(460, 420)
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

        # Form content
        form = tk.Frame(self, padx=18, pady=14)
        form.pack(fill=tk.BOTH, expand=True)

        row = 0
        # Transaction Type
        tk.Label(form, text="Transaction Type:", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._type_var = tk.StringVar(value=self._trans_type)
        type_combo = ttk.Combobox(form, textvariable=self._type_var, values=["Inflow", "Outflow"], width=20, state="readonly")
        type_combo.grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Date
        tk.Label(form, text="Date (YYYY-MM-DD):", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(form, textvariable=self._date_var, width=22).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Amount
        tk.Label(form, text="Amount (LKR): *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._amt_var = tk.StringVar()
        amt_entry = ttk.Entry(form, textvariable=self._amt_var, width=22, font=("Segoe UI", 10, "bold"))
        amt_entry.grid(row=row, column=1, sticky="w", pady=6)
        amt_entry.focus_set()

        row += 1
        # Source / Reference
        ref_label = "Source / Cheque # / Ref:" if self._trans_type == "Inflow" else "Reference / Purpose:"
        tk.Label(form, text=ref_label, font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._ref_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._ref_var, width=32).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Handed By
        tk.Label(form, text="Handed / Issued By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._handed_var = tk.StringVar()
        people = db.get_people(active_only=True)
        handed_combo = ttk.Combobox(form, textvariable=self._handed_var, values=people, width=30)
        handed_combo.grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Received By
        tk.Label(form, text="Received By:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._received_var = tk.StringVar(value=flt.get("custodian", ""))
        received_combo = ttk.Combobox(form, textvariable=self._received_var, values=people, width=30)
        received_combo.grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Notes / Remarks
        tk.Label(form, text="Notes / Remarks:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=6)
        self._notes_text = tk.Text(form, width=32, height=3, font=("Segoe UI", 9))
        self._notes_text.grid(row=row, column=1, sticky="w", pady=6)

        # Bottom Buttons
        btn_bar = tk.Frame(self, padx=16, pady=10, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        save_style = "success" if self._trans_type == "Inflow" else "warning"
        ttk.Button(btn_bar, text="💾 Save Transaction", command=self._save, bootstyle=save_style).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)

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

        db.add_float_transaction(
            float_id=self._float_id,
            amount=amt,
            date=date_val,
            trans_type=self._type_var.get(),
            source_ref=self._ref_var.get().strip(),
            handed_by=self._handed_var.get().strip(),
            received_by=self._received_var.get().strip(),
            notes=self._notes_text.get("1.0", tk.END).strip()
        )

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
        self.geometry("500x480")
        self.minsize(440, 420)
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

        form = tk.Frame(self, padx=18, pady=14)
        form.pack(fill=tk.BOTH, expand=True)

        row = 0
        # Float Name
        tk.Label(form, text="Float Name: *", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        self._name_var = tk.StringVar(value=existing.get("name", ""))
        name_entry = ttk.Entry(form, textvariable=self._name_var, width=28)
        name_entry.grid(row=row, column=1, sticky="w", pady=6)
        name_entry.focus_set()

        row += 1
        # Custodian
        tk.Label(form, text="Custodian / Responsible:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        self._custodian_var = tk.StringVar(value=existing.get("custodian", ""))
        people = db.get_people(active_only=True)
        ttk.Combobox(form, textvariable=self._custodian_var, values=people, width=26).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Opening Balance
        tk.Label(form, text="Opening Balance (LKR):", font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=6)
        op_val = f"{existing.get('opening_balance', 0.0):.2f}" if self._float_id else "0.00"
        self._ob_var = tk.StringVar(value=op_val)
        ttk.Entry(form, textvariable=self._ob_var, width=22).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Opening Date
        tk.Label(form, text="Opening Date (YYYY-MM-DD):", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=6)
        def_date = existing.get("opening_date") or datetime.now().strftime("%Y-%m-%d")
        self._ob_date_var = tk.StringVar(value=def_date)
        ttk.Entry(form, textvariable=self._ob_date_var, width=22).grid(row=row, column=1, sticky="w", pady=6)

        row += 1
        # Is Default Checkbox
        self._is_default_var = tk.BooleanVar(value=bool(existing.get("is_default", False)))
        ttk.Checkbutton(
            form, text="Set as Default Float for Cash Vouchers",
            variable=self._is_default_var, bootstyle="round-toggle"
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=8)

        row += 1
        # Notes
        tk.Label(form, text="Notes / Description:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="nw", pady=6)
        self._notes_text = tk.Text(form, width=28, height=3, font=("Segoe UI", 9))
        if existing.get("notes"):
            self._notes_text.insert("1.0", existing["notes"])
        self._notes_text.grid(row=row, column=1, sticky="w", pady=6)

        # Bottom Buttons
        btn_bar = tk.Frame(self, padx=16, pady=10, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_bar, text="💾 Save Float", command=self._save, bootstyle="success").pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4)

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

        self.destroy()
