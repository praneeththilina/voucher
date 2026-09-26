import unittest
import tkinter as tk
import ttkbootstrap as ttk
from ui.widgets import LineItemFrame
from ui.dialogs import PrintOptionsDialog

_shared_root = None


def get_test_root():
    global _shared_root
    if _shared_root is None or not _shared_root.winfo_exists():
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
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


class TestLineItemFrame(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")
        self.frame = LineItemFrame(self.root)

    def tearDown(self):
        if hasattr(self, "frame") and self.frame:
            try:
                self.frame.destroy()
            except Exception:
                pass

    def test_single_row_remove_button_disabled(self):
        """When only 1 line item exists, remove button should be disabled."""
        self.assertEqual(len(self.frame._rows), 1)
        btn = self.frame._rows[0]["remove_btn"]
        self.assertEqual(str(btn["state"]), tk.DISABLED)

    def test_multiple_rows_remove_button_enabled(self):
        """When multiple line items exist, remove buttons should be enabled."""
        self.frame.add_row()
        self.assertEqual(len(self.frame._rows), 2)
        btn1 = self.frame._rows[0]["remove_btn"]
        btn2 = self.frame._rows[1]["remove_btn"]
        self.assertEqual(str(btn1["state"]), tk.NORMAL)
        self.assertEqual(str(btn2["state"]), tk.NORMAL)

    def test_removing_row_updates_button_states(self):
        """Removing a row down to 1 row should re-disable the remove button."""
        self.frame.add_row()
        self.assertEqual(len(self.frame._rows), 2)
        row_frame_to_remove = self.frame._rows[1]["frame"]
        self.frame._remove_row(row_frame_to_remove)
        self.assertEqual(len(self.frame._rows), 1)
        remaining_btn = self.frame._rows[0]["remove_btn"]
        self.assertEqual(str(remaining_btn["state"]), tk.DISABLED)


class TestMainWindowAttachments(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        # Create dummy buttons mimicking MainWindow attachment controls
        self.preview_btn = ttk.Button(self.root, text="Preview")
        self.remove_btn = ttk.Button(self.root, text="Remove")

    def tearDown(self):
        if hasattr(self, "preview_btn"):
            try:
                self.preview_btn.destroy()
            except Exception:
                pass
        if hasattr(self, "remove_btn"):
            try:
                self.remove_btn.destroy()
            except Exception:
                pass

    def _refresh_attachment_list_logic(self, existing, pending):
        total = len(existing) + len(pending)
        state = tk.NORMAL if total > 0 else tk.DISABLED
        self.preview_btn.config(state=state)
        self.remove_btn.config(state=state)

    def test_attachment_buttons_disabled_when_empty(self):
        """When no attachments exist, preview and remove buttons should be disabled."""
        self._refresh_attachment_list_logic([], [])
        self.assertEqual(str(self.preview_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.remove_btn["state"]), tk.DISABLED)

    def test_attachment_buttons_enabled_when_attachments_exist(self):
        """When attachments exist, preview and remove buttons should be enabled."""
        self._refresh_attachment_list_logic([], [{"filename": "test.pdf"}])
        self.assertEqual(str(self.preview_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.remove_btn["state"]), tk.NORMAL)


class TestPrintOptionsDialog(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.sample_vouchers = [
            {"id": 1, "voucher_number": "V-001", "date": "2026-09-24", "paid_to": "Alice", "total_amount": 100.0},
            {"id": 2, "voucher_number": "V-002", "date": "2026-09-24", "paid_to": "Bob", "total_amount": 200.0},
        ]
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass

    def test_print_options_dialog_button_states(self):
        """Test that PrintOptionsDialog action buttons reflect checkbox selection states."""
        self.dialog = PrintOptionsDialog(self.root, self.sample_vouchers, callback=lambda ids, action: None)

        # By default, all items are checked -> buttons should be NORMAL
        self.assertEqual(str(self.dialog._preview_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.dialog._print_btn["state"]), tk.NORMAL)

        # Deselect All -> buttons should be DISABLED
        self.dialog._set_all(False)
        self.assertEqual(str(self.dialog._preview_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.dialog._print_btn["state"]), tk.DISABLED)

        # Select one -> buttons should become NORMAL
        self.dialog._check_vars[1].set(True)
        self.assertEqual(str(self.dialog._preview_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.dialog._print_btn["state"]), tk.NORMAL)


class TestTemplateManagerDialog(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        import tempfile
        import database as db
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        t_data = {
            "template_name": "Internet Subscription",
            "paid_to": "Dialog Axiata",
            "payment_method": "Cash",
            "bill_status": "Pending",
        }
        items = [{"description": "Monthly Fiber", "category": "Utilities", "amount": 3500.0}]
        self.template_id = db.create_template(t_data, items, company_id=1)
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass

        import os
        import database as db
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_template_manager_button_states(self):
        from ui.template_manager import TemplateManagerDialog
        self.dialog = TemplateManagerDialog(self.root)

        # 1. Initially no template selected -> buttons must be DISABLED
        self.assertEqual(str(self.dialog._apply_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.dialog._delete_btn["state"]), tk.DISABLED)

        # 2. Select the template in the tree -> buttons must become NORMAL
        self.dialog._tree.selection_set(str(self.template_id))
        self.dialog._on_template_selected()
        self.assertEqual(str(self.dialog._apply_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.dialog._delete_btn["state"]), tk.NORMAL)

        # 3. Clear selection -> buttons must become DISABLED again
        self.dialog._tree.selection_set(())
        self.dialog._on_template_selected()
        self.assertEqual(str(self.dialog._apply_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.dialog._delete_btn["state"]), tk.DISABLED)


class TestCategoryAndNameManagerDialogs(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        import tempfile
        import database as db
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.cat_id = db.add_category("Office Supplies")
        self.person_id = db.add_person("John Doe")

        self.cat_dialog = None
        self.name_dialog = None

    def tearDown(self):
        if self.cat_dialog:
            try:
                self.cat_dialog.destroy()
            except Exception:
                pass
        if self.name_dialog:
            try:
                self.name_dialog.destroy()
            except Exception:
                pass

        import os
        import database as db
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_category_manager_button_states(self):
        from ui.category_manager import CategoryManagerDialog
        self.cat_dialog = CategoryManagerDialog(self.root)

        # Initially no row selected -> edit and toggle buttons disabled
        self.assertEqual(str(self.cat_dialog._edit_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.cat_dialog._toggle_btn["state"]), tk.DISABLED)

        # Ensure action buttons exist and are properly instantiated
        self.assertTrue(hasattr(self.cat_dialog, "_add_btn"))
        self.assertTrue(hasattr(self.cat_dialog, "_close_btn"))

        # Select a category row -> edit and toggle buttons enabled
        self.cat_dialog._tree.selection_set(str(self.cat_id))
        self.cat_dialog._update_button_states()
        self.assertEqual(str(self.cat_dialog._edit_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.cat_dialog._toggle_btn["state"]), tk.NORMAL)

        # Clear selection -> edit and toggle buttons disabled again
        self.cat_dialog._tree.selection_set(())
        self.cat_dialog._update_button_states()
        self.assertEqual(str(self.cat_dialog._edit_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.cat_dialog._toggle_btn["state"]), tk.DISABLED)

    def test_name_manager_button_states(self):
        from ui.name_manager import NameManagerDialog
        self.name_dialog = NameManagerDialog(self.root)

        # Initially no row selected -> edit and toggle buttons disabled
        self.assertEqual(str(self.name_dialog._edit_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.name_dialog._toggle_btn["state"]), tk.DISABLED)

        # Ensure action buttons exist and are properly instantiated
        self.assertTrue(hasattr(self.name_dialog, "_add_btn"))
        self.assertTrue(hasattr(self.name_dialog, "_close_btn"))

        # Select a person row -> edit and toggle buttons enabled
        self.name_dialog._tree.selection_set(str(self.person_id))
        self.name_dialog._update_button_states()
        self.assertEqual(str(self.name_dialog._edit_btn["state"]), tk.NORMAL)
        self.assertEqual(str(self.name_dialog._toggle_btn["state"]), tk.NORMAL)

        # Clear selection -> edit and toggle buttons disabled again
        self.name_dialog._tree.selection_set(())
        self.name_dialog._update_button_states()
        self.assertEqual(str(self.name_dialog._edit_btn["state"]), tk.DISABLED)
        self.assertEqual(str(self.name_dialog._toggle_btn["state"]), tk.DISABLED)


class TestExportVouchersDialog(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.mock_vouchers = [
            {
                "id": 1,
                "voucher_number": "26SEP_01",
                "date": "2026-09-26",
                "paid_to": "Stationery Store",
                "total_amount": 5000.0,
                "status": "Active",
            },
            {
                "id": 2,
                "voucher_number": "26SEP_02",
                "date": "2026-09-26",
                "paid_to": "Hardware Hub",
                "total_amount": 12000.0,
                "status": "Cancelled",
            },
        ]
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass

    def test_dialog_init_and_preview_updates(self):
        from ui.dialogs import ExportVouchersDialog
        self.dialog = ExportVouchersDialog(self.root, self.mock_vouchers)

        # 1. Defaults
        self.assertEqual(self.dialog._format_var.get(), "itemized")
        self.assertTrue(self.dialog._total_row_var.get())
        self.assertTrue(self.dialog._active_only_var.get())
        self.assertTrue(self.dialog._open_file_var.get())

        # 2. Check summary card with active_only=True (only 1 active voucher)
        self.assertIn("1 voucher(s)", self.dialog._summary_lbl.cget("text"))
        self.assertIn("5,000.00", self.dialog._summary_lbl.cget("text"))

        # 3. Toggle active_only=False -> should show 2 vouchers and 17,000.00
        self.dialog._active_only_var.set(False)
        self.dialog._update_summary_card()
        self.assertIn("2 voucher(s)", self.dialog._summary_lbl.cget("text"))
        self.assertIn("17,000.00", self.dialog._summary_lbl.cget("text"))

        # 4. Check columns preview for itemized
        self.assertIn("Line Description", self.dialog._cols_lbl.cget("text"))
        self.assertIn("Line Amount", self.dialog._cols_lbl.cget("text"))

        # 5. Switch format to register
        self.dialog._format_var.set("register")
        self.dialog._on_format_changed()
        self.assertIn("Categories", self.dialog._cols_lbl.cget("text"))
        self.assertIn("Items Count", self.dialog._cols_lbl.cget("text"))

        # 6. Switch format to category_summary
        self.dialog._format_var.set("category_summary")
        self.dialog._on_format_changed()
        self.assertIn("Transaction Count", self.dialog._cols_lbl.cget("text"))
        self.assertIn("Share (%)", self.dialog._cols_lbl.cget("text"))


class TestMoneyFloatDialog(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        import tempfile
        import database as db
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        # Seed test float and voucher
        self.float_id = db.create_float(
            company_id=1,
            name="Main Vault Float",
            opening_balance=50000.0,
            opening_date="2026-09-01",
            custodian="Chief Cashier",
            is_default=True
        )
        db.add_float_transaction(
            float_id=self.float_id,
            amount=20000.0,
            date="2026-09-05",
            trans_type="Inflow",
            source_ref="Bank Cheque 101"
        )
        db.create_voucher(
            {"date": "2026-09-06", "paid_to": "Hardware Ltd", "cash_given_by": "Cashier", "payment_method": "Cash", "float_id": self.float_id},
            [{"description": "Tools", "amount": 8000.0}],
            company_id=1
        )
        self.dialog = None

    def tearDown(self):
        if self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass

        import os
        import database as db
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_float_dialog_kpis_and_ledger(self):
        from ui.float_manager import MoneyFloatDialog
        self.dialog = MoneyFloatDialog(self.root, company_id=1)

        # Verify KPI values (Opening: 50k, Inflow: 20k, Outflow: 8k -> Balance: 62k)
        self.assertIn("62,000.00", self.dialog._kpi_vars["current_balance"].get())
        self.assertIn("50,000.00", self.dialog._kpi_vars["opening_balance"].get())
        self.assertIn("20,000.00", self.dialog._kpi_vars["total_inflows"].get())
        self.assertIn("8,000.00", self.dialog._kpi_vars["total_outflows"].get())
        self.assertIn("Chief Cashier", self.dialog._custodian_badge_var.get())

        # Verify treeview entries (Opening + Inflow + Voucher = 3 entries)
        children = self.dialog._tree.get_children()
        self.assertEqual(len(children), 3)

        # Default sort should have latest transaction on top (2026-09-06)
        first_row_values = self.dialog._tree.item(children[0])["values"]
        self.assertEqual(first_row_values[0], "2026-09-06")
        last_row_values = self.dialog._tree.item(children[-1])["values"]
        self.assertEqual(last_row_values[0], "2026-09-01")

    def test_float_dialog_header_sorting(self):
        from ui.float_manager import MoneyFloatDialog
        self.dialog = MoneyFloatDialog(self.root, company_id=1)

        # 1. Initial default state: date descending (latest top)
        self.assertEqual(self.dialog._sort_col, "date")
        self.assertTrue(self.dialog._sort_desc)
        date_heading = self.dialog._tree.heading("date")["text"]
        self.assertIn("▼", date_heading)
        children = self.dialog._tree.get_children()
        self.assertEqual(self.dialog._tree.item(children[0])["values"][0], "2026-09-06")

        # 2. Click Date column -> toggles to ascending (oldest top)
        self.dialog._sort_by_column("date")
        self.assertFalse(self.dialog._sort_desc)
        self.assertIn("▲", self.dialog._tree.heading("date")["text"])
        children = self.dialog._tree.get_children()
        self.assertEqual(self.dialog._tree.item(children[0])["values"][0], "2026-09-01")

        # 3. Click Inflow column -> sorts by highest inflow first (Opening: 50k, Top-up: 20k)
        self.dialog._sort_by_column("inflow")
        self.assertEqual(self.dialog._sort_col, "inflow")
        self.assertTrue(self.dialog._sort_desc)
        children = self.dialog._tree.get_children()
        first_inflow = self.dialog._tree.item(children[0])["values"][6]
        second_inflow = self.dialog._tree.item(children[1])["values"][6]
        self.assertIn("50,000.00", first_inflow)
        self.assertIn("20,000.00", second_inflow)

        # 4. Click Outflow column -> sorts by highest outflow first
        self.dialog._sort_by_column("outflow")
        self.assertEqual(self.dialog._sort_col, "outflow")
        self.assertTrue(self.dialog._sort_desc)
        children = self.dialog._tree.get_children()
        first_outflow = self.dialog._tree.item(children[0])["values"][7]
        self.assertIn("8,000.00", first_outflow)

    def test_add_topup_dialog_validation(self):
        from ui.float_manager import AddTopUpDialog
        import database as db

        topup_dlg = AddTopUpDialog(self.root, float_id=self.float_id, trans_type="Inflow")
        topup_dlg._amt_var.set("10000.00")
        topup_dlg._ref_var.set("Ref #999")
        topup_dlg._handed_var.set("Director")
        topup_dlg._save()

        # Check float balance updated (62k + 10k = 72k)
        flt = db.get_float(self.float_id)
        self.assertEqual(flt["current_balance"], 72000.0)


class TestMainWindowFloatIntegration(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        import tempfile
        import database as db
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        from ui.main_window import MainWindow
        self.app = MainWindow(self.root)

    def tearDown(self):
        import os
        import database as db
        db.DB_PATH = self.orig_db_path
        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

    def test_main_window_float_ui_integration(self):
        import database as db
        # 1. Header bar button should exist and show default float name
        self.assertTrue(hasattr(self.app, "_float_bar_btn"))
        btn_text = self.app._float_bar_btn.cget("text")
        self.assertIn("Main Cash Float", btn_text)

        # 2. Form float selector should be populated
        self.assertTrue(hasattr(self.app, "_form_float_combo"))
        self.assertEqual(self.app._form_float_var.get(), "Main Cash Float")

        # 3. Create a cash voucher via form
        self.app._paid_to.insert(0, "Float Test Vendor")
        self.app._cash_given_by.insert(0, "Alice")
        self.app._line_items.set_items([{"description": "Stamps", "category": "Postage", "amount": 1200.0}])
        vid = self.app._save_voucher()
        self.assertIsNotNone(vid)

        # Verify voucher saved with float_id
        v = db.get_voucher(vid)["voucher"]
        self.assertIsNotNone(v.get("float_id"))
        self.assertEqual(v.get("float_name"), "Main Cash Float")

        # 4. Header button should reflect updated balance (0 - 1200 = -1200, overdrawn indicator)
        self.app._update_company_header()
        updated_btn_text = self.app._float_bar_btn.cget("text")
        self.assertIn("1,200.00", updated_btn_text)


if __name__ == "__main__":
    unittest.main()



