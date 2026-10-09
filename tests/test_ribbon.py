"""
Unit tests for the compact single-line Dashboard Stats Bar and Show/Hide controls.
"""

import os
import unittest
import tempfile
import tkinter as tk
from unittest.mock import patch
import ttkbootstrap as ttk

import database as db
import sales_database as sales_db
from ui.main_window import MainWindow
from tests.test_widgets import get_test_root


class TestDashboardStatsBar(unittest.TestCase):

    def setUp(self):
        """Set up isolated test database in a temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_vouchers.db")
        self.attachments_dir = os.path.join(self.temp_dir, "attachments")
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        self._orig_db_path = db.DB_PATH
        self._orig_attachments_dir = db.ATTACHMENTS_DIR
        self._orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        db.init_db()
        user_id = db.create_user(
            "testadmin",
            "Test Administrator",
            "StrongPass1!",
            role="admin",
        )
        if user_id:
            db.set_current_user(
                db.authenticate_user("testadmin", "StrongPass1!")
            )

    def tearDown(self):
        """Restore original database paths."""
        db.set_current_user(None)
        db.DB_PATH = self._orig_db_path
        db.ATTACHMENTS_DIR = self._orig_attachments_dir
        db.BACKUP_DIR = self._orig_backup_dir

    def test_main_window_rejects_unauthenticated_session(self):
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        db.set_current_user(None)
        with self.assertRaises(PermissionError):
            MainWindow(root)
    def test_quickbooks_menu_groups_replace_visible_tabs(self):
        """Navigation uses native grouped menus while notebook tabs stay hidden."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        app = MainWindow(root)
        labels = [
            app._top_menubar.entrycget(index, "label")
            for index in range(app._top_menubar.index("end") + 1)
        ]
        self.assertEqual(labels, [
            "File", "Edit", "View", "Lists", "Favorites", "Company",
            "Customers", "Vendors", "Employees", "Banking", "Accountant",
            "Reports",
            "Window", "Help",
        ])
        tab_layout = ttk.Style().layout("Workspace.TNotebook.Tab")
        self.assertTrue(
            not tab_layout or tab_layout[0][0] == "null",
            f"Unexpected visible tab layout: {tab_layout}",
        )

        app._ensure_form_tab()
        self.assertEqual(int(app._currency_selector.account_combo.cget("width")), 48)
        app.prepare_for_logout()
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    def test_window_menu_and_chart_of_accounts_workspace(self):
        """Window lists open workspaces and COA shortcuts target its hierarchy."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        parent_id = db.create_account({
            "company_id": 1,
            "account_code": "5901",
            "account_name": "Workspace Parent",
            "account_type": "Expense",
            "normal_balance": "Debit",
        })
        child_id = db.create_account({
            "company_id": 1,
            "account_code": "5902",
            "account_name": "Workspace Child",
            "account_type": "Expense",
            "normal_balance": "Debit",
            "parent_id": parent_id,
        })
        app = MainWindow(root)

        app._rebuild_window_menu()
        initial_labels = [
            app._window_menu.entrycget(index, "label")
            for index in range(app._window_menu.index("end") + 1)
        ]
        self.assertEqual(
            initial_labels, ["✓ Accountant Centre", "Voucher Register"]
        )

        app._open_chart_of_accounts()
        workspace = app._chart_of_accounts
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_COA
        )
        self.assertIs(workspace.master, app._coa_tab)
        self.assertEqual(workspace.tree.parent(str(child_id)), str(parent_id))

        app._rebuild_window_menu()
        open_labels = [
            app._window_menu.entrycget(index, "label")
            for index in range(app._window_menu.index("end") + 1)
        ]
        self.assertIn("✓ Chart of Accounts", open_labels)
        self.assertNotIn("Invoice Entry", open_labels)
        self.assertNotIn("Customer Centre", open_labels)

        workspace.tree.selection_set(str(child_id))
        with patch("ui.coa_dialog.AccountEditModal") as edit_modal:
            self.assertEqual(app._shortcut_edit(), "break")
            self.assertEqual(
                edit_modal.call_args.kwargs["account_data"]["id"], child_id
            )
        with patch("ui.coa_dialog.AccountEditModal") as new_modal:
            self.assertEqual(app._shortcut_new(), "break")
            self.assertNotIn("account_data", new_modal.call_args.kwargs)

        app.prepare_for_logout()
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    def test_accounting_workspaces_are_full_page_and_escape_returns_home(self):
        """Ledger, Trial Balance, journals, and COA stay in the main window."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        app = MainWindow(root)

        ledger = app._open_general_ledger()
        self.assertIs(ledger.master, app._general_ledger_tab)
        self.assertEqual(
            app._notebook.index(app._notebook.select()),
            app.TAB_GENERAL_LEDGER,
        )
        self.assertEqual(ledger.notebook.index(ledger.notebook.select()), 0)

        app._open_trial_balance()
        self.assertEqual(ledger.notebook.index(ledger.notebook.select()), 1)

        ledger._open_coa()
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_COA
        )
        coa = app._chart_of_accounts
        coa._open_general_ledger()
        self.assertEqual(
            app._notebook.index(app._notebook.select()),
            app.TAB_GENERAL_LEDGER,
        )

        journal = app._open_new_journal_entry()
        self.assertIs(journal.master, app._journal_tab)
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_JOURNAL
        )
        expense = db.get_account_by_code("5410", 1)
        cash = db.get_account_by_code("1110", 1)
        journal.ref_var.set("FULL-PAGE-JOURNAL")
        journal.desc_var.set("Embedded journal posting test")
        journal.lines_data = [
            {
                "account_id": expense["id"],
                "account_label": "5410 - Office Supplies & Stationery (Expense)",
                "description": "Test debit",
                "debit_amount": 125.0,
                "credit_amount": 0.0,
            },
            {
                "account_id": cash["id"],
                "account_label": "1110 - Petty Cash (Asset)",
                "description": "Test credit",
                "debit_amount": 0.0,
                "credit_amount": 125.0,
            },
        ]
        journal._refresh_lines_table()
        journal._recalculate_balance()
        journal._save_entry()
        with db.get_connection() as conn:
            posted = conn.execute(
                "SELECT id FROM journal_entries WHERE reference = ?",
                ("FULL-PAGE-JOURNAL",),
            ).fetchone()
        self.assertIsNotNone(posted)
        self.assertEqual(
            app._notebook.index(app._notebook.select()),
            app.TAB_GENERAL_LEDGER,
        )

        app._open_new_journal_entry()
        popup = tk.Toplevel(root)
        root.update_idletasks()
        self.assertEqual(app._shortcut_escape(), "break")
        self.assertFalse(popup.winfo_exists())
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_JOURNAL
        )
        self.assertEqual(app._shortcut_escape(), "break")
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_ACCOUNTANT
        )

        app._rebuild_window_menu()
        labels = [
            app._window_menu.entrycget(index, "label")
            for index in range(app._window_menu.index("end") + 1)
        ]
        self.assertIn("General Ledger & Trial Balance", labels)
        self.assertIn("Journal Entry", labels)

        app.prepare_for_logout()
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    def test_create_invoice_workspace_initializes_currency_controls(self):
        """Opening the embedded invoice workspace initializes currency state."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")
        sales_db.save_sales_item({
            "company_id": 1,
            "name": "Inline Consulting",
            "item_type": "Service",
            "sales_price": 2500.0,
            "is_active": True,
        })
        app = MainWindow(root)

        app._open_invoice_workspace()

        workspace = app._invoice_workspace
        self.assertIsNotNone(workspace)
        self.assertEqual(workspace.home_currency, "LKR")
        self.assertEqual(workspace.currency_values, ["LKR"])
        self.assertEqual(workspace.currency_var.get(), "LKR")
        self.assertEqual(workspace.rate_var.get(), "1.000000")
        self.assertTrue(workspace.quick_item_combo.winfo_exists())
        workspace.quick_item_var.set("Inline Consulting")
        workspace._quick_item_selected()
        workspace._quick_add_line()
        self.assertEqual(len(workspace.lines_data), 1)
        self.assertEqual(workspace.lines_data[0]["unit_price"], 2500.0)
        with patch.object(workspace, "_save") as save_invoice:
            self.assertEqual(app._shortcut_save(), "break")
            save_invoice.assert_called_once_with(issue=True)
        self.assertEqual(app._shortcut_escape(), "break")
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_CUSTOMERS
        )
        customer_center = app._ensure_customer_center()
        self.assertTrue(customer_center.customer_tree.bind("<Double-1>"))
        self.assertEqual(app._shortcut_escape(), "break")
        self.assertEqual(
            app._notebook.index(app._notebook.select()), app.TAB_ACCOUNTANT
        )
        app.prepare_for_logout()
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

    def test_stats_setting_persistence(self):
        """Test reading and writing stats visibility to app_settings table."""
        self.assertEqual(db.get_app_setting("dashboard_stats_visible", "show"), "show")

        db.set_app_setting("dashboard_stats_visible", "hide")
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "hide")

        db.set_app_setting("dashboard_stats_visible", "show")
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "show")

    def test_stats_bar_in_main_window(self):
        """Test Show and Hide transitions of the compact single-line stats bar in MainWindow."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Start with default show
        db.set_app_setting("dashboard_stats_visible", "show")
        app = MainWindow(root)

        self.assertTrue(app._stats_visible)
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Verify stat variables exist
        for key in ("total", "pending", "amount", "unprinted"):
            self.assertIn(key, app._stat_vars)

        # Hide stats bar
        app._hide_stats_bar(notify=False)
        self.assertFalse(app._stats_visible)
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "hide")
        self.assertNotIn(app._stats_bar, root.pack_slaves())

        # Show stats bar
        app._show_stats_bar(notify=False)
        self.assertTrue(app._stats_visible)
        self.assertEqual(db.get_app_setting("dashboard_stats_visible"), "show")
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Test Ctrl+F1 toggle
        app._shortcut_toggle_stats()
        self.assertFalse(app._stats_visible)
        self.assertNotIn(app._stats_bar, root.pack_slaves())

        app._shortcut_toggle_stats()
        self.assertTrue(app._stats_visible)
        self.assertIn(app._stats_bar, root.pack_slaves())

        # Cleanup children in root to prevent interference with other tests
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
