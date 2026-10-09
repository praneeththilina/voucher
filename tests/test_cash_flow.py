"""
tests/test_cash_flow.py
Unit tests for Cash Flow Statement generator in reports/cash_flow.py
"""

import os
import tempfile
import unittest
import database as db
from reports.cash_flow import generate_cash_flow, export_cash_flow_csv


class TestCashFlowReport(unittest.TestCase):
    def setUp(self):
        self.tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp_file.name
        self.tmp_file.close()

        db.configure_database(self.db_path)
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = db.get_active_company_id(self.conn)

    def tearDown(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_generate_cash_flow_empty(self):
        report = generate_cash_flow(company_id=self.company_id, start_date="2025-01-01", end_date="2025-12-31", conn=self.conn)
        self.assertEqual(report["company_id"], self.company_id)
        self.assertEqual(report["beginning_cash"], 0.0)
        self.assertEqual(report["ending_cash"], 0.0)
        self.assertEqual(report["total_inflows"], 0.0)
        self.assertEqual(report["total_outflows"], 0.0)
        self.assertEqual(report["net_change"], 0.0)

    def test_generate_cash_flow_with_transactions_and_breakdown(self):
        # Insert test accounts
        self.conn.execute(
            "INSERT INTO chart_of_accounts (company_id, account_code, account_name, account_type, sub_category, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (self.company_id, "1140", "Petty Cash", "Asset", "Cash & Bank")
        )
        self.conn.execute(
            "INSERT INTO chart_of_accounts (company_id, account_code, account_name, account_type, sub_category, is_active) VALUES (?, ?, ?, ?, ?, 1)",
            (self.company_id, "1150", "Operating Bank Account", "Asset", "Cash & Bank")
        )
        self.conn.commit()

        acct1 = self.conn.execute("SELECT id FROM chart_of_accounts WHERE company_id = ? AND account_code = '1140'", (self.company_id,)).fetchone()["id"]
        acct2 = self.conn.execute("SELECT id FROM chart_of_accounts WHERE company_id = ? AND account_code = '1150'", (self.company_id,)).fetchone()["id"]

        # Prior transaction (Beginning balance)
        self.conn.execute(
            "INSERT INTO journal_entries (company_id, entry_number, entry_date, description, is_posted) VALUES (?, ?, ?, ?, 1)",
            (self.company_id, "JE-001", "2024-12-31", "Prior balance")
        )
        je1_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 500.0, 0.0)",
            (je1_id, acct1)
        )

        # In-period transactions
        self.conn.execute(
            "INSERT INTO journal_entries (company_id, entry_number, entry_date, description, is_posted) VALUES (?, ?, ?, ?, 1)",
            (self.company_id, "JE-002", "2025-02-10", "Inflow to bank")
        )
        je2_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 1200.0, 0.0)",
            (je2_id, acct2)
        )

        self.conn.execute(
            "INSERT INTO journal_entries (company_id, entry_number, entry_date, description, is_posted) VALUES (?, ?, ?, ?, 1)",
            (self.company_id, "JE-003", "2025-03-15", "Outflow from petty cash")
        )
        je3_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            "INSERT INTO journal_lines (entry_id, account_id, debit_amount, credit_amount) VALUES (?, ?, 0.0, 150.0)",
            (je3_id, acct1)
        )
        self.conn.commit()

        report = generate_cash_flow(company_id=self.company_id, start_date="2025-01-01", end_date="2025-12-31", conn=self.conn)

        self.assertEqual(report["beginning_cash"], 500.0)
        self.assertEqual(report["total_inflows"], 1200.0)
        self.assertEqual(report["total_outflows"], 150.0)
        self.assertEqual(report["net_change"], 1050.0)
        self.assertEqual(report["ending_cash"], 1550.0)

        # Verify account breakdown map
        breakdown_dict = {b["code"]: b["balance"] for b in report["account_breakdown"]}
        self.assertEqual(breakdown_dict.get("1140"), 350.0)  # 500 - 150
        self.assertEqual(breakdown_dict.get("1150"), 1200.0)


if __name__ == "__main__":
    unittest.main()
