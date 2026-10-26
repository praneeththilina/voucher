"""Unit and integration tests for Customer Credit Notes (AR Memos)."""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
import sales_database as sales_db


class TestCustomerCreditNotes(unittest.TestCase):

    def setUp(self):
        # Create isolated temporary database for each test
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.configure_database(self.db_path)
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = db.get_active_company_id(self.conn)

        # Create test customer
        self.customer_id = db.create_customer(
            {"name": "Acme Global Solutions", "email": "billing@acme.com", "payment_terms": 30},
            conn=self.conn
        )

    def tearDown(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_credit_note_numbering_sequence(self):
        year = datetime.now().year
        cn1 = sales_db.get_next_credit_note_number(company_id=self.company_id, conn=self.conn)
        self.assertEqual(cn1, f"CN-{year}-0001")

        cn_id = sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "amount": 100.0, "reason": "Test CN"},
            company_id=self.company_id,
            conn=self.conn
        )
        self.assertTrue(cn_id > 0)

        cn2 = sales_db.get_next_credit_note_number(company_id=self.company_id, conn=self.conn)
        self.assertEqual(cn2, f"CN-{year}-0002")

    def test_create_credit_note_validation_and_gl_journal(self):
        # Reject non-positive amounts
        with self.assertRaises(ValueError):
            sales_db.create_customer_credit_note(
                {"customer_id": self.customer_id, "amount": 0.0},
                company_id=self.company_id,
                conn=self.conn
            )

        cn_id = sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "amount": 250.0, "reason": "Damaged goods return"},
            company_id=self.company_id,
            conn=self.conn
        )
        cn = sales_db.get_customer_credit_note(cn_id, conn=self.conn)
        self.assertIsNotNone(cn)
        self.assertEqual(cn["customer_id"], self.customer_id)
        self.assertEqual(cn["amount"], 250.0)
        self.assertEqual(cn["applied_amount"], 0.0)
        self.assertEqual(cn["unapplied_amount"], 250.0)
        self.assertEqual(cn["status"], "issued")

        # Verify General Ledger auto-journal
        je = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'customer_credit_note' AND source_id = ?",
            (cn_id,)
        ).fetchone()
        self.assertIsNotNone(je)
        self.assertEqual(je["entry_type"], "Credit Note")

        lines = self.conn.execute(
            "SELECT * FROM journal_lines WHERE entry_id = ?", (je["id"],)
        ).fetchall()
        self.assertEqual(len(lines), 2)
        debits = sum(float(l["debit_amount"]) for l in lines)
        credits = sum(float(l["credit_amount"]) for l in lines)
        self.assertEqual(debits, 250.0)
        self.assertEqual(credits, 250.0)

    def test_apply_credit_note_to_ar_invoice(self):
        # Create an open AR invoice for 500.0
        inv_id = db.create_ar_invoice(
            {
                "company_id": self.company_id,
                "customer_id": self.customer_id,
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
                "notes": "Test Sales Invoice",
            },
            [{"description": "Consulting Services", "quantity": 1, "unit_price": 500.0}],
            conn=self.conn
        )

        inv = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv["total_amount"], 500.0)
        self.assertEqual(inv["paid_amount"], 0.0)

        # Create credit note for 200.0
        cn_id = sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "amount": 200.0, "reason": "Discount allowance"},
            company_id=self.company_id,
            conn=self.conn
        )

        # Apply credit note to invoice
        ok, msg = sales_db.apply_customer_credit_note(cn_id, inv_id, 200.0, conn=self.conn)
        self.assertTrue(ok)

        # Check updated invoice status
        inv_after = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_after["paid_amount"], 200.0)
        self.assertEqual(inv_after["status"], "Partially Paid")

        # Check updated credit note status
        cn_after = sales_db.get_customer_credit_note(cn_id, conn=self.conn)
        self.assertEqual(cn_after["applied_amount"], 200.0)
        self.assertEqual(cn_after["unapplied_amount"], 0.0)
        self.assertEqual(cn_after["status"], "applied")

    def test_void_customer_credit_note(self):
        cn_id = sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "amount": 100.0, "reason": "Accidental issuance"},
            company_id=self.company_id,
            conn=self.conn
        )

        ok, msg = sales_db.void_customer_credit_note(cn_id, conn=self.conn)
        self.assertTrue(ok)

        cn = sales_db.get_customer_credit_note(cn_id, conn=self.conn)
        self.assertEqual(cn["status"], "void")

        # GL entries should be deleted
        je_count = self.conn.execute(
            "SELECT COUNT(*) FROM journal_entries WHERE source_module = 'customer_credit_note' AND source_id = ?",
            (cn_id,)
        ).fetchone()[0]
        self.assertEqual(je_count, 0)

    def test_customer_statement_integration(self):
        # Create invoice
        db.create_ar_invoice(
            {
                "company_id": self.company_id,
                "customer_id": self.customer_id,
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
            },
            [{"description": "Product A", "quantity": 1, "unit_price": 1000.0}],
            conn=self.conn
        )

        # Create credit note
        sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "credit_note_date": "2026-10-05", "amount": 200.0, "reason": "Return of defective unit"},
            company_id=self.company_id,
            conn=self.conn
        )

        stmt = db.get_customer_statement(self.customer_id, conn=self.conn)
        self.assertEqual(len(stmt["entries"]), 2)

        inv_entry = stmt["entries"][0]
        cn_entry = stmt["entries"][1]

        self.assertEqual(inv_entry["entry_type"], "Invoice")
        self.assertEqual(inv_entry["debit"], 1000.0)
        self.assertEqual(inv_entry["running_balance"], 1000.0)

        self.assertEqual(cn_entry["entry_type"], "Credit Note")
        self.assertEqual(cn_entry["credit"], 200.0)
        self.assertEqual(cn_entry["running_balance"], 800.0)

    def test_export_credit_notes_to_csv(self):
        sales_db.create_customer_credit_note(
            {"customer_id": self.customer_id, "amount": 150.0, "reason": "CSV Test CN"},
            company_id=self.company_id,
            conn=self.conn
        )

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            ok = sales_db.export_customer_credit_notes_to_csv(tmp_path, company_id=self.company_id, conn=self.conn)
            self.assertTrue(ok)

            with open(tmp_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            self.assertIn("Customer Credit Notes Register", content)
            self.assertIn("Acme Global Solutions", content)
            self.assertIn("150.00", content)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
