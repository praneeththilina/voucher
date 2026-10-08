"""General-ledger statement reconciliation services."""
from __future__ import annotations
import csv, os, tempfile
from datetime import datetime, timedelta
import database as db
TOLERANCE=.005

def rows(r): return [dict(x) for x in r]
def actor():
    u=db.get_current_user() or {}; return u.get('display_name') or u.get('username','System')

def accounts(company_id=None):
    con=db.get_connection()
    try:
        cid=company_id or db.get_active_company_id(con)
        return rows(con.execute("""SELECT r.*,c.account_code,c.account_name,c.account_type,c.normal_balance,
        (SELECT statement_end_date FROM reconciliation_sessions s WHERE s.reconciliation_account_id=r.id AND s.status='Completed' ORDER BY statement_end_date DESC,id DESC LIMIT 1) last_date,
        (SELECT statement_ending_balance FROM reconciliation_sessions s WHERE s.reconciliation_account_id=r.id AND s.status='Completed' ORDER BY statement_end_date DESC,id DESC LIMIT 1) last_balance
        FROM reconciliation_accounts r JOIN chart_of_accounts c ON c.id=r.account_id
        WHERE r.company_id=? AND r.is_active=1 AND c.is_active=1 ORDER BY c.account_code""",(cid,)).fetchall())
    finally: con.close()

def eligible(company_id=None):
    return [a for a in db.get_chart_of_accounts(company_id=company_id) if a['account_type'] in ('Asset','Liability','Equity')]

def configure(account_id,company_id=None,charge_id=None,interest_id=None):
    con=db.get_connection()
    try:
        cid=company_id or db.get_active_company_id(con); a=con.execute('SELECT * FROM chart_of_accounts WHERE id=? AND company_id=?',(account_id,cid)).fetchone()
        if not a: raise ValueError('Ledger account not found.')
        with con:
            con.execute("""INSERT INTO reconciliation_accounts(company_id,account_id,display_name,default_charge_account_id,default_interest_account_id)
            VALUES(?,?,?,?,?) ON CONFLICT(company_id,account_id) DO UPDATE SET default_charge_account_id=excluded.default_charge_account_id,default_interest_account_id=excluded.default_interest_account_id,is_active=1,updated_at=CURRENT_TIMESTAMP""",(cid,account_id,a['account_name'],charge_id,interest_id))
            return con.execute('SELECT id FROM reconciliation_accounts WHERE company_id=? AND account_id=?',(cid,account_id)).fetchone()[0]
    finally: con.close()

def account(rid):
    con=db.get_connection()
    try:
        x=con.execute("SELECT r.*,c.account_code,c.account_name,c.account_type,c.normal_balance FROM reconciliation_accounts r JOIN chart_of_accounts c ON c.id=r.account_id WHERE r.id=?",(rid,)).fetchone(); return dict(x) if x else None
    finally: con.close()

def defaults(rid):
    a=account(rid); con=db.get_connection()
    try:
        p=con.execute("SELECT * FROM reconciliation_sessions WHERE reconciliation_account_id=? AND status='Completed' ORDER BY statement_end_date DESC,id DESC LIMIT 1",(rid,)).fetchone()
        d=con.execute("SELECT * FROM reconciliation_sessions WHERE reconciliation_account_id=? AND status='In Progress' ORDER BY id DESC LIMIT 1",(rid,)).fetchone()
        start=(datetime.strptime(p['statement_end_date'],'%Y-%m-%d').date()+timedelta(days=1)).isoformat() if p else (a.get('opening_date') or datetime.now().strftime('%Y-%m-01'))
        return {'account':a,'prior':dict(p) if p else None,'draft':dict(d) if d else None,'start':start,'end':datetime.now().strftime('%Y-%m-%d'),'beginning':float(p['statement_ending_balance']) if p else float(a.get('opening_balance') or 0),'locked':bool(p)}
    finally: con.close()

