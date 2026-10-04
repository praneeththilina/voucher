"""
Bank Reconciliation Module.
Allows importing bank statements (CSV) and matching them to vouchers.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox

import database as db
import os


class BankReconciliationDialog(tk.Toplevel):
    """Modal dialog for bank reconciliation."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self.title("Bank Reconciliation")
        self.geometry("1100x650")
        self.minsize(900, 500)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._company_id = db.get_active_company_id()
        self._current_account_id = None
        self._build_ui()
        self._load_accounts()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # ── Top Bar ──
        top_bar = tk.Frame(self, bg="#f8fafc", padx=8, pady=8, highlightbackground="#e2e8f0", highlightthickness=1)
        top_bar.pack(fill=tk.X)

        tk.Label(top_bar, text="Bank Account:", font=("Segoe UI", 9), bg="#f8fafc").pack(side=tk.LEFT, padx=(8, 4))
        
        self._account_var = tk.StringVar()
        self._account_combo = ttk.Combobox(top_bar, textvariable=self._account_var, state="readonly", width=25)
        self._account_combo.pack(side=tk.LEFT)
        self._account_combo.bind("<<ComboboxSelected>>", self._on_account_changed)

        ttk.Button(top_bar, text="Manage Accounts", command=self._manage_accounts,
                   bootstyle="info-link").pack(side=tk.LEFT, padx=8)

        ttk.Button(top_bar, text="Import Statement (CSV)", command=self._import_statement,
                   bootstyle="success").pack(side=tk.RIGHT, padx=8)
        
        ttk.Button(top_bar, text="Auto-Match", command=self._auto_match,
                   bootstyle="primary").pack(side=tk.RIGHT, padx=4)

        # ── Summary KPIs ──
        self._summary_frame = tk.Frame(self, bg="#ffffff", padx=16, pady=8)
        self._summary_frame.pack(fill=tk.X)
        self._summary_labels = {}

        kpis = [
            ("total", "Bank Transactions", "#64748b"),
            ("unmatched", "Unmatched", "#ef4444"),
            ("matched", "Auto-Matched", "#f59e0b"),
            ("reconciled", "Reconciled", "#22c55e"),
        ]
        
        for key, title, color in kpis:
            f = tk.Frame(self._summary_frame, bg="#ffffff")
            f.pack(side=tk.LEFT, padx=(0, 24))
            tk.Label(f, text=title, font=("Segoe UI", 8), bg="#ffffff", fg="#94a3b8").pack(anchor="w")
            val_lbl = tk.Label(f, text="0", font=("Segoe UI", 16, "bold"), bg="#ffffff", fg=color)
            val_lbl.pack(anchor="w")
            self._summary_labels[key] = val_lbl

        # ── Main Splitter ──
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Panel: Bank Transactions
        left_frame = ttk.LabelFrame(paned, text="Bank Statement (Payments Out)", padding=4)
        paned.add(left_frame, weight=1)

        filter_frame1 = ttk.Frame(left_frame)
        filter_frame1.pack(fill=tk.X, pady=(0, 4))
        
        self._txn_filter_var = tk.StringVar(value="All")
        txn_filter = ttk.Combobox(filter_frame1, textvariable=self._txn_filter_var, 
                                  values=["All", "Unmatched", "Matched", "Reconciled"],
                                  state="readonly", width=12)
        txn_filter.pack(side=tk.RIGHT)
        txn_filter.bind("<<ComboboxSelected>>", lambda e: self._refresh_data())
        ttk.Label(filter_frame1, text="Filter:").pack(side=tk.RIGHT, padx=4)

        cols_l = ("date", "desc", "ref", "amount", "status")
        self._tree_l = ttk.Treeview(left_frame, columns=cols_l, show="headings", selectmode="browse")
        self._tree_l.heading("date", text="Date")
        self._tree_l.heading("desc", text="Description")
        self._tree_l.heading("ref", text="Reference")
        self._tree_l.heading("amount", text="Debit (Out)")
        self._tree_l.heading("status", text="Status")
        
        self._tree_l.column("date", width=80)
        self._tree_l.column("desc", width=150)
        self._tree_l.column("ref", width=80)
        self._tree_l.column("amount", width=90, anchor="e")
        self._tree_l.column("status", width=90, anchor="center")

        sb_l = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._tree_l.yview)
        self._tree_l.configure(yscrollcommand=sb_l.set)
        self._tree_l.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_l.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree_l.bind("<<TreeviewSelect>>", self._on_txn_select)

        # Right Panel: Vouchers
        right_frame = ttk.LabelFrame(paned, text="Active Vouchers (Unreconciled)", padding=4)
        paned.add(right_frame, weight=1)

        filter_frame2 = ttk.Frame(right_frame)
        filter_frame2.pack(fill=tk.X, pady=(0, 4))
        
        self._v_search_var = tk.StringVar()
        v_search = ttk.Entry(filter_frame2, textvariable=self._v_search_var, width=20)
        v_search.pack(side=tk.RIGHT)
        v_search.bind("<Return>", lambda e: self._refresh_vouchers())
        ttk.Label(filter_frame2, text="Search:").pack(side=tk.RIGHT, padx=4)

        cols_r = ("vno", "date", "payee", "amount", "ref")
        self._tree_r = ttk.Treeview(right_frame, columns=cols_r, show="headings", selectmode="browse")
        self._tree_r.heading("vno", text="Voucher No")
        self._tree_r.heading("date", text="Date")
        self._tree_r.heading("payee", text="Payee")
        self._tree_r.heading("amount", text="Amount")
        self._tree_r.heading("ref", text="Ref / Method")
        
        self._tree_r.column("vno", width=100)
        self._tree_r.column("date", width=80)
        self._tree_r.column("payee", width=120)
        self._tree_r.column("amount", width=90, anchor="e")
        self._tree_r.column("ref", width=90)

        sb_r = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self._tree_r.yview)
        self._tree_r.configure(yscrollcommand=sb_r.set)
        self._tree_r.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_r.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Action Buttons (Bottom) ──
        btn_frame = ttk.Frame(self, padding=(10, 8))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Confirm Selected Match", command=self._confirm_match,
                   bootstyle="success").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Manual Link", command=self._manual_link,
                   bootstyle="info").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Unlink Selected", command=self._unlink_match,
                   bootstyle="warning").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="📊 Export Report", command=self._export_report,
                   bootstyle="secondary-outline").pack(side=tk.LEFT, padx=(0, 6))
                   
        ttk.Button(btn_frame, text="Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _load_accounts(self):
        self._accounts = db.get_bank_accounts(self._company_id)
        if not self._accounts:
            self._account_combo.set("No accounts configured")
            self._account_combo["values"] = []
            return
            
        self._account_map = {f"{a['account_name']} ({a['currency']})": a["id"] for a in self._accounts}
        self._account_combo["values"] = list(self._account_map.keys())
        
        if self._current_account_id:
            for name, aid in self._account_map.items():
                if aid == self._current_account_id:
                    self._account_combo.set(name)
                    break
        else:
            self._account_combo.current(0)
            self._current_account_id = self._account_map[self._account_combo.get()]
            
        self._refresh_data()

    def _on_account_changed(self, event=None):
        name = self._account_combo.get()
        self._current_account_id = self._account_map.get(name)
        self._refresh_data()

    def _refresh_data(self):
        if not self._current_account_id:
            return
            
        # Update Summary
        summary = db.get_reconciliation_summary(self._current_account_id, self._company_id)
        self._summary_labels["total"].config(text=str(summary["total_bank_txns"]))
        self._summary_labels["unmatched"].config(text=str(summary["unmatched_txns"]))
        self._summary_labels["matched"].config(text=str(summary["matched_txns"]))
        self._summary_labels["reconciled"].config(text=str(summary["reconciled_txns"]))
        
        # Reload Bank Txns
        self._tree_l.delete(*self._tree_l.get_children())
        txns = db.get_bank_transactions(self._current_account_id)
        
        filter_val = self._txn_filter_var.get().lower()
        
        for t in txns:
            # Only show debits (payments out) for voucher matching
            if t["debit_amount"] <= 0:
                continue
                
            status = t["reconciliation_status"]
            if filter_val != "all" and status != filter_val:
                continue
                
            icon = "⚪"
            if status == "matched": icon = "🟡 Matched"
            elif status == "reconciled": icon = "🟢 Recon."
            elif status == "disputed": icon = "🔴 Disputed"
            
            item_id = self._tree_l.insert("", tk.END, iid=f"t_{t['id']}", values=(
                t["transaction_date"],
                t["description"],
                t["reference"],
                f"{t['debit_amount']:,.2f}",
                icon
            ))
            
            if status == "matched":
                self._tree_l.item(item_id, tags=("matched",))
            elif status == "reconciled":
                self._tree_l.item(item_id, tags=("reconciled",))
                
        self._tree_l.tag_configure("matched", background="#fef3c7")
        self._tree_l.tag_configure("reconciled", background="#dcfce7", foreground="#166534")

        # Reload Vouchers
        self._refresh_vouchers()

    def _refresh_vouchers(self):
        self._tree_r.delete(*self._tree_r.get_children())
        
        # In a real app, you'd fetch unreconciled vouchers via DB query
        # For this prototype, we'll fetch all and filter
        vouchers = db.search_vouchers(
            query=self._v_search_var.get(), 
            company_id=self._company_id,
            status_filter="Active"
        )
        
        for v in vouchers:
            if v.get("reconciliation_status", "unreconciled") != "unreconciled":
                continue
                
            self._tree_r.insert("", tk.END, iid=f"v_{v['id']}", values=(
                v["voucher_number"],
                v["date"],
                v["paid_to"],
                f"{v['total_amount']:,.2f}",
                f"{v['payment_method']} {v['payment_ref']}"
            ))

    def _on_txn_select(self, event=None):
        sel = self._tree_l.selection()
        if not sel: return
        
        txn_id = int(sel[0][2:]) # strip "t_"
        
        # If it's matched, find the voucher and highlight it
        conn = db.get_connection()
        try:
            t = conn.execute("SELECT matched_voucher_id FROM bank_transactions WHERE id = ?", (txn_id,)).fetchone()
            if t and t["matched_voucher_id"]:
                vid = f"v_{t['matched_voucher_id']}"
                if self._tree_r.exists(vid):
                    self._tree_r.selection_set(vid)
                    self._tree_r.see(vid)
        finally:
            conn.close()

    def _import_statement(self):
        if not self._current_account_id:
            messagebox.showwarning("No Account", "Please create a bank account first.", parent=self)
            return
            
        filepath = filedialog.askopenfilename(
            title="Import Bank Statement CSV",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self
        )
        if not filepath:
            return
            
        # Optional: Show column mapping dialog here
        # For now, rely on auto-detect
        
        succ, err, batch = db.import_bank_statement_csv(self._current_account_id, filepath)
        
        messagebox.showinfo("Import Complete", 
                           f"Imported {succ} transactions successfully.\nFailed: {err} rows.", 
                           parent=self)
        self._refresh_data()

    def _auto_match(self):
        if not self._current_account_id: return
        
        matches = db.auto_match_bank_transactions(self._current_account_id, self._company_id)
        messagebox.showinfo("Auto-Match Complete", 
                           f"Automatically matched {len(matches)} transactions based on amount, date, and reference.", 
                           parent=self)
        self._refresh_data()

    def _manual_link(self):
        sel_l = self._tree_l.selection()
        sel_r = self._tree_r.selection()
        
        if not sel_l or not sel_r:
            messagebox.showwarning("Selection Required", 
                                  "Please select a bank transaction on the left AND a voucher on the right to link them.", 
                                  parent=self)
            return
            
        txn_id = int(sel_l[0][2:])
        v_id = int(sel_r[0][2:])
        
        if db.manual_match_bank_transaction(txn_id, v_id):
            self._refresh_data()

    def _confirm_match(self):
        sel = self._tree_l.selection()
        if not sel: return
        
        txn_id = int(sel[0][2:])
        
        # Check if it's matched
        conn = db.get_connection()
        try:
            t = conn.execute("SELECT reconciliation_status FROM bank_transactions WHERE id = ?", (txn_id,)).fetchone()
            if not t or t["reconciliation_status"] != "matched":
                messagebox.showinfo("Not Matched", "Selected transaction must be in 'Matched' state to confirm.", parent=self)
                return
        finally:
            conn.close()
            
        if db.confirm_reconciliation(txn_id, reconciled_by="User"):
            self._refresh_data()

    def _unlink_match(self):
        sel = self._tree_l.selection()
        if not sel: return
        
        txn_id = int(sel[0][2:])
        if db.unmatch_bank_transaction(txn_id):
            self._refresh_data()

    def _manage_accounts(self):
        """Open dialog to manage bank accounts."""
        dlg = BankAccountManagerDialog(self, company_id=self._company_id, on_change=self._load_accounts)
        self.wait_window(dlg)
        self._load_accounts()

    def _export_report(self):
        """Export current reconciliation summary and transactions to CSV."""
        if not self._current_account_id:
            messagebox.showwarning("No Account", "Please select a bank account first.", parent=self)
            return

        import csv
        acc_name = self._account_var.get().replace(" ", "_")
        default_filename = f"reconciliation_{acc_name}_{db.datetime.now().strftime('%Y%m%d')}.csv"
        filepath = filedialog.asksaveasfilename(
            title="Export Reconciliation Report",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self
        )
        if not filepath:
            return

        try:
            summary = db.get_reconciliation_summary(self._current_account_id, self._company_id)
            txns = db.get_bank_transactions(self._current_account_id)

            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["BANK RECONCILIATION REPORT"])
                writer.writerow(["Account", self._account_var.get()])
                writer.writerow(["Exported At", db.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                writer.writerow(["SUMMARY"])
                writer.writerow(["Total Bank Transactions", summary.get("total_bank_txns", 0)])
                writer.writerow(["Unmatched Transactions", summary.get("unmatched_txns", 0)])
                writer.writerow(["Auto-Matched Transactions", summary.get("matched_txns", 0)])
                writer.writerow(["Reconciled Transactions", summary.get("reconciled_txns", 0)])
                writer.writerow(["Disputed Transactions", summary.get("disputed_txns", 0)])
                writer.writerow(["Total Debits", f"{summary.get('total_debits', 0):.2f}"])
                writer.writerow([])
                writer.writerow(["TRANSACTION DETAILS"])
                writer.writerow(["ID", "Date", "Description", "Reference", "Debit", "Credit", "Status", "Matched Voucher ID", "Reconciled By", "Reconciled At"])
                for t in txns:
                    writer.writerow([
                        t["id"],
                        t["transaction_date"],
                        t["description"],
                        t["reference"],
                        f"{t['debit_amount']:.2f}",
                        f"{t['credit_amount']:.2f}",
                        t["reconciliation_status"],
                        t["matched_voucher_id"] or "",
                        t["reconciled_by"] or "",
                        t["reconciled_at"] or ""
                    ])
            messagebox.showinfo("Export Success", f"Reconciliation report exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export report: {e}", parent=self)


class BankAccountManagerDialog(tk.Toplevel):
    """Dialog for creating, editing, and managing company bank accounts."""

    def __init__(self, parent, company_id=1, on_change=None):
        super().__init__(parent)
        self._company_id = company_id
        self._on_change = on_change

        self.title("Bank Account Management")
        self.geometry("680x480")
        self.minsize(600, 400)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._build_ui()
        self._refresh_list()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="Manage Bank Accounts", font=("Segoe UI", 12, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Add and configure company bank accounts for statement reconciliation",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        # Main Table
        table_frame = ttk.Frame(self, padding=(12, 8))
        table_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "bank", "account_num", "currency", "status")
        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
        self._tree.heading("name", text="Account Name")
        self._tree.heading("bank", text="Bank Name")
        self._tree.heading("account_num", text="Account Number")
        self._tree.heading("currency", text="Currency")
        self._tree.heading("status", text="Status")

        self._tree.column("name", width=160)
        self._tree.column("bank", width=140)
        self._tree.column("account_num", width=140)
        self._tree.column("currency", width=70, anchor="center")
        self._tree.column("status", width=70, anchor="center")

        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Form to add new account
        form = ttk.LabelFrame(self, text="Add New Bank Account", padding=10)
        form.pack(fill=tk.X, padx=12, pady=(0, 8))

        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Account Name:", width=13).pack(side=tk.LEFT)
        self._name_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._name_var, width=22).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row1, text="Bank Name:", width=10).pack(side=tk.LEFT)
        self._bank_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._bank_var, width=22).pack(side=tk.LEFT)

        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(row2, text="Account No:", width=13).pack(side=tk.LEFT)
        self._num_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._num_var, width=22).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row2, text="Currency:", width=10).pack(side=tk.LEFT)
        self._curr_var = tk.StringVar(value=db.get_company_base_currency(self._company_id))
        currencies = [c["code"] for c in db.get_currencies()] or ["LKR", "USD", "EUR", "GBP"]
        curr_combo = ttk.Combobox(row2, textvariable=self._curr_var, values=currencies, state="readonly", width=8)
        curr_combo.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Button(row2, text="+ Add Account", command=self._add_account,
                   bootstyle="success").pack(side=tk.LEFT)

        # Footer Actions
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="Toggle Active / Inactive", command=self._toggle_active,
                   bootstyle="warning-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Delete Account", command=self._delete_account,
                   bootstyle="danger-outline").pack(side=tk.LEFT)

        ttk.Button(footer, text="Done / Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        accounts = db.get_bank_accounts(self._company_id, active_only=False)
        for a in accounts:
            status = "Active" if a["is_active"] else "Inactive"
            item_id = self._tree.insert("", tk.END, iid=str(a["id"]), values=(
                a["account_name"],
                a.get("bank_name", ""),
                a.get("account_number", ""),
                a.get("currency", "LKR"),
                status
            ))
            if not a["is_active"]:
                self._tree.item(item_id, tags=("inactive",))
        self._tree.tag_configure("inactive", foreground="#94a3b8")

    def _add_account(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Account Name is required.", parent=self)
            return

        bank = self._bank_var.get().strip()
        acc_num = self._num_var.get().strip()
        curr = self._curr_var.get().strip() or "LKR"

        aid = db.create_bank_account(self._company_id, name, account_number=acc_num, bank_name=bank, currency=curr)
        if aid:
            self._name_var.set("")
            self._bank_var.set("")
            self._num_var.set("")
            self._refresh_list()
            if self._on_change:
                self._on_change()
        else:
            messagebox.showerror("Error", "Failed to create bank account.", parent=self)

    def _toggle_active(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select an account from the table.", parent=self)
            return
        aid = int(sel[0])
        accounts = db.get_bank_accounts(self._company_id, active_only=False)
        for a in accounts:
            if a["id"] == aid:
                db.update_bank_account(aid, {"is_active": 0 if a["is_active"] else 1})
                break
        self._refresh_list()
        if self._on_change:
            self._on_change()

    def _delete_account(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select an account to delete.", parent=self)
            return
        aid = int(sel[0])
        if messagebox.askyesno("Confirm Delete",
                               "Are you sure you want to delete this bank account?\n"
                               "All imported transactions for this account will be removed.",
                               parent=self):
            db.delete_bank_account(aid)
            self._refresh_list()
            if self._on_change:
                self._on_change()

