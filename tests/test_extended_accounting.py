"""Regression tests for full-page accounting additions and flexible payroll."""

import os
import tempfile
import shutil
import unittest

import database as db


class TestExtendedAccounting(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.temp_dir, "extended.db")
        self.original_path = db.DB_PATH
        db.DB_PATH = self.path
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_path
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_migration_37_adds_detail_types_and_payroll_configuration(self):
        with db.get_connection() as conn:
            account_columns = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(chart_of_accounts)"
                ).fetchall()
            }
            employee_columns = {
                row[1] for row in conn.execute(
                    "PRAGMA table_info(employees)"
                ).fetchall()
            }
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        self.assertIn("detail_type", account_columns)
        self.assertIn("pay_basis", employee_columns)
        self.assertIn("payroll_components", tables)
        self.assertIn("staff_loans", tables)
        self.assertGreaterEqual(len(db.get_payroll_components(1)), 6)

    def test_transfer_posts_debit_destination_and_credit_source(self):
        source = db.get_account_by_code("1120", 1)
        target = db.get_account_by_code("1110", 1)
        entry_id = db.create_account_transfer(
            company_id=1,
            transfer_date="2026-10-08",
            source_account_id=source["id"],
            target_account_id=target["id"],
            amount=2500,
            reference="TR-001",
        )
        with db.get_connection() as conn:
            rows = conn.execute(
                "SELECT account_id, debit_amount, credit_amount "
                "FROM journal_lines WHERE entry_id = ? ORDER BY line_order",
                (entry_id,),
            ).fetchall()
        self.assertEqual(rows[0]["account_id"], target["id"])
        self.assertEqual(rows[0]["debit_amount"], 2500)
        self.assertEqual(rows[1]["account_id"], source["id"])
        self.assertEqual(rows[1]["credit_amount"], 2500)

    def test_credit_card_payment_requires_card_liability(self):
        card_id = db.create_account({
            "company_id": 1,
            "account_code": "2410",
            "account_name": "Business Credit Card",
            "account_type": "Liability",
            "sub_category": "Credit Card",
            "detail_type": "Credit Card",
        })
        source = db.get_account_by_code("1120", 1)
        entry_id = db.create_account_transfer(
            company_id=1,
            transfer_date="2026-10-08",
            source_account_id=source["id"],
            target_account_id=card_id,
            amount=1000,
            transfer_type="credit_card_payment",
        )
        self.assertGreater(entry_id, 0)

    def test_staff_loan_posts_and_payroll_reduces_balance(self):
        employee_id = db.create_employee({
            "company_id": 1,
            "full_name": "Loan Employee",
            "basic_salary": 100000,
        })
        loan_asset_id = db.create_account({
            "company_id": 1,
            "account_code": "1260",
            "account_name": "Staff Loan Receivable - Security Division",
            "account_type": "Asset",
            "sub_category": "Other Current Assets",
        })
        bank = db.get_account_by_code("1120", 1)
        loan_id = db.create_staff_loan({
            "company_id": 1,
            "employee_id": employee_id,
            "loan_date": "2026-10-01",
            "principal": 5000,
            "installment_amount": 1000,
            "asset_account_id": loan_asset_id,
            "payment_account_id": bank["id"],
        })
        db.create_payroll_run(
            {"company_id": 1, "pay_period": "2026-10", "run_date": "2026-10-31"},
            [{
                "employee_id": employee_id,
                "basic_salary": 100000,
                "other_deductions": 1000,
                "staff_loan_deduction": 1000,
            }],
        )
        loan = next(row for row in db.get_staff_loans(1) if row["id"] == loan_id)
        self.assertEqual(loan["outstanding_balance"], 4000)
        with db.get_connection() as conn:
            repayment = conn.execute(
                "SELECT amount FROM staff_loan_repayments WHERE loan_id = ?",
                (loan_id,),
            ).fetchone()
        self.assertEqual(repayment["amount"], 1000)
    def test_sri_lanka_statutory_pay_calculation(self):
        employee = {
            "company_id": 1,
            "pay_basis": "Per Shift",
            "pay_rate": 5000,
            "standard_units": 30,
            "epf_eligible": 1,
            "apit_enabled": 1,
        }
        result = db.calculate_employee_pay(employee)
        self.assertEqual(result["basic_salary"], 150000)
        self.assertEqual(result["epf_employee"], 12000)
        self.assertEqual(result["epf_employer"], 18000)
        self.assertEqual(result["etf_employer"], 4500)
        self.assertEqual(result["tax_deduction"], 0)
        self.assertEqual(db.calculate_sl_apit_monthly(200000), 3000)


if __name__ == "__main__":
    unittest.main()