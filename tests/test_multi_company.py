"""
Unit tests for dynamic multi-company support.
Tests creating, switching, updating, and deleting companies,
as well as auto-provisioning floats and cascade deletions.
"""

import unittest
import os
import tempfile
import shutil
import database as db


class TestMultiCompany(unittest.TestCase):

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

    def test_default_companies_seeded(self):
        comps = db.get_all_companies()
        self.assertGreaterEqual(len(comps), 2)
        c_ids = [c["id"] for c in comps]
        self.assertIn(1, c_ids)
        self.assertIn(2, c_ids)

    def test_create_multiple_companies(self):
        c3_id = db.create_company("Alpha Enterprise", tagline="Tech & Design", custom_prefix="ALPHA-")
        c4_id = db.create_company("Beta Solutions", tagline="Consulting", custom_prefix="BETA-")

        self.assertEqual(c3_id, 3)
        self.assertEqual(c4_id, 4)

        comps = db.get_all_companies()
        self.assertEqual(len(comps), 4)

        c3 = db.get_company(c3_id)
        self.assertIsNotNone(c3)
        self.assertEqual(c3["name"], "Alpha Enterprise")
        self.assertEqual(c3["custom_prefix"], "ALPHA-")

        # Verify default cash float auto-provisioned
        floats_3 = db.get_floats(c3_id)
        self.assertEqual(len(floats_3), 1)
        self.assertEqual(floats_3[0]["name"], "Main Cash Float")
        self.assertTrue(floats_3[0]["is_default"])

        floats_4 = db.get_floats(c4_id)
        self.assertEqual(len(floats_4), 1)
        self.assertEqual(floats_4[0]["name"], "Main Cash Float")

    def test_multi_company_voucher_isolation(self):
        c3_id = db.create_company("Gamma Corp", custom_prefix="GAM-")
        db.set_active_company_id(c3_id)
        self.assertEqual(db.get_active_company_id(), c3_id)

        # Create voucher in Company 3
        v_data = {
            "date": "2026-10-04",
            "paid_to": "Vendor Gamma",
            "cash_given_by": "Finance",
            "spent_by": "Staff",
            "bill_status": "Received",
            "company_id": c3_id
        }
        items = [{"description": "Item 1", "category": "General", "amount": 2500.0}]
        vid = db.create_voucher(v_data, items)

        created_v = db.get_voucher(vid)
        self.assertEqual(created_v["voucher"]["company_id"], c3_id)
        self.assertEqual(created_v["company"]["id"], c3_id)

        # Company 1 vouchers list should not include Company 3 vouchers
        v_c1 = db.get_all_vouchers(company_id=1)
        self.assertNotIn(vid, [v["id"] for v in v_c1])

        # Company 3 vouchers list should include it
        v_c3 = db.get_all_vouchers(company_id=c3_id)
        self.assertIn(vid, [v["id"] for v in v_c3])

    def test_delete_company_and_cascade(self):
        c3_id = db.create_company("Temporary Co")
        v_data = {
            "date": "2026-10-04",
            "paid_to": "Temp Payee",
            "cash_given_by": "Finance",
            "spent_by": "Staff",
            "bill_status": "Pending",
            "company_id": c3_id
        }
        items = [{"description": "Temp Item", "category": "General", "amount": 100.0}]
        vid = db.create_voucher(v_data, items)

        # Set active to company 3 then delete
        db.set_active_company_id(c3_id)
        self.assertEqual(db.get_active_company_id(), c3_id)

        success = db.delete_company(c3_id)
        self.assertTrue(success)

        # Company 3 should no longer exist
        self.assertIsNone(db.get_company(c3_id))
        self.assertIsNone(db.get_voucher(vid))
        self.assertEqual(len(db.get_floats(c3_id)), 0)

        # Active company should automatically have fallen back to another company
        self.assertNotEqual(db.get_active_company_id(), c3_id)
        self.assertIn(db.get_active_company_id(), [1, 2])

    def test_cannot_delete_last_remaining_company(self):
        # Delete down to 1 company
        all_comps = db.get_all_companies()
        for c in all_comps[1:]:
            db.delete_company(c["id"])

        self.assertEqual(len(db.get_all_companies()), 1)
        last_id = db.get_all_companies()[0]["id"]

        with self.assertRaises(ValueError):
            db.delete_company(last_id)


if __name__ == "__main__":
    unittest.main()
