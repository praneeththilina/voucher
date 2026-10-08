"""
ui/payroll_dialog.py
UI Management Dialogs for Basic Payroll, Salary Slips & Employee Expense Claims (v4.0).

Includes:
- EmployeeManagerDialog & EmployeeEntryDialog (Staff master directory)
- PayrollRunDialog & PayrollRunEntryDialog (Monthly payroll processing, payslips & bulk voucher payout)
- ExpenseClaimDialog & ExpenseClaimEntryDialog (Employee expense claims & reimbursement voucher generation)
- PayrollMasterDialog (Unified Tabbed HR & Payroll Suite)
"""

import os
import tkinter as tk
import json
from datetime import datetime
from tkinter import messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import payroll_printer
from ui.dialogs import PdfViewerDialog


# =========================================================================
# 1. EMPLOYEE ENTRY DIALOG
# =========================================================================

class EmployeeEntryDialog(tb.Toplevel):
    """Modal dialog to create or edit an employee record."""

    def __init__(self, parent, company_id=None, employee_id=None, on_saved_callback=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.employee_id = employee_id
        self.on_saved_callback = on_saved_callback

        self.title("Edit Employee" if employee_id else "Add New Employee")
        self.geometry("640x720")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._load_data()
        self._build_ui()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _load_data(self):
        if self.employee_id:
            self.emp = db.get_employee(self.employee_id) or {}
        else:
            self.emp = {
                "employee_code": db.get_next_employee_code(self.company_id),
                "is_active": 1,
                "basic_salary": 0.0,
                "joined_date": datetime.now().strftime("%Y-%m-%d"),
                "pay_basis": "Monthly Salary",
                "pay_rate": 0.0,
                "standard_units": 1.0,
                "epf_eligible": 1,
                "apit_enabled": 1,
                "custom_fields_json": "{}",
            }

    def _build_ui(self):
        pad = tb.Frame(self, padding=20)
        pad.pack(fill=BOTH, expand=True)

        tb.Label(pad, text="👤 Employee Profile", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 12))

        # Row 1: Code and Full Name
        r1 = tb.Frame(pad)
        r1.pack(fill=X, pady=(0, 8))

        c1 = tb.Frame(r1)
        c1.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c1, text="Employee ID *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.code_var = tk.StringVar(value=self.emp.get("employee_code", ""))
        tb.Entry(c1, textvariable=self.code_var).pack(fill=X, pady=(2, 0))

        c2 = tb.Frame(r1)
        c2.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c2, text="Full Name *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.name_var = tk.StringVar(value=self.emp.get("full_name", ""))
        tb.Entry(c2, textvariable=self.name_var).pack(fill=X, pady=(2, 0))

        # Row 2: Designation and Department
        r2 = tb.Frame(pad)
        r2.pack(fill=X, pady=(0, 8))

        c3 = tb.Frame(r2)
        c3.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c3, text="Designation:", font=("Segoe UI", 8)).pack(anchor=W)
        self.desig_var = tk.StringVar(value=self.emp.get("designation", ""))
        tb.Entry(c3, textvariable=self.desig_var).pack(fill=X, pady=(2, 0))

        c4 = tb.Frame(r2)
        c4.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c4, text="Department:", font=("Segoe UI", 8)).pack(anchor=W)
        self.dept_var = tk.StringVar(value=self.emp.get("department", ""))
        tb.Entry(c4, textvariable=self.dept_var).pack(fill=X, pady=(2, 0))

        # Row 3: NIC and Joined Date
        r3 = tb.Frame(pad)
        r3.pack(fill=X, pady=(0, 8))

        c5 = tb.Frame(r3)
        c5.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c5, text="National ID (NIC):", font=("Segoe UI", 8)).pack(anchor=W)
        self.nic_var = tk.StringVar(value=self.emp.get("nic_number", ""))
        tb.Entry(c5, textvariable=self.nic_var).pack(fill=X, pady=(2, 0))

        c6 = tb.Frame(r3)
        c6.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c6, text="Joined Date (YYYY-MM-DD):", font=("Segoe UI", 8)).pack(anchor=W)
        self.joined_var = tk.StringVar(value=self.emp.get("joined_date", ""))
        tb.Entry(c6, textvariable=self.joined_var).pack(fill=X, pady=(2, 0))

        # Row 4: Phone and Email
        r4 = tb.Frame(pad)
        r4.pack(fill=X, pady=(0, 8))

        c7 = tb.Frame(r4)
        c7.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c7, text="Phone Number:", font=("Segoe UI", 8)).pack(anchor=W)
        self.phone_var = tk.StringVar(value=self.emp.get("phone", ""))
        tb.Entry(c7, textvariable=self.phone_var).pack(fill=X, pady=(2, 0))

        c8 = tb.Frame(r4)
        c8.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c8, text="Email Address:", font=("Segoe UI", 8)).pack(anchor=W)
        self.email_var = tk.StringVar(value=self.emp.get("email", ""))
        tb.Entry(c8, textvariable=self.email_var).pack(fill=X, pady=(2, 0))

        # Row 5: Bank Name & Account
        r5 = tb.Frame(pad)
        r5.pack(fill=X, pady=(0, 8))

        c9 = tb.Frame(r5)
        c9.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c9, text="Bank Name:", font=("Segoe UI", 8)).pack(anchor=W)
        self.bank_var = tk.StringVar(value=self.emp.get("bank_name", ""))
        tb.Entry(c9, textvariable=self.bank_var).pack(fill=X, pady=(2, 0))

        c10 = tb.Frame(r5)
        c10.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c10, text="Bank Account Number:", font=("Segoe UI", 8)).pack(anchor=W)
        self.acct_var = tk.StringVar(value=self.emp.get("bank_account", ""))
        tb.Entry(c10, textvariable=self.acct_var).pack(fill=X, pady=(2, 0))

        # Row 6: Basic Monthly Salary & Active Switch
        r6 = tb.Frame(pad)
        r6.pack(fill=X, pady=(0, 16))

        c11 = tb.Frame(r6)
        c11.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(c11, text="Default Pay / Rate (LKR) *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.salary_var = tk.StringVar(value=str(self.emp.get("pay_rate") or self.emp.get("basic_salary", 0.0)))
        tb.Entry(c11, textvariable=self.salary_var).pack(fill=X, pady=(2, 0))

        c12 = tb.Frame(r6)
        c12.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(c12, text="Employment Status:", font=("Segoe UI", 8)).pack(anchor=W)
        self.active_var = tk.BooleanVar(value=bool(self.emp.get("is_active", 1)))
        tb.Checkbutton(c12, text="Active Employee", variable=self.active_var, bootstyle="round-toggle").pack(anchor=W, pady=(6, 0))

        # Flexible pay basis and statutory settings
        r7 = tb.Frame(pad)
        r7.pack(fill=X, pady=(0, 8))
        basis_box = tb.Frame(r7)
        basis_box.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        tb.Label(basis_box, text="Pay Basis:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.pay_basis_var = tk.StringVar(
            value=self.emp.get("pay_basis") or "Monthly Salary"
        )
        tb.Combobox(
            basis_box, textvariable=self.pay_basis_var,
            values=("Monthly Salary", "Per Shift", "Per Day", "Per Hour", "Per Job"),
            state="readonly",
        ).pack(fill=X, pady=(2, 0))

        units_box = tb.Frame(r7)
        units_box.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        tb.Label(units_box, text="Standard Units / Period:", font=("Segoe UI", 8)).pack(anchor=W)
        self.units_var = tk.StringVar(value=str(self.emp.get("standard_units") or 1.0))
        tb.Entry(units_box, textvariable=self.units_var).pack(fill=X, pady=(2, 0))

        r8 = tb.Frame(pad)
        r8.pack(fill=X, pady=(0, 8))
        self.epf_var = tk.BooleanVar(value=bool(self.emp.get("epf_eligible", 1)))
        self.apit_var = tk.BooleanVar(value=bool(self.emp.get("apit_enabled", 1)))
        tb.Checkbutton(
            r8, text="EPF / ETF eligible", variable=self.epf_var,
            bootstyle="round-toggle",
        ).pack(side=LEFT, padx=(0, 20))
        tb.Checkbutton(
            r8, text="Calculate APIT", variable=self.apit_var,
            bootstyle="round-toggle",
        ).pack(side=LEFT)

        tb.Label(
            pad, text="Custom payslip fields (JSON, for example {\"Site\": \"Colombo\"}):",
            font=("Segoe UI", 8),
        ).pack(anchor=W)
        self.custom_fields_var = tk.StringVar(
            value=self.emp.get("custom_fields_json") or "{}"
        )
        tb.Entry(pad, textvariable=self.custom_fields_var).pack(
            fill=X, pady=(2, 10)
        )

        # Buttons
        btns = tb.Frame(pad)
        btns.pack(fill=X, side=BOTTOM)

        tb.Button(btns, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btns, text="Save Employee", bootstyle="success", command=self._save).pack(side=RIGHT)

    def _save(self):
        code = self.code_var.get().strip()
        name = self.name_var.get().strip()
        if not code or not name:
            messagebox.showwarning("Missing Information", "Please enter Employee ID and Full Name.", parent=self)
            return

        try:
            salary = float(self.salary_var.get().replace(",", "").strip())
            standard_units = float(self.units_var.get().replace(",", "").strip())
            custom_fields = json.loads(self.custom_fields_var.get().strip() or "{}")
            if not isinstance(custom_fields, dict):
                raise ValueError("Custom fields must be a JSON object.")
        except (ValueError, json.JSONDecodeError) as exc:
            messagebox.showwarning(
                "Invalid compensation setup", str(exc), parent=self
            )
            return

        data = {
            "company_id": self.company_id,
            "employee_code": code,
            "full_name": name,
            "designation": self.desig_var.get().strip(),
            "department": self.dept_var.get().strip(),
            "nic_number": self.nic_var.get().strip(),
            "joined_date": self.joined_var.get().strip(),
            "phone": self.phone_var.get().strip(),
            "email": self.email_var.get().strip(),
            "bank_name": self.bank_var.get().strip(),
            "bank_account": self.acct_var.get().strip(),
            "basic_salary": salary,
            "pay_basis": self.pay_basis_var.get(),
            "pay_rate": salary,
            "standard_units": standard_units,
            "epf_eligible": 1 if self.epf_var.get() else 0,
            "apit_enabled": 1 if self.apit_var.get() else 0,
            "custom_fields_json": json.dumps(custom_fields, ensure_ascii=False),
            "payslip_template": self.emp.get("payslip_template") or "Standard",
            "is_active": 1 if self.active_var.get() else 0,
        }

        try:
            if self.employee_id:
                db.update_employee(self.employee_id, data)
                messagebox.showinfo("Success", f"Employee {name} updated successfully.", parent=self)
            else:
                db.create_employee(data)
                messagebox.showinfo("Success", f"Employee {name} created successfully.", parent=self)

            if self.on_saved_callback:
                self.on_saved_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save employee:\n{e}", parent=self)


# =========================================================================
# 2. EMPLOYEE MANAGER DIALOG
# =========================================================================

class EmployeeManagerDialog(tb.Toplevel):
    """Directory window to manage staff master profiles."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()

        self.title("Employee & Staff Directory")
        self.geometry("980x600")
        self.minsize(800, 480)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_list()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header Bar
        hdr = tb.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="👥 Employee & Personnel Directory", font=("Segoe UI", 14, "bold")).pack(side=LEFT)

        tb.Button(hdr, text="➕ Add Employee", bootstyle="success", command=self._add_employee).pack(side=RIGHT)

        # Filter Bar
        flt = tb.Frame(container)
        flt.pack(fill=X, pady=(0, 10))

        tb.Label(flt, text="Search:").pack(side=LEFT, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._refresh_list())
        tb.Entry(flt, textvariable=self.search_var, width=28).pack(side=LEFT, padx=(0, 12))

        self.active_filter_var = tk.BooleanVar(value=True)
        tb.Checkbutton(flt, text="Active Employees Only", variable=self.active_filter_var, command=self._refresh_list).pack(side=LEFT)

        # Treeview
        tree_frame = tb.Frame(container)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "code", "name", "designation", "department", "nic", "phone", "basic_salary", "status")
        self.tree = tb.Treeview(tree_frame, columns=cols, show="headings", height=16)

        col_heads = [
            ("id", "ID", 50, "center"),
            ("code", "Emp #", 90, "center"),
            ("name", "Full Name", 180, "w"),
            ("designation", "Designation", 130, "w"),
            ("department", "Department", 120, "w"),
            ("nic", "NIC", 100, "center"),
            ("phone", "Phone", 100, "center"),
            ("basic_salary", "Basic Salary (LKR)", 120, "e"),
            ("status", "Status", 80, "center"),
        ]
        for c, h, w, anch in col_heads:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor=anch)

        sb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_selected())

        # Action Buttons
        act = tb.Frame(container)
        act.pack(fill=X, pady=(10, 0))

        tb.Button(act, text="✏️ Edit", bootstyle="primary-outline", command=self._edit_selected).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🔄 Toggle Status", bootstyle="warning-outline", command=self._toggle_status).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=self._delete_selected).pack(side=LEFT)

        tb.Button(act, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _refresh_list(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        emps = db.get_employees(
            company_id=self.company_id,
            active_only=self.active_filter_var.get(),
            search=self.search_var.get().strip()
        )
        for e in emps:
            st = "Active" if e.get("is_active") else "Inactive"
            sal = float(e.get("basic_salary") or 0.0)
            self.tree.insert("", END, values=(
                e["id"],
                e["employee_code"],
                e["full_name"],
                e.get("designation") or "-",
                e.get("department") or "-",
                e.get("nic_number") or "-",
                e.get("phone") or "-",
                f"{sal:,.2f}",
                st
            ))

    def _add_employee(self):
        EmployeeEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_list)

    def _edit_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Please select an employee to edit.", parent=self)
            return
        emp_id = int(self.tree.item(sel[0])["values"][0])
        EmployeeEntryDialog(self, company_id=self.company_id, employee_id=emp_id, on_saved_callback=self._refresh_list)

    def _toggle_status(self):
        sel = self.tree.selection()
        if not sel:
            return
        emp_id = int(self.tree.item(sel[0])["values"][0])
        emp = db.get_employee(emp_id)
        if emp:
            new_st = 0 if emp.get("is_active") else 1
            db.update_employee(emp_id, {**emp, "is_active": new_st})
            self._refresh_list()

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        emp_id = int(self.tree.item(sel[0])["values"][0])
        name = self.tree.item(sel[0])["values"][2]
        if messagebox.askyesno("Confirm Delete", f"Delete employee '{name}'?\n\nIf they have payroll records, deactivate instead.", parent=self):
            ok, msg = db.delete_employee(emp_id)
            if ok:
                messagebox.showinfo("Deleted", msg, parent=self)
                self._refresh_list()
            else:
                messagebox.showwarning("Cannot Delete", msg, parent=self)


# =========================================================================
# 3. PAYROLL RUN ENTRY / PROCESSING WIZARD
# =========================================================================

class PayrollRunEntryDialog(tb.Toplevel):
    """Wizard to calculate and process a monthly payroll run for all active staff."""

    def __init__(self, parent, company_id=None, on_saved_callback=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_saved_callback = on_saved_callback
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Process Monthly Payroll Run")
        self.geometry("1100x680")
        self.minsize(920, 520)
        self.transient(parent)

        self.line_widgets = []
        self._build_ui()
        self.center_window()
        self._populate_employees()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        # Header controls: Period & Run Date
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="💵 Monthly Payroll Processing Wizard", font=("Segoe UI", 13, "bold")).pack(side=LEFT)

        right_hdr = tb.Frame(hdr)
        right_hdr.pack(side=RIGHT)

        tb.Label(right_hdr, text="Pay Period (YYYY-MM):", font=("Segoe UI", 8, "bold")).pack(side=LEFT, padx=(0, 4))
        cur_period = datetime.now().strftime("%Y-%m")
        self.period_var = tk.StringVar(value=cur_period)
        tb.Entry(right_hdr, textvariable=self.period_var, width=9).pack(side=LEFT, padx=(0, 12))

        tb.Label(right_hdr, text="Date:", font=("Segoe UI", 8, "bold")).pack(side=LEFT, padx=(0, 4))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(right_hdr, textvariable=self.date_var, width=11).pack(side=LEFT)

        # Instructions / Note
        tb.Label(
            root,
            text="Enter allowances, overtime, and statutory deductions for each employee. Net salaries calculate automatically.",
            font=("Segoe UI", 8, "italic"),
            bootstyle="secondary"
        ).pack(anchor=W, pady=(0, 8))

        # Table Headers
        th = tb.Frame(root, bootstyle="dark", padding=(6, 4))
        th.pack(fill=X)

        cols = [
            ("Emp #", 60), ("Name", 150), ("Basic", 90), ("Allowances", 80),
            ("Overtime", 80), ("Gross", 95), ("EPF (8%)", 75), ("Tax/APIT", 75),
            ("Other Ded.", 75), ("Net Pay", 100), ("Payment Mode", 110)
        ]
        for title, w in cols:
            tb.Label(th, text=title, width=int(w / 7.5), font=("Segoe UI", 8, "bold"), bootstyle="inverse-dark").pack(side=LEFT, padx=1)

        # Scrollable Employee Rows Container
        canvas = tk.Canvas(root, highlightthickness=0)
        scrollbar = tb.Scrollbar(root, orient=VERTICAL, command=canvas.yview)
        self.rows_frame = tb.Frame(canvas)

        self.rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        # Bottom Totals & Actions Bar
        bot = tb.Frame(self, padding=16)
        bot.pack(fill=X, side=BOTTOM)

        # Totals Badges
        tot_box = tb.Frame(bot)
        tot_box.pack(side=LEFT)

        self.tot_gross_var = tk.StringVar(value="Gross: LKR 0.00")
        self.tot_ded_var = tk.StringVar(value="Deductions: LKR 0.00")
        self.tot_net_var = tk.StringVar(value="Net Payout: LKR 0.00")

        tb.Label(tot_box, textvariable=self.tot_gross_var, font=("Segoe UI", 9, "bold"), bootstyle="info").pack(side=LEFT, padx=(0, 12))
        tb.Label(tot_box, textvariable=self.tot_ded_var, font=("Segoe UI", 9, "bold"), bootstyle="danger").pack(side=LEFT, padx=(0, 12))
        tb.Label(tot_box, textvariable=self.tot_net_var, font=("Segoe UI", 11, "bold"), bootstyle="success").pack(side=LEFT)

        # Buttons
        btns = tb.Frame(bot)
        btns.pack(side=RIGHT)

        tb.Button(btns, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(btns, text="Confirm & Save Payroll Run", bootstyle="success", command=self._save_run).pack(side=RIGHT)

    def _populate_employees(self):
        active_emps = db.get_employees(company_id=self.company_id, active_only=True)
        if not active_emps:
            tb.Label(self.rows_frame, text="No active employees found. Please add employees first.", font=("Segoe UI", 9, "italic")).pack(pady=20)
            return

        components = db.get_payroll_components(self.company_id)
        for idx, emp in enumerate(active_emps):
            row = tb.Frame(self.rows_frame, padding=(4, 2))
            row.pack(fill=X)

            basis_rate = float(emp.get("pay_rate") or emp.get("basic_salary") or 0.0)
            units = float(emp.get("standard_units") or 1.0)
            basic_preview = basis_rate if (emp.get("pay_basis") or "Monthly Salary") == "Monthly Salary" else basis_rate * units
            earning_default = 0.0
            taxable_earnings = 0.0
            epf_earnings = 0.0
            deduction_default = 0.0
            for component in components:
                value = float(component.get("default_value") or 0.0)
                calc_type = component.get("calculation_type") or "Fixed"
                if calc_type == "Per Unit":
                    value *= units
                elif calc_type == "Percentage":
                    value = basic_preview * value / 100.0
                if component.get("component_type") == "Earning":
                    earning_default += value
                    if component.get("taxable"):
                        taxable_earnings += value
                    if component.get("epf_eligible"):
                        epf_earnings += value
                else:
                    deduction_default += value
            active_loans = db.get_staff_loans(
                self.company_id, employee_id=emp["id"], active_only=True
            )
            loan_default = sum(
                min(float(loan["installment_amount"]), float(loan["outstanding_balance"]))
                for loan in active_loans
            )
            deduction_default += loan_default
            calculated = db.calculate_employee_pay(
                emp, units=units, earnings=earning_default,
                deductions=deduction_default,
                taxable_earnings=taxable_earnings,
                epf_earnings=epf_earnings,
            )
            basic_val = float(calculated["basic_salary"])
            epf_default = float(calculated["epf_employee"])
            apit_default = float(calculated["tax_deduction"])

            tb.Label(row, text=emp.get("employee_code", ""), width=8, anchor=W).pack(side=LEFT, padx=1)
            tb.Label(row, text=emp.get("full_name", "")[:20], width=20, anchor=W).pack(side=LEFT, padx=1)

            basic_ent = tb.Entry(row, width=12)
            basic_ent.insert(0, f"{basic_val:.2f}")
            basic_ent.pack(side=LEFT, padx=1)

            allow_ent = tb.Entry(row, width=10)
            allow_ent.insert(0, f"{earning_default:.2f}")
            allow_ent.pack(side=LEFT, padx=1)

            ot_ent = tb.Entry(row, width=10)
            ot_ent.insert(0, "0.00")
            ot_ent.pack(side=LEFT, padx=1)

            gross_lbl = tb.Label(row, text=f"{basic_val:,.2f}", width=12, anchor=E, font=("Segoe UI", 8, "bold"))
            gross_lbl.pack(side=LEFT, padx=1)

            epf_ent = tb.Entry(row, width=10)
            epf_ent.insert(0, f"{epf_default:.2f}")
            epf_ent.pack(side=LEFT, padx=1)

            tax_ent = tb.Entry(row, width=10)
            tax_ent.insert(0, f"{apit_default:.2f}")
            tax_ent.pack(side=LEFT, padx=1)

            other_ded_ent = tb.Entry(row, width=10)
            other_ded_ent.insert(0, f"{deduction_default:.2f}")
            other_ded_ent.pack(side=LEFT, padx=1)

            net_lbl = tb.Label(row, text=f"{basic_val - epf_default - apit_default:,.2f}", width=14, anchor=E, font=("Segoe UI", 8, "bold"), bootstyle="success")
            net_lbl.pack(side=LEFT, padx=1)

            pm_combo = tb.Combobox(row, values=["Bank Transfer", "Cheque", "Cash"], width=13, state="readonly")
            pm_combo.set("Bank Transfer")
            pm_combo.pack(side=LEFT, padx=1)

            item = {
                "emp_id": emp["id"],
                "employee": emp,
                "staff_loan_deduction": loan_default,
                "basic_ent": basic_ent,
                "allow_ent": allow_ent,
                "ot_ent": ot_ent,
                "epf_ent": epf_ent,
                "tax_ent": tax_ent,
                "other_ded_ent": other_ded_ent,
                "gross_lbl": gross_lbl,
                "net_lbl": net_lbl,
                "pm_combo": pm_combo
            }
            self.line_widgets.append(item)

            # Bind live recalculation
            for ent in (basic_ent, allow_ent, ot_ent, epf_ent, tax_ent, other_ded_ent):
                ent.bind("<KeyRelease>", lambda e: self._recalc_all())

        self._recalc_all()

    def _recalc_all(self):
        tot_gross = 0.0
        tot_ded = 0.0
        tot_net = 0.0

        for w in self.line_widgets:
            try:
                b = float(w["basic_ent"].get().replace(",", "") or 0.0)
                a = float(w["allow_ent"].get().replace(",", "") or 0.0)
                ot = float(w["ot_ent"].get().replace(",", "") or 0.0)
                gross = round(b + a + ot, 2)
                w["gross_lbl"].configure(text=f"{gross:,.2f}")

                epf = float(w["epf_ent"].get().replace(",", "") or 0.0)
                tax = float(w["tax_ent"].get().replace(",", "") or 0.0)
                other = float(w["other_ded_ent"].get().replace(",", "") or 0.0)
                ded = round(epf + tax + other, 2)
                net = round(gross - ded, 2)
                w["net_lbl"].configure(text=f"{net:,.2f}")

                tot_gross += gross
                tot_ded += ded
                tot_net += net
            except Exception:
                pass

        self.tot_gross_var.set(f"Gross: {self.currency} {tot_gross:,.2f}")
        self.tot_ded_var.set(f"Deductions: {self.currency} {tot_ded:,.2f}")
        self.tot_net_var.set(f"Net Payout: {self.currency} {tot_net:,.2f}")

    def _save_run(self):
        period = self.period_var.get().strip()
        run_date = self.date_var.get().strip()
        if not period or not run_date:
            messagebox.showwarning("Missing Fields", "Please enter Pay Period and Run Date.", parent=self)
            return

        lines_data = []
        for w in self.line_widgets:
            try:
                b = float(w["basic_ent"].get().replace(",", "") or 0.0)
                a = float(w["allow_ent"].get().replace(",", "") or 0.0)
                ot = float(w["ot_ent"].get().replace(",", "") or 0.0)
                epf = float(w["epf_ent"].get().replace(",", "") or 0.0)
                tax = float(w["tax_ent"].get().replace(",", "") or 0.0)
                other = float(w["other_ded_ent"].get().replace(",", "") or 0.0)
                lines_data.append({
                    "employee_id": w["emp_id"],
                    "basic_salary": b,
                    "allowances": a,
                    "overtime": ot,
                    "epf_employee": epf,
                    "tax_deduction": tax,
                    "other_deductions": other,
                    "staff_loan_deduction": w.get("staff_loan_deduction", 0.0),
                    "payment_method": w["pm_combo"].get() or "Bank Transfer",
                })
            except ValueError:
                messagebox.showwarning("Invalid Input", "Please verify numeric amounts in all employee rows.", parent=self)
                return

        try:
            run_id = db.create_payroll_run(
                header_data={
                    "company_id": self.company_id,
                    "pay_period": period,
                    "run_date": run_date,
                    "status": "Approved",
                    "approved_by": "HR & Finance Management",
                },
                lines_data=lines_data
            )
            messagebox.showinfo("Success", f"Payroll run for {period} generated successfully (Run #{run_id})!", parent=self)
            if self.on_saved_callback:
                self.on_saved_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save payroll run:\n{e}", parent=self)


# =========================================================================
# 4. PAYROLL REGISTER & PAYSLIP MANAGER DIALOG
# =========================================================================

class PayrollRunDialog(tb.Toplevel):
    """Register window displaying monthly payroll runs, payslips, and voucher payouts."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Monthly Payroll Runs & Salary Slips")
        self.geometry("1020x620")
        self.minsize(840, 500)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_list()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header
        hdr = tb.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="💵 Monthly Payroll Runs & Payslip Generator", font=("Segoe UI", 14, "bold")).pack(side=LEFT)
        tb.Button(hdr, text="➕ Process New Payroll Run", bootstyle="success", command=self._new_run).pack(side=RIGHT)

        # Treeview
        cols = ("id", "period", "run_date", "employees", "total_gross", "total_net", "status", "voucher")
        self.tree = tb.Treeview(container, columns=cols, show="headings", height=14)

        col_heads = [
            ("id", "ID", 50, "center"),
            ("period", "Pay Period", 110, "center"),
            ("run_date", "Run Date", 100, "center"),
            ("employees", "Staff Count", 90, "center"),
            ("total_gross", "Total Gross (LKR)", 140, "e"),
            ("total_net", "Total Net Payout (LKR)", 150, "e"),
            ("status", "Status", 95, "center"),
            ("voucher", "Voucher #", 110, "center"),
        ]
        for c, h, w, anch in col_heads:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor=anch)

        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self._print_summary())

        # Action Buttons
        act = tb.Frame(container)
        act.pack(fill=X, pady=(12, 0))

        tb.Button(act, text="📄 View / Print Salary Slips", bootstyle="primary-outline", command=self._print_payslips).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="📊 Print Payroll Master Sheet", bootstyle="info-outline", command=self._print_summary).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="💰 Generate Bulk Payment Voucher", bootstyle="success", command=self._convert_to_voucher).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🗑️ Delete Run", bootstyle="danger-outline", command=self._delete_run).pack(side=LEFT)

        tb.Button(act, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _refresh_list(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        runs = db.get_payroll_runs(company_id=self.company_id)
        for r in runs:
            tg = float(r.get("total_gross") or 0.0)
            tn = float(r.get("total_net") or 0.0)
            self.tree.insert("", END, values=(
                r["id"],
                r["pay_period"],
                r["run_date"],
                r.get("employee_count", 0),
                f"{tg:,.2f}",
                f"{tn:,.2f}",
                r.get("status", "Draft"),
                r.get("voucher_number") or "Unpaid"
            ))

    def _new_run(self):
        PayrollRunEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_list)

    def _print_summary(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Run", "Please select a payroll run to print summary.", parent=self)
            return
        run_id = int(self.tree.item(sel[0])["values"][0])
        run_data = db.get_payroll_run(run_id)
        if not run_data:
            return

        pdf = payroll_printer.generate_payroll_run_pdf(run_data)
        PdfViewerDialog(self.master, pdf, title="Monthly Payroll Master Summary")

    def _print_payslips(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Run", "Please select a payroll run to generate payslips.", parent=self)
            return
        run_id = int(self.tree.item(sel[0])["values"][0])
        run_data = db.get_payroll_run(run_id)
        if not run_data or not run_data.get("lines"):
            messagebox.showinfo("Empty Run", "No employee records found in this run.", parent=self)
            return

        # Prompt folder destination or preview first
        first_line = run_data["lines"][0]
        pdf = payroll_printer.generate_payslip_pdf(first_line, run_data)
        PdfViewerDialog(self.master, pdf, title=f"Employee Payslip - {first_line.get('employee_name')}")

    def _convert_to_voucher(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Run", "Please select an approved payroll run.", parent=self)
            return
        run_id = int(self.tree.item(sel[0])["values"][0])
        period = self.tree.item(sel[0])["values"][1]
        v_num = self.tree.item(sel[0])["values"][7]

        if v_num != "Unpaid":
            messagebox.showinfo("Already Paid", f"Payroll run {period} is already linked to voucher #{v_num}.", parent=self)
            return

        if messagebox.askyesno("Confirm Voucher Generation", f"Generate bulk payment voucher for {period} payroll?\n\nThis will record a payment voucher for net staff salaries and post to the General Ledger.", parent=self):
            try:
                vid = db.create_voucher_from_payroll_run(run_id)
                messagebox.showinfo("Voucher Created", f"Successfully generated Payment Voucher #{vid} for {period} payroll payout!", parent=self)
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Could not create voucher:\n{e}", parent=self)

    def _delete_run(self):
        sel = self.tree.selection()
        if not sel:
            return
        run_id = int(self.tree.item(sel[0])["values"][0])
        period = self.tree.item(sel[0])["values"][1]

        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete payroll run {period}?", parent=self):
            ok, msg = db.delete_payroll_run(run_id)
            if ok:
                messagebox.showinfo("Deleted", msg, parent=self)
                self._refresh_list()
            else:
                messagebox.showwarning("Cannot Delete", msg, parent=self)


# =========================================================================
# 5. EXPENSE CLAIM ENTRY & MANAGER DIALOGS
# =========================================================================

class ExpenseClaimEntryDialog(tb.Toplevel):
    """Dialog to record an employee expense reimbursement claim."""

    def __init__(self, parent, company_id=None, on_saved_callback=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_saved_callback = on_saved_callback
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("New Employee Expense Claim")
        self.geometry("780x560")
        self.minsize(680, 440)
        self.transient(parent)

        self.line_items = []
        self._build_ui()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        tb.Label(root, text="🧾 Submit Employee Expense Claim", font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 10))

        # Header Details
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 10))

        # Employee Combobox
        c1 = tb.Frame(hdr)
        c1.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        tb.Label(c1, text="Claimant Employee *:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.emps = db.get_employees(company_id=self.company_id, active_only=True)
        self.emp_names = [f"{e['employee_code']} — {e['full_name']}" for e in self.emps]
        self.emp_combo = tb.Combobox(c1, values=self.emp_names, state="readonly")
        if self.emp_names:
            self.emp_combo.current(0)
        self.emp_combo.pack(fill=X, pady=(2, 0))

        # Claim Date
        c2 = tb.Frame(hdr)
        c2.pack(side=LEFT, fill=X, expand=True, padx=(8, 0))
        tb.Label(c2, text="Claim Date:", font=("Segoe UI", 8, "bold")).pack(anchor=W)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(c2, textvariable=self.date_var).pack(fill=X, pady=(2, 0))

        # Items Table
        tb.Label(root, text="Claim Itemized Expenses:", font=("Segoe UI", 9, "bold")).pack(anchor=W, pady=(6, 4))

        tree_frame = tb.Frame(root)
        tree_frame.pack(fill=BOTH, expand=True)

        cols = ("date", "description", "category", "amount")
        self.tree = tb.Treeview(tree_frame, columns=cols, show="headings", height=8)
        self.tree.heading("date", text="Date")
        self.tree.heading("description", text="Description")
        self.tree.heading("category", text="Category")
        self.tree.heading("amount", text=f"Amount ({self.currency})")
        self.tree.column("date", width=90, anchor="center")
        self.tree.column("description", width=300, anchor="w")
        self.tree.column("category", width=140, anchor="w")
        self.tree.column("amount", width=110, anchor="e")
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        # Line input form below
        add_box = tb.Frame(root, padding=(0, 6))
        add_box.pack(fill=X)

        self.item_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(add_box, textvariable=self.item_date_var, width=11).pack(side=LEFT, padx=(0, 4))

        self.item_desc_var = tk.StringVar()
        tb.Entry(add_box, textvariable=self.item_desc_var, width=28).pack(side=LEFT, padx=(0, 4))

        self.item_cat_var = tk.StringVar(value="Travel & Transport")
        tb.Combobox(add_box, textvariable=self.item_cat_var, values=["Travel & Transport", "Meals & Entertainment", "Office Stationery", "Client Meeting", "Accommodation", "General Expense"], width=18).pack(side=LEFT, padx=(0, 4))

        self.item_amt_var = tk.StringVar()
        tb.Entry(add_box, textvariable=self.item_amt_var, width=12).pack(side=LEFT, padx=(0, 4))

        tb.Button(add_box, text="➕ Add Line", bootstyle="primary-outline", command=self._add_line).pack(side=LEFT)
        tb.Button(add_box, text="Remove", bootstyle="danger-outline", command=self._remove_line).pack(side=LEFT, padx=(4, 0))

        # Total & Save footer
        foot = tb.Frame(root)
        foot.pack(fill=X, side=BOTTOM, pady=(10, 0))

        self.total_var = tk.StringVar(value=f"Total: {self.currency} 0.00")
        tb.Label(foot, textvariable=self.total_var, font=("Segoe UI", 11, "bold"), bootstyle="success").pack(side=LEFT)

        tb.Button(foot, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(6, 0))
        tb.Button(foot, text="Submit Claim", bootstyle="success", command=self._save_claim).pack(side=RIGHT)

    def _add_line(self):
        desc = self.item_desc_var.get().strip()
        if not desc:
            return
        try:
            amt = float(self.item_amt_var.get().replace(",", "").strip())
        except ValueError:
            return

        item = {
            "date": self.item_date_var.get().strip(),
            "description": desc,
            "category": self.item_cat_var.get().strip(),
            "amount": amt
        }
        self.line_items.append(item)
        self.tree.insert("", END, values=(item["date"], item["description"], item["category"], f"{amt:,.2f}"))
        self.item_desc_var.set("")
        self.item_amt_var.set("")
        self._update_total()

    def _remove_line(self):
        sel = self.tree.selection()
        if sel:
            idx = self.tree.index(sel[0])
            self.tree.delete(sel[0])
            if idx < len(self.line_items):
                self.line_items.pop(idx)
            self._update_total()

    def _update_total(self):
        tot = sum(l["amount"] for l in self.line_items)
        self.total_var.set(f"Total: {self.currency} {tot:,.2f}")

    def _save_claim(self):
        if not self.line_items:
            messagebox.showwarning("Empty Claim", "Please add at least one expense line item.", parent=self)
            return

        c_idx = self.emp_combo.current()
        if c_idx < 0 or c_idx >= len(self.emps):
            messagebox.showwarning("Select Employee", "Please select an employee.", parent=self)
            return

        emp_id = self.emps[c_idx]["id"]
        c_date = self.date_var.get().strip()

        try:
            claim_id = db.create_expense_claim(
                header_data={
                    "company_id": self.company_id,
                    "employee_id": emp_id,
                    "claim_date": c_date,
                    "status": "Pending",
                },
                lines_data=self.line_items
            )
            messagebox.showinfo("Success", f"Expense claim submitted successfully (ID #{claim_id})!", parent=self)
            if self.on_saved_callback:
                self.on_saved_callback()
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to submit claim:\n{e}", parent=self)


class ExpenseClaimDialog(tb.Toplevel):
    """Register window displaying employee expense claims and reimbursement payouts."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.currency = db.get_company_base_currency(self.company_id) or "LKR"

        self.title("Employee Expense Claims & Reimbursements")
        self.geometry("980x600")
        self.minsize(800, 480)
        self.transient(parent)

        self._build_ui()
        self.center_window()
        self._refresh_list()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_ui(self):
        container = tb.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header
        hdr = tb.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        tb.Label(hdr, text="🧾 Employee Expense Claims Register", font=("Segoe UI", 14, "bold")).pack(side=LEFT)
        tb.Button(hdr, text="➕ Submit Expense Claim", bootstyle="success", command=self._new_claim).pack(side=RIGHT)

        # Treeview
        cols = ("id", "claim_number", "date", "employee", "department", "amount", "status", "voucher")
        self.tree = tb.Treeview(container, columns=cols, show="headings", height=15)

        col_heads = [
            ("id", "ID", 50, "center"),
            ("claim_number", "Claim #", 120, "center"),
            ("date", "Date", 95, "center"),
            ("employee", "Employee Name", 180, "w"),
            ("department", "Department", 120, "w"),
            ("amount", "Amount (LKR)", 120, "e"),
            ("status", "Status", 95, "center"),
            ("voucher", "Voucher #", 100, "center"),
        ]
        for c, h, w, anch in col_heads:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor=anch)

        self.tree.pack(fill=BOTH, expand=True)

        # Action Buttons
        act = tb.Frame(container)
        act.pack(fill=X, pady=(12, 0))

        tb.Button(act, text="✅ Approve Claim", bootstyle="success-outline", command=self._approve_claim).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="💰 Reimburse via Voucher", bootstyle="primary", command=self._reimburse_claim).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="❌ Reject Claim", bootstyle="warning-outline", command=self._reject_claim).pack(side=LEFT, padx=(0, 6))
        tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=self._delete_claim).pack(side=LEFT)

        tb.Button(act, text="Close", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _refresh_list(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        claims = db.get_expense_claims(company_id=self.company_id)
        for c in claims:
            amt = float(c.get("total_amount") or 0.0)
            self.tree.insert("", END, values=(
                c["id"],
                c["claim_number"],
                c["claim_date"],
                c.get("employee_name", ""),
                c.get("department", "-"),
                f"{amt:,.2f}",
                c.get("status", "Pending"),
                c.get("voucher_number") or "-"
            ))

    def _new_claim(self):
        ExpenseClaimEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_list)

    def _approve_claim(self):
        sel = self.tree.selection()
        if not sel:
            return
        cid = int(self.tree.item(sel[0])["values"][0])
        db.update_expense_claim_status(cid, "Approved", approved_by="Management")
        self._refresh_list()

    def _reject_claim(self):
        sel = self.tree.selection()
        if not sel:
            return
        cid = int(self.tree.item(sel[0])["values"][0])
        db.update_expense_claim_status(cid, "Rejected")
        self._refresh_list()

    def _reimburse_claim(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Claim", "Please select an approved expense claim to reimburse.", parent=self)
            return
        cid = int(self.tree.item(sel[0])["values"][0])
        c_num = self.tree.item(sel[0])["values"][1]
        st = self.tree.item(sel[0])["values"][6]
        v_num = self.tree.item(sel[0])["values"][7]

        if st == "Paid" or v_num != "-":
            messagebox.showinfo("Already Paid", f"Claim {c_num} is already reimbursed (Voucher {v_num}).", parent=self)
            return

        if messagebox.askyesno("Confirm Reimbursement", f"Generate Payment Voucher to reimburse {c_num}?\n\nThis will disburse funds to the employee and post to the General Ledger.", parent=self):
            try:
                vid = db.create_voucher_from_expense_claim(cid)
                messagebox.showinfo("Reimbursed", f"Successfully generated Payment Voucher #{vid} for claim {c_num}!", parent=self)
                self._refresh_list()
            except Exception as e:
                messagebox.showerror("Error", f"Could not create voucher:\n{e}", parent=self)

    def _delete_claim(self):
        sel = self.tree.selection()
        if not sel:
            return
        cid = int(self.tree.item(sel[0])["values"][0])
        c_num = self.tree.item(sel[0])["values"][1]

        if messagebox.askyesno("Confirm Deletion", f"Delete claim {c_num}?", parent=self):
            ok, msg = db.delete_expense_claim(cid)
            if ok:
                messagebox.showinfo("Deleted", msg, parent=self)
                self._refresh_list()
            else:
                messagebox.showwarning("Cannot Delete", msg, parent=self)


# =========================================================================
# 6. UNIFIED PAYROLL & HR MASTER DIALOG
# =========================================================================

class PayrollMasterDialog(tb.Toplevel):
    """
    Unified Tabbed HR & Payroll Suite:
    - Tab 1: 👥 Staff Directory & Compensation
    - Tab 2: 💵 Monthly Payroll Runs & Payslips
    - Tab 3: 🧾 Employee Expense Claims & Reimbursements
    """

    def __init__(self, parent, company_id=None, initial_tab=0):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()

        self.title("Payroll, Staff & Expense Claims Manager (v4.0)")
        self.geometry("1140x700")
        self.minsize(960, 560)
        self.transient(parent)

        self._build_tabs(initial_tab)
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build_tabs(self, initial_tab=0):
        nb = tb.Notebook(self)
        nb.pack(fill=BOTH, expand=True, padx=12, pady=12)

        # Tab 1: Employees
        t1 = tb.Frame(nb, padding=8)
        nb.add(t1, text="  👥 Employees Directory  ")
        self._build_embedded_employees(t1)

        # Tab 2: Payroll Runs
        t2 = tb.Frame(nb, padding=8)
        nb.add(t2, text="  💵 Monthly Payroll & Payslips  ")
        self._build_embedded_payroll(t2)

        # Tab 3: Expense Claims
        t3 = tb.Frame(nb, padding=8)
        nb.add(t3, text="  🧾 Expense Claims & Reimbursements  ")
        self._build_embedded_claims(t3)

        # Tab 4: statutory rates and configurable pay components
        t4 = tb.Frame(nb, padding=8)
        nb.add(t4, text="  ⚙ Payroll Setup  ")
        self._build_payroll_setup(t4)

        t5 = tb.Frame(nb, padding=8)
        nb.add(t5, text="  Staff Loans  ")
        self._build_staff_loans(t5)

        nb.select(initial_tab)

    def _build_embedded_employees(self, frame):
        EmployeeManagerDialog._build_ui_embedded(self, frame)

    def _build_embedded_payroll(self, frame):
        PayrollRunDialog._build_ui_embedded(self, frame)

    def _build_embedded_claims(self, frame):
        ExpenseClaimDialog._build_ui_embedded(self, frame)

    def _build_staff_loans(self, container):
        tb.Label(
            container, text="Staff Loan Register", font=("Segoe UI", 12, "bold")
        ).pack(anchor=W, pady=(0, 8))
        tb.Label(
            container,
            text="Issuing a loan posts Staff Loan Receivable against the selected cash/bank account.",
            bootstyle="secondary",
        ).pack(anchor=W, pady=(0, 10))

        employees = db.get_employees(self.company_id, active_only=True)
        self._loan_employee_map = {
            f"[{row['employee_code']}] {row['full_name']}": row["id"]
            for row in employees
        }
        accounts = db.get_chart_of_accounts(self.company_id, active_only=True)
        self._loan_account_map = {
            f"[{row['account_code']}] {row['account_name']}": row["id"]
            for row in accounts
        }
        asset_choices = [
            label for label, account_id in self._loan_account_map.items()
            if next(row for row in accounts if row["id"] == account_id)["account_type"] == "Asset"
        ]
        payment_choices = [
            label for label, account_id in self._loan_account_map.items()
            if any(
                word in next(row for row in accounts if row["id"] == account_id)["account_name"].lower()
                for word in ("cash", "bank")
            )
        ]
        form = tb.Labelframe(container, text="Issue staff loan", padding=10)
        form.pack(fill=X, pady=(0, 10))
        self._loan_employee_var = tk.StringVar()
        self._loan_principal_var = tk.StringVar()
        self._loan_installment_var = tk.StringVar()
        self._loan_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self._loan_asset_var = tk.StringVar()
        self._loan_payment_var = tk.StringVar()
        fields = (
            ("Employee", self._loan_employee_var, list(self._loan_employee_map), 22),
            ("Principal", self._loan_principal_var, None, 10),
            ("Installment", self._loan_installment_var, None, 10),
            ("Date", self._loan_date_var, None, 11),
            ("Loan asset", self._loan_asset_var, asset_choices, 22),
            ("Pay from", self._loan_payment_var, payment_choices, 22),
        )
        for label, variable, values, width in fields:
            tb.Label(form, text=label).pack(side=LEFT, padx=(0, 3))
            widget = (
                tb.Combobox(form, textvariable=variable, values=values, state="readonly", width=width)
                if values is not None else tb.Entry(form, textvariable=variable, width=width)
            )
            widget.pack(side=LEFT, padx=(0, 8))
        tb.Button(
            form, text="Issue loan", bootstyle="success",
            command=self._issue_staff_loan,
        ).pack(side=RIGHT)

        columns = ("employee", "date", "principal", "outstanding", "installment", "status")
        self._loan_tree = tb.Treeview(container, columns=columns, show="headings")
        for column, heading, width in (
            ("employee", "Employee", 250), ("date", "Loan date", 100),
            ("principal", "Principal", 120), ("outstanding", "Outstanding", 120),
            ("installment", "Payroll installment", 130), ("status", "Status", 90),
        ):
            self._loan_tree.heading(column, text=heading)
            self._loan_tree.column(column, width=width)
        self._loan_tree.pack(fill=BOTH, expand=True)
        self._refresh_staff_loans()

    def _issue_staff_loan(self):
        try:
            employee_id = self._loan_employee_map.get(self._loan_employee_var.get())
            asset_id = self._loan_account_map.get(self._loan_asset_var.get())
            payment_id = self._loan_account_map.get(self._loan_payment_var.get())
            if not all((employee_id, asset_id, payment_id)):
                raise ValueError("Select employee, staff-loan asset, and payment account.")
            db.create_staff_loan({
                "company_id": self.company_id,
                "employee_id": employee_id,
                "loan_date": self._loan_date_var.get(),
                "principal": float(self._loan_principal_var.get().replace(",", "")),
                "installment_amount": float(self._loan_installment_var.get().replace(",", "")),
                "asset_account_id": asset_id,
                "payment_account_id": payment_id,
            })
            self._loan_principal_var.set("")
            self._loan_installment_var.set("")
            self._refresh_staff_loans()
            messagebox.showinfo("Staff loan", "Loan issued and posted to the ledger.", parent=self)
        except Exception as exc:
            messagebox.showerror("Staff loan", str(exc), parent=self)

    def _refresh_staff_loans(self):
        self._loan_tree.delete(*self._loan_tree.get_children())
        for loan in db.get_staff_loans(self.company_id):
            self._loan_tree.insert("", END, values=(
                f"[{loan['employee_code']}] {loan['employee_name']}", loan["loan_date"],
                f"{float(loan['principal']):,.2f}",
                f"{float(loan['outstanding_balance']):,.2f}",
                f"{float(loan['installment_amount']):,.2f}", loan["status"],
            ))
    def _build_payroll_setup(self, container):
        settings = db.get_payroll_settings(self.company_id)
        header = tb.Frame(container)
        header.pack(fill=X, pady=(0, 10))
        tb.Label(
            header, text="Sri Lanka statutory settings",
            font=("Segoe UI", 12, "bold"),
        ).pack(side=LEFT)
        tb.Label(
            header,
            text="Rates are effective-dated and editable when legislation changes.",
            bootstyle="secondary",
        ).pack(side=LEFT, padx=(12, 0))

        rates = tb.Labelframe(container, text="Contribution and payslip settings", padding=10)
        rates.pack(fill=X, pady=(0, 12))
        self._payroll_setting_vars = {
            "effective_from": tk.StringVar(value=settings.get("effective_from", "2025-04-01")),
            "epf_employee_rate": tk.StringVar(value=str(settings.get("epf_employee_rate", 8.0))),
            "epf_employer_rate": tk.StringVar(value=str(settings.get("epf_employer_rate", 12.0))),
            "etf_employer_rate": tk.StringVar(value=str(settings.get("etf_employer_rate", 3.0))),
            "payslip_title": tk.StringVar(value=settings.get("payslip_title", "CONFIDENTIAL PAYSLIP")),
        }
        fields = (
            ("Effective from", "effective_from", 12),
            ("Employee EPF %", "epf_employee_rate", 8),
            ("Employer EPF %", "epf_employer_rate", 8),
            ("Employer ETF %", "etf_employer_rate", 8),
            ("Payslip title", "payslip_title", 24),
        )
        for label, key, width in fields:
            tb.Label(rates, text=label).pack(side=LEFT, padx=(0, 4))
            tb.Entry(
                rates, textvariable=self._payroll_setting_vars[key], width=width
            ).pack(side=LEFT, padx=(0, 10))
        tb.Button(
            rates, text="Save settings", bootstyle="success",
            command=self._save_payroll_settings,
        ).pack(side=RIGHT)

        editor = tb.Labelframe(container, text="Add pay component", padding=10)
        editor.pack(fill=X, pady=(0, 10))
        self._component_name_var = tk.StringVar()
        self._component_type_var = tk.StringVar(value="Earning")
        self._component_calc_var = tk.StringVar(value="Fixed")
        self._component_value_var = tk.StringVar(value="0.00")
        for label, variable, values, width in (
            ("Name", self._component_name_var, None, 24),
            ("Type", self._component_type_var, ("Earning", "Deduction"), 12),
            ("Calculation", self._component_calc_var, ("Fixed", "Per Unit", "Percentage"), 13),
            ("Default", self._component_value_var, None, 10),
        ):
            tb.Label(editor, text=label).pack(side=LEFT, padx=(0, 4))
            widget = (
                tb.Combobox(editor, textvariable=variable, values=values, state="readonly", width=width)
                if values else tb.Entry(editor, textvariable=variable, width=width)
            )
            widget.pack(side=LEFT, padx=(0, 10))
        tb.Button(
            editor, text="Add component", bootstyle="primary",
            command=self._add_payroll_component,
        ).pack(side=RIGHT)

        columns = ("name", "type", "calculation", "value", "taxable", "epf")
        self._component_tree = tb.Treeview(
            container, columns=columns, show="headings", height=12
        )
        for column, heading, width in (
            ("name", "Component", 260), ("type", "Type", 110),
            ("calculation", "Calculation", 130), ("value", "Default", 100),
            ("taxable", "Taxable", 80), ("epf", "EPF Eligible", 90),
        ):
            self._component_tree.heading(column, text=heading)
            self._component_tree.column(column, width=width)
        self._component_tree.pack(fill=BOTH, expand=True)
        self._refresh_payroll_components()

    def _save_payroll_settings(self):
        try:
            values = {
                key: variable.get().strip()
                for key, variable in self._payroll_setting_vars.items()
            }
            values["apit_enabled"] = 1
            db.save_payroll_settings(self.company_id, values)
            messagebox.showinfo("Payroll setup", "Statutory and payslip settings saved.", parent=self)
        except Exception as exc:
            messagebox.showerror("Payroll setup", str(exc), parent=self)

    def _add_payroll_component(self):
        try:
            db.save_payroll_component({
                "company_id": self.company_id,
                "name": self._component_name_var.get(),
                "component_type": self._component_type_var.get(),
                "calculation_type": self._component_calc_var.get(),
                "default_value": float(self._component_value_var.get() or 0),
            })
            self._component_name_var.set("")
            self._component_value_var.set("0.00")
            self._refresh_payroll_components()
        except Exception as exc:
            messagebox.showerror("Pay component", str(exc), parent=self)

    def _refresh_payroll_components(self):
        self._component_tree.delete(*self._component_tree.get_children())
        for component in db.get_payroll_components(self.company_id):
            self._component_tree.insert("", END, values=(
                component["name"], component["component_type"],
                component["calculation_type"],
                f"{float(component['default_value']):,.2f}",
                "Yes" if component.get("taxable") else "No",
                "Yes" if component.get("epf_eligible") else "No",
            ))

# Attach embedded builders
def _build_ui_embedded_emp(self, container):
    # Top
    hdr = tb.Frame(container)
    hdr.pack(fill=X, pady=(0, 8))
    tb.Label(hdr, text="👥 Staff Master Profiles", font=("Segoe UI", 12, "bold")).pack(side=LEFT)
    tb.Button(hdr, text="➕ Add Employee", bootstyle="success", command=lambda: EmployeeEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_emp_list)).pack(side=RIGHT)

    # Filter
    flt = tb.Frame(container)
    flt.pack(fill=X, pady=(0, 8))
    tb.Label(flt, text="Search:").pack(side=LEFT, padx=(0, 4))
    self._emp_search_var = tk.StringVar()
    self._emp_search_var.trace_add("write", lambda *a: self._refresh_emp_list())
    tb.Entry(flt, textvariable=self._emp_search_var, width=24).pack(side=LEFT, padx=(0, 10))

    self._emp_active_var = tk.BooleanVar(value=True)
    tb.Checkbutton(flt, text="Active Staff Only", variable=self._emp_active_var, command=self._refresh_emp_list).pack(side=LEFT)

    # Treeview
    tf = tb.Frame(container)
    tf.pack(fill=BOTH, expand=True)
    cols = ("id", "code", "name", "designation", "department", "nic", "phone", "basic_salary", "status")
    self._emp_tree = tb.Treeview(tf, columns=cols, show="headings", height=14)
    col_heads = [
        ("id", "ID", 45, "center"), ("code", "Emp #", 85, "center"),
        ("name", "Full Name", 170, "w"), ("designation", "Designation", 120, "w"),
        ("department", "Department", 110, "w"), ("nic", "NIC", 95, "center"),
        ("phone", "Phone", 95, "center"), ("basic_salary", "Basic Salary (LKR)", 115, "e"),
        ("status", "Status", 75, "center")
    ]
    for c, h, w, anch in col_heads:
        self._emp_tree.heading(c, text=h)
        self._emp_tree.column(c, width=w, anchor=anch)
    self._emp_tree.pack(side=LEFT, fill=BOTH, expand=True)

    sb = tb.Scrollbar(tf, orient=VERTICAL, command=self._emp_tree.yview)
    self._emp_tree.configure(yscrollcommand=sb.set)
    sb.pack(side=RIGHT, fill=Y)

    # Action bar
    act = tb.Frame(container)
    act.pack(fill=X, pady=(8, 0))
    tb.Button(act, text="✏️ Edit", bootstyle="primary-outline", command=lambda: self._edit_emp_selected()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="🔄 Toggle Status", bootstyle="warning-outline", command=lambda: self._toggle_emp_status()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=lambda: self._delete_emp_selected()).pack(side=LEFT)

    self._refresh_emp_list()

def _refresh_emp_list(self):
    for i in self._emp_tree.get_children():
        self._emp_tree.delete(i)
    emps = db.get_employees(
        company_id=self.company_id,
        active_only=self._emp_active_var.get(),
        search=self._emp_search_var.get().strip()
    )
    for e in emps:
        st = "Active" if e.get("is_active") else "Inactive"
        sal = float(e.get("basic_salary") or 0.0)
        self._emp_tree.insert("", END, values=(
            e["id"], e["employee_code"], e["full_name"],
            e.get("designation") or "-", e.get("department") or "-",
            e.get("nic_number") or "-", e.get("phone") or "-",
            f"{sal:,.2f}", st
        ))

def _edit_emp_selected(self):
    sel = self._emp_tree.selection()
    if not sel:
        return
    emp_id = int(self._emp_tree.item(sel[0])["values"][0])
    EmployeeEntryDialog(self, company_id=self.company_id, employee_id=emp_id, on_saved_callback=self._refresh_emp_list)

def _toggle_emp_status(self):
    sel = self._emp_tree.selection()
    if not sel:
        return
    emp_id = int(self._emp_tree.item(sel[0])["values"][0])
    emp = db.get_employee(emp_id)
    if emp:
        db.update_employee(emp_id, {**emp, "is_active": 0 if emp.get("is_active") else 1})
        self._refresh_emp_list()

def _delete_emp_selected(self):
    sel = self._emp_tree.selection()
    if not sel:
        return
    emp_id = int(self._emp_tree.item(sel[0])["values"][0])
    name = self._emp_tree.item(sel[0])["values"][2]
    if messagebox.askyesno("Confirm", f"Delete employee '{name}'?", parent=self):
        ok, msg = db.delete_employee(emp_id)
        if ok:
            messagebox.showinfo("Deleted", msg, parent=self)
            self._refresh_emp_list()
        else:
            messagebox.showwarning("Cannot Delete", msg, parent=self)

EmployeeManagerDialog._build_ui_embedded = _build_ui_embedded_emp
PayrollMasterDialog._refresh_emp_list = _refresh_emp_list
PayrollMasterDialog._edit_emp_selected = _edit_emp_selected
PayrollMasterDialog._toggle_emp_status = _toggle_emp_status
PayrollMasterDialog._delete_emp_selected = _delete_emp_selected


# Embedded Payroll Runs
def _build_ui_embedded_pr(self, container):
    hdr = tb.Frame(container)
    hdr.pack(fill=X, pady=(0, 8))
    tb.Label(hdr, text="💵 Monthly Payroll Runs", font=("Segoe UI", 12, "bold")).pack(side=LEFT)
    tb.Button(hdr, text="➕ Process Payroll Run", bootstyle="success", command=lambda: PayrollRunEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_pr_list)).pack(side=RIGHT)

    tf = tb.Frame(container)
    tf.pack(fill=BOTH, expand=True)
    cols = ("id", "period", "run_date", "employees", "total_gross", "total_net", "status", "voucher")
    self._pr_tree = tb.Treeview(tf, columns=cols, show="headings", height=14)
    col_heads = [
        ("id", "ID", 45, "center"), ("period", "Pay Period", 110, "center"),
        ("run_date", "Run Date", 100, "center"), ("employees", "Staff Count", 90, "center"),
        ("total_gross", "Total Gross (LKR)", 140, "e"), ("total_net", "Total Net Payout (LKR)", 150, "e"),
        ("status", "Status", 95, "center"), ("voucher", "Voucher #", 110, "center")
    ]
    for c, h, w, anch in col_heads:
        self._pr_tree.heading(c, text=h)
        self._pr_tree.column(c, width=w, anchor=anch)
    self._pr_tree.pack(side=LEFT, fill=BOTH, expand=True)

    sb = tb.Scrollbar(tf, orient=VERTICAL, command=self._pr_tree.yview)
    self._pr_tree.configure(yscrollcommand=sb.set)
    sb.pack(side=RIGHT, fill=Y)

    act = tb.Frame(container)
    act.pack(fill=X, pady=(8, 0))
    tb.Button(act, text="📄 Print Payslip", bootstyle="primary-outline", command=lambda: self._pr_print_payslip()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="📊 Print Master Summary", bootstyle="info-outline", command=lambda: self._pr_print_summary()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="💰 Generate Payment Voucher", bootstyle="success", command=lambda: self._pr_convert_voucher()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=lambda: self._pr_delete_run()).pack(side=LEFT)

    self._refresh_pr_list()

def _refresh_pr_list(self):
    for i in self._pr_tree.get_children():
        self._pr_tree.delete(i)
    runs = db.get_payroll_runs(company_id=self.company_id)
    for r in runs:
        tg = float(r.get("total_gross") or 0.0)
        tn = float(r.get("total_net") or 0.0)
        self._pr_tree.insert("", END, values=(
            r["id"], r["pay_period"], r["run_date"], r.get("employee_count", 0),
            f"{tg:,.2f}", f"{tn:,.2f}", r.get("status", "Draft"),
            r.get("voucher_number") or "Unpaid"
        ))

def _pr_print_payslip(self):
    sel = self._pr_tree.selection()
    if not sel:
        return
    run_id = int(self._pr_tree.item(sel[0])["values"][0])
    rd = db.get_payroll_run(run_id)
    if rd and rd.get("lines"):
        pdf = payroll_printer.generate_payslip_pdf(rd["lines"][0], rd)
        PdfViewerDialog(self.master, pdf, title=f"Employee Payslip - {rd['lines'][0].get('employee_name')}")

def _pr_print_summary(self):
    sel = self._pr_tree.selection()
    if not sel:
        return
    run_id = int(self._pr_tree.item(sel[0])["values"][0])
    rd = db.get_payroll_run(run_id)
    if rd:
        pdf = payroll_printer.generate_payroll_run_pdf(rd)
        PdfViewerDialog(self.master, pdf, title=f"Payroll Summary - {rd.get('pay_period')}")

def _pr_convert_voucher(self):
    sel = self._pr_tree.selection()
    if not sel:
        return
    run_id = int(self._pr_tree.item(sel[0])["values"][0])
    period = self._pr_tree.item(sel[0])["values"][1]
    v_num = self._pr_tree.item(sel[0])["values"][7]
    if v_num != "Unpaid":
        messagebox.showinfo("Already Paid", f"Run {period} already has voucher #{v_num}.", parent=self)
        return
    if messagebox.askyesno("Confirm", f"Create payment voucher for {period} payroll?", parent=self):
        try:
            vid = db.create_voucher_from_payroll_run(run_id)
            messagebox.showinfo("Success", f"Voucher #{vid} generated for {period} payroll!", parent=self)
            self._refresh_pr_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed:\n{e}", parent=self)

def _pr_delete_run(self):
    sel = self._pr_tree.selection()
    if not sel:
        return
    run_id = int(self._pr_tree.item(sel[0])["values"][0])
    period = self._pr_tree.item(sel[0])["values"][1]
    if messagebox.askyesno("Confirm", f"Delete payroll run {period}?", parent=self):
        ok, msg = db.delete_payroll_run(run_id)
        if ok:
            messagebox.showinfo("Deleted", msg, parent=self)
            self._refresh_pr_list()
        else:
            messagebox.showwarning("Cannot Delete", msg, parent=self)

PayrollRunDialog._build_ui_embedded = _build_ui_embedded_pr
PayrollMasterDialog._refresh_pr_list = _refresh_pr_list
PayrollMasterDialog._pr_print_payslip = _pr_print_payslip
PayrollMasterDialog._pr_print_summary = _pr_print_summary
PayrollMasterDialog._pr_convert_voucher = _pr_convert_voucher
PayrollMasterDialog._pr_delete_run = _pr_delete_run


# Embedded Expense Claims
def _build_ui_embedded_ec(self, container):
    hdr = tb.Frame(container)
    hdr.pack(fill=X, pady=(0, 8))
    tb.Label(hdr, text="🧾 Employee Expense Claims", font=("Segoe UI", 12, "bold")).pack(side=LEFT)
    tb.Button(hdr, text="➕ Submit Expense Claim", bootstyle="success", command=lambda: ExpenseClaimEntryDialog(self, company_id=self.company_id, on_saved_callback=self._refresh_ec_list)).pack(side=RIGHT)

    tf = tb.Frame(container)
    tf.pack(fill=BOTH, expand=True)
    cols = ("id", "claim_number", "date", "employee", "department", "amount", "status", "voucher")
    self._ec_tree = tb.Treeview(tf, columns=cols, show="headings", height=14)
    col_heads = [
        ("id", "ID", 45, "center"), ("claim_number", "Claim #", 120, "center"),
        ("date", "Date", 95, "center"), ("employee", "Employee Name", 180, "w"),
        ("department", "Department", 120, "w"), ("amount", "Amount (LKR)", 120, "e"),
        ("status", "Status", 95, "center"), ("voucher", "Voucher #", 100, "center")
    ]
    for c, h, w, anch in col_heads:
        self._ec_tree.heading(c, text=h)
        self._ec_tree.column(c, width=w, anchor=anch)
    self._ec_tree.pack(side=LEFT, fill=BOTH, expand=True)

    sb = tb.Scrollbar(tf, orient=VERTICAL, command=self._ec_tree.yview)
    self._ec_tree.configure(yscrollcommand=sb.set)
    sb.pack(side=RIGHT, fill=Y)

    act = tb.Frame(container)
    act.pack(fill=X, pady=(8, 0))
    tb.Button(act, text="✅ Approve Claim", bootstyle="success-outline", command=lambda: self._ec_approve()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="💰 Reimburse via Voucher", bootstyle="primary", command=lambda: self._ec_reimburse()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="❌ Reject", bootstyle="warning-outline", command=lambda: self._ec_reject()).pack(side=LEFT, padx=(0, 4))
    tb.Button(act, text="🗑️ Delete", bootstyle="danger-outline", command=lambda: self._ec_delete()).pack(side=LEFT)

    self._refresh_ec_list()

def _refresh_ec_list(self):
    for i in self._ec_tree.get_children():
        self._ec_tree.delete(i)
    claims = db.get_expense_claims(company_id=self.company_id)
    for c in claims:
        amt = float(c.get("total_amount") or 0.0)
        self._ec_tree.insert("", END, values=(
            c["id"], c["claim_number"], c["claim_date"],
            c.get("employee_name", ""), c.get("department", "-"),
            f"{amt:,.2f}", c.get("status", "Pending"),
            c.get("voucher_number") or "-"
        ))

def _ec_approve(self):
    sel = self._ec_tree.selection()
    if not sel:
        return
    cid = int(self._ec_tree.item(sel[0])["values"][0])
    db.update_expense_claim_status(cid, "Approved", approved_by="Management")
    self._refresh_ec_list()

def _ec_reject(self):
    sel = self._ec_tree.selection()
    if not sel:
        return
    cid = int(self._ec_tree.item(sel[0])["values"][0])
    db.update_expense_claim_status(cid, "Rejected")
    self._refresh_ec_list()

def _ec_reimburse(self):
    sel = self._ec_tree.selection()
    if not sel:
        return
    cid = int(self._ec_tree.item(sel[0])["values"][0])
    c_num = self._ec_tree.item(sel[0])["values"][1]
    st = self._ec_tree.item(sel[0])["values"][6]
    v_num = self._ec_tree.item(sel[0])["values"][7]
    if st == "Paid" or v_num != "-":
        messagebox.showinfo("Already Paid", f"Claim {c_num} already reimbursed (Voucher {v_num}).", parent=self)
        return
    if messagebox.askyesno("Confirm", f"Create payment voucher for claim {c_num}?", parent=self):
        try:
            vid = db.create_voucher_from_expense_claim(cid)
            messagebox.showinfo("Success", f"Voucher #{vid} generated for claim {c_num}!", parent=self)
            self._refresh_ec_list()
        except Exception as e:
            messagebox.showerror("Error", f"Failed:\n{e}", parent=self)

def _ec_delete(self):
    sel = self._ec_tree.selection()
    if not sel:
        return
    cid = int(self._ec_tree.item(sel[0])["values"][0])
    c_num = self._ec_tree.item(sel[0])["values"][1]
    if messagebox.askyesno("Confirm", f"Delete claim {c_num}?", parent=self):
        ok, msg = db.delete_expense_claim(cid)
        if ok:
            messagebox.showinfo("Deleted", msg, parent=self)
            self._refresh_ec_list()
        else:
            messagebox.showwarning("Cannot Delete", msg, parent=self)

ExpenseClaimDialog._build_ui_embedded = _build_ui_embedded_ec
PayrollMasterDialog._refresh_ec_list = _refresh_ec_list
PayrollMasterDialog._ec_approve = _ec_approve
PayrollMasterDialog._ec_reject = _ec_reject
PayrollMasterDialog._ec_reimburse = _ec_reimburse
PayrollMasterDialog._ec_delete = _ec_delete
