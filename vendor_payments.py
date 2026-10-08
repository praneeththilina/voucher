"""Vendor centre and Accounts Payable settlement services."""
from datetime import datetime
import database as db
TOL=.005

def _actor():
    u=db.get_current_user() or {};return u.get('display_name') or u.get('username','System')

def cash_accounts(company_id=None, currency=None):
    """Return cash/bank/card ledgers in the requested transaction currency."""
    return db.get_currency_accounts(company_id=company_id, currency=currency)

def open_bills(company_id=None,supplier_id=None,start_date=None,end_date=None):
    return db.get_ap_invoices(company_id=company_id,status=None,supplier_id=supplier_id,start_date=start_date,end_date=end_date)

def credits(company_id=None,supplier_id=None,open_only=False):
    con=db.get_connection()
    try:
        cid=company_id or db.get_active_company_id(con);q="SELECT c.*,s.name supplier_name FROM vendor_credits c JOIN suppliers s ON s.id=c.supplier_id WHERE c.company_id=?";p=[cid]
        if supplier_id:q+=' AND c.supplier_id=?';p.append(supplier_id)
        if open_only:q+=" AND c.remaining_amount>0.004 AND c.status='Open'"
        q+=' ORDER BY c.credit_date DESC,c.id DESC';return [dict(x) for x in con.execute(q,p).fetchall()]
    finally:con.close()

def available_credit(company_id,supplier_id):return sum(float(x['remaining_amount']) for x in credits(company_id,supplier_id,True))

