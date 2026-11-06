"""QuickBooks-style Pay Bills and vendor credit screens."""
import os
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog, ttk
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


class BankTransferFileDialog(tb.Toplevel):
    """Corporate Bank Transfer & Direct Deposit Payment File Exporter (EFT CSV, ISO 20022 XML, NACHA)."""

    def __init__(self, parent, company_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.on_saved = on_saved
        self.title("Bank Transfer Batch Payment File Exporter")
        self.geometry("980x620")
        self.minsize(820, 500)
        self.transient(parent)

        self.batches = []
        self.selected_batch_ids = set()

        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.format_var = tk.StringVar(value="csv")
        self.summary_var = tk.StringVar(value="0 batches selected | Total: LKR 0.00")

        self.build_ui()
        self.refresh()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def build_ui(self):
        head = tk.Frame(self, bg="#0f172a", padx=20, pady=12)
        head.pack(fill=X)
        tk.Label(
            head, text="🏦 Bank Transfer Batch Payment File Generator",
            font=("Segoe UI", 16, "bold"), bg="#0f172a", fg="white"
        ).pack(anchor=W)
        tk.Label(
            head,
            text="Generate corporate direct deposit transfer files (EFT CSV, ISO 20022 XML, NACHA) for online banking upload.",
            bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9)
        ).pack(anchor=W)

        # Filters
        filters = tb.Labelframe(self, text="Filter Transfer Batches", padding=10)
        filters.pack(fill=X, padx=16, pady=10)

        tb.Label(filters, text="From Date:").pack(side=LEFT, padx=(0, 4))
        tb.Entry(filters, textvariable=self.start_date_var, width=12).pack(side=LEFT, padx=(0, 10))

        tb.Label(filters, text="To Date:").pack(side=LEFT, padx=(0, 4))
        tb.Entry(filters, textvariable=self.end_date_var, width=12).pack(side=LEFT, padx=(0, 10))

        tb.Button(filters, text="Apply Filter", command=self.refresh, bootstyle="info-outline").pack(side=LEFT, padx=(0, 10))
        tb.Button(filters, text="Reset", command=self._reset_filters, bootstyle="secondary-outline").pack(side=LEFT)

        tb.Label(filters, textvariable=self.summary_var, font=("Segoe UI", 10, "bold"), bootstyle="primary").pack(side=RIGHT)

        # Treeview
        columns = ("pick", "batch_id", "date", "vendor", "bank", "account", "tax_id", "ref", "amount", "currency")
        table_frame = tb.Frame(self, padding=(16, 0))
        table_frame.pack(fill=BOTH, expand=True)

        self.tree = tb.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = [
            ("pick", "Select", 55, CENTER),
            ("batch_id", "Batch #", 75, CENTER),
            ("date", "Payment Date", 95, CENTER),
            ("vendor", "Vendor Name", 170, W),
            ("bank", "Bank Name", 130, W),
            ("account", "Account Number", 130, W),
            ("tax_id", "Tax / NIC #", 95, W),
            ("ref", "Reference", 100, W),
            ("amount", "Transfer Amount", 120, E),
            ("currency", "Currency", 70, CENTER),
        ]
        for col_id, title, width, align in headings:
            self.tree.heading(col_id, text=title)
            self.tree.column(col_id, width=width, anchor=align)

        scrollbar = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", self.toggle_selection)
        self.tree.bind("<Return>", self.toggle_selection)
        self.tree.bind("<KP_Enter>", self.toggle_selection)
        self.bind("<Escape>", lambda e: self.destroy())

        # Bottom Bar
        bottom = tb.Frame(self, padding=16)
        bottom.pack(fill=X)

        tb.Label(bottom, text="Export Format:").pack(side=LEFT, padx=(0, 6))

        formats = [
            ("Standard EFT (CSV)", "csv"),
            ("ISO 20022 (XML)", "xml"),
            ("NACHA (TXT)", "nacha"),
        ]
        for label, val in formats:
            tb.Radiobutton(bottom, text=label, value=val, variable=self.format_var).pack(side=LEFT, padx=(0, 10))

        tb.Button(bottom, text="Close", command=self.destroy, bootstyle="secondary").pack(side=RIGHT)
        exp_btn = tb.Button(bottom, text="📥 Generate Bank Payment File", command=self.export_file, bootstyle="success")
        exp_btn.pack(side=RIGHT, padx=(0, 8))
        tb.ToolTip(exp_btn, text="Export selected bank transfer batch payment records into file format for banking portals")

        tb.Button(bottom, text="Clear All", command=lambda: self.select_all(False), bootstyle="secondary-outline").pack(side=LEFT, padx=(10, 4))
        tb.Button(bottom, text="Select All", command=lambda: self.select_all(True), bootstyle="success-outline").pack(side=LEFT)

    def _reset_filters(self):
        self.start_date_var.set("")
        self.end_date_var.set("")
        self.refresh()

    def refresh(self):
        self.batches = vp.bank_transfer_batches(
            company_id=self.company_id,
            start_date=self.start_date_var.get().strip() or None,
            end_date=self.end_date_var.get().strip() or None
        )
        if not self.selected_batch_ids:
            self.selected_batch_ids = {b["id"] for b in self.batches}
        else:
            valid_ids = {b["id"] for b in self.batches}
            self.selected_batch_ids = self.selected_batch_ids.intersection(valid_ids)

        self.redraw()

    def redraw(self):
        self.tree.delete(*self.tree.get_children())
        tot_amt = 0.0

        for b in self.batches:
            is_sel = b["id"] in self.selected_batch_ids
            amt = float(b.get("total_cash_amount") or 0.0)
            if is_sel:
                tot_amt += amt

            self.tree.insert(
                "", END, iid=str(b["id"]),
                values=(
                    "✓ Yes" if is_sel else "",
                    f"PAY-{b['id']}",
                    b.get("payment_date", ""),
                    b.get("supplier_name", ""),
                    b.get("supplier_bank_name") or "Standard Bank",
                    b.get("supplier_bank_account") or "—",
                    b.get("supplier_tax_id") or "—",
                    b.get("reference") or f"PAY-{b['id']}",
                    f"{amt:,.2f}",
                    (b.get("currency") or "LKR").upper(),
                ),
                tags=("selected",) if is_sel else ()
            )

        self.tree.tag_configure("selected", background="#dcf3e9")

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

        self.summary_var.set(
            f"{len(self.selected_batch_ids)} batch(es) selected | Total: LKR {tot_amt:,.2f}"
        )

    def toggle_selection(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        batch_id = int(sel[0])
        if batch_id in self.selected_batch_ids:
            self.selected_batch_ids.remove(batch_id)
        else:
            self.selected_batch_ids.add(batch_id)
        self.redraw()

    def select_all(self, val):
        if val:
            self.selected_batch_ids = {b["id"] for b in self.batches}
        else:
            self.selected_batch_ids.clear()
        self.redraw()

    def export_file(self):
        if not self.selected_batch_ids:
            messagebox.showwarning("No Selection", "Please select at least one bank transfer payment batch to export.", parent=self)
            return

        fmt = self.format_var.get()
        ext_map = {"csv": ".csv", "xml": ".xml", "nacha": ".txt"}
        type_map = {
            "csv": [("CSV Files", "*.csv"), ("All Files", "*.*")],
            "xml": [("XML Files", "*.xml"), ("All Files", "*.*")],
            "nacha": [("Text Files", "*.txt"), ("All Files", "*.*")],
        }

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Bank Transfer Direct Deposit File",
            defaultextension=ext_map.get(fmt, ".csv"),
            filetypes=type_map.get(fmt, [("All Files", "*.*")]),
            initialfile=f"bank_transfer_batch_{self.company_id}{ext_map.get(fmt, '.csv')}"
        )
        if not path:
            return

        try:
            res = vp.export_bank_transfer_batch_file(
                batch_ids=list(self.selected_batch_ids),
                filepath=path,
                format_type=fmt,
                company_id=self.company_id
            )
            messagebox.showinfo(
                "Export Successful",
                f"Bank Transfer payment file successfully generated!\n\n"
                f"• Format: {res['format'].upper()}\n"
                f"• Record Count: {res['record_count']}\n"
                f"• Total Amount: {res['currency']} {res['total_amount']:,.2f}\n"
                f"• File Path: {path}",
                parent=self
            )
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc), parent=self)


