"""UI regression tests for report-to-ledger drill-down navigation."""

from datetime import date
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import database as db
from ui.financial_reports_dialog import FinancialReportsDialog
from tests.test_widgets import get_test_root


class TestFinancialReportDrilldownUI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "reports_ui.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        cash = db.get_account_by_code("1110", company_id=1)
        sales = db.get_account_by_code("4110", company_id=1)
        today = date.today().strftime("%Y-%m-%d")
        db.create_journal_entry(
            {
                "company_id": 1,
                "entry_date": today,
                "description": "Current-period cash sale",
            },
            [
                {
                    "account_id": cash["id"],
                    "debit_amount": 15000.0,
                    "credit_amount": 0.0,
                },
                {
                    "account_id": sales["id"],
                    "debit_amount": 0.0,
                    "credit_amount": 15000.0,
                },
            ],
        )
        self.sales_id = sales["id"]
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

    def test_profit_loss_row_opens_transaction_detail(self):
        dialog = FinancialReportsDialog(self.root, company_id=1, initial_tab=0)
        detail_rows = {
            iid: detail
            for (tree, iid), detail in dialog._drilldown_rows.items()
            if tree is dialog.pl_tree
        }
        selected_iid = next(
            iid
            for iid, detail in detail_rows.items()
            if detail["account_ids"] == (self.sales_id,)
        )
        dialog.pl_tree.selection_set(selected_iid)

        with patch(
            "ui.financial_reports_dialog.ReportDrilldownDialog"
        ) as drilldown:
            dialog._open_report_drilldown(dialog.pl_tree)

        drilldown.assert_called_once()
        kwargs = drilldown.call_args.kwargs
        self.assertEqual(kwargs["account_ids"], (self.sales_id,))
        self.assertIsNotNone(kwargs["start_date"])
        self.assertIsNotNone(kwargs["end_date"])
        dialog.destroy()

    def test_all_four_reports_expose_drilldown_rows(self):
        dialog = FinancialReportsDialog(self.root, company_id=1)
        for tree in (
            dialog.pl_tree,
            dialog.bs_tree,
            dialog.tb_tree,
            dialog.cf_tree,
        ):
            self.assertTrue(
                any(report_tree is tree for report_tree, _iid in dialog._drilldown_rows),
                f"Expected drill-down metadata for {tree}",
            )
        dialog.destroy()


if __name__ == "__main__":
    unittest.main()