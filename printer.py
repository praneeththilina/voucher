"""
PDF Generation & Printing Engine for the Voucher Printing Tool.
Generates print-ready PDFs with 2 vouchers per A4 page.
Attachment pages follow with voucher number references.
"""

import os
import io
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

import database as db

# A4 dimensions
PAGE_WIDTH, PAGE_HEIGHT = A4  # 595.27, 841.89 points
HALF_HEIGHT = PAGE_HEIGHT / 2
MARGIN = 15 * mm
VOUCHER_WIDTH = PAGE_WIDTH - 2 * MARGIN
VOUCHER_HEIGHT = HALF_HEIGHT - 2 * MARGIN


def generate_voucher_pdf(voucher_ids, output_path=None):
    """
    Generate a PDF with 2 vouchers per A4 page.
    Returns the path to the generated PDF file.
    
    Args:
        voucher_ids: list of voucher IDs to print
        output_path: optional output path. If None, uses a temp file.
    
    Returns:
        Path to the generated PDF.
    """
    if not output_path:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"vouchers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )

    c = canvas.Canvas(output_path, pagesize=A4)

    # Collect all voucher data and attachments
    vouchers_data = []
    all_attachments = []

    for vid in voucher_ids:
        vdata = db.get_voucher(vid)
        if vdata:
            vouchers_data.append(vdata)
            for att in vdata.get("attachments", []):
                att_full = db.get_attachment_data(att["id"])
                if att_full:
                    all_attachments.append({
                        "voucher_number": vdata["voucher"]["voucher_number"],
                        "filename": att_full["filename"],
                        "file_data": att_full["file_data"],
                        "file_type": att_full["file_type"],
                    })

    # Draw vouchers: 2 per page
    for i in range(0, len(vouchers_data), 2):
        # Top voucher
        _draw_voucher(c, vouchers_data[i], y_offset=HALF_HEIGHT)

        # Bottom voucher (if exists)
        if i + 1 < len(vouchers_data):
            _draw_voucher(c, vouchers_data[i + 1], y_offset=0)

        # Draw cut line
        c.setStrokeColor(colors.grey)
        c.setDash(6, 3)
        c.line(MARGIN, HALF_HEIGHT, PAGE_WIDTH - MARGIN, HALF_HEIGHT)
        c.setDash()

        c.showPage()

    # Draw attachment pages (combine small receipts/slips on same A4 page, large on full page)
    _render_attachments(c, all_attachments)

    c.save()
    return output_path


def _draw_wrapped_text(c, text, x, y, max_w, font_name="Helvetica", font_size=7, color=None, line_gap=2.8 * mm):
    """Draw text, wrapping words to multiple lines if they exceed max_w. Returns new y."""
    if color:
        c.setFillColor(color)
    c.setFont(font_name, font_size)
    words = text.split()
    if not words:
        return y
    lines = []
    curr = ""
    for w in words:
        test = f"{curr} {w}".strip()
        if c.stringWidth(test, font_name, font_size) <= max_w:
            curr = test
        else:
            if curr:
                lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)

    cur_y = y
    for line in lines:
        c.drawString(x, cur_y, line)
        cur_y -= line_gap
    return cur_y


