"""
User Management & RBAC Module.
Provides UserManagementDialog for managing users & roles, and LoginDialog for authentication.
Roles supported: 'viewer', 'data_entry', 'cashier', 'manager', 'admin'.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
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
    """Check if the currently logged-in user meets or exceeds the required role level."""
    if not db.is_rbac_enabled():
        return True
    u = db.get_current_user()
    if not u:
        return False
    user_role = u.get("role", "viewer").lower()
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role.lower(), 0)


class UserManagementDialog(tk.Toplevel):
    """Modal dialog for Admin to manage users, PINs, and permission roles."""

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
        tk.Label(header, text="Manage user accounts, assign roles, and configure PIN authentication",
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

        self._tree.bind("<Return>", lambda e: self._reset_pin())
        self._tree.bind("<KP_Enter>", lambda e: self._reset_pin())
        self._tree.bind("<Delete>", lambda e: self._delete_user())
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._update_button_states())

        # Form to add new user
        form = ttk.LabelFrame(self, text="Create New User Account", padding=10)
        form.pack(fill=tk.X, padx=12, pady=(0, 8))

        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Username:", width=12).pack(side=tk.LEFT)
        self._uname_var = tk.StringVar()
        uname_entry = ttk.Entry(row1, textvariable=self._uname_var, width=16)
        uname_entry.pack(side=tk.LEFT, padx=(0, 12))
        ToolTip(uname_entry, text="Enter username for the new account")

        ttk.Label(row1, text="Display Name:", width=12).pack(side=tk.LEFT)
        self._dname_var = tk.StringVar()
        dname_entry = ttk.Entry(row1, textvariable=self._dname_var, width=20)
        dname_entry.pack(side=tk.LEFT, padx=(0, 12))
        ToolTip(dname_entry, text="Enter user's full name or display title")

        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(row2, text="PIN Code:", width=12).pack(side=tk.LEFT)
        self._pin_var = tk.StringVar()
        pin_entry = ttk.Entry(row2, textvariable=self._pin_var, width=16, show="*")
        pin_entry.pack(side=tk.LEFT, padx=(0, 12))
        ToolTip(pin_entry, text="Set 4-6 digit numerical PIN code")

        ttk.Label(row2, text="Role:", width=12).pack(side=tk.LEFT)
        self._role_var = tk.StringVar(value="data_entry")
        role_combo = ttk.Combobox(row2, textvariable=self._role_var,
                                  values=["viewer", "data_entry", "cashier", "manager", "admin"],
                                  state="readonly", width=14)
        role_combo.pack(side=tk.LEFT, padx=(0, 16))
        ToolTip(role_combo, text="Select RBAC permission role level")

        add_btn = ttk.Button(row2, text="+ Add User", command=self._add_user,
                             bootstyle="success")
        add_btn.pack(side=tk.LEFT)
        ToolTip(add_btn, text="Create new user account")

        # Footer Actions
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        self._reset_pin_btn = ttk.Button(footer, text="Reset PIN", command=self._reset_pin,
                                         bootstyle="info-outline", state=tk.DISABLED)
        self._reset_pin_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(self._reset_pin_btn, text="Reset PIN code for selected user")

        self._toggle_btn = ttk.Button(footer, text="Toggle Active", command=self._toggle_active,
                                      bootstyle="warning-outline", state=tk.DISABLED)
        self._toggle_btn.pack(side=tk.LEFT, padx=(0, 6))
        ToolTip(self._toggle_btn, text="Toggle selected user active/inactive status")

        self._delete_btn = ttk.Button(footer, text="Delete User", command=self._delete_user,
                                      bootstyle="danger-outline", state=tk.DISABLED)
        self._delete_btn.pack(side=tk.LEFT)
        ToolTip(self._delete_btn, text="Delete selected user account (Delete)")

        self._sync_btn = ttk.Button(footer, text="☁️ Sync Cloud", command=self._sync_cloud_users,
                                    bootstyle="primary-outline")
        self._sync_btn.pack(side=tk.LEFT, padx=(6, 0))
        ToolTip(self._sync_btn, text="Sync user accounts with Firebase Cloud")

        close_btn = ttk.Button(footer, text="Done / Close", command=self.destroy,
                               bootstyle="secondary")
        close_btn.pack(side=tk.RIGHT)
        ToolTip(close_btn, text="Close user management dialog (Escape)")

    def _update_button_states(self):
        """Enable Reset PIN, Toggle Active, and Delete User buttons only when a user row is selected."""
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        if hasattr(self, "_reset_pin_btn") and self._reset_pin_btn:
            self._reset_pin_btn.config(state=state)
        if hasattr(self, "_toggle_btn") and self._toggle_btn:
            self._toggle_btn.config(state=state)
        if hasattr(self, "_delete_btn") and self._delete_btn:
            self._delete_btn.config(state=state)

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

        children = self._tree.get_children()
        if children:
            first_item = children[0]
            self._tree.selection_set(first_item)
            self._tree.focus(first_item)
        self._update_button_states()

    def _add_user(self):
        uname = self._uname_var.get().strip()
        dname = self._dname_var.get().strip()
        pin = self._pin_var.get().strip()
        role = self._role_var.get().strip()

        if not uname or not dname or not pin:
            messagebox.showwarning("Validation Error", "Username, Display Name, and PIN are required.", parent=self)
            return
        if len(pin) < 4:
            messagebox.showwarning("PIN Too Short", "PIN must be at least 4 digits.", parent=self)
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
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a user to reset PIN.", parent=self)
            return
        uid = int(sel[0])

        new_pin = ttk.dialogs.Querybox.get_string("Enter new 4-6 digit PIN for this user:", title="Reset User PIN", parent=self)
        if new_pin is not None:
            new_pin = new_pin.strip()
            if len(new_pin) < 4:
                messagebox.showwarning("Invalid PIN", "PIN must be at least 4 characters.", parent=self)
                return
            if db.update_user(uid, pin=new_pin):
                try:
                    import firebase_client
                    if firebase_client.is_enabled():
                        firebase_client.push_user_to_cloud(uid, async_call=True)
                except Exception:
                    pass
                messagebox.showinfo("Success", "PIN reset successfully.", parent=self)
            else:
                messagebox.showerror("Error", "Failed to reset PIN.", parent=self)

    def _toggle_active(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a user.", parent=self)
            return
        uid = int(sel[0])
        users = db.get_users(active_only=False)
        for u in users:
            if u["id"] == uid:
                db.update_user(uid, is_active=not u["is_active"])
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
            db.delete_user(uid)
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


class LoginDialog(tk.Toplevel):
    """Login modal dialog prompted on startup when users are configured."""

    def __init__(self, parent, on_success=None):
        super().__init__(parent)
        self.title("Voucher Manager — Login")
        self.geometry("380x280")
        self.resizable(False, False)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._on_success = on_success
        self._authenticated = False

        self._build_ui()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")

        self.lift()
        self.focus_force()

    def _build_ui(self):
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="🔐 Sign In", font=("Segoe UI", 12, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Please authenticate with your username and PIN",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(self, padding=(24, 16))
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content, text="Username:", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
        self._uname_var = tk.StringVar()
        uname_entry = ttk.Entry(content, textvariable=self._uname_var, width=30)
        uname_entry.pack(fill=tk.X, pady=(0, 10))
        uname_entry.focus_set()

        ttk.Label(content, text="PIN Code:", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 2))
        self._pin_var = tk.StringVar()
        pin_entry = ttk.Entry(content, textvariable=self._pin_var, width=30, show="*")
        pin_entry.pack(fill=tk.X, pady=(0, 16))
        pin_entry.bind("<Return>", lambda e: self._attempt_login())

        btn_row = ttk.Frame(content)
        btn_row.pack(fill=tk.X)

        ttk.Button(btn_row, text="Sign In", command=self._attempt_login,
                   bootstyle="primary").pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancel / Exit", command=self.destroy,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT)

    def _attempt_login(self):
        uname = self._uname_var.get().strip()
        pin = self._pin_var.get().strip()
        if not uname or not pin:
            messagebox.showwarning("Login Required", "Please enter both username and PIN.", parent=self)
            return

        user = db.authenticate_user(uname, pin)
        if user:
            db.set_current_user(user)
            self._authenticated = True
            if self._on_success:
                self._on_success(user)
            self.destroy()
        else:
            messagebox.showerror("Access Denied", "Invalid username or PIN.", parent=self)
