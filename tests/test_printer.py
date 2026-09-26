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

    def test_non_image_assumed_as_pdf(self):
        """Verify non-image attachments are assumed to be PDFs."""
        self.assertTrue(printer._is_pdf_attachment({"filename": "invoice.pdf", "file_type": "application/pdf"}))
        self.assertTrue(printer._is_pdf_attachment({"filename": "document.doc", "file_type": "application/pdf"}))
        self.assertTrue(printer._is_pdf_attachment({"filename": "unknown_file", "file_type": ""}))
        # An actual image should NOT be considered a PDF
        self.assertFalse(printer._is_pdf_attachment({"filename": "receipt.jpg", "file_type": "image/jpeg"}))

    def test_prepare_image_for_pdf_transparent_png(self):
        """Verify transparent PNGs are composited onto pure white to prevent black background boxes."""
        import io
        from PIL import Image as PILImage

        # Create a 10x10 RGBA image: top half transparent (0,0,0,0), bottom half solid red (255,0,0,255)
        img = PILImage.new("RGBA", (10, 10), (0, 0, 0, 0))
        for x in range(10):
            for y in range(5, 10):
                img.putpixel((x, y), (255, 0, 0, 255))

        clean_img = printer._prepare_image_for_pdf(img)

        # Output must be RGB mode
        self.assertEqual(clean_img.mode, "RGB")

        # The previously transparent top pixel must now be pure white (255, 255, 255), NOT black!
        self.assertEqual(clean_img.getpixel((0, 0)), (255, 255, 255))
        # The bottom red pixel must remain red (255, 0, 0)
        self.assertEqual(clean_img.getpixel((0, 9)), (255, 0, 0))

    def test_voucher_pdf_with_transparent_png_logo(self):
        """Verify voucher PDF generation works cleanly when company has a transparent PNG logo."""
        import io
        from PIL import Image as PILImage

        # Create transparent PNG logo in memory
        logo_img = PILImage.new("RGBA", (100, 40), (0, 0, 0, 0))
        for x in range(10, 90):
            for y in range(10, 30):
                logo_img.putpixel((x, y), (30, 64, 175, 255))

        buf = io.BytesIO()
        logo_img.save(buf, format="PNG")
        logo_bytes = buf.getvalue()

        # Update company 1 logo in DB
        db.save_company(1, {"logo": logo_bytes})

        # Create voucher
        data = {
            "date": "2026-09-26",
            "paid_to": "Transparent Logo Vendor",
            "cash_given_by": "Finance",
            "spent_by": "Staff",
            "bill_status": "Received",
        }
        items = [{"description": "Office Supplies", "category": "General", "amount": 450.0}]
        v_id = db.create_voucher(data, items, company_id=1)

        pdf_output = os.path.join(self.test_dir, "logo_output.pdf")
        generated_path = printer.generate_voucher_pdf([v_id], output_path=pdf_output)

        self.assertTrue(os.path.exists(generated_path))
        self.assertGreater(os.path.getsize(generated_path), 0)


if __name__ == "__main__":
    unittest.main()


