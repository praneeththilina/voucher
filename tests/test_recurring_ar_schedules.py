import os
import tempfile
import unittest
from datetime import date, datetime, timedelta

import database as db
import sales_database as sdb


class TestRecurringARSchedules(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        db.DB_PATH = self.db_path
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = db.get_active_company_id(self.conn)

        # Create test customer
        self.customer_id = db.create_customer({
            "company_id": self.company_id,
            "name": "Acme Corp",
            "email": "billing@acme.com",
            "currency": "LKR",
        }, conn=self.conn)

        # Create test sales item
        self.item_id = sdb.save_sales_item({
            "company_id": self.company_id,
            "name": "Consulting Service",
            "item_type": "Service",
            "sales_price": 1500.0,
        }, conn=self.conn)

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_recurring_ar_schedule_validation(self):
        # Blank schedule name should raise ValueError
        with self.assertRaises(ValueError):
            sdb.create_recurring_ar_schedule(
                {"company_id": self.company_id, "schedule_name": "  ", "customer_id": self.customer_id},
                [{"item_id": self.item_id, "description": "Line", "quantity": 1, "unit_price": 100}],
                conn=self.conn,
            )

        # Missing customer should raise ValueError
        with self.assertRaises(ValueError):
            sdb.create_recurring_ar_schedule(
                {"company_id": self.company_id, "schedule_name": "Monthly Retainer", "customer_id": None},
                [{"item_id": self.item_id, "description": "Line", "quantity": 1, "unit_price": 100}],
                conn=self.conn,
            )

        # Empty items should raise ValueError
        with self.assertRaises(ValueError):
            sdb.create_recurring_ar_schedule(
                {"company_id": self.company_id, "schedule_name": "Monthly Retainer", "customer_id": self.customer_id},
                [],
                conn=self.conn,
            )

    def test_create_and_get_recurring_ar_schedule(self):
        sched_id = sdb.create_recurring_ar_schedule(
            {
                "company_id": self.company_id,
                "schedule_name": "Monthly Consulting",
                "customer_id": self.customer_id,
                "frequency": "monthly",
                "next_run_date": "2026-01-01",
                "terms_days": 15,
                "auto_post": 0,
                "notes": "Test recurring note",
            },
            [
                {"item_id": self.item_id, "description": "Monthly Consulting Fee", "quantity": 2, "unit_price": 1500.0}
            ],
            conn=self.conn,
        )

        self.assertIsNotNone(sched_id)

        sched = sdb.get_recurring_ar_schedule(sched_id, conn=self.conn)
        self.assertIsNotNone(sched)
        self.assertEqual(sched["schedule_name"], "Monthly Consulting")
        self.assertEqual(sched["customer_name"], "Acme Corp")
        self.assertEqual(sched["frequency"], "monthly")
        self.assertEqual(sched["total_amount"], 3000.0)
        self.assertEqual(len(sched["items"]), 1)

    def test_update_and_delete_recurring_ar_schedule(self):
        sched_id = sdb.create_recurring_ar_schedule(
            {
                "company_id": self.company_id,
                "schedule_name": "Weekly Service",
                "customer_id": self.customer_id,
                "frequency": "weekly",
                "next_run_date": "2026-02-01",
            },
            [{"description": "Weekly task", "quantity": 1, "unit_price": 500.0}],
            conn=self.conn,
        )

        updated = sdb.update_recurring_ar_schedule(
            sched_id,
            {
                "schedule_name": "Weekly Premium Service",
                "customer_id": self.customer_id,
                "frequency": "weekly",
                "status": "paused",
            },
            [{"description": "Weekly premium task", "quantity": 1, "unit_price": 800.0}],
            conn=self.conn,
        )
        self.assertTrue(updated)

        sched = sdb.get_recurring_ar_schedule(sched_id, conn=self.conn)
        self.assertEqual(sched["schedule_name"], "Weekly Premium Service")
        self.assertEqual(sched["status"], "paused")
        self.assertEqual(sched["total_amount"], 800.0)

        # Delete schedule
        deleted = sdb.delete_recurring_ar_schedule(sched_id, conn=self.conn)
        self.assertTrue(deleted)
        self.assertIsNone(sdb.get_recurring_ar_schedule(sched_id, conn=self.conn))

    def test_process_due_recurring_ar_schedules(self):
        today_str = date.today().strftime("%Y-%m-%d")

        # Create active schedule due today
        sched_id = sdb.create_recurring_ar_schedule(
            {
                "company_id": self.company_id,
                "schedule_name": "Due Today Draft",
                "customer_id": self.customer_id,
                "frequency": "monthly",
                "next_run_date": today_str,
                "auto_post": 0,
            },
            [{"item_id": self.item_id, "description": "Consulting", "quantity": 1, "unit_price": 1000.0}],
            conn=self.conn,
        )

        # Create active schedule with auto_post=1 due today
        sched_id_post = sdb.create_recurring_ar_schedule(
            {
                "company_id": self.company_id,
                "schedule_name": "Due Today Posted",
                "customer_id": self.customer_id,
                "frequency": "weekly",
                "next_run_date": today_str,
                "auto_post": 1,
            },
            [{"item_id": self.item_id, "description": "Consulting Auto", "quantity": 2, "unit_price": 500.0}],
            conn=self.conn,
        )

        res = sdb.process_due_recurring_ar_schedules(as_of_date=today_str, company_id=self.company_id, conn=self.conn)
        self.assertEqual(len(res), 2)

        # Check statuses
        statuses = {r["schedule_name"]: r["status"] for r in res}
        self.assertEqual(statuses["Due Today Draft"], "Draft")
        self.assertEqual(statuses["Due Today Posted"], "Unpaid")

        # Verify schedule's last_run_date and next_run_date were updated
        sched1 = sdb.get_recurring_ar_schedule(sched_id, conn=self.conn)
        self.assertEqual(sched1["last_run_date"], today_str)
        self.assertGreater(sched1["next_run_date"], today_str)

    def test_export_recurring_ar_schedules_to_csv(self):
        sched_id = sdb.create_recurring_ar_schedule(
            {
                "company_id": self.company_id,
                "schedule_name": "=SUM(1+1) Dangerous Name",
                "customer_id": self.customer_id,
                "frequency": "monthly",
                "next_run_date": "2026-03-01",
                "notes": "@Formula Injection Test",
            },
            [{"description": "Sample Item", "quantity": 1, "unit_price": 250.0}],
            conn=self.conn,
        )

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            csv_path = tmp.name

        try:
            out_path = sdb.export_recurring_ar_schedules_to_csv(csv_path, company_id=self.company_id)
            self.assertTrue(os.path.exists(out_path))

            with open(out_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            # Confirm formula injection sanitization occurred (' standard prefix)
            self.assertIn("'=SUM(1+1) Dangerous Name", content)
            self.assertIn("'@Formula Injection Test", content)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
