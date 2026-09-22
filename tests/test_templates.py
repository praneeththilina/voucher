"""
Unit tests for recurring voucher templates in database.py
"""

import unittest
import os
import tempfile
import database as db


class TestVoucherTemplates(unittest.TestCase):

    def setUp(self):
        # Setup temporary database file
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_template_crud(self):
        # 1. Test create_template
        t_data = {
            "template_name": "Monthly Office Electricity",
            "paid_to": "Ceylon Electricity Board",
            "cash_given_by": "John Doe",
            "spent_by": "John Doe",
            "prepared_by": "Alice",
            "approved_by": "Bob",
            "payment_method": "Bank Transfer",
            "bill_status": "Received",
        }
        line_items = [
            {"description": "Electricity Bill - Main Office", "category": "Utilities", "amount": 15000.0},
            {"description": "Late Fee Surcharge", "category": "Utilities", "amount": 250.0},
        ]

        t_id = db.create_template(t_data, line_items, company_id=1)
        self.assertIsNotNone(t_id)

        # 2. Test get_templates
        templates = db.get_templates(company_id=1)
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["template_name"], "Monthly Office Electricity")

        # 3. Test get_template
        full_t = db.get_template(t_id)
        self.assertIsNotNone(full_t)
        self.assertEqual(full_t["template"]["paid_to"], "Ceylon Electricity Board")
        self.assertEqual(len(full_t["line_items"]), 2)
        self.assertEqual(full_t["line_items"][0]["amount"], 15000.0)

        # 4. Test update_template
        updated_data = {
            "template_name": "Monthly Office Electricity (Updated)",
            "paid_to": "Ceylon Electricity Board",
            "cash_given_by": "Jane Doe",
            "spent_by": "Jane Doe",
            "prepared_by": "Alice",
            "approved_by": "Bob",
            "payment_method": "Bank Transfer",
            "bill_status": "Received",
        }
        updated_line_items = [
            {"description": "Electricity Bill - Main Office", "category": "Utilities", "amount": 16500.0},
        ]
        res = db.update_template(t_id, updated_data, updated_line_items)
        self.assertTrue(res)

        full_t_updated = db.get_template(t_id)
        self.assertEqual(full_t_updated["template"]["template_name"], "Monthly Office Electricity (Updated)")
        self.assertEqual(len(full_t_updated["line_items"]), 1)
        self.assertEqual(full_t_updated["line_items"][0]["amount"], 16500.0)

        # 5. Test create voucher from template data
        v_data = {
            "date": "2026-09-20",
            "paid_to": full_t_updated["template"]["paid_to"],
            "cash_given_by": full_t_updated["template"]["cash_given_by"],
            "spent_by": full_t_updated["template"]["spent_by"],
            "prepared_by": full_t_updated["template"]["prepared_by"],
            "approved_by": full_t_updated["template"]["approved_by"],
            "payment_method": full_t_updated["template"]["payment_method"],
            "bill_status": full_t_updated["template"]["bill_status"],
        }
        v_id = db.create_voucher(v_data, full_t_updated["line_items"], company_id=1)
        self.assertIsNotNone(v_id)

        v_saved = db.get_voucher(v_id)
        self.assertEqual(v_saved["voucher"]["paid_to"], "Ceylon Electricity Board")
        self.assertEqual(v_saved["voucher"]["total_amount"], 16500.0)

        # 6. Test delete_template
        del_res = db.delete_template(t_id)
        self.assertTrue(del_res)
        self.assertIsNone(db.get_template(t_id))
        self.assertEqual(len(db.get_templates(company_id=1)), 0)


if __name__ == "__main__":
    unittest.main()
