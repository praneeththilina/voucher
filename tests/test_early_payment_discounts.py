"""
tests/test_early_payment_discounts.py
Unit and UI tests for Early Payment Discount Optimization & Early Settlement.
"""

import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
import tkinter as tk
import ttkbootstrap as ttk

import database as db
import vendor_payments as vp
from ui.early_discount_dialog import EarlyPaymentDiscountDialog

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
    else:
        try:
            ttk.Style.instance = ttk.Style(theme="minty-light")
        except Exception:
            pass
    return _shared_root


class TestEarlyPaymentDiscounts(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_early_discounts.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = db.create_company(
            name="Discount Test SME",
            voucher_format="date_based",
            fiscal_year_start="01-01",
            fiscal_year_end="12-31"
        )
        db.set_active_company_id(self.company_id)

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_early_payment_terms(self):
        # 2/10 Net 30
        res = vp.parse_early_payment_terms("2/10 Net 30")
        self.assertEqual(res["discount_pct"], 2.0)
        self.assertEqual(res["discount_days"], 10)
        self.assertEqual(res["net_days"], 30)
        self.assertTrue(res["has_discount"])

        # 1.5/15 Net 45
        res = vp.parse_early_payment_terms("1.5/15 Net 45")
        self.assertEqual(res["discount_pct"], 1.5)
        self.assertEqual(res["discount_days"], 15)
        self.assertEqual(res["net_days"], 45)

        # Net 30 (no early discount)
        res = vp.parse_early_payment_terms("Net 30")
        self.assertEqual(res["discount_pct"], 0.0)
        self.assertEqual(res["discount_days"], 0)
        self.assertEqual(res["net_days"], 30)
        self.assertFalse(res["has_discount"])

        # None / Empty
        res = vp.parse_early_payment_terms(None)
        self.assertEqual(res["discount_pct"], 0.0)
        self.assertFalse(res["has_discount"])

    def test_calculate_ap_early_payment_discounts(self):
        # Create a supplier with 2/10 Net 30 terms
        sup_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Tech Supplies Ltd",
            "payment_terms": 30
        })

        today = date.today()
        inv_date = today.isoformat()
        due_date = (today + timedelta(days=30)).isoformat()

        # Create AP invoice with 2/10 Net 30 terms
        inv_data = {
            "company_id": self.company_id,
            "supplier_id": sup_id,
            "invoice_number": "INV-1001",
            "invoice_date": inv_date,
            "due_date": due_date,
            "discount_amount": 0.0,
            "currency": "LKR",
            "exchange_rate": 1.0,
            "notes": "Testing early payment discount",
            "terms": "2/10 Net 30"
        }
        line_items = [
            {
                "description": "Laptops and Hardware",
                "quantity": 10.0,
                "unit_price": 1000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 10000.0
            }
        ]
        inv_id = db.create_ap_invoice(inv_data, line_items)

        # Calculate early payment discounts as of today
        analysis = db.calculate_ap_early_payment_discounts(
            company_id=self.company_id,
            as_of_date=today.isoformat()
        )

        self.assertEqual(analysis["eligible_count"], 1)
        self.assertEqual(analysis["total_potential_savings"], 200.0)  # 2% of 10000
        self.assertGreater(analysis["top_apr"], 35.0)  # ~37.24% APR

        invoices = analysis["invoices"]
        self.assertEqual(len(invoices), 1)
        inv = invoices[0]
        self.assertEqual(inv["id"], inv_id)
        self.assertEqual(inv["discount_amount"], 200.0)
        self.assertEqual(inv["net_payable"], 9800.0)
        self.assertEqual(inv["days_remaining"], 10)
        self.assertEqual(inv["status"], "Available")

    def test_export_early_payment_discounts_to_csv(self):
        sup_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "=HYPERLINK(\"http://evil.com\")",
            "payment_terms": 30
        })

        inv_data = {
            "company_id": self.company_id,
            "supplier_id": sup_id,
            "invoice_number": "=1+2",
            "invoice_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "currency": "LKR",
            "terms": "3/10 Net 60"
        }
        line_items = [
            {"description": "Office Supplies", "quantity": 1, "unit_price": 5000, "tax_rate": 0, "tax_amount": 0, "line_total": 5000}
        ]
        db.create_ap_invoice(inv_data, line_items)

        temp_csv = os.path.join(self.test_dir, "export_test.csv")
        try:
            db.export_early_payment_discounts_to_csv(temp_csv, company_id=self.company_id)
            self.assertTrue(os.path.exists(temp_csv))

            with open(temp_csv, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # Verify formula injection protection
            self.assertIn("'=1+2", content)
            self.assertIn("'=HYPERLINK", content)
            self.assertIn("Early Payment Discount Optimization", content)
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)


class TestEarlyDiscountDialogUI(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "ui_test_early_discounts.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = db.create_company(
            name="UI Test SME",
            voucher_format="date_based",
            fiscal_year_start="01-01",
            fiscal_year_end="12-31"
        )
        db.set_active_company_id(self.company_id)

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if self.root and self.root.winfo_exists():
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

    def test_early_discount_dialog_ui(self):
        sup_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Global Office Equipment",
            "payment_terms": 30
        })

        inv_data = {
            "company_id": self.company_id,
            "supplier_id": sup_id,
            "invoice_number": "INV-500",
            "invoice_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "currency": "LKR",
            "terms": "2/10 Net 30"
        }
        line_items = [
            {"description": "Laser Printer", "quantity": 1, "unit_price": 20000, "tax_rate": 0, "tax_amount": 0, "line_total": 20000}
        ]
        db.create_ap_invoice(inv_data, line_items)

        dialog = EarlyPaymentDiscountDialog(self.root, company_id=self.company_id)
        dialog.update_idletasks()

        # Verify KPI variables updated
        self.assertIn("400.00", dialog.kpi_savings_var.get())  # 2% of 20000
        self.assertEqual(dialog.kpi_eligible_var.get(), "1")

        # Verify treeview populated and first row selected
        children = dialog.tree.get_children()
        self.assertEqual(len(children), 1)
        selected = dialog.tree.selection()
        self.assertEqual(len(selected), 1)

        # Test search filter
        dialog.search_var.set("Printer")
        dialog.update_idletasks()
        self.assertEqual(len(dialog.tree.get_children()), 0)

        dialog.search_var.set("Global")
        dialog.update_idletasks()
        self.assertEqual(len(dialog.tree.get_children()), 1)

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
