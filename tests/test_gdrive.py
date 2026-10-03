"""
Unit tests for Google Drive integration module (gdrive_client.py).
Tests folder detection, attachment synchronization, database backup snapshots,
and configuration persistence.
"""

import os
import shutil
import tempfile
import unittest

import database as db
import gdrive_client


class TestGDriveIntegration(unittest.TestCase):

    def setUp(self):
        db.init_db()
        self.temp_gdrive_dir = tempfile.mkdtemp(prefix="test_gdrive_")
        # Save temporary folder configuration
        gdrive_client.save_config({
            "enabled": True,
            "folder_path": self.temp_gdrive_dir,
            "backup_database": True,
            "organize_by_month": True
        })

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_gdrive_dir, ignore_errors=True)
        except Exception:
            pass

    def test_detect_google_drive_paths(self):
        """Verify detector runs without error and returns list of strings."""
        paths = gdrive_client.detect_google_drive_paths()
        self.assertIsInstance(paths, list)
        for p in paths:
            self.assertIsInstance(p, str)
            self.assertTrue(os.path.exists(p))

    def test_config_persistence(self):
        """Test reading and writing Google Drive config in database."""
        gdrive_client.save_config({
            "enabled": True,
            "folder_path": self.temp_gdrive_dir,
            "backup_database": True,
            "organize_by_month": False
        })
        cfg = gdrive_client.get_config()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(os.path.abspath(cfg["folder_path"]), os.path.abspath(self.temp_gdrive_dir))
        self.assertTrue(cfg["backup_database"])
        self.assertFalse(cfg["organize_by_month"])

    def test_validate_folder_path(self):
        """Test validation of valid directory vs invalid/empty directory."""
        ok, res = gdrive_client.validate_folder_path(self.temp_gdrive_dir)
        self.assertTrue(ok)

        ok_bad, msg = gdrive_client.validate_folder_path("")
        self.assertFalse(ok_bad)

    def test_sync_voucher_attachments(self):
        """Test syncing voucher attachments to Google Drive folder."""
        # Create a voucher with an attachment
        form_data = {
            "date": "2026-10-03",
            "paid_to": "GDrive Test Vendor",
            "cash_given_by": "Finance Manager",
            "spent_by": "Staff B",
            "bill_status": "Received",
            "payment_method": "Cash",
            "voucher_number": "GDRIVE_01"
        }
        items = [{"description": "Cloud storage test", "category": "General", "amount": 2500.0}]
        sample_file_data = b"%PDF-1.4 Fake PDF Content for Google Drive Backup"
        attachment_list = [
            {"filename": "receipt_scan.pdf", "file_data": sample_file_data, "file_type": "application/pdf"}
        ]

        vid = db.create_voucher(form_data, items, attachment_list=attachment_list, company_id=1)
        self.assertIsNotNone(vid)

        # Sync attachments
        count, paths = gdrive_client.sync_voucher_attachments(vid)
        self.assertEqual(count, 1)
        self.assertEqual(len(paths), 1)

        dest_file = paths[0]
        self.assertTrue(os.path.exists(dest_file))
        with open(dest_file, "rb") as f:
            content = f.read()
        self.assertEqual(content, sample_file_data)

        # Verify Google Drive subfolder structure
        self.assertIn("Voucher_Attachments", dest_file)
        self.assertIn("2026-10", dest_file)
        self.assertIn("Voucher_", dest_file)
        self.assertTrue(dest_file.endswith("receipt_scan.pdf"))


    def test_backup_database_to_gdrive(self):
        """Test database snapshot is properly saved to Google Drive backup folder."""
        dest = gdrive_client.backup_database_to_gdrive()
        self.assertIsNotNone(dest)
        self.assertTrue(os.path.exists(dest))
        self.assertIn("Database_Backups", dest)
        self.assertTrue(dest.endswith(".db"))

    def test_sync_voucher_attachments_unsafe_path_prevention(self):
        """Verify that sync_voucher_attachments refuses to copy files with unsafe external file paths."""
        form_data = {
            "date": "2026-10-03",
            "paid_to": "Unsafe Path Vendor",
            "cash_given_by": "Manager",
            "voucher_number": "UNSAFE_01"
        }
        items = [{"description": "Item", "amount": 100.0}]
        vid = db.create_voucher(form_data, items, attachment_list=None, company_id=1)

        # Inject an attachment record with an external file_path outside ATTACHMENTS_DIR
        outside_file = os.path.join(tempfile.gettempdir(), "sensitive_outside_file.txt")
        with open(outside_file, "w") as f:
            f.write("sensitive data")

        try:
            conn = db.get_connection()
            conn.execute(
                "INSERT INTO attachments (voucher_id, filename, file_path, file_size, file_type) VALUES (?, ?, ?, ?, ?)",
                (vid, "sensitive.txt", outside_file, 14, "text/plain")
            )
            conn.commit()
            conn.close()

            count, paths = gdrive_client.sync_voucher_attachments(vid)
            self.assertEqual(count, 0)
            self.assertEqual(len(paths), 0)
        finally:
            if os.path.exists(outside_file):
                os.remove(outside_file)

    def test_sync_all_existing_attachments(self):
        """Test bulk synchronization of all vouchers with attachments."""
        # Create voucher
        form_data = {
            "date": "2026-10-03",
            "paid_to": "Bulk Vendor",
            "cash_given_by": "Manager",
            "voucher_number": "BULK_01"
        }
        items = [{"description": "Item", "amount": 100.0}]
        attachment_list = [
            {"filename": "bulk_invoice.pdf", "file_data": b"Invoice Content", "file_type": "application/pdf"}
        ]
        db.create_voucher(form_data, items, attachment_list=attachment_list, company_id=1)

        ok, count, msg = gdrive_client.sync_all_existing_attachments()
        self.assertTrue(ok)
        self.assertGreaterEqual(count, 1)

    def test_get_status(self):
        """Test status dictionary output."""
        status = gdrive_client.get_status()
        self.assertTrue(status["enabled"])
        self.assertTrue(status["folder_exists"])
        self.assertGreaterEqual(status["total_attachments"], 0)


if __name__ == "__main__":
    unittest.main()
