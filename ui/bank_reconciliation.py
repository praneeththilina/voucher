"""QuickBooks-style general-ledger statement reconciliation UI."""
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import ttkbootstrap as ttk
import database as db
import reconciliation_service as svc
from ui.pdf_viewer import PdfViewerDialog

BG='#f4f6f8'; NAVY='#172033'; GREEN='#2c8b74'; RED='#c65353'; BLUE='#2878b5'

def money(v): return f"LKR {float(v or 0):,.2f}"
def current_actor():
    u=db.get_current_user() or {}; return u.get('display_name') or u.get('username','System')

class BankReconciliationDialog(tk.Toplevel):
    """Full-window statement reconciliation centre."""
    def __init__(self,parent):
        super().__init__(parent); self.withdraw(); self.title('Reconciliation Centre'); self.state('zoomed'); self.minsize(1050,650); self.transient(parent)
        self.company_id=db.get_active_company_id(); self.rid=None; self.sid=None; self._map={}; self.configure(bg=BG); self._home(); self.deiconify(); self.lift(); self.focus_force(); self.bind('<Escape>',lambda e:self.destroy())
    def wipe(self):
        for w in self.winfo_children():w.destroy()
    def header(self,title,subtitle):
        h=tk.Frame(self,bg=NAVY,padx=24,pady=16);h.pack(fill='x');tk.Label(h,text=title,font=('Segoe UI',18,'bold'),bg=NAVY,fg='white').pack(anchor='w');tk.Label(h,text=subtitle,font=('Segoe UI',9),bg=NAVY,fg='#b8c4d8').pack(anchor='w',pady=(3,0));ttk.Button(h,text='Close',command=self.destroy,bootstyle='light-outline').place(relx=1,rely=.5,anchor='e')
    def _home(self):
        self.wipe();self.header('Reconciliation Centre','Reconcile any statement-backed ledger, review history, and export audit reports.')
        bar=ttk.Frame(self,padding=14);bar.pack(fill='x');ttk.Label(bar,text='Account',font=('Segoe UI',10,'bold')).pack(side='left');self.accvar=tk.StringVar();self.combo=ttk.Combobox(bar,textvariable=self.accvar,state='readonly',width=43);self.combo.pack(side='left',padx=8);self.combo.bind('<<ComboboxSelected>>',lambda e:self.refresh_home())
        ttk.Button(bar,text='+ Configure ledger',command=self.manage,bootstyle='secondary-outline').pack(side='left',padx=4);ttk.Button(bar,text='Import statement CSV',command=self.import_statement,bootstyle='info-outline').pack(side='left',padx=4);ttk.Button(bar,text='History & reports',command=self.history,bootstyle='secondary-outline').pack(side='right');ttk.Button(bar,text='Start / resume reconciliation',command=self.setup,bootstyle='success').pack(side='right',padx=6)
        self.cards=tk.Frame(self,bg=BG);self.cards.pack(fill='x',padx=18,pady=10);self.card_labels={}
        for key,title,color in [('last','Last reconciled',BLUE),('balance','Last statement balance',GREEN),('draft','Work in progress','#c17b1d'),('periods','Completed periods',NAVY)]:
            f=tk.Frame(self.cards,bg='white',highlightbackground='#d8dee8',highlightthickness=1,padx=16,pady=13);f.pack(side='left',fill='x',expand=True,padx=5);tk.Label(f,text=title,bg='white',fg='#667085').pack(anchor='w');v=tk.Label(f,text='--',font=('Segoe UI',14,'bold'),bg='white',fg=color);v.pack(anchor='w',pady=(7,0));self.card_labels[key]=v
        info=tk.LabelFrame(self,text='How this works',bg='white',fg=NAVY,padx=18,pady=16);info.pack(fill='both',expand=True,padx=23,pady=10);tk.Label(info,text='1   Choose any configured balance-sheet ledger with a bank, card, cash, or other external statement.\n\n2   First use records the opening balance. Later periods automatically carry the previous statement ending balance.\n\n3   Tick deposits and receipts on the left; tick payments and charges on the right. The difference updates immediately.\n\n4   Finish only at zero difference. A balancing discrepancy journal is available only after explicit confirmation.\n\n5   History keeps summary and detailed reports. Undo reverses the selected period and all later periods.',justify='left',anchor='nw',font=('Segoe UI',11),bg='white',fg='#344054').pack(fill='both',expand=True)
        self.load_accounts()
    def load_accounts(self):
        acc=svc.accounts(self.company_id);self._map={f"{a['account_code']} - {a['account_name']}":a['id'] for a in acc};self.combo['values']=list(self._map)
        if self._map:self.combo.current(0);self.rid=self._map[self.combo.get()];self.refresh_home()
        else:self.combo.set('No reconciliable ledgers configured');self.refresh_home()
    def refresh_home(self):
        self.rid=self._map.get(self.accvar.get());hist=svc.history(self.rid) if self.rid else [];done=[x for x in hist if x['status']=='Completed'];draft=[x for x in hist if x['status']=='In Progress'];last=done[0] if done else None
        self.card_labels['last'].config(text=last['statement_end_date'] if last else 'Not reconciled');self.card_labels['balance'].config(text=money(last['statement_ending_balance']) if last else '--');self.card_labels['draft'].config(text='Resume available' if draft else 'None');self.card_labels['periods'].config(text=str(len(done)))
    def manage(self):
        dlg=LedgerSetupDialog(self,self.company_id);self.wait_window(dlg);self.load_accounts()
    def import_statement(self):
        if not self.rid:return messagebox.showwarning('Configure ledger','Configure and select a ledger first.',parent=self)
        p=filedialog.askopenfilename(parent=self,title='Import statement CSV',filetypes=[('CSV','*.csv')])
        if p:
            try:
                ok,bad,_=svc.import_csv(self.rid,p);messagebox.showinfo('Statement imported',f'Imported {ok} statement rows.\nSkipped {bad} invalid rows.',parent=self)
            except Exception as e:messagebox.showerror('Import failed',str(e),parent=self)
    def setup(self):
        if not self.rid:return messagebox.showwarning('Configure ledger','Configure and select a ledger first.',parent=self)
        d=svc.defaults(self.rid)
        if d['draft']:self.open_session(d['draft']['id']);return
        dlg=StartDialog(self,d);self.wait_window(dlg)
        if dlg.result:self.open_session(dlg.result)
    def open_session(self,sid):self.sid=sid;self._reconcile()
    def _reconcile(self):
        self.wipe();s=svc.session(self.sid);self.header(f"Reconcile {s['account_code']} - {s['account_name']}",f"Statement {s['statement_start_date']} to {s['statement_end_date']} | Double-click a row to check or uncheck it.")
        self.summary=tk.Frame(self,bg=BG);self.summary.pack(fill='x',padx=16,pady=9);self.sumlabels={}
        for key,title,color in [('beginning','Beginning',NAVY),('receipts','Checked receipts',GREEN),('payments','Checked payments',RED),('book','Cleared balance',BLUE),('statement','Statement ending',NAVY),('difference','Difference',RED)]:
            f=tk.Frame(self.summary,bg='white',highlightbackground='#d8dee8',highlightthickness=1,padx=10,pady=8);f.pack(side='left',fill='x',expand=True,padx=3);tk.Label(f,text=title,bg='white',fg='#667085',font=('Segoe UI',8)).pack(anchor='w');v=tk.Label(f,text='0.00',bg='white',fg=color,font=('Segoe UI',11,'bold'));v.pack(anchor='w');self.sumlabels[key]=v
        actions=ttk.Frame(self,padding=(17,3));actions.pack(fill='x');ttk.Button(actions,text='Import CSV',command=self.import_statement,bootstyle='info-outline').pack(side='left');ttk.Button(actions,text='Auto-check imported matches',command=self.auto_check,bootstyle='info').pack(side='left',padx=5);ttk.Button(actions,text='Add charge / interest',command=self.extra,bootstyle='warning-outline').pack(side='left',padx=5);ttk.Button(actions,text='Back to centre',command=self._home,bootstyle='secondary-outline').pack(side='right')
        panes=ttk.Panedwindow(self,orient='horizontal');panes.pack(fill='both',expand=True,padx=16,pady=8);self.trees={}
        for direction,title,color in [('Receipt','RECEIPTS / DEPOSITS',GREEN),('Payment','PAYMENTS / CHARGES',RED)]:
            f=ttk.LabelFrame(panes,text=title,padding=6);panes.add(f,weight=1);b=ttk.Frame(f);b.pack(fill='x');ttk.Button(b,text='Check all',command=lambda d=direction:self.all(d,True),bootstyle='success-outline').pack(side='left');ttk.Button(b,text='Uncheck all',command=lambda d=direction:self.all(d,False),bootstyle='secondary-outline').pack(side='left',padx=4)
            tree=ttk.Treeview(f,columns=('check','date','ref','desc','amount'),show='headings');self.trees[direction]=tree
            for c,h,w in [('check','Clear',48),('date','Date',85),('ref','Reference',95),('desc','Description',240),('amount','Amount',105)]:tree.heading(c,text=h);tree.column(c,width=w,anchor='e' if c=='amount' else 'w')
            sb=ttk.Scrollbar(f,command=tree.yview);tree.configure(yscrollcommand=sb.set);tree.pack(side='left',fill='both',expand=True,pady=5);sb.pack(side='right',fill='y');tree.bind('<Double-1>',lambda e,d=direction:self.toggle(d))
        foot=ttk.Frame(self,padding=14);foot.pack(fill='x');ttk.Button(foot,text='Finish now',command=lambda:self.finish(False),bootstyle='success').pack(side='right');ttk.Button(foot,text='Finish with adjustment',command=lambda:self.finish(True),bootstyle='danger-outline').pack(side='right',padx=7);ttk.Button(foot,text='Save for later',command=self._home,bootstyle='secondary').pack(side='left');self.refresh_lines()
    def refresh_lines(self):
        for t in self.trees.values():t.delete(*t.get_children())
        for x in svc.candidates(self.sid):self.trees[x['direction']].insert('', 'end',iid=str(x['line_id']),values=('Yes' if x['cleared'] else '',x['entry_date'],x['reference'] or x['entry_number'],x['description'],f"{abs(x['amount']):,.2f}"),tags=('on',) if x['cleared'] else ())
        for t in self.trees.values():t.tag_configure('on',background='#ddf4ea',foreground='#145c49')
        t=svc.totals(self.sid)
        for k in self.sumlabels:self.sumlabels[k].config(text=money(t[k]))
        self.sumlabels['difference'].config(fg=GREEN if abs(t['difference'])<=svc.TOLERANCE else RED)
    def toggle(self,direction):
        tr=self.trees[direction];sel=tr.selection()
        if sel:svc.clear(self.sid,int(sel[0]),tr.set(sel[0],'check')!='Yes');self.refresh_lines()
    def all(self,direction,value):svc.clear_all(self.sid,direction,value);self.refresh_lines()
    def auto_check(self):
        n=svc.auto_clear_imported(self.sid);self.refresh_lines();messagebox.showinfo('Statement matching',f'{n} unique ledger transaction(s) were checked. Ambiguous rows were left for review.',parent=self)
    def extra(self):
        dlg=ExtraDialog(self,self.sid);self.wait_window(dlg);self.refresh_lines()
    def finish(self,adjust):
        t=svc.totals(self.sid)
        if adjust and abs(t['difference'])>svc.TOLERANCE and not messagebox.askyesno('Post discrepancy adjustment',f"Difference is {money(t['difference'])}.\n\nPost a system balancing journal and finish? Use this only after reviewing the statement.",parent=self):return
        try:svc.finish(self.sid,adjust);messagebox.showinfo('Reconciled','The statement period is reconciled and its report snapshot is saved.',parent=self);self._home()
        except Exception as e:messagebox.showerror('Cannot finish',str(e),parent=self)
    def history(self):
        if not self.rid:return
        dlg=HistoryDialog(self,self.rid);self.wait_window(dlg);self.refresh_home()

