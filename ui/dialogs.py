"""
Dialog windows for the Voucher Printing Tool.
- Confirmation dialogs
- Attachment preview
- Print options
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap import ToolTip
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import os
import io


def confirm_cancel(parent, voucher_number):
    """Show confirmation dialog for cancelling a voucher."""
    return messagebox.askyesno(
        "Cancel Voucher",
        f"Are you sure you want to cancel voucher {voucher_number}?\n\n"
        "This will mark the voucher as cancelled.\n"
        "It can be restored later if needed.",
        parent=parent,
        icon="warning"
    )


def confirm_restore(parent, voucher_number):
    """Show confirmation dialog for restoring a cancelled voucher."""
    return messagebox.askyesno(
        "Restore Voucher",
        f"Restore voucher {voucher_number} back to Active status?",
        parent=parent,
    )


def select_attachments(parent):
    """
    Open a file dialog to select attachment files.
    Returns list of (filename, file_data, file_type) tuples.
    """
    filepaths = filedialog.askopenfilenames(
        parent=parent,
        title="Select Attachment(s)",
        filetypes=[
            ("Images", "*.jpg *.jpeg *.png *.bmp *.gif"),
            ("PDF Files", "*.pdf"),
            ("All Files", "*.*"),
        ]
    )

    attachments = []
    for fp in filepaths:
        filename = os.path.basename(fp)
        ext = os.path.splitext(filename)[1].lower()

        image_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        if ext in image_types:
            file_type = image_types[ext]
        else:
            # If attachment is not an image, assume it is a PDF document
            file_type = "application/pdf"

        try:
            with open(fp, "rb") as f:
                file_data = f.read()
            attachments.append({
                "filename": filename,
                "file_data": file_data,
                "file_type": file_type,
            })
        except Exception as e:
            messagebox.showerror(
                "Attachment Error",
                f"Could not read file: {filename}\n{str(e)}",
                parent=parent
            )

    return attachments


class AttachmentPreviewDialog(tk.Toplevel):
    """Dialog to preview an image or PDF attachment."""

    def __init__(self, parent, filename, file_data, file_type):
        super().__init__(parent)
        self.title(f"Attachment: {filename}")
        self.geometry("700x580")
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=filename, font=("Segoe UI", 11, "bold")).pack(pady=(10, 5))

        is_image = bool(file_type and file_type.startswith("image/"))
        previewed = False

        if is_image:
            try:
                from PIL import Image, ImageTk
                img = Image.open(io.BytesIO(file_data))

                # Resize to fit
                max_w, max_h = 650, 450
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

                self._photo = ImageTk.PhotoImage(img)
                label = ttk.Label(self, image=self._photo)
                label.pack(padx=10, pady=10)
                previewed = True
            except Exception as e:
                ttk.Label(self, text=f"Cannot preview: {str(e)}").pack(pady=20)
        else:
            # Non-image attachment: assume PDF and render preview
            try:
                import pypdfium2 as pdfium
                from PIL import Image, ImageTk
                doc = pdfium.PdfDocument(file_data)
                page_count = len(doc)
                if page_count > 0:
                    page = doc[0]
                    pil_img = page.render(scale=1.5).to_pil()
                    max_w, max_h = 650, 420
                    pil_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    self._photo = ImageTk.PhotoImage(pil_img)
                    label = ttk.Label(self, image=self._photo)
                    label.pack(padx=10, pady=6)

                    info_text = f"📄 PDF Document ({page_count} page{'s' if page_count != 1 else ''})"
                    ttk.Label(self, text=info_text, font=("Segoe UI", 9, "bold"), bootstyle="info").pack(pady=(0, 4))
                    previewed = True
            except Exception:
                pass

        if not previewed and not is_image:
            ttk.Label(
                self,
                text=f"PDF Document Attachment\n\nFile: {filename}\nSize: {len(file_data):,} bytes",
                font=("Segoe UI", 10),
                justify="center"
            ).pack(pady=40)

        btn_row = ttk.Frame(self)
        btn_row.pack(pady=10)

        if not is_image:
            ttk.Button(
                btn_row, text="📄 Open in PDF Viewer",
                command=lambda: self._open_in_viewer(filename, file_data),
                bootstyle="primary-outline"
            ).pack(side=tk.LEFT, padx=6)

        ttk.Button(btn_row, text="Close", command=self.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=6)

    def _open_in_viewer(self, filename, file_data):
        """Open the PDF attachment in the application's built-in PDF viewer."""
        try:
            import tempfile
            from ui.pdf_viewer import PdfViewerDialog
            temp_path = os.path.join(tempfile.gettempdir(), f"preview_{os.path.basename(filename)}")
            with open(temp_path, "wb") as f:
                f.write(file_data)
            PdfViewerDialog(self.master, temp_path, title=f"Attachment: {filename}")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Could not open PDF viewer: {e}", parent=self)


class PrintOptionsDialog(tk.Toplevel):
    """Dialog to select print options."""

    def __init__(self, parent, vouchers, callback):
        super().__init__(parent)
        self.title("Print Options")
        self.geometry("500x450")
        self.transient(parent)
        self.grab_set()
        self._callback = callback
        self._vouchers = vouchers
        self._check_vars = {}

        ttk.Label(
            self, text="Select Vouchers to Print",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(15, 10))

        # Voucher list with checkboxes
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        inner_frame = ttk.Frame(canvas)

        inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for v in vouchers:
            var = tk.BooleanVar(value=True)
            var.trace_add("write", lambda *args: self._update_button_states())
            self._check_vars[v["id"]] = var

            status_text = " [CANCELLED]" if v.get("status") == "Cancelled" else ""
            cb = ttk.Checkbutton(
                inner_frame,
                text=f"{v['voucher_number']}  |  {v['date']}  |  {v['paid_to']}  |  {v['total_amount']:,.2f}{status_text}",
                variable=var,
            )
            cb.pack(fill=tk.X, padx=5, pady=2, anchor="w")

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=15, pady=15)

        ttk.Button(
            btn_frame, text="Select All",
            command=lambda: self._set_all(True),
            bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            btn_frame, text="Deselect All",
            command=lambda: self._set_all(False),
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=5)

        self._preview_btn = ttk.Button(
            btn_frame, text="Preview PDF",
            command=lambda: self._on_action("preview"),
            bootstyle="info"
        )
        self._preview_btn.pack(side=tk.RIGHT, padx=5)
        ToolTip(self._preview_btn, text="Preview selected voucher PDF (Requires at least 1 selected)")

        self._print_btn = ttk.Button(
            btn_frame, text="Print",
            command=lambda: self._on_action("print"),
            bootstyle="success"
        )
        self._print_btn.pack(side=tk.RIGHT, padx=5)
        ToolTip(self._print_btn, text="Send selected vouchers to printer (Requires at least 1 selected)")

        ttk.Button(
            btn_frame, text="Cancel",
            command=self.destroy,
            bootstyle="secondary"
        ).pack(side=tk.RIGHT, padx=5)

        self._update_button_states()

    def _update_button_states(self):
        """Enable or disable print/preview action buttons based on voucher selection."""
        any_selected = any(var.get() for var in self._check_vars.values())
        state = tk.NORMAL if any_selected else tk.DISABLED
        if hasattr(self, "_preview_btn") and self._preview_btn:
            self._preview_btn.config(state=state)
        if hasattr(self, "_print_btn") and self._print_btn:
            self._print_btn.config(state=state)

    def _set_all(self, state):
        for var in self._check_vars.values():
            var.set(state)
        self._update_button_states()

    def _on_action(self, action):
        selected_ids = [vid for vid, var in self._check_vars.items() if var.get()]
        if not selected_ids:
            messagebox.showwarning("No Selection", "Please select at least one voucher.", parent=self)
            return
        self.destroy()
        self._callback(selected_ids, action)


