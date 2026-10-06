"""
ui/check_template_dialog.py
Bank Check Template Configuration Dialogs for Voucher Manager v3.0.

Provides:
- CheckTemplateListDialog: Manage bank check templates
- CheckTemplateEditDialog: Configure mm coordinates, stock dimensions, series and signatories
- CalibrationPrintDialog: Generate and preview calibration grid sheet for check stock
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

import database as db
import check_printer
from ui.pdf_viewer import PdfViewerDialog


class CheckTemplateListDialog(ttk.Toplevel):
    """Dialog to list, add, edit, and calibrate check templates."""

    def __init__(self, parent, company_id=1, on_change=None):
        super().__init__(parent)
        self.withdraw()
        self.title("Check Stock Templates")
        self.geometry("750x480")
        self.minsize(650, 400)
        self.transient(parent)
        self.grab_set()

        self.parent = parent
        self.company_id = company_id
        self.on_change = on_change

        self._build_ui()
        self._load_templates()

        self.update_idletasks()
        # Center dialog
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 750
        h = 480
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Header
        hdr_frame = ttk.Frame(container)
        hdr_frame.pack(fill=X, pady=(0, 12))

        ttk.Label(
            hdr_frame,
            text="🏦 Bank Check Templates",
            font=("Segoe UI", 13, "bold"),
            foreground="#1e3a8a"
        ).pack(side=LEFT)

        ttk.Label(
            hdr_frame,
            text="Configure field positions (mm) for pre-printed check leaves",
            font=("Segoe UI", 9),
            foreground="#64748b"
        ).pack(side=LEFT, padx=(12, 0))

        # Toolbar
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=X, pady=(0, 10))

        ttk.Button(
            btn_frame,
            text="+ New Template",
            bootstyle="primary",
            command=self._on_add
        ).pack(side=LEFT, padx=(0, 6))

        ttk.Button(
            btn_frame,
            text="✏ Edit Template",
            bootstyle="secondary-outline",
            command=self._on_edit
        ).pack(side=LEFT, padx=(0, 6))

        ttk.Button(
            btn_frame,
            text="🗑 Delete",
            bootstyle="danger-outline",
            command=self._on_delete
        ).pack(side=LEFT, padx=(0, 6))

        ttk.Button(
            btn_frame,
            text="📐 Calibration Grid Sheet",
            bootstyle="info-outline",
            command=self._on_calibration
        ).pack(side=RIGHT)

        # Treeview table
        columns = ("id", "bank_name", "prefix", "next_num", "size_mm", "signatories")
        self.tree = ttk.Treeview(
            container,
            columns=columns,
            show="headings",
            bootstyle="primary",
            selectmode="browse"
        )
        self.tree.heading("id", text="#")
        self.tree.heading("bank_name", text="Bank Name")
        self.tree.heading("prefix", text="Series Prefix")
        self.tree.heading("next_num", text="Next Check #")
        self.tree.heading("size_mm", text="Dimensions (WxH mm)")
        self.tree.heading("signatories", text="Signatories")

        self.tree.column("id", width=40, anchor=CENTER)
        self.tree.column("bank_name", width=220, anchor=W)
        self.tree.column("prefix", width=90, anchor=CENTER)
        self.tree.column("next_num", width=120, anchor=CENTER)
        self.tree.column("size_mm", width=130, anchor=CENTER)
        self.tree.column("signatories", width=90, anchor=CENTER)

        scrollbar = ttk.Scrollbar(container, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._on_edit())
        self.tree.bind("<Return>", lambda e: self._on_edit())

    def _load_templates(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        templates = db.get_check_templates(self.company_id, active_only=True)
        for t in templates:
            tid = t["id"]
            next_num = db.get_next_check_number(tid)
            sigs = db.get_signatories_for_template(tid)
            sig_text = f"{len(sigs)} active" if sigs else "None"
            size_text = f"{t.get('page_width_mm', 210):.0f} x {t.get('page_height_mm', 88):.0f}"
            self.tree.insert("", END, values=(
                tid,
                t.get("bank_name", ""),
                t.get("check_series_prefix", ""),
                next_num,
                size_text,
                sig_text
            ))

    def _on_add(self):
        dialog = CheckTemplateEditDialog(self, company_id=self.company_id)
        self.wait_window(dialog)
        self._load_templates()
        if self.on_change:
            self.on_change()

    def _on_edit(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Template", "Please select a template to edit.", parent=self)
            return
        item = self.tree.item(sel[0])
        template_id = int(item["values"][0])
        dialog = CheckTemplateEditDialog(self, template_id=template_id, company_id=self.company_id)
        self.wait_window(dialog)
        self._load_templates()
        if self.on_change:
            self.on_change()

    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select Template", "Please select a template to delete.", parent=self)
            return
        item = self.tree.item(sel[0])
        template_id = int(item["values"][0])
        name = item["values"][1]

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to remove check template '{name}'?\n\nIf checks already use this template, it will be deactivated safely without deleting check history.",
            parent=self
        ):
            return

        db.delete_check_template(template_id)
        self._load_templates()
        if self.on_change:
            self.on_change()

    def _on_calibration(self):
        pdf_path = check_printer.generate_calibration_pdf()
        try:
            viewer = PdfViewerDialog(self, pdf_path, title="Check Alignment Calibration Sheet")
            viewer.show()
        except Exception:
            os.startfile(pdf_path)


class CheckTemplateEditDialog(ttk.Toplevel):
    """Add or edit physical check layout parameters in millimeters."""

    def __init__(self, parent, template_id=None, company_id=1):
        super().__init__(parent)
        self.withdraw()
        self.template_id = template_id
        self.company_id = company_id
        self.title("Edit Check Template" if template_id else "New Check Template")
        self.geometry("780x640")
        self.minsize(700, 580)
        self.transient(parent)
        self.grab_set()

        self._template = db.get_check_template_by_id(template_id) if template_id else {}
        self._signatories = db.get_signatories_for_template(template_id) if template_id else []

        self._build_ui()
        self._load_data()

        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        w = 780
        h = 640
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.deiconify()

    def _build_ui(self):
        container = ttk.Frame(self, padding=16)
        container.pack(fill=BOTH, expand=True)

        # Scrollable form canvas
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=VERTICAL, command=lambda *args: (canvas.yview(*args), canvas.update_idletasks()))
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_win = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        # Section 1: Bank & Identity
        sec1 = ttk.Labelframe(self.scrollable_frame, text="Bank & Account Identity", padding=12)
        sec1.pack(fill=X, pady=(0, 10))

        ttk.Label(sec1, text="Bank Name:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.bank_name_var = tk.StringVar(value=self._template.get("bank_name", "Commercial Bank of Ceylon PLC"))
        ttk.Entry(sec1, textvariable=self.bank_name_var, width=35).grid(row=0, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(sec1, text="Branch Name:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.branch_var = tk.StringVar(value=self._template.get("branch_name", ""))
        ttk.Entry(sec1, textvariable=self.branch_var, width=25).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        ttk.Label(sec1, text="Bank Account:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        self.acct_var = tk.StringVar()
        self.acct_combo = ttk.Combobox(sec1, textvariable=self.acct_var, width=33, state="readonly")
        self.acct_combo.grid(row=1, column=1, sticky=W, padx=4, pady=4)
        self._populate_accounts()

        ttk.Label(sec1, text="Account Number:").grid(row=1, column=2, sticky=W, padx=4, pady=4)
        self.acct_no_var = tk.StringVar(value=self._template.get("account_number", ""))
        ttk.Entry(sec1, textvariable=self.acct_no_var, width=25).grid(row=1, column=3, sticky=W, padx=4, pady=4)

        # Section 2: Physical Stock Dimensions
        sec2 = ttk.Labelframe(self.scrollable_frame, text="Check Leaf Dimensions (mm)", padding=12)
        sec2.pack(fill=X, pady=(0, 10))

        ttk.Label(sec2, text="Leaf Width (mm):").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.w_mm_var = tk.DoubleVar(value=float(self._template.get("page_width_mm", 210.0)))
        ttk.Spinbox(sec2, from_=100.0, to=300.0, increment=1.0, textvariable=self.w_mm_var, width=10).grid(row=0, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(sec2, text="Leaf Height (mm):").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.h_mm_var = tk.DoubleVar(value=float(self._template.get("page_height_mm", 88.0)))
        ttk.Spinbox(sec2, from_=50.0, to=200.0, increment=1.0, textvariable=self.h_mm_var, width=10).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        # Section 3: Field Coordinates (mm from bottom-left corner of check leaf)
        sec3 = ttk.Labelframe(self.scrollable_frame, text="Field Coordinates (in mm from bottom-left of check)", padding=12)
        sec3.pack(fill=X, pady=(0, 10))

        # Payee
        ttk.Label(sec3, text="Payee Line:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=0, column=1, sticky=E)
        self.payee_x_var = tk.DoubleVar(value=float(self._template.get("payee_x", 45.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.payee_x_var, width=6).grid(row=0, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=0, column=3, sticky=E)
        self.payee_y_var = tk.DoubleVar(value=float(self._template.get("payee_y", 52.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.payee_y_var, width=6).grid(row=0, column=4, padx=2)
        ttk.Label(sec3, text="Max W:").grid(row=0, column=5, sticky=E)
        self.payee_w_var = tk.DoubleVar(value=float(self._template.get("payee_max_w", 118.0)))
        ttk.Spinbox(sec3, from_=20, to=200, increment=1, textvariable=self.payee_w_var, width=6).grid(row=0, column=6, padx=2)

        # Amount Box
        ttk.Label(sec3, text="Amount Box:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=1, column=1, sticky=E)
        self.amt_x_var = tk.DoubleVar(value=float(self._template.get("amount_box_x", 155.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.amt_x_var, width=6).grid(row=1, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=1, column=3, sticky=E)
        self.amt_y_var = tk.DoubleVar(value=float(self._template.get("amount_box_y", 52.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.amt_y_var, width=6).grid(row=1, column=4, padx=2)
        ttk.Label(sec3, text="Width:").grid(row=1, column=5, sticky=E)
        self.amt_w_var = tk.DoubleVar(value=float(self._template.get("amount_box_w", 42.0)))
        ttk.Spinbox(sec3, from_=10, to=100, increment=1, textvariable=self.amt_w_var, width=6).grid(row=1, column=6, padx=2)

        # Amount in Words
        ttk.Label(sec3, text="Amount Words:").grid(row=2, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=2, column=1, sticky=E)
        self.words_x_var = tk.DoubleVar(value=float(self._template.get("amount_words_x", 10.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.words_x_var, width=6).grid(row=2, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=2, column=3, sticky=E)
        self.words_y_var = tk.DoubleVar(value=float(self._template.get("amount_words_y", 40.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.words_y_var, width=6).grid(row=2, column=4, padx=2)
        ttk.Label(sec3, text="Max W:").grid(row=2, column=5, sticky=E)
        self.words_w_var = tk.DoubleVar(value=float(self._template.get("amount_words_max_w", 168.0)))
        ttk.Spinbox(sec3, from_=20, to=200, increment=1, textvariable=self.words_w_var, width=6).grid(row=2, column=6, padx=2)

        # Date
        ttk.Label(sec3, text="Date Field:").grid(row=3, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=3, column=1, sticky=E)
        self.date_x_var = tk.DoubleVar(value=float(self._template.get("date_x", 156.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.date_x_var, width=6).grid(row=3, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=3, column=3, sticky=E)
        self.date_y_var = tk.DoubleVar(value=float(self._template.get("date_y", 68.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.date_y_var, width=6).grid(row=3, column=4, padx=2)

        # Signatory 1
        ttk.Label(sec3, text="Signatory 1:").grid(row=4, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=4, column=1, sticky=E)
        self.sig1_x_var = tk.DoubleVar(value=float(self._template.get("sig1_x", 115.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.sig1_x_var, width=6).grid(row=4, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=4, column=3, sticky=E)
        self.sig1_y_var = tk.DoubleVar(value=float(self._template.get("sig1_y", 12.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.sig1_y_var, width=6).grid(row=4, column=4, padx=2)

        # Signatory 2
        ttk.Label(sec3, text="Signatory 2:").grid(row=5, column=0, sticky=W, padx=4, pady=4)
        ttk.Label(sec3, text="X:").grid(row=5, column=1, sticky=E)
        self.sig2_x_var = tk.DoubleVar(value=float(self._template.get("sig2_x", 157.0)))
        ttk.Spinbox(sec3, from_=0, to=210, increment=1, textvariable=self.sig2_x_var, width=6).grid(row=5, column=2, padx=2)
        ttk.Label(sec3, text="Y:").grid(row=5, column=3, sticky=E)
        self.sig2_y_var = tk.DoubleVar(value=float(self._template.get("sig2_y", 12.0)))
        ttk.Spinbox(sec3, from_=0, to=150, increment=1, textvariable=self.sig2_y_var, width=6).grid(row=5, column=4, padx=2)

        # Section 4: Series & Numbering
        sec4 = ttk.Labelframe(self.scrollable_frame, text="Check Series & Numbering", padding=12)
        sec4.pack(fill=X, pady=(0, 10))

        ttk.Label(sec4, text="Series Prefix:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.prefix_var = tk.StringVar(value=self._template.get("check_series_prefix", "CB-"))
        ttk.Entry(sec4, textvariable=self.prefix_var, width=10).grid(row=0, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(sec4, text="Starting #:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.start_num_var = tk.IntVar(value=int(self._template.get("check_series_start", 1)))
        ttk.Spinbox(sec4, from_=1, to=999999, textvariable=self.start_num_var, width=10).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        self.print_comp_var = tk.IntVar(value=int(self._template.get("print_company_name", 1)))
        ttk.Checkbutton(sec4, text="Print Company Name on Check", variable=self.print_comp_var).grid(row=1, column=0, columnspan=2, sticky=W, padx=4, pady=4)

        # Section 5: Signatories
        sec5 = ttk.Labelframe(self.scrollable_frame, text="Authorized Signatories", padding=12)
        sec5.pack(fill=X, pady=(0, 10))

        # Signatory 1
        ttk.Label(sec5, text="Signatory 1 Name:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        sig1 = self._signatories[0] if len(self._signatories) > 0 else {}
        self.sig1_name_var = tk.StringVar(value=sig1.get("name", ""))
        ttk.Entry(sec5, textvariable=self.sig1_name_var, width=28).grid(row=0, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(sec5, text="Title:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.sig1_title_var = tk.StringVar(value=sig1.get("title", ""))
        ttk.Entry(sec5, textvariable=self.sig1_title_var, width=22).grid(row=0, column=3, sticky=W, padx=4, pady=4)

        # Signatory 2
        ttk.Label(sec5, text="Signatory 2 Name:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        sig2 = self._signatories[1] if len(self._signatories) > 1 else {}
        self.sig2_name_var = tk.StringVar(value=sig2.get("name", ""))
        ttk.Entry(sec5, textvariable=self.sig2_name_var, width=28).grid(row=1, column=1, sticky=W, padx=4, pady=4)

        ttk.Label(sec5, text="Title:").grid(row=1, column=2, sticky=W, padx=4, pady=4)
        self.sig2_title_var = tk.StringVar(value=sig2.get("title", ""))
        ttk.Entry(sec5, textvariable=self.sig2_title_var, width=22).grid(row=1, column=3, sticky=W, padx=4, pady=4)

        # Action Buttons
        act_frame = ttk.Frame(self.scrollable_frame)
        act_frame.pack(fill=X, pady=(10, 0))

        ttk.Button(act_frame, text="Save Template", bootstyle="success", command=self._on_save).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(act_frame, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=RIGHT)

    def _populate_accounts(self):
        try:
            accounts = db.get_bank_accounts(self.company_id)
            vals = []
            self._acct_map = {}
            for a in accounts:
                lbl = f"{a['account_name']} ({a.get('account_number', '')})"
                vals.append(lbl)
                self._acct_map[lbl] = a["id"]
            self.acct_combo["values"] = vals
            if self._template.get("account_id"):
                for lbl, aid in self._acct_map.items():
                    if aid == self._template["account_id"]:
                        self.acct_var.set(lbl)
                        break
        except Exception:
            pass

    def _load_data(self):
        pass

    def _on_save(self):
        bname = self.bank_name_var.get().strip()
        if not bname:
            messagebox.showerror("Validation Error", "Bank name is required.", parent=self)
            return

        aid = self._acct_map.get(self.acct_var.get())

        data = {
            "company_id": self.company_id,
            "bank_name": bname,
            "account_id": aid,
            "account_number": self.acct_no_var.get().strip(),
            "branch_name": self.branch_var.get().strip(),
            "page_width_mm": float(self.w_mm_var.get()),
            "page_height_mm": float(self.h_mm_var.get()),
            "payee_x": float(self.payee_x_var.get()),
            "payee_y": float(self.payee_y_var.get()),
            "payee_max_w": float(self.payee_w_var.get()),
            "amount_box_x": float(self.amt_x_var.get()),
            "amount_box_y": float(self.amt_y_var.get()),
            "amount_box_w": float(self.amt_w_var.get()),
            "amount_words_x": float(self.words_x_var.get()),
            "amount_words_y": float(self.words_y_var.get()),
            "amount_words_max_w": float(self.words_w_var.get()),
            "date_x": float(self.date_x_var.get()),
            "date_y": float(self.date_y_var.get()),
            "sig1_x": float(self.sig1_x_var.get()),
            "sig1_y": float(self.sig1_y_var.get()),
            "sig2_x": float(self.sig2_x_var.get()),
            "sig2_y": float(self.sig2_y_var.get()),
            "check_series_prefix": self.prefix_var.get().strip(),
            "check_series_start": int(self.start_num_var.get()),
            "print_company_name": int(self.print_comp_var.get()),
            "is_active": 1
        }

        if self.template_id:
            db.update_check_template(self.template_id, data)
            tid = self.template_id
        else:
            tid = db.create_check_template(data)

        # Save signatories
        sig1_name = self.sig1_name_var.get().strip()
        sig2_name = self.sig2_name_var.get().strip()
        if tid:
            # Clear old signatories and recreate
            sigs = db.get_signatories_for_template(tid)
            for s in sigs:
                db.delete_signatory(s["id"])

            if sig1_name:
                db.save_signatory(tid, sig1_name, self.sig1_title_var.get().strip(), signatory_order=1)
            if sig2_name:
                db.save_signatory(tid, sig2_name, self.sig2_title_var.get().strip(), signatory_order=2)

        self.destroy()
