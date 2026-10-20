"""
Unit tests for pending approvals dialog and approver manager UI components.
"""

import unittest
import os
import tempfile
import shutil
import tkinter as tk
import ttkbootstrap as ttk

import database as db
import ui.approval_dialog as approval_dialog

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
    else:
        try:
            ttk.Style.instance = ttk.Style(theme="minty-light")
        except Exception:
            pass
    return _shared_root


class TestPendingApprovalsUI(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "vouchers_test.db")
        self.attachments_dir = os.path.join(self.test_dir, "attachments")
        self.backup_dir = os.path.join(self.test_dir, "backups")

        self.orig_db_path = db.DB_PATH
        self.orig_attachments_dir = db.ATTACHMENTS_DIR
        self.orig_backup_dir = db.BACKUP_DIR

        db.DB_PATH = self.db_path
        db.ATTACHMENTS_DIR = self.attachments_dir
        db.BACKUP_DIR = self.backup_dir

        os.makedirs(self.attachments_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        db.BACKUP_DIR = self.orig_backup_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if self.root and self.root.winfo_exists():
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

    def test_pending_approvals_dialog_treeview_and_selection(self):
        # Create a voucher pending L1 approval
        vid1 = db.create_voucher({
            "date": "2026-10-15",
            "paid_to": "Approval Vendor",
            "cash_given_by": "Cashier",
            "approval_status": "pending_l1",
            "prepared_by": "John",
        }, [{"description": "Item 1", "category": "Office", "amount": 1250.0}], company_id=1)

        dlg = approval_dialog.PendingApprovalsDialog(self.root)
        try:
            items = dlg._tree.get_children()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0], str(vid1))

            # Auto-selection verification
            sel = dlg._tree.selection()
            self.assertEqual(sel, (str(vid1),))
            self.assertEqual(str(dlg._btn_review["state"]), "normal")
        finally:
            dlg.destroy()

    def test_approver_manager_dialog_treeview_and_keyboard(self):
        # Add an approver
        aid = db.add_approver("Test Manager", "1234", company_id=1, approval_level=1)

        dlg = approval_dialog.ApproverManagerDialog(self.root)
        try:
            items = dlg._tree.get_children()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0], str(aid))

            # Auto-selection verification
            sel = dlg._tree.selection()
            self.assertEqual(sel, (str(aid),))
            self.assertEqual(str(dlg._btn_toggle["state"]), "normal")
            self.assertEqual(str(dlg._btn_delete["state"]), "normal")
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
