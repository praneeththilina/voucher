"""Regression tests for business performance analytics."""

from datetime import datetime, timedelta
import os
import shutil
import tempfile
import unittest

import database as db
from ui.analytics_dashboard import AnalyticsDashboard


class TestAnalyticsData(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "analytics.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.invalidate_all_caches()
        db.init_db()

        now = datetime.now()
        previous = now.replace(day=1) - timedelta(days=1)
        current_date = now.strftime("%Y-%m-%d")
        previous_date = previous.strftime("%Y-%m-%d")
        overdue_date = (now - timedelta(days=5)).strftime("%Y-%m-%d")

        db.create_voucher(
            {
                "date": current_date,
                "due_date": overdue_date,
                "paid_to": "Current Vendor",
                "cash_given_by": "Cashier",
                "payment_method": "Cash",
                "bill_status": "Pending",
            },
            [
                {
                    "description": "Current supplies",
                    "category": "Office Supplies",
                    "amount": 1200.0,
                }
            ],
            company_id=1,
        )
        db.create_voucher(
            {
                "date": previous_date,
                "paid_to": "Previous Vendor",
                "cash_given_by": "Cashier",
                "payment_method": "Cheque",
                "bill_status": "Received",
            },
            [
                {
                    "description": "Previous travel",
                    "category": "Travel",
                    "amount": 800.0,
                }
            ],
            company_id=1,
        )

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        db.invalidate_all_caches()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_dashboard_kpis_are_period_aware(self):
        current = db.get_dashboard_kpis(1, "This Month")
        previous = db.get_dashboard_kpis(1, "Last Month")

        self.assertEqual(current["voucher_count"], 1)
        self.assertEqual(current["total_spent"], 1200.0)
        self.assertEqual(current["avg_voucher_size"], 1200.0)
        self.assertEqual(current["bills_pending"], 1)
        self.assertEqual(current["overdue_count"], 1)

        self.assertEqual(previous["voucher_count"], 1)
        self.assertEqual(previous["total_spent"], 800.0)
        self.assertEqual(previous["bills_pending"], 0)

    def test_last_month_filter_applies_to_details(self):
        payees = db.get_top_payees(1, date_filter="Last Month")
        payments = db.get_payment_method_distribution(
            1,
            date_filter="Last Month",
        )

        self.assertEqual([row["payee"] for row in payees], ["Previous Vendor"])
        self.assertEqual(
            [row["payment_method"] for row in payments],
            ["Cheque"],
        )

    def test_received_bills_are_not_attention_items(self):
        aging = db.get_due_date_aging(1)

        self.assertEqual(aging["overdue"]["count"], 1)
        self.assertEqual(aging["overdue"]["total"], 1200.0)


class TestAnalyticsTransforms(unittest.TestCase):
    def test_sparse_trend_is_normalized_to_twelve_months(self):
        normalized = AnalyticsDashboard._normalize_monthly_trend(
            [{"month": "2026-10", "total": 2500.0, "count": 1}],
            as_of=datetime(2026, 10, 8),
        )

        self.assertEqual(len(normalized), 12)
        self.assertEqual(normalized[0]["month"], "2025-11")
        self.assertEqual(normalized[-1]["month"], "2026-10")
        self.assertEqual(normalized[-1]["total"], 2500.0)
        self.assertTrue(all(row["total"] == 0 for row in normalized[:-1]))


if __name__ == "__main__":
    unittest.main()
