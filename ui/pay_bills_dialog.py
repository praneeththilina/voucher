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
    """Settle multiple same-vendor, same-currency bills in one payment."""

    def __init__(
        self, parent, company_id=None, initial_supplier_id=None, on_saved=None
    ):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_saved = on_saved
        self.title("Pay Bills")
        self.state("zoomed")
        self.minsize(1050, 650)
        self.transient(parent)
        self.suppliers = db.get_suppliers(self.company_id, active_only=False)
        self.smap = {"All vendors": None} | {
            row["name"]: row["id"] for row in self.suppliers
        }
        self.selected = {}
        self.bills = []
        self.cmap = {}
        self.currency = db.get_company_base_currency(self.company_id).upper()
        self.vendor = tk.StringVar(value="All vendors")
        self.start = tk.StringVar()
        self.end = tk.StringVar()
        self.method = tk.StringVar(value="Cheque")
        self.account = tk.StringVar()
        self.date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.rate = tk.StringVar(value="1.000000")
        self.check = tk.StringVar()
        self.print_later = tk.BooleanVar(value=False)
        self.reference = tk.StringVar()
        self.credit_label = tk.StringVar()
        self.total_label = tk.StringVar()
        if initial_supplier_id:
            for name, supplier_id in self.smap.items():
                if supplier_id == initial_supplier_id:
                    self.vendor.set(name)
                    break
        self.build()
        self.refresh()

    def build(self):
        head = tk.Frame(self, bg="#172033", padx=22, pady=14)
        head.pack(fill=X)
        tk.Label(
            head, text="Pay Bills", font=("Segoe UI", 19, "bold"),
            bg="#172033", fg="white"
        ).pack(anchor=W)
        tk.Label(
            head,
            text="Select bills for one vendor and currency, apply credits, then pay the balance.",
            bg="#172033", fg="#bdc8d9"
        ).pack(anchor=W)

        filters = tb.Labelframe(self, text="Show bills", padding=10)
        filters.pack(fill=X, padx=16, pady=10)
        tb.Label(filters, text="Vendor").pack(side=LEFT)
        vendor_combo = tb.Combobox(
            filters, textvariable=self.vendor, values=list(self.smap),
            state="readonly", width=27
        )
        vendor_combo.pack(side=LEFT, padx=6)
        vendor_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        tb.Label(filters, text="From").pack(side=LEFT)
        tb.Entry(filters, textvariable=self.start, width=12).pack(side=LEFT, padx=5)
        tb.Label(filters, text="To").pack(side=LEFT)
        tb.Entry(filters, textvariable=self.end, width=12).pack(side=LEFT, padx=5)
        tb.Button(
            filters, text="Apply filter", command=self.refresh,
            bootstyle="info-outline"
        ).pack(side=LEFT, padx=6)
        tb.Button(
            filters, text="Select all", command=lambda: self.select_all(True),
            bootstyle="success-outline"
        ).pack(side=RIGHT)
        tb.Button(
            filters, text="Clear", command=lambda: self.select_all(False),
            bootstyle="secondary-outline"
        ).pack(side=RIGHT, padx=5)

        columns = (
            "pick", "vendor", "currency", "date", "due", "number",
            "original", "open", "credit", "pay"
        )
        self.tree = tb.Treeview(
            self, columns=columns, show="headings", selectmode="browse"
        )
        definitions = [
            ("pick", "Pay", 48), ("vendor", "Vendor", 170),
            ("currency", "Currency", 70), ("date", "Bill date", 88),
            ("due", "Due date", 88), ("number", "Bill no.", 110),
            ("original", "Original", 100), ("open", "Open balance", 110),
            ("credit", "Credit applied", 110), ("pay", "Amount to pay", 110),
        ]
        for key, heading, width in definitions:
            self.tree.heading(key, text=heading)
            self.tree.column(
                key, width=width,
                anchor=E if key in {"original", "open", "credit", "pay"} else W
            )
        scrollbar = tb.Scrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True, padx=(16, 0), pady=5)
        scrollbar.pack(side=LEFT, fill=Y, pady=5)
        self.tree.bind("<Double-1>", self.toggle)

        side = tb.Frame(self, padding=16, width=340)
        side.pack(side=RIGHT, fill=Y)
        tb.Label(side, text="Payment details", font=("Segoe UI", 14, "bold")).pack(anchor=W)
        tb.Label(side, textvariable=self.credit_label, bootstyle="info").pack(anchor=W, pady=(5, 14))
        self._field(side, "Payment date", self.date)
        self._field(
            side, "Method", self.method,
            ["Cheque", "Cash", "Bank Transfer", "EFT", "Online/Other"]
        )
        self._field(side, "Exchange rate", self.rate)
        self.account_combo = self._field(side, "Cash / bank account", self.account, [])
        self._field(side, "Check number", self.check)
        self._field(side, "Reference", self.reference)
        tb.Checkbutton(
            side, text="Print later (assign check number later)",
            variable=self.print_later, bootstyle="round-toggle"
        ).pack(anchor=W, pady=12)
        tb.Separator(side).pack(fill=X, pady=8)
        tb.Label(
            side, textvariable=self.total_label,
            font=("Segoe UI", 11, "bold"), wraplength=310
        ).pack(anchor=W, pady=8)
        tb.Button(
            side, text="Pay selected bills", command=self.pay,
            bootstyle="success"
        ).pack(fill=X, pady=8)
        tb.Button(
            side, text="New vendor credit", command=self.new_credit,
            bootstyle="warning-outline"
        ).pack(fill=X)
        tb.Button(side, text="Close", command=self.destroy).pack(fill=X, pady=8)

    @staticmethod
    def _field(parent, label, variable, values=None):
        tb.Label(parent, text=label).pack(anchor=W, pady=(7, 2))
        if values is None:
            widget = tb.Entry(parent, textvariable=variable, width=36)
        else:
            widget = tb.Combobox(
                parent, textvariable=variable, values=values,
                state="readonly", width=34
            )
        widget.pack(fill=X)
        return widget

    def refresh(self):
        supplier_id = self.smap.get(self.vendor.get())
        self.bills = [
            row for row in vp.open_bills(
                self.company_id, supplier_id,
                self.start.get() or None, self.end.get() or None
            )
            if row["status"] not in ("Paid", "Cancelled")
        ]
        valid = {row["id"] for row in self.bills}
        self.selected = {
            key: value for key, value in self.selected.items() if key in valid
        }
        self.redraw()

    def _refresh_currency_accounts(self):
        selected = [row for row in self.bills if row["id"] in self.selected]
        self.currency = (
            (selected[0].get("currency") if selected else None)
            or db.get_company_base_currency(self.company_id)
        ).upper()
        accounts = vp.cash_accounts(self.company_id, self.currency)
        self.cmap = {
            f"{row['account_code']} - {row['account_name']} ({row['currency']})": row["id"]
            for row in accounts
        }
        self.account_combo.configure(values=list(self.cmap))
        if self.account.get() not in self.cmap:
            self.account.set(next(iter(self.cmap), ""))
        home = db.get_company_base_currency(self.company_id).upper()
        if self.currency == home:
            self.rate.set("1.000000")
        else:
            found = db.get_exchange_rate(self.currency, home)
            self.rate.set(f"{float(found['rate']):.6f}" if found else "")

    def redraw(self):
        self._refresh_currency_accounts()
        self.tree.delete(*self.tree.get_children())
        for bill in self.bills:
            allocation = self.selected.get(bill["id"], {"credit": 0, "cash": 0})
            self.tree.insert(
                "", END, iid=str(bill["id"]),
                values=(
                    "Yes" if bill["id"] in self.selected else "",
                    bill["supplier_name"], bill.get("currency") or self.currency,
                    bill["invoice_date"], bill["due_date"], bill["invoice_number"],
                    f"{bill['total_amount']:,.2f}", f"{bill['balance_due']:,.2f}",
                    f"{allocation['credit']:,.2f}", f"{allocation['cash']:,.2f}",
                ),
                tags=("selected",) if bill["id"] in self.selected else (),
            )
        self.tree.tag_configure("selected", background="#dcf3e9")
        supplier_id = self.single_vendor()
        available = vp.available_credit(self.company_id, supplier_id) if supplier_id else 0
        self.credit_label.set(f"Available credit: {self.currency} {available:,.2f}")
        cash = sum(row["cash"] for row in self.selected.values())
        credits = sum(row["credit"] for row in self.selected.values())
        self.total_label.set(
            f"Cash to pay: {self.currency} {cash:,.2f}\n"
            f"Credits applied: {self.currency} {credits:,.2f}"
        )

    def single_vendor(self):
        ids = {
            row["supplier_id"] for row in self.bills
            if row["id"] in self.selected
        }
        return next(iter(ids)) if len(ids) == 1 else None

    def toggle(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        invoice_id = int(selection[0])
        bill = next(row for row in self.bills if row["id"] == invoice_id)
        if invoice_id in self.selected:
            del self.selected[invoice_id]
        else:
            existing = self.single_vendor()
            if existing and existing != bill["supplier_id"]:
                messagebox.showwarning(
                    "One vendor per payment",
                    "A payment may cover several bills only for one vendor.",
                    parent=self,
                )
                return
            selected_currency = next(
                (
                    row.get("currency") for row in self.bills
                    if row["id"] in self.selected
                ),
                bill.get("currency"),
            )
            if selected_currency != bill.get("currency"):
                messagebox.showwarning(
                    "One currency per payment",
                    "A payment batch cannot mix currencies.", parent=self
                )
                return
            self.selected[invoice_id] = {
                "credit": 0, "cash": float(bill["balance_due"])
            }
        self.apply_credits()
        self.redraw()

    def select_all(self, value):
        self.selected = {}
        if value and self.bills:
            supplier_id = self.bills[0]["supplier_id"]
            currency = self.bills[0].get("currency")
            for bill in self.bills:
                if bill["supplier_id"] == supplier_id and bill.get("currency") == currency:
                    self.selected[bill["id"]] = {
                        "credit": 0, "cash": float(bill["balance_due"])
                    }
        self.apply_credits()
        self.redraw()

    def apply_credits(self):
        supplier_id = self.single_vendor()
        remaining = vp.available_credit(self.company_id, supplier_id) if supplier_id else 0
        selected = sorted(
            (row for row in self.bills if row["id"] in self.selected),
            key=lambda row: (row["due_date"], row["id"]),
        )
        for bill in selected:
            due = float(bill["balance_due"])
            credit = min(due, remaining)
            self.selected[bill["id"]] = {
                "credit": credit, "cash": due - credit
            }
            remaining -= credit

    def new_credit(self):
        VendorCreditDialog(
            self, self.company_id, self.single_vendor(), self.refresh
        )

    def pay(self):
        supplier_id = self.single_vendor()
        if not supplier_id:
            messagebox.showwarning(
                "Select bills", "Select bills for one vendor.", parent=self
            )
            return
        try:
            batch_id = vp.pay_bills(
                {
                    "company_id": self.company_id,
                    "supplier_id": supplier_id,
                    "payment_date": self.date.get(),
                    "payment_method": self.method.get(),
                    "payment_account_id": self.cmap.get(self.account.get()),
                    "check_number": self.check.get(),
                    "print_later": self.print_later.get(),
                    "reference": self.reference.get(),
                    "currency": self.currency,
                    "exchange_rate": self.rate.get(),
                },
                [
                    {
                        "invoice_id": invoice_id,
                        "cash_amount": allocation["cash"],
                        "credit_amount": allocation["credit"],
                    }
                    for invoice_id, allocation in self.selected.items()
                ],
            )
            messagebox.showinfo(
                "Bills paid",
                f"Payment batch #{batch_id} was recorded. Settled bills are now Paid.",
                parent=self,
            )
            self.selected = {}
            self.refresh()
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            messagebox.showerror("Cannot pay bills", str(exc), parent=self)