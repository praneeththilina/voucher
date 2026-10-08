"""End-to-end multi-currency accounting regression tests."""

import os
import tempfile
import unittest

import database as db


class TestMultiCurrencyAccounting(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        db.enable_multicurrency(1)
        self.usd_account_id = db.create_account({
            "company_id": 1,
            "account_code": "1111",
            "account_name": "USD Bank",
            "account_type": "Asset",
            "sub_category": "Current Assets - Bank Accounts",
            "currency": "USD",
        })

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def journal_lines(self, source_module, source_id):
        conn = db.get_connection()
        try:
            return [dict(row) for row in conn.execute(
                """
                SELECT jl.*, coa.account_code
                FROM journal_entries je
                JOIN journal_lines jl ON jl.entry_id = je.id
                JOIN chart_of_accounts coa ON coa.id = jl.account_id
                WHERE je.source_module = ? AND je.source_id = ?
                ORDER BY jl.line_order
                """,
                (source_module, source_id),
            ).fetchall()]
        finally:
            conn.close()

    def test_ap_payment_posts_realized_fx_loss(self):
        supplier_id = db.create_supplier({
            "company_id": 1, "name": "USD Vendor", "currency": "USD"
        })
        invoice_id = db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": supplier_id,
            "invoice_number": "USD-BILL-1",
            "invoice_date": "2026-07-01",
            "due_date": "2026-07-31",
            "currency": "USD",
            "exchange_rate": 300,
        }, [{"description": "Services", "quantity": 1, "unit_price": 100}])
        invoice_lines = self.journal_lines("ap_invoice", invoice_id)
        self.assertAlmostEqual(sum(row["debit_amount"] for row in invoice_lines), 30000)
        self.assertAlmostEqual(sum(row["credit_amount"] for row in invoice_lines), 30000)

        payment_id = db.record_ap_payment({
            "invoice_id": invoice_id,
            "payment_date": "2026-07-15",
            "amount": 100,
            "currency": "USD",
            "exchange_rate": 310,
            "payment_account_id": self.usd_account_id,
        })
        lines = self.journal_lines("ap_payment", payment_id)
        by_code = {row["account_code"]: row for row in lines}
        self.assertAlmostEqual(by_code["2110"]["debit_amount"], 30000)
        self.assertAlmostEqual(by_code["1111"]["credit_amount"], 31000)
        self.assertAlmostEqual(by_code["5985"]["debit_amount"], 1000)

    def test_ar_receipt_posts_realized_fx_gain(self):
        customer_id = db.create_customer({
            "company_id": 1, "name": "USD Customer", "currency": "USD"
        })
        invoice_id = db.create_ar_invoice({
            "company_id": 1,
            "customer_id": customer_id,
            "invoice_number": "USD-INV-1",
            "invoice_date": "2026-08-01",
            "due_date": "2026-08-31",
            "currency": "USD",
            "exchange_rate": 300,
            "status": "Unpaid",
        }, [{"description": "Consulting", "quantity": 1, "unit_price": 100}])
        receipt_id = db.record_ar_receipt({
            "invoice_id": invoice_id,
            "receipt_date": "2026-08-20",
            "amount": 100,
            "currency": "USD",
            "exchange_rate": 310,
            "payment_account_id": self.usd_account_id,
        })
        lines = self.journal_lines("ar_receipt", receipt_id)
        by_code = {row["account_code"]: row for row in lines}
        self.assertAlmostEqual(by_code["1111"]["debit_amount"], 31000)
        self.assertAlmostEqual(by_code["1210"]["credit_amount"], 30000)
        self.assertAlmostEqual(by_code["4985"]["credit_amount"], 1000)

    def test_rate_lookup_never_uses_a_future_rate(self):
        db.save_exchange_rate("USD", "LKR", 300, "2026-01-01")
        db.save_exchange_rate("USD", "LKR", 325, "2026-03-01")

        rate = db.get_exchange_rate("USD", "LKR", "2026-02-01")
        self.assertEqual(rate["rate"], 300)
        self.assertEqual(rate["rate_date"], "2026-01-01")
        self.assertIsNone(db.get_exchange_rate("USD", "LKR", "2025-12-31"))

    def test_centres_and_aging_report_home_currency_values(self):
        supplier_id = db.create_supplier({
            "company_id": 1, "name": "USD Aging Vendor", "currency": "USD"
        })
        db.create_ap_invoice({
            "company_id": 1,
            "supplier_id": supplier_id,
            "invoice_number": "USD-AGING-1",
            "invoice_date": "2026-01-01",
            "due_date": "2026-01-31",
            "currency": "USD",
            "exchange_rate": 300,
        }, [{"description": "Services", "quantity": 1, "unit_price": 100}])

        supplier = db.get_supplier_by_id(supplier_id)
        summary = next(
            row for row in db.get_suppliers(1) if row["id"] == supplier["id"]
        )
        self.assertEqual(summary["total_invoiced"], 30000)
        self.assertEqual(summary["balance_due"], 30000)

        report = db.get_ap_aging_report(1, "2026-02-15")
        detail = report["by_supplier"][0]["invoices"][0]
        self.assertEqual(report["totals"]["total_due"], 30000)
        self.assertEqual(detail["balance_due"], 30000)
        self.assertEqual(detail["foreign_balance_due"], 100)
        self.assertEqual(detail["currency"], "USD")
    def test_backend_journal_rejects_wrong_currency_monetary_account(self):
        home_account = db.get_account_by_code("1110", 1)
        expense_account = db.get_account_by_code("5990", 1)
        header = {
            "company_id": 1,
            "entry_date": "2026-09-01",
            "transaction_currency": "USD",
            "exchange_rate": 300,
            "foreign_amount": 10,
            "source_module": "manual",
        }
        lines = [
            {"account_id": expense_account["id"], "debit_amount": 3000},
            {"account_id": home_account["id"], "credit_amount": 3000},
        ]
        with self.assertRaisesRegex(ValueError, "LKR monetary account"):
            db.create_journal_entry(header, lines)

        lines[1]["account_id"] = self.usd_account_id
        entry_id = db.create_journal_entry(header, lines)
        entry = db.get_journal_entry(entry_id)["entry"]
        self.assertEqual(entry["transaction_currency"], "USD")
        self.assertEqual(entry["exchange_rate"], 300)
        self.assertEqual(entry["foreign_amount"], 10)
    def test_foreign_transaction_rejects_home_currency_account(self):
        home_account = db.get_account_by_code("1110", 1)
        with self.assertRaisesRegex(ValueError, "cannot settle a USD transaction"):
            db.create_voucher({
                "company_id": 1,
                "date": "2026-09-01",
                "paid_to": "Foreign Supplier",
                "cash_given_by": "Cashier",
                "payment_method": "Cash",
                "currency": "USD",
                "exchange_rate": 300,
                "payment_account_id": home_account["id"],
            }, [{"description": "Travel", "category": "Travel", "amount": 10}])


if __name__ == "__main__":
    unittest.main()