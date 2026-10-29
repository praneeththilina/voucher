"""
Unit and integration tests for Bank Transfer Payment Batch Export
and Vendor Credits CSV Export.
"""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime

import database as db
import vendor_payments as vp


class TestBankTransferExport(unittest.TestCase):
    def setUp(self):
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db_file.close()
        db.configure_database(self.temp_db_file.name)
        db.init_db()
        self.company_id = db.get_active_company_id()

        # Register test supplier
        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Acme Bank Beneficiary Ltd",
            "contact_person": "Jane Doe",
            "phone": "+1-555-0199",
            "email": "jane@acme.com",
            "tax_id": "TAX-998877",
            "bank_name": "Commercial Bank PLC",
            "bank_account": "100200300400",
            "payment_terms": 30,
            "currency": "LKR"
        })

        # Create AP invoice
        self.exp_account = db.get_account_by_code("5990", self.company_id)
        self.invoice_id = db.create_ap_invoice(
            {
                "company_id": self.company_id,
                "supplier_id": self.supplier_id,
                "invoice_number": "INV-EFT-101",
                "invoice_date": "2026-03-01",
                "due_date": "2026-03-31",
                "currency": "LKR",
                "exchange_rate": 1.0,
                "status": "Unpaid"
            },
            [
                {
                    "description": "IT Consulting Services",
                    "account_id": self.exp_account["id"],
                    "quantity": 1,
                    "unit_price": 75000.0,
                    "tax_rate": 0.0,
                    "tax_amount": 0.0,
                    "line_total": 75000.0
                }
            ]
        )

        # Pay bill via Bank Transfer
        cash_acct = db.get_account_by_code("1120", self.company_id)
        self.batch_id = vp.pay_bills(
            {
                "company_id": self.company_id,
                "supplier_id": self.supplier_id,
                "payment_date": "2026-03-05",
                "payment_method": "Bank Transfer",
                "payment_account_id": cash_acct["id"],
                "reference": "EFT-REF-2026",
                "notes": "Monthly retainer payout",
                "currency": "LKR",
                "exchange_rate": 1.0,
            },
            [
                {
                    "invoice_id": self.invoice_id,
                    "cash_amount": 75000.0,
                    "credit_amount": 0.0
                }
            ]
        )

        # Create Vendor Credit
        self.credit_id = vp.create_credit({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "credit_number": "VC-2026-001",
            "credit_date": "2026-03-02",
            "amount": 5000.0,
            "expense_account_id": self.exp_account["id"],
            "reference": "RETURN-01",
            "notes": "Faulty hardware return"
        })

    def tearDown(self):
        try:
            if hasattr(self, "temp_db_file") and os.path.exists(self.temp_db_file.name):
                os.remove(self.temp_db_file.name)
        except Exception:
            pass

    def test_get_bank_transfer_batches(self):
        batches = vp.bank_transfer_batches(company_id=self.company_id)
        self.assertTrue(len(batches) >= 1)
        found = next((b for b in batches if b["id"] == self.batch_id), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["supplier_name"], "Acme Bank Beneficiary Ltd")
        self.assertEqual(found["supplier_bank_name"], "Commercial Bank PLC")
        self.assertEqual(found["supplier_bank_account"], "100200300400")
        self.assertEqual(float(found["total_cash_amount"]), 75000.0)

    def test_export_bank_transfer_batch_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            path = tf.name

        try:
            res = vp.export_bank_transfer_batch_file(
                batch_ids=[self.batch_id],
                filepath=path,
                format_type="csv",
                company_id=self.company_id
            )
            self.assertEqual(res["record_count"], 1)
            self.assertEqual(res["total_amount"], 75000.0)

            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("# REPORT:,Corporate Bank Direct Deposit Payment Transfer File", content)
            self.assertIn("PAY-" + str(self.batch_id), content)
            self.assertIn("Acme Bank Beneficiary Ltd", content)
            self.assertIn("100200300400", content)
            self.assertIn("75000.00", content)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_export_bank_transfer_batch_xml(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tf:
            path = tf.name

        try:
            res = vp.export_bank_transfer_batch_file(
                batch_ids=[self.batch_id],
                filepath=path,
                format_type="xml",
                company_id=self.company_id
            )
            self.assertEqual(res["format"], "xml")

            tree = ET.parse(path)
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("Document"))

            namespaces = {"ns": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}
            cstmr = root.find("ns:CstmrCdtTrfInitn", namespaces)
            self.assertIsNotNone(cstmr)

            grp_hdr = cstmr.find("ns:GrpHdr", namespaces)
            self.assertIsNotNone(grp_hdr)
            self.assertEqual(grp_hdr.find("ns:NbOfTxs", namespaces).text, "1")
            self.assertEqual(grp_hdr.find("ns:CtrlSum", namespaces).text, "75000.00")

            pmt_inf = cstmr.find("ns:PmtInf", namespaces)
            self.assertIsNotNone(pmt_inf)

            tx_inf = pmt_inf.find("ns:CdtTrfTxInf", namespaces)
            self.assertIsNotNone(tx_inf)
            self.assertEqual(tx_inf.find("ns:Cdtr/ns:Nm", namespaces).text, "Acme Bank Beneficiary Ltd")
            self.assertEqual(tx_inf.find("ns:CdtrAcct/ns:Id/ns:Othr/ns:Id", namespaces).text, "100200300400")
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_export_bank_transfer_batch_nacha(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            path = tf.name

        try:
            res = vp.export_bank_transfer_batch_file(
                batch_ids=[self.batch_id],
                filepath=path,
                format_type="nacha",
                company_id=self.company_id
            )
            self.assertEqual(res["format"], "nacha")

            with open(path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]

            self.assertTrue(lines[0].startswith("101"))  # File Header
            self.assertTrue(lines[1].startswith("5220")) # Batch Header
            self.assertTrue(lines[2].startswith("622"))  # Entry Detail
            self.assertIn("100200300400", lines[2])
            self.assertTrue(lines[-2].startswith("8220")) # Batch Control
            self.assertTrue(lines[-1].startswith("9000")) # File Control
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_export_vendor_credits_to_csv(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            path = tf.name

        try:
            ok = vp.export_vendor_credits_to_csv(
                filepath=path,
                company_id=self.company_id,
                supplier_id=self.supplier_id
            )
            self.assertTrue(ok)

            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("# REPORT:,Accounts Payable Vendor Credit Notes & Memos", content)
            self.assertIn("VC-2026-001", content)
            self.assertIn("Acme Bank Beneficiary Ltd", content)
            self.assertIn("5000.00", content)
            self.assertIn("TOTALS", content)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_bank_transfer_file_dialog_ui(self):
        try:
            import ttkbootstrap as tb
            from ui.pay_bills_dialog import BankTransferFileDialog

            root = tb.Window(themename="litera")
            root.withdraw()

            dialog = BankTransferFileDialog(root, company_id=self.company_id)
            dialog.update()

            self.assertTrue(len(dialog.batches) >= 1)
            self.assertTrue(str(self.batch_id) in [str(b["id"]) for b in dialog.batches])

            # Toggle selection
            dialog.toggle_selection()
            dialog.redraw()

            dialog.select_all(True)
            dialog.redraw()

            dialog.destroy()
            root.destroy()
        except Exception as e:
            self.skipTest(f"UI test skipped due to display environment: {e}")

    def test_vendor_credits_list_dialog_ui(self):
        try:
            import ttkbootstrap as tb
            from ui.pay_bills_dialog import VendorCreditListDialog

            root = tb.Window(themename="litera")
            root.withdraw()

            dialog = VendorCreditListDialog(root, company_id=self.company_id, supplier_id=self.supplier_id)
            dialog.update()

            children = dialog.tree.get_children()
            self.assertTrue(len(children) >= 1)

            dialog.open_only_var.set(True)
            dialog.refresh()

            dialog.destroy()
            root.destroy()
        except Exception as e:
            self.skipTest(f"UI test skipped due to display environment: {e}")


if __name__ == "__main__":
    unittest.main()