def _draw_voucher(c, vdata, y_offset):
    """Draw a single voucher in the given half of the page."""
    voucher = vdata["voucher"]
    line_items = vdata["line_items"]

    # Outer bounding box
    box_x = MARGIN
    box_y = y_offset + MARGIN
    box_w = PAGE_WIDTH - 2 * MARGIN
    box_h = HALF_HEIGHT - 2 * MARGIN

    # Generous padding inside border so border lines NEVER cross any content
    pad_x = 4 * mm
    pad_y = 3.5 * mm

    inner_left = box_x + pad_x
    inner_right = box_x + box_w - pad_x
    inner_top = box_y + box_h - pad_y
    inner_w = inner_right - inner_left

    # ---- Company Profile & Header ----
    company = vdata.get("company")
    if not company:
        comp_id = voucher.get("company_id") or 1
        company = db.get_company(comp_id) or {}

    c_name = company.get("name") or "PAYMENT VOUCHER"
    c_tagline = company.get("tagline", "")
    c_address = company.get("address", "")
    c_contact = company.get("contact", "")
    c_email = company.get("email", "")
    logo_data = company.get("logo")

    # Right-hand Voucher Metadata
    meta_w = 48 * mm
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(inner_right, inner_top - 1.5 * mm, "PAYMENT VOUCHER")

    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawRightString(inner_right, inner_top - 5.5 * mm, f"Voucher #: {voucher['voucher_number']}")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawRightString(inner_right, inner_top - 9 * mm, f"Date: {voucher['date']}")

    # Left-hand Logo & Company Details
    avail_left_w = inner_w - meta_w - 4 * mm
    logo_w = 0
    draw_lh = 0

    if logo_data:
        try:
            from PIL import Image as PILImage
            from reportlab.lib.utils import ImageReader
            l_stream = io.BytesIO(logo_data)
            pil_logo = PILImage.open(l_stream)
            lw, lh = pil_logo.size
            max_lh = 13 * mm
            max_lw = 38 * mm
            ratio = min(max_lw / lw, max_lh / lh)
            draw_lw = lw * ratio
            draw_lh = lh * ratio
            logo_y = inner_top - draw_lh
            l_stream.seek(0)
            c.drawImage(ImageReader(l_stream), inner_left, logo_y, draw_lw, draw_lh)
            logo_w = draw_lw + 3.5 * mm
        except Exception:
            logo_w = 0
            draw_lh = 0

    text_x = inner_left + logo_w
    avail_text_w = avail_left_w - logo_w

    # Company Name
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(text_x, inner_top - 2.5 * mm, c_name)
    cur_y = inner_top - 2.5 * mm - 3.5 * mm

    # Tagline
    if c_tagline:
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(text_x, cur_y, c_tagline)
        cur_y -= 3.2 * mm

    # Full Address (wrapped - no truncation!)
    if c_address:
        cur_y = _draw_wrapped_text(
            c, c_address, text_x, cur_y, avail_text_w,
            font_name="Helvetica", font_size=7, color=colors.HexColor("#475569"), line_gap=2.8 * mm
        )

    # Contact & Email (wrapped - no truncation!)
    contact_parts = []
    if c_contact:
        contact_parts.append(f"Tel: {c_contact}")
    if c_email:
        contact_parts.append(f"Email: {c_email}")
    if contact_parts:
        cur_y = _draw_wrapped_text(
            c, "  |  ".join(contact_parts), text_x, cur_y, avail_text_w,
            font_name="Helvetica", font_size=7, color=colors.HexColor("#475569"), line_gap=2.8 * mm
        )

    # Calculate divider y position safely below both logo and text
    logo_bottom = (inner_top - draw_lh) if draw_lh else inner_top
    divider_y = min(cur_y, logo_bottom, inner_top - 12 * mm) - 2 * mm

    # Status badge if Cancelled
    status = voucher.get("status", "Active")
    if status == "Cancelled":
        c.setFillColor(colors.red)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(box_x + box_w / 2, divider_y + 1 * mm, "*** CANCELLED ***")
        c.setFillColor(colors.black)
        divider_y -= 3.5 * mm

    # Horizontal divider line under header
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setLineWidth(0.75)
    c.line(inner_left, divider_y, inner_right, divider_y)

    current_y = divider_y - 4 * mm

    # ---- People fields ----
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    fields = [
        ("Cash Given By", voucher.get("cash_given_by", "")),
        ("Paid To", voucher.get("paid_to", "")),
    ]
    spent_by = voucher.get("spent_by", "")
    if spent_by and spent_by != voucher.get("paid_to", ""):
        fields.append(("Spent By", spent_by))

    for label, value in fields:
        c.setFont("Helvetica-Bold", 8)
        c.drawString(inner_left, current_y, f"{label}:")
        c.setFont("Helvetica", 9)
        c.drawString(inner_left + 28 * mm, current_y, value)
        current_y -= 4.5 * mm

    current_y -= 1.5 * mm

    # ---- Line Items Table ----
    col_widths = [inner_w * 0.08, inner_w * 0.46, inner_w * 0.24, inner_w * 0.22]

    table_data = [["#", "Description", "Category", "Amount"]]
    for idx, item in enumerate(line_items, 1):
        table_data.append([
            str(idx),
            item.get("description", ""),
            item.get("category", ""),
            f"{item.get('amount', 0):,.2f}",
        ])

    # Total row
    table_data.append(["", "", "TOTAL", f"{voucher.get('total_amount', 0):,.2f}"])

    # Determine max rows that fit
    available_height = current_y - (box_y + pad_y + 26 * mm)
    row_height = 5 * mm
    max_rows = max(int(available_height / row_height), 4)

    # Truncate if too many rows
    if len(table_data) > max_rows:
        keep = max_rows - 2
        table_data = table_data[:1] + table_data[1:1+keep] + [["", "", "...", ""], table_data[-1]]

    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('ALIGN', (2, -1), (2, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -2), 0.5, colors.grey),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    table_width, table_height = table.wrap(inner_w, available_height)
    table.drawOn(c, inner_left, current_y - table_height)
    current_y -= table_height + 3.5 * mm

    # ---- Bill Status ----
    bill_status = voucher.get("bill_status", "Pending")
    c.setFont("Helvetica", 8)
    c.drawString(inner_left, current_y, "Bill Status: ")
    if bill_status == "Received":
        c.setFillColor(colors.Color(0, 0.5, 0))
    elif bill_status == "Pending":
        c.setFillColor(colors.red)
    else:
        c.setFillColor(colors.Color(0.8, 0.5, 0))
    c.setFont("Helvetica-Bold", 8)
    c.drawString(inner_left + 20 * mm, current_y, bill_status)
    c.setFillColor(colors.black)

    # Attachment indicator
    att_count = len(vdata.get("attachments", []))
    if att_count > 0:
        c.setFont("Helvetica", 8)
        c.drawRightString(
            inner_right, current_y,
            f"Attachments: {att_count} file(s)"
        )

    current_y -= 7 * mm

    # ---- Signature Lines ----
    sig_y = box_y + pad_y + 8 * mm
    sig_width = inner_w / 3
    sig_labels = ["Prepared By", "Approved By", "Received By"]
    sig_values = [
        voucher.get("prepared_by", ""),
        voucher.get("approved_by", ""),
        "",
    ]

    for i, (label, value) in enumerate(zip(sig_labels, sig_values)):
        sx = inner_left + i * sig_width
        c.setFont("Helvetica", 7)
        # Signature line
        c.line(sx, sig_y, sx + sig_width - 8 * mm, sig_y)
        c.drawString(sx, sig_y - 4 * mm, label)
        if value:
            c.setFont("Helvetica", 8)
            c.drawString(sx, sig_y + 2.5 * mm, value)

    # ---- Outer Box Border ----
    c.setStrokeColor(colors.HexColor("#334155"))
    c.setLineWidth(0.6)
    c.rect(box_x, box_y, box_w, box_h)


