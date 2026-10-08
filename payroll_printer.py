"""
payroll_printer.py
PDF Generation Engine for Employee Salary Slips (Payslips) & Payroll Summaries (v4.0).

Generates professional, print-ready A4 documents with:
- Dynamic company profile branding & logo
- Comprehensive employee credentials (Code, Name, Designation, Department, NIC, Bank)
- Transparent Earnings & Deductions tabular breakdown
- Large Net Pay summary badge with Amount-in-Words conversion
- Dual-signatory sign-off blocks (Employee Acknowledgment & Authorized HR/Finance Signatory)
- Bulk Monthly Payroll Summary Report for executive audit & bank transfer dispatch
"""

import os
import tempfile
import json
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from PIL import Image as PILImage

import database as db
from check_printer import amount_to_words


def _draw_wrapped_text(c, text: str, x: float, y: float, max_w: float, font_name: str, font_size: float, leading: float, max_lines: int = 4) -> float:
    """Helper to draw word-wrapped text within max_w and return final y position."""
    c.setFont(font_name, font_size)
    words = (text or "").split()
    if not words:
        return y

    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        if c.stringWidth(test_line, font_name, font_size) <= max_w:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            if len(lines) >= max_lines - 1:
                break
    if current_line and len(lines) < max_lines:
        lines.append(" ".join(current_line))

    curr_y = y
    for line in lines:
        c.drawString(x, curr_y, line)
        curr_y -= leading
    return curr_y


# =========================================================================
# 1. EMPLOYEE SALARY SLIP (PAYSLIP)
# =========================================================================

