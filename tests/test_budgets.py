"""
tests/test_budgets.py
Unit tests for Budgets & Variance Analytics Module (v4.0).
Tests setting and retrieving monthly/annual budgets, variance calculations
against General Ledger transactions and vouchers, burn rate evaluations,
ReportLab PDF report generation, and company cascade deletion.
"""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
from reports.budget_vs_actual import generate_budget_vs_actual_pdf, export_budget_vs_actual_csv


class TestBudgets(unittest.TestCase):
    """Test suite verifying Account Budgets and Budget vs Actual Variance reporting."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = 1
        self.created_temp_files = []

    def tearDown(self):
        for fpath in self.created_temp_files:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        db.DB_PATH = self.orig_db_path

    def test_set_and_get_account_budget(self):
        """Test setting, upserting, and retrieving monthly and annual budgets."""
        # Find Rent Expense account (5200)
        coas = db.get_chart_of_accounts(self.company_id)
        rent_acct = [a for a in coas if "rent" in a["account_name"].lower()][0]
        aid = rent_acct["id"]

        bid = db.set_account_budget(
            company_id=self.company_id,
            account_id=aid,
            year=2026,
            month=10,
            amount=150000.0,
            notes="October Office Rent Allocation"
        )
        self.assertGreater(bid, 0)

        # Retrieve
        b = db.get_account_budget(self.company_id, aid, 2026, 10)
        self.assertIsNotNone(b)
        self.assertEqual(b["budget_amount"], 150000.0)
        self.assertEqual(b["notes"], "October Office Rent Allocation")

        # Upsert / update same month
        db.set_account_budget(
            company_id=self.company_id,
            account_id=aid,
            year=2026,
            month=10,
            amount=165000.0,
            notes="Adjusted with service charge"
        )
        updated = db.get_account_budget(self.company_id, aid, 2026, 10)
        self.assertEqual(updated["budget_amount"], 165000.0)
        self.assertEqual(updated["notes"], "Adjusted with service charge")

        # Period query
        monthly_list = db.get_budgets_for_period(self.company_id, 2026, 10)
        self.assertEqual(len(monthly_list), 1)
        self.assertEqual(monthly_list[0]["account_id"], aid)

    def test_delete_account_budget(self):
        """Test deleting a budget allocation."""
        coas = db.get_chart_of_accounts(self.company_id)
        aid = coas[0]["id"]

        db.set_account_budget(self.company_id, aid, 2026, 5, 50000.0)
        self.assertIsNotNone(db.get_account_budget(self.company_id, aid, 2026, 5))

        ok = db.delete_account_budget(self.company_id, aid, 2026, 5)
        self.assertTrue(ok)
        self.assertIsNone(db.get_account_budget(self.company_id, aid, 2026, 5))

    def test_generate_budget_vs_actual_monthly(self):
        """Test monthly budget vs actual variance calculation with favorable and exceeded outcomes."""
        coas = db.get_chart_of_accounts(self.company_id)
        # Rent (e.g. 5200) and Travel (e.g. 5300)
        rent_acct = [a for a in coas if "rent" in a["account_name"].lower()][0]
        travel_acct = [a for a in coas if "travel" in a["account_name"].lower()][0]

        # Set Budgets for October 2026:
        # Rent Budget = 100,000
        # Travel Budget = 20,000
        db.set_account_budget(self.company_id, rent_acct["id"], 2026, 10, 100000.0)
        db.set_account_budget(self.company_id, travel_acct["id"], 2026, 10, 20000.0)

        # Record Actual Spending:
        # 1. Rent: Journal entry for 70,000 (Within budget at 70% utilization, 30,000 remaining)
        bank_acct = [a for a in coas if a["account_code"] == "1120"][0]
        db.create_journal_entry({
            "company_id": self.company_id,
            "entry_date": "2026-10-05",
            "reference": "RENT-OCT",
            "description": "October Office Lease Payment",
            "is_posted": 1,
        }, [
            {"account_id": rent_acct["id"], "debit_amount": 70000.0, "credit_amount": 0.0},
            {"account_id": bank_acct["id"], "debit_amount": 0.0, "credit_amount": 70000.0},
        ])

        # 2. Travel: Voucher for 25,000 (Exceeded budget by 5,000, 125% burn)
        v_data = {
            "company_id": self.company_id,
            "date": "2026-10-12",
            "paid_to": "Airlines & Cabs",
            "cash_given_by": "Cashier",
            "spent_by": "Sales Rep",
            "bill_status": "Received",
            "payment_method": "Cash",
        }
        db.create_voucher(v_data, [
            {"description": "Client visit flights", "category": "Travel", "amount": 25000.0}
        ])

        # Compute October 2026 Variance Report
        rep = db.generate_budget_vs_actual(self.company_id, 2026, 10)
        self.assertIsNotNone(rep)
        self.assertEqual(rep["year"], 2026)
        self.assertEqual(rep["month"], 10)

        # Total Budget = 120,000, Total Actual = 95,000 (70k + 25k)
        self.assertEqual(rep["total_budget"], 120000.0)
        self.assertEqual(rep["total_actual"], 95000.0)
        self.assertEqual(rep["total_variance"], 25000.0)

        lines_by_id = {l["account_id"]: l for l in rep["lines"]}
        self.assertIn(rent_acct["id"], lines_by_id)
        self.assertIn(travel_acct["id"], lines_by_id)

        r_line = lines_by_id[rent_acct["id"]]
        self.assertEqual(r_line["budget_amount"], 100000.0)
        self.assertEqual(r_line["actual_amount"], 70000.0)
        self.assertEqual(r_line["variance"], 30000.0)
        self.assertEqual(r_line["status"], "Within Budget")

        t_line = lines_by_id[travel_acct["id"]]
        self.assertEqual(t_line["budget_amount"], 20000.0)
        self.assertEqual(t_line["actual_amount"], 25000.0)
        self.assertEqual(t_line["variance"], -5000.0)
        self.assertEqual(t_line["status"], "Exceeded")

    def test_generate_budget_vs_actual_annual(self):
        """Test full-year annual aggregation of monthly budgets."""
        coas = db.get_chart_of_accounts(self.company_id)
        rent_acct = [a for a in coas if "rent" in a["account_name"].lower()][0]
        aid = rent_acct["id"]

        # Set 50,000 in Jan, Feb, Mar (Total = 150,000)
        db.set_account_budget(self.company_id, aid, 2026, 1, 50000.0)
        db.set_account_budget(self.company_id, aid, 2026, 2, 50000.0)
        db.set_account_budget(self.company_id, aid, 2026, 3, 50000.0)

        rep = db.generate_budget_vs_actual(self.company_id, 2026, month=0)
        self.assertEqual(rep["period_label"], "Full Year 2026")

        rent_lines = [l for l in rep["lines"] if l["account_id"] == aid]
        self.assertEqual(len(rent_lines), 1)
        self.assertEqual(rent_lines[0]["budget_amount"], 150000.0)

    def test_budget_vs_actual_pdf_generation(self):
        """Test ReportLab PDF export for budget variance report."""
        coas = db.get_chart_of_accounts(self.company_id)
        aid = coas[0]["id"]
        db.set_account_budget(self.company_id, aid, 2026, 10, 80000.0)

        rep = db.generate_budget_vs_actual(self.company_id, 2026, 10)

        fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.created_temp_files.append(out_pdf)

        res_path = generate_budget_vs_actual_pdf(rep, output_path=out_pdf)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 2500)

    def test_company_cascade_deletion(self):
        """Test that company cascade delete properly removes budget entries."""
        c2_id = db.create_company("Budget Test Co 2")
        coas = db.get_chart_of_accounts(c2_id)
        aid = coas[0]["id"]

        db.set_account_budget(c2_id, aid, 2026, 1, 100000.0)
        self.assertIsNotNone(db.get_account_budget(c2_id, aid, 2026, 1))

        # Delete company 2
        ok = db.delete_company(c2_id)
        self.assertTrue(ok)

        # Verify budgets clean
        b_list = db.get_budgets_for_period(c2_id, 2026, 1)
        self.assertEqual(len(b_list), 0)

    def test_export_budget_vs_actual_csv(self):
        """Test CSV export for budget vs actual variance report with sanitization."""
        coas = db.get_chart_of_accounts(self.company_id)
        rent_acct = [a for a in coas if "rent" in a["account_name"].lower()][0]
        aid = rent_acct["id"]

        # Set budget and update account name with potentially dangerous CSV formula string
        db.set_account_budget(self.company_id, aid, 2026, 10, 150000.0)
        conn = db.get_connection()
        conn.execute("UPDATE chart_of_accounts SET account_name = '=1+1 Rent Account' WHERE id = ?", (aid,))
        conn.commit()
        conn.close()

        rep = db.generate_budget_vs_actual(self.company_id, 2026, 10)

        # Test 1: Passing report dict
        fd, out_csv1 = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.created_temp_files.append(out_csv1)

        res_path1 = export_budget_vs_actual_csv(rep, output_path=out_csv1)
        self.assertTrue(os.path.exists(res_path1))

        with open(res_path1, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("BUDGET VS ACTUAL VARIANCE STATEMENT", content)
        self.assertIn("Total Allocated Budget", content)
        self.assertIn("150000.00", content)
        # Verify CSV formula injection protection prefix
        self.assertIn("'=1+1 Rent Account", content)

        # Test 2: Passing company_id, year, month
        fd, out_csv2 = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.created_temp_files.append(out_csv2)

        res_path2 = export_budget_vs_actual_csv(self.company_id, output_path=out_csv2, year=2026, month=10)
        self.assertTrue(os.path.exists(res_path2))


if __name__ == "__main__":
    unittest.main()