def _is_image_attachment(att):
    """Check if attachment is an image (by MIME, extension, or raw bytes)."""
    file_type = att.get("file_type", "").lower()
    if "image/" in file_type:
        return True
    filename = att.get("filename", "").lower()
    if any(filename.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"]):
        return True
    file_data = att.get("file_data")
    if file_data:
        try:
            from PIL import Image as PILImage
            with PILImage.open(io.BytesIO(file_data)) as im:
                im.verify()
            return True
        except Exception:
            pass
    return False


def _is_pdf_attachment(att):
    """Check if attachment is a PDF document."""
    file_type = att.get("file_type", "").lower()
    if "pdf" in file_type:
        return True
    filename = att.get("filename", "").lower()
    if filename.endswith(".pdf"):
        return True
    file_data = att.get("file_data")
    if file_data and file_data.startswith(b"%PDF"):
        return True
    return False


def _is_small_attachment(att):
    """
    Check attachment resolution and size.
    Returns True if attachment is a small image (e.g. POS slip, fuel receipt, stub)
    that should be combined with other small attachments on the same A4 page to save paper.
    """
    if not _is_image_attachment(att):
        return False

    file_data = att.get("file_data")
    if not file_data:
        return False

    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(file_data))
        w, h = img.size
        # Full A4 at 150-300 DPI is 1240x1754 to 2480x3508.
        # If dimensions are within receipt/slip proportions (w <= 1150 and h <= 1400)
        # or total pixels <= 1.3 Megapixels, it's considered a small receipt/slip.
        if (w <= 1150 and h <= 1400) or (w <= 1400 and h <= 900) or (w * h <= 1_350_000):
            return True
        return False
    except Exception:
        return False


