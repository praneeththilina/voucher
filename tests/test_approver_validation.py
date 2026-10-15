"""Unit tests for approver name and PIN input validation in database.py."""
import unittest
import os
import tempfile
import database as db


class TestApproverValidation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vouchers.db")
        db.configure_database(self.db_path)
        db.init_db()

    def tearDown(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_add_approver_valid(self):
        app_id = db.add_approver("Alice Manager", "12345678", company_id=1, approval_level=1)
        self.assertIsNotNone(app_id)
        self.assertTrue(db.verify_approver_pin(app_id, "12345678"))

    def test_add_approver_rejects_empty_or_whitespace_name(self):
        with self.assertRaises(ValueError):
            db.add_approver("", "12345678")

        with self.assertRaises(ValueError):
            db.add_approver("   ", "12345678")

        with self.assertRaises(ValueError):
            db.add_approver(None, "12345678")

    def test_add_approver_rejects_empty_or_whitespace_pin(self):
        with self.assertRaises(ValueError):
            db.add_approver("Bob Approver", "")

        with self.assertRaises(ValueError):
            db.add_approver("Bob Approver", "   ")

        with self.assertRaises(ValueError):
            db.add_approver("Bob Approver", None)

    def test_update_approver_valid(self):
        app_id = db.add_approver("Charlie Director", "87654321")
        self.assertIsNotNone(app_id)

        res = db.update_approver(app_id, name="Charlie Senior Director", pin="11223344")
        self.assertTrue(res)
        self.assertTrue(db.verify_approver_pin(app_id, "11223344"))

    def test_update_approver_rejects_empty_or_whitespace_name(self):
        app_id = db.add_approver("Diana Exec", "99887766")

        with self.assertRaises(ValueError):
            db.update_approver(app_id, name="")

        with self.assertRaises(ValueError):
            db.update_approver(app_id, name="   ")

    def test_update_approver_rejects_empty_or_whitespace_pin(self):
        app_id = db.add_approver("Edward Exec", "55443322")

        with self.assertRaises(ValueError):
            db.update_approver(app_id, pin="")

        with self.assertRaises(ValueError):
            db.update_approver(app_id, pin="   ")


if __name__ == "__main__":
    unittest.main()
