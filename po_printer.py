"""
po_printer.py
PDF Generation Engine for Purchase Orders (PO) & Goods Received Notes (GRN).

Generates professional, print-ready A4 PDF documents with:
- Dynamic company profile branding & logo
- Detailed vendor & delivery recipient information
- Clean tabular item specifications with quantities, units, rates, and tax calculations
- Financial summary breakdown and amount-in-words conversion
- Terms & conditions and delivery instructions
- Goods Received Note (GRN) warehouse receiving inspection slips
- Dual-signatory approval and storekeeper receiving sign-off boxes
"""

import os
import io
import tempfile
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
# 1. PURCHASE ORDER PDF
# =========================================================================

def generate_purchase_order_pdf(po_or_id, company: dict = None, output_path: str = None) -> str:
    """
    Generate an A4 PDF document for a Purchase Order.

    Args:
        po_or_id: Purchase Order ID or dictionary.
        company: Optional company dict or output path string.
        output_path: Optional destination path; generates temp file if omitted.

    Returns:
        str: Absolute path to the generated PDF file.
    """
    if isinstance(company, str) and output_path is None:
        output_path = company
        company = None

    if isinstance(po_or_id, dict):
        po_data = po_or_id
        po_id = po_data.get("id") or "new"
    else:
        po_id = int(po_or_id)
        po_data = db.get_purchase_order(po_id)

    if not po_data:
        raise ValueError(f"Purchase Order #{po_id} not found.")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"purchase_order_{po_id}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    _render_single_po(c, po_data, page_w, page_h, comp_override=company)
    c.showPage()
    c.save()
    return output_path


