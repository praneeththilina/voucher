"""
check_printer.py
Check Printing Engine for Voucher Manager v3.0.

Handles:
- Amount-to-words conversion (LKR, multi-currency)
- Millimeter-accurate check field rendering onto pre-printed stock
- Check stub generation (retention copy)
- Batch check PDF compilation
- Calibration page generation for physical check stock alignment
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


def amount_to_words(amount: float, currency: str = "LKR") -> str:
    """
    Convert a numeric amount to formal check-ready English words string.
    
    Handles amounts up to 999,999,999,999.99 (LKR or equivalent).
    Includes cents/decimal part with 'and XX/100' or 'Only' notation.
    
    Args:
        amount: Float or numeric amount (e.g. 125750.50)
        currency: Currency code (e.g. 'LKR', 'USD', 'EUR')
        
    Returns:
        str: e.g. "One Hundred Twenty-Five Thousand Seven Hundred Fifty and 50/100"
    """
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return "Zero Only"

    if amount < 0:
        return f"Negative {amount_to_words(abs(amount), currency)}"

    ONES = [
        "", "One", "Two", "Three", "Four", "Five",
        "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
        "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen"
    ]
    TENS = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty",
        "Sixty", "Seventy", "Eighty", "Ninety"
    ]

    def _say_below_thousand(n: int) -> str:
        if n == 0:
            return ""
        elif n < 20:
            return ONES[n]
        elif n < 100:
            tens = TENS[n // 10]
            ones = ONES[n % 10]
            return f"{tens}-{ones}" if ones else tens
        else:
            hundreds = ONES[n // 100]
            remainder = _say_below_thousand(n % 100)
            return f"{hundreds} Hundred {remainder}".strip() if remainder else f"{hundreds} Hundred"

    int_part = int(round(amount * 100) // 100)
    dec_part = int(round(amount * 100) % 100)

    if int_part == 0 and dec_part == 0:
        return "Zero Only"

    parts = []
    billions = (int_part % 1_000_000_000_000) // 1_000_000_000
    millions = (int_part % 1_000_000_000) // 1_000_000
    thousands = (int_part % 1_000_000) // 1_000
    remainder = int_part % 1_000

    trillions = int_part // 1_000_000_000_000
    if trillions:
        parts.append(f"{_say_below_thousand(trillions)} Trillion")
    if billions:
        parts.append(f"{_say_below_thousand(billions)} Billion")
    if millions:
        parts.append(f"{_say_below_thousand(millions)} Million")
    if thousands:
        parts.append(f"{_say_below_thousand(thousands)} Thousand")
    if remainder:
        parts.append(_say_below_thousand(remainder))

    words = " ".join(parts).strip()
    if not words:
        words = "Zero"

    if dec_part > 0:
        return f"{words} and {dec_part:02d}/100"
    else:
        return f"{words} Only"


def _draw_check_wrapped_text(
    c, text: str, x: float, y: float, max_w: float,
    font_name: str = "Helvetica", font_size: int = 9,
    line_gap: float = 4.5 * mm, max_lines: int = 3
) -> float:
    """
    Wrap text across multiple lines within a given width in millimeters/points.
    """
    c.setFont(font_name, font_size)
    words = text.split()
    lines, curr = [], ""
    for w in words:
        test = f"{curr} {w}".strip()
        if c.stringWidth(test, font_name, font_size) <= max_w:
            curr = test
        else:
            if curr:
                lines.append(curr)
            curr = w
            if len(lines) >= max_lines - 1:
                break
    if curr:
        lines.append(curr)

    cur_y = y
    for line in lines[:max_lines]:
        c.drawString(x, cur_y, line)
        cur_y -= line_gap
    return cur_y


def _draw_signature_image(c, img_bytes: bytes, x: float, y: float, max_w: float = 40 * mm, max_h: float = 15 * mm):
    """Draw a scanned signature image onto the check canvas."""
    if not img_bytes:
        return
    try:
        pil_img = PILImage.open(io.BytesIO(img_bytes))
        w, h = pil_img.size
        if w > 0 and h > 0:
            aspect = w / h
            target_w = min(max_w, max_h * aspect)
            target_h = target_w / aspect
            img_reader = ImageReader(io.BytesIO(img_bytes))
            c.drawImage(img_reader, x, y, width=target_w, height=target_h, mask="auto")
    except Exception as e:
        print(f"Notice: Failed to draw signature image: {e}")


def _draw_check_only(c, check: dict, template: dict, company: dict, signatories: list, y_base: float = 0.0):
    """
    Draw check text fields aligned to physical check stock.
    y_base is 0.0 when printing check only, or bottom offset when printing with stub.
    """
    # Coordinates from template in mm, offset by y_base
    px = float(template.get("payee_x", 45.0)) * mm
    py = y_base + float(template.get("payee_y", 52.0)) * mm
    pmw = float(template.get("payee_max_w", 118.0)) * mm

    ax = float(template.get("amount_box_x", 155.0)) * mm
    ay = y_base + float(template.get("amount_box_y", 52.0)) * mm
    abw = float(template.get("amount_box_w", 42.0)) * mm

    wx = float(template.get("amount_words_x", 10.0)) * mm
    wy = y_base + float(template.get("amount_words_y", 40.0)) * mm
    wmw = float(template.get("amount_words_max_w", 168.0)) * mm

    dx = float(template.get("date_x", 156.0)) * mm
    dy = y_base + float(template.get("date_y", 68.0)) * mm

    # Optional Company Header
    if template.get("print_company_name", 1):
        cx = float(template.get("company_x", 10.0)) * mm
        cy = y_base + float(template.get("company_y", 68.0)) * mm
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#334155"))
        comp_name = company.get("name", "")
        if comp_name:
            c.drawString(cx, cy, comp_name.upper())

    # --- Payee Name ---
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.black)
    payee = check.get("payee_name", "")
    # Word-truncate if exceeds width
    while c.stringWidth(payee, "Helvetica-Bold", 10) > pmw and len(payee) > 5:
        payee = payee[:-1]
    if payee != check.get("payee_name", ""):
        payee = payee[:-3] + "..."
    c.drawString(px, py, payee)

    # --- Amount in Figures ---
    amt = float(check.get("amount", 0.0))
    amt_str = f"**{amt:,.2f}**"
    c.setFont("Helvetica-Bold", 11)
    # Right-align inside amount box
    c.drawRightString(ax + abw, ay, amt_str)

    # --- Amount in Words ---
    words = check.get("amount_words") or amount_to_words(amt, check.get("currency", "LKR"))
    c.setFont("Helvetica", 9)
    _draw_check_wrapped_text(c, words, wx, wy, wmw, font_size=9, line_gap=4.5 * mm)

    # --- Date ---
    raw_date = check.get("check_date", "")
    try:
        dt = datetime.strptime(raw_date, "%Y-%m-%d")
        date_str = dt.strftime("%d/%m/%Y")
    except Exception:
        date_str = raw_date
    c.setFont("Helvetica-Bold", 10)
    c.drawString(dx, dy, date_str)

    # --- Signatories ---
    for sig in signatories:
        order = sig.get("signatory_order", 1)
        sx = float(template.get(f"sig{order}_x", 115.0 if order == 1 else 157.0)) * mm
        sy = y_base + float(template.get(f"sig{order}_y", 12.0)) * mm

        if sig.get("signature_image"):
            _draw_signature_image(c, sig["signature_image"], sx, sy + 3 * mm)

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.black)
        c.drawString(sx, sy, sig.get("name", ""))
        if sig.get("title"):
            c.setFont("Helvetica-Oblique", 6)
            c.drawString(sx, sy - 3 * mm, sig.get("title", ""))

    # --- Draft Watermark ---
    if check.get("status") == "Draft":
        c.saveState()
        c.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.35))
        c.setFont("Helvetica-Bold", 42)
        c.translate(105 * mm, y_base + 35 * mm)
        c.rotate(22)
        c.drawCentredString(0, 0, "DRAFT — NOT NEGOTIABLE")
        c.restoreState()


def _draw_check_stub(c, check: dict, company: dict, y_origin: float):
    """Render the retention stub in the upper half of the page."""
    PAGE_WIDTH = A4[0]
    x = 15 * mm
    y = y_origin - 10 * mm
    line_h = 5.2 * mm

    # Stub Header
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, f"CHECK STUB / RETENTION COPY — {company.get('name', 'Voucher Manager')}")

    c.setFillColor(colors.HexColor("#64748b"))
    c.setFont("Helvetica", 7.5)
    c.drawRightString(PAGE_WIDTH - 15 * mm, y, "RETAIN FOR BOOKKEEPING / AUDIT")
    y -= line_h * 1.3

    # Divider line
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setLineWidth(0.8)
    c.line(x, y, PAGE_WIDTH - 15 * mm, y)
    y -= line_h * 1.1

    def _row(label: str, value: str, bold_val: bool = False):
        nonlocal y
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawString(x, y, f"{label}:")
        c.setFont("Helvetica-Bold" if bold_val else "Helvetica", 8.5)
        c.setFillColor(colors.black)
        c.drawString(x + 36 * mm, y, str(value or "-"))
        y -= line_h

    _row("Check Number", check.get("check_number", ""), bold_val=True)
    _row("Check Date", check.get("check_date", ""))
    if check.get("post_date"):
        _row("Post-Dated For", check.get("post_date", ""), bold_val=True)

    _row("Pay To (Payee)", check.get("payee_name", ""), bold_val=True)
    curr = check.get("currency", "LKR")
    amt = float(check.get("amount", 0.0))
    _row("Amount", f"{curr} {amt:,.2f}", bold_val=True)
    _row("In Words", check.get("amount_words", ""))

    if check.get("voucher_number"):
        _row("Voucher Reference", check.get("voucher_number", ""))
    if check.get("payment_ref"):
        _row("Payment Reference", check.get("payment_ref", ""))
    if check.get("memo"):
        _row("Memo / Description", check.get("memo", ""))

    y -= line_h * 0.4
    c.setStrokeColor(colors.HexColor("#cbd5e1"))
    c.setLineWidth(0.5)
    c.line(x, y, PAGE_WIDTH - 15 * mm, y)
    y -= line_h * 0.8

    _row("Prepared By", check.get("prepared_by", ""))
    _row("Authorized By", check.get("authorized_by", ""))
    _row("Lifecycle Status", check.get("status", "Issued"))
    _row("Printed At", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _draw_check_with_stub(c, check: dict, template: dict, company: dict, signatories: list):
    """Draw retention stub on top half and check on bottom half."""
    PAGE_WIDTH, PAGE_HEIGHT = A4
    STUB_HEIGHT = PAGE_HEIGHT / 2

    # Draw stub on top half
    _draw_check_stub(c, check, company, y_origin=PAGE_HEIGHT)

    # Draw perforated cut line
    c.setStrokeColor(colors.HexColor("#94a3b8"))
    c.setLineWidth(0.6)
    c.setDash(4, 3)
    c.line(15 * mm, STUB_HEIGHT, PAGE_WIDTH - 15 * mm, STUB_HEIGHT)
    c.setDash()

    c.setFont("Helvetica-Oblique", 6.5)
    c.setFillColor(colors.HexColor("#64748b"))
    c.drawCentredString(PAGE_WIDTH / 2, STUB_HEIGHT + 1.2 * mm, "✂ — — — TEAR / CUT HERE BEFORE DEPOSITING — — — ✂")

    # Draw check on bottom half
    _draw_check_only(c, check, template, company, signatories, y_base=0.0)


def _draw_voided_page(c, check: dict, template: dict):
    """Draw voided check with dark red VOID watermark and strikethrough."""
    PAGE_WIDTH, PAGE_HEIGHT = A4
    c.saveState()
    c.setFillColor(colors.HexColor("#dc2626"))
    c.setFont("Helvetica-Bold", 60)
    c.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
    c.rotate(30)
    c.drawCentredString(0, 0, "VOID — CANCELLED")
    c.restoreState()

    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#dc2626"))
    c.drawString(20 * mm, PAGE_HEIGHT - 30 * mm, f"VOIDED CHECK: {check.get('check_number', '')}")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    c.drawString(20 * mm, PAGE_HEIGHT - 36 * mm, f"Payee: {check.get('payee_name', '')} | Amount: {check.get('currency', 'LKR')} {check.get('amount', 0):,.2f}")


def generate_check_pdf(
    check_ids: list,
    output_path: str = None,
    include_stub: bool = True
) -> str:
    """
    Generate print-ready PDF for one or more check IDs.
    Returns absolute path to generated PDF.
    """
    if not check_ids:
        raise ValueError("No check IDs provided for printing.")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"checks_{ts}.pdf")

    checks_data = db.get_checks_full_by_ids(check_ids)
    if not checks_data:
        raise ValueError("Could not find check records for the given IDs.")

    c = canvas.Canvas(output_path, pagesize=A4)

    for item in checks_data:
        check = item["check"]
        template = item["template"]
        company = item["company"]
        signatories = item.get("signatories", [])

        if check.get("status") == "Voided":
            _draw_voided_page(c, check, template)
        else:
            if include_stub:
                _draw_check_with_stub(c, check, template, company, signatories)
            else:
                _draw_check_only(c, check, template, company, signatories, y_base=0.0)

        c.showPage()

    c.save()
    return output_path


def generate_calibration_pdf(output_path: str = None) -> str:
    """
    Generate an A4 alignment calibration grid sheet.
    Helps users calibrate physical check stock against a light source.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"check_calibration_{ts}.pdf")

    PAGE_WIDTH, PAGE_HEIGHT = A4
    c = canvas.Canvas(output_path, pagesize=A4)

    # Title & instructions
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawString(15 * mm, PAGE_HEIGHT - 15 * mm, "Check Stock Calibration Grid (A4)")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#475569"))
    c.drawString(
        15 * mm, PAGE_HEIGHT - 20 * mm,
        "Instructions: Place your pre-printed bank check over this sheet at bottom-left (0, 0) against a window or light source."
    )

    # 10mm grid lines on bottom 100mm (check area)
    c.setLineWidth(0.3)
    c.setStrokeColor(colors.HexColor("#cbd5e1"))

    # Vertical lines every 10mm
    for x in range(0, int(PAGE_WIDTH / mm), 10):
        c.line(x * mm, 0, x * mm, 100 * mm)
        c.setFont("Helvetica", 5)
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(x * mm + 0.5 * mm, 1 * mm, f"{x}")

    # Horizontal lines every 10mm
    for y in range(0, 101, 10):
        c.line(0, y * mm, PAGE_WIDTH, y * mm)
        c.setFont("Helvetica", 5)
        c.setFillColor(colors.HexColor("#94a3b8"))
        c.drawString(1 * mm, y * mm + 0.5 * mm, f"{y}")

    # Sample template reference boxes
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.HexColor("#2563eb"))

    # Payee line box
    c.rect(45 * mm, 50 * mm, 118 * mm, 6 * mm)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(colors.HexColor("#2563eb"))
    c.drawString(46 * mm, 51.5 * mm, "PAYEE LINE (X: 45mm, Y: 52mm, W: 118mm)")

    # Amount box
    c.rect(155 * mm, 50 * mm, 42 * mm, 6 * mm)
    c.drawString(156 * mm, 51.5 * mm, "AMOUNT BOX (X: 155mm, Y: 52mm)")

    # Amount words
    c.rect(10 * mm, 38 * mm, 168 * mm, 6 * mm)
    c.drawString(11 * mm, 39.5 * mm, "AMOUNT IN WORDS (X: 10mm, Y: 40mm)")

    # Date
    c.rect(156 * mm, 66 * mm, 35 * mm, 6 * mm)
    c.drawString(157 * mm, 67.5 * mm, "DATE (X: 156mm, Y: 68mm)")

    # Signatories
    c.rect(115 * mm, 10 * mm, 35 * mm, 10 * mm)
    c.drawString(116 * mm, 14 * mm, "SIG 1 (X: 115, Y: 12)")

    c.rect(157 * mm, 10 * mm, 35 * mm, 10 * mm)
    c.drawString(158 * mm, 14 * mm, "SIG 2 (X: 157, Y: 12)")

    c.showPage()
    c.save()
    return output_path
