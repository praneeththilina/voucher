"""
reports/budget_vs_actual.py
Budget vs Actual Variance Report PDF Engine (v4.0).

Generates professional publication-grade variance reports:
- Executive KPI summary cards (Total Budget, Actual Spending, Net Variance, Burn Rate)
- Line-by-line Chart of Accounts variance breakdown with utilization badges
- Color-coded status markers (Within Budget, Warning >=80%, Exceeded >100%)
- Sign-off approval blocks (Financial Controller & CFO)
- Two-pass NumberedCanvas for 'Page X of Y' headers and footers
"""

import os
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
pt = 1
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import database as db
from reports.report_printer import NumberedCanvas


def generate_budget_vs_actual_pdf(report_data_or_company_id, year: int = None, month: int = 0, company: dict = None, output_path: str = None) -> str:
    """
    Generate an official Budget vs Actual Variance Report PDF document.

    Args:
        report_data_or_company_id: Either a computed report dict or an int company_id.
        year: Budget year (required if company_id is passed).
        month: Budget month (0 for annual, 1-12 for monthly).
        company: Optional company dict override.
        output_path: Optional destination file path.

    Returns:
        str: Absolute path to the generated PDF document.
    """
    if isinstance(report_data_or_company_id, dict):
        rep = report_data_or_company_id
        company_id = rep.get("company_id") or 1
    else:
        company_id = int(report_data_or_company_id)
        if year is None:
            year = datetime.now().year
        rep = db.generate_budget_vs_actual(company_id, year, month)

    comp = company or db.get_company(company_id) or {}
    comp_name = comp.get("name") or rep.get("company_name") or "Main Enterprise"
    currency = comp.get("currency") or rep.get("currency") or "LKR"

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        period_str = f"{rep['year']}_{rep['month']}"
        output_path = os.path.join(temp_dir, f"budget_variance_{period_str}_{ts}.pdf")

    margin = 15 * mm
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin
    )
    avail_width = doc.width

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "BTitle",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0F172A")
    )
    sub_style = ParagraphStyle(
        "BSub",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569")
    )
    sec_title = ParagraphStyle(
        "BSecTitle",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1E3A8A")
    )
    tbl_hdr = ParagraphStyle(
        "BTblHdr",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.white
    )
    tbl_cell = ParagraphStyle(
        "BTblCell",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1E293B")
    )
    tbl_cell_r = ParagraphStyle(
        "BTblCellR",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1E293B")
    )
    tbl_cell_bold_r = ParagraphStyle(
        "BTblCellBoldR",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0F172A")
    )

    story = []

    # 1. Header & Letterhead
    story.append(Paragraph(comp_name, title_style))
    contact_parts = []
    if comp.get("address"):
        contact_parts.append(comp["address"])
    if comp.get("phone"):
        contact_parts.append(f"Tel: {comp['phone']}")
    story.append(Paragraph(" • ".join(contact_parts), sub_style))
    story.append(Spacer(1, 4 * mm))

    # Title Banner
    banner_data = [
        [
            Paragraph("<b>BUDGET VS ACTUAL VARIANCE STATEMENT</b>", ParagraphStyle("BannerT", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1E3A8A"))),
            Paragraph(f"<b>Period:</b> {rep.get('period_label', '')} &nbsp;|&nbsp; <b>Currency:</b> {currency}", ParagraphStyle("BannerD", fontName="Helvetica-Bold", fontSize=8.5, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor("#1E3A8A")))
        ]
    ]
    t_banner = Table(banner_data, colWidths=[avail_width * 0.6, avail_width * 0.4])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
        ('TOPPADDING', (0, 0), (-1, -1), 5 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 * pt),
        ('LEFTPADDING', (0, 0), (-1, -1), 8 * pt),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8 * pt),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 4 * mm))

    # 2. Executive KPI Cards
    tb_amt = rep.get("total_budget", 0.0)
    ta_amt = rep.get("total_actual", 0.0)
    tv_amt = rep.get("total_variance", 0.0)
    tu_pct = rep.get("total_utilization_pct", 0.0)

    card_data = [
        [
            Paragraph(f"<font size='7' color='#475569'><b>TOTAL ALLOCATED BUDGET</b></font><br/><font size='11' color='#1E3A8A'><b>{currency} {tb_amt:,.2f}</b></font>", ParagraphStyle("KC1", leading=14)),
            Paragraph(f"<font size='7' color='#475569'><b>ACTUAL EXPENDITURE</b></font><br/><font size='11' color='#0F172A'><b>{currency} {ta_amt:,.2f}</b></font>", ParagraphStyle("KC2", leading=14)),
            Paragraph(f"<font size='7' color='#475569'><b>NET VARIANCE (REMAINING)</b></font><br/><font size='11' color='{'#059669' if tv_amt >= 0 else '#DC2626'}'><b>{currency} {tv_amt:,.2f}</b></font>", ParagraphStyle("KC3", leading=14)),
            Paragraph(f"<font size='7' color='#475569'><b>OVERALL UTILIZATION</b></font><br/><font size='11' color='{'#DC2626' if tu_pct > 100 else ('#D97706' if tu_pct >= 80 else '#059669')}'><b>{tu_pct:.1f}%</b></font>", ParagraphStyle("KC4", leading=14)),
        ]
    ]
    w_card = avail_width / 4.0
    t_cards = Table(card_data, colWidths=[w_card] * 4)
    t_cards.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 5 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 * pt),
        ('LEFTPADDING', (0, 0), (-1, -1), 6 * pt),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6 * pt),
    ]))
    story.append(t_cards)
    story.append(Spacer(1, 5 * mm))

    # 3. Line Items Table
    lines = rep.get("lines", [])
    story.append(Paragraph(f"<b>ACCOUNT EXPENDITURE & VARIANCE BREAKDOWN ({len(lines)} Accounts)</b>", sec_title))
    story.append(Spacer(1, 2 * mm))

    t_rows = [
        [
            Paragraph("<b>Code</b>", tbl_hdr),
            Paragraph("<b>Account Name</b>", tbl_hdr),
            Paragraph(f"<b>Budget ({currency})</b>", ParagraphStyle("TH1", parent=tbl_hdr, alignment=TA_RIGHT)),
            Paragraph(f"<b>Actual ({currency})</b>", ParagraphStyle("TH2", parent=tbl_hdr, alignment=TA_RIGHT)),
            Paragraph(f"<b>Variance ({currency})</b>", ParagraphStyle("TH3", parent=tbl_hdr, alignment=TA_RIGHT)),
            Paragraph("<b>Burn %</b>", ParagraphStyle("TH4", parent=tbl_hdr, alignment=TA_RIGHT)),
            Paragraph("<b>Status</b>", ParagraphStyle("TH5", parent=tbl_hdr, alignment=TA_CENTER)),
        ]
    ]

    for idx, l in enumerate(lines):
        b = l["budget_amount"]
        a = l["actual_amount"]
        v = l["variance"]
        u = l["utilization_pct"]
        st = l["status"]

        if st == "Exceeded":
            st_color = "#DC2626"
            st_text = f"<font color='{st_color}'><b>OVER</b></font>"
        elif st == "Warning":
            st_color = "#D97706"
            st_text = f"<font color='{st_color}'><b>WARN</b></font>"
        else:
            st_color = "#059669"
            st_text = f"<font color='{st_color}'><b>OK</b></font>"

        t_rows.append([
            Paragraph(l.get("account_code", ""), tbl_cell),
            Paragraph(l.get("account_name", "")[:35], tbl_cell),
            Paragraph(f"{b:,.2f}", tbl_cell_r),
            Paragraph(f"{a:,.2f}", tbl_cell_r),
            Paragraph(f"<font color='{'#059669' if v >= 0 else '#DC2626'}'>{v:,.2f}</font>", tbl_cell_r),
            Paragraph(f"{u:.1f}%", tbl_cell_r),
            Paragraph(st_text, ParagraphStyle("StBadge", parent=tbl_cell, alignment=TA_CENTER)),
        ])

    # Grand Totals Row
    t_rows.append([
        Paragraph("<b>GRAND TOTAL</b>", ParagraphStyle("GTH", parent=tbl_cell, fontName="Helvetica-Bold")),
        Paragraph("", tbl_cell),
        Paragraph(f"<b>{tb_amt:,.2f}</b>", tbl_cell_bold_r),
        Paragraph(f"<b>{ta_amt:,.2f}</b>", tbl_cell_bold_r),
        Paragraph(f"<b><font color='{'#059669' if tv_amt >= 0 else '#DC2626'}'>{tv_amt:,.2f}</font></b>", tbl_cell_bold_r),
        Paragraph(f"<b>{tu_pct:.1f}%</b>", tbl_cell_bold_r),
        Paragraph(f"<b>{rep.get('overall_status', '')}</b>", ParagraphStyle("GSt", parent=tbl_cell, alignment=TA_CENTER, fontName="Helvetica-Bold")),
    ])

    col_widths = [18 * mm, avail_width - 110 * mm, 24 * mm, 24 * mm, 24 * mm, 16 * mm, 16 * mm]
    t_table = Table(t_rows, colWidths=col_widths)
    t_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5 * pt),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#1E3A8A")),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, colors.HexColor("#1E3A8A")),
    ]))
    story.append(t_table)
    story.append(Spacer(1, 8 * mm))

    # 4. Dual Sign-off Blocks
    sig_data = [
        [
            Paragraph(
                "<br/><br/>________________________________________<br/>"
                "<b>Prepared By: Financial Controller</b><br/>"
                "<font size='7' color='#64748B'>Variance analysis compiled & reviewed</font>",
                ParagraphStyle("Sig1", fontName="Helvetica", fontSize=7.5, leading=11, textColor=colors.HexColor("#334155"))
            ),
            Paragraph(
                "<br/><br/>________________________________________<br/>"
                "<b>Approved By: Chief Financial Officer (CFO)</b><br/>"
                "<font size='7' color='#64748B'>Executive expenditure sign-off</font>",
                ParagraphStyle("Sig2", fontName="Helvetica", fontSize=7.5, leading=11, alignment=TA_RIGHT, textColor=colors.HexColor("#334155"))
            )
        ]
    ]
    t_sig = Table(sig_data, colWidths=[avail_width * 0.5, avail_width * 0.5])
    t_sig.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 4 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * pt),
    ]))
    story.append(KeepTogether(t_sig))

    doc.build(story, canvasmaker=NumberedCanvas)
    return output_path


