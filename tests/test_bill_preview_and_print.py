import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk
import ttkbootstrap as ttk

import database as db
import printer


_shared_root = None


def get_test_root():
    global _shared_root
    try:
        exists = _shared_root is not None and bool(_shared_root.winfo_exists())
    except Exception:
        exists = False
        _shared_root = None

    if not exists:
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
            ttk.Style(theme="minty-light")
        except Exception:
            _shared_root = None
    return _shared_root


def tearDownModule():
    global _shared_root
    if _shared_root and _shared_root.winfo_exists():
        try:
            for child in _shared_root.winfo_children():
                child.destroy()
            _shared_root.destroy()
        except Exception:
            pass


class TestBillPreviewAndPrint(unittest.TestCase):
    """Test suite for saving expenses as supplier bills and previewing/printing them."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vouchers.db")
        db.configure_database(self.db_path)
        db.init_db()

    def tearDown(self):
        db.set_current_user(None)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_migration_44_ap_invoices_terms_column(self):
        """Verify ap_invoices table contains terms column via Migration 44."""
        conn = db.get_connection()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(ap_invoices)").fetchall()]
        self.assertIn("terms", cols)
        applied = [r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()]
        self.assertIn(44, applied)
        conn.close()

    def test_create_supplier_bill_voucher_and_generate_pdf(self):
        """Verify creating a supplier bill voucher and generating its PDF preview succeeds."""
        # Create a vendor first
        vendor_id = db.create_supplier({
            "name": "Acme Supplies Ltd",
            "contact_person": "Jane Doe",
            "payment_terms": 30,
        })
        self.assertGreater(vendor_id, 0)

        # Create a supplier bill voucher
        voucher_data = {
            "date": "2026-11-06",
            "voucher_number": "BILL-2026-001",
            "paid_to": "Acme Supplies Ltd",
            "payment_ref": "INV-ACME-9001",
            "payment_method": "Accounts Payable",
            "bill_status": "Unpaid",
            "prepared_by": "Accountant",
            "cash_given_by": "Warehouse Manager",
        }
        line_items = [
            {
                "description": "Office Stationery & Printing Paper",
                "category": "Office Supplies & Stationery",
                "amount": 4250.0,
            },
            {
                "description": "Printer Cartridge Replacement",
                "category": "Office Supplies & Stationery",
                "amount": 8500.0,
            },
        ]

        voucher_id = db.create_supplier_bill_voucher(voucher_data, line_items)
        self.assertIsNotNone(voucher_id)
        self.assertGreater(voucher_id, 0)

        # Verify voucher record in database
        v_full = db.get_voucher(voucher_id)
        self.assertIsNotNone(v_full)
        voucher = v_full["voucher"]
        self.assertEqual(voucher["source_module"], "ap_invoice")
        self.assertIsNotNone(voucher["source_id"])
        self.assertEqual(voucher["paid_to"], "Acme Supplies Ltd")
        self.assertEqual(voucher["total_amount"], 12750.0)

        # Verify linked A/P invoice
        ap_inv = db.get_ap_invoice(voucher["source_id"])
        self.assertIsNotNone(ap_inv)
        self.assertEqual(ap_inv["invoice"]["invoice_number"], "INV-ACME-9001")
        self.assertEqual(ap_inv["invoice"]["total_amount"], 12750.0)

        # Verify PDF generation works
        pdf_path = printer.generate_voucher_pdf([voucher_id])
        self.assertTrue(os.path.isfile(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 1000)

        # Clean up generated PDF
        try:
            os.remove(pdf_path)
        except OSError:
            pass

    def test_form_preview_ui_button_and_actions(self):
        """Verify Preview button UI and dynamic configuration in MainWindow."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Authenticate user
        u_id = db.create_user(
            "admin_test",
            "Admin Tester",
            "AdminPass123!",
            role="admin",
        )
        user = db.authenticate_user("admin_test", "AdminPass123!")
        db.set_current_user(user)

        from ui.main_window import MainWindow

        win = MainWindow(root)
        try:
            # Ensure form tab is built
            win._ensure_form_tab()
            self.assertTrue(hasattr(win, "_form_preview_btn"))
            self.assertIsNotNone(win._form_preview_btn)

            # Test in Bill mode
            win._voucher_mode = "bill"
            win._configure_voucher_mode()
            self.assertIn("Preview Bill", win._form_preview_btn.cget("text"))
            self.assertIn("Save Bill", win._form_save_btn.cget("text"))
            self.assertIn("Save & Print Bill", win._form_save_print_btn.cget("text"))

            # Test in Payment mode
            win._voucher_mode = "payment"
            win._configure_voucher_mode()
            self.assertIn("Preview", win._form_preview_btn.cget("text"))
            self.assertNotIn("Bill", win._form_preview_btn.cget("text"))
            self.assertIn("Save Payment", win._form_save_btn.cget("text"))
            self.assertIn("Save & Print", win._form_save_print_btn.cget("text"))

            # Test _preview_voucher_form calls _do_print with "preview"
            with patch.object(win, "_save_voucher", return_value=123) as mock_save, \
                 patch.object(win, "_do_print") as mock_print:
                win._preview_voucher_form()
                mock_save.assert_called_once()
                mock_print.assert_called_once_with([123], "preview")

            # Test _save_and_print calls _do_print with "preview"
            with patch.object(win, "_save_voucher", return_value=456) as mock_save, \
                 patch.object(win, "_do_print") as mock_print:
                win._save_and_print()
                mock_save.assert_called_once()
                mock_print.assert_called_once_with([456], "preview")

        finally:
            win.root.withdraw()


if __name__ == "__main__":
    unittest.main()
