"""Tests for one-database-per-company storage and safe legacy migration."""

import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from company_store import CompanyStore
import database as db


class TestCompanyStore(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "legacy"
        self.target_dir = Path(self.test_dir) / "new"
        self.source_dir.mkdir(parents=True)
        self.source_path = self.source_dir / "vouchers.db"

        self.original_paths = (
            db.DB_PATH,
            db.DB_DIR,
            db.ATTACHMENTS_DIR,
            db.BACKUP_DIR,
        )
        db.DB_PATH = str(self.source_path)
        db.DB_DIR = str(self.source_dir)
        db.ATTACHMENTS_DIR = str(self.source_dir / "attachments")
        db.BACKUP_DIR = str(self.source_dir / "backups")
        db.init_db()

        second_id = db.create_company("Second Company")
        db.create_voucher(
            {
                "date": "2026-10-07",
                "paid_to": "First Supplier",
                "cash_given_by": "Owner",
                "company_id": 1,
            },
            [{"description": "First item", "amount": 100.0}],
            company_id=1,
        )
        db.create_voucher(
            {
                "date": "2026-10-07",
                "paid_to": "Second Supplier",
                "cash_given_by": "Owner",
                "company_id": second_id,
            },
            [{"description": "Second item", "amount": 200.0}],
            company_id=second_id,
        )

    def tearDown(self):
        db.set_current_user(None)
        (
            db.DB_PATH,
            db.DB_DIR,
            db.ATTACHMENTS_DIR,
            db.BACKUP_DIR,
        ) = self.original_paths
        db.invalidate_all_caches()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_new_database_starts_with_one_company(self):
        self.assertEqual(len(db.get_all_companies()), 2)
        fresh_path = Path(self.test_dir) / "fresh" / "company.db"
        db.configure_database(str(fresh_path))
        db.init_db()
        companies = db.get_all_companies()
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["id"], 1)

    def test_split_preserves_source_and_isolates_each_company(self):
        source_size = self.source_path.stat().st_size
        store = CompanyStore(self.target_dir)
        records = store.migrate_legacy_database(self.source_path)

        self.assertEqual(len(records), 2)
        self.assertTrue(self.source_path.exists())
        self.assertEqual(self.source_path.stat().st_size, source_size)
        self.assertEqual(
            len(list((self.target_dir / "legacy_backups").glob("*.db"))),
            1,
        )

        voucher_total = 0
        for record in records:
            conn = sqlite3.connect(record.path)
            company_count = conn.execute(
                "SELECT COUNT(*) FROM companies"
            ).fetchone()[0]
            wrong_company_rows = conn.execute(
                "SELECT COUNT(*) FROM vouchers WHERE company_id != ?",
                (record.company_id,),
            ).fetchone()[0]
            voucher_total += conn.execute(
                "SELECT COUNT(*) FROM vouchers"
            ).fetchone()[0]
            violations = conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            conn.close()

            self.assertEqual(company_count, 1)
            self.assertEqual(wrong_company_rows, 0)
            self.assertEqual(violations, [])

        self.assertEqual(voucher_total, 2)

    def test_registry_remembers_username_but_no_password(self):
        store = CompanyStore(self.target_dir)
        records = store.migrate_legacy_database(self.source_path)
        selected = records[0]
        store.remember_username(selected.path, "BookKeeper")

        refreshed = {
            item.path: item for item in store.list_companies()
        }[selected.path]
        self.assertEqual(refreshed.last_username, "bookkeeper")

        registry_text = store.registry_path.read_text(encoding="utf-8")
        registry = json.loads(registry_text)
        self.assertTrue(registry)
        self.assertNotIn("password", registry_text.lower())
        self.assertNotIn("recovery", registry_text.lower())


if __name__ == "__main__":
    unittest.main()
