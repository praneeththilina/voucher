"""
reports/report_printer.py
Multi-Page High-Precision Financial Report PDF Engine using ReportLab Platypus.

Generates publication-quality financial reports:
- Profit & Loss (Income Statement)
- Balance Sheet (Statement of Financial Position)
- Trial Balance
- Cash Flow Statement

Features:
- Two-pass NumberedCanvas for exact "Page X of Y" page numbers and headers/footers
- Elegant styling with corporate palettes, sharp borders, and double-underline grand totals
- Dynamic company logo integration
- Sign-off approval blocks
"""

import os
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
pt = 1  # Base unit in ReportLab is points (1/72 inch)
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
    Image as PlatypusImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from PIL import Image as PILImage


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y' footers
    and running headers across all pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        page_w, page_h = A4
        margin = 36 * pt

        # Top running header on pages > 1
        if self._pageNumber > 1:
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(margin, page_h - 26 * pt, getattr(self, "doc_title", "Financial Statement"))
            self.drawRightString(page_w - margin, page_h - 26 * pt, getattr(self, "doc_subtitle", ""))
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(margin, page_h - 30 * pt, page_w - margin, page_h - 30 * pt)

        # Footer
        footer_y = 26 * pt
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(margin, footer_y + 12 * pt, page_w - margin, footer_y + 12 * pt)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(margin, footer_y, "CONFIDENTIAL — VOUCHER MANAGER SME BOOKKEEPING")
        timestamp_str = getattr(self, "doc_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.drawCentredString(page_w / 2.0, footer_y, f"Generated: {timestamp_str}")
        self.drawRightString(page_w - margin, footer_y, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def _format_currency(val: float, currency: str = "") -> str:
    """Format floating point numbers as accounting currency string."""
    if abs(val) < 0.001:
        return "0.00"
    if val < 0:
        return f"({abs(val):,.2f})"
    return f"{val:,.2f}"


def _build_header_elements(report_data: dict, title: str, subtitle: str, styles: dict) -> list:
    """Create standard corporate letterhead banner for reports."""
    elements = []
    comp_name = report_data.get("company_name", "Main Enterprise")
    tax_num = report_data.get("tax_number", "")
    addr = report_data.get("company_address", "")
    phone = report_data.get("company_phone", "")
    email = report_data.get("company_email", "")
    logo_path = report_data.get("logo_path", "")

    contact_parts = []
    if tax_num:
        contact_parts.append(f"Tax / VAT ID: {tax_num}")
    if addr:
        contact_parts.append(addr)
    if phone:
        contact_parts.append(f"Tel: {phone}")
    if email:
        contact_parts.append(email)
    contact_str = " | ".join(contact_parts)

    left_paras = [
        Paragraph(comp_name, styles["CompTitle"]),
    ]
    if contact_str:
        left_paras.append(Paragraph(contact_str, styles["CompSub"]))

    # Right side: Logo if available
    logo_cell = ""
    if logo_path and os.path.exists(logo_path):
        try:
            with PILImage.open(logo_path) as im:
                w, h = im.size
                aspect = h / float(w)
                target_w = min(110.0, float(w))
                target_h = target_w * aspect
                if target_h > 45.0:
                    target_h = 45.0
                    target_w = target_h / aspect
            logo_cell = PlatypusImage(logo_path, width=target_w * pt, height=target_h * pt)
        except Exception:
            logo_cell = ""

    header_table_data = [[left_paras, logo_cell]]
    header_table = Table(header_table_data, colWidths=[400 * pt, 120 * pt])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8 * pt))

    # Divider bar
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceBefore=0, spaceAfter=8 * pt))

    # Report title section
    elements.append(Paragraph(title, styles["ReportTitle"]))
    elements.append(Paragraph(subtitle, styles["ReportSubtitle"]))
    elements.append(Spacer(1, 10 * pt))
    return elements


