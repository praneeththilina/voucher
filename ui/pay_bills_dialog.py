"""QuickBooks-style Pay Bills and vendor credit screens."""
import tkinter as tk
from tkinter import messagebox, simpledialog
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
        self.check_templates = db.get_check_templates(
            self.company_id, active_only=True
        )
        self.template_map = {
            (
                f"{row['bank_name']} - {row.get('account_number') or 'Cheque book'}"
            ): row["id"]
            for row in self.check_templates
        }
        self.currency = db.get_company_base_currency(self.company_id).upper()
        self.vendor = tk.StringVar(value="All vendors")
        self.show_mode = tk.StringVar(value="All open bills")
        self.due_by = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.sort_by = tk.StringVar(value="Due date")
        self.method = tk.StringVar(value="Cheque")
        self.account = tk.StringVar()
        self.check_template = tk.StringVar(
            value=next(iter(self.template_map), "")
        )
        self.date = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.rate = tk.StringVar(value="1.000000")
        self.check = tk.StringVar()
        self.print_later = tk.BooleanVar(value=False)
        self.reference = tk.StringVar()
        self.credit_label = tk.StringVar()
        self.total_label = tk.StringVar()
        self.highlight_label = tk.StringVar(
            value="Highlight a selected bill to set its payment or credits."
        )
        if initial_supplier_id:
            for name, supplier_id in self.smap.items():
                if supplier_id == initial_supplier_id:
                    self.vendor.set(name)
                    break
        self.build()
        self.bind("<Control-Return>", lambda _event: self.pay())
        self.bind("<Escape>", lambda _event: self.destroy())
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
            state="readonly", width=24
        )
        vendor_combo.pack(side=LEFT, padx=(6, 12))
        vendor_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        tb.Label(filters, text="Show").pack(side=LEFT)
        show_combo = tb.Combobox(
            filters,
            textvariable=self.show_mode,
            values=["All open bills", "Due on or before"],
            state="readonly",
            width=18,
        )
        show_combo.pack(side=LEFT, padx=(6, 8))
        show_combo.bind("<<ComboboxSelected>>", self._show_filter_changed)
        self.due_label = tb.Label(filters, text="Date")
        self.due_label.pack(side=LEFT)
        self.due_entry = tb.Entry(filters, textvariable=self.due_by, width=12)
        self.due_entry.pack(side=LEFT, padx=(6, 12))

        tb.Label(filters, text="Sort by").pack(side=LEFT)
        sort_combo = tb.Combobox(
            filters,
            textvariable=self.sort_by,
            values=["Due date", "Vendor", "Bill date", "Amount due"],
            state="readonly",
            width=13,
        )
        sort_combo.pack(side=LEFT, padx=(6, 8))
        sort_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        tb.Button(
            filters, text="Refresh", command=self.refresh,
            bootstyle="info-outline"
        ).pack(side=LEFT)
        tb.Button(
            filters, text="Select all", command=lambda: self.select_all(True),
            bootstyle="success-outline"
        ).pack(side=RIGHT)
        tb.Button(
            filters, text="Clear selections",
            command=lambda: self.select_all(False),
            bootstyle="secondary-outline"
        ).pack(side=RIGHT, padx=5)

        # Keep a real button row under the separator. Packing buttons beside a
        # top separator made Tk request only separator height on scaled screens.
        self.command_bar = tb.Frame(self, padding=(16, 4, 16, 10))
        self.command_bar.pack(side=BOTTOM, fill=X)
        tb.Separator(self.command_bar).pack(fill=X, pady=(0, 8))
        self.command_row = tb.Frame(self.command_bar)
        self.command_row.pack(fill=X)
        tb.Label(
            self.command_row,
            text="Double-click a bill to mark/unmark it. Highlight it to set amount or credits.",
            bootstyle="secondary",
        ).pack(side=LEFT)
        self.close_btn = tb.Button(
            self.command_row,
            text="Close (Esc)",
            command=self.destroy,
            bootstyle="secondary",
        )
        self.close_btn.pack(side=RIGHT)
        self.pay_btn = tb.Button(
            self.command_row,
            text="Pay selected bills (Ctrl+Enter)",
            command=self.pay,
            bootstyle="success",
        )
        self.pay_btn.pack(side=RIGHT, padx=(0, 8))
        self.credit_btn = tb.Button(
            self.command_row,
            text="New vendor credit",
            command=self.new_credit,
            bootstyle="warning-outline",
        )
        self.credit_btn.pack(side=RIGHT, padx=(0, 8))
        columns = (
            "pick", "vendor", "currency", "date", "due", "number",
            "original", "open", "credit", "discount", "pay"
        )
        self.tree = tb.Treeview(
            self, columns=columns, show="headings", selectmode="browse"
        )
        definitions = [
            ("pick", "Pay", 48), ("vendor", "Vendor", 170),
            ("currency", "Currency", 70), ("date", "Bill date", 88),
            ("due", "Due date", 88), ("number", "Bill no.", 110),
            ("original", "Original", 100), ("open", "Open balance", 110),
            ("credit", "Credit applied", 100),
            ("discount", "Discount", 90), ("pay", "Amount to pay", 105),
        ]
        for key, heading, width in definitions:
            self.tree.heading(key, text=heading)
            self.tree.column(
                key, width=width,
                anchor=E if key in {"original", "open", "credit", "discount", "pay"} else W
            )
        scrollbar = tb.Scrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True, padx=(16, 0), pady=5)
        scrollbar.pack(side=LEFT, fill=Y, pady=5)
        self.tree.bind("<Double-1>", self.toggle)
        self.tree.bind("<<TreeviewSelect>>", self._update_highlighted_bill)

        side = tb.Frame(self, padding=(14, 8), width=350)
        side.pack(side=RIGHT, fill=Y)
        tb.Label(
            side, text="Payment details", font=("Segoe UI", 14, "bold")
        ).pack(anchor=W)
        tb.Label(
            side, textvariable=self.credit_label, bootstyle="info"
        ).pack(anchor=W, pady=(2, 6))
        self._field(side, "Payment date", self.date)
        self.method_combo = self._field(
            side,
            "Method",
            self.method,
            [
                "Cheque", "Credit Card", "Cash", "Bank Transfer", "EFT",
                "Online Bank Payment", "Online/Other",
            ],
        )
        self.method_combo.bind(
            "<<ComboboxSelected>>", self._update_payment_method
        )
        self.template_combo = self._field(
            side,
            "Cheque book / Write Cheques template",
            self.check_template,
            list(self.template_map),
        )
        self._field(side, "Exchange rate", self.rate)
        self.account_combo = self._field(
            side, "Cash / bank / credit-card account", self.account, []
        )
        self.check_entry = self._field(side, "Check number", self.check)
        self._field(side, "Reference / memo", self.reference)
        self.print_later_check = tb.Checkbutton(
            side,
            text="To be printed / assign check number later",
            variable=self.print_later,
            bootstyle="round-toggle",
        )
        self.print_later_check.pack(anchor=W, pady=6)

        allocation_box = tb.Labelframe(
            side,
            text="Highlighted bill — discount & credit information",
            padding=8,
        )
        allocation_box.pack(fill=X, pady=(4, 6))
        tb.Label(
            allocation_box,
            textvariable=self.highlight_label,
            wraplength=315,
            bootstyle="secondary",
        ).pack(anchor=W, fill=X, pady=(0, 6))
        allocation_actions = tb.Frame(allocation_box)
        allocation_actions.pack(fill=X)
        tb.Button(
            allocation_actions,
            text="Set amount",
            command=self.set_payment_amount,
            bootstyle="info-outline",
        ).pack(side=LEFT)
        tb.Button(
            allocation_actions,
            text="Set credits",
            command=self.set_credits,
            bootstyle="warning-outline",
        ).pack(side=LEFT, padx=5)
        tb.Button(
            allocation_actions,
            text="Discount",
            command=self.set_discount,
            bootstyle="success-outline",
        ).pack(side=LEFT, padx=(0, 5))
        tb.Button(
            allocation_actions,
            text="Auto-apply",
            command=self.auto_apply_credits,
            bootstyle="secondary-outline",
        ).pack(side=LEFT)

        tb.Separator(side).pack(fill=X, pady=4)
        tb.Label(
            side,
            textvariable=self.total_label,
            font=("Segoe UI", 11, "bold"),
            wraplength=315,
        ).pack(anchor=W, pady=4)
        self._update_payment_method()
        self._show_filter_changed(refresh=False)

    @staticmethod
    def _field(parent, label, variable, values=None):
        tb.Label(parent, text=label).pack(anchor=W, pady=(3, 1))
        if values is None:
            widget = tb.Entry(parent, textvariable=variable, width=36)
        else:
            widget = tb.Combobox(
                parent, textvariable=variable, values=values,
                state="readonly", width=34
            )
        widget.pack(fill=X)
        return widget

    def _show_filter_changed(self, _event=None, refresh=True):
        """Enable the due-date field only for QuickBooks-style due filtering."""
        due_mode = self.show_mode.get() == "Due on or before"
        self.due_entry.configure(state="normal" if due_mode else "disabled")
        self.due_label.configure(
            bootstyle="default" if due_mode else "secondary"
        )
        if refresh:
            self.refresh()

    def _update_payment_method(self, _event=None):
        """Show cheque controls only when the selected method needs them."""
        cheque = self.method.get() == "Cheque"
        self.template_combo.configure(state="readonly" if cheque else "disabled")
        self.check_entry.configure(state="normal" if cheque else "disabled")
        self.print_later_check.configure(state="normal" if cheque else "disabled")
        if not cheque:
            self.print_later.set(False)

    def _selected_bill(self, require_marked=False):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo(
                "Highlight a bill",
                "Highlight a bill in the list first.",
                parent=self,
            )
            return None
        invoice_id = int(selection[0])
        bill = next(
            (row for row in self.bills if row["id"] == invoice_id), None
        )
        if require_marked and invoice_id not in self.selected:
            messagebox.showinfo(
                "Select the bill",
                "Double-click the highlighted bill to mark it for payment first.",
                parent=self,
            )
            return None
        return bill

    def _update_highlighted_bill(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            self.highlight_label.set(
                "Highlight a selected bill to set its payment or credits."
            )
            return
        invoice_id = int(selection[0])
        bill = next(
            (row for row in self.bills if row["id"] == invoice_id), None
        )
        if not bill:
            return
        allocation = self.selected.get(invoice_id)
        if allocation:
            detail = (
                f"{bill['invoice_number']} | Open {self.currency} "
                f"{float(bill['balance_due']):,.2f}\n"
                f"Pay {self.currency} {allocation['cash']:,.2f} | "
                f"Credits {self.currency} {allocation['credit']:,.2f} | "
                f"Discount {self.currency} {allocation.get('discount', 0):,.2f}"
            )
        else:
            detail = (
                f"{bill['invoice_number']} | Open {self.currency} "
                f"{float(bill['balance_due']):,.2f}\n"
                "Not selected for payment."
            )
        self.highlight_label.set(detail)

    def set_payment_amount(self):
        """Set a full or partial cash amount for the highlighted bill."""
        bill = self._selected_bill(require_marked=True)
        if not bill:
            return
        allocation = self.selected[bill["id"]]
        maximum = max(
            0.0, float(bill["balance_due"]) - allocation["credit"]
            - allocation.get("discount", 0)
        )
        amount = simpledialog.askfloat(
            "Amount to pay",
            f"Cash amount for bill {bill['invoice_number']} "
            f"(maximum {self.currency} {maximum:,.2f}):",
            parent=self,
            initialvalue=allocation["cash"],
            minvalue=0.0,
            maxvalue=maximum,
        )
        if amount is None:
            return
        allocation["cash"] = round(amount, 2)
        self.redraw(focus_id=bill["id"])

    def set_credits(self):
        """Apply a chosen amount of available vendor credit to one bill."""
        bill = self._selected_bill(require_marked=True)
        if not bill:
            return
        allocation = self.selected[bill["id"]]
        supplier_id = self.single_vendor()
        total_available = vp.available_credit(self.company_id, supplier_id)
        used_elsewhere = sum(
            row["credit"] for invoice_id, row in self.selected.items()
            if invoice_id != bill["id"]
        )
        available = max(0.0, total_available - used_elsewhere)
        maximum = min(
            float(bill["balance_due"]) - allocation.get("discount", 0),
            available,
        )
        if maximum <= vp.TOL:
            messagebox.showinfo(
                "No vendor credit",
                "This vendor has no unapplied credit available.",
                parent=self,
            )
            return
        amount = simpledialog.askfloat(
            "Set Credits",
            f"Credit to apply to bill {bill['invoice_number']} "
            f"(available {self.currency} {maximum:,.2f}):",
            parent=self,
            initialvalue=min(allocation["credit"], maximum),
            minvalue=0.0,
            maxvalue=maximum,
        )
        if amount is None:
            return
        old_credit = allocation["credit"]
        allocation["credit"] = round(amount, 2)
        allocation["cash"] = min(
            allocation["cash"] + old_credit,
            float(bill["balance_due"]) - allocation["credit"]
            - allocation.get("discount", 0),
        )
        self.redraw(focus_id=bill["id"])

    def set_discount(self):
        """Apply an early-payment discount to the highlighted bill."""
        bill = self._selected_bill(require_marked=True)
        if not bill:
            return
        allocation = self.selected[bill["id"]]
        maximum = max(
            0.0,
            float(bill["balance_due"]) - allocation["credit"],
        )
        amount = simpledialog.askfloat(
            "Set Discount",
            f"Discount received for bill {bill['invoice_number']} "
            f"(maximum {self.currency} {maximum:,.2f}).\n\n"
            "This posts to 4310 - Other Income & Discounts Received:",
            parent=self,
            initialvalue=min(allocation.get("discount", 0), maximum),
            minvalue=0.0,
            maxvalue=maximum,
        )
        if amount is None:
            return
        old_discount = allocation.get("discount", 0)
        allocation["discount"] = round(amount, 2)
        allocation["cash"] = min(
            allocation["cash"] + old_discount,
            float(bill["balance_due"])
            - allocation["credit"]
            - allocation["discount"],
        )
        self.redraw(focus_id=bill["id"])
    def auto_apply_credits(self):
        """Apply available credits oldest-due-bill first, like the QB preference."""
        if not self.selected:
            messagebox.showinfo(
                "Select bills",
                "Select at least one bill before applying credits.",
                parent=self,
            )
            return
        self.apply_credits()
        self.redraw()
    def refresh(self):
        supplier_id = self.smap.get(self.vendor.get())
        bills = [
            row for row in vp.open_bills(self.company_id, supplier_id)
            if row["status"] not in ("Paid", "Cancelled")
        ]
        if self.show_mode.get() == "Due on or before":
            try:
                cutoff = datetime.strptime(
                    self.due_by.get().strip(), "%Y-%m-%d"
                ).strftime("%Y-%m-%d")
            except ValueError:
                messagebox.showwarning(
                    "Invalid date",
                    "Enter the due date as YYYY-MM-DD.",
                    parent=self,
                )
                return
            bills = [row for row in bills if row["due_date"] <= cutoff]

        sorters = {
            "Due date": lambda row: (row["due_date"], row["supplier_name"]),
            "Vendor": lambda row: (row["supplier_name"].casefold(), row["due_date"]),
            "Bill date": lambda row: (row["invoice_date"], row["id"]),
            "Amount due": lambda row: (-float(row["balance_due"]), row["due_date"]),
        }
        self.bills = sorted(bills, key=sorters[self.sort_by.get()])
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

    def redraw(self, focus_id=None):
        previous = focus_id
        if previous is None and self.tree.selection():
            previous = int(self.tree.selection()[0])
        self._refresh_currency_accounts()
        self.tree.delete(*self.tree.get_children())
        for bill in self.bills:
            allocation = self.selected.get(
                bill["id"], {"credit": 0, "discount": 0, "cash": 0}
            )
            self.tree.insert(
                "", END, iid=str(bill["id"]),
                values=(
                    "Yes" if bill["id"] in self.selected else "",
                    bill["supplier_name"], bill.get("currency") or self.currency,
                    bill["invoice_date"], bill["due_date"], bill["invoice_number"],
                    f"{bill['total_amount']:,.2f}",
                    f"{bill['balance_due']:,.2f}",
                    f"{allocation['credit']:,.2f}",
                    f"{allocation.get('discount', 0):,.2f}",
                    f"{allocation['cash']:,.2f}",
                ),
                tags=("selected",) if bill["id"] in self.selected else (),
            )
        self.tree.tag_configure("selected", background="#dcf3e9")
        if previous is not None and self.tree.exists(str(previous)):
            self.tree.selection_set(str(previous))
            self.tree.focus(str(previous))
            self.tree.see(str(previous))
        supplier_id = self.single_vendor()
        available = (
            vp.available_credit(self.company_id, supplier_id)
            if supplier_id else 0
        )
        self.credit_label.set(
            f"Available credit: {self.currency} {available:,.2f}"
        )
        cash = sum(row["cash"] for row in self.selected.values())
        credits = sum(row["credit"] for row in self.selected.values())
        discounts = sum(
            row.get("discount", 0) for row in self.selected.values()
        )
        self.total_label.set(
            f"Cash to pay: {self.currency} {cash:,.2f}\n"
            f"Credits applied: {self.currency} {credits:,.2f}\n"
            f"Discounts: {self.currency} {discounts:,.2f}\n"
            f"Selected bills: {len(self.selected)}"
        )
        self._update_highlighted_bill()
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
                "credit": 0,
                "discount": 0,
                "cash": float(bill["balance_due"]),
            }
        self.redraw(focus_id=invoice_id)
    def select_all(self, value):
        self.selected = {}
        if value and self.bills:
            supplier_id = self.bills[0]["supplier_id"]
            currency = self.bills[0].get("currency")
            for bill in self.bills:
                if (
                    bill["supplier_id"] == supplier_id
                    and bill.get("currency") == currency
                ):
                    self.selected[bill["id"]] = {
                        "credit": 0,
                        "discount": 0,
                        "cash": float(bill["balance_due"]),
                    }
        self.redraw()
    def apply_credits(self):
        supplier_id = self.single_vendor()
        remaining = vp.available_credit(self.company_id, supplier_id) if supplier_id else 0
        selected = sorted(
            (row for row in self.bills if row["id"] in self.selected),
            key=lambda row: (row["due_date"], row["id"]),
        )
        for bill in selected:
            discount = self.selected[bill["id"]].get("discount", 0)
            due = max(0.0, float(bill["balance_due"]) - discount)
            credit = min(due, remaining)
            self.selected[bill["id"]] = {
                "credit": credit,
                "discount": discount,
                "cash": due - credit,
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
                    "check_template_id": self.template_map.get(
                        self.check_template.get()
                    ),
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
                        "discount_amount": allocation.get("discount", 0),
                    }
                    for invoice_id, allocation in self.selected.items()
                ],
            )
            result = vp.get_payment_batch(batch_id) or {}
            details = [
                f"A/P payment batch #{batch_id} was recorded.",
                "The selected bills were settled through Accounts Payable; "
                "no extra payment voucher was created.",
            ]
            if result.get("linked_check_number"):
                details.append(
                    "Write Cheques record: "
                    f"{result['linked_check_number']} (ready in Check Register)."
                )
            elif self.method.get() == "Cheque" and self.print_later.get():
                details.append(
                    "Cheque: Print later — the payment batch remains available "
                    "for cheque issue when the cheque number is available."
                )
            details.append("Settled bills are now marked Paid.")
            messagebox.showinfo(
                "Bills paid", "\n".join(details), parent=self
            )
            self.selected = {}
            self.refresh()
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            messagebox.showerror("Cannot pay bills", str(exc), parent=self)