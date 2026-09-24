import unittest
import tkinter as tk
import ttkbootstrap as ttk
from ui.widgets import LineItemFrame


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
        if cls.root:
            cls.root.destroy()

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


if __name__ == "__main__":
    unittest.main()
