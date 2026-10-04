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
from ui.float_manager import MoneyFloatDialog, MoneyFloatView
from ui.tag_manager import TagManagerDialog


class MainWindow:
    """Main application window with tabbed interface and keyboard shortcut support."""

    def __init__(self, root):
        self.root = root
        self._editing_voucher_id = None
        self._pending_attachments = []  # new attachments not yet saved
        self._existing_attachments = []  # already-saved attachments
        self._comp_logo_photo = None
        self._cached_logo_key = None
        self._form_scroll_timer = None
        self._toast_frame = None
        self._search_timer = None
        self._list_dirty = False
        self._tag_buttons = {}
        self._ribbon_mode = db.get_app_setting("dashboard_ribbon_mode", "always_show")
        self._is_temporarily_revealed = False
        self._auto_hide_timer = None

        self._setup_custom_styles()
        self._build_ui()
        self._toast_timer_id = None
        self._update_company_header()
        self._clear_form()
        self._setup_shortcuts()
        self._refresh_list()

        # Clean window close handler to cancel pending after loops
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)

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

        # Toggle Dashboard Ribbon Display: Ctrl+F1
        self.root.bind_all("<Control-F1>", lambda e: self._shortcut_toggle_ribbon())

        # Tab Switching: Ctrl+1 (Voucher List), Ctrl+2 (New Voucher), Ctrl+3 (Cash Float)
        self.root.bind_all("<Control-1>", lambda e: self._notebook.select(0))
        self.root.bind_all("<Control-Key-1>", lambda e: self._notebook.select(0))
        self.root.bind_all("<Control-2>", lambda e: self._new_voucher())
        self.root.bind_all("<Control-Key-2>", lambda e: self._new_voucher())

    def _on_tab_changed(self, event=None):
        """Handle notebook tab change events with zero-lag cached rendering."""
        if getattr(self, "_ribbon_mode", "always_show") == "auto_hide" and getattr(self, "_is_temporarily_revealed", False):
            self._collapse_ribbon()
        curr = self._notebook.index(self._notebook.select())
        if curr != 1:
            try:
                self.root.unbind_all("<MouseWheel>")
            except Exception:
                pass
        if curr == 0:
            if getattr(self, "_list_dirty", False):
                self._refresh_list()
                self._list_dirty = False
        elif curr == 2:
            if hasattr(self, "_float_view"):
                self._float_view.refresh()

    def _on_notebook_click(self, event=None):
        """Auto-hide dashboard cards when user interacts with notebook content."""
        if getattr(self, "_ribbon_mode", "always_show") == "auto_hide" and getattr(self, "_is_temporarily_revealed", False):
            self._collapse_ribbon()

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
        if self._notebook.index(self._notebook.select()) in (1, 2):
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
        self._notebook.bind("<Button-1>", self._on_notebook_click, add="+")

        # Tab 1: Voucher List
        self._list_tab = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(self._list_tab, text="  📋 Voucher List (Ctrl+1)  ")
        self._build_list_tab()

        # Tab 2: Voucher Form
        self._form_tab = ttk.Frame(self._notebook, padding=6)
        self._notebook.add(self._form_tab, text="  ➕ New Voucher (Ctrl+2)  ")
        self._build_form_tab()

        # Tab 3: Cash Float & Drawers
        self._float_tab = ttk.Frame(self._notebook, padding=2)
        self._notebook.add(self._float_tab, text="  💰 Cash Float & Drawers (Ctrl+3)  ")
        self._float_view = MoneyFloatView(
            self._float_tab,
            company_id=db.get_active_company_id(),
            on_update_callback=self._on_float_updated,
            on_close_callback=lambda: self._notebook.select(0)
        )
        self._float_view.pack(fill=tk.BOTH, expand=True)

        # Apply user preferred ribbon display mode (Always Show, Auto-Hide, Hide)
        self._apply_ribbon_mode()

        # Pre-warm widget geometries once to eliminate initial tab switch stutter
        self.root.update_idletasks()

    def _build_stats_bar(self):
        """Build the statistics bar at the top with distinct pastel card colors and MS Office ribbon controls."""
        self._stats_frame = ttk.Frame(self.root, padding=(8, 4))
        self._stats_frame.pack(fill=tk.X)

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
                self._stats_frame, bg=bg_color,
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

        # Right-side Action controls inside stats frame (Pin / Collapse / Menu)
        card_ctrl_frame = tk.Frame(self._stats_frame)
        card_ctrl_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(2, 4))

        self._card_pin_btn = ttk.Button(
            card_ctrl_frame, text="📌 Pin",
            command=lambda: self._set_ribbon_mode("always_show"),
            bootstyle="primary-link", width=6
        )
        ToolTip(self._card_pin_btn, text="Pin Dashboard Cards (Always Show)")

        self._card_collapse_btn = ttk.Button(
            card_ctrl_frame, text="▲",
            command=self._on_card_collapse_click,
            bootstyle="secondary-link", width=3
        )
        self._card_collapse_btn.pack(side=tk.TOP, pady=1)
        ToolTip(self._card_collapse_btn, text="Collapse Dashboard Cards (Ctrl+F1)")

        self._card_menu_btn = ttk.Button(
            card_ctrl_frame, text="▾",
            command=self._show_ribbon_menu,
            bootstyle="secondary-link", width=3
        )
        self._card_menu_btn.pack(side=tk.TOP, pady=1)
        ToolTip(self._card_menu_btn, text="Dashboard Display Options")

        # Track mouse leaving cards for Auto-Hide
        self._stats_frame.bind("<Leave>", self._on_stats_frame_leave)
        self._stats_frame.bind("<Enter>", self._on_stats_frame_enter)

        # Build Slim Collapsed / Auto-Hide Ribbon Strip
        self._stats_collapsed_strip = tk.Frame(
            self.root, bg="#f8fafc", cursor="hand2",
            highlightbackground="#cbd5e1", highlightthickness=1,
            padx=12, pady=3
        )

        self._collapsed_stat_lbl = tk.Label(
            self._stats_collapsed_strip,
            text="📊 Total Vouchers: 0   •   Bills Pending: 0   •   Total: LKR 0.00   •   Unprinted: 0",
            font=("Segoe UI", 8), bg="#f8fafc", fg="#475569"
        )
        self._collapsed_stat_lbl.pack(side=tk.LEFT)

        expand_lbl = tk.Label(
            self._stats_collapsed_strip,
            text="▾ Expand Dashboard (Ctrl+F1)",
            font=("Segoe UI", 8, "bold"), bg="#f8fafc", fg="#2563eb"
        )
        expand_lbl.pack(side=tk.RIGHT)

        for w in (self._stats_collapsed_strip, self._collapsed_stat_lbl, expand_lbl):
            w.bind("<Button-1>", lambda e: self._reveal_ribbon())
            w.bind("<Enter>", lambda e: self._on_collapsed_strip_enter())

        ToolTip(self._stats_collapsed_strip, text="Click or hover to reveal full Dashboard Cards (Ctrl+F1)")

    def _on_card_collapse_click(self):
        """Handle clicking the collapse chevron inside the cards bar."""
        if self._ribbon_mode == "always_show":
            self._set_ribbon_mode("auto_hide")
        else:
            self._collapse_ribbon()

    def _show_ribbon_menu(self):
        """Display the MS Office Ribbon Display Options dropdown menu."""
        menu = tk.Menu(self.root, tearoff=0)
        curr = getattr(self, "_ribbon_mode", "always_show")

        def _mark(mode):
            return "● " if curr == mode else "   "

        menu.add_command(
            label=f"{_mark('always_show')}📌 Always Show Dashboard Cards",
            command=lambda: self._set_ribbon_mode("always_show")
        )
        menu.add_command(
            label=f"{_mark('auto_hide')}⚡ Auto-Hide Dashboard Cards",
            command=lambda: self._set_ribbon_mode("auto_hide")
        )
        menu.add_command(
            label=f"{_mark('hide')}▲ Hide Dashboard Cards",
            command=lambda: self._set_ribbon_mode("hide")
        )
        menu.add_separator()
        menu.add_command(
            label="   Toggle Ribbon Display (Ctrl+F1)",
            command=self._shortcut_toggle_ribbon
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

    def _set_ribbon_mode(self, mode, notify=True):
        """Set and persist the dashboard ribbon display mode."""
        if mode not in ("always_show", "auto_hide", "hide"):
            mode = "always_show"
        self._ribbon_mode = mode
        db.set_app_setting("dashboard_ribbon_mode", mode)
        self._apply_ribbon_mode()

        if notify:
            if mode == "always_show":
                self._show_toast("Dashboard cards pinned (Always Show)", icon="📌", bg="#0f172a", fg="#f0fdf4")
            elif mode == "auto_hide":
                self._show_toast("Auto-Hide enabled: Hover or click top strip to reveal", icon="⚡", bg="#0f172a", fg="#f0fdf4")
            elif mode == "hide":
                self._show_toast("Dashboard cards hidden (Press Ctrl+F1 to toggle)", icon="▲", bg="#0f172a", fg="#f0fdf4")

    def _apply_ribbon_mode(self):
        """Apply current ribbon mode to widget visibility."""
        if getattr(self, "_auto_hide_timer", None):
            try:
                self.root.after_cancel(self._auto_hide_timer)
            except Exception:
                pass
            self._auto_hide_timer = None

        if self._ribbon_mode == "always_show":
            self._is_temporarily_revealed = False
            self._stats_collapsed_strip.pack_forget()
            self._stats_frame.pack(fill=tk.X, before=self._notebook)
            self._card_pin_btn.pack_forget()
            self._card_collapse_btn.pack(side=tk.TOP, pady=1)
            if hasattr(self, "_ribbon_opt_btn"):
                self._ribbon_opt_btn.config(text="📊 Dashboard: Show ▾")

        elif self._ribbon_mode == "auto_hide":
            self._is_temporarily_revealed = False
            self._stats_frame.pack_forget()
            self._stats_collapsed_strip.pack(fill=tk.X, before=self._notebook, padx=8, pady=(0, 2))
            self._card_pin_btn.pack(side=tk.TOP, pady=1)
            self._card_collapse_btn.pack(side=tk.TOP, pady=1)
            if hasattr(self, "_ribbon_opt_btn"):
                self._ribbon_opt_btn.config(text="📊 Dashboard: Auto ▾")

        elif self._ribbon_mode == "hide":
            self._is_temporarily_revealed = False
            self._stats_frame.pack_forget()
            self._stats_collapsed_strip.pack_forget()
            if hasattr(self, "_ribbon_opt_btn"):
                self._ribbon_opt_btn.config(text="📊 Dashboard: Hidden ▾")

    def _reveal_ribbon(self):
        """Temporarily expand dashboard cards in Auto-Hide mode."""
        if getattr(self, "_auto_hide_timer", None):
            try:
                self.root.after_cancel(self._auto_hide_timer)
            except Exception:
                pass
            self._auto_hide_timer = None

        self._is_temporarily_revealed = True
        self._stats_collapsed_strip.pack_forget()
        self._stats_frame.pack(fill=tk.X, before=self._notebook)
        if self._ribbon_mode == "auto_hide":
            self._card_pin_btn.pack(side=tk.TOP, pady=1)

    def _collapse_ribbon(self):
        """Collapse dashboard cards back to auto-hide strip or hidden state."""
        if getattr(self, "_auto_hide_timer", None):
            try:
                self.root.after_cancel(self._auto_hide_timer)
            except Exception:
                pass
            self._auto_hide_timer = None

        self._is_temporarily_revealed = False
        if self._ribbon_mode == "auto_hide":
            self._stats_frame.pack_forget()
            self._stats_collapsed_strip.pack(fill=tk.X, before=self._notebook, padx=8, pady=(0, 2))
        elif self._ribbon_mode == "hide":
            self._stats_frame.pack_forget()
            self._stats_collapsed_strip.pack_forget()

    def _on_collapsed_strip_enter(self):
        """Auto-reveal when hovering over the collapsed strip."""
        if self._ribbon_mode == "auto_hide":
            self._reveal_ribbon()

    def _on_stats_frame_enter(self, event=None):
        """Cancel auto-hide collapse while mouse is inside stats cards."""
        if getattr(self, "_auto_hide_timer", None):
            try:
                self.root.after_cancel(self._auto_hide_timer)
            except Exception:
                pass
            self._auto_hide_timer = None

    def _on_stats_frame_leave(self, event=None):
        """Schedule collapse when mouse leaves stats cards in auto-hide mode."""
        if self._ribbon_mode == "auto_hide" and self._is_temporarily_revealed:
            if getattr(self, "_auto_hide_timer", None):
                try:
                    self.root.after_cancel(self._auto_hide_timer)
                except Exception:
                    pass
            self._auto_hide_timer = self.root.after(700, self._check_and_auto_hide)

    def _check_and_auto_hide(self):
        """Verify pointer position before collapsing in auto-hide mode."""
        self._auto_hide_timer = None
        if not self._is_temporarily_revealed or self._ribbon_mode != "auto_hide":
            return

        try:
            px = self.root.winfo_pointerx()
            py = self.root.winfo_pointery()
            fx = self._stats_frame.winfo_rootx()
            fy = self._stats_frame.winfo_rooty()
            fw = self._stats_frame.winfo_width()
            fh = self._stats_frame.winfo_height()

            if fx <= px <= (fx + fw) and fy <= py <= (fy + fh):
                return
        except Exception:
            pass

        self._collapse_ribbon()

    def _shortcut_toggle_ribbon(self, event=None):
        """Toggle dashboard ribbon display between expanded and collapsed (Ctrl+F1)."""
        curr = getattr(self, "_ribbon_mode", "always_show")
        if curr == "always_show":
            self._set_ribbon_mode("auto_hide")
        elif curr == "auto_hide":
            if self._is_temporarily_revealed:
                self._collapse_ribbon()
            else:
                self._reveal_ribbon()
        else: # hide
            self._set_ribbon_mode("always_show")
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
            right_box, text="🔄 Switch Company (Ctrl+K)",
            command=self._toggle_active_company, bootstyle="primary"
        )
        self._switch_comp_btn.pack(side=tk.LEFT, padx=4)
        ToolTip(self._switch_comp_btn, text="Switch active company profile (Ctrl+K)")

        self._cloud_bar_btn = ttk.Button(
            right_box, text="☁️ Cloud",
            command=self._open_settings_cloud, bootstyle="secondary-outline"
        )
        self._cloud_bar_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._cloud_bar_btn, text="Firebase Cloud NoSQL Database Sync & Settings")

        self._ribbon_opt_btn = ttk.Button(
            right_box, text="📊 Dashboard ▾",
            command=self._show_ribbon_menu, bootstyle="secondary-outline"
        )
        self._ribbon_opt_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._ribbon_opt_btn, text="Dashboard Cards Display Options (Always Show, Auto-Hide, Hide) [Ctrl+F1]")

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
        other_id = 2 if active_id == 1 else 1
        other_comp = db.get_company(other_id, conn=conn) or {}

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
            self._cloud_bar_tooltip.text = f"Firebase Cloud Firestore Live ({pid})\nClick to open Cloud Settings."
        elif firebase_client.is_configured():
            self._cloud_bar_btn.config(text="☁️ Cloud: Paused", bootstyle="warning-outline")
            self._cloud_bar_tooltip.text = "Firebase Configured but Sync is Disabled. Click to configure."
        else:
            self._cloud_bar_btn.config(text="☁️ Cloud: Offline", bootstyle="secondary-outline")
            self._cloud_bar_tooltip.text = "Connect Free Firebase NoSQL Database (Click to Setup)"

    def _open_settings_cloud(self):
        """Open settings dialog directly focused on the Firebase Cloud tab."""
        self._open_settings(initial_tab=2)

    def _toggle_active_company(self):
        """Switch active company between 1 and 2."""
        curr = db.get_active_company_id()
        next_id = 2 if curr == 1 else 1
        db.set_active_company_id(next_id)
        self._cached_logo_key = None
        self._update_company_header()
        comp = db.get_company(next_id) or {}
        c_name = comp.get("name", f"Company {next_id}")
        self._show_toast(f"Active Company: {c_name}", icon="🏢", bg="#1e3a8a", fg="#eff6ff")
        self._update_stats()
        self._refresh_list()
        self._clear_form()
        if hasattr(self, "_float_view"):
            self._float_view.mark_dirty()

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
            "[Ctrl+P] Print   [Del] Cancel"
        )
        tk.Label(
            bar, text=left_text,
            font=("Segoe UI", 8, "bold"), bg="#0f172a", fg="#f1f5f9"
        ).pack(side=tk.LEFT)

        # Navigation & Tools (Right)
        right_text = (
            "[Ctrl+F1] Ribbon   [Ctrl+3 / Ctrl+Shift+F] Floats   [Ctrl+K] Switch   [Ctrl+G] Categories   "
            "[Ctrl+M] Names   [Ctrl+,] Settings   [F5] Refresh   [Esc] Back"
        )
        tk.Label(
            bar, text=right_text,
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(side=tk.RIGHT)

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

        # Action buttons container below treeview (docked at the bottom of the list tab first so it spans the full window width)
        action_container = ttk.Frame(self._list_tab)
        action_container.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        # Row 1: All Primary & Operational Voucher Actions (Left-aligned across full bar, zero collision)
        row1_actions = ttk.Frame(action_container)
        row1_actions.pack(fill=tk.X, pady=(0, 3))

        primary_buttons = [
            ("➕ New (Ctrl+N)", self._new_voucher, "success", "Create a new payment voucher (Ctrl+N)"),
            ("✏️ Edit (Ctrl+E)", self._edit_selected, "primary", "Edit the selected voucher (Ctrl+E)"),
            ("📋 Duplicate (Ctrl+D)", self._duplicate_selected, "secondary-outline", "Duplicate selected voucher into a new entry (Ctrl+D)"),
            ("👁️ View PDF", self._view_selected, "info", "Preview generated PDF for selected voucher"),
            ("🖨️ Print (Ctrl+P)", self._print_selected, "primary-outline", "Print selected voucher (Ctrl+P)"),
            ("📄 Print Pending", self._print_all_pending, "success-outline", "Batch print all unprinted vouchers (Ctrl+Shift+P)"),
            ("📊 Export CSV", self._export_csv, "info-outline", "Export current filtered vouchers to CSV spreadsheet"),
            ("📜 Audit Log", self._view_audit_history_selected, "secondary-outline", "View complete audit trail history for selected voucher"),
        ]
        for text, cmd, style, tip in primary_buttons:
            btn = ttk.Button(row1_actions, text=text, command=cmd, bootstyle=style)
            btn.pack(side=tk.LEFT, padx=2)
            ToolTip(btn, text=tip)

        # Row 2: Lifecycle Actions
        row2_actions = ttk.Frame(action_container)
        row2_actions.pack(fill=tk.X, pady=(0, 3))

        lifecycle_buttons = [
            ("❌ Cancel (Del)", self._cancel_selected, "danger-outline", "Cancel and disable the selected voucher (Del)"),
            ("♻️ Restore (Ctrl+R)", self._restore_selected, "warning-outline", "Restore a cancelled voucher back to active (Ctrl+R)"),
            ("🗑️ Delete (Shift+Del)", self._delete_selected_permanent, "danger-outline", "Permanently remove selected cancelled voucher (Shift+Del)"),
        ]
        for text, cmd, style, tip in lifecycle_buttons:
            btn = ttk.Button(row2_actions, text=text, command=cmd, bootstyle=style)
            btn.pack(side=tk.LEFT, padx=2)
            ToolTip(btn, text=tip)

        # Row 3: Management Modules
        row3_actions = ttk.Frame(action_container)
        row3_actions.pack(fill=tk.X)

        mgr_buttons = [
            ("📁 Categories (Ctrl+G)", self._open_category_manager, "secondary-outline", "Manage Expense Categories & Budgets (Ctrl+G)"),
            ("👤 Names (Ctrl+M)", self._open_name_manager, "secondary-outline", "Manage Payees, Approvers & Personnel (Ctrl+M)"),
            ("🏷️ Tags (Ctrl+Shift+T)", self._open_tag_manager, "info-outline", "Manage Voucher Tags & Expense Labels (Ctrl+Shift+T)"),
            ("💰 Floats (Ctrl+3)", self._open_float_manager, "success-outline", "Manage Cash Floats & Drawers (Ctrl+3 / Ctrl+Shift+F)"),
            ("📜 Statements (Ctrl+Shift+S)", self._open_payee_statement, "primary-outline", "View and export Payee Account Statements (Ctrl+Shift+S)"),
            ("📈 Analytics (Ctrl+I)", self._open_expense_summary, "info-outline", "View expense summary and category breakdown charts (Ctrl+I)"),
            ("⚙️ Settings (Ctrl+,)", self._open_settings, "secondary-outline", "Configure company profiles, printing, and defaults (Ctrl+,)"),
            ("🗑️ Clear All", self._clear_all_vouchers_prompt, "danger-outline", "Delete all vouchers for the active company"),
        ]
        for text, cmd, style, tip in mgr_buttons:
            btn = ttk.Button(row3_actions, text=text, command=cmd, bootstyle=style)
            btn.pack(side=tk.LEFT, padx=2)
            ToolTip(btn, text=tip)

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
            command=lambda: self._notebook.select(0), bootstyle="secondary-outline"
        )
        back_list_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(back_list_btn, text="Return to the Voucher List tab (Esc)")

        # 2. Scrollable Canvas wrapper fills all remaining space above the docked action bar
        form_canvas = tk.Canvas(self._form_tab, highlightthickness=0)
        form_scrollbar = ttk.Scrollbar(self._form_tab, orient=tk.VERTICAL, command=form_canvas.yview)
        self._form_inner = ttk.Frame(form_canvas, padding=(2, 2))

        def _on_form_inner_configure(e):
            if self._form_scroll_timer is not None:
                try:
                    self.root.after_cancel(self._form_scroll_timer)
                except Exception:
                    pass
            self._form_scroll_timer = self.root.after(
                35, lambda: form_canvas.configure(scrollregion=form_canvas.bbox("all"))
            )

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
            if self._notebook.index(self._notebook.select()) == 1:
                form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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
            command=lambda: self._notebook.select(0), bootstyle="secondary-outline"
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
        pm_combo.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(pm_combo, text="Payment method used (Cash, Bank Transfer, Cheque, Credit Card, Online/Other)")

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
            categories_callback=lambda: db.get_categories(active_only=True),
            at_trigger_callback=self._get_at_suggestions,
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

            # Update collapsed strip micro-summary
            if hasattr(self, "_collapsed_stat_lbl") and self._collapsed_stat_lbl:
                self._collapsed_stat_lbl.config(
                    text=f"📊 Total Vouchers: {stats['total_vouchers']}  •  Bills Pending: {stats['bills_pending']}  •  Total: LKR {stats['total_amount']:,.2f}  •  Unprinted: {unprinted_str}"
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # List Tab Actions
    # ------------------------------------------------------------------

    def _refresh_list(self, *args):
        """Refresh the voucher list treeview with vast search, filters, and custom sorting."""
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
        finally:
            conn.close()

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
        self._populate_form_floats(select_float_id=v.get("float_id"))

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
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("No Selection", "Please select vouchers to print.")
            return

        # Bolt Optimization: Single batch query replaces 2x get_voucher N+1 query loop (~98.6% speedup)
        vouchers = db.get_vouchers_by_ids(ids)
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
        if self._notebook.index(self._notebook.select()) == 0:
            self._refresh_list()
        else:
            self._list_dirty = True

    def _open_tag_manager(self):
        """Open the Tag and Label Manager dialog."""
        dlg = TagManagerDialog(self.root, on_tags_changed_callback=self._on_tags_changed)
        dlg.lift()
        dlg.focus_force()

    def _on_tags_changed(self):
        """Callback when tags are added, renamed, or deleted."""
        self._refresh_form_tags()
        if self._notebook.index(self._notebook.select()) == 0:
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

        self._notebook.select(1)
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

        for vid in ids:
            vdata = db.get_voucher(vid)
            if vdata:
                v = vdata["voucher"]
                items = vdata["line_items"]
                if days is None:
                    new_due = ""
                else:
                    base_str = v.get("date") or datetime.now().strftime("%Y-%m-%d")
                    try:
                        base_dt = datetime.strptime(base_str.strip(), "%Y-%m-%d")
                    except Exception:
                        base_dt = datetime.now()
                    new_due = (base_dt + timedelta(days=days)).strftime("%Y-%m-%d")
                v["due_date"] = new_due
                db.update_voucher(vid, v, items)

        msg = "Cleared Due Date" if days is None else f"Set Due Date (+{days} days)"
        self._show_toast(f"{msg} for {len(ids)} voucher(s)", icon="📅", bg="#0f172a", fg="#f0fdf4")
        self._refresh_list()
        self._update_stats()

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

        if v.get("is_reimbursed"):
            reimb_d = v.get("reimbursed_at") or ""
            self._form_title_var.set(f"Edit Voucher: {v['voucher_number']}  [🔄 Reimbursed]")
            self._show_toast(
                f"ℹ️ Voucher {v['voucher_number']} has been reimbursed{f' on {reimb_d}' if reimb_d else ''}.",
                icon="🔄", bg="#065f46", fg="#ffffff", duration_ms=4500
            )
        else:
            self._form_title_var.set(f"Edit Voucher: {v['voucher_number']}")
        self._notebook.tab(1, text=f"  ✏️ {v['voucher_number']}  ")
        self._notebook.select(1)
        self._paid_to.focus_set()

    def _on_payee_changed(self, event=None):
        """Check if selected payee has a default expense category and auto-fill line items if blank."""
        payee_name = self._paid_to.get().strip()
        if not payee_name:
            return

        person = db.get_person_by_name(payee_name)
        if not person:
            return

        default_cat = person.get("default_category", "").strip()
        if not default_cat:
            return

        # Check if first line item category is empty
        if self._line_items._rows:
            first_cat_entry = self._line_items._rows[0]["category"]
            if not first_cat_entry.get().strip():
                first_cat_entry.delete(0, tk.END)
                first_cat_entry.insert(0, default_cat)
                self._show_toast(f"Auto-filled default category '{default_cat}' for {person['name']}", icon="✨", bg="#064e3b", fg="#ecfdf5", duration_ms=2200)

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

        # Pre-fill Prepared By from sticky remembered setting until changed
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
        self._form_title_var.set("New Voucher")
        self._notebook.tab(1, text="  ➕ New Voucher (Ctrl+N)  ")

    def _get_form_data(self):
        """Extract form data into a dict."""
        float_id = None
        flt_name = getattr(self, "_form_float_var", tk.StringVar()).get().strip()
        if flt_name and hasattr(self, "_form_float_id_map"):
            float_id = self._form_float_id_map.get(flt_name)

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
            if self._notebook.index(self._notebook.select()) == 0:
                self._refresh_list()
            else:
                self._list_dirty = True

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
        """Clean up pending timer callbacks and close the window."""
        if getattr(self, "_search_timer", None):
            try:
                self.root.after_cancel(self._search_timer)
            except Exception:
                pass
            self._search_timer = None

        if getattr(self, "_toast_timer_id", None):
            try:
                self.root.after_cancel(self._toast_timer_id)
            except Exception:
                pass
            self._toast_timer_id = None

        if getattr(self, "_auto_hide_timer", None):
            try:
                self.root.after_cancel(self._auto_hide_timer)
            except Exception:
                pass
            self._auto_hide_timer = None

        self.root.destroy()