def _draw_attachment_in_box(c, att, box_x, box_y, box_w, box_h):
    """
    Draw a single attachment in a designated bounding box.
    CRITICAL: Preserves strict aspect ratio - NEVER stretches, distorts, or crops image.
    Includes reference header showing voucher number and filename.
    """
    voucher_number = att["voucher_number"]
    filename = att["filename"]
    file_data = att.get("file_data")
    file_type = att.get("file_type", "")

    # Draw card border with subtle outline
    c.setStrokeColor(colors.Color(0.7, 0.75, 0.82))
    c.setLineWidth(0.75)
    c.setDash(3, 2)
    c.rect(box_x, box_y, box_w, box_h)
    c.setDash()

    # Header bar
    header_h = 13 * mm
    c.setFillColor(colors.Color(0.94, 0.96, 0.98))
    c.rect(box_x, box_y + box_h - header_h, box_w, header_h, fill=1, stroke=0)
    c.setStrokeColor(colors.Color(0.82, 0.86, 0.90))
    c.line(box_x, box_y + box_h - header_h, box_x + box_w, box_y + box_h - header_h)

    # Header text
    c.setFillColor(colors.Color(0.1, 0.2, 0.4))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(box_x + 3 * mm, box_y + box_h - 5 * mm, f"Voucher: {voucher_number}")
    c.setFillColor(colors.Color(0.35, 0.4, 0.48))
    c.setFont("Helvetica", 7.5)
    display_fn = filename if len(filename) <= 32 else filename[:29] + "..."
    c.drawString(box_x + 3 * mm, box_y + box_h - 10 * mm, f"File: {display_fn}")

    # Available drawing area inside box
    padding = 2.5 * mm
    avail_w = box_w - 2 * padding
    avail_h = box_h - header_h - 2 * padding
    content_x = box_x + padding
    content_y = box_y + padding

    if file_data and _is_image_attachment(att):
        try:
            from PIL import Image as PILImage
            from reportlab.lib.utils import ImageReader

            img_stream = io.BytesIO(file_data)
            pil_img = PILImage.open(img_stream)
            img_w, img_h = pil_img.size

            # Strictly maintain aspect ratio: min ratio in both dimensions
            ratio = min(avail_w / img_w, avail_h / img_h)
            draw_w = img_w * ratio
            draw_h = img_h * ratio

            # Center proportionally in the slot
            draw_x = content_x + (avail_w - draw_w) / 2
            draw_y = content_y + (avail_h - draw_h) / 2

            img_stream.seek(0)
            img_reader = ImageReader(img_stream)
            c.drawImage(img_reader, draw_x, draw_y, draw_w, draw_h)
        except Exception as e:
            c.setFillColor(colors.Color(0.7, 0.1, 0.1))
            c.setFont("Helvetica", 8)
            c.drawCentredString(
                box_x + box_w / 2, box_y + (box_h - header_h) / 2,
                f"[Image display error: {str(e)[:35]}]"
            )
    else:
        c.setFillColor(colors.Color(0.3, 0.3, 0.3))
        c.setFont("Helvetica", 8)
        c.drawCentredString(
            box_x + box_w / 2, box_y + (box_h - header_h) / 2,
            f"[{filename} — {file_type or 'Document'}]"
        )