def generate_payslip_pdf(line_data: dict, run_data: dict, company: dict = None, output_path: str = None) -> str:
    """
    Generate an official A4 Employee Payslip PDF.

    Args:
        line_data: Payroll line dictionary with employee details and salary calculations.
        run_data: Payroll run header dictionary with pay_period, run_date.
        company: Optional company dict override.
        output_path: Optional destination path.

    Returns:
        str: Absolute path to the generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        emp_code = line_data.get("employee_code") or "EMP"
        output_path = os.path.join(temp_dir, f"payslip_{emp_code}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    _render_single_payslip(c, line_data, run_data, page_w, page_h, comp_override=company)
    c.showPage()
    c.save()
    return output_path


def _render_single_payslip(c: canvas.Canvas, line: dict, run: dict, page_w: float, page_h: float, comp_override: dict = None):
    """Render a single Employee Payslip on an A4 page."""
    margin = 16 * mm
    top_y = page_h - margin

    comp_id = run.get("company_id") or 1
    comp = comp_override or db.get_company(comp_id) or {}
    comp_name = comp.get("name") or "Main Enterprise"
    currency = comp.get("currency") or "LKR"
    payroll_settings = db.get_payroll_settings(comp_id)

    # --- 1. Header / Letterhead ---
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin, top_y - 4 * mm, comp_name)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748B"))
    header_parts = []
    if comp.get("address"):
        header_parts.append(comp["address"])
    if comp.get("phone"):
        header_parts.append(f"Tel: {comp['phone']}")
    if comp.get("email"):
        header_parts.append(f"Email: {comp['email']}")
    c.drawString(margin, top_y - 9 * mm, " • ".join(header_parts))

    # Right Side Document Title Badge
    badge_w = 75 * mm
    badge_h = 16 * mm
    badge_x = page_w - margin - badge_w
    badge_y = top_y - badge_h + 2 * mm

    c.setFillColor(colors.HexColor("#EFF6FF"))
    c.roundRect(badge_x, badge_y, badge_w, badge_h, 3, stroke=1, fill=1)
    c.setStrokeColor(colors.HexColor("#3B82F6"))

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#1E3A8A"))
    c.drawRightString(
        page_w - margin - 4 * mm, badge_y + 10 * mm,
        payroll_settings.get("payslip_title") or "CONFIDENTIAL PAYSLIP",
    )
    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#1D4ED8"))
    c.drawRightString(page_w - margin - 4 * mm, badge_y + 4.5 * mm, f"Pay Period: {run.get('pay_period', '')}")

    # Top Divider
    div_y = top_y - 20 * mm
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(margin, div_y, page_w - margin, div_y)

    # --- 2. Employee Details Card ---
    info_y = div_y - 6 * mm
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.roundRect(margin, info_y - 32 * mm, page_w - 2 * margin, 32 * mm, 3, stroke=1, fill=1)

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin + 4 * mm, info_y - 5 * mm, "EMPLOYEE INFORMATION")

    # 2 columns of employee details
    col1_x = margin + 4 * mm
    col2_x = margin + 95 * mm
    y_step = 5.2 * mm

    emp_code = line.get("employee_code", "")
    emp_name = line.get("employee_name", "")
    designation = line.get("designation", "-")
    department = line.get("department", "-")
    nic = line.get("nic_number", "-")
    b_name = line.get("bank_name", "-")
    b_acct = line.get("bank_account", "-")
    p_method = line.get("payment_method", "Bank Transfer")

    rows_left = [
        ("Employee ID:", emp_code),
        ("Full Name:", emp_name),
        ("Designation:", designation),
        ("Department:", department),
    ]
    rows_right = [
        ("National ID (NIC):", nic),
        ("Payment Mode:", p_method),
        ("Bank Name:", b_name),
        ("Account No:", b_acct),
    ]

    cur_row_y = info_y - 11 * mm
    for lbl, val in rows_left:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(col1_x, cur_row_y, lbl)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(col1_x + 30 * mm, cur_row_y, str(val))
        cur_row_y -= y_step

    cur_row_y = info_y - 11 * mm
    for lbl, val in rows_right:
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(col2_x, cur_row_y, lbl)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(col2_x + 32 * mm, cur_row_y, str(val))
        cur_row_y -= y_step

    # --- 3. Earnings & Deductions Tables (Side by Side) ---
    tables_top_y = info_y - 42 * mm
    half_w = (page_w - 2 * margin - 6 * mm) / 2
    earn_x = margin
    ded_x = margin + half_w + 6 * mm
    row_h = 6.5 * mm

    # Titles
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#059669"))
    c.drawString(earn_x, tables_top_y, "EARNINGS & ALLOWANCES")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#DC2626"))
    c.drawString(ded_x, tables_top_y, "DEDUCTIONS")

    # Table Headers
    th_y = tables_top_y - 7 * mm
    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.rect(earn_x, th_y, half_w, row_h, fill=1, stroke=0)
    c.rect(ded_x, th_y, half_w, row_h, fill=1, stroke=0)

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(earn_x + 3 * mm, th_y + 2 * mm, "Description")
    c.drawRightString(earn_x + half_w - 3 * mm, th_y + 2 * mm, f"Amount ({currency})")

    c.drawString(ded_x + 3 * mm, th_y + 2 * mm, "Description")
    c.drawRightString(ded_x + half_w - 3 * mm, th_y + 2 * mm, f"Amount ({currency})")

    # Data Rows
    earnings_items = [
        ("Basic Salary", float(line.get("basic_salary") or 0.0)),
        ("Allowances & Perks", float(line.get("allowances") or 0.0)),
        ("Overtime & Incentives", float(line.get("overtime") or 0.0)),
    ]
    deductions_items = [
        ("Employee EPF (8%)", float(line.get("epf_employee") or 0.0)),
        ("Tax / APIT Withholding", float(line.get("tax_deduction") or 0.0)),
        ("Other / Advances", float(line.get("other_deductions") or 0.0)),
    ]

    cur_e_y = th_y - row_h
    for desc, amt in earnings_items:
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.5)
        c.line(earn_x, cur_e_y, earn_x + half_w, cur_e_y)

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#1E293B"))
        c.drawString(earn_x + 3 * mm, cur_e_y + 2 * mm, desc)
        c.drawRightString(earn_x + half_w - 3 * mm, cur_e_y + 2 * mm, f"{amt:,.2f}")
        cur_e_y -= row_h

    cur_d_y = th_y - row_h
    for desc, amt in deductions_items:
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.5)
        c.line(ded_x, cur_d_y, ded_x + half_w, cur_d_y)

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#1E293B"))
        c.drawString(ded_x + 3 * mm, cur_d_y + 2 * mm, desc)
        c.drawRightString(ded_x + half_w - 3 * mm, cur_d_y + 2 * mm, f"{amt:,.2f}")
        cur_d_y -= row_h

    # Subtotals
    gross_pay = float(line.get("gross_pay") or 0.0)
    total_ded = float(line.get("total_deductions") or 0.0)

    c.setFillColor(colors.HexColor("#ECFDF5"))
    c.rect(earn_x, cur_e_y, half_w, row_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#065F46"))
    c.drawString(earn_x + 3 * mm, cur_e_y + 2 * mm, "GROSS EARNINGS:")
    c.drawRightString(earn_x + half_w - 3 * mm, cur_e_y + 2 * mm, f"{gross_pay:,.2f}")

    c.setFillColor(colors.HexColor("#FEF2F2"))
    c.rect(ded_x, cur_d_y, half_w, row_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#991B1B"))
    c.drawString(ded_x + 3 * mm, cur_d_y + 2 * mm, "TOTAL DEDUCTIONS:")
    c.drawRightString(ded_x + half_w - 3 * mm, cur_d_y + 2 * mm, f"{total_ded:,.2f}")

    # --- 4. NET PAY HIGHLIGHT CARD ---
    net_box_y = cur_e_y - 28 * mm
    c.setFillColor(colors.HexColor("#F0FDF4"))
    c.setStrokeColor(colors.HexColor("#22C55E"))
    c.setLineWidth(1.5)
    c.roundRect(margin, net_box_y, page_w - 2 * margin, 24 * mm, 4, stroke=1, fill=1)

    net_pay = float(line.get("net_pay") or 0.0)
    words = amount_to_words(net_pay, currency=currency)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#166534"))
    c.drawString(margin + 6 * mm, net_box_y + 17 * mm, "NET TAKE-HOME SALARY:")

    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#15803D"))
    c.drawString(margin + 6 * mm, net_box_y + 9 * mm, f"{currency} {net_pay:,.2f}")

    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    _draw_wrapped_text(c, f"** {words} ONLY **", margin + 6 * mm, net_box_y + 4.5 * mm, page_w - 2 * margin - 12 * mm, "Helvetica-Oblique", 7.5, 3.2 * mm, max_lines=2)

    # --- 5. Notes / Disclaimers ---
    notes_y = net_box_y - 12 * mm
    custom_fields = {}
    try:
        custom_fields = json.loads(line.get("custom_fields_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        custom_fields = {}
    employer_info = (
        f"Employer EPF: {currency} {float(line.get('epf_employer') or 0):,.2f}; "
        f"Employer ETF: {currency} {float(line.get('etf_employer') or 0):,.2f}"
    )
    custom_text = "; ".join(f"{key}: {value}" for key, value in custom_fields.items())
    notes = line.get("notes") or "Computer-generated payroll record."
    notes = " | ".join(part for part in (notes, employer_info, custom_text) if part)
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748B"))
    _draw_wrapped_text(c, f"Note: {notes}", margin, notes_y, page_w - 2 * margin, "Helvetica", 7.5, 3.2 * mm, max_lines=2)

    # --- 6. Dual Signature Blocks ---
    sig_y = 26 * mm
    sig_w = 60 * mm

    # Left: Employee Acknowledgment
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.6)
    c.line(margin, sig_y + 8 * mm, margin + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin, sig_y + 4.5 * mm, "Employee Signature / Acknowledgment")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, sig_y + 1 * mm, "I acknowledge receipt of full payment as specified.")

    # Right: HR / Finance Signatory
    sig2_x = page_w - margin - sig_w
    c.line(sig2_x, sig_y + 8 * mm, sig2_x + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(sig2_x, sig_y + 4.5 * mm, "HR / Finance Authorized Signatory")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(sig2_x, sig_y + 1 * mm, "Prepared & Certified By Human Resources")

    # --- 7. Footer ---
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(0.5)
    c.line(margin, 14 * mm, page_w - margin, 14 * mm)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(margin, 9 * mm, "CONFIDENTIAL — OFFICIAL PAYROLL RECORD — VOUCHER MACHINE BOOKKEEPING")
    c.drawRightString(page_w - margin, 9 * mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page 1 of 1")


# =========================================================================
# 2. MONTHLY PAYROLL RUN SUMMARY REPORT (A4 Landscape)
# =========================================================================

def generate_payroll_run_pdf(run_data: dict, company: dict = None, output_path: str = None) -> str:
    """
    Generate an A4 Landscape Monthly Payroll Summary Sheet.
    Useful for executive audit and bulk bank salary upload instructions.
    """
    from reportlab.lib.pagesizes import landscape
    pagesize = landscape(A4)
    page_w, page_h = pagesize

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        period = run_data.get("pay_period", "monthly")
        output_path = os.path.join(temp_dir, f"payroll_run_{period}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=pagesize)
    margin = 15 * mm
    top_y = page_h - margin

    comp_id = run_data.get("company_id") or 1
    comp = company or db.get_company(comp_id) or {}
    comp_name = comp.get("name") or "Main Enterprise"
    currency = comp.get("currency") or "LKR"
    payroll_settings = db.get_payroll_settings(comp_id)

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin, top_y - 4 * mm, comp_name)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#1E3A8A"))
    c.drawRightString(page_w - margin, top_y - 4 * mm, f"PAYROLL MASTER SUMMARY — {run_data.get('pay_period', '')}")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, top_y - 9 * mm, f"Run Date: {run_data.get('run_date', '')} | Status: {run_data.get('status', 'Draft')}")
    c.drawRightString(page_w - margin, top_y - 9 * mm, f"Currency: {currency}")

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(margin, top_y - 12 * mm, page_w - margin, top_y - 12 * mm)

    # Table Header
    th_y = top_y - 20 * mm
    row_h = 6.5 * mm
    c.setFillColor(colors.HexColor("#1E293B"))
    c.rect(margin, th_y, page_w - 2 * margin, row_h, fill=1, stroke=0)

    # Column layout
    cols = [
        ("EMP #", 18 * mm, margin + 2 * mm, "left"),
        ("EMPLOYEE NAME", 60 * mm, margin + 22 * mm, "left"),
        ("DESIGNATION", 45 * mm, margin + 84 * mm, "left"),
        ("BASIC", 26 * mm, margin + 155 * mm, "right"),
        ("ALLOW.", 22 * mm, margin + 179 * mm, "right"),
        ("OVERTIME", 22 * mm, margin + 203 * mm, "right"),
        ("GROSS", 26 * mm, margin + 231 * mm, "right"),
        ("DEDUCT.", 24 * mm, margin + 257 * mm, "right"),
        ("NET SALARY", 26 * mm, page_w - margin - 2 * mm, "right"),
    ]

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.white)
    for title, w, pos_x, align in cols:
        if align == "left":
            c.drawString(pos_x, th_y + 2 * mm, title)
        else:
            c.drawRightString(pos_x, th_y + 2 * mm, title)

    # Rows
    cur_y = th_y - row_h
    lines = run_data.get("lines", [])

    tot_basic = 0.0
    tot_allow = 0.0
    tot_ot = 0.0
    tot_gross = 0.0
    tot_ded = 0.0
    tot_net = 0.0

    for idx, l in enumerate(lines):
        if cur_y < 28 * mm:
            c.showPage()
            cur_y = page_h - margin - 15 * mm

        bg = colors.HexColor("#F8FAFC") if idx % 2 == 1 else colors.white
        c.setFillColor(bg)
        c.rect(margin, cur_y, page_w - 2 * margin, row_h, fill=1, stroke=0)

        basic = float(l.get("basic_salary") or 0.0)
        allow = float(l.get("allowances") or 0.0)
        ot = float(l.get("overtime") or 0.0)
        gross = float(l.get("gross_pay") or 0.0)
        ded = float(l.get("total_deductions") or 0.0)
        net = float(l.get("net_pay") or 0.0)

        tot_basic += basic
        tot_allow += allow
        tot_ot += ot
        tot_gross += gross
        tot_ded += ded
        tot_net += net

        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(margin + 2 * mm, cur_y + 2 * mm, l.get("employee_code", ""))
        c.drawString(margin + 22 * mm, cur_y + 2 * mm, l.get("employee_name", "")[:35])
        c.drawString(margin + 84 * mm, cur_y + 2 * mm, l.get("designation", "")[:26])
        c.drawRightString(margin + 155 * mm, cur_y + 2 * mm, f"{basic:,.2f}")
        c.drawRightString(margin + 179 * mm, cur_y + 2 * mm, f"{allow:,.2f}")
        c.drawRightString(margin + 203 * mm, cur_y + 2 * mm, f"{ot:,.2f}")
        c.drawRightString(margin + 231 * mm, cur_y + 2 * mm, f"{gross:,.2f}")
        c.drawRightString(margin + 257 * mm, cur_y + 2 * mm, f"{ded:,.2f}")

        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#15803D"))
        c.drawRightString(page_w - margin - 2 * mm, cur_y + 2 * mm, f"{net:,.2f}")

        cur_y -= row_h

    # Totals Row
    c.setFillColor(colors.HexColor("#EFF6FF"))
    c.rect(margin, cur_y, page_w - 2 * margin, row_h + 1 * mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#1E3A8A"))
    c.drawString(margin + 2 * mm, cur_y + 2 * mm, f"TOTAL ({len(lines)} EMPLOYEES)")
    c.drawRightString(margin + 155 * mm, cur_y + 2 * mm, f"{tot_basic:,.2f}")
    c.drawRightString(margin + 179 * mm, cur_y + 2 * mm, f"{tot_allow:,.2f}")
    c.drawRightString(margin + 203 * mm, cur_y + 2 * mm, f"{tot_ot:,.2f}")
    c.drawRightString(margin + 231 * mm, cur_y + 2 * mm, f"{tot_gross:,.2f}")
    c.drawRightString(margin + 257 * mm, cur_y + 2 * mm, f"{tot_ded:,.2f}")
    c.drawRightString(page_w - margin - 2 * mm, cur_y + 2 * mm, f"{tot_net:,.2f}")

    # Signatures
    sig_y = 12 * mm
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, sig_y, f"Prepared by: {run_data.get('created_by') or 'HR/Payroll'} ___________________")
    c.drawString(margin + 100 * mm, sig_y, f"Approved by: {run_data.get('approved_by') or 'Finance Director'} ___________________")
    c.drawRightString(page_w - margin, sig_y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    c.showPage()
    c.save()
    return output_path
