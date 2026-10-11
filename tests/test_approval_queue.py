"""
Unit and GUI tests for Pending Approvals Queue and CSV Export.
"""

import unittest
import os
import tempfile
import csv
import tkinter as tk
import ttkbootstrap as ttk
import database as db


class TestApprovalQueue(unittest.TestCase):
    """Test get_pending_approvals and export_pending_approvals_to_csv."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "approval_queue_test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir

    def test_get_and_export_pending_approvals(self):
        """Test fetching pending approvals and exporting to CSV with formula injection sanitization."""
        # Create vouchers
        v1_id = db.create_voucher({
            "paid_to": "=1+1 Payee",
            "cash_given_by": "Tester",
            "total_amount": 1500.0,
            "prepared_by": "Clerk 1"
        }, [{"description": "Office Chair", "amount": 1500.0}])

        v2_id = db.create_voucher({
            "paid_to": "ACME Corp",
            "cash_given_by": "Tester",
            "total_amount": 60000.0,
            "prepared_by": "Clerk 2"
        }, [{"description": "Server Rack", "amount": 60000.0}])

        # Set approval statuses
        db.submit_voucher_for_approval(v1_id)
        db.submit_voucher_for_approval(v2_id)

        pending = db.get_pending_approvals()
        self.assertEqual(len(pending), 2)
        v_ids = [p["id"] for p in pending]
        self.assertIn(v1_id, v_ids)
        self.assertIn(v2_id, v_ids)

        csv_path = os.path.join(self.test_dir, "pending_approvals.csv")
        res = db.export_pending_approvals_to_csv(csv_path)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(csv_path))

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = list(csv.reader(f))

        # Check sanitization for formula injection payee "=1+1 Payee" -> "'=1+1 Payee"
        flat_cells = [cell for row in reader for cell in row]
        self.assertIn("'=1+1 Payee", flat_cells)
        self.assertIn("Server Rack", flat_cells)
        self.assertIn("SUMMARY", flat_cells)


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
            ttk.Style(theme="minty-light")
        except Exception:
            _shared_root = None
    return _shared_root


class TestPendingApprovalsDialogUI(unittest.TestCase):
    """GUI tests for PendingApprovalsDialog."""

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "approval_queue_ui_test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir

    def test_pending_approvals_dialog_population_and_selection(self):
        """Test dialog populates pending vouchers and sets row selection."""
        v_id = db.create_voucher({
            "paid_to": "Supplier X",
            "cash_given_by": "Admin",
            "total_amount": 2000.0,
        }, [{"description": "Hardware", "amount": 2000.0}])
        db.submit_voucher_for_approval(v_id)

        from ui.approval_dialog import PendingApprovalsDialog
        dlg = PendingApprovalsDialog(self.root)
        try:
            sel = dlg._tree.selection()
            self.assertTrue(len(sel) > 0)
            self.assertEqual(sel[0], str(v_id))
            self.assertEqual(str(dlg._review_btn["state"]), tk.NORMAL)
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
