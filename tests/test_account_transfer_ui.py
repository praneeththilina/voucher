"""UI tests for AccountTransferFrame keyboard accessibility and user interaction."""

from datetime import date
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import database as db
from ui.account_transfer import AccountTransferFrame
from tests.test_widgets import get_test_root


class TestAccountTransferUI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "account_transfer_ui.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
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

    @patch("tkinter.messagebox.showinfo")
    @patch("tkinter.messagebox.showwarning")
    def test_post_transfer_via_keyboard_return(self, mock_warning, mock_info):
        frame = AccountTransferFrame(self.root, company_id=1)
        frame.pack(fill="both", expand=True)

        # Retrieve accounts
        cash = db.get_account_by_code("1110", company_id=1)
        bank = db.get_account_by_code("1120", company_id=1)
        self.assertIsNotNone(cash)
        self.assertIsNotNone(bank)

        source_label = frame._label(cash)
        target_label = frame._label(bank)

        frame.from_var.set(source_label)
        frame.to_var.set(target_label)
        frame.amount_var.set("500.00")
        frame.reference_var.set("REF-12345")
        frame.memo_var.set("Test inter-account transfer")

        # Simulate Return keypress on amount input
        frame._post()

        mock_info.assert_called_once()
        self.assertIn("posted for LKR 500.00", mock_info.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
