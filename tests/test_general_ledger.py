"""
Unit tests for General Ledger, Double-Entry Invariants, Trial Balance,
and Automated Voucher Journaling (v3.5).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db


class TestGeneralLedger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gl.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migrations 23 & 24)
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_24_tables(self):
        """Verify journal_entries and journal_lines tables exist with proper indexes."""
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("journal_entries", tables)
        self.assertIn("journal_lines", tables)

    def test_sequential_journal_entry_numbers(self):
        """Verify journal entries generate sequential numbers (e.g. JE-2026-0001)."""
        num1 = db.get_next_journal_entry_number(company_id=1, year=2026, conn=self.conn)
        self.assertEqual(num1, "JE-2026-0001")

        # Insert an entry
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        equity = db.get_account_by_code("3110", company_id=1, conn=self.conn)
        header = {
            "company_id": 1,
            "entry_number": num1,
            "entry_date": "2026-01-01",
            "entry_type": "Opening"
        }
        lines = [
            {"account_id": cash["id"], "debit_amount": 50000.0, "credit_amount": 0.0},
            {"account_id": equity["id"], "debit_amount": 0.0, "credit_amount": 50000.0}
        ]
        db.create_journal_entry(header, lines, conn=self.conn)

        num2 = db.get_next_journal_entry_number(company_id=1, year=2026, conn=self.conn)
        self.assertEqual(num2, "JE-2026-0002")

    def test_double_entry_balance_invariant_enforced(self):
        """Strictly assert that debits != credits raises a ValueError."""
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        exp = db.get_account_by_code("5210", company_id=1, conn=self.conn)

        header = {"company_id": 1, "entry_date": "2026-02-01"}
        unbalanced_lines = [
            {"account_id": exp["id"], "debit_amount": 1000.0, "credit_amount": 0.0},
            {"account_id": cash["id"], "debit_amount": 0.0, "credit_amount": 950.0}
        ]
        with self.assertRaises(ValueError) as ctx:
            db.create_journal_entry(header, unbalanced_lines, conn=self.conn)
        self.assertIn("unbalanced", str(ctx.exception).lower())

    def test_minimum_two_lines_and_positive_total_required(self):
        """Test that single lines or 0-amount lines are rejected."""
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        header = {"company_id": 1, "entry_date": "2026-02-01"}

        # Only 1 line
        with self.assertRaises(ValueError):
            db.create_journal_entry(header, [{"account_id": cash["id"], "debit_amount": 100.0, "credit_amount": 0.0}], conn=self.conn)

        # Zero amount
        with self.assertRaises(ValueError):
            db.create_journal_entry(header, [
                {"account_id": cash["id"], "debit_amount": 0.0, "credit_amount": 0.0},
                {"account_id": cash["id"], "debit_amount": 0.0, "credit_amount": 0.0}
            ], conn=self.conn)

    def test_general_ledger_running_balance(self):
        """
        Test running balance calculation for:
        - Asset (Normal Debit): Prior + Debits - Credits
        - Liability (Normal Credit): Prior + Credits - Debits
        """
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        sales = db.get_account_by_code("4110", company_id=1, conn=self.conn)
        rent = db.get_account_by_code("5210", company_id=1, conn=self.conn)

        # Entry 1: Sale of 20,000 cash -> Debit Cash 20,000, Credit Sales 20,000
        db.create_journal_entry(
            {"company_id": 1, "entry_date": "2026-03-01", "description": "Cash Sales"},
            [
                {"account_id": cash["id"], "debit_amount": 20000.0, "credit_amount": 0.0},
                {"account_id": sales["id"], "debit_amount": 0.0, "credit_amount": 20000.0}
            ],
            conn=self.conn
        )

        # Entry 2: Pay Rent 5,000 -> Debit Rent 5,000, Credit Cash 5,000
        db.create_journal_entry(
            {"company_id": 1, "entry_date": "2026-03-05", "description": "Office Rent"},
            [
                {"account_id": rent["id"], "debit_amount": 5000.0, "credit_amount": 0.0},
                {"account_id": cash["id"], "debit_amount": 0.0, "credit_amount": 5000.0}
            ],
            conn=self.conn
        )

        # Check GL for Cash
        cash_gl = db.get_general_ledger(company_id=1, account_id=cash["id"], conn=self.conn)
        self.assertEqual(len(cash_gl), 2)
        self.assertEqual(cash_gl[0]["running_balance"], 20000.0)
        self.assertEqual(cash_gl[1]["running_balance"], 15000.0)

        # Check GL for Sales (Normal Credit)
        sales_gl = db.get_general_ledger(company_id=1, account_id=sales["id"], conn=self.conn)
        self.assertEqual(len(sales_gl), 1)
        self.assertEqual(sales_gl[0]["running_balance"], 20000.0)

    def test_trial_balance_balanced(self):
        """Test that Trial Balance confirms debits == credits."""
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        equity = db.get_account_by_code("3110", company_id=1, conn=self.conn)
        rent = db.get_account_by_code("5210", company_id=1, conn=self.conn)

        db.create_journal_entry(
            {"company_id": 1, "entry_date": "2026-04-01"},
            [
                {"account_id": cash["id"], "debit_amount": 100000.0, "credit_amount": 0.0},
                {"account_id": equity["id"], "debit_amount": 0.0, "credit_amount": 100000.0}
            ],
            conn=self.conn
        )

        db.create_journal_entry(
            {"company_id": 1, "entry_date": "2026-04-10"},
            [
                {"account_id": rent["id"], "debit_amount": 12000.0, "credit_amount": 0.0},
                {"account_id": cash["id"], "debit_amount": 0.0, "credit_amount": 12000.0}
            ],
            conn=self.conn
        )

        tb = db.get_trial_balance(company_id=1, conn=self.conn)
        self.assertTrue(tb["is_balanced"])
        self.assertEqual(tb["difference"], 0.0)
        self.assertEqual(tb["total_debit"], 100000.0)
        self.assertEqual(tb["total_credit"], 100000.0)

    def test_auto_journal_for_voucher_lifecycle(self):
        """
        Verify that:
        1. create_voucher automatically generates a balanced journal entry.
        2. update_voucher automatically refreshes the journal entry.
        3. cancel_voucher marks the journal entry unposted (is_posted = 0).
        4. restore_voucher marks the journal entry posted again (is_posted = 1).
        5. permanently_delete_voucher deletes the journal entry.
        """
        # 1. Create Voucher
        v_data = {
            "company_id": 1,
            "date": "2026-05-01",
            "paid_to": "Metro City Office Supplies",
            "cash_given_by": "Manager",
            "payment_method": "Cash"
        }
        items = [
            {"description": "Paper and Pens", "category": "Office Stationery", "amount": 3500.0},
            {"description": "Office Electricity Bill", "category": "Utilities", "amount": 6500.0}
        ]
        vid = db.create_voucher(v_data, items, company_id=1)
        self.assertIsNotNone(vid)

        # Check journal entry exists for this voucher
        entry_row = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'voucher' AND source_id = ?",
            (vid,)
        ).fetchone()
        self.assertIsNotNone(entry_row)
        self.assertEqual(entry_row["is_posted"], 1)

        # Check journal lines: total debits == total credits == 10000.0
        lines = self.conn.execute(
            "SELECT * FROM journal_lines WHERE entry_id = ?",
            (entry_row["id"],)
        ).fetchall()
        tot_deb = sum(l["debit_amount"] for l in lines)
        tot_cred = sum(l["credit_amount"] for l in lines)
        self.assertEqual(tot_deb, 10000.0)
        self.assertEqual(tot_cred, 10000.0)

        # 2. Update Voucher
        v_data["paid_to"] = "Metro City Supplies Updated"
        items[0]["amount"] = 5500.0  # Total now 12000.0
        db.update_voucher(vid, v_data, items)

        lines_upd = self.conn.execute(
            "SELECT * FROM journal_lines WHERE entry_id = ?",
            (entry_row["id"],)
        ).fetchall()
        tot_deb_upd = sum(l["debit_amount"] for l in lines_upd)
        tot_cred_upd = sum(l["credit_amount"] for l in lines_upd)
        self.assertEqual(tot_deb_upd, 12000.0)
        self.assertEqual(tot_cred_upd, 12000.0)

        # 3. Cancel Voucher
        db.cancel_voucher(vid)
        entry_cancelled = self.conn.execute(
            "SELECT is_posted FROM journal_entries WHERE id = ?",
            (entry_row["id"],)
        ).fetchone()
        self.assertEqual(entry_cancelled["is_posted"], 0)

        # GL should exclude unposted entries
        gl_active = db.get_general_ledger(company_id=1, conn=self.conn)
        entry_ids_in_gl = [r["entry_id"] for r in gl_active]
        self.assertNotIn(entry_row["id"], entry_ids_in_gl)

        # 4. Restore Voucher
        db.restore_voucher(vid)
        entry_restored = self.conn.execute(
            "SELECT is_posted FROM journal_entries WHERE id = ?",
            (entry_row["id"],)
        ).fetchone()
        self.assertEqual(entry_restored["is_posted"], 1)

        # 5. Permanently Delete Voucher
        db.permanently_delete_voucher(vid)
        entry_deleted = self.conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?",
            (entry_row["id"],)
        ).fetchone()
        self.assertIsNone(entry_deleted)

        lines_deleted = self.conn.execute(
            "SELECT * FROM journal_lines WHERE entry_id = ?",
            (entry_row["id"],)
        ).fetchall()
        self.assertEqual(len(lines_deleted), 0)

    def test_backfill_historical_vouchers(self):
        """Test backfilling vouchers that existed prior to double-entry system."""
        # Insert a voucher directly via raw SQL without journal entry
        cur = self.conn.execute("""
            INSERT INTO vouchers (company_id, voucher_number, date, paid_to, cash_given_by, total_amount, payment_method, status)
            VALUES (1, 'V-HIST-001', '2026-01-15', 'Old Vendor', 'Manager', 8000.0, 'Cash', 'Active')
        """)
        raw_vid = cur.lastrowid
        self.conn.execute("""
            INSERT INTO line_items (voucher_id, description, category, amount)
            VALUES (?, 'Office Rent Jan', 'Rent', 8000.0)
        """, (raw_vid,))
        self.conn.commit()

        # Run backfill
        count = db.backfill_vouchers_to_journal(company_id=1, conn=self.conn)
        self.assertGreaterEqual(count, 1)

        # Check journal entry created
        je = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'voucher' AND source_id = ?",
            (raw_vid,)
        ).fetchone()
        self.assertIsNotNone(je)
        self.assertEqual(je["reference"], "V-HIST-001")

    def test_trial_balance_excludes_future_and_unposted_entries(self):
        """An as-of trial balance includes only posted entries through its date."""
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        equity = db.get_account_by_code("3110", company_id=1, conn=self.conn)
        future_id = db.create_journal_entry(
            {"company_id": 1, "entry_date": "2027-01-01"},
            [
                {
                    "account_id": cash["id"],
                    "debit_amount": 10000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": equity["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 10000.0,
                },
            ],
            conn=self.conn,
        )
        unposted_id = db.create_journal_entry(
            {"company_id": 1, "entry_date": "2026-01-01"},
            [
                {
                    "account_id": cash["id"],
                    "debit_amount": 5000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": equity["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 5000.0,
                },
            ],
            conn=self.conn,
        )
        self.conn.execute(
            "UPDATE journal_entries SET is_posted = 0 WHERE id = ?",
            (unposted_id,),
        )
        self.conn.commit()

        balance = db.get_trial_balance(
            company_id=1,
            as_of_date="2026-12-31",
            conn=self.conn,
        )
        self.assertEqual(balance["total_debit"], 0.0)
        self.assertEqual(balance["total_credit"], 0.0)
        self.assertNotEqual(future_id, unposted_id)
    def test_general_ledger_multi_account_and_entry_filters(self):
        """Report drill-down filters return only the requested source lines."""
        cash = db.get_account_by_code("1110", company_id=1, conn=self.conn)
        sales = db.get_account_by_code("4110", company_id=1, conn=self.conn)
        rent = db.get_account_by_code("5210", company_id=1, conn=self.conn)

        sale_entry_id = db.create_journal_entry(
            {
                "company_id": 1,
                "entry_date": "2026-06-01",
                "description": "Cash sale",
            },
            [
                {
                    "account_id": cash["id"],
                    "debit_amount": 25000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": sales["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 25000.0,
                },
            ],
            conn=self.conn,
        )
        db.create_journal_entry(
            {
                "company_id": 1,
                "entry_date": "2026-06-02",
                "description": "Rent payment",
            },
            [
                {
                    "account_id": rent["id"],
                    "debit_amount": 5000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": cash["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 5000.0,
                },
            ],
            conn=self.conn,
        )

        account_rows = db.get_general_ledger(
            company_id=1,
            account_ids=[cash["id"], sales["id"]],
            start_date="2026-06-01",
            end_date="2026-06-30",
            conn=self.conn,
        )
        self.assertEqual(len(account_rows), 3)
        self.assertEqual(
            {row["account_id"] for row in account_rows},
            {cash["id"], sales["id"]},
        )

        entry_rows = db.get_general_ledger(
            company_id=1,
            entry_ids=[sale_entry_id],
            conn=self.conn,
        )
        self.assertEqual(len(entry_rows), 2)
        self.assertEqual({row["entry_id"] for row in entry_rows}, {sale_entry_id})

if __name__ == "__main__":
    unittest.main()
