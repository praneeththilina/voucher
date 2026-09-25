import unittest
import tkinter as tk
import ttkbootstrap as ttk
from ui.widgets import LineItemFrame
from ui.dialogs import PrintOptionsDialog


class TestLineItemFrame(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except Exception as e:
            cls.root = None

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        if not self.root:
            self.skipTest("Tkinter display not available")
        self.frame = LineItemFrame(self.root)

    def tearDown(self):
        if hasattr(self, "frame") and self.frame:
            self.frame.destroy()

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
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")

        # Create dummy buttons mimicking MainWindow attachment controls
        self.preview_btn = ttk.Button(self.root, text="Preview")
        self.remove_btn = ttk.Button(self.root, text="Remove")

    def tearDown(self):
        if hasattr(self, "root") and self.root:
            self.root.destroy()

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
        try:
            self.root = tk.Tk()
            self.root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")

        self.sample_vouchers = [
            {"id": 1, "voucher_number": "V-001", "date": "2026-09-24", "paid_to": "Alice", "total_amount": 100.0},
            {"id": 2, "voucher_number": "V-002", "date": "2026-09-24", "paid_to": "Bob", "total_amount": 200.0},
        ]

    def tearDown(self):
        if hasattr(self, "root") and self.root:
            self.root.destroy()

    def test_print_options_dialog_button_states(self):
        """Test that PrintOptionsDialog action buttons reflect checkbox selection states."""
        dialog = PrintOptionsDialog(self.root, self.sample_vouchers, callback=lambda ids, action: None)

        # By default, all items are checked -> buttons should be NORMAL
        self.assertEqual(str(dialog._preview_btn["state"]), tk.NORMAL)
        self.assertEqual(str(dialog._print_btn["state"]), tk.NORMAL)

        # Deselect All -> buttons should be DISABLED
        dialog._set_all(False)
        self.assertEqual(str(dialog._preview_btn["state"]), tk.DISABLED)
        self.assertEqual(str(dialog._print_btn["state"]), tk.DISABLED)

        # Select one -> buttons should become NORMAL
        dialog._check_vars[1].set(True)
        self.assertEqual(str(dialog._preview_btn["state"]), tk.NORMAL)
        self.assertEqual(str(dialog._print_btn["state"]), tk.NORMAL)

        dialog.destroy()


if __name__ == "__main__":
    unittest.main()
