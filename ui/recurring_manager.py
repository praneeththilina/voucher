"""
Recurring Payment Schedule Manager Dialog.
Allows users to create, edit, pause, and delete recurring voucher schedules.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox
from datetime import datetime, date

import database as db


class RecurringManagerDialog(tk.Toplevel):
    """Modal dialog for managing recurring payment schedules."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Recurring Payments Manager")
        self.geometry("880x560")
        self.minsize(780, 460)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._company_id = db.get_active_company_id()
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
        self.bind("<F5>", lambda e: self._refresh_list())

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)

        tk.Label(header, text="Recurring Payments Manager",
                 font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Automate repeating vouchers: rent, fuel, utilities, subscriptions",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        # Main table
        content = ttk.Frame(self, padding=(10, 8))
        content.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "payee", "amount", "frequency", "mode", "next_run", "runs", "status")
        self._tree = ttk.Treeview(content, columns=cols, show="headings", height=14)
        self._tree.heading("name", text="Schedule Name")
        self._tree.heading("payee", text="Payee")
        self._tree.heading("amount", text="Amount")
        self._tree.heading("frequency", text="Frequency")
        self._tree.heading("mode", text="Mode")
        self._tree.heading("next_run", text="Next Run")
        self._tree.heading("runs", text="Runs")
        self._tree.heading("status", text="Status")

        self._tree.column("name", width=140)
        self._tree.column("payee", width=120)
        self._tree.column("amount", width=80, anchor="e")
        self._tree.column("frequency", width=80)
        self._tree.column("mode", width=80)
        self._tree.column("next_run", width=90)
        self._tree.column("runs", width=50, anchor="center")
        self._tree.column("status", width=60, anchor="center")

        sb = ttk.Scrollbar(content, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit_selected())
        self._tree.bind("<Return>", lambda e: self._edit_selected())
        self._tree.bind("<KP_Enter>", lambda e: self._edit_selected())
        self._tree.bind("<Delete>", lambda e: self._delete_selected())

        # Footer buttons
        footer = ttk.Frame(self, padding=(10, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="+ New Schedule", command=self._new_schedule,
                   bootstyle="success").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Edit", command=self._edit_selected,
                   bootstyle="info-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Pause / Resume", command=self._toggle_active,
                   bootstyle="warning-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Delete", command=self._delete_selected,
                   bootstyle="danger-outline").pack(side=tk.LEFT, padx=(0, 6))

        self._status_label = tk.Label(footer, text="", font=("Segoe UI", 8), fg="#64748b")
        self._status_label.pack(side=tk.RIGHT)

        ttk.Button(footer, text="Close (Esc)", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT, padx=(0, 8))

    def _refresh_list(self):
        """Reload schedules into the table."""
        self._tree.delete(*self._tree.get_children())
        schedules = db.get_recurring_schedules(self._company_id, active_only=False)

        for s in schedules:
            status = "Active" if s.get("is_active") else "Paused"
            mode_map = {"auto_create": "Auto", "remind_only": "Remind", "auto_hold": "Hold"}
            mode = mode_map.get(s.get("mode", ""), s.get("mode", ""))
            runs = str(s.get("total_runs", 0))
            if s.get("max_runs"):
                runs += f"/{s['max_runs']}"

            self._tree.insert("", tk.END, iid=str(s["id"]), values=(
                s.get("schedule_name", ""),
                s.get("paid_to", ""),
                f"{s.get('amount', 0):,.2f}",
                s.get("frequency", "").capitalize(),
                mode,
                s.get("next_run", ""),
                runs,
                status,
            ))

        self._status_label.configure(text=f"{len(schedules)} schedule(s)")

    def _get_selected_id(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a schedule first.", parent=self)
            return None
        return int(sel[0])

    def _new_schedule(self):
        """Open dialog to create a new recurring schedule."""
        dlg = _ScheduleEditDialog(self, company_id=self._company_id)
        self.wait_window(dlg)
        self._refresh_list()

    def _edit_selected(self):
        sid = self._get_selected_id()
        if sid is None:
            return
        sched = db.get_recurring_schedule(sid)
        if sched:
            dlg = _ScheduleEditDialog(self, schedule=sched, company_id=self._company_id)
            self.wait_window(dlg)
            self._refresh_list()

    def _toggle_active(self):
        sid = self._get_selected_id()
        if sid is None:
            return
        sched = db.get_recurring_schedule(sid)
        if sched:
            new_active = 0 if sched["is_active"] else 1
            db.update_recurring_schedule(sid, {"is_active": new_active})
            self._refresh_list()

    def _delete_selected(self):
        sid = self._get_selected_id()
        if sid is None:
            return
        if messagebox.askyesno("Delete Schedule", "Delete this recurring schedule?", parent=self):
            db.delete_recurring_schedule(sid)
            self._refresh_list()


class _ScheduleEditDialog(tk.Toplevel):
    """Create / Edit dialog for a single recurring schedule."""

    def __init__(self, parent, schedule=None, company_id=1):
        super().__init__(parent)
        self._schedule = schedule
        self._company_id = company_id
        self._is_edit = schedule is not None

        self.title("Edit Schedule" if self._is_edit else "New Recurring Schedule")
        self.geometry("520x520")
        self.transient(parent)
        self.grab_set()

        self._build_form()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_form(self):
        f = ttk.Frame(self, padding=16)
        f.pack(fill=tk.BOTH, expand=True)

        row = 0

        def add_field(label, var, row_num, width=30):
            ttk.Label(f, text=label, font=("Segoe UI", 9)).grid(row=row_num, column=0, sticky="w", pady=3)
            entry = ttk.Entry(f, textvariable=var, width=width)
            entry.grid(row=row_num, column=1, sticky="ew", padx=(8, 0), pady=3)
            return entry

        s = self._schedule or {}

        self._name_var = tk.StringVar(value=s.get("schedule_name", ""))
        add_field("Schedule Name:", self._name_var, row)
        row += 1

        self._payee_var = tk.StringVar(value=s.get("paid_to", ""))
        add_field("Payee:", self._payee_var, row)
        row += 1

        self._amount_var = tk.StringVar(value=str(s.get("amount", "")))
        add_field("Amount:", self._amount_var, row)
        row += 1

        self._desc_var = tk.StringVar(value=s.get("description", ""))
        add_field("Description:", self._desc_var, row)
        row += 1

        self._category_var = tk.StringVar(value=s.get("category", ""))
        add_field("Category:", self._category_var, row)
        row += 1

        # Frequency
        ttk.Label(f, text="Frequency:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self._freq_var = tk.StringVar(value=s.get("frequency", "monthly"))
        freq_combo = ttk.Combobox(f, textvariable=self._freq_var, width=28,
                                  values=["daily", "weekly", "biweekly", "monthly", "quarterly", "annually"],
                                  state="readonly")
        freq_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1

        # Day of month
        self._dom_var = tk.StringVar(value=str(s.get("day_of_month", "") or ""))
        add_field("Day of Month (1-28):", self._dom_var, row)
        row += 1

        # Mode
        ttk.Label(f, text="Mode:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self._mode_var = tk.StringVar(value=s.get("mode", "auto_create"))
        mode_combo = ttk.Combobox(f, textvariable=self._mode_var, width=28,
                                  values=["auto_create", "remind_only", "auto_hold"],
                                  state="readonly")
        mode_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1

        # Payment method
        ttk.Label(f, text="Payment Method:", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self._pm_var = tk.StringVar(value=s.get("payment_method", "Cash"))
        pm_combo = ttk.Combobox(f, textvariable=self._pm_var, width=28,
                                values=["Cash", "Cheque", "Bank Transfer", "Card"],
                                state="readonly")
        pm_combo.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1

        # Start date
        self._start_var = tk.StringVar(value=s.get("start_date", date.today().strftime("%Y-%m-%d")))
        add_field("Start Date:", self._start_var, row)
        row += 1

        # Given by
        self._given_var = tk.StringVar(value=s.get("cash_given_by", ""))
        add_field("Cash Given By:", self._given_var, row)
        row += 1

        f.columnconfigure(1, weight=1)

        # Buttons
        btn_frame = ttk.Frame(self, padding=(16, 8))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Save", command=self._save,
                   bootstyle="success").pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _save(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Please enter a schedule name.", parent=self)
            return

        try:
            amount = float(self._amount_var.get().replace(",", "")) if self._amount_var.get().strip() else 0
        except ValueError:
            messagebox.showwarning("Invalid Amount", "Please enter a valid amount.", parent=self)
            return

        dom = None
        if self._dom_var.get().strip():
            try:
                dom = int(self._dom_var.get())
                if dom < 1 or dom > 28:
                    dom = None
            except ValueError:
                pass

        data = {
            "schedule_name": name,
            "paid_to": self._payee_var.get().strip(),
            "amount": amount,
            "description": self._desc_var.get().strip(),
            "category": self._category_var.get().strip(),
            "frequency": self._freq_var.get(),
            "day_of_month": dom,
            "mode": self._mode_var.get(),
            "payment_method": self._pm_var.get(),
            "cash_given_by": self._given_var.get().strip(),
        }

        if self._is_edit:
            db.update_recurring_schedule(self._schedule["id"], data)
        else:
            start = self._start_var.get().strip() or date.today().strftime("%Y-%m-%d")
            data["start_date"] = start
            data["next_run"] = start
            db.create_recurring_schedule(data, self._company_id)

        self.destroy()
