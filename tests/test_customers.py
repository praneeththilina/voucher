"""
Unit tests for Customers & Customer Directory (v3.8).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db


class TestCustomers(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_customers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migration 26)
        db.init_db()
        self.conn = db.get_connection()

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_migration_26_tables_exist(self):
        """Verify Migration 26 creates customers and AR tables."""
        tables = [r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        self.assertIn("customers", tables)
        self.assertIn("ar_invoices", tables)
        self.assertIn("ar_invoice_lines", tables)
        self.assertIn("ar_receipts", tables)

    def test_create_and_get_customer(self):
        """Test creating and retrieving a customer profile."""
        data = {
            "company_id": 1,
            "name": "Apex Retail Stores Ltd",
            "contact_person": "Robert Perera",
            "address": "120 Kandy Road, Kiribathgoda",
            "phone": "+94 11 987 6543",
            "email": "purchasing@apexretail.lk",
            "tax_id": "VAT-987654321",
            "credit_limit": 500000.0,
            "payment_terms": 30,
            "bank_name": "Commercial Bank",
            "bank_account": "1002345678",
            "notes": "VIP Wholesale Customer",
            "is_active": 1
        }
        cid = db.create_customer(data, conn=self.conn)
        self.assertIsNotNone(cid)

        cust = db.get_customer_by_id(cid, conn=self.conn)
        self.assertIsNotNone(cust)
        self.assertEqual(cust["name"], "Apex Retail Stores Ltd")
        self.assertEqual(cust["contact_person"], "Robert Perera")
        self.assertEqual(cust["credit_limit"], 500000.0)
        self.assertEqual(cust["payment_terms"], 30)
        self.assertEqual(cust["is_active"], 1)

    def test_update_customer(self):
        """Test updating customer information."""
        cid = db.create_customer({
            "company_id": 1,
            "name": "Quick Mart",
            "phone": "111",
            "credit_limit": 100000.0,
            "payment_terms": 15
        }, conn=self.conn)

        ok = db.update_customer(cid, {
            "name": "Quick Mart Supermarkets PLC",
            "contact_person": "Ms. De Silva",
            "phone": "222",
            "email": "accounts@quickmart.com",
            "credit_limit": 250000.0,
            "payment_terms": 45,
            "is_active": 1
        }, conn=self.conn)
        self.assertTrue(ok)

        updated = db.get_customer_by_id(cid, conn=self.conn)
        self.assertEqual(updated["name"], "Quick Mart Supermarkets PLC")
        self.assertEqual(updated["credit_limit"], 250000.0)
        self.assertEqual(updated["payment_terms"], 45)
        self.assertEqual(updated["phone"], "222")

    def test_delete_customer_without_invoices_succeeds(self):
        """Test deleting a customer with no invoices succeeds."""
        cid = db.create_customer({"company_id": 1, "name": "One-Time Customer"}, conn=self.conn)
        success, msg = db.delete_customer(cid, conn=self.conn)
        self.assertTrue(success)
        self.assertIsNone(db.get_customer_by_id(cid, conn=self.conn))

    def test_delete_customer_with_invoices_blocked(self):
        """Test deleting a customer with AR invoices is blocked."""
        cid = db.create_customer({"company_id": 1, "name": "Client with Invoices"}, conn=self.conn)

        # Create an AR invoice
        rev_acct = db.get_account_by_code("4110", 1, conn=self.conn)
        db.create_ar_invoice({
            "company_id": 1,
            "customer_id": cid,
            "invoice_number": "INV-BLOCKED-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "IT Support Services", "account_id": rev_acct["id"], "quantity": 1, "unit_price": 45000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 45000.0}
        ], conn=self.conn)

        success, msg = db.delete_customer(cid, conn=self.conn)
        self.assertFalse(success)
        self.assertIn("invoice(s) on record", msg)
        self.assertIsNotNone(db.get_customer_by_id(cid, conn=self.conn))

    def test_get_customers_with_balances(self):
        """Test retrieving customers with calculated balance totals and search filtering."""
        c1_id = db.create_customer({"company_id": 1, "name": "Alpha Corp", "phone": "0771112233"}, conn=self.conn)
        c2_id = db.create_customer({"company_id": 1, "name": "Beta Industries", "phone": "0774445566"}, conn=self.conn)

        rev_acct = db.get_account_by_code("4110", 1, conn=self.conn)

        # Add invoice for Alpha
        db.create_ar_invoice({
            "company_id": 1,
            "customer_id": c1_id,
            "invoice_number": "INV-ALPHA-01",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30"
        }, [
            {"description": "Consulting Services", "account_id": rev_acct["id"], "quantity": 1, "unit_price": 50000.0, "tax_rate": 0.0, "tax_amount": 0.0, "line_total": 50000.0}
        ], conn=self.conn)

        customers = db.get_customers(company_id=1, conn=self.conn)
        self.assertEqual(len(customers), 2)

        alpha = next(c for c in customers if c["id"] == c1_id)
        beta = next(c for c in customers if c["id"] == c2_id)

        self.assertEqual(alpha["total_invoiced"], 50000.0)
        self.assertEqual(alpha["balance_due"], 50000.0)
        self.assertEqual(beta["total_invoiced"], 0.0)

        # Search test
        searched = db.get_customers(company_id=1, search="Beta", conn=self.conn)
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0]["name"], "Beta Industries")

    def test_customer_csv_export_sanitization(self):
        """Verify customer fields with formula triggers are sanitized via _sanitize_csv_row."""
        data = {
            "company_id": 1,
            "name": "=CMD|' /C calc'!A1",
            "contact_person": "+94771234567",
            "email": "@evil.com",
            "address": "-100 Main Street",
            "phone": "0771234567",
            "tax_id": "VAT-123",
            "credit_limit": 1000.0,
            "payment_terms": 30,
            "bank_name": "=SUM(A1:A10)",
            "bank_account": "1234567890",
            "is_active": 1
        }
        cid = db.create_customer(data, conn=self.conn)
        cust = db.get_customer_by_id(cid, conn=self.conn)

        raw_row = [
            cust["id"], cust["name"], cust.get("contact_person", ""),
            cust.get("phone", ""), cust.get("email", ""), cust.get("address", ""),
            cust.get("tax_id", ""), cust.get("credit_limit", 0.0), cust.get("payment_terms", 30),
            cust.get("bank_name", ""), cust.get("bank_account", ""),
            0.0, 0.0, 0.0, "Active"
        ]
        sanitized = db._sanitize_csv_row(raw_row)

        self.assertTrue(sanitized[1].startswith("'="))
        self.assertTrue(sanitized[2].startswith("'+"))
        self.assertTrue(sanitized[4].startswith("'@"))
        self.assertTrue(sanitized[5].startswith("'-"))
        self.assertTrue(sanitized[9].startswith("'="))


if __name__ == "__main__":
    unittest.main()