def _get_styles():
    """Build typography and styling rules for ReportLab Platypus."""
    base_styles = getSampleStyleSheet()
    styles = {
        "CompTitle": ParagraphStyle(
            "CompTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#0F172A")
        ),
        "CompSub": ParagraphStyle(
            "CompSub",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#475569")
        ),
        "ReportTitle": ParagraphStyle(
            "ReportTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1E3A8A"),
            alignment=TA_LEFT
        ),
        "ReportSubtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),
            alignment=TA_LEFT
        ),
        "CellCode": ParagraphStyle(
            "CellCode",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#64748B")
        ),
        "CellName": ParagraphStyle(
            "CellName",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#1E293B")
        ),
        "CellCategory": ParagraphStyle(
            "CellCategory",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B")
        ),
        "CellAmount": ParagraphStyle(
            "CellAmount",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#0F172A")
        ),
        "HeaderCell": ParagraphStyle(
            "HeaderCell",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=colors.white
        ),
        "HeaderCellRight": ParagraphStyle(
            "HeaderCellRight",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            textColor=colors.white
        ),
        "SignTitle": ParagraphStyle(
            "SignTitle",
            parent=base_styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B")
        ),
    }
    return styles


def _build_signoff_block() -> KeepTogether:
    """Create accounting sign-off block."""
    sign_data = [
        ["Prepared By:", "Verified / Audited By:", "Approved By:"],
        ["", "", ""],
        ["________________________", "________________________", "________________________"],
        ["Finance Officer", "Senior Accountant", "Managing Director / Owner"],
        ["Date: _______________", "Date: _______________", "Date: _______________"]
    ]
    t = Table(sign_data, colWidths=[173 * pt, 173 * pt, 174 * pt])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#475569")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 20 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * pt),
    ]))
    return KeepTogether([Spacer(1, 14 * pt), t])


# =========================================================================
# 1. PROFIT & LOSS PDF
# =========================================================================

