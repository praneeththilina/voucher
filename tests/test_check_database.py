"""
Unit tests for check printing database operations and business rules.
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db


class TestCheckDatabase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vouchers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Full init including base tables and Migration 22
        db.init_db()

        # Connect helper
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_22_tables_created(self):
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("bank_check_templates", tables)
        self.assertIn("checks", tables)
        self.assertIn("check_audit_log", tables)
        self.assertIn("check_signatories", tables)

        # Ensure vouchers table got check_id column
        cols = [c[1].lower() for c in self.conn.execute("PRAGMA table_info(vouchers)").fetchall()]
        self.assertIn("check_id", cols)

    def test_default_templates_seeded(self):
        templates = db.get_check_templates(company_id=1, conn=self.conn)
        self.assertTrue(len(templates) >= 2)
        names = [t["bank_name"] for t in templates]
        self.assertTrue(any("Commercial Bank" in n for n in names))
        self.assertTrue(any("Hatton National Bank" in n for n in names))

    def test_create_and_update_check_template(self):
        tmpl_id = db.create_check_template({
            "company_id": 1,
            "bank_name": "Sampath Bank PLC",
            "check_series_prefix": "SMP-",
            "check_series_start": 100,
            "page_width_mm": 210.0,
            "page_height_mm": 90.0
        }, conn=self.conn)
        self.assertIsNotNone(tmpl_id)

        tmpl = db.get_check_template_by_id(tmpl_id, conn=self.conn)
        self.assertEqual(tmpl["bank_name"], "Sampath Bank PLC")
        self.assertEqual(tmpl["check_series_prefix"], "SMP-")
        self.assertEqual(tmpl["check_series_start"], 100)

        # Update template
        ok = db.update_check_template(tmpl_id, {
            "bank_name": "Sampath Bank Updated",
            "check_series_prefix": "SMP-",
            "check_series_start": 100,
            "page_width_mm": 210.0,
            "page_height_mm": 90.0
        }, conn=self.conn)
        self.assertTrue(ok)
        tmpl_updated = db.get_check_template_by_id(tmpl_id, conn=self.conn)
        self.assertEqual(tmpl_updated["bank_name"], "Sampath Bank Updated")

    def test_check_series_auto_increment(self):
        templates = db.get_check_templates(company_id=1, conn=self.conn)
        tmpl_id = templates[0]["id"]

        next_series_1 = db.get_next_check_series(tmpl_id, conn=self.conn)
        next_num_1 = db.get_next_check_number(tmpl_id, conn=self.conn)
        self.assertEqual(next_series_1, 1)

        # Create check 1
        cid1 = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Vendor A",
            "amount": 10000.0,
            "check_series": next_series_1,
            "check_number": next_num_1,
            "status": "Draft"
        }, actor="TestUser", conn=self.conn)

        # Next should increment to 2
        next_series_2 = db.get_next_check_series(tmpl_id, conn=self.conn)
        self.assertEqual(next_series_2, 2)

        # Create check 2 with auto numbering
        cid2 = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Vendor B",
            "amount": 25000.0,
        }, actor="TestUser", conn=self.conn)
        c2 = db.get_check_by_id(cid2, conn=self.conn)
        self.assertEqual(c2["check_series"], 2)

    def test_status_transitions_and_audit_trail(self):
        templates = db.get_check_templates(company_id=1, conn=self.conn)
        tmpl_id = templates[0]["id"]

        cid = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Office Depot",
            "amount": 15000.0,
            "status": "Draft"
        }, actor="Alice", conn=self.conn)

        # Mark printed -> moves to Issued
        db.mark_check_printed(cid, actor="Bob", conn=self.conn)
        c = db.get_check_by_id(cid, conn=self.conn)
        self.assertEqual(c["status"], "Issued")
        self.assertEqual(c["printed"], 1)
        self.assertEqual(c["print_count"], 1)

        # Mark Presented
        db.update_check_status(cid, "Presented", actor="Bob", note="Deposited by payee", conn=self.conn)
        c = db.get_check_by_id(cid, conn=self.conn)
        self.assertEqual(c["status"], "Presented")

        # Mark Cleared
        db.update_check_status(cid, "Cleared", actor="Charlie", note="Bank debit confirmed", conn=self.conn)
        c = db.get_check_by_id(cid, conn=self.conn)
        self.assertEqual(c["status"], "Cleared")
        self.assertTrue(c["cleared_date"])

        # Cleared check CANNOT be voided
        ok, msg = db.void_check(cid, actor="Admin", reason="Mistake", conn=self.conn)
        self.assertFalse(ok)
        self.assertIn("cannot be voided", msg.lower())

        # Audit trail verification
        audit = db.get_check_audit_trail(cid, conn=self.conn)
        self.assertTrue(len(audit) >= 4)
        actions = [a["action"] for a in audit]
        self.assertIn("Created", actions)
        self.assertIn("Printed", actions)
        self.assertIn("Status Transition", actions)

    def test_void_and_unlinking_voucher(self):
        # Create a voucher first
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO vouchers (company_id, voucher_number, total_amount, paid_to, date, cash_given_by, spent_by, prepared_by)
            VALUES (1, 'V-TEST-01', 50000.0, 'Acme Corp', '2026-10-05', 'Cashier', 'Driver', 'Admin')
        """)
        self.conn.commit()
        vid = cursor.lastrowid

        templates = db.get_check_templates(company_id=1, conn=self.conn)
        tmpl_id = templates[0]["id"]

        cid = db.create_check({
            "company_id": 1,
            "voucher_id": vid,
            "template_id": tmpl_id,
            "payee_name": "Acme Corp",
            "amount": 50000.0,
            "status": "Issued"
        }, actor="Alice", conn=self.conn)

        # Check that voucher has check_id linked
        v_row = self.conn.execute("SELECT check_id FROM vouchers WHERE id = ?", (vid,)).fetchone()
        self.assertEqual(v_row["check_id"], cid)

        # Void check
        ok, msg = db.void_check(cid, actor="Manager", reason="Printed on wrong account", conn=self.conn)
        self.assertTrue(ok)
        c = db.get_check_by_id(cid, conn=self.conn)
        self.assertEqual(c["status"], "Voided")

        # Voucher check_id should be reset to None/NULL
        v_row_after = self.conn.execute("SELECT check_id FROM vouchers WHERE id = ?", (vid,)).fetchone()
        self.assertIsNone(v_row_after["check_id"])

    def test_record_bounce(self):
        templates = db.get_check_templates(company_id=1, conn=self.conn)
        tmpl_id = templates[0]["id"]

        cid = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Supplier Z",
            "amount": 100000.0,
            "status": "Presented"
        }, actor="Alice", conn=self.conn)

        ok = db.record_check_bounce(cid, actor="BankTeller", reason="Insufficient Funds", bounce_date="2026-10-05", conn=self.conn)
        self.assertTrue(ok)
        c = db.get_check_by_id(cid, conn=self.conn)
        self.assertEqual(c["status"], "Bounced")
        self.assertEqual(c["bounce_reason"], "Insufficient Funds")
        self.assertEqual(c["bounce_date"], "2026-10-05")


if __name__ == "__main__":
    unittest.main()