class ClearVouchersDialog(tk.Toplevel):
    """
    Password-protected modal dialog to permanently clear vouchers.
    Requires administrator password.
    Allows clearing active company only or all companies (entire database).
    """

    def __init__(self, parent, on_success_callback=None):
        super().__init__(parent)
        self.title("🔒 Password Protected: Clear Vouchers")
        self.resizable(False, False)
        self.geometry("480x370")
        self.transient(parent)
        self.grab_set()

        self._on_success = on_success_callback
        self._scope_var = tk.StringVar(value="all")
        self._pwd_var = tk.StringVar()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self._pwd_entry.focus_set()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._submit())

    def _build_ui(self):
        # 1. Header Banner with Warning Icon
        top_banner = tk.Frame(self, bg="#fee2e2", padx=16, pady=12)
        top_banner.pack(fill=tk.X)

        tk.Label(
            top_banner, text="⚠️ DANGER ZONE: CLEAR VOUCHERS",
            font=("Segoe UI", 11, "bold"), bg="#fee2e2", fg="#991b1b"
        ).pack(anchor="w")

        tk.Label(
            top_banner,
            text="Permanently deletes vouchers, line items, attachments, and memos.\nThis operation CANNOT be reversed or undone.",
            font=("Segoe UI", 8), bg="#fee2e2", fg="#7f1d1d", justify=tk.LEFT
        ).pack(anchor="w", pady=(2, 0))

        # 2. Body Frame
        body = ttk.Frame(self, padding=(20, 16))
        body.pack(fill=tk.BOTH, expand=True)

        # Scope Selection
        import database as db
        active_id = db.get_active_company_id()
        comp = db.get_company(active_id) or {}
        comp_name = comp.get("name", f"Company {active_id}")

        ttk.Label(body, text="Select Deletion Scope:", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

        rb1 = ttk.Radiobutton(
            body,
            text="Clear ALL Vouchers across ALL Companies (Entire Database Wipe)",
            variable=self._scope_var,
            value="all"
        )
        rb1.pack(anchor="w", pady=2)

        rb2 = ttk.Radiobutton(
            body,
            text=f"Clear Vouchers for Current Company Only ({comp_name})",
            variable=self._scope_var,
            value="active"
        )
        rb2.pack(anchor="w", pady=2)

        ttk.Separator(body).pack(fill=tk.X, pady=12)

        # Password Entry
        ttk.Label(
            body, text="Enter Administrator Password:",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 4))

        pwd_frame = ttk.Frame(body)
        pwd_frame.pack(fill=tk.X)

        self._pwd_entry = ttk.Entry(
            pwd_frame, textvariable=self._pwd_var, show="*",
            font=("Segoe UI", 11), width=28
        )
        self._pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._err_lbl = tk.Label(
            body, text="", font=("Segoe UI", 8, "bold"), fg="#dc2626"
        )
        self._err_lbl.pack(anchor="w", pady=(4, 0))

        # 3. Action Buttons
        btn_frame = ttk.Frame(self, padding=(16, 12))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            btn_frame, text="🗑️ Permanently Delete Vouchers",
            command=self._submit, bootstyle="danger"
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btn_frame, text="Cancel (Esc)",
            command=self.destroy, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT)

    def _submit(self):
        import database as db
        entered = self._pwd_var.get().strip()

        if not entered:
            self._err_lbl.config(text="Please enter the administrator password.")
            self._pwd_entry.focus_set()
            return

        if not db.verify_admin_password(entered):
            self._err_lbl.config(text="❌ Incorrect password. Access denied.")
            self._pwd_entry.delete(0, tk.END)
            self._pwd_entry.focus_set()
            messagebox.showerror("Access Denied", "Incorrect administrator password.\nVoucher deletion aborted.", parent=self)
            return

        # Double confirmation
        scope = self._scope_var.get()
        active_id = db.get_active_company_id() if scope == "active" else None
        scope_text = "for CURRENT COMPANY ONLY" if scope == "active" else "for ALL COMPANIES (ENTIRE DATABASE)"

        if not messagebox.askyesno(
            "Final Confirmation",
            f"Are you ABSOLUTELY SURE you want to delete all vouchers {scope_text}?\n\nThis will destroy all voucher records, line items, and attachments!",
            parent=self,
            icon="warning"
        ):
            return

        try:
            db.clear_all_vouchers(company_id=active_id)
            self.destroy()
            if self._on_success:
                self._on_success(scope)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear vouchers:\n{e}", parent=self)