class VendorCreditListDialog(tb.Toplevel):
    """Vendor Credits & Memos Directory Dialog."""

    def __init__(self, parent, company_id=None, supplier_id=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.supplier_id = supplier_id
        self.on_saved = on_saved
        self.title("Accounts Payable Vendor Credit Notes & Memos")
        self.geometry("960x560")
        self.transient(parent)

        self.open_only_var = tk.BooleanVar(value=False)
        self.summary_var = tk.StringVar()

        self._build_ui()
        self.refresh()
        self.center_window()

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        root = tb.Frame(self, padding=16)
        root.pack(fill=BOTH, expand=True)

        # Header
        hdr = tb.Frame(root)
        hdr.pack(fill=X, pady=(0, 12))

        tb.Label(hdr, text="📜 Vendor Credit Notes & Memos", font=("Segoe UI", 16, "bold")).pack(anchor=W)
        tb.Label(hdr, textvariable=self.summary_var, font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)

        # Toolbar
        toolbar = tb.Labelframe(root, text="Options & Actions", padding=10)
        toolbar.pack(fill=X, pady=(0, 12))

        tb.Checkbutton(
            toolbar, text="Open / Unapplied Credits Only", variable=self.open_only_var,
            bootstyle="round-toggle", command=self.refresh
        ).pack(side=LEFT, padx=(0, 12))

        tb.Button(toolbar, text="➕ New Vendor Credit", command=self._new_credit, bootstyle="warning").pack(side=LEFT)
        tb.Button(toolbar, text="📥 Export CSV", command=self._export_csv, bootstyle="outline").pack(side=RIGHT)

        # Table
        columns = ("number", "date", "vendor", "account", "amount", "remaining", "currency", "status", "ref")
        table_frame = tb.Frame(root)
        table_frame.pack(fill=BOTH, expand=True)

        self.tree = tb.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = [
            ("number", "Credit #", 110, CENTER),
            ("date", "Date", 95, CENTER),
            ("vendor", "Vendor Name", 180, W),
            ("account", "Expense Ledger Reversed", 180, W),
            ("amount", "Credit Amount", 120, E),
            ("remaining", "Remaining", 120, E),
            ("currency", "Currency", 75, CENTER),
            ("status", "Status", 80, CENTER),
            ("ref", "Reference", 100, W),
        ]
        for cid, title, width, align in headings:
            self.tree.heading(cid, text=title)
            self.tree.column(cid, width=width, anchor=align)

        scroll = tb.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        self.bind("<Escape>", lambda e: self.destroy())

        # Footer
        bottom = tb.Frame(root, padding=(0, 10, 0, 0))
        bottom.pack(fill=X)
        tb.Button(bottom, text="Close", command=self.destroy, bootstyle="secondary").pack(side=RIGHT)

    def refresh(self):
        credits_list = vp.credits(
            company_id=self.company_id,
            supplier_id=self.supplier_id,
            open_only=self.open_only_var.get()
        )
        self.tree.delete(*self.tree.get_children())
        tot_rem = 0.0

        for c in credits_list:
            rem = float(c.get("remaining_amount") or 0.0)
            tot_rem += rem
            self.tree.insert(
                "", END, iid=str(c["id"]),
                values=(
                    c.get("credit_number", ""),
                    c.get("credit_date", ""),
                    c.get("supplier_name", ""),
                    c.get("expense_account_name") or "Reversed Ledger",
                    f"{float(c.get('amount') or 0.0):,.2f}",
                    f"{rem:,.2f}",
                    (c.get("currency") or "LKR").upper(),
                    c.get("status", "Open"),
                    c.get("reference", ""),
                )
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

        self.summary_var.set(
            f"{len(credits_list)} credit note(s) found | Total Open Available Credit: LKR {tot_rem:,.2f}"
        )

    def _new_credit(self):
        VendorCreditDialog(self, self.company_id, self.supplier_id, on_saved=self._on_saved_credit)

    def _on_saved_credit(self):
        self.refresh()
        if self.on_saved:
            self.on_saved()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Vendor Credits to CSV",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=f"vendor_credits_{self.company_id}.csv"
        )
        if not path:
            return

        try:
            vp.export_vendor_credits_to_csv(
                filepath=path,
                company_id=self.company_id,
                supplier_id=self.supplier_id,
                open_only=self.open_only_var.get()
            )
            messagebox.showinfo("Export Successful", f"Vendor credits exported to:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc), parent=self)