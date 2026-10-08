"""Professional accounting integrity and close-control regression tests."""

import os
import tempfile
import unittest

import database as db


class TestAccountingControls(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    @staticmethod
    def voucher_data(transaction_date="2026-02-01", **overrides):
        data = {
            "date": transaction_date,
            "paid_to": "Professional Supplier",
            "cash_given_by": "Cashier",
            "payment_method": "Cash",
            "currency": "LKR",
            "exchange_rate": 1.0,
        }
        data.update(overrides)
        return data

    @staticmethod
    def lines(amount=100.0):
        return [{
            "description": "Office supplies",
            "category": "Office Supplies",
            "amount": amount,
        }]

    def test_closed_period_blocks_financial_mutations(self):
        voucher_id = db.create_voucher(
            self.voucher_data("2026-01-15"), self.lines(), company_id=1
        )
        db.lock_accounting_period(
            "2026-01-31", company_id=1, locked_by="Admin", reason="Month closed"
        )

        with self.assertRaisesRegex(ValueError, "closed through 2026-01-31"):
            db.create_voucher(
                self.voucher_data("2026-01-31"), self.lines(), company_id=1
            )
        with self.assertRaisesRegex(ValueError, "closed through 2026-01-31"):
            db.update_voucher(
                voucher_id, self.voucher_data("2026-01-15"), self.lines(125.0)
            )
        with self.assertRaisesRegex(ValueError, "closed through 2026-01-31"):
            db.cancel_voucher(voucher_id)

        open_period_id = db.create_voucher(
            self.voucher_data("2026-02-01"), self.lines(), company_id=1
        )
        self.assertIsInstance(open_period_id, int)

    def test_manual_journal_respects_closed_period(self):
        accounts = db.get_chart_of_accounts(company_id=1)
        debit = next(a for a in accounts if a["account_type"] == "Expense")
        credit = next(a for a in accounts if a["account_code"] == "1110")
        db.lock_accounting_period("2026-03-31", company_id=1)

        with self.assertRaisesRegex(ValueError, "closed through 2026-03-31"):
            db.create_journal_entry(
                {
                    "company_id": 1,
                    "entry_date": "2026-03-31",
                    "description": "Late adjustment",
                },
                [
                    {"account_id": debit["id"], "debit_amount": 50, "credit_amount": 0},
                    {"account_id": credit["id"], "debit_amount": 0, "credit_amount": 50},
                ],
            )

    def test_foreign_currency_voucher_posts_base_currency(self):
        with self.assertRaisesRegex(ValueError, "Multi-currency is disabled"):
            db.create_voucher(
                self.voucher_data(
                    "2026-04-01", currency="USD", exchange_rate=300.0
                ),
                self.lines(10.0),
                company_id=1,
            )

        db.enable_multicurrency(1)
        conn = db.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO chart_of_accounts (
                        company_id, account_code, account_name, account_type,
                        sub_category, normal_balance, currency
                    ) VALUES (1, '1111', 'USD Cash', 'Asset', 'Cash', 'Debit', 'USD')
                    """
                )
                usd_account_id = cursor.lastrowid
        finally:
            conn.close()

        voucher_id = db.create_voucher(
            self.voucher_data(
                "2026-04-01", currency="USD", exchange_rate=300.0,
                payment_account_id=usd_account_id,
            ),
            self.lines(10.0),
            company_id=1,
        )
        conn = db.get_connection()
        try:
            journal = conn.execute(
                "SELECT id FROM journal_entries "
                "WHERE source_module = 'voucher' AND source_id = ?",
                (voucher_id,),
            ).fetchone()
            lines = conn.execute(
                "SELECT debit_amount, credit_amount FROM journal_lines "
                "WHERE entry_id = ?",
                (journal["id"],),
            ).fetchall()
        finally:
            conn.close()

        self.assertAlmostEqual(sum(row["debit_amount"] for row in lines), 3000.0)
        self.assertAlmostEqual(sum(row["credit_amount"] for row in lines), 3000.0)

    def test_source_linked_journal_cannot_be_manually_changed(self):
        voucher_id = db.create_voucher(
            self.voucher_data(), self.lines(), company_id=1
        )
        conn = db.get_connection()
        try:
            journal = conn.execute(
                "SELECT id FROM journal_entries "
                "WHERE source_module = 'voucher' AND source_id = ?",
                (voucher_id,),
            ).fetchone()
            accounts = db.get_chart_of_accounts(company_id=1, conn=conn)
        finally:
            conn.close()

        debit = next(a for a in accounts if a["account_type"] == "Expense")
        credit = next(a for a in accounts if a["account_code"] == "1110")
        balanced_lines = [
            {"account_id": debit["id"], "debit_amount": 100, "credit_amount": 0},
            {"account_id": credit["id"], "debit_amount": 0, "credit_amount": 100},
        ]
        with self.assertRaisesRegex(ValueError, "source transaction"):
            db.update_journal_entry(
                journal["id"],
                {"entry_date": "2026-02-01", "description": "Tampered"},
                balanced_lines,
            )
        with self.assertRaisesRegex(ValueError, "source transaction"):
            db.delete_journal_entry(journal["id"])

    def test_closed_period_ap_and_ar_transactions(self):
        supplier_id = db.create_supplier({
            "company_id": 1,
            "name": "Locked Period Supplier",
        })
        customer_id = db.create_customer({
            "company_id": 1,
            "name": "Locked Period Customer",
        })
        db.lock_accounting_period("2026-05-31", company_id=1)

        with self.assertRaisesRegex(ValueError, "closed through 2026-05-31"):
            db.create_ap_invoice({
                "company_id": 1,
                "supplier_id": supplier_id,
                "invoice_number": "AP-LOCKED",
                "invoice_date": "2026-05-20",
                "due_date": "2026-06-20",
            }, [{
                "description": "Locked supplier cost",
                "quantity": 1,
                "unit_price": 100,
            }])

        with self.assertRaisesRegex(ValueError, "closed through 2026-05-31"):
            db.create_ar_invoice({
                "company_id": 1,
                "customer_id": customer_id,
                "invoice_number": "AR-LOCKED",
                "invoice_date": "2026-05-20",
                "due_date": "2026-06-20",
            }, [{
                "description": "Locked customer sale",
                "quantity": 1,
                "unit_price": 100,
            }])

        ap_id = db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": supplier_id,
            "invoice_number": "AP-OPEN",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30",
        }, [{"description": "Open cost", "quantity": 1, "unit_price": 100}])
        ar_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": customer_id,
            "invoice_number": "AR-OPEN",
            "invoice_date": "2026-06-01",
            "due_date": "2026-06-30",
        }, [{"description": "Open sale", "quantity": 1, "unit_price": 100}])

        with self.assertRaisesRegex(ValueError, "closed through 2026-05-31"):
            db.record_ap_payment({
                "invoice_id": ap_id,
                "payment_date": "2026-05-31",
                "amount": 50,
            })
        with self.assertRaisesRegex(ValueError, "closed through 2026-05-31"):
            db.record_ar_receipt({
                "invoice_id": ar_id,
                "receipt_date": "2026-05-31",
                "amount": 50,
            })

if __name__ == "__main__":
    unittest.main()