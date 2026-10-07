"""
tests/test_check_integration.py
End-to-End integration tests for Check Printing Feature (v3.0).

Tests:
1. MainWindow Tab 5 (Check Register) presence and switching.
2. Check action buttons and form controls integration.
3. Bank reconciliation Pass 0 matching via check number.
4. Reconciliation confirmation auto-clearing linked check.
5. Smart alerts for due/post-dated checks.
6. Firebase cloud serialization of checks and templates.
"""

import unittest
import os
import shutil
import tempfile
import tkinter as tk
from datetime import datetime, date, timedelta

import database as db
import firebase_client


class TestCheckIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_vouchers.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        db.set_active_company_id(1)

        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        db.DB_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_main_window_check_tab_and_shortcuts(self):
        """Verify Check Register Tab 5 is present in MainWindow."""
        from ui.main_window import MainWindow
        app = MainWindow(self.root)
        app._ensure_check_register()
        app._ensure_form_tab()

        # Tab count should be 5
        self.assertEqual(app._notebook.index("end"), 5)

        # Tab text should identify Check Register
        tab_text = app._notebook.tab(4, "text")
        self.assertIn("Check Register", tab_text)

        # Frame instance check
        self.assertTrue(hasattr(app, "_check_register"))
        self.assertEqual(app._check_register.company_id, db.get_active_company_id())

        # Check action button in list tab
        self.assertIn("print_check", app._action_buttons)

        # Check issue button in form tab
        self.assertTrue(hasattr(app, "_issue_check_form_btn"))

        # Test company switch updates check register
        new_comp_id = db.create_company("Second Enterprise Ltd")
        app._switch_to_company(new_comp_id)
        self.assertEqual(app._check_register.company_id, new_comp_id)

    def test_bank_reconciliation_pass_0_and_auto_clear(self):
        """Verify bank transaction auto-matches check number and marks check Cleared upon confirmation."""
        comp_id = 1

        # 1. Create a voucher
        v_data = {
            "voucher_number": "PV-CHK-001",
            "date": "2026-10-05",
            "paid_to": "Apex Suppliers",
            "cash_given_by": "Finance Dept",
            "payment_method": "Cheque",
            "status": "Active"
        }
        items = [{"description": "Office Supplies", "category": "Office", "amount": 25000.0}]
        vid = db.create_voucher(v_data, items, company_id=comp_id)

        # 2. Issue a check linked to this voucher
        templates = db.get_check_templates(company_id=comp_id)
        self.assertTrue(len(templates) > 0)
        tid = templates[0]["id"]

        chk_data = {
            "company_id": comp_id,
            "voucher_id": vid,
            "template_id": tid,
            "check_number": "009812",
            "check_series": 1,
            "payee_name": "Apex Suppliers",
            "amount": 25000.0,
            "amount_words": "Twenty Five Thousand Rupees Only",
            "check_date": "2026-10-05",
            "issued_date": "2026-10-05",
            "status": "Issued"
        }
        cid = db.create_check(chk_data)
        db.link_voucher_to_check(vid, cid)

        # 3. Create bank account and bank transaction
        acct_id = db.create_bank_account(comp_id, "Commercial Main", "1002345678", "Commercial Bank", "LKR")
        conn = db.get_connection()
        cur = conn.execute("""
            INSERT INTO bank_transactions (
                bank_account_id, transaction_date, reference, description,
                debit_amount, credit_amount
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (acct_id, "2026-10-06", "CHQ 009812", "Cheque clearance Apex Suppliers", 25000.0, 0.0))
        txn_id = cur.lastrowid
        conn.commit()
        conn.close()

        # 4. Run auto_match_bank_transactions
        matches = db.auto_match_bank_transactions(acct_id, company_id=comp_id)
        self.assertEqual(len(matches), 1)
        matched_txn_id, matched_vid, confidence = matches[0]
        self.assertEqual(matched_txn_id, txn_id)
        self.assertEqual(matched_vid, vid)
        self.assertAlmostEqual(confidence, 0.98, places=2)

        # 5. Confirm reconciliation
        ok = db.confirm_reconciliation(txn_id, voucher_id=vid, reconciled_by="Auditor Jane")
        self.assertTrue(ok)

        # 6. Check that linked check status is now Cleared!
        chk = db.get_check_by_id(cid)
        self.assertEqual(chk["status"], "Cleared")
        self.assertTrue(len(chk["cleared_date"]) > 0)

        # Audit trail should reflect cleared state
        trail = db.get_check_audit_trail(cid)
        reconciled_logs = [l for l in trail if l["new_status"] == "Cleared"]
        self.assertTrue(len(reconciled_logs) > 0)

    def test_smart_alerts_for_due_checks(self):
        """Verify post-dated / due check triggers automated warning alert."""
        comp_id = 1
        templates = db.get_check_templates(company_id=comp_id)
        self.assertTrue(len(templates) > 0)
        tid = templates[0]["id"]
        today_str = date.today().strftime("%Y-%m-%d")

        # Create check due today
        chk_data = {
            "company_id": comp_id,
            "template_id": tid,
            "check_number": "777888",
            "check_series": 1,
            "payee_name": "Southern Mills",
            "amount": 18500.0,
            "amount_words": "Eighteen Thousand Five Hundred Rupees Only",
            "check_date": today_str,
            "issued_date": today_str,
            "status": "Issued"
        }
        cid = db.create_check(chk_data)

        alerts = db.generate_alerts(company_id=comp_id)
        check_alerts = [a for a in alerts if a["alert_type"] == "check_due" and a["reference_id"] == cid]
        self.assertEqual(len(check_alerts), 1)
        self.assertEqual(check_alerts[0]["severity"], "warning")
        self.assertIn("777888", check_alerts[0]["title"])
        self.assertIn("Southern Mills", check_alerts[0]["message"])

    def test_cloud_serialization_checks_and_templates(self):
        """Verify Firebase Firestore serializer formats check models cleanly."""
        comp_id = 1
        templates = db.get_check_templates(company_id=comp_id)
        self.assertTrue(len(templates) > 0)
        tid = templates[0]["id"]

        # 1. Template serialization
        t_doc = firebase_client.serialize_check_template(tid)
        self.assertIsNotNone(t_doc)
        self.assertIn("_doc_id", t_doc)
        self.assertEqual(t_doc["id"], tid)
        self.assertIn("bank_name", t_doc)
        self.assertEqual(t_doc["_app_version"], "3.0")

        # 2. Check serialization
        chk_data = {
            "company_id": comp_id,
            "template_id": tid,
            "check_number": "555123",
            "check_series": 1,
            "payee_name": "Lanka Electricity Co",
            "amount": 42150.0,
            "amount_words": "Forty Two Thousand One Hundred Fifty Rupees Only",
            "check_date": "2026-10-10",
            "issued_date": "2026-10-05",
            "status": "Post-Dated",
            "post_date": "2026-10-10"
        }
        cid = db.create_check(chk_data)
        c_doc = firebase_client.serialize_check(cid)
        self.assertIsNotNone(c_doc)
        self.assertEqual(c_doc["_doc_id"], f"check_comp_{comp_id}_555123")
        self.assertEqual(c_doc["check_number"], "555123")
        self.assertEqual(c_doc["amount"], 42150.0)
        self.assertEqual(c_doc["status"], "Post-Dated")
        self.assertEqual(c_doc["is_post_dated"], 1)


if __name__ == "__main__":
    unittest.main()