def start(rid,start_date,end_date,beginning,ending):
    datetime.strptime(start_date,'%Y-%m-%d'); datetime.strptime(end_date,'%Y-%m-%d')
    if end_date<start_date: raise ValueError('Statement ending date cannot be before its start.')
    con=db.get_connection()
    try:
        a=con.execute('SELECT * FROM reconciliation_accounts WHERE id=?',(rid,)).fetchone(); d=con.execute("SELECT id FROM reconciliation_sessions WHERE reconciliation_account_id=? AND status='In Progress'",(rid,)).fetchone()
        if d:return d[0]
        p=con.execute("SELECT * FROM reconciliation_sessions WHERE reconciliation_account_id=? AND status='Completed' ORDER BY statement_end_date DESC,id DESC LIMIT 1",(rid,)).fetchone()
        if p and abs(float(beginning)-p['statement_ending_balance'])>TOLERANCE: raise ValueError(f"Beginning balance must equal the prior ending balance ({p['statement_ending_balance']:,.2f}). Undo that period to fix it.")
        if p and start_date<=p['statement_end_date']: raise ValueError('Statement period overlaps the previous reconciliation.')
        db.assert_accounting_period_open(a['company_id'],end_date,'start this reconciliation',conn=con)
        with con:
            if not p: con.execute('UPDATE reconciliation_accounts SET opening_balance=?,opening_date=? WHERE id=?',(beginning,start_date,rid))
            return con.execute("INSERT INTO reconciliation_sessions(company_id,reconciliation_account_id,statement_start_date,statement_end_date,beginning_balance,statement_ending_balance,created_by) VALUES(?,?,?,?,?,?,?)",(a['company_id'],rid,start_date,end_date,float(beginning),float(ending),actor())).lastrowid
    finally: con.close()

def session(sid):
    con=db.get_connection()
    try:
        x=con.execute("SELECT s.*,r.account_id,c.account_code,c.account_name,c.normal_balance FROM reconciliation_sessions s JOIN reconciliation_accounts r ON r.id=s.reconciliation_account_id JOIN chart_of_accounts c ON c.id=r.account_id WHERE s.id=?",(sid,)).fetchone(); return dict(x) if x else None
    finally: con.close()

def candidates(sid):
    s=session(sid); con=db.get_connection()
    try:
        out=[]
        q=con.execute("""SELECT l.id line_id,l.entry_id,e.entry_date,e.entry_number,e.reference,COALESCE(NULLIF(l.description,''),e.description) description,l.debit_amount,l.credit_amount,CASE WHEN i.id IS NULL THEN 0 ELSE 1 END cleared
        FROM journal_lines l JOIN journal_entries e ON e.id=l.entry_id LEFT JOIN reconciliation_items i ON i.session_id=? AND i.journal_line_id=l.id
        WHERE l.account_id=? AND e.is_posted=1 AND e.entry_date<=? AND NOT EXISTS(SELECT 1 FROM reconciliation_items oi JOIN reconciliation_sessions os ON os.id=oi.session_id WHERE oi.journal_line_id=l.id AND os.status='Completed' AND os.id!=?) ORDER BY e.entry_date,e.id,l.id""",(sid,s['account_id'],s['statement_end_date'],sid))
        for x in q:
            d=dict(x); amt=float(d['debit_amount'])-float(d['credit_amount']); d['amount']=amt if s['normal_balance']=='Debit' else -amt; d['direction']='Receipt' if d['amount']>=0 else 'Payment'; out.append(d)
        return out
    finally: con.close()

def clear(sid,line_id,value):
    d={x['line_id']:x for x in candidates(sid)}.get(line_id)
    if not d: raise ValueError('Transaction is not available.')
    con=db.get_connection()
    try:
        with con:
            if value: con.execute("INSERT OR REPLACE INTO reconciliation_items(session_id,journal_line_id,journal_entry_id,transaction_date,reference,description,amount,direction) VALUES(?,?,?,?,?,?,?,?)",(sid,line_id,d['entry_id'],d['entry_date'],d['reference'] or d['entry_number'],d['description'],d['amount'],d['direction']))
            else: con.execute('DELETE FROM reconciliation_items WHERE session_id=? AND journal_line_id=?',(sid,line_id))
    finally: con.close()

def clear_all(sid,direction,value):
    for x in candidates(sid):
        if x['direction']==direction and bool(x['cleared'])!=value: clear(sid,x['line_id'],value)

def totals(sid):
    s=session(sid); con=db.get_connection()
    try:
        x=con.execute("SELECT COALESCE(SUM(CASE WHEN amount>=0 THEN amount ELSE 0 END),0) r,COALESCE(SUM(CASE WHEN amount<0 THEN -amount ELSE 0 END),0) p,COALESCE(SUM(amount),0) n,COUNT(*) c FROM reconciliation_items WHERE session_id=?",(sid,)).fetchone(); book=float(s['beginning_balance'])+x['n']; return {'beginning':float(s['beginning_balance']),'receipts':x['r'],'payments':x['p'],'book':book,'statement':float(s['statement_ending_balance']),'difference':float(s['statement_ending_balance'])-book,'count':x['c']}
    finally: con.close()

