"""
Unit tests for database layer (database.py).
"""

import unittest
import os
import tempfile
import sqlite3
import shutil

# Override database path for testing before importing database
import database as db


class TestDatabaseLayer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_test.db")
        self.attachments_dir = os.path.join(self.test_dir, "attachments")
        self.backup_dir = os.path.join(self.test_dir, "backups")

        # Monkey-patch database paths
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

    def test_company_creation_and_retrieval(self):
        companies = db.get_all_companies()
        self.assertGreaterEqual(len(companies), 2)
        c1 = db.get_company(1)
        self.assertIsNotNone(c1)
        self.assertEqual(c1["name"], "Company 1")

        # Update company profile
        db.save_company(1, {"name": "Updated Company 1", "tagline": "Best SME"})
        c1_updated = db.get_company(1)
        self.assertEqual(c1_updated["name"], "Updated Company 1")
        self.assertEqual(c1_updated["tagline"], "Best SME")

    def test_active_company_switch(self):
        self.assertEqual(db.get_active_company_id(), 1)
        db.set_active_company_id(2)
        self.assertEqual(db.get_active_company_id(), 2)

    def test_voucher_number_generation(self):
        # Date based numbering
        vn1 = db.get_next_voucher_number(company_id=1)
        self.assertTrue(vn1.startswith("V-"))

        # Create voucher to verify increment
        data = {
            "date": "2026-09-18",
            "paid_to": "John Doe",
            "cash_given_by": "Manager",
            "spent_by": "John Doe",
            "bill_status": "Pending",
        }
        line_items = [{"description": "Office Supplies", "category": "Stationery", "amount": 150.0}]
        v_id = db.create_voucher(data, line_items, company_id=1)
        self.assertIsNotNone(v_id)

        vn2 = db.get_next_voucher_number(company_id=1, voucher_date="2026-09-18")
        self.assertNotEqual(vn1, vn2)

    def test_voucher_crud(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "Jane Smith",
            "cash_given_by": "Cashier",
            "spent_by": "Jane Smith",
            "bill_status": "Pending",
            "prepared_by": "Alice",
            "approved_by": "Bob",
        }
        line_items = [
            {"description": "Travel Expenses", "category": "Transport", "amount": 250.0},
            {"description": "Meals", "category": "Food", "amount": 50.0},
        ]
        v_id = db.create_voucher(data, line_items, company_id=1)

        v_data = db.get_voucher(v_id)
        self.assertIsNotNone(v_data)
        self.assertEqual(v_data["voucher"]["paid_to"], "Jane Smith")
        self.assertEqual(v_data["voucher"]["total_amount"], 300.0)
        self.assertEqual(len(v_data["line_items"]), 2)

        # Update voucher
        data["paid_to"] = "Jane Smith Updated"
        new_line_items = [{"description": "Travel Expenses", "category": "Transport", "amount": 300.0}]
        db.update_voucher(v_id, data, new_line_items)

        updated_v = db.get_voucher(v_id)
        self.assertEqual(updated_v["voucher"]["paid_to"], "Jane Smith Updated")
        self.assertEqual(updated_v["voucher"]["total_amount"], 300.0)

        # Soft cancel
        db.cancel_voucher(v_id)
        canceled_v = db.get_voucher(v_id)
        self.assertEqual(canceled_v["voucher"]["status"], "Cancelled")

        # Restore
        db.restore_voucher(v_id)
        restored_v = db.get_voucher(v_id)
        self.assertEqual(restored_v["voucher"]["status"], "Active")

        # Permanent deletion
        db.cancel_voucher(v_id)
        deleted = db.permanently_delete_voucher(v_id)
        self.assertTrue(deleted)
        self.assertIsNone(db.get_voucher(v_id))

    def test_categories_and_people(self):
        cat_id = db.add_category("TestCategory")
        self.assertIsNotNone(cat_id)
        self.assertIn("TestCategory", db.get_categories())

        person_id = db.add_person("TestPerson")
        self.assertIsNotNone(person_id)
        self.assertIn("TestPerson", db.get_people())

    def test_search_vouchers(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "Unique Payee Name",
            "cash_given_by": "Admin",
            "spent_by": "Unique Payee Name",
            "bill_status": "Pending",
        }
        line_items = [{"description": "Special Keyword Description", "category": "General", "amount": 500.0}]
        db.create_voucher(data, line_items, company_id=1)

        results = db.search_vouchers(query="Unique Payee", company_id=1)
        self.assertEqual(len(results), 1)

        results_keyword = db.search_vouchers(query="Special Keyword", company_id=1)
        self.assertEqual(len(results_keyword), 1)

    def test_export_vouchers_to_csv(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "CSV Supplier",
            "cash_given_by": "Finance",
            "spent_by": "CSV Supplier",
            "bill_status": "Received",
        }
        line_items = [{"description": "Hardware Purchase", "category": "Equipment", "amount": 1200.0}]
        v_id = db.create_voucher(data, line_items, company_id=1)
        vouchers = db.search_vouchers(query="CSV Supplier", company_id=1)

        csv_path = os.path.join(self.test_dir, "test_out.csv")
        db.export_vouchers_to_csv(vouchers, csv_path)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("CSV Supplier", content)
            self.assertIn("1200.00", content)
            self.assertIn("Hardware Purchase", content)

    def test_get_expense_summary(self):
        data1 = {
            "date": "2026-09-18",
            "paid_to": "Alpha Vendor",
            "cash_given_by": "Manager",
            "spent_by": "Alpha Vendor",
            "bill_status": "Pending",
        }
        line_items1 = [{"description": "Item 1", "category": "Utilities", "amount": 300.0}]
        db.create_voucher(data1, line_items1, company_id=1)

        data2 = {
            "date": "2026-09-18",
            "paid_to": "Alpha Vendor",
            "cash_given_by": "Manager",
            "spent_by": "Alpha Vendor",
            "bill_status": "Received",
        }
        line_items2 = [{"description": "Item 2", "category": "Utilities", "amount": 200.0}]
        db.create_voucher(data2, line_items2, company_id=1)

        summary = db.get_expense_summary(company_id=1, date_filter="all")
        self.assertEqual(summary["grand_total"], 500.0)
        self.assertEqual(summary["voucher_count"], 2)
        self.assertGreaterEqual(len(summary["by_category"]), 1)
        self.assertEqual(summary["by_category"][0]["category"], "Utilities")
        self.assertEqual(summary["by_category"][0]["amount"], 500.0)


if __name__ == "__main__":
    unittest.main()
