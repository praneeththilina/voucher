"""Secure company selection and authentication screens."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

import ttkbootstrap as ttk

import database as db
from company_store import CompanyFile, CompanyStore


GREEN = "#2F7D32"
DARK_GREEN = "#185B2A"
DEEP_GREEN = "#103C24"
PALE_GREEN = "#EAF5EC"
INK = "#17212B"
MUTED = "#65727E"
BORDER = "#D7DEE3"
WHITE = "#FFFFFF"


class LoginScreen(ttk.Frame):
    """Full-window company login gate shown before the accounting workspace."""

    def __init__(
        self,
        parent: tk.Misc,
        store: CompanyStore,
        on_authenticated: Callable[[dict], None],
        on_exit: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.store = store
        self.on_authenticated = on_authenticated
        self.on_exit = on_exit
        self._companies: list[CompanyFile] = []
        self._failed_attempts: dict[str, tuple[int, datetime | None]] = {}
        self._password_visible = tk.BooleanVar(value=False)
        self._company_var = tk.StringVar()
        self._username_var = tk.StringVar()
        self._password_var = tk.StringVar()
        self._status_var = tk.StringVar()
        self._build_ui()
        self.refresh_companies()
        self.pack(fill=tk.BOTH, expand=True)

    def _build_ui(self) -> None:
        self.configure(style="Login.TFrame")
        style = ttk.Style()
        style.configure("Login.TFrame", background="#F4F6F7")
        style.configure(
            "LoginCard.TFrame",
            background=WHITE,
            relief="flat",
        )
        style.configure(
            "LoginTitle.TLabel",
            background=WHITE,
            foreground=INK,
            font=("Segoe UI", 22, "bold"),
        )
        style.configure(
            "LoginText.TLabel",
            background=WHITE,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "LoginField.TLabel",
            background=WHITE,
            foreground=INK,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "LoginStatus.TLabel",
            background=WHITE,
            foreground="#B42318",
            font=("Segoe UI", 9),
        )

        shell = tk.Frame(self, bg="#F4F6F7")
        shell.pack(fill=tk.BOTH, expand=True)

        brand = tk.Frame(shell, bg=DEEP_GREEN, width=390)
        brand.pack(side=tk.LEFT, fill=tk.Y)
        brand.pack_propagate(False)

        brand_inner = tk.Frame(brand, bg=DEEP_GREEN, padx=48, pady=58)
        brand_inner.pack(fill=tk.BOTH, expand=True)
        mark = tk.Canvas(
            brand_inner,
            width=58,
            height=58,
            bg=DEEP_GREEN,
            highlightthickness=0,
        )
        mark.pack(anchor="w")
        mark.create_oval(3, 3, 55, 55, fill=GREEN, outline="#70C576", width=2)
        mark.create_text(
            29,
            29,
            text="V",
            fill=WHITE,
            font=("Segoe UI", 24, "bold"),
        )
        tk.Label(
            brand_inner,
            text="Voucher Manager",
            bg=DEEP_GREEN,
            fg=WHITE,
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w", pady=(22, 4))
        tk.Label(
            brand_inner,
            text="Small business accounting",
            bg=DEEP_GREEN,
            fg="#B8DCC2",
            font=("Segoe UI", 11),
        ).pack(anchor="w")
        tk.Frame(brand_inner, bg="#3D8052", height=1).pack(
            fill=tk.X, pady=(34, 28)
        )
        for text in (
            "One protected file for each company",
            "Role-based access for every user",
            "Passwords are never remembered",
        ):
            row = tk.Frame(brand_inner, bg=DEEP_GREEN)
            row.pack(fill=tk.X, pady=7)
            tk.Label(
                row,
                text="✓",
                bg=DEEP_GREEN,
                fg="#7BD389",
                font=("Segoe UI", 11, "bold"),
            ).pack(side=tk.LEFT)
            tk.Label(
                row,
                text=text,
                bg=DEEP_GREEN,
                fg="#DCEDE1",
                font=("Segoe UI", 9),
            ).pack(side=tk.LEFT, padx=(10, 0))

        right = tk.Frame(shell, bg="#F4F6F7")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        card = ttk.Frame(right, style="LoginCard.TFrame", padding=(46, 38))
        card.place(relx=0.5, rely=0.5, anchor="center", width=470, height=570)

        ttk.Label(card, text="Sign in", style="LoginTitle.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            card,
            text="Select a company file, then enter your username and password.",
            style="LoginText.TLabel",
            wraplength=370,
        ).pack(anchor="w", pady=(4, 26))

        ttk.Label(card, text="Company", style="LoginField.TLabel").pack(
            anchor="w", pady=(0, 5)
        )
        self._company_combo = ttk.Combobox(
            card,
            textvariable=self._company_var,
            state="readonly",
            font=("Segoe UI", 10),
        )
        self._company_combo.pack(fill=tk.X, ipady=5)
        self._company_combo.bind(
            "<<ComboboxSelected>>", self._on_company_selected
        )

        company_actions = ttk.Frame(card, style="LoginCard.TFrame")
        company_actions.pack(fill=tk.X, pady=(7, 18))
        ttk.Button(
            company_actions,
            text="Create company",
            command=self._create_company,
            bootstyle="link-success",
        ).pack(side=tk.LEFT)
        ttk.Button(
            company_actions,
            text="Open company file",
            command=self._open_company_file,
            bootstyle="link-secondary",
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(card, text="Username", style="LoginField.TLabel").pack(
            anchor="w", pady=(0, 5)
        )
        self._username_entry = ttk.Entry(
            card,
            textvariable=self._username_var,
            font=("Segoe UI", 10),
        )
        self._username_entry.pack(fill=tk.X, ipady=5, pady=(0, 15))

        password_header = ttk.Frame(card, style="LoginCard.TFrame")
        password_header.pack(fill=tk.X)
        ttk.Label(
            password_header,
            text="Password",
            style="LoginField.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Button(
            password_header,
            text="Forgot password?",
            command=self._forgot_password,
            bootstyle="link-success",
        ).pack(side=tk.RIGHT)

        password_row = ttk.Frame(card, style="LoginCard.TFrame")
        password_row.pack(fill=tk.X, pady=(5, 4))
        self._password_entry = ttk.Entry(
            password_row,
            textvariable=self._password_var,
            show="•",
            font=("Segoe UI", 10),
        )
        self._password_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        ttk.Checkbutton(
            password_row,
            text="Show",
            variable=self._password_visible,
            command=self._toggle_password,
            bootstyle="success-round-toggle",
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(
            card,
            textvariable=self._status_var,
            style="LoginStatus.TLabel",
            wraplength=370,
        ).pack(anchor="w", pady=(4, 8))

        self._sign_in_button = ttk.Button(
            card,
            text="Sign in",
            command=self._attempt_login,
            bootstyle="success",
        )
        self._sign_in_button.pack(fill=tk.X, ipady=7, pady=(3, 10))
        ttk.Button(
            card,
            text="Exit",
            command=self.on_exit,
            bootstyle="secondary-outline",
        ).pack(fill=tk.X, ipady=4)

        self._password_entry.bind(
            "<Return>", lambda _event: self._attempt_login()
        )
        self._username_entry.bind(
            "<Return>", lambda _event: self._password_entry.focus_set()
        )

    def refresh_companies(self, select_path: str | None = None) -> None:
        """Refresh the company picker and restore its remembered username."""
        self._companies = self.store.list_companies()
        labels = [
            f"{item.name}  ·  {Path(item.path).stem}"
            for item in self._companies
        ]
        self._company_combo.configure(values=labels)
        if not self._companies:
            self._company_var.set("No company files yet")
            self._company_combo.configure(state=tk.DISABLED)
            self._username_var.set("")
            self._status_var.set("Create or open a company file to continue.")
            return

        self._company_combo.configure(state="readonly")
        index = 0
        if select_path:
            selected = str(Path(select_path).resolve())
            for candidate_index, item in enumerate(self._companies):
                if str(Path(item.path).resolve()) == selected:
                    index = candidate_index
                    break
        self._company_combo.current(index)
        self._on_company_selected()
        self.after(50, self._focus_first_missing_field)

    def _selected_company(self) -> CompanyFile | None:
        index = self._company_combo.current()
        if index < 0 or index >= len(self._companies):
            return None
        return self._companies[index]

    def _on_company_selected(self, _event=None) -> None:
        company = self._selected_company()
        self._password_var.set("")
        self._status_var.set("")
        if company:
            self._username_var.set(company.last_username)
            self._focus_first_missing_field()

    def _focus_first_missing_field(self) -> None:
        if self._username_var.get().strip():
            self._password_entry.focus_set()
        else:
            self._username_entry.focus_set()

    def _toggle_password(self) -> None:
        self._password_entry.configure(
            show="" if self._password_visible.get() else "•"
        )

    def _prepare_company(self, company: CompanyFile) -> None:
        db.configure_database(company.path)
        db.init_db()
        db.set_active_company_id(company.company_id)

    def _attempt_login(self) -> None:
        company = self._selected_company()
        username = self._username_var.get().strip()
        password = self._password_var.get()
        if company is None:
            self._status_var.set("Select or create a company first.")
            return
        if not username or not password:
            self._status_var.set("Enter both username and password.")
            return

        attempts, locked_until = self._failed_attempts.get(
            company.path, (0, None)
        )
        now = datetime.now()
        if locked_until and now < locked_until:
            seconds = max(1, int((locked_until - now).total_seconds()))
            self._status_var.set(
                f"Too many attempts. Try again in {seconds} seconds."
            )
            return

        self._sign_in_button.configure(state=tk.DISABLED)
        self.update_idletasks()
        try:
            self._prepare_company(company)
            if not db.is_rbac_enabled():
                self._setup_first_admin(company)
                return

            user = db.authenticate_user(username, password)
            if not user:
                attempts += 1
                if attempts >= 5:
                    locked_until = now + timedelta(seconds=30)
                    attempts = 0
                    self._status_var.set(
                        "Too many failed attempts. Sign-in is locked for 30 seconds."
                    )
                else:
                    remaining = 5 - attempts
                    self._status_var.set(
                        f"Incorrect username or password. {remaining} attempt(s) remain."
                    )
                self._failed_attempts[company.path] = (
                    attempts,
                    locked_until,
                )
                self._password_var.set("")
                self._password_entry.focus_set()
                return

            self._failed_attempts.pop(company.path, None)
            db.set_current_user(user)
            self.store.remember_username(company.path, username)
            if user.get("role") == "admin" and not db.has_company_recovery_key():
                self._create_recovery_key()
            self.on_authenticated(user)
        except Exception as exc:
            db.set_current_user(None)
            self._status_var.set(f"Unable to open this company: {exc}")
        finally:
            if self.winfo_exists():
                self._sign_in_button.configure(state=tk.NORMAL)

    def _setup_first_admin(self, company: CompanyFile) -> None:
        dialog = AdminSetupDialog(self, company.name)
        self.wait_window(dialog)
        if not dialog.result:
            self._status_var.set(
                "Administrator setup is required before this company can open."
            )
            return
        username, display_name, password = dialog.result
        user_id = db.create_user(
            username,
            display_name,
            password,
            role="admin",
            company_access=str(company.company_id),
        )
        if not user_id:
            self._status_var.set("Could not create the administrator account.")
            return
        self._username_var.set(username)
        self._password_var.set("")
        self.store.remember_username(company.path, username)
        self._create_recovery_key()
        self._status_var.set("Administrator created. Enter the password to sign in.")
        self._password_entry.focus_set()

    def _create_recovery_key(self) -> None:
        recovery_key = db.generate_recovery_key()
        db.set_company_recovery_key(recovery_key)
        RecoveryKeyDialog(self, recovery_key)

    def _forgot_password(self) -> None:
        company = self._selected_company()
        if company is None:
            self._status_var.set("Select a company first.")
            return
        try:
            self._prepare_company(company)
        except Exception as exc:
            self._status_var.set(f"Unable to open this company: {exc}")
            return
        if not db.has_company_recovery_key():
            messagebox.showinfo(
                "Password recovery",
                "This company does not have a recovery key yet. Ask another "
                "administrator to reset your password from User Management.",
                parent=self,
            )
            return
        dialog = PasswordResetDialog(
            self,
            initial_username=self._username_var.get().strip(),
        )
        self.wait_window(dialog)
        if dialog.reset_username:
            self._username_var.set(dialog.reset_username)
            self._password_var.set("")
            self._status_var.set(
                "Password reset complete. Sign in with the new password."
            )
            self._password_entry.focus_set()

    def _create_company(self) -> None:
        dialog = CreateCompanyDialog(self, self.store)
        self.wait_window(dialog)
        if dialog.created:
            self.refresh_companies(select_path=dialog.created.path)
            self._username_var.set(dialog.admin_username)
            self._password_entry.focus_set()

    def _open_company_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Open company file",
            filetypes=[
                ("Voucher company database", "*.db"),
                ("All files", "*.*"),
            ],
            parent=self,
        )
        if not selected:
            return
        record = self.store.inspect_database(selected)
        if not record:
            messagebox.showerror(
                "Invalid company file",
                "The selected file is not a valid Voucher Manager database.",
                parent=self,
            )
            return
        conn = None
        try:
            import sqlite3

            conn = sqlite3.connect(record.path)
            company_count = conn.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
        finally:
            if conn is not None:
                conn.close()
        if company_count != 1:
            messagebox.showerror(
                "Consolidated database",
                "This file contains multiple companies. Use the migrated "
                "one-company files shown in the company list.",
                parent=self,
            )
            return
        registered = self.store.register(
            record.path,
            record.name,
            record.company_id,
        )
        self.refresh_companies(select_path=registered.path)


class AdminSetupDialog(tk.Toplevel):
    """Require creation of the first administrator for an unprotected file."""

    def __init__(self, parent: tk.Misc, company_name: str) -> None:
        super().__init__(parent)
        self.result: tuple[str, str, str] | None = None
        self.title("Secure company setup")
        self.geometry("470x470")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._username = tk.StringVar(value="admin")
        self._display_name = tk.StringVar(value="Administrator")
        self._password = tk.StringVar()
        self._confirm = tk.StringVar()
        self._build(company_name)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._center(parent)

    def _build(self, company_name: str) -> None:
        content = ttk.Frame(self, padding=28)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Protect this company",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                f"{company_name} has no users. Create its first administrator. "
                "The accounting workspace remains locked until this is complete."
            ),
            wraplength=400,
            bootstyle="secondary",
        ).pack(anchor="w", pady=(5, 20))
        for label, variable, show in (
            ("Username", self._username, ""),
            ("Display name", self._display_name, ""),
            ("Password", self._password, "•"),
            ("Confirm password", self._confirm, "•"),
        ):
            ttk.Label(content, text=label).pack(anchor="w", pady=(7, 3))
            ttk.Entry(
                content,
                textvariable=variable,
                show=show,
            ).pack(fill=tk.X, ipady=4)
        ttk.Label(
            content,
            text="Use at least 8 characters and do not use numbers only.",
            bootstyle="secondary",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(5, 16))
        ttk.Button(
            content,
            text="Create administrator",
            command=self._save,
            bootstyle="success",
        ).pack(fill=tk.X, ipady=5)

    def _save(self) -> None:
        username = self._username.get().strip().lower()
        display_name = self._display_name.get().strip()
        password = self._password.get()
        if not username or not display_name:
            messagebox.showwarning(
                "Required fields",
                "Username and display name are required.",
                parent=self,
            )
            return
        valid, message = db.validate_new_password(password)
        if not valid:
            messagebox.showwarning("Weak password", message, parent=self)
            return
        if password != self._confirm.get():
            messagebox.showwarning(
                "Passwords do not match",
                "Enter the same password in both password fields.",
                parent=self,
            )
            return
        self.result = (username, display_name, password)
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (
            parent.winfo_width() - self.winfo_width()
        ) // 2
        y = parent.winfo_rooty() + (
            parent.winfo_height() - self.winfo_height()
        ) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")


class PasswordResetDialog(tk.Toplevel):
    """Reset an account using the company's offline recovery key."""

    def __init__(self, parent: tk.Misc, initial_username: str = "") -> None:
        super().__init__(parent)
        self.reset_username = ""
        self.title("Reset password")
        self.geometry("470x455")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._username = tk.StringVar(value=initial_username)
        self._recovery = tk.StringVar()
        self._password = tk.StringVar()
        self._confirm = tk.StringVar()
        self._build()
        self._center(parent)

    def _build(self) -> None:
        content = ttk.Frame(self, padding=28)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Reset password",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "Enter the recovery key saved by your company administrator. "
                "No password or recovery key is stored in readable form."
            ),
            wraplength=400,
            bootstyle="secondary",
        ).pack(anchor="w", pady=(5, 18))
        for label, variable, show in (
            ("Username", self._username, ""),
            ("Company recovery key", self._recovery, ""),
            ("New password", self._password, "•"),
            ("Confirm new password", self._confirm, "•"),
        ):
            ttk.Label(content, text=label).pack(anchor="w", pady=(6, 3))
            ttk.Entry(
                content,
                textvariable=variable,
                show=show,
            ).pack(fill=tk.X, ipady=4)
        ttk.Button(
            content,
            text="Reset password",
            command=self._reset,
            bootstyle="success",
        ).pack(fill=tk.X, ipady=5, pady=(18, 0))

    def _reset(self) -> None:
        username = self._username.get().strip().lower()
        password = self._password.get()
        if not username or not self._recovery.get().strip():
            messagebox.showwarning(
                "Required fields",
                "Username and recovery key are required.",
                parent=self,
            )
            return
        if password != self._confirm.get():
            messagebox.showwarning(
                "Passwords do not match",
                "Enter the same new password twice.",
                parent=self,
            )
            return
        try:
            reset = db.reset_user_password_with_recovery(
                username,
                self._recovery.get().strip(),
                password,
            )
        except ValueError as exc:
            messagebox.showwarning("Invalid password", str(exc), parent=self)
            return
        if not reset:
            messagebox.showerror(
                "Reset failed",
                "The username or recovery key is incorrect.",
                parent=self,
            )
            return
        self.reset_username = username
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (
            parent.winfo_width() - self.winfo_width()
        ) // 2
        y = parent.winfo_rooty() + (
            parent.winfo_height() - self.winfo_height()
        ) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")


