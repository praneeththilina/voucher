"""
Unit tests for Smart Voucher Assistant features:
- Category auto-completion/suggestion for payees
- Potential duplicate voucher detection
"""

import unittest
import os
import shutil
import tempfile
from datetime import datetime, timedelta

import database as db


class TestSmartVoucherAssistant(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_db_path = db.DB_PATH
        self.orig_db_dir = db.DB_DIR
        self.orig_attachments_dir = db.ATTACHMENTS_DIR

        db.DB_DIR = self.temp_dir
        db.DB_PATH = os.path.join(self.temp_dir, "test_vouchers.db")
        db.ATTACHMENTS_DIR = os.path.join(self.temp_dir, "attachments")
        os.makedirs(db.ATTACHMENTS_DIR, exist_ok=True)

        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        db.DB_DIR = self.orig_db_dir
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_suggest_category_for_payee_empty(self):
        """Empty or unknown payee should return empty string."""
        self.assertEqual(db.suggest_category_for_payee(""), "")
        self.assertEqual(db.suggest_category_for_payee("   "), "")
        self.assertEqual(db.suggest_category_for_payee("Non Existent Vendor"), "")

    def test_suggest_category_from_payee_directory_default(self):
        """Should prefer default category configured in payee directory."""
        db.add_person(
            name="Keells Super",
            default_category="Office Provisions"
        )
        cat = db.suggest_category_for_payee("Keells Super")
        self.assertEqual(cat, "Office Provisions")

    def test_suggest_category_from_historical_vouchers(self):
        """Should suggest the most frequent category used in historical vouchers for payee if directory default is not set."""
        # Create historical vouchers for vendor
        v_data = {
            "paid_to": "Keells Super",
            "cash_given_by": "Cashier",
            "date": "2026-03-01",
            "bill_status": "Pending",
        }
        # 2 vouchers under Refreshments, 1 under Office Supplies
        db.create_voucher(v_data, [{"description": "Tea", "category": "Refreshments", "amount": 500}])
        db.create_voucher(v_data, [{"description": "Coffee", "category": "Refreshments", "amount": 750}])
        db.create_voucher(v_data, [{"description": "Paper", "category": "Office Supplies", "amount": 1000}])

        cat = db.suggest_category_for_payee("keells super")  # Case insensitive
        self.assertEqual(cat, "Refreshments")

    def test_check_potential_duplicate_voucher(self):
        """Should detect potential duplicate vouchers with matching payee, amount, and close date."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        v_data = {
            "paid_to": "Keells Super",
            "cash_given_by": "Cashier",
            "date": today_str,
            "bill_status": "Pending",
        }
        v_id1 = db.create_voucher(v_data, [{"description": "Supplies", "category": "Office Supplies", "amount": 2500}])

        # Check exact match
        dups = db.check_potential_duplicate_voucher("Keells Super", 2500, today_str)
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]["id"], v_id1)

        # Check case-insensitivity and floating amount precision
        dups2 = db.check_potential_duplicate_voucher("keells super", 2500.00, today_str)
        self.assertEqual(len(dups2), 1)

        # Exclude self when editing
        dups_edit = db.check_potential_duplicate_voucher("Keells Super", 2500, today_str, exclude_voucher_id=v_id1)
        self.assertEqual(len(dups_edit), 0)

        # Date outside tolerance window (e.g. +30 days)
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        dups_far = db.check_potential_duplicate_voucher("Keells Super", 2500, future_date, tolerance_days=7)
        self.assertEqual(len(dups_far), 0)

        # Different amount
        dups_diff_amt = db.check_potential_duplicate_voucher("Keells Super", 3000, today_str)
        self.assertEqual(len(dups_diff_amt), 0)

    def test_suggest_category_from_description(self):
        """Should suggest expense category based on line item description keywords."""
        v_data = {
            "paid_to": "ACME Supplies",
            "cash_given_by": "Cashier",
            "date": "2026-03-01",
            "bill_status": "Pending",
        }
        db.create_voucher(v_data, [{"description": "Printer Cartridge Black HP", "category": "Office Printing", "amount": 4500}])
        db.create_voucher(v_data, [{"description": "HP Toner Cartridge Magenta", "category": "Office Printing", "amount": 6500}])

        # Test description match
        self.assertEqual(db.suggest_category_from_description("Printer Cartridge"), "Office Printing")
        self.assertEqual(db.suggest_category_from_description("Cartridge"), "Office Printing")
        self.assertEqual(db.suggest_category_from_description(""), "")

        # Test fallback via suggest_category_for_payee with unknown payee
        cat = db.suggest_category_for_payee("Unknown Vendor", description="Printer Cartridge")
        self.assertEqual(cat, "Office Printing")

    def test_detect_voucher_anomaly(self):
        """Should detect statistical expense anomalies when amount exceeds 3x historical average."""
        v_data = {
            "paid_to": "Keells Super",
            "cash_given_by": "Cashier",
            "date": "2026-03-01",
            "bill_status": "Pending",
        }

        # Create 3 normal vouchers (~1,000 LKR)
        db.create_voucher(v_data, [{"description": "Provisions", "category": "Refreshments", "amount": 1000}])
        db.create_voucher(v_data, [{"description": "Provisions", "category": "Refreshments", "amount": 1100}])
        db.create_voucher(v_data, [{"description": "Provisions", "category": "Refreshments", "amount": 900}])

        # Test normal amount (1,200 LKR) -> No anomaly
        no_anomaly = db.detect_voucher_anomaly(paid_to="Keells Super", category="Refreshments", amount=1200)
        self.assertFalse(no_anomaly["is_anomaly"])

        # Test outlier amount (10,000 LKR) -> Anomaly detected
        anomaly = db.detect_voucher_anomaly(paid_to="Keells Super", category="Refreshments", amount=10000)
        self.assertTrue(anomaly["is_anomaly"])
        self.assertTrue(len(anomaly["reasons"]) >= 1)

        # Test edge case: zero amount or fewer than 3 historical samples
        self.assertFalse(db.detect_voucher_anomaly(paid_to="Keells Super", category="Refreshments", amount=0)["is_anomaly"])
        self.assertFalse(db.detect_voucher_anomaly(paid_to="New Vendor", category="New Cat", amount=50000)["is_anomaly"])


if __name__ == "__main__":
    unittest.main()
