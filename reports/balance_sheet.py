"""
reports/balance_sheet.py
Balance Sheet (Statement of Financial Position) Generator for Voucher Manager SME Bookkeeping.

Enforces:
    Assets = Liabilities + Equity
Where:
    Equity = Owner's Capital + Retained Earnings + Current Period Net Profit / (Loss)
"""

import csv
from datetime import datetime
import database as db


def generate_balance_sheet(
    company_id: int | None = None,
    as_of_date: str | None = None,
    conn=None
) -> dict:
    """
    Generate a Balance Sheet (Statement of Financial Position) as of a specific date.

    Args:
        company_id: Optional ID of the company; defaults to active company.
        as_of_date: Optional 'YYYY-MM-DD' cutoff date; defaults to today.
        conn: Optional existing sqlite3 database connection.

    Returns:
        dict: Categorized assets, liabilities, equity, and balancing verification.
    """
    close_conn = False
    if conn is None:
        conn = db.get_connection()
        close_conn = True

    try:
        if company_id is None:
            company_id = db.get_active_company_id(conn)

        now = datetime.now()
        if not as_of_date:
            as_of_date = now.strftime("%Y-%m-%d")

        comp = db.get_company(company_id, conn=conn) or {}
        comp_name = comp.get("name") or "Main Enterprise"
        currency = db.get_company_base_currency(company_id, conn=conn) or "LKR"

        # Backfill any unjournaled vouchers
        try:
            db.backfill_vouchers_to_journal(company_id, conn=conn)
        except Exception:
            pass

        # Query all Asset, Liability, Equity accounts up to as_of_date
        query = """
            SELECT coa.id as account_id, coa.account_code, coa.account_name, coa.account_type,
                   coa.sub_category, coa.normal_balance,
                   COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.debit_amount ELSE 0 END), 0.0) as total_debit,
                   COALESCE(SUM(CASE WHEN je.id IS NOT NULL THEN jl.credit_amount ELSE 0 END), 0.0) as total_credit
            FROM chart_of_accounts coa
            LEFT JOIN journal_lines jl ON coa.id = jl.account_id
            LEFT JOIN journal_entries je ON jl.entry_id = je.id AND je.is_posted = 1 AND je.entry_date <= ?
            WHERE coa.company_id = ?
              AND coa.is_active = 1
              AND coa.account_type IN ('Asset', 'Liability', 'Equity')
            GROUP BY coa.id
            ORDER BY coa.account_code ASC
        """
        rows = conn.execute(query, (as_of_date, company_id)).fetchall()

        current_assets = []
        non_current_assets = []
        current_liabilities = []
        long_term_liabilities = []
        equity_accounts = []

        tot_ca = 0.0
        tot_nca = 0.0
        tot_cl = 0.0
        tot_ltl = 0.0
        tot_eq = 0.0

        for r in rows:
            d = dict(r)
            code = d["account_code"]
            name = d["account_name"]
            acct_type = d["account_type"]
            sub_cat = d.get("sub_category") or ""
            deb = float(d["total_debit"])
            cred = float(d["total_credit"])

            if acct_type == "Asset":
                # Asset normal balance: Debit
                net = deb - cred
                if abs(net) < 0.001:
                    continue

                item = {
                    "account_id": d["account_id"],
                    "account_code": code,
                    "account_name": name,
                    "sub_category": sub_cat or "Current Assets",
                    "amount": round(net, 2),
                }

                if sub_cat in ("Fixed Assets", "Non-Current Assets") or code.startswith("14") or code.startswith("15"):
                    non_current_assets.append(item)
                    tot_nca += net
                else:
                    current_assets.append(item)
                    tot_ca += net

            elif acct_type == "Liability":
                # Liability normal balance: Credit
                net = cred - deb
                if abs(net) < 0.001:
                    continue

                item = {
                    "account_id": d["account_id"],
                    "account_code": code,
                    "account_name": name,
                    "sub_category": sub_cat or "Current Liabilities",
                    "amount": round(net, 2),
                }

                if sub_cat in ("Long-Term Liabilities", "Loans") or code.startswith("25"):
                    long_term_liabilities.append(item)
                    tot_ltl += net
                else:
                    current_liabilities.append(item)
                    tot_cl += net

            elif acct_type == "Equity":
                # Equity normal balance: Credit
                net = cred - deb
                if abs(net) < 0.001:
                    continue

                item = {
                    "account_id": d["account_id"],
                    "account_code": code,
                    "account_name": name,
                    "sub_category": sub_cat or "Equity",
                    "amount": round(net, 2),
                }
                equity_accounts.append(item)
                tot_eq += net

        # Calculate Current Period Net Income (Retained Earnings to Date)
        net_income_query = """
            SELECT
                COALESCE(SUM(CASE WHEN coa.account_type = 'Income' THEN jl.credit_amount - jl.debit_amount ELSE 0 END), 0.0) -
                COALESCE(SUM(CASE WHEN coa.account_type = 'Expense' THEN jl.debit_amount - jl.credit_amount ELSE 0 END), 0.0) as net_income
            FROM chart_of_accounts coa
            JOIN journal_lines jl ON coa.id = jl.account_id
            JOIN journal_entries je ON jl.entry_id = je.id
            WHERE coa.company_id = ?
              AND je.is_posted = 1
              AND je.entry_date <= ?
              AND coa.account_type IN ('Income', 'Expense')
        """
        ni_row = conn.execute(net_income_query, (company_id, as_of_date)).fetchone()
        net_income = round(float(ni_row["net_income"]) if ni_row and ni_row["net_income"] else 0.0, 2)

        # Append Net Income to Equity breakdown
        equity_items = list(equity_accounts)
        if abs(net_income) >= 0.01 or not equity_items:
            equity_items.append({
                "account_id": None,
                "account_code": "NET_INC",
                "account_name": "Current Period Net Profit / (Loss)",
                "sub_category": "Earnings",
                "amount": net_income,
                "is_calculated": True
            })

        tot_ca = round(tot_ca, 2)
        tot_nca = round(tot_nca, 2)
        tot_assets = round(tot_ca + tot_nca, 2)

        tot_cl = round(tot_cl, 2)
        tot_ltl = round(tot_ltl, 2)
        tot_liabilities = round(tot_cl + tot_ltl, 2)

        tot_equity = round(tot_eq + net_income, 2)
        tot_liabilities_and_equity = round(tot_liabilities + tot_equity, 2)

        diff = round(tot_assets - tot_liabilities_and_equity, 2)
        is_balanced = abs(diff) < 0.01

        return {
            "company_id": company_id,
            "company_name": comp_name,
            "company_address": comp.get("address") or "",
            "company_phone": comp.get("phone") or "",
            "company_email": comp.get("email") or "",
            "tax_number": comp.get("tax_number") or "",
            "logo_path": comp.get("logo_path") or "",
            "as_of_date": as_of_date,
            "currency": currency,
            "current_assets": current_assets,
            "total_current_assets": tot_ca,
            "non_current_assets": non_current_assets,
            "total_non_current_assets": tot_nca,
            "total_assets": tot_assets,
            "current_liabilities": current_liabilities,
            "total_current_liabilities": tot_cl,
            "long_term_liabilities": long_term_liabilities,
            "total_long_term_liabilities": tot_ltl,
            "total_liabilities": tot_liabilities,
            "equity_items": equity_items,
            "current_period_net_income": net_income,
            "total_equity": tot_equity,
            "total_liabilities_and_equity": tot_liabilities_and_equity,
            "difference": diff,
            "is_balanced": is_balanced,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    finally:
        if close_conn:
            conn.close()


def export_balance_sheet_csv(report_data: dict, output_path: str) -> str:
    """
    Export the generated Balance Sheet to a CSV file.

    Args:
        report_data: Dictionary returned by generate_balance_sheet.
        output_path: File destination path.

    Returns:
        str: output_path
    """
    curr = report_data["currency"]
    as_of = report_data["as_of_date"]

    with open(output_path, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        def write_row(row):
            writer.writerow(db._sanitize_csv_row(row))

        write_row([report_data["company_name"]])
        write_row(["BALANCE SHEET (STATEMENT OF FINANCIAL POSITION)"])
        write_row([f"As of: {as_of}"])
        write_row([f"Currency: {curr} | Generated: {report_data['generated_at']}"])
        write_row([])

        write_row(["Account Code", "Account Name", "Subcategory", f"Amount ({curr})"])

        # ASSETS
        write_row(["=== ASSETS ===", "", "", ""])
        write_row(["--- CURRENT ASSETS ---", "", "", ""])
        for it in report_data["current_assets"]:
            write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}"])
        write_row(["TOTAL CURRENT ASSETS", "", "", f"{report_data['total_current_assets']:.2f}"])
        write_row([])

        if report_data["non_current_assets"]:
            write_row(["--- NON-CURRENT ASSETS ---", "", "", ""])
            for it in report_data["non_current_assets"]:
                write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}"])
            write_row(["TOTAL NON-CURRENT ASSETS", "", "", f"{report_data['total_non_current_assets']:.2f}"])
            write_row([])

        write_row(["TOTAL ASSETS", "", "", f"{report_data['total_assets']:.2f}"])
        write_row([])

        # LIABILITIES
        write_row(["=== LIABILITIES ===", "", "", ""])
        write_row(["--- CURRENT LIABILITIES ---", "", "", ""])
        for it in report_data["current_liabilities"]:
            write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}"])
        write_row(["TOTAL CURRENT LIABILITIES", "", "", f"{report_data['total_current_liabilities']:.2f}"])
        write_row([])

        if report_data["long_term_liabilities"]:
            write_row(["--- LONG-TERM LIABILITIES ---", "", "", ""])
            for it in report_data["long_term_liabilities"]:
                write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}"])
            write_row(["TOTAL LONG-TERM LIABILITIES", "", "", f"{report_data['total_long_term_liabilities']:.2f}"])
            write_row([])

        write_row(["TOTAL LIABILITIES", "", "", f"{report_data['total_liabilities']:.2f}"])
        write_row([])

        # EQUITY
        write_row(["=== EQUITY ===", "", "", ""])
        for it in report_data["equity_items"]:
            write_row([it["account_code"], it["account_name"], it["sub_category"], f"{it['amount']:.2f}"])
        write_row(["TOTAL EQUITY", "", "", f"{report_data['total_equity']:.2f}"])
        write_row([])

        write_row(["TOTAL LIABILITIES & EQUITY", "", "", f"{report_data['total_liabilities_and_equity']:.2f}"])
        status = "BALANCED" if report_data["is_balanced"] else f"OUT OF BALANCE (Diff: {report_data['difference']:.2f})"
        write_row(["STATUS", "", "", status])

    return output_path