def _draw_two_attachments_page(c, attachments):
    """Draw 2 small attachments stacked vertically on a single A4 page."""
    c.setFillColor(colors.Color(0.2, 0.25, 0.35))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN + 1.5 * mm, "VOUCHER ATTACHMENTS (RECEIPTS & SLIPS)")

    gap = 6 * mm
    total_h = PAGE_HEIGHT - 2 * MARGIN - 6 * mm
    slot_h = (total_h - gap) / 2
    slot_w = PAGE_WIDTH - 2 * MARGIN

    # Top slot
    top_y = MARGIN + slot_h + gap
    _draw_attachment_in_box(c, attachments[0], MARGIN, top_y, slot_w, slot_h)

    # Bottom slot
    bottom_y = MARGIN
    _draw_attachment_in_box(c, attachments[1], MARGIN, bottom_y, slot_w, slot_h)


def _draw_grid_attachments_page(c, attachments):
    """Draw 3 or 4 small attachments in a 2x2 grid on a single A4 page."""
    c.setFillColor(colors.Color(0.2, 0.25, 0.35))
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN + 1.5 * mm, "VOUCHER ATTACHMENTS (RECEIPTS & SLIPS)")

    gap_x = 5 * mm
    gap_y = 5 * mm
    total_w = PAGE_WIDTH - 2 * MARGIN
    total_h = PAGE_HEIGHT - 2 * MARGIN - 6 * mm

    slot_w = (total_w - gap_x) / 2
    slot_h = (total_h - gap_y) / 2

    coords = [
        (MARGIN, MARGIN + slot_h + gap_y),                   # Top-Left
        (MARGIN + slot_w + gap_x, MARGIN + slot_h + gap_y),  # Top-Right
        (MARGIN, MARGIN),                                    # Bottom-Left
        (MARGIN + slot_w + gap_x, MARGIN),                   # Bottom-Right
    ]

    for idx, att in enumerate(attachments[:4]):
        bx, by = coords[idx]
        _draw_attachment_in_box(c, att, bx, by, slot_w, slot_h)


def _render_pdf_attachment(c, attachment):
    """
    Render each page of a PDF attachment as a full page in the output PDF using pypdfium2.
    """
    voucher_number = attachment["voucher_number"]
    filename = attachment["filename"]
    file_data = attachment.get("file_data")
    if not file_data:
        return

    try:
        import pypdfium2 as pdfium
        from reportlab.lib.utils import ImageReader

        doc = pdfium.PdfDocument(file_data)
        total_pages = len(doc)
        for page_idx in range(total_pages):
            page = doc[page_idx]
            pil_img = page.render(scale=2.0).to_pil()
            img_w, img_h = pil_img.size

            # Header
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(colors.Color(0.1, 0.2, 0.4))
            header_text = f"Attachment for {voucher_number}"
            if total_pages > 1:
                header_text += f" (Page {page_idx + 1} of {total_pages})"
            c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN, header_text)

            c.setFont("Helvetica", 8.5)
            c.setFillColor(colors.Color(0.35, 0.4, 0.48))
            c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN - 4.5 * mm, f"File: {filename}")

            # Draw outer border
            c.setStrokeColor(colors.Color(0.75, 0.8, 0.85))
            c.setDash(3, 2)
            c.rect(MARGIN, MARGIN, PAGE_WIDTH - 2 * MARGIN, PAGE_HEIGHT - 2 * MARGIN - 12 * mm)
            c.setDash()

            # Calculate fitting area
            avail_w = PAGE_WIDTH - 2 * MARGIN - 8 * mm
            avail_h = PAGE_HEIGHT - 2 * MARGIN - 20 * mm

            ratio = min(avail_w / img_w, avail_h / img_h)
            draw_w = img_w * ratio
            draw_h = img_h * ratio
            draw_x = MARGIN + 4 * mm + (avail_w - draw_w) / 2
            draw_y = MARGIN + 4 * mm + (avail_h - draw_h) / 2

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            img_reader = ImageReader(buf)
            c.drawImage(img_reader, draw_x, draw_y, draw_w, draw_h)

            c.showPage()
    except Exception as e:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.red)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, f"Could not render PDF: {e}")
        c.showPage()


