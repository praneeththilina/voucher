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
from tkinter import messagebox
from datetime import datetime, date
import os
import io
import subprocess
import sys

import database as db
import printer
from ui.widgets import AutocompleteEntry, LineItemFrame, MemoPanel, SmartDateEntry
from ui import dialogs
from ui.category_manager import CategoryManagerDialog
from ui.name_manager import NameManagerDialog
from ui.settings_dialog import SettingsDialog
from ui.pdf_viewer import PdfViewerDialog
from ui.template_manager import TemplateManagerDialog


class MainWindow:
    """Main application window with tabbed interface and keyboard shortcut support."""

    def __init__(self, root):
        self.root = root
        self._editing_voucher_id = None
        self._pending_attachments = []  # new attachments not yet saved
        self._existing_attachments = []  # already-saved attachments
        self._comp_logo_photo = None
        self._toast_frame = None
        self._search_timer = None

        self._setup_custom_styles()
        self._build_ui()
        self._update_company_header()
        self._clear_form()
        self._setup_shortcuts()
        self._refresh_list()

        # Non-blocking background check for updates after UI settles
        self.root.after(2500, self._check_for_updates_background)

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
        self.root.bind_all("<F5>", lambda e: self._refresh_list())

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
        self.root.bind_all("<Control-k>", lambda e: self._toggle_active_company())
        self.root.bind_all("<Control-K>", lambda e: self._toggle_active_company())

        # Settings: Ctrl+comma
        self.root.bind_all("<Control-comma>", lambda e: self._open_settings())

        # Expense Analytics: Ctrl+I
        self.root.bind_all("<Control-i>", lambda e: self._open_expense_summary())
        self.root.bind_all("<Control-I>", lambda e: self._open_expense_summary())

        # Template Manager: Ctrl+T
        self.root.bind_all("<Control-t>", lambda e: self._open_template_manager())
        self.root.bind_all("<Control-T>", lambda e: self._open_template_manager())

        # About App: F1
        self.root.bind_all("<F1>", lambda e: self._open_about_dialog())

    def _on_tab_changed(self, event=None):
        """Handle notebook tab change events."""
        curr = self._notebook.index(self._notebook.select())
        if curr != 1:
            try:
                self.root.unbind_all("<MouseWheel>")
            except Exception:
                pass

    def _shortcut_save(self):
        if self._notebook.index(self._notebook.select()) == 1:
            self._save_voucher()
        return "break"

    def _shortcut_save_and_print(self):
        if self._notebook.index(self._notebook.select()) == 1:
            self._save_and_print()
        return "break"

    def _shortcut_print(self):
        curr = self._notebook.index(self._notebook.select())
        if curr == 1:
            self._save_and_print()
        else:
            self._print_selected()
        return "break"

    def _shortcut_focus_search(self):
        self._notebook.select(0)
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        return "break"

    def _shortcut_clear_form(self):
        if self._notebook.index(self._notebook.select()) == 1:
            self._clear_form()
        return "break"

    def _shortcut_add_line(self):
        if self._notebook.index(self._notebook.select()) == 1:
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
        if self._notebook.index(self._notebook.select()) == 1:
            self._notebook.select(0)
        return "break"

    def _shortcut_delete(self, event):
        widget = self.root.focus_get()
        # If user is in an entry or text widget, let normal deletion happen
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text)):
            return
        if self._notebook.index(self._notebook.select()) == 0:
            self._cancel_selected()
            return "break"

    def _shortcut_delete_permanent(self, event=None):
        widget = self.root.focus_get()
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text)):
            return
        if self._notebook.index(self._notebook.select()) == 0:
            self._delete_selected_permanent()
            return "break"

    def _on_search_change(self):
        """Debounce search queries to ensure silky-smooth, lag-free 60fps typing."""
        if self._search_timer is not None:
            try:
                self.root.after_cancel(self._search_timer)
            except Exception:
                pass
        self._search_timer = self.root.after(140, self._refresh_list)

    def _show_toast(self, message, icon="✓", bg="#0f172a", fg="#f8fafc", duration_ms=2800):
        """
        Display a modern Windows 11 sliding toast notification banner with smooth animation.
        """
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
                self.root.after(16, lambda: slide_in(new_y))
            else:
                self.root.after(duration_ms, slide_out)

        def slide_out():
            def step_out(curr_y):
                if not self._toast_frame or not self._toast_frame.winfo_exists():
                    return
                if curr_y > start_y:
                    new_y = curr_y - 6
                    self._toast_frame.place_configure(y=new_y)
                    self.root.after(16, lambda: step_out(new_y))
                else:
                    if self._toast_frame and self._toast_frame.winfo_exists():
                        self._toast_frame.destroy()
                    self._toast_frame = None
            step_out(target_y)

        slide_in(start_y)

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Build the entire UI layout."""
        # Top Company Switcher Header Bar
        self._build_company_header_bar()

        # Compact Stats bar at top
        self._build_stats_bar()

        # Global Shortcut Helper Footer Bar (docked at bottom first)
        self._build_shortcut_bar()

        # Notebook (tabs)
        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 2))
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Tab 1: Voucher List
        self._list_tab = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(self._list_tab, text="  📋 Voucher List (Ctrl+1)  ")
        self._build_list_tab()

        # Tab 2: Voucher Form
        self._form_tab = ttk.Frame(self._notebook, padding=6)
        self._notebook.add(self._form_tab, text="  ➕ New Voucher (Ctrl+N)  ")
        self._build_form_tab()

    def _build_stats_bar(self):
        """Build the statistics bar at the top with distinct pastel card colors."""
        stats_frame = ttk.Frame(self.root, padding=(8, 4))
        stats_frame.pack(fill=tk.X)

        self._stat_vars = {
            "total": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "amount": tk.StringVar(value="0.00"),
            "unprinted": tk.StringVar(value="0"),
        }

        stat_configs = [
            ("Total Vouchers", "total", "#eff6ff", "#bfdbfe", "#1d4ed8"),
            ("Bills Pending", "pending", "#fffbeb", "#fde68a", "#b45309"),
            ("Total Amount (LKR)", "amount", "#f0fdf4", "#bbf7d0", "#15803d"),
            ("Unprinted", "unprinted", "#f5f3ff", "#ddd6fe", "#6d28d9"),
        ]

        for label, key, bg_color, border_color, val_color in stat_configs:
            card = tk.Frame(
                stats_frame, bg=bg_color,
                highlightbackground=border_color, highlightthickness=1,
                padx=10, pady=5
            )
            card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

            tk.Label(
                card, text=label,
                font=("Segoe UI", 8), bg=bg_color, fg="#64748b"
            ).pack(anchor="w")

            tk.Label(
                card, textvariable=self._stat_vars[key],
                font=("Segoe UI", 13, "bold"),
                bg=bg_color, fg=val_color
            ).pack(anchor="w")

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

        # Right side: Switch Company Button + Header Settings Button
        right_box = tk.Frame(self._comp_bar, bg="#ffffff")
        right_box.pack(side=tk.RIGHT)

        self._switch_comp_btn = ttk.Button(
            right_box, text="🔄 Switch Company (Ctrl+K)",
            command=self._toggle_active_company, bootstyle="primary"
        )
        self._switch_comp_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(self._switch_comp_btn, text="Switch active company profile (Ctrl+K)")

        ttk.Button(
            right_box, text="⚙️ Header Settings (Ctrl+,)",
            command=self._open_settings, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            right_box, text="ℹ️ About (F1)",
            command=self._open_about_dialog, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=3)

    def _update_company_header(self):
        """Refresh top company bar with active company details and logo."""
        active_id = db.get_active_company_id()
        comp = db.get_company(active_id) or {}
        other_id = 2 if active_id == 1 else 1
        other_comp = db.get_company(other_id) or {}

        c_name = comp.get("name", f"Company {active_id}")
        other_name = other_comp.get("name", f"Company {other_id}")

        self._comp_name_var.set(c_name)
        self._comp_tagline_var.set(comp.get("tagline", ""))

        # Badge styling
        if active_id == 1:
            self._comp_badge_lbl.config(text="Company 1 Profile", bg="#dbeafe", fg="#1e40af")
        else:
            self._comp_badge_lbl.config(text="Company 2 Profile", bg="#d1fae5", fg="#065f46")

        # Switch button text
        self._switch_comp_btn.config(text=f"🔄 Switch to {other_name} (Ctrl+K)")

        # Render mini logo thumbnail if present
        logo_data = comp.get("logo")
        if logo_data:
            try:
                from PIL import Image as PILImage, ImageTk
                l_img = PILImage.open(io.BytesIO(logo_data))
                l_img.thumbnail((36, 30), PILImage.Resampling.LANCZOS)
                self._comp_logo_photo = ImageTk.PhotoImage(l_img)
                self._comp_logo_lbl.config(image=self._comp_logo_photo, text="")
            except Exception:
                self._comp_logo_lbl.config(image="", text="🏢")
        else:
            self._comp_logo_lbl.config(image="", text="🏢")

    def _toggle_active_company(self):
        """Switch active company between 1 and 2."""
        curr = db.get_active_company_id()
        next_id = 2 if curr == 1 else 1
        db.set_active_company_id(next_id)
        self._update_company_header()
        comp = db.get_company(next_id) or {}
        c_name = comp.get("name", f"Company {next_id}")
        self._show_toast(f"Active Company: {c_name}", icon="🏢", bg="#1e3a8a", fg="#eff6ff")
        self._update_stats()
        self._refresh_list()
        self._clear_form()

    def _build_shortcut_bar(self):
        """Build the persistent shortcut guide bar at the bottom."""
        bar = tk.Frame(
            self.root, bg="#0f172a", highlightbackground="#1e293b",
            highlightthickness=1, padx=12, pady=5
        )
        bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Primary Actions (Left)
        left_text = (
            "⌨️  [Ctrl+N] New   [Ctrl+E] Edit   [Ctrl+S] Save   [Ctrl+Enter] Save & Print   "
            "[Ctrl+T] Templates   [Ctrl+P] Print   [Del] Cancel   [Shift+Del] Purge Disabled"
        )
        tk.Label(
            bar, text=left_text,
            font=("Segoe UI", 8, "bold"), bg="#0f172a", fg="#f1f5f9"
        ).pack(side=tk.LEFT)

        # Navigation & Tools (Right)
        right_text = (
            "[Ctrl+K] Switch Co.   [Ctrl+G] Categories   [Ctrl+M] Names   "
            "[Ctrl+,] Settings   [F1] About   [@] Auto-suggest   [F5] Refresh   [Esc] Back"
        )
        tk.Label(
            bar, text=right_text,
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(side=tk.RIGHT)

    def _build_list_tab(self):
        """Build the voucher list tab with light styled search and filter bar."""
        # Search & Filter bar with soft light slate card
        filter_frame = tk.Frame(self._list_tab, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=6)
        filter_frame.pack(fill=tk.X, pady=(0, 6))

        tk.Label(filter_frame, text="🔍 Vast Search (Ctrl+F):", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._on_search_change())
        self._search_entry = ttk.Entry(filter_frame, textvariable=self._search_var, width=20, style="Search.TEntry")
        self._search_entry.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(self._search_entry, text="Search by voucher number, payee, or description (Ctrl+F)")

        tk.Label(filter_frame, text="Status:", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._status_filter = tk.StringVar(value="All")
        status_combo = ttk.Combobox(
            filter_frame, textvariable=self._status_filter,
            values=["All", "Active", "Cancelled"], width=8, state="readonly"
        )
        status_combo.pack(side=tk.LEFT, padx=(0, 10))
        status_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_frame, text="Bills:", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._bill_filter = tk.StringVar(value="All")
        bill_combo = ttk.Combobox(
            filter_frame, textvariable=self._bill_filter,
            values=["All", "Pending", "Received", "Partial"], width=8, state="readonly"
        )
        bill_combo.pack(side=tk.LEFT, padx=(0, 10))
        bill_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_frame, text="Payment:", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._payment_method_filter = tk.StringVar(value="All")
        payment_combo = ttk.Combobox(
            filter_frame, textvariable=self._payment_method_filter,
            values=["All", "Cash", "Bank Transfer", "Cheque", "Credit Card", "Online/Other"], width=11, state="readonly"
        )
        payment_combo.pack(side=tk.LEFT, padx=(0, 10))
        payment_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_frame, text="Date Range:", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._date_range_filter = tk.StringVar(value="All Time")
        date_range_combo = ttk.Combobox(
            filter_frame, textvariable=self._date_range_filter,
            values=["All Time", "Today", "Yesterday", "This Week", "This Month", "Last Month", "This Year"], width=10, state="readonly"
        )
        date_range_combo.pack(side=tk.LEFT, padx=(0, 10))
        date_range_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        tk.Label(filter_frame, text="Sort:", font=("Segoe UI", 9), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(0, 4))
        self._sort_var = tk.StringVar(value="Date (Newest)")
        sort_combo = ttk.Combobox(
            filter_frame, textvariable=self._sort_var,
            values=[
                "Date (Newest)", "Date (Oldest)",
                "Amount (Highest)", "Amount (Lowest)",
                "Voucher # (Desc)", "Voucher # (Asc)",
                "Paid To (A-Z)"
            ],
            width=14, state="readonly"
        )
        sort_combo.pack(side=tk.LEFT, padx=(0, 10))
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_list())

        ttk.Button(
            filter_frame, text="⟳ Refresh (F5)", command=self._refresh_list,
            bootstyle="secondary-outline"
        ).pack(side=tk.RIGHT)

        # Summary Badge for current search/filter results
        self._list_summary_var = tk.StringVar(value="Showing 0 vouchers | Total: LKR 0.00")
        summary_lbl = tk.Label(
            filter_frame, textvariable=self._list_summary_var,
            font=("Segoe UI", 9, "bold"), bg="#e0f2fe", fg="#0369a1",
            padx=8, pady=3, highlightbackground="#7dd3fc", highlightthickness=1
        )
        summary_lbl.pack(side=tk.RIGHT, padx=(0, 10))

        # Treeview (Voucher list table)
        columns = ("number", "date", "paid_to", "spent_by", "amount", "payment_method", "bill_status", "attachments", "status", "printed")
        self._tree = ttk.Treeview(
            self._list_tab, columns=columns, show="headings",
            height=16, selectmode="extended"
        )

        col_configs = [
            ("number", "Voucher #", 90, "center"),
            ("date", "Date", 80, "center"),
            ("paid_to", "Paid To", 120, "w"),
            ("spent_by", "Spent By", 110, "w"),
            ("amount", "Amount", 90, "e"),
            ("payment_method", "Payment", 95, "center"),
            ("bill_status", "Bills", 80, "center"),
            ("attachments", "📎 Files", 60, "center"),
            ("status", "Status", 70, "center"),
            ("printed", "Printed", 60, "center"),
        ]

        for col, heading, width, anchor in col_configs:
            self._tree.heading(col, text=heading, command=lambda c=col: self._sort_column(c))
            self._tree.column(col, width=width, anchor=anchor)

        # Colorful tags for visual clarity
        self._tree.tag_configure("bill_pending", background="#fffdf5", foreground="#92400e")
        self._tree.tag_configure("bill_received", background="#f0fdf4", foreground="#166534")
        self._tree.tag_configure("bill_partial", background="#f0f9ff", foreground="#0369a1")
        self._tree.tag_configure("canceled", foreground="#94a3b8", background="#f8fafc")
        self._tree.tag_configure("has_attachment", font=("Segoe UI", 9, "bold"))

        scrollbar = ttk.Scrollbar(self._list_tab, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Return>", lambda e: self._edit_selected())

        # Right-click context menu
        self._tree_menu = tk.Menu(self.root, tearoff=0)
        self._tree_menu.add_command(label="✏️ Edit Voucher (Ctrl+E)", command=self._edit_selected)
        self._tree_menu.add_command(label="📋 Duplicate Voucher (Ctrl+D)", command=self._duplicate_selected)
        self._tree_menu.add_command(label="👁️ View PDF", command=self._view_selected)
        self._tree_menu.add_separator()

        # Cascading Bill Status sub-menu
        bill_menu = tk.Menu(self._tree_menu, tearoff=0)
        bill_menu.add_command(label="✅ Received", command=lambda: self._mark_bill_status_selected("Received"))
        bill_menu.add_command(label="⏳ Pending", command=lambda: self._mark_bill_status_selected("Pending"))
        bill_menu.add_command(label="⚠️ Partial", command=lambda: self._mark_bill_status_selected("Partial"))
        self._tree_menu.add_cascade(label="📋 Mark Bill Status", menu=bill_menu)

        self._tree_menu.add_separator()
        self._tree_menu.add_command(label="🖨️ Print (Ctrl+P)", command=self._print_selected)
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

        # Action buttons below treeview
        action_frame = ttk.Frame(self._list_tab)
        action_frame.pack(fill=tk.X, pady=(6, 0), side=tk.BOTTOM)

        buttons = [
            ("➕ New (Ctrl+N)", self._new_voucher, "success"),
            ("✏️ Edit (Ctrl+E)", self._edit_selected, "primary"),
            ("📋 Duplicate (Ctrl+D)", self._duplicate_selected, "secondary-outline"),
            ("👁️ View PDF", self._view_selected, "info"),
            ("❌ Cancel (Del)", self._cancel_selected, "danger-outline"),
            ("♻️ Restore (Ctrl+R)", self._restore_selected, "warning-outline"),
            ("🗑️ Delete (Shift+Del)", self._delete_selected_permanent, "danger-outline"),
            ("📊 Export CSV", self._export_csv, "info-outline"),
            ("🖨️ Print (Ctrl+P)", self._print_selected, "primary-outline"),
            ("📄 Print All Pending (Ctrl+Shift+P)", self._print_all_pending, "success-outline"),
        ]

        for text, cmd, style in buttons:
            ttk.Button(action_frame, text=text, command=cmd, bootstyle=style).pack(
                side=tk.LEFT, padx=3
            )

        # Manager shortcut buttons (right-aligned)
        right_mgr = ttk.Frame(action_frame)
        right_mgr.pack(side=tk.RIGHT)
        ttk.Button(
            right_mgr, text="🗑️ Clear All Vouchers",
            command=self._clear_all_vouchers_prompt, bootstyle="danger-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            right_mgr, text="📁 Categories (Ctrl+G)",
            command=self._open_category_manager, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            right_mgr, text="👤 Names (Ctrl+M)",
            command=self._open_name_manager, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            right_mgr, text="📈 Analytics (Ctrl+I)",
            command=self._open_expense_summary, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            right_mgr, text="⚙️ Settings (Ctrl+,)",
            command=self._open_settings, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=2)

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
        # Canvas wrapper with auto-width adjustment
        form_canvas = tk.Canvas(self._form_tab, highlightthickness=0)
        form_scrollbar = ttk.Scrollbar(self._form_tab, orient=tk.VERTICAL, command=form_canvas.yview)
        self._form_inner = ttk.Frame(form_canvas, padding=4)

        self._form_inner.bind(
            "<Configure>",
            lambda e: form_canvas.configure(scrollregion=form_canvas.bbox("all"))
        )
        self._form_window = form_canvas.create_window((0, 0), window=self._form_inner, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scrollbar.set)

        def _on_canvas_configure(e):
            form_canvas.itemconfig(self._form_window, width=e.width)
        form_canvas.bind("<Configure>", _on_canvas_configure)

        form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        form_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            if self._notebook.index(self._notebook.select()) == 1:
                form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        form_canvas.bind("<Enter>", lambda e: form_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        form_canvas.bind("<Leave>", lambda e: form_canvas.unbind_all("<MouseWheel>"))

        # --------------------------------------------------------------
        # 1. Header & Quick Action Row (Compact Light Card)
        # --------------------------------------------------------------
        header_card = tk.Frame(self._form_inner, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1, padx=8, pady=6)
        header_card.pack(fill=tk.X, pady=(0, 6))

        left_hdr = tk.Frame(header_card, bg="#f1f5f9")
        left_hdr.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._form_title_var = tk.StringVar(value="New Voucher")
        tk.Label(
            left_hdr, textvariable=self._form_title_var,
            font=("Segoe UI", 12, "bold"), bg="#f1f5f9", fg="#1d4ed8"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(left_hdr, text="Voucher #:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(4, 2))
        self._voucher_num_var = tk.StringVar()
        self._voucher_num_entry = ttk.Entry(
            left_hdr, textvariable=self._voucher_num_var, width=14,
            state="readonly", font=("Segoe UI", 10, "bold"), style="VoucherBadge.TEntry"
        )
        self._voucher_num_entry.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(left_hdr, text="Date:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(4, 2))
        self._date_entry = SmartDateEntry(left_hdr)
        self._date_entry.pack(side=tk.LEFT, padx=(0, 3))
        self._date_entry.bind("<<DateModified>>", self._on_date_changed)

        tk.Label(
            left_hdr, text="(↑/↓: Day | Shift+↑/↓: Month | T: Today)",
            font=("Segoe UI", 8), bg="#f1f5f9", fg="#64748b"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(left_hdr, text="Bills:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(4, 2))
        self._bill_status_var = tk.StringVar(value="Pending")
        ttk.Combobox(
            left_hdr, textvariable=self._bill_status_var,
            values=["Pending", "Received", "Partial"], width=9, state="readonly"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(left_hdr, text="Payment Method:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(4, 2))
        self._payment_method_var = tk.StringVar(value="Cash")
        ttk.Combobox(
            left_hdr, textvariable=self._payment_method_var,
            values=["Cash", "Bank Transfer", "Cheque", "Credit Card", "Online/Other"], width=12, state="readonly"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(left_hdr, text="Payment Ref:", font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#334155").pack(side=tk.LEFT, padx=(4, 2))
        self._payment_ref_var = tk.StringVar()
        ttk.Entry(
            left_hdr, textvariable=self._payment_ref_var, width=12, style="TEntry"
        ).pack(side=tk.LEFT)

        # Quick Top Action Buttons
        right_hdr = tk.Frame(header_card, bg="#f1f5f9")
        right_hdr.pack(side=tk.RIGHT)

        ttk.Button(
            right_hdr, text="📝 Templates (Ctrl+T)",
            command=self._open_template_manager, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            right_hdr, text="💾 Save (Ctrl+S)",
            command=self._save_voucher, bootstyle="success"
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            right_hdr, text="🖨️ Save & Print (Ctrl+Enter)",
            command=self._save_and_print, bootstyle="primary"
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            right_hdr, text="← Back (Esc)",
            command=lambda: self._notebook.select(0), bootstyle="secondary-outline"
        ).pack(side=tk.LEFT, padx=2)

        # --------------------------------------------------------------
        # 2. Parties & Signatures (Compact 2-Row Horizontal Layout)
        # --------------------------------------------------------------
        parties_frame = ttk.LabelFrame(
            self._form_inner,
            text="👤 Parties & Signatures (Autocomplete Memory)",
            padding=(6, 4),
            bootstyle="info"
        )
        parties_frame.pack(fill=tk.X, pady=(0, 5))

        # Row 0: Paid To, Cash Given By, Spent By
        r0 = ttk.Frame(parties_frame)
        r0.pack(fill=tk.X, pady=1)

        ttk.Label(r0, text="Paid To: *", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self._paid_to = AutocompleteEntry(
            r0, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions, width=22,
            style="Party.TEntry"
        )
        self._paid_to.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(r0, text="Cash Given By: *", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self._cash_given_by = AutocompleteEntry(
            r0, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions, width=22,
            style="Party.TEntry"
        )
        self._cash_given_by.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(r0, text="Spent By:").pack(side=tk.LEFT, padx=(0, 2))
        self._spent_by = AutocompleteEntry(
            r0, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions, width=20,
            style="Party.TEntry"
        )
        self._spent_by.pack(side=tk.LEFT, padx=(0, 3))
        ttk.Label(r0, text="(delegated to X)", font=("Segoe UI", 8), foreground="#6c757d").pack(side=tk.LEFT)

        # Row 1: Prepared By, Approved By, Note
        r1 = ttk.Frame(parties_frame)
        r1.pack(fill=tk.X, pady=1)

        ttk.Label(r1, text="Prepared By:").pack(side=tk.LEFT, padx=(0, 2))
        self._prepared_by = AutocompleteEntry(
            r1, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions, width=20,
            style="Party.TEntry"
        )
        self._prepared_by.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(r1, text="Approved By:").pack(side=tk.LEFT, padx=(0, 2))
        self._approved_by = AutocompleteEntry(
            r1, suggestions_callback=lambda: db.get_people(active_only=True),
            at_trigger_callback=self._get_at_suggestions, width=20,
            style="Party.TEntry"
        )
        self._approved_by.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(
            r1, text="* Paid To & Cash Given By required. Leave Spent By blank if same as Paid To.",
            font=("Segoe UI", 8), foreground="#6c757d"
        ).pack(side=tk.LEFT, padx=10)

        # --------------------------------------------------------------
        # 3. Line Items Section (Prioritized Workspace)
        # --------------------------------------------------------------
        self._line_items = LineItemFrame(
            self._form_inner,
            categories_callback=lambda: db.get_categories(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
            bootstyle="primary"
        )
        self._line_items.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # --------------------------------------------------------------
        # 4. Side-by-Side Attachments & Memos (Cuts vertical space by 50%)
        # --------------------------------------------------------------
        lower_split = ttk.Frame(self._form_inner)
        lower_split.pack(fill=tk.BOTH, expand=True, pady=(0, 4))

        # Left Column: Attachments
        att_frame = ttk.LabelFrame(lower_split, text="📎 Attachments", padding=4, bootstyle="secondary")
        att_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))

        att_top = ttk.Frame(att_frame)
        att_top.pack(fill=tk.X, pady=(0, 2))

        att_add_btn = ttk.Button(
            att_top, text="+ Add Files",
            command=self._add_attachments, bootstyle="info-outline"
        )
        att_add_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(att_add_btn, text="Attach files to this voucher")

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
        self._att_remove_btn.pack(side=tk.LEFT)
        ToolTip(self._att_remove_btn, text="Remove selected attachment")

        self._att_count_var = tk.StringVar(value="No attachments")
        ttk.Label(
            att_top, textvariable=self._att_count_var,
            font=("Segoe UI", 8), foreground="#6c757d"
        ).pack(side=tk.RIGHT)

        self._att_listbox = tk.Listbox(
            att_frame, height=3, font=("Segoe UI", 9),
            bg="#f8fafc", fg="#1e293b",
            selectbackground="#3b82f6", selectforeground="white",
            relief=tk.SOLID, bd=1, highlightthickness=0
        )
        self._att_listbox.pack(fill=tk.BOTH, expand=True)


        # Right Column: Memos & Notes
        self._memo_panel = MemoPanel(
            lower_split,
            on_add_callback=self._on_add_memo,
            text_height=3
        )
        self._memo_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(3, 0))

        # --------------------------------------------------------------
        # 5. Bottom Action Buttons Bar
        # --------------------------------------------------------------
        btn_frame = ttk.Frame(self._form_inner)
        btn_frame.pack(fill=tk.X, pady=(2, 0))

        ttk.Button(
            btn_frame, text="💾 Save Voucher (Ctrl+S)",
            command=self._save_voucher, bootstyle="success"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            btn_frame, text="🖨️ Save & Print (Ctrl+Enter)",
            command=self._save_and_print, bootstyle="primary"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            btn_frame, text="⭐ Save as Template",
            command=self._save_as_template, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            btn_frame, text="🔄 Clear Form (Ctrl+W)",
            command=self._clear_form, bootstyle="warning-outline"
        ).pack(side=tk.LEFT, padx=3)

        ttk.Button(
            btn_frame, text="← Back to List (Esc)",
            command=lambda: self._notebook.select(0), bootstyle="secondary-outline"
        ).pack(side=tk.RIGHT, padx=3)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def _update_stats(self):
        """Update the statistics bar."""
        try:
            stats = db.get_voucher_stats()
            self._stat_vars["total"].set(str(stats["total_vouchers"]))
            self._stat_vars["pending"].set(str(stats["bills_pending"]))
            self._stat_vars["amount"].set(f"{stats['total_amount']:,.2f}")
            self._stat_vars["unprinted"].set(str(stats["unprinted"]))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # List Tab Actions
    # ------------------------------------------------------------------

    def _refresh_list(self, *args):
        """Refresh the voucher list treeview with vast search, filters, and custom sorting."""
        for item in self._tree.get_children():
            self._tree.delete(item)

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

        vouchers = db.search_vouchers(query, status, bill, sort_by=sort_by, payment_method_filter=pm_filter, date_filter=date_filter)

        filtered_count = len(vouchers)
        filtered_total = sum(v["total_amount"] for v in vouchers)
        if hasattr(self, "_list_summary_var"):
            self._list_summary_var.set(f"Showing {filtered_count} voucher(s)  |  Total: LKR {filtered_total:,.2f}")

        for v in vouchers:
            printed = "🖨️ Yes" if v.get("printed") else "—"
            bill_st = v.get("bill_status", "Pending")
            v_st = v.get("status", "Active")

            # Determine badge icons & row colors
            if v_st == "Cancelled":
                tag = "canceled"
                bill_display = f"❌ {bill_st}"
                status_display = "❌ Cancelled"
            else:
                status_display = "Active"
                if bill_st == "Received":
                    tag = "bill_received"
                    bill_display = "✅ Received"
                elif bill_st == "Partial":
                    tag = "bill_partial"
                    bill_display = "⚠️ Partial"
                else:
                    tag = "bill_pending"
                    bill_display = "⏳ Pending"

            att_count = v.get("attachment_count", 0)
            att_display = f"📎 {att_count}" if att_count > 0 else "—"

            tags = [tag]
            if att_count > 0:
                tags.append("has_attachment")

            pm = v.get("payment_method", "Cash")
            pm_ref = v.get("payment_ref", "")
            pm_display = f"{pm} ({pm_ref})" if pm_ref else pm

            self._tree.insert("", tk.END, iid=str(v["id"]), tags=tuple(tags), values=(
                v["voucher_number"],
                v["date"],
                v["paid_to"],
                v.get("spent_by", ""),
                f"{v['total_amount']:,.2f}",
                pm_display,
                bill_display,
                att_display,
                status_display,
                printed,
            ))

        self._update_stats()

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
        self._clear_form()
        self._voucher_num_var.set(db.get_next_voucher_number(company_id=db.get_active_company_id()))
        self._form_title_var.set("New Voucher")
        self._notebook.tab(1, text="  ➕ New Voucher (Ctrl+N)  ")
        self._notebook.select(1)
        self._paid_to.focus_set()

    def _edit_selected(self):
        """Load the selected voucher into the form for editing."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to edit.")
            return
        self._load_voucher_to_form(ids[0])

    def _duplicate_selected(self):
        """Duplicate the selected voucher into a new voucher form."""
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

        # Load line items from source voucher
        self._line_items.set_items(vdata["line_items"])

        next_num = db.get_next_voucher_number(company_id=db.get_active_company_id())
        self._voucher_num_var.set(next_num)

        self._form_title_var.set(f"New Voucher (Copy of {v['voucher_number']})")
        self._notebook.tab(1, text="  ➕ New Voucher (Copy)  ")
        self._notebook.select(1)
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
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to cancel.")
            return

        canceled = 0
        for vid in ids:
            vdata = db.get_voucher(vid)
            if vdata and dialogs.confirm_cancel(self.root, vdata["voucher"]["voucher_number"]):
                db.cancel_voucher(vid)
                canceled += 1

        if canceled:
            self._show_toast(f"Cancelled {canceled} voucher(s)", icon="❌", bg="#7f1d1d", fg="#fef2f2")
        self._refresh_list()

    def _restore_selected(self):
        """Restore the selected cancelled voucher(s)."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a voucher to restore.")
            return

        restored = 0
        for vid in ids:
            vdata = db.get_voucher(vid)
            if vdata and vdata["voucher"]["status"] == "Cancelled":
                if dialogs.confirm_restore(self.root, vdata["voucher"]["voucher_number"]):
                    db.restore_voucher(vid)
                    restored += 1

        if restored:
            self._show_toast(f"Restored {restored} voucher(s)", icon="♻️", bg="#064e3b", fg="#ecfdf5")
        self._refresh_list()

    def _delete_selected_permanent(self):
        """Permanently delete selected disabled/cancelled vouchers after password verification."""
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select a disabled voucher to permanently delete.")
            return

        vouchers_data = []
        active_found = []
        for vid in ids:
            vinfo = db.get_voucher(vid)
            if vinfo:
                v = vinfo["voucher"]
                if v["status"] != "Cancelled":
                    active_found.append(v["voucher_number"])
                else:
                    vouchers_data.append(v)

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

        if not vouchers_data:
            messagebox.showinfo("Notice", "No cancelled/disabled vouchers selected to delete.")
            return

        dialogs.DeleteDisabledVoucherDialog(
            self.root, vouchers_data, on_success_callback=self._on_specific_vouchers_deleted
        )

    def _on_specific_vouchers_deleted(self, deleted_vouchers):
        """Callback after specific disabled vouchers are permanently deleted."""
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
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select vouchers to print.")
            return

        vouchers = [db.get_voucher(vid)["voucher"] for vid in ids if db.get_voucher(vid)]
        dialogs.PrintOptionsDialog(self.root, vouchers, self._do_print)

    def _print_all_pending(self):
        """Print all unprinted active vouchers."""
        vouchers = db.search_vouchers(status_filter="Active")
        unprinted = [v for v in vouchers if not v.get("printed")]

        if not unprinted:
            messagebox.showinfo("Nothing to Print", "No unprinted vouchers found.")
            return

        dialogs.PrintOptionsDialog(self.root, unprinted, self._do_print)

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
        vouchers = db.search_vouchers(query, status, bill, sort_by=sort_by, payment_method_filter=pm_filter, date_filter=date_filter)

        if not vouchers:
            messagebox.showinfo("Export CSV", "No vouchers available to export.", parent=self.root)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Vouchers to CSV",
            initialfile=f"vouchers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")]
        )

        if filepath:
            try:
                db.export_vouchers_to_csv(vouchers, filepath)
                self._show_toast(f"Exported {len(vouchers)} voucher(s) to CSV", icon="📊", bg="#0f172a", fg="#f0fdf4")
            except Exception as e:
                messagebox.showerror("Export Error", f"Could not export CSV file:\n{e}", parent=self.root)

    def _do_print(self, voucher_ids, action):
        """Execute the print/preview action."""
        try:
            pdf_path = printer.generate_voucher_pdf(voucher_ids)

            if action == "print":
                printer.print_pdf(pdf_path)
                db.mark_as_printed(voucher_ids)
                self._refresh_list()
                self._show_toast(f"Sent {len(voucher_ids)} voucher(s) to printer", icon="🖨️", bg="#0f172a", fg="#f8fafc")
            elif action == "preview":
                PdfViewerDialog(self.root, pdf_path, voucher_ids=voucher_ids)

        except Exception as e:
            messagebox.showerror("Print Error", f"Error generating PDF:\n{str(e)}")

    # ------------------------------------------------------------------
    # Manager / Settings dialogs
    # ------------------------------------------------------------------

    def _get_at_suggestions(self):
        """
        Returns combined list of (label, type_hint) for @ trigger autocomplete.
        type_hint is 'person' or 'category'.
        """
        # Bolt Optimization: Reuse single DB connection across people and category lookups
        conn = db.get_connection()
        try:
            people = [(name, "person") for name in db.get_people(active_only=True, conn=conn)]
            cats = [(name, "category") for name in db.get_categories(active_only=True, conn=conn)]
            return people + cats
        finally:
            conn.close()

    def _open_category_manager(self):
        dlg = CategoryManagerDialog(self.root)
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

    def _open_template_manager(self):
        dlg = TemplateManagerDialog(self.root, on_apply_callback=self._apply_template_data)
        dlg.lift()
        dlg.focus_force()

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

        self._notebook.select(1)
        self._show_toast(f"Applied Template: '{t['template_name']}'", icon="✨", bg="#064e3b", fg="#ecfdf5")

    def _open_settings(self):
        dlg = SettingsDialog(self.root, on_saved_callback=self._on_settings_saved)
        dlg.lift()
        dlg.focus_force()

    def _open_about_dialog(self):
        """Open the About Application & Developer Details dialog."""
        dlg = dialogs.AboutAppDialog(self.root)
        dlg.lift()
        dlg.focus_force()

    def _check_for_updates_background(self):
        """Perform a quiet, non-blocking check for updates on GitHub in the background."""
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
        """Callback when settings dialog saves company profiles and numbering."""
        self._update_company_header()
        self._update_stats()
        self._refresh_list()
        self._clear_form()
        self._show_toast("Settings saved successfully.", icon="⚙️", bg="#0f172a", fg="#f0fdf4")

    def _clear_all_vouchers_prompt(self):
        """Open password-protected modal dialog to clear vouchers."""
        dialogs.ClearVouchersDialog(self.root, on_success_callback=self._on_vouchers_cleared)

    def _on_vouchers_cleared(self, scope):
        """Callback when vouchers are successfully cleared."""
        self._refresh_list()
        self._update_stats()
        self._clear_form()
        msg = "All vouchers permanently deleted from database." if scope == "all" else "Current company vouchers deleted."
        self._show_toast(msg, icon="🗑️", bg="#7f1d1d", fg="#fef2f2", duration_ms=3500)

    # ------------------------------------------------------------------
    # Form Tab Actions
    # ------------------------------------------------------------------

    def _load_voucher_to_form(self, voucher_id):
        """Load a voucher into the edit form."""
        vdata = db.get_voucher(voucher_id)
        if not vdata:
            messagebox.showerror("Error", "Voucher not found.")
            return

        self._clear_form()
        self._editing_voucher_id = voucher_id

        v = vdata["voucher"]
        self._voucher_num_var.set(v["voucher_number"])
        self._date_entry.set_date(v["date"])
        self._bill_status_var.set(v.get("bill_status", "Pending"))
        self._payment_method_var.set(v.get("payment_method", "Cash"))
        self._payment_ref_var.set(v.get("payment_ref", ""))

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

        # Load memos
        self._memo_panel.load_memos(vdata.get("memos", []))

        self._form_title_var.set(f"Edit Voucher: {v['voucher_number']}")
        self._notebook.tab(1, text=f"  ✏️ {v['voucher_number']}  ")
        self._notebook.select(1)
        self._paid_to.focus_set()

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

    def _clear_form(self):
        """Reset the form for a new voucher."""
        self._editing_voucher_id = None
        self._date_entry.set_date(date.today().strftime("%Y-%m-%d"))
        self._voucher_num_var.set(db.get_next_voucher_number(company_id=db.get_active_company_id(), voucher_date=self._date_entry.get_date()))
        self._bill_status_var.set("Pending")
        self._payment_method_var.set("Cash")
        self._payment_ref_var.set("")

        for entry in (self._cash_given_by, self._paid_to, self._spent_by,
                      self._prepared_by, self._approved_by):
            entry.delete(0, tk.END)

        # Pre-fill Prepared By from sticky remembered setting until changed
        default_prep = db.get_settings().get("default_prepared_by", "")
        if default_prep:
            self._prepared_by.insert(0, default_prep)

        self._line_items.clear()
        self._pending_attachments = []
        self._existing_attachments = []
        self._att_listbox.delete(0, tk.END)
        self._att_count_var.set("No attachments")
        self._memo_panel.clear()
        self._form_title_var.set("New Voucher")
        self._notebook.tab(1, text="  ➕ New Voucher (Ctrl+N)  ")

    def _get_form_data(self):
        """Extract form data into a dict."""
        return {
            "voucher_number": self._voucher_num_var.get().strip(),
            "date": self._date_entry.get_date(),
            "paid_to": self._paid_to.get().strip(),
            "cash_given_by": self._cash_given_by.get().strip(),
            "spent_by": self._spent_by.get().strip(),
            "bill_status": self._bill_status_var.get(),
            "payment_method": self._payment_method_var.get(),
            "payment_ref": self._payment_ref_var.get().strip(),
            "prepared_by": self._prepared_by.get().strip(),
            "approved_by": self._approved_by.get().strip(),
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
                self._show_toast(f"Voucher updated: {v_num}", icon="💾", bg="#0f172a", fg="#f0fdf4")
            else:
                voucher_id = db.create_voucher(
                    data, items, self._pending_attachments or None,
                    company_id=db.get_active_company_id()
                )
                v_num = db.get_voucher(voucher_id)['voucher']['voucher_number']
                self._show_toast(f"Voucher created: {v_num}", icon="✨", bg="#064e3b", fg="#ecfdf5")

            self._pending_attachments = []
            self._refresh_list()

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
