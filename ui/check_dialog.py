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
import printer
from ui.pdf_viewer import PdfViewerDialog
from ui.widgets import AutocompleteEntry


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
                    manager_name = u.get("display_name") or u.get("username", "Manager")
                    break

        # Check against registered approvers
        if not valid:
            try:
                for app in db.get_approvers():
                    if app.get("is_active") and db.verify_approver_pin(app["id"], pin):
                        valid = True
                        manager_name = app.get("name", "Approver")
                        break
            except Exception:
                pass
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


class VoucherLinkSelectorDialog(ttk.Toplevel):
    """
    Searchable, filterable modal dialog for linking a voucher to a check.
    Supports real-time search, status filtering, double-click preview of voucher PDF,
    and responsive layout guaranteeing visible command buttons.
    """

    def __init__(self, parent, company_id=1, payee_filter="", allow_all_payees=False, on_select=None):
        super().__init__(parent)
        self.withdraw()
        self.parent = parent
        self.company_id = company_id
        self.initial_payee = (payee_filter or "").strip()
        self.allow_all_payees = bool(allow_all_payees)
        self.on_select = on_select
        self.selected_voucher = None

        self.title("Select Voucher to Link")
        self.transient(parent)
        self.grab_set()

        self._all_vouchers = []
        self._filtered_vouchers = []

        # If a target payee was given and allow_all_payees is False, default show_all_payees_var to False (filter for that payee)
        initial_show_all = self.allow_all_payees or not bool(self.initial_payee)
        self.show_all_payees_var = tk.BooleanVar(value=initial_show_all)

        self._build_ui()
        self._load_data()

        # Geometry & centering
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(980, max(840, int(sw * 0.62)))
        h = min(640, max(520, int(sh * 0.62)))
        self.minsize(800, 460)
        self.resizable(True, True)

        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = max(20, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()
        self.search_entry.focus()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # 1. Header
        hdr = ttk.Frame(container)
        hdr.pack(fill=X, pady=(0, 10))

        ttk.Label(
            hdr,
            text="📑 Select Voucher to Link",
            font=("Segoe UI", 12, "bold"),
            foreground="#1e3a8a"
        ).pack(side=LEFT)

        ttk.Label(
            hdr,
            text="💡 Tip: Double-click row to view voucher PDF | Press Enter to link",
            font=("Segoe UI", 8, "italic"),
            foreground="#64748b"
        ).pack(side=RIGHT)

        # 2. Bottom Command Button Bar (PACKED FIRST at side=BOTTOM so it is NEVER squished or clipped!)
        btn_bar = ttk.Frame(container, padding=(0, 10, 0, 0))
        btn_bar.pack(side=BOTTOM, fill=X)

        self.btn_link = ttk.Button(
            btn_bar,
            text="🔗 Link Selected Voucher",
            bootstyle="primary",
            command=self._on_confirm_selection
        )
        self.btn_link.pack(side=RIGHT, padx=(6, 0), ipady=4)

        self.btn_preview = ttk.Button(
            btn_bar,
            text="👁️ View Voucher PDF (Double-Click)",
            bootstyle="info-outline",
            command=self._on_view_selected
        )
        self.btn_preview.pack(side=RIGHT, padx=(6, 0), ipady=4)

        btn_cancel = ttk.Button(
            btn_bar,
            text="✕ Cancel",
            bootstyle="secondary",
            command=self.destroy
        )
        btn_cancel.pack(side=RIGHT, ipady=4)

        self.status_count_lbl = ttk.Label(
            btn_bar,
            text="Showing 0 vouchers",
            font=("Segoe UI", 9, "bold"),
            foreground="#475569"
        )
        self.status_count_lbl.pack(side=LEFT)

        # 3. Filters & Search Frame
        toolbar = ttk.Labelframe(container, text="Filters & Search", padding=(10, 8))
        toolbar.pack(fill=X, pady=(0, 10))

        search_row = ttk.Frame(toolbar)
        search_row.pack(fill=X)

        ttk.Label(search_row, text="🔍 Search:").pack(side=LEFT, padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_row, textvariable=self.search_var, width=28)
        self.search_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        self.search_var.trace_add("write", lambda *a: self._apply_filters())

        btn_clear = ttk.Button(search_row, text="✕ Clear", bootstyle="secondary-outline", command=self._on_clear_search)
        btn_clear.pack(side=LEFT, padx=(0, 12))

        ttk.Label(search_row, text="Status:").pack(side=LEFT, padx=(0, 6))
        self.status_filter_var = tk.StringVar(value="Unlinked Only")
        status_opts = ["Unlinked Only", "All Active", "Approved Only", "Paid Only", "All Vouchers"]
        self.status_combo = ttk.Combobox(search_row, textvariable=self.status_filter_var, values=status_opts, state="readonly", width=15)
        self.status_combo.pack(side=LEFT, padx=(0, 12))
        self.status_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        ttk.Label(search_row, text="Sort:").pack(side=LEFT, padx=(0, 6))
        self.sort_var = tk.StringVar(value="Newest First")
        sort_opts = ["Newest First", "Oldest First", "Amount: High to Low", "Amount: Low to High", "Payee A-Z"]
        self.sort_combo = ttk.Combobox(search_row, textvariable=self.sort_var, values=sort_opts, state="readonly", width=17)
        self.sort_combo.pack(side=LEFT)
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        # Row 2: Payee Scope & Different Party / Cash Cheque Checkbox
        payee_scope_row = ttk.Frame(toolbar)
        payee_scope_row.pack(fill=X, pady=(6, 0))

        if self.initial_payee:
            self.payee_scope_lbl = ttk.Label(
                payee_scope_row,
                text=f"👤 Payee Filter: '{self.initial_payee}'",
                font=("Segoe UI", 9, "bold"),
                foreground="#1e3a8a"
            )
            self.payee_scope_lbl.pack(side=LEFT, padx=(0, 10))

            self.diff_party_check = ttk.Checkbutton(
                payee_scope_row,
                text="Pay Different Party / Show all payees (Cash Cheque / Alternate Payee)",
                variable=self.show_all_payees_var,
                bootstyle="info-round-toggle",
                command=self._on_scope_toggled
            )
            self.diff_party_check.pack(side=LEFT)
        else:
            self.payee_scope_lbl = ttk.Label(
                payee_scope_row,
                text="👤 Payee Filter: All Payees",
                font=("Segoe UI", 9, "bold"),
                foreground="#475569"
            )
            self.payee_scope_lbl.pack(side=LEFT, padx=(0, 10))

            self.diff_party_check = ttk.Checkbutton(
                payee_scope_row,
                text="Show All Payees",
                variable=self.show_all_payees_var,
                bootstyle="info-round-toggle",
                command=self._apply_filters
            )
            self.diff_party_check.pack(side=LEFT)

        # 4. Table (Treeview)
        table_frame = ttk.Frame(container)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "vnum", "date", "payee", "amount", "status", "check_link", "memo")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("id", text="#")
        self.tree.heading("vnum", text="Voucher #")
        self.tree.heading("date", text="Date")
        self.tree.heading("payee", text="Payee")
        self.tree.heading("amount", text="Amount")
        self.tree.heading("status", text="Status")
        self.tree.heading("check_link", text="Check Status")
        self.tree.heading("memo", text="Description / Notes")

        self.tree.column("id", width=45, minwidth=35, stretch=False)
        self.tree.column("vnum", width=110, minwidth=85)
        self.tree.column("date", width=95, minwidth=75)
        self.tree.column("payee", width=190, minwidth=120)
        self.tree.column("amount", width=110, minwidth=85, anchor=E)
        self.tree.column("status", width=85, minwidth=65, anchor=CENTER)
        self.tree.column("check_link", width=110, minwidth=80, anchor=CENTER)
        self.tree.column("memo", width=180, minwidth=100)

        v_scroll = ttk.Scrollbar(table_frame, orient=VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Double-click or double-tap opens voucher PDF
        self.tree.bind("<Double-1>", lambda e: self._on_view_selected())
        self.tree.bind("<Return>", lambda e: self._on_confirm_selection())
        self.tree.bind("<KP_Enter>", lambda e: self._on_confirm_selection())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_scope_toggled(self):
        if hasattr(self, "payee_scope_lbl") and self.initial_payee:
            if self.show_all_payees_var.get():
                self.payee_scope_lbl.configure(
                    text=f"👤 Scope: All Payees (Check Payee: '{self.initial_payee}')",
                    foreground="#d97706"
                )
            else:
                self.payee_scope_lbl.configure(
                    text=f"👤 Payee Filter: '{self.initial_payee}'",
                    foreground="#1e3a8a"
                )
        self._apply_filters()

    def _on_clear_search(self):
        self.search_var.set("")
        self.status_filter_var.set("Unlinked Only")
        self.sort_var.set("Newest First")
        self._apply_filters()

    def _load_data(self):
        vouchers = db.get_all_vouchers()
        cid = getattr(self, "company_id", None)
        if cid:
            vouchers = [v for v in vouchers if v.get("company_id") in (cid, None)]
        self._all_vouchers = vouchers
        self._apply_filters()

    def _apply_filters(self):
        query = self.search_var.get().strip().lower()
        st_filter = self.status_filter_var.get()
        sort_mode = self.sort_var.get()

        filter_by_payee = (not self.show_all_payees_var.get()) and bool(self.initial_payee)
        target_payee_lower = self.initial_payee.lower() if filter_by_payee else ""

        filtered = []
        for v in self._all_vouchers:
            v_status = v.get("status", "")
            has_check = bool(v.get("check_id") or v.get("check_number"))

            if st_filter == "Unlinked Only" and (has_check or v_status not in ("Active", "Approved")):
                continue
            elif st_filter == "All Active" and v_status != "Active":
                continue
            elif st_filter == "Approved Only" and v_status != "Approved":
                continue
            elif st_filter == "Paid Only" and v_status != "Paid":
                continue

            v_payee = (v.get("paid_to") or "").strip()
            if filter_by_payee:
                if target_payee_lower not in v_payee.lower() and v_payee.lower() not in target_payee_lower:
                    continue

            if query:
                haystack = " ".join([
                    str(v.get("id", "")),
                    str(v.get("voucher_number", "")),
                    str(v_payee),
                    str(v.get("description", "")),
                    str(v.get("payment_ref", "")),
                    str(v.get("notes", "")),
                    str(v.get("category", "")),
                    f"{float(v.get('total_amount', 0.0)):.2f}",
                ]).lower()
                if query not in haystack:
                    continue

            filtered.append(v)

        if sort_mode == "Newest First":
            filtered.sort(key=lambda x: (str(x.get("date", "")), int(x.get("id", 0))), reverse=True)
        elif sort_mode == "Oldest First":
            filtered.sort(key=lambda x: (str(x.get("date", "")), int(x.get("id", 0))))
        elif sort_mode == "Amount: High to Low":
            filtered.sort(key=lambda x: float(x.get("total_amount", 0.0)), reverse=True)
        elif sort_mode == "Amount: Low to High":
            filtered.sort(key=lambda x: float(x.get("total_amount", 0.0)))
        elif sort_mode == "Payee A-Z":
            filtered.sort(key=lambda x: str(x.get("paid_to", "")).lower())

        self._filtered_vouchers = filtered
        self._render_tree()

    def _render_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for v in self._filtered_vouchers:
            vid = v.get("id", "")
            vnum = v.get("voucher_number", "")
            vdate = v.get("date", "")
            payee = v.get("paid_to", "")
            amt = float(v.get("total_amount", 0.0))
            st = v.get("status", "Active")
            chk_ref = f"Check #{v.get('check_number')}" if v.get("check_number") else ("Linked" if v.get("check_id") else "Unlinked")
            desc = v.get("description", "") or v.get("notes", "") or "-"

            self.tree.insert("", END, values=(
                vid,
                vnum,
                vdate,
                payee,
                f"{amt:,.2f}",
                st,
                chk_ref,
                desc
            ))

        total_cnt = len(self._all_vouchers)
        visible_cnt = len(self._filtered_vouchers)
        filter_by_payee = (not self.show_all_payees_var.get()) and bool(self.initial_payee)
        if filter_by_payee:
            self.status_count_lbl.configure(text=f"Showing {visible_cnt} of {total_cnt} vouchers (Filtered for payee: '{self.initial_payee}')")
        else:
            self.status_count_lbl.configure(text=f"Showing {visible_cnt} of {total_cnt} vouchers (All Payees)")

    def _on_confirm_selection(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Voucher", "Please select a voucher from the list to link.", parent=self)
            return
        item_vals = self.tree.item(sel[0])["values"]
        if not item_vals:
            return
        try:
            vid = int(item_vals[0])
        except (ValueError, TypeError):
            messagebox.showerror("Error", "Invalid voucher ID selected.", parent=self)
            return

        v_full = db.get_voucher(vid)
        if not v_full:
            messagebox.showerror("Error", "Selected voucher not found.", parent=self)
            return

        v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else v_full
        if isinstance(v, dict):
            # Guarantee "id" key is present to prevent KeyError: 'id' in any consumer
            if "id" not in v:
                v["id"] = vid
            if "voucher" not in v:
                v["voucher"] = v
        self.selected_voucher = v
        if self.on_select:
            self.on_select(v)
        self.destroy()

    def _on_view_selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Voucher", "Please select a voucher to preview.", parent=self)
            return
        vid = int(self.tree.item(sel[0])["values"][0])
        self._preview_voucher(vid)

    def _preview_voucher(self, vid):
        try:
            pdf_path = printer.generate_voucher_pdf([vid])
            v_full = db.get_voucher(vid)
            v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else None
            vnum = v.get("voucher_number", "") if v else str(vid)
            try:
                viewer = PdfViewerDialog(self, pdf_path, title=f"Voucher Preview — #{vnum}", voucher_ids=[vid])
                viewer.show()
            except Exception:
                os.startfile(pdf_path)
        except Exception as ex:
            messagebox.showerror("Preview Error", f"Could not generate voucher preview:\n{ex}", parent=self)


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
        self.minsize(860, 580)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._check_data = db.get_check_by_id(check_id) if check_id else {}
        v_full = db.get_voucher(voucher_id) if voucher_id else {}
        self._voucher_data = v_full.get("voucher", v_full) if isinstance(v_full, dict) else {}

        self._build_ui()
        self._load_initial_values()

        # Geometry & responsive sizing
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(1020, max(880, int(sw * 0.65)))
        h = min(780, max(660, int(sh * 0.78)))

        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = max(20, px + (pw - w) // 2)
        y = max(20, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # ── Header Bar ──
        hdr = ttk.Frame(container)
        hdr.pack(fill=X, pady=(0, 12))

        title_text = "✏ Edit Check Payment" if self.check_id else "🏦 Create Bank Check Payment"
        ttk.Label(hdr, text=title_text, font=("Segoe UI", 13, "bold"), foreground="#1e3a8a").pack(side=LEFT)

        comp = db.get_company(self.company_id)
        comp_name = comp.get("name", "Company") if comp else "Company"
        ttk.Label(hdr, text=f"🏢 {comp_name}", font=("Segoe UI", 9, "bold"), foreground="#475569").pack(side=RIGHT)

        # ── Main Body Split: Left = Form, Right = Vertical Action Rail ──
        body_frame = ttk.Frame(container)
        body_frame.pack(fill=BOTH, expand=True)

        # Right Action Rail (Vertical Buttons)
        action_rail = ttk.Frame(body_frame, width=210)
        action_rail.pack(side=RIGHT, fill=Y, padx=(14, 0))
        action_rail.pack_propagate(False)

        # Left Scrollable Form
        form_container = ttk.Frame(body_frame)
        form_container.pack(side=LEFT, fill=BOTH, expand=True)

        canvas = tk.Canvas(form_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(form_container, orient=VERTICAL, command=canvas.yview)
        self.form = ttk.Frame(canvas)

        self.form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        cwin = canvas.create_window((0, 0), window=self.form, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(cwin, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        def _on_mousewheel(event):
            if canvas.winfo_exists():
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>") if e.widget == self else None)

        # ── Vertical Action Buttons (in action_rail) ──
        ttk.Label(action_rail, text="ACTIONS", font=("Segoe UI", 8, "bold"), foreground="#64748b").pack(anchor=W, pady=(0, 8))

        self.btn_print = ttk.Button(
            action_rail,
            text="🖨️  Save & Print",
            bootstyle="success",
            command=lambda: self._on_save(as_draft=False)
        )
        self.btn_print.pack(fill=X, pady=(0, 8), ipady=5)

        self.btn_draft = ttk.Button(
            action_rail,
            text="💾  Save Draft",
            bootstyle="primary-outline",
            command=lambda: self._on_save(as_draft=True)
        )
        self.btn_draft.pack(fill=X, pady=(0, 8), ipady=4)

        self.btn_preview = ttk.Button(
            action_rail,
            text="👁️  Preview PDF",
            bootstyle="info-outline",
            command=self._on_preview
        )
        self.btn_preview.pack(fill=X, pady=(0, 8), ipady=4)

        ttk.Separator(action_rail, orient=HORIZONTAL).pack(fill=X, pady=8)

        btn_cancel = ttk.Button(
            action_rail,
            text="✕  Cancel",
            bootstyle="secondary",
            command=self.destroy
        )
        btn_cancel.pack(fill=X, pady=(0, 12), ipady=3)

        # Summary Labelframe
        summary_card = ttk.Labelframe(action_rail, text="Check Summary", padding=10)
        summary_card.pack(fill=X, pady=(4, 0))

        ttk.Label(summary_card, text="Amount:", font=("Segoe UI", 8), foreground="#64748b").pack(anchor=W)
        self.summary_amt_lbl = ttk.Label(summary_card, text="LKR 0.00", font=("Segoe UI", 11, "bold"), foreground="#0f172a")
        self.summary_amt_lbl.pack(anchor=W, pady=(1, 5))

        ttk.Label(summary_card, text="Payee:", font=("Segoe UI", 8), foreground="#64748b").pack(anchor=W)
        self.summary_payee_lbl = ttk.Label(summary_card, text="—", font=("Segoe UI", 8, "italic"), foreground="#334155", wraplength=170)
        self.summary_payee_lbl.pack(anchor=W, pady=(1, 5))

        ttk.Label(summary_card, text="Check #:", font=("Segoe UI", 8), foreground="#64748b").pack(anchor=W)
        self.summary_chk_lbl = ttk.Label(summary_card, text="—", font=("Segoe UI", 9, "bold"), foreground="#2563eb")
        self.summary_chk_lbl.pack(anchor=W, pady=(1, 5))

        ttk.Label(summary_card, text="Linkage:", font=("Segoe UI", 8), foreground="#64748b").pack(anchor=W)
        self.summary_status_lbl = ttk.Label(summary_card, text="Standalone", font=("Segoe UI", 8, "bold"), foreground="#64748b")
        self.summary_status_lbl.pack(anchor=W)

        # Shortcut hints
        shortcuts_box = ttk.Frame(action_rail, padding=(4, 8))
        shortcuts_box.pack(side=BOTTOM, fill=X)
        ttk.Label(
            shortcuts_box,
            text="⚡ Shortcuts\n• Ctrl+P: Print\n• Ctrl+S: Save\n• Ctrl+R: Preview\n• Esc: Close",
            font=("Segoe UI", 8),
            foreground="#94a3b8",
            justify=LEFT
        ).pack(anchor=W)

        # ── Group 1: Bank & Check Identity ──
        g1 = ttk.Labelframe(self.form, text="Check Leaf & Bank Account", padding=12)
        g1.pack(fill=X, pady=(0, 10))
        g1.columnconfigure(1, weight=1)
        g1.columnconfigure(3, weight=1)

        ttk.Label(g1, text="Template / Bank:").grid(row=0, column=0, sticky=W, padx=6, pady=5)
        self.template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(g1, textvariable=self.template_var, state="readonly")
        self.template_combo.grid(row=0, column=1, sticky="ew", padx=6, pady=5)
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_changed)

        ttk.Label(g1, text="Check Number:").grid(row=0, column=2, sticky=W, padx=6, pady=5)
        self.chk_num_var = tk.StringVar()
        self.chk_entry = ttk.Entry(g1, textvariable=self.chk_num_var)
        self.chk_entry.grid(row=0, column=3, sticky="ew", padx=6, pady=5)

        ttk.Label(g1, text="Check Date:").grid(row=1, column=0, sticky=W, padx=6, pady=5)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(g1, textvariable=self.date_var).grid(row=1, column=1, sticky="ew", padx=6, pady=5)

        # Post-dated checkbox
        self.post_dated_var = tk.BooleanVar(value=False)
        self.post_check = ttk.Checkbutton(g1, text="Post-Dated", variable=self.post_dated_var, command=self._toggle_post_date)
        self.post_check.grid(row=1, column=2, sticky=W, padx=6, pady=5)

        self.post_date_var = tk.StringVar(value="")
        self.post_entry = ttk.Entry(g1, textvariable=self.post_date_var, state="disabled")
        self.post_entry.grid(row=1, column=3, sticky="ew", padx=6, pady=5)

        # ── Group 2: Voucher Linkage ──
        g2 = ttk.Labelframe(self.form, text="Voucher Linkage (Optional)", padding=12)
        g2.pack(fill=X, pady=(0, 10))

        v_top = ttk.Frame(g2)
        v_top.pack(fill=X, pady=(0, 6))

        ttk.Label(v_top, text="Linked Voucher:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 8))
        self.voucher_lbl_var = tk.StringVar(value="None linked (Standalone Check)")
        self.voucher_lbl = ttk.Label(
            v_top,
            textvariable=self.voucher_lbl_var,
            font=("Segoe UI", 9, "bold"),
            foreground="#2563eb",
            cursor="hand2"
        )
        self.voucher_lbl.pack(side=LEFT, padx=(0, 12))
        self.voucher_lbl.bind("<Double-1>", lambda e: self._on_view_linked_voucher())

        v_btns = ttk.Frame(g2)
        v_btns.pack(fill=X)

        ttk.Button(v_btns, text="🔗 Link Voucher", bootstyle="outline-primary", command=self._on_choose_voucher).pack(side=LEFT, padx=(0, 6))
        self.view_voucher_btn = ttk.Button(v_btns, text="👁️ View Voucher", bootstyle="outline-info", command=self._on_view_linked_voucher, state="disabled")
        self.view_voucher_btn.pack(side=LEFT, padx=(0, 6))
        ttk.Button(v_btns, text="✕ Unlink", bootstyle="outline-secondary", command=self._on_unlink_voucher).pack(side=LEFT, padx=(0, 12))

        # Different Party / Cash Cheque checkbox
        self.diff_party_var = tk.BooleanVar(value=False)
        self.diff_party_check = ttk.Checkbutton(
            v_btns,
            text="Pay Different Party / Cash Cheque",
            variable=self.diff_party_var,
            bootstyle="info-round-toggle",
            command=self._on_diff_party_toggled
        )
        self.diff_party_check.pack(side=LEFT, padx=(6, 0))

        self.diff_party_hint = ttk.Label(
            g2,
            text="",
            font=("Segoe UI", 8, "italic"),
            foreground="#64748b"
        )
        self.diff_party_hint.pack(anchor=W, pady=(4, 0))

        # ── Group 3: Payee & Amount Details ──
        g3 = ttk.Labelframe(self.form, text="Payee & Amount Details", padding=12)
        g3.pack(fill=X, pady=(0, 10))
        g3.columnconfigure(1, weight=1)
        g3.columnconfigure(3, weight=1)

        ttk.Label(g3, text="Pay To (Payee): *").grid(row=0, column=0, sticky=W, padx=6, pady=5)
        self.payee_var = tk.StringVar()
        
        payee_row = ttk.Frame(g3)
        payee_row.grid(row=0, column=1, columnspan=3, sticky="ew", padx=6, pady=5)

        self.payee_entry = AutocompleteEntry(
            payee_row,
            textvariable=self.payee_var,
            suggestions_callback=lambda: db.get_people(active_only=True)
        )
        self.payee_entry.pack(side=LEFT, fill=X, expand=True)
        self.payee_entry.bind("<<AutocompleteSelected>>", self._on_payee_autocomplete_selected)

        self.btn_payee_dropdown = ttk.Button(
            payee_row,
            text="▾",
            bootstyle="secondary-outline",
            width=3,
            command=self.payee_entry.show_dropdown
        )
        self.btn_payee_dropdown.pack(side=LEFT, padx=(3, 0))

        ttk.Label(g3, text="Payee Address:").grid(row=1, column=0, sticky=W, padx=6, pady=5)
        self.addr_var = tk.StringVar()
        self.addr_entry = ttk.Entry(g3, textvariable=self.addr_var)
        self.addr_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=5)

        ttk.Label(g3, text="Amount:").grid(row=2, column=0, sticky=W, padx=6, pady=5)
        self.amount_var = tk.StringVar(value="0.00")
        self.amt_entry = ttk.Entry(g3, textvariable=self.amount_var)
        self.amt_entry.grid(row=2, column=1, sticky="ew", padx=6, pady=5)
        self.amount_var.trace_add("write", self._on_amount_changed)

        ttk.Label(g3, text="Currency:").grid(row=2, column=2, sticky=W, padx=6, pady=5)
        self.currency_var = tk.StringVar(value="LKR")
        self.curr_combo = ttk.Combobox(g3, textvariable=self.currency_var, width=10, state="readonly", values=["LKR", "USD", "EUR", "GBP", "INR", "AED", "AUD", "SGD", "JPY", "CNY"])
        self.curr_combo.grid(row=2, column=3, sticky="w", padx=6, pady=5)
        self.curr_combo.bind("<<ComboboxSelected>>", self._on_amount_changed)

        ttk.Label(g3, text="In Words (Auto):").grid(row=3, column=0, sticky=NW, padx=6, pady=5)
        self.words_var = tk.StringVar()
        self.words_entry = ttk.Entry(g3, textvariable=self.words_var)
        self.words_entry.grid(row=3, column=1, columnspan=3, sticky="ew", padx=6, pady=5)

        # ── Group 4: Memo & References ──
        g4 = ttk.Labelframe(self.form, text="Memo & Accounting References", padding=12)
        g4.pack(fill=X, pady=(0, 10))
        g4.columnconfigure(1, weight=1)
        g4.columnconfigure(3, weight=1)

        ttk.Label(g4, text="Memo / Description:").grid(row=0, column=0, sticky=W, padx=6, pady=5)
        self.memo_var = tk.StringVar()
        ttk.Entry(g4, textvariable=self.memo_var).grid(row=0, column=1, sticky="ew", padx=6, pady=5)

        ttk.Label(g4, text="Internal Ref / Bill #:").grid(row=0, column=2, sticky=W, padx=6, pady=5)
        self.ref_var = tk.StringVar()
        ttk.Entry(g4, textvariable=self.ref_var).grid(row=0, column=3, sticky="ew", padx=6, pady=5)

        # Trace listeners for live summary updates
        self.payee_var.trace_add("write", lambda *a: self._update_summary())
        self.chk_num_var.trace_add("write", lambda *a: self._update_summary())
        self.template_var.trace_add("write", lambda *a: self._update_summary())

        # Keyboard shortcuts
        self.bind("<Control-s>", lambda e: self._on_save(as_draft=True))
        self.bind("<Control-S>", lambda e: self._on_save(as_draft=True))
        self.bind("<Control-p>", lambda e: self._on_save(as_draft=False))
        self.bind("<Control-P>", lambda e: self._on_save(as_draft=False))
        self.bind("<Control-r>", lambda e: self._on_preview())
        self.bind("<Control-R>", lambda e: self._on_preview())
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_payee_autocomplete_selected(self, event=None):
        self._update_summary()

    def _on_diff_party_toggled(self):
        if self.diff_party_var.get():
            self.diff_party_hint.configure(
                text="ℹ️ Cash Cheque / Different Payee mode: Check payee can differ from voucher payee (e.g. Cash, Bearer, Alternate recipient)",
                foreground="#d97706"
            )
        else:
            self.diff_party_hint.configure(
                text="",
                foreground="#64748b"
            )
        self._update_summary()

    def _update_summary(self):
        if not hasattr(self, "summary_amt_lbl"):
            return
        try:
            curr = self.currency_var.get() or "LKR"
            amt_str = self.amount_var.get().replace(",", "").strip()
            amt = float(amt_str) if amt_str else 0.0
            self.summary_amt_lbl.configure(text=f"{curr} {amt:,.2f}")
        except Exception:
            self.summary_amt_lbl.configure(text="Invalid Amount")

        payee = self.payee_var.get().strip()
        self.summary_payee_lbl.configure(text=payee if payee else "—")

        chk = self.chk_num_var.get().strip()
        self.summary_chk_lbl.configure(text=f"#{chk}" if chk else "—")

        if self.voucher_id:
            if hasattr(self, "diff_party_var") and self.diff_party_var.get():
                self.summary_status_lbl.configure(text="Linked (Diff Payee / Cash)", foreground="#d97706")
            else:
                self.summary_status_lbl.configure(text="Linked to Voucher", foreground="#2563eb")
        else:
            self.summary_status_lbl.configure(text="Standalone Check", foreground="#64748b")

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
            v_dict = self._voucher_data.get("voucher", self._voucher_data) if isinstance(self._voucher_data, dict) else {}
            self.payee_var.set(v_dict.get("paid_to", ""))
            amt = float(v_dict.get("total_amount", 0.0))
            self.amount_var.set(f"{amt:.2f}")
            self.currency_var.set(v_dict.get("currency", "LKR"))
            self.words_var.set(check_printer.amount_to_words(amt, self.currency_var.get()))
            self.memo_var.set(f"Payment for Voucher {v_dict.get('voucher_number', '')}")
            self.ref_var.set(v_dict.get("payment_ref", ""))

        if self.voucher_id:
            v_full = db.get_voucher(self.voucher_id)
            if v_full:
                v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else v_full
                self.voucher_lbl_var.set(f"Voucher {v.get('voucher_number', '')} — {v.get('paid_to', '')}")
                if hasattr(self, "view_voucher_btn"):
                    self.view_voucher_btn.configure(state="normal")
                v_payee = (v.get("paid_to") or "").strip()
                chk_payee = self.payee_var.get().strip()
                if chk_payee and v_payee and chk_payee.lower() != v_payee.lower():
                    self.diff_party_var.set(True)
                    self._on_diff_party_toggled()

        if not self.template_var.get() and templates:
            self.template_var.set(list(self._tmpl_map.keys())[0])
            self._on_template_changed()

        self._update_summary()

    def _on_template_changed(self, event=None):
        lbl = self.template_var.get()
        tid = self._tmpl_map.get(lbl)
        if tid and not self.check_id:
            next_num = db.get_next_check_number(tid)
            self.chk_num_var.set(next_num)
        self._update_summary()

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
        self._update_summary()

    def _on_choose_voucher(self):
        def _handle_selected(v):
            if not v:
                return
            if isinstance(v, dict):
                inner = v.get("voucher")
                v_dict = inner if isinstance(inner, dict) else v
            else:
                return

            vid = v_dict.get("id") or (v.get("id") if isinstance(v, dict) else None)
            if not vid:
                return
            self.voucher_id = vid
            vnum = v_dict.get("voucher_number", "")
            payee = v_dict.get("paid_to", "")
            lbl_text = f"Voucher {vnum} - {payee}" if vnum or payee else f"Voucher #{vid}"
            self.voucher_lbl_var.set(lbl_text)
            if hasattr(self, "view_voucher_btn"):
                self.view_voucher_btn.configure(state="normal")

            chk_payee = self.payee_var.get().strip()
            if self.diff_party_var.get():
                # Different party mode: keep existing check payee if present
                if not chk_payee:
                    self.payee_var.set(payee)
                    if v_dict.get("payee_address"):
                        self.addr_var.set(v_dict.get("payee_address", ""))
            else:
                # Normal mode: check if entered payee differs from voucher payee
                if chk_payee and payee and chk_payee.lower() != payee.lower():
                    self.diff_party_var.set(True)
                    self._on_diff_party_toggled()
                else:
                    if payee:
                        self.payee_var.set(payee)
                    if v_dict.get("payee_address"):
                        self.addr_var.set(v_dict.get("payee_address", ""))

            curr_amt = 0.0
            try:
                curr_amt = float(self.amount_var.get().replace(",", "").strip())
            except Exception:
                curr_amt = 0.0
            if curr_amt == 0:
                amt = float(v_dict.get("total_amount", 0.0))
                self.amount_var.set(f"{amt:.2f}")
                self.words_var.set(check_printer.amount_to_words(amt, self.currency_var.get()))
            if not self.memo_var.get().strip() and vnum:
                self.memo_var.set(f"Payment for Voucher {vnum}")
            if not self.ref_var.get().strip() and v_dict.get("payment_ref"):
                self.ref_var.set(v_dict.get("payment_ref", ""))
            self._update_summary()

        current_payee = self.payee_var.get().strip()
        allow_all = self.diff_party_var.get()
        VoucherLinkSelectorDialog(
            self,
            company_id=self.company_id,
            payee_filter=current_payee,
            allow_all_payees=allow_all,
            on_select=_handle_selected
        )

    def _on_view_linked_voucher(self):
        if not self.voucher_id:
            messagebox.showinfo("No Voucher", "No voucher is currently linked to this check.", parent=self)
            return
        try:
            pdf_path = printer.generate_voucher_pdf([self.voucher_id])
            v_full = db.get_voucher(self.voucher_id)
            v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else None
            vnum = v.get("voucher_number", "") if v else str(self.voucher_id)
            try:
                viewer = PdfViewerDialog(self, pdf_path, title=f"Voucher Preview — #{vnum}", voucher_ids=[self.voucher_id])
                viewer.show()
            except Exception:
                os.startfile(pdf_path)
        except Exception as ex:
            messagebox.showerror("Preview Error", f"Could not generate voucher preview:\n{ex}", parent=self)

    def _on_unlink_voucher(self):
        self.voucher_id = None
        self.voucher_lbl_var.set("None linked (Standalone Check)")
        if hasattr(self, "view_voucher_btn"):
            self.view_voucher_btn.configure(state="disabled")
        self._update_summary()

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

        tid = data["template_id"]
        tmpl = db.get_check_template_by_id(tid)
        comp = db.get_company(self.company_id) or {"name": "Company"}
        signatories = db.get_signatories_for_template(tid)

        data["status"] = "Draft"
        if self.voucher_id:
            v_full = db.get_voucher(self.voucher_id)
            if v_full:
                v = v_full.get("voucher", v_full) if isinstance(v_full, dict) else None
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
            if self.check_id and self._check_data.get("status"):
                data["status"] = self._check_data["status"]
            else:
                data["status"] = "Draft"

        try:
            if self.check_id:
                db.update_check(self.check_id, data, actor=auth_by or current_actor)
                cid = self.check_id
            else:
                cid = db.create_check(data, actor=auth_by or current_actor)
        except Exception as ex:
            messagebox.showerror("Save Error", f"Failed to save check:\n{ex}", parent=self)
            return

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
            try:
                self.on_save()
            except Exception as ex:
                print(f"Notice: on_save callback error: {ex}")
        self.destroy()
