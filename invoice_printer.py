"""
invoice_printer.py
PDF Generation Engine for Supplier Invoices (Accounts Payable) & Purchase Billing.

Generates professional, print-ready A4 PDF documents for Accounts Payable invoices,
complete with:
- Dynamic company profile branding & logo
- Supplier information & tax/VAT identification
- Line items table with quantities, rates, and tax calculations
- Financial summary breakdown (Subtotal, Tax, Discount, Total, Balance Due)
- Payment history tracking table
- Authorization and approval sign-off boxes
"""

import os
import io
import tempfile
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from PIL import Image as PILImage

import database as db


def generate_ap_invoice_pdf(invoice_ids: list[int] | int, output_path: str = None) -> str:
    """
    Generate an A4 PDF document for one or more Accounts Payable supplier invoices.

    Args:
        invoice_ids: Single invoice ID or list of invoice IDs.
        output_path: Optional destination path; generates timestamped temp file if omitted.

    Returns:
        str: Absolute path to the generated PDF file.
    """
    if isinstance(invoice_ids, int):
        invoice_ids = [invoice_ids]

    if not invoice_ids:
        raise ValueError("At least one invoice ID must be provided to generate invoice PDF.")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"ap_invoice_{invoice_ids[0]}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    for inv_id in invoice_ids:
        inv_data = db.get_ap_invoice(inv_id)
        if not inv_data:
            continue

        _render_single_invoice(c, inv_data, page_w, page_h)
        c.showPage()

    c.save()
    return output_path


