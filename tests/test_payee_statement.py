"""
Unit tests for the Payee Statement & Vendor Ledger feature.
Tests database aggregation, CSV export, PDF statement generation, and UI dialog.
"""

import os
import unittest
import tempfile
import sqlite3
import tkinter as tk
import ttkbootstrap as ttk

import database as db
import printer
from ui.payee_statement import PayeeStatementDialog
from tests.test_widgets import get_test_root


class TestPayeeStatement(unittest.TestCase):

    def setUp(self):
        """Set up isolated test database in a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vouchers.db")
        self.attachments_dir = os.path.join(self.temp_dir, "attachments")
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self._orig_db_path = db.DB_PATH
        self._orig_attachments_dir = db.ATTACHMENTS_DIR
        self._orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        db.init_db()

        # Create sample voucher data for "ACME Suppliers" and "Beta Traders"
        v1_data = {
            "date": "2026-03-01",
            "paid_to": "ACME Suppliers",
            "cash_given_by": "John Admin",
            "bill_status": "Received",
            "payment_method": "Bank Transfer",
            "payment_ref": "TRX-101",
        }
        v1_items = [
            {"description": "Office Stationery", "category": "Office Supplies", "amount": 1500.0},
            {"description": "Printer Paper", "category": "Office Supplies", "amount": 500.0},
        ]
        self.v1_id = db.create_voucher(v1_data, v1_items)

        v2_data = {
            "date": "2026-03-15",
            "paid_to": "ACME Suppliers",
            "cash_given_by": "John Admin",
            "bill_status": "Pending",
            "payment_method": "Cash",
        }
        v2_items = [
            {"description": "Hardware Repair", "category": "Maintenance", "amount": 3000.0},
        ]
        self.v2_id = db.create_voucher(v2_data, v2_items)

        v3_data = {
            "date": "2026-03-20",
            "paid_to": "Beta Traders",
            "cash_given_by": "Mary Manager",
            "bill_status": "Received",
            "payment_method": "Cheque",
            "payment_ref": "CHQ-888",
        }
        v3_items = [
            {"description": "Consulting Fee", "category": "Professional Services", "amount": 10000.0},
        ]
        self.v3_id = db.create_voucher(v3_data, v3_items)

    def tearDown(self):
        """Restore original database paths."""
        db.DB_PATH = self._orig_db_path
        db.ATTACHMENTS_DIR = self._orig_attachments_dir
        db.BACKUP_DIR = self._orig_backup_dir

    def test_get_payee_statement(self):
        """Test get_payee_statement data aggregation."""
        stmt = db.get_payee_statement("ACME Suppliers", date_filter="All Time")
        self.assertEqual(stmt["payee_name"], "ACME Suppliers")
        self.assertEqual(stmt["total_vouchers"], 2)
        self.assertEqual(stmt["total_spent"], 5000.0)
        self.assertEqual(stmt["avg_voucher_amount"], 2500.0)
        self.assertEqual(stmt["pending_bills_count"], 1)
        self.assertEqual(stmt["pending_amount"], 3000.0)

        # Category breakdown check
        cats = {c["category"]: c["amount"] for c in stmt["by_category"]}
        self.assertIn("Office Supplies", cats)
        self.assertEqual(cats["Office Supplies"], 2000.0)
        self.assertIn("Maintenance", cats)
        self.assertEqual(cats["Maintenance"], 3000.0)

    def test_get_payee_statement_other_payee(self):
        """Test get_payee_statement for Beta Traders."""
        stmt = db.get_payee_statement("Beta Traders", date_filter="All Time")
        self.assertEqual(stmt["payee_name"], "Beta Traders")
        self.assertEqual(stmt["total_vouchers"], 1)
        self.assertEqual(stmt["total_spent"], 10000.0)
        self.assertEqual(stmt["pending_amount"], 0.0)

    def test_export_payee_statement_to_csv(self):
        """Test CSV export for payee statement."""
        csv_path = os.path.join(self.temp_dir, "acme_statement.csv")
        db.export_payee_statement_to_csv("ACME Suppliers", csv_path)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("PAYEE PAYMENT STATEMENT / VENDOR LEDGER", content)
        self.assertIn("ACME Suppliers", content)
        self.assertIn("5000.00", content)
        self.assertIn("Office Supplies", content)

    def test_generate_payee_statement_pdf(self):
        """Test PDF generation for payee statement."""
        pdf_path = os.path.join(self.temp_dir, "acme_statement.pdf")
        res_path = printer.generate_payee_statement_pdf("ACME Suppliers", output_path=pdf_path)

        self.assertEqual(res_path, pdf_path)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 0)

    def test_payee_statement_dialog_ui(self):
        """Test PayeeStatementDialog GUI creation and initialization."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        dialog = PayeeStatementDialog(root, initial_payee="ACME Suppliers")
        dialog.update()

        self.assertEqual(dialog._payee_var.get(), "ACME Suppliers")
        self.assertEqual(dialog._stat_vars["vouchers_count"].get(), "2")
        self.assertIn("5,000.00", dialog._stat_vars["total_spent"].get())

        children = dialog._tree.get_children()
        self.assertEqual(len(children), 2)

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
