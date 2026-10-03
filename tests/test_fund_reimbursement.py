import unittest
import os
import tempfile
import shutil
import database as db
from datetime import datetime


class TestFundReimbursement(unittest.TestCase):
    def setUp(self):
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

        self.comp_id = 1
        # Create a test money float
        self.float_id = db.create_float(
            company_id=self.comp_id,
            name="Main Petty Cash",
            opening_balance=50000.0,
            custodian="Kamal Perera",
            is_default=True
        )

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        db.ATTACHMENTS_DIR = self.orig_attachments_dir
        db.BACKUP_DIR = self.orig_backup_dir
        try:
            shutil.rmtree(self.test_dir)
        except Exception:
            pass

    def _create_voucher(self, number, amount, paid_to="Vendor A"):
        v_id = db.create_voucher(
            data={
                "voucher_number": number,
                "date": "2026-10-01",
                "paid_to": paid_to,
                "cash_given_by": "Kamal Perera",
                "spent_by": paid_to,
                "float_id": self.float_id,
                "payment_method": "Cash",
                "status": "Active",
            },
            line_items=[{"description": "Expense item", "category": "Office", "amount": amount}],
            company_id=self.comp_id
        )
        return v_id

    def test_unreimbursed_vouchers_query(self):
        v1 = self._create_voucher("PV-001", 3500.0)
        v2 = self._create_voucher("PV-002", 4500.0)

        unreimbursed = db.get_unreimbursed_vouchers(float_id=self.float_id, company_id=self.comp_id)
        self.assertEqual(len(unreimbursed), 2)
        total_spent = sum(v["total_amount"] for v in unreimbursed)
        self.assertEqual(total_spent, 8000.0)

    def test_create_fund_reimbursement(self):
        v1 = self._create_voucher("PV-001", 3500.0)
        v2 = self._create_voucher("PV-002", 4500.0)
        v3 = self._create_voucher("PV-003", 2000.0)

        # Reimburse v1 and v2 (Total: 8000)
        trans_id = db.create_fund_reimbursement(
            float_id=self.float_id,
            amount=8000.0,
            voucher_ids=[v1, v2],
            date="2026-10-02",
            source_ref="CHQ-778899",
            handed_by="Finance Manager",
            received_by="Kamal Perera",
            notes="Weekly replenishment claim #1",
            company_id=self.comp_id
        )

        self.assertIsNotNone(trans_id)

        # Check reimbursement details
        details = db.get_reimbursement_details(trans_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["transaction"]["source_ref"], "CHQ-778899")
        self.assertEqual(details["transaction"]["sub_type"], "reimbursement")
        self.assertEqual(details["total_vouchers_amount"], 8000.0)
        self.assertEqual(len(details["vouchers"]), 2)

        # Only v3 should remain unreimbursed
        unreimbursed = db.get_unreimbursed_vouchers(float_id=self.float_id, company_id=self.comp_id)
        self.assertEqual(len(unreimbursed), 1)
        self.assertEqual(unreimbursed[0]["id"], v3)

        # Check voucher records
        v1_data = db.get_voucher(v1)["voucher"]
        self.assertEqual(v1_data["is_reimbursed"], 1)
        self.assertEqual(v1_data["reimbursement_id"], trans_id)
        self.assertEqual(v1_data["reimbursed_at"], "2026-10-02")

        v3_data = db.get_voucher(v3)["voucher"]
        self.assertEqual(v3_data.get("is_reimbursed", 0), 0)

    def test_delete_reimbursement_resets_vouchers(self):
        v1 = self._create_voucher("PV-001", 3500.0)
        trans_id = db.create_fund_reimbursement(
            float_id=self.float_id,
            amount=3500.0,
            voucher_ids=[v1],
            source_ref="CHQ-001",
            company_id=self.comp_id
        )

        self.assertEqual(len(db.get_unreimbursed_vouchers(float_id=self.float_id)), 0)

        # Delete reimbursement transaction
        deleted = db.delete_float_transaction(trans_id)
        self.assertTrue(deleted)

        # v1 should now be unreimbursed again
        unreimb = db.get_unreimbursed_vouchers(float_id=self.float_id)
        self.assertEqual(len(unreimb), 1)
        self.assertEqual(unreimb[0]["id"], v1)
        v1_data = db.get_voucher(v1)["voucher"]
        self.assertEqual(v1_data["is_reimbursed"], 0)
        self.assertIsNone(v1_data["reimbursement_id"])

    def test_cash_received_transaction_sub_types(self):
        t1 = db.add_float_transaction(
            float_id=self.float_id,
            amount=15000.0,
            trans_type="Inflow",
            sub_type="cash_received",
            source_ref="Direct Cash",
            company_id=self.comp_id
        )
        t_data = db.get_float_transaction(t1)
        self.assertEqual(t_data["sub_type"], "cash_received")

        # Update transaction
        db.update_float_transaction(t1, {
            "source_ref": "Updated Cash Ref",
            "notes": "Verified receipt",
            "sub_type": "top_up"
        })
        t_updated = db.get_float_transaction(t1)
        self.assertEqual(t_updated["source_ref"], "Updated Cash Ref")
        self.assertEqual(t_updated["sub_type"], "top_up")

    def test_float_ledger_labels_and_stats(self):
        v1 = self._create_voucher("PV-001", 5000.0)
        t_reimb = db.create_fund_reimbursement(
            float_id=self.float_id,
            amount=5000.0,
            voucher_ids=[v1],
            company_id=self.comp_id
        )
        t_cash = db.add_float_transaction(
            float_id=self.float_id,
            amount=10000.0,
            trans_type="Inflow",
            sub_type="cash_received",
            company_id=self.comp_id
        )
        v2 = self._create_voucher("PV-002", 2000.0)

        entries, stats = db.get_float_ledger(self.float_id)
        self.assertEqual(stats["unreimbursed_count"], 1)
        self.assertEqual(stats["unreimbursed_total"], 2000.0)

        types_found = {e["entry_type"]: e["type_label"] for e in entries}
        self.assertIn("reimbursement", types_found)
        self.assertIn("cash_received", types_found)
        self.assertIn("🔄 Fund Reimbursement", types_found["reimbursement"])
        self.assertIn("📥 Cash Received", types_found["cash_received"])


if __name__ == "__main__":
    unittest.main()
