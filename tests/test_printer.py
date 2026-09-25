"""
Unit tests for printer PDF generation engine (printer.py).
"""

import unittest
import os
import tempfile
import shutil

import database as db
import printer


class TestPrinterEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_test.db")
        self.attachments_dir = os.path.join(self.test_dir, "attachments")
        self.backup_dir = os.path.join(self.test_dir, "backups")

        self.orig_db_path = db.DB_PATH
        self.orig_attachments_dir = db.ATTACHMENTS_DIR
        self.orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        db.BACKUP_DIR = self.orig_backup_dir

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_voucher_pdf(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "Test Supplier",
            "cash_given_by": "Accountant",
            "spent_by": "Test Supplier",
            "bill_status": "Received",
            "prepared_by": "User A",
            "approved_by": "Manager B",
        }
        line_items = [
            {"description": "Raw Materials", "category": "Production", "amount": 1200.0},
            {"description": "Delivery Charge", "category": "Logistics", "amount": 150.0},
        ]
        v_id = db.create_voucher(data, line_items, company_id=1)

        pdf_output = os.path.join(self.test_dir, "output.pdf")
        generated_path = printer.generate_voucher_pdf([v_id], output_path=pdf_output)

        self.assertTrue(os.path.exists(generated_path))
        self.assertGreater(os.path.getsize(generated_path), 0)

    def test_print_and_open_pdf_invalid_path(self):
        # Verify non-existent file paths return False without raising unhandled exceptions
        non_existent_file = os.path.join(self.test_dir, "does_not_exist.pdf")
        self.assertFalse(printer.print_pdf(non_existent_file))
        self.assertFalse(printer.open_pdf(non_existent_file))

        # Verify None and invalid type inputs return False safely
        self.assertFalse(printer.print_pdf(None))
        self.assertFalse(printer.open_pdf(None))


if __name__ == "__main__":
    unittest.main()
