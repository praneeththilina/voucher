"""Integration tests for supplier bills, Pay Bills, and Write Cheques."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import database as db
import vendor_payments as vp
from tests.test_widgets import get_test_root
from ui.pay_bills_dialog import PayBillsDialog


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

    def test_pay_bills_settles_ap_without_creating_payment_voucher(self):
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
        self.assertIsNone(batch["voucher_id"])
        payments = self.connection.execute(
            "SELECT * FROM ap_payments WHERE batch_id = ?", (batch_id,)
        ).fetchall()
        self.assertEqual(len(payments), 2)
        self.assertTrue(all(row["voucher_id"] is None for row in payments))
        dedicated = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='ap_payment_batch' AND source_id=?",
            (batch_id,),
        ).fetchone()[0]
        self.assertEqual(dedicated, 1)
        statuses = self.connection.execute(
            "SELECT status FROM ap_invoices WHERE id IN (?, ?) ORDER BY id",
            (first, second),
        ).fetchall()
        self.assertEqual([row["status"] for row in statuses], ["Paid", "Paid"])

    def test_cheque_payment_links_check_to_ap_batch_not_voucher(self):
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
            [{"invoice_id": bill_id, "cash_amount": 3500, "credit_amount": 0}],
        )

        batch = vp.get_payment_batch(batch_id)
        self.assertIsNone(batch["voucher_id"])
        self.assertIsNotNone(batch["check_id"])
        check = db.get_check_by_id(batch["check_id"], conn=self.connection)
        self.assertEqual(check["check_number"], "CHQ-9001")
        self.assertIsNone(check["voucher_id"])
        self.assertEqual(check["ap_payment_batch_id"], batch_id)
        self.assertEqual(check["payee_name"], "Linked Vendor")
        payment = self.connection.execute(
            "SELECT * FROM ap_payments WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        self.assertIsNone(payment["voucher_id"])
        self.assertEqual(payment["check_id"], batch["check_id"])

    def test_print_later_defers_cheque_number_and_creates_no_voucher(self):
        bill_id = self._bill("BILL-LATER", 900)
        batch_id = vp.pay_bills(
            self._payment_data(
                payment_method="Cheque", check_number="", print_later=True
            ),
            [{"invoice_id": bill_id, "cash_amount": 900, "credit_amount": 0}],
        )
        batch = vp.get_payment_batch(batch_id)
        self.assertIsNone(batch["voucher_id"])
        self.assertIsNone(batch["check_id"])
        self.assertEqual(batch["print_later"], 1)

    def test_legacy_ap_bill_converts_to_voucher_without_second_journal(self):
        invoice_id = self._bill("LEGACY-001", 725)
        voucher_id = db.ensure_supplier_bill_voucher(invoice_id)
        voucher = db.get_voucher(voucher_id, conn=self.connection)["voucher"]
        self.assertEqual(voucher["source_module"], "ap_invoice")
        self.assertEqual(voucher["source_id"], invoice_id)
        invoice = db.get_ap_invoice(invoice_id, conn=self.connection)["invoice"]
        self.assertEqual(invoice["voucher_id"], voucher_id)
        self.assertEqual(db.ensure_supplier_bill_voucher(invoice_id), voucher_id)
        ap_journals = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='ap_invoice' AND source_id=?",
            (invoice_id,),
        ).fetchone()[0]
        voucher_journals = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='voucher' AND source_id=?",
            (voucher_id,),
        ).fetchone()[0]
        self.assertEqual(ap_journals, 1)
        self.assertEqual(voucher_journals, 0)
    def test_current_voucher_document_creates_real_supplier_bill(self):
        expense = db.get_account_by_code(
            "5410", company_id=1, conn=self.connection
        )
        voucher_id = db.create_supplier_bill_voucher(
            {
                "company_id": 1,
                "voucher_number": "VB-001",
                "date": "2026-10-01",
                "due_date": "2026-10-31",
                "paid_to": "Linked Vendor",
                "cash_given_by": "Admin",
                "spent_by": "",
                "bill_status": "Unpaid",
                "payment_method": "Accounts Payable",
                "payment_ref": "SUP-INV-001",
                "prepared_by": "Admin",
                "currency": "LKR",
                "exchange_rate": 1,
            },
            [
                {
                    "description": "Office supplies bill",
                    "category": expense["account_name"],
                    "amount": 1500,
                }
            ],
            company_id=1,
        )
        voucher = db.get_voucher(voucher_id, conn=self.connection)["voucher"]
        self.assertEqual(voucher["source_module"], "ap_invoice")
        self.assertEqual(voucher["payment_method"], "Accounts Payable")
        self.assertIsNone(voucher["payment_account_id"])
        invoice = db.get_ap_invoice(voucher["source_id"], conn=self.connection)
        self.assertEqual(invoice["invoice"]["voucher_id"], voucher_id)
        self.assertEqual(invoice["invoice"]["invoice_number"], "SUP-INV-001")
        self.assertEqual(invoice["invoice"]["status"], "Unpaid")
        ap_journals = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='ap_invoice' AND source_id=?",
            (voucher["source_id"],),
        ).fetchone()[0]
        voucher_journals = self.connection.execute(
            "SELECT COUNT(*) FROM journal_entries "
            "WHERE source_module='voucher' AND source_id=?",
            (voucher_id,),
        ).fetchone()[0]
        self.assertEqual(ap_journals, 1)
        self.assertEqual(voucher_journals, 0)

        batch_id = vp.pay_bills(
            self._payment_data(),
            [{
                "invoice_id": voucher["source_id"],
                "cash_amount": 1500,
                "credit_amount": 0,
            }],
        )
        self.assertIsNotNone(batch_id)
        settled = db.get_voucher(voucher_id, conn=self.connection)["voucher"]
        self.assertEqual(settled["bill_status"], "Paid")
        voucher_count = self.connection.execute(
            "SELECT COUNT(*) FROM vouchers WHERE company_id = 1"
        ).fetchone()[0]
        self.assertEqual(voucher_count, 1)

    def test_pay_bills_posts_early_payment_discount(self):
        """Discount closes AP and credits the discounts-received ledger."""
        bill_id = self._bill("BILL-DISCOUNT", 1000)
        batch_id = vp.pay_bills(
            self._payment_data(),
            [{
                "invoice_id": bill_id,
                "cash_amount": 900,
                "credit_amount": 0,
                "discount_amount": 100,
            }],
        )

        invoice = db.get_ap_invoice(bill_id, conn=self.connection)["invoice"]
        self.assertEqual(invoice["status"], "Paid")
        self.assertEqual(invoice["paid_amount"], 1000)
        batch = vp.get_payment_batch(batch_id)
        self.assertEqual(batch["total_cash_amount"], 900)
        self.assertEqual(batch["total_credit_amount"], 100)
        discount = self.connection.execute(
            "SELECT * FROM vendor_credits WHERE credit_number = ?",
            (f"DISC-{batch_id}-{bill_id}",),
        ).fetchone()
        self.assertIsNotNone(discount)
        self.assertEqual(discount["status"], "Applied")
        discount_account = db.get_account_by_code(
            "4310", company_id=1, conn=self.connection
        )
        journal_credit = self.connection.execute(
            "SELECT jl.credit_amount FROM journal_entries je "
            "JOIN journal_lines jl ON jl.entry_id = je.id "
            "WHERE je.source_module = 'vendor_credit' "
            "AND je.source_id = ? AND jl.account_id = ?",
            (discount["id"], discount_account["id"]),
        ).fetchone()
        self.assertEqual(journal_credit["credit_amount"], 100)

    def test_pay_bills_command_bar_remains_visible(self):
        """Pay Bills keeps commands visible and supports QB-style allocation."""
        bill_id = self._bill("BILL-UI", 1200)
        expense = db.get_account_by_code(
            "5410", company_id=1, conn=self.connection
        )
        vp.create_credit({
            "company_id": 1,
            "supplier_id": self.supplier_id,
            "credit_number": "CREDIT-UI",
            "credit_date": "2026-10-05",
            "amount": 100,
            "expense_account_id": expense["id"],
        })
        root = get_test_root()
        if not root:
            self.skipTest("Tkinter display not available")

        root.deiconify()
        dialog = PayBillsDialog(
            root,
            company_id=1,
            initial_supplier_id=self.supplier_id,
        )
        root.update()
        self.assertEqual(dialog.command_bar.winfo_manager(), "pack")
        self.assertTrue(dialog.command_row.winfo_ismapped())
        for button in (dialog.pay_btn, dialog.credit_btn, dialog.close_btn):
            self.assertEqual(button.winfo_manager(), "pack")
            self.assertTrue(button.winfo_ismapped())
            self.assertGreater(button.winfo_height(), 1)
            button_bottom = button.winfo_rooty() + button.winfo_height()
            window_bottom = dialog.winfo_rooty() + dialog.winfo_height()
            self.assertLessEqual(button_bottom, window_bottom)

        dialog.show_mode.set("Due on or before")
        dialog.due_by.set("2026-10-15")
        dialog.refresh()
        self.assertEqual(dialog.bills, [])
        dialog.show_mode.set("All open bills")
        dialog.refresh()
        self.assertEqual([row["id"] for row in dialog.bills], [bill_id])

        dialog.select_all(True)
        dialog.tree.selection_set(str(bill_id))
        with patch(
            "ui.pay_bills_dialog.simpledialog.askfloat", return_value=250.0
        ):
            dialog.set_payment_amount()
        self.assertEqual(dialog.selected[bill_id]["cash"], 250.0)
        with patch(
            "ui.pay_bills_dialog.simpledialog.askfloat", return_value=100.0
        ):
            dialog.set_credits()
        self.assertEqual(dialog.selected[bill_id]["credit"], 100.0)
        with patch(
            "ui.pay_bills_dialog.simpledialog.askfloat", return_value=50.0
        ):
            dialog.set_discount()
        self.assertEqual(dialog.selected[bill_id]["discount"], 50.0)

        dialog.destroy()
        root.withdraw()
        for child in root.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
