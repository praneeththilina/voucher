"""
tests/test_tax_manager.py
Unit tests for Tax Management (VAT / GST) & Statutory Returns Module (v4.0).
Tests tax rate presets, CRUD, default switching, VAT Return calculation (Boxes 1-5),
refund credit handling, ReportLab PDF generation, and company cascade deletion.
"""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
from reports.vat_return import generate_vat_return_pdf


class TestTaxManager(unittest.TestCase):
    """Test suite verifying Tax Rates presets, VAT Return calculation and PDF export."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = 1
        self.created_temp_files = []

    def tearDown(self):
        for fpath in self.created_temp_files:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        db.DB_PATH = self.orig_db_path

    def test_default_tax_rates_seeded(self):
        """Test that default tax presets (VAT18, ZERO, EXEMPT, WHT5) were seeded properly."""
        rates = db.get_tax_rates(self.company_id)
        self.assertGreaterEqual(len(rates), 4)

        codes = {r["code"]: r for r in rates}
        self.assertIn("VAT18", codes)
        self.assertIn("ZERO", codes)
        self.assertIn("EXEMPT", codes)
        self.assertIn("WHT5", codes)

        vat18 = codes["VAT18"]
        self.assertEqual(vat18["rate"], 0.18)
        self.assertEqual(vat18["is_default"], 1)
        self.assertEqual(vat18["tax_type"], "VAT")

    def test_tax_rate_crud_and_default_switching(self):
        """Test creating, updating, setting default, and deleting tax rates."""
        tid = db.create_tax_rate({
            "company_id": self.company_id,
            "name": "Custom Green Levy",
            "code": "GRN25",
            "rate": 2.5,  # Percentage format 2.5% -> stored as 0.025
            "tax_type": "Custom",
            "is_default": 0,
            "notes": "Environmental tax",
        })
        self.assertGreater(tid, 0)

        tr = db.get_tax_rate(tid)
        self.assertIsNotNone(tr)
        self.assertEqual(tr["code"], "GRN25")
        self.assertAlmostEqual(tr["rate"], 0.025, places=4)
        self.assertEqual(tr["tax_type"], "Custom")

        # Update
        db.update_tax_rate(tid, {
            **tr,
            "rate": 3.0,
            "name": "Custom Green Levy Updated"
        })
        updated = db.get_tax_rate(tid)
        self.assertAlmostEqual(updated["rate"], 0.03, places=4)
        self.assertEqual(updated["name"], "Custom Green Levy Updated")

        # Set as default
        db.set_default_tax_rate(self.company_id, tid)
        def_tr = db.get_tax_rate(tid)
        self.assertEqual(def_tr["is_default"], 1)

        # Check old default VAT18 is no longer default
        all_rates = db.get_tax_rates(self.company_id)
        vat18 = [r for r in all_rates if r["code"] == "VAT18"][0]
        self.assertEqual(vat18["is_default"], 0)

        # Attempt to delete current default rate (should be blocked)
        ok, msg = db.delete_tax_rate(tid)
        self.assertFalse(ok)
        self.assertIn("default", msg.lower())

        # Restore VAT18 as default, then delete custom rate
        vat18_id = vat18["id"]
        db.set_default_tax_rate(self.company_id, vat18_id)
        ok, msg = db.delete_tax_rate(tid)
        self.assertTrue(ok)
        self.assertIsNone(db.get_tax_rate(tid))

    def test_vat_return_calculation_payable(self):
        """Test calculation of VAT Return with net VAT payable (Sales VAT > Purchase VAT)."""
        # Create Customer & AR Invoice (Output Tax)
        cust_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Apex Solutions Ltd",
            "tax_id": "VAT-992211",
        })
        ar_inv_id = db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": cust_id,
            "invoice_number": "INV-2026-0001",
            "invoice_date": "2026-08-10",
            "due_date": "2026-09-10",
            "status": "Sent",
        }, [
            {
                "description": "IT Consulting Services",
                "quantity": 1.0,
                "unit_price": 100000.0,
                "tax_rate": 18.0,
                "tax_amount": 18000.0,
                "line_total": 118000.0,
            }
        ])
        self.assertGreater(ar_inv_id, 0)

        # Create Supplier & AP Invoice (Input Tax)
        supp_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Cloud Host Provider Inc",
            "tax_id": "VAT-110022",
        })
        ap_inv_id = db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": supp_id,
            "invoice_number": "BILL-CL-5501",
            "invoice_date": "2026-08-15",
            "due_date": "2026-09-15",
            "status": "Unpaid",
        }, [
            {
                "description": "Server Hosting Infrastructure",
                "quantity": 1.0,
                "unit_price": 40000.0,
                "tax_rate": 18.0,
                "tax_amount": 7200.0,
                "line_total": 47200.0,
            }
        ])
        self.assertGreater(ap_inv_id, 0)

        # Generate VAT Return for August 2026
        vat_res = db.generate_vat_return(
            company_id=self.company_id,
            period_start="2026-08-01",
            period_end="2026-08-31"
        )
        self.assertIsNotNone(vat_res)

        # Box 1: Sales subtotal
        self.assertEqual(vat_res["box1_sales"], 100000.0)
        # Box 2: Output VAT
        self.assertEqual(vat_res["box2_output_vat"], 18000.0)
        # Box 3: Purchases subtotal
        self.assertEqual(vat_res["box3_purchases"], 40000.0)
        # Box 4: Input VAT
        self.assertEqual(vat_res["box4_input_vat"], 7200.0)
        # Box 5: Net Payable = 18,000 - 7,200 = 10,800
        self.assertEqual(vat_res["box5_net_payable"], 10800.0)
        self.assertFalse(vat_res["is_refund"])

        self.assertEqual(len(vat_res["sales_transactions"]), 1)
        self.assertEqual(len(vat_res["purchase_transactions"]), 1)

    def test_vat_return_calculation_refund_credit(self):
        """Test calculation of VAT Return with net tax credit / refund due (Purchase VAT > Sales VAT)."""
        # Customer AR Invoice
        cust_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Minor Client",
        })
        db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": cust_id,
            "invoice_number": "INV-2026-0002",
            "invoice_date": "2026-09-05",
            "due_date": "2026-10-05",
            "status": "Paid",
        }, [
            {
                "description": "Small Repair",
                "quantity": 1.0,
                "unit_price": 20000.0,
                "tax_rate": 18.0,
                "tax_amount": 3600.0,
                "line_total": 23600.0,
            }
        ])

        # Supplier AP Bill (Heavy capital procurement)
        supp_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Hardware Equipment Importers",
        })
        db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": supp_id,
            "invoice_number": "BILL-HW-900",
            "invoice_date": "2026-09-12",
            "due_date": "2026-10-12",
            "status": "Unpaid",
        }, [
            {
                "description": "Industrial Core Switches",
                "quantity": 1.0,
                "unit_price": 50000.0,
                "tax_rate": 18.0,
                "tax_amount": 9000.0,
                "line_total": 59000.0,
            }
        ])

        vat_res = db.generate_vat_return(
            company_id=self.company_id,
            period_start="2026-09-01",
            period_end="2026-09-30"
        )
        self.assertEqual(vat_res["box2_output_vat"], 3600.0)
        self.assertEqual(vat_res["box4_input_vat"], 9000.0)
        # Box 5: 3,600 - 9,000 = -5,400 (Refund Due)
        self.assertEqual(vat_res["box5_net_payable"], -5400.0)
        self.assertTrue(vat_res["is_refund"])

    def test_vat_return_pdf_generation(self):
        """Test generation of official multi-page ReportLab PDF for VAT Return."""
        # Create test customer and invoice
        cust_id = db.create_customer({"company_id": self.company_id, "name": "Global Client Corp"})
        db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": cust_id,
            "invoice_number": "INV-PDF-1",
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-31",
            "status": "Sent",
        }, [
            {
                "description": "Software Subscription",
                "quantity": 1.0,
                "unit_price": 50000.0,
                "tax_rate": 18.0,
                "tax_amount": 9000.0,
                "line_total": 59000.0,
            }
        ])

        fd, out_pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.created_temp_files.append(out_pdf)

        res_path = generate_vat_return_pdf(
            vat_data_or_company_id=self.company_id,
            period_start="2026-10-01",
            period_end="2026-10-31",
            output_path=out_pdf
        )
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 2500)

    def test_company_cascade_deletion(self):
        """Test that deleting a company properly cascades and removes tax rates."""
        c2_id = db.create_company("Tax Test Company 2")
        rates = db.get_tax_rates(c2_id)
        self.assertGreater(len(rates), 0)

        # Delete company
        ok = db.delete_company(c2_id)
        self.assertTrue(ok)

        # Verify tax rates clean
        self.assertEqual(len(db.get_tax_rates(c2_id)), 0)


if __name__ == "__main__":
    unittest.main()
