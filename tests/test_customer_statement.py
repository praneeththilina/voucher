"""
Unit tests for Customer Statement & Receivables Ledger features.
Tests database functions `get_customer_statement` and `export_customer_statement_to_csv`,
and UI dialogs `CustomerStatementDialog` and `CustomerManagerDialog`.
"""

import os
import tempfile
import unittest
import tkinter as tk
from unittest.mock import patch, MagicMock

import database as db
from ui.customer_manager import CustomerStatementDialog, CustomerManagerDialog


class TestCustomerStatementDatabase(unittest.TestCase):
    """Test backend database statement functions for customers."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        db.DB_PATH = self.temp_db_path
        db.init_db()

        self.company_id = db.create_company("Test Statement SME")
        db.set_active_company_id(self.company_id)

        # Create customer
        self.cust_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Acme Corp",
            "phone": "+94771234567",
            "email": "billing@acme.com",
            "payment_terms": 30,
            "credit_limit": 50000.0,
        })

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_get_customer_statement_empty(self):
        stmt = db.get_customer_statement(self.cust_id, company_id=self.company_id)
        self.assertEqual(stmt["customer_name"], "Acme Corp")
        self.assertEqual(stmt["total_invoiced"], 0.0)
        self.assertEqual(stmt["total_paid"], 0.0)
        self.assertEqual(stmt["balance_due"], 0.0)
        self.assertEqual(len(stmt["entries"]), 0)

    def test_get_customer_statement_with_invoices_and_receipts(self):
        # Create Invoice 1
        inv1_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.cust_id,
            "invoice_number": "INV-2026-0001",
            "invoice_date": "2026-01-10",
            "due_date": "2026-02-10",
            "subtotal": 1000.0,
            "tax_amount": 0.0,
            "total_amount": 1000.0,
            "notes": "Supply of stationery",
        }, [{
            "description": "Stationery Items",
            "quantity": 1,
            "unit_price": 1000.0,
            "amount": 1000.0,
        }])

        # Create Invoice 2
        inv2_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.cust_id,
            "invoice_number": "INV-2026-0002",
            "invoice_date": "2026-01-15",
            "due_date": "2026-02-15",
            "subtotal": 500.0,
            "tax_amount": 0.0,
            "total_amount": 500.0,
            "notes": "IT Consulting",
        }, [{
            "description": "Consulting Services",
            "quantity": 1,
            "unit_price": 500.0,
            "amount": 500.0,
        }])

        # Record Receipt for Invoice 1
        db.record_ar_receipt({
            "company_id": self.company_id,
            "invoice_id": inv1_id,
            "receipt_date": "2026-01-20",
            "amount": 600.0,
            "payment_method": "Bank Transfer",
            "reference": "TXN99812",
        })

        stmt = db.get_customer_statement(self.cust_id, company_id=self.company_id)

        self.assertEqual(stmt["total_invoiced"], 1500.0)
        self.assertEqual(stmt["total_paid"], 600.0)
        self.assertEqual(stmt["balance_due"], 900.0)
        self.assertEqual(stmt["invoice_count"], 2)
        self.assertEqual(stmt["receipt_count"], 1)

        entries = stmt["entries"]
        self.assertEqual(len(entries), 3)

        # Check chronological sequence and running balance
        self.assertEqual(entries[0]["ref"], "INV-2026-0001")
        self.assertEqual(entries[0]["debit"], 1000.0)
        self.assertEqual(entries[0]["running_balance"], 1000.0)

        self.assertEqual(entries[1]["ref"], "INV-2026-0002")
        self.assertEqual(entries[1]["debit"], 500.0)
        self.assertEqual(entries[1]["running_balance"], 1500.0)

        self.assertEqual(entries[2]["entry_type"], "Receipt")
        self.assertEqual(entries[2]["credit"], 600.0)
        self.assertEqual(entries[2]["running_balance"], 900.0)

    def test_export_customer_statement_to_csv(self):
        inv_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": self.cust_id,
            "invoice_number": "INV-2026-0001",
            "invoice_date": "2026-01-10",
            "due_date": "2026-02-10",
            "subtotal": 2000.0,
            "tax_amount": 0.0,
            "total_amount": 2000.0,
        }, [{
            "description": "Goods",
            "quantity": 1,
            "unit_price": 2000.0,
            "amount": 2000.0,
        }])
        db.record_ar_receipt({
            "company_id": self.company_id,
            "invoice_id": inv_id,
            "receipt_date": "2026-01-12",
            "amount": 1000.0,
            "payment_method": "Cash",
        })

        tmp_csv = tempfile.mktemp(suffix=".csv")
        try:
            res_path = db.export_customer_statement_to_csv(self.cust_id, tmp_csv, company_id=self.company_id)
            self.assertTrue(os.path.exists(res_path))

            with open(res_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("CUSTOMER STATEMENT & RECEIVABLES LEDGER", content)
            self.assertIn("Acme Corp", content)
            self.assertIn("INV-2026-0001", content)
            self.assertIn("2000.00", content)
            self.assertIn("1000.00", content)
        finally:
            if os.path.exists(tmp_csv):
                os.remove(tmp_csv)


class TestCustomerStatementUI(unittest.TestCase):
    """Test UI dialogs for customer statements and customer management."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        db.DB_PATH = self.temp_db_path
        db.init_db()

        self.company_id = db.create_company("UI Test SME")
        db.set_active_company_id(self.company_id)

        self.cust_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Beta Ltd",
            "phone": "+94112223334",
            "email": "info@betaltd.com",
            "payment_terms": 15,
            "credit_limit": 100000.0,
        })

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    @patch("tkinter.messagebox.showinfo")
    def test_customer_statement_dialog_initialization(self, mock_info):
        dialog = CustomerStatementDialog(self.root, initial_customer_id=self.cust_id, company_id=self.company_id)
        dialog.update()

        self.assertEqual(dialog._get_selected_customer_id(), self.cust_id)
        children = dialog.tree.get_children()
        # No transactions yet
        self.assertEqual(len(children), 0)

        dialog.destroy()

    @patch("tkinter.messagebox.showinfo")
    def test_customer_manager_dialog_auto_selection(self, mock_info):
        dialog = CustomerManagerDialog(self.root, company_id=self.company_id)
        dialog.update()

        # Verify treeview populated and first item auto-selected
        children = dialog.tree.get_children()
        self.assertGreaterEqual(len(children), 1)

        sel = dialog.tree.selection()
        self.assertEqual(len(sel), 1)
        self.assertEqual(dialog._get_selected_customer_id(), self.cust_id)

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
