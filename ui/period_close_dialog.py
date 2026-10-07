"""Accounting period close controls."""

import tkinter as tk
from tkinter import messagebox, simpledialog

import ttkbootstrap as ttk

import database as db
from ui.widgets import SmartDateEntry


class PeriodCloseDialog(tk.Toplevel):
    """Close or reopen historical accounting periods for one company."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("Accounting Period Close")
        self.geometry("560x390")
        self.minsize(520, 360)
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self._refresh_status()

    def _build_ui(self):
        body = ttk.Frame(self, padding=20)
        body.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            body,
            text="Close the Books",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            body,
            text=(
                "Transactions dated on or before the close date cannot be created, "
                "edited, cancelled, restored, or deleted."
            ),
            foreground="#475569",
            wraplength=500,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 16))

        self._status_frame = ttk.LabelFrame(body, text="Current status", padding=12)
        self._status_frame.pack(fill=tk.X, pady=(0, 14))
        self._status_var = tk.StringVar()
        ttk.Label(
            self._status_frame,
            textvariable=self._status_var,
            font=("Segoe UI", 10, "bold"),
            wraplength=470,
        ).pack(anchor=tk.W)

        form = ttk.LabelFrame(body, text="New close date", padding=12)
        form.pack(fill=tk.X)
        row = ttk.Frame(form)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Close through:", width=15).pack(side=tk.LEFT)
        self._date_entry = SmartDateEntry(row)
        self._date_entry.pack(side=tk.LEFT)

        ttk.Label(form, text="Reason / note:").pack(anchor=tk.W, pady=(12, 4))
        self._reason_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._reason_var).pack(fill=tk.X)

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X, pady=(18, 0))
        ttk.Button(
            buttons,
            text="Lock Period",
            command=self._lock_period,
            bootstyle="danger",
        ).pack(side=tk.LEFT)
        self._unlock_button = ttk.Button(
            buttons,
            text="Reopen Books",
            command=self._unlock_period,
            bootstyle="warning-outline",
        )
        self._unlock_button.pack(side=tk.LEFT, padx=8)
        ttk.Button(
            buttons,
            text="Close",
            command=self.destroy,
            bootstyle="secondary",
        ).pack(side=tk.RIGHT)

    def _refresh_status(self):
        lock = db.get_accounting_period_lock(self.company_id)
        if lock:
            detail = f"Books are closed through {lock['period_end']}."
            if lock.get("locked_by"):
                detail += f" Locked by {lock['locked_by']}."
            if lock.get("reason"):
                detail += f" Reason: {lock['reason']}"
            self._status_var.set(detail)
            self._unlock_button.configure(state=tk.NORMAL)
        else:
            self._status_var.set("Books are open. No accounting close date is active.")
            self._unlock_button.configure(state=tk.DISABLED)

    def _lock_period(self):
        period_end = self._date_entry.get_date()
        if not messagebox.askyesno(
            "Confirm Period Close",
            f"Close all accounting periods through {period_end}?\n\n"
            "Historical transactions in this range will become read-only.",
            parent=self,
        ):
            return
        user = db.get_current_user() or {}
        actor = user.get("display_name") or user.get("username") or "Admin"
        try:
            db.lock_accounting_period(
                period_end,
                company_id=self.company_id,
                locked_by=actor,
                reason=self._reason_var.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Invalid Close Date", str(exc), parent=self)
            return
        self._refresh_status()
        messagebox.showinfo(
            "Books Closed",
            f"Transactions through {period_end} are now locked.",
            parent=self,
        )

    def _unlock_period(self):
        credential = simpledialog.askstring(
            "Administrator Verification",
            "Enter administrator PIN or password to reopen the books:",
            show="*",
            parent=self,
        )
        if credential is None:
            return
        if not db.verify_admin_pin_or_password(credential):
            messagebox.showerror(
                "Verification Failed", "Incorrect administrator credential.", parent=self
            )
            return
        db.unlock_accounting_period(self.company_id)
        self._refresh_status()
        messagebox.showinfo(
            "Books Reopened", "The accounting close date was removed.", parent=self
        )