def post_extra(sid,amount,offset_id,kind,date):
    s=session(sid); amount=abs(float(amount or 0))
    if not amount:return
    if not offset_id:raise ValueError(f'Select the {kind} ledger account.')
    dr,cr=((0,amount),(amount,0)) if kind=='charge' else ((amount,0),(0,amount))
    if s['normal_balance']=='Credit': dr,cr=cr,dr
    con=db.get_connection()
    try:
        jid=db.create_journal_entry({'company_id':s['company_id'],'entry_date':date,'reference':f'RECON-{sid}','description':f'Statement {kind}','entry_type':'Adjustment','source_module':f'reconciliation_{kind}','source_id':sid,'created_by':actor()},[{'account_id':s['account_id'],'debit_amount':dr[0],'credit_amount':dr[1]},{'account_id':offset_id,'debit_amount':cr[0],'credit_amount':cr[1]}],conn=con)
        col='service_charge_journal_id' if kind=='charge' else 'interest_journal_id'
        with con: con.execute(f'UPDATE reconciliation_sessions SET {col}=? WHERE id=?',(jid,sid))
        lid=con.execute('SELECT id FROM journal_lines WHERE entry_id=? AND account_id=?',(jid,s['account_id'])).fetchone()[0]; clear(sid,lid,True)
    finally: con.close()

def finish(sid,adjust=False):
    s=session(sid); t=totals(sid); diff=t['difference']; con=db.get_connection()
    try:
        db.assert_accounting_period_open(s['company_id'],s['statement_end_date'],'finish this reconciliation',conn=con); jid=None
        if abs(diff)>TOLERANCE:
            if not adjust: raise ValueError(f'Reconciliation is out by {diff:,.2f}. Review cleared entries first.')
            positive=diff>0; code='4995' if positive else '5995'; off=con.execute('SELECT id FROM chart_of_accounts WHERE company_id=? AND account_code=?',(s['company_id'],code)).fetchone()
            if not off: off=(db.create_account({'company_id':s['company_id'],'account_code':code,'account_name':'Reconciliation Gain' if positive else 'Reconciliation Discrepancies','account_type':'Income' if positive else 'Expense'},conn=con),)
            amt=abs(diff); ld,lc=((amt,0) if positive else (0,amt));
            if s['normal_balance']=='Credit':ld,lc=lc,ld
            jid=db.create_journal_entry({'company_id':s['company_id'],'entry_date':s['statement_end_date'],'reference':f'RECON-{sid}','description':'Confirmed reconciliation difference','entry_type':'Adjustment','source_module':'reconciliation_discrepancy','source_id':sid,'created_by':actor()},[{'account_id':s['account_id'],'debit_amount':ld,'credit_amount':lc},{'account_id':off[0],'debit_amount':lc,'credit_amount':ld}],conn=con)
            lid=con.execute('SELECT id FROM journal_lines WHERE entry_id=? AND account_id=?',(jid,s['account_id'])).fetchone()[0]; clear(sid,lid,True); t=totals(sid)
        with con: con.execute("UPDATE reconciliation_sessions SET cleared_receipts=?,cleared_payments=?,book_ending_balance=?,discrepancy_amount=?,discrepancy_journal_id=?,status='Completed',completed_by=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",(t['receipts'],t['payments'],t['book'],diff,jid,actor(),sid))
    finally: con.close()

def history(rid):
    con=db.get_connection()
    try:return rows(con.execute('SELECT * FROM reconciliation_sessions WHERE reconciliation_account_id=? ORDER BY statement_end_date DESC,id DESC',(rid,)).fetchall())
    finally:con.close()

def undo(sid,reason=''):
    s=session(sid); u=db.get_current_user() or {}
    if u.get('role') not in ('admin','accountant'):raise PermissionError('Only an administrator or accountant can undo reconciliations.')
    con=db.get_connection()
    try:
        affected=con.execute("SELECT * FROM reconciliation_sessions WHERE reconciliation_account_id=? AND status='Completed' AND (statement_end_date>? OR (statement_end_date=? AND id>=?)) ORDER BY statement_end_date DESC,id DESC",(s['reconciliation_account_id'],s['statement_end_date'],s['statement_end_date'],sid)).fetchall()
        with con:
            for x in affected:
                db.assert_accounting_period_open(x['company_id'],x['statement_end_date'],'undo this reconciliation',conn=con)
                for col in ('discrepancy_journal_id','service_charge_journal_id','interest_journal_id'):
                    if x[col]:con.execute('DELETE FROM journal_entries WHERE id=?',(x[col],))
                con.execute("UPDATE reconciliation_sessions SET status='Undone',undone_by=?,undone_at=CURRENT_TIMESTAMP,undo_reason=? WHERE id=?",(actor(),reason,x['id']))
        return len(affected)
    finally:con.close()

