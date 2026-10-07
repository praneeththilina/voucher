"""
Approval Workflow Dialog.
PIN-based approval/rejection dialog for vouchers requiring authorization.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

import database as db


class ApprovalDialog(tk.Toplevel):
    """Modal dialog for approving or rejecting a voucher."""

    def __init__(self, parent, voucher_id, on_complete=None):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self._voucher_id = voucher_id
        self._on_complete = on_complete
        self._result = None

        self.title("Voucher Approval")
        self.geometry("440x400")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#1e293b", padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="Approval Required", font=("Segoe UI", 13, "bold"),
                 bg="#1e293b", fg="#ffffff").pack(anchor="w")

        # Voucher info
        v_full = db.get_voucher(self._voucher_id)
        if not v_full:
            tk.Label(self, text="Voucher not found", font=("Segoe UI", 10),
                     fg="#ef4444").pack(pady=20)
            return
        v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else v_full

        info = ttk.Frame(self, padding=(16, 12))
        info.pack(fill=tk.X)

        info_lines = [
            ("Voucher:", v.get("voucher_number", "")),
            ("Payee:", v.get("paid_to", "")),
            ("Amount:", f"{v.get('total_amount', 0):,.2f}"),
            ("Date:", v.get("date", "")),
            ("Status:", v.get("approval_status", "none")),
        ]

        for label, value in info_lines:
            row = ttk.Frame(info)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, font=("Segoe UI", 9), width=10, anchor="e").pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(self).pack(fill=tk.X, padx=16, pady=8)

        # Approver selection and PIN
        form = ttk.Frame(self, padding=(16, 4))
        form.pack(fill=tk.X)

        approvers = db.get_approvers()
        if not approvers:
            tk.Label(form, text="No approvers configured.\nGo to Settings > Manage Approvers to add one.",
                     font=("Segoe UI", 9), fg="#f59e0b", justify="center").pack(pady=16)
            ttk.Button(self, text="Close", command=self.destroy,
                       bootstyle="secondary").pack(pady=8)
            return

        ttk.Label(form, text="Select Approver:", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
        self._approver_var = tk.StringVar()
        self._approver_map = {f"{a['name']} (L{a['approval_level']})": a["id"] for a in approvers}
        approver_combo = ttk.Combobox(form, textvariable=self._approver_var,
                                       values=list(self._approver_map.keys()),
                                       state="readonly", width=30)
        approver_combo.pack(fill=tk.X, pady=(0, 8))
        if self._approver_map:
            approver_combo.current(0)

        ttk.Label(form, text="PIN:", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
        self._pin_var = tk.StringVar()
        pin_entry = ttk.Entry(form, textvariable=self._pin_var, show="*", width=20)
        pin_entry.pack(fill=tk.X, pady=(0, 8))
        pin_entry.focus_set()
        pin_entry.bind("<Return>", lambda e: self._approve())

        ttk.Label(form, text="Comment (optional):", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 2))
        self._comment_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._comment_var, width=30).pack(fill=tk.X, pady=(0, 8))

        # Action buttons
        btn_frame = ttk.Frame(self, padding=(16, 8))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Approve", command=self._approve,
                   bootstyle="success").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Reject", command=self._reject,
                   bootstyle="danger").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Cancel", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _get_approver_id(self):
        name = self._approver_var.get()
        return self._approver_map.get(name)

    def _approve(self):
        approver_id = self._get_approver_id()
        pin = self._pin_var.get().strip()
        if not approver_id or not pin:
            messagebox.showwarning("Missing Info", "Please select an approver and enter PIN.", parent=self)
            return

        success, msg = db.approve_voucher(self._voucher_id, approver_id, pin,
                                           comments=self._comment_var.get().strip())
        if success:
            messagebox.showinfo("Approved", msg, parent=self)
            self._result = "approved"
            if self._on_complete:
                self._on_complete("approved")
            self.destroy()
        else:
            messagebox.showerror("Approval Failed", msg, parent=self)

    def _reject(self):
        approver_id = self._get_approver_id()
        pin = self._pin_var.get().strip()
        if not approver_id or not pin:
            messagebox.showwarning("Missing Info", "Please select an approver and enter PIN.", parent=self)
            return

        comment = self._comment_var.get().strip()
        if not comment:
            messagebox.showwarning("Comment Required", "Please provide a reason for rejection.", parent=self)
            return

        success, msg = db.reject_voucher(self._voucher_id, approver_id, pin, comments=comment)
        if success:
            messagebox.showinfo("Rejected", msg, parent=self)
            self._result = "rejected"
            if self._on_complete:
                self._on_complete("rejected")
            self.destroy()
        else:
            messagebox.showerror("Rejection Failed", msg, parent=self)


class ApproverManagerDialog(tk.Toplevel):
    """Dialog to manage the list of approvers (add/edit/delete)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self.title("Manage Approvers")
        self.geometry("560x420")
        self.transient(parent)
        self.grab_set()

        self._company_id = db.get_active_company_id()
        self._build_ui()
        self._refresh_list()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        header = tk.Frame(self, bg="#1e293b", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="Manage Approvers", font=("Segoe UI", 12, "bold"),
                 bg="#1e293b", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Add authorized personnel who can approve vouchers via PIN",
                 font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8").pack(anchor="w")

        content = ttk.Frame(self, padding=10)
        content.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "level", "status")
        self._tree = ttk.Treeview(content, columns=cols, show="headings", height=10)
        self._tree.heading("name", text="Name")
        self._tree.heading("level", text="Approval Level")
        self._tree.heading("status", text="Status")
        self._tree.column("name", width=200)
        self._tree.column("level", width=120, anchor="center")
        self._tree.column("status", width=80, anchor="center")
        self._tree.pack(fill=tk.BOTH, expand=True)

        # Add new approver section
        add_frame = ttk.LabelFrame(self, text="Add New Approver", padding=8)
        add_frame.pack(fill=tk.X, padx=10, pady=(4, 0))

        ttk.Label(add_frame, text="Name:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self._new_name = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self._new_name, width=18).grid(row=0, column=1, padx=4)

        ttk.Label(add_frame, text="PIN:").grid(row=0, column=2, padx=(8, 4))
        self._new_pin = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self._new_pin, width=10, show="*").grid(row=0, column=3, padx=4)

        ttk.Label(add_frame, text="Level:").grid(row=0, column=4, padx=(8, 4))
        self._new_level = tk.StringVar(value="1")
        ttk.Combobox(add_frame, textvariable=self._new_level, values=["1", "2"],
                     state="readonly", width=4).grid(row=0, column=5, padx=4)

        ttk.Button(add_frame, text="Add", command=self._add_approver,
                   bootstyle="success").grid(row=0, column=6, padx=(8, 0))

        # Footer
        footer = ttk.Frame(self, padding=(10, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="Toggle Active", command=self._toggle_active,
                   bootstyle="warning-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Delete", command=self._delete_selected,
                   bootstyle="danger-outline").pack(side=tk.LEFT)
        ttk.Button(footer, text="Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        approvers = db.get_approvers(self._company_id, active_only=False)
        for a in approvers:
            status = "Active" if a["is_active"] else "Inactive"
            self._tree.insert("", tk.END, iid=str(a["id"]),
                              values=(a["name"], f"Level {a['approval_level']}", status))

    def _add_approver(self):
        name = self._new_name.get().strip()
        pin = self._new_pin.get().strip()
        if not name or not pin:
            messagebox.showwarning("Missing Info", "Name and PIN are required.", parent=self)
            return
        if len(pin) < 4:
            messagebox.showwarning("PIN Too Short", "PIN must be at least 4 characters.", parent=self)
            return

        level = int(self._new_level.get())
        result = db.add_approver(name, pin, self._company_id, level)
        if result:
            try:
                import firebase_client
                if firebase_client.is_enabled():
                    firebase_client.push_approver_to_cloud(result, async_call=True)
            except Exception:
                pass
            self._new_name.set("")
            self._new_pin.set("")
            self._refresh_list()
        else:
            messagebox.showerror("Error", "Failed to add approver.", parent=self)

    def _toggle_active(self):
        sel = self._tree.selection()
        if not sel:
            return
        aid = int(sel[0])
        approvers = db.get_approvers(self._company_id, active_only=False)
        for a in approvers:
            if a["id"] == aid:
                db.update_approver(aid, is_active=not a["is_active"])
                try:
                    import firebase_client
                    if firebase_client.is_enabled():
                        firebase_client.push_approver_to_cloud(aid, async_call=True)
                except Exception:
                    pass
                break
        self._refresh_list()

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        aid = int(sel[0])
        appr_name = None
        for a in db.get_approvers(self._company_id, active_only=False):
            if a["id"] == aid:
                appr_name = a["name"]
                break
        if messagebox.askyesno("Delete Approver", "Delete this approver?", parent=self):
            db.delete_approver(aid)
            if appr_name:
                try:
                    import firebase_client
                    if firebase_client.is_enabled():
                        firebase_client.delete_approver_from_cloud(self._company_id, appr_name, async_call=True)
                except Exception:
                    pass
            self._refresh_list()
