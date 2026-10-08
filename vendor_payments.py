"""Vendor centre and Accounts Payable settlement services."""
from datetime import datetime
import database as db
TOL=.005

def _actor():
    u=db.get_current_user() or {};return u.get('display_name') or u.get('username','System')

def cash_accounts(company_id=None):
    return [a for a in db.get_chart_of_accounts(company_id=company_id) if a['account_type']=='Asset' and ('cash' in (a.get('account_name') or '').lower() or 'bank' in (a.get('account_name') or '').lower() or 'cash' in (a.get('sub_category') or '').lower() or 'bank' in (a.get('sub_category') or '').lower())]

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
    amount=round(float(data['amount']),2)
    if amount<=0:raise ValueError('Credit amount must be greater than zero.')
    con=db.get_connection()
    try:
        cid=data.get('company_id') or db.get_active_company_id(con);date=data.get('credit_date') or datetime.now().strftime('%Y-%m-%d');db.assert_accounting_period_open(cid,date,'record this vendor credit',conn=con);ap=db.get_account_by_code('2110',cid,conn=con)
        if not ap:raise ValueError('Accounts Payable ledger 2110 is missing.')
        supplier=db.get_supplier_by_id(int(data['supplier_id']),conn=con)
        if not supplier:raise ValueError('Vendor not found.')
        with con:
            cur=con.execute("INSERT INTO vendor_credits(company_id,supplier_id,credit_number,credit_date,amount,remaining_amount,expense_account_id,reference,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)",(cid,supplier['id'],data['credit_number'].strip(),date,amount,amount,int(data['expense_account_id']),data.get('reference','').strip(),data.get('notes','').strip(),_actor()));credit_id=cur.lastrowid
            jid=db.create_journal_entry({'company_id':cid,'entry_date':date,'reference':data['credit_number'],'description':f"Vendor credit {data['credit_number']} - {supplier['name']}",'entry_type':'Credit','source_module':'vendor_credit','source_id':credit_id,'created_by':_actor()},[{'account_id':ap['id'],'debit_amount':amount,'credit_amount':0,'description':'Reduce Accounts Payable'},{'account_id':int(data['expense_account_id']),'debit_amount':0,'credit_amount':amount,'description':'Vendor credit / purchase return'}],conn=con);con.execute('UPDATE vendor_credits SET journal_entry_id=? WHERE id=?',(jid,credit_id))
        return credit_id
    finally:con.close()

