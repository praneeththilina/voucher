"""
Unit tests for voucher audit logging and activity history.
"""

import unittest
import os
import tempfile
import shutil
import database as db


class TestAuditLog(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_test.db")
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

    def test_audit_log_creation_and_retrieval(self):
        v_data = {
            "paid_to": "Audit Test Payee",
            "cash_given_by": "Manager",
            "spent_by": "Audit Test Payee",
            "prepared_by": "Accountant A",
            "approved_by": "Director B",
            "bill_status": "Pending",
            "payment_method": "Cash",
        }
        items = [{"description": "Office Supplies", "category": "Stationery", "amount": 1250.0}]

        vid = db.create_voucher(v_data, items)
        self.assertIsNotNone(vid)

        logs = db.get_audit_logs(vid)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action_type"], "Created")
        self.assertEqual(logs[0]["actor"], "Accountant A")
        self.assertIn("Audit Test Payee", logs[0]["details"])

    def test_audit_log_update(self):
        v_data = {
            "date": "2026-09-26",
            "paid_to": "Original Payee",
            "cash_given_by": "Manager",
            "prepared_by": "User1",
        }
        items = [{"description": "Item 1", "amount": 100.0}]
        vid = db.create_voucher(v_data, items)

        v_data["paid_to"] = "Updated Payee"
        v_data["prepared_by"] = "User2"
        db.update_voucher(vid, v_data, items)

        logs = db.get_audit_logs(vid)
        self.assertEqual(len(logs), 2)
        # Newest first
        self.assertEqual(logs[0]["action_type"], "Updated")
        self.assertEqual(logs[0]["actor"], "User2")
        self.assertIn("Updated Payee", logs[0]["details"])

    def test_audit_log_cancel_and_restore(self):
        v_data = {
            "paid_to": "Test Payee",
            "cash_given_by": "Manager",
        }
        items = [{"description": "Item", "amount": 500.0}]
        vid = db.create_voucher(v_data, items)

        db.cancel_voucher(vid, actor="AdminX")
        logs = db.get_audit_logs(vid)
        self.assertEqual(logs[0]["action_type"], "Cancelled")
        self.assertEqual(logs[0]["actor"], "AdminX")

        db.restore_voucher(vid, actor="AdminY")
        logs = db.get_audit_logs(vid)
        self.assertEqual(logs[0]["action_type"], "Restored")
        self.assertEqual(logs[0]["actor"], "AdminY")

    def test_audit_log_mark_printed(self):
        v_data = {
            "paid_to": "Print Payee",
            "cash_given_by": "Manager",
        }
        items = [{"description": "Print Item", "amount": 250.0}]
        vid = db.create_voucher(v_data, items)

        db.mark_as_printed([vid], actor="PrinterUser")
        logs = db.get_audit_logs(vid)
        self.assertEqual(logs[0]["action_type"], "Printed")
        self.assertEqual(logs[0]["actor"], "PrinterUser")

    def test_audit_log_duplication(self):
        v_data = {
            "paid_to": "Source Payee",
            "cash_given_by": "Manager",
            "prepared_by": "Clerk",
        }
        items = [{"description": "Original Item", "amount": 300.0}]
        source_id = db.create_voucher(v_data, items)

        dup_id = db.duplicate_voucher(source_id)
        self.assertIsNotNone(dup_id)

        dup_logs = db.get_audit_logs(dup_id)
        # Should have Created and Duplicated audit logs
        action_types = [l["action_type"] for l in dup_logs]
        self.assertIn("Duplicated", action_types)
        self.assertIn("Created", action_types)

    def test_audit_log_bill_status_batch(self):
        v_data = {
            "paid_to": "Batch Payee",
            "cash_given_by": "Manager",
        }
        items = [{"description": "Item", "amount": 100.0}]
        v1 = db.create_voucher(v_data, items)
        v2 = db.create_voucher(v_data, items)

        db.update_bill_status_batch([v1, v2], "Received", actor="Accountant")

        l1 = db.get_audit_logs(v1)
        l2 = db.get_audit_logs(v2)

        self.assertEqual(l1[0]["action_type"], "Bill Status Changed")
        self.assertEqual(l1[0]["actor"], "Accountant")
        self.assertEqual(l2[0]["action_type"], "Bill Status Changed")
        self.assertEqual(l2[0]["actor"], "Accountant")


if __name__ == "__main__":
    unittest.main()
