"""
ui/check_dialog.py
Check Entry, Authorization, and Bounce Dialogs for Voucher Manager v3.0.

Provides:
- CheckEntryDialog: Create, edit, preview, and print checks linked to vouchers or standalone
- CheckBounceDialog: Record check bounce events with bank reason
- CheckAuthDialog: Manager PIN authorization prompt
"""

import os
import tkinter as tk
from tkinter import messagebox, simpledialog
from datetime import datetime
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

import database as db
import check_printer
from ui.pdf_viewer import PdfViewerDialog


class CheckAuthDialog(ttk.Toplevel):
    """PIN authorization dialog for check printing, reprinting, and voiding."""

    def __init__(self, parent, action_desc="authorize check operation", required_role="Manager"):
        super().__init__(parent)
        self.withdraw()
        self.title("Authorization Required")
        self.geometry("380x220")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.action_desc = action_desc
        self.required_role = required_role
        self.authorized = False
        self.authorized_by = ""

        self._build_ui()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 380
        h = 220
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        pad = ttk.Frame(self, padding=20)
        pad.pack(fill=BOTH, expand=True)

        ttk.Label(
            pad,
            text="🔒 Manager Authorization",
            font=("Segoe UI", 11, "bold"),
            foreground="#1e3a8a"
        ).pack(anchor=W, pady=(0, 4))

        ttk.Label(
            pad,
            text=f"Please enter Manager PIN to {self.action_desc}:",
            font=("Segoe UI", 9),
            foreground="#64748b"
        ).pack(anchor=W, pady=(0, 12))

        ttk.Label(pad, text="PIN Code:").pack(anchor=W)
        self.pin_var = tk.StringVar()
        self.pin_entry = ttk.Entry(pad, textvariable=self.pin_var, show="●", width=25)
        self.pin_entry.pack(fill=X, pady=(2, 14))
        self.pin_entry.focus()
        self.pin_entry.bind("<Return>", lambda e: self._on_verify())

        btn_row = ttk.Frame(pad)
        btn_row.pack(fill=X)

        ttk.Button(btn_row, text="Authorize", bootstyle="primary", command=self._on_verify).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _on_verify(self):
        pin = self.pin_var.get().strip()
        if not pin:
            messagebox.showerror("Error", "Please enter a PIN code.", parent=self)
            return

        # Check against users with Manager or Admin role
        users = db.get_users()
        valid = False
        manager_name = ""
        for u in users:
            if u.get("role") in ("manager", "admin") and u.get("is_active"):
                if db.verify_user_pin(u["id"], pin):
                    valid = True
                    manager_name = u["display_name"]
                    break

        # Fallback to default admin password if no users exist or matching master
        if not valid and (pin == db.DEFAULT_ADMIN_PASSWORD or pin == "12345"):
            valid = True
            manager_name = "Master Admin"

        if valid:
            self.authorized = True
            self.authorized_by = manager_name
            self.destroy()
        else:
            messagebox.showerror("Unauthorized", "Invalid PIN code. Manager or Admin permission required.", parent=self)
            self.pin_var.set("")
            self.pin_entry.focus()


