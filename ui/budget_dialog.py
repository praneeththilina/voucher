"""
ui/budget_dialog.py
Account Budgets & Variance Analytics Management Dialog (v4.0).

Features:
- Interactive monthly and annual budget configuration per COA account
- Real-time KPI summary cards (Budget, Actual Spend, Variance, Utilization)
- Status badges (Within Budget, Warning >=80%, Exceeded >100%)
- Quick annual spread wizard (distributes annual budget equally across 12 months)
- Publication-quality PDF & CSV export
"""

import os
import csv
import calendar
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from reports.budget_vs_actual import generate_budget_vs_actual_pdf
from ui.dialogs import PdfViewerDialog


# =========================================================================
# 1. BUDGET ENTRY DIALOG
# =========================================================================

class BudgetEntryDialog(tb.Toplevel):
    """Modal dialog to set or update budget for a specific account and period."""

    def __init__(self, parent, company_id=None, account_id=None, year=None, month=None, on_saved_callback=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.account_id = account_id
        self.year = year or datetime.now().year
        self.month = month if month is not None else datetime.now().month
        self.on_saved_callback = on_saved_callback
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Set Account Budget")
        self.geometry("480x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._load_data()
        self._build_ui()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _load_data(self):
        self.accounts = db.get_chart_of_accounts(self.company_id)
        # Filter to Expense and Income accounts
        self.accounts = [a for a in self.accounts if a.get("account_type") in ("Expense", "Income") and a.get("is_active")]

        self.current_budget = 0.0
        self.notes = ""
        if self.account_id:
            b = db.get_account_budget(self.company_id, self.account_id, self.year, self.month)
            if b:
                self.current_budget = float(b.get("budget_amount") or 0.0)
                self.notes = b.get("notes") or ""

    def _build_ui(self):
        pad = tb.Frame(self, padding=20)
        pad.pack(fill=BOTH, expand=True)

        tb.Label(pad, text="🎯 Set Account Budget", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 14))

        # Account Selection
        tb.Label(pad, text="Target Account *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.acct_names = [f"{a['account_code']} — {a['account_name']} ({a['account_type']})" for a in self.accounts]
        self.acct_combo = tb.Combobox(pad, values=self.acct_names, state="readonly")
        if self.account_id:
            for idx, a in enumerate(self.accounts):
                if a["id"] == self.account_id:
                    self.acct_combo.current(idx)
                    break
        elif self.acct_names:
            self.acct_combo.current(0)
        self.acct_combo.pack(fill=X, pady=(2, 10))

        # Year and Month
        r1 = tb.Frame(pad)
        r1.pack(fill=X, pady=(0, 10))

        c1 = tb.Frame(r1)
        c1.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c1, text="Budget Year *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.year_var = tk.IntVar(value=self.year)
        tb.Spinbox(c1, from_=2020, to=2035, textvariable=self.year_var).pack(fill=X, pady=(2, 0))

        c2 = tb.Frame(r1)
        c2.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c2, text="Budget Month *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        month_choices = ["0 - Full Year (Annual)"] + [f"{m} - {calendar.month_name[m]}" for m in range(1, 13)]
        self.month_combo = tb.Combobox(c2, values=month_choices, state="readonly")
        self.month_combo.current(self.month)
        self.month_combo.pack(fill=X, pady=(2, 0))

        # Budget Amount
        tb.Label(pad, text=f"Budget Amount ({self.currency}) *:", font=("Segoe UI", 8, "bold")).pack(anchor=W, pady=(4, 0))
        self.amt_var = tk.StringVar(value=f"{self.current_budget:.2f}" if self.current_budget else "0.00")
        tb.Entry(pad, textvariable=self.amt_var).pack(fill=X, pady=(2, 10))

        # Notes
        tb.Label(pad, text="Budget Notes / Justification:", font=("Segoe UI", 8)).pack(anchor=W)
        self.notes_var = tk.StringVar(value=self.notes)
        tb.Entry(pad, textvariable=self.notes_var).pack(fill=X, pady=(2, 16))

        # Buttons
        btns = tb.Frame(pad)
        btns.pack(fill=X, side=BOTTOM)

        tb.Button(btns, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btns, text="Save Budget", bootstyle="success", command=self._save).pack(side=RIGHT)

    def _save(self):
        c_idx = self.acct_combo.current()
        if c_idx < 0 or c_idx >= len(self.accounts):
            messagebox.showwarning("Select Account", "Please select an account.", parent=self)
            return
        aid = self.accounts[c_idx]["id"]

        try:
            amt = float(self.amt_var.get().replace(",", "").strip())
            if amt < 0:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Invalid Amount", "Please enter a valid non-negative budget amount.", parent=self)
            return

        m_idx = self.month_combo.current()  # 0 is annual, 1..12 is monthly
        y_val = self.year_var.get()

        try:
            db.set_account_budget(
                company_id=self.company_id,
                account_id=aid,
                year=y_val,
                month=m_idx,
                amount=amt,
                notes=self.notes_var.get().strip()
            )
            messagebox.showinfo("Success", "Budget allocation saved successfully.", parent=self)
            if self.on_saved_callback:
                self.on_saved_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save budget:\n{e}", parent=self)


# =========================================================================
# 2. BUDGET MANAGER & VARIANCE DASHBOARD
# =========================================================================

class BudgetManagerDialog(tb.Toplevel):
    """
    Main Budget Management & Variance Analytics Dashboard.
    """

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Budgeting & Expense Variance Analytics (v4.0)")
        self.geometry("1120x680")
        self.minsize(920, 520)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_report()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Top Filter Bar
        flt = tb.Frame(container)
        flt.pack(fill=X, pady=(0, 10))

        tb.Label(flt, text="🎯 Budget Period:", font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=(0, 8))

        tb.Label(flt, text="Year:").pack(side=LEFT, padx=(0, 4))
        self.year_var = tk.IntVar(value=datetime.now().year)
        tb.Spinbox(flt, from_=2020, to=2035, textvariable=self.year_var, width=7, command=self._refresh_report).pack(side=LEFT, padx=(0, 10))

        tb.Label(flt, text="Month:").pack(side=LEFT, padx=(0, 4))
        month_choices = ["All Months (Full Year)"] + [calendar.month_name[m] for m in range(1, 13)]
        self.month_combo = tb.Combobox(flt, values=month_choices, state="readonly", width=18)
        self.month_combo.current(datetime.now().month)
        self.month_combo.pack(side=LEFT, padx=(0, 14))
        self.month_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_report())

        tb.Button(flt, text="🔄 Refresh", bootstyle="primary", command=self._refresh_report).pack(side=LEFT)

        # Action buttons on right
        tb.Button(flt, text="➕ Set Budget", bootstyle="success", command=self._open_budget_entry).pack(side=RIGHT, padx=(6, 0))
        tb.Button(flt, text="⚡ Annual Spread Wizard", bootstyle="warning-outline", command=self._open_spread_wizard).pack(side=RIGHT)

        # KPI Summary Cards
        kpi_frame = tb.Frame(container, padding=(0, 6))
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.kpi_budget = self._create_kpi_card(kpi_frame, "ALLOCATED BUDGET", "0.00", "info")
        self.kpi_actual = self._create_kpi_card(kpi_frame, "ACTUAL EXPENDITURE", "0.00", "primary")
        self.kpi_variance = self._create_kpi_card(kpi_frame, "REMAINING (VARIANCE)", "0.00", "success")
        self.kpi_burn = self._create_kpi_card(kpi_frame, "OVERALL BURN RATE", "0.0%", "secondary")

        # Treeview
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("code", "name", "type", "budget", "actual", "variance", "burn", "status")
        self.tree = tb.Treeview(tree_frame, columns=cols, show="headings", height=14)

        col_heads = [
            ("code", "Code", 80, "center"),
            ("name", "Account Name", 260, "w"),
            ("type", "Type", 90, "center"),
            ("budget", f"Budget ({self.currency})", 130, "e"),
            ("actual", f"Actual ({self.currency})", 130, "e"),
            ("variance", f"Variance ({self.currency})", 130, "e"),
            ("burn", "Burn %", 90, "e"),
            ("status", "Status", 110, "center"),
        ]
        for c, h, w, anch in col_heads:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor=anch)

        sb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_selected_budget())

        # Bottom Actions Bar
        bot = tb.Frame(container)
        bot.pack(fill=X, pady=(10, 0))

        tb.Button(bot, text="📄 Export PDF Report", bootstyle="success-outline", command=self._export_pdf).pack(side=LEFT, padx=(0, 6))
        tb.Button(bot, text="📊 Export CSV", bootstyle="info-outline", command=self._export_csv).pack(side=LEFT, padx=(0, 6))
        tb.Button(bot, text="🗑️ Clear Budget", bootstyle="danger-outline", command=self._clear_selected_budget).pack(side=LEFT)

        tb.Button(bot, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _create_kpi_card(self, parent, title, val, style):
        card = tb.Frame(parent, bootstyle=f"{style}", padding=8)
        card.pack(side=LEFT, fill=X, expand=True, padx=3)
        tb.Label(card, text=title, font=("Segoe UI", 7, "bold"), bootstyle=f"inverse-{style}").pack(anchor=W)
        lbl = tb.Label(card, text=f"{self.currency} {val}", font=("Segoe UI", 11, "bold"), bootstyle=f"inverse-{style}")
        lbl.pack(anchor=W, pady=(2, 0))
        return lbl

    def _refresh_report(self):
        y = self.year_var.get()
        m = self.month_combo.current()  # 0 is full year, 1..12 is monthly

        self.rep = db.generate_budget_vs_actual(self.company_id, y, m)

        # Update KPIs
        tb_amt = self.rep.get("total_budget", 0.0)
        ta_amt = self.rep.get("total_actual", 0.0)
        tv_amt = self.rep.get("total_variance", 0.0)
        tu_pct = self.rep.get("total_utilization_pct", 0.0)

        self.kpi_budget.configure(text=f"{self.currency} {tb_amt:,.2f}")
        self.kpi_actual.configure(text=f"{self.currency} {ta_amt:,.2f}")
        self.kpi_variance.configure(text=f"{self.currency} {tv_amt:,.2f}")
        self.kpi_burn.configure(text=f"{tu_pct:.1f}%")

        # Update Treeview
        for i in self.tree.get_children():
            self.tree.delete(i)

        for l in self.rep.get("lines", []):
            st = l["status"]
            if st == "Exceeded":
                st_badge = "🔴 Exceeded"
            elif st == "Warning":
                st_badge = "🟡 Warning"
            else:
                st_badge = "🟢 OK"

            self.tree.insert("", END, values=(
                l["account_code"],
                l["account_name"],
                l["account_type"],
                f"{l['budget_amount']:,.2f}",
                f"{l['actual_amount']:,.2f}",
                f"{l['variance']:,.2f}",
                f"{l['utilization_pct']:.1f}%",
                st_badge
            ))

    def _open_budget_entry(self):
        y = self.year_var.get()
        m = self.month_combo.current()
        BudgetEntryDialog(self, company_id=self.company_id, year=y, month=m, on_saved_callback=self._refresh_report)

    def _edit_selected_budget(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        lines = self.rep.get("lines", [])
        if idx < len(lines):
            aid = lines[idx]["account_id"]
            y = self.year_var.get()
            m = self.month_combo.current()
            BudgetEntryDialog(self, company_id=self.company_id, account_id=aid, year=y, month=m, on_saved_callback=self._refresh_report)

    def _clear_selected_budget(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        lines = self.rep.get("lines", [])
        if idx < len(lines):
            line = lines[idx]
            aid = line["account_id"]
            y = self.year_var.get()
            m = self.month_combo.current()
            if messagebox.askyesno("Confirm", f"Remove budget allocation for '{line['account_name']}' in {self.rep['period_label']}?", parent=self):
                db.delete_account_budget(self.company_id, aid, y, m)
                self._refresh_report()

    def _open_spread_wizard(self):
        """Spread an annual budget equally across 12 calendar months."""
        top = tb.Toplevel(self)
        top.title("Annual Budget Spread Wizard")
        top.geometry("450x300")
        top.resizable(False, False)
        top.transient(self)
        top.grab_set()

        # Center
        top.update_idletasks()
        w, h = top.winfo_width(), top.winfo_height()
        sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
        top.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        pad = tb.Frame(top, padding=16)
        pad.pack(fill=BOTH, expand=True)

        tb.Label(pad, text="⚡ Distribute Annual Budget to 12 Months", font=("Segoe UI", 11, "bold")).pack(anchor=W, pady=(0, 10))

        accts = [a for a in db.get_chart_of_accounts(self.company_id) if a.get("account_type") in ("Expense", "Income") and a.get("is_active")]
        acct_names = [f"{a['account_code']} — {a['account_name']}" for a in accts]
        acct_combo = tb.Combobox(pad, values=acct_names, state="readonly")
        if acct_names:
            acct_combo.current(0)
        acct_combo.pack(fill=X, pady=(0, 8))

        tb.Label(pad, text=f"Total Annual Budget ({self.currency}) *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        tot_var = tk.StringVar(value="1200000.00")
        tb.Entry(pad, textvariable=tot_var).pack(fill=X, pady=(2, 8))

        m_calc_lbl = tb.Label(pad, text=f"Monthly Allocation: {self.currency} 100,000.00 / month", font=("Segoe UI", 8, "italic"), bootstyle="info")
        m_calc_lbl.pack(anchor=W, pady=(0, 12))

        def _update_calc(*a):
            try:
                tot = float(tot_var.get().replace(",", "").strip())
                m_calc_lbl.configure(text=f"Monthly Allocation: {self.currency} {tot / 12.0:,.2f} / month")
            except Exception:
                pass
        tot_var.trace_add("write", _update_calc)

        def _apply():
            idx = acct_combo.current()
            if idx < 0:
                return
            aid = accts[idx]["id"]
            try:
                tot = float(tot_var.get().replace(",", "").strip())
                m_amt = round(tot / 12.0, 2)
                y = self.year_var.get()
                for m in range(1, 13):
                    db.set_account_budget(self.company_id, aid, y, m, m_amt, notes="Annual spread allocation")
                messagebox.showinfo("Success", f"Distributed {self.currency} {tot:,.2f} equally across months 1..12!", parent=top)
                top.destroy()
                self._refresh_report()
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}", parent=top)

        tb.Button(pad, text="Apply Distribution", bootstyle="success", command=_apply).pack(side=RIGHT)
        tb.Button(pad, text="Cancel", bootstyle="secondary", command=top.destroy).pack(side=RIGHT, padx=(0, 6))

    def _export_pdf(self):
        if not hasattr(self, "rep"):
            return
        pdf_path = generate_budget_vs_actual_pdf(self.rep)
        PdfViewerDialog(self.master, pdf_path, title=f"Budget Variance — {self.rep['period_label']}")

    def _export_csv(self):
        if not hasattr(self, "rep"):
            return
        fp = filedialog.asksaveasfilename(
            parent=self,
            title="Export Budget Variance to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv")],
            initialfile=f"budget_variance_{self.rep['year']}_{self.rep['month']}.csv"
        )
        if not fp:
            return

        with open(fp, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["BUDGET VS ACTUAL VARIANCE STATEMENT"])
            w.writerow(db._sanitize_csv_row(["Company", self.rep["company_name"]]))
            w.writerow(db._sanitize_csv_row(["Period", self.rep["period_label"]]))
            w.writerow(db._sanitize_csv_row(["Currency", self.rep["currency"]]))
            w.writerow([])
            w.writerow(["SUMMARY"])
            w.writerow(["Total Allocated Budget", f"{self.rep['total_budget']:.2f}"])
            w.writerow(["Total Actual Expenditure", f"{self.rep['total_actual']:.2f}"])
            w.writerow(["Net Variance (Remaining)", f"{self.rep['total_variance']:.2f}"])
            w.writerow(["Overall Burn Rate", f"{self.rep['total_utilization_pct']:.1f}%"])
            w.writerow([])
            w.writerow(["Code", "Account Name", "Type", "Budget", "Actual", "Variance", "Burn %", "Status"])
            for l in self.rep.get("lines", []):
                w.writerow(db._sanitize_csv_row([
                    l["account_code"], l["account_name"], l["account_type"],
                    f"{l['budget_amount']:.2f}", f"{l['actual_amount']:.2f}", f"{l['variance']:.2f}",
                    f"{l['utilization_pct']:.1f}%", l["status"]
                ]))

        messagebox.showinfo("Exported", f"Budget statement exported to:\n{fp}", parent=self)
