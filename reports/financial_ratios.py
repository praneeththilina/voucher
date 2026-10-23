"""
reports/financial_ratios.py
Financial Ratios & Business Health Analytics Engine for Voucher Manager SME Bookkeeping.

Calculates key SME financial metrics across liquidity, profitability, and leverage:
- Liquidity: Current Ratio, Quick Ratio, Cash Ratio, Working Capital
- Profitability: Gross Profit Margin %, Net Profit Margin %, Operating Expense Ratio %
- Leverage & Capital Structure: Debt-to-Equity Ratio, Equity Ratio %

Evaluates each ratio against standard SME benchmarks, assigns health indicators
("Optimal", "Adequate", "Moderate", "Warning", "N/A"), and provides an overall
Business Health Rating.
"""

import csv
from datetime import datetime
import database as db
from reports.profit_loss import generate_profit_loss
from reports.balance_sheet import generate_balance_sheet


def generate_financial_ratios(
    company_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    conn=None
) -> dict:
    """
    Generate financial ratio analytics and business health metrics for a given period.

    Args:
        company_id: Optional ID of company; defaults to active company.
        start_date: Optional start date 'YYYY-MM-DD'; defaults to Jan 1 of current year.
        end_date: Optional end date 'YYYY-MM-DD'; defaults to current date.
        conn: Optional existing sqlite3 database connection.

    Returns:
        dict: Structured report containing calculated ratios, benchmark statuses, and health grade.
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

        # Obtain underlying Financial Statements
        pl_data = generate_profit_loss(
            company_id=company_id,
            start_date=start_date,
            end_date=end_date,
            conn=conn
        )
        bs_data = generate_balance_sheet(
            company_id=company_id,
            as_of_date=end_date,
            conn=conn
        )

        # Extract statement totals
        tot_ca = float(bs_data.get("total_current_assets", 0.0))
        tot_cl = float(bs_data.get("total_current_liabilities", 0.0))
        tot_assets = float(bs_data.get("total_assets", 0.0))
        tot_liab = float(bs_data.get("total_liabilities", 0.0))
        tot_eq = float(bs_data.get("total_equity", 0.0))

        tot_op_rev = float(pl_data.get("total_operating_revenue", 0.0))
        tot_oth_inc = float(pl_data.get("total_other_income", 0.0))
        tot_revenue = tot_op_rev + tot_oth_inc
        gross_profit = float(pl_data.get("gross_profit", 0.0))
        tot_op_exp = float(pl_data.get("total_operating_expenses", 0.0))
        net_profit = float(pl_data.get("net_profit", 0.0))

        # Identify inventory and cash & bank account subsets
        inventory_amount = 0.0
        cash_bank_amount = 0.0

        for item in bs_data.get("current_assets", []):
            sub_cat = (item.get("sub_category") or "").lower()
            name = (item.get("account_name") or "").lower()
            code = str(item.get("account_code") or "")
            amount = float(item.get("amount", 0.0))

            if "inventory" in sub_cat or "stock" in sub_cat or "inventory" in name or "stock" in name:
                inventory_amount += amount
            elif (
                "bank" in sub_cat or "cash" in sub_cat or
                "bank" in name or "cash" in name or "petty" in name or
                code.startswith("10") or code.startswith("11")
            ):
                cash_bank_amount += amount

        ratios = []

        # ---------------------------------------------------------------------
        # 1. LIQUIDITY RATIOS
        # ---------------------------------------------------------------------

        # Current Ratio
        if tot_cl > 0:
            cr_val = round(tot_ca / tot_cl, 2)
            cr_status = "Optimal" if cr_val >= 1.5 else ("Adequate" if cr_val >= 1.0 else "Warning")
        elif tot_ca > 0:
            cr_val = 99.0
            cr_status = "Optimal"
        else:
            cr_val = 0.0
            cr_status = "Adequate"

        ratios.append({
            "key": "current_ratio",
            "name": "Current Ratio",
            "category": "Liquidity",
            "value": cr_val,
            "display_value": f"{cr_val:.2f}x" if cr_val < 90 else "N/A (No Liabilities)",
            "benchmark": ">= 1.50x",
            "status": cr_status,
            "description": "Short-term obligation coverage using current assets."
        })

        # Quick Ratio (Acid-Test)
        liquid_assets = max(0.0, tot_ca - inventory_amount)
        if tot_cl > 0:
            qr_val = round(liquid_assets / tot_cl, 2)
            qr_status = "Optimal" if qr_val >= 1.0 else ("Adequate" if qr_val >= 0.8 else "Warning")
        elif liquid_assets > 0:
            qr_val = 99.0
            qr_status = "Optimal"
        else:
            qr_val = 0.0
            qr_status = "Adequate"

        ratios.append({
            "key": "quick_ratio",
            "name": "Quick Ratio (Acid-Test)",
            "category": "Liquidity",
            "value": qr_val,
            "display_value": f"{qr_val:.2f}x" if qr_val < 90 else "N/A (No Liabilities)",
            "benchmark": ">= 1.00x",
            "status": qr_status,
            "description": "Liquid obligation coverage excluding inventory."
        })

        # Cash Ratio
        if tot_cl > 0:
            cash_r_val = round(cash_bank_amount / tot_cl, 2)
            cash_r_status = "Optimal" if cash_r_val >= 0.5 else ("Adequate" if cash_r_val >= 0.2 else "Warning")
        elif cash_bank_amount > 0:
            cash_r_val = 99.0
            cash_r_status = "Optimal"
        else:
            cash_r_val = 0.0
            cash_r_status = "Adequate"

        ratios.append({
            "key": "cash_ratio",
            "name": "Cash Ratio",
            "category": "Liquidity",
            "value": cash_r_val,
            "display_value": f"{cash_r_val:.2f}x" if cash_r_val < 90 else "N/A (No Liabilities)",
            "benchmark": ">= 0.50x",
            "status": cash_r_status,
            "description": "Immediate cash and bank balance coverage for current debts."
        })

        # Working Capital
        wc_val = round(tot_ca - tot_cl, 2)
        wc_status = "Optimal" if wc_val > 0 else ("Warning" if wc_val < 0 else "Adequate")
        ratios.append({
            "key": "working_capital",
            "name": "Working Capital",
            "category": "Liquidity",
            "value": wc_val,
            "display_value": f"{currency} {wc_val:,.2f}",
            "benchmark": "> 0.00",
            "status": wc_status,
            "description": "Net operating liquidity available for daily business operations."
        })

        # ---------------------------------------------------------------------
        # 2. PROFITABILITY RATIOS
        # ---------------------------------------------------------------------

        # Gross Profit Margin %
        if tot_op_rev > 0:
            gpm_val = round((gross_profit / tot_op_rev) * 100.0, 2)
            gpm_status = "Optimal" if gpm_val >= 30.0 else ("Moderate" if gpm_val >= 15.0 else "Warning")
        else:
            gpm_val = 0.0
            gpm_status = "N/A"

        ratios.append({
            "key": "gross_profit_margin",
            "name": "Gross Profit Margin",
            "category": "Profitability",
            "value": gpm_val,
            "display_value": f"{gpm_val:.2f}%" if tot_op_rev > 0 else "N/A",
            "benchmark": ">= 30.00%",
            "status": gpm_status,
            "description": "Percentage of revenue retained after direct costs of goods sold."
        })

        # Net Profit Margin %
        if tot_revenue > 0:
            npm_val = round((net_profit / tot_revenue) * 100.0, 2)
            npm_status = "Optimal" if npm_val >= 10.0 else ("Moderate" if npm_val >= 3.0 else ("Warning" if npm_val < 0 else "Adequate"))
        else:
            npm_val = 0.0
            npm_status = "N/A"

        ratios.append({
            "key": "net_profit_margin",
            "name": "Net Profit Margin",
            "category": "Profitability",
            "value": npm_val,
            "display_value": f"{npm_val:.2f}%" if tot_revenue > 0 else "N/A",
            "benchmark": ">= 10.00%",
            "status": npm_status,
            "description": "Net bottom-line margin retained per revenue currency unit."
        })

        # Operating Expense Ratio %
        if tot_revenue > 0:
            oer_val = round((tot_op_exp / tot_revenue) * 100.0, 2)
            oer_status = "Optimal" if oer_val <= 50.0 else ("Moderate" if oer_val <= 70.0 else "Warning")
        else:
            oer_val = 0.0
            oer_status = "N/A"

        ratios.append({
            "key": "operating_expense_ratio",
            "name": "Operating Expense Ratio",
            "category": "Profitability",
            "value": oer_val,
            "display_value": f"{oer_val:.2f}%" if tot_revenue > 0 else "N/A",
            "benchmark": "<= 50.00%",
            "status": oer_status,
            "description": "Overhead and operating expense burden as a % of revenue."
        })

        # ---------------------------------------------------------------------
        # 3. LEVERAGE & CAPITAL STRUCTURE RATIOS
        # ---------------------------------------------------------------------

        # Debt-to-Equity Ratio
        if tot_eq > 0:
            de_val = round(tot_liab / tot_eq, 2)
            de_status = "Optimal" if de_val <= 1.5 else ("Moderate" if de_val <= 2.5 else "Warning")
        elif tot_liab > 0:
            de_val = 99.0
            de_status = "Warning"
        else:
            de_val = 0.0
            de_status = "Optimal"

        ratios.append({
            "key": "debt_to_equity",
            "name": "Debt-to-Equity Ratio",
            "category": "Leverage",
            "value": de_val,
            "display_value": f"{de_val:.2f}x" if de_val < 90 else "N/A (Deficit Equity)",
            "benchmark": "<= 1.50x",
            "status": de_status,
            "description": "Financial leverage comparing total debt liabilities to owner equity."
        })

        # Equity Ratio %
        if tot_assets > 0:
            eq_r_val = round((tot_eq / tot_assets) * 100.0, 2)
            eq_r_status = "Optimal" if eq_r_val >= 40.0 else ("Moderate" if eq_r_val >= 20.0 else "Warning")
        else:
            eq_r_val = 0.0
            eq_r_status = "N/A"

        ratios.append({
            "key": "equity_ratio",
            "name": "Equity Ratio",
            "category": "Leverage",
            "value": eq_r_val,
            "display_value": f"{eq_r_val:.2f}%" if tot_assets > 0 else "N/A",
            "benchmark": ">= 40.00%",
            "status": eq_r_status,
            "description": "Proportion of total company assets financed through owner equity."
        })

        # Compute Overall Health Rating
        warnings_count = sum(1 for r in ratios if r["status"] == "Warning")
        optimals_count = sum(1 for r in ratios if r["status"] == "Optimal")

        if warnings_count == 0 and optimals_count >= 5:
            health_grade = "Strong (Grade A)"
            health_summary = "Excellent financial liquidity, solid margins, and conservative leverage."
        elif warnings_count <= 1:
            health_grade = "Good (Grade B)"
            health_summary = "Healthy operational profile with manageable expense or leverage levels."
        elif warnings_count <= 3:
            health_grade = "Caution (Grade C)"
            health_summary = "Moderate financial exposure in cash flow, liquidity, or overhead costs."
        else:
            health_grade = "Needs Attention (Grade D)"
            health_summary = "Significant pressure on liquidity, profitability, or solvency."

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
            "summary_totals": {
                "total_current_assets": tot_ca,
                "total_current_liabilities": tot_cl,
                "total_assets": tot_assets,
                "total_liabilities": tot_liab,
                "total_equity": tot_eq,
                "total_revenue": tot_revenue,
                "gross_profit": gross_profit,
                "total_operating_expenses": tot_op_exp,
                "net_profit": net_profit,
                "cash_bank_amount": cash_bank_amount,
                "inventory_amount": inventory_amount,
            },
            "ratios": ratios,
            "health_grade": health_grade,
            "health_summary": health_summary,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    finally:
        if close_conn:
            conn.close()


def export_financial_ratios_csv(report_data: dict, output_path: str) -> str:
    """
    Export the generated Financial Ratios report to a CSV file.

    Args:
        report_data: Dictionary returned by generate_financial_ratios.
        output_path: File destination path.

    Returns:
        str: output_path
    """
    p = report_data["period"]
    curr = report_data["currency"]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(db._sanitize_csv_row([report_data["company_name"]]))
        writer.writerow(db._sanitize_csv_row(["FINANCIAL RATIOS & HEALTH ANALYTICS REPORT"]))
        writer.writerow(db._sanitize_csv_row([f"Period: {p['start_date']} to {p['end_date']}"]))
        writer.writerow(db._sanitize_csv_row([f"Base Currency: {curr} | Generated: {report_data['generated_at']}"]))
        writer.writerow([])

        # Summary Health Card
        writer.writerow(db._sanitize_csv_row(["OVERALL BUSINESS HEALTH GRADE", report_data["health_grade"]]))
        writer.writerow(db._sanitize_csv_row(["EXECUTIVE SUMMARY", report_data["health_summary"]]))
        writer.writerow([])

        # Ratios Table
        writer.writerow(db._sanitize_csv_row([
            "Ratio Metric Name", "Category", "Calculated Value", "SME Benchmark", "Health Status", "Metric Description"
        ]))

        current_cat = None
        for r in report_data.get("ratios", []):
            if r["category"] != current_cat:
                current_cat = r["category"]
                writer.writerow(db._sanitize_csv_row([f"--- {current_cat.upper()} RATIOS ---", "", "", "", "", ""]))

            writer.writerow(db._sanitize_csv_row([
                r["name"],
                r["category"],
                r["display_value"],
                r["benchmark"],
                r["status"],
                r["description"]
            ]))

    return output_path
