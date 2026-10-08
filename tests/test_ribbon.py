"""
Unit tests for the compact single-line Dashboard Stats Bar and Show/Hide controls.
"""

import os
import unittest
import tempfile
import tkinter as tk
import ttkbootstrap as ttk

import database as db
from ui.main_window import MainWindow
from tests.test_widgets import get_test_root


class TestDashboardStatsBar(unittest.TestCase):

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
        user_id = db.create_user(
            "testadmin",
            "Test Administrator",
            "StrongPass1!",
            role="admin",
        )
        if user_id:
            db.set_current_user(
                db.authenticate_user("testadmin", "StrongPass1!")
            )

    def tearDown(self):
        """Restore original database paths."""
        db.set_current_user(None)
        db.DB_PATH = self._orig_db_path
        db.ATTACHMENTS_DIR = self._orig_attachments_dir
        db.BACKUP_DIR = self._orig_backup_dir

    def test_main_window_rejects_unauthenticated_session(self):
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        db.set_current_user(None)
        with self.assertRaises(PermissionError):
            MainWindow(root)
    def test_stats_setting_persistence(self):
        """Test reading and writing stats visibility to app_settings table."""
        self.assertEqual(db.get_app_setting("dashboard_stats_visible", "show"), "show")

        db.set_app_setting("dashboard_stats_visible", "hide")
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "hide")

        db.set_app_setting("dashboard_stats_visible", "show")
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "show")

    def test_stats_bar_in_main_window(self):
        """Test Show and Hide transitions of the compact single-line stats bar in MainWindow."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Start with default show
        db.set_app_setting("dashboard_stats_visible", "show")
        app = MainWindow(root)

        self.assertTrue(app._stats_visible)
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Verify stat variables exist
        for key in ("total", "pending", "amount", "unprinted"):
            self.assertIn(key, app._stat_vars)

        # Hide stats bar
        app._hide_stats_bar(notify=False)
        self.assertFalse(app._stats_visible)
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "hide")
        self.assertNotIn(app._stats_bar, root.pack_slaves())

        # Show stats bar
        app._show_stats_bar(notify=False)
        self.assertTrue(app._stats_visible)
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "show")
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Test Ctrl+F1 toggle
        app._shortcut_toggle_stats()
        self.assertFalse(app._stats_visible)
        self.assertNotIn(app._stats_bar, root.pack_slaves())

        app._shortcut_toggle_stats()
        self.assertTrue(app._stats_visible)
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Cleanup children in root to prevent interference with other tests
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
