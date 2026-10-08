"""
tests/test_check_dialog_ui.py
Unit tests verifying CheckEntryDialog, VoucherLinkSelectorDialog, and CheckRegister UI updates:
1. CheckEntryDialog geometry, responsive sizing, and vertical action buttons.
2. VoucherLinkSelectorDialog search, filtering, and voucher previewing.
3. CheckRegisterFrame context menu and voucher preview linking.
"""

import unittest
import os
import shutil
import tempfile
import tkinter as tk
import ttkbootstrap as ttk

import database as db
from ui.check_dialog import CheckEntryDialog, VoucherLinkSelectorDialog
from ui.check_register import CheckRegisterFrame

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


class TestCheckDialogUI(unittest.TestCase):

    def setUp(self):
        self.root = get_test_root()
        if not self.root:
            self.skipTest("Tkinter display not available")

        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vouchers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        db.set_active_company_id(1)

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        if self.root and self.root.winfo_exists():
            for child in self.root.winfo_children():
                try:
                    child.destroy()
                except Exception:
                    pass

    def test_check_entry_dialog_layout_and_vertical_buttons(self):
        """Verify CheckEntryDialog initializes with responsive geometry and vertical action buttons."""
        dialog = CheckEntryDialog(self.root, company_id=1)
        dialog.update_idletasks()

        # Check title & minimum sizing
        self.assertIn("Check Payment", dialog.title())
        min_w, min_h = dialog.minsize()
        self.assertGreaterEqual(min_w, 800)
        self.assertGreaterEqual(min_h, 500)

        # Verify vertical action buttons exist
        self.assertTrue(hasattr(dialog, "btn_print"))
        self.assertTrue(hasattr(dialog, "btn_draft"))
        self.assertTrue(hasattr(dialog, "btn_preview"))

        # Verify summary card exists and updates
        self.assertTrue(hasattr(dialog, "summary_amt_lbl"))
        self.assertTrue(hasattr(dialog, "summary_payee_lbl"))
        self.assertTrue(hasattr(dialog, "summary_chk_lbl"))

        dialog.payee_var.set("Test Power Utility")
        dialog.amount_var.set("15000.00")
        dialog.chk_num_var.set("998877")
        dialog.update_idletasks()

        self.assertIn("15,000.00", dialog.summary_amt_lbl.cget("text"))
        self.assertEqual("Test Power Utility", dialog.summary_payee_lbl.cget("text"))
        self.assertEqual("#998877", dialog.summary_chk_lbl.cget("text"))

        # Verify linked voucher view button exists and defaults to disabled
        self.assertTrue(hasattr(dialog, "view_voucher_btn"))
        self.assertIn("disabled", str(dialog.view_voucher_btn.cget("state")))

        dialog.destroy()

    def test_voucher_link_selector_dialog_search_and_filters(self):
        """Verify VoucherLinkSelectorDialog filters vouchers and provides search."""
        # Create test vouchers with line items
        v1_id = db.create_voucher(
            {
                "voucher_number": "PV-2026-001",
                "date": "2026-10-01",
                "paid_to": "Colombo Electric PLC",
                "status": "Active"
            },
            [{"description": "Electricity", "category": "Utilities", "amount": 25000.0}],
            company_id=1
        )
        v2_id = db.create_voucher(
            {
                "voucher_number": "PV-2026-002",
                "date": "2026-10-02",
                "paid_to": "Water Board",
                "status": "Active"
            },
            [{"description": "Water Supply", "category": "Utilities", "amount": 4200.0}],
            company_id=1
        )

        selected = []
        def _on_select(v):
            selected.append(v)

        selector = VoucherLinkSelectorDialog(self.root, company_id=1, on_select=_on_select)
        selector.update_idletasks()

        # Both vouchers should be loaded initially
        self.assertEqual(len(selector._all_vouchers), 2)
        self.assertEqual(len(selector._filtered_vouchers), 2)

        # Verify command button bar widgets exist
        self.assertTrue(hasattr(selector, "btn_link"))
        self.assertTrue(hasattr(selector, "btn_preview"))
        self.assertTrue(hasattr(selector, "status_count_lbl"))

        # Test live search filter by payee
        selector.search_var.set("electric")
        selector.update_idletasks()
        self.assertEqual(len(selector._filtered_vouchers), 1)
        self.assertEqual(selector._filtered_vouchers[0]["id"], v1_id)

        # Test search filter by voucher number
        selector.search_var.set("2026-002")
        selector.update_idletasks()
        self.assertEqual(len(selector._filtered_vouchers), 1)
        self.assertEqual(selector._filtered_vouchers[0]["id"], v2_id)

        # Test clear search
        selector._on_clear_search()
        selector.update_idletasks()
        self.assertEqual(len(selector._filtered_vouchers), 2)

        # Select row 0 and confirm
        children = selector.tree.get_children()
        self.assertTrue(len(children) > 0)
        selector.tree.selection_set(children[0])
        selector._on_confirm_selection()

        self.assertEqual(len(selected), 1)
        selector.destroy()

    def test_check_register_context_menu_and_view_voucher(self):
        """Verify CheckRegisterFrame has context menu and handles view voucher."""
        reg = CheckRegisterFrame(self.root, company_id=1)
        reg.update_idletasks()

        self.assertTrue(hasattr(reg, "_context_menu"))
        self.assertTrue(hasattr(reg, "_on_view_linked_voucher"))
        reg.destroy()

    def test_check_entry_voucher_linking_end_to_end(self):
        """Verify CheckEntryDialog links voucher and handles callback safely without KeyError."""
        v_id = db.create_voucher(
            {
                "voucher_number": "PV-LINK-999",
                "date": "2026-10-06",
                "paid_to": "ACME Supplier Ltd",
                "status": "Active"
            },
            [{"description": "Supplies", "category": "Office", "amount": 18500.0}],
            company_id=1
        )

        dialog = CheckEntryDialog(self.root, company_id=1)
        dialog.update_idletasks()

        captured_v = []
        def _handle_selected(v):
            # Explicitly test v["id"] to verify no KeyError is raised
            vid = v["id"]
            captured_v.append(v)
            dialog.voucher_id = vid
            dialog.payee_var.set(v.get("paid_to", ""))
            dialog.amount_var.set(f"{float(v.get('total_amount', 0)):.2f}")
            dialog._update_summary()

        selector = VoucherLinkSelectorDialog(dialog, company_id=1, on_select=_handle_selected)
        selector.update_idletasks()

        # Find row corresponding to v_id
        target_item = None
        for item in selector.tree.get_children():
            if int(selector.tree.item(item)["values"][0]) == v_id:
                target_item = item
                break
        self.assertIsNotNone(target_item)
        selector.tree.selection_set(target_item)

        # Confirm selection and verify dialog is populated
        selector._on_confirm_selection()
        dialog.update_idletasks()

        self.assertEqual(len(captured_v), 1)
        self.assertEqual(captured_v[0]["id"], v_id)
        self.assertEqual(dialog.voucher_id, v_id)
        self.assertEqual(dialog.payee_var.get(), "ACME Supplier Ltd")
        self.assertEqual(float(dialog.amount_var.get()), 18500.0)
        self.assertIn("18,500.00", dialog.summary_amt_lbl.cget("text"))

        selector.destroy()
        dialog.destroy()

    def test_payee_autocomplete_dropdown_and_different_party_support(self):
        """Verify payee AutocompleteEntry, dropdown button, and different party toggle."""
        dialog = CheckEntryDialog(self.root, company_id=1)
        dialog.update_idletasks()

        # Check payee entry is AutocompleteEntry and dropdown button exists
        self.assertTrue(hasattr(dialog, "payee_entry"))
        self.assertTrue(hasattr(dialog, "btn_payee_dropdown"))
        self.assertTrue(hasattr(dialog, "diff_party_var"))
        self.assertTrue(hasattr(dialog, "diff_party_check"))

        # Trigger dropdown without errors
        dialog.payee_entry.show_dropdown()
        dialog.update_idletasks()

        # Toggle Different Party / Cash Cheque
        self.assertFalse(dialog.diff_party_var.get())
        dialog.diff_party_var.set(True)
        dialog._on_diff_party_toggled()
        self.assertIn("Different Payee", dialog.diff_party_hint.cget("text"))

        dialog.diff_party_var.set(False)
        dialog._on_diff_party_toggled()
        self.assertEqual("", dialog.diff_party_hint.cget("text"))

        dialog.destroy()

    def test_voucher_link_selector_payee_scoping_and_override(self):
        """Verify VoucherLinkSelectorDialog scopes to specified payee and toggles show all."""
        v1 = db.create_voucher(
            {"voucher_number": "PV-SCOPE-1", "date": "2026-10-06", "paid_to": "Southern Mills", "status": "Active"},
            [{"description": "Item 1", "amount": 12000.0}],
            company_id=1
        )
        v2 = db.create_voucher(
            {"voucher_number": "PV-SCOPE-2", "date": "2026-10-06", "paid_to": "Apex Suppliers", "status": "Active"},
            [{"description": "Item 2", "amount": 25000.0}],
            company_id=1
        )

        # 1. Scoped to Southern Mills
        selector = VoucherLinkSelectorDialog(self.root, company_id=1, payee_filter="Southern Mills")
        selector.update_idletasks()

        # Should show only Southern Mills (1 voucher)
        visible_ids = [int(selector.tree.item(i)["values"][0]) for i in selector.tree.get_children()]
        self.assertIn(v1, visible_ids)
        self.assertNotIn(v2, visible_ids)

        # 2. Toggle "Show all payees / Different Party"
        selector.show_all_payees_var.set(True)
        selector._on_scope_toggled()
        selector.update_idletasks()

        visible_ids_all = [int(selector.tree.item(i)["values"][0]) for i in selector.tree.get_children()]
        self.assertIn(v1, visible_ids_all)
        self.assertIn(v2, visible_ids_all)

        selector.destroy()


if __name__ == "__main__":
    unittest.main()