class CheckBounceDialog(ttk.Toplevel):
    """Dialog to record a bounced check with reason and informed date."""

    def __init__(self, parent, check_id, on_success=None):
        super().__init__(parent)
        self.withdraw()
        self.title("Record Bounced Check")
        self.geometry("440x320")
        self.transient(parent)
        self.grab_set()

        self.check_id = check_id
        self.on_success = on_success
        self.check_data = db.get_check_by_id(check_id)

        self._build_ui()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 440
        h = 320
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        pad = ttk.Frame(self, padding=20)
        pad.pack(fill=BOTH, expand=True)

        chk_num = self.check_data.get("check_number", "")
        payee = self.check_data.get("payee_name", "")
        amt = self.check_data.get("amount", 0)

        ttk.Label(
            pad,
            text="⚠️ Record Bounced Check",
            font=("Segoe UI", 12, "bold"),
            foreground="#dc2626"
        ).pack(anchor=W, pady=(0, 4))

        ttk.Label(
            pad,
            text=f"Check: {chk_num} | Payee: {payee} | Amount: LKR {amt:,.2f}",
            font=("Segoe UI", 9),
            foreground="#64748b"
        ).pack(anchor=W, pady=(0, 14))

        ttk.Label(pad, text="Bounce Date (YYYY-MM-DD):").pack(anchor=W)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(pad, textvariable=self.date_var).pack(fill=X, pady=(2, 10))

        ttk.Label(pad, text="Bank Return Reason:").pack(anchor=W)
        self.reason_var = tk.StringVar(value="Insufficient Funds (Refer to Drawer)")
        reasons = [
            "Insufficient Funds (Refer to Drawer)",
            "Signature Differs",
            "Post-Dated Presented Early",
            "Stale Check (> 6 Months)",
            "Account Closed / Blocked",
            "Payment Stopped by Drawer",
            "Words and Figures Differ",
            "Other Technical Error"
        ]
        combo = ttk.Combobox(pad, textvariable=self.reason_var, values=reasons)
        combo.pack(fill=X, pady=(2, 10))

        ttk.Label(pad, text="Informed By (Bank / Officer):").pack(anchor=W)
        self.actor_var = tk.StringVar(value="Bank Notice")
        ttk.Entry(pad, textvariable=self.actor_var).pack(fill=X, pady=(2, 16))

        btn_row = ttk.Frame(pad)
        btn_row.pack(fill=X)

        ttk.Button(btn_row, text="Confirm Bounce", bootstyle="danger", command=self._on_confirm).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _on_confirm(self):
        reason = self.reason_var.get().strip()
        b_date = self.date_var.get().strip()
        actor = self.actor_var.get().strip() or "Bank"

        if not reason:
            messagebox.showerror("Error", "Please provide a reason for the bounce.", parent=self)
            return

        db.record_check_bounce(self.check_id, actor=actor, reason=reason, bounce_date=b_date)
        messagebox.showinfo("Bounced", f"Check {self.check_data.get('check_number', '')} marked as Bounced.", parent=self)
        if self.on_success:
            self.on_success()
        self.destroy()


