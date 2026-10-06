"""
Unit tests for Chart of Accounts (COA) database operations, classification rules,
and system account safeguards (v3.5).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db


class TestChartOfAccounts(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_coa.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migration 23 & 24)
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_23_tables_and_columns(self):
        """Verify chart_of_accounts table and categories.account_id exist."""
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("chart_of_accounts", tables)

        cols = [c[1].lower() for c in self.conn.execute("PRAGMA table_info(categories)").fetchall()]
        self.assertIn("account_id", cols)

    def test_default_accounts_seeded_for_company(self):
        """Verify default 5-group SME Chart of Accounts is seeded for default company."""
        accounts = db.get_chart_of_accounts(company_id=1, conn=self.conn)
        self.assertGreaterEqual(len(accounts), 20)

        types = set(a["account_type"] for a in accounts)
        self.assertIn("Asset", types)
        self.assertIn("Liability", types)
        self.assertIn("Equity", types)
        self.assertTrue("Income" in types or "Revenue" in types)
        self.assertIn("Expense", types)

        # Check key standard accounts
        petty_cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        self.assertIsNotNone(petty_cash)
        self.assertEqual(petty_cash["account_name"], "Petty Cash")
        self.assertEqual(petty_cash["normal_balance"], "Debit")
        self.assertEqual(petty_cash["is_system"], 1)

        retained_earnings = db.get_account_by_code("3210", company_id=1, conn=self.conn)
        self.assertIsNotNone(retained_earnings)
        self.assertEqual(retained_earnings["account_type"], "Equity")
        self.assertEqual(retained_earnings["normal_balance"], "Credit")

    def test_filter_accounts_by_type_and_active(self):
        """Test retrieving accounts filtered by account_type or active status."""
        assets = db.get_chart_of_accounts(company_id=1, account_type="Asset", conn=self.conn)
        for a in assets:
            self.assertEqual(a["account_type"], "Asset")

        expenses = db.get_chart_of_accounts(company_id=1, account_type="Expense", conn=self.conn)
        self.assertTrue(len(expenses) > 0)
        for e in expenses:
            self.assertEqual(e["account_type"], "Expense")

    def test_create_custom_account(self):
        """Test adding a custom account to the Chart of Accounts."""
        new_account = {
            "company_id": 1,
            "account_code": "5950",
            "account_name": "Software Subscriptions",
            "account_type": "Expense",
            "sub_category": "Operating Expenses",
            "normal_balance": "Debit",
            "is_active": 1,
            "notes": "SaaS & Cloud subscriptions"
        }
        acct_id = db.create_account(new_account, conn=self.conn)
        self.assertIsNotNone(acct_id)

        retrieved = db.get_account_by_id(acct_id, conn=self.conn)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["account_code"], "5950")
        self.assertEqual(retrieved["account_name"], "Software Subscriptions")
        self.assertEqual(retrieved["is_system"], 0)

    def test_account_code_uniqueness(self):
        """Test that duplicate account code for same company is rejected."""
        acct = {
            "company_id": 1,
            "account_code": "1110",  # Already exists (Petty Cash)
            "account_name": "Duplicate Cash",
            "account_type": "Asset"
        }
        with self.assertRaises(Exception):
            db.create_account(acct, conn=self.conn)

    def test_update_account(self):
        """Test modifying account attributes."""
        acct_id = db.create_account({
            "company_id": 1,
            "account_code": "1140",
            "account_name": "Treasury Bond Fund",
            "account_type": "Asset",
            "normal_balance": "Debit"
        }, conn=self.conn)

        success = db.update_account(acct_id, {
            "account_name": "Treasury Bonds & Fixed Deposits",
            "sub_category": "Short Term Investments"
        }, conn=self.conn)
        self.assertTrue(success)

        updated = db.get_account_by_id(acct_id, conn=self.conn)
        self.assertEqual(updated["account_name"], "Treasury Bonds & Fixed Deposits")
        self.assertEqual(updated["sub_category"], "Short Term Investments")

    def test_delete_system_account_blocked(self):
        """Test that default system accounts cannot be deleted."""
        petty_cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        success, msg = db.delete_account(petty_cash["id"], conn=self.conn)
        self.assertFalse(success)
        self.assertIn("System accounts are protected", msg)

    def test_delete_custom_account_with_no_activity(self):
        """Test deleting an unused custom account succeeds."""
        acct_id = db.create_account({
            "company_id": 1,
            "account_code": "5999",
            "account_name": "Temp Test Expense",
            "account_type": "Expense"
        }, conn=self.conn)

        success, msg = db.delete_account(acct_id, conn=self.conn)
        self.assertTrue(success)
        self.assertIsNone(db.get_account_by_id(acct_id, conn=self.conn))

    def test_delete_account_with_journal_activity_blocked(self):
        """Test that accounts with ledger entries cannot be deleted."""
        acct_id = db.create_account({
            "company_id": 1,
            "account_code": "5980",
            "account_name": "Research & Development",
            "account_type": "Expense"
        }, conn=self.conn)

        # Create a journal entry using this account
        header = {
            "company_id": 1,
            "entry_number": "JE-2026-TEST",
            "entry_date": "2026-10-01",
            "entry_type": "Manual"
        }
        petty_cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        lines = [
            {"account_id": acct_id, "debit_amount": 500.0, "credit_amount": 0.0},
            {"account_id": petty_cash["id"], "debit_amount": 0.0, "credit_amount": 500.0}
        ]
        db.create_journal_entry(header, lines, conn=self.conn)

        # Deletion must be blocked
        success, msg = db.delete_account(acct_id, conn=self.conn)
        self.assertFalse(success)
        self.assertIn("transaction(s) in the General Ledger", msg)


if __name__ == "__main__":
    unittest.main()
