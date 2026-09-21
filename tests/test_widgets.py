import unittest
import os
import ttkbootstrap as ttk
from ui.widgets import LineItemFrame


class TestWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get("DISPLAY"):
            cls.skipTest(cls, "No DISPLAY available for GUI tests")

    def setUp(self):
        self.root = ttk.Window()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_line_item_frame_tooltips_and_rows(self):
        frame = LineItemFrame(self.root)
        frame.pack()
        self.root.update()

        # Check initial row
        self.assertEqual(len(frame._rows), 1)

        # Add a row
        frame.add_row(description="Office Supplies", category="Stationery", amount="150.00")
        self.assertEqual(len(frame._rows), 2)

        # Check total
        self.assertIn("150.00", frame._total_var.get())

        # Check items
        items = frame.get_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["description"], "Office Supplies")
        self.assertEqual(items[0]["category"], "Stationery")
        self.assertEqual(items[0]["amount"], 150.0)


if __name__ == "__main__":
    unittest.main()
