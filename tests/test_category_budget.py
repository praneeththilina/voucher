import unittest
import tempfile
import os
import tkinter as tk
import ttkbootstrap as ttk
import database as db

_shared_root = None


def get_test_root():
    global _shared_root
    if _shared_root is None or not _shared_root.winfo_exists():
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
            ttk.Style(theme="cosmo")
        except Exception:
            _shared_root = None
    return _shared_root


def tearDownModule():
    global _shared_root
    if _shared_root and _shared_root.winfo_exists():
        try:
            _shared_root.destroy()
        except Exception:
            pass
        _shared_root = None


class TestCategoryBudgetDatabase(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_set_and_get_category_budget(self):
        cat_id = db.add_category("Office Stationery")
        self.assertIsNotNone(cat_id)

        # Set budget to 25,000
        ok = db.set_category_budget(cat_id, 25000.0)
        self.assertTrue(ok)

        # Get full categories
        full_cats = db.get_all_categories_full()
        target = next((c for c in full_cats if c["id"] == cat_id), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["monthly_budget"], 25000.0)

    def test_invalid_negative_budget_raises_value_error(self):
        cat_id = db.add_category("Travel & Transport")
        with self.assertRaises(ValueError):
            db.set_category_budget(cat_id, "invalid_num")

    def test_category_budget_calculations_and_badges(self):
        cat_id = db.add_category("Utilities")
        db.set_category_budget(cat_id, 10000.0)

        # Create voucher with line item in Utilities for 8,500
        today_month = db.datetime.now().strftime("%Y-%m")
        v_date = f"{today_month}-10"

        db.create_voucher(
            {"date": v_date, "paid_to": "Electricity Board", "cash_given_by": "Cashier"},
            [{"description": "Electricity Bill", "category": "Utilities", "amount": 8500.0}],
            company_id=1
        )

        budgets = db.get_category_budgets(month_str=today_month, company_id=1)
        util_cat = next((b for b in budgets if b["id"] == cat_id), None)

        self.assertIsNotNone(util_cat)
        self.assertEqual(util_cat["monthly_budget"], 10000.0)
        self.assertEqual(util_cat["actual_spend"], 8500.0)
        self.assertEqual(util_cat["remaining"], 1500.0)
        self.assertEqual(util_cat["utilization_pct"], 85.0)
        self.assertEqual(util_cat["status_badge"], "🟠 Near Limit")

    def test_check_category_budget_alert_over_budget(self):
        cat_id = db.add_category("IT Software")
        db.set_category_budget(cat_id, 5000.0)

        today_month = db.datetime.now().strftime("%Y-%m")
        v_date = f"{today_month}-05"

        db.create_voucher(
            {"date": v_date, "paid_to": "SaaS Vendor", "cash_given_by": "Cashier"},
            [{"description": "License Subscription", "category": "IT Software", "amount": 4000.0}],
            company_id=1
        )

        # Proposed line item for 2,000 -> Total 6,000 vs Budget 5,000
        alert = db.check_category_budget_alert("IT Software", amount_to_add=2000.0, month_str=today_month, company_id=1)
        self.assertTrue(alert["is_over_budget"])
        self.assertEqual(alert["monthly_budget"], 5000.0)
        self.assertEqual(alert["current_spend"], 4000.0)
        self.assertEqual(alert["proposed_total"], 6000.0)
        self.assertEqual(alert["over_amount"], 1000.0)


class TestCategoryBudgetUI(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.cat_id = db.add_category("Marketing")
        db.set_category_budget(self.cat_id, 30000.0)

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_category_manager_dialog_budget_button_and_display(self):
        from ui.category_manager import CategoryManagerDialog

        dialog = CategoryManagerDialog(self.root)
        self.assertTrue(hasattr(dialog, "_budget_btn"))

        # Initially no row selected -> budget button disabled
        self.assertEqual(str(dialog._budget_btn["state"]), tk.DISABLED)

        # Select Marketing row -> budget button becomes normal
        dialog._tree.selection_set(str(self.cat_id))
        dialog._update_button_states()
        self.assertEqual(str(dialog._budget_btn["state"]), tk.NORMAL)

        row_vals = dialog._tree.item(str(self.cat_id))["values"]
        self.assertEqual(row_vals[0], "Marketing")
        self.assertIn("30,000.00", row_vals[1])

        dialog.destroy()

    def test_expense_summary_dialog_budget_performance_tab(self):
        from ui.dialogs import ExpenseSummaryDialog

        dialog = ExpenseSummaryDialog(self.root)
        self.assertTrue(hasattr(dialog, "_budget_tree"))

        children = dialog._budget_tree.get_children()
        self.assertGreater(len(children), 0)

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
