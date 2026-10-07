"""
reports/cash_flow_forecast.py
Cash Flow Forecast & Payment Obligations Engine for Voucher Manager SME Bookkeeping.

Projects liquid cash position and upcoming obligations over 30, 60, or 90 days based on:
- Current Liquid Cash & Bank Position (GL Cash/Bank accounts)
- Expected Accounts Receivable Collections (Outstanding AR Invoices)
- Expected Accounts Payable Obligations (Outstanding AP Invoices)
- Expected Recurring Expenses (Active Recurring Schedules)

Provides:
- `generate_cash_flow_forecast`: Core calculation logic
- `export_cash_flow_forecast_csv`: CSV export with formula injection sanitization
- `generate_cash_flow_forecast_pdf`: Publication-quality ReportLab PDF report
"""

import csv
import os
import tempfile
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4
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
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

import database as db
from reports.report_printer import NumberedCanvas, _build_header_elements, _build_signoff_block, _format_currency, pt


def generate_cash_flow_forecast(
    company_id: int | None = None,
    horizon_days: int = 30,
    min_reserve: float = 0.0,
    start_date: str | None = None,
    conn=None
) -> dict:
    """
    Generate a Cash Flow Forecast and Payment Obligations report.

    Args:
        company_id: Optional ID of the company; defaults to active company.
        horizon_days: Projection window in days (e.g. 30, 60, 90).
        min_reserve: Minimum safety reserve threshold.
        start_date: Optional forecast start date 'YYYY-MM-DD'; defaults to today.
        conn: Optional existing sqlite3 database connection.

    Returns:
        dict: Projected cash movements, timeline, deficit alerts, and summary metrics.
    """
    close_conn = False
    if conn is None:
        conn = db.get_connection()
        close_conn = True

    try:
        if company_id is None:
            company_id = db.get_active_company_id(conn)

        now = datetime.now()
        if not start_date:
            start_date_dt = now
        else:
            try:
                start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                start_date_dt = now

        start_date_str = start_date_dt.strftime("%Y-%m-%d")
        end_date_dt = start_date_dt + timedelta(days=horizon_days)
        end_date_str = end_date_dt.strftime("%Y-%m-%d")

        comp = db.get_company(company_id, conn=conn) or {}
        comp_name = comp.get("name") or "Main Enterprise"
        currency = db.get_company_base_currency(company_id, conn=conn) or "LKR"

        # Backfill unjournaled vouchers to ensure GL up-to-date
        try:
            db.backfill_vouchers_to_journal(company_id, conn=conn)
        except Exception:
            pass

        # 1. Starting Liquid Cash Position (GL Cash & Bank accounts as of start_date)
        cash_accts = conn.execute("""
            SELECT id, account_code, account_name, sub_category
            FROM chart_of_accounts
            WHERE company_id = ?
              AND is_active = 1
              AND (sub_category = 'Cash & Bank' OR account_code IN ('1110', '1120', '1130', '1140'))
            ORDER BY account_code ASC
        """, (company_id,)).fetchall()

        cash_acct_ids = [r["id"] for r in cash_accts]
        if not cash_acct_ids:
            cash_accts = conn.execute("""
                SELECT id, account_code, account_name, sub_category
                FROM chart_of_accounts
                WHERE company_id = ? AND is_active = 1 AND account_code LIKE '11%'
            """, (company_id,)).fetchall()
            cash_acct_ids = [r["id"] for r in cash_accts]

        placeholders = ",".join("?" for _ in cash_acct_ids) if cash_acct_ids else "0"
        beg_query = f"""
            SELECT COALESCE(SUM(jl.debit_amount - jl.credit_amount), 0.0) as beg_bal
            FROM journal_lines jl
            JOIN journal_entries je ON jl.entry_id = je.id
            WHERE je.company_id = ?
              AND je.is_posted = 1
              AND je.entry_date <= ?
              AND jl.account_id IN ({placeholders})
        """
        beg_params = [company_id, start_date_str] + cash_acct_ids
        beg_row = conn.execute(beg_query, beg_params).fetchone()
        starting_cash = round(float(beg_row["beg_bal"]) if beg_row and beg_row["beg_bal"] else 0.0, 2)

        # 2. Expected Inflows: Outstanding AR Customer Invoices
        ar_invoices_raw = db.get_ar_invoices(company_id=company_id, conn=conn)
        inflow_items = []
        tot_projected_inflows = 0.0

        for inv in ar_invoices_raw:
            st = (inv.get("status") or "").lower()
            if st in ("cancelled", "paid"):
                continue

            tot_amt = float(inv.get("total_amount") or 0.0)
            paid_amt = float(inv.get("paid_amount") or 0.0)
            bal_due = round(tot_amt - paid_amt, 2)

            if bal_due <= 0.001:
                continue

            due_d = inv.get("due_date") or inv.get("invoice_date") or start_date_str
            # If overdue, schedule for start_date_str for realistic projection
            effective_due = due_d if due_d >= start_date_str else start_date_str

            if effective_due <= end_date_str:
                inflow_items.append({
                    "type": "AR Invoice",
                    "ref": inv.get("invoice_number", ""),
                    "party": inv.get("customer_name", "Customer"),
                    "due_date": due_d,
                    "effective_date": effective_due,
                    "amount": bal_due,
                    "is_overdue": due_d < start_date_str
                })
                tot_projected_inflows += bal_due

        tot_projected_inflows = round(tot_projected_inflows, 2)

        # 3. Expected Outflows: AP Vendor Bills & Recurring Schedules
        outflow_items = []
        tot_projected_outflows = 0.0

        # a) AP Vendor Bills
        ap_invoices_raw = db.get_ap_invoices(company_id=company_id, conn=conn)
        for inv in ap_invoices_raw:
            st = (inv.get("status") or "").lower()
            if st in ("cancelled", "paid"):
                continue

            tot_amt = float(inv.get("total_amount") or 0.0)
            paid_amt = float(inv.get("paid_amount") or 0.0)
            bal_due = round(tot_amt - paid_amt, 2)

            if bal_due <= 0.001:
                continue

            due_d = inv.get("due_date") or inv.get("invoice_date") or start_date_str
            effective_due = due_d if due_d >= start_date_str else start_date_str

            if effective_due <= end_date_str:
                outflow_items.append({
                    "type": "AP Bill",
                    "ref": inv.get("invoice_number", ""),
                    "party": inv.get("supplier_name", "Supplier"),
                    "due_date": due_d,
                    "effective_date": effective_due,
                    "amount": bal_due,
                    "is_overdue": due_d < start_date_str
                })
                tot_projected_outflows += bal_due

        # b) Active Recurring Payment Schedules
        recurring_schedules_raw = db.get_recurring_schedules(company_id=company_id, active_only=True, conn=conn)
        for sched in recurring_schedules_raw:
            next_run_str = sched.get("next_run") or start_date_str
            sched_amt = float(sched.get("amount") or 0.0)
            freq = (sched.get("frequency") or "Monthly").capitalize()

            if sched_amt <= 0.001:
                continue

            try:
                curr_run_dt = datetime.strptime(next_run_str, "%Y-%m-%d")
            except ValueError:
                curr_run_dt = start_date_dt

            # Advance if prior to start date
            while curr_run_dt < start_date_dt:
                curr_run_dt = _advance_recurring_date(curr_run_dt, freq)

            # Project recurrences up to end_date_dt
            while curr_run_dt <= end_date_dt:
                run_str = curr_run_dt.strftime("%Y-%m-%d")
                outflow_items.append({
                    "type": "Recurring Schedule",
                    "ref": f"REC-{sched.get('id', '')}",
                    "party": sched.get("payee_name") or sched.get("schedule_name") or "Recurring Payment",
                    "due_date": run_str,
                    "effective_date": run_str,
                    "amount": sched_amt,
                    "is_overdue": False
                })
                tot_projected_outflows += sched_amt
                curr_run_dt = _advance_recurring_date(curr_run_dt, freq)

        tot_projected_outflows = round(tot_projected_outflows, 2)
        net_projected_flow = round(tot_projected_inflows - tot_projected_outflows, 2)
        projected_ending_cash = round(starting_cash + net_projected_flow, 2)

        # 4. Construct Day-by-Day Timeline
        # Index inflows & outflows by effective_date
        daily_inflows_map = {}
        for it in inflow_items:
            ed = it["effective_date"]
            daily_inflows_map[ed] = round(daily_inflows_map.get(ed, 0.0) + it["amount"], 2)

        daily_outflows_map = {}
        for it in outflow_items:
            ed = it["effective_date"]
            daily_outflows_map[ed] = round(daily_outflows_map.get(ed, 0.0) + it["amount"], 2)

        timeline = []
        running_bal = starting_cash
        lowest_bal = starting_cash
        lowest_bal_date = start_date_str
        deficit_dates = []

        curr_dt = start_date_dt
        while curr_dt <= end_date_dt:
            d_str = curr_dt.strftime("%Y-%m-%d")
            day_in = daily_inflows_map.get(d_str, 0.0)
            day_out = daily_outflows_map.get(d_str, 0.0)
            day_net = round(day_in - day_out, 2)
            running_bal = round(running_bal + day_net, 2)

            is_def = running_bal < min_reserve or running_bal < 0.0
            if is_def:
                deficit_dates.append({
                    "date": d_str,
                    "projected_balance": running_bal,
                    "shortfall": round(min_reserve - running_bal if min_reserve > running_bal else abs(running_bal), 2)
                })

            if running_bal < lowest_bal:
                lowest_bal = running_bal
                lowest_bal_date = d_str

            timeline.append({
                "date": d_str,
                "inflow": day_in,
                "outflow": day_out,
                "net_flow": day_net,
                "projected_balance": running_bal,
                "is_deficit": is_def
            })

            curr_dt += timedelta(days=1)

        # Sort items by effective date
        inflow_items.sort(key=lambda x: x["effective_date"])
        outflow_items.sort(key=lambda x: x["effective_date"])

        return {
            "company_id": company_id,
            "company_name": comp_name,
            "currency": currency,
            "period": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "horizon_days": horizon_days,
            },
            "min_reserve": min_reserve,
            "starting_cash": starting_cash,
            "total_projected_inflows": tot_projected_inflows,
            "total_projected_outflows": tot_projected_outflows,
            "net_projected_flow": net_projected_flow,
            "projected_ending_cash": projected_ending_cash,
            "lowest_projected_balance": lowest_bal,
            "lowest_projected_balance_date": lowest_bal_date,
            "has_deficit_alert": len(deficit_dates) > 0 or lowest_bal < min_reserve or lowest_bal < 0.0,
            "deficit_dates": deficit_dates,
            "timeline": timeline,
            "inflows": inflow_items,
            "outflows": outflow_items,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    finally:
        if close_conn:
            conn.close()


