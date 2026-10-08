"""
Additional tests for admin password utilities in database.py
"""

import unittest
import os
import tempfile
import shutil

import database as db


class TestRetiredMasterPassword(unittest.TestCase):

    def test_global_master_password_is_disabled(self):
        db.set_current_user(None)
        self.assertFalse(db.verify_admin_password("12345"))
        with self.assertRaises(RuntimeError):
            db.set_admin_password("AnyGlobalPassword1!")

class TestSecureUserAuthentication(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "secure_auth.db")
        self.orig_db_path = db.DB_PATH
        self.orig_attachments_dir = db.ATTACHMENTS_DIR
        self.orig_backup_dir = db.BACKUP_DIR
        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = os.path.join(self.test_dir, "attachments")
        db.BACKUP_DIR = os.path.join(self.test_dir, "backups")
        db.init_db()

    def tearDown(self):
        db.set_current_user(None)
        db.DB_PATH = self.orig_db_path
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        db.BACKUP_DIR = self.orig_backup_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_permissions_deny_unauthenticated_sessions(self):
        self.assertFalse(db.has_permission("view_reports"))
        self.assertFalse(db.get_current_user())

    def test_admin_verifier_requires_current_admin_password(self):
        admin_id = db.create_user(
            "admin",
            "Administrator",
            "StrongPass1!",
            role="admin",
        )
        self.assertIsNotNone(admin_id)
        self.assertFalse(
            db.verify_admin_pin_or_password("StrongPass1!")
        )
        user = db.authenticate_user("admin", "StrongPass1!")
        db.set_current_user(user)
        self.assertTrue(
            db.verify_admin_pin_or_password("StrongPass1!")
        )
        self.assertFalse(db.verify_admin_pin_or_password("12345"))
    def test_recovery_key_resets_password(self):
        user_id = db.create_user(
            "owner",
            "Owner",
            "OriginalPass1!",
            role="admin",
        )
        self.assertIsNotNone(user_id)
        recovery_key = db.generate_recovery_key()
        db.set_company_recovery_key(recovery_key)
        self.assertTrue(db.has_company_recovery_key())
        self.assertFalse(db.verify_company_recovery_key("wrong-key"))
        self.assertTrue(db.verify_company_recovery_key(recovery_key))
        self.assertTrue(
            db.reset_user_password_with_recovery(
                "owner",
                recovery_key,
                "ReplacementPass2!",
            )
        )
        self.assertIsNone(
            db.authenticate_user("owner", "OriginalPass1!")
        )
        self.assertIsNotNone(
            db.authenticate_user("owner", "ReplacementPass2!")
        )

    def test_weak_passwords_are_rejected(self):
        self.assertIsNone(
            db.create_user("weak", "Weak User", "1234", role="viewer")
        )
        valid, message = db.validate_new_password("12345678")
        self.assertFalse(valid)
        self.assertIn("only numbers", message)

    def test_final_admin_cannot_be_disabled_or_deleted(self):
        admin_id = db.create_user(
            "admin",
            "Administrator",
            "StrongPass1!",
            role="admin",
        )
        user = db.authenticate_user("admin", "StrongPass1!")
        db.set_current_user(user)
        self.assertFalse(db.update_user(admin_id, is_active=False))
        self.assertFalse(db.delete_user(admin_id))

if __name__ == "__main__":
    unittest.main()