class DeleteDisabledVoucherDialog(tk.Toplevel):
    """
    Password-protected modal dialog to permanently delete specific disabled/cancelled vouchers.
    Requires administrator password.
    """

    def __init__(self, parent, vouchers, on_success_callback=None):
        super().__init__(parent)
        self.title("🔒 Password Required: Delete Disabled Voucher")
        self.resizable(False, False)
        self.geometry("490x360")
        self.transient(parent)
        self.grab_set()

        self._vouchers = vouchers  # list of voucher dicts
        self._on_success = on_success_callback
        self._pwd_var = tk.StringVar()

        self._build_ui()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self._pwd_entry.focus_set()

        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._submit())

    def _build_ui(self):
        # 1. Header Banner
        top_banner = tk.Frame(self, bg="#fee2e2", padx=16, pady=12)
        top_banner.pack(fill=tk.X)

        tk.Label(
            top_banner, text="🗑️ PERMANENTLY DELETE DISABLED VOUCHER",
            font=("Segoe UI", 11, "bold"), bg="#fee2e2", fg="#991b1b"
        ).pack(anchor="w")

        v_nums = [v["voucher_number"] for v in self._vouchers]
        display_nums = ", ".join(v_nums[:4])
        if len(v_nums) > 4:
            display_nums += f" and {len(v_nums) - 4} more"

        tk.Label(
            top_banner,
            text=f"Target: {display_nums}\nPermanently deletes records and all attached files.",
            font=("Segoe UI", 8), bg="#fee2e2", fg="#7f1d1d", justify=tk.LEFT
        ).pack(anchor="w", pady=(2, 0))

        # 2. Body Frame
        body = ttk.Frame(self, padding=(20, 16))
        body.pack(fill=tk.BOTH, expand=True)

        # Voucher details preview card
        info_frame = tk.Frame(body, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=10, pady=8)
        info_frame.pack(fill=tk.X, pady=(0, 12))

        count_txt = f"{len(self._vouchers)} disabled / cancelled voucher(s) selected for deletion."
        tk.Label(info_frame, text=count_txt, font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#0f172a").pack(anchor="w")
        tk.Label(
            info_frame,
            text="⚠️ Warning: This action cannot be undone. Only disabled vouchers can be deleted.",
            font=("Segoe UI", 8), bg="#f8fafc", fg="#b45309"
        ).pack(anchor="w", pady=(2, 0))

        # Password Entry
        ttk.Label(
            body, text="Enter Administrator Password to Confirm:",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 4))

        pwd_frame = ttk.Frame(body)
        pwd_frame.pack(fill=tk.X)

        self._pwd_entry = ttk.Entry(
            pwd_frame, textvariable=self._pwd_var, show="*",
            font=("Segoe UI", 11), width=28
        )
        self._pwd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._err_lbl = tk.Label(
            body, text="", font=("Segoe UI", 8, "bold"), fg="#dc2626"
        )
        self._err_lbl.pack(anchor="w", pady=(4, 0))

        # 3. Action Buttons
        btn_frame = ttk.Frame(self, padding=(16, 12))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            btn_frame, text="🗑️ Delete Permanently",
            command=self._submit, bootstyle="danger"
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btn_frame, text="Cancel (Esc)",
            command=self.destroy, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT)

    def _submit(self):
        import database as db
        entered = self._pwd_var.get().strip()

        if not entered:
            self._err_lbl.config(text="Please enter the administrator password.")
            self._pwd_entry.focus_set()
            return

        if not db.verify_admin_password(entered):
            self._err_lbl.config(text="❌ Incorrect password. Access denied.")
            self._pwd_entry.delete(0, tk.END)
            self._pwd_entry.focus_set()
            messagebox.showerror("Access Denied", "Incorrect administrator password.\nVoucher deletion aborted.", parent=self)
            return

        try:
            for v in self._vouchers:
                db.permanently_delete_voucher(v["id"])

            self.destroy()
            if self._on_success:
                self._on_success(self._vouchers)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete voucher:\n{e}", parent=self)


# ==============================================================================
# Version History & Changelog Registry
# ==============================================================================

VERSION_HISTORY = [
    {
        "version": "1.3.0",
        "date": "2026-09-26",
        "badge": "LATEST",
        "features": [
            "Petty Cash & Money Float Manager: Multi-float drawer tracking with opening balance, top-ups/inflows, outflows, and custodian tracking.",
            "Real-Time Balance Header Badge: Live status widget in the header bar showing active float and balance with visual color indicators.",
            "Audit Ledger & Interactive Table Sorting: Reverse-chronological ledger table showing latest transactions on top with clickable header sorting (▲ / ▼) and period filtering.",
            "Automatic Voucher Deductions: Seamless linking between cash payment vouchers and designated money floats with real-time balance updates.",
            "Accountant-Grade CSV Export Engine: Multi-section financial workbook format with metadata header, executive KPI summary, detailed line-item register, and payment breakdowns.",
            "Transparent PNG Logo Fix: Corrected alpha channel blending in PDF voucher generation to prevent black rectangle artifacts.",
            "Universal Attachment Support: Native support for previewing and attaching PDFs and multi-format documents alongside images.",
            "Expense Analytics Enhancements: Added Payment Method breakdown tab and direct CSV export for expense analytics summaries.",
            "Streamlined Filter Bar: Compact, responsive layout preventing button shrinking and maximizing table workspace."
        ]
    },
    {
        "version": "1.2.0",
        "date": "2026-09-23",
        "badge": "STABLE",
        "features": [
            "Recurring Voucher Templates: Save frequently used vouchers as templates and load them instantly (Ctrl+T).",
            "Duplicate Voucher: Quick 1-click clone of existing vouchers with fresh numbering and current date.",
            "Batch Bill Status Update: Multi-select vouchers to batch update status (Paid / Unpaid / Pending) via context menu.",
            "Payment Method & Reference Fields: Explicit tracking for payment types (Cash, Cheque, Bank Transfer, Online) and reference/transaction numbers.",
            "Comprehensive Hover Tooltips: Rich contextual guidance on action buttons, inputs, and expense line item headers.",
            "High-Performance Database Queries: Single-pass conditional aggregation for voucher statistics and optimized monthly expense summaries.",
            "Security Hardening: Constant-time hash verification against timing attacks and strict attachment path traversal sanitization."
        ]
    },
    {
        "version": "1.1.7",
        "date": "2026-09-20",
        "badge": "STABLE",
        "features": [
            "New Monthly Voucher Numbering: '26AUG_01' format (YYMMM_NN) based on voucher date.",
            "Automatic monthly counter reset to 01 at the beginning of each new calendar month.",
            "Sequential order preservation across same-month dates and backdated vouchers.",
            "Dynamic voucher number recalculation on the entry form upon date change.",
            "Company Header Settings: Added Monthly numbering option with live preview.",
            "Automated GitHub Version Delivery system with non-blocking background checks.",
            "1-Click streaming download and self-updating Windows batch process.",
            "Zero-Data-Loss non-destructive database migrations and pre-migration backups."
        ]
    },
    {
        "version": "1.1.6",
        "date": "2026-09-18",
        "badge": "STABLE",
        "features": [
            "About App Dialog with developer credentials and legal copyright notices.",
            "Integrated 'What's New' changelog tracking all enhancements per version.",
            "Single-file standalone Windows executable (VoucherManager.exe) compilation.",
            "Password-protected permanent deletion for disabled/cancelled vouchers.",
            "Administrator security protection with password 'Praneeth1991'.",
            "Enhanced bottom shortcut bar with dual-sided layout for improved visibility.",
            "Internal PDF Viewer with 100% default scale, page navigation, and caching.",
            "Dual Company profiles with instant Ctrl+K switcher and independent voucher sets.",
            "Company header customization: Logos stored as BLOBs, address, contact, and email.",
            "Smart multi-slip attachment packing onto A4 pages.",
            "Vast search bar with 140ms debouncing and real-time color highlights.",
            "Auto-suggest popup trigger with '@' for quick Name and Category lookup."
        ]
    },
    {
        "version": "1.1.0",
        "date": "2026-09-17",
        "badge": "STABLE",
        "features": [
            "Company Profile Header customization & database storage.",
            "Independent voucher numbering formats (Date-based 'V-YYYYMMDD-001' and Custom).",
            "Smart date entry widget with keyboard shortcuts (Up/Down, Shift+Up/Down, Today).",
            "Password-protected database wipe feature for entire database or active company."
        ]
    },
    {
        "version": "1.0.0",
        "date": "2026-09-15",
        "badge": "RELEASE",
        "features": [
            "Initial release of SME Payment Voucher Tool.",
            "2 vouchers per A4 print layout via ReportLab canvas engine.",
            "Full voucher CRUD, line item management, and memo audit trail.",
            "Cosmo ttkbootstrap modern user interface."
        ]
    }
]


