"""
reports/vat_return.py
VAT / GST Statutory Return Generator & Multi-Page PDF Engine (v4.0).

Generates official VAT Return reports formatted in accordance with Commonwealth / IRD standards:
- Box 1: Total Value of Taxable Sales / Supplies (excl. VAT)
- Box 2: Total Output VAT Charged on Sales
- Box 3: Total Value of Taxable Purchases / Inputs (excl. VAT)
- Box 4: Total Input VAT Paid on Purchases
- Box 5: Net VAT Payable / (Refund / Tax Credit Due) = Box 2 - Box 4

Includes:
- Official Schedule of Output Tax (Itemized customer tax invoices)
- Official Schedule of Input Tax (Itemized supplier invoices & claimable expenses)
- Statutory declaration & authorized signatory block
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


def generate_vat_return_pdf(vat_data_or_company_id, period_start: str = None, period_end: str = None, company: dict = None, output_path: str = None) -> str:
    """
    Generate an official VAT / GST Statutory Return PDF document.

    Args:
        vat_data_or_company_id: Either a computed vat_data dict or an int company_id.
        period_start: Start date string (YYYY-MM-DD), required if company_id is provided.
        period_end: End date string (YYYY-MM-DD), required if company_id is provided.
        company: Optional company dict override.
        output_path: Optional destination file path.

    Returns:
        str: Absolute path to the generated PDF document.
    """
    if isinstance(vat_data_or_company_id, dict):
        vat_data = vat_data_or_company_id
        company_id = vat_data.get("company_id") or 1
    else:
        company_id = int(vat_data_or_company_id)
        if not period_start or not period_end:
            raise ValueError("period_start and period_end must be provided when passing company_id.")
        vat_data = db.generate_vat_return(company_id, period_start, period_end)

    comp = company or db.get_company(company_id) or {}
    comp_name = comp.get("name") or vat_data.get("company_name") or "Main Enterprise"
    currency = comp.get("currency") or vat_data.get("currency") or "LKR"
    tax_no = comp.get("tax_number") or comp.get("tax_id") or "Pending Registration"

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = tempfile.gettempdir()
        output_path = os.path.join(temp_dir, f"vat_return_{company_id}_{ts}.pdf")

    # Document Setup
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
        "VatTitle",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0F172A")
    )
    sub_style = ParagraphStyle(
        "VatSub",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569")
    )
    sec_title = ParagraphStyle(
        "VatSecTitle",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1E3A8A")
    )
    tbl_hdr = ParagraphStyle(
        "VatTblHdr",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.white
    )
    tbl_cell = ParagraphStyle(
        "VatTblCell",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1E293B")
    )
    tbl_cell_r = ParagraphStyle(
        "VatTblCellR",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#1E293B")
    )
    tbl_cell_bold_r = ParagraphStyle(
        "VatTblCellBoldR",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0F172A")
    )

    story = []

    # 1. Company Letterhead & Document Header
    story.append(Paragraph(comp_name, title_style))
    contact_parts = []
    if tax_no:
        contact_parts.append(f"<b>Tax / VAT Registration:</b> {tax_no}")
    if comp.get("address"):
        contact_parts.append(comp["address"])
    if comp.get("phone"):
        contact_parts.append(f"Tel: {comp['phone']}")
    story.append(Paragraph(" • ".join(contact_parts), sub_style))
    story.append(Spacer(1, 4 * mm))

    # Title Banner
    banner_data = [
        [
            Paragraph("<b>VALUE ADDED TAX (VAT) STATUTORY RETURN</b>", ParagraphStyle("BTitle", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1E3A8A"))),
            Paragraph(f"<b>Period:</b> {vat_data['period_start']} to {vat_data['period_end']}", ParagraphStyle("BDate", fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor("#1E3A8A")))
        ]
    ]
    t_banner = Table(banner_data, colWidths=[avail_width * 0.6, avail_width * 0.4])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
        ('TOPPADDING', (0, 0), (-1, -1), 6 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6 * pt),
        ('LEFTPADDING', (0, 0), (-1, -1), 8 * pt),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8 * pt),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 5 * mm))

    # 2. STATUTORY RETURN BOX 1 - BOX 5 SCHEDULE
    story.append(Paragraph("<b>PART 1: VAT CALCULATION SCHEDULE (BOX 1 - 5)</b>", sec_title))
    story.append(Spacer(1, 2 * mm))

    box1 = vat_data["box1_sales"]
    box2 = vat_data["box2_output_vat"]
    box3 = vat_data["box3_purchases"]
    box4 = vat_data["box4_input_vat"]
    box5 = vat_data["box5_net_payable"]

    box_rows = [
        [
            Paragraph("<b>Box No.</b>", tbl_hdr),
            Paragraph("<b>Description of Supplies & Tax Computations</b>", tbl_hdr),
            Paragraph(f"<b>Taxable Value ({currency})</b>", ParagraphStyle("TH2", parent=tbl_hdr, alignment=TA_RIGHT)),
            Paragraph(f"<b>VAT Amount ({currency})</b>", ParagraphStyle("TH3", parent=tbl_hdr, alignment=TA_RIGHT)),
        ],
        [
            Paragraph("<b>BOX 1 & 2</b>", tbl_cell),
            Paragraph("<b>OUTPUT TAX (Tax on Sales & Taxable Supplies)</b><br/><font color='#64748B' size='6.5'>Total taxable invoices issued to customers during the filing period</font>", tbl_cell),
            Paragraph(f"{box1:,.2f}", tbl_cell_bold_r),
            Paragraph(f"{box2:,.2f}", tbl_cell_bold_r),
        ],
        [
            Paragraph("<b>BOX 3 & 4</b>", tbl_cell),
            Paragraph("<b>INPUT TAX (Tax on Purchases & Allowable Expenses)</b><br/><font color='#64748B' size='6.5'>Total taxable bills & procurement invoices received from registered suppliers</font>", tbl_cell),
            Paragraph(f"{box3:,.2f}", tbl_cell_bold_r),
            Paragraph(f"{box4:,.2f}", tbl_cell_bold_r),
        ],
        [
            Paragraph("<b>BOX 5</b>", ParagraphStyle("Box5H", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#065F46") if box5 < 0 else colors.HexColor("#991B1B"))),
            Paragraph(
                f"<b>{'NET TAX CREDIT / REFUND DUE' if box5 < 0 else 'NET VAT PAYABLE TO TAX AUTHORITY'}</b><br/>"
                f"<font color='#475569' size='7'>Computed as Box 2 (Output VAT) minus Box 4 (Input VAT)</font>",
                tbl_cell
            ),
            Paragraph("-", ParagraphStyle("Dash", parent=tbl_cell, alignment=TA_CENTER)),
            Paragraph(
                f"<b>{currency} {abs(box5):,.2f}</b><br/>"
                f"<font size='6.5'>{'[CREDIT / REFUND]' if box5 < 0 else '[PAYABLE]'}</font>",
                ParagraphStyle("B5Amt", fontName="Helvetica-Bold", fontSize=10, leading=12, alignment=TA_RIGHT, textColor=colors.HexColor("#059669") if box5 < 0 else colors.HexColor("#DC2626"))
            ),
        ]
    ]

    t_box = Table(box_rows, colWidths=[20 * mm, avail_width - 80 * mm, 30 * mm, 30 * mm])
    t_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ('TOPPADDING', (0, 0), (-1, -1), 5 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5 * pt),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ('BACKGROUND', (0, 2), (-1, 2), colors.white),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor("#ECFDF5") if box5 < 0 else colors.HexColor("#FEF2F2")),
        ('BOX', (0, 3), (-1, 3), 1.5, colors.HexColor("#10B981") if box5 < 0 else colors.HexColor("#EF4444")),
    ]))
    story.append(t_box)
    story.append(Spacer(1, 6 * mm))

    # 3. SCHEDULE A: OUTPUT TAX BREAKDOWN (CUSTOMER SALES)
    sales_txns = vat_data.get("sales_transactions", [])
    story.append(Paragraph(f"<b>SCHEDULE A: OUTPUT TAX — SALES INVOICES ({len(sales_txns)} records)</b>", sec_title))
    story.append(Spacer(1, 1.5 * mm))

    if sales_txns:
        s_rows = [
            [
                Paragraph("<b>Date</b>", tbl_hdr),
                Paragraph("<b>Invoice #</b>", tbl_hdr),
                Paragraph("<b>Customer Name</b>", tbl_hdr),
                Paragraph("<b>Taxable Value</b>", ParagraphStyle("THS1", parent=tbl_hdr, alignment=TA_RIGHT)),
                Paragraph("<b>Output VAT</b>", ParagraphStyle("THS2", parent=tbl_hdr, alignment=TA_RIGHT)),
                Paragraph("<b>Total Invoice</b>", ParagraphStyle("THS3", parent=tbl_hdr, alignment=TA_RIGHT)),
            ]
        ]
        for idx, s in enumerate(sales_txns):
            bg = colors.HexColor("#F8FAFC") if idx % 2 == 1 else colors.white
            s_rows.append([
                Paragraph(s.get("invoice_date", ""), tbl_cell),
                Paragraph(s.get("invoice_number", ""), tbl_cell),
                Paragraph((s.get("customer_name") or "")[:30], tbl_cell),
                Paragraph(f"{float(s.get('taxable_amount') or 0.0):,.2f}", tbl_cell_r),
                Paragraph(f"{float(s.get('tax_amount') or 0.0):,.2f}", tbl_cell_r),
                Paragraph(f"{float(s.get('total_amount') or 0.0):,.2f}", tbl_cell_r),
            ])
        # Summary row
        s_rows.append([
            Paragraph("<b>Total Output Tax</b>", ParagraphStyle("STot", parent=tbl_cell, fontName="Helvetica-Bold")),
            Paragraph("", tbl_cell),
            Paragraph(f"<b>{len(sales_txns)} Invoices</b>", ParagraphStyle("SCount", parent=tbl_cell, fontName="Helvetica-Bold")),
            Paragraph(f"<b>{box1:,.2f}</b>", tbl_cell_bold_r),
            Paragraph(f"<b>{box2:,.2f}</b>", tbl_cell_bold_r),
            Paragraph(f"<b>{box1 + box2:,.2f}</b>", tbl_cell_bold_r),
        ])

        t_sales = Table(s_rows, colWidths=[20 * mm, 25 * mm, avail_width - 105 * mm, 20 * mm, 20 * mm, 20 * mm])
        t_sales.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5 * pt),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5 * pt),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#475569")),
        ]))
        story.append(t_sales)
    else:
        story.append(Paragraph("<i>No sales invoices recorded within this filing period.</i>", sub_style))

    story.append(Spacer(1, 6 * mm))

    # 4. SCHEDULE B: INPUT TAX BREAKDOWN (PURCHASES & SUPPLIER BILLS)
    purch_txns = vat_data.get("purchase_transactions", [])
    story.append(Paragraph(f"<b>SCHEDULE B: INPUT TAX — PURCHASES & BILLS ({len(purch_txns)} records)</b>", sec_title))
    story.append(Spacer(1, 1.5 * mm))

    if purch_txns:
        p_rows = [
            [
                Paragraph("<b>Date</b>", tbl_hdr),
                Paragraph("<b>Bill / Ref #</b>", tbl_hdr),
                Paragraph("<b>Supplier / Vendor</b>", tbl_hdr),
                Paragraph("<b>Taxable Value</b>", ParagraphStyle("THP1", parent=tbl_hdr, alignment=TA_RIGHT)),
                Paragraph("<b>Input VAT</b>", ParagraphStyle("THP2", parent=tbl_hdr, alignment=TA_RIGHT)),
                Paragraph("<b>Total Bill</b>", ParagraphStyle("THP3", parent=tbl_hdr, alignment=TA_RIGHT)),
            ]
        ]
        for idx, p in enumerate(purch_txns):
            p_rows.append([
                Paragraph(p.get("invoice_date", ""), tbl_cell),
                Paragraph(p.get("invoice_number", ""), tbl_cell),
                Paragraph((p.get("supplier_name") or "")[:30], tbl_cell),
                Paragraph(f"{float(p.get('taxable_amount') or 0.0):,.2f}", tbl_cell_r),
                Paragraph(f"{float(p.get('tax_amount') or 0.0):,.2f}", tbl_cell_r),
                Paragraph(f"{float(p.get('total_amount') or 0.0):,.2f}", tbl_cell_r),
            ])
        p_rows.append([
            Paragraph("<b>Total Input Tax</b>", ParagraphStyle("PTot", parent=tbl_cell, fontName="Helvetica-Bold")),
            Paragraph("", tbl_cell),
            Paragraph(f"<b>{len(purch_txns)} Bills</b>", ParagraphStyle("PCount", parent=tbl_cell, fontName="Helvetica-Bold")),
            Paragraph(f"<b>{box3:,.2f}</b>", tbl_cell_bold_r),
            Paragraph(f"<b>{box4:,.2f}</b>", tbl_cell_bold_r),
            Paragraph(f"<b>{box3 + box4:,.2f}</b>", tbl_cell_bold_r),
        ])

        t_purch = Table(p_rows, colWidths=[20 * mm, 25 * mm, avail_width - 105 * mm, 20 * mm, 20 * mm, 20 * mm])
        t_purch.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#334155")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5 * pt),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5 * pt),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor("#475569")),
        ]))
        story.append(t_purch)
    else:
        story.append(Paragraph("<i>No purchase invoices recorded within this filing period.</i>", sub_style))

    story.append(Spacer(1, 8 * mm))

    # 5. TAXPAYER STATUTORY DECLARATION & SIGN-OFF BLOCK
    decl_data = [
        [
            Paragraph("<b>TAXPAYER STATUTORY DECLARATION:</b><br/>"
                      "I hereby declare that the information given in this return and the accompanying schedules "
                      "is true, correct, and complete in accordance with the Value Added Tax legislation.", sub_style)
        ],
        [
            Paragraph(
                "<br/><br/>"
                "___________________________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; ______________________<br/>"
                "<b>Authorized Declarant Signature & Official Seal</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Date (DD/MM/YYYY)</b>",
                ParagraphStyle("Sig", fontName="Helvetica", fontSize=7.5, leading=11, textColor=colors.HexColor("#334155"))
            )
        ]
    ]
    t_decl = Table(decl_data, colWidths=[avail_width])
    t_decl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('TOPPADDING', (0, 0), (-1, -1), 6 * pt),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8 * pt),
        ('LEFTPADDING', (0, 0), (-1, -1), 8 * pt),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8 * pt),
    ]))
    story.append(KeepTogether(t_decl))

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    return output_path
