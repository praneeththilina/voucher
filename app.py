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

    APP_VERSION = "1.1.7"
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
            minsize=(900, 600),
        )

        # Center on screen
        self.root.place_window_center()

        # Build UI
        self.main_window = MainWindow(self.root)

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()
