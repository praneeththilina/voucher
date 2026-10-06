"""
Unit tests for Accounts Payable (AP) Invoices, Double-Entry Journal Integration,
Payment Settlements, Aging Reports, and PDF generation (v3.5).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime, timedelta
import database as db
import invoice_printer


class TestAPInvoices(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ap.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migration 25)
        db.init_db()
        self.conn = db.get_connection()

        # Create a test supplier
        self.supplier_id = db.create_supplier({
            "company_id": 1,
            "name": "United Paper Mills",
            "contact_person": "Kamal Perera",
            "phone": "+94 11 987 6543",
            "email": "kamal@unitedpaper.lk",
            "tax_id": "VAT-555666777",
            "payment_terms": 30
        }, conn=self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_ap_invoice_and_auto_journal(self):
        """Test creating an AP invoice calculates totals and creates balanced double-entry."""
        invoice_data = {
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "invoice_number": "INV-2026-001",
            "internal_ref": "PO-99",
            "invoice_date": "2026-05-01",
            "due_date": "2026-05-31",
            "discount_amount": 500.0,
            "currency": "LKR",
            "notes": "Office paper reams"
        }
        exp_acct = db.get_account_by_code("5410", company_id=1, conn=self.conn)  # Office Supplies
        lines = [
            {"description": "A4 Paper 80gsm (10 boxes)", "account_id": exp_acct["id"], "quantity": 10.0, "unit_price": 2000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 20000.0},
            {"description": "Envelopes Box", "account_id": exp_acct["id"], "quantity": 5.0, "unit_price": 1000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 5000.0}
        ]
        # Total = 20000 + 5000 - 500 = 24500.0
        inv_id = db.create_ap_invoice(invoice_data, lines, conn=self.conn)
        self.assertIsNotNone(inv_id)

        inv_record = db.get_ap_invoice(inv_id, conn=self.conn)
        self.assertIsNotNone(inv_record)
        h = inv_record["invoice"]
        self.assertEqual(h["subtotal"], 25000.0)
        self.assertEqual(h["discount_amount"], 500.0)
        self.assertEqual(h["total_amount"], 24500.0)
        self.assertEqual(h["paid_amount"], 0.0)
        self.assertEqual(h["balance_due"], 24500.0)
        self.assertEqual(h["status"], "Unpaid")

        # Verify auto-journal entry in General Ledger:
        # DEBIT: Expense 5410 for 25,000 (lines)
        # CREDIT: Accounts Payable 2110 for 24,500
        je = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'ap_invoice' AND source_id = ?",
            (inv_id,)
        ).fetchone()
        self.assertIsNotNone(je)
        self.assertEqual(je["reference"], "INV-2026-001")

        jl = self.conn.execute("SELECT * FROM journal_lines WHERE entry_id = ?", (je["id"],)).fetchall()
        tot_deb = sum(l["debit_amount"] for l in jl)
        tot_cred = sum(l["credit_amount"] for l in jl)
        self.assertEqual(tot_deb, tot_cred)

    def test_record_ap_payment_lifecycle(self):
        """Test recording partial and full payments against an AP invoice."""
        inv_id = db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "invoice_number": "INV-SETTLE-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "Raw Material Batch", "quantity": 1, "unit_price": 50000.0, "line_total": 50000.0}
        ], conn=self.conn)

        # 1. Partial payment: LKR 20,000 via Bank Transfer
        pmt1_id = db.record_ap_payment({
            "invoice_id": inv_id,
            "amount": 20000.0,
            "payment_date": "2026-06-10",
            "payment_method": "Bank Transfer",
            "reference": "TXN-88899"
        }, conn=self.conn)
        self.assertIsNotNone(pmt1_id)

        inv_p1 = db.get_ap_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_p1["paid_amount"], 20000.0)
        self.assertEqual(inv_p1["balance_due"], 30000.0)
        self.assertEqual(inv_p1["status"], "Partially Paid")

        # Verify payment auto-journal (Debit AP 2110, Credit Bank 1120)
        je_p1 = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'ap_payment' AND source_id = ?",
            (pmt1_id,)
        ).fetchone()
        self.assertIsNotNone(je_p1)

        # 2. Remaining payment: LKR 30,000 via Cash
        pmt2_id = db.record_ap_payment({
            "invoice_id": inv_id,
            "amount": 30000.0,
            "payment_date": "2026-06-25",
            "payment_method": "Cash"
        }, conn=self.conn)

        inv_p2 = db.get_ap_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_p2["paid_amount"], 50000.0)
        self.assertEqual(inv_p2["balance_due"], 0.0)
        self.assertEqual(inv_p2["status"], "Paid")

        # 3. Delete pmt2 -> invoice reverts to Partially Paid
        db.delete_ap_payment(pmt2_id, conn=self.conn)
        inv_rev = db.get_ap_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_rev["paid_amount"], 20000.0)
        self.assertEqual(inv_rev["status"], "Partially Paid")

    def test_delete_ap_invoice_safeguard(self):
        """Test that invoices with recorded payments cannot be deleted."""
        inv_id = db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "invoice_number": "INV-DELETE-GUARD",
            "invoice_date": "2026-07-01",
            "due_date": "2026-07-31"
        }, [{"description": "Item", "quantity": 1, "unit_price": 10000.0, "line_total": 10000.0}], conn=self.conn)

        db.record_ap_payment({
            "invoice_id": inv_id,
            "amount": 5000.0,
            "payment_date": "2026-07-15"
        }, conn=self.conn)

        # Attempting delete must fail
        ok, msg = db.delete_ap_invoice(inv_id, conn=self.conn)
        self.assertFalse(ok)
        self.assertIn("payment(s) recorded", msg)

    def test_ap_aging_report_buckets(self):
        """Test AP aging buckets categorization."""
        as_of = "2026-08-01"
        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()

        # 1. Current (Due 2026-08-15) -> 10,000
        db.create_ap_invoice({
            "company_id": 1, "supplier_id": self.supplier_id, "invoice_number": "INV-CURR",
            "invoice_date": "2026-07-15", "due_date": "2026-08-15"
        }, [{"description": "Item", "quantity": 1, "unit_price": 10000.0, "line_total": 10000.0}], conn=self.conn)

        # 2. 1-30 days overdue (Due 2026-07-20 -> 12 days overdue) -> 15,000
        db.create_ap_invoice({
            "company_id": 1, "supplier_id": self.supplier_id, "invoice_number": "INV-1-30",
            "invoice_date": "2026-06-20", "due_date": "2026-07-20"
        }, [{"description": "Item", "quantity": 1, "unit_price": 15000.0, "line_total": 15000.0}], conn=self.conn)

        # 3. 31-60 days overdue (Due 2026-06-15 -> 47 days overdue) -> 20,000
        db.create_ap_invoice({
            "company_id": 1, "supplier_id": self.supplier_id, "invoice_number": "INV-31-60",
            "invoice_date": "2026-05-15", "due_date": "2026-06-15"
        }, [{"description": "Item", "quantity": 1, "unit_price": 20000.0, "line_total": 20000.0}], conn=self.conn)

        # 4. Over 90 days overdue (Due 2026-03-01 -> 153 days overdue) -> 25,000
        db.create_ap_invoice({
            "company_id": 1, "supplier_id": self.supplier_id, "invoice_number": "INV-OVER-90",
            "invoice_date": "2026-02-01", "due_date": "2026-03-01"
        }, [{"description": "Item", "quantity": 1, "unit_price": 25000.0, "line_total": 25000.0}], conn=self.conn)

        aging = db.get_ap_aging_report(company_id=1, as_of_date=as_of, conn=self.conn)
        totals = aging["totals"]

        self.assertEqual(totals["current"], 10000.0)
        self.assertEqual(totals["days_1_30"], 15000.0)
        self.assertEqual(totals["days_31_60"], 20000.0)
        self.assertEqual(totals["days_over_90"], 25000.0)
        self.assertEqual(totals["total_due"], 70000.0)

    def test_invoice_pdf_generation(self):
        """Test generating an AP invoice PDF using invoice_printer."""
        inv_id = db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "invoice_number": "INV-PDF-TEST",
            "invoice_date": "2026-09-01",
            "due_date": "2026-09-30"
        }, [
            {"description": "Computer Monitors 27-inch", "quantity": 2, "unit_price": 45000.0, "tax_amount": 0.0, "line_total": 90000.0}
        ], conn=self.conn)

        pdf_path = invoice_printer.generate_ap_invoice_pdf([inv_id])
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 500)


if __name__ == "__main__":
    unittest.main()