class WhatsNewDialog(tk.Toplevel):
    """
    Modal dialog displaying the version history and feature updates for each release.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("What's New — Voucher Manager")
        self.geometry("540x480")
        self.minsize(480, 380)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")
        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # 1. Header banner
        header = tk.Frame(self, bg="#0f172a", padx=18, pady=12)
        header.pack(fill=tk.X)

        top_row = tk.Frame(header, bg="#0f172a")
        top_row.pack(anchor="w")

        tk.Label(
            top_row, text="What's New in Voucher Manager",
            font=("Segoe UI", 13, "bold"), bg="#0f172a", fg="#f8fafc"
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            top_row, text="Changelog",
            font=("Segoe UI", 8, "bold"), bg="#1e293b", fg="#94a3b8",
            padx=6, pady=1
        ).pack(side=tk.LEFT)

        tk.Label(
            header, text="Feature updates, improvements, and enhancements across releases.",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Scrollable content area
        container = ttk.Frame(self, padding=(14, 10))
        container.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, highlightthickness=0, bg="#ffffff")
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#ffffff")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas_win = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(canvas_win, width=e.width)
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.bind("<MouseWheel>", _on_mousewheel)
        canvas.bind("<MouseWheel>", _on_mousewheel)

        for release in VERSION_HISTORY:
            v_box = tk.Frame(
                scrollable_frame, bg="#ffffff", highlightbackground="#e2e8f0",
                highlightthickness=1, padx=14, pady=10
            )
            v_box.pack(fill=tk.X, pady=(0, 10))

            # Header line: Version + Badge + Date
            hdr_row = tk.Frame(v_box, bg="#ffffff")
            hdr_row.pack(fill=tk.X)

            tk.Label(
                hdr_row, text=f"Version {release['version']}",
                font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#0f172a"
            ).pack(side=tk.LEFT, padx=(0, 8))

            badge_bg = "#dbeafe" if release.get("badge") == "LATEST" else "#f1f5f9"
            badge_fg = "#1e40af" if release.get("badge") == "LATEST" else "#475569"
            tk.Label(
                hdr_row, text=release.get("badge", "UPDATE"),
                font=("Segoe UI", 7, "bold"), bg=badge_bg, fg=badge_fg, padx=6, pady=1
            ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Label(
                hdr_row, text=release.get("date", ""),
                font=("Segoe UI", 8), bg="#ffffff", fg="#64748b"
            ).pack(side=tk.RIGHT)

            # Bullet points
            items_frame = tk.Frame(v_box, bg="#ffffff")
            items_frame.pack(fill=tk.X, pady=(6, 0))

            for feat in release.get("features", []):
                item_row = tk.Frame(items_frame, bg="#ffffff")
                item_row.pack(fill=tk.X, anchor="w", pady=2)
                tk.Label(
                    item_row, text="•", font=("Segoe UI", 9, "bold"),
                    bg="#ffffff", fg="#2563eb"
                ).pack(side=tk.LEFT, anchor="n", padx=(0, 6))
                tk.Label(
                    item_row, text=feat, font=("Segoe UI", 8),
                    bg="#ffffff", fg="#334155", justify=tk.LEFT, wraplength=460
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Bottom close button
        btn_bar = ttk.Frame(self, padding=(14, 10))
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_bar, text="Close (Esc)", command=self.destroy, bootstyle="secondary").pack(side=tk.RIGHT)


class AboutAppDialog(tk.Toplevel):
    """
    About Application Dialog presenting:
    - App Title & Version (1.3.0)
    - Developer details (Praneeth Thilina, rmpthilina@gmail.com, 0754688251)
    - Legal copyright protection warning
    - What's New button
    """
    APP_VERSION = "1.3.0"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("About Voucher Manager")
        self.resizable(False, False)
        self.geometry("520x410")
        self.transient(parent)
        self.grab_set()

        self._build_ui()

        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")
        self.lift()

        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # 1. Top Brand Header
        header = tk.Frame(self, bg="#0f172a", padx=20, pady=14)
        header.pack(fill=tk.X)

        title_row = tk.Frame(header, bg="#0f172a")
        title_row.pack(anchor="w")

        tk.Label(
            title_row, text="Voucher Manager",
            font=("Segoe UI", 15, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(
            title_row, text=f"v{self.APP_VERSION}",
            font=("Segoe UI", 8, "bold"), bg="#2563eb", fg="#ffffff",
            padx=8, pady=2
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="Professional SME Payment Voucher Management & Printing Solution",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(3, 0))

        # 2. Main Body Container
        body = ttk.Frame(self, padding=(18, 12))
        body.pack(fill=tk.BOTH, expand=True)

        # Developer Information Card
        dev_card = tk.Frame(body, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1, padx=16, pady=10)
        dev_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            dev_card, text="DEVELOPER DETAILS",
            font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#475569"
        ).pack(anchor="w", pady=(0, 4))

        # Precision 3-column Grid for perfectly aligned Labels, Colons, and Values
        grid_frame = tk.Frame(dev_card, bg="#f8fafc")
        grid_frame.pack(fill=tk.X)

        fields = [
            ("Developer", "Praneeth Thilina"),
            ("Email", "rmpthilina@gmail.com"),
            ("Tel", "0754688251"),
        ]

        for r, (lbl, val) in enumerate(fields):
            tk.Label(
                grid_frame, text=lbl, font=("Segoe UI", 9, "bold"),
                bg="#f8fafc", fg="#475569", anchor="w", width=10
            ).grid(row=r, column=0, sticky="w", pady=2)

            tk.Label(
                grid_frame, text=":", font=("Segoe UI", 9, "bold"),
                bg="#f8fafc", fg="#64748b", padx=6
            ).grid(row=r, column=1, pady=2)

            val_fg = "#1d4ed8" if "@" in val else "#0f172a"
            tk.Label(
                grid_frame, text=val,
                font=("Segoe UI", 9, "bold" if r == 0 else "normal"),
                bg="#f8fafc", fg=val_fg, anchor="w"
            ).grid(row=r, column=2, sticky="w", pady=2)

        # Legal Copyright Warning Card
        legal_card = tk.Frame(body, bg="#fffdf5", highlightbackground="#fde68a", highlightthickness=1, padx=16, pady=10)
        legal_card.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            legal_card, text="COPYRIGHT & LEGAL NOTICE",
            font=("Segoe UI", 8, "bold"), bg="#fffdf5", fg="#92400e"
        ).pack(anchor="w", pady=(0, 4))

        warning_text = (
            "Warning: This computer program is protected by copyright laws and "
            "international treaties. Unauthorized reproduction or distribution of this "
            "program, or any portion of it, may result in severe civil and criminal "
            "penalties, and will be prosecuted to the maximum extent possible under law."
        )
        tk.Label(
            legal_card, text=warning_text,
            font=("Segoe UI", 8), bg="#fffdf5", fg="#78350f",
            justify=tk.LEFT, wraplength=450
        ).pack(anchor="w")

        # 3. Action Buttons Footer
        footer = ttk.Frame(self, padding=(18, 10))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            footer, text="✨ What's New",
            command=self._open_whats_new, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._update_btn = ttk.Button(
            footer, text="🔄 Check for Updates",
            command=self._check_for_updates, bootstyle="primary"
        )
        self._update_btn.pack(side=tk.LEFT)

        ttk.Button(
            footer, text="Close (Esc)",
            command=self.destroy, bootstyle="secondary-outline"
        ).pack(side=tk.RIGHT)

    def _open_whats_new(self):
        WhatsNewDialog(self)

    def _check_for_updates(self):
        import updater
        import threading

        self._update_btn.config(state="disabled", text="Checking...")

        def _worker():
            res = updater.check_for_updates(self.APP_VERSION)
            def _apply():
                try:
                    if self.winfo_exists():
                        self._update_btn.config(state="normal", text="🔄 Check for Updates")
                except Exception:
                    pass

                if res.get("update_available"):
                    UpdateAvailableDialog(self, res)
                elif res.get("error"):
                    messagebox.showinfo("Update Check", f"Could not check for updates:\n{res['error']}", parent=self)
                else:
                    messagebox.showinfo("Up to Date", f"You're running the latest version (v{self.APP_VERSION})!", parent=self)

            try:
                self.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()


class UpdateAvailableDialog(tk.Toplevel):
    """
    Modal dialog announcing that a newer version is available on GitHub.
    """

    def __init__(self, parent, update_info):
        super().__init__(parent)
        self.title(f"🚀 New Update Available: v{update_info.get('latest_version')}")
        self.geometry("520x460")
        self.minsize(480, 380)
        self.transient(parent)
        self.grab_set()

        self._info = update_info
        self._build_ui()

        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")
        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # 1. Header Banner
        header = tk.Frame(self, bg="#0f172a", padx=18, pady=14)
        header.pack(fill=tk.X)

        title_row = tk.Frame(header, bg="#0f172a")
        title_row.pack(anchor="w")

        tk.Label(
            title_row, text="🚀 New Version Available",
            font=("Segoe UI", 13, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            title_row, text=f"v{self._info.get('latest_version')}",
            font=("Segoe UI", 9, "bold"), bg="#16a34a", fg="#ffffff",
            padx=8, pady=1
        ).pack(side=tk.LEFT)

        current_v = self._info.get("current_version", "")
        tk.Label(
            header,
            text=f"Current version: v{current_v}  ➔  Latest: v{self._info.get('latest_version')}",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(3, 0))

        # 2. Main Body
        body = ttk.Frame(self, padding=(16, 12))
        body.pack(fill=tk.BOTH, expand=True)

        # Release Title
        rel_name = self._info.get("release_name", "New Release")
        tk.Label(
            body, text=rel_name,
            font=("Segoe UI", 10, "bold"), fg="#0f172a"
        ).pack(anchor="w", pady=(0, 6))

        # Release Notes Scrollable Box
        notes_frame = tk.Frame(body, bg="#f8fafc", highlightbackground="#cbd5e1", highlightthickness=1)
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        notes_text = tk.Text(
            notes_frame, wrap=tk.WORD, font=("Segoe UI", 8),
            bg="#f8fafc", fg="#334155", padx=10, pady=8,
            relief=tk.FLAT, height=8
        )
        notes_sb = ttk.Scrollbar(notes_frame, orient=tk.VERTICAL, command=notes_text.yview)
        notes_text.configure(yscrollcommand=notes_sb.set)

        notes_text.insert("1.0", self._info.get("release_notes", "No changelog provided."))
        notes_text.config(state="disabled")

        notes_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        notes_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Safety & Size Notice
        size_bytes = self._info.get("asset_size", 0)
        size_txt = f"{size_bytes / (1024 * 1024):.1f} MB" if size_bytes > 0 else "Ready to download"

        notice_box = tk.Frame(body, bg="#f0fdf4", highlightbackground="#86efac", highlightthickness=1, padx=12, pady=8)
        notice_box.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            notice_box,
            text=f"✓ Download Size: {size_txt}   •   Database Safe",
            font=("Segoe UI", 8, "bold"), bg="#f0fdf4", fg="#15803d"
        ).pack(anchor="w")

        tk.Label(
            notice_box,
            text="All vouchers, attachments, and settings are preserved. The update will smoothly migrate your schema without data loss.",
            font=("Segoe UI", 8), bg="#f0fdf4", fg="#166534", wraplength=450, justify=tk.LEFT
        ).pack(anchor="w", pady=(2, 0))

        # 3. Action Buttons
        footer = ttk.Frame(self, padding=(16, 10))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        if self._info.get("download_url"):
            ttk.Button(
                footer, text="⬇️ Download & Update Now",
                command=self._start_download, bootstyle="success"
            ).pack(side=tk.LEFT)
        else:
            ttk.Button(
                footer, text="🌐 Open Release Page in Browser",
                command=self._open_browser, bootstyle="primary"
            ).pack(side=tk.LEFT)

        ttk.Button(
            footer, text="Remind Me Later",
            command=self.destroy, bootstyle="secondary-outline"
        ).pack(side=tk.RIGHT)

    def _open_browser(self):
        import webbrowser
        webbrowser.open(self._info.get("html_url"))
        self.destroy()

    def _start_download(self):
        download_url = self._info.get("download_url")
        latest_ver = self._info.get("latest_version")
        self.destroy()
        UpdateDownloadDialog(self.master, download_url, latest_ver)


class ExpenseSummaryDialog(tk.Toplevel):
    """
    Dialog displaying expense analytics and breakdown by Category and Payee.
    Includes date range filters (All Time, This Month, Last Month, This Year).
    """

    def __init__(self, parent):
        super().__init__(parent)
        import database as db
        active_id = db.get_active_company_id()
        comp = db.get_company(active_id) or {}
        self._comp_name = comp.get("name", f"Company {active_id}")

        self.title(f"📈 Expense Analytics — {self._comp_name}")
        self.geometry("640x520")
        self.minsize(520, 400)
        self.transient(parent)
        self.grab_set()

        self._date_filter_var = tk.StringVar(value="all")
        self._build_ui()
        self._refresh_analytics()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # Header Banner
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="📈 Expense Breakdown & Analytics",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        # Filter bar
        filter_bar = tk.Frame(self, bg="#f1f5f9", padx=12, pady=6)
        filter_bar.pack(fill=tk.X)

        tk.Label(filter_bar, text="Period:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 6))

        periods = [
            ("All Time", "all"),
            ("This Month", "this_month"),
            ("Last Month", "last_month"),
            ("This Year", "this_year"),
        ]

        for text, val in periods:
            rb = ttk.Radiobutton(
                filter_bar, text=text, value=val,
                variable=self._date_filter_var, command=self._refresh_analytics
            )
            rb.pack(side=tk.LEFT, padx=6)

        # Grand Total Summary Card
        total_card = tk.Frame(self, bg="#f0fdf4", highlightbackground="#86efac", highlightthickness=1, padx=12, pady=8)
        total_card.pack(fill=tk.X, padx=12, pady=8)

        self._summary_lbl = tk.Label(
            total_card, text="Grand Total: LKR 0.00  |  Vouchers: 0",
            font=("Segoe UI", 11, "bold"), bg="#f0fdf4", fg="#15803d"
        )
        self._summary_lbl.pack(anchor="w")

        # Notebook with Category Breakdown and Payee Breakdown
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        # Tab 1: Category Breakdown
        cat_tab = ttk.Frame(nb, padding=6)
        nb.add(cat_tab, text="  📁 Expenses by Category  ")

        cat_cols = ("category", "count", "amount", "percent")
        self._cat_tree = ttk.Treeview(cat_tab, columns=cat_cols, show="headings", height=10)
        self._cat_tree.heading("category", text="Category")
        self._cat_tree.heading("count", text="Vouchers")
        self._cat_tree.heading("amount", text="Total Amount (LKR)")
        self._cat_tree.heading("percent", text="Share (%)")

        self._cat_tree.column("category", width=220, anchor="w")
        self._cat_tree.column("count", width=80, anchor="center")
        self._cat_tree.column("amount", width=140, anchor="e")
        self._cat_tree.column("percent", width=80, anchor="center")

        cat_sb = ttk.Scrollbar(cat_tab, orient=tk.VERTICAL, command=self._cat_tree.yview)
        self._cat_tree.configure(yscrollcommand=cat_sb.set)
        self._cat_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cat_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 2: Payee Breakdown
        payee_tab = ttk.Frame(nb, padding=6)
        nb.add(payee_tab, text="  👤 Expenses by Payee  ")

        payee_cols = ("payee", "count", "amount", "percent")
        self._payee_tree = ttk.Treeview(payee_tab, columns=payee_cols, show="headings", height=10)
        self._payee_tree.heading("payee", text="Payee / Party")
        self._payee_tree.heading("count", text="Vouchers")
        self._payee_tree.heading("amount", text="Total Amount (LKR)")
        self._payee_tree.heading("percent", text="Share (%)")

        self._payee_tree.column("payee", width=220, anchor="w")
        self._payee_tree.column("count", width=80, anchor="center")
        self._payee_tree.column("amount", width=140, anchor="e")
        self._payee_tree.column("percent", width=80, anchor="center")

        payee_sb = ttk.Scrollbar(payee_tab, orient=tk.VERTICAL, command=self._payee_tree.yview)
        self._payee_tree.configure(yscrollcommand=payee_sb.set)
        self._payee_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        payee_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Tab 3: Payment Method Breakdown
        pm_tab = ttk.Frame(nb, padding=6)
        nb.add(pm_tab, text="  💳 Expenses by Payment Method  ")

        pm_cols = ("payment_method", "count", "amount", "percent")
        self._pm_tree = ttk.Treeview(pm_tab, columns=pm_cols, show="headings", height=10)
        self._pm_tree.heading("payment_method", text="Payment Method")
        self._pm_tree.heading("count", text="Vouchers")
        self._pm_tree.heading("amount", text="Total Amount (LKR)")
        self._pm_tree.heading("percent", text="Share (%)")

        self._pm_tree.column("payment_method", width=220, anchor="w")
        self._pm_tree.column("count", width=80, anchor="center")
        self._pm_tree.column("amount", width=140, anchor="e")
        self._pm_tree.column("percent", width=80, anchor="center")

        pm_sb = ttk.Scrollbar(pm_tab, orient=tk.VERTICAL, command=self._pm_tree.yview)
        self._pm_tree.configure(yscrollcommand=pm_sb.set)
        self._pm_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pm_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Footer close and export buttons
        footer = ttk.Frame(self, padding=(12, 8))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        export_btn = ttk.Button(footer, text="📊 Export CSV", command=self._export_csv, bootstyle="info-outline")
        export_btn.pack(side=tk.LEFT)
        ToolTip(export_btn, text="Export expense summary breakdown report to CSV file")

        ttk.Button(footer, text="Close (Esc)", command=self.destroy, bootstyle="secondary").pack(side=tk.RIGHT)

    def _refresh_analytics(self):
        import database as db
        data = db.get_expense_summary(date_filter=self._date_filter_var.get())

        grand_total = data["grand_total"]
        v_count = data["voucher_count"]
        self._summary_lbl.config(
            text=f"Total Expenses: LKR {grand_total:,.2f}  |  Active Vouchers: {v_count}"
        )

        # Populate Category Tree
        self._cat_tree.delete(*self._cat_tree.get_children())
        for row in data["by_category"]:
            amt = row["amount"]
            pct = (amt / grand_total * 100) if grand_total > 0 else 0.0
            self._cat_tree.insert("", tk.END, values=(
                row["category"], row["count"], f"{amt:,.2f}", f"{pct:.1f}%"
            ))

        # Populate Payee Tree
        self._payee_tree.delete(*self._payee_tree.get_children())
        for row in data["by_payee"]:
            amt = row["amount"]
            pct = (amt / grand_total * 100) if grand_total > 0 else 0.0
            self._payee_tree.insert("", tk.END, values=(
                row["payee"], row["count"], f"{amt:,.2f}", f"{pct:.1f}%"
            ))

        # Populate Payment Method Tree
        self._pm_tree.delete(*self._pm_tree.get_children())
        for row in data.get("by_payment_method", []):
            amt = row["amount"]
            pct = (amt / grand_total * 100) if grand_total > 0 else 0.0
            self._pm_tree.insert("", tk.END, values=(
                row["payment_method"], row["count"], f"{amt:,.2f}", f"{pct:.1f}%"
            ))

    def _export_csv(self):
        import database as db
        from datetime import datetime
        period_labels = {
            "all": "All Time",
            "this_month": "This Month",
            "last_month": "Last Month",
            "this_year": "This Year",
        }
        curr_period = self._date_filter_var.get()
        period_txt = period_labels.get(curr_period, "All Time")
        data = db.get_expense_summary(date_filter=curr_period)

        if not data or (not data.get("by_category") and not data.get("by_payee")):
            messagebox.showinfo("Export CSV", "No expense data available to export for this period.", parent=self)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Expense Analytics Summary to CSV",
            initialfile=f"expense_summary_{curr_period}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")]
        )

        if filepath:
            try:
                db.export_expense_summary_to_csv(
                    data, filepath, period_label=period_txt, company_name=getattr(self, "_comp_name", "")
                )
                messagebox.showinfo("Export Successful", f"Expense summary report saved to:\n{filepath}", parent=self)
            except Exception as e:
                messagebox.showerror("Export Error", f"Could not export CSV file:\n{e}", parent=self)



class ExportVouchersDialog(tk.Toplevel):
    """
    Modal dialog allowing accountants to export vouchers in formats tailored for
    accounting workflows:
    - Detailed General Ledger (Itemized line-by-line)
    - Voucher Register (Summary by voucher)
    - Category Expense Summary (Aggregated totals)
    """

    def __init__(self, parent, vouchers, on_exported_callback=None):
        super().__init__(parent)
        self.title("📊 Export Vouchers — Accounting Hub")
        self.geometry("660x680")
        self.minsize(580, 620)
        self.transient(parent)
        self.grab_set()

        self._vouchers = vouchers or []
        self._on_exported = on_exported_callback
        self._format_var = tk.StringVar(value="itemized")
        self._total_row_var = tk.BooleanVar(value=True)
        self._active_only_var = tk.BooleanVar(value=True)
        self._open_file_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._update_summary_card()
        self._update_columns_preview()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        # 1. Header Banner (TOP)
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            header, text="📊 Export Vouchers for Accounting",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header,
            text="Generate clean, accounting-ready CSV files for general ledgers, pivot tables, and audits.",
            font=("Segoe UI", 8, "normal"), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # 2. Footer Actions (BOTTOM - packed before expandable content to prevent squeezing)
        footer_sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        footer_sep.pack(fill=tk.X, side=tk.BOTTOM)

        footer = ttk.Frame(self, padding=(16, 12))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            footer, text="Cancel", command=self.destroy,
            bootstyle="secondary-outline", width=12
        ).pack(side=tk.RIGHT, padx=(10, 0), ipady=5)

        export_btn = ttk.Button(
            footer, text="📊 Export to CSV...",
            command=self._do_export, bootstyle="success", width=22
        )
        export_btn.pack(side=tk.RIGHT, ipady=5)
        export_btn.focus_set()

        # 3. Middle Content (Expandable)
        content = ttk.Frame(self, padding=(16, 12))
        content.pack(fill=tk.BOTH, expand=True)

        # Voucher Summary Card
        self._summary_card = tk.Frame(
            content, bg="#f8fafc", highlightbackground="#cbd5e1",
            highlightthickness=1, padx=12, pady=8
        )
        self._summary_card.pack(fill=tk.X, pady=(0, 10))

        self._summary_lbl = tk.Label(
            self._summary_card, text="",
            font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b"
        )
        self._summary_lbl.pack(anchor="w")

        # Format Selection Group
        fmt_label = tk.Label(
            content, text="Select Export Format:",
            font=("Segoe UI", 10, "bold"), fg="#1e293b"
        )
        fmt_label.pack(anchor="w", pady=(0, 6))

        formats_frame = ttk.LabelFrame(content, text=" Output Formats ", padding=10)
        formats_frame.pack(fill=tk.X, pady=(0, 10))

        # 1. Detailed Itemized Ledger
        opt1_frame = ttk.Frame(formats_frame)
        opt1_frame.pack(fill=tk.X, pady=(2, 6))
        rb1 = ttk.Radiobutton(
            opt1_frame,
            text="Detailed Itemized Ledger (General Ledger) — Recommended",
            value="itemized",
            variable=self._format_var,
            command=self._on_format_changed,
            bootstyle="primary"
        )
        rb1.pack(anchor="w")
        tk.Label(
            opt1_frame,
            text="Each line item is exported on its own row with dedicated Category, Description, and Amount columns.\n"
                 "★ Ideal for Excel Pivot Tables, category filtering, and software import (QuickBooks, Xero, Tally).",
            font=("Segoe UI", 8), fg="#64748b", justify=tk.LEFT
        ).pack(anchor="w", padx=(24, 0), pady=(1, 0))

        # 2. Voucher Register
        opt2_frame = ttk.Frame(formats_frame)
        opt2_frame.pack(fill=tk.X, pady=(4, 6))
        rb2 = ttk.Radiobutton(
            opt2_frame,
            text="Voucher Register (Summary by Voucher)",
            value="register",
            variable=self._format_var,
            command=self._on_format_changed,
            bootstyle="primary"
        )
        rb2.pack(anchor="w")
        tk.Label(
            opt2_frame,
            text="One row per voucher with clean category tags, item count, and voucher totals.\n"
                 "★ Best for checkbook registries, filing binders, and executive review.",
            font=("Segoe UI", 8), fg="#64748b", justify=tk.LEFT
        ).pack(anchor="w", padx=(24, 0), pady=(1, 0))

        # 3. Category Expense Summary
        opt3_frame = ttk.Frame(formats_frame)
        opt3_frame.pack(fill=tk.X, pady=(4, 2))
        rb3 = ttk.Radiobutton(
            opt3_frame,
            text="Category Expense Summary (Aggregated Totals)",
            value="category_summary",
            variable=self._format_var,
            command=self._on_format_changed,
            bootstyle="primary"
        )
        rb3.pack(anchor="w")
        tk.Label(
            opt3_frame,
            text="Aggregated expenditure grouped by Category with item counts and percentage shares.\n"
                 "★ Best for monthly budget reviews and cost center analysis.",
            font=("Segoe UI", 8), fg="#64748b", justify=tk.LEFT
        ).pack(anchor="w", padx=(24, 0), pady=(1, 0))

        # Preview of Export Columns
        prev_box = ttk.LabelFrame(content, text=" Exported Columns Preview ", padding=8)
        prev_box.pack(fill=tk.X, pady=(0, 10))

        self._cols_lbl = tk.Label(
            prev_box, text="",
            font=("Consolas", 8), fg="#334155", justify=tk.LEFT, wraplength=590
        )
        self._cols_lbl.pack(anchor="w")

        # Accountant Options
        opts_box = ttk.LabelFrame(content, text=" Export Options ", padding=8)
        opts_box.pack(fill=tk.X, pady=(0, 6))

        ttk.Checkbutton(
            opts_box,
            text="Include Grand Total summary row at bottom",
            variable=self._total_row_var,
            bootstyle="success-round-toggle"
        ).pack(anchor="w", pady=2)

        ttk.Checkbutton(
            opts_box,
            text="Active vouchers only (exclude cancelled/voided records)",
            variable=self._active_only_var,
            command=self._update_summary_card,
            bootstyle="info-round-toggle"
        ).pack(anchor="w", pady=2)

        ttk.Checkbutton(
            opts_box,
            text="Open exported file in Excel / Default App immediately",
            variable=self._open_file_var,
            bootstyle="primary-round-toggle"
        ).pack(anchor="w", pady=2)

    def _on_format_changed(self):
        self._update_columns_preview()

    def _update_columns_preview(self):
        fmt = self._format_var.get()
        if fmt == "itemized":
            cols = [
                "Voucher #", "Date", "Paid To", "Category", "Line Description",
                "Line Amount", "Payment Method", "Payment Ref", "Bill Status",
                "Cash Given By", "Spent By", "Prepared By", "Approved By", "Status", "Voucher Total"
            ]
        elif fmt == "register":
            cols = [
                "Voucher #", "Date", "Paid To", "Categories", "Items Count",
                "Total Amount", "Payment Method", "Payment Ref", "Bill Status",
                "Cash Given By", "Spent By", "Prepared By", "Approved By", "Status", "Printed"
            ]
        elif fmt == "category_summary":
            cols = ["Category", "Transaction Count", "Total Amount", "Share (%)"]
        else:
            cols = []

        cols_str = "  |  ".join(cols)
        self._cols_lbl.config(text=f"Columns ({len(cols)}):\n{cols_str}")

    def _update_summary_card(self):
        active_only = self._active_only_var.get()
        vouchers = self._vouchers
        if active_only:
            vouchers = [v for v in vouchers if v.get("status") == "Active"]

        count = len(vouchers)
        total_val = sum(float(v.get("total_amount") or 0.0) for v in vouchers)

        if active_only and len(vouchers) != len(self._vouchers):
            status_hint = f"({count} active of {len(self._vouchers)} total filtered)"
        else:
            status_hint = f"({count} records)"

        self._summary_lbl.config(
            text=f"📄 Selected for Export: {count} voucher(s) {status_hint}  |  Total Value: LKR {total_val:,.2f}"
        )

    def _do_export(self):
        from datetime import datetime
        import database as db

        fmt = self._format_var.get()
        include_tot = self._total_row_var.get()
        active_only = self._active_only_var.get()
        open_after = self._open_file_var.get()

        prefix_map = {
            "itemized": "vouchers_detailed_ledger",
            "register": "vouchers_register",
            "category_summary": "vouchers_category_summary",
        }
        prefix = prefix_map.get(fmt, "vouchers_export")
        default_filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Vouchers to CSV",
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")]
        )

        if not filepath:
            return

        try:
            db.export_vouchers_to_csv(
                self._vouchers,
                filepath,
                format_type=fmt,
                include_total_row=include_tot,
                active_only=active_only
            )

            v_count = len([v for v in self._vouchers if v.get("status") == "Active"]) if active_only else len(self._vouchers)

            if open_after:
                try:
                    os.startfile(filepath)
                except Exception:
                    pass

            if self._on_exported:
                self._on_exported(filepath, v_count)

            self.destroy()

        except Exception as e:
            messagebox.showerror("Export Error", f"Could not export CSV file:\n{e}", parent=self)



class UpdateDownloadDialog(tk.Toplevel):
    """
    Modal dialog handling the stream download of the new executable with progress bar.
    """

    def __init__(self, parent, download_url, latest_version):
        super().__init__(parent)
        self.title("Updating Voucher Manager...")
        self.resizable(False, False)
        self.geometry("460x220")
        self.transient(parent)
        self.grab_set()

        self._url = download_url
        self._version = latest_version
        self._cancel_event = None
        self._temp_exe = None

        self._build_ui()

        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")
        self.lift()

        self._start_download_thread()

    def _build_ui(self):
        pad = ttk.Frame(self, padding=(20, 16))
        pad.pack(fill=tk.BOTH, expand=True)

        self._status_lbl = tk.Label(
            pad, text="Connecting to GitHub...",
            font=("Segoe UI", 10, "bold"), fg="#0f172a"
        )
        self._status_lbl.pack(anchor="w", pady=(0, 8))

        self._pbar = ttk.Progressbar(pad, mode="determinate", length=400)
        self._pbar.pack(fill=tk.X, pady=(0, 8))

        self._detail_lbl = tk.Label(
            pad, text="Preparing download...",
            font=("Segoe UI", 8), fg="#64748b"
        )
        self._detail_lbl.pack(anchor="w", pady=(0, 14))

        self._btn_frame = ttk.Frame(pad)
        self._btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self._action_btn = ttk.Button(
            self._btn_frame, text="Cancel",
            command=self._cancel, bootstyle="secondary-outline"
        )
        self._action_btn.pack(side=tk.RIGHT)

    def _start_download_thread(self):
        import updater
        import tempfile
        import threading

        self._cancel_event = threading.Event()
        self._temp_exe = os.path.join(tempfile.gettempdir(), f"VoucherManager_v{self._version}.exe")

        def _progress(downloaded, total, percent):
            def _ui():
                try:
                    if self.winfo_exists():
                        self._pbar["value"] = percent
                        mb_down = downloaded / (1024 * 1024)
                        mb_tot = total / (1024 * 1024)
                        self._status_lbl.config(text=f"Downloading Update v{self._version}...")
                        self._detail_lbl.config(text=f"{mb_down:.1f} MB / {mb_tot:.1f} MB ({percent:.0f}%)")
                except Exception:
                    pass
            try:
                self.after(0, _ui)
            except Exception:
                pass

        def _worker():
            try:
                success = updater.download_update(
                    self._url, self._temp_exe,
                    progress_callback=_progress,
                    cancel_event=self._cancel_event
                )
                def _done():
                    if success:
                        self._on_download_complete()
                self.after(0, _done)
            except Exception as e:
                def _err():
                    try:
                        if self.winfo_exists():
                            self._status_lbl.config(text="Download Failed", fg="#dc2626")
                            self._detail_lbl.config(text=str(e))
                            self._action_btn.config(text="Close", command=self.destroy)
                    except Exception:
                        pass
                self.after(0, _err)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_download_complete(self):
        try:
            if not self.winfo_exists():
                return
            self._status_lbl.config(text="✅ Download Complete!", fg="#15803d")
            self._detail_lbl.config(text="Click below to restart and apply update. Data is 100% preserved.")
            self._pbar["value"] = 100

            self._action_btn.destroy()

            ttk.Button(
                self._btn_frame, text="🔄 Restart & Update Now",
                command=self._apply_and_restart, bootstyle="success"
            ).pack(side=tk.LEFT)

            ttk.Button(
                self._btn_frame, text="Later",
                command=self.destroy, bootstyle="secondary-outline"
            ).pack(side=tk.RIGHT)
        except Exception:
            pass

    def _apply_and_restart(self):
        import updater
        if self._temp_exe and os.path.exists(self._temp_exe):
            updater.apply_update_and_restart(self._temp_exe)

    def _cancel(self):
        if self._cancel_event:
            self._cancel_event.set()
        self.destroy()

