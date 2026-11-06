"""
Unit tests for Suppliers & Vendor Management (v3.5).
"""

import unittest
import sqlite3
import os
import tempfile
import shutil
import database as db
from tests.test_widgets import get_test_root
from ui.supplier_manager import SupplierEditModal


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

    def test_supplier_csv_export_sanitization(self):
        """Verify supplier fields with formula triggers are sanitized via _sanitize_csv_row."""
        data = {
            "company_id": 1,
            "name": "=SUM(1+1)",
            "contact_person": "@contact",
            "phone": "+94770000000",
            "email": "vendor@test.com",
            "address": "-20 Industrial Zone",
            "tax_id": "VAT-999",
            "payment_terms": 30,
            "bank_name": "National Bank",
            "bank_account": "111222333",
            "notes": "=EXCEL_FORMULA",
            "is_active": 1
        }
        sid = db.create_supplier(data, conn=self.conn)
        sup = db.get_supplier_by_id(sid, conn=self.conn)

        raw_row = [
            sup["name"],
            sup.get("contact_person") or "",
            sup.get("phone") or "",
            sup.get("email") or "",
            sup.get("address") or "",
            sup.get("tax_id") or "",
            sup.get("payment_terms") or 30,
            sup.get("bank_name") or "",
            sup.get("bank_account") or "",
            "0.00",
            "0.00",
            "Active",
            sup.get("notes") or ""
        ]
        sanitized = db._sanitize_csv_row(raw_row)

        self.assertTrue(sanitized[0].startswith("'="))
        self.assertTrue(sanitized[1].startswith("'@"))
        self.assertTrue(sanitized[2].startswith("'+"))
        self.assertTrue(sanitized[4].startswith("'-"))
        self.assertTrue(sanitized[12].startswith("'="))

    def test_get_suppliers_available_credit_aggregation(self):
        """Verify get_suppliers accurately aggregates available vendor credits and invoice stats."""
        s1 = db.create_supplier({"company_id": 1, "name": "Credit Vendor A"}, conn=self.conn)
        s2 = db.create_supplier({"company_id": 1, "name": "Credit Vendor B"}, conn=self.conn)

        # Invoices for s1
        db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": s1,
            "invoice_number": "INV-CR-1",
            "invoice_date": "2026-10-01",
            "due_date": "2026-10-31"
        }, [{"description": "Service", "quantity": 1, "unit_price": 1000.0, "line_total": 1000.0}], conn=self.conn)

        # Open Vendor Credits for s1 (500 + 250 = 750)
        self.conn.execute("""
            INSERT INTO vendor_credits (company_id, supplier_id, credit_number, credit_date, amount, remaining_amount, expense_account_id, status)
            VALUES (1, ?, 'VC-001', '2026-10-02', 500.0, 500.0, 1, 'Open')
        """, (s1,))
        self.conn.execute("""
            INSERT INTO vendor_credits (company_id, supplier_id, credit_number, credit_date, amount, remaining_amount, expense_account_id, status)
            VALUES (1, ?, 'VC-002', '2026-10-03', 300.0, 250.0, 1, 'Open')
        """, (s1,))
        # Closed Vendor Credit for s1 (should not be included)
        self.conn.execute("""
            INSERT INTO vendor_credits (company_id, supplier_id, credit_number, credit_date, amount, remaining_amount, expense_account_id, status)
            VALUES (1, ?, 'VC-003', '2026-10-03', 100.0, 100.0, 1, 'Closed')
        """, (s1,))

        # Open Vendor Credit with exchange rate for s2
        self.conn.execute("""
            INSERT INTO vendor_credits (company_id, supplier_id, credit_number, credit_date, amount, remaining_amount, expense_account_id, status, exchange_rate)
            VALUES (1, ?, 'VC-004', '2026-10-04', 100.0, 100.0, 1, 'Open', 2.0)
        """, (s2,))

        self.conn.commit()

        suppliers = db.get_suppliers(company_id=1, conn=self.conn)
        s_map = {s["name"]: s for s in suppliers}

        self.assertIn("Credit Vendor A", s_map)
        self.assertIn("Credit Vendor B", s_map)

        # Credit Vendor A: 500 + 250 = 750 available credit, 1 invoice, balance_due 1000
        self.assertEqual(s_map["Credit Vendor A"]["available_credit"], 750.0)
        self.assertEqual(s_map["Credit Vendor A"]["total_invoiced"], 1000.0)
        self.assertEqual(s_map["Credit Vendor A"]["balance_due"], 1000.0)
        self.assertEqual(s_map["Credit Vendor A"]["invoice_count"], 1)

        # Credit Vendor B: 100 * 2.0 = 200 available credit, 0 invoices
        self.assertEqual(s_map["Credit Vendor B"]["available_credit"], 200.0)
        self.assertEqual(s_map["Credit Vendor B"]["invoice_count"], 0)


    def test_supplier_form_commands_are_visible_and_save(self):
        """Create/edit form reserves a visible footer for Save and Cancel."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        dialog = SupplierEditModal(root, company_id=1)
        root.update()
        self.assertEqual(dialog.button_bar.winfo_manager(), "pack")
        self.assertEqual(dialog.save_btn.winfo_manager(), "pack")
        self.assertEqual(dialog.cancel_btn.winfo_manager(), "pack")
        button_bottom = (
            dialog.save_btn.winfo_rooty() + dialog.save_btn.winfo_height()
        )
        window_bottom = dialog.winfo_rooty() + dialog.winfo_height()
        self.assertLessEqual(button_bottom, window_bottom)

        dialog.name_var.set("Visible Commands Vendor")
        dialog.save_btn.invoke()
        self.assertFalse(dialog.winfo_exists())
        supplier = db.get_supplier_by_name(
            "Visible Commands Vendor", company_id=1
        )
        self.assertIsNotNone(supplier)

        edit_dialog = SupplierEditModal(
            root,
            company_id=1,
            supplier_data=supplier,
        )
        root.update()
        self.assertEqual(edit_dialog.save_btn.winfo_manager(), "pack")
        self.assertEqual(edit_dialog.cancel_btn.winfo_manager(), "pack")
        edit_dialog.contact_var.set("Updated Contact")
        edit_dialog.save_btn.invoke()
        self.assertFalse(edit_dialog.winfo_exists())
        updated = db.get_supplier_by_id(supplier["id"])
        self.assertEqual(updated["contact_person"], "Updated Contact")

        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
