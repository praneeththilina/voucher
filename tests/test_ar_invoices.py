"""
Unit tests for Accounts Receivable (AR) Invoicing & Customer Billing (v3.8).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
from datetime import datetime, timedelta

import database as db
import invoice_printer
import sales_database as sales_db


class TestARInvoices(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ar.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations
        db.init_db()
        self.conn = db.get_connection()

        # Seed test customer
        self.customer_id = db.create_customer({
            "company_id": 1,
            "name": "Lanka Digital Solutions (Pvt) Ltd",
            "contact_person": "Kamal Perera",
            "phone": "+94 77 123 4567",
            "email": "kamal@lankadigital.lk",
            "payment_terms": 30
        }, conn=self.conn)

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_ar_invoice_and_auto_journal(self):
        """Test creating an AR customer invoice calculates totals and creates balanced double-entry."""
        rev_acct = db.get_account_by_code("4110", 1, conn=self.conn)
        self.assertIsNotNone(rev_acct)

        invoice_data = {
            "company_id": 1,
            "customer_id": self.customer_id,
            "invoice_number": "INV-2026-0001",
            "internal_ref": "PO-CLIENT-99",
            "invoice_date": "2026-05-10",
            "due_date": "2026-06-09",
            "discount_amount": 1000.0,
            "notes": "Annual software licensing and maintenance agreement."
        }
        lines = [
            {"description": "Enterprise Software License", "account_id": rev_acct["id"], "quantity": 1.0, "unit_price": 50000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 50000.0},
            {"description": "Implementation & Training", "account_id": rev_acct["id"], "quantity": 10.0, "unit_price": 2500.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 25000.0}
        ]
        # Total = 50000 + 25000 - 1000 = 74000.0
        inv_id = db.create_ar_invoice(invoice_data, lines, conn=self.conn)
        self.assertIsNotNone(inv_id)

        inv_record = db.get_ar_invoice(inv_id, conn=self.conn)
        self.assertIsNotNone(inv_record)
        h = inv_record["invoice"]
        self.assertEqual(h["subtotal"], 75000.0)
        self.assertEqual(h["discount_amount"], 1000.0)
        self.assertEqual(h["total_amount"], 74000.0)
        self.assertEqual(h["paid_amount"], 0.0)
        self.assertEqual(h["balance_due"], 74000.0)
        self.assertEqual(h["status"], "Draft")

        # Verify auto-journal entry in General Ledger:
        # DEBITS: AR 1210 for 74,000 + Discount for 1,000 = 75,000
        # CREDITS: Revenue 4110 for 75,000
        je = self.conn.execute(
            "SELECT * FROM journal_entries WHERE source_module = 'ar_invoice' AND source_id = ?",
            (inv_id,)
        ).fetchone()
        self.assertIsNotNone(je)
        self.assertEqual(je["reference"], "INV-2026-0001")

        jl = self.conn.execute("SELECT * FROM journal_lines WHERE entry_id = ?", (je["id"],)).fetchall()
        tot_deb = sum(l["debit_amount"] for l in jl)
        tot_cred = sum(l["credit_amount"] for l in jl)
        self.assertEqual(tot_deb, tot_cred)
        self.assertEqual(tot_deb, 75000.0)

    def test_record_ar_receipt_lifecycle(self):
        """Test recording partial and full customer payment receipts against an AR invoice."""
        inv_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": self.customer_id,
            "invoice_number": "INV-SETTLE-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "Consulting Milestone 1", "quantity": 1, "unit_price": 50000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 50000.0}
        ], conn=self.conn)

        inv = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv["status"], "Draft")
        self.assertEqual(inv["balance_due"], 50000.0)

        # 1. Partial Receipt (LKR 20,000)
        r1_id = db.record_ar_receipt({
            "invoice_id": inv_id,
            "receipt_date": "2026-06-15",
            "amount": 20000.0,
            "payment_method": "Bank Transfer",
            "reference": "TXN-BANK-101",
            "created_by": "Cashier"
        }, conn=self.conn)
        self.assertIsNotNone(r1_id)

        inv_part = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_part["paid_amount"], 20000.0)
        self.assertEqual(inv_part["balance_due"], 30000.0)
        self.assertEqual(inv_part["status"], "Partially Paid")

        # Verify receipt auto-journal
        je1 = self.conn.execute("SELECT * FROM journal_entries WHERE source_module = 'ar_receipt' AND source_id = ?", (r1_id,)).fetchone()
        self.assertIsNotNone(je1)
        jl1 = self.conn.execute("SELECT * FROM journal_lines WHERE entry_id = ?", (je1["id"],)).fetchall()
        self.assertEqual(sum(l["debit_amount"] for l in jl1), 20000.0)
        self.assertEqual(sum(l["credit_amount"] for l in jl1), 20000.0)

        # 2. Final Receipt (LKR 30,000)
        r2_id = db.record_ar_receipt({
            "invoice_id": inv_id,
            "receipt_date": "2026-06-25",
            "amount": 30000.0,
            "payment_method": "Cash",
            "reference": "REC-CASH-002",
            "created_by": "Cashier"
        }, conn=self.conn)
        self.assertIsNotNone(r2_id)

        inv_paid = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_paid["paid_amount"], 50000.0)
        self.assertEqual(inv_paid["balance_due"], 0.0)
        self.assertEqual(inv_paid["status"], "Paid")

    def test_delete_ar_receipt_reverses_balance(self):
        """Test deleting a receipt reverses the invoice balance and status."""
        inv_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": self.customer_id,
            "invoice_number": "INV-REV-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "Design Mockups", "quantity": 1, "unit_price": 20000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 20000.0}
        ], conn=self.conn)

        rid = db.record_ar_receipt({
            "invoice_id": inv_id,
            "amount": 20000.0,
            "payment_method": "Cash"
        }, conn=self.conn)

        inv = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv["status"], "Paid")

        # Delete receipt
        ok = db.delete_ar_receipt(rid, conn=self.conn)
        self.assertTrue(ok)

        inv_after = db.get_ar_invoice(inv_id, conn=self.conn)["invoice"]
        self.assertEqual(inv_after["paid_amount"], 0.0)
        self.assertEqual(inv_after["balance_due"], 20000.0)
        self.assertEqual(inv_after["status"], "Unpaid")

        # Ensure receipt journal entry was also deleted
        je = self.conn.execute("SELECT * FROM journal_entries WHERE source_module = 'ar_receipt' AND source_id = ?", (rid,)).fetchone()
        self.assertIsNone(je)

    def test_delete_ar_invoice_with_receipts_blocked(self):
        """Test deleting an invoice with receipts recorded is prevented."""
        inv_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": self.customer_id,
            "invoice_number": "INV-GUARD-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "Hardware Delivery", "quantity": 1, "unit_price": 10000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 10000.0}
        ], conn=self.conn)

        db.record_ar_receipt({
            "invoice_id": inv_id,
            "amount": 5000.0,
            "payment_method": "Cash"
        }, conn=self.conn)

        ok, msg = db.delete_ar_invoice(inv_id, conn=self.conn)
        self.assertFalse(ok)
        self.assertIn("receipt(s) recorded", msg)

    def test_ar_aging_report(self):
        """Test Accounts Receivable Aging calculations across overdue buckets."""
        today = datetime.now().date()
        date_current = (today + timedelta(days=15)).strftime("%Y-%m-%d")
        date_15_over = (today - timedelta(days=15)).strftime("%Y-%m-%d")
        date_45_over = (today - timedelta(days=45)).strftime("%Y-%m-%d")
        date_75_over = (today - timedelta(days=75)).strftime("%Y-%m-%d")
        date_100_over = (today - timedelta(days=100)).strftime("%Y-%m-%d")

        # Current (not due)
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-CUR", "invoice_date": "2026-01-01", "due_date": date_current
        }, [{"description": "Item 1", "quantity": 1, "unit_price": 10000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 10000.0}], conn=self.conn)

        # 1-30 days overdue
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-1-30", "invoice_date": "2026-01-01", "due_date": date_15_over
        }, [{"description": "Item 2", "quantity": 1, "unit_price": 20000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 20000.0}], conn=self.conn)

        # 31-60 days overdue
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-31-60", "invoice_date": "2026-01-01", "due_date": date_45_over
        }, [{"description": "Item 3", "quantity": 1, "unit_price": 30000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 30000.0}], conn=self.conn)

        # 61-90 days overdue
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-61-90", "invoice_date": "2026-01-01", "due_date": date_75_over
        }, [{"description": "Item 4", "quantity": 1, "unit_price": 40000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 40000.0}], conn=self.conn)

        # > 90 days overdue
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-90-PLUS", "invoice_date": "2026-01-01", "due_date": date_100_over
        }, [{"description": "Item 5", "quantity": 1, "unit_price": 50000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 50000.0}], conn=self.conn)

        report = db.get_ar_aging_report(company_id=1, conn=self.conn)
        t = report["totals"]

        self.assertEqual(t["current"], 10000.0)
        self.assertEqual(t["days_1_30"], 20000.0)
        self.assertEqual(t["days_31_60"], 30000.0)
        self.assertEqual(t["days_61_90"], 40000.0)
        self.assertEqual(t["days_over_90"], 50000.0)
        self.assertEqual(t["total_due"], 150000.0)

        custom = db.get_ar_aging_report(
            company_id=1,
            as_of_date=datetime.now().strftime("%Y-%m-%d"),
            bucket_days=30,
            bucket_count=6,
            conn=self.conn,
        )
        self.assertEqual(len(custom["bucket_definitions"]), 7)
        self.assertEqual(
            custom["bucket_definitions"][-1]["key"], "days_over_180"
        )
        self.assertEqual(custom["totals"]["days_61_90"], 40000.0)
        self.assertEqual(custom["totals"]["days_91_120"], 50000.0)
        self.assertEqual(custom["totals"]["days_over_180"], 0.0)

    def test_generate_ar_invoice_pdf(self):
        """Test customer invoice PDF rendering produces valid document."""
        inv_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": self.customer_id,
            "invoice_number": "INV-PDF-01",
            "invoice_date": "2026-07-01",
            "due_date": "2026-07-31"
        }, [
            {"description": "Network Infrastructure Setup", "quantity": 2.0, "unit_price": 35000.0, "tax_rate": 0.18, "tax_amount": 12600.0, "line_total": 82600.0}
        ], conn=self.conn)

        pdf_path = invoice_printer.generate_ar_invoice_pdf([inv_id])
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 1000)

        # Clean up generated PDF
        try:
            os.remove(pdf_path)
        except Exception:
            pass

    def test_custom_invoice_number_format(self):
        """Company templates produce unique date-aware invoice numbers."""
        sales_db.save_sales_preferences(1, {
            "inventory_enabled": False,
            "sales_tax_enabled": True,
            "discounts_enabled": True,
            "allow_negative_stock": False,
            "invoice_number_format": "{YY}{MM}_{COMPANY}_{EXTRA}_{NUMBER:04}",
            "invoice_company_prefix": "LSF",
            "invoice_number_extra": "AR",
            "invoice_number_start": "25",
        })
        first = db.get_next_ar_invoice_number(
            company_id=1, invoice_date="2026-04-10", conn=self.conn
        )
        self.assertEqual(first, "26APR_LSF_AR_0025")
        db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": first, "invoice_date": "2026-04-10",
            "due_date": "2026-05-10",
        }, [{
            "description": "Service", "quantity": 1,
            "unit_price": 1000, "tax_amount": 0,
        }], conn=self.conn)
        self.assertEqual(
            db.get_next_ar_invoice_number(
                company_id=1, invoice_date="2026-04-10", conn=self.conn
            ),
            "26APR_LSF_AR_0026",
        )

    def test_unapplied_receipts_apply_oldest_first(self):
        """Invoice credit uses compatible unapplied receipts oldest first."""
        invoice_id = db.create_ar_invoice({
            "company_id": 1, "customer_id": self.customer_id,
            "invoice_number": "INV-CREDIT-01",
            "invoice_date": "2026-09-01", "due_date": "2026-09-30",
            "status": "Unpaid",
        }, [{
            "description": "Annual service", "quantity": 1,
            "unit_price": 1000, "tax_amount": 0,
        }], conn=self.conn)
        first_payment = sales_db.create_customer_payment({
            "company_id": 1, "customer_id": self.customer_id,
            "payment_date": "2026-08-01", "amount": 300,
            "payment_method": "Cash", "reference": "ADV-OLD",
        }, conn=self.conn)
        second_payment = sales_db.create_customer_payment({
            "company_id": 1, "customer_id": self.customer_id,
            "payment_date": "2026-08-15", "amount": 400,
            "payment_method": "Cash", "reference": "ADV-NEW",
        }, conn=self.conn)
        applied = sales_db.apply_available_customer_credit(
            self.customer_id, invoice_id, 500, conn=self.conn,
            application_date="2026-09-01",
        )
        self.assertEqual(applied, 500)
        invoice = db.get_ar_invoice(invoice_id, conn=self.conn)["invoice"]
        self.assertEqual(invoice["paid_amount"], 500)
        self.assertEqual(invoice["balance_due"], 500)
        payments = {
            row["id"]: row for row in sales_db.get_customer_payments(
                1, self.customer_id, conn=self.conn
            )
        }
        self.assertEqual(payments[first_payment]["unapplied_amount"], 0)
        self.assertEqual(payments[second_payment]["unapplied_amount"], 200)
        entries = self.conn.execute(
            "SELECT id FROM journal_entries WHERE "
            "source_module = 'customer_payment_application'"
        ).fetchall()
        self.assertEqual(len(entries), 2)
        for entry in entries:
            lines = self.conn.execute(
                "SELECT debit_amount, credit_amount FROM journal_lines "
                "WHERE entry_id = ?", (entry["id"],)
            ).fetchall()
            self.assertAlmostEqual(
                sum(row["debit_amount"] for row in lines),
                sum(row["credit_amount"] for row in lines), places=2,
            )

if __name__ == "__main__":
    unittest.main()