def create_credit(data):
    """Record a vendor credit in the vendor's assigned currency."""
    amount = round(float(data["amount"]), 2)
    if amount <= 0:
        raise ValueError("Credit amount must be greater than zero.")
    con = db.get_connection()
    try:
        company_id = data.get("company_id") or db.get_active_company_id(con)
        credit_date = data.get("credit_date") or datetime.now().strftime("%Y-%m-%d")
        db.assert_accounting_period_open(
            company_id, credit_date, "record this vendor credit", conn=con
        )
        supplier = db.get_supplier_by_id(int(data["supplier_id"]), conn=con)
        if not supplier:
            raise ValueError("Vendor not found.")
        currency, exchange_rate = db.normalize_transaction_currency(
            company_id, supplier.get("currency"), data.get("exchange_rate"),
            credit_date, conn=con
        )
        base_amount = round(amount * exchange_rate, 2)
        ap_account = db.get_account_by_code("2110", company_id, conn=con)
        if not ap_account:
            raise ValueError("Accounts Payable ledger 2110 is missing.")
        expense_account_id = int(data["expense_account_id"])
        with con:
            cursor = con.execute(
                """
                INSERT INTO vendor_credits(
                    company_id, supplier_id, credit_number, credit_date, amount,
                    remaining_amount, expense_account_id, reference, notes,
                    created_by, currency, exchange_rate, base_amount
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    company_id, supplier["id"], data["credit_number"].strip(),
                    credit_date, amount, amount, expense_account_id,
                    data.get("reference", "").strip(),
                    data.get("notes", "").strip(), _actor(), currency,
                    exchange_rate, base_amount,
                ),
            )
            credit_id = cursor.lastrowid
            journal_id = db.create_journal_entry(
                {
                    "company_id": company_id,
                    "entry_date": credit_date,
                    "reference": data["credit_number"],
                    "description": f"Vendor credit {data['credit_number']} - {supplier['name']}",
                    "entry_type": "Credit",
                    "source_module": "vendor_credit",
                    "source_id": credit_id,
                    "created_by": _actor(),
                    "transaction_currency": currency,
                    "exchange_rate": exchange_rate,
                    "foreign_amount": amount,
                },
                [
                    {
                        "account_id": ap_account["id"],
                        "debit_amount": base_amount,
                        "credit_amount": 0,
                        "description": "Reduce Accounts Payable",
                    },
                    {
                        "account_id": expense_account_id,
                        "debit_amount": 0,
                        "credit_amount": base_amount,
                        "description": "Vendor credit / purchase return",
                    },
                ],
                conn=con,
            )
            con.execute(
                "UPDATE vendor_credits SET journal_entry_id=? WHERE id=?",
                (journal_id, credit_id),
            )
        return credit_id
    finally:
        con.close()

def _refresh_invoice(invoice_id,con):
    inv=con.execute('SELECT total_amount FROM ap_invoices WHERE id=?',(invoice_id,)).fetchone()
    cash=con.execute('SELECT COALESCE(SUM(amount),0) FROM ap_payments WHERE invoice_id=?',(invoice_id,)).fetchone()[0];credit=con.execute('SELECT COALESCE(SUM(amount),0) FROM ap_credit_applications WHERE invoice_id=?',(invoice_id,)).fetchone()[0];paid=round(float(cash)+float(credit),2);total=float(inv['total_amount']);status='Paid' if paid>=total-TOL else ('Partially Paid' if paid>0 else 'Unpaid');con.execute('UPDATE ap_invoices SET paid_amount=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(min(paid,total),status,invoice_id))

def pay_bills(data, allocations):
    """Pay several same-currency bills and recognize realized FX differences."""
    clean = []
    for allocation in allocations:
        cash = round(float(allocation.get("cash_amount") or 0), 2)
        credit = round(float(allocation.get("credit_amount") or 0), 2)
        if cash > 0 or credit > 0:
            clean.append({
                "invoice_id": int(allocation["invoice_id"]),
                "cash": cash,
                "credit": credit,
            })
    if not clean:
        raise ValueError("Select at least one bill and enter an amount.")

    con = db.get_connection()
    try:
        company_id = data.get("company_id") or db.get_active_company_id(con)
        supplier_id = int(data["supplier_id"])
        payment_date = data.get("payment_date") or datetime.now().strftime("%Y-%m-%d")
        db.assert_accounting_period_open(
            company_id, payment_date, "pay these supplier bills", conn=con
        )
        invoices = []
        currency = None
        historical_cash_base = 0.0
        for allocation in clean:
            row = con.execute(
                "SELECT * FROM ap_invoices WHERE id = ? AND company_id = ? "
                "AND supplier_id = ? AND status NOT IN ('Paid', 'Cancelled')",
                (allocation["invoice_id"], company_id, supplier_id),
            ).fetchone()
            if not row:
                raise ValueError("A selected bill is no longer open for this vendor.")
            invoice = dict(row)
            invoice_currency = (invoice.get("currency") or db.get_company_base_currency(
                company_id, conn=con
            )).upper()
            if currency is None:
                currency = invoice_currency
            elif currency != invoice_currency:
                raise ValueError("One payment batch cannot mix bill currencies.")
            due = float(invoice["total_amount"]) - float(invoice["paid_amount"])
            if allocation["cash"] + allocation["credit"] > due + TOL:
                raise ValueError(
                    f"Allocation for bill {invoice['invoice_number']} exceeds its "
                    f"{due:,.2f} {currency} balance."
                )
            _, invoice_rate = db.normalize_transaction_currency(
                company_id, currency, invoice.get("exchange_rate"),
                invoice.get("invoice_date"), conn=con
            )
            historical_cash_base += allocation["cash"] * invoice_rate
            invoices.append(invoice)

        currency, settlement_rate = db.normalize_transaction_currency(
            company_id, currency, data.get("exchange_rate"), payment_date, conn=con
        )
        account = db.validate_currency_account(
            int(data["payment_account_id"]), company_id, currency, conn=con
        )
        available = available_credit(company_id, supplier_id)
        credit_total = round(sum(item["credit"] for item in clean), 2)
        cash_total = round(sum(item["cash"] for item in clean), 2)
        if credit_total > available + TOL:
            raise ValueError(
                f"Applied credit exceeds available vendor credit ({available:,.2f})."
            )
        method = data.get("payment_method", "Cheque")
        print_later = int(bool(data.get("print_later")))
        check_number = data.get("check_number", "").strip()
        if method == "Cheque" and not print_later and not check_number:
            raise ValueError("Enter the check number or choose Print later.")
        settlement_base = round(cash_total * settlement_rate, 2)
        historical_cash_base = round(historical_cash_base, 2)

        with con:
            cursor = con.execute(
                """
                INSERT INTO ap_payment_batches(
                    company_id, supplier_id, payment_date, payment_method,
                    payment_account_id, total_cash_amount, total_credit_amount,
                    reference, check_number, print_later, notes, created_by,
                    currency, exchange_rate, base_cash_amount
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    company_id, supplier_id, payment_date, method, account["id"],
                    cash_total, credit_total, data.get("reference", "").strip(),
                    check_number, print_later, data.get("notes", "").strip(),
                    _actor(), currency, settlement_rate, settlement_base,
                ),
            )
            batch_id = cursor.lastrowid
            open_credits = [dict(row) for row in con.execute(
                "SELECT * FROM vendor_credits WHERE company_id = ? AND supplier_id = ? "
                "AND status = 'Open' AND remaining_amount > 0.004 "
                "ORDER BY credit_date, id",
                (company_id, supplier_id),
            ).fetchall()]
            for allocation in clean:
                con.execute(
                    "INSERT INTO ap_payment_allocations(batch_id, invoice_id, "
                    "cash_amount, credit_amount) VALUES(?,?,?,?)",
                    (batch_id, allocation["invoice_id"], allocation["cash"], allocation["credit"]),
                )
                if allocation["cash"] > 0:
                    con.execute(
                        """
                        INSERT INTO ap_payments(
                            invoice_id, company_id, payment_date, amount,
                            payment_method, reference, notes, created_by, batch_id,
                            payment_account_id, currency, exchange_rate, base_amount
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            allocation["invoice_id"], company_id, payment_date,
                            allocation["cash"], method,
                            check_number or data.get("reference", "").strip(),
                            data.get("notes", "").strip(), _actor(), batch_id,
                            account["id"], currency, settlement_rate,
                            round(allocation["cash"] * settlement_rate, 2),
                        ),
                    )
                remaining = allocation["credit"]
                for vendor_credit in open_credits:
                    take = min(remaining, float(vendor_credit["remaining_amount"]))
                    if take <= TOL:
                        continue
                    con.execute(
                        "INSERT INTO ap_credit_applications(credit_id, invoice_id, "
                        "batch_id, amount) VALUES(?,?,?,?)",
                        (vendor_credit["id"], allocation["invoice_id"], batch_id, take),
                    )
                    new_remaining = float(vendor_credit["remaining_amount"]) - take
                    con.execute(
                        "UPDATE vendor_credits SET remaining_amount=?, status=? WHERE id=?",
                        (max(0, new_remaining), "Applied" if new_remaining <= TOL else "Open", vendor_credit["id"]),
                    )
                    vendor_credit["remaining_amount"] = new_remaining
                    remaining -= take
                    if remaining <= TOL:
                        break
                _refresh_invoice(allocation["invoice_id"], con)

            if cash_total > 0:
                ap_account = db.get_account_by_code("2110", company_id, conn=con)
                lines = [
                    {
                        "account_id": ap_account["id"],
                        "debit_amount": historical_cash_base,
                        "credit_amount": 0,
                        "description": "Settle Accounts Payable",
                    },
                    {
                        "account_id": account["id"],
                        "debit_amount": 0,
                        "credit_amount": settlement_base,
                        "description": f"Paid via {method}",
                    },
                ]
                difference = round(settlement_base - historical_cash_base, 2)
                if difference > 0:
                    fx = db.get_account_by_code("5985", company_id, conn=con)
                    lines.append({
                        "account_id": fx["id"], "debit_amount": difference,
                        "credit_amount": 0, "description": "Realized foreign exchange loss",
                    })
                elif difference < 0:
                    fx = db.get_account_by_code("4985", company_id, conn=con)
                    lines.append({
                        "account_id": fx["id"], "debit_amount": 0,
                        "credit_amount": abs(difference),
                        "description": "Realized foreign exchange gain",
                    })
                journal_id = db.create_journal_entry(
                    {
                        "company_id": company_id,
                        "entry_date": payment_date,
                        "reference": check_number or data.get("reference") or f"PAY-{batch_id}",
                        "description": "Pay selected vendor bills",
                        "entry_type": "Payment",
                        "source_module": "ap_payment_batch",
                        "source_id": batch_id,
                        "created_by": _actor(),
                        "transaction_currency": currency,
                        "exchange_rate": settlement_rate,
                        "foreign_amount": cash_total,
                    },
                    lines,
                    conn=con,
                )
                con.execute(
                    "UPDATE ap_payment_batches SET journal_entry_id=? WHERE id=?",
                    (journal_id, batch_id),
                )
        return batch_id
    finally:
        con.close()

def vendor_summary(supplier_id):
    con=db.get_connection()
    try:
        s=db.get_supplier_by_id(supplier_id,conn=con);bills=db.get_ap_invoices(company_id=s['company_id'],supplier_id=supplier_id,conn=con);return {'supplier':s,'bills':bills,'open_bills':sum(1 for x in bills if x['status'] not in ('Paid','Cancelled')),'invoiced':sum(float(x['total_amount']) for x in bills if x['status']!='Cancelled'),'paid':sum(float(x['paid_amount']) for x in bills if x['status']!='Cancelled'),'due':sum(float(x['balance_due']) for x in bills if x['status'] not in ('Paid','Cancelled')),'credit':available_credit(s['company_id'],supplier_id)}
    finally:con.close()