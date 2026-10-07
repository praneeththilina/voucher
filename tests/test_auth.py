"""
Additional tests for admin password utilities in database.py
"""

import unittest
import os
import tempfile
import shutil

import database as db


class TestAdminPasswordUtilities(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_pwd_test.db")
        self.attachments_dir = os.path.join(self.test_dir, "attachments")
        self.backup_dir = os.path.join(self.test_dir, "backups")

        self.orig_db_path = db.DB_PATH
        self.orig_attachments_dir = db.ATTACHMENTS_DIR
        self.orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        db.BACKUP_DIR = self.orig_backup_dir

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_password_verification(self):
        self.assertTrue(db.verify_admin_password("12345"))
        self.assertFalse(db.verify_admin_password("WrongPassword"))
        self.assertFalse(db.verify_admin_password(""))

    def test_custom_password_update(self):
        db.set_admin_password("NewSecret2026")
        self.assertTrue(db.verify_admin_password("NewSecret2026"))
        self.assertFalse(db.verify_admin_password("12345"))

        # Verify hash format stored in settings is PBKDF2
        conn = db.get_connection()
        row = conn.execute("SELECT value FROM settings WHERE key = 'admin_password_hash'").fetchone()
        conn.close()
        self.assertTrue(row["value"].startswith("pbkdf2:sha256:100000$"))

    def test_empty_password_rejection(self):
        """Verify set_admin_password rejects None, empty, or whitespace-only passwords."""
        with self.assertRaises(ValueError):
            db.set_admin_password("")
        with self.assertRaises(ValueError):
            db.set_admin_password("   ")
        with self.assertRaises(ValueError):
            db.set_admin_password(None)

    def test_legacy_sha256_transparent_migration(self):
        """Verify legacy SHA-256 hashes are verified and transparently upgraded to PBKDF2."""
        import hashlib

        legacy_pass = "LegacyPass123"
        legacy_hash = hashlib.sha256(legacy_pass.encode("utf-8")).hexdigest()

        # Manually store legacy SHA-256 hash in settings
        db.save_settings({"admin_password_hash": legacy_hash})

        # Verify password using legacy hash
        self.assertTrue(db.verify_admin_password(legacy_pass))

        # Check that hash in DB has been transparently upgraded to PBKDF2
        conn = db.get_connection()
        row = conn.execute("SELECT value FROM settings WHERE key = 'admin_password_hash'").fetchone()
        conn.close()
        self.assertTrue(row["value"].startswith("pbkdf2:sha256:100000$"))

        # Subsequent verification should still succeed with PBKDF2
        self.assertTrue(db.verify_admin_password(legacy_pass))

    def test_verify_user_pin(self):
        """Verify user PIN verification by user ID."""
        uid = db.create_user("testmanager", "Test Manager", "9876", "manager")
        self.assertIsNotNone(uid)
        self.assertTrue(db.verify_user_pin(uid, "9876"))
        self.assertFalse(db.verify_user_pin(uid, "0000"))
        self.assertFalse(db.verify_user_pin(uid, ""))
        self.assertFalse(db.verify_user_pin(99999, "9876"))


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
            import tkinter as tk
            import ttkbootstrap as ttk
            _shared_root = tk.Tk()
            _shared_root.withdraw()
            ttk.Style(theme="cosmo")
        except Exception:
            _shared_root = None
    return _shared_root


class TestUserManagementDialogUI(unittest.TestCase):
    """GUI tests for UserManagementDialog auto-selection, button states, and dynamic state updates."""

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "vouchers_user_ui_test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_user_management_dialog_autoselect_and_button_states(self):
        """Test auto-selection on load and dynamic button enabling/disabling."""
        import tkinter as tk
        from ui.user_manager import UserManagementDialog

        # Seed a user
        uid = db.create_user("alice", "Alice Smith", "1234", "manager")
        self.assertIsNotNone(uid)

        dlg = UserManagementDialog(self.root)
        try:
            # 1. On open, first user row should be auto-selected and action buttons enabled
            sel = dlg._tree.selection()
            self.assertEqual(len(sel), 1)
            self.assertEqual(str(dlg._reset_pin_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg._toggle_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg._delete_btn["state"]), tk.NORMAL)

            # 2. When selection is cleared, action buttons should be disabled
            dlg._tree.selection_remove(sel[0])
            dlg._update_button_states()
            self.assertEqual(len(dlg._tree.selection()), 0)
            self.assertEqual(str(dlg._reset_pin_btn["state"]), tk.DISABLED)
            self.assertEqual(str(dlg._toggle_btn["state"]), tk.DISABLED)
            self.assertEqual(str(dlg._delete_btn["state"]), tk.DISABLED)

            # 3. Selecting a row re-enables action buttons
            dlg._tree.selection_set(sel[0])
            dlg._update_button_states()
            self.assertEqual(str(dlg._reset_pin_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg._toggle_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg._delete_btn["state"]), tk.NORMAL)
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
