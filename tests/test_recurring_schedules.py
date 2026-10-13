"""
Unit tests for recurring payment schedules in database.py and ui/recurring_manager.py
"""

import unittest
import os
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

import database as db
from ui.recurring_manager import RecurringManagerDialog
from tests.test_widgets import get_test_root


class TestRecurringSchedulesBackend(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        db.configure_database(self.temp_db.name)
        db.init_db()
        self.company_id = db.get_active_company_id()

    def tearDown(self):
        db.invalidate_all_caches()
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    def test_create_and_get_recurring_schedule(self):
        data = {
            "schedule_name": "Monthly Office Rent",
            "paid_to": "Landlord Corp",
            "amount": 45000.0,
            "frequency": "monthly",
            "category": "Rent Expense",
            "payment_method": "Bank Transfer",
            "mode": "auto_create"
        }
        sid = db.create_recurring_schedule(data, company_id=self.company_id)
        self.assertIsNotNone(sid)

        sched = db.get_recurring_schedule(sid)
        self.assertIsNotNone(sched)
        self.assertEqual(sched["schedule_name"], "Monthly Office Rent")
        self.assertEqual(sched["paid_to"], "Landlord Corp")
        self.assertEqual(float(sched["amount"]), 45000.0)
        self.assertEqual(sched["frequency"], "monthly")

    def test_create_schedule_validation(self):
        # Empty or whitespace name should raise ValueError
        with self.assertRaises(ValueError):
            db.create_recurring_schedule({"schedule_name": ""}, company_id=self.company_id)

        with self.assertRaises(ValueError):
            db.create_recurring_schedule({"schedule_name": "   \t \n"}, company_id=self.company_id)

        # Valid name with surrounding whitespace should be stripped
        sid = db.create_recurring_schedule({"schedule_name": "  Utilities Bill  "}, company_id=self.company_id)
        sched = db.get_recurring_schedule(sid)
        self.assertEqual(sched["schedule_name"], "Utilities Bill")

    def test_update_recurring_schedule(self):
        sid = db.create_recurring_schedule({
            "schedule_name": "Internet Subscription",
            "amount": 3500.0
        }, company_id=self.company_id)

        # Update fields
        ok = db.update_recurring_schedule(sid, {
            "schedule_name": "Fiber Internet 100Mbps",
            "amount": 4200.0,
            "is_active": 0
        })
        self.assertTrue(ok)

        sched = db.get_recurring_schedule(sid)
        self.assertEqual(sched["schedule_name"], "Fiber Internet 100Mbps")
        self.assertEqual(float(sched["amount"]), 4200.0)
        self.assertEqual(sched["is_active"], 0)

        # Updating name to empty should raise ValueError
        with self.assertRaises(ValueError):
            db.update_recurring_schedule(sid, {"schedule_name": "  "})

    def test_delete_recurring_schedule(self):
        sid = db.create_recurring_schedule({
            "schedule_name": "Temporary Schedule",
            "amount": 1000.0
        }, company_id=self.company_id)

        self.assertIsNotNone(db.get_recurring_schedule(sid))
        ok = db.delete_recurring_schedule(sid)
        self.assertTrue(ok)
        self.assertIsNone(db.get_recurring_schedule(sid))

    def test_get_recurring_schedules_active_only(self):
        sid1 = db.create_recurring_schedule({"schedule_name": "Schedule 1", "amount": 100}, company_id=self.company_id)
        sid2 = db.create_recurring_schedule({"schedule_name": "Schedule 2", "amount": 200}, company_id=self.company_id)
        db.update_recurring_schedule(sid2, {"is_active": 0})

        all_schedules = db.get_recurring_schedules(self.company_id, active_only=False)
        self.assertEqual(len(all_schedules), 2)

        active_schedules = db.get_recurring_schedules(self.company_id, active_only=True)
        self.assertEqual(len(active_schedules), 1)
        self.assertEqual(active_schedules[0]["id"], sid1)

    def test_export_recurring_schedules_to_csv(self):
        sid1 = db.create_recurring_schedule({
            "schedule_name": "=SUM(1+2) Software",
            "paid_to": "SaaS Co",
            "amount": 1500.0,
            "category": "Software Licenses",
            "frequency": "monthly"
        }, company_id=self.company_id)

        tmp_csv = tempfile.mktemp(suffix=".csv")
        try:
            res = db.export_recurring_schedules_to_csv(tmp_csv, company_id=self.company_id)
            self.assertTrue(res)
            self.assertTrue(os.path.exists(tmp_csv))

            with open(tmp_csv, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("Recurring Payment Schedules Report", content)
            self.assertIn("Schedule Name", content)
            self.assertIn("Software Licenses", content)
            # Verify formula injection sanitization
            self.assertIn("'=SUM(1+2) Software", content)
        finally:
            if os.path.exists(tmp_csv):
                os.remove(tmp_csv)

    def test_connection_reuse(self):
        conn = db.get_connection()
        try:
            sid = db.create_recurring_schedule({
                "schedule_name": "Schedule with conn",
                "amount": 500.0
            }, company_id=self.company_id, conn=conn)
            self.assertIsNotNone(sid)

            sched = db.get_recurring_schedule(sid, conn=conn)
            self.assertEqual(sched["schedule_name"], "Schedule with conn")

            db.update_recurring_schedule(sid, {"amount": 750.0}, conn=conn)
            sched = db.get_recurring_schedule(sid, conn=conn)
            self.assertEqual(float(sched["amount"]), 750.0)

            db.delete_recurring_schedule(sid, conn=conn)
            self.assertIsNone(db.get_recurring_schedule(sid, conn=conn))
        finally:
            conn.close()


class TestRecurringManagerDialogUI(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        db.configure_database(self.temp_db.name)
        db.init_db()
        self.company_id = db.get_active_company_id()
        self.root = get_test_root()

    def tearDown(self):
        db.invalidate_all_caches()
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    def test_dialog_auto_selection(self):
        sid1 = db.create_recurring_schedule({"schedule_name": "Office Rent", "amount": 50000}, company_id=self.company_id)
        sid2 = db.create_recurring_schedule({"schedule_name": "Insurance", "amount": 12000}, company_id=self.company_id)

        dlg = RecurringManagerDialog(self.root)
        try:
            sel = dlg._tree.selection()
            self.assertEqual(len(sel), 1)
            self.assertEqual(sel[0], str(sid1))
        finally:
            dlg.destroy()

    def test_dialog_csv_export_action(self):
        sid = db.create_recurring_schedule({"schedule_name": "Cloud Backup", "amount": 2000}, company_id=self.company_id)
        dlg = RecurringManagerDialog(self.root)

        tmp_csv = tempfile.mktemp(suffix=".csv")
        try:
            with patch("tkinter.filedialog.asksaveasfilename", return_value=tmp_csv), \
                 patch("tkinter.messagebox.showinfo") as mock_info:
                dlg._export_csv()
                self.assertTrue(os.path.exists(tmp_csv))
                mock_info.assert_called_once()
        finally:
            if os.path.exists(tmp_csv):
                os.remove(tmp_csv)
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
