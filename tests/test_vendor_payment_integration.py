"""Integration tests for Pay Bills payment vouchers and Write Cheques."""

import os
import shutil
import tempfile
import unittest

import database as db
import vendor_payments as vp


class TestVendorPaymentIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.test_dir, "vendor_payment.db")
        db.init_db()
        self.connection = db.get_connection()
        self.supplier_id = db.create_supplier(
            {
                "company_id": 1,
                "name": "Linked Vendor",
                "payment_terms": 30,
                "currency": "LKR",
            },
            conn=self.connection,
        )
        self.payment_account = db.get_account_by_code(
            "1120", company_id=1, conn=self.connection
        )

    def tearDown(self):
        self.connection.close()
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _bill(self, number, amount):
        expense = db.get_account_by_code(
            "5410", company_id=1, conn=self.connection
        )
        return db.create_ap_invoice(
            {
                "company_id": 1,
                "supplier_id": self.supplier_id,
                "invoice_number": number,
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
                "currency": "LKR",
            },
            [
                {
                    "description": "Supplies",
                    "account_id": expense["id"],
                    "quantity": 1,
                    "unit_price": amount,
                    "line_total": amount,
                }
            ],
            conn=self.connection,
        )

    def _payment_data(self, **overrides):
        data = {
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "payment_date": "2026-10-15",
            "payment_method": "Bank Transfer",
            "payment_account_id": self.payment_account["id"],
            "reference": "BANK-100",
            "currency": "LKR",
            "exchange_rate": 1,
        }
        data.update(overrides)
        return data

    def test_pay_bills_creates_one_nonposting_payment_voucher(self):
        first = self._bill("BILL-001", 1200)
        second = self._bill("BILL-002", 800)

        batch_id = vp.pay_bills(
            self._payment_data(),
            [
                {"invoice_id": first, "cash_amount": 1200, "credit_amount": 0},
                {"invoice_id": second, "cash_amount": 800, "credit_amount": 0},
            ],
        )

        batch = vp.get_payment_batch(batch_id)
        self.assertIsNotNone(batch["voucher_id"])
        voucher = db.get_voucher(
            batch["voucher_id"], conn=self.connection
        )
        self.assertEqual(
            voucher["voucher"]["source_module"], "ap_payment_batch"
        )
        self.assertEqual(voucher["voucher"]["source_id"], batch_id)
        self.assertEqual(voucher["voucher"]["total_amount"], 2000)
        self.assertEqual(len(voucher["line_items"]), 2)

        payments = self.connection.execute(
            "SELECT * FROM ap_payments WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        self.assertEqual(len(payments), 2)
        self.assertTrue(
            all(row["voucher_id"] == batch["voucher_id"] for row in payments)
        )
        dedicated = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='ap_payment_batch' AND source_id=?",
            (batch_id,),
        ).fetchone()[0]
        duplicate = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='voucher' AND source_id=?",
            (batch["voucher_id"],),
        ).fetchone()[0]
        self.assertEqual(dedicated, 1)
        self.assertEqual(duplicate, 0)

    def test_cheque_payment_creates_linked_write_cheques_record(self):
        bill_id = self._bill("BILL-CHQ", 3500)
        bank_id = self.connection.execute(
            """
            INSERT INTO bank_accounts(
                company_id, account_name, account_number, bank_name, currency
            ) VALUES(1, 'Main Bank', '001-100', 'Test Bank', 'LKR')
            """
        ).lastrowid
        template_id = self.connection.execute(
            """
            INSERT INTO bank_check_templates(
                company_id, bank_name, account_id, account_number
            ) VALUES(1, 'Test Bank', ?, '001-100')
            """,
            (bank_id,),
        ).lastrowid
        self.connection.commit()

        batch_id = vp.pay_bills(
            self._payment_data(
                payment_method="Cheque",
                check_number="CHQ-9001",
                check_template_id=template_id,
                reference="PAY-CHQ",
            ),
            [
                {
                    "invoice_id": bill_id,
                    "cash_amount": 3500,
                    "credit_amount": 0,
                }
            ],
        )

        batch = vp.get_payment_batch(batch_id)
        self.assertIsNotNone(batch["voucher_id"])
        self.assertIsNotNone(batch["check_id"])
        check = db.get_check_by_id(
            batch["check_id"], conn=self.connection
        )
        self.assertEqual(check["check_number"], "CHQ-9001")
        self.assertEqual(check["voucher_id"], batch["voucher_id"])
        self.assertEqual(check["payee_name"], "Linked Vendor")
        payment = self.connection.execute(
            "SELECT * FROM ap_payments WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        self.assertEqual(payment["voucher_id"], batch["voucher_id"])
        self.assertEqual(payment["check_id"], batch["check_id"])

    def test_print_later_keeps_voucher_without_allocating_cheque(self):
        bill_id = self._bill("BILL-LATER", 900)
        batch_id = vp.pay_bills(
            self._payment_data(
                payment_method="Cheque",
                check_number="",
                print_later=True,
            ),
            [
                {
                    "invoice_id": bill_id,
                    "cash_amount": 900,
                    "credit_amount": 0,
                }
            ],
        )
        batch = vp.get_payment_batch(batch_id)
        self.assertIsNotNone(batch["voucher_id"])
        self.assertIsNone(batch["check_id"])
        voucher = db.get_voucher(
            batch["voucher_id"], conn=self.connection
        )["voucher"]
        self.assertEqual(voucher["payment_method"], "Cheque")
        self.assertIsNone(voucher.get("check_id"))


if __name__ == "__main__":
    unittest.main()