class StartDialog(tk.Toplevel):
    def __init__(self,parent,d):
        super().__init__(parent);self.result=None;self.d=d;self.title('Start reconciliation');self.geometry('620x570');self.transient(parent);self.grab_set();a=d['account'];ttk.Label(self,text=f"{a['account_code']} - {a['account_name']}",font=('Segoe UI',16,'bold')).pack(anchor='w',padx=22,pady=(20,3));ttk.Label(self,text='Enter the dates and balances exactly as shown on the statement.').pack(anchor='w',padx=22)
        f=ttk.LabelFrame(self,text='Statement',padding=15);f.pack(fill='x',padx=22,pady=15);self.v={}
        fields=[('start','Starting date',d['start']),('end','Closing date',d['end']),('beginning','Beginning balance',f"{d['beginning']:.2f}"),('ending','Statement closing balance','0.00')]
        for i,(k,label,val) in enumerate(fields):ttk.Label(f,text=label).grid(row=i,column=0,sticky='w',pady=6);v=tk.StringVar(value=val);self.v[k]=v;e=ttk.Entry(f,textvariable=v,width=28);e.grid(row=i,column=1,sticky='ew',padx=10);e.configure(state='readonly' if k=='beginning' and d['locked'] else 'normal')
        note='First reconciliation: enter the statement opening balance.' if not d['locked'] else 'Beginning balance is carried from the previous completed statement.';ttk.Label(self,text=note,bootstyle='info',wraplength=540).pack(anchor='w',padx=22)
        b=ttk.Frame(self,padding=22);b.pack(fill='x',side='bottom');ttk.Button(b,text='Continue',command=self.go,bootstyle='success').pack(side='right');ttk.Button(b,text='Cancel',command=self.destroy).pack(side='right',padx=8)
    def go(self):
        try:self.result=svc.start(self.d['account']['id'],self.v['start'].get(),self.v['end'].get(),float(self.v['beginning'].get().replace(',','')),float(self.v['ending'].get().replace(',','')));self.destroy()
        except Exception as e:messagebox.showerror('Cannot start',str(e),parent=self)

