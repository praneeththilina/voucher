"""
Unit and UI tests for Products & Services Item Manager dialogs.
"""

import unittest
import os
import tempfile
import tkinter as tk
import ttkbootstrap as tb

import database as db
import sales_database as sales_db


_shared_root = None


def get_test_root():
    global _shared_root
    try:
        exists = _shared_root is not None and bool(_shared_root.winfo_exists())
    except Exception:
        exists = False
        _shared_root = None

    if not exists:
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
            tb.Style(theme="minty-light")
        except Exception:
            _shared_root = None
    return _shared_root


class TestProductsServicesDialogUI(unittest.TestCase):
    """GUI tests for ProductsServicesDialog auto-selection, keyboard bindings, and button states."""

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "items_ui_test.db")
        db.init_db()

        # Seed test items in sales_database
        self.company_id = db.get_active_company_id()
        sales_db.save_sales_item(
            {
                "company_id": self.company_id,
                "name": "Consulting Service",
                "item_type": "Service",
                "sales_price": 150.00,
                "is_active": True,
            }
        )
        sales_db.save_sales_item(
            {
                "company_id": self.company_id,
                "name": "Office Paper",
                "item_type": "Non-inventory",
                "sales_price": 25.00,
                "is_active": True,
            }
        )

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir

    def test_dialog_autoselects_first_row_and_enables_buttons(self):
        """Test that ProductsServicesDialog auto-selects first row and enables action buttons."""
        from ui.item_manager import ProductsServicesDialog

        dlg = ProductsServicesDialog(self.root, company_id=self.company_id)
        try:
            selection = dlg.tree.selection()
            self.assertTrue(len(selection) > 0)
            self.assertEqual(str(dlg.edit_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg.deactivate_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg.merge_btn["state"]), tk.NORMAL)

            # Clear selection and verify buttons become disabled
            dlg.tree.selection_set(())
            dlg._update_button_states()
            self.assertEqual(str(dlg.edit_btn["state"]), tk.DISABLED)
            self.assertEqual(str(dlg.deactivate_btn["state"]), tk.DISABLED)
            self.assertEqual(str(dlg.merge_btn["state"]), tk.DISABLED)
        finally:
            dlg.destroy()

    def test_escape_key_dismisses_dialogs(self):
        """Test that pressing Escape dismisses ProductsServicesDialog and ItemEditDialog."""
        from ui.item_manager import ProductsServicesDialog, ItemEditDialog

        self.root.deiconify()
        try:
            dlg = ProductsServicesDialog(self.root, company_id=self.company_id)
            dlg.focus_set()
            dlg.update()
            self.assertTrue(dlg.winfo_exists())
            dlg.event_generate("<KeyPress>", keysym="Escape")
            self.root.update()
            self.assertFalse(dlg.winfo_exists())

            edit_dlg = ItemEditDialog(self.root, company_id=self.company_id)
            edit_dlg.focus_set()
            edit_dlg.update()
            self.assertTrue(edit_dlg.winfo_exists())
            edit_dlg.event_generate("<KeyPress>", keysym="Escape")
            self.root.update()
            self.assertFalse(edit_dlg.winfo_exists())
        finally:
            self.root.withdraw()


if __name__ == "__main__":
    unittest.main()
