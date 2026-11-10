"""
Tests for Recurring Voucher Schedules: validation, CRUD, CSV export, and UI interactions.
"""

import os
import unittest
import tempfile
import csv
from unittest.mock import patch, MagicMock
from datetime import datetime, date

import database as db
from tests.test_widgets import get_test_root


class TestRecurringSchedules(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_vouchers.db")
        db.configure_database(self.db_path)
        db.init_db()
        self.company_id = 1

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_create_recurring_schedule_validation(self):
        """Verify create_recurring_schedule validates schedule_name and trims whitespace."""
        # Missing or empty name should raise ValueError
        with self.assertRaises(ValueError):
            db.create_recurring_schedule({"schedule_name": ""}, company_id=self.company_id)

        with self.assertRaises(ValueError):
            db.create_recurring_schedule({"schedule_name": "   "}, company_id=self.company_id)

        with self.assertRaises(ValueError):
            db.create_recurring_schedule({}, company_id=self.company_id)

        # Valid name with whitespace should be trimmed
        sid = db.create_recurring_schedule({
            "schedule_name": "  Monthly Office Rent  ",
            "paid_to": "Landlord Corp",
            "amount": 75000.0,
            "category": "Rent Expense",
            "frequency": "monthly",
            "day_of_month": 1,
            "mode": "auto_create",
            "start_date": "2026-01-01",
            "next_run": "2026-02-01",
        }, company_id=self.company_id)

        self.assertIsNotNone(sid)
        sched = db.get_recurring_schedule(sid)
        self.assertEqual(sched["schedule_name"], "Monthly Office Rent")
        self.assertEqual(sched["paid_to"], "Landlord Corp")
        self.assertEqual(float(sched["amount"]), 75000.0)

    def test_update_recurring_schedule_validation_and_crud(self):
        """Verify update_recurring_schedule updates fields and validates names."""
        sid = db.create_recurring_schedule({
            "schedule_name": "Internet Subscription",
            "paid_to": "ISP Ltd",
            "amount": 5000.0,
            "frequency": "monthly",
        }, company_id=self.company_id)

        # Update with empty schedule name should raise ValueError
        with self.assertRaises(ValueError):
            db.update_recurring_schedule(sid, {"schedule_name": "  "})

        # Valid update
        ok = db.update_recurring_schedule(sid, {
            "schedule_name": " Fiber Internet ",
            "amount": 5500.0,
            "is_active": 0,
        })
        self.assertTrue(ok)

        sched = db.get_recurring_schedule(sid)
        self.assertEqual(sched["schedule_name"], "Fiber Internet")
        self.assertEqual(float(sched["amount"]), 5500.0)
        self.assertEqual(sched["is_active"], 0)

        # Delete schedule
        del_ok = db.delete_recurring_schedule(sid)
        self.assertTrue(del_ok)
        self.assertIsNone(db.get_recurring_schedule(sid))

    def test_export_recurring_schedules_to_csv(self):
        """Verify export_recurring_schedules_to_csv generates report with UTF-8 BOM, metadata, and sanitized fields."""
        # Create schedules including one with potential formula injection
        db.create_recurring_schedule({
            "schedule_name": "=CMD|' /C calc'!A0",
            "paid_to": "+94771234567",
            "amount": 12000.0,
            "category": "Software",
            "frequency": "monthly",
            "day_of_month": 15,
            "mode": "auto_create",
            "start_date": "2026-01-15",
            "next_run": "2026-02-15",
        }, company_id=self.company_id)

        db.create_recurring_schedule({
            "schedule_name": "Cloud Hosting Server",
            "paid_to": "Cloud Services Inc",
            "amount": 25000.0,
            "category": "Hosting",
            "frequency": "monthly",
            "day_of_month": 5,
            "mode": "auto_create",
            "start_date": "2026-01-05",
            "next_run": "2026-02-05",
        }, company_id=self.company_id)

        csv_path = os.path.join(self.temp_dir.name, "recurring_export.csv")
        out_path = db.export_recurring_schedules_to_csv(csv_path, company_id=self.company_id)
        self.assertEqual(out_path, csv_path)
        self.assertTrue(os.path.exists(csv_path))

        # Check BOM
        with open(csv_path, "rb") as f:
            raw_bytes = f.read(3)
            self.assertEqual(raw_bytes, b"\xef\xbb\xbf")

        # Read CSV rows
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertGreater(len(rows), 6)
        self.assertEqual(rows[0][0], "RECURRING PAYMENT SCHEDULES REPORT")
        self.assertTrue(rows[1][0].startswith("Company:"))
        self.assertTrue(rows[2][0].startswith("Base Currency:"))
        self.assertTrue(rows[3][0].startswith("Generated At:"))
        self.assertEqual(rows[4][0], "Total Schedules: 2")

        header_row = rows[6]
        self.assertIn("Schedule Name", header_row)
        self.assertIn("Payee", header_row)
        self.assertIn("Mode", header_row)
        self.assertIn("Frequency", header_row)

        data_rows = rows[7:]
        self.assertEqual(len(data_rows), 2)

        # Check formula injection prefix `'`
        found_sanitized = False
        for r in data_rows:
            if r[0].startswith("'=CMD"):
                found_sanitized = True
                self.assertTrue(r[1].startswith("'+9477"))
        self.assertTrue(found_sanitized)

    def test_recurring_manager_dialog_ui(self):
        """Verify RecurringManagerDialog UI initialization, auto-selection, button states, and CSV export action."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Create sample schedules
        sid1 = db.create_recurring_schedule({
            "schedule_name": "Office Electricity",
            "paid_to": "Electricity Board",
            "amount": 18500.0,
            "frequency": "monthly",
            "start_date": "2026-01-01",
        }, company_id=self.company_id)

        sid2 = db.create_recurring_schedule({
            "schedule_name": "Water Bill",
            "paid_to": "Water Supply Board",
            "amount": 3200.0,
            "frequency": "monthly",
            "start_date": "2026-01-01",
        }, company_id=self.company_id)

        from ui.recurring_manager import RecurringManagerDialog
        dlg = RecurringManagerDialog(root)
        root.update()

        # Check treeview children
        children = dlg._tree.get_children()
        self.assertEqual(len(children), 2)

        # Verify auto-selection of first row
        selected = dlg._tree.selection()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0], str(children[0]))

        # Verify button states enabled when row selected
        self.assertEqual(str(dlg._edit_btn["state"]), "normal")
        self.assertEqual(str(dlg._toggle_btn["state"]), "normal")
        self.assertEqual(str(dlg._del_btn["state"]), "normal")

        # Clear selection and verify buttons disable
        dlg._tree.selection_remove(selected[0])
        dlg._on_tree_select()
        self.assertEqual(str(dlg._edit_btn["state"]), "disabled")
        self.assertEqual(str(dlg._toggle_btn["state"]), "disabled")
        self.assertEqual(str(dlg._del_btn["state"]), "disabled")

        # Select row again
        dlg._tree.selection_set(children[1])
        dlg._on_tree_select()
        self.assertEqual(str(dlg._edit_btn["state"]), "normal")

        # Test CSV export triggered via UI
        csv_target = os.path.join(self.temp_dir.name, "ui_recurring_export.csv")
        with patch("tkinter.filedialog.asksaveasfilename", return_value=csv_target), \
             patch("tkinter.messagebox.showinfo") as mock_info:
            dlg._export_csv()
            self.assertTrue(os.path.exists(csv_target))
            mock_info.assert_called_once()

        dlg.destroy()


if __name__ == "__main__":
    unittest.main()