def _refresh_invoice(invoice_id,con):
    inv=con.execute('SELECT total_amount FROM ap_invoices WHERE id=?',(invoice_id,)).fetchone()
    cash=con.execute('SELECT COALESCE(SUM(amount),0) FROM ap_payments WHERE invoice_id=?',(invoice_id,)).fetchone()[0];credit=con.execute('SELECT COALESCE(SUM(amount),0) FROM ap_credit_applications WHERE invoice_id=?',(invoice_id,)).fetchone()[0];paid=round(float(cash)+float(credit),2);total=float(inv['total_amount']);status='Paid' if paid>=total-TOL else ('Partially Paid' if paid>0 else 'Unpaid');con.execute('UPDATE ap_invoices SET paid_amount=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(min(paid,total),status,invoice_id))

def pay_bills(data,allocations):
    """Pay several open bills for one vendor and apply that vendor's credits."""
    clean=[]
    for x in allocations:
        cash=round(float(x.get('cash_amount') or 0),2);credit=round(float(x.get('credit_amount') or 0),2)
        if cash>0 or credit>0:clean.append({'invoice_id':int(x['invoice_id']),'cash':cash,'credit':credit})
    if not clean:raise ValueError('Select at least one bill and enter an amount.')
    con=db.get_connection()
    try:
        cid=data.get('company_id') or db.get_active_company_id(con);supplier_id=int(data['supplier_id']);date=data.get('payment_date') or datetime.now().strftime('%Y-%m-%d');db.assert_accounting_period_open(cid,date,'pay these supplier bills',conn=con)
        account=con.execute("SELECT * FROM chart_of_accounts WHERE id=? AND company_id=? AND account_type='Asset'",(int(data['payment_account_id']),cid)).fetchone()
        if not account:raise ValueError('Select a valid cash or bank ledger account.')
        available=available_credit(cid,supplier_id);credit_total=sum(x['credit'] for x in clean);cash_total=sum(x['cash'] for x in clean)
        if credit_total>available+TOL:raise ValueError(f'Applied credit exceeds available vendor credit ({available:,.2f}).')
        for x in clean:
            inv=con.execute("SELECT * FROM ap_invoices WHERE id=? AND company_id=? AND supplier_id=? AND status NOT IN ('Paid','Cancelled')",(x['invoice_id'],cid,supplier_id)).fetchone()
            if not inv:raise ValueError('A selected bill is no longer open for this vendor.')
            due=float(inv['total_amount'])-float(inv['paid_amount'])
            if x['cash']+x['credit']>due+TOL:raise ValueError(f"Allocation for bill {inv['invoice_number']} exceeds its {due:,.2f} balance.")
        method=data.get('payment_method','Cheque');print_later=int(bool(data.get('print_later')));check_no=data.get('check_number','').strip()
        if method=='Cheque' and not print_later and not check_no:raise ValueError('Enter the check number or choose Print later.')
        with con:
            cur=con.execute("INSERT INTO ap_payment_batches(company_id,supplier_id,payment_date,payment_method,payment_account_id,total_cash_amount,total_credit_amount,reference,check_number,print_later,notes,created_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(cid,supplier_id,date,method,account['id'],cash_total,credit_total,data.get('reference','').strip(),check_no,print_later,data.get('notes','').strip(),_actor()));batch=cur.lastrowid
            open_credits=con.execute("SELECT * FROM vendor_credits WHERE company_id=? AND supplier_id=? AND status='Open' AND remaining_amount>0.004 ORDER BY credit_date,id",(cid,supplier_id)).fetchall()
            for x in clean:
                con.execute('INSERT INTO ap_payment_allocations(batch_id,invoice_id,cash_amount,credit_amount) VALUES(?,?,?,?)',(batch,x['invoice_id'],x['cash'],x['credit']))
                if x['cash']>0:con.execute("INSERT INTO ap_payments(invoice_id,company_id,payment_date,amount,payment_method,reference,notes,created_by,batch_id,payment_account_id) VALUES(?,?,?,?,?,?,?,?,?,?)",(x['invoice_id'],cid,date,x['cash'],method,check_no or data.get('reference','').strip(),data.get('notes','').strip(),_actor(),batch,account['id']))
                remaining=x['credit']
                for credit in open_credits:
                    take=min(remaining,float(credit['remaining_amount']))
                    if take<=TOL:continue
                    con.execute('INSERT INTO ap_credit_applications(credit_id,invoice_id,batch_id,amount) VALUES(?,?,?,?)',(credit['id'],x['invoice_id'],batch,take));new=float(credit['remaining_amount'])-take;con.execute("UPDATE vendor_credits SET remaining_amount=?,status=? WHERE id=?",(max(0,new),'Applied' if new<=TOL else 'Open',credit['id']));credit=dict(credit);credit['remaining_amount']=new;remaining-=take
                    for i,c in enumerate(open_credits):
                        if c['id']==credit['id']:open_credits[i]=credit
                    if remaining<=TOL:break
                _refresh_invoice(x['invoice_id'],con)
            if cash_total>0:
                ap=db.get_account_by_code('2110',cid,conn=con);jid=db.create_journal_entry({'company_id':cid,'entry_date':date,'reference':check_no or data.get('reference') or f'PAY-{batch}','description':'Pay selected vendor bills','entry_type':'Payment','source_module':'ap_payment_batch','source_id':batch,'created_by':_actor()},[{'account_id':ap['id'],'debit_amount':cash_total,'credit_amount':0,'description':'Settle Accounts Payable'},{'account_id':account['id'],'debit_amount':0,'credit_amount':cash_total,'description':f"Paid via {method}"}],conn=con);con.execute('UPDATE ap_payment_batches SET journal_entry_id=? WHERE id=?',(jid,batch))
        return batch
    finally:con.close()

def vendor_summary(supplier_id):
    con=db.get_connection()
    try:
        s=db.get_supplier_by_id(supplier_id,conn=con);bills=db.get_ap_invoices(company_id=s['company_id'],supplier_id=supplier_id,conn=con);return {'supplier':s,'bills':bills,'open_bills':sum(1 for x in bills if x['status'] not in ('Paid','Cancelled')),'invoiced':sum(float(x['total_amount']) for x in bills if x['status']!='Cancelled'),'paid':sum(float(x['paid_amount']) for x in bills if x['status']!='Cancelled'),'due':sum(float(x['balance_due']) for x in bills if x['status'] not in ('Paid','Cancelled')),'credit':available_credit(s['company_id'],supplier_id)}
    finally:con.close()