class RecoveryKeyDialog(tk.Toplevel):
    """Show a newly generated recovery key exactly when it is created."""

    def __init__(self, parent: tk.Misc, recovery_key: str) -> None:
        super().__init__(parent)
        self.title("Save recovery key")
        self.geometry("520x310")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._confirmed = tk.BooleanVar(value=False)
        content = ttk.Frame(self, padding=28)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Save your company recovery key",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "Store this key securely outside this computer. It is required "
                "to reset a forgotten password and cannot be displayed again."
            ),
            wraplength=450,
            bootstyle="secondary",
        ).pack(anchor="w", pady=(6, 18))
        key_var = tk.StringVar(value=recovery_key)
        entry = ttk.Entry(
            content,
            textvariable=key_var,
            state="readonly",
            justify="center",
            font=("Consolas", 12, "bold"),
        )
        entry.pack(fill=tk.X, ipady=7)
        ttk.Checkbutton(
            content,
            text="I have saved this recovery key securely",
            variable=self._confirmed,
            command=lambda: button.configure(
                state=tk.NORMAL if self._confirmed.get() else tk.DISABLED
            ),
            bootstyle="success",
        ).pack(anchor="w", pady=(18, 12))
        button = ttk.Button(
            content,
            text="Continue",
            command=self.destroy,
            state=tk.DISABLED,
            bootstyle="success",
        )
        button.pack(fill=tk.X)
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.update_idletasks()
        x = parent.winfo_rootx() + (
            parent.winfo_width() - self.winfo_width()
        ) // 2
        y = parent.winfo_rooty() + (
            parent.winfo_height() - self.winfo_height()
        ) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.wait_window(self)


