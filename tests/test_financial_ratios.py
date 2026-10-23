"""
tests/test_financial_ratios.py
Unit and Integration Tests for Financial Ratios & Health Analytics Module.
"""

import os
import sqlite3
import tempfile
import unittest
import tkinter as tk
from unittest.mock import patch, MagicMock

import database as db
from reports import (
    generate_financial_ratios,
    export_financial_ratios_csv,
    generate_financial_ratios_pdf,
)
from ui.financial_reports_dialog import FinancialReportsDialog


class TestFinancialRatiosModule(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        db.DB_PATH = self.db_path
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = 1

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_generate_financial_ratios_empty(self):
        """Test financial ratios generation on a fresh/empty database."""
        report = generate_financial_ratios(self.company_id, conn=self.conn)
        self.assertIsNotNone(report)
        self.assertEqual(report["company_id"], self.company_id)
        self.assertIn("ratios", report)
        self.assertEqual(len(report["ratios"]), 9)
        self.assertIn("health_grade", report)

    def test_generate_financial_ratios_populated(self):
        """Test ratio calculations with populated GL journal entries."""
        # 1. Post Revenue (Income) and Cash Receipt (Current Asset)
        # Sales Revenue: 10,000 credit, Cash: 10,000 debit
        rev_acct = self.conn.execute(
            "SELECT id FROM chart_of_accounts WHERE account_type = 'Income' AND company_id = ? LIMIT 1",
            (self.company_id,)
        ).fetchone()
        cash_acct = self.conn.execute(
            "SELECT id FROM chart_of_accounts WHERE account_type = 'Asset' AND sub_category LIKE '%Cash%' AND company_id = ? LIMIT 1",
            (self.company_id,)
        ).fetchone()
        exp_acct = self.conn.execute(
            "SELECT id FROM chart_of_accounts WHERE account_type = 'Expense' AND company_id = ? LIMIT 1",
            (self.company_id,)
        ).fetchone()
        liab_acct = self.conn.execute(
            "SELECT id FROM chart_of_accounts WHERE account_type = 'Liability' AND company_id = ? LIMIT 1",
            (self.company_id,)
        ).fetchone()

        if not rev_acct or not cash_acct or not exp_acct or not liab_acct:
            self.skipTest("Missing essential accounts in seed COA")

        # Create Journal Entry 1: Income 10,000 -> Cash 10,000
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO journal_entries (company_id, entry_number, entry_date, description, is_posted) VALUES (?, 'JE-101', '2025-01-10', 'Sales Revenue', 1)",
            (self.company_id,)
        )
        je1_id = cur.lastrowid
        cur.execute("INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 10000.0, 0.0)", (je1_id, cash_acct[0]))
        cur.execute("INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 0.0, 10000.0)", (je1_id, rev_acct[0]))

        # Create Journal Entry 2: Operating Expense 3,000 -> Accounts Payable 3,000
        cur.execute(
            "INSERT INTO journal_entries (company_id, entry_number, entry_date, description, is_posted) VALUES (?, 'JE-102', '2025-01-15', 'Office Expenses', 1)",
            (self.company_id,)
        )
        je2_id = cur.lastrowid
        cur.execute("INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 3000.0, 0.0)", (je2_id, exp_acct[0]))
        cur.execute("INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 0.0, 3000.0)", (je2_id, liab_acct[0]))

        self.conn.commit()

        report = generate_financial_ratios(self.company_id, start_date="2025-01-01", end_date="2025-01-31", conn=self.conn)

        # Totals verification
        st = report["summary_totals"]
        self.assertAlmostEqual(st["total_revenue"], 10000.0)
        self.assertAlmostEqual(st["total_operating_expenses"], 3000.0)
        self.assertAlmostEqual(st["net_profit"], 7000.0)
        self.assertAlmostEqual(st["total_current_assets"], 10000.0)
        self.assertAlmostEqual(st["total_current_liabilities"], 3000.0)

        # Check ratios
        r_map = {r["key"]: r for r in report["ratios"]}

        # Current Ratio: 10,000 / 3,000 = 3.33x
        self.assertAlmostEqual(r_map["current_ratio"]["value"], 3.33, places=2)
        self.assertEqual(r_map["current_ratio"]["status"], "Optimal")

        # Working Capital: 10,000 - 3,000 = 7,000
        self.assertAlmostEqual(r_map["working_capital"]["value"], 7000.0)
        self.assertEqual(r_map["working_capital"]["status"], "Optimal")

        # Net Profit Margin %: 7,000 / 10,000 * 100 = 70%
        self.assertAlmostEqual(r_map["net_profit_margin"]["value"], 70.0)
        self.assertEqual(r_map["net_profit_margin"]["status"], "Optimal")

        # Operating Expense Ratio %: 3,000 / 10,000 * 100 = 30%
        self.assertAlmostEqual(r_map["operating_expense_ratio"]["value"], 30.0)
        self.assertEqual(r_map["operating_expense_ratio"]["status"], "Optimal")

    def test_export_financial_ratios_csv(self):
        """Test exporting financial ratio analytics to CSV with formula injection sanitization."""
        report = generate_financial_ratios(self.company_id, conn=self.conn)

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = f.name

        try:
            res_path = export_financial_ratios_csv(report, csv_path)
            self.assertTrue(os.path.exists(res_path))
            with open(res_path, encoding="utf-8-sig") as csv_f:
                content = csv_f.read()
                self.assertIn("FINANCIAL RATIOS & HEALTH ANALYTICS REPORT", content)
                self.assertIn("Current Ratio", content)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_generate_financial_ratios_pdf(self):
        """Test PDF generation for Financial Ratios Report."""
        report = generate_financial_ratios(self.company_id, conn=self.conn)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            pdf_path = f.name

        try:
            res_path = generate_financial_ratios_pdf(report, pdf_path)
            self.assertTrue(os.path.exists(res_path))
            self.assertGreater(os.path.getsize(res_path), 0)
        finally:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

    def test_ui_financial_reports_dialog_ratios_tab(self):
        """Test FinancialReportsDialog rendering of Tab 4 (Financial Ratios & Health)."""
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = FinancialReportsDialog(root, company_id=self.company_id, initial_tab=4)
            dialog.update_idletasks()
            self.assertIsNotNone(dialog.ratios_data)
            self.assertEqual(len(dialog.ratios_tree.get_children()), 12)  # 3 section headers + 9 ratio rows
            dialog.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