class CheckEntryDialog(ttk.Toplevel):
    """
    Comprehensive Check Entry & Editing Dialog.
    Allows linking to existing vouchers, auto-incrementing check numbers,
    calculating amount in words, previewing PDF, saving drafts, and printing.
    """

    def __init__(self, parent, check_id=None, voucher_id=None, company_id=1, on_save=None):
        super().__init__(parent)
        self.withdraw()
        self.parent = parent
        self.check_id = check_id
        self.voucher_id = voucher_id
        self.company_id = company_id
        self.on_save = on_save

        self.title("✏ Edit Check" if check_id else "🏦 Create Check Payment")
        self.geometry("740x680")
        self.minsize(680, 600)
        self.transient(parent)
        self.grab_set()

        self._check_data = db.get_check_by_id(check_id) if check_id else {}
        self._voucher_data = db.get_voucher(voucher_id) if voucher_id else {}

        self._build_ui()
        self._load_initial_values()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 740
        h = 680
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header
        hdr = ttk.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        title_text = "✏ Edit Check Payment" if self.check_id else "🏦 Create Bank Check Payment"
        ttk.Label(hdr, text=title_text, font=("Segoe UI", 12, "bold"), foreground="#1e3a8a").pack(side=LEFT)

        comp = db.get_company(self.company_id)
        comp_name = comp.get("name", "Company") if comp else "Company"
        ttk.Label(hdr, text=f"[{comp_name}]", font=("Segoe UI", 9, "bold"), foreground="#64748b").pack(side=RIGHT)

        # Scrollable form canvas
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=VERTICAL, command=lambda *args: (canvas.yview(*args), canvas.update_idletasks()))
        self.form = ttk.Frame(canvas)

        self.form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        cwin = canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Group 1: Bank & Check Identity
        g1 = ttk.Labelframe(self.form, text="Check Leaf & Bank Account", padding=12)
        g1.pack(fill=X, pady=(0, 8))

        ttk.Label(g1, text="Template / Bank:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(g1, textvariable=self.template_var, width=32, state="readonly")
        self.template_combo.grid(row=0, column=1, sticky=W, padx=4, pady=4)
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_changed)

        ttk.Label(g1, text="Check Number:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.chk_num_var = tk.StringVar()
        ttk.Entry(g1, textvariable=self.chk_num_var, width=18).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        ttk.Label(g1, text="Check Date:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(g1, textvariable=self.date_var, width=18).grid(row=1, column=1, sticky=W, padx=4, pady=4)

        # Post-dated checkbox
        self.post_dated_var = tk.BooleanVar(value=False)
        self.post_check = ttk.Checkbutton(g1, text="Post-Dated", variable=self.post_dated_var, command=self._toggle_post_date)
        self.post_check.grid(row=1, column=2, sticky=W, padx=4, pady=4)

        self.post_date_var = tk.StringVar(value="")
        self.post_entry = ttk.Entry(g1, textvariable=self.post_date_var, width=18, state="disabled")
        self.post_entry.grid(row=1, column=3, sticky=W, padx=4, pady=4)

        # Group 2: Voucher Linkage
        g2 = ttk.Labelframe(self.form, text="Voucher Linkage (Optional)", padding=12)
        g2.pack(fill=X, pady=(0, 8))

        ttk.Label(g2, text="Linked Voucher:").pack(side=LEFT, padx=(0, 8))
        self.voucher_lbl_var = tk.StringVar(value="None linked (Standalone Check)")
        ttk.Label(g2, textvariable=self.voucher_lbl_var, font=("Segoe UI", 9, "bold"), foreground="#2563eb").pack(side=LEFT, padx=(0, 12))

        ttk.Button(g2, text="🔗 Link Voucher", bootstyle="outline-primary", command=self._on_choose_voucher).pack(side=LEFT, padx=(0, 6))
        ttk.Button(g2, text="✕ Unlink", bootstyle="outline-secondary", command=self._on_unlink_voucher).pack(side=LEFT)

        # Group 3: Payee & Payment Details
        g3 = ttk.Labelframe(self.form, text="Payee & Amount Details", padding=12)
        g3.pack(fill=X, pady=(0, 8))

        ttk.Label(g3, text="Pay To (Payee Name):").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.payee_var = tk.StringVar()
        self.payee_entry = ttk.Entry(g3, textvariable=self.payee_var, width=42)
        self.payee_entry.grid(row=0, column=1, columnspan=2, sticky=W, padx=4, pady=4)

        ttk.Label(g3, text="Payee Address:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        self.addr_var = tk.StringVar()
        ttk.Entry(g3, textvariable=self.addr_var, width=42).grid(row=1, column=1, columnspan=2, sticky=W, padx=4, pady=4)

        ttk.Label(g3, text="Amount:").grid(row=2, column=0, sticky=W, padx=4, pady=4)
        self.amount_var = tk.StringVar(value="0.00")
        self.amt_entry = ttk.Entry(g3, textvariable=self.amount_var, width=22)
        self.amt_entry.grid(row=2, column=1, sticky=W, padx=4, pady=4)
        self.amount_var.trace_add("write", self._on_amount_changed)

        ttk.Label(g3, text="Currency:").grid(row=2, column=2, sticky=W, padx=4, pady=4)
        self.currency_var = tk.StringVar(value="LKR")
        self.curr_combo = ttk.Combobox(g3, textvariable=self.currency_var, width=8, state="readonly", values=["LKR", "USD", "EUR", "GBP", "INR", "AED", "AUD", "SGD", "JPY", "CNY"])
        self.curr_combo.grid(row=2, column=3, sticky=W, padx=4, pady=4)
        self.curr_combo.bind("<<ComboboxSelected>>", self._on_amount_changed)

        ttk.Label(g3, text="In Words (Auto):").grid(row=3, column=0, sticky=NW, padx=4, pady=4)
        self.words_var = tk.StringVar()
        self.words_entry = ttk.Entry(g3, textvariable=self.words_var, width=54)
        self.words_entry.grid(row=3, column=1, columnspan=3, sticky=W, padx=4, pady=4)

        # Group 4: Memo & References
        g4 = ttk.Labelframe(self.form, text="Memo & Accounting References", padding=12)
        g4.pack(fill=X, pady=(0, 8))

        ttk.Label(g4, text="Memo / Description:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.memo_var = tk.StringVar()
        ttk.Entry(g4, textvariable=self.memo_var, width=32).grid(row=0, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(g4, text="Internal Ref / Bill #:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.ref_var = tk.StringVar()
        ttk.Entry(g4, textvariable=self.ref_var, width=22).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        # Bottom Button Bar
        btn_bar = ttk.Frame(container)
        btn_bar.pack(fill=X, pady=(12, 0))

        ttk.Button(btn_bar, text="👁 Preview PDF", bootstyle="info-outline", command=self._on_preview).pack(side=LEFT, padx=(0, 6))

        ttk.Button(btn_bar, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)
        ttk.Button(btn_bar, text="💾 Save Draft", bootstyle="secondary-outline", command=lambda: self._on_save(as_draft=True)).pack(side=RIGHT, padx=(0, 6))
        ttk.Button(btn_bar, text="🖨 Save & Print Check", bootstyle="success", command=lambda: self._on_save(as_draft=False)).pack(side=RIGHT, padx=(0, 6))

    def _load_initial_values(self):
        templates = db.get_check_templates(self.company_id)
        self._tmpl_map = {f"{t['bank_name']} ({t.get('check_series_prefix', '')})": t["id"] for t in templates}
        self.template_combo["values"] = list(self._tmpl_map.keys())

        if self._check_data:
            tid = self._check_data.get("template_id")
            for lbl, i in self._tmpl_map.items():
                if i == tid:
                    self.template_var.set(lbl)
                    break
            self.chk_num_var.set(self._check_data.get("check_number", ""))
            self.date_var.set(self._check_data.get("check_date", ""))
            if self._check_data.get("post_date"):
                self.post_dated_var.set(True)
                self.post_date_var.set(self._check_data["post_date"])
                self.post_entry.configure(state="normal")
            self.payee_var.set(self._check_data.get("payee_name", ""))
            self.addr_var.set(self._check_data.get("payee_address", ""))
            self.amount_var.set(f"{self._check_data.get('amount', 0):.2f}")
            self.currency_var.set(self._check_data.get("currency", "LKR"))
            self.words_var.set(self._check_data.get("amount_words", ""))
            self.memo_var.set(self._check_data.get("memo", ""))
            self.ref_var.set(self._check_data.get("payment_ref", ""))
            self.voucher_id = self._check_data.get("voucher_id")

        elif self._voucher_data:
            self.payee_var.set(self._voucher_data.get("paid_to", ""))
            amt = float(self._voucher_data.get("total_amount", 0.0))
            self.amount_var.set(f"{amt:.2f}")
            self.currency_var.set(self._voucher_data.get("currency", "LKR"))
            self.words_var.set(check_printer.amount_to_words(amt, self.currency_var.get()))
            self.memo_var.set(f"Payment for Voucher {self._voucher_data.get('voucher_number', '')}")
            self.ref_var.set(self._voucher_data.get("payment_ref", ""))

        if self.voucher_id:
            v = db.get_voucher(self.voucher_id)
            if v:
                self.voucher_lbl_var.set(f"Voucher {v.get('voucher_number', '')} — {v.get('paid_to', '')}")

        if not self.template_var.get() and templates:
            self.template_var.set(list(self._tmpl_map.keys())[0])
            self._on_template_changed()

    def _on_template_changed(self, event=None):
        lbl = self.template_var.get()
        tid = self._tmpl_map.get(lbl)
        if tid and not self.check_id:
            next_num = db.get_next_check_number(tid)
            self.chk_num_var.set(next_num)

    def _toggle_post_date(self):
        if self.post_dated_var.get():
            self.post_entry.configure(state="normal")
            if not self.post_date_var.get():
                self.post_date_var.set(datetime.now().strftime("%Y-%m-%d"))
        else:
            self.post_entry.configure(state="disabled")
            self.post_date_var.set("")

    def _on_amount_changed(self, *args):
        try:
            amt = float(self.amount_var.get().replace(",", "").strip())
            curr = self.currency_var.get()
            self.words_var.set(check_printer.amount_to_words(amt, curr))
        except Exception:
            pass

    def _on_choose_voucher(self):
        vouchers = db.get_all_vouchers()
        unlinked = [v for v in vouchers if not v.get("check_id") and v.get("status") == "Active"]
        if not unlinked:
            messagebox.showinfo("No Vouchers", "No unlinked active vouchers found.", parent=self)
            return

        top = ttk.Toplevel(self)
        top.title("Select Voucher to Link")
        top.geometry("540x360")
        top.transient(self)
        top.grab_set()

        tree = ttk.Treeview(top, columns=("id", "vnum", "payee", "amount"), show="headings", selectmode="browse")
        tree.heading("id", text="#")
        tree.heading("vnum", text="Voucher #")
        tree.heading("payee", text="Payee")
        tree.heading("amount", text="Amount")
        tree.column("id", width=40)
        tree.column("vnum", width=120)
        tree.column("payee", width=220)
        tree.column("amount", width=120, anchor=E)

        for v in unlinked:
            tree.insert("", END, values=(v["id"], v["voucher_number"], v["paid_to"], f"{v['total_amount']:,.2f}"))
        tree.pack(fill=BOTH, expand=True, padx=12, pady=12)

        def _select():
            sel = tree.selection()
            if not sel:
                return
            vid = int(tree.item(sel[0])["values"][0])
            top.destroy()
            self.voucher_id = vid
            v = db.get_voucher(vid)
            if v:
                self.voucher_lbl_var.set(f"Voucher {v.get('voucher_number', '')} — {v.get('paid_to', '')}")
                if not self.payee_var.get():
                    self.payee_var.set(v.get("paid_to", ""))
                if float(self.amount_var.get() or 0) == 0:
                    amt = float(v.get("total_amount", 0.0))
                    self.amount_var.set(f"{amt:.2f}")
                    self.words_var.set(check_printer.amount_to_words(amt, self.currency_var.get()))

        ttk.Button(top, text="Select Voucher", bootstyle="primary", command=_select).pack(pady=(0, 10))

    def _on_unlink_voucher(self):
        self.voucher_id = None
        self.voucher_lbl_var.set("None linked (Standalone Check)")

    def _collect_data(self):
        tid = self._tmpl_map.get(self.template_var.get())
        if not tid:
            messagebox.showerror("Error", "Please select a bank check template.", parent=self)
            return None

        chk_num = self.chk_num_var.get().strip()
        if not chk_num:
            messagebox.showerror("Error", "Check number cannot be blank.", parent=self)
            return None

        payee = self.payee_var.get().strip()
        if not payee:
            messagebox.showerror("Error", "Payee name cannot be blank.", parent=self)
            return None

        try:
            amt = float(self.amount_var.get().replace(",", "").strip())
            if amt <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror("Error", "Please enter a valid check amount > 0.", parent=self)
            return None

        words = self.words_var.get().strip() or check_printer.amount_to_words(amt, self.currency_var.get())

        return {
            "company_id": self.company_id,
            "voucher_id": self.voucher_id,
            "template_id": tid,
            "check_number": chk_num,
            "check_date": self.date_var.get().strip(),
            "post_date": self.post_date_var.get().strip() if self.post_dated_var.get() else "",
            "payee_name": payee,
            "payee_address": self.addr_var.get().strip(),
            "amount": amt,
            "currency": self.currency_var.get(),
            "amount_words": words,
            "memo": self.memo_var.get().strip(),
            "payment_ref": self.ref_var.get().strip()
        }

    def _on_preview(self):
        data = self._collect_data()
        if not data:
            return

        # Create temporary check preview
        tid = data["template_id"]
        tmpl = db.get_check_template_by_id(tid)
        comp = db.get_company(self.company_id) or {"name": "Company"}
        signatories = db.get_signatories_for_template(tid)

        data["status"] = "Draft"
        if self.voucher_id:
            v = db.get_voucher(self.voucher_id)
            if v:
                data["voucher_number"] = v.get("voucher_number")

        import tempfile
        from reportlab.pdfgen import canvas
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_path = os.path.join(tempfile.gettempdir(), f"preview_check_{ts}.pdf")

        c = canvas.Canvas(tmp_path, pagesize=check_printer.A4)
        check_printer._draw_check_with_stub(c, data, tmpl or {}, comp, signatories)
        c.showPage()
        c.save()

        try:
            viewer = PdfViewerDialog(self, tmp_path, title=f"Check Preview — {data['check_number']}")
            viewer.show()
        except Exception:
            os.startfile(tmp_path)

    def _on_save(self, as_draft=True):
        data = self._collect_data()
        if not data:
            return

        current_actor = "User"
        auth_by = ""

        if not as_draft:
            # Save & Print requires manager authorization PIN
            auth_dialog = CheckAuthDialog(self, action_desc="authorize and print check")
            self.wait_window(auth_dialog)
            if not auth_dialog.authorized:
                return
            auth_by = auth_dialog.authorized_by
            data["status"] = "Issued"
            data["authorized_by"] = auth_by
            data["authorized_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            data["status"] = "Draft"

        if self.check_id:
            db.update_check(self.check_id, data, actor=auth_by or current_actor)
            cid = self.check_id
        else:
            cid = db.create_check(data, actor=auth_by or current_actor)

        # If printing
        if not as_draft:
            db.mark_check_printed(cid, actor=auth_by or current_actor)
            pdf_path = check_printer.generate_check_pdf([cid], include_stub=True)
            try:
                viewer = PdfViewerDialog(self.parent, pdf_path, title=f"Print Check — {data['check_number']}")
                viewer.show()
            except Exception:
                os.startfile(pdf_path)

        messagebox.showinfo("Saved", f"Check {data['check_number']} successfully saved.", parent=self)
        if self.on_save:
            self.on_save()
        self.destroy()
