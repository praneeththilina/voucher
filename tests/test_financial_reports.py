"""
tests/test_financial_reports.py
Unit tests for Financial Reporting Engine (Profit & Loss, Balance Sheet,
Cash Flow, Trial Balance, CSV Exports, and PDF Generation).
"""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
from reports import (
    generate_profit_loss,
    export_profit_loss_csv,
    generate_balance_sheet,
    export_balance_sheet_csv,
    generate_cash_flow,
    export_cash_flow_csv,
    generate_profit_loss_pdf,
    generate_balance_sheet_pdf,
    generate_trial_balance_pdf,
    generate_cash_flow_pdf,
)


class TestFinancialReports(unittest.TestCase):
    """Test suite verifying financial calculations, double-entry balancing, and report exports."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = 1
        self.created_temp_files = []

        # Populate realistic bookkeeping double-entry transactions
        # 1. Capital Injection: DEBIT Bank (1120) 500,000, CREDIT Owner's Capital (3110) 500,000
        b_acct = db.get_account_by_code("1120", self.company_id)
        cap_acct = db.get_account_by_code("3110", self.company_id)
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-01-01",
                "reference": "CAP-001",
                "description": "Initial Capital Injection",
                "entry_type": "Manual",
            },
            [
                {"account_id": b_acct["id"], "debit_amount": 500000.0, "credit_amount": 0.0, "description": "Bank Deposit"},
                {"account_id": cap_acct["id"], "debit_amount": 0.0, "credit_amount": 500000.0, "description": "Capital Contributed"},
            ]
        )

        # 2. Sales Revenue: DEBIT Accounts Receivable (1210) 150,000, CREDIT Sales Revenue (4110) 150,000
        ar_acct = db.get_account_by_code("1210", self.company_id)
        rev_acct = db.get_account_by_code("4110", self.company_id)
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-02-15",
                "reference": "INV-2026-0001",
                "description": "Consulting & Software Services",
                "entry_type": "AR Invoice",
            },
            [
                {"account_id": ar_acct["id"], "debit_amount": 150000.0, "credit_amount": 0.0, "description": "Receivable from Customer"},
                {"account_id": rev_acct["id"], "debit_amount": 0.0, "credit_amount": 150000.0, "description": "Sales Revenue"},
            ]
        )

        # 3. Customer AR Payment: DEBIT Cash at Bank (1120) 100,000, CREDIT Accounts Receivable (1210) 100,000
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-03-01",
                "reference": "REC-001",
                "description": "Customer partial payment received",
                "entry_type": "AR Receipt",
            },
            [
                {"account_id": b_acct["id"], "debit_amount": 100000.0, "credit_amount": 0.0, "description": "Bank Inflow"},
                {"account_id": ar_acct["id"], "debit_amount": 0.0, "credit_amount": 100000.0, "description": "Settled AR"},
            ]
        )

        # 4. Rent Expense Payment: DEBIT Rent Expense (5210) 30,000, CREDIT Cash at Bank (1120) 30,000
        rent_acct = db.get_account_by_code("5210", self.company_id)
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-03-05",
                "reference": "V-001",
                "description": "Office Rent March 2026",
                "entry_type": "Voucher",
            },
            [
                {"account_id": rent_acct["id"], "debit_amount": 30000.0, "credit_amount": 0.0, "description": "Office Rent"},
                {"account_id": b_acct["id"], "debit_amount": 0.0, "credit_amount": 30000.0, "description": "Bank Payout"},
            ]
        )

        # 5. Utilities Expense Payment: DEBIT Utilities (5310) 10,000, CREDIT Cash at Bank (1120) 10,000
        util_acct = db.get_account_by_code("5310", self.company_id)
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-03-10",
                "reference": "V-002",
                "description": "Electricity & Internet Bill",
                "entry_type": "Voucher",
            },
            [
                {"account_id": util_acct["id"], "debit_amount": 10000.0, "credit_amount": 0.0, "description": "Electricity"},
                {"account_id": b_acct["id"], "debit_amount": 0.0, "credit_amount": 10000.0, "description": "Bank Payout"},
            ]
        )

        # 6. Discounts Received (Other Income): DEBIT Trade Creditors (2110) 5,000, CREDIT Other Income (4310) 5,000
        ap_acct = db.get_account_by_code("2110", self.company_id)
        oth_inc_acct = db.get_account_by_code("4310", self.company_id)
        db.create_journal_entry(
            {
                "company_id": self.company_id,
                "entry_date": "2026-03-15",
                "reference": "DISC-01",
                "description": "Supplier Settlement Early Payment Discount",
                "entry_type": "Manual",
            },
            [
                {"account_id": ap_acct["id"], "debit_amount": 5000.0, "credit_amount": 0.0, "description": "AP Discount"},
                {"account_id": oth_inc_acct["id"], "debit_amount": 0.0, "credit_amount": 5000.0, "description": "Other Income"},
            ]
        )

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        for p in self.created_temp_files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass

    def test_generate_profit_loss_calculations(self):
        """Verify Profit & Loss calculates revenue, expenses, operating profit, and net profit with exact margins."""
        pl = generate_profit_loss(self.company_id, start_date="2026-01-01", end_date="2026-12-31")

        self.assertEqual(pl["total_operating_revenue"], 150000.0)
        self.assertEqual(pl["total_cost_of_sales"], 0.0)
        self.assertEqual(pl["gross_profit"], 150000.0)
        self.assertEqual(pl["gross_profit_margin_pct"], 100.0)

        # Operating Expenses: Rent 30,000 + Utilities 10,000 = 40,000
        self.assertEqual(pl["total_operating_expenses"], 40000.0)
        self.assertEqual(pl["operating_profit"], 110000.0)

        # Other Income: 5,000
        self.assertEqual(pl["total_other_income"], 5000.0)

        # Net Profit: Operating Profit (110,000) + Other Income (5,000) = 115,000
        self.assertEqual(pl["net_profit"], 115000.0)
        self.assertTrue(pl["is_profit"])

        # Total income for margin = 150,000 + 5,000 = 155,000; Net Margin % = (115,000 / 155,000) * 100 = 74.19%
        self.assertAlmostEqual(pl["net_profit_margin_pct"], 74.19, places=2)

    def test_profit_loss_date_filtering(self):
        """Verify Profit & Loss strictly isolates figures within the requested date boundary."""
        # Range excluding March: Only Feb 2026
        pl_feb = generate_profit_loss(self.company_id, start_date="2026-02-01", end_date="2026-02-28")
        self.assertEqual(pl_feb["total_operating_revenue"], 150000.0)
        self.assertEqual(pl_feb["total_operating_expenses"], 0.0)
        self.assertEqual(pl_feb["net_profit"], 150000.0)

        # March only
        pl_mar = generate_profit_loss(self.company_id, start_date="2026-03-01", end_date="2026-03-31")
        self.assertEqual(pl_mar["total_operating_revenue"], 0.0)
        self.assertEqual(pl_mar["total_operating_expenses"], 40000.0)
        self.assertEqual(pl_mar["total_other_income"], 5000.0)
        self.assertEqual(pl_mar["net_profit"], -35000.0)
        self.assertFalse(pl_mar["is_profit"])

    def test_balance_sheet_equation_balanced(self):
        """Verify Balance Sheet satisfies the fundamental accounting equation: Assets = Liabilities + Equity."""
        bs = generate_balance_sheet(self.company_id, as_of_date="2026-12-31")

        # Bank balance: 500,000 (Capital) + 100,000 (AR) - 30,000 (Rent) - 10,000 (Utilities) = 560,000
        # AR balance: 150,000 (Invoiced) - 100,000 (Paid) = 50,000
        # Total Assets = 560,000 + 50,000 = 610,000
        self.assertEqual(bs["total_assets"], 610000.0)

        # Liabilities: Trade Creditors (debit 5,000 from discount -> -5,000)
        # Equity: Capital 500,000 + Net Income 115,000 = 615,000
        # Liabilities + Equity = -5,000 + 615,000 = 610,000
        self.assertEqual(bs["total_liabilities_and_equity"], 610000.0)

        self.assertTrue(bs["is_balanced"])
        self.assertEqual(bs["difference"], 0.0)
        self.assertEqual(bs["current_period_net_income"], 115000.0)

    def test_trial_balance_balancing(self):
        """Verify Trial Balance confirms all debit transactions equal credit transactions."""
        tb = db.get_trial_balance(self.company_id, as_of_date="2026-12-31")
        self.assertTrue(tb["is_balanced"])
        self.assertEqual(tb["difference"], 0.0)
        self.assertGreater(tb["total_debit"], 0.0)
        self.assertEqual(tb["total_debit"], tb["total_credit"])

    def test_cash_flow_statement_reconciliation(self):
        """Verify Cash Flow Statement accurately tracks beginning balance, inflows, outflows, and ending balance."""
        cf = generate_cash_flow(self.company_id, start_date="2026-01-01", end_date="2026-12-31")

        # Beginning cash before Jan 1 was 0
        self.assertEqual(cf["beginning_cash"], 0.0)
        # Inflows: 500,000 (Capital) + 100,000 (Customer AR) = 600,000
        self.assertEqual(cf["total_inflows"], 600000.0)
        # Outflows: 30,000 (Rent) + 10,000 (Utilities) = 40,000
        self.assertEqual(cf["total_outflows"], 40000.0)
        # Net change = 600,000 - 40,000 = 560,000
        self.assertEqual(cf["net_change"], 560000.0)
        # Ending cash = 560,000
        self.assertEqual(cf["ending_cash"], 560000.0)

    def test_pdf_report_generation(self):
        """Verify all 4 financial statement PDF reports generate valid non-empty PDF files."""
        # 1. P&L PDF
        pl = generate_profit_loss(self.company_id)
        pl_path = generate_profit_loss_pdf(pl)
        self.created_temp_files.append(pl_path)
        self.assertTrue(os.path.exists(pl_path))
        self.assertGreater(os.path.getsize(pl_path), 1000)
        with open(pl_path, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

        # 2. Balance Sheet PDF
        bs = generate_balance_sheet(self.company_id)
        bs_path = generate_balance_sheet_pdf(bs)
        self.created_temp_files.append(bs_path)
        self.assertTrue(os.path.exists(bs_path))
        self.assertGreater(os.path.getsize(bs_path), 1000)
        with open(bs_path, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

        # 3. Trial Balance PDF
        tb = db.get_trial_balance(self.company_id)
        tb["company_name"] = "Test Enterprise"
        tb_path = generate_trial_balance_pdf(tb)
        self.created_temp_files.append(tb_path)
        self.assertTrue(os.path.exists(tb_path))
        self.assertGreater(os.path.getsize(tb_path), 1000)
        with open(tb_path, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

        # 4. Cash Flow PDF
        cf = generate_cash_flow(self.company_id)
        cf_path = generate_cash_flow_pdf(cf)
        self.created_temp_files.append(cf_path)
        self.assertTrue(os.path.exists(cf_path))
        self.assertGreater(os.path.getsize(cf_path), 1000)
        with open(cf_path, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

    def test_csv_report_exports(self):
        """Verify CSV export functionality for Profit & Loss, Balance Sheet, and Cash Flow."""
        temp_dir = tempfile.gettempdir()

        # P&L CSV
        pl = generate_profit_loss(self.company_id)
        pl_csv = os.path.join(temp_dir, f"test_pl_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
        self.created_temp_files.append(pl_csv)
        export_profit_loss_csv(pl, pl_csv)
        self.assertTrue(os.path.exists(pl_csv))
        with open(pl_csv, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("PROFIT & LOSS STATEMENT", content)
            self.assertIn("TOTAL OPERATING REVENUE", content)
            self.assertIn("150000.00", content)

        # Balance Sheet CSV
        bs = generate_balance_sheet(self.company_id)
        bs_csv = os.path.join(temp_dir, f"test_bs_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
        self.created_temp_files.append(bs_csv)
        export_balance_sheet_csv(bs, bs_csv)
        self.assertTrue(os.path.exists(bs_csv))
        with open(bs_csv, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("BALANCE SHEET", content)
            self.assertIn("TOTAL ASSETS", content)
            self.assertIn("610000.00", content)

        # Cash Flow CSV
        cf = generate_cash_flow(self.company_id)
        cf_csv = os.path.join(temp_dir, f"test_cf_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv")
        self.created_temp_files.append(cf_csv)
        export_cash_flow_csv(cf, cf_csv)
        self.assertTrue(os.path.exists(cf_csv))
        with open(cf_csv, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("CASH FLOW STATEMENT", content)
            self.assertIn("ENDING CASH & BANK BALANCE", content)
            self.assertIn("560000.00", content)


if __name__ == "__main__":
    unittest.main()