def export_budget_vs_actual_csv(report_data_or_company_id, output_path: str = None, year: int = None, month: int = 0, company: dict = None) -> str:
    """
    Export Budget vs Actual Variance Report to a CSV spreadsheet.

    Args:
        report_data_or_company_id: Either a computed report dict or an int company_id.
        output_path: Target CSV file path (optional; generates temp file if omitted).
        year: Budget year (required if company_id is passed).
        month: Budget month (0 for annual, 1-12 for monthly).
        company: Optional company dict override.

    Returns:
        str: Path to generated CSV file.
    """
    import csv

    if isinstance(report_data_or_company_id, dict):
        rep = report_data_or_company_id
        company_id = rep.get("company_id") or 1
    else:
        company_id = int(report_data_or_company_id)
        if year is None:
            year = datetime.now().year
        rep = db.generate_budget_vs_actual(company_id, year, month)

    comp = company or db.get_company(company_id) or {}
    comp_name = comp.get("name") or rep.get("company_name") or "Main Enterprise"
    currency = comp.get("currency") or rep.get("currency") or "LKR"

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        period_str = f"{rep['year']}_{rep['month']}"
        output_path = os.path.join(temp_dir, f"budget_variance_{period_str}_{ts}.csv")

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["BUDGET VS ACTUAL VARIANCE STATEMENT"])
        writer.writerow(db._sanitize_csv_row(["Company", comp_name]))
        writer.writerow(db._sanitize_csv_row(["Period", rep.get("period_label", "")]))
        writer.writerow(db._sanitize_csv_row(["Currency", currency]))
        writer.writerow([])
        writer.writerow(["SUMMARY"])
        writer.writerow(db._sanitize_csv_row(["Total Allocated Budget", f"{rep.get('total_budget', 0.0):.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Total Actual Expenditure", f"{rep.get('total_actual', 0.0):.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Net Variance (Remaining)", f"{rep.get('total_variance', 0.0):.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Overall Burn Rate", f"{rep.get('total_utilization_pct', 0.0):.1f}%"]))
        writer.writerow(db._sanitize_csv_row(["Overall Status", rep.get("overall_status", "")]))
        writer.writerow([])
        writer.writerow(["Code", "Account Name", "Type", f"Budget ({currency})", f"Actual ({currency})", f"Variance ({currency})", "Burn %", "Status"])

        for l in rep.get("lines", []):
            writer.writerow(db._sanitize_csv_row([
                l.get("account_code", ""),
                l.get("account_name", ""),
                l.get("account_type", ""),
                f"{l.get('budget_amount', 0.0):.2f}",
                f"{l.get('actual_amount', 0.0):.2f}",
                f"{l.get('variance', 0.0):.2f}",
                f"{l.get('utilization_pct', 0.0):.1f}%",
                l.get("status", "")
            ]))

    return output_path
