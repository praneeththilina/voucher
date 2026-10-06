"""
Unit tests for Suppliers & Vendor Management (v3.5).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db


class TestSuppliers(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_suppliers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migration 25)
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_25_tables_exist(self):
        """Verify Migration 25 creates suppliers and AP tables."""
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("suppliers", tables)
        self.assertIn("ap_invoices", tables)
        self.assertIn("ap_invoice_lines", tables)
        self.assertIn("ap_payments", tables)

    def test_create_and_get_supplier(self):
        """Test creating and retrieving a supplier profile."""
        data = {
            "company_id": 1,
            "name": "Acme Office Supplies Ltd",
            "contact_person": "Jane Doe",
            "address": "45 Galle Road, Colombo 03",
            "phone": "+94 11 234 5678",
            "email": "sales@acme.lk",
            "tax_id": "VAT-123456789",
            "payment_terms": 30,
            "bank_name": "Commercial Bank",
            "bank_account": "1002345678",
            "notes": "Primary stationery vendor",
            "is_active": 1
        }
        sid = db.create_supplier(data, conn=self.conn)
        self.assertIsNotNone(sid)

        supplier = db.get_supplier_by_id(sid, conn=self.conn)
        self.assertIsNotNone(supplier)
        self.assertEqual(supplier["name"], "Acme Office Supplies Ltd")
        self.assertEqual(supplier["contact_person"], "Jane Doe")
        self.assertEqual(supplier["payment_terms"], 30)
        self.assertEqual(supplier["is_active"], 1)

    def test_update_supplier(self):
        """Test updating supplier information."""
        sid = db.create_supplier({
            "company_id": 1,
            "name": "Global Tech",
            "phone": "111",
            "payment_terms": 14
        }, conn=self.conn)

        ok = db.update_supplier(sid, {
            "name": "Global Tech Solutions PLC",
            "contact_person": "Mr. Smith",
            "phone": "222",
            "email": "info@globaltech.com",
            "payment_terms": 45,
            "is_active": 1
        }, conn=self.conn)
        self.assertTrue(ok)

        updated = db.get_supplier_by_id(sid, conn=self.conn)
        self.assertEqual(updated["name"], "Global Tech Solutions PLC")
        self.assertEqual(updated["payment_terms"], 45)
        self.assertEqual(updated["phone"], "222")

    def test_delete_supplier_without_invoices_succeeds(self):
        """Test deleting a supplier with no invoices succeeds."""
        sid = db.create_supplier({"company_id": 1, "name": "Temporary Vendor"}, conn=self.conn)
        success, msg = db.delete_supplier(sid, conn=self.conn)
        self.assertTrue(success)
        self.assertIsNone(db.get_supplier_by_id(sid, conn=self.conn))

    def test_delete_supplier_with_invoices_blocked(self):
        """Test deleting a supplier with AP invoices is blocked."""
        sid = db.create_supplier({"company_id": 1, "name": "Active Vendor with Invoices"}, conn=self.conn)

        # Create an AP invoice for this supplier
        inv_data = {
            "company_id": 1,
            "supplier_id": sid,
            "invoice_number": "INV-TEST-001",
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-31"
        }
        lines = [{"description": "Services", "quantity": 1, "unit_price": 5000.0, "line_total": 5000.0}]
        db.create_ap_invoice(inv_data, lines, conn=self.conn)

        success, msg = db.delete_supplier(sid, conn=self.conn)
        self.assertFalse(success)
        self.assertIn("invoice(s) on record", msg)

    def test_get_suppliers_search_and_filter(self):
        """Test searching and filtering suppliers."""
        db.create_supplier({"company_id": 1, "name": "Alpha Logistics", "phone": "0771234567", "is_active": 1}, conn=self.conn)
        db.create_supplier({"company_id": 1, "name": "Beta Packaging", "phone": "0779999999", "is_active": 0}, conn=self.conn)

        # Search by name
        res = db.get_suppliers(company_id=1, search="Alpha", conn=self.conn)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["name"], "Alpha Logistics")

        # Filter active only
        active_list = db.get_suppliers(company_id=1, active_only=True, conn=self.conn)
        names = [s["name"] for s in active_list]
        self.assertIn("Alpha Logistics", names)
        self.assertNotIn("Beta Packaging", names)


if __name__ == "__main__":
    unittest.main()
