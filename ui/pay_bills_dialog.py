"""QuickBooks-style Pay Bills and vendor credit screens."""
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import database as db
import vendor_payments as vp

class VendorCreditDialog(tb.Toplevel):
    def __init__(self,parent,company_id=None,supplier_id=None,on_saved=None):
        super().__init__(parent);self.company_id=company_id or db.get_active_company_id();self.on_saved=on_saved;self.title('New Vendor Credit');self.geometry('620x480');self.transient(parent);self.grab_set();self.suppliers=db.get_suppliers(self.company_id,active_only=True);self.smap={x['name']:x['id'] for x in self.suppliers};self.accounts=[x for x in db.get_chart_of_accounts(self.company_id) if x['account_type'] in ('Expense','Asset')];self.amap={f"{x['account_code']} - {x['account_name']}":x['id'] for x in self.accounts};self.v={k:tk.StringVar() for k in ('supplier','number','date','amount','account','reference','notes')};self.v['date'].set(datetime.now().strftime('%Y-%m-%d'))
        if supplier_id:
            for n,i in self.smap.items():
                if i==supplier_id:self.v['supplier'].set(n)
        f=tb.Frame(self,padding=24);f.pack(fill=BOTH,expand=True);tb.Label(f,text='Vendor Credit',font=('Segoe UI',17,'bold')).grid(row=0,column=0,columnspan=2,sticky=W,pady=(0,4));tb.Label(f,text='Record a purchase return or credit memo, then apply it in Pay Bills.',bootstyle='secondary').grid(row=1,column=0,columnspan=2,sticky=W,pady=(0,16))
        fields=[('supplier','Vendor',list(self.smap)),('number','Credit no.',None),('date','Credit date',None),('amount','Amount',None),('account','Expense / item ledger reversed',list(self.amap)),('reference','Reference',None),('notes','Memo',None)]
        for r,(k,label,values) in enumerate(fields,2):tb.Label(f,text=label).grid(row=r,column=0,sticky=W,pady=6);w=tb.Combobox(f,textvariable=self.v[k],values=values,state='readonly',width=38) if values is not None else tb.Entry(f,textvariable=self.v[k],width=40);w.grid(row=r,column=1,sticky=EW,padx=(12,0),pady=6)
        f.columnconfigure(1,weight=1);b=tb.Frame(f);b.grid(row=10,column=0,columnspan=2,sticky=EW,pady=18);tb.Button(b,text='Save vendor credit',command=self.save,bootstyle='success').pack(side=RIGHT);tb.Button(b,text='Cancel',command=self.destroy).pack(side=RIGHT,padx=8)
    def save(self):
        try:
            if not self.smap.get(self.v['supplier'].get()):raise ValueError('Select a vendor.')
            if not self.v['number'].get().strip():raise ValueError('Credit number is required.')
            vp.create_credit({'company_id':self.company_id,'supplier_id':self.smap[self.v['supplier'].get()],'credit_number':self.v['number'].get(),'credit_date':self.v['date'].get(),'amount':float(self.v['amount'].get().replace(',','')),'expense_account_id':self.amap.get(self.v['account'].get()),'reference':self.v['reference'].get(),'notes':self.v['notes'].get()});
            if self.on_saved:self.on_saved()
            self.destroy()
        except Exception as e:messagebox.showerror('Cannot save credit',str(e),parent=self)

