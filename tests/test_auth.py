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

    def test_user_pin_validation(self):
        """Verify create_user and update_user reject empty or whitespace-only PINs."""
        # Empty PIN or username on creation should raise ValueError
        with self.assertRaises(ValueError):
            db.create_user("john_doe", "John Doe", "")
        with self.assertRaises(ValueError):
            db.create_user("john_doe", "John Doe", "   ")
        with self.assertRaises(ValueError):
            db.create_user("john_doe", "John Doe", None)
        with self.assertRaises(ValueError):
            db.create_user("", "John Doe", "1234")

        # Valid user creation and authentication
        uid = db.create_user("john_doe", "John Doe", "1234")
        self.assertIsNotNone(uid)
        authenticated = db.authenticate_user("john_doe", "1234")
        self.assertIsNotNone(authenticated)

        # Resetting PIN to empty or whitespace should raise ValueError
        with self.assertRaises(ValueError):
            db.update_user(uid, pin="")
        with self.assertRaises(ValueError):
            db.update_user(uid, pin="   ")

        # Updating PIN with valid value should succeed
        self.assertTrue(db.update_user(uid, pin="5678"))
        self.assertIsNotNone(db.authenticate_user("john_doe", "5678"))

    def test_approver_pin_validation(self):
        """Verify add_approver and update_approver reject empty or whitespace-only PINs/names."""
        # Empty name or PIN on approver creation should raise ValueError
        with self.assertRaises(ValueError):
            db.add_approver("Manager", "")
        with self.assertRaises(ValueError):
            db.add_approver("Manager", "   ")
        with self.assertRaises(ValueError):
            db.add_approver("Manager", None)
        with self.assertRaises(ValueError):
            db.add_approver("", "1234")

        # Valid approver creation and PIN verification
        aid = db.add_approver("Manager", "1234")
        self.assertIsNotNone(aid)
        self.assertTrue(db.verify_approver_pin(aid, "1234"))

        # Updating approver PIN to empty or whitespace should raise ValueError
        with self.assertRaises(ValueError):
            db.update_approver(aid, pin="")
        with self.assertRaises(ValueError):
            db.update_approver(aid, pin="   ")

        # Updating approver PIN with valid value should succeed
        self.assertTrue(db.update_approver(aid, pin="9999"))
        self.assertTrue(db.verify_approver_pin(aid, "9999"))


if __name__ == "__main__":
    unittest.main()
