"""
Unit tests for database layer (database.py).
"""

import unittest
import os
import tempfile
import sqlite3
import shutil

# Override database path for testing before importing database
import database as db


class TestDatabaseLayer(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_test.db")
        self.attachments_dir = os.path.join(self.test_dir, "attachments")
        self.backup_dir = os.path.join(self.test_dir, "backups")

        # Monkey-patch database paths
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

    def test_company_creation_and_retrieval(self):
        companies = db.get_all_companies()
        self.assertGreaterEqual(len(companies), 2)
        c1 = db.get_company(1)
        self.assertIsNotNone(c1)
        self.assertEqual(c1["name"], "Company 1")

        # Update company profile
        db.save_company(1, {"name": "Updated Company 1", "tagline": "Best SME"})
        c1_updated = db.get_company(1)
        self.assertEqual(c1_updated["name"], "Updated Company 1")
        self.assertEqual(c1_updated["tagline"], "Best SME")

    def test_active_company_switch(self):
        self.assertEqual(db.get_active_company_id(), 1)
        db.set_active_company_id(2)
        self.assertEqual(db.get_active_company_id(), 2)

    def test_voucher_number_generation(self):
        # Date based numbering
        vn1 = db.get_next_voucher_number(company_id=1)
        self.assertTrue(vn1.startswith("V-"))

        # Create voucher to verify increment
        data = {
            "date": "2026-09-18",
            "paid_to": "John Doe",
            "cash_given_by": "Manager",
            "spent_by": "John Doe",
            "bill_status": "Pending",
        }
        line_items = [{"description": "Office Supplies", "category": "Stationery", "amount": 150.0}]
        v_id = db.create_voucher(data, line_items, company_id=1)
        self.assertIsNotNone(v_id)

        vn2 = db.get_next_voucher_number(company_id=1, voucher_date="2026-09-18")
        self.assertNotEqual(vn1, vn2)

    def test_monthly_voucher_number_generation(self):
        # Configure company 1 with month_based numbering
        db.save_company(1, {"voucher_format": "month_based"})

        # Month: August 2026
        vn_aug_1 = db.get_next_voucher_number(company_id=1, voucher_date="2026-08-10")
        self.assertEqual(vn_aug_1, "26AUG_01")

        # Create first voucher in August
        v1 = db.create_voucher({
            "date": "2026-08-10",
            "voucher_number": vn_aug_1,
            "paid_to": "Vendor A",
            "cash_given_by": "Manager",
        }, [{"description": "Item 1", "amount": 100.0}], company_id=1)
        self.assertIsNotNone(v1)

        # Second voucher in August should be 26AUG_02
        vn_aug_2 = db.get_next_voucher_number(company_id=1, voucher_date="2026-08-15")
        self.assertEqual(vn_aug_2, "26AUG_02")

        # Create second voucher in August
        db.create_voucher({
            "date": "2026-08-15",
            "voucher_number": vn_aug_2,
            "paid_to": "Vendor B",
            "cash_given_by": "Manager",
        }, [{"description": "Item 2", "amount": 200.0}], company_id=1)

        # Third voucher candidate in August
        vn_aug_3 = db.get_next_voucher_number(company_id=1, voucher_date="2026-08-20")
        self.assertEqual(vn_aug_3, "26AUG_03")

        # New month: September 2026 should reset counter to 01 -> 26SEP_01
        vn_sep_1 = db.get_next_voucher_number(company_id=1, voucher_date="2026-09-01")
        self.assertEqual(vn_sep_1, "26SEP_01")

        # Create voucher in September
        db.create_voucher({
            "date": "2026-09-01",
            "voucher_number": vn_sep_1,
            "paid_to": "Vendor C",
            "cash_given_by": "Manager",
        }, [{"description": "Item 3", "amount": 300.0}], company_id=1)

        # Next in September should be 26SEP_02
        vn_sep_2 = db.get_next_voucher_number(company_id=1, voucher_date="2026-09-20")
        self.assertEqual(vn_sep_2, "26SEP_02")

        # Switching date back to August still yields 26AUG_03
        self.assertEqual(db.get_next_voucher_number(company_id=1, voucher_date="2026-08-25"), "26AUG_03")

        # Different Year: January 2027 should be 27JAN_01
        self.assertEqual(db.get_next_voucher_number(company_id=1, voucher_date="2027-01-05"), "27JAN_01")

    def test_voucher_crud(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "Jane Smith",
            "cash_given_by": "Cashier",
            "spent_by": "Jane Smith",
            "bill_status": "Pending",
            "payment_method": "Bank Transfer",
            "payment_ref": "TXN123456",
            "prepared_by": "Alice",
            "approved_by": "Bob",
        }
        line_items = [
            {"description": "Travel Expenses", "category": "Transport", "amount": 250.0},
            {"description": "Meals", "category": "Food", "amount": 50.0},
        ]
        v_id = db.create_voucher(data, line_items, company_id=1)

        v_data = db.get_voucher(v_id)
        self.assertIsNotNone(v_data)
        self.assertEqual(v_data["voucher"]["paid_to"], "Jane Smith")
        self.assertEqual(v_data["voucher"]["total_amount"], 300.0)
        self.assertEqual(v_data["voucher"]["payment_method"], "Bank Transfer")
        self.assertEqual(v_data["voucher"]["payment_ref"], "TXN123456")
        self.assertEqual(len(v_data["line_items"]), 2)

        # Update voucher
        data["paid_to"] = "Jane Smith Updated"
        new_line_items = [{"description": "Travel Expenses", "category": "Transport", "amount": 300.0}]
        db.update_voucher(v_id, data, new_line_items)

        updated_v = db.get_voucher(v_id)
        self.assertEqual(updated_v["voucher"]["paid_to"], "Jane Smith Updated")
        self.assertEqual(updated_v["voucher"]["total_amount"], 300.0)

        # Soft cancel
        db.cancel_voucher(v_id)
        canceled_v = db.get_voucher(v_id)
        self.assertEqual(canceled_v["voucher"]["status"], "Cancelled")

        # Restore
        db.restore_voucher(v_id)
        restored_v = db.get_voucher(v_id)
        self.assertEqual(restored_v["voucher"]["status"], "Active")

        # Permanent deletion
        db.cancel_voucher(v_id)
        deleted = db.permanently_delete_voucher(v_id)
        self.assertTrue(deleted)
        self.assertIsNone(db.get_voucher(v_id))

    def test_duplicate_voucher(self):
        source_data = {
            "date": "2026-09-18",
            "paid_to": "Duplicate Supplier",
            "cash_given_by": "Cashier Alpha",
            "spent_by": "Employee Beta",
            "bill_status": "Pending",
            "payment_method": "Bank Transfer",
            "payment_ref": "REF-9988",
            "prepared_by": "Preparer 1",
            "approved_by": "Approver 1",
        }
        line_items = [
            {"description": "Laptops", "category": "IT Hardware", "amount": 1500.0},
            {"description": "Monitors", "category": "IT Hardware", "amount": 600.0},
        ]
        source_id = db.create_voucher(source_data, line_items, company_id=1)
        self.assertIsNotNone(source_id)

        # Duplicate voucher
        dup_id = db.duplicate_voucher(source_id, target_date="2026-10-01", company_id=1)
        self.assertIsNotNone(dup_id)
        self.assertNotEqual(source_id, dup_id)

        dup_data = db.get_voucher(dup_id)
        self.assertIsNotNone(dup_data)
        v = dup_data["voucher"]

        self.assertEqual(v["date"], "2026-10-01")
        self.assertEqual(v["paid_to"], "Duplicate Supplier")
        self.assertEqual(v["cash_given_by"], "Cashier Alpha")
        self.assertEqual(v["spent_by"], "Employee Beta")
        self.assertEqual(v["payment_method"], "Bank Transfer")
        self.assertEqual(v["payment_ref"], "REF-9988")
        self.assertEqual(v["prepared_by"], "Preparer 1")
        self.assertEqual(v["approved_by"], "Approver 1")
        self.assertEqual(v["total_amount"], 2100.0)
        self.assertEqual(v["status"], "Active")

        dup_items = dup_data["line_items"]
        self.assertEqual(len(dup_items), 2)
        self.assertEqual(dup_items[0]["description"], "Laptops")
        self.assertEqual(dup_items[0]["amount"], 1500.0)
        self.assertEqual(dup_items[1]["description"], "Monitors")
        self.assertEqual(dup_items[1]["amount"], 600.0)

    def test_categories_and_people(self):
        cat_id = db.add_category("TestCategory")
        self.assertIsNotNone(cat_id)
        self.assertIn("TestCategory", db.get_categories())

        person_id = db.add_person("TestPerson")
        self.assertIsNotNone(person_id)
        self.assertIn("TestPerson", db.get_people())

    def test_search_vouchers(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "Unique Payee Name",
            "cash_given_by": "Admin",
            "spent_by": "Unique Payee Name",
            "bill_status": "Pending",
        }
        line_items = [{"description": "Special Keyword Description", "category": "General", "amount": 500.0}]
        db.create_voucher(data, line_items, company_id=1)

        results = db.search_vouchers(query="Unique Payee", company_id=1)
        self.assertEqual(len(results), 1)

        results_keyword = db.search_vouchers(query="Special Keyword", company_id=1)
        self.assertEqual(len(results_keyword), 1)

    def test_payment_method_filter(self):
        data1 = {
            "date": "2026-09-18",
            "paid_to": "Vendor X",
            "cash_given_by": "Manager",
            "payment_method": "Cheque",
            "payment_ref": "CHQ-001",
        }
        data2 = {
            "date": "2026-09-18",
            "paid_to": "Vendor Y",
            "cash_given_by": "Manager",
            "payment_method": "Credit Card",
            "payment_ref": "CC-99",
        }
        db.create_voucher(data1, [{"description": "Item A", "amount": 100.0}], company_id=1)
        db.create_voucher(data2, [{"description": "Item B", "amount": 200.0}], company_id=1)

        chq_results = db.search_vouchers(payment_method_filter="Cheque", company_id=1)
        self.assertEqual(len(chq_results), 1)
        self.assertEqual(chq_results[0]["payment_ref"], "CHQ-001")

        ref_query = db.search_vouchers(query="CHQ-001", company_id=1)
        self.assertEqual(len(ref_query), 1)

    def test_date_range_filter(self):
        from datetime import datetime, timedelta
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        yest_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        old_str = "2020-01-01"

        db.create_voucher({"date": today_str, "paid_to": "Today Vendor", "cash_given_by": "Manager"}, [{"description": "Item 1", "amount": 10.0}], company_id=1)
        db.create_voucher({"date": yest_str, "paid_to": "Yest Vendor", "cash_given_by": "Manager"}, [{"description": "Item 2", "amount": 20.0}], company_id=1)
        db.create_voucher({"date": old_str, "paid_to": "Old Vendor", "cash_given_by": "Manager"}, [{"description": "Item 3", "amount": 30.0}], company_id=1)

        today_results = db.search_vouchers(date_filter="Today", company_id=1)
        self.assertEqual(len(today_results), 1)
        self.assertEqual(today_results[0]["paid_to"], "Today Vendor")

        yest_results = db.search_vouchers(date_filter="Yesterday", company_id=1)
        self.assertEqual(len(yest_results), 1)
        self.assertEqual(yest_results[0]["paid_to"], "Yest Vendor")

        custom_results = db.search_vouchers(date_filter="Custom", start_date="2019-01-01", end_date="2020-12-31", company_id=1)
        self.assertEqual(len(custom_results), 1)
        self.assertEqual(custom_results[0]["paid_to"], "Old Vendor")

    def test_export_vouchers_to_csv(self):
        data = {
            "date": "2026-09-18",
            "paid_to": "CSV Supplier",
            "cash_given_by": "Finance",
            "spent_by": "CSV Supplier",
            "bill_status": "Received",
        }
        line_items = [{"description": "Hardware Purchase", "category": "Equipment", "amount": 1200.0}]
        v_id = db.create_voucher(data, line_items, company_id=1)
        vouchers = db.search_vouchers(query="CSV Supplier", company_id=1)

        csv_path = os.path.join(self.test_dir, "test_out.csv")
        db.export_vouchers_to_csv(vouchers, csv_path)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("CSV Supplier", content)
            self.assertIn("1200.00", content)
            self.assertIn("Hardware Purchase", content)
            self.assertIn("Equipment", content)
            self.assertIn("TOTAL", content)

    def test_export_vouchers_to_csv_formats(self):
        # Create a voucher with multiple line items
        data = {
            "date": "2026-09-20",
            "paid_to": "Mega Office Depot",
            "cash_given_by": "Finance Mgr",
            "spent_by": "Alice",
            "bill_status": "Received",
            "status": "Active",
        }
        items = [
            {"description": "A4 Paper Reams", "category": "Stationery", "amount": 3500.0},
            {"description": "Printer Ink", "category": "Stationery", "amount": 8000.0},
            {"description": "Staff Coffee & Milk", "category": "Welfare", "amount": 2200.0},
        ]
        v_id = db.create_voucher(data, items, company_id=1)
        vouchers = db.search_vouchers(query="Mega Office Depot", company_id=1)

        # 1. Test Itemized (General Ledger)
        csv_itemized = os.path.join(self.test_dir, "test_itemized.csv")
        db.export_vouchers_to_csv(vouchers, csv_itemized, format_type="itemized", include_total_row=True)
        with open(csv_itemized, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
            # Header + 3 line items + 1 Total row = 5 rows
            self.assertEqual(len(lines), 5)
            self.assertIn("Line Description", lines[0])
            self.assertIn("Category", lines[0])
            self.assertIn("A4 Paper Reams", lines[1])
            self.assertIn("Printer Ink", lines[2])
            self.assertIn("Staff Coffee & Milk", lines[3])
            self.assertIn("TOTAL", lines[4])
            self.assertIn("13700.00", lines[4])

        # 2. Test Register (Summary)
        csv_register = os.path.join(self.test_dir, "test_register.csv")
        db.export_vouchers_to_csv(vouchers, csv_register, format_type="register", include_total_row=True)
        with open(csv_register, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
            # Header + 1 voucher row + 1 Total row = 3 rows
            self.assertEqual(len(lines), 3)
            self.assertIn("Categories", lines[0])
            self.assertIn("Stationery, Welfare", lines[1])
            self.assertIn("3", lines[1])  # 3 items
            self.assertIn("13700.00", lines[1])
            self.assertIn("TOTAL", lines[2])

        # 3. Test Category Summary
        csv_cat = os.path.join(self.test_dir, "test_cat.csv")
        db.export_vouchers_to_csv(vouchers, csv_cat, format_type="category_summary", include_total_row=True)
        with open(csv_cat, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
            # Header + 2 categories (Stationery, Welfare) + 1 Total row = 4 rows
            self.assertEqual(len(lines), 4)
            self.assertIn("Category,Transaction Count,Total Amount,Share (%)", lines[0])
            self.assertIn("Stationery,2,11500.00", lines[1])
            self.assertIn("Welfare,1,2200.00", lines[2])
            self.assertIn("TOTAL,3,13700.00,100.0%", lines[3])

    def test_export_vouchers_active_only_and_no_total(self):
        # Create one active and one cancelled voucher
        d1 = {"date": "2026-09-21", "paid_to": "Active Vendor", "cash_given_by": "Finance", "spent_by": "Sam", "bill_status": "Pending"}
        v1 = db.create_voucher(d1, [{"description": "Active Item", "category": "General", "amount": 500.0}], company_id=1)

        d2 = {"date": "2026-09-22", "paid_to": "Cancelled Vendor", "cash_given_by": "Finance", "spent_by": "Sam", "bill_status": "Pending"}
        v2 = db.create_voucher(d2, [{"description": "Cancelled Item", "category": "General", "amount": 900.0}], company_id=1)
        db.cancel_voucher(v2)

        vouchers = [db.get_voucher(v1), db.get_voucher(v2)]

        csv_active = os.path.join(self.test_dir, "test_active.csv")
        db.export_vouchers_to_csv(vouchers, csv_active, format_type="itemized", include_total_row=False, active_only=True)
        with open(csv_active, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("Active Vendor", content)
            self.assertNotIn("Cancelled Vendor", content)
            self.assertNotIn("TOTAL", content)

    def test_export_expense_summary_to_csv(self):
        data1 = {
            "date": "2026-09-18",
            "paid_to": "Alpha Vendor",
            "cash_given_by": "Manager",
            "spent_by": "Alpha Vendor",
            "bill_status": "Pending",
        }
        line_items1 = [{"description": "Item 1", "category": "Utilities", "amount": 300.0}]
        db.create_voucher(data1, line_items1, company_id=1)

        summary = db.get_expense_summary(company_id=1, date_filter="all")

        csv_path = os.path.join(self.test_dir, "expense_summary_test.csv")
        db.export_expense_summary_to_csv(summary, csv_path, period_label="All Time", company_name="Company 1")

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("EXPENSE ANALYTICS SUMMARY REPORT", content)
            self.assertIn("Company 1", content)
            self.assertIn("All Time", content)
            self.assertIn("Utilities", content)
            self.assertIn("Alpha Vendor", content)
            self.assertIn("300.00", content)

    def test_csv_formula_injection_sanitization(self):
        # Directly test cell sanitization helper
        self.assertEqual(db._sanitize_csv_cell("=CMD|' /C calc'!A1"), "'=CMD|' /C calc'!A1")
        self.assertEqual(db._sanitize_csv_cell("+441234567"), "'+441234567")
        self.assertEqual(db._sanitize_csv_cell("-100"), "'-100")
        self.assertEqual(db._sanitize_csv_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(db._sanitize_csv_cell("\t=1+1"), "'\t=1+1")
        self.assertEqual(db._sanitize_csv_cell("Normal Text"), "Normal Text")
        self.assertEqual(db._sanitize_csv_cell(123.45), 123.45)

        # Create voucher with malicious CSV formula triggers
        data = {
            "date": "2026-09-20",
            "paid_to": "=CMD|' /C calc'!A1",
            "cash_given_by": "+4471234567",
            "spent_by": "@EVAL(1+1)",
            "bill_status": "Received",
        }
        line_items = [
            {"description": "@SUM(A1:A10)", "category": "-DangerousCat", "amount": 500.0}
        ]
        v_id = db.create_voucher(data, line_items, company_id=1)
        vouchers = db.search_vouchers(query="calc", company_id=1)

        csv_path = os.path.join(self.test_dir, "csv_injection_test.csv")
        db.export_vouchers_to_csv(vouchers, csv_path, format_type="itemized")

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("'=CMD|' /C calc'!A1", content)
            self.assertIn("'+4471234567", content)
            self.assertIn("'@EVAL(1+1)", content)
            self.assertIn("'@SUM(A1:A10)", content)
            self.assertIn("'-DangerousCat", content)

    def test_update_bill_status_batch(self):
        v1 = db.create_voucher({
            "date": "2026-09-18",
            "paid_to": "Vendor Batch 1",
            "cash_given_by": "Manager",
            "bill_status": "Pending",
        }, [{"description": "Item 1", "amount": 100.0}], company_id=1)

        v2 = db.create_voucher({
            "date": "2026-09-18",
            "paid_to": "Vendor Batch 2",
            "cash_given_by": "Manager",
            "bill_status": "Pending",
        }, [{"description": "Item 2", "amount": 150.0}], company_id=1)

        v3 = db.create_voucher({
            "date": "2026-09-18",
            "paid_to": "Vendor Batch 3",
            "cash_given_by": "Manager",
            "bill_status": "Pending",
        }, [{"description": "Item 3", "amount": 200.0}], company_id=1)

        # Single update via update_bill_status
        db.update_bill_status(v1, "Partial")
        self.assertEqual(db.get_voucher(v1)["voucher"]["bill_status"], "Partial")

        # Batch update via update_bill_status_batch
        count = db.update_bill_status_batch([v1, v2, v3], "Received")
        self.assertEqual(count, 3)
        self.assertEqual(db.get_voucher(v1)["voucher"]["bill_status"], "Received")
        self.assertEqual(db.get_voucher(v2)["voucher"]["bill_status"], "Received")
        self.assertEqual(db.get_voucher(v3)["voucher"]["bill_status"], "Received")

    def test_get_expense_summary(self):
        data1 = {
            "date": "2026-09-18",
            "paid_to": "Alpha Vendor",
            "cash_given_by": "Manager",
            "spent_by": "Alpha Vendor",
            "bill_status": "Pending",
        }
        line_items1 = [{"description": "Item 1", "category": "Utilities", "amount": 300.0}]
        db.create_voucher(data1, line_items1, company_id=1)

        data2 = {
            "date": "2026-09-18",
            "paid_to": "Alpha Vendor",
            "cash_given_by": "Manager",
            "spent_by": "Alpha Vendor",
            "bill_status": "Received",
        }
        line_items2 = [{"description": "Item 2", "category": "Utilities", "amount": 200.0}]
        db.create_voucher(data2, line_items2, company_id=1)

        data3 = {
            "date": "2026-09-18",
            "paid_to": "Beta Supplier",
            "cash_given_by": "Manager",
            "spent_by": "Beta Supplier",
            "bill_status": "Received",
            "payment_method": "Bank Transfer",
        }
        line_items3 = [{"description": "Item 3", "category": "Equipment", "amount": 1000.0}]
        db.create_voucher(data3, line_items3, company_id=1)

        summary = db.get_expense_summary(company_id=1, date_filter="all")
        self.assertEqual(summary["grand_total"], 1500.0)
        self.assertEqual(summary["voucher_count"], 3)
        self.assertGreaterEqual(len(summary["by_category"]), 1)

        # Verify by_payment_method breakdown
        pm_summary = {row["payment_method"]: row for row in summary["by_payment_method"]}
        self.assertIn("Cash", pm_summary)
        self.assertEqual(pm_summary["Cash"]["amount"], 500.0)
        self.assertEqual(pm_summary["Cash"]["count"], 2)

        self.assertIn("Bank Transfer", pm_summary)
        self.assertEqual(pm_summary["Bank Transfer"]["amount"], 1000.0)
        self.assertEqual(pm_summary["Bank Transfer"]["count"], 1)

    def test_attachment_path_traversal_prevention(self):
        # 1. Test _save_attachment_file strips path traversal characters
        disk_path, _ = db._save_attachment_file(1, "../../../etc/passwd", b"test content")
        self.assertTrue(db._is_safe_attachment_path(disk_path))
        self.assertNotIn("..", os.path.basename(disk_path))

        # Create voucher with attachment
        v_id = db.create_voucher({
            "date": "2026-09-18",
            "paid_to": "Att Vendor",
            "cash_given_by": "Manager",
        }, [{"description": "Item", "amount": 100.0}],
        attachment_list=[{"filename": "../evil.txt", "file_data": b"secret data"}],
        company_id=1)

        v_data = db.get_voucher(v_id)
        att_id = v_data["attachments"][0]["id"]

        # Verify normal retrieval works
        att_data = db.get_attachment_data(att_id)
        self.assertEqual(att_data["file_data"], b"secret data")

        # Inject malicious path traversal file_path into database attachment record
        conn = db.get_connection()
        malicious_path = os.path.abspath(os.path.join(self.test_dir, "vouchers_test.db"))
        conn.execute("UPDATE attachments SET file_path = ? WHERE id = ?", (malicious_path, att_id))
        conn.commit()
        conn.close()

        # Verify get_attachment_data refuses to read malicious path outside ATTACHMENTS_DIR
        att_data_mal = db.get_attachment_data(att_id)
        self.assertIsNone(att_data_mal.get("file_data"))

        # Verify delete_attachment refuses to delete malicious path outside ATTACHMENTS_DIR
        db.delete_attachment(att_id)
        self.assertTrue(os.path.exists(malicious_path))

    def test_backup_database_path_traversal_prevention(self):
        # Test that backup_database creates a backup safely with standard reason
        path = db.backup_database(reason="normal_test")
        self.assertIsNotNone(path)
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.commonpath([path, os.path.abspath(db.BACKUP_DIR)]) == os.path.abspath(db.BACKUP_DIR))

        # Test that relative path sequences in reason are sanitized and stay inside BACKUP_DIR
        traversal_reason = "../../../etc/cron.d/malicious"
        path_trav = db.backup_database(reason=traversal_reason)
        self.assertIsNotNone(path_trav)
        self.assertTrue(os.path.exists(path_trav))
        self.assertTrue(os.path.commonpath([path_trav, os.path.abspath(db.BACKUP_DIR)]) == os.path.abspath(db.BACKUP_DIR))
        self.assertNotIn("..", os.path.basename(path_trav))

    def test_get_vouchers_by_ids(self):
        # Empty input should return empty list without error
        self.assertEqual(db.get_vouchers_by_ids([]), [])

        # Create multiple vouchers
        v1 = db.create_voucher(
            {"date": "2026-09-20", "paid_to": "Alpha", "cash_given_by": "Cashier", "spent_by": "Alpha", "bill_status": "Pending"},
            [{"description": "Item 1", "category": "General", "amount": 500.0}],
            company_id=1
        )
        v2 = db.create_voucher(
            {"date": "2026-09-21", "paid_to": "Beta", "cash_given_by": "Cashier", "spent_by": "Beta", "bill_status": "Pending"},
            [{"description": "Item 2", "category": "General", "amount": 1000.0}],
            company_id=1
        )
        v3 = db.create_voucher(
            {"date": "2026-09-22", "paid_to": "Gamma", "cash_given_by": "Cashier", "spent_by": "Gamma", "bill_status": "Cancelled"},
            [{"description": "Item 3", "category": "General", "amount": 1500.0}],
            company_id=1
        )

        # Batch lookup preserving order and handling missing IDs
        results = db.get_vouchers_by_ids([v3, 99999, v1, v2, v1])
        self.assertEqual(len(results), 3)
        self.assertEqual([r["id"] for r in results], [v3, v1, v2])
        self.assertEqual(results[0]["paid_to"], "Gamma")
        self.assertEqual(results[1]["paid_to"], "Alpha")
        self.assertEqual(results[2]["paid_to"], "Beta")

    def test_money_float_tracking_and_balance_lifecycle(self):
        # 1. Create a float with opening balance
        float_id = db.create_float(
            company_id=1,
            name="Petty Cash Drawer A",
            opening_balance=25000.0,
            opening_date="2026-09-01",
            custodian="Jane Doe",
            notes="Primary office petty cash",
            is_default=False
        )
        self.assertIsNotNone(float_id)

        flt = db.get_float(float_id)
        self.assertEqual(flt["name"], "Petty Cash Drawer A")
        self.assertEqual(flt["opening_balance"], 25000.0)
        self.assertEqual(flt["current_balance"], 25000.0)

        # 2. Add Inflow / Top-Up transaction (e.g. Bank withdrawal)
        t1 = db.add_float_transaction(
            float_id=float_id,
            amount=15000.0,
            date="2026-09-05",
            trans_type="Inflow",
            source_ref="Cheque #99104",
            handed_by="Bank Cashier",
            received_by="Jane Doe",
            notes="Replenishment"
        )
        self.assertIsNotNone(t1)

        flt_after_topup = db.get_float(float_id)
        self.assertEqual(flt_after_topup["total_inflows"], 15000.0)
        self.assertEqual(flt_after_topup["current_balance"], 40000.0)

        # 3. Create active voucher spent from this float
        v_data = {
            "date": "2026-09-08",
            "paid_to": "Office Supplies Co",
            "cash_given_by": "Jane Doe",
            "spent_by": "Jane Doe",
            "payment_method": "Cash",
            "float_id": float_id,
            "bill_status": "Received"
        }
        v_id = db.create_voucher(
            v_data,
            [{"description": "Printer Paper", "category": "Stationery", "amount": 6500.0}],
            company_id=1
        )

        flt_after_voucher = db.get_float(float_id)
        self.assertEqual(flt_after_voucher["voucher_count"], 1)
        self.assertEqual(flt_after_voucher["voucher_outflows"], 6500.0)
        self.assertEqual(flt_after_voucher["current_balance"], 33500.0)

        # 4. Cancelling a voucher must immediately restore float balance
        db.cancel_voucher(v_id)
        flt_cancelled = db.get_float(float_id)
        self.assertEqual(flt_cancelled["voucher_count"], 0)
        self.assertEqual(flt_cancelled["voucher_outflows"], 0.0)
        self.assertEqual(flt_cancelled["current_balance"], 40000.0)

        # 5. Restoring a voucher must re-apply the outflow
        db.restore_voucher(v_id)
        flt_restored = db.get_float(float_id)
        self.assertEqual(flt_restored["voucher_count"], 1)
        self.assertEqual(flt_restored["voucher_outflows"], 6500.0)
        self.assertEqual(flt_restored["current_balance"], 33500.0)

        # 6. Manual cash adjustment outflow
        t2 = db.add_float_transaction(
            float_id=float_id,
            amount=3500.0,
            date="2026-09-10",
            trans_type="Outflow",
            source_ref="Bank Deposit",
            handed_by="Jane Doe",
            received_by="Bank Deposit",
            notes="Deposited excess back to bank"
        )
        flt_adj = db.get_float(float_id)
        self.assertEqual(flt_adj["manual_outflows"], 3500.0)
        self.assertEqual(flt_adj["current_balance"], 30000.0)

        # 7. Delete manual transaction
        db.delete_float_transaction(t2)
        flt_del_adj = db.get_float(float_id)
        self.assertEqual(flt_del_adj["manual_outflows"], 0.0)
        self.assertEqual(flt_del_adj["current_balance"], 33500.0)

    def test_float_ledger_running_balance(self):
        float_id = db.create_float(
            company_id=1,
            name="Ledger Test Float",
            opening_balance=10000.0,
            opening_date="2026-09-01"
        )
        # Top-up: +5000 -> 15000
        db.add_float_transaction(float_id=float_id, amount=5000.0, date="2026-09-02", trans_type="Inflow")
        # Voucher: -2000 -> 13000
        db.create_voucher(
            {"date": "2026-09-03", "paid_to": "Vendor A", "cash_given_by": "Cashier", "payment_method": "Cash", "float_id": float_id},
            [{"description": "Item A", "amount": 2000.0}],
            company_id=1
        )
        # Voucher: -3000 -> 10000
        db.create_voucher(
            {"date": "2026-09-04", "paid_to": "Vendor B", "cash_given_by": "Cashier", "payment_method": "Cash", "float_id": float_id},
            [{"description": "Item B", "amount": 3000.0}],
            company_id=1
        )

        entries, stats = db.get_float_ledger(float_id)
        self.assertEqual(len(entries), 4)
        self.assertEqual(stats["current_balance"], 10000.0)

        # Check running balances row-by-row
        self.assertEqual(entries[0]["running_balance"], 10000.0)  # Opening
        self.assertEqual(entries[1]["running_balance"], 15000.0)  # Inflow 5000
        self.assertEqual(entries[2]["running_balance"], 13000.0)  # Outflow 2000
        self.assertEqual(entries[3]["running_balance"], 10000.0)  # Outflow 3000

    def test_export_float_ledger_to_csv(self):
        float_id = db.create_float(
            company_id=1,
            name="Export Float Test",
            opening_balance=5000.0,
            opening_date="2026-09-01",
            custodian="Alex"
        )
        db.add_float_transaction(float_id=float_id, amount=2000.0, date="2026-09-02", trans_type="Inflow", source_ref="TopUp #1")

        csv_path = os.path.join(self.test_dir, "test_float_ledger.csv")
        db.export_float_ledger_to_csv(float_id, csv_path)

        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("MONEY FLOAT RUNNING BALANCE LEDGER", content)
            self.assertIn("Export Float Test", content)
            self.assertIn("Alex", content)
            self.assertIn("Running Balance (LKR)", content)
            self.assertIn("7000.00", content)

    def test_search_vouchers_float_filter(self):
        f1 = db.create_float(company_id=1, name="Float One", opening_balance=5000.0)
        f2 = db.create_float(company_id=1, name="Float Two", opening_balance=5000.0)

        v1 = db.create_voucher(
            {"date": "2026-09-10", "paid_to": "Vendor One", "cash_given_by": "Cashier", "payment_method": "Cash", "float_id": f1},
            [{"description": "Item 1", "amount": 100.0}],
            company_id=1
        )
        v2 = db.create_voucher(
            {"date": "2026-09-10", "paid_to": "Vendor Two", "cash_given_by": "Cashier", "payment_method": "Cash", "float_id": f2},
            [{"description": "Item 2", "amount": 200.0}],
            company_id=1
        )

        res_f1 = db.search_vouchers(float_id_filter=f1, company_id=1)
        res_f2 = db.search_vouchers(float_id_filter=f2, company_id=1)

        f1_ids = [r["id"] for r in res_f1]
        f2_ids = [r["id"] for r in res_f2]

        self.assertIn(v1, f1_ids)
        self.assertNotIn(v2, f1_ids)
        self.assertIn(v2, f2_ids)
        self.assertNotIn(v1, f2_ids)


if __name__ == "__main__":
    unittest.main()