def _draw_attachment_page(c, attachment):
    """Draw an attachment on a full page with voucher reference header."""
    voucher_number = attachment["voucher_number"]
    filename = attachment["filename"]
    file_data = attachment.get("file_data")
    file_type = attachment.get("file_type", "")
    if not file_data:
        return

    # Header
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.Color(0.1, 0.2, 0.4))
    c.drawCentredString(
        PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN,
        f"Attachment for {voucher_number}"
    )
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.Color(0.35, 0.4, 0.48))
    c.drawCentredString(
        PAGE_WIDTH / 2, PAGE_HEIGHT - MARGIN - 5 * mm,
        f"File: {filename}"
    )

    # Draw border
    c.setStrokeColor(colors.Color(0.75, 0.8, 0.85))
    c.setDash(3, 2)
    c.rect(MARGIN, MARGIN, PAGE_WIDTH - 2 * MARGIN, PAGE_HEIGHT - 2 * MARGIN - 15 * mm)
    c.setDash()

    if _is_image_attachment(attachment):
        try:
            from PIL import Image as PILImage
            from reportlab.lib.utils import ImageReader

            img_stream = io.BytesIO(file_data)
            pil_img = PILImage.open(img_stream)
            img_w, img_h = pil_img.size

            max_width = PAGE_WIDTH - 4 * MARGIN
            max_height = PAGE_HEIGHT - 4 * MARGIN - 20 * mm

            ratio = min(max_width / img_w, max_height / img_h)
            draw_width = img_w * ratio
            draw_height = img_h * ratio
            img_x = (PAGE_WIDTH - draw_width) / 2
            img_y = (PAGE_HEIGHT - draw_height) / 2 - 5 * mm

            img_stream.seek(0)
            img_reader = ImageReader(img_stream)
            c.drawImage(img_reader, img_x, img_y, draw_width, draw_height)
        except Exception as e:
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.red)
            c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, f"[Image could not be rendered: {str(e)}]")
    else:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.Color(0.3, 0.3, 0.3))
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT / 2, f"[Attachment: {filename} — Type: {file_type or 'Document'}]")


def _render_attachments(c, all_attachments):
    """
    Render all voucher attachments:
    - Multi-page PDFs: Each page rendered crisp and clear at 2x resolution with voucher header.
    - Small receipt/slip images: Combined up to 4 per page.
    - Large images: Dedicated full A4 page.
    - Never stretches or crops attachments; preserves exact aspect ratio.
    """
    if not all_attachments:
        return

    small_batch = []

    def flush_small_batch():
        nonlocal small_batch
        if not small_batch:
            return
        if len(small_batch) == 1:
            _draw_attachment_page(c, small_batch[0])
            c.showPage()
        elif len(small_batch) == 2:
            _draw_two_attachments_page(c, small_batch)
            c.showPage()
        else:
            _draw_grid_attachments_page(c, small_batch)
            c.showPage()
        small_batch = []

    for att in all_attachments:
        file_data = att.get("file_data")
        if not file_data:
            continue

        if _is_pdf_attachment(att):
            flush_small_batch()
            _render_pdf_attachment(c, att)
        elif _is_small_attachment(att):
            small_batch.append(att)
            if len(small_batch) == 4:
                flush_small_batch()
        else:
            flush_small_batch()
            _draw_attachment_page(c, att)
            c.showPage()

    flush_small_batch()


def print_pdf(pdf_path):
    """Send a PDF to the default Windows printer."""
    try:
        os.startfile(pdf_path, "print")
        return True
    except Exception as e:
        print(f"Print error: {e}")
        return False


def open_pdf(pdf_path):
    """Open a PDF for preview (in default PDF viewer)."""
    try:
        os.startfile(pdf_path)
        return True
    except Exception as e:
        print(f"Open error: {e}")
        return False
