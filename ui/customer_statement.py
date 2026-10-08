"""
ui/customer_statement.py
Customer Statement & Accounts Receivable (AR) Ledger Dialog.
Allows users to view, analyze, export, and print transaction statements
for individual customers across any date range.
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


class CustomerStatementDialog(tk.Toplevel):
    """Modal dialog for viewing customer statements of account and AR ledgers."""

    def __init__(self, parent, initial_customer=None, company_id=None):
        super().__init__(parent)
        self.title("📜 Customer Statement & AR Account Ledger")
        self.geometry("920x620")
        self.resizable(True, True)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._company_id = company_id or db.get_active_company_id()
        self._initial_customer = initial_customer

        self._build_ui()
        self._load_customer_list()

        if initial_customer:
            if isinstance(initial_customer, int):
                c_obj = db.get_customer_by_id(initial_customer)
                if c_obj:
                    self._customer_var.set(c_obj["name"])
            else:
                self._customer_var.set(str(initial_customer))

        self._refresh_statement()

        # Center on parent
        self.update_idletasks()
        try:
            px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{px}+{py}")
        except Exception:
            pass

        self.lift()
        self.focus_force()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<F5>", lambda e: self._refresh_statement())
        self.bind("<Control-e>", lambda e: self._export_csv())
        self.bind("<Control-E>", lambda e: self._export_csv())
        self.bind("<Control-p>", lambda e: self._view_pdf_statement())
        self.bind("<Control-P>", lambda e: self._view_pdf_statement())

    def _build_ui(self):
        # ── 1. Top Controls Bar (Customer Selector & Date Filter) ────────────────
        top_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=12, pady=8)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 6))

        tk.Label(top_bar, text="👤 Customer:", font=("Segoe UI", 10, "bold"), bg="#f8fafc", fg="#0f172a").pack(side=tk.LEFT, padx=(0, 6))

        self._customer_var = tk.StringVar()
        self._customer_combo = ttk.Combobox(top_bar, textvariable=self._customer_var, width=28)
        self._customer_combo.pack(side=tk.LEFT, padx=(0, 14))
        self._customer_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_statement())
        self._customer_combo.bind("<Return>", lambda e: self._refresh_statement())

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
            "total_invoiced": tk.StringVar(value="0.00"),
            "total_received": tk.StringVar(value="0.00"),
            "outstanding_balance": tk.StringVar(value="0.00"),
            "avg_invoice_amount": tk.StringVar(value="0.00"),
        }

        cards = [
            ("Total Invoiced (LKR)", "total_invoiced", "#eff6ff", "#bfdbfe", "#1d4ed8"),
            ("Total Received (LKR)", "total_received", "#f0fdf4", "#bbf7d0", "#15803d"),
            ("Outstanding Balance (AR)", "outstanding_balance", "#fffbeb", "#fde68a", "#b45309"),
            ("Avg Invoice Value", "avg_invoice_amount", "#f5f3ff", "#ddd6fe", "#6d28d9"),
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
        ToolTip(csv_btn, text="Export statement ledger for this customer to CSV spreadsheet (Ctrl+E)")

        pdf_btn = ttk.Button(
            btn_bar, text="👁️ View / Print Statement (PDF)", command=self._view_pdf_statement, bootstyle="primary"
        )
        pdf_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(pdf_btn, text="Generate and preview printable PDF statement of account (Ctrl+P)")

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

        # ── 3. Transaction Register Treeview ───────────────
        tree_frame = ttk.Frame(self, padding=(10, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("date", "doc_type", "ref", "details", "status", "invoiced", "received", "balance")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=14, selectmode="browse"
        )

        col_configs = [
            ("date", "Date", 85, "center"),
            ("doc_type", "Type", 75, "center"),
            ("ref", "Reference #", 100, "center"),
            ("details", "Particulars / Details", 240, "w"),
            ("status", "Status", 90, "center"),
            ("invoiced", "Invoiced (+)", 105, "e"),
            ("received", "Received (-)", 105, "e"),
            ("balance", "Running Bal (LKR)", 115, "e"),
        ]

        for col, heading, width, anchor in col_configs:
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor=anchor)

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.tag_configure("doc_invoice", background="#eff6ff", foreground="#1e3a8a")
        self._tree.tag_configure("doc_receipt", background="#f0fdf4", foreground="#14532d")

    def _load_customer_list(self):
        """Populate customer combobox with all active customers in the company."""
        custs = db.get_customers(company_id=self._company_id, active_only=False)
        names = [c["name"] for c in custs]
        self._customer_combo["values"] = names
        if names and not self._customer_var.get():
            self._customer_var.set(names[0])

    def _refresh_statement(self):
        """Fetch customer statement data and populate stat cards & treeview."""
        cust_name = self._customer_var.get().strip()
        date_filter = self._date_filter_var.get()

        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)

        if not cust_name:
            self._stat_vars["total_invoiced"].set("0.00")
            self._stat_vars["total_received"].set("0.00")
            self._stat_vars["outstanding_balance"].set("0.00")
            self._stat_vars["avg_invoice_amount"].set("0.00")
            return

        stmt = db.get_customer_statement(
            customer_id_or_name=cust_name, company_id=self._company_id, date_filter=date_filter
        )

        self._stat_vars["total_invoiced"].set(f"{stmt['total_invoiced']:,.2f}")
        self._stat_vars["total_received"].set(f"{stmt['total_received']:,.2f}")
        self._stat_vars["outstanding_balance"].set(f"{stmt['outstanding_balance']:,.2f}")
        self._stat_vars["avg_invoice_amount"].set(f"{stmt['avg_invoice_amount']:,.2f}")

        for idx, tx in enumerate(stmt["transactions"]):
            doc_type = tx.get("doc_type", "Invoice")
            tag = "doc_receipt" if doc_type == "Receipt" else "doc_invoice"

            inv_str = f"{tx['invoiced_amount']:,.2f}" if tx['invoiced_amount'] > 0 else "—"
            rec_str = f"{tx['received_amount']:,.2f}" if tx['received_amount'] > 0 else "—"
            bal_str = f"{tx['running_balance']:,.2f}"

            self._tree.insert("", tk.END, iid=f"{doc_type}_{tx['id']}_{idx}", tags=(tag,), values=(
                tx.get("date", ""),
                doc_type,
                tx.get("reference", ""),
                tx.get("details", ""),
                tx.get("status", ""),
                inv_str,
                rec_str,
                bal_str,
            ))

    def _export_csv(self):
        """Export customer statement to CSV."""
        cust_name = self._customer_var.get().strip()
        if not cust_name:
            messagebox.showwarning("Select Customer", "Please select a customer first.", parent=self)
            return

        safe_name = "".join(c for c in cust_name if c.isalnum() or c in "_- ").strip().replace(" ", "_")
        default_fn = f"Customer_Statement_{safe_name}_{datetime.now().strftime('%Y%m%d')}.csv"

        filepath = filedialog.asksavefilename(
            parent=self,
            title="Export Customer Statement CSV",
            initialfile=default_fn,
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            db.export_customer_statement_to_csv(
                customer_id_or_name=cust_name,
                filepath=filepath,
                company_id=self._company_id,
                date_filter=self._date_filter_var.get()
            )
            messagebox.showinfo("Export Successful", f"Customer Statement exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting CSV statement:\n{str(e)}", parent=self)

    def _view_pdf_statement(self):
        """Generate PDF statement and open preview dialog."""
        cust_name = self._customer_var.get().strip()
        if not cust_name:
            messagebox.showwarning("Select Customer", "Please select a customer first.", parent=self)
            return

        self.config(cursor="watch")

        def _worker():
            try:
                pdf_path = printer.generate_customer_statement_pdf(
                    customer_id_or_name=cust_name,
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