def _advance_recurring_date(dt: datetime, freq: str) -> datetime:
    """Advance datetime object according to recurrence frequency."""
    f = freq.lower()
    if f in ("daily", "day"):
        return dt + timedelta(days=1)
    elif f in ("weekly", "week"):
        return dt + timedelta(days=7)
    elif f in ("bi-weekly", "biweekly", "fortnightly"):
        return dt + timedelta(days=14)
    elif f in ("monthly", "month"):
        # Advance 1 month
        m = dt.month % 12 + 1
        y = dt.year + (dt.month // 12)
        d = min(dt.day, 28)
        return datetime(y, m, d)
    elif f in ("quarterly", "quarter"):
        m = (dt.month + 2) % 12 + 1
        y = dt.year + ((dt.month + 2) // 12)
        d = min(dt.day, 28)
        return datetime(y, m, d)
    elif f in ("annually", "annual", "yearly"):
        return datetime(dt.year + 1, dt.month, min(dt.day, 28))
    else:
        return dt + timedelta(days=30)


def export_cash_flow_forecast_csv(report_data: dict, output_path: str) -> str:
    """
    Export the generated Cash Flow Forecast report to CSV with formula injection protection.

    Args:
        report_data: Dictionary returned by generate_cash_flow_forecast.
        output_path: File destination path.

    Returns:
        str: output_path
    """
    p = report_data["period"]
    curr = report_data["currency"]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        writer.writerow(db._sanitize_csv_row([report_data["company_name"]]))
        writer.writerow(db._sanitize_csv_row(["CASH FLOW FORECAST & PAYMENT OBLIGATIONS"]))
        writer.writerow(db._sanitize_csv_row([f"Forecast Horizon: {p['horizon_days']} Days ({p['start_date']} to {p['end_date']})"]))
        writer.writerow(db._sanitize_csv_row([f"Currency: {curr} | Minimum Reserve Ceiling: {report_data['min_reserve']:.2f}"]))
        writer.writerow(db._sanitize_csv_row([f"Generated: {report_data['generated_at']}"]))
        writer.writerow([])

        # KPI Summary
        writer.writerow(db._sanitize_csv_row(["--- SUMMARY METRICS ---", "", "", ""]))
        writer.writerow(db._sanitize_csv_row(["Starting Liquid Cash", f"{report_data['starting_cash']:.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Projected AR Collections (+)", f"{report_data['total_projected_inflows']:.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Projected AP/Recurring Obligations (-)", f"{report_data['total_projected_outflows']:.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Net Projected Change", f"{report_data['net_projected_flow']:.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Projected Ending Cash Balance", f"{report_data['projected_ending_cash']:.2f}"]))
        writer.writerow(db._sanitize_csv_row(["Lowest Projected Balance", f"{report_data['lowest_projected_balance']:.2f} (on {report_data['lowest_projected_balance_date']})"]))
        writer.writerow(db._sanitize_csv_row(["Deficit Alert Status", "DEFICIT WARNING ALERT" if report_data['has_deficit_alert'] else "SAFE CASH POSITION"]))
        writer.writerow([])

        # Daily Timeline
        writer.writerow(db._sanitize_csv_row(["--- DAY-BY-DAY CASH PROJECTION TIMELINE ---", "", "", "", ""]))
        writer.writerow(db._sanitize_csv_row(["Date", "Expected Inflow", "Expected Outflow", "Net Daily Flow", "Projected Cash Balance", "Deficit Status"]))
        for row in report_data["timeline"]:
            st = "DEFICIT WARNING" if row["is_deficit"] else "OK"
            writer.writerow(db._sanitize_csv_row([
                row["date"],
                f"{row['inflow']:.2f}",
                f"{row['outflow']:.2f}",
                f"{row['net_flow']:.2f}",
                f"{row['projected_balance']:.2f}",
                st
            ]))
        writer.writerow([])

        # Inflows Detail
        writer.writerow(db._sanitize_csv_row(["--- EXPECTED INFLOWS (AR COLLECTIONS) ---", "", "", "", ""]))
        writer.writerow(db._sanitize_csv_row(["Type", "Ref #", "Customer Name", "Due Date", "Effective Date", f"Amount ({curr})"]))
        for it in report_data["inflows"]:
            writer.writerow(db._sanitize_csv_row([
                it["type"],
                it["ref"],
                it["party"],
                it["due_date"],
                it["effective_date"],
                f"{it['amount']:.2f}"
            ]))
        writer.writerow([])

        # Outflows Detail
        writer.writerow(db._sanitize_csv_row(["--- EXPECTED OUTFLOWS (AP BILLS & RECURRING) ---", "", "", "", ""]))
        writer.writerow(db._sanitize_csv_row(["Type", "Ref #", "Supplier / Payee Name", "Due Date", "Effective Date", f"Amount ({curr})"]))
        for it in report_data["outflows"]:
            writer.writerow(db._sanitize_csv_row([
                it["type"],
                it["ref"],
                it["party"],
                it["due_date"],
                it["effective_date"],
                f"{it['amount']:.2f}"
            ]))

    return output_path


def generate_cash_flow_forecast_pdf(report_data: dict, output_path: str = None) -> str:
    """
    Generate an A4 publication-quality Cash Flow Forecast PDF using ReportLab Platypus.

    Args:
        report_data: Dictionary from generate_cash_flow_forecast.
        output_path: Optional output path.

    Returns:
        str: Absolute path of generated PDF file.
    """
    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(tempfile.gettempdir(), f"cash_flow_forecast_{ts}.pdf")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36 * pt,
        rightMargin=36 * pt,
        topMargin=36 * pt,
        bottomMargin=36 * pt,
    )

    base_styles = getSampleStyleSheet()
    styles = {
        "CompTitle": ParagraphStyle("FC1", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor("#0F172A")),
        "CompSub": ParagraphStyle("FC2", parent=base_styles["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#475569")),
        "ReportTitle": ParagraphStyle("FC3", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=colors.HexColor("#1E3A8A"), alignment=TA_LEFT),
        "ReportSubtitle": ParagraphStyle("FC4", parent=base_styles["Normal"], fontName="Helvetica", fontSize=9, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_LEFT),
        "CellCode": ParagraphStyle("FC5", parent=base_styles["Normal"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#64748B")),
        "CellName": ParagraphStyle("FC6", parent=base_styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#1E293B")),
        "CellAmount": ParagraphStyle("FC7", parent=base_styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, alignment=TA_RIGHT, textColor=colors.HexColor("#0F172A")),
        "HeaderCell": ParagraphStyle("FC8", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.white),
        "HeaderCellRight": ParagraphStyle("FC9", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=10, alignment=TA_RIGHT, textColor=colors.white),
        "AlertText": ParagraphStyle("FC10", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#991B1B")),
        "SafeText": ParagraphStyle("FC11", parent=base_styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.HexColor("#065F46")),
    }

    p = report_data["period"]
    curr = report_data["currency"]
    title = "CASH FLOW FORECAST & PAYMENT OBLIGATIONS"
    subtitle = f"Forecast Window: {p['horizon_days']} Days ({p['start_date']} to {p['end_date']})  |  Amounts in {curr}"

    elements = _build_header_elements(report_data, title, subtitle, styles)

    # 1. Deficit Alert Banner if applicable
    if report_data["has_deficit_alert"]:
        alert_msg = f"⚠️ CASH DEFICIT WARNING: Projected cash drops to a minimum of {_format_currency(report_data['lowest_projected_balance'])} on {report_data['lowest_projected_balance_date']} (Reserve Ceiling: {_format_currency(report_data['min_reserve'])})."
        alert_tbl = Table([[Paragraph(alert_msg, styles["AlertText"])]], colWidths=[520 * pt])
        alert_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEE2E2")),
            ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#FCA5A5")),
            ("TOPPADDING", (0, 0), (-1, -1), 6 * pt),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6 * pt),
            ("LEFTPADDING", (0, 0), (-1, -1), 8 * pt),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8 * pt),
        ]))
        elements.append(alert_tbl)
        elements.append(Spacer(1, 8 * pt))
    else:
        safe_msg = f"✅ SAFE CASH POSITION: Projected cash remains above reserve ceiling of {_format_currency(report_data['min_reserve'])} throughout the forecast window."
        safe_tbl = Table([[Paragraph(safe_msg, styles["SafeText"])]], colWidths=[520 * pt])
        safe_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#D1FAE5")),
            ("BORDER", (0, 0), (-1, -1), 1, colors.HexColor("#6EE7B7")),
            ("TOPPADDING", (0, 0), (-1, -1), 6 * pt),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6 * pt),
            ("LEFTPADDING", (0, 0), (-1, -1), 8 * pt),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8 * pt),
        ]))
        elements.append(safe_tbl)
        elements.append(Spacer(1, 8 * pt))

    # 2. KPI Summary Grid
    kpi_data = [
        [
            Paragraph("Starting Liquid Cash", styles["CompSub"]),
            Paragraph("Projected AR Collections", styles["CompSub"]),
            Paragraph("Projected AP/Recurring Obligations", styles["CompSub"]),
            Paragraph("Projected Ending Cash", styles["CompSub"]),
        ],
        [
            Paragraph(_format_currency(report_data["starting_cash"]), styles["CellName"]),
            Paragraph(_format_currency(report_data["total_projected_inflows"]), styles["CellName"]),
            Paragraph(_format_currency(report_data["total_projected_outflows"]), styles["CellName"]),
            Paragraph(_format_currency(report_data["projected_ending_cash"]), styles["CellName"]),
        ]
    ]
    kpi_tbl = Table(kpi_data, colWidths=[130 * pt, 130 * pt, 130 * pt, 130 * pt])
    kpi_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * pt),
        ("LEFTPADDING", (0, 0), (-1, -1), 6 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6 * pt),
    ]))
    elements.append(kpi_tbl)
    elements.append(Spacer(1, 10 * pt))

    # 3. Daily Projection Timeline
    elements.append(Paragraph("Day-by-Day Cash Projection Timeline:", styles["ReportSubtitle"]))
    elements.append(Spacer(1, 4 * pt))

    t_rows = [[
        Paragraph("Date", styles["HeaderCell"]),
        Paragraph("Inflow (+)", styles["HeaderCellRight"]),
        Paragraph("Outflow (-)", styles["HeaderCellRight"]),
        Paragraph("Net Daily Flow", styles["HeaderCellRight"]),
        Paragraph("Projected Cash Balance", styles["HeaderCellRight"]),
    ]]

    t_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * pt),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5 * pt),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * pt),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * pt),
    ]

    for idx, row in enumerate(report_data["timeline"], start=1):
        bg = "#FEE2E2" if row["is_deficit"] else ("#F8FAFC" if idx % 2 == 0 else "#FFFFFF")
        if row["is_deficit"]:
            t_styles.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))

        t_rows.append([
            Paragraph(row["date"], styles["CellCode"]),
            Paragraph(_format_currency(row["inflow"]), styles["CellAmount"]),
            Paragraph(_format_currency(row["outflow"]), styles["CellAmount"]),
            Paragraph(_format_currency(row["net_flow"]), styles["CellAmount"]),
            Paragraph(_format_currency(row["projected_balance"]), styles["CellAmount"]),
        ])

    timeline_tbl = Table(t_rows, colWidths=[90 * pt, 105 * pt, 105 * pt, 105 * pt, 115 * pt], repeatRows=1)
    timeline_tbl.setStyle(TableStyle(t_styles))
    elements.append(timeline_tbl)
    elements.append(Spacer(1, 10 * pt))

    # 4. Outflows Detail Table if any
    if report_data["outflows"]:
        elements.append(Paragraph("Upcoming Payment Obligations (AP Bills & Recurring Schedules):", styles["ReportSubtitle"]))
        elements.append(Spacer(1, 4 * pt))

        o_rows = [[
            Paragraph("Type / Ref", styles["HeaderCell"]),
            Paragraph("Supplier / Payee Name", styles["HeaderCell"]),
            Paragraph("Due Date", styles["HeaderCell"]),
            Paragraph(f"Amount ({curr})", styles["HeaderCellRight"]),
        ]]
        o_styles = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 5 * pt),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5 * pt),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * pt),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * pt),
        ]

        for it in report_data["outflows"]:
            ref_str = f"{it['type']}<br/>{it['ref']}"
            o_rows.append([
                Paragraph(ref_str, styles["CellCode"]),
                Paragraph(it["party"], styles["CellName"]),
                Paragraph(it["effective_date"], styles["CellCode"]),
                Paragraph(_format_currency(it["amount"]), styles["CellAmount"]),
            ])

        outflow_tbl = Table(o_rows, colWidths=[110 * pt, 220 * pt, 80 * pt, 110 * pt], repeatRows=1)
        outflow_tbl.setStyle(TableStyle(o_styles))
        elements.append(outflow_tbl)

    elements.append(_build_signoff_block())

    def _canvas_factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c.doc_title = f"{report_data['company_name']} — Cash Flow Forecast"
        c.doc_subtitle = f"Window: {p['horizon_days']} Days ({p['start_date']} to {p['end_date']})"
        c.doc_timestamp = report_data.get("generated_at", "")
        return c

    doc.build(elements, canvasmaker=_canvas_factory)
    return output_path
