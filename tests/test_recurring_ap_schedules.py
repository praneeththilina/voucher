"""
tests/test_recurring_ap_schedules.py
Unit and UI tests for Recurring Accounts Payable (AP) Schedules.
"""

import os
import csv
import tempfile
import unittest
from datetime import datetime, timedelta

import database as db
from ui.ap_invoice_dialog import RecurringAPScheduleModal, RecurringAPManagerDialog
from tests.test_widgets import get_test_root


class TestRecurringAPDatabase(unittest.TestCase):
    """Database CRUD, processing engine, and export tests for Recurring AP Schedules."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vouchers.db")
        db.configure_database(self.db_path)
        db.init_db()

        self.company_id = db.get_active_company_id()
        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Acme Office Supplies",
            "contact_person": "Jane Doe",
            "payment_terms": 30
        })

        self.coa_accounts = db.get_chart_of_accounts(company_id=self.company_id, account_type="Expense")
        self.expense_account_id = self.coa_accounts[0]["id"] if self.coa_accounts else None

    def tearDown(self):
        db.invalidate_all_caches()

    def test_crud_recurring_ap_schedule(self):
        """Test creating, reading, updating, and deleting a recurring AP schedule."""
        today = datetime.now().strftime("%Y-%m-%d")

        sched_id = db.create_recurring_ap_schedule({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "schedule_name": "Monthly Office Stationery",
            "frequency": "monthly",
            "start_date": today,
            "payment_terms": 30,
            "amount": 15000.0,
            "expense_account_id": self.expense_account_id,
            "tax_rate": 18.0,
            "description": "Monthly paper and toner supplies",
            "auto_post": 1
        }, company_id=self.company_id)

        self.assertIsNotNone(sched_id)

        # Retrieve single schedule
        sched = db.get_recurring_ap_schedule(sched_id)
        self.assertIsNotNone(sched)
        self.assertEqual(sched["schedule_name"], "Monthly Office Stationery")
        self.assertEqual(sched["supplier_name"], "Acme Office Supplies")
        self.assertEqual(float(sched["amount"]), 15000.0)

        # Retrieve schedule list
        schedules = db.get_recurring_ap_schedules(company_id=self.company_id, active_only=True)
        self.assertTrue(any(s["id"] == sched_id for s in schedules))

        # Update schedule
        success = db.update_recurring_ap_schedule(sched_id, {
            "schedule_name": "Updated Office Stationery",
            "amount": 17500.0
        })
        self.assertTrue(success)

        updated_sched = db.get_recurring_ap_schedule(sched_id)
        self.assertEqual(updated_sched["schedule_name"], "Updated Office Stationery")
        self.assertEqual(float(updated_sched["amount"]), 17500.0)

        # Delete schedule
        del_success = db.delete_recurring_ap_schedule(sched_id)
        self.assertTrue(del_success)
        self.assertIsNone(db.get_recurring_ap_schedule(sched_id))

    def test_validation_rules(self):
        """Test schedule creation validation rules."""
        with self.assertRaises(ValueError):
            db.create_recurring_ap_schedule({
                "supplier_id": self.supplier_id,
                "schedule_name": "   "
            }, company_id=self.company_id)

        with self.assertRaises(ValueError):
            db.create_recurring_ap_schedule({
                "supplier_id": None,
                "schedule_name": "Valid Name"
            }, company_id=self.company_id)

    def test_process_due_recurring_ap_schedules(self):
        """Test processing due schedules and automated supplier bill creation."""
        today_str = datetime.now().strftime("%Y-%m-%d")

        sched_id = db.create_recurring_ap_schedule({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "schedule_name": "Internet Service Retainer",
            "frequency": "monthly",
            "start_date": today_str,
            "next_run": today_str,
            "payment_terms": 15,
            "amount": 25000.0,
            "expense_account_id": self.expense_account_id,
            "tax_rate": 0.0,
            "description": "Monthly fiber connectivity",
            "is_active": 1
        }, company_id=self.company_id)

        processed = db.process_due_recurring_ap_schedules(company_id=self.company_id)
        self.assertEqual(len(processed), 1)

        item = processed[0]
        self.assertEqual(item["schedule_id"], sched_id)
        self.assertEqual(item["schedule_name"], "Internet Service Retainer")

        # Verify created AP bill
        inv_data = db.get_ap_invoice(item["invoice_id"])
        self.assertIsNotNone(inv_data)
        h = inv_data["invoice"]
        lines = inv_data["lines"]

        self.assertEqual(h["supplier_id"], self.supplier_id)
        self.assertEqual(float(h["total_amount"]), 25000.0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["description"], "Monthly fiber connectivity")

        # Verify schedule state updated
        updated_sched = db.get_recurring_ap_schedule(sched_id)
        self.assertEqual(updated_sched["total_runs"], 1)
        self.assertEqual(updated_sched["last_run"], today_str)

        # Next run should be 1 month after today_str
        dt_today = datetime.strptime(today_str, "%Y-%m-%d")
        next_dt = datetime.strptime(updated_sched["next_run"], "%Y-%m-%d")
        self.assertGreater(next_dt, dt_today)

    def test_max_runs_and_end_date_deactivation(self):
        """Test schedule auto-deactivation on max runs or end date limit."""
        today_str = datetime.now().strftime("%Y-%m-%d")

        sched_id = db.create_recurring_ap_schedule({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "schedule_name": "Limited Campaign",
            "frequency": "daily",
            "start_date": today_str,
            "next_run": today_str,
            "amount": 5000.0,
            "max_runs": 1,
            "is_active": 1
        }, company_id=self.company_id)

        processed = db.process_due_recurring_ap_schedules(company_id=self.company_id)
        self.assertEqual(len(processed), 1)

        sched = db.get_recurring_ap_schedule(sched_id)
        self.assertEqual(sched["is_active"], 0)
        self.assertEqual(sched["total_runs"], 1)

    def test_export_recurring_ap_schedules_to_csv(self):
        """Test exporting recurring AP schedules to CSV with formula injection protection."""
        db.create_recurring_ap_schedule({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "schedule_name": "=SUM(1+1) Dangerous Name",
            "frequency": "monthly",
            "amount": 10000.0
        }, company_id=self.company_id)

        csv_path = os.path.join(self.test_dir, "recurring_ap_export.csv")
        out_path = db.export_recurring_ap_schedules_to_csv(csv_path, company_id=self.company_id)
        self.assertTrue(os.path.exists(out_path))

        with open(out_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)

        self.assertTrue(len(rows) >= 5)
        self.assertIn("RECURRING ACCOUNTS PAYABLE (AP) SCHEDULES REPORT", rows[0][0])

        # Check sanitized formula row
        formula_row = next((r for r in rows if r and "Dangerous Name" in r[0]), None)
        self.assertIsNotNone(formula_row)
        self.assertTrue(formula_row[0].startswith("'="))


class TestRecurringAPUI(unittest.TestCase):
    """UI tests for Recurring AP Schedule Modal and Manager Dialog."""

    def setUp(self):
        self.root = get_test_root()
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ui_vouchers.db")
        db.configure_database(self.db_path)
        db.init_db()

        self.company_id = db.get_active_company_id()
        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Global Cloud Services",
            "contact_person": "Alex Smith"
        })

    def tearDown(self):
        db.invalidate_all_caches()

    def test_recurring_ap_schedule_modal(self):
        """Test RecurringAPScheduleModal rendering and field interaction."""
        saved_calls = []

        def on_saved():
            saved_calls.append(True)

        dlg = RecurringAPScheduleModal(self.root, company_id=self.company_id, on_saved=on_saved)
        self.root.update_idletasks()

        dlg.name_var.set("Monthly Server Hosting")
        dlg.amount_var.set("45000.00")
        dlg._save_schedule()

        self.assertEqual(len(saved_calls), 1)
        schedules = db.get_recurring_ap_schedules(company_id=self.company_id)
        self.assertTrue(any(s["schedule_name"] == "Monthly Server Hosting" for s in schedules))

    def test_recurring_ap_manager_dialog(self):
        """Test RecurringAPManagerDialog tree population and action buttons."""
        db.create_recurring_ap_schedule({
            "company_id": self.company_id,
            "supplier_id": self.supplier_id,
            "schedule_name": "SaaS Subscription",
            "frequency": "monthly",
            "amount": 12000.0
        }, company_id=self.company_id)

        mgr = RecurringAPManagerDialog(self.root, company_id=self.company_id)
        self.root.update_idletasks()

        children = mgr.tree.get_children()
        self.assertEqual(len(children), 1)

        # First row auto-selection
        self.assertEqual(mgr.tree.selection()[0], children[0])
        self.assertEqual(str(mgr.btn_edit["state"]), "normal")
        self.assertEqual(str(mgr.btn_pause["state"]), "normal")
        self.assertEqual(str(mgr.btn_delete["state"]), "normal")

        # Test toggle active
        mgr._toggle_active()
        schedules = db.get_recurring_ap_schedules(company_id=self.company_id, active_only=False)
        self.assertEqual(schedules[0]["is_active"], 0)

        mgr.destroy()


if __name__ == "__main__":
    unittest.main()