def generate_profit_loss_pdf(report_data: dict, output_path: str = None) -> str:
    """
    Generate an A4 publication-quality Profit & Loss Statement PDF.

    Args:
        report_data: Dictionary from generate_profit_loss.
        output_path: Optional output path.

    Returns:
        str: Absolute path of the generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"profit_loss_{ts}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=36 * pt,
    )

    styles = _get_styles()
    period = report_data["period"]
    curr = report_data["currency"]
    title = "STATEMENT OF PROFIT & LOSS"
    subtitle = f"For the Period: {period['start_date']} to {period['end_date']}  |  All amounts in {curr}"

    elements = _build_header_elements(report_data, title, subtitle, styles)

    # Main P&L Table Rows
    # Col Widths: Code (55pt), Description (240pt), Details (100pt), Amount (125pt) = 520pt
    col_w = [55 * pt, 240 * pt, 100 * pt, 125 * pt]
    rows = []
    tstyles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * pt),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
    ]

    # Header Row
    rows.append([
        Paragraph("Code", styles["HeaderCell"]),
        Paragraph("Account / Category Description", styles["HeaderCell"]),
        Paragraph("% of Revenue", styles["HeaderCellRight"]),
        Paragraph(f"Amount ({curr})", styles["HeaderCellRight"]),
    ])

    def _add_section_header(name):
        idx = len(rows)
        rows.append(["", name.upper(), "", ""])
        tstyles.extend([
            ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F1F5F9")),
            ("FONTNAME", (1, idx), (1, idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, idx), (1, idx), colors.HexColor("#1E293B")),
            ("SPAN", (1, idx), (2, idx)),
        ])

    def _add_subtotal(label, amt_val, pct_val=None, is_double_bar=False, bg_color=None):
        idx = len(rows)
        pct_text = f"{pct_val:.2f}%" if pct_val is not None else ""
        rows.append([
            "",
            label,
            Paragraph(pct_text, styles["CellAmount"]),
            Paragraph(_format_currency(amt_val), styles["CellAmount"])
        ])
        tstyles.extend([
            ("FONTNAME", (1, idx), (-1, idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, idx), (-1, idx), colors.HexColor("#0F172A")),
            ("LINEABOVE", (0, idx), (-1, idx), 1.0, colors.HexColor("#94A3B8")),
        ])
        if bg_color:
            tstyles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg_color)))
        if is_double_bar:
            tstyles.extend([
                ("LINEBELOW", (0, idx), (-1, idx), 2.0, colors.HexColor("#0F172A")),
                ("BOTTOMPADDING", (0, idx), (-1, idx), 6 * pt),
                ("TOPPADDING", (0, idx), (-1, idx), 6 * pt),
            ])

    # 1. Operating Revenue
    _add_section_header("Operating Revenue")
    for it in report_data["operating_revenue"]:
        rows.append([
            Paragraph(it["account_code"], styles["CellCode"]),
            Paragraph(it["account_name"], styles["CellName"]),
            Paragraph(f"{it['pct_of_revenue']:.2f}%", styles["CellAmount"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL OPERATING REVENUE", report_data["total_operating_revenue"], 100.0)

    # 2. Cost of Goods Sold
    if report_data["cost_of_sales"]:
        _add_section_header("Cost of Goods Sold")
        for it in report_data["cost_of_sales"]:
            rows.append([
                Paragraph(it["account_code"], styles["CellCode"]),
                Paragraph(it["account_name"], styles["CellName"]),
                Paragraph(f"{it['pct_of_revenue']:.2f}%", styles["CellAmount"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])
        _add_subtotal("TOTAL COST OF GOODS SOLD", report_data["total_cost_of_sales"])

    # 3. Gross Profit
    _add_subtotal(
        "GROSS PROFIT",
        report_data["gross_profit"],
        report_data["gross_profit_margin_pct"],
        bg_color="#F8FAFC"
    )

    # 4. Operating Expenses
    _add_section_header("Operating Expenses")
    for cat_name, items in report_data["expenses_by_category"].items():
        for it in items:
            rows.append([
                Paragraph(it["account_code"], styles["CellCode"]),
                Paragraph(f"{it['account_name']} ({cat_name})", styles["CellName"]),
                Paragraph(f"{it['pct_of_revenue']:.2f}%", styles["CellAmount"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])
    _add_subtotal("TOTAL OPERATING EXPENSES", report_data["total_operating_expenses"])

    # 5. Operating Profit
    _add_subtotal("OPERATING PROFIT (EBIT)", report_data["operating_profit"], bg_color="#F8FAFC")

    # 6. Other Income
    if report_data["other_income"]:
        _add_section_header("Other Income & Discounts Received")
        for it in report_data["other_income"]:
            rows.append([
                Paragraph(it["account_code"], styles["CellCode"]),
                Paragraph(it["account_name"], styles["CellName"]),
                Paragraph(f"{it['pct_of_revenue']:.2f}%", styles["CellAmount"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])
        _add_subtotal("TOTAL OTHER INCOME", report_data["total_other_income"])

    # 7. Net Profit / (Loss)
    net_label = "NET PROFIT FOR THE PERIOD" if report_data["is_profit"] else "NET LOSS FOR THE PERIOD"
    net_bg = "#ECFDF5" if report_data["is_profit"] else "#FEF2F2"
    _add_subtotal(
        net_label,
        report_data["net_profit"],
        report_data["net_profit_margin_pct"],
        is_double_bar=True,
        bg_color=net_bg
    )

    pl_table = Table(rows, colWidths=col_w, repeatRows=1)
    pl_table.setStyle(TableStyle(tstyles))
    elements.append(pl_table)

    elements.append(_build_signoff_block())

    # Build PDF using NumberedCanvas
    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_title = f"{report_data['company_name']} — Profit & Loss"
        c.doc_subtitle = f"{period['start_date']} to {period['end_date']}"
        c.doc_timestamp = report_data.get("generated_at", "")
        return c

    doc.build(elements, canvasmaker=_canvas_factory)
    return output_path


# =========================================================================
# 2. BALANCE SHEET PDF
# =========================================================================

def generate_balance_sheet_pdf(report_data: dict, output_path: str = None) -> str:
    """
    Generate an A4 publication-quality Balance Sheet (Financial Position) PDF.

    Args:
        report_data: Dictionary from generate_balance_sheet.
        output_path: Optional output path.

    Returns:
        str: Absolute path of generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"balance_sheet_{ts}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=36 * pt,
    )

    styles = _get_styles()
    as_of = report_data["as_of_date"]
    curr = report_data["currency"]
    title = "STATEMENT OF FINANCIAL POSITION (BALANCE SHEET)"
    subtitle = f"As of Date: {as_of}  |  All amounts in {curr}"

    elements = _build_header_elements(report_data, title, subtitle, styles)

    col_w = [60 * pt, 240 * pt, 95 * pt, 125 * pt]
    rows = []
    tstyles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * pt),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
    ]

    rows.append([
        Paragraph("Code", styles["HeaderCell"]),
        Paragraph("Account / Category Description", styles["HeaderCell"]),
        Paragraph("Subcategory", styles["HeaderCell"]),
        Paragraph(f"Amount ({curr})", styles["HeaderCellRight"]),
    ])

    def _add_section_header(name, is_major=False):
        idx = len(rows)
        rows.append(["", name.upper(), "", ""])
        bg = colors.HexColor("#E2E8F0") if is_major else colors.HexColor("#F1F5F9")
        tstyles.extend([
            ("BACKGROUND", (0, idx), (-1, idx), bg),
            ("FONTNAME", (1, idx), (1, idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, idx), (1, idx), colors.HexColor("#0F172A")),
            ("SPAN", (1, idx), (2, idx)),
        ])

    def _add_subtotal(label, amt_val, is_double_bar=False, bg_color=None):
        idx = len(rows)
        rows.append([
            "",
            label,
            "",
            Paragraph(_format_currency(amt_val), styles["CellAmount"])
        ])
        tstyles.extend([
            ("FONTNAME", (1, idx), (-1, idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, idx), (-1, idx), colors.HexColor("#0F172A")),
            ("LINEABOVE", (0, idx), (-1, idx), 1.0, colors.HexColor("#94A3B8")),
        ])
        if bg_color:
            tstyles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg_color)))
        if is_double_bar:
            tstyles.extend([
                ("LINEBELOW", (0, idx), (-1, idx), 2.0, colors.HexColor("#0F172A")),
                ("BOTTOMPADDING", (0, idx), (-1, idx), 6 * pt),
                ("TOPPADDING", (0, idx), (-1, idx), 6 * pt),
            ])

    # === ASSETS ===
    _add_section_header("1. ASSETS", is_major=True)
    _add_section_header("Current Assets")
    for it in report_data["current_assets"]:
        rows.append([
            Paragraph(it["account_code"], styles["CellCode"]),
            Paragraph(it["account_name"], styles["CellName"]),
            Paragraph(it["sub_category"], styles["CellCategory"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL CURRENT ASSETS", report_data["total_current_assets"])

    if report_data["non_current_assets"]:
        _add_section_header("Non-Current (Fixed) Assets")
        for it in report_data["non_current_assets"]:
            rows.append([
                Paragraph(it["account_code"], styles["CellCode"]),
                Paragraph(it["account_name"], styles["CellName"]),
                Paragraph(it["sub_category"], styles["CellCategory"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])
        _add_subtotal("TOTAL NON-CURRENT ASSETS", report_data["total_non_current_assets"])

    _add_subtotal("TOTAL ASSETS", report_data["total_assets"], is_double_bar=True, bg_color="#EFF6FF")

    # === LIABILITIES ===
    _add_section_header("2. LIABILITIES", is_major=True)
    _add_section_header("Current Liabilities")
    for it in report_data["current_liabilities"]:
        rows.append([
            Paragraph(it["account_code"], styles["CellCode"]),
            Paragraph(it["account_name"], styles["CellName"]),
            Paragraph(it["sub_category"], styles["CellCategory"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL CURRENT LIABILITIES", report_data["total_current_liabilities"])

    if report_data["long_term_liabilities"]:
        _add_section_header("Long-Term Liabilities")
        for it in report_data["long_term_liabilities"]:
            rows.append([
                Paragraph(it["account_code"], styles["CellCode"]),
                Paragraph(it["account_name"], styles["CellName"]),
                Paragraph(it["sub_category"], styles["CellCategory"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])
        _add_subtotal("TOTAL LONG-TERM LIABILITIES", report_data["total_long_term_liabilities"])

    _add_subtotal("TOTAL LIABILITIES", report_data["total_liabilities"])

    # === EQUITY ===
    _add_section_header("3. EQUITY", is_major=True)
    for it in report_data["equity_items"]:
        code_str = it["account_code"] or ""
        rows.append([
            Paragraph(code_str, styles["CellCode"]),
            Paragraph(it["account_name"], styles["CellName"]),
            Paragraph(it["sub_category"], styles["CellCategory"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL EQUITY", report_data["total_equity"])

    # TOTAL LIABILITIES & EQUITY
    bal_bg = "#ECFDF5" if report_data["is_balanced"] else "#FEF2F2"
    _add_subtotal("TOTAL LIABILITIES & EQUITY", report_data["total_liabilities_and_equity"], is_double_bar=True, bg_color=bal_bg)

    bs_table = Table(rows, colWidths=col_w, repeatRows=1)
    bs_table.setStyle(TableStyle(tstyles))
    elements.append(bs_table)

    elements.append(_build_signoff_block())

    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_title = f"{report_data['company_name']} — Balance Sheet"
        c.doc_subtitle = f"As of {as_of}"
        c.doc_timestamp = report_data.get("generated_at", "")
        return c

    doc.build(elements, canvasmaker=_canvas_factory)
    return output_path


# =========================================================================
# 3. TRIAL BALANCE PDF
# =========================================================================

def generate_trial_balance_pdf(report_data: dict, output_path: str = None) -> str:
    """
    Generate an A4 publication-quality Trial Balance PDF.

    Args:
        report_data: Dictionary from database.get_trial_balance.
        output_path: Optional output path.

    Returns:
        str: Absolute path of generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"trial_balance_{ts}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=36 * pt,
    )

    styles = _get_styles()
    as_of = report_data.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
    comp_name = report_data.get("company_name", "Main Enterprise")
    title = "TRIAL BALANCE"
    subtitle = f"As of: {as_of}  |  Accounting Equation: Debits = Credits"

    elements = _build_header_elements(report_data, title, subtitle, styles)

    col_w = [60 * pt, 240 * pt, 110 * pt, 110 * pt]
    rows = []
    tstyles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * pt),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
    ]

    rows.append([
        Paragraph("Code", styles["HeaderCell"]),
        Paragraph("Account Name & Type", styles["HeaderCell"]),
        Paragraph("Debit Balance", styles["HeaderCellRight"]),
        Paragraph("Credit Balance", styles["HeaderCellRight"]),
    ])

    for a in report_data.get("accounts", []):
        d_val = float(a.get("debit", 0.0))
        c_val = float(a.get("credit", 0.0))
        if d_val == 0.0 and c_val == 0.0:
            continue

        deb_str = _format_currency(d_val) if d_val > 0 else "-"
        cred_str = _format_currency(c_val) if c_val > 0 else "-"
        type_str = f" ({a.get('account_type', '')})"

        rows.append([
            Paragraph(a.get("account_code", ""), styles["CellCode"]),
            Paragraph(f"{a.get('account_name', '')}{type_str}", styles["CellName"]),
            Paragraph(deb_str, styles["CellAmount"]),
            Paragraph(cred_str, styles["CellAmount"]),
        ])

    # Totals Row
    idx = len(rows)
    tot_deb = float(report_data.get("total_debit", 0.0))
    tot_cred = float(report_data.get("total_credit", 0.0))
    is_bal = report_data.get("is_balanced", False)
    bg = "#ECFDF5" if is_bal else "#FEF2F2"

    rows.append([
        "",
        "TOTAL TRIAL BALANCE",
        Paragraph(_format_currency(tot_deb), styles["CellAmount"]),
        Paragraph(_format_currency(tot_cred), styles["CellAmount"])
    ])
    tstyles.extend([
        ("FONTNAME", (1, idx), (-1, idx), "Helvetica-Bold"),
        ("LINEABOVE", (0, idx), (-1, idx), 1.0, colors.HexColor("#0F172A")),
        ("LINEBELOW", (0, idx), (-1, idx), 2.0, colors.HexColor("#0F172A")),
        ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)),
        ("TOPPADDING", (0, idx), (-1, idx), 6 * pt),
        ("BOTTOMPADDING", (0, idx), (-1, idx), 6 * pt),
    ])

    tb_table = Table(rows, colWidths=col_w, repeatRows=1)
    tb_table.setStyle(TableStyle(tstyles))
    elements.append(tb_table)

    elements.append(_build_signoff_block())

    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_title = f"{comp_name} — Trial Balance"
        c.doc_subtitle = f"As of {as_of}"
        return c

    doc.build(elements, canvasmaker=_canvas_factory)
    return output_path


# =========================================================================
# 4. CASH FLOW STATEMENT PDF
# =========================================================================

def generate_cash_flow_pdf(report_data: dict, output_path: str = None) -> str:
    """
    Generate an A4 publication-quality Cash Flow Statement PDF.

    Args:
        report_data: Dictionary from generate_cash_flow.
        output_path: Optional output path.

    Returns:
        str: Absolute path of generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"cash_flow_{ts}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=36 * pt,
    )

    styles = _get_styles()
    period = report_data["period"]
    curr = report_data["currency"]
    title = "STATEMENT OF CASH FLOWS"
    subtitle = f"For the Period: {period['start_date']} to {period['end_date']}  |  All amounts in {curr}"

    elements = _build_header_elements(report_data, title, subtitle, styles)

    col_w = [70 * pt, 230 * pt, 100 * pt, 120 * pt]
    rows = []
    tstyles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * pt),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
    ]

    rows.append([
        Paragraph("Date / Ref", styles["HeaderCell"]),
        Paragraph("Description / Transaction Details", styles["HeaderCell"]),
        Paragraph("Cash/Bank Account", styles["HeaderCell"]),
        Paragraph(f"Amount ({curr})", styles["HeaderCellRight"]),
    ])

    # Beginning Cash Row
    rows.append([
        "",
        "BEGINNING CASH & BANK POSITION",
        "",
        Paragraph(_format_currency(report_data["beginning_cash"]), styles["CellAmount"])
    ])
    tstyles.extend([
        ("FONTNAME", (1, 1), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
    ])

    def _add_section_header(name):
        idx = len(rows)
        rows.append(["", name.upper(), "", ""])
        tstyles.extend([
            ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#F1F5F9")),
            ("FONTNAME", (1, idx), (1, idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, idx), (1, idx), colors.HexColor("#0F172A")),
            ("SPAN", (1, idx), (2, idx)),
        ])

    def _add_subtotal(label, amt_val, is_double=False, bg=None):
        idx = len(rows)
        rows.append([
            "",
            label,
            "",
            Paragraph(_format_currency(amt_val), styles["CellAmount"])
        ])
        tstyles.extend([
            ("FONTNAME", (1, idx), (-1, idx), "Helvetica-Bold"),
            ("LINEABOVE", (0, idx), (-1, idx), 1.0, colors.HexColor("#94A3B8")),
        ])
        if bg:
            tstyles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))
        if is_double:
            tstyles.extend([
                ("LINEBELOW", (0, idx), (-1, idx), 2.0, colors.HexColor("#0F172A")),
                ("TOPPADDING", (0, idx), (-1, idx), 6 * pt),
                ("BOTTOMPADDING", (0, idx), (-1, idx), 6 * pt),
            ])

    # Inflows
    _add_section_header("Cash Inflows (Receipts & Collections)")
    for it in report_data["inflows"]:
        rows.append([
            Paragraph(f"{it['date']}<br/>{it['entry_number']}", styles["CellCode"]),
            Paragraph(it["description"], styles["CellName"]),
            Paragraph(it["account"], styles["CellCategory"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL CASH INFLOWS", report_data["total_inflows"])

    # Outflows
    _add_section_header("Cash Outflows (Disbursements & Payments)")
    for it in report_data["outflows"]:
        rows.append([
            Paragraph(f"{it['date']}<br/>{it['entry_number']}", styles["CellCode"]),
            Paragraph(it["description"], styles["CellName"]),
            Paragraph(it["account"], styles["CellCategory"]),
            Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
        ])
    _add_subtotal("TOTAL CASH OUTFLOWS", report_data["total_outflows"])

    # Net Change
    _add_subtotal("NET CHANGE IN CASH & BANK", report_data["net_change"], bg="#F8FAFC")

    # Ending Cash
    _add_subtotal("ENDING CASH & BANK POSITION", report_data["ending_cash"], is_double=True, bg="#EFF6FF")

    cf_table = Table(rows, colWidths=col_w, repeatRows=1)
    cf_table.setStyle(TableStyle(tstyles))
    elements.append(cf_table)

    # Account Breakdown Sub-table
    elements.append(Spacer(1, 10 * pt))
    elements.append(Paragraph("Account Breakdown at Period End:", styles["ReportSubtitle"]))
    ab_rows = [["Account Code", "Account Name", "Ending Balance"]]
    ab_styles = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * pt),
    ]
    for ab in report_data["account_breakdown"]:
        ab_rows.append([ab["code"], ab["name"], _format_currency(ab["balance"])])

    ab_table = Table(ab_rows, colWidths=[100 * pt, 280 * pt, 140 * pt])
    ab_table.setStyle(TableStyle(ab_styles))
    elements.append(ab_table)

    elements.append(_build_signoff_block())

    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_title = f"{report_data['company_name']} — Cash Flow"
        c.doc_subtitle = f"{period['start_date']} to {period['end_date']}"
        c.doc_timestamp = report_data.get("generated_at", "")
        return c

    doc.build(elements, canvasmaker=_canvas_factory)
    return output_path