class LedgerSetupDialog(tk.Toplevel):
    def __init__(self,parent,cid):
        super().__init__(parent);self.cid=cid;self.title('Configure reconciliable ledgers');self.geometry('760x530');self.transient(parent);self.grab_set();ttk.Label(self,text='Reconciliable ledger accounts',font=('Segoe UI',15,'bold')).pack(anchor='w',padx=18,pady=(16,3));ttk.Label(self,text='Choose any balance-sheet ledger that has an external statement or report.').pack(anchor='w',padx=18);self.tree=ttk.Treeview(self,columns=('code','name','type','status'),show='headings');
        for c,h,w in [('code','Code',90),('name','Ledger account',300),('type','Type',120),('status','Configured',100)]:self.tree.heading(c,text=h);self.tree.column(c,width=w)
        self.tree.pack(fill='both',expand=True,padx=18,pady=12);b=ttk.Frame(self,padding=18);b.pack(fill='x');ttk.Button(b,text='Enable selected ledger',command=self.enable,bootstyle='success').pack(side='left');ttk.Button(b,text='Done',command=self.destroy).pack(side='right');self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children());done={x['account_id'] for x in svc.accounts(self.cid,)}
        for a in svc.eligible(self.cid):self.tree.insert('','end',iid=str(a['id']),values=(a['account_code'],a['account_name'],a['account_type'],'Yes' if a['id'] in done else ''))
    def enable(self):
        if not self.tree.selection():return
        svc.configure(int(self.tree.selection()[0]),self.cid);self.refresh()

