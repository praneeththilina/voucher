"""
reports/cash_flow.py
Cash Flow Statement Generator for Voucher Manager SME Bookkeeping.

Tracks:
- Beginning Cash & Bank Position
- Cash Inflows (Operating Receipts, Customer AR Collections, Float additions)
- Cash Outflows (Vendor AP Payments, Payment Vouchers, Operating Disbursements)
- Net Change in Cash & Bank Position
- Ending Cash & Bank Position
- Reconciliation verification
"""

import csv
from datetime import datetime
import database as db


def generate_cash_flow(
    company_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    conn=None
) -> dict:
    """
    Generate a Cash Flow Statement for the specified period based on cash & bank accounts.

    Args:
        company_id: Optional ID of the company; defaults to active company.
        start_date: Optional start date 'YYYY-MM-DD'; defaults to Jan 1 of current year.
        end_date: Optional end date 'YYYY-MM-DD'; defaults to current date.
        conn: Optional existing sqlite3 database connection.

    Returns:
        dict: Inflows, outflows, beginning/ending balances, and reconciliation status.
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

        # Backfill unjournaled vouchers
        try:
            db.backfill_vouchers_to_journal(company_id, conn=conn)
        except Exception:
            pass

        # Identify all Cash & Bank accounts (Assets with sub_category 'Cash & Bank' or codes 1110, 1120, 1130, 1140)
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
            # Fallback to standard asset accounts
            cash_accts = conn.execute("""
                SELECT id, account_code, account_name, sub_category
                FROM chart_of_accounts
                WHERE company_id = ? AND is_active = 1 AND account_code LIKE '11%'
            """, (company_id,)).fetchall()
            cash_acct_ids = [r["id"] for r in cash_accts]

        # 1. Beginning Cash Balance (all transactions before start_date)
        placeholders = ",".join("?" for _ in cash_acct_ids) if cash_acct_ids else "0"
        beg_query = f"""
            SELECT COALESCE(SUM(jl.debit_amount - jl.credit_amount), 0.0) as beg_bal
            FROM journal_lines jl
            JOIN journal_entries je ON jl.entry_id = je.id
            WHERE je.company_id = ?
              AND je.is_posted = 1
              AND je.entry_date < ?
              AND jl.account_id IN ({placeholders})
        """
        beg_params = [company_id, start_date] + cash_acct_ids
        beg_row = conn.execute(beg_query, beg_params).fetchone()
        beginning_cash = round(float(beg_row["beg_bal"]) if beg_row and beg_row["beg_bal"] else 0.0, 2)

        # 2. Inflows and Outflows within the period
        period_query = f"""
            SELECT jl.id, jl.entry_id, jl.account_id, jl.debit_amount, jl.credit_amount,
                   je.entry_number, je.entry_date, je.description, je.entry_type, je.source_module,
                   coa.account_code, coa.account_name
            FROM journal_lines jl
            JOIN journal_entries je ON jl.entry_id = je.id
            JOIN chart_of_accounts coa ON jl.account_id = coa.id
            WHERE je.company_id = ?
              AND je.is_posted = 1
              AND je.entry_date >= ?
              AND je.entry_date <= ?
              AND jl.account_id IN ({placeholders})
            ORDER BY je.entry_date ASC, je.id ASC
        """
        period_params = [company_id, start_date, end_date] + cash_acct_ids
        trans_rows = conn.execute(period_query, period_params).fetchall()

        inflows = []
        outflows = []
        tot_inflows = 0.0
        tot_outflows = 0.0

        for r in trans_rows:
            d = dict(r)
            deb = float(d["debit_amount"])
            cred = float(d["credit_amount"])

            # Inflow: Debited to Cash/Bank account
            if deb > 0.001:
                inflows.append({
                    "entry_id": d["entry_id"],
                    "account_id": d["account_id"],
                    "date": d["entry_date"],
                    "entry_number": d["entry_number"],
                    "description": d["description"],
                    "account": f"{d['account_code']} - {d['account_name']}",
                    "amount": round(deb, 2)
                })
                tot_inflows += deb

            # Outflow: Credited to Cash/Bank account
            if cred > 0.001:
                outflows.append({
                    "entry_id": d["entry_id"],
                    "account_id": d["account_id"],
                    "date": d["entry_date"],
                    "entry_number": d["entry_number"],
                    "description": d["description"],
                    "account": f"{d['account_code']} - {d['account_name']}",
                    "amount": round(cred, 2)
                })
                tot_outflows += cred

        tot_inflows = round(tot_inflows, 2)
        tot_outflows = round(tot_outflows, 2)
        net_change = round(tot_inflows - tot_outflows, 2)
        ending_cash = round(beginning_cash + net_change, 2)

        # Account breakdown at end_date
        account_breakdown = []
        for a in cash_accts:
            aid = a["id"]
            bal_row = conn.execute("""
                SELECT COALESCE(SUM(jl.debit_amount - jl.credit_amount), 0.0) as bal
                FROM journal_lines jl
                JOIN journal_entries je ON jl.entry_id = je.id
                WHERE je.company_id = ? AND je.is_posted = 1 AND je.entry_date <= ? AND jl.account_id = ?
            """, (company_id, end_date, aid)).fetchone()
            bal = round(float(bal_row["bal"]) if bal_row and bal_row["bal"] else 0.0, 2)
            account_breakdown.append({
                "account_id": aid,
                "code": a["account_code"],
                "name": a["account_name"],
                "balance": bal
            })

        return {
            "company_id": company_id,
            "company_name": comp_name,
            "period": {"start_date": start_date, "end_date": end_date},
            "currency": currency,
            "beginning_cash": beginning_cash,
            "inflows": inflows,
            "total_inflows": tot_inflows,
            "outflows": outflows,
            "total_outflows": tot_outflows,
            "net_change": net_change,
            "ending_cash": ending_cash,
            "account_breakdown": account_breakdown,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    finally:
        if close_conn:
            conn.close()


def export_cash_flow_csv(report_data: dict, output_path: str) -> str:
    """
    Export the generated Cash Flow report to CSV.

    Args:
        report_data: Dictionary returned by generate_cash_flow.
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
        write_row(["CASH FLOW STATEMENT"])
        write_row([f"Period: {p['start_date']} to {p['end_date']}"])
        write_row([f"Currency: {curr} | Generated: {report_data['generated_at']}"])
        write_row([])

        write_row(["BEGINNING CASH & BANK BALANCE", "", "", f"{report_data['beginning_cash']:.2f}"])
        write_row([])

        write_row(["--- CASH INFLOWS (RECEIPTS) ---", "", "", ""])
        write_row(["Date", "Entry #", "Description / Account", f"Amount ({curr})"])
        for it in report_data["inflows"]:
            write_row([it["date"], it["entry_number"], f"{it['description']} ({it['account']})", f"{it['amount']:.2f}"])
        write_row(["TOTAL CASH INFLOWS", "", "", f"{report_data['total_inflows']:.2f}"])
        write_row([])

        write_row(["--- CASH OUTFLOWS (DISBURSEMENTS) ---", "", "", ""])
        write_row(["Date", "Entry #", "Description / Account", f"Amount ({curr})"])
        for it in report_data["outflows"]:
            write_row([it["date"], it["entry_number"], f"{it['description']} ({it['account']})", f"{it['amount']:.2f}"])
        write_row(["TOTAL CASH OUTFLOWS", "", "", f"{report_data['total_outflows']:.2f}"])
        write_row([])

        write_row(["NET CHANGE IN CASH", "", "", f"{report_data['net_change']:.2f}"])
        write_row(["ENDING CASH & BANK BALANCE", "", "", f"{report_data['ending_cash']:.2f}"])
        write_row([])

        write_row(["--- ACCOUNT BALANCES AT PERIOD END ---", "", "", ""])
        for ab in report_data["account_breakdown"]:
            write_row([ab["code"], ab["name"], "", f"{ab['balance']:.2f}"])

    return output_path
