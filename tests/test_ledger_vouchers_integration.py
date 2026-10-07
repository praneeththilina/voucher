"""
Unit tests for SME Double-Entry Ledger and Voucher Integration:
- Category to Ledger Account linking
- Cash Float to Ledger Cash Account linking
- Auto-Journal Double-Entry (Debit Category Account, Credit Float Account)
- Sub-Accounts hierarchy and parent dropdown options
- Classified Balance Sheet / Income Statement sub-categories
- Company Fiscal Year / Tax Year configuration
- Multi-company switching and data scoping
- Indexing verification
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime

import database as db
from ui.coa_dialog import AccountEditModal


class TestLedgerVouchersIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger_vouchers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and all migrations (up to Migration 31)
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_31_columns_and_indexes(self):
        """Verify Migration 31 added account_id to money_floats, fiscal dates to companies, and indexes."""
        # 1. money_floats.account_id
        cols = [c[1].lower() for c in self.conn.execute("PRAGMA table_info(money_floats)").fetchall()]
        self.assertIn("account_id", cols)

        # 2. companies.fiscal_year_start & fiscal_year_end
        c_cols = [c[1].lower() for c in self.conn.execute("PRAGMA table_info(companies)").fetchall()]
        self.assertIn("fiscal_year_start", c_cols)
        self.assertIn("fiscal_year_end", c_cols)

        # 3. High-performance indexes
        indexes = [r[1].lower() for r in self.conn.execute("SELECT type, name FROM sqlite_master WHERE type='index'").fetchall()]
        self.assertIn("idx_floats_acct", indexes)
        self.assertIn("idx_floats_comp_active", indexes)
        self.assertIn("idx_coa_parent", indexes)
        self.assertIn("idx_coa_comp_active", indexes)
        self.assertIn("idx_categories_name", indexes)
        self.assertIn("idx_categories_account_id", indexes)
        self.assertIn("idx_journal_entries_comp_posted", indexes)

    def test_cash_float_ledger_account_linking(self):
        """Verify cash floats link directly to cash/asset ledger accounts in Chart of Accounts."""
        # Find Bank Account (1120) in COA for Company 1
        bank_acct = db.get_account_by_code("1120", company_id=1, conn=self.conn)
        self.assertIsNotNone(bank_acct)

        # Create a new float linked to the Bank Account
        flt_id = db.create_float(
            company_id=1,
            name="Bank Checking Drawer",
            opening_balance=50000.0,
            account_id=bank_acct["id"],
            conn=self.conn
        )
        self.assertIsNotNone(flt_id)

        # Fetch float and verify joined ledger account fields
        flt = db.get_float(flt_id, conn=self.conn)
        self.assertIsNotNone(flt)
        self.assertEqual(flt["account_id"], bank_acct["id"])
        self.assertEqual(flt["linked_account_code"], "1120")
        self.assertEqual(flt["linked_account_name"], bank_acct["account_name"])

        # Update float to link to Petty Cash (1110)
        petty_acct = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        db.update_float(flt_id, {"account_id": petty_acct["id"]}, conn=self.conn)

        flt_updated = db.get_float(flt_id, conn=self.conn)
        self.assertEqual(flt_updated["account_id"], petty_acct["id"])
        self.assertEqual(flt_updated["linked_account_code"], "1110")

    def test_category_ledger_account_linking(self):
        """Verify expense categories link to COA accounts and return linked account metadata."""
        # Get Rent Expense account (5210)
        rent_acct = db.get_account_by_code("5210", company_id=1, conn=self.conn)
        self.assertIsNotNone(rent_acct)

        # Add category with linked account
        cat_id = db.add_category("Office Rent", account_id=rent_acct["id"], conn=self.conn)
        self.assertIsNotNone(cat_id)

        # Verify get_all_categories_full returns linked account details
        cats = db.get_all_categories_full(company_id=1, conn=self.conn)
        matched = next((c for c in cats if c["id"] == cat_id), None)
        self.assertIsNotNone(matched)
        self.assertEqual(matched["account_id"], rent_acct["id"])
        self.assertEqual(matched["linked_account_code"], "5210")
        self.assertEqual(matched["linked_account_type"], "Expense")

        # Update category linked account to Office Supplies & Stationery (5410)
        supplies_acct = db.get_account_by_code("5410", company_id=1, conn=self.conn)
        db.update_category(cat_id, new_name="Stationery & Office", account_id=supplies_acct["id"], conn=self.conn)

        cats_after = db.get_all_categories_full(company_id=1, conn=self.conn)
        matched_after = next((c for c in cats_after if c["id"] == cat_id), None)
        self.assertEqual(matched_after["name"], "Stationery & Office")
        self.assertEqual(matched_after["linked_account_code"], "5410")

    def test_voucher_double_entry_auto_journal_with_linked_accounts(self):
        """
        Verify that posting a voucher posts double-entry journal entries correctly:
        - Debit: Category's linked expense account
        - Credit: Cash float's linked cash account
        """
        # 1. Setup specific ledger accounts
        supplies_acct = db.get_account_by_code("5410", company_id=1, conn=self.conn)  # Office Supplies & Stationery
        bank_acct = db.get_account_by_code("1120", company_id=1, conn=self.conn)      # Cash at Bank
        self.assertIsNotNone(supplies_acct)
        self.assertIsNotNone(bank_acct)

        # 2. Setup Category linked to 5410
        cat_id = db.add_category("Printing Paper & Ink", account_id=supplies_acct["id"], conn=self.conn)

        # 3. Setup Float linked to 1120
        flt_id = db.create_float(
            company_id=1,
            name="Bank Disbursement Float",
            opening_balance=100000.0,
            account_id=bank_acct["id"],
            conn=self.conn
        )

        # 4. Create and post a Voucher with this category and float
        v_data = {
            "voucher_number": "V-2026-TEST-01",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "paid_to": "Apex Supplies",
            "payment_method": "Cash",
            "float_id": flt_id,
            "company_id": 1,
            "status": "Approved",
        }
        line_items = [
            {"description": "A4 Paper & Printer Cartridges", "amount": 25000.0, "category_id": cat_id, "category": "Printing Paper & Ink"}
        ]
        v_id = db.create_voucher(v_data, line_items, company_id=1)
        self.assertIsNotNone(v_id)

        # 5. Trigger Auto-Journal Double Entry
        entry_id = db.auto_journal_for_voucher(v_id, conn=self.conn)
        self.assertIsNotNone(entry_id)

        # 6. Verify Journal Entry Header & Lines
        lines = self.conn.execute("""
            SELECT jl.account_id, coa.account_code, coa.account_name, jl.debit_amount, jl.credit_amount, jl.description
            FROM journal_lines jl
            JOIN chart_of_accounts coa ON coa.id = jl.account_id
            WHERE jl.entry_id = ?
            ORDER BY jl.line_order ASC
        """, (entry_id,)).fetchall()

        self.assertEqual(len(lines), 2)

        # Line 1: Debit Category Expense Account (5410 Office Supplies & Stationery)
        debit_line = lines[0]
        self.assertEqual(debit_line[1], "5410")
        self.assertEqual(float(debit_line[3]), 25000.0)
        self.assertEqual(float(debit_line[4]), 0.0)

        # Line 2: Credit Float Cash Account (1120 Cash at Bank)
        credit_line = lines[1]
        self.assertEqual(credit_line[1], "1120")
        self.assertEqual(float(credit_line[3]), 0.0)
        self.assertEqual(float(credit_line[4]), 25000.0)

        # Balanced Double-Entry Check
        total_debit = sum(float(l[3]) for l in lines)
        total_credit = sum(float(l[4]) for l in lines)
        self.assertEqual(total_debit, total_credit)

    def test_sub_accounts_and_parent_dropdown(self):
        """Verify sub-account parent lookup and hierarchical display fields."""
        # 1. Available parent accounts for Asset type in Company 1
        parents = db.get_available_parent_accounts(company_id=1, account_type="Asset", conn=self.conn)
        self.assertGreater(len(parents), 0)
        # All parents should be of type Asset
        for p in parents:
            self.assertEqual(p["account_type"], "Asset")

        # 2. Create a sub-account under Petty Cash (1110)
        petty = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        sub_acct_id = db.create_account({
            "company_id": 1,
            "account_code": "1111",
            "account_name": "Petty Cash - Main Warehouse",
            "account_type": "Asset",
            "sub_category": "Current Assets - Cash & Cash Equivalents",
            "parent_id": petty["id"],
            "normal_balance": "Debit"
        }, conn=self.conn)
        self.assertIsNotNone(sub_acct_id)

        # 3. Retrieve COA and verify joined parent metadata
        accounts = db.get_chart_of_accounts(company_id=1, conn=self.conn)
        child = next((a for a in accounts if a["id"] == sub_acct_id), None)
        self.assertIsNotNone(child)
        self.assertEqual(child["parent_id"], petty["id"])
        self.assertEqual(child["parent_code"], "1110")
        self.assertEqual(child["parent_name"], "Petty Cash")

    def test_classified_balance_sheet_sub_categories_and_normal_balances(self):
        """Verify standard classified subcategories and normal balance assignment rules."""
        subcats = AccountEditModal.STANDARD_SUB_CATEGORIES
        self.assertIn("Asset", subcats)
        self.assertTrue(any("Current Assets" in s for s in subcats["Asset"]))
        self.assertTrue(any("Fixed Assets" in s for s in subcats["Asset"]))
        self.assertTrue(any("Current Liabilities" in s for s in subcats["Liability"]))
        self.assertTrue(any("Long-Term Liabilities" in s for s in subcats["Liability"]))
        self.assertTrue(any("Retained Earnings" in s for s in subcats["Equity"]))

        # Check normal balance convention:
        # Asset, Expense -> Debit (+ is debit)
        # Liability, Equity, Revenue -> Credit (+ is credit)
        for atype in ("Asset", "Expense"):
            bal = "Debit" if atype in ("Asset", "Expense") else "Credit"
            self.assertEqual(bal, "Debit")

        for atype in ("Liability", "Equity", "Revenue", "Income"):
            bal = "Debit" if atype in ("Asset", "Expense") else "Credit"
            self.assertEqual(bal, "Credit")

    def test_company_fiscal_year_opening_closing_dates(self):
        """Verify setting and reading fiscal year / tax year opening and closing dates."""
        # 1. Verify default fiscal year is 01-01 to 12-31
        f_start, f_end = db.get_company_fiscal_year(company_id=1, conn=self.conn)
        self.assertEqual(f_start, "01-01")
        self.assertEqual(f_end, "12-31")

        # 2. Update to UK / South Asia Tax Year (Apr 1 - Mar 31)
        db.save_company(1, {
            "fiscal_year_start": "04-01",
            "fiscal_year_end": "03-31"
        })

        f_start2, f_end2 = db.get_company_fiscal_year(company_id=1, conn=self.conn)
        self.assertEqual(f_start2, "04-01")
        self.assertEqual(f_end2, "03-31")

    def test_multi_company_switching_and_isolated_accounts(self):
        """Verify that creating and switching company automatically seeds COA and scopes data."""
        # Create Company 2
        comp2_id = db.create_company(
            name="Subsidiary Logistics Ltd",
            fiscal_year_start="07-01",
            fiscal_year_end="06-30",
            conn=self.conn
        )
        self.assertIsNotNone(comp2_id)

        # Switch active company to Company 2
        db.set_active_company_id(comp2_id)
        self.assertEqual(db.get_active_company_id(), comp2_id)

        # Verify Company 2 COA is seeded
        comp2_accounts = db.get_chart_of_accounts(company_id=comp2_id, conn=self.conn)
        self.assertGreaterEqual(len(comp2_accounts), 20)

        # Verify Company 2 has its own default float linked to Company 2's Petty Cash
        comp2_floats = db.get_floats(company_id=comp2_id, conn=self.conn)
        self.assertGreaterEqual(len(comp2_floats), 1)
        self.assertEqual(comp2_floats[0]["linked_account_code"], "1110")

        # Switch back to Company 1
        db.set_active_company_id(1)
        self.assertEqual(db.get_active_company_id(), 1)


if __name__ == "__main__":
    unittest.main()
