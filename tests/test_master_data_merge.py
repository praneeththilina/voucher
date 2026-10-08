"""Regression tests for duplicate detection and master-record merges."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import database as db
import sales_database as sales_db


class TestMasterDataMerge(unittest.TestCase):
    """Ensure merges retain accounting history and reject duplicate names."""

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "master_merge.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        self.conn = db.get_connection()
        self.revenue = db.get_account_by_code("4110", 1, conn=self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        db.DB_PATH = self.original_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalized_duplicate_names_are_rejected(self) -> None:
        db.create_customer(
            {"company_id": 1, "name": "Acme  Retail"}, conn=self.conn
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.create_customer(
                {"company_id": 1, "name": "  ACME retail  "}, conn=self.conn
            )

        db.create_supplier(
            {"company_id": 1, "name": "North Star Vendor"}, conn=self.conn
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.create_supplier(
                {"company_id": 1, "name": "north   star vendor"},
                conn=self.conn,
            )

        db.create_account(
            {
                "company_id": 1,
                "account_code": "5981",
                "account_name": "Online Service Fees",
                "account_type": "Expense",
            },
            conn=self.conn,
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.create_account(
                {
                    "company_id": 1,
                    "account_code": "5982",
                    "account_name": "online  service fees",
                    "account_type": "Expense",
                },
                conn=self.conn,
            )

        sales_db.save_sales_item(
            {
                "company_id": 1,
                "name": "Monthly Support",
                "item_type": "Service",
                "income_account_id": self.revenue["id"],
            },
            conn=self.conn,
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            sales_db.save_sales_item(
                {
                    "company_id": 1,
                    "name": " monthly   SUPPORT ",
                    "item_type": "Service",
                    "income_account_id": self.revenue["id"],
                },
                conn=self.conn,
            )

    def test_duplicate_name_updates_are_rejected(self) -> None:
        customer_a = db.create_customer(
            {"company_id": 1, "name": "Customer Alpha"}, conn=self.conn
        )
        customer_b = db.create_customer(
            {"company_id": 1, "name": "Customer Beta"}, conn=self.conn
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.update_customer(
                customer_b, {"name": " customer   ALPHA "}, conn=self.conn
            )

        supplier_a = db.create_supplier(
            {"company_id": 1, "name": "Vendor Alpha"}, conn=self.conn
        )
        supplier_b = db.create_supplier(
            {"company_id": 1, "name": "Vendor Beta"}, conn=self.conn
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.update_supplier(
                supplier_b, {"name": "VENDOR alpha"}, conn=self.conn
            )

        account_a = db.create_account(
            {
                "company_id": 1,
                "account_code": "5961",
                "account_name": "Account Alpha",
                "account_type": "Expense",
            },
            conn=self.conn,
        )
        account_b = db.create_account(
            {
                "company_id": 1,
                "account_code": "5962",
                "account_name": "Account Beta",
                "account_type": "Expense",
            },
            conn=self.conn,
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            db.update_account(
                account_b,
                {"account_name": " account  ALPHA "},
                conn=self.conn,
            )

        item_a = sales_db.save_sales_item(
            {
                "company_id": 1,
                "name": "Service Alpha",
                "item_type": "Service",
                "income_account_id": self.revenue["id"],
            },
            conn=self.conn,
        )
        item_b = sales_db.save_sales_item(
            {
                "company_id": 1,
                "name": "Service Beta",
                "item_type": "Service",
                "income_account_id": self.revenue["id"],
            },
            conn=self.conn,
        )
        item_data = sales_db.get_sales_item(item_b, conn=self.conn)
        item_data["name"] = " SERVICE alpha "
        with self.assertRaisesRegex(ValueError, "already exists"):
            sales_db.save_sales_item(item_data, item_id=item_b, conn=self.conn)

        self.assertIsNotNone(customer_a)
        self.assertIsNotNone(supplier_a)
        self.assertIsNotNone(account_a)
        self.assertIsNotNone(item_a)
    def test_customer_merge_moves_invoices_and_unapplied_payments(self) -> None:
        target_id = db.create_customer(
            {"company_id": 1, "name": "Retained Customer"}, conn=self.conn
        )
        source_id = db.create_customer(
            {"company_id": 1, "name": "Duplicate Customer"}, conn=self.conn
        )
        invoice_id = db.create_ar_invoice(
            {
                "company_id": 1,
                "customer_id": source_id,
                "invoice_number": "INV-MERGE-001",
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
            },
            [
                {
                    "description": "Consulting",
                    "account_id": self.revenue["id"],
                    "quantity": 1,
                    "unit_price": 1000,
                    "line_total": 1000,
                }
            ],
            conn=self.conn,
        )
        payment_id = self.conn.execute(
            """
            INSERT INTO customer_payments (
                company_id, customer_id, payment_date, amount,
                applied_amount, unapplied_amount
            ) VALUES (1, ?, '2026-10-02', 250, 0, 250)
            """,
            (source_id,),
        ).lastrowid
        self.conn.commit()

        self.assertEqual(
            db.merge_customers(source_id, target_id, conn=self.conn), target_id
        )
        self.assertIsNone(db.get_customer_by_id(source_id, conn=self.conn))
        invoice_customer = self.conn.execute(
            "SELECT customer_id FROM ar_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()[0]
        payment_customer = self.conn.execute(
            "SELECT customer_id FROM customer_payments WHERE id = ?",
            (payment_id,),
        ).fetchone()[0]
        self.assertEqual(invoice_customer, target_id)
        self.assertEqual(payment_customer, target_id)

    def test_supplier_merge_moves_bills_and_credits(self) -> None:
        target_id = db.create_supplier(
            {"company_id": 1, "name": "Retained Vendor"}, conn=self.conn
        )
        source_id = db.create_supplier(
            {"company_id": 1, "name": "Duplicate Vendor"}, conn=self.conn
        )
        invoice_id = db.create_ap_invoice(
            {
                "company_id": 1,
                "supplier_id": source_id,
                "invoice_number": "BILL-MERGE-001",
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
            },
            [{"description": "Supplies", "quantity": 1, "unit_price": 600,
              "line_total": 600}],
            conn=self.conn,
        )

        self.assertEqual(
            db.merge_suppliers(source_id, target_id, conn=self.conn), target_id
        )
        self.assertIsNone(db.get_supplier_by_id(source_id, conn=self.conn))
        invoice_supplier = self.conn.execute(
            "SELECT supplier_id FROM ap_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()[0]
        self.assertEqual(invoice_supplier, target_id)

    def test_item_merge_moves_invoice_and_inventory_history(self) -> None:
        target_id = sales_db.save_sales_item(
            {
                "company_id": 1,
                "name": "Retained Service",
                "item_type": "Service",
                "income_account_id": self.revenue["id"],
            },
            conn=self.conn,
        )
        source_id = sales_db.save_sales_item(
            {
                "company_id": 1,
                "name": "Duplicate Service",
                "item_type": "Service",
                "income_account_id": self.revenue["id"],
            },
            conn=self.conn,
        )
        customer_id = db.create_customer(
            {"company_id": 1, "name": "Item Merge Customer"}, conn=self.conn
        )
        invoice_id = db.create_ar_invoice(
            {
                "company_id": 1,
                "customer_id": customer_id,
                "invoice_number": "INV-ITEM-MERGE",
                "invoice_date": "2026-10-01",
                "due_date": "2026-10-31",
            },
            [
                {
                    "item_id": source_id,
                    "description": "Service",
                    "account_id": self.revenue["id"],
                    "quantity": 1,
                    "unit_price": 300,
                    "line_total": 300,
                }
            ],
            conn=self.conn,
        )
        self.conn.execute(
            "UPDATE ar_invoice_lines SET item_id = ? WHERE invoice_id = ?",
            (source_id, invoice_id),
        )
        movement_id = self.conn.execute(
            """
            INSERT INTO inventory_movements (
                company_id, item_id, movement_date, quantity_change,
                unit_cost, source_type, source_id
            ) VALUES (1, ?, '2026-10-01', -1, 0, 'test', ?)
            """,
            (source_id, invoice_id),
        ).lastrowid
        self.conn.commit()

        self.assertEqual(
            sales_db.merge_sales_items(source_id, target_id, conn=self.conn),
            target_id,
        )
        self.assertIsNone(sales_db.get_sales_item(source_id, conn=self.conn))
        line_item = self.conn.execute(
            "SELECT item_id FROM ar_invoice_lines WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]
        movement_item = self.conn.execute(
            "SELECT item_id FROM inventory_movements WHERE id = ?",
            (movement_id,),
        ).fetchone()[0]
        self.assertEqual(line_item, target_id)
        self.assertEqual(movement_item, target_id)

    def test_account_merge_moves_journals_budgets_and_children(self) -> None:
        target_id = db.create_account(
            {
                "company_id": 1,
                "account_code": "5971",
                "account_name": "Retained Expense",
                "account_type": "Expense",
            },
            conn=self.conn,
        )
        source_id = db.create_account(
            {
                "company_id": 1,
                "account_code": "5972",
                "account_name": "Duplicate Expense",
                "account_type": "Expense",
            },
            conn=self.conn,
        )
        child_id = db.create_account(
            {
                "company_id": 1,
                "account_code": "5973",
                "account_name": "Expense Subaccount",
                "account_type": "Expense",
                "parent_id": source_id,
            },
            conn=self.conn,
        )
        journal_id = db.create_journal_entry(
            {
                "company_id": 1,
                "entry_number": "JE-MERGE-001",
                "entry_date": "2026-10-01",
                "description": "Merge test",
            },
            [
                {"account_id": source_id, "debit_amount": 100,
                 "credit_amount": 0},
                {"account_id": target_id, "debit_amount": 0,
                 "credit_amount": 100},
            ],
            conn=self.conn,
        )
        self.conn.execute(
            """
            INSERT INTO budgets (
                company_id, account_id, budget_year, budget_month,
                budget_amount, actual_amount, notes
            ) VALUES (1, ?, 2026, 10, 400, 40, 'source')
            """,
            (source_id,),
        )
        self.conn.execute(
            """
            INSERT INTO budgets (
                company_id, account_id, budget_year, budget_month,
                budget_amount, actual_amount, notes
            ) VALUES (1, ?, 2026, 10, 600, 60, 'target')
            """,
            (target_id,),
        )
        self.conn.commit()

        self.assertEqual(
            db.merge_accounts(source_id, target_id, conn=self.conn), target_id
        )
        self.assertIsNone(db.get_account_by_id(source_id, conn=self.conn))
        line_accounts = {
            row[0] for row in self.conn.execute(
                "SELECT account_id FROM journal_lines WHERE entry_id = ?",
                (journal_id,),
            ).fetchall()
        }
        self.assertEqual(line_accounts, {target_id})
        child_parent = self.conn.execute(
            "SELECT parent_id FROM chart_of_accounts WHERE id = ?", (child_id,)
        ).fetchone()[0]
        budget = self.conn.execute(
            """
            SELECT budget_amount, actual_amount FROM budgets
            WHERE account_id = ? AND budget_year = 2026 AND budget_month = 10
            """,
            (target_id,),
        ).fetchone()
        self.assertEqual(child_parent, target_id)
        self.assertEqual(budget[0], 1000)
        self.assertEqual(budget[1], 100)


if __name__ == "__main__":
    unittest.main()