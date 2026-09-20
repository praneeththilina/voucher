"""
Additional tests for admin password utilities in database.py
"""

import unittest
import os
import tempfile
import shutil

import database as db


class TestAdminPasswordUtilities(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_pwd_test.db")
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

    def test_default_password_verification(self):
        self.assertTrue(db.verify_admin_password("Praneeth1991"))
        self.assertFalse(db.verify_admin_password("WrongPassword"))
        self.assertFalse(db.verify_admin_password(""))

    def test_custom_password_update(self):
        db.set_admin_password("NewSecret2026")
        self.assertTrue(db.verify_admin_password("NewSecret2026"))
        self.assertFalse(db.verify_admin_password("Praneeth1991"))


if __name__ == "__main__":
    unittest.main()
