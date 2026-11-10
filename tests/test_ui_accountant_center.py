"""UI and data-contract tests for the Accountant Centre landing page."""

from datetime import date
import os
import shutil
import tempfile
import unittest

import database as db
from ui.accountant_center import AccountantCenterFrame
from tests.test_widgets import get_test_root


class TestAccountantCenter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "accountant_center.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        cash = db.get_account_by_code("1110", company_id=1)
        sales = db.get_account_by_code("4110", company_id=1)
        db.create_journal_entry(
            {
                "company_id": 1,
                "entry_date": date.today().strftime("%Y-%m-%d"),
                "description": "Dashboard smoke sale",
            },
            [
                {
                    "account_id": cash["id"],
                    "debit_amount": 2000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": sales["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 2000.0,
                },
            ],
        )
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

    def tearDown(self):
        for child in self.root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_overview_loads_kpis_attention_and_recent_activity(self):
        callbacks = {
            name: (lambda *args: None)
            for name in (
                "new_voucher",
                "new_journal",
                "chart_of_accounts",
                "general_ledger",
                "financial_reports",
                "ap_invoices",
                "ap_aging",
                "ar_invoices",
                "ar_aging",
                "bank_reconciliation",
                "period_close",
                "alerts",
                "voucher_list",
            )
        }
        center = AccountantCenterFrame(
            self.root,
            company_id=1,
            callbacks=callbacks,
        )
        center.pack(fill="both", expand=True)
        center._load_data()

        self.assertIn("2,000.00", center._kpi_vars["cash"].get())
        self.assertIn("2,000.00", center._kpi_vars["profit"].get())
        self.assertEqual(len(center.attention_tree.get_children()), 3)
        self.assertEqual(len(center.recent_tree.get_children()), 1)
        self.assertNotIn("Could not refresh", center.status_var.get())

        # Verify auto-selection of the first row in attention and recent trees
        self.assertEqual(center.attention_tree.selection(), ("attention-0",))
        self.assertEqual(center.recent_tree.selection(), ("entry-0",))

    def test_keypad_enter_and_keyboard_navigation(self):
        invoked = []
        callbacks = {
            "ar_aging": lambda: invoked.append("ar_aging"),
        }
        center = AccountantCenterFrame(
            self.root,
            company_id=1,
            callbacks=callbacks,
        )
        center.pack(fill="both", expand=True)
        center._load_data()

        # Check key bindings on trees (Tkinter normalizes <KP_Enter> to <Key-KP_Enter>)
        self.assertTrue(
            "<KP_Enter>" in center.attention_tree.bind() or "<Key-KP_Enter>" in center.attention_tree.bind()
        )
        self.assertTrue(
            "<KP_Enter>" in center.recent_tree.bind() or "<Key-KP_Enter>" in center.recent_tree.bind()
        )

        # Test triggering attention action via keypad enter callback
        center.attention_tree.selection_set("attention-0")
        center._open_attention_item()
        self.assertIn("ar_aging", invoked)


if __name__ == "__main__":
    unittest.main()