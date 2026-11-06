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

    def test_verify_pin_hash_rejects_whitespace_inputs(self):
        user_id = db.create_user(
            "secuser",
            "Security User",
            "SecurePass123!",
            role="admin",
        )
        self.assertIsNotNone(user_id)
        # Test that whitespace-only candidate passwords fail
        self.assertFalse(db.verify_user_pin(user_id, "   "))
        self.assertFalse(db.verify_user_pin(user_id, "\t\n"))
        self.assertIsNone(db.authenticate_user("secuser", "   "))
        self.assertIsNone(db.authenticate_user(None, "SecurePass123!"))
        self.assertIsNone(db.authenticate_user("secuser", None))
        self.assertIsNone(db.authenticate_user("   ", "SecurePass123!"))
        self.assertFalse(db.verify_user_pin(user_id, None))
        self.assertFalse(db._verify_pin_hash("   ", "pbkdf2:sha256:100000$00$00"))
        self.assertFalse(db._verify_pin_hash("validpass", "   "))
        self.assertFalse(db._verify_pin_hash("   ", "   "))

    def test_authenticate_user_upgrades_legacy_hash_to_pbkdf2(self):
        user_id = db.create_user(
            "legacyuser",
            "Legacy User",
            "ValidPass123!",
            role="data_entry",
        )
        self.assertIsNotNone(user_id)
        # Manually set a legacy plain-text password format
        conn = db.get_connection()
        conn.execute("UPDATE users SET pin_hash = ? WHERE id = ?", ("ValidPass123!", user_id))
        conn.commit()
        conn.close()

        # Verify before authentication it has legacy format (not PBKDF2)
        full_user_before = db.get_user_full(user_id)
        self.assertEqual(full_user_before["pin_hash"], "ValidPass123!")
        self.assertFalse(full_user_before["pin_hash"].startswith("pbkdf2:sha256:"))

        # Authenticate successfully
        auth_user = db.authenticate_user("legacyuser", "ValidPass123!")
        self.assertIsNotNone(auth_user)
        self.assertEqual(auth_user["id"], user_id)

        # Verify after authentication it has been upgraded to PBKDF2 format
        full_user_after = db.get_user_full(user_id)
        self.assertTrue(full_user_after["pin_hash"].startswith("pbkdf2:sha256:"))
        self.assertTrue(db.verify_user_pin(user_id, "ValidPass123!"))

if __name__ == "__main__":
    unittest.main()