class PayBillsDialog(tb.Toplevel):
    def __init__(self,parent,company_id=None,initial_supplier_id=None,on_saved=None):
        super().__init__(parent);self.company_id=company_id or db.get_active_company_id();self.on_saved=on_saved;self.title('Pay Bills');self.state('zoomed');self.minsize(1050,650);self.transient(parent);self.suppliers=db.get_suppliers(self.company_id,active_only=False);self.smap={'All vendors':None}|{x['name']:x['id'] for x in self.suppliers};self.cash=vp.cash_accounts(self.company_id);self.cmap={f"{x['account_code']} - {x['account_name']}":x['id'] for x in self.cash};self.selected={};self.vendor=tk.StringVar(value='All vendors');self.start=tk.StringVar();self.end=tk.StringVar();self.method=tk.StringVar(value='Cheque');self.account=tk.StringVar(value=next(iter(self.cmap),'') );self.date=tk.StringVar(value=datetime.now().strftime('%Y-%m-%d'));self.check=tk.StringVar();self.print_later=tk.BooleanVar(value=False);self.reference=tk.StringVar();self.credit_label=tk.StringVar(value='Available credit: LKR 0.00');self.total_label=tk.StringVar(value='Cash to pay: LKR 0.00 | Credits applied: LKR 0.00')
        if initial_supplier_id:
            for n,i in self.smap.items():
                if i==initial_supplier_id:self.vendor.set(n)
        self.build();self.refresh()
    def build(self):
        head=tk.Frame(self,bg='#172033',padx=22,pady=14);head.pack(fill=X);tk.Label(head,text='Pay Bills',font=('Segoe UI',19,'bold'),bg='#172033',fg='white').pack(anchor=W);tk.Label(head,text='Select open bills for one vendor, apply available credits, then pay the remaining balance.',bg='#172033',fg='#bdc8d9').pack(anchor=W)
        filters=tb.Labelframe(self,text='Show bills',padding=10);filters.pack(fill=X,padx=16,pady=10);tb.Label(filters,text='Vendor').pack(side=LEFT);c=tb.Combobox(filters,textvariable=self.vendor,values=list(self.smap),state='readonly',width=27);c.pack(side=LEFT,padx=6);c.bind('<<ComboboxSelected>>',lambda e:self.refresh());tb.Label(filters,text='From').pack(side=LEFT);tb.Entry(filters,textvariable=self.start,width=12).pack(side=LEFT,padx=5);tb.Label(filters,text='To').pack(side=LEFT);tb.Entry(filters,textvariable=self.end,width=12).pack(side=LEFT,padx=5);tb.Button(filters,text='Apply filter',command=self.refresh,bootstyle='info-outline').pack(side=LEFT,padx=6);tb.Button(filters,text='Select all',command=lambda:self.select_all(True),bootstyle='success-outline').pack(side=RIGHT);tb.Button(filters,text='Clear',command=lambda:self.select_all(False),bootstyle='secondary-outline').pack(side=RIGHT,padx=5)
        cols=('pick','vendor','date','due','number','original','open','credit','pay');self.tree=tb.Treeview(self,columns=cols,show='headings',selectmode='browse')
        for k,h,w in [('pick','Pay',48),('vendor','Vendor',190),('date','Bill date',88),('due','Due date',88),('number','Bill no.',110),('original','Original',105),('open','Open balance',115),('credit','Credit applied',110),('pay','Amount to pay',115)]:self.tree.heading(k,text=h);self.tree.column(k,width=w,anchor=E if k in ('original','open','credit','pay') else W)
        sb=tb.Scrollbar(self,command=self.tree.yview);self.tree.configure(yscrollcommand=sb.set);self.tree.pack(side=LEFT,fill=BOTH,expand=True,padx=(16,0),pady=5);sb.pack(side=LEFT,fill=Y,pady=5);self.tree.bind('<Double-1>',self.toggle)
        side=tb.Frame(self,padding=16,width=330);side.pack(side=RIGHT,fill=Y);tb.Label(side,text='Payment details',font=('Segoe UI',14,'bold')).pack(anchor=W);tb.Label(side,textvariable=self.credit_label,bootstyle='info').pack(anchor=W,pady=(5,14));
        for label,var,values in [('Payment date',self.date,None),('Method',self.method,['Cheque','Cash','Bank Transfer','EFT','Online/Other']),('Cash / bank account',self.account,list(self.cmap)),('Check number',self.check,None),('Reference',self.reference,None)]:tb.Label(side,text=label).pack(anchor=W,pady=(7,2));w=tb.Combobox(side,textvariable=var,values=values,state='readonly',width=34) if values else tb.Entry(side,textvariable=var,width=36);w.pack(fill=X)
        tb.Checkbutton(side,text='Print later (assign check number later)',variable=self.print_later,bootstyle='round-toggle').pack(anchor=W,pady=12);tb.Separator(side).pack(fill=X,pady=8);tb.Label(side,textvariable=self.total_label,font=('Segoe UI',11,'bold'),wraplength=300).pack(anchor=W,pady=8);tb.Button(side,text='Pay selected bills',command=self.pay,bootstyle='success').pack(fill=X,pady=8);tb.Button(side,text='New vendor credit',command=self.new_credit,bootstyle='warning-outline').pack(fill=X);tb.Button(side,text='Close',command=self.destroy).pack(fill=X,pady=8)
    def refresh(self):
        supplier=self.smap.get(self.vendor.get());self.bills=[x for x in vp.open_bills(self.company_id,supplier,self.start.get() or None,self.end.get() or None) if x['status'] not in ('Paid','Cancelled')];valid={x['id'] for x in self.bills};self.selected={k:v for k,v in self.selected.items() if k in valid};self.redraw()
    def redraw(self):
        self.tree.delete(*self.tree.get_children())
        for x in self.bills:
            a=self.selected.get(x['id'],{'credit':0,'cash':0});self.tree.insert('',END,iid=str(x['id']),values=('Yes' if x['id'] in self.selected else '',x['supplier_name'],x['invoice_date'],x['due_date'],x['invoice_number'],f"{x['total_amount']:,.2f}",f"{x['balance_due']:,.2f}",f"{a['credit']:,.2f}",f"{a['cash']:,.2f}"),tags=('selected',) if x['id'] in self.selected else ());self.tree.tag_configure('selected',background='#dcf3e9')
        sid=self.single_vendor();available=vp.available_credit(self.company_id,sid) if sid else 0;self.credit_label.set(f'Available credit: LKR {available:,.2f}');self.total_label.set(f"Cash to pay: LKR {sum(x['cash'] for x in self.selected.values()):,.2f}\nCredits applied: LKR {sum(x['credit'] for x in self.selected.values()):,.2f}")
    def single_vendor(self):
        ids={x['supplier_id'] for x in self.bills if x['id'] in self.selected};return next(iter(ids)) if len(ids)==1 else None
    def toggle(self,event=None):
        sel=self.tree.selection()
        if not sel:return
        iid=int(sel[0]);bill=next(x for x in self.bills if x['id']==iid)
        if iid in self.selected:del self.selected[iid]
        else:
            existing=self.single_vendor()
            if existing and existing!=bill['supplier_id']:return messagebox.showwarning('One vendor per payment','A single payment/check can cover several bills only for the same vendor. Clear the selection before choosing another vendor.',parent=self)
            self.selected[iid]={'credit':0,'cash':float(bill['balance_due'])}
        self.apply_credits();self.redraw()
    def select_all(self,value):
        self.selected={}
        if value and self.bills:
            sid=self.bills[0]['supplier_id']
            for x in self.bills:
                if x['supplier_id']==sid:self.selected[x['id']]={'credit':0,'cash':float(x['balance_due'])}
        self.apply_credits();self.redraw()
    def apply_credits(self):
        sid=self.single_vendor();remaining=vp.available_credit(self.company_id,sid) if sid else 0
        for bill in sorted((x for x in self.bills if x['id'] in self.selected),key=lambda x:(x['due_date'],x['id'])):
            due=float(bill['balance_due']);credit=min(due,remaining);self.selected[bill['id']]={'credit':credit,'cash':due-credit};remaining-=credit
    def new_credit(self):VendorCreditDialog(self,self.company_id,self.single_vendor(),self.refresh)
    def pay(self):
        sid=self.single_vendor()
        if not sid:return messagebox.showwarning('Select bills','Select one or more bills for one vendor.',parent=self)
        try:
            batch=vp.pay_bills({'company_id':self.company_id,'supplier_id':sid,'payment_date':self.date.get(),'payment_method':self.method.get(),'payment_account_id':self.cmap.get(self.account.get()),'check_number':self.check.get(),'print_later':self.print_later.get(),'reference':self.reference.get()},[{'invoice_id':i,'cash_amount':x['cash'],'credit_amount':x['credit']} for i,x in self.selected.items()]);messagebox.showinfo('Bills paid',f'Payment batch #{batch} was recorded. Fully settled bills are now marked Paid.',parent=self);self.selected={};self.refresh();
            
            if self.on_saved:self.on_saved()
        except Exception as e:messagebox.showerror('Cannot pay bills',str(e),parent=self)