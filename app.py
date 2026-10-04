"""
Application class for the Voucher Printing Tool.
Sets up the main window with ttkbootstrap theming.
"""

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

import database as db
from ui.main_window import MainWindow


class VoucherApp:
    """Main application class."""

    APP_VERSION = "2.0.0"
    APP_TITLE = f"Voucher Manager v{APP_VERSION} — SME Payment Voucher Tool"
    APP_SIZE = "1100x750"

    def __init__(self):
        # Initialize database
        db.init_db()

        # Create themed root window
        self.root = ttk.Window(
            title=self.APP_TITLE,
            themename="cosmo",  # Clean, professional theme
            size=(1100, 750),
            minsize=(800, 500),
        )

        # Set application window and taskbar icon
        self._set_app_icon()

        # Center on screen as fallback
        self.root.place_window_center()

        # Always open as maximized screen by default
        self._maximize_window()

        # Build UI
        self.main_window = MainWindow(self.root)

        # Re-assert maximized state after widget hierarchy and styling settle
        self.root.after(50, self._maximize_window)

    def _set_app_icon(self):
        """Set the window icon for titlebar and Windows taskbar."""
        import os
        import sys
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        # Check standard and _internal locations
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
                    from PIL import ImageTk, Image
                    icon_img = ImageTk.PhotoImage(Image.open(png))
                    self.root.iconphoto(True, icon_img)
                    self._icon_img_ref = icon_img
                    break
                except Exception:
                    pass

    def _maximize_window(self):
        """Maximize the root window to fully fit the display screen."""
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

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()
