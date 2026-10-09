"""
reports/profit_loss.py
Profit & Loss (Income Statement) Generator for Voucher Manager SME Bookkeeping.

Calculates:
- Operating Revenue (Sales, Service Revenue)
- Cost of Goods Sold / Direct Costs
- Gross Profit & Gross Margin %
- Operating Expenses categorized by COA subcategories
- Operating Profit (EBIT)
- Other Income & Discounts Received
- Net Profit / (Loss) & Net Margin %
"""

import csv
import io
import os
from datetime import datetime
import database as db


def generate_profit_loss(
    company_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    conn=None
) -> dict:
    """
    Generate a comprehensive Profit & Loss (Income Statement) for the given date range.

    Args:
        company_id: Optional ID of the company; defaults to active company.
        start_date: Optional start date 'YYYY-MM-DD'; defaults to Jan 1 of current year.
        end_date: Optional end date 'YYYY-MM-DD'; defaults to current date.
        conn: Optional existing sqlite3 database connection.

    Returns:
        dict: Structured financial report with income, expense breakdown, and margins.
    """
    close_conn = False
    if conn is None:
        conn = db.get_connection()
        close_conn = True

    try:
        if company_id is None:
            company_id = db.get_active_company_id(conn)

        now = datetime.now()
        if not end_date:
            end_date = now.strftime("%Y-%m-%d")
        if not start_date:
            start_date = f"{now.year}-01-01"

        comp = db.get_company(company_id, conn=conn) or {}
        comp_name = comp.get("name") or "Main Enterprise"
        currency = db.get_company_base_currency(company_id, conn=conn) or "LKR"

        # Ensure historical vouchers have corresponding journal entries
        try:
            db.backfill_vouchers_to_journal(company_id, conn=conn)
        except Exception:
            pass

        # Query all posted journal lines for Income and Expense accounts
        query = """
            SELECT coa.id as account_id, coa.account_code, coa.account_name, coa.account_type,
                   coa.sub_category, coa.normal_balance,
                   COALESCE(SUM(jl.debit_amount), 0.0) as total_debit,
                   COALESCE(SUM(jl.credit_amount), 0.0) as total_credit
            FROM chart_of_accounts coa
            JOIN journal_lines jl ON coa.id = jl.account_id
            JOIN journal_entries je ON jl.entry_id = je.id
            WHERE coa.company_id = ?
              AND je.is_posted = 1
              AND je.entry_date >= ?
              AND je.entry_date <= ?
              AND coa.account_type IN ('Income', 'Expense')
            GROUP BY coa.id
            ORDER BY coa.account_code ASC
        """
        rows = conn.execute(query, (company_id, start_date, end_date)).fetchall()

        operating_revenue = []
        cost_of_sales = []
        operating_expenses = []
        other_income = []

        total_op_rev = 0.0
        total_cos = 0.0
        total_op_exp = 0.0
        total_oth_inc = 0.0

        # Categorize accounts
        for r in rows:
            d = dict(r)
            code = d["account_code"]
            name = d["account_name"]
            acct_type = d["account_type"]
            sub_cat = d.get("sub_category") or ""
            deb = float(d["total_debit"])
            cred = float(d["total_credit"])

            if acct_type == "Income":
                # Income normal balance: Credit
                net = cred - deb
                if abs(net) < 0.001:
                    continue

                item = {
                    "account_id": d["account_id"],
                    "account_code": code,
                    "account_name": name,
                    "sub_category": sub_cat or "Operating Revenue",
                    "amount": round(net, 2),
                }

                if sub_cat == "Other Income" or code.startswith("43"):
                    other_income.append(item)
                    total_oth_inc += net
                else:
                    operating_revenue.append(item)
                    total_op_rev += net

            elif acct_type == "Expense":
                # Expense normal balance: Debit
                net = deb - cred
                if abs(net) < 0.001:
                    continue

                item = {
                    "account_id": d["account_id"],
                    "account_code": code,
                    "account_name": name,
                    "sub_category": sub_cat or "General Expenses",
                    "amount": round(net, 2),
                }

                if sub_cat == "Cost of Goods Sold" or code.startswith("50") or code.startswith("510"):
                    cost_of_sales.append(item)
                    total_cos += net
                else:
                    operating_expenses.append(item)
                    total_op_exp += net

        total_op_rev = round(total_op_rev, 2)
        total_cos = round(total_cos, 2)
        gross_profit = round(total_op_rev - total_cos, 2)
        total_op_exp = round(total_op_exp, 2)
        operating_profit = round(gross_profit - total_op_exp, 2)
        total_oth_inc = round(total_oth_inc, 2)
        net_profit = round(operating_profit + total_oth_inc, 2)

        # Margins & percentages
        gp_margin = round((gross_profit / total_op_rev * 100.0), 2) if total_op_rev > 0 else 0.0
        total_all_income = total_op_rev + total_oth_inc
        np_margin = round((net_profit / total_all_income * 100.0), 2) if total_all_income > 0 else 0.0

        for it in operating_revenue:
            it["pct_of_revenue"] = round((it["amount"] / total_op_rev * 100.0), 2) if total_op_rev > 0 else 0.0

        for it in cost_of_sales:
            it["pct_of_revenue"] = round((it["amount"] / total_op_rev * 100.0), 2) if total_op_rev > 0 else 0.0

        for it in operating_expenses:
            it["pct_of_revenue"] = round((it["amount"] / total_op_rev * 100.0), 2) if total_op_rev > 0 else 0.0

        for it in other_income:
            it["pct_of_revenue"] = round((it["amount"] / total_all_income * 100.0), 2) if total_all_income > 0 else 0.0

        # Group operating expenses by subcategory for neat presentation
        expenses_by_category = {}
        for it in operating_expenses:
            sc = it["sub_category"]
            if sc not in expenses_by_category:
                expenses_by_category[sc] = []
            expenses_by_category[sc].append(it)

        return {
            "company_id": company_id,
            "company_name": comp_name,
            "company_address": comp.get("address") or "",
            "company_phone": comp.get("phone") or "",
            "company_email": comp.get("email") or "",
            "tax_number": comp.get("tax_number") or "",
            "logo_path": comp.get("logo_path") or "",
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "currency": currency,
            "operating_revenue": operating_revenue,
            "total_operating_revenue": total_op_rev,
            "cost_of_sales": cost_of_sales,
            "total_cost_of_sales": total_cos,
            "gross_profit": gross_profit,
            "gross_profit_margin_pct": gp_margin,
            "operating_expenses": operating_expenses,
            "expenses_by_category": expenses_by_category,
            "total_operating_expenses": total_op_exp,
            "operating_profit": operating_profit,
            "other_income": other_income,
            "total_other_income": total_oth_inc,
            "net_profit": net_profit,
            "net_profit_margin_pct": np_margin,
            "is_profit": net_profit >= 0.0,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    finally:
        if close_conn:
            conn.close()


def export_profit_loss_csv(report_data: dict, output_path: str) -> str:
    """
    Export the generated Profit & Loss report to a CSV file.

    Args:
        report_data: Dictionary returned by generate_profit_loss.
        output_path: File destination path.

    Returns:
        str: output_path
    """
    p = report_data["period"]
    curr = report_data["currency"]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        def write_row(row):
            writer.writerow(db._sanitize_csv_row(row))

        write_row([report_data["company_name"]])
        write_row(["PROFIT & LOSS STATEMENT"])
        write_row([f"Period: {p['start_date']} to {p['end_date']}"])
        write_row([f"Currency: {curr} | Generated: {report_data['generated_at']}"])
        write_row([])

        write_row(["Account Code", "Account Name", "Category", f"Amount ({curr})", "% of Revenue"])

        # Revenue
        write_row(["--- OPERATING REVENUE ---", "", "", "", ""])
        for it in report_data["operating_revenue"]:
            write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}", f"{it['pct_of_revenue']:.2f}%"])
        write_row(["TOTAL OPERATING REVENUE", "", "", f"{report_data['total_operating_revenue']:.2f}", "100.00%"])
        write_row([])

        # Cost of Sales
        if report_data["cost_of_sales"]:
            write_row(["--- COST OF SALES ---", "", "", "", ""])
            for it in report_data["cost_of_sales"]:
                write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}", f"{it['pct_of_revenue']:.2f}%"])
            write_row(["TOTAL COST OF SALES", "", "", f"{report_data['total_cost_of_sales']:.2f}", ""])
            write_row([])

        # Gross Profit
        write_row(["GROSS PROFIT", "", "", f"{report_data['gross_profit']:.2f}", f"{report_data['gross_profit_margin_pct']:.2f}%"])
        write_row([])

        # Operating Expenses
        write_row(["--- OPERATING EXPENSES ---", "", "", "", ""])
        for cat, items in report_data["expenses_by_category"].items():
            for it in items:
                write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}", f"{it['pct_of_revenue']:.2f}%"])
        write_row(["TOTAL OPERATING EXPENSES", "", "", f"{report_data['total_operating_expenses']:.2f}", ""])
        write_row([])

        # Operating Profit
        write_row(["OPERATING PROFIT", "", "", f"{report_data['operating_profit']:.2f}", ""])
        write_row([])

        # Other Income
        if report_data["other_income"]:
            write_row(["--- OTHER INCOME ---", "", "", "", ""])
            for it in report_data["other_income"]:
                write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}", f"{it['pct_of_revenue']:.2f}%"])
            write_row(["TOTAL OTHER INCOME", "", "", f"{report_data['total_other_income']:.2f}", ""])
            write_row([])

        # Net Profit
        status = "NET PROFIT" if report_data["is_profit"] else "NET LOSS"
        write_row([status, "", "", f"{report_data['net_profit']:.2f}", f"{report_data['net_profit_margin_pct']:.2f}%"])

    return output_path