def _render_single_po(c: canvas.Canvas, po: dict, page_w: float, page_h: float, comp_override: dict = None):
    """Render a single Purchase Order on an A4 page."""
    margin = 15 * mm
    top_y = page_h - margin

    comp_id = po.get("company_id") or 1
    comp = comp_override or db.get_company(comp_id) or {}
    comp_name = comp.get("name") or "Main Enterprise"
    currency = po.get("currency") or "LKR"

    # --- 1. Company Letterhead Header ---
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin, top_y - 5 * mm, comp_name)

    contact_parts = []
    if comp.get("tax_number"):
        contact_parts.append(f"Tax / VAT ID: {comp['tax_number']}")
    if comp.get("address"):
        contact_parts.append(comp["address"])
    if comp.get("phone"):
        contact_parts.append(f"Tel: {comp['phone']}")
    if comp.get("email"):
        contact_parts.append(comp["email"])

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    sub_y = top_y - 9.5 * mm
    if contact_parts:
        c.drawString(margin, sub_y, " | ".join(contact_parts[:2]))
        if len(contact_parts) > 2:
            c.drawString(margin, sub_y - 3.5 * mm, " | ".join(contact_parts[2:]))

    # Company Logo (top right)
    logo_path = comp.get("logo_path")
    if logo_path and os.path.exists(logo_path):
        try:
            with PILImage.open(logo_path) as im:
                lw, lh = im.size
                aspect = lh / float(lw)
                target_w = 38 * mm
                target_h = target_w * aspect
                if target_h > 18 * mm:
                    target_h = 18 * mm
                    target_w = target_h / aspect
                c.drawImage(logo_path, page_w - margin - target_w, top_y - target_h - 2 * mm, width=target_w, height=target_h, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    # Header Divider Rule
    divider_y = top_y - 19 * mm
    c.setStrokeColor(colors.HexColor("#0284C7"))  # Sky blue accent for PO
    c.setLineWidth(1.5)
    c.line(margin, divider_y, page_w - margin, divider_y)

    # --- 2. PO Title & Document Metadata Banner ---
    banner_y = divider_y - 4 * mm
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawString(margin, banner_y - 4 * mm, "PURCHASE ORDER")

    # Status Badge
    status = po.get("status", "Draft").upper()
    badge_colors = {
        "DRAFT": ("#F1F5F9", "#475569"),
        "SENT": ("#EFF6FF", "#1D4ED8"),
        "PARTIALLY RECEIVED": ("#FEF3C7", "#B45309"),
        "FULLY RECEIVED": ("#DCFCE7", "#15803D"),
        "CANCELLED": ("#FEE2E2", "#B91C1C")
    }
    bg_col, txt_col = badge_colors.get(status, ("#F1F5F9", "#475569"))
    badge_w = 40 * mm
    badge_h = 6 * mm
    badge_x = margin + 55 * mm
    badge_y = banner_y - 6 * mm

    c.setFillColor(colors.HexColor(bg_col))
    c.roundRect(badge_x, badge_y, badge_w, badge_h, 2 * mm, fill=True, stroke=False)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor(txt_col))
    c.drawCentredString(badge_x + badge_w / 2.0, badge_y + 1.8 * mm, f"STATUS: {status}")

    # Metadata Grid (Right side)
    meta_x = page_w - margin - 70 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(meta_x, banner_y - 2 * mm, "PO Number:")
    c.drawString(meta_x, banner_y - 6.5 * mm, "Order Date:")
    c.drawString(meta_x, banner_y - 11 * mm, "Expected Date:")

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawRightString(page_w - margin, banner_y - 2 * mm, po.get("po_number", "PO-DRAFT"))
    c.drawRightString(page_w - margin, banner_y - 6.5 * mm, po.get("po_date", ""))
    c.drawRightString(page_w - margin, banner_y - 11 * mm, po.get("expected_date") or "Prompt Delivery")

    # --- 3. Two-Column Information Box (Vendor vs Delivery Details) ---
    cards_top = banner_y - 16 * mm
    card_w = (page_w - 2 * margin - 6 * mm) / 2.0
    card_h = 29 * mm

    # Left: Vendor / Supplier Card
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.6)
    c.roundRect(margin, cards_top - card_h, card_w, card_h, 2 * mm, fill=True, stroke=True)

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawString(margin + 4 * mm, cards_top - 5 * mm, "VENDOR / SUPPLIER:")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin + 4 * mm, cards_top - 10 * mm, po.get("supplier_name", "Supplier Not Assigned"))

    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#475569"))
    c_y = cards_top - 14 * mm
    if po.get("supplier_contact"):
        c.drawString(margin + 4 * mm, c_y, f"Attn: {po['supplier_contact']}")
        c_y -= 3.5 * mm
    if po.get("supplier_address"):
        c.drawString(margin + 4 * mm, c_y, po["supplier_address"][:50])
        c_y -= 3.5 * mm
    comm_parts = []
    if po.get("supplier_phone"):
        comm_parts.append(f"Tel: {po['supplier_phone']}")
    if po.get("supplier_tax_id"):
        comm_parts.append(f"VAT: {po['supplier_tax_id']}")
    if comm_parts:
        c.drawString(margin + 4 * mm, c_y, " | ".join(comm_parts))

    # Right: Ship To & Terms Card
    right_x = margin + card_w + 6 * mm
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.roundRect(right_x, cards_top - card_h, card_w, card_h, 2 * mm, fill=True, stroke=True)

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawString(right_x + 4 * mm, cards_top - 5 * mm, "SHIP TO & PAYMENT TERMS:")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#0F172A"))
    s_addr = po.get("shipping_address") or comp.get("address") or "Company Warehouse"
    c.drawString(right_x + 4 * mm, cards_top - 10 * mm, f"Delivery: {s_addr[:45]}")
    terms_txt = po.get("terms") or "Net 30 Days on receipt of tax invoice"
    c.drawString(right_x + 4 * mm, cards_top - 14.5 * mm, f"Terms: {terms_txt[:45]}")
    c.drawString(right_x + 4 * mm, cards_top - 19 * mm, f"Currency: {currency}")
    if po.get("approved_by"):
        c.drawString(right_x + 4 * mm, cards_top - 23.5 * mm, f"Approved By: {po['approved_by']}")

    # --- 4. Line Items Table ---
    tbl_top = cards_top - card_h - 6 * mm
    col_x = [
        margin,                  # # (0)
        margin + 10 * mm,        # Description (1)
        margin + 98 * mm,        # Unit (2)
        margin + 114 * mm,       # Quantity (3)
        margin + 134 * mm,       # Unit Price (4)
        margin + 158 * mm,       # Tax (5)
        page_w - margin          # Line Total (right align)
    ]

    header_h = 6.5 * mm
    c.setFillColor(colors.HexColor("#0369A1"))
    c.rect(margin, tbl_top - header_h, page_w - 2 * margin, header_h, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.white)
    c.drawString(col_x[0] + 2 * mm, tbl_top - 4.5 * mm, "#")
    c.drawString(col_x[1] + 1 * mm, tbl_top - 4.5 * mm, "Item Description / Specification")
    c.drawString(col_x[2] + 1 * mm, tbl_top - 4.5 * mm, "Unit")
    c.drawRightString(col_x[3] + 16 * mm, tbl_top - 4.5 * mm, "Qty")
    c.drawRightString(col_x[4] + 20 * mm, tbl_top - 4.5 * mm, f"Unit Price ({currency})")
    c.drawRightString(col_x[5] + 16 * mm, tbl_top - 4.5 * mm, "Tax")
    c.drawRightString(col_x[6] - 2 * mm, tbl_top - 4.5 * mm, f"Total ({currency})")

    curr_y = tbl_top - header_h
    row_h = 6.5 * mm
    lines = po.get("lines") or []

    for idx, line in enumerate(lines, 1):
        if idx % 2 == 0:
            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.rect(margin, curr_y - row_h, page_w - 2 * margin, row_h, fill=True, stroke=False)

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.4)
        c.line(margin, curr_y - row_h, page_w - margin, curr_y - row_h)

        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(col_x[0] + 2 * mm, curr_y - 4.5 * mm, str(idx))

        desc = line.get("description", "")
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(col_x[1] + 1 * mm, curr_y - 4.5 * mm, desc[:50])

        c.setFont("Helvetica", 7.5)
        c.drawString(col_x[2] + 1 * mm, curr_y - 4.5 * mm, line.get("unit", "pcs"))

        qty_str = f"{line.get('quantity', 0):,.2f}".rstrip('0').rstrip('.')
        c.drawRightString(col_x[3] + 16 * mm, curr_y - 4.5 * mm, qty_str)
        c.drawRightString(col_x[4] + 20 * mm, curr_y - 4.5 * mm, f"{line.get('unit_price', 0):,.2f}")

        trate = float(line.get("tax_rate") or 0.0)
        tax_str = f"{trate * 100:.0f}%" if trate > 0 else "-"
        c.drawRightString(col_x[5] + 16 * mm, curr_y - 4.5 * mm, tax_str)
        c.drawRightString(col_x[6] - 2 * mm, curr_y - 4.5 * mm, f"{line.get('line_total', 0):,.2f}")

        curr_y -= row_h
        if curr_y < 85 * mm:
            break

    # Outer Table Border
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.6)
    c.rect(margin, curr_y, page_w - 2 * margin, tbl_top - curr_y, fill=False, stroke=True)

    # --- 5. Financial Summary Box ---
    summary_w = 70 * mm
    summary_x = page_w - margin - summary_w
    summary_y = curr_y - 4 * mm

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(summary_x, summary_y - 4 * mm, "Subtotal:")
    c.drawString(summary_x, summary_y - 8.5 * mm, "VAT / Sales Tax:")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawRightString(page_w - margin, summary_y - 4 * mm, f"{po.get('subtotal', 0):,.2f}")
    c.drawRightString(page_w - margin, summary_y - 8.5 * mm, f"{po.get('tax_amount', 0):,.2f}")

    # Total Box
    tot_box_y = summary_y - 17 * mm
    tot_box_h = 7.5 * mm
    c.setFillColor(colors.HexColor("#EFF6FF"))
    c.setStrokeColor(colors.HexColor("#0284C7"))
    c.setLineWidth(1.0)
    c.roundRect(summary_x, tot_box_y, summary_w, tot_box_h, 1.5 * mm, fill=True, stroke=True)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawString(summary_x + 3 * mm, tot_box_y + 2.3 * mm, "TOTAL ORDER VALUE:")
    c.drawRightString(page_w - margin - 3 * mm, tot_box_y + 2.3 * mm, f"{currency} {po.get('total_amount', 0):,.2f}")

    # Amount in words (left side of summary)
    tot_amt = float(po.get("total_amount") or 0.0)
    words_text = amount_to_words(tot_amt, currency=currency)
    w_box_w = summary_x - margin - 8 * mm
    w_box_y = summary_y - 17 * mm

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin, summary_y - 4 * mm, "AMOUNT IN WORDS:")
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(colors.HexColor("#0F172A"))
    _draw_wrapped_text(c, f"** {words_text} ONLY **", margin, summary_y - 8.5 * mm, w_box_w, "Helvetica-Oblique", 7.5, 3.5 * mm, max_lines=2)

    # --- 6. Notes & Terms Section ---
    notes_y = tot_box_y - 8 * mm
    notes = po.get("notes") or "Please quote Purchase Order number on all shipping advice notes, invoices, and packages."
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(margin, notes_y, "INSTRUCTIONS & NOTES:")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#0F172A"))
    _draw_wrapped_text(c, notes, margin, notes_y - 3.5 * mm, page_w - 2 * margin, "Helvetica", 7.5, 3.2 * mm, max_lines=2)

    # --- 7. Authorization & Approval Signatures ---
    sig_y = 22 * mm
    sig_w = 55 * mm

    # Left: Prepared by
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.6)
    c.line(margin, sig_y + 8 * mm, margin + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin, sig_y + 4.5 * mm, "Prepared By (Procurement Officer)")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, sig_y + 1 * mm, f"User: {po.get('created_by') or 'Authorized Staff'}")

    # Right: Authorized Signatory
    sig2_x = page_w - margin - sig_w
    c.line(sig2_x, sig_y + 8 * mm, sig2_x + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(sig2_x, sig_y + 4.5 * mm, "Authorized Signatory & Official Stamp")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(sig2_x, sig_y + 1 * mm, "Finance Director / Managing Director")

    # --- 8. Page Footer ---
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(0.5)
    c.line(margin, 12 * mm, page_w - margin, 12 * mm)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(margin, 8 * mm, "CONFIDENTIAL — OFFICIAL PURCHASE ORDER — VOUCHER MACHINE BOOKKEEPING")
    c.drawRightString(page_w - margin, 8 * mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page 1 of 1")


# =========================================================================
# 2. GOODS RECEIVED NOTE (GRN) PDF
# =========================================================================

def generate_grn_pdf(grn_or_id, company: dict = None, output_path: str = None) -> str:
    """
    Generate an A4 PDF document for a Goods Received Note (GRN).

    Args:
        grn_or_id: Goods Received Note ID or dictionary.
        company: Optional company dict or output path string.
        output_path: Optional destination path.

    Returns:
        str: Absolute path to generated PDF.
    """
    if isinstance(company, str) and output_path is None:
        output_path = company
        company = None

    if isinstance(grn_or_id, dict):
        grn_data = grn_or_id
        grn_id = grn_data.get("id") or "new"
    else:
        grn_id = int(grn_or_id)
        grn_data = db.get_goods_received_note(grn_id)

    if not grn_data:
        raise ValueError(f"Goods Received Note #{grn_id} not found.")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"grn_{grn_id}_{ts}.pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    page_w, page_h = A4

    _render_single_grn(c, grn_data, page_w, page_h, comp_override=company)
    c.showPage()
    c.save()
    return output_path


def _render_single_grn(c: canvas.Canvas, grn: dict, page_w: float, page_h: float, comp_override: dict = None):
    """Render a single Goods Received Note on an A4 page."""
    margin = 15 * mm
    top_y = page_h - margin

    comp_id = grn.get("company_id") or 1
    comp = comp_override or db.get_company(comp_id) or {}
    comp_name = comp.get("name") or "Main Enterprise"

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin, top_y - 5 * mm, comp_name)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(margin, top_y - 9.5 * mm, "Warehouse Receiving Department & Stores Quality Inspection")

    # Divider Line (Emerald green for receiving / goods in)
    divider_y = top_y - 15 * mm
    c.setStrokeColor(colors.HexColor("#059669"))
    c.setLineWidth(1.5)
    c.line(margin, divider_y, page_w - margin, divider_y)

    # Document Banner
    banner_y = divider_y - 4 * mm
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(colors.HexColor("#047857"))
    c.drawString(margin, banner_y - 4 * mm, "GOODS RECEIVED NOTE (GRN)")

    meta_x = page_w - margin - 75 * mm
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(meta_x, banner_y - 2 * mm, "GRN Number:")
    c.drawString(meta_x, banner_y - 6.5 * mm, "Received Date:")
    c.drawString(meta_x, banner_y - 11 * mm, "Linked PO Number:")

    c.setFont("Helvetica", 8.5)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawRightString(page_w - margin, banner_y - 2 * mm, grn.get("grn_number", ""))
    c.drawRightString(page_w - margin, banner_y - 6.5 * mm, grn.get("grn_date", ""))
    c.drawRightString(page_w - margin, banner_y - 11 * mm, grn.get("po_number", ""))

    # Supplier & Receiving Metadata Cards
    cards_top = banner_y - 17 * mm
    card_w = (page_w - 2 * margin - 6 * mm) / 2.0
    card_h = 24 * mm

    # Left: Vendor
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.6)
    c.roundRect(margin, cards_top - card_h, card_w, card_h, 2 * mm, fill=True, stroke=True)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#047857"))
    c.drawString(margin + 4 * mm, cards_top - 5 * mm, "SUPPLIER / CARRIER:")
    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(margin + 4 * mm, cards_top - 10 * mm, grn.get("supplier_name", ""))
    if grn.get("delivery_note_ref"):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(margin + 4 * mm, cards_top - 15 * mm, f"Delivery Note / Waybill: {grn['delivery_note_ref']}")

    # Right: Receiving Officer
    right_x = margin + card_w + 6 * mm
    c.roundRect(right_x, cards_top - card_h, card_w, card_h, 2 * mm, fill=True, stroke=True)

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor("#047857"))
    c.drawString(right_x + 4 * mm, cards_top - 5 * mm, "RECEIVING OFFICER & STORAGE:")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#0F172A"))
    c.drawString(right_x + 4 * mm, cards_top - 10 * mm, f"Received By: {grn.get('received_by') or 'Storekeeper'}")
    c.drawString(right_x + 4 * mm, cards_top - 15 * mm, f"Warehouse Location: Main Stores")

    # Table of Received Items
    tbl_top = cards_top - card_h - 6 * mm
    col_x = [
        margin,                 # #
        margin + 10 * mm,       # Description
        margin + 90 * mm,       # Unit
        margin + 110 * mm,      # Ordered Qty
        margin + 130 * mm,      # Received Qty
        margin + 150 * mm,      # Rejected Qty
        page_w - margin         # Condition / Notes
    ]

    header_h = 6.5 * mm
    c.setFillColor(colors.HexColor("#047857"))
    c.rect(margin, tbl_top - header_h, page_w - 2 * margin, header_h, fill=True, stroke=False)

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.white)
    c.drawString(col_x[0] + 2 * mm, tbl_top - 4.5 * mm, "#")
    c.drawString(col_x[1] + 1 * mm, tbl_top - 4.5 * mm, "Item Description / Goods Received")
    c.drawString(col_x[2] + 1 * mm, tbl_top - 4.5 * mm, "Unit")
    c.drawRightString(col_x[3] + 16 * mm, tbl_top - 4.5 * mm, "Ordered")
    c.drawRightString(col_x[4] + 16 * mm, tbl_top - 4.5 * mm, "Received")
    c.drawRightString(col_x[5] + 16 * mm, tbl_top - 4.5 * mm, "Rejected")
    c.drawString(col_x[5] + 18 * mm, tbl_top - 4.5 * mm, "Condition Notes")

    curr_y = tbl_top - header_h
    row_h = 6.5 * mm
    lines = grn.get("lines") or []

    for idx, line in enumerate(lines, 1):
        if idx % 2 == 0:
            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.rect(margin, curr_y - row_h, page_w - 2 * margin, row_h, fill=True, stroke=False)

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.4)
        c.line(margin, curr_y - row_h, page_w - margin, curr_y - row_h)

        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(col_x[0] + 2 * mm, curr_y - 4.5 * mm, str(idx))

        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        c.drawString(col_x[1] + 1 * mm, curr_y - 4.5 * mm, line.get("description", "")[:45])

        c.setFont("Helvetica", 7.5)
        c.drawString(col_x[2] + 1 * mm, curr_y - 4.5 * mm, line.get("unit", "pcs"))

        ord_str = f"{line.get('ordered_qty', 0):,.2f}".rstrip('0').rstrip('.')
        rec_str = f"{line.get('received_qty', 0):,.2f}".rstrip('0').rstrip('.')
        rej_str = f"{line.get('rejected_qty', 0):,.2f}".rstrip('0').rstrip('.')

        c.drawRightString(col_x[3] + 16 * mm, curr_y - 4.5 * mm, ord_str)
        c.drawRightString(col_x[4] + 16 * mm, curr_y - 4.5 * mm, rec_str)
        c.drawRightString(col_x[5] + 16 * mm, curr_y - 4.5 * mm, rej_str if float(line.get('rejected_qty', 0)) > 0 else "-")

        cnotes = line.get("condition_notes") or "Good condition"
        c.drawString(col_x[5] + 18 * mm, curr_y - 4.5 * mm, cnotes[:30])

        curr_y -= row_h
        if curr_y < 85 * mm:
            break

    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.6)
    c.rect(margin, curr_y, page_w - 2 * margin, tbl_top - curr_y, fill=False, stroke=True)

    # General Notes
    notes_y = curr_y - 8 * mm
    if grn.get("notes"):
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(margin, notes_y, "RECEIVING REMARKS:")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#0F172A"))
        _draw_wrapped_text(c, grn["notes"], margin, notes_y - 3.5 * mm, page_w - 2 * margin, "Helvetica", 7.5, 3.2 * mm, max_lines=2)

    # Sign-Off Blocks
    sig_y = 25 * mm
    sig_w = 50 * mm

    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.6)

    # Signatory 1: Storekeeper
    c.line(margin, sig_y + 8 * mm, margin + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(margin, sig_y + 4.5 * mm, "Received By (Storekeeper)")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(margin, sig_y + 1 * mm, grn.get("received_by") or "Warehouse Officer")

    # Signatory 2: Quality Inspection
    sig2_x = margin + sig_w + 15 * mm
    c.line(sig2_x, sig_y + 8 * mm, sig2_x + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(sig2_x, sig_y + 4.5 * mm, "Inspected By (Quality Check)")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(sig2_x, sig_y + 1 * mm, "Quality Assurance Officer")

    # Signatory 3: Store Manager
    sig3_x = page_w - margin - sig_w
    c.line(sig3_x, sig_y + 8 * mm, sig3_x + sig_w, sig_y + 8 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(sig3_x, sig_y + 4.5 * mm, "Approved By (Stores Manager)")
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(sig3_x, sig_y + 1 * mm, "Inventory Controller")

    # Footer
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(0.5)
    c.line(margin, 12 * mm, page_w - margin, 12 * mm)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.drawString(margin, 8 * mm, "CONFIDENTIAL — GOODS RECEIVED NOTE — VOUCHER MACHINE BOOKKEEPING")
    c.drawRightString(page_w - margin, 8 * mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Page 1 of 1")
