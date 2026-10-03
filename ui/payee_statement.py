"""
Payee Statement & Vendor Ledger Dialog.
Allows users to view, analyze, export, and print transaction statements
for individual payees / vendors across any date range.
"""

import os
import tempfile
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox, filedialog
from datetime import datetime

import database as db
import printer
from ui.pdf_viewer import PdfViewerDialog


class PayeeStatementDialog(tk.Toplevel):
    """Modal dialog for viewing payee payment statements and vendor ledgers."""

    def __init__(self, parent, initial_payee=None):
        super().__init__(parent)
        self.title("📜 Payee Statement & Vendor Ledger")
        self.geometry("860x600")
        self.resizable(True, True)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._company_id = db.get_active_company_id()
        self._initial_payee = initial_payee

        self._build_ui()
        self._load_payee_list()

        if initial_payee:
            self._payee_var.set(initial_payee)

        self._refresh_statement()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.focus_force()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F5>", lambda e: self._refresh_statement())
        self.bind("<Control-e>", lambda e: self._export_csv())
        self.bind("<Control-E>", lambda e: self._export_csv())
        self.bind("<Control-p>", lambda e: self._view_pdf_statement())
        self.bind("<Control-P>", lambda e: self._view_pdf_statement())

    def _build_ui(self):
        # ── 1. Top Controls Bar (Payee Selector & Date Filter) ────────────────
        top_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=8)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 6))

        tk.Label(top_bar, text="👤 Payee / Party:", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0f172a").pack(side=tk.LEFT, padx=(0, 6))

        self._payee_var = tk.StringVar()
        self._payee_combo = ttk.Combobox(top_bar, textvariable=self._payee_var, width=28)
        self._payee_combo.pack(side=tk.LEFT, padx=(0, 14))
        self._payee_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_statement())
        self._payee_combo.bind("<Return>", lambda e: self._refresh_statement())

        tk.Label(top_bar, text="📅 Date Filter:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT, padx=(0, 6))

        self._date_filter_var = tk.StringVar(value="All Time")
        date_combo = ttk.Combobox(
            top_bar, textvariable=self._date_filter_var,
            values=["All Time", "Today", "Yesterday", "This Week", "This Month", "Last Month", "This Year"],
            width=12, state="readonly"
        )
        date_combo.pack(side=tk.LEFT, padx=(0, 10))
        date_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_statement())

        ttk.Button(
            top_bar, text="⟳ Refresh", command=self._refresh_statement, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT)

        # ── 2. Stat Cards Bar ────────────────────────────────────────────────
        stats_frame = ttk.Frame(self, padding=(10, 2))
        stats_frame.pack(fill=tk.X)

        self._stat_vars = {
            "total_spent": tk.StringVar(value="0.00"),
            "vouchers_count": tk.StringVar(value="0"),
            "pending_amount": tk.StringVar(value="0.00"),
            "avg_amount": tk.StringVar(value="0.00"),
        }

        cards = [
            ("Total Spent (LKR)", "total_spent", "#f0fdf4", "#bbf7d0", "#15803d"),
            ("Total Vouchers", "vouchers_count", "#eff6ff", "#bfdbfe", "#1d4ed8"),
            ("Pending Bills (LKR)", "pending_amount", "#fffbeb", "#fde68a", "#b45309"),
            ("Avg Voucher Value", "avg_amount", "#f5f3ff", "#ddd6fe", "#6d28d9"),
        ]

        for label, key, bg_col, border_col, val_col in cards:
            card = tk.Frame(
                stats_frame, bg=bg_col,
                highlightbackground=border_col, highlightthickness=1,
                padx=10, pady=6
            )
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

            tk.Label(card, text=label, font=("Segoe UI", 8), bg=bg_col, fg="#64748b").pack(anchor="w")
            tk.Label(card, textvariable=self._stat_vars[key], font=("Segoe UI", 12, "bold"), bg=bg_col, fg=val_col).pack(anchor="w")

        # ── 4. Action Buttons Footer (Docked at BOTTOM first so it is never pushed off) ──
        btn_bar = ttk.Frame(self, padding=(10, 8))
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)

        csv_btn = ttk.Button(
            btn_bar, text="📊 Export Statement (CSV)", command=self._export_csv, bootstyle="info-outline"
        )
        csv_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(csv_btn, text="Export statement ledger for this payee to CSV spreadsheet (Ctrl+E)")

        pdf_btn = ttk.Button(
            btn_bar, text="👁️ View / Print Statement (PDF)", command=self._view_pdf_statement, bootstyle="primary"
        )
        pdf_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(pdf_btn, text="Generate and preview printable PDF statement for payee (Ctrl+P)")

        ref_btn = ttk.Button(
            btn_bar, text="⟳ Refresh (F5)", command=self._refresh_statement, bootstyle="secondary-outline"
        )
        ref_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(ref_btn, text="Reload statement data from database (F5)")

        close_btn = ttk.Button(
            btn_bar, text="✕ Close (Esc)", command=self.destroy, bootstyle="secondary"
        )
        close_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(close_btn, text="Close dialog (Esc)")

        # ── 3. Transaction Register Treeview (Occupies all remaining vertical space) ──
        tree_frame = ttk.Frame(self, padding=(10, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("number", "date", "due_date", "items", "payment", "bill_status", "amount")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=14, selectmode="browse"
        )

        col_configs = [
            ("number", "Voucher #", 100, "center"),
            ("date", "Date", 85, "center"),
            ("due_date", "Due Date", 85, "center"),
            ("items", "Items / Category Summary", 270, "w"),
            ("payment", "Payment Method", 110, "center"),
            ("bill_status", "Bill Status", 90, "center"),
            ("amount", "Amount (LKR)", 110, "e"),
        ]

        for col, heading, width, anchor in col_configs:
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor=anchor)

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.tag_configure("bill_pending", background="#fffdf5", foreground="#92400e")
        self._tree.tag_configure("bill_received", background="#f0fdf4", foreground="#166534")

    def _load_payee_list(self):
        """Populate payee combobox with all people in the database."""
        people = db.get_people(active_only=False)
        self._payee_combo["values"] = people
        if people and not self._payee_var.get():
            self._payee_var.set(people[0])

    def _refresh_statement(self):
        """Fetch payee statement data and populate stat cards & treeview."""
        payee = self._payee_var.get().strip()
        date_filter = self._date_filter_var.get()

        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)

        if not payee:
            self._stat_vars["total_spent"].set("0.00")
            self._stat_vars["vouchers_count"].set("0")
            self._stat_vars["pending_amount"].set("0.00")
            self._stat_vars["avg_amount"].set("0.00")
            return

        stmt = db.get_payee_statement(
            payee_name=payee, company_id=self._company_id, date_filter=date_filter
        )

        self._stat_vars["total_spent"].set(f"{stmt['total_spent']:,.2f}")
        self._stat_vars["vouchers_count"].set(str(stmt["total_vouchers"]))
        self._stat_vars["pending_amount"].set(f"{stmt['pending_amount']:,.2f}")
        self._stat_vars["avg_amount"].set(f"{stmt['avg_voucher_amount']:,.2f}")

        for v in stmt["vouchers"]:
            items = v.get("line_items", [])
            if items:
                desc_parts = [f"{it['description']} ({it['category'] or 'Misc'})" for it in items[:2]]
                if len(items) > 2:
                    desc_parts.append(f"+{len(items)-2} more")
                desc_str = "; ".join(desc_parts)
            else:
                desc_str = "Voucher Payment"

            bill_st = v.get("bill_status", "Pending")
            tag = "bill_received" if bill_st == "Received" else "bill_pending"

            pm = v.get("payment_method", "Cash")
            pm_ref = v.get("payment_ref", "")
            pm_str = f"{pm} ({pm_ref})" if pm_ref else pm

            self._tree.insert("", tk.END, iid=str(v["id"]), tags=(tag,), values=(
                v.get("voucher_number", ""),
                v.get("date", ""),
                v.get("due_date", "") or "—",
                desc_str,
                pm_str,
                bill_st,
                f"{v.get('total_amount', 0):,.2f}",
            ))

    def _export_csv(self):
        """Export payee statement to CSV."""
        payee = self._payee_var.get().strip()
        if not payee:
            messagebox.showwarning("Select Payee", "Please select a payee first.", parent=self)
            return

        safe_name = "".join(c for c in payee if c.isalnum() or c in "_- ").strip().replace(" ", "_")
        default_fn = f"Payee_Statement_{safe_name}_{datetime.now().strftime('%Y%m%d')}.csv"

        filepath = filedialog.asksavefilename(
            parent=self,
            title="Export Payee Statement CSV",
            initialfile=default_fn,
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            db.export_payee_statement_to_csv(
                payee_name=payee,
                filepath=filepath,
                company_id=self._company_id,
                date_filter=self._date_filter_var.get()
            )
            messagebox.showinfo("Export Successful", f"Payee Statement exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting CSV statement:\n{str(e)}", parent=self)

    def _view_pdf_statement(self):
        """Generate PDF statement and open preview dialog."""
        payee = self._payee_var.get().strip()
        if not payee:
            messagebox.showwarning("Select Payee", "Please select a payee first.", parent=self)
            return

        self.config(cursor="watch")

        def _worker():
            try:
                pdf_path = printer.generate_payee_statement_pdf(
                    payee_name=payee,
                    company_id=self._company_id,
                    date_filter=self._date_filter_var.get()
                )
                def _ui_success():
                    self.config(cursor="")
                    if self.winfo_exists():
                        PdfViewerDialog(self, pdf_path)
                if self.winfo_exists():
                    self.after(0, _ui_success)
            except Exception as e:
                def _ui_error():
                    self.config(cursor="")
                    if self.winfo_exists():
                        messagebox.showerror("PDF Error", f"Could not generate PDF statement:\n{str(e)}", parent=self)
                if self.winfo_exists():
                    self.after(0, _ui_error)

        import threading
        threading.Thread(target=_worker, daemon=True).start()