class ExtraDialog(tk.Toplevel):
    def __init__(self,parent,sid):
        super().__init__(parent);self.sid=sid;self.title('Statement charge or interest');self.geometry('560x350');self.transient(parent);self.grab_set();self.kind=tk.StringVar(value='charge');self.amount=tk.StringVar(value='0.00');self.date=tk.StringVar(value=svc.session(sid)['statement_end_date']);acc=[a for a in db.get_chart_of_accounts() if a['account_type'] in ('Expense','Income')];self.map={f"{a['account_code']} - {a['account_name']}":a['id'] for a in acc};self.acct=tk.StringVar();f=ttk.Frame(self,padding=22);f.pack(fill='both',expand=True);ttk.Label(f,text='Add statement-only entry',font=('Segoe UI',15,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,15));ttk.Label(f,text='Type').grid(row=1,column=0,sticky='w',pady=6);ttk.Combobox(f,textvariable=self.kind,values=['charge','interest'],state='readonly').grid(row=1,column=1);ttk.Label(f,text='Amount').grid(row=2,column=0,sticky='w',pady=6);ttk.Entry(f,textvariable=self.amount).grid(row=2,column=1);ttk.Label(f,text='Date').grid(row=3,column=0,sticky='w',pady=6);ttk.Entry(f,textvariable=self.date).grid(row=3,column=1);ttk.Label(f,text='Linked ledger').grid(row=4,column=0,sticky='w',pady=6);ttk.Combobox(f,textvariable=self.acct,values=list(self.map),state='readonly',width=35).grid(row=4,column=1);ttk.Button(f,text='Post and check',command=self.go,bootstyle='success').grid(row=5,column=1,sticky='e',pady=18)
    def go(self):
        try:svc.post_extra(self.sid,self.amount.get(),self.map.get(self.acct.get()),self.kind.get(),self.date.get());self.destroy()
        except Exception as e:messagebox.showerror('Cannot post',str(e),parent=self)

