"""
Unit and integration tests for Voucher Tags and Expense Labels System.
"""

import unittest
import os
import tempfile
import tkinter as tk
import ttkbootstrap as ttk
import database as db


class TestVoucherTags(unittest.TestCase):
    """Test tag CRUD operations, database schema migration, voucher associations, search filtering, and CSV export."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "vouchers_test.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir

    def test_default_tags_seeded(self):
        """Test that migration 9 seeds default tags."""
        tags = db.get_tags()
        tag_names = [t["name"] for t in tags]
        self.assertIn("Tax Deductible", tag_names)
        self.assertIn("Urgent", tag_names)
        self.assertIn("Reimbursable", tag_names)
        self.assertIn("Billable", tag_names)

    def test_add_and_get_tags(self):
        """Test adding new tags and retrieving full details."""
        tag_id = db.add_tag("Project Alpha", color="#10b981")
        self.assertIsNotNone(tag_id)

        # Adding duplicate tag returns existing ID
        dup_id = db.add_tag("Project Alpha", color="#10b981")
        self.assertEqual(tag_id, dup_id)

        all_tags = db.get_all_tags_full()
        tag_dict = next((t for t in all_tags if t["id"] == tag_id), None)
        self.assertIsNotNone(tag_dict)
        self.assertEqual(tag_dict["name"], "Project Alpha")
        self.assertEqual(tag_dict["color"], "#10b981")

    def test_update_and_delete_tag(self):
        """Test updating tag name/color and deleting tags."""
        tag_id = db.add_tag("Temp Tag", color="#000000")
        ok = db.update_tag(tag_id, "Renamed Tag", color="#ffffff")
        self.assertTrue(ok)

        tags = db.get_tags()
        names = [t["name"] for t in tags]
        self.assertIn("Renamed Tag", names)

        del_ok = db.delete_tag(tag_id)
        self.assertTrue(del_ok)

        tags_after = db.get_tags()
        names_after = [t["name"] for t in tags_after]
        self.assertNotIn("Renamed Tag", names_after)

    def test_voucher_tag_association_create_and_get(self):
        """Test creating a voucher with tags and fetching them."""
        data = {
            "paid_to": "ACME Supplies",
            "cash_given_by": "John Doe",
            "tags": ["Tax Deductible", "Urgent"]
        }
        line_items = [{"description": "Paper", "amount": 100.0}]
        v_id = db.create_voucher(data, line_items)

        vdata = db.get_voucher(v_id)
        v_tags = vdata.get("tags", [])
        tag_names = [t["name"] for t in v_tags]
        self.assertIn("Tax Deductible", tag_names)
        self.assertIn("Urgent", tag_names)

        # Test batch fetch
        batch_full = db.get_vouchers_full_by_ids([v_id])
        self.assertEqual(len(batch_full), 1)
        batch_tags = [t["name"] for t in batch_full[0]["tags"]]
        self.assertIn("Tax Deductible", batch_tags)

    def test_update_voucher_tags(self):
        """Test updating a voucher's tag associations."""
        data = {
            "paid_to": "Hardware Store",
            "cash_given_by": "Jane",
            "tags": ["CapEx"]
        }
        line_items = [{"description": "Tools", "amount": 250.0}]
        v_id = db.create_voucher(data, line_items)

        # Update tags
        data["tags"] = ["OpEx", "Reimbursable"]
        db.update_voucher(v_id, data, line_items)

        vdata = db.get_voucher(v_id)
        tag_names = [t["name"] for t in vdata.get("tags", [])]
        self.assertIn("OpEx", tag_names)
        self.assertIn("Reimbursable", tag_names)
        self.assertNotIn("CapEx", tag_names)

    def test_duplicate_voucher_copies_tags(self):
        """Test that duplicating a voucher copies its tag associations."""
        data = {
            "paid_to": "Software Co",
            "cash_given_by": "Admin",
            "tags": ["Billable", "Urgent"]
        }
        line_items = [{"description": "SaaS Subscription", "amount": 500.0}]
        src_id = db.create_voucher(data, line_items)

        new_id = db.duplicate_voucher(src_id)
        self.assertIsNotNone(new_id)

        dup_vdata = db.get_voucher(new_id)
        dup_tag_names = [t["name"] for t in dup_vdata.get("tags", [])]
        self.assertIn("Billable", dup_tag_names)
        self.assertIn("Urgent", dup_tag_names)

    def test_search_vouchers_by_tag(self):
        """Test filtering vouchers by tag in search_vouchers."""
        v1 = db.create_voucher(
            {"paid_to": "Vendor A", "cash_given_by": "Alice", "tags": ["Tax Deductible"]},
            [{"description": "Item 1", "amount": 50.0}]
        )
        v2 = db.create_voucher(
            {"paid_to": "Vendor B", "cash_given_by": "Bob", "tags": ["CapEx"]},
            [{"description": "Item 2", "amount": 500.0}]
        )

        res_tax = db.search_vouchers(tag_filter="Tax Deductible")
        tax_ids = [v["id"] for v in res_tax]
        self.assertIn(v1, tax_ids)
        self.assertNotIn(v2, tax_ids)

        res_capex = db.search_vouchers(tag_filter="CapEx")
        capex_ids = [v["id"] for v in res_capex]
        self.assertIn(v2, capex_ids)
        self.assertNotIn(v1, capex_ids)

        # Test query text matching tag name
        res_query = db.search_vouchers(query="Tax Deductible")
        q_ids = [v["id"] for v in res_query]
        self.assertIn(v1, q_ids)

    def test_export_vouchers_to_csv_with_tags(self):
        """Test CSV export includes the Tags column."""
        v_id = db.create_voucher(
            {"paid_to": "Print Shop", "cash_given_by": "Eve", "tags": ["Tax Deductible", "Urgent"]},
            [{"description": "Flyers", "amount": 75.0}]
        )
        vdata = db.get_voucher(v_id)
        vouchers = [vdata]

        csv_path = os.path.join(self.test_dir, "vouchers_test_export.csv")
        db.export_vouchers_to_csv(vouchers, csv_path, format_type="itemized")

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        self.assertIn("Tags", content)
        self.assertIn("Tax Deductible", content)


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


class TestTagManagerDialogUI(unittest.TestCase):
    """GUI tests for TagManagerDialog auto-selection and button states."""

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.old_db_path = db.DB_PATH
        self.old_db_dir = db.DB_DIR
        db.DB_DIR = self.test_dir
        db.DB_PATH = os.path.join(self.test_dir, "vouchers_test_tags_ui.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        db.DB_DIR = self.old_db_dir

    def test_tag_manager_dialog_autoselects_first_row(self):
        """Test that TagManagerDialog auto-selects the first row and enables action buttons on open."""
        import tkinter as tk
        from ui.tag_manager import TagManagerDialog
        dlg = TagManagerDialog(self.root)
        try:
            selection = dlg._tree.selection()
            self.assertTrue(len(selection) > 0)
            self.assertEqual(str(dlg._edit_btn["state"]), tk.NORMAL)
            self.assertEqual(str(dlg._del_btn["state"]), tk.NORMAL)
        finally:
            dlg.destroy()


if __name__ == "__main__":
    unittest.main()
