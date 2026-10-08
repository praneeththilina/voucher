"""Application lifecycle for secure company login and accounting workspace."""

from __future__ import annotations

import os
import sys
from tkinter import messagebox

import ttkbootstrap as ttk

import database as db
from company_store import CompanyStore
from ui.login_screen import LoginScreen


class VoucherApp:
    """Main application class with authentication as the hard entry gate."""

    APP_VERSION = "4.0.0"
    APP_TITLE = (
        f"Voucher Manager v{APP_VERSION} — SME Payment Voucher & Financial ERP"
    )
    LOGIN_TITLE = f"Voucher Manager v{APP_VERSION} — Sign in"

    def __init__(self) -> None:
        self.root = ttk.Window(
            title=self.LOGIN_TITLE,
            themename="minty-light",
            size=(1024, 650),
            minsize=(900, 600),
        )
        self.main_window = None
        self.login_screen = None
        self._icon_img_ref = None
        self._set_app_icon()
        self.root.place_window_center()
        self.root.protocol("WM_DELETE_WINDOW", self._exit_application)

        data_dir = os.path.dirname(db.DEFAULT_DB_PATH)
        self.company_store = CompanyStore(data_dir)
        try:
            self.company_store.migrate_legacy_database(db.DEFAULT_DB_PATH)
        except Exception as exc:
            messagebox.showerror(
                "Company migration failed",
                "The original database was not changed. Voucher Manager could "
                f"not prepare one-file-per-company databases:\n\n{exc}",
                parent=self.root,
            )
        self._show_login()

    def _show_login(self) -> None:
        """Remove all accounting widgets and show only the login gate."""
        if self.main_window is not None:
            try:
                self.main_window.prepare_for_logout()
            except Exception:
                pass
            self.main_window = None

        db.set_current_user(None)
        for child in self.root.winfo_children():
            child.destroy()

        self.root.title(self.LOGIN_TITLE)
        self.root.protocol("WM_DELETE_WINDOW", self._exit_application)
        self.root.state("normal")
        self.root.geometry("1024x650")
        self.root.minsize(900, 600)
        self.root.place_window_center()
        self.login_screen = LoginScreen(
            self.root,
            store=self.company_store,
            on_authenticated=self._open_accounting_workspace,
            on_exit=self._exit_application,
        )

    def _open_accounting_workspace(self, user: dict) -> None:
        """Construct the accounting workspace only after successful login."""
        if not user or not db.get_current_user():
            return
        if self.login_screen is not None:
            self.login_screen.destroy()
            self.login_screen = None

        self.root.title(self.APP_TITLE)
        self.root.minsize(800, 500)
        from ui.main_window import MainWindow

        self.main_window = MainWindow(
            self.root,
            on_logout=self._show_login,
        )
        self._maximize_window()
        self.root.after(50, self._maximize_window)

    def _exit_application(self) -> None:
        """Clear the authenticated session and close the application."""
        db.set_current_user(None)
        try:
            self.root.destroy()
        except Exception:
            pass

    def _set_app_icon(self) -> None:
        """Set the window icon for titlebar and Windows taskbar."""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        ico_candidates = [
            os.path.join(base_dir, "assets", "icon.ico"),
            os.path.join(base_dir, "_internal", "assets", "icon.ico"),
        ]
        png_candidates = [
            os.path.join(base_dir, "assets", "icon.png"),
            os.path.join(base_dir, "_internal", "assets", "icon.png"),
        ]

        for ico in ico_candidates:
            if os.path.exists(ico):
                try:
                    self.root.iconbitmap(ico)
                    break
                except Exception:
                    pass

        for png in png_candidates:
            if os.path.exists(png):
                try:
                    from PIL import Image, ImageTk

                    icon_img = ImageTk.PhotoImage(Image.open(png))
                    self.root.iconphoto(True, icon_img)
                    self._icon_img_ref = icon_img
                    break
                except Exception:
                    pass

    def _maximize_window(self) -> None:
        """Maximize the authenticated accounting workspace."""
        try:
            self.root.state("zoomed")
        except Exception:
            try:
                self.root.attributes("-zoomed", True)
            except Exception:
                try:
                    self.root.wm_attributes("-zoomed", 1)
                except Exception:
                    pass

    def run(self) -> None:
        """Start the application main loop."""
        self.root.mainloop()