class CreateCompanyDialog(tk.Toplevel):
    """Create a new one-company database with an administrator account."""

    def __init__(self, parent: tk.Misc, store: CompanyStore) -> None:
        super().__init__(parent)
        self.store = store
        self.created: CompanyFile | None = None
        self.admin_username = ""
        self.title("Create company")
        self.geometry("500x540")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._company = tk.StringVar()
        self._username = tk.StringVar(value="admin")
        self._display_name = tk.StringVar(value="Administrator")
        self._password = tk.StringVar()
        self._confirm = tk.StringVar()
        self._build()
        self._center(parent)

    def _build(self) -> None:
        content = ttk.Frame(self, padding=28)
        content.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            content,
            text="Create a company file",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            content,
            text=(
                "This company will have its own database, attachments, backups, "
                "users, and accounting records."
            ),
            wraplength=420,
            bootstyle="secondary",
        ).pack(anchor="w", pady=(5, 18))
        for label, variable, show in (
            ("Company name", self._company, ""),
            ("Administrator username", self._username, ""),
            ("Administrator display name", self._display_name, ""),
            ("Password", self._password, "•"),
            ("Confirm password", self._confirm, "•"),
        ):
            ttk.Label(content, text=label).pack(anchor="w", pady=(6, 3))
            ttk.Entry(
                content,
                textvariable=variable,
                show=show,
            ).pack(fill=tk.X, ipady=4)
        ttk.Button(
            content,
            text="Create company",
            command=self._create,
            bootstyle="success",
        ).pack(fill=tk.X, ipady=6, pady=(20, 0))

    def _create(self) -> None:
        company_name = self._company.get().strip()
        username = self._username.get().strip().lower()
        display_name = self._display_name.get().strip()
        password = self._password.get()
        if not company_name or not username or not display_name:
            messagebox.showwarning(
                "Required fields",
                "Company name, username, and display name are required.",
                parent=self,
            )
            return
        valid, message = db.validate_new_password(password)
        if not valid:
            messagebox.showwarning("Weak password", message, parent=self)
            return
        if password != self._confirm.get():
            messagebox.showwarning(
                "Passwords do not match",
                "Enter the same password in both password fields.",
                parent=self,
            )
            return

        path = self.store.company_path(company_name)
        try:
            db.configure_database(str(path))
            db.init_db()
            db.save_company(1, {"name": company_name})
            user_id = db.create_user(
                username,
                display_name,
                password,
                role="admin",
                company_access="1",
            )
            if not user_id:
                raise RuntimeError("Could not create administrator account.")
            recovery_key = db.generate_recovery_key()
            db.set_company_recovery_key(recovery_key)
            self.created = self.store.register(
                str(path),
                company_name,
                company_id=1,
                last_username=username,
            )
            self.admin_username = username
        except Exception as exc:
            messagebox.showerror(
                "Company creation failed",
                str(exc),
                parent=self,
            )
            return

        RecoveryKeyDialog(self, recovery_key)
        self.destroy()

    def _center(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        x = parent.winfo_rootx() + (
            parent.winfo_width() - self.winfo_width()
        ) // 2
        y = parent.winfo_rooty() + (
            parent.winfo_height() - self.winfo_height()
        ) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
