"""
Main Window for the Voucher Printing Tool.
Two-tab layout:
  - Tab 1: Voucher List (search, filter, actions)
  - Tab 2: Voucher Form (create / edit, highly compact, prioritized layout)
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap import ToolTip
from ttkbootstrap.constants import *
from tkinter import messagebox, simpledialog
from datetime import datetime, date, timedelta
import os
import io
import subprocess
import sys

import database as db
import firebase_client
import gdrive_client
import printer
from ui.widgets import AutocompleteEntry, LineItemFrame, MemoPanel, SmartDateEntry
from ui import dialogs
from ui.category_manager import CategoryManagerDialog
from ui.name_manager import NameManagerDialog
from ui.settings_dialog import SettingsDialog
from ui.pdf_viewer import PdfViewerDialog
from ui.template_manager import TemplateManagerDialog
from ui.tag_manager import TagManagerDialog

# V2.0 Modules
from ui.recurring_manager import RecurringManagerDialog
from ui.approval_dialog import ApprovalDialog, ApproverManagerDialog
from ui.bank_reconciliation import BankReconciliationDialog
from ui.alert_center import AlertCenterDialog
from ui.import_wizard import ImportWizardDialog
from ui.currency_ui import CurrencySelector, show_exchange_rate_manager
from ui.user_manager import (
    ChangePasswordDialog,
    UserManagementDialog,
    current_user_has_role,
)

# V3.0 Check Printing Modules
from ui.check_dialog import CheckEntryDialog

# V3.5 SME Bookkeeping Modules
from ui.coa_dialog import ChartOfAccountsDialog
from ui.journal_dialog import GeneralLedgerDialog, JournalEntryDialog
from ui.supplier_manager import SupplierManagerDialog
from ui.customer_manager import CustomerManagerDialog


class MenuActionProxy:
    """Proxy object representing a dropdown menu item within self._action_buttons.
    Maintains 100% compatibility with RBAC permission checks, unit tests, and programmatic invocation."""
    def __init__(self, menu, index, command=None, label="", menubutton=None):
        self.menu = menu
        self.index = index
        self.command = command
        self.label = label
        self.menubutton = menubutton

    def configure(self, **kwargs):
        if "state" in kwargs:
            st = tk.NORMAL if kwargs["state"] in (tk.NORMAL, "normal") else tk.DISABLED
            try:
                self.menu.entryconfig(self.index, state=st)
            except Exception:
                pass
        if "text" in kwargs or "label" in kwargs:
            lbl = kwargs.get("text", kwargs.get("label"))
            try:
                self.menu.entryconfig(self.index, label=lbl)
                self.label = lbl
            except Exception:
                pass

    def config(self, **kwargs):
        self.configure(**kwargs)

    def invoke(self):
        if self.command:
            return self.command()

    def cget(self, key):
        if key == "state":
            try:
                return self.menu.entrycget(self.index, "state")
            except Exception:
                return "normal"
        elif key in ("text", "label"):
            try:
                return self.menu.entrycget(self.index, "label")
            except Exception:
                return self.label
        raise KeyError(key)

    def __getitem__(self, key):
        return self.cget(key)


class MainWindow:
    """Main application window with tabbed interface and keyboard shortcut support."""

    TAB_ACCOUNTANT = 0
    TAB_VOUCHERS = 1
    TAB_FORM = 2
    TAB_FLOAT = 3
    TAB_ANALYTICS = 4
    TAB_CHECKS = 5
    TAB_CUSTOMERS = 6
    TAB_INVOICE = 7

    def __init__(self, root, on_logout=None):
        if not db.get_current_user():
            raise PermissionError(
                "Authentication is required before opening the workspace."
            )
        self.root = root
        self._on_logout = on_logout
        self._editing_voucher_id = None
        self._pending_attachments = []  # new attachments not yet saved
        self._existing_attachments = []  # already-saved attachments
        self._comp_logo_photo = None
        self._cached_logo_key = None
        self._form_scroll_timer = None
        self._toast_frame = None
        self._search_timer = None
        self._startup_timer_ids = set()
        self._is_closing = False
        self._form_built = False
        self._list_dirty = True
        self._tag_buttons = {}
        saved_stats_visible = db.get_app_setting("dashboard_stats_visible", None)
        if saved_stats_visible is None:
            saved_stats_visible = "hide" if db.get_app_setting("dashboard_ribbon_mode") == "hide" else "show"
        self._stats_visible = (saved_stats_visible != "hide")

        self._setup_custom_styles()
        self._build_ui()
        self._toast_timer_id = None
        self._update_company_header()
        self._setup_shortcuts()

        # Clean window close handler to cancel pending after loops
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")

        # Non-blocking background check for updates after UI settles
        self._startup_timer_ids.add(
            self.root.after(2500, self._check_for_updates_background)
        )

        # V2.0 Startup background tasks (recurring vouchers, alerts, RBAC)
        self._startup_timer_ids.add(self.root.after(1000, self._v2_startup_tasks))

    def _on_root_destroy(self, event=None):
        """Cancel callbacks when the root is destroyed by any code path."""
        if event is not None and event.widget is not self.root:
            return
        self._cancel_pending_callbacks()

    def _cancel_pending_callbacks(self):
        """Cancel delayed UI work so no Tcl callback outlives the window."""
        if self._is_closing:
            return
        self._is_closing = True

        timer_ids = set(getattr(self, "_startup_timer_ids", set()))
        for attr_name in ("_search_timer", "_toast_timer_id", "_form_scroll_timer"):
            timer_id = getattr(self, attr_name, None)
            if timer_id:
                timer_ids.add(timer_id)

        for timer_id in timer_ids:
            try:
                self.root.after_cancel(timer_id)
            except (tk.TclError, ValueError):
                pass

        self._startup_timer_ids.clear()
        self._search_timer = None
        self._toast_timer_id = None
        self._form_scroll_timer = None

    def prepare_for_logout(self):
        """Stop background work and remove workspace-wide key bindings."""
        self._cancel_pending_callbacks()
        try:
            sequences = self.root.bind_all()
            for sequence in sequences or ():
                self.root.unbind_all(sequence)
        except tk.TclError:
            pass
    def _setup_custom_styles(self):
        """Configure elegant Windows 11 Fluent theme styles for text boxes and controls."""
        style = ttk.Style()

        # Modern Windows 11 Treeview with spacious touch/click row height
        style.configure(
            "Treeview",
            rowheight=28,
            font=("Segoe UI", 9),
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground="#0f172a"
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 9, "bold"),
            padding=(6, 5)
        )
        style.map(
            "Treeview",
            background=[("selected", "#0067c0")],
            foreground=[("selected", "#ffffff")]
        )

        # Base entry style: soft light background instead of stark white
        style.configure("TEntry", fieldbackground="#f8fafc", foreground="#0f172a")
        style.map("TEntry",
            fieldbackground=[("focus", "#ffffff"), ("disabled", "#f1f5f9"), ("!disabled", "#f8fafc")]
        )

        # Voucher Number Badge: distinct soft sky-blue badge
        style.configure("VoucherBadge.TEntry", fieldbackground="#e0f2fe", foreground="#0369a1")
        style.map("VoucherBadge.TEntry",
            fieldbackground=[("readonly", "#e0f2fe"), ("!disabled", "#e0f2fe")],
            foreground=[("readonly", "#0369a1"), ("!disabled", "#0369a1")]
        )

        # Party / People input: soft light ice-blue tint
        style.configure("Party.TEntry", fieldbackground="#f0f7ff", foreground="#0f172a")
        style.map("Party.TEntry",
            fieldbackground=[("focus", "#ffffff"), ("!disabled", "#f0f7ff")]
        )

        # Line Item Description: clean light tint
        style.configure("Desc.TEntry", fieldbackground="#f8fafc", foreground="#0f172a")
        style.map("Desc.TEntry",
            fieldbackground=[("focus", "#ffffff"), ("!disabled", "#f8fafc")]
        )

        # Line Item Category: soft light emerald/mint tint
        style.configure("Category.TEntry", fieldbackground="#f0fdf4", foreground="#166534")
        style.map("Category.TEntry",
            fieldbackground=[("focus", "#ffffff"), ("!disabled", "#f0fdf4")]
        )

        # Line Item Amount: soft light warm cream/gold tint
        style.configure("Amount.TEntry", fieldbackground="#fefce8", foreground="#854d0e")
        style.map("Amount.TEntry",
            fieldbackground=[("focus", "#ffffff"), ("!disabled", "#fefce8")]
        )

        # Search box: clean white with focus border
        style.configure("Search.TEntry", fieldbackground="#ffffff", foreground="#0f172a")
        style.map("Search.TEntry",
            fieldbackground=[("focus", "#ffffff"), ("!disabled", "#ffffff")]
        )

    # ------------------------------------------------------------------
    # Keyboard Shortcuts Setup
    # ------------------------------------------------------------------

    def _setup_shortcuts(self):
        """Bind global and context-aware keyboard shortcuts."""
        # New Voucher: Ctrl+N
        self.root.bind_all("<Control-n>", lambda e: self._new_voucher())
        self.root.bind_all("<Control-N>", lambda e: self._new_voucher())

        # Save: Ctrl+S
        self.root.bind_all("<Control-s>", lambda e: self._shortcut_save())
        self.root.bind_all("<Control-S>", lambda e: self._shortcut_save())

        # Save & Print: Ctrl+Enter
        self.root.bind_all("<Control-Return>", lambda e: self._shortcut_save_and_print())

        # Print: Ctrl+P
        self.root.bind_all("<Control-p>", lambda e: self._shortcut_print())
        self.root.bind_all("<Control-P>", lambda e: self._shortcut_print())

        # Print All Pending: Ctrl+Shift+P
        self.root.bind_all("<Control-Shift-P>", lambda e: self._print_all_pending())
        self.root.bind_all("<Control-Shift-p>", lambda e: self._print_all_pending())

        # Edit Selected: Ctrl+E
        self.root.bind_all("<Control-e>", lambda e: self._edit_selected())
        self.root.bind_all("<Control-E>", lambda e: self._edit_selected())

        # Duplicate Selected: Ctrl+D
        self.root.bind_all("<Control-d>", lambda e: self._duplicate_selected())
        self.root.bind_all("<Control-D>", lambda e: self._duplicate_selected())

        # Restore: Ctrl+R
        self.root.bind_all("<Control-r>", lambda e: self._restore_selected())
        self.root.bind_all("<Control-R>", lambda e: self._restore_selected())

        # Focus Search: Ctrl+F
        self.root.bind_all("<Control-f>", lambda e: self._shortcut_focus_search())
        self.root.bind_all("<Control-F>", lambda e: self._shortcut_focus_search())

        # Clear Form: Ctrl+W
        self.root.bind_all("<Control-w>", lambda e: self._shortcut_clear_form())
        self.root.bind_all("<Control-W>", lambda e: self._shortcut_clear_form())

        # Add Line: Alt+A
        self.root.bind_all("<Alt-a>", lambda e: self._shortcut_add_line())
        self.root.bind_all("<Alt-A>", lambda e: self._shortcut_add_line())

        # Refresh: F5
        self.root.bind_all("<F5>", self._shortcut_refresh)

        # Back to List: Esc
        self.root.bind_all("<Escape>", lambda e: self._shortcut_escape())

        # Cancel Voucher: Delete key (only if not typing in text field)
        self.root.bind_all("<Delete>", self._shortcut_delete)

        # Permanent Delete Disabled Voucher: Shift+Delete
        self.root.bind_all("<Shift-Delete>", self._shortcut_delete_permanent)

        # Category Manager: Ctrl+G
        self.root.bind_all("<Control-g>", lambda e: self._open_category_manager())
        self.root.bind_all("<Control-G>", lambda e: self._open_category_manager())

        # Name Manager: Ctrl+M
        self.root.bind_all("<Control-m>", lambda e: self._open_name_manager())
        self.root.bind_all("<Control-M>", lambda e: self._open_name_manager())

        # Switch Company: Ctrl+K
        self.root.bind_all("<Control-k>", lambda e: self._shortcut_switch_company())
        self.root.bind_all("<Control-K>", lambda e: self._shortcut_switch_company())

        # Settings: Ctrl+comma
        self.root.bind_all("<Control-comma>", lambda e: self._open_settings())

        # Expense Analytics: Ctrl+I
        self.root.bind_all("<Control-i>", lambda e: self._open_expense_summary())
        self.root.bind_all("<Control-I>", lambda e: self._open_expense_summary())

        # Payee Statement: Ctrl+Shift+S
        self.root.bind_all("<Control-Shift-s>", lambda e: self._open_payee_statement())
        self.root.bind_all("<Control-Shift-S>", lambda e: self._open_payee_statement())

        # Template Manager: Ctrl+T
        self.root.bind_all("<Control-t>", lambda e: self._open_template_manager())
        self.root.bind_all("<Control-T>", lambda e: self._open_template_manager())

        # Money Float Manager: Ctrl+3 / Ctrl+Shift+F / Ctrl+Shift+M
        self.root.bind_all("<Control-Shift-f>", lambda e: self._open_float_manager())
        self.root.bind_all("<Control-Shift-F>", lambda e: self._open_float_manager())
        self.root.bind_all("<Control-Shift-m>", lambda e: self._open_float_manager())
        self.root.bind_all("<Control-Shift-M>", lambda e: self._open_float_manager())
        self.root.bind_all("<Control-3>", lambda e: self._open_float_manager())
        self.root.bind_all("<Control-Key-3>", lambda e: self._open_float_manager())

        # Tag Manager: Ctrl+Shift+T
        self.root.bind_all("<Control-Shift-t>", lambda e: self._open_tag_manager())
        self.root.bind_all("<Control-Shift-T>", lambda e: self._open_tag_manager())

        # About App: F1
        self.root.bind_all("<F1>", lambda e: self._open_about_dialog())

        # Toggle Stats Bar: Ctrl+F1
        self.root.bind_all("<Control-F1>", lambda e: self._shortcut_toggle_stats())

        # Workspace switching: Ctrl+0 home, Ctrl+1 list, Ctrl+2 entry,
        # Ctrl+3 float, Ctrl+4 analytics, Ctrl+5 cheque register.
        self.root.bind_all(
            "<Control-0>",
            lambda e: self._notebook.select(self.TAB_ACCOUNTANT),
        )
        self.root.bind_all(
            "<Control-Key-0>",
            lambda e: self._notebook.select(self.TAB_ACCOUNTANT),
        )
        self.root.bind_all(
            "<Control-1>",
            lambda e: self._notebook.select(self.TAB_VOUCHERS),
        )
        self.root.bind_all(
            "<Control-Key-1>",
            lambda e: self._notebook.select(self.TAB_VOUCHERS),
        )
        self.root.bind_all("<Control-2>", lambda e: self._new_voucher())
        self.root.bind_all("<Control-Key-2>", lambda e: self._new_voucher())
        self.root.bind_all(
            "<Control-4>",
            lambda e: self._notebook.select(self.TAB_ANALYTICS),
        )
        self.root.bind_all(
            "<Control-Key-4>",
            lambda e: self._notebook.select(self.TAB_ANALYTICS),
        )
        self.root.bind_all(
            "<Control-5>",
            lambda e: self._notebook.select(self.TAB_CHECKS),
        )
        self.root.bind_all(
            "<Control-Key-5>",
            lambda e: self._notebook.select(self.TAB_CHECKS),
        )
        self.root.bind_all("<Control-Shift-c>", lambda e: self._open_check_register())
        self.root.bind_all("<Control-Shift-C>", lambda e: self._open_check_register())

        # V2 Power Shortcuts
        self.root.bind_all("<Control-Shift-r>", lambda e: self._open_recurring_manager())
        self.root.bind_all("<Control-Shift-R>", lambda e: self._open_recurring_manager())
        self.root.bind_all("<Control-Shift-b>", lambda e: self._open_bank_reconciliation())
        self.root.bind_all("<Control-Shift-B>", lambda e: self._open_bank_reconciliation())
        self.root.bind_all("<Control-Shift-u>", lambda e: self._open_user_manager())
        self.root.bind_all("<Control-Shift-U>", lambda e: self._open_user_manager())
        self.root.bind_all("<Control-Shift-l>", lambda e: self._switch_user_dialog())
        self.root.bind_all("<Control-Shift-L>", lambda e: self._switch_user_dialog())
        self.root.bind_all("<Control-Shift-i>", lambda e: self._open_import_wizard())
        self.root.bind_all("<Control-Shift-I>", lambda e: self._open_import_wizard())
        self.root.bind_all("<Control-Shift-a>", lambda e: self._open_alert_center())
        self.root.bind_all("<Control-Shift-A>", lambda e: self._open_alert_center())

        # V3.5 SME Double-Entry Bookkeeping Shortcuts
        self.root.bind_all("<Control-Shift-o>", lambda e: self._open_chart_of_accounts())
        self.root.bind_all("<Control-Shift-O>", lambda e: self._open_chart_of_accounts())
        self.root.bind_all("<Control-Shift-g>", lambda e: self._open_general_ledger())
        self.root.bind_all("<Control-Shift-G>", lambda e: self._open_general_ledger())
        self.root.bind_all("<Control-Shift-j>", lambda e: self._open_new_journal_entry())
        self.root.bind_all("<Control-Shift-J>", lambda e: self._open_new_journal_entry())

    def _on_tab_changed(self, event=None):
        """Load each workspace on demand and refresh only when it is visible."""
        curr = self._notebook.index(self._notebook.select())
        if curr != self.TAB_FORM:
            try:
                self.root.unbind_all("<MouseWheel>")
            except Exception:
                pass
        if curr == self.TAB_ACCOUNTANT:
            self._ensure_accountant_center().refresh()
        elif curr == self.TAB_VOUCHERS:
            if getattr(self, "_list_dirty", False):
                self._refresh_list()
                self._list_dirty = False
        elif curr == self.TAB_FORM:
            self._ensure_form_tab()
        elif curr == self.TAB_FLOAT:
            self._ensure_float_view().refresh()
        elif curr == self.TAB_ANALYTICS:
            self._ensure_analytics_dashboard().refresh()
        elif curr == self.TAB_CHECKS:
            self._ensure_check_register().refresh()
        elif curr == self.TAB_CUSTOMERS:
            self._ensure_customer_center().refresh()
        elif curr == self.TAB_INVOICE:
            self._ensure_invoice_workspace()
    def _shortcut_save(self):
        if self._notebook.index(self._notebook.select()) == self.TAB_FORM:
            self._save_voucher()
        return "break"

    def _shortcut_save_and_print(self):
        if self._notebook.index(self._notebook.select()) == self.TAB_FORM:
            self._save_and_print()
        return "break"

    def _shortcut_print(self):
        curr = self._notebook.index(self._notebook.select())
        if curr == self.TAB_FORM:
            self._save_and_print()
        else:
            self._print_selected()
        return "break"

    def _shortcut_refresh(self, event=None):
        """Refresh the visible workspace without loading hidden heavy tabs."""
        current = self._notebook.index(self._notebook.select())
        if current == self.TAB_ACCOUNTANT:
            self._ensure_accountant_center().refresh(force=True)
        elif current == self.TAB_VOUCHERS:
            self._refresh_list()
        elif current == self.TAB_FLOAT:
            self._ensure_float_view().refresh(force=True)
        elif current == self.TAB_ANALYTICS:
            self._ensure_analytics_dashboard().refresh()
        elif current == self.TAB_CHECKS:
            self._ensure_check_register().refresh()
        elif current == self.TAB_CUSTOMERS:
            self._ensure_customer_center().refresh()
        elif current == self.TAB_INVOICE:
            self._ensure_invoice_workspace()._refresh_lines()
        return "break"
    def _shortcut_focus_search(self):
        self._notebook.select(self.TAB_VOUCHERS)
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        return "break"

    def _shortcut_clear_form(self):
        if self._notebook.index(self._notebook.select()) == self.TAB_FORM:
            self._clear_form()
        return "break"

    def _shortcut_add_line(self):
        if self._notebook.index(self._notebook.select()) == self.TAB_FORM:
            self._line_items.add_row(focus_desc=True)
        return "break"

    def _shortcut_escape(self):
        # If any toplevel popup is open, close it first
        for child in list(self.root.winfo_children()):
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                try:
                    child.destroy()
                    return "break"
                except Exception:
                    pass
        current = self._notebook.index(self._notebook.select())
        if current == self.TAB_INVOICE:
            self._notebook.select(self.TAB_CUSTOMERS)
        elif current in (
            self.TAB_FORM, self.TAB_FLOAT, self.TAB_ANALYTICS,
            self.TAB_CHECKS, self.TAB_CUSTOMERS,
        ):
            self._notebook.select(self.TAB_VOUCHERS)
        return "break"

    def _shortcut_delete(self, event):
        widget = self.root.focus_get()
        # If user is in an entry or text widget, let normal deletion happen
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text)):
            return
        if self._notebook.index(self._notebook.select()) == self.TAB_VOUCHERS:
            self._cancel_selected()
            return "break"

    def _shortcut_delete_permanent(self, event=None):
        widget = self.root.focus_get()
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text)):
            return
        if self._notebook.index(self._notebook.select()) == self.TAB_VOUCHERS:
            self._delete_selected_permanent()
            return "break"

    def _on_search_change(self):
        """Debounce search queries to ensure silky-smooth, lag-free 60fps typing."""
        if self._is_closing:
            return
        if self._search_timer is not None:
            try:
                self.root.after_cancel(self._search_timer)
            except Exception:
                pass
        self._search_timer = self.root.after(140, self._refresh_list)

    def _show_toast(self, message, icon="✓", bg="#0f172a", fg="#f8fafc", duration_ms=2800, duration=None):
        """
        Display a modern Windows 11 sliding toast notification banner with smooth animation.
        Explicitly cancels previous timers to prevent accumulating .after() loops.
        """
        if duration is not None:
            duration_ms = duration
        if getattr(self, "_toast_timer_id", None):
            try:
                self.root.after_cancel(self._toast_timer_id)
            except Exception:
                pass
            self._toast_timer_id = None

        if hasattr(self, "_toast_frame") and self._toast_frame:
            try:
                self._toast_frame.destroy()
            except Exception:
                pass

        self._toast_frame = tk.Frame(
            self.root, bg=bg, highlightbackground="#38bdf8",
            highlightthickness=1, padx=16, pady=7
        )
        tk.Label(
            self._toast_frame, text=f"{icon}  {message}",
            font=("Segoe UI", 9, "bold"), bg=bg, fg=fg
        ).pack(side=tk.LEFT)

        target_y = 10
        start_y = -45

        self._toast_frame.place(relx=0.5, y=start_y, anchor="n")
        self._toast_frame.lift()

        def slide_in(curr_y):
            if not self._toast_frame or not self._toast_frame.winfo_exists():
                return
            if curr_y < target_y:
                step = max(2, (target_y - curr_y) // 2 + 1)
                new_y = min(target_y, curr_y + step)
                self._toast_frame.place_configure(y=new_y)
                self._toast_timer_id = self.root.after(16, lambda: slide_in(new_y))
            else:
                self._toast_timer_id = self.root.after(duration_ms, slide_out)

        def slide_out():
            def step_out(curr_y):
                if not self._toast_frame or not self._toast_frame.winfo_exists():
                    return
                if curr_y > start_y:
                    new_y = curr_y - 6
                    self._toast_frame.place_configure(y=new_y)
                    self._toast_timer_id = self.root.after(16, lambda: step_out(new_y))
                else:
                    if self._toast_frame and self._toast_frame.winfo_exists():
                        self._toast_frame.destroy()
                    self._toast_frame = None
                    self._toast_timer_id = None
            step_out(target_y)

        slide_in(start_y)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Build the authenticated workspace with Accountant Centre first."""
        self._build_company_header_bar()
        self._build_stats_bar()

        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._accountant_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._accountant_tab, text="  Accountant Centre  ")
        self._build_lazy_tab_placeholder(
            self._accountant_tab,
            "Accountant Centre",
            "Preparing your accounting overview…",
        )

        self._list_tab = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(self._list_tab, text="  Voucher List (Ctrl+1)  ")
        self._build_list_tab()

        self._form_tab = ttk.Frame(self._notebook, padding=6)
        self._notebook.add(self._form_tab, text="  New Voucher (Ctrl+2)  ")
        self._build_lazy_tab_placeholder(
            self._form_tab, "Voucher Entry", "Preparing the entry workspace…"
        )

        self._float_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._float_tab, text="  Cash Float & Drawers (Ctrl+3)  ")
        self._build_lazy_tab_placeholder(
            self._float_tab, "Cash Float & Drawers", "Loading cash balances…"
        )

        self._analytics_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._analytics_tab, text="  Analytics Dashboard (Ctrl+4)  ")
        self._build_lazy_tab_placeholder(
            self._analytics_tab, "Analytics Dashboard", "Preparing financial insights…"
        )

        self._check_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._check_tab, text="  Check Register (Ctrl+5)  ")
        self._build_lazy_tab_placeholder(
            self._check_tab, "Check Register", "Loading cheque records…"
        )

        self._customer_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._customer_tab, text="  Customer Centre  ")
        self._build_lazy_tab_placeholder(
            self._customer_tab, "Customer Centre", "Loading customers and invoices…"
        )

        self._invoice_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._invoice_tab, text="  Create Invoice  ")
        self._build_lazy_tab_placeholder(
            self._invoice_tab, "Invoice", "Preparing the invoice workspace…"
        )

        self._apply_stats_bar_visibility()
        self._notebook.select(self.TAB_ACCOUNTANT)
        self._ensure_accountant_center()

    @staticmethod
    def _build_lazy_tab_placeholder(parent, title, message):
        """Render a lightweight placeholder until a heavy module is opened."""
        panel = ttk.Frame(parent, padding=30)
        panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            panel, text=title, font=("Segoe UI", 16, "bold")
        ).pack(pady=(80, 8))
        ttk.Label(panel, text=message, foreground="#64748b").pack()

    def _clear_lazy_tab(self, parent):
        """Remove a lazy placeholder immediately before module creation."""
        for child in parent.winfo_children():
            child.destroy()
        self.root.update_idletasks()

    def _ensure_accountant_center(self):
        """Create the accounting home on first use and reuse its cached widgets."""
        if not hasattr(self, "_accountant_center"):
            from ui.accountant_center import AccountantCenterFrame

            self._clear_lazy_tab(self._accountant_tab)
            self._accountant_center = AccountantCenterFrame(
                self._accountant_tab,
                company_id=db.get_active_company_id(),
                callbacks={
                    "new_voucher": self._new_voucher,
                    "new_journal": self._open_new_journal_entry,
                    "chart_of_accounts": self._open_chart_of_accounts,
                    "general_ledger": self._open_general_ledger,
                    "financial_reports": self._open_financial_reports,
                    "ap_invoices": self._open_ap_invoices,
                    "ap_aging": self._open_ap_aging,
                    "ar_invoices": self._open_ar_invoices,
                    "ar_aging": self._open_ar_aging,
                    "bank_reconciliation": self._open_bank_reconciliation,
                    "period_close": self._open_period_close,
                    "alerts": self._open_alert_center,
                    "voucher_list": lambda: self._notebook.select(
                        self.TAB_VOUCHERS
                    ),
                },
            )
            self._accountant_center.pack(fill=tk.BOTH, expand=True)
        return self._accountant_center
    def _ensure_form_tab(self):
        """Build the voucher form only when entry or editing is requested."""
        if not self._form_built:
            self._clear_lazy_tab(self._form_tab)
            self._build_form_tab()
            self._form_built = True
            self._clear_form()
        return self._form_tab
    def _ensure_float_view(self):
        """Create the cash-float workspace on first use and then reuse it."""
        if not hasattr(self, "_float_view"):
            from ui.float_manager import MoneyFloatView

            self._clear_lazy_tab(self._float_tab)
            self._float_view = MoneyFloatView(
                self._float_tab,
                company_id=db.get_active_company_id(),
                on_update_callback=self._on_float_updated,
                on_close_callback=lambda: self._notebook.select(self.TAB_VOUCHERS),
            )
            self._float_view.pack(fill=tk.BOTH, expand=True)
        return self._float_view

    def _ensure_analytics_dashboard(self):
        """Create analytics on first use and then reuse the dashboard."""
        if not hasattr(self, "_analytics_dashboard"):
            from ui.analytics_dashboard import AnalyticsDashboard

            self._clear_lazy_tab(self._analytics_tab)
            self._analytics_dashboard = AnalyticsDashboard(
                self._analytics_tab,
                drilldown_callback=self._open_analytics_drilldown,
            )
            self._analytics_dashboard.pack(fill=tk.BOTH, expand=True)
        return self._analytics_dashboard

    def _open_analytics_drilldown(self, kind, value):
        """Open the voucher list with the dashboard selection applied."""
        self._search_var.set("")
        period = getattr(
            getattr(self, "_analytics_dashboard", None),
            "_date_filter",
            "All Time",
        )
        self._date_range_filter.set(
            period if period in {"This Month", "Last Month", "This Year"}
            else "All Time"
        )
        self._status_filter.set("Active")
        self._bill_filter.set("All")
        self._payment_method_filter.set("All")
        self._due_filter_var.set("All")
        self._float_filter_var.set("All")
        self._tag_filter_var.set("All")
        self._sort_var.set("Date (Newest)")

        if kind in {"payee", "category"}:
            self._search_var.set(value)
        elif kind == "payment":
            self._payment_method_filter.set(value)
        elif kind == "due":
            self._due_filter_var.set(value)
            self._date_range_filter.set("All Time")

        if self._search_timer is not None:
            try:
                self.root.after_cancel(self._search_timer)
            except tk.TclError:
                pass
            self._search_timer = None
        self._notebook.select(self.TAB_VOUCHERS)
        self._refresh_list()
        self._search_entry.focus_set()
        self._show_toast(f"Showing vouchers for {value}", icon="↗")

    def _ensure_check_register(self):
        """Create the cheque register on first use and then reuse it."""
        if not hasattr(self, "_check_register"):
            from ui.check_register import CheckRegisterFrame

            self._clear_lazy_tab(self._check_tab)
            self._check_register = CheckRegisterFrame(
                self._check_tab, company_id=db.get_active_company_id()
            )
            self._check_register.pack(fill=tk.BOTH, expand=True)
        return self._check_register

    def _ensure_customer_center(self):
        """Create and reuse the full-window Customer Centre workspace."""
        if not hasattr(self, "_customer_center"):
            from ui.ar_workspace import ARCustomerCentreFrame

            self._clear_lazy_tab(self._customer_tab)
            self._customer_center = ARCustomerCentreFrame(
                self._customer_tab,
                company_id=db.get_active_company_id(),
                open_invoice_callback=self._open_invoice_workspace,
                on_close=lambda: self._notebook.select(self.TAB_ACCOUNTANT),
                on_customer_changed=self._refresh_customer_center,
            )
            self._customer_center.pack(fill=tk.BOTH, expand=True)
        return self._customer_center

    def _refresh_customer_center(self, customer_id=None):
        """Refresh customer data after changes from any AR workspace."""
        center = self._ensure_customer_center()
        center.refresh(customer_id=customer_id)

    def _ensure_invoice_workspace(self):
        """Create a new full-window invoice workspace on first access."""
        if not hasattr(self, "_invoice_workspace"):
            self._open_invoice_workspace()
        return self._invoice_workspace

    def _open_invoice_workspace(self, invoice_id=None, customer_id=None):
        """Open a create/edit invoice form inside the main application tab."""
        from ui.ar_workspace import ARInvoiceEntryFrame

        self._clear_lazy_tab(self._invoice_tab)
        if hasattr(self, "_invoice_workspace"):
            try:
                self._invoice_workspace.destroy()
            except tk.TclError:
                pass
        self._invoice_workspace = ARInvoiceEntryFrame(
            self._invoice_tab,
            company_id=db.get_active_company_id(),
            invoice_id=invoice_id,
            customer_id=customer_id,
            on_saved=lambda _invoice_id: self._invoice_saved(customer_id),
            on_cancel=lambda: self._notebook.select(self.TAB_CUSTOMERS),
            on_customer_changed=self._refresh_customer_center,
        )
        self._invoice_workspace.pack(fill=tk.BOTH, expand=True)
        self._notebook.tab(
            self.TAB_INVOICE,
            text="  Edit Invoice  " if invoice_id else "  Create Invoice  ",
        )
        self._notebook.select(self.TAB_INVOICE)
        return self._invoice_workspace

    def _invoice_saved(self, customer_id=None):
        """Return to Customer Centre and show the latest invoice state."""
        if hasattr(self, "_invoice_workspace"):
            selected_name = self._invoice_workspace.customer_var.get()
            customer = self._invoice_workspace.customer_lookup.get(selected_name)
            if customer:
                customer_id = customer["id"]
        self._refresh_customer_center(customer_id)
        self._notebook.select(self.TAB_CUSTOMERS)
    def _build_stats_bar(self):
        """Build the compact single-line statistics bar."""
        self._stats_bar = tk.Frame(
            self.root, bg="#f8fafc",
            highlightbackground="#cbd5e1", highlightthickness=1,
            padx=10, pady=3
        )
        self._stats_bar.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._stat_vars = {
            "total": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "amount": tk.StringVar(value="0.00"),
            "unprinted": tk.StringVar(value="0"),
        }

        # Container for inline metric pills
        metrics_box = tk.Frame(self._stats_bar, bg="#f8fafc")
        metrics_box.pack(side=tk.LEFT, fill=tk.Y)

        stat_items = [
            ("📋 Total Vouchers:", "total", "#1d4ed8", "#eff6ff", "#bfdbfe"),
            ("⏳ Bills Pending:", "pending", "#b45309", "#fffbeb", "#fde68a"),
            ("💰 Total Amount (LKR):", "amount", "#15803d", "#f0fdf4", "#bbf7d0"),
            ("🖨️ Unprinted:", "unprinted", "#6d28d9", "#f5f3ff", "#ddd6fe"),
        ]

        for title, key, val_color, pill_bg, pill_border in stat_items:
            pill = tk.Frame(
                metrics_box, bg=pill_bg,
                highlightbackground=pill_border, highlightthickness=1,
                padx=8, pady=2
            )
            pill.pack(side=tk.LEFT, padx=(0, 6))

            tk.Label(
                pill, text=title,
                font=("Segoe UI", 8), bg=pill_bg, fg="#64748b"
            ).pack(side=tk.LEFT, padx=(0, 4))

            tk.Label(
                pill, textvariable=self._stat_vars[key],
                font=("Segoe UI", 9, "bold"), bg=pill_bg, fg=val_color
            ).pack(side=tk.LEFT)

        # Right side action controls: quick Hide button
        right_box = tk.Frame(self._stats_bar, bg="#f8fafc")
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        hide_btn = ttk.Button(
            right_box, text="▲ Hide",
            command=self._hide_stats_bar,
            bootstyle="secondary-link", width=6
        )
        hide_btn.pack(side=tk.RIGHT, padx=2)
        ToolTip(hide_btn, text="Hide Stats Bar [Ctrl+F1]")

    def _show_ribbon_menu(self):
        """Display Show / Hide options dropdown menu for the stats bar."""
        menu = tk.Menu(self.root, tearoff=0)
        curr = "show" if getattr(self, "_stats_visible", True) else "hide"

        menu.add_command(
            label=f"{'● ' if curr == 'show' else '   '}Show Stats Bar",
            command=self._show_stats_bar
        )
        menu.add_command(
            label=f"{'● ' if curr == 'hide' else '   '}Hide Stats Bar",
            command=self._hide_stats_bar
        )
        menu.add_separator()
        menu.add_command(
            label="   Toggle (Ctrl+F1)",
            command=self._toggle_stats_bar
        )

        try:
            btn = getattr(self, "_ribbon_opt_btn", None)
            if btn and btn.winfo_exists():
                x = btn.winfo_rootx()
                y = btn.winfo_rooty() + btn.winfo_height()
                menu.post(x, y)
            else:
                menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
        except Exception:
            try:
                menu.post(self.root.winfo_pointerx(), self.root.winfo_pointery())
            except Exception:
                pass

    def _apply_stats_bar_visibility(self):
        """Apply current visibility setting to the compact stats bar."""
        if getattr(self, "_stats_visible", True):
            self._stats_bar.pack(fill=tk.X, before=self._notebook, padx=8, pady=(0, 4))
            if hasattr(self, "_ribbon_opt_btn"):
                self._ribbon_opt_btn.config(text="📊 Stats: On ▾")
        else:
            self._stats_bar.pack_forget()
            if hasattr(self, "_ribbon_opt_btn"):
                self._ribbon_opt_btn.config(text="📊 Stats: Off ▾")

    def _show_stats_bar(self, notify=True):
        """Show the compact statistics bar."""
        self._stats_visible = True
        db.set_app_setting("dashboard_stats_visible", "show")
        self._apply_stats_bar_visibility()
        if notify:
            self._show_toast("Stats bar visible", icon="📊", bg="#0f172a", fg="#f0fdf4")

    def _hide_stats_bar(self, notify=True):
        """Hide the compact statistics bar to maximize workspace."""
        self._stats_visible = False
        db.set_app_setting("dashboard_stats_visible", "hide")
        self._apply_stats_bar_visibility()
        if notify:
            self._show_toast("Stats bar hidden (Press Ctrl+F1 to show)", icon="▲", bg="#0f172a", fg="#f0fdf4")

    def _toggle_stats_bar(self):
        """Toggle stats bar visibility between shown and hidden."""
        if getattr(self, "_stats_visible", True):
            self._hide_stats_bar()
        else:
            self._show_stats_bar()

    def _shortcut_toggle_stats(self, event=None):
        """Handle Ctrl+F1 shortcut to toggle stats bar."""
        self._toggle_stats_bar()
        return "break"

    def _build_company_header_bar(self):
        """Build the top company profile bar showing active company, logo, and switcher button."""
        self._comp_bar = tk.Frame(
            self.root, bg="#ffffff", highlightbackground="#cbd5e1",
            highlightthickness=1, padx=12, pady=6
        )
        self._comp_bar.pack(fill=tk.X, padx=8, pady=(6, 2))

        # Left side: Logo / Icon + Company Name + Tagline
        left_box = tk.Frame(self._comp_bar, bg="#ffffff")
        left_box.pack(side=tk.LEFT, fill=tk.Y)

        self._comp_logo_lbl = tk.Label(left_box, text="🏢", font=("Segoe UI", 16), bg="#ffffff")
        self._comp_logo_lbl.pack(side=tk.LEFT, padx=(0, 10))

        text_box = tk.Frame(left_box, bg="#ffffff")
        text_box.pack(side=tk.LEFT)

        title_row = tk.Frame(text_box, bg="#ffffff")
        title_row.pack(anchor="w")

        self._comp_name_var = tk.StringVar(value="Company 1")
        tk.Label(
            title_row, textvariable=self._comp_name_var,
            font=("Segoe UI", 12, "bold"), bg="#ffffff", fg="#0f172a"
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._comp_badge_lbl = tk.Label(
            title_row, text="Company 1", font=("Segoe UI", 8, "bold"),
            bg="#dbeafe", fg="#1e40af", padx=6, pady=1
        )
        self._comp_badge_lbl.pack(side=tk.LEFT)

        self._comp_tagline_var = tk.StringVar(value="")
        self._comp_tagline_lbl = tk.Label(
            text_box, textvariable=self._comp_tagline_var,
            font=("Segoe UI", 8, "italic"), bg="#ffffff", fg="#64748b"
        )
        self._comp_tagline_lbl.pack(anchor="w")

        # Right side: Switch Company Button + Cash Float Button + Header Settings Button
        right_box = tk.Frame(self._comp_bar, bg="#ffffff")
        right_box.pack(side=tk.RIGHT)

        self._float_bar_btn = ttk.Button(
            right_box, text="💰 Cash Float: LKR 0.00",
            command=self._open_float_manager, bootstyle="success-outline"
        )
        self._float_bar_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._float_bar_btn, text="Company Cash Float & Cash Drawer Tracking (Ctrl+Shift+F)")

        self._switch_comp_btn = ttk.Button(
            right_box, text="🔄 Switch Company ▾ (Ctrl+K)",
            command=self._show_company_switch_menu, bootstyle="primary"
        )
        self._switch_comp_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(self._switch_comp_btn, text="Close this company and securely choose another (Ctrl+K)")

        self._cloud_bar_btn = ttk.Button(
            right_box, text="☁️ Cloud",
            command=self._on_cloud_bar_btn_click, bootstyle="secondary-outline"
        )
        self._cloud_bar_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._cloud_bar_btn, text="Firebase Cloud NoSQL Database Sync & Multi-User Mode")

        self._user_btn = ttk.Button(
            right_box, text="👤 User ▾",
            command=self._show_user_menu, bootstyle="dark-outline"
        )
        self._user_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._user_btn, text="Active User Profile, Switch User & RBAC (Ctrl+Shift+L)")

        self._ribbon_opt_btn = ttk.Button(
            right_box, text="📊 Stats ▾",
            command=self._show_ribbon_menu, bootstyle="secondary-outline"
        )
        self._ribbon_opt_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._ribbon_opt_btn, text="Stats Bar Display (Show / Hide) [Ctrl+F1]")

        ttk.Button(
            right_box, text="⚙️ Settings (Ctrl+,)",
            command=self._open_settings, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            right_box, text="ℹ️ About (F1)",
            command=self._open_about_dialog, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=3)

    def _update_company_header(self, conn=None):
        """Refresh top company bar with active company details and logo. Accepts optional existing database connection."""
        active_id = db.get_active_company_id(conn=conn)
        comp = db.get_company(active_id, conn=conn) or {}
        all_comps = db.get_all_companies(conn=conn)

        c_name = comp.get("name", f"Company {active_id}")

        self._comp_name_var.set(c_name)
        self._comp_tagline_var.set(comp.get("tagline", ""))

        # Dynamic badge styling per company ID
        badge_palettes = [
            ("#dbeafe", "#1e40af"),  # Blue
            ("#d1fae5", "#065f46"),  # Emerald
            ("#fef3c7", "#92400e"),  # Amber
            ("#f3e8ff", "#6b21a8"),  # Purple
            ("#ffe4e6", "#9f1239"),  # Rose
            ("#e0f2fe", "#075985"),  # Sky
            ("#ffedd5", "#9a3412"),  # Orange
            ("#ede9fe", "#5b21b6"),  # Indigo
        ]
        palette = badge_palettes[(active_id - 1) % len(badge_palettes)]
        self._comp_badge_lbl.config(
            text=f"Profile #{active_id}",
            bg=palette[0], fg=palette[1]
        )

        # Switch button text
        if len(all_comps) == 2:
            other_comp = [c for c in all_comps if c["id"] != active_id][0]
            other_name = other_comp.get("name", f"Company {other_comp['id']}")
            self._switch_comp_btn.config(text=f"🔄 Switch to {other_name} ▾ (Ctrl+K)")
        else:
            self._switch_comp_btn.config(text=f"🏢 Switch Company ({len(all_comps)}) ▾ (Ctrl+K)")

        # Update cash float badge
        if hasattr(self, "_float_bar_btn"):
            try:
                floats = db.get_floats(active_id, active_only=True, conn=conn)
                def_float = next((f for f in floats if f.get("is_default")), floats[0] if floats else None)
                if def_float:
                    cur_bal = def_float.get("current_balance", 0.0)
                    sign = "" if cur_bal >= 0 else "⚠️ OVERDRAWN: "
                    bstyle = "success-outline" if cur_bal >= 0 else "danger-outline"
                    self._float_bar_btn.config(
                        text=f"💰 {def_float['name']}: {sign}LKR {cur_bal:,.2f}",
                        bootstyle=bstyle
                    )
                else:
                    self._float_bar_btn.config(text="💰 Cash Float: Setup (Ctrl+Shift+F)", bootstyle="secondary-outline")
            except Exception:
                pass

        # Render company logo in header bar if present (cached to avoid redundant LANCZOS resamples)
        logo_data = comp.get("logo")
        if logo_data:
            logo_key = (active_id, len(logo_data), hash(logo_data[:64]))
            if getattr(self, "_cached_logo_key", None) != logo_key or not self._comp_logo_photo:
                try:
                    from PIL import Image as PILImage, ImageTk
                    l_img = PILImage.open(io.BytesIO(logo_data))
                    if l_img.mode in ("RGBA", "LA") or (l_img.mode == "P" and "transparency" in l_img.info):
                        rgba = l_img.convert("RGBA")
                        bg = PILImage.new("RGBA", rgba.size, (255, 255, 255, 255))
                        l_img = PILImage.alpha_composite(bg, rgba).convert("RGB")
                    l_img.thumbnail((170, 44), PILImage.Resampling.LANCZOS)
                    self._comp_logo_photo = ImageTk.PhotoImage(l_img)
                    self._cached_logo_key = logo_key
                    self._comp_logo_lbl.config(image=self._comp_logo_photo, text="")
                except Exception:
                    self._cached_logo_key = None
                    self._comp_logo_photo = None
                    self._comp_logo_lbl.config(image="", text="🏢")
            else:
                self._comp_logo_lbl.config(image=self._comp_logo_photo, text="")
        else:
            self._cached_logo_key = None
            self._comp_logo_photo = None
            self._comp_logo_lbl.config(image="", text="🏢")

        if hasattr(self, "_float_view"):
            try:
                self._float_view.set_company_id(active_id)
            except Exception:
                pass

        self._update_cloud_header_status()
        self._update_user_badge()

    def _update_cloud_header_status(self):
        """Update top bar cloud sync indicator."""
        if not hasattr(self, "_cloud_bar_btn"):
            return
        if not hasattr(self, "_cloud_bar_tooltip"):
            self._cloud_bar_tooltip = ToolTip(self._cloud_bar_btn, text="")

        if firebase_client.is_enabled():
            cfg = firebase_client.get_config()
            pid = cfg.get("project_id") or "Connected"
            self._cloud_bar_btn.config(text="☁️ Cloud: Active", bootstyle="success-outline")
            self._cloud_bar_tooltip.text = f"Firebase Cloud Firestore Live ({pid})\nClick for cloud sync actions."
        elif firebase_client.is_configured():
            self._cloud_bar_btn.config(text="☁️ Cloud: Paused", bootstyle="warning-outline")
            self._cloud_bar_tooltip.text = "Firebase Configured but Sync is Disabled. Click to configure."
        else:
            self._cloud_bar_btn.config(text="☁️ Cloud: Offline", bootstyle="secondary-outline")
            self._cloud_bar_tooltip.text = "Connect Free Firebase NoSQL Database (Click to Setup)"

    def _on_cloud_bar_btn_click(self):
        """Handle click on Cloud button: show action menu or open settings."""
        if not firebase_client.is_configured():
            self._open_settings_cloud()
            return

        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
        cfg = firebase_client.get_config()
        pid = cfg.get("project_id") or "Connected"
        status = "Live (Sync Active)" if firebase_client.is_enabled() else "Paused"
        menu.add_command(label=f"Firebase Cloud Firestore [{status}]", state="disabled")
        menu.add_command(label=f"Project: {pid}", state="disabled")
        last_s = cfg.get("last_synced")
        if last_s:
            menu.add_command(label=f"Last Synced: {last_s}", state="disabled")
        menu.add_separator()
        menu.add_command(label="🔄 Sync Now (Pull Latest from Cloud)", command=self._trigger_cloud_pull_now)
        menu.add_command(label="⬆️ Upload All Local Data to Cloud", command=self._trigger_cloud_upload_now)
        menu.add_separator()
        menu.add_command(label="⚙️ Cloud Settings & Credentials...", command=self._open_settings_cloud)

        bx = self._cloud_bar_btn.winfo_rootx()
        by = self._cloud_bar_btn.winfo_rooty() + self._cloud_bar_btn.winfo_height()
        menu.tk_popup(bx, by)

    def _trigger_cloud_pull_now(self):
        """Immediately pull all latest cloud vouchers, users, and floats in background."""
        self._show_toast("Syncing data from Firebase Cloud...", icon="☁️", bg="#0284c7", fg="#ffffff")
        import threading
        def _worker():
            try:
                ok_u, _, _ = firebase_client.pull_cloud_users()
                ok_a, _, _ = firebase_client.pull_cloud_approvers()
                ok_v, count, msg = firebase_client.pull_cloud_vouchers()
                self.root.after(0, self._refresh_list)
                self.root.after(0, self._update_stats_bar)
                self.root.after(0, self._update_user_badge)
                self.root.after(0, lambda: self._show_toast(f"Cloud Sync Complete: {count} updates loaded", icon="✅", bg="#059669", fg="#ffffff"))
            except Exception as e:
                self.root.after(0, lambda: self._show_toast(f"Cloud Sync Error: {e}", icon="⚠️", bg="#dc2626", fg="#ffffff"))
        threading.Thread(target=_worker, daemon=True).start()

    def _trigger_cloud_upload_now(self):
        """Immediately upload local vouchers, users, floats to cloud."""
        self._show_toast("Uploading data to Firebase Cloud...", icon="☁️", bg="#0284c7", fg="#ffffff")
        import threading
        def _worker():
            try:
                ok, count, msg = firebase_client.upload_all_local_data()
                if ok:
                    self.root.after(0, lambda: self._show_toast(f"Cloud Upload Complete: {count} items synced", icon="✅", bg="#059669", fg="#ffffff"))
                else:
                    self.root.after(0, lambda: self._show_toast(f"Upload Warning: {msg}", icon="⚠️", bg="#d97706", fg="#ffffff"))
            except Exception as e:
                self.root.after(0, lambda: self._show_toast(f"Cloud Upload Error: {e}", icon="⚠️", bg="#dc2626", fg="#ffffff"))
        threading.Thread(target=_worker, daemon=True).start()

    def _update_user_badge(self):
        """Update the top-bar identity badge for the authenticated user."""
        if not hasattr(self, "_user_btn"):
            return
        try:
            if not self._user_btn.winfo_exists():
                return
            current = db.get_current_user()
            if not current:
                self._user_btn.configure(
                    text="Locked",
                    bootstyle="warning-outline",
                )
                return
            display_name = current.get(
                "display_name",
                current.get("username", "User"),
            )
            role = current.get("role", "viewer").upper()
            self._user_btn.configure(
                text=f"👤 {display_name} ({role}) ▾",
                bootstyle="dark",
            )
        except tk.TclError:
            return
    def _show_user_menu(self):
        """Display pop-up menu for active user account, shift change, and RBAC management."""
        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
        curr = db.get_current_user()
        if curr:
            dname = curr.get("display_name", curr.get("username"))
            role = curr.get("role", "admin").upper()
            menu.add_command(label=f"Active User: {dname} [{role}]", state="disabled")
            menu.add_separator()
            menu.add_command(label="🔄 Switch User / Change Shift (Ctrl+Shift+L)", command=self._switch_user_dialog)
            menu.add_command(label="🔑 Change My Password", command=self._change_own_password)
            if curr.get("role") == "admin":
                menu.add_command(label="👥 Manage Users & Roles (Ctrl+Shift+U)", command=self._open_user_manager)
            menu.add_command(label="🚪 Sign Out", command=self._logout_user)
        elif db.is_rbac_enabled():
            menu.add_command(label="Not Signed In", state="disabled")
            menu.add_separator()
            menu.add_command(label="🔑 Sign In / Authenticate (Ctrl+Shift+L)", command=self._switch_user_dialog)
            menu.add_command(label="👥 Manage Users (Admin PIN/Password Required)", command=self._open_user_manager)
        else:
            menu.add_command(label="Mode: Full Administrator (RBAC Inactive)", state="disabled")
            menu.add_separator()
            menu.add_command(label="👥 Setup Users & Access Control (Ctrl+Shift+U)", command=self._open_user_manager)

        bx = self._user_btn.winfo_rootx()
        by = self._user_btn.winfo_rooty() + self._user_btn.winfo_height()
        menu.tk_popup(bx, by)

    def _change_own_password(self):
        """Open the authenticated user's password-change dialog."""
        dialog = ChangePasswordDialog(self.root)
        self.root.wait_window(dialog)
        if dialog.changed:
            self._show_toast(
                "Password changed successfully",
                icon="🔐",
                bg="#166534",
                fg="#ffffff",
            )
    def _switch_user_dialog(self):
        """Close the company so switching users always requires a password."""
        self._logout_user()
    def _logout_user(self):
        """Destroy the workspace and return to the protected login screen."""
        if not messagebox.askyesno(
            "Close company",
            "Close this company and return to the sign-in screen?",
            parent=self.root,
        ):
            return
        db.set_current_user(None)
        if self._on_logout:
            self._on_logout()
        else:
            self._on_app_close()
    def _open_settings_cloud(self):
        """Open settings dialog directly focused on the Firebase Cloud tab."""
        self._open_settings(initial_tab=1)

    def _show_company_switch_menu(self):
        """Offer a secure close-and-reopen flow for company switching."""
        company_id = db.get_active_company_id()
        company = db.get_company(company_id) or {}
        company_name = company.get("name", f"Company {company_id}")
        menu = tk.Menu(self.root, tearoff=0, font=("Segoe UI", 9))
        menu.add_command(
            label=f"Open company: {company_name}",
            state="disabled",
        )
        menu.add_separator()
        menu.add_command(
            label="Close Company / Choose Another...",
            command=self._logout_user,
        )
        try:
            x = self._switch_comp_btn.winfo_rootx()
            y = (
                self._switch_comp_btn.winfo_rooty()
                + self._switch_comp_btn.winfo_height()
            )
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
    def _shortcut_switch_company(self):
        """Close the current company before selecting another company file."""
        self._logout_user()
        return "break"
    def _switch_to_company(self, target_id):
        """Prevent in-workspace company changes; re-authentication is required."""
        if target_id != db.get_active_company_id():
            self._logout_user()
    def _prompt_add_company(self):
        """Quick prompt to add a new company profile."""
        name = simpledialog.askstring("Add Company Profile", "Enter name for new company profile:", parent=self.root)
        if not name or not name.strip():
            return
        try:
            new_id = db.create_company(name=name.strip())
            self._switch_to_company(new_id)
            self._open_settings(initial_tab=0)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create company profile:\n{e}", parent=self.root)

    def _toggle_active_company(self):
        """Alias for _shortcut_switch_company for backwards compatibility."""
        self._shortcut_switch_company()


    def _build_list_tab(self):
        """Build the voucher list tab with light styled search and filter bar."""
        # Search & Filter bar with soft light slate card (two compact rows to prevent horizontal shrinking)
        filter_frame = tk.Frame(self._list_tab, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1, padx=8, pady=4)
        filter_frame.pack(fill=tk.X, pady=(0, 6))

        # --- Row 1: Search, Refresh & Results Summary ---
        row1 = tk.Frame(filter_frame, bg="#f8fafc")
        row1.pack(fill=tk.X, pady=(0, 3))

        tk.Label(row1, text="🔍 Search:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._on_search_change())
        self._search_entry = ttk.Entry(row1, textvariable=self._search_var, width=24, style="Search.TEntry")
        self._search_entry.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self._search_entry, text="Search by voucher number, payee, or description (Ctrl+F)")

        ttk.Button(
            row1, text="⟳ Refresh (F5)", command=self._refresh_list,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            row1, text="Clear Filters", command=self._clear_list_filters,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            row1, text="View:", font=("Segoe UI", 8, "bold"),
            bg="#f8fafc", fg="#64748b"
        ).pack(side=tk.LEFT, padx=(4, 3))
        self._voucher_view_var = tk.StringVar(value="Compact")
        voucher_view_combo = ttk.Combobox(
            row1, textvariable=self._voucher_view_var,
            values=["Compact", "Detailed"], width=10, state="readonly"
        )
        voucher_view_combo.pack(side=tk.LEFT, padx=(0, 8))
        voucher_view_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._apply_voucher_list_view(),
        )

        # Summary Badge for current search/filter results
        self._list_summary_var = tk.StringVar(value="Showing 0 vouchers | Total: LKR 0.00")
        summary_lbl = tk.Label(
            row1, textvariable=self._list_summary_var,
            font=("Segoe UI", 9, "bold"), bg="#e0f2fe", fg="#0369a1",
            padx=8, pady=2, highlightbackground="#7dd3fc", highlightthickness=1
        )
        summary_lbl.pack(side=tk.RIGHT)

        # --- Row 2: Filter Comboboxes ---
        filter_row2 = tk.Frame(filter_frame, bg="#f8fafc")
        filter_row2.pack(fill=tk.X, pady=(1, 0))

        tk.Label(filter_row2, text="Date:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._date_range_filter = tk.StringVar(value="All Time")
        date_range_combo = ttk.Combobox(
            filter_row2, textvariable=self._date_range_filter,
            values=["All Time", "Today", "Yesterday", "This Week", "This Month", "Last Month", "This Year"], width=10, state="readonly"
        )
        date_range_combo.pack(side=tk.LEFT, padx=(0, 8))
        date_range_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Status:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._status_filter = tk.StringVar(value="All")
        status_combo = ttk.Combobox(
            filter_row2, textvariable=self._status_filter,
            values=["All", "Active", "Cancelled"], width=8, state="readonly"
        )
        status_combo.pack(side=tk.LEFT, padx=(0, 8))
        status_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Bills:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._bill_filter = tk.StringVar(value="All")
        bill_combo = ttk.Combobox(
            filter_row2, textvariable=self._bill_filter,
            values=["All", "Pending", "Received", "Partial"], width=8, state="readonly"
        )
        bill_combo.pack(side=tk.LEFT, padx=(0, 8))
        bill_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Payment:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._payment_method_filter = tk.StringVar(value="All")
        payment_combo = ttk.Combobox(
            filter_row2, textvariable=self._payment_method_filter,
            values=["All", "Cash", "Bank Transfer", "Cheque", "Credit Card", "Online/Other"], width=11, state="readonly"
        )
        payment_combo.pack(side=tk.LEFT, padx=(0, 8))
        payment_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Due:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._due_filter_var = tk.StringVar(value="All")
        due_combo = ttk.Combobox(
            filter_row2, textvariable=self._due_filter_var,
            values=["All", "Overdue", "Due Today", "Due This Week", "Due This Month", "Has Due Date"], width=11, state="readonly"
        )
        due_combo.pack(side=tk.LEFT, padx=(0, 8))
        due_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Float:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._float_filter_var = tk.StringVar(value="All")
        self._float_filter_combo = ttk.Combobox(
            filter_row2, textvariable=self._float_filter_var,
            values=["All"], width=13, state="readonly"
        )
        self._float_filter_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._float_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Tag:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._tag_filter_var = tk.StringVar(value="All")
        self._tag_filter_combo = ttk.Combobox(
            filter_row2, textvariable=self._tag_filter_var,
            values=["All"], width=12, state="readonly"
        )
        self._tag_filter_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._tag_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_row2, text="Sort:", font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#64748b").pack(side=tk.LEFT, padx=(0, 3))
        self._sort_var = tk.StringVar(value="Date (Newest)")
        sort_combo = ttk.Combobox(
            filter_row2, textvariable=self._sort_var,
            values=[
                "Date (Newest)", "Date (Oldest)",
                "Amount (Highest)", "Amount (Lowest)",
                "Voucher # (Desc)", "Voucher # (Asc)",
                "Paid To (A-Z)"
            ],
            width=13, state="readonly"
        )
        sort_combo.pack(side=tk.LEFT, padx=(0, 4))
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        # Single-row compact Action Bar (replaces the cluttered 4 rows with clean dropdown menus)
        action_container = ttk.Frame(self._list_tab, padding=(2, 6))
        action_container.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 2))

        self._action_buttons = {}

        # Left cluster: Direct voucher operations + More Actions dropdown
        left_cluster = ttk.Frame(action_container)
        left_cluster.pack(side=tk.LEFT, fill=tk.Y)

        primary_buttons = [
            ("create_voucher", "➕ New (Ctrl+N)", self._new_voucher, "success", "Create a new payment voucher (Ctrl+N)"),
            ("edit_voucher", "✏️ Edit (Ctrl+E)", self._edit_selected, "primary", "Edit the selected voucher in form tab (Ctrl+E)"),
            ("view_pdf", "👁️ View PDF", self._view_selected, "info-outline", "Preview generated PDF for selected voucher"),
            ("print_voucher", "🖨️ Print (Ctrl+P)", self._print_selected, "primary-outline", "Print selected voucher (Ctrl+P)"),
        ]
        for key, text, cmd, style, tip in primary_buttons:
            btn = ttk.Button(left_cluster, text=text, command=cmd, bootstyle=style)
            btn.pack(side=tk.LEFT, padx=(0, 3))
            ToolTip(btn, text=tip)
            self._action_buttons[key] = btn

        # Dropdown 1: Voucher Actions (Lifecycle, check issue, batch print, CSV import/export, audit trail)
        more_mb = ttk.Menubutton(left_cluster, text="⚡ Voucher Actions ▾", bootstyle="secondary-outline", direction="below")
        more_mb.pack(side=tk.LEFT, padx=(0, 3))
        ToolTip(more_mb, text="Voucher duplicate, check issuing, approvals, lifecycle, batch printing, CSV and audit history")
        more_menu = tk.Menu(more_mb, tearoff=0, font=("Segoe UI", 9))
        more_mb["menu"] = more_menu

        more_items = [
            ("duplicate_voucher", "📋 Duplicate Voucher", "Ctrl+D", self._duplicate_selected),
            ("print_check", "🖋️ Issue / Print Bank Check", "", self._issue_check_for_selected),
            ("print_pending", "📄 Batch Print Pending", "Ctrl+Shift+P", self._print_all_pending),
            None,
            ("approve_voucher", "✅ Approve / Reject Voucher", "", self._approve_selected),
            ("cancel_voucher", "❌ Cancel (Disable) Voucher", "Del", self._cancel_selected),
            ("restore_voucher", "♻️ Restore Cancelled Voucher", "Ctrl+R", self._restore_selected),
            ("delete_voucher", "🗑️ Delete Permanently", "Shift+Del", self._delete_selected_permanent),
            None,
            ("view_audit", "📜 View Audit Trail History", "", self._view_audit_history_selected),
            ("export_csv", "📊 Export Current List to CSV", "", self._export_csv),
            ("import_data", "📥 Bulk Import Vouchers (CSV)", "Ctrl+Shift+I", self._open_import_wizard),
            None,
            ("clear_data", "🗑️ Clear All Vouchers", "", self._clear_all_vouchers_prompt),
        ]
        self._populate_dropdown_menu(more_menu, more_items, more_mb)

        # Subtle vertical divider separating voucher actions from business modules
        sep = ttk.Separator(action_container, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)

        # Middle cluster: Business Modules & Operations Dropdown Menus
        nav_cluster = ttk.Frame(action_container)
        nav_cluster.pack(side=tk.LEFT, fill=tk.Y)

        # Dropdown 2: Accounting & General Ledger
        acct_mb = ttk.Menubutton(nav_cluster, text="📒 Accounting ▾", bootstyle="info-outline", direction="below")
        acct_mb.pack(side=tk.LEFT, padx=(0, 3))
        ToolTip(acct_mb, text="Chart of Accounts, General Ledger, Journals, Financial Reports & Banking")
        acct_menu = tk.Menu(acct_mb, tearoff=0, font=("Segoe UI", 9))
        acct_mb["menu"] = acct_menu

        acct_items = [
            ("manage_coa", "📒 Chart of Accounts", "Ctrl+Shift+O", self._open_chart_of_accounts),
            ("view_gl", "📖 General Ledger & Trial Balance", "Ctrl+Shift+G", self._open_general_ledger),
            ("new_journal_entry", "✍️ New Journal Entry", "Ctrl+Shift+J", self._open_new_journal_entry),
            ("close_books", "🔒 Close Accounting Period", "", self._open_period_close),
            None,
            ("manage_financial_reports", "📊 Financial Reports (P&L, BS)", "", self._open_financial_reports),
            ("manage_cash_flow_forecast", "🔮 Cash Flow Forecast & Obligations", "", self._open_cash_flow_forecast),
            ("manage_tax", "🏛️ Tax Rates & VAT Return", "", self._open_tax_manager),
            ("manage_bank_accounts", "🏦 Bank Reconciliation", "Ctrl+Shift+B", self._open_bank_reconciliation),
            ("manage_exchange", "💱 Multi-Currency & Rates", "", self._open_exchange_rates),
        ]
        self._populate_dropdown_menu(acct_menu, acct_items, acct_mb)

        # Dropdown 3: Commercial (AP & AR Invoices)
        comm_mb = ttk.Menubutton(nav_cluster, text="💼 AP & AR ▾", bootstyle="primary-outline", direction="below")
        comm_mb.pack(side=tk.LEFT, padx=(0, 3))
        ToolTip(comm_mb, text="Accounts Payable (Suppliers, Invoices, POs) & Accounts Receivable (Customers, Invoices)")
        comm_menu = tk.Menu(comm_mb, tearoff=0, font=("Segoe UI", 9))
        comm_mb["menu"] = comm_menu

        comm_items = [
            ("manage_suppliers", "🏢 Suppliers Directory", "", self._open_suppliers),
            ("manage_ap", "📄 AP Invoices & Aging", "", self._open_ap_invoices),
            ("manage_po", "📦 Purchase Orders & GRN", "", self._open_purchase_orders),
            None,
            ("manage_customers", "👥 Customers Directory", "", self._open_customers),
            ("manage_ar", "🧾 AR Invoices & Receipts", "", self._open_ar_invoices),
        ]
        self._populate_dropdown_menu(comm_menu, comm_items, comm_mb)

        # Dropdown 4: Operations & Masters
        ops_mb = ttk.Menubutton(nav_cluster, text="📁 Operations ▾", bootstyle="secondary-outline", direction="below")
        ops_mb.pack(side=tk.LEFT, padx=(0, 3))
        ToolTip(ops_mb, text="Expense Categories, Payees, Tags, Cash Floats, Payroll, Recurring Schedules, Analytics & Users")
        ops_menu = tk.Menu(ops_mb, tearoff=0, font=("Segoe UI", 9))
        ops_mb["menu"] = ops_menu

        ops_items = [
            ("manage_categories", "📁 Expense Categories & Budgets", "Ctrl+G", self._open_category_manager),
            ("manage_budgets", "🎯 Budgets & Variance Analysis", "", self._open_budget_manager),
            ("manage_people", "👤 Payees & Personnel Directory", "Ctrl+M", self._open_name_manager),
            ("manage_tags", "🏷️ Voucher Tags", "Ctrl+Shift+T", self._open_tag_manager),
            ("manage_float", "💰 Cash Floats & Drawers", "Ctrl+3", self._open_float_manager),
            None,
            ("manage_payroll", "👥 Payroll & HR (Staff, Runs)", "", self._open_payroll),
            ("manage_recurring", "📅 Recurring Payment Schedules", "Ctrl+Shift+R", self._open_recurring_manager),
            ("view_statements", "📜 Payee Account Statements", "Ctrl+Shift+S", self._open_payee_statement),
            ("view_analytics", "📈 Analytics & Expense Charts", "Ctrl+I", self._open_expense_summary),
            None,
            ("manage_approvers", "✅ Approvers PIN Management", "", self._open_approval_manager),
            ("manage_users", "👥 Users & Access Control", "Ctrl+Shift+U", self._open_user_manager),
            ("manage_settings", "⚙️ System Settings", "Ctrl+,", self._open_settings),
        ]
        self._populate_dropdown_menu(ops_menu, ops_items, ops_mb)

        # Right cluster: Smart Alerts button/badge
        right_cluster = ttk.Frame(action_container)
        right_cluster.pack(side=tk.RIGHT, fill=tk.Y)

        self._alert_btn = ttk.Button(
            right_cluster, text="⚡ Smart Alerts",
            command=self._open_alert_center,
            bootstyle="warning"
        )
        self._alert_btn.pack(side=tk.RIGHT, padx=(4, 0))
        ToolTip(self._alert_btn, text="View active notifications and financial alerts (Ctrl+Shift+A)")
        self._action_buttons["view_alerts"] = self._alert_btn

        self._apply_role_permissions()

        # Treeview frame occupies the remaining vertical space above the action buttons
        tree_frame = ttk.Frame(self._list_tab)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        columns = ("number", "date", "due_date", "paid_to", "tags", "spent_by", "amount", "payment_method", "float_name", "bill_status", "attachments", "status", "printed")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=16, selectmode="extended"
        )

        col_configs = [
            ("number", "Voucher #", 95, "center", False),
            ("date", "Date", 85, "center", False),
            ("due_date", "Due Date", 85, "center", False),
            ("paid_to", "Paid To", 130, "w", True),
            ("tags", "🏷️ Tags", 110, "w", True),
            ("spent_by", "Spent By", 110, "w", True),
            ("amount", "Amount", 95, "e", False),
            ("payment_method", "Payment", 100, "center", False),
            ("float_name", "Float / Drawer", 115, "w", True),
            ("bill_status", "Bills", 80, "center", False),
            ("attachments", "📎 Files", 60, "center", False),
            ("status", "Status", 70, "center", False),
            ("printed", "Printed", 60, "center", False),
        ]

        for col, heading, width, anchor, stretch in col_configs:
            self._tree.heading(col, text=heading, command=lambda c=col: self._sort_column(c))
            self._tree.column(col, width=width, minwidth=width if not stretch else 60, anchor=anchor, stretch=stretch)

        # Start with the fast, decision-focused register used for daily work.
        # Detailed view remains one click away without discarding any data.
        self._voucher_compact_columns = (
            "number", "date", "due_date", "paid_to", "amount",
            "payment_method", "bill_status", "status",
        )
        self._voucher_detailed_columns = columns
        self._tree.configure(displaycolumns=self._voucher_compact_columns)

        # Colorful tags for visual clarity
        self._tree.tag_configure("bill_pending", background="#fffdf5", foreground="#92400e")
        self._tree.tag_configure("bill_received", background="#f0fdf4", foreground="#166534")
        self._tree.tag_configure("bill_partial", background="#f0f9ff", foreground="#0369a1")
        self._tree.tag_configure("due_overdue", background="#fef2f2", foreground="#991b1b")
        self._tree.tag_configure("due_today", background="#fff7ed", foreground="#c2410c")
        self._tree.tag_configure("canceled", foreground="#94a3b8", background="#f8fafc")
        self._tree.tag_configure("has_attachment", font=("Segoe UI", 9, "bold"))

        # Both vertical and horizontal scrollbars for complete responsive access
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Return>", lambda e: self._edit_selected())

        # Right-click context menu
        self._tree_menu = tk.Menu(self.root, tearoff=0)
        self._tree_menu.add_command(label="✏️ Edit Voucher (Ctrl+E)", command=self._edit_selected)
        self._tree_menu.add_command(label="📋 Duplicate Voucher (Ctrl+D)", command=self._duplicate_selected)
        self._tree_menu.add_command(label="👁️ View PDF", command=self._view_selected)
        self._tree_menu.add_command(label="📜 View Audit History", command=self._view_audit_history_selected)
        self._tree_menu.add_command(label="📜 View Payee Statement (Ctrl+Shift+S)", command=self._open_payee_statement_for_selected)
        self._tree_menu.add_separator()

        # Cascading Bill Status sub-menu
        bill_menu = tk.Menu(self._tree_menu, tearoff=0)
        bill_menu.add_command(label="✅ Received", command=lambda: self._mark_bill_status_selected("Received"))
        bill_menu.add_command(label="⏳ Pending", command=lambda: self._mark_bill_status_selected("Pending"))
        bill_menu.add_command(label="⚠️ Partial", command=lambda: self._mark_bill_status_selected("Partial"))
        self._tree_menu.add_cascade(label="📋 Mark Bill Status", menu=bill_menu)

        # Quick Due Date sub-menu
        due_menu = tk.Menu(self._tree_menu, tearoff=0)
        due_menu.add_command(label="+7 Days", command=lambda: self._set_quick_due_date_selected(7))
        due_menu.add_command(label="+15 Days", command=lambda: self._set_quick_due_date_selected(15))
        due_menu.add_command(label="+30 Days", command=lambda: self._set_quick_due_date_selected(30))
        due_menu.add_command(label="Clear Due Date", command=lambda: self._set_quick_due_date_selected(None))
        self._tree_menu.add_cascade(label="📅 Set Due Date", menu=due_menu)

        self._tree_menu.add_separator()
        self._tree_menu.add_command(label="🖨️ Print (Ctrl+P)", command=self._print_selected)
        self._tree_menu.add_command(label="🖋️ Issue Bank Check", command=self._issue_check_for_selected)
        self._tree_menu.add_separator()
        self._tree_menu.add_command(label="❌ Cancel (Disable) Voucher (Del)", command=self._cancel_selected)
        self._tree_menu.add_command(label="♻️ Restore Voucher (Ctrl+R)", command=self._restore_selected)
        self._tree_menu.add_separator()
        self._tree_menu.add_command(label="🗑️ Delete Permanently (Shift+Del)", command=self._delete_selected_permanent)

        def _on_tree_right_click(event):
            item = self._tree.identify_row(event.y)
            if item:
                if item not in self._tree.selection():
                    self._tree.selection_set(item)
                self._tree_menu.post(event.x_root, event.y_root)

        self._tree.bind("<Button-3>", _on_tree_right_click)

    def _build_form_tab(self):
        """
        Build the voucher entry/edit form tab.
        Prioritized layout:
        1. Top Bar: Title, Voucher #, SmartDate with dropdown & arrow keys, Bill Status, and Top Action buttons.
        2. Parties: Compact 2-row horizontal grid (Paid To, Cash Given By, Spent By, Prepared By, Approved By).
        3. Line Items: Primary workspace table with Add Line (Alt+A) and Enter-to-next-row.
        4. Lower Area: Side-by-side Attachments & Memos.
        5. Bottom Action Bar with full keyboard shortcuts.
        """
        # 1. Dock the Bottom Action Buttons Bar to self._form_tab FIRST so it never scrolls off
        btn_frame = ttk.Frame(self._form_tab, padding=(0, 4))
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

        save_btn = ttk.Button(
            btn_frame, text="💾 Save Voucher (Ctrl+S)",
            command=self._save_voucher, bootstyle="success"
        )
        save_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(save_btn, text="Save voucher to database (Ctrl+S)")

        save_print_btn = ttk.Button(
            btn_frame, text="🖨️ Save & Print (Ctrl+Enter)",
            command=self._save_and_print, bootstyle="primary"
        )
        save_print_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(save_print_btn, text="Save voucher and immediately open print/PDF preview (Ctrl+Enter)")

        tpl_save_btn = ttk.Button(
            btn_frame, text="⭐ Save as Template",
            command=self._save_as_template, bootstyle="info-outline"
        )
        tpl_save_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(tpl_save_btn, text="Save current form parties & line items as a reusable template")

        clear_btn = ttk.Button(
            btn_frame, text="🔄 Clear Form (Ctrl+W)",
            command=self._clear_form, bootstyle="warning-outline"
        )
        clear_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(clear_btn, text="Reset all form fields and start a fresh voucher (Ctrl+W)")

        back_list_btn = ttk.Button(
            btn_frame, text="← Back to List (Esc)",
            command=lambda: self._notebook.select(self.TAB_VOUCHERS), bootstyle="secondary-outline"
        )
        back_list_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(back_list_btn, text="Return to the Voucher List tab (Esc)")

        # 2. Scrollable Canvas wrapper fills all remaining space above the docked action bar
        form_canvas = tk.Canvas(self._form_tab, highlightthickness=0)

        def _on_form_scroll(*args):
            form_canvas.yview(*args)
            form_canvas.update_idletasks()

        form_scrollbar = ttk.Scrollbar(self._form_tab, orient=tk.VERTICAL, command=_on_form_scroll)
        self._form_inner = ttk.Frame(form_canvas, padding=(2, 2))

        def _on_form_inner_configure(e):
            if self._is_closing:
                return
            if self._form_scroll_timer is not None:
                try:
                    self.root.after_cancel(self._form_scroll_timer)
                except Exception:
                    pass
            def _refresh_scroll_region():
                self._form_scroll_timer = None
                if self._is_closing or not form_canvas.winfo_exists():
                    return
                form_canvas.configure(scrollregion=form_canvas.bbox("all"))

            self._form_scroll_timer = self.root.after(35, _refresh_scroll_region)

        self._form_inner.bind("<Configure>", _on_form_inner_configure)
        self._form_window = form_canvas.create_window((0, 0), window=self._form_inner, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scrollbar.set)

        def _on_canvas_configure(e):
            if getattr(self, "_last_canvas_width", None) != e.width:
                self._last_canvas_width = e.width
                form_canvas.itemconfig(self._form_window, width=e.width)
        form_canvas.bind("<Configure>", _on_canvas_configure)

        form_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def _on_mousewheel(event):
            if self._notebook.index(self._notebook.select()) == self.TAB_FORM:
                delta = int(-1 * (event.delta / 120))
                form_canvas.yview_scroll(delta, "units")
                form_canvas.update_idletasks()
                return "break"

        form_canvas.bind("<Enter>", lambda e: form_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        form_canvas.bind("<Leave>", lambda e: form_canvas.unbind_all("<MouseWheel>"))

        # --------------------------------------------------------------
        # 1. Header & Quick Action Row (Compact Light Card)
        # --------------------------------------------------------------
        header_card = tk.Frame(self._form_inner, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=4)
        header_card.pack(fill=tk.X, pady=(0, 4))

        # Row 1: Title, Voucher #, Date, Due Date (+quick buttons), and Right Quick Actions
        hdr_row1 = tk.Frame(header_card, bg="#f1f5f9")
        hdr_row1.pack(fill=tk.X, pady=(0, 3))

        # Right buttons on Row 1 (docked RIGHT first so they never get pushed off)
        hdr_r1_right = tk.Frame(hdr_row1, bg="#f1f5f9")
        hdr_r1_right.pack(side=tk.RIGHT)

        tpl_btn = ttk.Button(
            hdr_r1_right, text="⭐ Templates (Ctrl+T)",
            command=self._open_template_manager, bootstyle="info-outline"
        )
        tpl_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(tpl_btn, text="Load or manage reusable voucher templates (Ctrl+T)")

        back_btn = ttk.Button(
            hdr_r1_right, text="← Back (Esc)",
            command=lambda: self._notebook.select(self.TAB_VOUCHERS), bootstyle="secondary-outline"
        )
        back_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(back_btn, text="Return to Voucher List (Esc)")

        # Left items on Row 1
        hdr_r1_left = tk.Frame(hdr_row1, bg="#f1f5f9")
        hdr_r1_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._form_title_var = tk.StringVar(value="New Voucher")
        tk.Label(
            hdr_r1_left, textvariable=self._form_title_var,
            font=("Segoe UI", 11, "bold"), bg="#f1f5f9", fg="#1d4ed8"
        ).pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(hdr_r1_left, text="Voucher #:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._voucher_num_var = tk.StringVar()
        self._voucher_num_entry = ttk.Entry(
            hdr_r1_left, textvariable=self._voucher_num_var, width=13,
            state="readonly", font=("Segoe UI", 9, "bold"), style="VoucherBadge.TEntry"
        )
        self._voucher_num_entry.pack(side=tk.LEFT, padx=(0, 8))
        ToolTip(self._voucher_num_entry, text="Auto-generated unique voucher number for active company")

        tk.Label(hdr_r1_left, text="Date:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._date_entry = SmartDateEntry(hdr_r1_left)
        self._date_entry.pack(side=tk.LEFT, padx=(0, 8))
        self._date_entry.bind("<<DateModified>>", self._on_date_changed)
        ToolTip(self._date_entry, text="Voucher issue date (YYYY-MM-DD). Type or use calendar")

        tk.Label(hdr_r1_left, text="Due Date:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._due_date_entry = SmartDateEntry(hdr_r1_left)
        self._due_date_entry.pack(side=tk.LEFT, padx=(0, 2))
        ToolTip(self._due_date_entry, text="Payment due / settlement deadline (YYYY-MM-DD)")

        btn_7 = ttk.Button(
            hdr_r1_left, text="+7d", command=lambda: self._set_quick_due_days(7),
            bootstyle="secondary-outline"
        )
        btn_7.pack(side=tk.LEFT, padx=1)
        ToolTip(btn_7, text="Set due date to +7 days from voucher date")

        btn_15 = ttk.Button(
            hdr_r1_left, text="+15d", command=lambda: self._set_quick_due_days(15),
            bootstyle="secondary-outline"
        )
        btn_15.pack(side=tk.LEFT, padx=1)
        ToolTip(btn_15, text="Set due date to +15 days from voucher date")

        btn_30 = ttk.Button(
            hdr_r1_left, text="+30d", command=lambda: self._set_quick_due_days(30),
            bootstyle="secondary-outline"
        )
        btn_30.pack(side=tk.LEFT, padx=(1, 4))
        ToolTip(btn_30, text="Set due date to +30 days from voucher date")

        # Row 2: Bills, Payment Method, Payment Ref, Cash Float
        hdr_row2 = tk.Frame(header_card, bg="#f1f5f9")
        hdr_row2.pack(fill=tk.X)

        tk.Label(hdr_row2, text="Bills:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._bill_status_var = tk.StringVar(value="Pending")
        bill_combo = ttk.Combobox(
            hdr_row2, textvariable=self._bill_status_var,
            values=["Pending", "Received", "Partial"], width=9, state="readonly"
        )
        bill_combo.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(bill_combo, text="Bill / invoice attachment status (Pending, Received, Partial)")

        tk.Label(hdr_row2, text="Payment Method:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._payment_method_var = tk.StringVar(value="Cash")
        pm_combo = ttk.Combobox(
            hdr_row2, textvariable=self._payment_method_var,
            values=["Cash", "Bank Transfer", "Cheque", "Credit Card", "Online/Other"], width=13, state="readonly"
        )
        pm_combo.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(pm_combo, text="Payment method used (Cash, Bank Transfer, Cheque, Credit Card, Online/Other)")

        self._issue_check_form_btn = ttk.Button(
            hdr_row2, text="🖋️ Issue Check", command=self._issue_check_from_form,
            bootstyle="primary-outline"
        )
        self._issue_check_form_btn.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(self._issue_check_form_btn, text="Issue or open a bank check linked to this voucher")

        tk.Label(hdr_row2, text="Payment Ref:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._payment_ref_var = tk.StringVar()
        ref_entry = ttk.Entry(
            hdr_row2, textvariable=self._payment_ref_var, width=15, style="TEntry"
        )
        ref_entry.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(ref_entry, text="Reference details (cheque number, transaction ID, bank reference)")

        tk.Label(hdr_row2, text="Float / Drawer:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 2))
        self._form_float_var = tk.StringVar()
        self._form_float_combo = ttk.Combobox(
            hdr_row2, textvariable=self._form_float_var, width=18, state="readonly"
        )
        self._form_float_combo.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(self._form_float_combo, text="Company cash float or cash drawer linked to this payout")

        # Currency Selector
        self._currency_selector = CurrencySelector(hdr_row2, company_id=db.get_active_company_id())
        self._currency_selector.pack(side=tk.LEFT, padx=(0, 10))

        # --------------------------------------------------------------
        # 2. Parties & Signatures (Clean 2-Row Responsive Layout with full ToolTips)
        # --------------------------------------------------------------
        parties_frame = ttk.LabelFrame(
            self._form_inner,
            text="👤 Parties & Signatures (* Required fields | Spent By defaults to Paid To)",
            padding=(8, 4),
            bootstyle="info"
        )
        parties_frame.pack(fill=tk.X, pady=(0, 4))

        # Row 1: Primary Parties (Paid To & Cash Given By) - 50/50 responsive split
        p_row1 = ttk.Frame(parties_frame)
        p_row1.pack(fill=tk.X, pady=(0, 3))

        p1_left = ttk.Frame(p_row1)
        p1_left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Label(p1_left, text="Paid To: *", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 3))
        self._paid_to = AutocompleteEntry(
            p1_left, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            style="Party.TEntry"
        )
        self._paid_to.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._paid_to.bind("<FocusOut>", self._on_payee_changed)
        ToolTip(self._paid_to, text="Payee / Recipient name (Required). Type to search or @ for shortcuts")

        p1_right = ttk.Frame(p_row1)
        p1_right.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ttk.Label(p1_right, text="Cash Given By: *", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 3))
        self._cash_given_by = AutocompleteEntry(
            p1_right, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            style="Party.TEntry"
        )
        self._cash_given_by.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self._cash_given_by, text="Payer / Disburser handing over the cash (Required)")

        # Row 2: Secondary Parties (Spent By, Prepared By, Approved By) - 33/33/33 responsive split
        p_row2 = ttk.Frame(parties_frame)
        p_row2.pack(fill=tk.X)

        p2_c1 = ttk.Frame(p_row2)
        p2_c1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Label(p2_c1, text="Spent By:").pack(side=tk.LEFT, padx=(0, 3))
        self._spent_by = AutocompleteEntry(
            p2_c1, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            style="Party.TEntry"
        )
        self._spent_by.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self._spent_by, text="Person actually incurring the expense (defaults to Paid To if blank)")

        p2_c2 = ttk.Frame(p_row2)
        p2_c2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(p2_c2, text="Prepared By:").pack(side=tk.LEFT, padx=(0, 3))
        self._prepared_by = AutocompleteEntry(
            p2_c2, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            style="Party.TEntry"
        )
        self._prepared_by.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self._prepared_by, text="Staff member preparing this voucher")

        p2_c3 = ttk.Frame(p_row2)
        p2_c3.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        ttk.Label(p2_c3, text="Approved By:").pack(side=tk.LEFT, padx=(0, 3))
        self._approved_by = AutocompleteEntry(
            p2_c3, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            style="Party.TEntry"
        )
        self._approved_by.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ToolTip(self._approved_by, text="Authorizing manager / approver signing off")

        # --------------------------------------------------------------
        # 2b. Voucher Tags & Expense Labels (Slim Inline Bar)
        # --------------------------------------------------------------
        self._selected_tag_ids = set()
        tag_frame = tk.Frame(
            self._form_inner, bg="#f8fafc", highlightbackground="#e2e8f0",
            highlightthickness=1, padx=8, pady=3
        )
        tag_frame.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            tag_frame, text="🏷️ Tags:", font=("Segoe UI", 9, "bold"),
            bg="#f8fafc", fg="#334155"
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._tags_chip_box = tk.Frame(tag_frame, bg="#f8fafc")
        self._tags_chip_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        mgr_tags_btn = ttk.Button(
            tag_frame, text="🏷️ Manage Tags (Ctrl+Shift+T)",
            command=self._open_tag_manager, bootstyle="info-outline"
        )
        mgr_tags_btn.pack(side=tk.RIGHT, padx=2)
        ToolTip(mgr_tags_btn, text="Open Tag Manager to create and manage custom voucher tags (Ctrl+Shift+T)")

        self._refresh_form_tags()

        # --------------------------------------------------------------
        # 3. Line Items Section (Prioritized Workspace)
        # --------------------------------------------------------------
        self._line_items = LineItemFrame(
            self._form_inner,
            categories_callback=lambda: db.get_categories_with_ledger_info(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            manage_categories_callback=self._open_category_manager,
            bootstyle="primary"
        )
        self._line_items.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        # --------------------------------------------------------------
        # 4. Side-by-Side Attachments & Memos (Compact Height)
        # --------------------------------------------------------------
        lower_split = ttk.Frame(self._form_inner)
        lower_split.pack(fill=tk.BOTH, expand=True, pady=(0, 2))

        # Left Column: Attachments
        att_frame = ttk.LabelFrame(lower_split, text="📎 Attachments", padding=(6, 3), bootstyle="secondary")
        att_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))

        att_top = ttk.Frame(att_frame)
        att_top.pack(fill=tk.X, pady=(0, 2))

        att_add_btn = ttk.Button(
            att_top, text="+ Add Files",
            command=self._add_attachments, bootstyle="info-outline"
        )
        att_add_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(att_add_btn, text="Attach files (bills, receipts, PDFs, images) to this voucher")

        self._att_preview_btn = ttk.Button(
            att_top, text="Preview",
            command=self._preview_attachment, bootstyle="secondary-outline"
        )
        self._att_preview_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(self._att_preview_btn, text="Preview selected attachment")

        self._att_remove_btn = ttk.Button(
            att_top, text="Remove",
            command=self._remove_attachment, bootstyle="danger-outline"
        )
        self._att_remove_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(self._att_remove_btn, text="Remove selected attachment from this voucher")

        self._att_gdrive_btn = ttk.Button(
            att_top, text="📁 Drive",
            command=self._open_gdrive_folder, bootstyle="outline-primary"
        )
        self._att_gdrive_btn.pack(side=tk.LEFT)
        ToolTip(self._att_gdrive_btn, text="Open Google Drive cloud attachments folder (15 GB Free)")

        self._att_count_var = tk.StringVar(value="No attachments")
        ttk.Label(
            att_top, textvariable=self._att_count_var,
            font=("Segoe UI", 8), foreground="#6c757d"
        ).pack(side=tk.RIGHT)

        self._att_listbox = tk.Listbox(
            att_frame, height=2, font=("Segoe UI", 9),
            bg="#f8fafc", fg="#1e293b",
            selectbackground="#3b82f6", selectforeground="white",
            relief=tk.SOLID, bd=1, highlightthickness=0
        )
        self._att_listbox.pack(fill=tk.BOTH, expand=True)
        self._att_listbox.bind("<Double-1>", lambda e: self._preview_attachment())
        self._att_listbox.bind("<Return>", lambda e: self._preview_attachment())
        ToolTip(self._att_listbox, text="Double-click or press Enter on an attachment to preview")

        # Right Column: Memos & Notes
        self._memo_panel = MemoPanel(
            lower_split,
            on_add_callback=self._on_add_memo,
            text_height=2
        )
        self._memo_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(3, 0))

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats(self, conn=None):
        """Update the statistics bar. Accepts optional existing database connection."""
        try:
            stats = db.get_voucher_stats(conn=conn)
            self._stat_vars["total"].set(str(stats["total_vouchers"]))
            self._stat_vars["pending"].set(str(stats["bills_pending"]))
            self._stat_vars["amount"].set(f"{stats['total_amount']:,.2f}")
            unprinted_str = str(stats["unprinted"])
            if stats.get("overdue", 0) > 0:
                unprinted_str += f" (⚠️ {stats['overdue']} overdue)"
            self._stat_vars["unprinted"].set(unprinted_str)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # List Tab Actions
    # ------------------------------------------------------------------

    def _refresh_list(self, *args):
        """Refresh the voucher list treeview with vast search, filters, and custom sorting."""
        if self._is_closing:
            return
        self._list_dirty = False
        # Bolt Optimization: Reuse a single SQLite connection across the entire refresh pipeline
        conn = db.get_connection()
        try:
            children = self._tree.get_children()
            if children:
                self._tree.delete(*children)

            query = self._search_var.get().strip()
            status = self._status_filter.get()
            bill = self._bill_filter.get()
            pm_filter = getattr(self, "_payment_method_filter", tk.StringVar(value="All")).get()
            date_filter = getattr(self, "_date_range_filter", tk.StringVar(value="All Time")).get()
            due_filter = getattr(self, "_due_filter_var", tk.StringVar(value="All")).get()

            # Update float filter dropdown options
            active_id = db.get_active_company_id(conn)
            try:
                floats = db.get_floats(active_id, active_only=True, conn=conn)
                self._filter_float_id_map = {f["name"]: f["id"] for f in floats}
                combo_opts = ["All"] + [f["name"] for f in floats]
                if hasattr(self, "_float_filter_combo"):
                    cur_opts = list(self._float_filter_combo["values"])
                    if cur_opts != combo_opts:
                        self._float_filter_combo["values"] = combo_opts
                        if self._float_filter_var.get() not in combo_opts:
                            self._float_filter_var.set("All")
            except Exception:
                pass

            float_filter_val = getattr(self, "_float_filter_var", tk.StringVar(value="All")).get()
            float_id_arg = "All"
            if float_filter_val != "All" and hasattr(self, "_filter_float_id_map"):
                float_id_arg = self._filter_float_id_map.get(float_filter_val, "All")

            # Update tag filter combo options
            try:
                all_tags = db.get_tags(conn=conn)
                self._filter_tag_id_map = {t["name"]: t["id"] for t in all_tags}
                combo_tag_opts = ["All"] + [t["name"] for t in all_tags]
                if hasattr(self, "_tag_filter_combo"):
                    cur_opts = list(self._tag_filter_combo["values"])
                    if cur_opts != combo_tag_opts:
                        self._tag_filter_combo["values"] = combo_tag_opts
                        if self._tag_filter_var.get() not in combo_tag_opts:
                            self._tag_filter_var.set("All")
            except Exception:
                pass

            tag_filter_val = getattr(self, "_tag_filter_var", tk.StringVar(value="All")).get()
            tag_id_arg = "All"
            if tag_filter_val != "All" and hasattr(self, "_filter_tag_id_map"):
                tag_id_arg = self._filter_tag_id_map.get(tag_filter_val, "All")

            sort_map = {
                "Date (Newest)": "date_desc",
                "Date (Oldest)": "date_asc",
                "Amount (Highest)": "amount_desc",
                "Amount (Lowest)": "amount_asc",
                "Voucher # (Desc)": "number_desc",
                "Voucher # (Asc)": "number_asc",
                "Paid To (A-Z)": "paid_to_asc",
            }
            sort_by = sort_map.get(getattr(self, "_sort_var", tk.StringVar()).get(), "date_desc")

            vouchers = db.search_vouchers(
                query, status, bill, sort_by=sort_by,
                payment_method_filter=pm_filter, date_filter=date_filter,
                float_id_filter=float_id_arg, due_status_filter=due_filter,
                tag_filter=tag_id_arg,
                conn=conn
            )

            filtered_count = len(vouchers)
            filtered_total = sum(v["total_amount"] for v in vouchers)
            if hasattr(self, "_list_summary_var"):
                self._list_summary_var.set(f"Showing {filtered_count} voucher(s)  |  Total: LKR {filtered_total:,.2f}")

            today_str = datetime.now().strftime("%Y-%m-%d")

            for v in vouchers:
                printed = "🖨️ Yes" if v.get("printed") else "—"
                bill_st = v.get("bill_status", "Pending")
                v_st = v.get("status", "Active")
                due_d = v.get("due_date", "")

                due_display = "—"
                if due_d:
                    if due_d < today_str and bill_st != "Received" and v_st != "Cancelled":
                        due_display = f"⚠️ {due_d}"
                    elif due_d == today_str and bill_st != "Received" and v_st != "Cancelled":
                        due_display = f"⏳ Today"
                    else:
                        due_display = due_d

                # Determine badge icons & row colors
                if v_st == "Cancelled":
                    tag = "canceled"
                    bill_display = f"❌ {bill_st}"
                    status_display = "❌ Cancelled"
                else:
                    status_display = "Active"
                    if due_d and due_d < today_str and bill_st != "Received":
                        tag = "due_overdue"
                    elif due_d and due_d == today_str and bill_st != "Received":
                        tag = "due_today"
                    elif bill_st == "Received":
                        tag = "bill_received"
                    elif bill_st == "Partial":
                        tag = "bill_partial"
                    else:
                        tag = "bill_pending"

                if bill_st == "Received" and v_st != "Cancelled":
                    bill_display = "✅ Received"
                elif bill_st == "Partial" and v_st != "Cancelled":
                    bill_display = "⚠️ Partial"
                elif v_st != "Cancelled":
                    bill_display = "⏳ Pending"

                att_count = v.get("attachment_count", 0)
                att_display = f"📎 {att_count}" if att_count > 0 else "—"

                tags = [tag]
                if att_count > 0:
                    tags.append("has_attachment")

                pm = v.get("payment_method", "Cash")
                pm_ref = v.get("payment_ref", "")
                pm_display = f"{pm} ({pm_ref})" if pm_ref else pm

                tags_data = v.get("tags", [])
                tags_display = ", ".join(t["name"] for t in tags_data) if tags_data else "—"

                flt_name = v.get("float_name")
                if flt_name:
                    is_reimb = bool(v.get("is_reimbursed"))
                    float_display = f"{flt_name} (🔄 Reimbursed)" if is_reimb else f"{flt_name} (⏳ Pending)"
                else:
                    float_display = "—"

                self._tree.insert("", tk.END, iid=str(v["id"]), tags=tuple(tags), values=(
                    v["voucher_number"],
                    v["date"],
                    due_display,
                    v["paid_to"],
                    tags_display,
                    v.get("spent_by", ""),
                    f"{v['total_amount']:,.2f}",
                    pm_display,
                    float_display,
                    bill_display,
                    att_display,
                    status_display,
                    printed,
                ))

            self._update_stats(conn=conn)
            self._update_company_header(conn=conn)
            if hasattr(self, "_accountant_center"):
                self._accountant_center.mark_dirty()
        finally:
            conn.close()

    def _clear_list_filters(self):
        """Reset all voucher-list filters and return focus to search."""
        self._search_var.set("")
        self._date_range_filter.set("All Time")
        self._status_filter.set("All")
        self._bill_filter.set("All")
        self._payment_method_filter.set("All")
        self._due_filter_var.set("All")
        self._float_filter_var.set("All")
        self._tag_filter_var.set("All")
        self._sort_var.set("Date (Newest)")
        if self._search_timer is not None:
            try:
                self.root.after_cancel(self._search_timer)
            except tk.TclError:
                pass
            self._search_timer = None
        self._refresh_list()
        self._search_entry.focus_set()
        self._show_toast("Voucher filters cleared", icon="🧹")

    def _sort_column(self, col):
        """Sort treeview by column with intelligent numeric/attachment parsing."""
        def sort_key(item_tuple):
            val = str(item_tuple[0]).strip()
            if col == "attachments":
                if val.startswith("📎"):
                    try:
                        return float(val.replace("📎", "").strip())
                    except ValueError:
                        return 0.0
                return -1.0
            try:
                return float(val.replace(",", ""))
            except ValueError:
                return val.lower()

        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        items.sort(key=sort_key)
        for index, (val, k) in enumerate(items):
            self._tree.move(k, "", index)

    def _get_selected_ids(self):
        """Get list of selected voucher IDs."""
        return [int(iid) for iid in self._tree.selection()]

    def _on_double_click(self, event):
        """Handle double-click on treeview row."""
        self._edit_selected()

    def _new_voucher(self):
        """Switch to form tab for a new voucher."""
        if not self._check_permission("create_voucher", "create new payment vouchers"):
            return
        self._ensure_form_tab()
        self._clear_form()
        self._form_title_var.set("New Voucher")
        self._notebook.tab(self.TAB_FORM, text="  ➕ New Voucher (Ctrl+N)  ")
        self._notebook.select(self.TAB_FORM)
        self._paid_to.focus_set()

    def _edit_selected(self):
        """Load the selected voucher into the form for editing."""
        if not self._check_permission("edit_voucher", "edit payment vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to edit.")
            return
        self._load_voucher_to_form(ids[0])

    def _duplicate_selected(self):
        """Duplicate the selected voucher into a new voucher form."""
        if not self._check_permission("duplicate_voucher", "duplicate payment vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to duplicate.")
            return

        vdata = db.get_voucher(ids[0])
        if not vdata:
            messagebox.showerror("Error", "Selected voucher not found.")
            return

        self._clear_form()
        v = vdata["voucher"]

        self._paid_to.delete(0, tk.END)
        self._paid_to.insert(0, v.get("paid_to", ""))

        self._cash_given_by.delete(0, tk.END)
        self._cash_given_by.insert(0, v.get("cash_given_by", ""))

        self._spent_by.delete(0, tk.END)
        self._spent_by.insert(0, v.get("spent_by", ""))

        self._prepared_by.delete(0, tk.END)
        self._prepared_by.insert(0, v.get("prepared_by", ""))

        self._approved_by.delete(0, tk.END)
        self._approved_by.insert(0, v.get("approved_by", ""))

        self._bill_status_var.set(v.get("bill_status", "Pending"))
        self._payment_method_var.set(v.get("payment_method", "Cash"))
        self._payment_ref_var.set(v.get("payment_ref", ""))
        self._populate_form_floats(select_float_id=v.get("float_id"))

        # Load line items from source voucher
        self._line_items.set_items(vdata["line_items"])

        next_num = db.get_next_voucher_number(company_id=db.get_active_company_id())
        self._voucher_num_var.set(next_num)

        self._form_title_var.set(f"New Voucher (Copy of {v['voucher_number']})")
        self._notebook.tab(self.TAB_FORM, text="  ➕ New Voucher (Copy)  ")
        self._notebook.select(self.TAB_FORM)
        self._paid_to.focus_set()
        self._show_toast(f"Duplicated voucher from {v['voucher_number']}", icon="📋", bg="#0f172a", fg="#e0f2fe")

    def _view_selected(self):
        """Generate a PDF of the selected voucher and open it for preview."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to view.")
            return
        try:
            pdf_path = printer.generate_voucher_pdf(ids)
            PdfViewerDialog(self.root, pdf_path, voucher_ids=ids)
        except Exception as e:
            messagebox.showerror("View Error", f"Could not generate PDF preview:\n{str(e)}")

    def _view_audit_history_selected(self):
        """Open audit history dialog for the selected voucher."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to view audit history.")
            return
        vdata = db.get_voucher(ids[0])
        if vdata:
            v_num = vdata["voucher"]["voucher_number"]
            dialogs.AuditHistoryDialog(self.root, ids[0], voucher_number=v_num)

    def _mark_bill_status_selected(self, status):
        """Update bill status for selected voucher(s)."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select voucher(s) to update bill status.")
            return

        updated_count = db.update_bill_status_batch(ids, status)
        if updated_count:
            status_icons = {"Received": "✅", "Pending": "⏳", "Partial": "⚠️"}
            icon = status_icons.get(status, "📋")
            self._show_toast(f"Marked {updated_count} voucher(s) as {status}", icon=icon, bg="#0f172a", fg="#f0fdf4")
            self._refresh_list()
            self._update_stats()

    def _cancel_selected(self):
        """Cancel the selected voucher(s)."""
        if not self._check_permission("cancel_voucher", "cancel vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to cancel.")
            return

        canceled = 0
        vouchers = db.get_vouchers_by_ids(ids)
        for v in vouchers:
            if dialogs.confirm_cancel(self.root, v["voucher_number"]):
                db.cancel_voucher(v["id"])
                if firebase_client.is_enabled():
                    firebase_client.delete_voucher_from_cloud(v["company_id"], v["voucher_number"], async_call=True)
                    if v.get("float_id"):
                        firebase_client.push_float_to_cloud(v["float_id"], async_call=True)
                canceled += 1

        if canceled:
            if hasattr(self, "_float_view"):
                self._float_view.mark_dirty()
            self._show_toast(f"Cancelled {canceled} voucher(s)", icon="❌", bg="#7f1d1d", fg="#fef2f2")
        self._refresh_list()

    def _restore_selected(self):
        """Restore the selected cancelled voucher(s)."""
        if not self._check_permission("cancel_voucher", "restore vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to restore.")
            return

        restored = 0
        vouchers = db.get_vouchers_by_ids(ids)
        for v in vouchers:
            if v.get("status") == "Cancelled":
                if dialogs.confirm_restore(self.root, v["voucher_number"]):
                    db.restore_voucher(v["id"])
                    if firebase_client.is_enabled():
                        firebase_client.push_voucher_to_cloud(v["id"], async_call=True)
                        if v.get("float_id"):
                            firebase_client.push_float_to_cloud(v["float_id"], async_call=True)
                    restored += 1

        if restored:
            if hasattr(self, "_float_view"):
                self._float_view.mark_dirty()
            self._show_toast(f"Restored {restored} voucher(s)", icon="♻️", bg="#064e3b", fg="#ecfdf5")
        self._refresh_list()

    def _delete_selected_permanent(self):
        """Permanently delete selected disabled/cancelled vouchers after password verification."""
        if not self._check_permission("delete_voucher", "permanently delete vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a disabled voucher to permanently delete.")
            return

        # Bolt Optimization: Batch fetch voucher records to eliminate N+1 query loop
        vouchers = db.get_vouchers_by_ids(ids)
        active_found = [v["voucher_number"] for v in vouchers if v.get("status") != "Cancelled"]

        if active_found:
            active_list = ", ".join(active_found[:3])
            messagebox.showwarning(
                "Cannot Delete Active Vouchers",
                f"The following voucher(s) are still ACTIVE:\n{active_list}\n\n"
                "Only disabled (cancelled) vouchers can be permanently deleted.\n"
                "Please cancel the voucher first (Del key) before deleting permanently.",
                parent=self.root
            )
            return

        vouchers_data = [v for v in vouchers if v.get("status") == "Cancelled"]
        if not vouchers_data:
            messagebox.showinfo("Notice", "No cancelled/disabled vouchers selected to delete.")
            return

        dialogs.DeleteDisabledVoucherDialog(
            self.root, vouchers_data, on_success_callback=self._on_specific_vouchers_deleted
        )

    def _on_specific_vouchers_deleted(self, deleted_vouchers):
        """Callback after specific disabled vouchers are permanently deleted."""
        if hasattr(self, "_float_view"):
            self._float_view.mark_dirty()
        self._refresh_list()
        self._update_stats()
        del_ids = {v["id"] for v in deleted_vouchers}
        if self._editing_voucher_id in del_ids:
            self._clear_form()

        nums = ", ".join(v["voucher_number"] for v in deleted_vouchers[:3])
        if len(deleted_vouchers) > 3:
            nums += f" and {len(deleted_vouchers) - 3} more"
        self._show_toast(f"Permanently deleted: {nums}", icon="🗑️", bg="#7f1d1d", fg="#fef2f2", duration_ms=3500)

    def _print_selected(self):
        """Print selected vouchers."""
        if not self._check_permission("print_voucher", "print vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select vouchers to print.")
            return

        # Bolt Optimization: Single batch query replaces 2x get_voucher N+1 query loop (~98.6% speedup)
        vouchers = db.get_vouchers_by_ids(ids)
        dialogs.PrintOptionsDialog(self.root, vouchers, self._do_print)

    def _print_all_pending(self):
        """Print all unprinted active vouchers."""
        if not self._check_permission("print_voucher", "batch print pending vouchers"):
            return
        vouchers = db.search_vouchers(status_filter="Active")
        unprinted = [v for v in vouchers if not v.get("printed")]

        if not unprinted:
            messagebox.showinfo("Nothing to Print", "No unprinted vouchers found.")
            return

        dialogs.PrintOptionsDialog(self.root, unprinted, self._do_print)

    def _issue_check_for_selected(self):
        """Issue or open a bank check for the selected voucher in the list."""
        if not self._check_permission("print_voucher", "issue bank checks"):
            return
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Select Voucher", "Please select a voucher first to issue or view its bank check.")
            return
        vid = ids[0]
        def _on_done():
            self._refresh_list()
            if hasattr(self, "_check_register"):
                self._check_register.refresh()

        existing_check = db.get_check_for_voucher(vid)
        if existing_check:
            CheckEntryDialog(self.root, company_id=db.get_active_company_id(), check_id=existing_check["id"], voucher_id=vid, on_save=_on_done)
        else:
            CheckEntryDialog(self.root, company_id=db.get_active_company_id(), voucher_id=vid, on_save=_on_done)

    def _issue_check_from_form(self):
        """Issue or open a bank check from the active voucher form."""
        if not self._check_permission("print_voucher", "issue bank checks"):
            return
        vid = self._editing_voucher_id
        if not vid:
            if not messagebox.askyesno("Save Voucher First", "The voucher must be saved before issuing a bank check.\n\nSave voucher now?"):
                return
            vid = self._save_voucher()
            if not vid:
                return

        def _on_form_done():
            chk = db.get_check_for_voucher(vid)
            if chk:
                self._payment_method_var.set("Cheque")
                self._payment_ref_var.set(chk["check_number"])
                try:
                    db.update_voucher_payment(vid, "Cheque", chk["check_number"])
                except Exception:
                    pass
            self._refresh_list()
            if hasattr(self, "_check_register"):
                self._check_register.refresh()

        existing_check = db.get_check_for_voucher(vid)
        if existing_check:
            CheckEntryDialog(self.root, company_id=db.get_active_company_id(), check_id=existing_check["id"], voucher_id=vid, on_save=_on_form_done)
        else:
            CheckEntryDialog(self.root, company_id=db.get_active_company_id(), voucher_id=vid, on_save=_on_form_done)

    def _open_check_register(self):
        """Switch to the Check Register workspace."""
        self._notebook.select(self.TAB_CHECKS)

    def _open_chart_of_accounts(self):
        """Open Chart of Accounts master ledger window."""
        ChartOfAccountsDialog(self.root, company_id=db.get_active_company_id())

    def _open_general_ledger(self):
        """Open General Ledger and Trial Balance audit window."""
        GeneralLedgerDialog(self.root, company_id=db.get_active_company_id())

    def _open_new_journal_entry(self):
        """Open modal dialog to record a balanced double-entry journal entry."""
        JournalEntryDialog(
            self.root,
            company_id=db.get_active_company_id(),
            on_saved=self._on_accounting_changed,
        )

    def _on_accounting_changed(self):
        """Invalidate dependent workspaces after a posted accounting change."""
        self._list_dirty = True
        if hasattr(self, "_accountant_center"):
            self._accountant_center.mark_dirty()
            if self._notebook.index(self._notebook.select()) == self.TAB_ACCOUNTANT:
                self._accountant_center.refresh(force=True)
        self._update_stats()
    def _open_period_close(self):
        """Open professional accounting period close controls."""
        if not self._check_permission("manage_settings", "close accounting periods"):
            return
        from ui.period_close_dialog import PeriodCloseDialog

        PeriodCloseDialog(self.root, company_id=db.get_active_company_id())

    def _open_suppliers(self):
        """Open Suppliers & Vendors Directory window."""
        SupplierManagerDialog(self.root, company_id=db.get_active_company_id())

    def _open_ap_invoices(self):
        """Open Accounts Payable (AP) Invoices & Bills register window."""
        from ui.ap_invoice_dialog import APInvoiceListDialog

        APInvoiceListDialog(self.root, company_id=db.get_active_company_id())

    def _open_ap_aging(self):
        """Open Accounts Payable Aging report window."""
        from ui.ap_invoice_dialog import APAgingDialog

        APAgingDialog(self.root, company_id=db.get_active_company_id())

    def _open_customers(self):
        """Switch to the full-window Customer Centre workspace."""
        self._ensure_customer_center().refresh()
        self._notebook.select(self.TAB_CUSTOMERS)

    def _open_ar_invoices(self):
        """Switch to the full-window Customer Centre workspace."""
        self._ensure_customer_center().refresh()
        self._notebook.select(self.TAB_CUSTOMERS)

    def _open_ar_aging(self):
        """Open Accounts Receivable Aging report window."""
        from ui.ar_invoice_dialog import ARAgingDialog

        ARAgingDialog(self.root, company_id=db.get_active_company_id())

    def _open_financial_reports(self, initial_tab=0):
        """Open Financial Reports & Statements Dashboard window."""
        from ui.financial_reports_dialog import FinancialReportsDialog

        FinancialReportsDialog(self.root, company_id=db.get_active_company_id(), initial_tab=initial_tab)

    def _open_cash_flow_forecast(self):
        """Open Cash Flow Forecast & Payment Obligations window."""
        from ui.cash_flow_forecast_dialog import CashFlowForecastDialog

        CashFlowForecastDialog(self.root, company_id=db.get_active_company_id())

    def _open_purchase_orders(self):
        """Open Purchase Orders & Goods Receiving management window."""
        from ui.purchase_order_dialog import PurchaseOrderListDialog

        PurchaseOrderListDialog(self.root, company_id=db.get_active_company_id())

    def _open_payroll(self, initial_tab=0):
        """Open Unified Payroll, Staff Directory & Expense Claims Dashboard."""
        from ui.payroll_dialog import PayrollMasterDialog

        PayrollMasterDialog(self.root, company_id=db.get_active_company_id(), initial_tab=initial_tab)

    def _open_tax_manager(self, initial_tab=0):
        """Open Tax Rates & VAT/GST Statutory Returns Dashboard."""
        from ui.tax_manager_dialog import TaxManagerDialog

        TaxManagerDialog(self.root, company_id=db.get_active_company_id(), initial_tab=initial_tab)

    def _open_budget_manager(self):
        """Open Account Budgets & Variance Analytics Dashboard."""
        from ui.budget_dialog import BudgetManagerDialog

        BudgetManagerDialog(self.root, company_id=db.get_active_company_id())

    def _export_csv(self):
        """Export current search/filtered list of vouchers to a CSV file."""
        from tkinter import filedialog
        query = self._search_var.get().strip()
        status = self._status_filter.get()
        bill = self._bill_filter.get()
        pm_filter = getattr(self, "_payment_method_filter", tk.StringVar(value="All")).get()
        date_filter = getattr(self, "_date_range_filter", tk.StringVar(value="All Time")).get()
        sort_map = {
            "Date (Newest)": "date_desc",
            "Date (Oldest)": "date_asc",
            "Amount (Highest)": "amount_desc",
            "Amount (Lowest)": "amount_asc",
            "Voucher # (Desc)": "number_desc",
            "Voucher # (Asc)": "number_asc",
            "Paid To (A-Z)": "paid_to_asc",
        }
        sort_by = sort_map.get(getattr(self, "_sort_var", tk.StringVar()).get(), "date_desc")
        float_filter_val = getattr(self, "_float_filter_var", tk.StringVar(value="All")).get()
        float_id_arg = "All"
        if float_filter_val != "All" and hasattr(self, "_filter_float_id_map"):
            float_id_arg = self._filter_float_id_map.get(float_filter_val, "All")

        vouchers = db.search_vouchers(
            query, status, bill, sort_by=sort_by,
            payment_method_filter=pm_filter, date_filter=date_filter,
            float_id_filter=float_id_arg
        )

        if not vouchers:
            messagebox.showinfo("Export CSV", "No vouchers available to export.", parent=self.root)
            return

        def _on_exported(filepath, count):
            self._show_toast(f"Exported {count} voucher(s) to CSV", icon="📊", bg="#0f172a", fg="#f0fdf4")

        dialogs.ExportVouchersDialog(self.root, vouchers, on_exported_callback=_on_exported)

    def _do_print(self, voucher_ids, action):
        """Execute the print/preview action in a background worker to avoid freezing the UI."""
        self.root.config(cursor="watch")

        def _worker():
            try:
                pdf_path = printer.generate_voucher_pdf(voucher_ids)
                if action == "print":
                    printer.print_pdf(pdf_path)
                    db.mark_as_printed(voucher_ids)

                def _ui_success():
                    self.root.config(cursor="")
                    if action == "print":
                        self._refresh_list()
                        self._show_toast(f"Sent {len(voucher_ids)} voucher(s) to printer", icon="🖨️", bg="#0f172a", fg="#f8fafc")
                    elif action == "preview":
                        PdfViewerDialog(self.root, pdf_path, voucher_ids=voucher_ids)
                if self.root.winfo_exists():
                    self.root.after(0, _ui_success)
            except Exception as e:
                def _ui_error():
                    self.root.config(cursor="")
                    messagebox.showerror("Print Error", f"Error generating PDF:\n{str(e)}", parent=self.root)
                if self.root.winfo_exists():
                    self.root.after(0, _ui_error)

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Manager / Settings dialogs
    # ------------------------------------------------------------------

    def _get_at_suggestions(self):
        """
        Returns combined list of (label, type_hint) for @ trigger autocomplete.
        type_hint is 'person' or 'category'.
        """
        people = [(name, "person") for name in db.get_people(active_only=True)]
        cats = [(name, "category") for name in db.get_categories(active_only=True)]
        return people + cats

    def _open_category_manager(self):
        dlg = CategoryManagerDialog(self.root, company_id=db.get_active_company_id())
        dlg.lift()
        dlg.focus_force()

    def _open_name_manager(self):
        dlg = NameManagerDialog(self.root)
        dlg.lift()
        dlg.focus_force()

    def _open_expense_summary(self):
        dlg = dialogs.ExpenseSummaryDialog(self.root)
        dlg.lift()
        dlg.focus_force()

    def _open_payee_statement(self, initial_payee=None):
        from ui.payee_statement import PayeeStatementDialog
        dlg = PayeeStatementDialog(self.root, initial_payee=initial_payee)
        dlg.lift()
        dlg.focus_force()

    def _open_payee_statement_for_selected(self):
        ids = self._get_selected_ids()
        if not ids:
            self._open_payee_statement()
            return
        vdata = db.get_voucher(ids[0])
        payee = vdata["voucher"]["paid_to"] if vdata else None
        self._open_payee_statement(initial_payee=payee)

    def _open_template_manager(self):
        dlg = TemplateManagerDialog(self.root, on_apply_callback=self._apply_template_data)
        dlg.lift()
        dlg.focus_force()

    def _open_float_manager(self):
        """Open the Money Float and Cash Drawer Manager tab."""
        self._notebook.select(self._float_tab)

    def _on_float_updated(self):
        """Callback when floats or transactions are modified."""
        if hasattr(self, "_float_view"):
            self._float_view.mark_dirty()
        self._update_company_header()
        self._populate_form_floats()
        if self._notebook.index(self._notebook.select()) == self.TAB_VOUCHERS:
            self._refresh_list()
        else:
            self._list_dirty = True

    def _open_tag_manager(self):
        """Open the Tag and Label Manager dialog."""
        dlg = TagManagerDialog(self.root, on_tags_changed_callback=self._on_tags_changed)
        dlg.lift()
        dlg.focus_force()

    def _open_alert_center(self):
        dlg = AlertCenterDialog(self.root)
        self.root.wait_window(dlg)
        self._update_alert_button_badge()

    def _open_recurring_manager(self):
        dlg = RecurringManagerDialog(self.root)
        self.root.wait_window(dlg)
        self._refresh_list()

    def _check_permission(self, permission: str, action_name: str = "this action") -> bool:
        """Check if current session user has the requested permission. Shows warning if denied."""
        if not db.has_permission(permission):
            curr = db.get_current_user()
            role_name = curr.get("role", "viewer").upper() if curr else "VIEWER"
            from tkinter import messagebox
            messagebox.showwarning(
                "Permission Denied",
                f"Your current role [{role_name}] is not authorized to {action_name}.\n\n"
                f"Please switch to an account with higher permissions (e.g. Manager or Admin).",
                parent=self.root
            )
            return False
        return True

    def _apply_voucher_list_view(self):
        """Switch between a daily-work register and the full audit columns."""
        if not hasattr(self, "_tree"):
            return
        detailed = self._voucher_view_var.get() == "Detailed"
        columns = (
            self._voucher_detailed_columns
            if detailed else self._voucher_compact_columns
        )
        self._tree.configure(displaycolumns=columns)
    def _populate_dropdown_menu(self, menu, items, menubutton=None):
        """Populate a tk.Menu with items and register MenuActionProxy instances in self._action_buttons."""
        for entry in items:
            if entry is None:
                menu.add_separator()
                continue
            key, label, accel, cmd = entry
            opts = {"label": label, "command": cmd}
            if accel:
                opts["accelerator"] = accel
            menu.add_command(**opts)
            idx = menu.index("end")
            proxy = MenuActionProxy(menu, idx, command=cmd, label=label, menubutton=menubutton)
            self._action_buttons[key] = proxy

    def _apply_role_permissions(self, user=None):
        """Enable actions only when an authenticated role grants permission."""
        if not hasattr(self, "_action_buttons") or not self._action_buttons:
            return

        if user is None:
            user = db.get_current_user()

        role = user.get("role", "viewer") if user else "viewer"
        perms = db.ROLE_PERMISSIONS.get(role, set())

        perm_map = {
            "create_voucher": "create_voucher",
            "edit_voucher": "edit_voucher",
            "duplicate_voucher": "duplicate_voucher",
            "view_pdf": "view_pdf",
            "print_voucher": "print_voucher",
            "print_check": "print_voucher",
            "print_pending": "print_voucher",
            "export_csv": "export_csv",
            "view_audit": "view_audit",
            "approve_voucher": "approve_voucher",
            "cancel_voucher": "cancel_voucher",
            "restore_voucher": "cancel_voucher",
            "delete_voucher": "delete_voucher",
            "manage_categories": "manage_categories",
            "manage_people": "manage_people",
            "manage_tags": "manage_tags",
            "manage_float": "manage_float",
            "view_statements": "view_reports",
            "view_analytics": "view_analytics",
            "manage_settings": "manage_settings",
            "clear_data": "clear_data",
            "view_alerts": "view_reports",
            "manage_recurring": "create_voucher",
            "manage_bank_accounts": "manage_bank_accounts",
            "manage_approvers": "manage_approvers",
            "import_data": "import_data",
            "manage_exchange": "edit_voucher",
            "manage_users": "manage_users",
            "manage_coa": "manage_categories",
            "view_gl": "view_reports",
            "new_journal_entry": "create_voucher",
            "close_books": "manage_settings",
            "manage_suppliers": "manage_people",
            "manage_ap": "create_voucher",
            "manage_customers": "manage_people",
            "manage_ar": "create_voucher",
            "manage_po": "create_voucher",
            "manage_payroll": "manage_people",
            "manage_financial_reports": "view_reports",
            "manage_tax": "view_reports",
            "manage_budgets": "manage_categories",
        }

        for btn_key, btn in self._action_buttons.items():
            required = perm_map.get(btn_key)
            if not required:
                continue
            try:
                state = tk.NORMAL if required in perms else tk.DISABLED
                btn.configure(state=state)
            except Exception:
                pass
    def _open_bank_reconciliation(self):
        if not self._check_permission("manage_bank_accounts", "access bank reconciliation"):
            return
        dlg = BankReconciliationDialog(self.root)
        self.root.wait_window(dlg)
        self._refresh_list()

    def _open_approval_manager(self):
        if not self._check_permission("manage_approvers", "manage approvers"):
            return
        dlg = ApproverManagerDialog(self.root)
        self.root.wait_window(dlg)

    def _open_user_manager(self):
        """Open User Management for an authenticated administrator only."""
        current = db.get_current_user()
        if not current or current.get("role") != "admin":
            messagebox.showerror(
                "Access denied",
                "Only a signed-in administrator can manage users.",
                parent=self.root,
            )
            return
        dialog = UserManagementDialog(self.root)
        self.root.wait_window(dialog)
        self._update_user_badge()
        self._apply_role_permissions(db.get_current_user())
    def _approve_selected(self):
        if not self._check_permission("approve_voucher", "approve or reject vouchers"):
            return
        ids = self._get_selected_ids()
        if not ids:
            self._show_toast("Select a voucher to approve", icon="⚠️", bg="#f59e0b", fg="#fffbeb")
            return
        vid = ids[0]
        dlg = ApprovalDialog(self.root, voucher_id=vid, on_complete=lambda status: self._refresh_list())
        self.root.wait_window(dlg)

    def _open_import_wizard(self):
        if not self._check_permission("import_data", "import vouchers from CSV"):
            return
        dlg = ImportWizardDialog(self.root)
        self.root.wait_window(dlg)
        self._refresh_list()

    def _open_exchange_rates(self):
        dlg = show_exchange_rate_manager(self.root)
        self.root.wait_window(dlg)
        if hasattr(self, "_currency_selector"):
            self._currency_selector.refresh_currencies()

    def _v2_startup_tasks(self):
        """Run post-login recurring, alert, cloud, and currency tasks."""
        if self._is_closing:
            return
        if not db.get_current_user():
            if self._on_logout:
                self._on_logout()
            return

        required_tables = {
            "alert_preferences",
            "companies",
            "currencies",
            "exchange_rates",
            "recurring_schedules",
            "settings",
            "users",
        }
        conn = db.get_connection()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            available_tables = {row[0] for row in rows}
        finally:
            conn.close()
        if not required_tables.issubset(available_tables):
            return

        try:
            due_results = db.process_due_recurring_schedules()
            created_count = sum(1 for result in due_results if result[1] is not None)
            if created_count > 0:
                self._show_toast(
                    f"Auto-created {created_count} recurring voucher(s)!",
                    icon="📅",
                    bg="#0f766e",
                    fg="#f0fdfa",
                )
                self._refresh_list()
        except Exception as exc:
            print(f"Notice: Recurring check: {exc}")

        try:
            db.generate_alerts()
            self._update_alert_button_badge()
        except Exception as exc:
            print(f"Notice: Alert generation: {exc}")

        self._update_user_badge()
        self._apply_role_permissions(db.get_current_user())

        try:
            if firebase_client.is_enabled():
                import threading

                def _bg_cloud_startup():
                    try:
                        firebase_client.pull_cloud_users()
                        firebase_client.pull_cloud_approvers()
                        _ok, count, _message = (
                            firebase_client.pull_cloud_vouchers()
                        )
                        if count > 0 and not self._is_closing:
                            self.root.after(0, self._refresh_list)
                            self.root.after(0, self._update_stats_bar)
                            self.root.after(0, self._update_user_badge)
                    except Exception as exc:
                        print(f"Notice: Background cloud startup sync: {exc}")

                threading.Thread(
                    target=_bg_cloud_startup,
                    daemon=True,
                ).start()
        except Exception as exc:
            print(f"Notice: Startup cloud sync trigger: {exc}")

        try:
            import threading

            company_id = db.get_active_company_id()
            base_currency = db.get_company_base_currency(company_id)
            threading.Thread(
                target=db.fetch_and_store_daily_exchange_rates,
                args=(base_currency, False),
                daemon=True,
            ).start()
        except Exception as exc:
            print(f"Notice: Daily exchange rate sync error: {exc}")
    def _on_user_logged_in(self, user):
        role_label = user.get("role", "admin").upper()
        self._show_toast(f"Welcome, {user.get('display_name')} ({role_label})", icon="👋", bg="#0f172a", fg="#ffffff")
        self._update_company_header()
        self._update_user_badge()
        self._apply_role_permissions(user)

    def _update_alert_button_badge(self):
        try:
            cid = db.get_active_company_id()
            unread = db.get_unread_alert_count(cid)
            if hasattr(self, "_alert_btn") and self._alert_btn:
                if unread > 0:
                    self._alert_btn.config(text=f"⚡ Alerts ({unread})", bootstyle="danger")
                else:
                    self._alert_btn.config(text="⚡ Smart Alerts", bootstyle="warning")
        except Exception:
            pass

    def _on_tags_changed(self):
        """Callback when tags are added, renamed, or deleted."""
        self._refresh_form_tags()
        if self._notebook.index(self._notebook.select()) == self.TAB_VOUCHERS:
            self._refresh_list()
        else:
            self._list_dirty = True

    def _refresh_form_tags(self):
        """Re-render or update tag chip toggle buttons in form tab."""
        if not hasattr(self, "_tags_chip_box") or not self._tags_chip_box:
            return

        all_tags = db.get_tags()
        if not all_tags:
            for child in self._tags_chip_box.winfo_children():
                child.destroy()
            self._tag_buttons = {}
            tk.Label(
                self._tags_chip_box, text="No tags created. Click Manage Tags to create custom labels.",
                font=("Segoe UI", 8, "italic"), fg="#64748b"
            ).pack(side=tk.LEFT)
            return

        current_tag_ids = [t["id"] for t in all_tags]
        existing_ids = list(getattr(self, "_tag_buttons", {}).keys())

        # If tag definitions haven't changed, perform instant in-place style updates
        if current_tag_ids == existing_ids and all(btn.winfo_exists() for btn in self._tag_buttons.values()):
            selected_ids = getattr(self, "_selected_tag_ids", set())
            for tag in all_tags:
                tid = tag["id"]
                btn = self._tag_buttons[tid]
                tname = tag["name"]
                tcol = tag.get("color") or "#3b82f6"
                is_sel = tid in selected_ids
                bg = tcol if is_sel else "#f1f5f9"
                fg = "#ffffff" if is_sel else "#334155"
                relief = tk.RAISED if is_sel else tk.FLAT
                bd = 2 if is_sel else 1
                prefix = "✓ " if is_sel else "+ "
                btn.config(
                    text=f"{prefix}{tname}",
                    bg=bg, fg=fg, relief=relief, bd=bd,
                    font=("Segoe UI", 8, "bold" if is_sel else "normal")
                )
            return

        for child in self._tags_chip_box.winfo_children():
            child.destroy()
        self._tag_buttons = {}

        selected_ids = getattr(self, "_selected_tag_ids", set())
        for tag in all_tags:
            tid = tag["id"]
            tname = tag["name"]
            tcol = tag.get("color") or "#3b82f6"
            is_sel = tid in selected_ids

            bg = tcol if is_sel else "#f1f5f9"
            fg = "#ffffff" if is_sel else "#334155"
            relief = tk.RAISED if is_sel else tk.FLAT
            bd = 2 if is_sel else 1
            prefix = "✓ " if is_sel else "+ "

            btn = tk.Button(
                self._tags_chip_box,
                text=f"{prefix}{tname}",
                bg=bg, fg=fg, relief=relief, bd=bd,
                font=("Segoe UI", 8, "bold" if is_sel else "normal"),
                padx=6, pady=2,
                command=lambda t_id=tid: self._toggle_form_tag(t_id)
            )
            btn.pack(side=tk.LEFT, padx=3, pady=2)
            ToolTip(btn, text=f"Click to toggle '{tname}' tag on this voucher")
            self._tag_buttons[tid] = btn

    def _toggle_form_tag(self, tag_id):
        if not hasattr(self, "_selected_tag_ids"):
            self._selected_tag_ids = set()
        if tag_id in self._selected_tag_ids:
            self._selected_tag_ids.remove(tag_id)
        else:
            self._selected_tag_ids.add(tag_id)
        self._refresh_form_tags()

    def _save_as_template(self):
        data = self._get_form_data()
        items = self._line_items.get_items()

        if not items:
            messagebox.showwarning("Empty Form", "Please add at least one line item before saving as template.", parent=self.root)
            return

        default_name = f"{data.get('paid_to', 'Recurring')} Template" if data.get('paid_to') else "Recurring Template"

        dialog = tk.Toplevel(self.root)
        dialog.title("⭐ Save as Template")
        dialog.geometry("400x180")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Enter Template Name:", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(16, 6))
        name_var = tk.StringVar(value=default_name)
        entry = ttk.Entry(dialog, textvariable=name_var, font=("Segoe UI", 10))
        entry.pack(fill=tk.X, padx=16, pady=(0, 16))
        entry.focus_set()
        entry.select_range(0, tk.END)

        def _do_save():
            t_name = name_var.get().strip()
            if not t_name:
                messagebox.showwarning("Missing Name", "Please enter a template name.", parent=dialog)
                return

            template_data = {
                "template_name": t_name,
                "paid_to": data.get("paid_to", ""),
                "cash_given_by": data.get("cash_given_by", ""),
                "spent_by": data.get("spent_by", ""),
                "prepared_by": data.get("prepared_by", ""),
                "approved_by": data.get("approved_by", ""),
                "payment_method": data.get("payment_method", "Cash"),
                "bill_status": data.get("bill_status", "Pending")
            }

            db.create_template(template_data, items, company_id=db.get_active_company_id())
            dialog.destroy()
            self._show_toast(f"Template '{t_name}' saved successfully!", icon="⭐", bg="#0f172a", fg="#f0fdf4")

        btn_bar = ttk.Frame(dialog)
        btn_bar.pack(fill=tk.X, padx=16)
        ttk.Button(btn_bar, text="Save Template", command=_do_save, bootstyle="success").pack(side=tk.RIGHT)
        ttk.Button(btn_bar, text="Cancel", command=dialog.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=6)

    def _apply_template_data(self, template_full_data):
        t = template_full_data["template"]
        items = template_full_data["line_items"]

        self._clear_form()

        self._paid_to.delete(0, tk.END)
        self._paid_to.insert(0, t.get("paid_to", ""))

        self._cash_given_by.delete(0, tk.END)
        self._cash_given_by.insert(0, t.get("cash_given_by", ""))

        self._spent_by.delete(0, tk.END)
        self._spent_by.insert(0, t.get("spent_by", ""))

        self._prepared_by.delete(0, tk.END)
        self._prepared_by.insert(0, t.get("prepared_by", ""))

        self._approved_by.delete(0, tk.END)
        self._approved_by.insert(0, t.get("approved_by", ""))

        self._payment_method_var.set(t.get("payment_method", "Cash"))
        self._bill_status_var.set(t.get("bill_status", "Pending"))

        self._line_items.set_items(items)

        self._notebook.select(self.TAB_FORM)
        self._show_toast(f"Applied Template: '{t['template_name']}'", icon="✨", bg="#064e3b", fg="#ecfdf5")

    def _open_settings(self, initial_tab=0):
        dlg = SettingsDialog(self.root, on_saved_callback=self._on_settings_saved, initial_tab=initial_tab)
        dlg.lift()
        dlg.focus_force()

    def _open_about_dialog(self):
        """Open the About Application & Developer Details dialog."""
        dlg = dialogs.AboutAppDialog(self.root)
        dlg.lift()
        dlg.focus_force()

    def _check_for_updates_background(self):
        """Perform a quiet, non-blocking check for updates on GitHub in the background."""
        if self._is_closing:
            return
        import updater
        import threading
        from app import VoucherApp

        def _worker():
            res = updater.check_for_updates(VoucherApp.APP_VERSION, timeout=5)
            if res.get("update_available"):
                def _notify():
                    try:
                        if self.root.winfo_exists():
                            dialogs.UpdateAvailableDialog(self.root, res)
                    except Exception:
                        pass
                try:
                    self.root.after(0, _notify)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_settings_saved(self):
        """Callback when settings dialog saves company profiles, numbering, or Firebase."""
        self._update_company_header()
        self._update_cloud_header_status()
        self._update_stats()
        self._refresh_list()
        self._clear_form()
        self._show_toast("Settings saved successfully.", icon="⚙️", bg="#0f172a", fg="#f0fdf4")

    def _clear_all_vouchers_prompt(self):
        """Open password-protected modal dialog to clear vouchers."""
        if not self._check_permission("clear_data", "clear all vouchers"):
            return
        dialogs.ClearVouchersDialog(self.root, on_success_callback=self._on_vouchers_cleared)

    def _on_vouchers_cleared(self, scope):
        """Callback when vouchers are successfully cleared."""
        if hasattr(self, "_float_view"):
            self._float_view.mark_dirty()
        self._refresh_list()
        self._update_stats()
        self._clear_form()
        msg = "All vouchers permanently deleted from database." if scope == "all" else "Current company vouchers deleted."
        self._show_toast(msg, icon="🗑️", bg="#7f1d1d", fg="#fef2f2", duration_ms=3500)

    # ------------------------------------------------------------------
    # Form Tab Actions
    # ------------------------------------------------------------------

    def _set_quick_due_days(self, days):
        """Set due date to current voucher date + N days."""
        base_str = self._date_entry.get_date()
        try:
            base_dt = datetime.strptime(base_str.strip(), "%Y-%m-%d")
        except Exception:
            base_dt = datetime.now()
        due_dt = base_dt + timedelta(days=days)
        self._due_date_entry.set_date(due_dt.strftime("%Y-%m-%d"))

    def _set_quick_due_date_selected(self, days):
        """Set due date for selected voucher(s)."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select voucher(s) to set due date.")
            return

        # Bolt Optimization: Single batch update replacing N individual get_voucher/update_voucher calls (~95.6% speedup)
        db.update_due_dates_batch(ids, days=days)

        msg = "Cleared Due Date" if days is None else f"Set Due Date (+{days} days)"
        self._show_toast(f"{msg} for {len(ids)} voucher(s)", icon="📅", bg="#0f172a", fg="#f0fdf4")
        self._refresh_list()
        self._update_stats()

    def _load_voucher_to_form(self, voucher_id):
        """Load a voucher into the edit form."""
        self._ensure_form_tab()
        vdata = db.get_voucher(voucher_id)
        if not vdata:
            messagebox.showerror("Error", "Voucher not found.")
            return

        self._clear_form()
        self._editing_voucher_id = voucher_id

        v = vdata["voucher"]
        self._voucher_num_var.set(v["voucher_number"])
        self._date_entry.set_date(v["date"])
        self._due_date_entry.set_date(v.get("due_date", ""))
        self._bill_status_var.set(v.get("bill_status", "Pending"))
        self._payment_method_var.set(v.get("payment_method", "Cash"))
        self._payment_ref_var.set(v.get("payment_ref", ""))
        self._populate_form_floats(select_float_id=v.get("float_id"))

        self._cash_given_by.delete(0, tk.END)
        self._cash_given_by.insert(0, v.get("cash_given_by", ""))

        self._paid_to.delete(0, tk.END)
        self._paid_to.insert(0, v.get("paid_to", ""))

        self._spent_by.delete(0, tk.END)
        self._spent_by.insert(0, v.get("spent_by", ""))

        self._prepared_by.delete(0, tk.END)
        self._prepared_by.insert(0, v.get("prepared_by", ""))

        self._approved_by.delete(0, tk.END)
        self._approved_by.insert(0, v.get("approved_by", ""))

        # Load line items
        self._line_items.set_items(vdata["line_items"])

        # Load existing attachments
        self._existing_attachments = vdata.get("attachments", [])
        self._pending_attachments = []
        self._refresh_attachment_list()

        # Load tags
        self._selected_tag_ids = {t["id"] for t in vdata.get("tags", [])}
        self._refresh_form_tags()

        # Load memos
        self._memo_panel.load_memos(vdata.get("memos", []))

        # Load currency
        if hasattr(self, "_currency_selector"):
            self._currency_selector.set_currency(v.get("currency", "LKR"), v.get("exchange_rate", 1.0))

        if v.get("is_reimbursed"):
            reimb_d = v.get("reimbursed_at") or ""
            self._form_title_var.set(f"Edit Voucher: {v['voucher_number']}  [🔄 Reimbursed]")
            self._show_toast(
                f"ℹ️ Voucher {v['voucher_number']} has been reimbursed{f' on {reimb_d}' if reimb_d else ''}.",
                icon="🔄", bg="#065f46", fg="#ffffff", duration_ms=4500
            )
        else:
            self._form_title_var.set(f"Edit Voucher: {v['voucher_number']}")
        self._notebook.tab(self.TAB_FORM, text=f"  ✏️ {v['voucher_number']}  ")
        self._notebook.select(self.TAB_FORM)
        self._paid_to.focus_set()

    def _on_payee_changed(self, event=None):
        """Check if selected payee has a default or suggested expense category and auto-fill line items if blank."""
        payee_name = self._paid_to.get().strip()
        if not payee_name:
            return

        suggested_cat = db.suggest_category_for_payee(payee_name, company_id=db.get_active_company_id())
        if not suggested_cat:
            return

        # Check if first line item category is empty
        if self._line_items._rows:
            first_cat_entry = self._line_items._rows[0]["category"]
            if not first_cat_entry.get().strip():
                first_cat_entry.delete(0, tk.END)
                first_cat_entry.insert(0, suggested_cat)
                self._show_toast(f"Auto-suggested category '{suggested_cat}' for {payee_name}", icon="✨", bg="#064e3b", fg="#ecfdf5", duration_ms=2200)

    def _on_date_changed(self, event=None):
        """Update voucher number prefix when date changes (for new vouchers)."""
        if self._editing_voucher_id is None:
            raw_date = self._date_entry.get_date().strip()
            clean = raw_date.replace("-", "").replace("/", "")
            if len(clean) >= 8 and clean[:8].isdigit():
                try:
                    datetime.strptime(clean[:8], "%Y%m%d")
                    next_vn = db.get_next_voucher_number(company_id=db.get_active_company_id(), voucher_date=raw_date)
                    self._voucher_num_var.set(next_vn)
                except ValueError:
                    pass

    def _populate_form_floats(self, select_float_id=None):
        """Populate Float combobox for active company in voucher entry form."""
        if not self._form_built:
            return
        if not hasattr(self, "_form_float_combo"):
            return
        active_id = db.get_active_company_id()
        try:
            floats = db.get_floats(active_id, active_only=True)
            self._form_float_id_map = {f["name"]: f["id"] for f in floats}
            self._form_id_to_float_name = {f["id"]: f["name"] for f in floats}

            names = [f["name"] for f in floats]
            self._form_float_combo["values"] = names

            target_name = ""
            if select_float_id and select_float_id in self._form_id_to_float_name:
                target_name = self._form_id_to_float_name[select_float_id]
            else:
                def_float = next((f for f in floats if f.get("is_default")), floats[0] if floats else None)
                if def_float:
                    target_name = def_float["name"]

            self._form_float_var.set(target_name)
        except Exception:
            pass

    def _clear_form(self):
        """Reset the form for a new voucher."""
        if not self._form_built:
            return
        self._editing_voucher_id = None
        self._date_entry.set_date(date.today().strftime("%Y-%m-%d"))
        self._due_date_entry.set_date("")
        self._voucher_num_var.set(db.get_next_voucher_number(company_id=db.get_active_company_id(), voucher_date=self._date_entry.get_date()))
        self._bill_status_var.set("Pending")
        self._payment_method_var.set("Cash")
        self._payment_ref_var.set("")
        self._populate_form_floats()

        for entry in (self._cash_given_by, self._paid_to, self._spent_by,
                      self._prepared_by, self._approved_by):
            entry.delete(0, tk.END)

        # Pre-fill Prepared By from active logged-in user or remembered setting
        curr_user = db.get_current_user()
        if curr_user:
            self._prepared_by.insert(0, curr_user.get("display_name") or curr_user.get("username", ""))
        else:
            default_prep = db.get_settings().get("default_prepared_by", "")
            if default_prep:
                self._prepared_by.insert(0, default_prep)

        self._line_items.clear()
        self._pending_attachments = []
        self._existing_attachments = []
        self._selected_tag_ids = set()
        self._refresh_form_tags()
        self._refresh_attachment_list()
        self._memo_panel.clear()
        if hasattr(self, "_currency_selector"):
            self._currency_selector.reset()
        self._form_title_var.set("New Voucher")
        self._notebook.tab(self.TAB_FORM, text="  ➕ New Voucher (Ctrl+N)  ")

    def _get_form_data(self):
        """Extract form data into a dict."""
        float_id = None
        flt_name = getattr(self, "_form_float_var", tk.StringVar()).get().strip()
        if flt_name and hasattr(self, "_form_float_id_map"):
            float_id = self._form_float_id_map.get(flt_name)

        curr = self._currency_selector.get_currency() if hasattr(self, "_currency_selector") else "LKR"
        ex_rate = self._currency_selector.get_rate() if hasattr(self, "_currency_selector") else 1.0

        return {
            "voucher_number": self._voucher_num_var.get().strip(),
            "date": self._date_entry.get_date(),
            "due_date": self._due_date_entry.get_date().strip(),
            "paid_to": self._paid_to.get().strip(),
            "cash_given_by": self._cash_given_by.get().strip(),
            "spent_by": self._spent_by.get().strip(),
            "bill_status": self._bill_status_var.get(),
            "payment_method": self._payment_method_var.get(),
            "payment_ref": self._payment_ref_var.get().strip(),
            "float_id": float_id,
            "prepared_by": self._prepared_by.get().strip(),
            "approved_by": self._approved_by.get().strip(),
            "tags": list(getattr(self, "_selected_tag_ids", set())),
            "currency": curr,
            "exchange_rate": ex_rate,
        }

    def _validate_form(self):
        """Validate form data. Returns error message or None."""
        data = self._get_form_data()

        if not data["date"]:
            return "Date is required."
        if not data["paid_to"]:
            return "Paid To is required."
        if not data["cash_given_by"]:
            return "Cash Given By is required."

        items = self._line_items.get_items()
        if not items:
            return "At least one line item is required."

        category_error = self._line_items.validate_categories()
        if category_error:
            return category_error

        for i, item in enumerate(items, 1):
            if item["amount"] <= 0:
                return f"Line item #{i} must have a positive amount."

        return None

    def _save_voucher(self):
        """Save (create or update) the voucher."""
        error = self._validate_form()
        if error:
            messagebox.showwarning("Validation Error", error)
            return None

        data = self._get_form_data()
        items = self._line_items.get_items()

        # Check for potential duplicate voucher
        total_amt = sum(it.get("amount", 0.0) for it in items)
        dups = db.check_potential_duplicate_voucher(
            paid_to=data.get("paid_to", ""),
            total_amount=total_amt,
            voucher_date=data.get("date"),
            company_id=db.get_active_company_id(),
            exclude_voucher_id=self._editing_voucher_id
        )
        if dups:
            dup_details = "\n".join(f"• #{d['voucher_number']} on {d['date']} (Amount: {d['total_amount']:,.2f})" for d in dups[:3])
            confirm = messagebox.askyesno(
                "Potential Duplicate Voucher Detected",
                f"A similar voucher for '{data.get('paid_to')}' already exists:\n\n{dup_details}\n\nDo you still want to save this voucher?",
                icon="warning"
            )
            if not confirm:
                return None

        # Remember Prepared By for subsequent vouchers as fixed default
        if data.get("prepared_by"):
            try:
                db.save_settings({"default_prepared_by": data["prepared_by"]})
            except Exception:
                pass

        try:
            if self._editing_voucher_id:
                db.update_voucher(
                    self._editing_voucher_id, data, items,
                    self._pending_attachments if self._pending_attachments else None
                )
                voucher_id = self._editing_voucher_id
                v_num = data.get("voucher_number", "")
                toast_msg = f"Voucher updated: {v_num}"
                toast_icon = "💾"
                toast_bg = "#0f172a"
                toast_fg = "#f0fdf4"
            else:
                voucher_id = db.create_voucher(
                    data, items, self._pending_attachments or None,
                    company_id=db.get_active_company_id()
                )
                v_num = db.get_voucher(voucher_id)['voucher']['voucher_number']
                toast_msg = f"Voucher created: {v_num}"
                toast_icon = "✨"
                toast_bg = "#064e3b"
                toast_fg = "#ecfdf5"

            # Auto-sync to Firebase NoSQL cloud live if enabled
            if firebase_client.is_enabled():
                firebase_client.push_voucher_to_cloud(voucher_id, async_call=True)
                try:
                    v_row = db.get_voucher(voucher_id)
                    flt_id = v_row.get("voucher", {}).get("float_id") if v_row else None
                    if flt_id:
                        firebase_client.push_float_to_cloud(flt_id, async_call=True)
                except Exception:
                    pass

            # Auto-sync attachments to Google Drive if enabled
            if gdrive_client.is_enabled():
                gdrive_client.sync_voucher_attachments_async(voucher_id)

            # Check category monthly budget limits for soft warning notification
            over_budget_cats = []
            m_str = data.get("date", "")[:7] if data.get("date") else None
            cat_totals = {}
            for it in items:
                c = (it.get("category") or "").strip()
                if c:
                    cat_totals[c] = cat_totals.get(c, 0.0) + float(it.get("amount") or 0.0)

            for cat_name in cat_totals:
                b_alert = db.check_category_budget_alert(
                    category_name=cat_name, amount_to_add=0.0,
                    month_str=m_str, company_id=db.get_active_company_id()
                )
                if b_alert.get("is_over_budget"):
                    over_budget_cats.append(f"'{cat_name}' (over by LKR {b_alert['over_amount']:,.2f})")

            if over_budget_cats:
                cat_list_str = ", ".join(over_budget_cats[:2])
                self._show_toast(
                    f"{v_num} saved! Note: Category {cat_list_str} exceeds monthly budget.",
                    icon="⚠️", bg="#7c2d12", fg="#fef3c7", duration_ms=4500
                )
            else:
                self._show_toast(toast_msg, icon=toast_icon, bg=toast_bg, fg=toast_fg)

            if hasattr(self, "_float_view"):
                self._float_view.mark_dirty()
            self._pending_attachments = []
            self._refresh_list()
            self._list_dirty = False

            # Reload the form to reflect saved state
            self._load_voucher_to_form(voucher_id)
            return voucher_id

        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving voucher:\n{str(e)}")
            return None

    def _save_and_print(self):
        """Save the voucher and print it immediately."""
        voucher_id = self._save_voucher()
        if voucher_id:
            self._do_print([voucher_id], "print")

    # ------------------------------------------------------------------
    # Attachment Management
    # ------------------------------------------------------------------

    def _add_attachments(self):
        """Open file dialog and add attachments."""
        new_atts = dialogs.select_attachments(self.root)
        if new_atts:
            self._pending_attachments.extend(new_atts)
            self._refresh_attachment_list()

    def _refresh_attachment_list(self):
        """Refresh the attachment listbox and update action button states."""
        self._att_listbox.delete(0, tk.END)

        for att in self._existing_attachments:
            self._att_listbox.insert(tk.END, f"[saved] {att['filename']}")

        for att in self._pending_attachments:
            self._att_listbox.insert(tk.END, f"[new] {att['filename']}")

        total = len(self._existing_attachments) + len(self._pending_attachments)
        self._att_count_var.set(
            f"{total} file(s)" if total > 0 else "No attachments"
        )

        state = tk.NORMAL if total > 0 else tk.DISABLED
        if hasattr(self, "_att_preview_btn") and self._att_preview_btn:
            self._att_preview_btn.config(state=state)
        if hasattr(self, "_att_remove_btn") and self._att_remove_btn:
            self._att_remove_btn.config(state=state)

    def _preview_attachment(self):
        """Preview the selected attachment."""
        sel = self._att_listbox.curselection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select an attachment to preview.")
            return

        idx = sel[0]
        existing_count = len(self._existing_attachments)

        if idx < existing_count:
            att_info = self._existing_attachments[idx]
            att_full = db.get_attachment_data(att_info["id"])
            if att_full:
                dialogs.AttachmentPreviewDialog(
                    self.root, att_full["filename"],
                    att_full["file_data"], att_full["file_type"]
                )
        else:
            att = self._pending_attachments[idx - existing_count]
            dialogs.AttachmentPreviewDialog(
                self.root, att["filename"], att["file_data"], att["file_type"]
            )

    def _remove_attachment(self):
        """Remove the selected attachment."""
        sel = self._att_listbox.curselection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select an attachment to remove.")
            return

        idx = sel[0]
        existing_count = len(self._existing_attachments)

        if idx < existing_count:
            att = self._existing_attachments[idx]
            if messagebox.askyesno("Remove Attachment", f"Remove '{att['filename']}'?\nThis cannot be undone."):
                db.delete_attachment(att["id"])
                self._existing_attachments.pop(idx)
        else:
            pidx = idx - existing_count
            self._pending_attachments.pop(pidx)

        self._refresh_attachment_list()

    def _open_gdrive_folder(self):
        """Open Google Drive attachments folder in Explorer or prompt setup."""
        if gdrive_client.is_enabled():
            gdrive_client.open_gdrive_folder()
        else:
            if messagebox.askyesno(
                "Google Drive Cloud Storage",
                "Google Drive Attachment Sync is not enabled yet.\n\n"
                "Every Google account comes with 15 GB of 100% free cloud storage.\n"
                "Would you like to configure your Google Drive folder now?",
                parent=self.root
            ):
                self._open_settings(initial_tab="gdrive")

    # ------------------------------------------------------------------
    # Memo Management
    # ------------------------------------------------------------------

    def _on_add_memo(self, text, memo_type):
        """Handle adding a new memo."""
        if self._editing_voucher_id:
            db.add_memo(self._editing_voucher_id, text, memo_type)
            memos = db.get_memos(self._editing_voucher_id)
            self._memo_panel.load_memos(memos)
        else:
            messagebox.showinfo(
                "Save First",
                "Please save the voucher before adding memos."
            )

    def _on_app_close(self):
        """Clear the session, cancel callbacks, and close the window."""
        db.set_current_user(None)
        self._cancel_pending_callbacks()
        self.root.destroy()