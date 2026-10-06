"""
Unit tests for check PDF generation in check_printer.py.
"""

import unittest
import os
import tempfile
import shutil
import database as db
import check_printer


class TestCheckPrinter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.test_dir, "test_vouchers.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_generate_single_check_with_stub(self):
        tmpls = db.get_check_templates(company_id=1)
        self.assertTrue(len(tmpls) > 0)
        tmpl_id = tmpls[0]["id"]

        cid = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "ABC Engineering Solutions",
            "amount": 75400.0,
            "currency": "LKR",
            "status": "Issued",
            "memo": "Structural engineering consultation fee",
            "check_date": "2026-10-05"
        }, actor="TestAdmin")

        out_pdf = os.path.join(self.test_dir, "check_single.pdf")
        res_path = check_printer.generate_check_pdf([cid], output_path=out_pdf, include_stub=True)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 1000)

    def test_generate_check_only_no_stub(self):
        tmpls = db.get_check_templates(company_id=1)
        tmpl_id = tmpls[0]["id"]

        cid = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Quick Printing Services",
            "amount": 12500.50,
            "currency": "LKR",
            "status": "Draft",
            "check_date": "2026-10-05"
        }, actor="TestAdmin")

        out_pdf = os.path.join(self.test_dir, "check_no_stub.pdf")
        res_path = check_printer.generate_check_pdf([cid], output_path=out_pdf, include_stub=False)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 1000)

    def test_generate_batch_checks(self):
        tmpls = db.get_check_templates(company_id=1)
        tmpl_id = tmpls[0]["id"]

        cid1 = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Payee 1",
            "amount": 5000.0,
        })
        cid2 = db.create_check({
            "company_id": 1,
            "template_id": tmpl_id,
            "payee_name": "Payee 2",
            "amount": 8500.0,
        })

        out_pdf = os.path.join(self.test_dir, "checks_batch.pdf")
        res_path = check_printer.generate_check_pdf([cid1, cid2], output_path=out_pdf)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 2000)

    def test_generate_calibration_pdf(self):
        out_pdf = os.path.join(self.test_dir, "calibration.pdf")
        res_path = check_printer.generate_calibration_pdf(output_path=out_pdf)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 1000)


if __name__ == "__main__":
    unittest.main()
