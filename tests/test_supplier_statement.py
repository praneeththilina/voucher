"""
Unit tests for Supplier Statement & Accounts Payable Ledger features.
Tests database functions `get_supplier_statement` and `export_supplier_statement_to_csv`,
and UI dialogs `SupplierStatementDialog` and `SupplierManagerDialog`.
"""

import os
import tempfile
import unittest
import tkinter as tk
from unittest.mock import patch

import database as db
import vendor_payments as vp
from ui.supplier_manager import SupplierStatementDialog, SupplierManagerDialog


class TestSupplierStatementDatabase(unittest.TestCase):
    """Test backend database statement functions for suppliers/vendors."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        db.DB_PATH = self.temp_db_path
        db.init_db()

        self.company_id = db.create_company("Test Supplier Statement SME")
        db.set_active_company_id(self.company_id)

        # Create supplier
        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Global Supplies Ltd",
            "contact_person": "Jane Doe",
            "phone": "+94771234567",
            "email": "jane@globalsupplies.com",
            "payment_terms": 30,
        })

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_get_supplier_statement_empty(self):
        stmt = db.get_supplier_statement(self.supplier_id, company_id=self.company_id)
        self.assertEqual(stmt["supplier_name"], "Global Supplies Ltd")
        self.assertEqual(stmt["total_billed"], 0.0)
        self.assertEqual(stmt["total_paid"], 0.0)
        self.assertEqual(stmt["total_credits"], 0.0)
        self.assertEqual(stmt["balance_due"], 0.0)
        self.assertEqual(len(stmt["entries"]), 0)

    def test_get_supplier_statement_invalid_supplier(self):
        with self.assertRaises(ValueError):
            db.get_supplier_statement(999999, company_id=self.company_id)

    def test_get_supplier_statement_with_bills_payments_and_credits(self):
        # 1. Create AP Bill 1
        bill1_id = db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "invoice_number": "BILL-2026-001",
            "invoice_date": "2026-01-05",
            "due_date": "2026-02-05",
            "subtotal": 5000.0,
            "tax_amount": 0.0,
            "total_amount": 5000.0,
            "notes": "Office Raw Materials",
        }, [{
            "description": "Raw Material Batch A",
            "quantity": 5,
            "unit_price": 1000.0,
            "amount": 5000.0,
        }])

        # 2. Create AP Bill 2
        bill2_id = db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "invoice_number": "BILL-2026-002",
            "invoice_date": "2026-01-10",
            "due_date": "2026-02-10",
            "subtotal": 2000.0,
            "tax_amount": 0.0,
            "total_amount": 2000.0,
            "notes": "Hardware Tools",
        }, [{
            "description": "Tool Sets",
            "quantity": 2,
            "unit_price": 1000.0,
            "amount": 2000.0,
        }])

        # 3. Create Vendor Credit Note
        expense_acct = db.get_account_by_code("5410", self.company_id)
        credit_id = vp.create_credit({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "credit_number": "VCR-2026-001",
            "credit_date": "2026-01-12",
            "amount": 500.0,
            "expense_account_id": expense_acct["id"],
            "notes": "Damaged goods return",
        })

        # 4. Record Payment for Bill 1
        bank_acct = db.get_account_by_code("1120", self.company_id)
        vp.pay_bills(
            {
                "company_id": self.company_id,
                "supplier_id": self.supplier_id,
                "payment_date": "2026-01-15",
                "payment_method": "Bank Transfer",
                "payment_account_id": bank_acct["id"],
                "reference": "TXN100200",
            },
            [{"invoice_id": bill1_id, "cash_amount": 3000.0, "credit_amount": 0.0}]
        )

        stmt = db.get_supplier_statement(self.supplier_id, company_id=self.company_id)

        self.assertEqual(stmt["total_billed"], 7000.0)
        self.assertEqual(stmt["total_paid"], 3000.0)
        self.assertEqual(stmt["total_credits"], 500.0)
        self.assertEqual(stmt["balance_due"], 3500.0)
        self.assertEqual(stmt["bill_count"], 2)
        self.assertEqual(stmt["payment_count"], 1)
        self.assertEqual(stmt["credit_count"], 1)

        entries = stmt["entries"]
        self.assertEqual(len(entries), 4)

        # Chronological verification
        # Entry 0: Bill 1 (2026-01-05) -> Billed: 5000, Running: 5000
        self.assertEqual(entries[0]["ref"], "BILL-2026-001")
        self.assertEqual(entries[0]["billed"], 5000.0)
        self.assertEqual(entries[0]["running_balance"], 5000.0)

        # Entry 1: Bill 2 (2026-01-10) -> Billed: 2000, Running: 7000
        self.assertEqual(entries[1]["ref"], "BILL-2026-002")
        self.assertEqual(entries[1]["billed"], 2000.0)
        self.assertEqual(entries[1]["running_balance"], 7000.0)

        # Entry 2: Vendor Credit (2026-01-12) -> Credits: 500, Running: 6500
        self.assertEqual(entries[2]["entry_type"], "Credit Note")
        self.assertEqual(entries[2]["credits"], 500.0)
        self.assertEqual(entries[2]["running_balance"], 6500.0)

        # Entry 3: Payment (2026-01-15) -> Paid: 3000, Running: 3500
        self.assertEqual(entries[3]["entry_type"], "Payment")
        self.assertEqual(entries[3]["paid"], 3000.0)
        self.assertEqual(entries[3]["running_balance"], 3500.0)

    def test_export_supplier_statement_to_csv(self):
        bill_id = db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "invoice_number": "=SUM(1,2)",  # CSV formula test string
            "invoice_date": "2026-01-10",
            "due_date": "2026-02-10",
            "subtotal": 4000.0,
            "tax_amount": 0.0,
            "total_amount": 4000.0,
        }, [{
            "description": "Equipment",
            "quantity": 1,
            "unit_price": 4000.0,
            "amount": 4000.0,
        }])

        tmp_csv = tempfile.mktemp(suffix=".csv")
        try:
            res_path = db.export_supplier_statement_to_csv(self.supplier_id, tmp_csv, company_id=self.company_id)
            self.assertTrue(os.path.exists(res_path))

            with open(res_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("SUPPLIER STATEMENT", content)
            self.assertIn("Global Supplies Ltd", content)
            self.assertIn("4000.00", content)
            # Ensure formula injection sanitization prefix is applied
            self.assertIn("'=SUM(1,2)", content)
        finally:
            if os.path.exists(tmp_csv):
                os.remove(tmp_csv)


class TestSupplierStatementUI(unittest.TestCase):
    """Test UI dialogs for supplier statements and supplier management."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)
        db.DB_PATH = self.temp_db_path
        db.init_db()

        self.company_id = db.create_company("UI Test Supplier SME")
        db.set_active_company_id(self.company_id)

        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Apex Vendor Corp",
            "phone": "+94119998888",
            "email": "sales@apexvendor.com",
            "payment_terms": 30,
        })

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    @patch("tkinter.messagebox.showinfo")
    def test_supplier_statement_dialog_initialization(self, mock_info):
        dialog = SupplierStatementDialog(self.root, initial_supplier_id=self.supplier_id, company_id=self.company_id)
        dialog.update()

        self.assertEqual(dialog._get_selected_supplier_id(), self.supplier_id)
        children = dialog.tree.get_children()
        # No transactions yet
        self.assertEqual(len(children), 0)

        dialog.destroy()

    @patch("tkinter.messagebox.showinfo")
    def test_supplier_statement_dialog_with_bill_auto_selection(self, mock_info):
        # Create a bill so statement treeview is non-empty
        db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "invoice_number": "BILL-101",
            "invoice_date": "2026-01-10",
            "due_date": "2026-02-10",
            "subtotal": 1200.0,
            "tax_amount": 0.0,
            "total_amount": 1200.0,
        }, [{
            "description": "Stock",
            "quantity": 1,
            "unit_price": 1200.0,
            "amount": 1200.0,
        }])

        dialog = SupplierStatementDialog(self.root, initial_supplier_id=self.supplier_id, company_id=self.company_id)
        dialog.update()

        children = dialog.tree.get_children()
        self.assertEqual(len(children), 1)

        # Check first row is auto-selected and focused
        sel = dialog.tree.selection()
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0], children[0])
        self.assertEqual(dialog.tree.focus(), children[0])

        dialog.destroy()

    @patch("tkinter.messagebox.showinfo")
    def test_supplier_manager_dialog_open_statement(self, mock_info):
        dialog = SupplierManagerDialog(self.root, company_id=self.company_id)
        dialog.update()

        # Select the supplier in the manager dialog
        children = dialog.tree.get_children()
        self.assertGreaterEqual(len(children), 1)
        dialog.tree.selection_set(children[0])

        selected_supplier = dialog._get_selected_supplier()
        self.assertEqual(selected_supplier["id"], self.supplier_id)

        # Launch supplier statement dialog
        dialog._view_supplier_statement()
        dialog.update()

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
