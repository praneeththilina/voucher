"""
Tests for reconciliation_service batch operations, performance, and connection reuse.
"""

import os
import tempfile
import time
import unittest

import database as db
import reconciliation_service as recon


class TestReconciliationPerformance(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.DB_PATH = self.db_path
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = db.get_active_company_id(self.conn)
        coas = db.get_chart_of_accounts(self.company_id, conn=self.conn)
        self.cash_id = [a["id"] for a in coas if a["account_code"] == "1110"][0]
        self.exp_id = [a["id"] for a in coas if a["account_code"] == "5110"][0]

        self.rid = recon.configure(self.cash_id, company_id=self.company_id, conn=self.conn)
        self.sid = recon.start(self.rid, "2025-01-01", "2025-01-31", 0.0, 100000.0, conn=self.conn)

    def tearDown(self):
        if self.conn:
            self.conn.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_clear_all_batch_performance_and_correctness(self):
        # Create 100 journal entries
        with self.conn:
            for i in range(100):
                self.conn.execute(
                    "INSERT INTO journal_entries(company_id, entry_date, entry_number, reference, description, entry_type, is_posted) "
                    "VALUES(?, ?, ?, ?, ?, ?, 1)",
                    (self.company_id, "2025-01-15", f"JE{i}", f"REF{i}", f"Test {i}", "Voucher")
                )
                je_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                self.conn.execute(
                    "INSERT INTO journal_lines(entry_id, account_id, debit_amount, credit_amount, description) VALUES(?, ?, 500.0, 0.0, ?)",
                    (je_id, self.cash_id, f"Line {i}")
                )
                self.conn.execute(
                    "INSERT INTO journal_lines(entry_id, account_id, debit_amount, credit_amount, description) VALUES(?, ?, 0.0, 500.0, ?)",
                    (je_id, self.exp_id, f"Line {i}")
                )

        cands = recon.candidates(self.sid, conn=self.conn)
        self.assertEqual(len(cands), 100)
        self.assertTrue(all(not c["cleared"] for c in cands))

        # Measure clear_all timing
        t0 = time.perf_counter()
        recon.clear_all(self.sid, "Receipt", True, conn=self.conn)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000

        # Verify all 100 items cleared
        tot = recon.totals(self.sid, conn=self.conn)
        self.assertEqual(tot["count"], 100)
        self.assertEqual(tot["receipts"], 50000.0)
        self.assertLess(dur_ms, 500.0, f"clear_all took {dur_ms:.2f}ms, expected under 500ms")

        # Test batch unclearing
        recon.clear_all(self.sid, "Receipt", False, conn=self.conn)
        tot_after = recon.totals(self.sid, conn=self.conn)
        self.assertEqual(tot_after["count"], 0)
        self.assertEqual(tot_after["receipts"], 0.0)

    def test_auto_clear_imported_batch_performance_and_correctness(self):
        # Create 50 journal entries & matching imported statement lines
        with self.conn:
            for i in range(50):
                self.conn.execute(
                    "INSERT INTO journal_entries(company_id, entry_date, entry_number, reference, description, entry_type, is_posted) "
                    "VALUES(?, ?, ?, ?, ?, ?, 1)",
                    (self.company_id, "2025-01-15", f"JE{i}", f"REF{i}", f"Test {i}", "Voucher")
                )
                je_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                self.conn.execute(
                    "INSERT INTO journal_lines(entry_id, account_id, debit_amount, credit_amount, description) VALUES(?, ?, ?, 0.0, ?)",
                    (je_id, self.cash_id, 100.0 + i, f"Line {i}")
                )
                self.conn.execute(
                    "INSERT INTO journal_lines(entry_id, account_id, debit_amount, credit_amount, description) VALUES(?, ?, 0.0, ?, ?)",
                    (je_id, self.exp_id, 100.0 + i, f"Line {i}")
                )
                self.conn.execute(
                    "INSERT INTO reconciliation_statement_lines(company_id, reconciliation_account_id, transaction_date, description, reference, debit_amount, credit_amount, import_batch_id) "
                    "VALUES(?, ?, ?, ?, ?, 0.0, ?, ?)",
                    (self.company_id, self.rid, "2025-01-15", f"Test {i}", f"REF{i}", 100.0 + i, "batch1")
                )

        t0 = time.perf_counter()
        matched = recon.auto_clear_imported(self.sid, conn=self.conn)
        t1 = time.perf_counter()
        dur_ms = (t1 - t0) * 1000

        self.assertEqual(matched, 50)
        tot = recon.totals(self.sid, conn=self.conn)
        self.assertEqual(tot["count"], 50)
        self.assertLess(dur_ms, 500.0, f"auto_clear_imported took {dur_ms:.2f}ms, expected under 500ms")


if __name__ == "__main__":
    unittest.main()