def _render_single_invoice(c: canvas.Canvas, inv_data: dict, page_w: float, page_h: float):
    """Render a single supplier invoice onto the current page."""
    inv = inv_data["invoice"]
    lines = inv_data["lines"]
    payments = inv_data.get("payments", [])
    company_id = inv["company_id"]
    company = db.get_company(company_id) or {}

    margin_x = 15 * mm
    top_y = page_h - 15 * mm
    bottom_y = 15 * mm
    content_w = page_w - 2 * margin_x

    # 1. Header Bar: Company Branding & Document Title
    curr_y = top_y

    # Logo
    logo_w = 28 * mm
    logo_h = 22 * mm
    logo_drawn = False
    logo_path = company.get("logo_path")
    if logo_path and os.path.exists(logo_path):
        try:
            with PILImage.open(logo_path) as pil_img:
                pil_img = pil_img.convert("RGB")
                img_buf = io.BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=90)
                img_buf.seek(0)
                c.drawImage(ImageReader(img_buf), margin_x, curr_y - logo_h, width=logo_w, height=logo_h, preserveAspectRatio=True)
                logo_drawn = True
        except Exception:
            logo_drawn = False

    comp_text_x = margin_x + (logo_w + 4 * mm if logo_drawn else 0)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(comp_text_x, curr_y - 5 * mm, company.get("name", "Voucher Manager SME"))

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    addr_line = company.get("address", "")
    phone_email = f"Phone: {company.get('phone', '—')}   Email: {company.get('email', '—')}"
    tax_line = f"VAT / Tax Reg: {company.get('tax_number') or company.get('tax_id') or 'N/A'}"

    c.drawString(comp_text_x, curr_y - 10 * mm, addr_line[:65])
    c.drawString(comp_text_x, curr_y - 14 * mm, phone_email)
    c.drawString(comp_text_x, curr_y - 18 * mm, tax_line)

    # Document Title Box on Top Right
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawRightString(page_w - margin_x, curr_y - 5 * mm, "SUPPLIER INVOICE")

    # Status Pill
    status = inv.get("status", "Unpaid").upper()
    status_bg = colors.HexColor("#fee2e2") if status == "UNPAID" else colors.HexColor("#dcfce7") if status == "PAID" else colors.HexColor("#fef3c7")
    status_fg = colors.HexColor("#991b1b") if status == "UNPAID" else colors.HexColor("#166534") if status == "PAID" else colors.HexColor("#92400e")

    pill_w = 34 * mm
    pill_h = 7 * mm
    pill_x = page_w - margin_x - pill_w
    pill_y = curr_y - 17 * mm
    c.setFillColor(status_bg)
    c.roundRect(pill_x, pill_y, pill_w, pill_h, 3, stroke=0, fill=1)
    c.setFillColor(status_fg)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(pill_x + pill_w / 2, pill_y + 2 * mm, status)

    curr_y -= 26 * mm

    # Horizontal Divider Line
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.setLineWidth(1)
    c.line(margin_x, curr_y, page_w - margin_x, curr_y)
    curr_y -= 5 * mm

    # 2. Two-Column Metadata Box: Supplier Info (Left) | Invoice Details (Right)
    col_w = (content_w - 6 * mm) / 2
    box_h = 28 * mm

    # Supplier Box
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(margin_x, curr_y - box_h, col_w, box_h, stroke=1, fill=1)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1e293b"))
    c.drawString(margin_x + 3 * mm, curr_y - 5 * mm, "SUPPLIER / VENDOR DETAILS")

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin_x + 3 * mm, curr_y - 10 * mm, inv.get("supplier_name", "—"))

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(margin_x + 3 * mm, curr_y - 14 * mm, f"Address: {inv.get('supplier_address', '—')[:40]}")
    c.drawString(margin_x + 3 * mm, curr_y - 18 * mm, f"Phone: {inv.get('supplier_phone', '—')}   Email: {inv.get('supplier_email', '—')}")
    c.drawString(margin_x + 3 * mm, curr_y - 22 * mm, f"Supplier Tax/VAT #: {inv.get('supplier_tax_id', '—')}")

    # Invoice Details Box
    right_x = margin_x + col_w + 6 * mm
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(right_x, curr_y - box_h, col_w, box_h, stroke=1, fill=1)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1e293b"))
    c.drawString(right_x + 3 * mm, curr_y - 5 * mm, "INVOICE REFERENCE & DATES")

    c.setFont("Helvetica", 8)
    c.drawString(right_x + 3 * mm, curr_y - 10 * mm, "Invoice Number:")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(right_x + 32 * mm, curr_y - 10 * mm, inv.get("invoice_number", "—"))

    c.setFont("Helvetica", 8)
    c.drawString(right_x + 3 * mm, curr_y - 14 * mm, "Invoice Date:")
    c.drawString(right_x + 32 * mm, curr_y - 14 * mm, inv.get("invoice_date", "—"))

    c.drawString(right_x + 3 * mm, curr_y - 18 * mm, "Due Date:")
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#b91c1c") if inv.get("status") != "Paid" else colors.HexColor("#15803d"))
    c.drawString(right_x + 32 * mm, curr_y - 18 * mm, inv.get("due_date", "—"))

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(right_x + 3 * mm, curr_y - 22 * mm, "Internal Ref / PO:")
    c.drawString(right_x + 32 * mm, curr_y - 22 * mm, inv.get("internal_ref") or "—")

    curr_y -= (box_h + 8 * mm)

    # 3. Line Items Table
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#1e293b"))
    th_h = 7 * mm

    # Header Row
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.rect(margin_x, curr_y - th_h, content_w, th_h, stroke=0, fill=1)

    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin_x + 2 * mm, curr_y - 5 * mm, "#")
    c.drawString(margin_x + 10 * mm, curr_y - 5 * mm, "Description / Item")
    c.drawString(margin_x + 85 * mm, curr_y - 5 * mm, "Account Code")
    c.drawRightString(margin_x + 115 * mm, curr_y - 5 * mm, "Qty")
    c.drawRightString(margin_x + 140 * mm, curr_y - 5 * mm, "Unit Price")
    c.drawRightString(margin_x + 158 * mm, curr_y - 5 * mm, "Tax")
    c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 5 * mm, "Line Total (LKR)")

    curr_y -= th_h

    # Rows
    c.setFont("Helvetica", 8)
    row_h = 6.5 * mm
    for idx, l in enumerate(lines, 1):
        bg_col = colors.HexColor("#ffffff") if idx % 2 == 1 else colors.HexColor("#f8fafc")
        c.setFillColor(bg_col)
        c.rect(margin_x, curr_y - row_h, content_w, row_h, stroke=0, fill=1)

        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(margin_x + 2 * mm, curr_y - 4.5 * mm, str(idx))
        desc = (l.get("description") or "—")[:48]
        c.drawString(margin_x + 10 * mm, curr_y - 4.5 * mm, desc)

        acct_lbl = l.get("account_code") or "—"
        c.drawString(margin_x + 85 * mm, curr_y - 4.5 * mm, acct_lbl)

        qty_str = f"{float(l.get('quantity') or 1.0):,.1f}"
        c.drawRightString(margin_x + 115 * mm, curr_y - 4.5 * mm, qty_str)

        price_str = f"{float(l.get('unit_price') or 0.0):,.2f}"
        c.drawRightString(margin_x + 140 * mm, curr_y - 4.5 * mm, price_str)

        tax_str = f"{float(l.get('tax_amount') or 0.0):,.2f}"
        c.drawRightString(margin_x + 158 * mm, curr_y - 4.5 * mm, tax_str)

        tot_str = f"{float(l.get('line_total') or 0.0):,.2f}"
        c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 4.5 * mm, tot_str)

        curr_y -= row_h

    # Table bottom line
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.line(margin_x, curr_y, page_w - margin_x, curr_y)
    curr_y -= 6 * mm

    # 4. Summary & Totals Box (Right Aligned)
    sum_w = 75 * mm
    sum_x = page_w - margin_x - sum_w

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(sum_x, curr_y, "Subtotal:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('subtotal') or 0.0):,.2f}")
    curr_y -= 4.5 * mm

    if float(inv.get("discount_amount") or 0.0) > 0:
        c.drawString(sum_x, curr_y, "Discount:")
        c.drawRightString(page_w - margin_x, curr_y, f"- LKR {float(inv.get('discount_amount') or 0.0):,.2f}")
        curr_y -= 4.5 * mm

    if float(inv.get("tax_amount") or 0.0) > 0:
        c.drawString(sum_x, curr_y, "VAT / Tax:")
        c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('tax_amount') or 0.0):,.2f}")
        curr_y -= 4.5 * mm

    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.line(sum_x, curr_y + 1 * mm, page_w - margin_x, curr_y + 1 * mm)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(sum_x, curr_y - 3 * mm, "Total Invoiced:")
    c.drawRightString(page_w - margin_x, curr_y - 3 * mm, f"LKR {float(inv.get('total_amount') or 0.0):,.2f}")
    curr_y -= 8 * mm

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#166534"))
    c.drawString(sum_x, curr_y, "Paid Amount:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('paid_amount') or 0.0):,.2f}")
    curr_y -= 5 * mm

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#991b1b") if float(inv.get("balance_due") or 0.0) > 0 else colors.HexColor("#15803d"))
    c.drawString(sum_x, curr_y, "Balance Due:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('balance_due') or 0.0):,.2f}")
    curr_y -= 10 * mm

    # 5. Payment Records Section (if any payments made)
    if payments:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawString(margin_x, curr_y, "PAYMENT SETTLEMENT HISTORY")
        curr_y -= 4 * mm

        c.setFillColor(colors.HexColor("#f1f5f9"))
        c.rect(margin_x, curr_y - 5 * mm, content_w, 5 * mm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(margin_x + 2 * mm, curr_y - 3.5 * mm, "Payment Date")
        c.drawString(margin_x + 35 * mm, curr_y - 3.5 * mm, "Method")
        c.drawString(margin_x + 65 * mm, curr_y - 3.5 * mm, "Reference")
        c.drawString(margin_x + 105 * mm, curr_y - 3.5 * mm, "Voucher / Check #")
        c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 3.5 * mm, "Amount (LKR)")
        curr_y -= 5 * mm

        c.setFont("Helvetica", 7.5)
        for p in payments:
            c.drawString(margin_x + 2 * mm, curr_y - 3.5 * mm, p.get("payment_date", "—"))
            c.drawString(margin_x + 35 * mm, curr_y - 3.5 * mm, p.get("payment_method", "—"))
            c.drawString(margin_x + 65 * mm, curr_y - 3.5 * mm, (p.get("reference") or "—")[:20])
            vc_num = p.get("voucher_number") or p.get("check_number") or "—"
            c.drawString(margin_x + 105 * mm, curr_y - 3.5 * mm, vc_num)
            c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 3.5 * mm, f"{float(p.get('amount') or 0.0):,.2f}")
            curr_y -= 4.5 * mm

        curr_y -= 4 * mm

    # 6. Notes & Authorization Section
    if inv.get("notes"):
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(margin_x, curr_y, f"Notes: {inv['notes'][:120]}")
        curr_y -= 6 * mm

    # Signatures at bottom
    sig_y = bottom_y + 12 * mm
    sig_w = 48 * mm

    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.line(margin_x, sig_y, margin_x + sig_w, sig_y)
    c.line(margin_x + 60 * mm, sig_y, margin_x + 60 * mm + sig_w, sig_y)
    c.line(page_w - margin_x - sig_w, sig_y, page_w - margin_x, sig_y)

    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(margin_x + sig_w / 2, sig_y - 4 * mm, "Goods / Services Received By")
    c.drawCentredString(margin_x + 60 * mm + sig_w / 2, sig_y - 4 * mm, "Finance Verified By")
    c.drawCentredString(page_w - margin_x - sig_w / 2, sig_y - 4 * mm, "Approved For Payment")

    # Document Footer
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawString(margin_x, bottom_y - 4 * mm, f"Generated by Voucher Manager v3.5 on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawRightString(page_w - margin_x, bottom_y - 4 * mm, "Page 1 of 1")


def generate_ar_invoice_pdf(invoice_ids: list[int] | int, output_path: str = None) -> str:
    """
    Generate an A4 PDF document for one or more Accounts Receivable customer invoices.

    Args:
        invoice_ids: Single invoice ID or list of invoice IDs.
        output_path: Optional destination path; generates timestamped temp file if omitted.

    Returns:
        str: Absolute path to the generated PDF file.
    """
    if isinstance(invoice_ids, int):
        invoice_ids = [invoice_ids]

    if not invoice_ids:
        raise ValueError("At least one invoice ID must be provided to generate invoice PDF.")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"ar_invoice_{invoice_ids[0]}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    for inv_id in invoice_ids:
        inv_data = db.get_ar_invoice(inv_id)
        if not inv_data:
            continue

        _render_single_ar_invoice(c, inv_data, page_w, page_h)
        c.showPage()

    c.save()
    return output_path


def _render_single_ar_invoice(c: canvas.Canvas, inv_data: dict, page_w: float, page_h: float):
    """Render a single customer sales invoice onto the current page."""
    inv = inv_data["invoice"]
    lines = inv_data["lines"]
    receipts = inv_data.get("receipts", [])
    company_id = inv["company_id"]
    company = db.get_company(company_id) or {}

    margin_x = 15 * mm
    top_y = page_h - 15 * mm
    bottom_y = 15 * mm
    content_w = page_w - 2 * margin_x

    # 1. Header Bar: Company Branding & Document Title
    curr_y = top_y

    # Logo
    logo_w = 28 * mm
    logo_h = 22 * mm
    logo_drawn = False
    logo_path = company.get("logo_path")
    if logo_path and os.path.exists(logo_path):
        try:
            with PILImage.open(logo_path) as pil_img:
                pil_img = pil_img.convert("RGB")
                img_buf = io.BytesIO()
                pil_img.save(img_buf, format="JPEG", quality=90)
                img_buf.seek(0)
                c.drawImage(ImageReader(img_buf), margin_x, curr_y - logo_h, width=logo_w, height=logo_h, preserveAspectRatio=True)
                logo_drawn = True
        except Exception:
            logo_drawn = False

    comp_text_x = margin_x + (logo_w + 4 * mm if logo_drawn else 0)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(comp_text_x, curr_y - 4 * mm, company.get("name") or "Company Profile")

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#64748b"))
    tag = company.get("tagline") or ""
    if tag:
        c.drawString(comp_text_x, curr_y - 9 * mm, tag)
    addr = company.get("address") or ""
    if addr:
        c.drawString(comp_text_x, curr_y - 13 * mm, addr[:60])
    contact = f"Tel: {company.get('contact', '')}  |  Email: {company.get('email', '')}".strip()
    if contact != "Tel:   |  Email:":
        c.drawString(comp_text_x, curr_y - 17 * mm, contact)

    # Document Title Block (Right-aligned)
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(colors.HexColor("#1e3a8a"))  # Deep professional blue for AR Invoices
    c.drawRightString(page_w - margin_x, curr_y - 4 * mm, "TAX INVOICE")

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#1e293b"))
    c.drawRightString(page_w - margin_x, curr_y - 11 * mm, f"#{inv.get('invoice_number', '')}")

    status_str = (inv.get("status") or "Draft").upper()
    c.setFont("Helvetica-Bold", 8)
    if status_str == "PAID":
        c.setFillColor(colors.HexColor("#15803d"))
    elif status_str in ("OVERDUE", "CANCELLED", "BAD DEBT"):
        c.setFillColor(colors.HexColor("#b91c1c"))
    elif status_str == "PARTIALLY PAID":
        c.setFillColor(colors.HexColor("#b45309"))
    else:
        c.setFillColor(colors.HexColor("#475569"))
    c.drawRightString(page_w - margin_x, curr_y - 17 * mm, f"[{status_str}]")

    curr_y -= 25 * mm

    # Divider bar
    c.setStrokeColor(colors.HexColor("#e2e8f0"))
    c.setLineWidth(1)
    c.line(margin_x, curr_y, page_w - margin_x, curr_y)
    curr_y -= 6 * mm

    # 2. Metadata Cards: Bill To (Customer) & Invoice Meta
    col_w = content_w / 2

    # Left: Bill To (Customer Details)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#1e293b"))
    c.drawString(margin_x, curr_y, "BILL TO (CUSTOMER):")
    curr_y -= 4.5 * mm

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(margin_x, curr_y, inv.get("customer_name") or "Customer")
    curr_y -= 4 * mm

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    if inv.get("contact_person"):
        c.drawString(margin_x, curr_y, f"Attn: {inv['contact_person']}")
        curr_y -= 3.5 * mm
    if inv.get("customer_address"):
        c.drawString(margin_x, curr_y, inv["customer_address"][:60])
        curr_y -= 3.5 * mm
    c_contact = []
    if inv.get("customer_phone"):
        c_contact.append(f"Phone: {inv['customer_phone']}")
    if inv.get("customer_email"):
        c_contact.append(f"Email: {inv['customer_email']}")
    if c_contact:
        c.drawString(margin_x, curr_y, "  |  ".join(c_contact))
        curr_y -= 3.5 * mm
    if inv.get("customer_tax_id"):
        c.drawString(margin_x, curr_y, f"VAT / Tax ID: {inv['customer_tax_id']}")
        curr_y -= 3.5 * mm

    # Right: Invoice Details Box
    right_x = margin_x + col_w + 10 * mm
    meta_y = curr_y + 19 * mm

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#64748b"))
    meta_labels = [
        ("Invoice Date:", inv.get("invoice_date", "")),
        ("Payment Due Date:", inv.get("due_date", "")),
        ("Payment Terms:", inv.get("terms") or "Net 30 Days"),
        ("Currency:", inv.get("currency", "LKR")),
    ]
    if inv.get("internal_ref"):
        meta_labels.append(("Customer PO / Ref:", inv["internal_ref"]))

    for lbl, val in meta_labels:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(right_x, meta_y, lbl)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawRightString(page_w - margin_x, meta_y, str(val))
        meta_y -= 4 * mm

    curr_y = min(curr_y - 4 * mm, meta_y - 2 * mm)

    # 3. Line Items Table
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.rect(margin_x, curr_y - 6 * mm, content_w, 6 * mm, stroke=0, fill=1)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.white)
    c.drawString(margin_x + 3 * mm, curr_y - 4.2 * mm, "#")
    c.drawString(margin_x + 12 * mm, curr_y - 4.2 * mm, "Item Description")
    c.drawRightString(margin_x + 105 * mm, curr_y - 4.2 * mm, "Qty")
    c.drawRightString(margin_x + 130 * mm, curr_y - 4.2 * mm, "Unit Price")
    c.drawRightString(margin_x + 150 * mm, curr_y - 4.2 * mm, "VAT Rate")
    c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 4.2 * mm, "Amount (LKR)")

    curr_y -= 6 * mm

    row_h = 6 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#1e293b"))

    for idx, line in enumerate(lines, 1):
        bg_col = colors.HexColor("#f8fafc") if (idx % 2 == 0) else colors.white
        c.setFillColor(bg_col)
        c.rect(margin_x, curr_y - row_h, content_w, row_h, stroke=0, fill=1)

        c.setStrokeColor(colors.HexColor("#e2e8f0"))
        c.setLineWidth(0.5)
        c.line(margin_x, curr_y - row_h, page_w - margin_x, curr_y - row_h)

        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(margin_x + 3 * mm, curr_y - 4.2 * mm, str(idx))
        desc = line.get("description", "")
        c.drawString(margin_x + 12 * mm, curr_y - 4.2 * mm, desc[:48])
        c.drawRightString(margin_x + 105 * mm, curr_y - 4.2 * mm, f"{float(line.get('quantity') or 1.0):.2f}")
        c.drawRightString(margin_x + 130 * mm, curr_y - 4.2 * mm, f"{float(line.get('unit_price') or 0.0):,.2f}")
        t_rate = float(line.get("tax_rate") or 0.0)
        c.drawRightString(margin_x + 150 * mm, curr_y - 4.2 * mm, f"{t_rate * 100:.1f}%" if t_rate else "0.0%")
        c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 4.2 * mm, f"{float(line.get('line_total') or 0.0):,.2f}")

        curr_y -= row_h

    curr_y -= 4 * mm

    # 4. Financial Summary Breakdown (Right side)
    sum_w = 75 * mm
    sum_x = page_w - margin_x - sum_w

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(sum_x, curr_y, "Subtotal:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('subtotal') or 0.0):,.2f}")
    curr_y -= 4.5 * mm

    disc = float(inv.get("discount_amount") or 0.0)
    if disc > 0:
        c.drawString(sum_x, curr_y, "Discount Applied:")
        c.drawRightString(page_w - margin_x, curr_y, f"- LKR {disc:,.2f}")
        curr_y -= 4.5 * mm

    tax_amt = float(inv.get("tax_amount") or 0.0)
    if tax_amt > 0:
        c.drawString(sum_x, curr_y, "VAT / Taxes:")
        c.drawRightString(page_w - margin_x, curr_y, f"+ LKR {tax_amt:,.2f}")
        curr_y -= 4.5 * mm

    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.setLineWidth(1)
    c.line(sum_x, curr_y + 1 * mm, page_w - margin_x, curr_y + 1 * mm)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.drawString(sum_x, curr_y - 3 * mm, "Total Amount Due:")
    c.drawRightString(page_w - margin_x, curr_y - 3 * mm, f"LKR {float(inv.get('total_amount') or 0.0):,.2f}")
    curr_y -= 8 * mm

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawString(sum_x, curr_y, "Paid to Date:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('paid_amount') or 0.0):,.2f}")
    curr_y -= 4.5 * mm

    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColor(colors.HexColor("#b91c1c") if float(inv.get("balance_due") or 0.0) > 0 else colors.HexColor("#15803d"))
    c.drawString(sum_x, curr_y, "Balance Remaining:")
    c.drawRightString(page_w - margin_x, curr_y, f"LKR {float(inv.get('balance_due') or 0.0):,.2f}")
    curr_y -= 8 * mm

    # Left: Bank Remittance Info Box
    remit_y = curr_y + 26 * mm
    remit_w = content_w - sum_w - 10 * mm
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.rect(margin_x, remit_y - 25 * mm, remit_w, 25 * mm, stroke=1, fill=1)
    c.setStrokeColor(colors.HexColor("#e2e8f0"))

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawString(margin_x + 3 * mm, remit_y - 4 * mm, "PAYMENT / REMITTANCE INSTRUCTIONS")

    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin_x + 3 * mm, remit_y - 9 * mm, f"Please remit payment quoting Invoice #{inv.get('invoice_number', '')}")
    b_name = company.get("bank_name") or "Commercial Bank of Ceylon PLC"
    b_acct = company.get("bank_account") or "A/C: 1000-2458-9120"
    c.drawString(margin_x + 3 * mm, remit_y - 14 * mm, f"Bank: {b_name}")
    c.drawString(margin_x + 3 * mm, remit_y - 19 * mm, f"Account: {b_acct}")

    # 5. Customer Receipt Records Section (if any receipts recorded)
    if receipts:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#1e293b"))
        c.drawString(margin_x, curr_y, "PAYMENT SETTLEMENT & RECEIPT HISTORY")
        curr_y -= 4 * mm

        c.setFillColor(colors.HexColor("#f1f5f9"))
        c.rect(margin_x, curr_y - 5 * mm, content_w, 5 * mm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(margin_x + 2 * mm, curr_y - 3.5 * mm, "Receipt Date")
        c.drawString(margin_x + 35 * mm, curr_y - 3.5 * mm, "Method")
        c.drawString(margin_x + 65 * mm, curr_y - 3.5 * mm, "Reference")
        c.drawString(margin_x + 105 * mm, curr_y - 3.5 * mm, "Bank Account")
        c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 3.5 * mm, "Amount Received (LKR)")
        curr_y -= 5 * mm

        c.setFont("Helvetica", 7.5)
        for r in receipts:
            c.drawString(margin_x + 2 * mm, curr_y - 3.5 * mm, r.get("receipt_date", "—"))
            c.drawString(margin_x + 35 * mm, curr_y - 3.5 * mm, r.get("payment_method", "—"))
            c.drawString(margin_x + 65 * mm, curr_y - 3.5 * mm, (r.get("reference") or "—")[:20])
            b_acc = r.get("bank_account_name") or "—"
            c.drawString(margin_x + 105 * mm, curr_y - 3.5 * mm, b_acc[:25])
            c.drawRightString(page_w - margin_x - 3 * mm, curr_y - 3.5 * mm, f"{float(r.get('amount') or 0.0):,.2f}")
            curr_y -= 4.5 * mm

        curr_y -= 4 * mm

    # 6. Notes & Terms
    if inv.get("notes") or inv.get("footer_text"):
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(colors.HexColor("#64748b"))
        msg = inv.get("footer_text") or inv.get("notes") or ""
        c.drawString(margin_x, curr_y, f"Note: {msg[:120]}")
        curr_y -= 6 * mm

    # Signatures at bottom
    sig_y = bottom_y + 12 * mm
    sig_w = 55 * mm

    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.line(margin_x, sig_y, margin_x + sig_w, sig_y)
    c.line(page_w - margin_x - sig_w, sig_y, page_w - margin_x, sig_y)

    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(margin_x + sig_w / 2, sig_y - 4 * mm, "Prepared By")
    c.drawCentredString(page_w - margin_x - sig_w / 2, sig_y - 4 * mm, "Authorized Signatory & Stamp")

    # Document Footer
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94a3b8"))
    c.drawString(margin_x, bottom_y - 4 * mm, f"Generated by Voucher Manager v3.8 on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawRightString(page_w - margin_x, bottom_y - 4 * mm, "Page 1 of 1")