class HistoryDialog(tk.Toplevel):
    def __init__(self,parent,rid):
        super().__init__(parent);self.rid=rid;self.title('Reconciliation history and reports');self.geometry('1050x650');self.transient(parent);self.grab_set();ttk.Label(self,text='Reconciliation history',font=('Segoe UI',17,'bold')).pack(anchor='w',padx=18,pady=(15,5));self.tree=ttk.Treeview(self,columns=('period','begin','end','difference','status','by'),show='headings');
        for c,h,w in [('period','Statement period',220),('begin','Beginning',130),('end','Ending',130),('difference','Adjustment',120),('status','Status',100),('by','Completed by',140)]:self.tree.heading(c,text=h);self.tree.column(c,width=w,anchor='e' if c in ('begin','end','difference') else 'w')
        self.tree.pack(fill='both',expand=True,padx=18,pady=10);b=ttk.Frame(self,padding=18);b.pack(fill='x');ttk.Button(b,text='Summary PDF / Print',command=lambda:self.pdf(False),bootstyle='info-outline').pack(side='left');ttk.Button(b,text='Detailed PDF / Print',command=lambda:self.pdf(True),bootstyle='info').pack(side='left',padx=5);ttk.Button(b,text='Export CSV',command=self.csv,bootstyle='secondary-outline').pack(side='left');ttk.Button(b,text='Undo selected',command=self.undo,bootstyle='danger-outline').pack(side='right');self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for x in svc.history(self.rid):self.tree.insert('','end',iid=str(x['id']),values=(f"{x['statement_start_date']} to {x['statement_end_date']}",f"{x['beginning_balance']:,.2f}",f"{x['statement_ending_balance']:,.2f}",f"{x['discrepancy_amount']:,.2f}",x['status'],x['completed_by']))
    def selected(self):return int(self.tree.selection()[0]) if self.tree.selection() else None
    def pdf(self,detail):
        if self.selected():PdfViewerDialog(self,svc.export_pdf(self.selected(),detail),title='Detailed Reconciliation Report' if detail else 'Reconciliation Summary')
    def csv(self):
        sid=self.selected()
        if not sid:return
        p=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',filetypes=[('CSV','*.csv')]);
        if p:svc.export_csv(sid,p,True);messagebox.showinfo('Exported',f'Report saved to:\n{p}',parent=self)
    def undo(self):
        sid=self.selected()
        if not sid:return
        reason=simpledialog.askstring('Undo reconciliation','Reason for undo:',parent=self)
        if reason is None:return
        if not messagebox.askyesno('Undo reconciliation','This period and every later completed period will be undone. System-created charge, interest, and discrepancy journals will be removed. Continue?',parent=self):return
        try:n=svc.undo(sid,reason);messagebox.showinfo('Reconciliation undone',f'{n} period(s) were undone.',parent=self);self.refresh()
        except Exception as e:messagebox.showerror('Cannot undo',str(e),parent=self)

BankAccountManagerDialog=LedgerSetupDialog