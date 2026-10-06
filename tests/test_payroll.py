"""
tests/test_payroll.py
Unit tests for Basic Payroll & Employee Expense Claims Module (v4.0).
Tests employee CRUD, auto-numbering, payroll run salary calculations,
voucher generation, double-entry auto-journaling, expense claim reimbursement,
and ReportLab PDF generation for payslips and payroll master summaries.
"""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
import payroll_printer


class TestPayroll(unittest.TestCase):
    """Test suite verifying employees, payroll runs, payslips, claims, and voucher integration."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = 1
        self.created_temp_files = []

    def tearDown(self):
        for fpath in self.created_temp_files:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        db.DB_PATH = self.orig_db_path

    def test_employee_crud_and_autonumbering(self):
        """Test employee code auto-numbering, creation, retrieval, and updating."""
        c1 = db.get_next_employee_code(self.company_id)
        self.assertEqual(c1, "EMP-0001")

        e1_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": c1,
            "full_name": "Kasun Perera",
            "designation": "Senior Software Engineer",
            "department": "Engineering",
            "nic_number": "941234567V",
            "email": "kasun@company.com",
            "phone": "+94 77 123 4567",
            "basic_salary": 180000.0,
            "bank_name": "Commercial Bank",
            "bank_account": "8001234567",
            "is_active": 1,
        })
        self.assertGreater(e1_id, 0)

        c2 = db.get_next_employee_code(self.company_id)
        self.assertEqual(c2, "EMP-0002")

        e2_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": c2,
            "full_name": "Nimali Silva",
            "designation": "Finance Executive",
            "department": "Accounts",
            "nic_number": "968765432V",
            "basic_salary": 95000.0,
            "is_active": 1,
        })
        self.assertGreater(e2_id, 0)

        # Retrieve and verify
        e1 = db.get_employee(e1_id)
        self.assertIsNotNone(e1)
        self.assertEqual(e1["employee_code"], "EMP-0001")
        self.assertEqual(e1["full_name"], "Kasun Perera")
        self.assertEqual(e1["basic_salary"], 180000.0)

        # Update
        db.update_employee(e1_id, {
            **e1,
            "basic_salary": 200000.0,
            "designation": "Lead Architect"
        })
        updated = db.get_employee(e1_id)
        self.assertEqual(updated["basic_salary"], 200000.0)
        self.assertEqual(updated["designation"], "Lead Architect")

        # Search
        results = db.get_employees(self.company_id, search="Nimali")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["employee_code"], "EMP-0002")

    def test_payroll_run_calculation_and_processing(self):
        """Test payroll run earnings, deductions, gross/net pay calculation."""
        e1_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": "EMP-0001",
            "full_name": "Ruwan Fernando",
            "designation": "Operations Lead",
            "basic_salary": 150000.0,
        })
        e2_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": "EMP-0002",
            "full_name": "Dilini Gamage",
            "designation": "Operations Associate",
            "basic_salary": 75000.0,
        })

        lines = [
            {
                "employee_id": e1_id,
                "basic_salary": 150000.0,
                "allowances": 20000.0,
                "overtime": 10000.0,
                # Gross: 180,000
                "epf_employee": 12000.0,   # 8% of 150k
                "tax_deduction": 5000.0,
                "other_deductions": 3000.0,
                # Total deductions: 20,000
                # Net: 160,000
                "payment_method": "Bank Transfer",
            },
            {
                "employee_id": e2_id,
                "basic_salary": 75000.0,
                "allowances": 5000.0,
                "overtime": 0.0,
                # Gross: 80,000
                "epf_employee": 6000.0,    # 8% of 75k
                "tax_deduction": 0.0,
                "other_deductions": 0.0,
                # Total deductions: 6,000
                # Net: 74,000
                "payment_method": "Bank Transfer",
            }
        ]

        run_id = db.create_payroll_run({
            "company_id": self.company_id,
            "pay_period": "2026-10",
            "run_date": "2026-10-25",
            "status": "Approved",
            "notes": "October 2026 Monthly Salaries",
            "created_by": "HR Officer",
        }, lines)
        self.assertGreater(run_id, 0)

        run = db.get_payroll_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(run["pay_period"], "2026-10")
        self.assertEqual(run["total_gross"], 260000.0)  # 180k + 80k
        self.assertEqual(run["total_net"], 234000.0)    # 160k + 74k
        self.assertEqual(len(run["lines"]), 2)

        l1 = [l for l in run["lines"] if l["employee_id"] == e1_id][0]
        self.assertEqual(l1["gross_pay"], 180000.0)
        self.assertEqual(l1["total_deductions"], 20000.0)
        self.assertEqual(l1["net_pay"], 160000.0)

        # Deletion protection: employee cannot be deleted while in payroll run
        can_del, msg = db.delete_employee(e1_id)
        self.assertFalse(can_del)
        self.assertIn("payroll record", msg)

    def test_payroll_bulk_voucher_creation_and_auto_journal(self):
        """Test converting approved payroll run into a bulk payment voucher with General Ledger double-entry."""
        e1_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": "EMP-0001",
            "full_name": "Saman Kumara",
            "basic_salary": 100000.0,
        })

        run_id = db.create_payroll_run({
            "company_id": self.company_id,
            "pay_period": "2026-10",
            "run_date": "2026-10-28",
            "status": "Approved",
        }, [
            {
                "employee_id": e1_id,
                "basic_salary": 100000.0,
                "allowances": 0.0,
                "overtime": 0.0,
                "epf_employee": 8000.0,
                "tax_deduction": 2000.0,
                "other_deductions": 0.0,
            }
        ])

        run_before = db.get_payroll_run(run_id)
        self.assertEqual(run_before["total_net"], 90000.0)

        # Convert to Voucher
        voucher_id = db.create_voucher_from_payroll_run(
            run_id=run_id,
            payment_method="Bank Transfer",
            paid_to="Staff Salary Transfer - October 2026"
        )
        self.assertGreater(voucher_id, 0)

        # Check run status updated to Paid and voucher_id linked
        run_after = db.get_payroll_run(run_id)
        self.assertEqual(run_after["status"], "Paid")
        self.assertEqual(run_after["voucher_id"], voucher_id)

        # Check created voucher
        vdata = db.get_voucher(voucher_id)
        self.assertIsNotNone(vdata)
        v = vdata["voucher"]
        self.assertEqual(v["total_amount"], 90000.0)
        self.assertEqual(v["paid_to"], "Staff Salary Transfer - October 2026")
        self.assertEqual(v["payment_method"], "Bank Transfer")

        # Verify auto-journal double entry created for voucher
        jes = db.get_journal_entries(self.company_id, search=v["voucher_number"])
        self.assertTrue(len(jes) > 0)
        je = db.get_journal_entry(jes[0]["id"])
        self.assertIsNotNone(je)
        debits = sum(l["debit_amount"] for l in je["lines"])
        credits = sum(l["credit_amount"] for l in je["lines"])
        self.assertAlmostEqual(debits, 90000.0, places=2)
        self.assertAlmostEqual(credits, 90000.0, places=2)

    def test_expense_claim_lifecycle_and_reimbursement(self):
        """Test employee expense claim creation, approval, and voucher reimbursement."""
        e_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": "EMP-0010",
            "full_name": "Chaminda Vaas",
            "designation": "Field Engineer",
            "basic_salary": 120000.0,
        })

        next_c = db.get_next_claim_number(self.company_id)
        current_year = datetime.now().year
        self.assertEqual(next_c, f"CLM-{current_year}-0001")

        claim_lines = [
            {
                "date": "2026-10-10",
                "description": "Client Site Travel & Fuel",
                "category": "Travel & Transport",
                "amount": 14500.0,
            },
            {
                "date": "2026-10-11",
                "description": "Hardware Replacement Tools",
                "category": "Office Stationery",
                "amount": 5500.0,
            }
        ]

        claim_id = db.create_expense_claim({
            "company_id": self.company_id,
            "employee_id": e_id,
            "claim_number": next_c,
            "claim_date": "2026-10-12",
            "notes": "Urgent on-site installation expenses",
        }, claim_lines)
        self.assertGreater(claim_id, 0)

        # Retrieve and verify
        claim = db.get_expense_claim(claim_id)
        self.assertIsNotNone(claim)
        self.assertEqual(claim["employee_name"], "Chaminda Vaas")
        self.assertEqual(claim["total_amount"], 20000.0)
        self.assertEqual(claim["status"], "Pending")
        self.assertEqual(len(claim["lines"]), 2)

        # Approve claim
        db.update_expense_claim_status(claim_id, "Approved", approved_by="Project Manager")
        appr_claim = db.get_expense_claim(claim_id)
        self.assertEqual(appr_claim["status"], "Approved")

        # Reimburse via payment voucher
        voucher_id = db.create_voucher_from_expense_claim(claim_id, payment_method="Cash")
        self.assertGreater(voucher_id, 0)

        # Verify claim marked as Paid and voucher linked
        paid_claim = db.get_expense_claim(claim_id)
        self.assertEqual(paid_claim["status"], "Paid")
        self.assertEqual(paid_claim["voucher_id"], voucher_id)

        # Verify reimbursement voucher contents
        vdata = db.get_voucher(voucher_id)
        v = vdata["voucher"]
        self.assertEqual(v["total_amount"], 20000.0)
        self.assertEqual(v["paid_to"], "Chaminda Vaas")
        self.assertEqual(len(vdata["line_items"]), 2)

    def test_payslip_and_payroll_run_pdf_generation(self):
        """Test PDF generation for individual employee payslip and payroll master sheet."""
        e_id = db.create_employee({
            "company_id": self.company_id,
            "employee_code": "EMP-0099",
            "full_name": "Anura Kumara",
            "designation": "Director",
            "department": "Executive",
            "nic_number": "701234567V",
            "bank_name": "Commercial Bank",
            "bank_account": "1002345678",
            "basic_salary": 250000.0,
        })

        run_id = db.create_payroll_run({
            "company_id": self.company_id,
            "pay_period": "2026-10",
            "run_date": "2026-10-31",
            "status": "Approved",
            "created_by": "HR Manager",
            "approved_by": "Board Director",
        }, [
            {
                "employee_id": e_id,
                "basic_salary": 250000.0,
                "allowances": 50000.0,
                "overtime": 0.0,
                "epf_employee": 20000.0,
                "tax_deduction": 15000.0,
                "other_deductions": 0.0,
                "payment_method": "Bank Transfer",
            }
        ])

        run_data = db.get_payroll_run(run_id)
        comp = db.get_company(self.company_id)
        line = run_data["lines"][0]

        # 1. Test Payslip PDF
        fd1, out_slip = tempfile.mkstemp(suffix=".pdf")
        os.close(fd1)
        self.created_temp_files.append(out_slip)

        res_slip = payroll_printer.generate_payslip_pdf(line, run_data, company=comp, output_path=out_slip)
        self.assertTrue(os.path.exists(res_slip))
        self.assertGreater(os.path.getsize(res_slip), 2000)

        # 2. Test Payroll Master Summary Sheet PDF
        fd2, out_summary = tempfile.mkstemp(suffix=".pdf")
        os.close(fd2)
        self.created_temp_files.append(out_summary)

        res_summary = payroll_printer.generate_payroll_run_pdf(run_data, company=comp, output_path=out_summary)
        self.assertTrue(os.path.exists(res_summary))
        self.assertGreater(os.path.getsize(res_summary), 2000)

    def test_company_cascade_deletion(self):
        """Test that company cascade delete properly removes employees, payroll, and claims."""
        # Create a second company
        c2_id = db.create_company("Payroll Test Co 2")
        e_id = db.create_employee({
            "company_id": c2_id,
            "employee_code": "EMP-9999",
            "full_name": "Test Emp",
            "basic_salary": 50000.0,
        })
        self.assertGreater(e_id, 0)

        run_id = db.create_payroll_run({
            "company_id": c2_id,
            "pay_period": "2026-10",
            "run_date": "2026-10-31",
        }, [
            {
                "employee_id": e_id,
                "basic_salary": 50000.0,
                "allowances": 0.0,
                "overtime": 0.0,
                "epf_employee": 4000.0,
                "tax_deduction": 0.0,
                "other_deductions": 0.0,
            }
        ])
        self.assertGreater(run_id, 0)

        claim_id = db.create_expense_claim({
            "company_id": c2_id,
            "employee_id": e_id,
            "claim_number": "CLM-C2-001",
            "claim_date": "2026-10-15",
        }, [
            {
                "date": "2026-10-15",
                "description": "Test expense",
                "amount": 2500.0,
            }
        ])
        self.assertGreater(claim_id, 0)

        # Delete company 2
        ok = db.delete_company(c2_id)
        self.assertTrue(ok)

        # Verify cascades
        self.assertIsNone(db.get_employee(e_id))
        self.assertIsNone(db.get_payroll_run(run_id))
        self.assertIsNone(db.get_expense_claim(claim_id))


if __name__ == "__main__":
    unittest.main()
