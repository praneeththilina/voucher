"""
tests/test_customer_statement.py
Unit tests for Customer Statement & Accounts Receivable (AR) Ledger functions,
CSV export, PDF generation, and UI CustomerStatementDialog.
"""

import os
import tempfile
import unittest
import database as db
import printer


class TestCustomerStatementBackend(unittest.TestCase):
    """Test database customer statement calculation, running balances, and CSV export."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = db.create_company("Acme Holdings")
        self.customer_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Global Tech Ltd",
            "contact_person": "Jane Doe",
            "phone": "+94771234567",
            "email": "jane@globaltech.com",
            "address": "123 Business Park, Colombo",
            "tax_id": "VAT-987654",
            "credit_limit": 100000.0,
            "payment_terms": 30
        })

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_customer_statement_running_balance(self):
        """Verify invoices and receipts produce accurate running balances and totals."""
        inv1_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.customer_id,
            "invoice_number": "INV-1001",
            "invoice_date": "2025-01-01",
            "due_date": "2025-01-31",
            "notes": "Software Services",
            "total_amount": 1000.0,
            "subtotal": 1000.0
        }, [{"description": "Software Services", "quantity": 1, "unit_price": 1000.0, "amount": 1000.0}])

        inv2_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.customer_id,
            "invoice_number": "INV-1002",
            "invoice_date": "2025-01-10",
            "due_date": "2025-02-10",
            "notes": "Hardware Supply",
            "total_amount": 500.0,
            "subtotal": 500.0
        }, [{"description": "Hardware", "quantity": 1, "unit_price": 500.0, "amount": 500.0}])

        db.record_ar_receipt({
            "invoice_id": inv1_id,
            "amount": 600.0,
            "payment_method": "Bank Transfer",
            "receipt_date": "2025-01-05",
            "reference": "TXN-001"
        })

        db.record_ar_receipt({
            "invoice_id": inv2_id,
            "amount": 500.0,
            "payment_method": "Cash",
            "receipt_date": "2025-01-15",
            "reference": "RCT-002"
        })

        stmt = db.get_customer_statement(self.customer_id, company_id=self.company_id)

        self.assertEqual(stmt["customer"]["name"], "Global Tech Ltd")
        self.assertEqual(stmt["total_invoiced"], 1500.0)
        self.assertEqual(stmt["total_received"], 1100.0)
        self.assertEqual(stmt["outstanding_balance"], 400.0)
        self.assertEqual(stmt["invoice_count"], 2)
        self.assertEqual(stmt["receipt_count"], 2)

        txs = stmt["transactions"]
        self.assertEqual(len(txs), 4)

        # Tx 0: Inv 1001 (Jan 1) -> Running Bal = +1000.0
        self.assertEqual(txs[0]["doc_type"], "Invoice")
        self.assertEqual(txs[0]["reference"], "INV-1001")
        self.assertEqual(txs[0]["running_balance"], 1000.0)

        # Tx 1: Receipt 600 (Jan 5) -> Running Bal = +400.0
        self.assertEqual(txs[1]["doc_type"], "Receipt")
        self.assertEqual(txs[1]["received_amount"], 600.0)
        self.assertEqual(txs[1]["running_balance"], 400.0)

        # Tx 2: Inv 1002 (Jan 10) -> Running Bal = +900.0
        self.assertEqual(txs[2]["doc_type"], "Invoice")
        self.assertEqual(txs[2]["invoiced_amount"], 500.0)
        self.assertEqual(txs[2]["running_balance"], 900.0)

        # Tx 3: Receipt 500 (Jan 15) -> Running Bal = +400.0
        self.assertEqual(txs[3]["doc_type"], "Receipt")
        self.assertEqual(txs[3]["received_amount"], 500.0)
        self.assertEqual(txs[3]["running_balance"], 400.0)

    def test_export_customer_statement_to_csv(self):
        """Verify CSV export writes valid header metadata and sanitized row values."""
        inv_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.customer_id,
            "invoice_number": "INV-2001",
            "invoice_date": "2025-01-01",
            "due_date": "2025-01-31",
            "notes": "=SUM(1+1) Formula Test",
            "total_amount": 250.0,
            "subtotal": 250.0
        }, [{"description": "Service", "quantity": 1, "unit_price": 250.0, "amount": 250.0}])

        tmp_csv = os.path.join(tempfile.gettempdir(), "test_customer_stmt.csv")
        try:
            db.export_customer_statement_to_csv(self.customer_id, tmp_csv, company_id=self.company_id)
            self.assertTrue(os.path.exists(tmp_csv))

            with open(tmp_csv, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("CUSTOMER STATEMENT OF ACCOUNT & AR LEDGER", content)
            self.assertIn("Global Tech Ltd", content)
            self.assertIn("250.00", content)
            # Ensure formula injection was sanitized with leading single quote
            self.assertIn("'=SUM(1+1)", content)
        finally:
            if os.path.exists(tmp_csv):
                os.unlink(tmp_csv)

    def test_generate_customer_statement_pdf(self):
        """Verify ReportLab PDF statement generation creates valid non-empty file."""
        inv_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.customer_id,
            "invoice_number": "INV-3001",
            "invoice_date": "2025-01-01",
            "due_date": "2025-01-31",
            "notes": "Consulting retainer",
            "total_amount": 1200.0,
            "subtotal": 1200.0
        }, [{"description": "Retainer", "quantity": 1, "unit_price": 1200.0, "amount": 1200.0}])

        pdf_path = printer.generate_customer_statement_pdf(self.customer_id, company_id=self.company_id)
        try:
            self.assertTrue(os.path.exists(pdf_path))
            self.assertGreater(os.path.getsize(pdf_path), 1000)
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)


class TestCustomerStatementUI(unittest.TestCase):
    """Test Tkinter CustomerStatementDialog UI initialization and callbacks."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = db.create_company("Test UI Corp")
        self.cid = db.create_customer({
            "company_id": self.company_id,
            "name": "Alpha Corporation"
        })

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_dialog_instantiation(self):
        """Verify CustomerStatementDialog initializes without error."""
        import tkinter as tk
        from ui.customer_statement import CustomerStatementDialog

        root = tk.Tk()
        root.withdraw()

        try:
            dlg = CustomerStatementDialog(root, initial_customer=self.cid, company_id=self.company_id)
            self.assertEqual(dlg._customer_var.get(), "Alpha Corporation")
            dlg.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
