"""
ui/check_register.py
Check Register & Management Module for Voucher Manager v3.0.

Provides:
- CheckRegisterFrame: Complete Check Register list view with filtering,
  lifecycle state transitions, batch printing, bounce recording, voiding,
  and CSV export.
"""

import os
import csv
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

import database as db
import check_printer
import printer
from ui.check_dialog import CheckEntryDialog, CheckBounceDialog, CheckAuthDialog
from ui.check_template_dialog import CheckTemplateListDialog
from ui.pdf_viewer import PdfViewerDialog


class CheckRegisterFrame(ttk.Frame):
    """Check Register List View & Management Console."""

    STATUS_COLORS = {
        "Draft": "#94a3b8",
        "Issued": "#2563eb",
        "Presented": "#f59e0b",
        "Cleared": "#16a34a",
        "Bounced": "#dc2626",
        "Voided": "#6b7280",
        "Post-Dated": "#7c3aed"
    }

    def __init__(self, parent, company_id=1, **kwargs):
        super().__init__(parent, **kwargs)
        self.company_id = company_id
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        container = ttk.Frame(self, padding=12)
        container.pack(fill=BOTH, expand=True)

        # 1. Top Header & KPI Summary Cards
        kpi_row = ttk.Frame(container)
        kpi_row.pack(fill=X, pady=(0, 10))

        self.card_issued = self._create_kpi_card(kpi_row, "Issued / Outstanding", "0.00", "#2563eb")
        self.card_presented = self._create_kpi_card(kpi_row, "Presented at Bank", "0.00", "#f59e0b")
        self.card_cleared = self._create_kpi_card(kpi_row, "Cleared / Settled", "0.00", "#16a34a")
        self.card_post_dated = self._create_kpi_card(kpi_row, "Post-Dated", "0.00", "#7c3aed")
        self.card_bounced = self._create_kpi_card(kpi_row, "Bounced", "0.00", "#dc2626")

        # 2. Filter Bar
        filter_bar = ttk.Labelframe(container, text="Filters & Search", padding=8)
        filter_bar.pack(fill=X, pady=(0, 10))

        # Search box
        ttk.Label(filter_bar, text="Search:").pack(side=LEFT, padx=(4, 4))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_bar, textvariable=self.search_var, width=22)
        search_entry.pack(side=LEFT, padx=(0, 12))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh())

        # Status filter
        ttk.Label(filter_bar, text="Status:").pack(side=LEFT, padx=(0, 4))
        self.status_var = tk.StringVar(value="All Statuses")
        statuses = ["All Statuses", "Draft", "Issued", "Presented", "Cleared", "Bounced", "Voided", "Post-Dated"]
        status_combo = ttk.Combobox(filter_bar, textvariable=self.status_var, values=statuses, width=13, state="readonly")
        status_combo.pack(side=LEFT, padx=(0, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Bank Template filter
        ttk.Label(filter_bar, text="Bank:").pack(side=LEFT, padx=(0, 4))
        self.bank_filter_var = tk.StringVar(value="All Banks")
        self.bank_combo = ttk.Combobox(filter_bar, textvariable=self.bank_filter_var, width=18, state="readonly")
        self.bank_combo.pack(side=LEFT, padx=(0, 12))
        self.bank_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        # Refresh button
        ttk.Button(filter_bar, text="🔄 Reset Filters", bootstyle="secondary-outline", command=self._reset_filters).pack(side=RIGHT)

        # 3. Action Toolbar
        toolbar = ttk.Frame(container)
        toolbar.pack(fill=X, pady=(0, 8))

        ttk.Button(toolbar, text="+ New Check", bootstyle="primary", command=self._on_new_check).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="👁 View Voucher", bootstyle="info-outline", command=self._on_view_linked_voucher).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="🖨 Print / Preview", bootstyle="success-outline", command=self._on_print_check).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="🏛 Mark Presented", bootstyle="warning-outline", command=self._on_mark_presented).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="✅ Mark Cleared", bootstyle="success", command=self._on_mark_cleared).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="⚠️ Record Bounce", bootstyle="danger-outline", command=self._on_record_bounce).pack(side=LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="🚫 Void Check", bootstyle="secondary", command=self._on_void_check).pack(side=LEFT, padx=(0, 6))

        ttk.Button(toolbar, text="⚙ Check Templates", bootstyle="info-outline", command=self._on_manage_templates).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(toolbar, text="📥 Export CSV", bootstyle="secondary-outline", command=self._on_export_csv).pack(side=RIGHT)

        # 4. Table view
        table_frame = ttk.Frame(container)
        table_frame.pack(fill=BOTH, expand=True)

        cols = ("id", "check_num", "bank", "date", "post_date", "payee", "amount", "status", "voucher", "printed")
        self.tree = ttk.Treeview(
            table_frame,
            columns=cols,
            show="headings",
            bootstyle="primary",
            selectmode="extended"
        )

        self.tree.heading("id", text="#")
        self.tree.heading("check_num", text="Check #")
        self.tree.heading("bank", text="Bank / Leaf")
        self.tree.heading("date", text="Check Date")
        self.tree.heading("post_date", text="Post-Dated")
        self.tree.heading("payee", text="Payee")
        self.tree.heading("amount", text="Amount")
        self.tree.heading("status", text="Status")
        self.tree.heading("voucher", text="Voucher Ref")
        self.tree.heading("printed", text="Printed")

        self.tree.column("id", width=40, anchor=CENTER)
        self.tree.column("check_num", width=110, anchor=CENTER)
        self.tree.column("bank", width=160, anchor=W)
        self.tree.column("date", width=95, anchor=CENTER)
        self.tree.column("post_date", width=95, anchor=CENTER)
        self.tree.column("payee", width=220, anchor=W)
        self.tree.column("amount", width=115, anchor=E)
        self.tree.column("status", width=95, anchor=CENTER)
        self.tree.column("voucher", width=110, anchor=CENTER)
        self.tree.column("printed", width=75, anchor=CENTER)

        # Configure status row tags for styling
        for st, color in self.STATUS_COLORS.items():
            self.tree.tag_configure(f"status_{st}", foreground=color)

        v_scroll = ttk.Scrollbar(table_frame, orient=VERTICAL, command=lambda *a: (self.tree.yview(*a), self.tree.update_idletasks()))
        self.tree.configure(yscrollcommand=v_scroll.set)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        v_scroll.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._on_edit_check())
        self.tree.bind("<Return>", lambda e: self._on_edit_check())
        self.tree.bind("<KP_Enter>", lambda e: self._on_edit_check())
        self.tree.bind("<Delete>", lambda e: self._on_void_check())

        # Context menu
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="✏️ Edit Check", command=self._on_edit_check)
        self._context_menu.add_command(label="👁️ View Linked Voucher (PDF)", command=self._on_view_linked_voucher)
        self._context_menu.add_command(label="🖨️ Print Check", command=self._on_print_check)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="🏛️ Mark Presented", command=self._on_mark_presented)
        self._context_menu.add_command(label="✅ Mark Cleared", command=self._on_mark_cleared)
        self._context_menu.add_command(label="⚠️ Record Bounce", command=self._on_record_bounce)
        self._context_menu.add_command(label="🚫 Void Check", command=self._on_void_check)

        def _on_right_click(event):
            row_id = self.tree.identify_row(event.y)
            if row_id:
                if row_id not in self.tree.selection():
                    self.tree.selection_set(row_id)
                self._context_menu.post(event.x_root, event.y_root)

        self.tree.bind("<Button-3>", _on_right_click)

    def _create_kpi_card(self, parent, title, val, color):
        frame = ttk.Frame(parent, bootstyle="light", padding=(10, 6))
        frame.pack(side=LEFT, fill=X, expand=True, padx=3)

        ttk.Label(frame, text=title, font=("Segoe UI", 8), foreground="#64748b").pack(anchor=W)
        val_lbl = ttk.Label(frame, text=val, font=("Segoe UI", 11, "bold"), foreground=color)
        val_lbl.pack(anchor=W)
        return val_lbl

    def _reset_filters(self):
        self.search_var.set("")
        self.status_var.set("All Statuses")
        self.bank_filter_var.set("All Banks")
        self.refresh()

    def refresh(self):
        # Refresh bank filter options
        templates = db.get_check_templates(self.company_id, active_only=True)
        self._tmpl_filter_map = {"All Banks": None}
        b_names = ["All Banks"]
        for t in templates:
            b_names.append(t["bank_name"])
            self._tmpl_filter_map[t["bank_name"]] = t["id"]
        self.bank_combo["values"] = b_names

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        filters = {}
        st = self.status_var.get()
        if st == "Post-Dated":
            filters["post_dated_only"] = True
        elif st != "All Statuses":
            filters["status"] = st

        b_sel = self.bank_filter_var.get()
        if b_sel != "All Banks" and self._tmpl_filter_map.get(b_sel):
            filters["template_id"] = self._tmpl_filter_map[b_sel]

        q = self.search_var.get().strip()
        if q:
            filters["payee_query"] = q

        checks = db.get_checks(self.company_id, filters=filters)

        # Totals for KPIs
        tot_issued = 0.0
        tot_presented = 0.0
        tot_cleared = 0.0
        tot_post_dated = 0.0
        tot_bounced = 0.0

        for c in checks:
            cid = c["id"]
            amt = float(c.get("amount", 0.0))
            c_status = c.get("status", "Draft")

            if c_status == "Issued":
                tot_issued += amt
            elif c_status == "Presented":
                tot_presented += amt
            elif c_status == "Cleared":
                tot_cleared += amt
            elif c_status == "Bounced":
                tot_bounced += amt

            if c.get("post_date"):
                tot_post_dated += amt

            printed_str = "Yes" if c.get("printed") else "No"
            curr = c.get("currency", "LKR")
            amt_str = f"{curr} {amt:,.2f}"

            tag = f"status_{c_status}"
            self.tree.insert("", END, values=(
                cid,
                c.get("check_number", ""),
                c.get("bank_name", ""),
                c.get("check_date", ""),
                c.get("post_date", "-") or "-",
                c.get("payee_name", ""),
                amt_str,
                c_status.upper(),
                c.get("voucher_number", "-") or "-",
                printed_str
            ), tags=(tag,))

        # Update KPI labels
        self.card_issued.configure(text=f"LKR {tot_issued:,.2f}")
        self.card_presented.configure(text=f"LKR {tot_presented:,.2f}")
        self.card_cleared.configure(text=f"LKR {tot_cleared:,.2f}")
        self.card_post_dated.configure(text=f"LKR {tot_post_dated:,.2f}")
        self.card_bounced.configure(text=f"LKR {tot_bounced:,.2f}")

    def _get_selected_ids(self):
        sel = self.tree.selection()
        ids = []
        for s in sel:
            item = self.tree.item(s)
            ids.append(int(item["values"][0]))
        return ids

    def _on_new_check(self):
        dialog = CheckEntryDialog(self, company_id=self.company_id, on_save=self.refresh)

    def _on_edit_check(self):
        ids = self._get_selected_ids()
        if not ids:
            return
        cid = ids[0]
        dialog = CheckEntryDialog(self, check_id=cid, company_id=self.company_id, on_save=self.refresh)

    def _on_print_check(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select one or more checks to print.", parent=self)
            return

        pdf_path = check_printer.generate_check_pdf(ids, include_stub=True)
        # Mark printed for each
        for cid in ids:
            db.mark_check_printed(cid, actor="User")
        self.refresh()

        try:
            viewer = PdfViewerDialog(self, pdf_path, title=f"Print Check Run ({len(ids)} checks)")
            viewer.show()
        except Exception:
            os.startfile(pdf_path)

    def _on_view_linked_voucher(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select a check to view its linked voucher.", parent=self)
            return
        cid = ids[0]
        chk = db.get_check_by_id(cid)
        if not chk or not chk.get("voucher_id"):
            messagebox.showinfo("No Linked Voucher", "The selected check is not linked to any voucher.", parent=self)
            return
        vid = chk["voucher_id"]
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

    def _on_mark_presented(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select check(s) to mark as presented to bank.", parent=self)
            return

        for cid in ids:
            db.update_check_status(cid, "Presented", actor="User", note="Marked presented in register")
        self.refresh()
        messagebox.showinfo("Updated", f"{len(ids)} check(s) marked as Presented.", parent=self)

    def _on_mark_cleared(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select check(s) to mark as cleared by bank.", parent=self)
            return

        for cid in ids:
            db.update_check_status(cid, "Cleared", actor="User", note="Bank settlement confirmed")
        self.refresh()
        messagebox.showinfo("Cleared", f"{len(ids)} check(s) marked as Cleared.", parent=self)

    def _on_record_bounce(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select a check to record bounce.", parent=self)
            return
        cid = ids[0]
        dialog = CheckBounceDialog(self, check_id=cid, on_success=self.refresh)

    def _on_void_check(self):
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Check", "Please select a check to void.", parent=self)
            return
        cid = ids[0]
        chk = db.get_check_by_id(cid)
        if not chk:
            return

        if chk.get("status") == "Cleared":
            messagebox.showerror("Cannot Void", "Cleared checks cannot be voided as funds have already settled.", parent=self)
            return
        if chk.get("status") == "Voided":
            messagebox.showinfo("Notice", "Check is already voided.", parent=self)
            return

        # Requires Manager PIN authorization
        auth = CheckAuthDialog(self, action_desc=f"VOID check {chk.get('check_number', '')}")
        self.wait_window(auth)
        if not auth.authorized:
            return

        reason = simpledialog.askstring("Void Reason", "Enter reason for voiding this check:", parent=self)
        if reason is None:
            return

        ok, msg = db.void_check(cid, actor=auth.authorized_by, reason=reason.strip() or "Voided by manager")
        if ok:
            messagebox.showinfo("Voided", msg, parent=self)
            self.refresh()
        else:
            messagebox.showerror("Error", msg, parent=self)

    def _on_manage_templates(self):
        dialog = CheckTemplateListDialog(self, company_id=self.company_id, on_change=self.refresh)

    def _on_export_csv(self):
        checks = db.get_checks(self.company_id)
        if not checks:
            messagebox.showinfo("No Data", "No checks found to export.", parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            initialfile=f"Check_Register_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Check Number", "Bank Name", "Check Date", "Post Date",
                    "Payee", "Amount", "Currency", "Status", "Voucher Number",
                    "Printed", "Cleared Date", "Bounce Reason", "Memo", "Payment Ref"
                ])
                for c in checks:
                    def _sanitize(val):
                        s = str(val or "")
                        if s and s[0] in ("=", "+", "-", "@"):
                            return f"'{s}"
                        return s

                    writer.writerow([
                        _sanitize(c.get("check_number")),
                        _sanitize(c.get("bank_name")),
                        _sanitize(c.get("check_date")),
                        _sanitize(c.get("post_date")),
                        _sanitize(c.get("payee_name")),
                        f"{c.get('amount', 0):.2f}",
                        c.get("currency", "LKR"),
                        c.get("status", ""),
                        _sanitize(c.get("voucher_number")),
                        "Yes" if c.get("printed") else "No",
                        _sanitize(c.get("cleared_date")),
                        _sanitize(c.get("bounce_reason")),
                        _sanitize(c.get("memo")),
                        _sanitize(c.get("payment_ref"))
                    ])
            messagebox.showinfo("Export Successful", f"Exported {len(checks)} check records to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not write CSV file:\n{e}", parent=self)
