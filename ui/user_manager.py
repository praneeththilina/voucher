"""
User Management & RBAC Module.
Provides administrator-only user and role management.
Roles supported: 'viewer', 'data_entry', 'cashier', 'manager', 'admin'.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

import database as db

ROLE_HIERARCHY = {
    "viewer": 1,
    "data_entry": 2,
    "cashier": 3,
    "manager": 4,
    "admin": 5,
}

ROLE_DESCRIPTIONS = {
    "viewer": "Viewer: Read-only access to vouchers and reports.",
    "data_entry": "Data Entry: Create, edit, and duplicate vouchers.",
    "cashier": "Cashier: Print vouchers, manage floats and templates.",
    "manager": "Manager: Approve/reject vouchers, cancel, export, manage tags/categories.",
    "admin": "Admin: Full unrestricted system access.",
}


def current_user_has_role(required_role="admin"):
    """Return whether the signed-in user meets the required role level."""
    user = db.get_current_user()
    if not user:
        return False
    user_role = user.get("role", "viewer").lower()
    return (
        ROLE_HIERARCHY.get(user_role, 0)
        >= ROLE_HIERARCHY.get(required_role.lower(), 0)
    )

class NewPasswordDialog(tk.Toplevel):
    """Collect and validate a masked replacement password."""

    def __init__(self, parent):
        super().__init__(parent)
        self.password = None
        self.title("Reset User Password")
        self.geometry("420x290")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._password_var = tk.StringVar()
        self._confirm_var = tk.StringVar()

        content = ttk.Frame(self, padding=24)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Set a new password",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text="Use at least 8 characters; numbers-only passwords are blocked.",
            bootstyle="secondary",
            wraplength=360,
        ).pack(anchor="w", pady=(4, 14))
        ttk.Label(content, text="New password").pack(anchor="w")
        ttk.Entry(
            content,
            textvariable=self._password_var,
            show="•",
        ).pack(fill=tk.X, ipady=4, pady=(3, 10))
        ttk.Label(content, text="Confirm password").pack(anchor="w")
        confirm = ttk.Entry(
            content,
            textvariable=self._confirm_var,
            show="•",
        )
        confirm.pack(fill=tk.X, ipady=4, pady=(3, 16))
        confirm.bind("<Return>", lambda _event: self._save())
        ttk.Button(
            content,
            text="Reset password",
            command=self._save,
            bootstyle="success",
        ).pack(fill=tk.X)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _save(self):
        password = self._password_var.get()
        valid, validation_message = db.validate_new_password(password)
        if not valid:
            messagebox.showwarning(
                "Weak Password",
                validation_message,
                parent=self,
            )
            return
        if password != self._confirm_var.get():
            messagebox.showwarning(
                "Passwords Do Not Match",
                "Enter the same password in both fields.",
                parent=self,
            )
            return
        self.password = password
        self.destroy()

class ChangePasswordDialog(tk.Toplevel):
    """Let the authenticated user change their own password."""

    def __init__(self, parent):
        super().__init__(parent)
        self.changed = False
        self.title("Change Password")
        self.geometry("420x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._current_var = tk.StringVar()
        self._new_var = tk.StringVar()
        self._confirm_var = tk.StringVar()

        content = ttk.Frame(self, padding=24)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Change your password",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text="Your current password is required.",
            bootstyle="secondary",
        ).pack(anchor="w", pady=(4, 14))
        for label, variable in (
            ("Current password", self._current_var),
            ("New password", self._new_var),
            ("Confirm new password", self._confirm_var),
        ):
            ttk.Label(content, text=label).pack(anchor="w", pady=(5, 3))
            ttk.Entry(
                content,
                textvariable=variable,
                show="•",
            ).pack(fill=tk.X, ipady=4)
        ttk.Button(
            content,
            text="Change password",
            command=self._save,
            bootstyle="success",
        ).pack(fill=tk.X, ipady=4, pady=(18, 0))

    def _save(self):
        user = db.get_current_user()
        if not user:
            self.destroy()
            return
        if self._new_var.get() != self._confirm_var.get():
            messagebox.showwarning(
                "Passwords Do Not Match",
                "Enter the same new password in both fields.",
                parent=self,
            )
            return
        try:
            changed = db.change_user_password(
                user["id"],
                self._current_var.get(),
                self._new_var.get(),
            )
        except ValueError as exc:
            messagebox.showwarning(
                "Weak Password",
                str(exc),
                parent=self,
            )
            return
        if not changed:
            messagebox.showerror(
                "Password Not Changed",
                "The current password is incorrect.",
                parent=self,
            )
            return
        self.changed = True
        self.destroy()

class UserManagementDialog(tk.Toplevel):
    """Modal dialog for administrators to manage users and roles."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self.title("User Management & RBAC")
        self.geometry("760x520")
        self.minsize(680, 420)
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
        self.deiconify()

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="User Roles & Access Control (RBAC)",
                 font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Manage user accounts, passwords, roles, and active status",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        # Main Table
        table_frame = ttk.Frame(self, padding=(12, 8))
        table_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("username", "display_name", "role", "status", "last_login")
        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
        self._tree.heading("username", text="Username")
        self._tree.heading("display_name", text="Display Name")
        self._tree.heading("role", text="Role")
        self._tree.heading("status", text="Status")
        self._tree.heading("last_login", text="Last Login")

        self._tree.column("username", width=120)
        self._tree.column("display_name", width=160)
        self._tree.column("role", width=100, anchor="center")
        self._tree.column("status", width=80, anchor="center")
        self._tree.column("last_login", width=140)

        sb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Form to add new user
        form = ttk.LabelFrame(self, text="Create New User Account", padding=10)
        form.pack(fill=tk.X, padx=12, pady=(0, 8))

        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Username:", width=12).pack(side=tk.LEFT)
        self._uname_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._uname_var, width=16).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row1, text="Display Name:", width=12).pack(side=tk.LEFT)
        self._dname_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._dname_var, width=20).pack(side=tk.LEFT, padx=(0, 12))

        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(row2, text="Password:", width=12).pack(side=tk.LEFT)
        self._pin_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self._pin_var, width=16, show="*").pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row2, text="Role:", width=12).pack(side=tk.LEFT)
        self._role_var = tk.StringVar(value="data_entry")
        role_combo = ttk.Combobox(row2, textvariable=self._role_var,
                                  values=["viewer", "data_entry", "cashier", "manager", "admin"],
                                  state="readonly", width=14)
        role_combo.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Button(row2, text="+ Add User", command=self._add_user,
                   bootstyle="success").pack(side=tk.LEFT)

        # Footer Actions
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="Reset Password", command=self._reset_pin,
                   bootstyle="info-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Toggle Active", command=self._toggle_active,
                   bootstyle="warning-outline").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(footer, text="Delete User", command=self._delete_user,
                   bootstyle="danger-outline").pack(side=tk.LEFT)
        ttk.Button(footer, text="☁️ Sync Cloud", command=self._sync_cloud_users,
                   bootstyle="primary-outline").pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(footer, text="Done / Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        users = db.get_users(active_only=False)
        for u in users:
            status = "Active" if u["is_active"] else "Inactive"
            item_id = self._tree.insert("", tk.END, iid=str(u["id"]), values=(
                u["username"],
                u["display_name"],
                u["role"].upper(),
                status,
                u.get("last_login") or "Never"
            ))
            if not u["is_active"]:
                self._tree.item(item_id, tags=("inactive",))
        self._tree.tag_configure("inactive", foreground="#94a3b8")

    def _add_user(self):
        uname = self._uname_var.get().strip()
        dname = self._dname_var.get().strip()
        pin = self._pin_var.get().strip()
        role = self._role_var.get().strip()

        if not uname or not dname or not pin:
            messagebox.showwarning("Validation Error", "Username, display name, and password are required.", parent=self)
            return
        valid, validation_message = db.validate_new_password(pin)
        if not valid:
            messagebox.showwarning(
                "Weak Password",
                validation_message,
                parent=self,
            )
            return

        uid = db.create_user(uname, dname, pin, role=role)
        if uid:
            try:
                import firebase_client
                if firebase_client.is_enabled():
                    firebase_client.push_user_to_cloud(uid, async_call=True)
            except Exception as e:
                print(f"Notice: Cloud sync user: {e}")

            self._uname_var.set("")
            self._dname_var.set("")
            self._pin_var.set("")
            self._refresh_list()
            messagebox.showinfo("Success", f"User '{uname}' ({role.upper()}) created successfully.", parent=self)
        else:
            messagebox.showerror("Error", f"Failed to create user '{uname}'. Username might already exist.", parent=self)

    def _reset_pin(self):
        """Set a new password for the selected user as an administrator."""
        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo(
                "Selection Required",
                "Please select a user to reset the password.",
                parent=self,
            )
            return
        user_id = int(selection[0])
        dialog = NewPasswordDialog(self)
        self.wait_window(dialog)
        if dialog.password is None:
            return
        if db.update_user(user_id, pin=dialog.password):
            try:
                import firebase_client
                if firebase_client.is_enabled():
                    firebase_client.push_user_to_cloud(
                        user_id, async_call=True
                    )
            except Exception:
                pass
            messagebox.showinfo(
                "Success",
                "Password reset successfully.",
                parent=self,
            )
        else:
            messagebox.showerror(
                "Error",
                "The password could not be reset.",
                parent=self,
            )
    def _toggle_active(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a user.", parent=self)
            return
        uid = int(sel[0])
        users = db.get_users(active_only=False)
        for u in users:
            if u["id"] == uid:
                if not db.update_user(
                    uid,
                    is_active=not u["is_active"],
                ):
                    messagebox.showwarning(
                        "Change blocked",
                        "You cannot deactivate your own account or the last "
                        "active administrator.",
                        parent=self,
                    )
                    return
                try:
                    import firebase_client
                    if firebase_client.is_enabled():
                        firebase_client.push_user_to_cloud(uid, async_call=True)
                except Exception:
                    pass
                break
        self._refresh_list()

    def _delete_user(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a user to delete.", parent=self)
            return
        uid = int(sel[0])
        uname = None
        for u in db.get_users(active_only=False):
            if u["id"] == uid:
                uname = u["username"]
                break
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to permanently delete this user account?", parent=self):
            if not db.delete_user(uid):
                messagebox.showwarning(
                    "Delete blocked",
                    "You cannot delete your own account or the last active "
                    "administrator.",
                    parent=self,
                )
                return
            if uname:
                try:
                    import firebase_client
                    if firebase_client.is_enabled():
                        firebase_client.delete_user_from_cloud(uname, async_call=True)
                except Exception:
                    pass
            self._refresh_list()

    def _sync_cloud_users(self):
        try:
            import firebase_client
            if not firebase_client.is_configured():
                messagebox.showinfo("Cloud Not Configured", "Firebase Cloud is not configured. Go to Settings -> Cloud to configure Firebase.", parent=self)
                return
            ok, count, msg = firebase_client.pull_cloud_users()
            self._refresh_list()
            if ok:
                messagebox.showinfo("Cloud Sync Complete", f"Successfully synced user accounts with Firebase Cloud!\n\n{msg}", parent=self)
            else:
                messagebox.showerror("Cloud Sync Error", f"Failed to sync users: {msg}", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Sync error: {e}", parent=self)
