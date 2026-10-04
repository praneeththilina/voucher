"""
Unit tests for MS Office style Dashboard Ribbon Display Options (Always Show, Auto-Hide, Hide).
"""

import os
import unittest
import tempfile
import tkinter as tk
import ttkbootstrap as ttk

import database as db
from ui.main_window import MainWindow
from tests.test_widgets import get_test_root


class TestDashboardRibbon(unittest.TestCase):

    def setUp(self):
        """Set up isolated test database in a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vouchers.db")
        self.attachments_dir = os.path.join(self.temp_dir, "attachments")
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self._orig_db_path = db.DB_PATH
        self._orig_attachments_dir = db.ATTACHMENTS_DIR
        self._orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        db.init_db()

    def tearDown(self):
        """Restore original database paths."""
        db.DB_PATH = self._orig_db_path
        db.ATTACHMENTS_DIR = self._orig_attachments_dir
        db.BACKUP_DIR = self._orig_backup_dir

    def test_ribbon_mode_persistence(self):
        """Test reading and writing ribbon mode to app_settings table."""
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode", "always_show"), "always_show")

        db.set_app_setting("dashboard_ribbon_mode", "auto_hide")
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode"), "auto_hide")

        db.set_app_setting("dashboard_ribbon_mode", "hide")
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode"), "hide")

        db.set_app_setting("dashboard_ribbon_mode", "always_show")
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode"), "always_show")

    def test_ribbon_modes_in_main_window(self):
        """Test Always Show, Auto-Hide, and Hide state transitions in MainWindow."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Start with default always_show
        db.set_app_setting("dashboard_ribbon_mode", "always_show")
        app = MainWindow(root)

        self.assertEqual(app._ribbon_mode, "always_show")
        self.assertFalse(app._is_temporarily_revealed)
        self.assertIn(app._stats_frame, root.pack_slaves())
        self.assertNotIn(app._stats_collapsed_strip, root.pack_slaves())

        # Switch to Auto-Hide
        app._set_ribbon_mode("auto_hide", notify=False)
        self.assertEqual(app._ribbon_mode, "auto_hide")
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode"), "auto_hide")
        self.assertNotIn(app._stats_frame, root.pack_slaves())
        self.assertIn(app._stats_collapsed_strip, root.pack_slaves())

        # Test Reveal in Auto-Hide
        app._reveal_ribbon()
        self.assertTrue(app._is_temporarily_revealed)
        self.assertIn(app._stats_frame, root.pack_slaves())
        self.assertNotIn(app._stats_collapsed_strip, root.pack_slaves())

        # Test Collapse in Auto-Hide
        app._collapse_ribbon()
        self.assertFalse(app._is_temporarily_revealed)
        self.assertNotIn(app._stats_frame, root.pack_slaves())
        self.assertIn(app._stats_collapsed_strip, root.pack_slaves())

        # Switch to Hide
        app._set_ribbon_mode("hide", notify=False)
        self.assertEqual(app._ribbon_mode, "hide")
        self.assertEqual(db.get_app_setting("dashboard_ribbon_mode"), "hide")
        self.assertNotIn(app._stats_frame, root.pack_slaves())
        self.assertNotIn(app._stats_collapsed_strip, root.pack_slaves())

        # Test Ctrl+F1 shortcut toggle
        app._shortcut_toggle_ribbon()
        self.assertEqual(app._ribbon_mode, "always_show")
        self.assertIn(app._stats_frame, root.pack_slaves())

        # Toggle again from always_show -> auto_hide
        app._shortcut_toggle_ribbon()
        self.assertEqual(app._ribbon_mode, "auto_hide")

        # Cleanup
        if getattr(app, "_auto_hide_timer", None):
            try:
                root.after_cancel(app._auto_hide_timer)
            except Exception:
                pass
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
