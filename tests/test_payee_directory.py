"""
Unit tests for the Payee Directory & Default Category Auto-Fill features.
Tests schema migration 11, payee CRUD with contact details, default category lookup,
and voucher form auto-fill behavior.
"""

import os
import unittest
import tempfile
import tkinter as tk
import ttkbootstrap as ttk

import database as db
from ui.name_manager import NameManagerDialog, _PersonEditorDialog
from ui.main_window import MainWindow
from tests.test_widgets import get_test_root


class TestPayeeDirectory(unittest.TestCase):

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

    def tearDown(self):
        """Restore original database paths."""
        db.DB_PATH = self._orig_db_path
        db.ATTACHMENTS_DIR = self._orig_attachments_dir
        db.BACKUP_DIR = self._orig_backup_dir

    def test_add_and_get_person_with_details(self):
        """Test adding a payee with contact info and default expense category."""
        pid = db.add_person(
            name="Electricity Board",
            phone="011-2345678",
            email="billing@ceb.lk",
            tax_id="CEB-9988",
            default_category="Utilities",
            notes="Monthly power bill"
        )
        self.assertIsNotNone(pid)

        person = db.get_person_by_name("Electricity Board")
        self.assertIsNotNone(person)
        self.assertEqual(person["id"], pid)
        self.assertEqual(person["name"], "Electricity Board")
        self.assertEqual(person["phone"], "011-2345678")
        self.assertEqual(person["email"], "billing@ceb.lk")
        self.assertEqual(person["tax_id"], "CEB-9988")
        self.assertEqual(person["default_category"], "Utilities")
        self.assertEqual(person["notes"], "Monthly power bill")

    def test_case_insensitive_get_person_by_name(self):
        """Test case-insensitive payee lookup by name."""
        db.add_person("Stat Station", default_category="Office Supplies")

        p1 = db.get_person_by_name("stat station")
        self.assertIsNotNone(p1)
        self.assertEqual(p1["default_category"], "Office Supplies")

        p2 = db.get_person_by_name("   STAT STATION  ")
        self.assertIsNotNone(p2)
        self.assertEqual(p2["default_category"], "Office Supplies")

    def test_update_person_details(self):
        """Test updating payee contact information and default category."""
        pid = db.add_person("Vendor Alpha")
        self.assertIsNotNone(pid)

        ok = db.update_person(
            person_id=pid,
            new_name="Vendor Alpha Ltd",
            phone="077-1234567",
            email="info@alphavendor.com",
            tax_id="TIN-776655",
            default_category="Raw Materials",
            notes="Primary supplier"
        )
        self.assertTrue(ok)

        person = db.get_person_by_name("Vendor Alpha Ltd")
        self.assertIsNotNone(person)
        self.assertEqual(person["phone"], "077-1234567")
        self.assertEqual(person["default_category"], "Raw Materials")

    def test_get_all_people_full(self):
        """Test get_all_people_full returns all payee fields."""
        db.add_person("Payee One", default_category="Category A", phone="111")
        db.add_person("Payee Two", default_category="Category B", phone="222")

        all_people = db.get_all_people_full()
        self.assertGreaterEqual(len(all_people), 2)
        p1 = next((p for p in all_people if p["name"] == "Payee One"), None)
        self.assertIsNotNone(p1)
        self.assertEqual(p1["default_category"], "Category A")
        self.assertEqual(p1["phone"], "111")

    def test_payee_auto_fill_in_main_window(self):
        """Test payee default category auto-fill behavior in MainWindow."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        # Setup category and payee with default category
        db.add_category("Utilities")
        db.add_person("CEB Power", default_category="Utilities")

        app = MainWindow(root)
        app._clear_form()

        # Enter payee name in Paid To field
        app._paid_to.delete(0, tk.END)
        app._paid_to.insert(0, "CEB Power")

        # Trigger _on_payee_changed
        app._on_payee_changed()

        self.assertGreaterEqual(len(app._line_items._rows), 1)
        first_cat = app._line_items._rows[0]["category"].get()
        self.assertEqual(first_cat, "Utilities")

    def test_export_people_to_csv(self):
        """Test export_people_to_csv exports directory correctly with CSV formula sanitization."""
        import csv

        db.add_person(
            name="Formula Payee",
            phone="011-1234567",
            email="test@formula.com",
            tax_id="=1+1",
            default_category="Consulting",
            notes="DDE test"
        )
        db.add_person(
            name="Normal Payee",
            phone="011-7654321",
            email="normal@test.com",
            tax_id="TAX-123",
            default_category="Supplies",
            notes="Normal payee"
        )

        csv_path = os.path.join(self.temp_dir, "payee_directory_export.csv")
        db.export_people_to_csv(csv_path)

        self.assertTrue(os.path.exists(csv_path))

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))

        self.assertGreaterEqual(len(reader), 2)
        formula_row = next((r for r in reader if r["Person / Payee Name"] == "Formula Payee"), None)
        self.assertIsNotNone(formula_row)
        self.assertEqual(formula_row["Default Category"], "Consulting")
        # Formula trigger '=' should be sanitized to "'=1+1"
        self.assertEqual(formula_row["Tax ID / Reg No"], "'=1+1")

    def test_name_manager_dialog_ui(self):
        """Test NameManagerDialog GUI and _PersonEditorDialog."""
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        db.add_person("Test Vendor", default_category="Services", phone="555")

        dlg = NameManagerDialog(root)
        dlg.update()

        children = dlg._tree.get_children()
        self.assertGreaterEqual(len(children), 1)

        # Select first item and open editor
        dlg._tree.selection_set(children[0])
        dlg.update()

        self.assertEqual(str(dlg._edit_btn["state"]), str(tk.NORMAL))

        # Check export button exists
        self.assertTrue(hasattr(dlg, "_export_btn"))

        dlg.destroy()


if __name__ == "__main__":
    unittest.main()