def import_csv(rid,path):
    a=account(rid); m=db._auto_detect_csv_columns(path); ok=bad=0; batch=f'recon_{datetime.now():%Y%m%d_%H%M%S}'; con=db.get_connection()
    try:
        with open(path,encoding='utf-8-sig',newline='') as f:
            it=csv.reader(f);next(it,None)
            with con:
                for row in it:
                    try:
                        v=lambda k,d='':row[m.get(k,-1)].strip() if 0<=m.get(k,-1)<len(row) else d; date=db._normalize_date(v('transaction_date'))
                        con.execute('INSERT INTO reconciliation_statement_lines(company_id,reconciliation_account_id,transaction_date,description,reference,debit_amount,credit_amount,balance,import_batch_id) VALUES(?,?,?,?,?,?,?,?,?)',(a['company_id'],rid,date,v('description'),v('reference'),db._parse_amount(v('debit_amount','0')),db._parse_amount(v('credit_amount','0')),db._parse_amount(v('balance')) if v('balance') else None,batch));ok+=1
                    except Exception:bad+=1
    finally:con.close()
    return ok,bad,batch


def auto_clear_imported(sid):
    """Check unique ledger matches for imported statement rows by amount/date."""
    s=session(sid); con=db.get_connection(); matched=0; used=set()
    try:
        lines=rows(con.execute("SELECT * FROM reconciliation_statement_lines WHERE reconciliation_account_id=? AND transaction_date BETWEEN ? AND ? AND matched_journal_line_id IS NULL",(s['reconciliation_account_id'],s['statement_start_date'],s['statement_end_date'])).fetchall())
        available=[x for x in candidates(sid) if not x['cleared']]
        for line in lines:
            amount=float(line['credit_amount'] or 0)-float(line['debit_amount'] or 0)
            if s['normal_balance']=='Credit':amount=-amount
            day=datetime.strptime(line['transaction_date'],'%Y-%m-%d').date()
            found=[x for x in available if x['line_id'] not in used and abs(x['amount']-amount)<=TOLERANCE and abs((datetime.strptime(x['entry_date'],'%Y-%m-%d').date()-day).days)<=3]
            if len(found)==1:
                x=found[0];clear(sid,x['line_id'],True)
                with con:con.execute("UPDATE reconciliation_statement_lines SET matched_journal_line_id=?,match_status='Matched' WHERE id=?",(x['line_id'],line['id']))
                used.add(x['line_id']);matched+=1
        return matched
    finally:con.close()
def report(sid):
    s=session(sid); con=db.get_connection()
    try:return s,totals(sid),rows(con.execute('SELECT * FROM reconciliation_items WHERE session_id=? ORDER BY transaction_date,id',(sid,)).fetchall())
    finally:con.close()

def export_csv(sid,path,detail=True):
    s,t,items=report(sid)
    with open(path,'w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerows([['RECONCILIATION REPORT'],['Account',f"{s['account_code']} - {s['account_name']}"],['Period',s['statement_start_date'],s['statement_end_date']],['Status',s['status']],[],['Beginning',t['beginning']],['Receipts',t['receipts']],['Payments',t['payments']],['Cleared ending',t['book']],['Statement ending',t['statement']],['Difference',t['difference']]])
        if detail:
            w.writerow([]);w.writerow(['Date','Type','Reference','Description','Amount'])
            for x in items:w.writerow(db._sanitize_csv_row([x['transaction_date'],x['direction'],x['reference'],x['description'],x['amount']]))
    return path

def export_pdf(sid,detail=True):
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.lib import colors
    s,t,items=report(sid); path=os.path.join(tempfile.gettempdir(),f"reconciliation_{sid}_{'detail' if detail else 'summary'}.pdf"); styles=getSampleStyleSheet(); story=[Paragraph('Reconciliation Report',styles['Title']),Paragraph(f"{s['account_code']} - {s['account_name']}",styles['Heading2']),Paragraph(f"{s['statement_start_date']} to {s['statement_end_date']} | {s['status']}",styles['Normal']),Spacer(1,10)]; data=[['Beginning','Receipts','Payments','Cleared ending','Statement ending','Difference'],[f"{t['beginning']:,.2f}",f"{t['receipts']:,.2f}",f"{t['payments']:,.2f}",f"{t['book']:,.2f}",f"{t['statement']:,.2f}",f"{t['difference']:,.2f}"]]; tab=Table(data,repeatRows=1);tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0f766e')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.5,colors.grey),('ALIGN',(0,0),(-1,-1),'RIGHT')]));story += [tab,Spacer(1,12)]
    if detail:
        data=[['Date','Type','Reference','Description','Amount']]+[[x['transaction_date'],x['direction'],x['reference'],x['description'],f"{x['amount']:,.2f}"] for x in items]; story.append(Table(data,repeatRows=1,colWidths=[70,70,90,330,80]))
    SimpleDocTemplate(path,pagesize=landscape(A4) if detail else A4).build(story);return path