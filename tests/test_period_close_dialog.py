"""Unit tests for PeriodCloseDialog UX enhancements."""

import tempfile
import tkinter as tk
import unittest
import ttkbootstrap as ttk

import database as db
from ui.period_close_dialog import PeriodCloseDialog


_shared_root = None


def get_test_root():
    global _shared_root
    try:
        exists = _shared_root is not None and bool(_shared_root.winfo_exists())
    except Exception:
        exists = False
        _shared_root = None

    if not exists:
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
            ttk.Style(theme="minty-light")
        except Exception:
            _shared_root = None
    return _shared_root


class TestPeriodCloseDialog(unittest.TestCase):
    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.set_current_user(None)
        db.DB_PATH = self.db_path
        db.init_db()
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass
        db.DB_PATH = self.orig_db_path

    def test_period_close_dialog_initialization_and_escape(self):
        self.root.deiconify()
        self.dialog = PeriodCloseDialog(self.root, company_id=1)
        self.dialog.deiconify()
        self.dialog.update()

        # Check Escape binding
        bindings = self.dialog.bind("<Escape>")
        self.assertTrue(bindings, "Escape key should be bound to dismiss dialog")

        # Check that Reopen Books button is initially disabled if books are open
        self.assertEqual(str(self.dialog._unlock_button["state"]), tk.DISABLED)

        # Trigger Escape key press on focused child widget
        self.dialog._date_entry.focus_force()
        self.dialog.update()
        focused = self.dialog.focus_get() or self.dialog
        focused.event_generate("<Key-Escape>")
        self.dialog.update()
        self.assertFalse(self.dialog.winfo_exists(), "Dialog should be destroyed after pressing Escape")
