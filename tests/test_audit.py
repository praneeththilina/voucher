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

    def test_get_company_audit_logs_and_filtering(self):
        v_data = {
            "paid_to": "Company Audit Payee",
            "cash_given_by": "Manager",
            "prepared_by": "Auditor User",
        }
        items = [{"description": "Item", "amount": 150.0}]
        v1 = db.create_voucher(v_data, items, company_id=1)

        v_data2 = {
            "paid_to": "=Formula Injection Payee",
            "cash_given_by": "Manager",
            "prepared_by": "Clerk",
        }
        v2 = db.create_voucher(v_data2, items, company_id=1)
        db.cancel_voucher(v2, actor="AdminZ")

        # Get all company audit logs for company 1
        c_logs = db.get_company_audit_logs(company_id=1)
        self.assertGreaterEqual(len(c_logs), 3)  # v1 created, v2 created, v2 cancelled

        # Filter by action_type 'Cancelled'
        cancelled_logs = db.get_company_audit_logs(company_id=1, action_type_filter="Cancelled")
        self.assertTrue(all(l["action_type"] == "Cancelled" for l in cancelled_logs))
        self.assertIn("AdminZ", [l["actor"] for l in cancelled_logs])

        # Filter by date_filter 'Today'
        today_logs = db.get_company_audit_logs(company_id=1, date_filter="Today")
        self.assertGreaterEqual(len(today_logs), 1)

    def test_export_audit_logs_to_csv_single_voucher(self):
        v_data = {
            "paid_to": "=Formula Vendor",
            "cash_given_by": "Manager",
            "prepared_by": "Test Accountant",
        }
        items = [{"description": "Test Line Item", "amount": 500.0}]
        vid = db.create_voucher(v_data, items)
        db.mark_as_printed([vid], actor="Print User")

        csv_path = os.path.join(self.test_dir, "voucher_audit.csv")
        db.export_audit_logs_to_csv(csv_path, voucher_id=vid)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("AUDIT TRAIL REPORT", content)
        self.assertIn("Event ID", content)
        self.assertIn("Action Type", content)
        self.assertIn("Test Accountant", content)
        # Verify DDE formula sanitization
        self.assertIn("'=Formula Vendor", content)

    def test_export_audit_logs_to_csv_company_wide(self):
        v_data = {
            "paid_to": "General Vendor",
            "cash_given_by": "Manager",
            "prepared_by": "User A",
        }
        items = [{"description": "Office Item", "amount": 300.0}]
        vid = db.create_voucher(v_data, items, company_id=1)

        csv_path = os.path.join(self.test_dir, "company_audit.csv")
        db.export_audit_logs_to_csv(csv_path, company_id=1, action_type_filter="All", date_filter="All Time")

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("SYSTEM AUDIT LOG & ACTIVITY TRAIL REPORT", content)
        self.assertIn("General Vendor", content)
        self.assertIn("User A", content)


if __name__ == "__main__":
    unittest.main()
