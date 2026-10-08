"""
Reusable custom widgets for the Voucher Printing Tool.
- AutocompleteEntry: Text entry with dropdown suggestions
- LineItemFrame: Dynamic table for adding/removing expense line items
- MemoPanel: Scrollable memo history with add capability
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap import ToolTip
from ttkbootstrap.constants import *


from datetime import datetime, timedelta, date
import calendar
from ttkbootstrap.widgets import DateEntry
import database as db


class SmartDateEntry(DateEntry):
    """
    Enhanced Date Entry with:
    - Text field formatted YYYY-MM-DD
    - Dropdown Calendar picker button (via ttkbootstrap DateEntry)
    - Keyboard navigation:
        * Up / Down: ±1 Day
        * Shift + Up / Shift + Down (or PageUp / PageDown): ±1 Month
        * Ctrl + Up / Ctrl + Down: ±1 Year
        * 't' or 'T': Jump to Today
    """

    def __init__(self, master=None, **kwargs):
        kwargs.setdefault("date_format", "%Y-%m-%d")
        kwargs.setdefault("start_date", date.today())
        kwargs.setdefault("width", 11)
        super().__init__(master, **kwargs)

        # Ensure initial value is cleanly formatted YYYY-MM-DD
        cur = self.entry.get().strip()
        if len(cur) > 10:
            self.set_date(cur[:10])

        ToolTip(self.entry, text="Date (YYYY-MM-DD)\nKeyboard: Up/Down ±1d | Shift+Up/Down ±1m | Ctrl+Up/Down ±1y | T = Today")

        # Bind keyboard arrows and shortcuts to the text entry
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Shift-Up>", self._on_shift_up)
        self.entry.bind("<Shift-Down>", self._on_shift_down)
        self.entry.bind("<Prior>", self._on_shift_up)    # PageUp
        self.entry.bind("<Next>", self._on_shift_down)   # PageDown
        self.entry.bind("<Control-Up>", self._on_ctrl_up)
        self.entry.bind("<Control-Down>", self._on_ctrl_down)
        self.entry.bind("<Key-t>", self._on_today)
        self.entry.bind("<Key-T>", self._on_today)

        # Notify when user manually types or pastes or blurs or selects from popup
        self.entry.bind("<KeyRelease>", self._on_key_release_date)
        self.entry.bind("<FocusOut>", lambda e: self.event_generate("<<DateModified>>"))
        self.bind("<<DateEntrySelected>>", lambda e: self.event_generate("<<DateModified>>"))

    def _on_key_release_date(self, event):
        if event.keysym in ("Up", "Down", "Prior", "Next", "Escape", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R"):
            return
        self.event_generate("<<DateModified>>")

    def _adjust(self, days=0, months=0, years=0):
        val = self.entry.get().strip()
        if len(val) > 10:
            val = val[:10]
        try:
            dt = datetime.strptime(val, "%Y-%m-%d")
        except Exception:
            dt = datetime.now()

        ny = dt.year + years
        nm = dt.month + months
        while nm > 12:
            nm -= 12
            ny += 1
        while nm < 1:
            nm += 12
            ny -= 1

        max_d = calendar.monthrange(ny, nm)[1]
        nd = min(dt.day, max_d)
        dt = dt.replace(year=ny, month=nm, day=nd)
        dt += timedelta(days=days)

        new_str = dt.strftime("%Y-%m-%d")
        self.entry.delete(0, tk.END)
        self.entry.insert(0, new_str)
        self.event_generate("<<DateModified>>")
        return "break"

    def _on_arrow_up(self, event):
        return self._adjust(days=1)

    def _on_arrow_down(self, event):
        return self._adjust(days=-1)

    def _on_shift_up(self, event):
        return self._adjust(months=1)

    def _on_shift_down(self, event):
        return self._adjust(months=-1)

    def _on_ctrl_up(self, event):
        return self._adjust(years=1)

    def _on_ctrl_down(self, event):
        return self._adjust(years=-1)

    def _on_today(self, event):
        today_str = datetime.now().strftime("%Y-%m-%d")
        self.entry.delete(0, tk.END)
        self.entry.insert(0, today_str)
        self.event_generate("<<DateModified>>")
        return "break"

    def get_date(self):
        """Return the current date string in YYYY-MM-DD format."""
        val = self.entry.get().strip()
        if len(val) >= 10:
            return val[:10]
        return val

    def set_date(self, date_str):
        """Set the date value and notify listeners."""
        s = str(date_str).strip()
        if len(s) > 10:
            s = s[:10]
        self.entry.delete(0, tk.END)
        self.entry.insert(0, s)
        self.event_generate("<<DateModified>>")


class AutocompleteEntry(ttk.Entry):
    """
    Entry widget with two autocomplete modes:

    1. Normal autocomplete (suggestions_callback):
       - Triggers on any keypress and filters suggestions by what's typed.

    2. @ Trigger autocomplete (at_trigger_callback):
       - Triggered when user types '@' anywhere in the field.
       - Shows ALL items from at_trigger_callback() (people + categories).
       - User continues typing to filter (text after '@').
       - Arrow keys navigate the popup; Tab selects and replaces '@...' with value.
       - Escape dismisses the popup.
    """

    def __init__(self, master, suggestions_callback=None, at_trigger_callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self._suggestions_callback = suggestions_callback or (lambda: [])
        self._at_trigger_callback = at_trigger_callback  # returns list of (label, type_hint)
        self._listbox = None
        self._listbox_window = None
        self._at_mode = False          # True when we are in @-trigger mode
        self._at_pos = -1              # cursor position just after '@'
        self._at_items = []            # full combined list for @-mode

        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Down>", self._on_arrow_down)
        self.bind("<Up>", self._on_arrow_up_from_entry)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Tab>", self._on_tab)
        self.bind("<Return>", self._on_return)

    # ── Key handling ───────────────────────────────────────────────────────

    def _on_key_release(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab", "Shift_L", "Shift_R",
                            "Control_L", "Control_R", "Alt_L", "Alt_R", "Next", "Prior"):
            return

        text = self.get()
        cursor = self.index(tk.INSERT)

        # ── @ trigger mode ────────────────────────────────────────────────
        if self._at_trigger_callback:
            # Find the last '@' at or before cursor
            before_cursor = text[:cursor]
            at_idx = before_cursor.rfind("@")
            if at_idx != -1:
                # We are in @ context
                if not self._at_mode:
                    # Just entered @ mode
                    self._at_mode = True
                    self._at_pos = at_idx + 1
                    self._at_items = self._at_trigger_callback()

                fragment = before_cursor[at_idx + 1:]  # what user typed after '@'
                if fragment:
                    matches = [it for it in self._at_items if fragment.lower() in it[0].lower()]
                else:
                    matches = list(self._at_items)

                if matches:
                    self._show_listbox_at(matches)
                else:
                    self._close_listbox()
                return
            else:
                if self._at_mode:
                    self._at_mode = False
                    self._close_listbox()

        # ── Normal autocomplete ───────────────────────────────────────────
        self._at_mode = False
        typed = text.strip()
        suggestions = self._suggestions_callback() if self._suggestions_callback else []
        if not suggestions:
            self._close_listbox()
            return

        if not typed:
            # If entry is cleared but popup is visible, show all suggestions
            if self._listbox_window and self._listbox_window.winfo_exists():
                self._show_listbox(suggestions)
            else:
                self._close_listbox()
            return

        matches = []
        for s in suggestions:
            if isinstance(s, tuple):
                display, val = s[0], s[1]
                if typed.lower() in display.lower() or typed.lower() in str(val).lower():
                    matches.append(s)
            elif isinstance(s, dict):
                display = s.get("display", "")
                val = s.get("value", s.get("name", ""))
                if typed.lower() in str(display).lower() or typed.lower() in str(val).lower():
                    matches.append(s)
            else:
                if typed.lower() in str(s).lower():
                    matches.append(s)

        if matches:
            self._show_listbox(matches)
        else:
            self._close_listbox()

    def _on_tab(self, event):
        """Tab selects highlighted item from popup if open."""
        if self._listbox and self._listbox.winfo_exists() and self._listbox.curselection():
            if self._at_mode:
                self._on_at_select()
            else:
                self._on_select()
            return "break"  # prevent focus change
        return None  # normal tab behaviour

    def _on_return(self, event):
        """Enter key selects highlighted item from popup if open."""
        if self._listbox and self._listbox.winfo_exists() and self._listbox.curselection():
            if self._at_mode:
                self._on_at_select()
            else:
                self._on_select()
            return "break"
        return None

    def _on_escape(self, event):
        """Escape closes popup if open."""
        if self._listbox and self._listbox.winfo_exists():
            self._close_listbox()
            return "break"
        return None

    # ── Normal autocomplete popup (QuickBooks / Ledger-Aware) ──────────────

    def _show_listbox(self, items):
        """Show a rich string / tuple list popup with scrollbar and keyboard support."""
        self._close_listbox()
        if not items:
            return

        self._listbox_window = tk.Toplevel(self)
        self._listbox_window.wm_overrideredirect(True)
        self._listbox_window.attributes("-topmost", True)

        container = tk.Frame(self._listbox_window, bg="#0f172a", bd=1, relief="solid")
        container.pack(fill=tk.BOTH, expand=True)

        # Header hint for quick search & navigation
        hint_frame = tk.Frame(container, bg="#1e293b", padx=6, pady=3)
        hint_frame.pack(fill=tk.X)
        tk.Label(
            hint_frame,
            text="📁 Categories & Linked Ledgers (↑↓ / Click to pick)",
            bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8, "bold"), anchor="w"
        ).pack(side=tk.LEFT)

        body_frame = tk.Frame(container, bg="#0f172a")
        body_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(body_frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            body_frame,
            height=min(len(items), 9),
            font=("Segoe UI", 9),
            selectbackground="#2563eb",
            selectforeground="white",
            bg="#0f172a",
            fg="#f8fafc",
            bd=0,
            highlightthickness=0,
            exportselection=False,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self._listbox.yview)

        if len(items) > 9:
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._display_items = items
        for item in items:
            if isinstance(item, tuple):
                display_text = item[0]
            elif isinstance(item, dict):
                display_text = item.get("display", item.get("name", ""))
            else:
                display_text = str(item)
            self._listbox.insert(tk.END, f"  {display_text}")

        if items:
            self._listbox.select_set(0)
            self._listbox.activate(0)

        # Position calculation
        self.update_idletasks()
        try:
            root_x = self.winfo_rootx()
            root_y = self.winfo_rooty()
            widget_h = self.winfo_height()
            screen_h = self.winfo_screenheight()
        except Exception:
            root_x, root_y, widget_h, screen_h = 100, 100, 24, 800

        w = max(self.winfo_width(), 360)
        h = min(len(items), 9) * 22 + 28
        y = root_y + widget_h + 1
        if y + h > screen_h - 40:
            y = max(10, root_y - h - 1)

        self._listbox_window.geometry(f"{w}x{h}+{root_x}+{y}")

        self._listbox.bind("<ButtonRelease-1>", lambda e: self._on_select())
        self._listbox.bind("<Return>", lambda e: self._on_select())
        self._listbox.bind("<Tab>", lambda e: (self._on_select(), "break")[1])
        self._listbox.bind("<Escape>", lambda e: (self._close_listbox(), self.focus_set(), "break")[2])

    # ── @ trigger popup ────────────────────────────────────────────────────

    def _show_listbox_at(self, items):
        """
        Show popup for @-trigger mode.
        items: list of (label, type_hint) tuples where type_hint is 'person' or 'category'
        """
        self._close_listbox()
        self._listbox_window = tk.Toplevel(self)
        self._listbox_window.wm_overrideredirect(True)
        self._listbox_window.attributes("-topmost", True)

        frame = tk.Frame(self._listbox_window, bg="#1e293b")
        frame.pack(fill=tk.BOTH, expand=True)

        # Header hint
        hint_lbl = tk.Label(
            frame, text="@ suggestions — ↑↓ navigate, Tab/Enter to insert, Esc to close",
            bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 7), anchor="w", padx=4
        )
        hint_lbl.pack(fill=tk.X)

        self._listbox = tk.Listbox(
            frame,
            height=min(len(items), 9),
            font=("Segoe UI", 9),
            selectbackground="#3b82f6",
            selectforeground="white",
            bg="#0f172a",
            fg="#e2e8f0",
            bd=0,
            highlightthickness=0,
            exportselection=False,
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)

        # Store items for type-aware selection
        self._at_display_items = items
        for label, type_hint in items:
            prefix = "👤" if type_hint == "person" else "📁"
            self._listbox.insert(tk.END, f"  {prefix}  {label}")

        if items:
            self._listbox.select_set(0)
            self._listbox.activate(0)

        # Position
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 280)
        h = min(len(items), 9) * 22 + 20
        self._listbox_window.geometry(f"{w}x{h}+{x}+{y}")

        self._listbox.bind("<ButtonRelease-1>", lambda e: self._on_at_select())
        self._listbox.bind("<Return>", lambda e: self._on_at_select())
        self._listbox.bind("<Tab>", lambda e: (self._on_at_select(), "break")[1])
        self._listbox.bind("<Escape>", lambda e: (self._close_listbox(), self.focus_set(), "break")[2])

    def _on_select(self, event=None):
        """Normal autocomplete / dropdown select."""
        if self._listbox and self._listbox.curselection():
            idx = self._listbox.curselection()[0]
            if hasattr(self, "_display_items") and idx < len(self._display_items):
                item = self._display_items[idx]
                if isinstance(item, tuple):
                    val = item[1]
                elif isinstance(item, dict):
                    val = item.get("value", item.get("name", ""))
                else:
                    val = str(item)
            else:
                val = self._listbox.get(idx).strip()

            self.delete(0, tk.END)
            self.insert(0, str(val))
            self._close_listbox()
            self.event_generate("<<AutocompleteSelected>>")
            return "break"

    def _on_at_select(self, event=None):
        """@ trigger: replace '@...' text with the selected value."""
        if not (self._listbox and self._listbox.curselection()):
            return
        idx = self._listbox.curselection()[0]
        label, _type = self._at_display_items[idx]

        # Replace from the '@' sign to cursor with the selected label
        current = self.get()
        cursor = self.index(tk.INSERT)
        before = current[:cursor]
        after = current[cursor:]
        at_idx = before.rfind("@")
        if at_idx != -1:
            new_text = current[:at_idx] + label + after
            self.delete(0, tk.END)
            self.insert(0, new_text)
            self.icursor(at_idx + len(label))

        self._at_mode = False
        self._close_listbox()
        self.event_generate("<<AutocompleteSelected>>")
        return "break"

    def show_dropdown(self):
        """Manually trigger dropdown display (e.g. from a dropdown arrow button or shortcut)."""
        suggestions = self._suggestions_callback() if self._suggestions_callback else []
        typed = self.get().strip().lower()
        if typed:
            matches = []
            for s in suggestions:
                if isinstance(s, tuple):
                    if typed in s[0].lower() or typed in str(s[1]).lower():
                        matches.append(s)
                elif isinstance(s, dict):
                    display = s.get("display", "")
                    val = s.get("value", s.get("name", ""))
                    if typed in str(display).lower() or typed in str(val).lower():
                        matches.append(s)
                else:
                    if typed in str(s).lower():
                        matches.append(s)
        else:
            matches = list(suggestions)

        if matches:
            self._show_listbox(matches)

    # ── Navigation ─────────────────────────────────────────────────────────

    def _on_arrow_down(self, event):
        if self._listbox and self._listbox.winfo_exists():
            cur = self._listbox.curselection()
            if not cur:
                next_idx = 0
            else:
                next_idx = min(cur[0] + 1, self._listbox.size() - 1)
            self._listbox.select_clear(0, tk.END)
            self._listbox.select_set(next_idx)
            self._listbox.activate(next_idx)
            self._listbox.see(next_idx)
            return "break"
        else:
            self.show_dropdown()
            return "break"
        return None

    def _on_arrow_up_from_entry(self, event):
        if self._listbox and self._listbox.winfo_exists():
            cur = self._listbox.curselection()
            if cur:
                prev_idx = max(cur[0] - 1, 0)
                self._listbox.select_clear(0, tk.END)
                self._listbox.select_set(prev_idx)
                self._listbox.activate(prev_idx)
                self._listbox.see(prev_idx)
            return "break"
        return None

    def _on_focus_out(self, event):
        def _check_and_close():
            self._focus_timer = None
            try:
                focused = self.focus_get()
                if self._listbox and focused == self._listbox:
                    return
                if self._listbox_window and focused == self._listbox_window:
                    return
            except Exception:
                pass
            self._close_listbox()

        if getattr(self, "_focus_timer", None):
            try:
                self.after_cancel(self._focus_timer)
            except Exception:
                pass
        self._focus_timer = self.after(200, _check_and_close)

    def _close_listbox(self, event=None):
        if getattr(self, "_focus_timer", None):
            try:
                self.after_cancel(self._focus_timer)
            except Exception:
                pass
            self._focus_timer = None
        self._at_mode = False
        if self._listbox_window:
            try:
                self._listbox_window.destroy()
            except Exception:
                pass
            self._listbox_window = None
            self._listbox = None

    def set(self, text):
        """Helper method to clear and set entry text."""
        self.delete(0, tk.END)
        if text is not None and str(text) != "":
            self.insert(0, str(text))


class LineItemFrame(ttk.LabelFrame):
    """
    A dynamic frame for managing multiple line items (expense lines).
    Each row has: Description, Category with QuickBooks-style linked ledger dropdown, Amount, and a remove button.
    """

    def __init__(
        self,
        master,
        categories_callback=None,
        at_trigger_callback=None,
        manage_categories_callback=None,
        **kwargs,
    ):
        super().__init__(master, text="Expense Line Items", padding=4, **kwargs)
        self._categories_callback = categories_callback or (lambda: [])
        self._at_callback = at_trigger_callback  # callback -> [(label, type_hint), ...]
        self._manage_categories_callback = manage_categories_callback
        self._rows = []
        self._currency = "LKR"

        # Header row with light soft slate background
        header = tk.Frame(self, bg="#e2e8f0", padx=4, pady=3)
        header.pack(fill=tk.X, pady=(0, 3))

        num_hdr = tk.Label(header, text="#", width=3, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#334155", anchor="center")
        num_hdr.pack(side=tk.LEFT, padx=2)
        ToolTip(num_hdr, text="Line item index")

        desc_hdr = tk.Label(header, text="Description", font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#334155", anchor="w")
        desc_hdr.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ToolTip(desc_hdr, text="Enter details about the expense line item")

        cat_hdr = tk.Label(header, text="📁 Category / Ledger (select existing) ▼", width=32, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#166534", anchor="w")
        cat_hdr.pack(side=tk.LEFT, padx=2)
        ToolTip(cat_hdr, text="Type to search, then select an existing category or ledger account")

        self._amount_header = tk.Label(header, text="💵 Amount (LKR)", width=16, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#854d0e", anchor="w")
        self._amount_header.pack(side=tk.LEFT, padx=2)
        self._amount_header_tip = ToolTip(self._amount_header, text="Enter amount in LKR")

        tk.Label(header, text="", width=4, bg="#e2e8f0").pack(side=tk.LEFT, padx=2)

        # Container for rows
        self._scroll_frame = ttk.Frame(self)
        self._scroll_frame.pack(fill=tk.BOTH, expand=True)

        # Buttons and total bar
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        self._add_btn = ttk.Button(
            btn_frame, text="+ Add Line (Alt+A)",
            command=self.add_row, bootstyle="success-outline"
        )
        self._add_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(self._add_btn, text="Add a new expense line item (Alt+A)")

        self._clear_btn = ttk.Button(
            btn_frame, text="🧹 Clear All Lines",
            command=self.clear, bootstyle="secondary-outline"
        )
        self._clear_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(self._clear_btn, text="Clear all line items")

        if self._manage_categories_callback:
            self._manage_categories_btn = ttk.Button(
                btn_frame,
                text="📁 Manage Categories (Ctrl+G)",
                command=self._manage_categories_callback,
                bootstyle="info-outline",
            )
            self._manage_categories_btn.pack(side=tk.LEFT, padx=(0, 4))
            ToolTip(
                self._manage_categories_btn,
                text="Create or edit categories in the controlled Category Manager",
            )

        ttk.Label(
            btn_frame, text="Type to search; select from the list. Enter in Amount adds the next line.",
            font=("Segoe UI", 8), foreground="#6c757d"
        ).pack(side=tk.LEFT, padx=6)

        # Styled Total badge with soft green tint
        total_badge = tk.Frame(btn_frame, bg="#dcfce7", padx=8, pady=2, highlightbackground="#86efac", highlightthickness=1)
        total_badge.pack(side=tk.RIGHT, padx=6)
        self._total_var = tk.StringVar(value="Total: LKR 0.00")
        tk.Label(
            total_badge, textvariable=self._total_var,
            font=("Segoe UI", 12, "bold"), bg="#dcfce7", fg="#15803d"
        ).pack()

        # Start with one empty row
        self.add_row()

    def set_currency(self, currency: str) -> None:
        """Set the transaction currency shown for all entered line amounts."""
        self._currency = (currency or "LKR").upper()
        self.configure(text=f"Expense Line Items — enter amounts in {self._currency}")
        self._amount_header.configure(text=f"💵 Amount ({self._currency})")
        self._amount_header_tip.configure(
            text=f"Enter each line amount in {self._currency}, not home currency"
        )
        for row in self._rows:
            amount_tip = row.get("amount_tip")
            if amount_tip:
                amount_tip.configure(
                    text=(
                        f"Line item amount in {self._currency} "
                        "(Press Enter to add next line)"
                    )
                )
        self._update_total()
    def add_row(self, description="", category="", amount="", focus_desc=False):
        """Add a new line item row with category dropdown and ledger suggestions."""
        row_frame = ttk.Frame(self._scroll_frame)
        row_frame.pack(fill=tk.X, pady=1)

        row_num = len(self._rows) + 1
        num_label = ttk.Label(row_frame, text=str(row_num), width=3, anchor="center")
        num_label.pack(side=tk.LEFT, padx=2)

        desc_entry = AutocompleteEntry(
            row_frame,
            at_trigger_callback=self._at_callback,
            style="Desc.TEntry"
        )
        desc_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        if description:
            desc_entry.insert(0, description)
        ToolTip(desc_entry, text="Line item description (Ctrl+Shift+D to duplicate row)")

        # Category box with integrated dropdown arrow button (QuickBooks style)
        cat_box = tk.Frame(
            row_frame,
            background="#ffffff",
            highlightbackground="#cbd5e1",
            highlightcolor="#2563eb",
            highlightthickness=1,
        )
        cat_box.pack(side=tk.LEFT, padx=2)

        cat_entry = AutocompleteEntry(
            cat_box,
            suggestions_callback=self._categories_callback,
            at_trigger_callback=self._at_callback,
            style="Category.TEntry",
            width=24
        )
        cat_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        if category:
            cat_entry.insert(0, category)
        ToolTip(
            cat_entry,
            text="Required. Type to search and select an existing category or ledger account.",
        )

        cat_drop_btn = ttk.Button(
            cat_box,
            text="▼",
            width=2,
            command=cat_entry.show_dropdown,
            bootstyle="secondary-outline"
        )
        cat_drop_btn.pack(side=tk.LEFT, padx=(1, 0))
        ToolTip(cat_drop_btn, text="Browse existing categories and linked ledger accounts")

        cat_entry.bind(
            "<<AutocompleteSelected>>",
            lambda event: self._validate_category_entry(cat_entry),
        )
        cat_entry.bind(
            "<FocusOut>",
            lambda event: self._validate_category_entry(cat_entry),
        )
        cat_entry.bind(
            "<KeyRelease>",
            lambda event: self._set_category_state(cat_entry, valid=None),
            add="+",
        )

        # Double click on entry also reveals dropdown
        cat_entry.bind("<Double-Button-1>", lambda e: cat_entry.show_dropdown())

        amt_entry = ttk.Entry(row_frame, width=16, style="Amount.TEntry")
        amt_entry.pack(side=tk.LEFT, padx=2)
        if amount:
            amt_entry.insert(0, str(amount))
        amt_entry.bind("<KeyRelease>", lambda e: self._update_total())
        amt_entry.bind("<Return>", lambda e: self._on_enter_amt())
        amount_tip = ToolTip(
            amt_entry,
            text=(
                f"Line item amount in {self._currency} "
                "(Press Enter to add next line)"
            ),
        )

        remove_btn = ttk.Button(
            row_frame, text="✕", width=3,
            command=lambda: self._remove_row(row_frame),
            bootstyle="danger-outline"
        )
        remove_btn.pack(side=tk.LEFT, padx=2)
        ToolTip(remove_btn, text="Remove this line item")

        row_data = {
            "frame": row_frame,
            "num_label": num_label,
            "description": desc_entry,
            "category": cat_entry,
            "category_box": cat_box,
            "amount": amt_entry,
            "amount_tip": amount_tip,
            "remove_btn": remove_btn,
        }
        self._rows.append(row_data)
        self._renumber_rows()
        self._update_remove_button_states()

        # Bind Ctrl+Shift+D to duplicate focused row
        for widget in (desc_entry, cat_entry, amt_entry):
            widget.bind("<Control-Shift-D>", lambda e, r=row_data: self._duplicate_row(r))
            widget.bind("<Control-Shift-d>", lambda e, r=row_data: self._duplicate_row(r))

        if focus_desc:
            desc_entry.focus_set()

    @staticmethod
    def _normalize_category(value: object) -> str:
        """Normalize a category value for stable, case-insensitive matching."""
        return " ".join(str(value or "").split()).casefold()

    def _category_value_map(self) -> dict[str, str]:
        """Return allowed category and ledger values keyed by normalized text."""
        try:
            options = self._categories_callback() or []
        except Exception:
            options = []

        values = {}
        for option in options:
            if isinstance(option, (tuple, list)) and len(option) >= 2:
                display, value = option[0], option[1]
            elif isinstance(option, dict):
                display = option.get("display") or option.get("label") or ""
                value = option.get("value") or option.get("name") or ""
            else:
                display = value = option

            clean_value = " ".join(str(value or "").split())
            if (
                not clean_value
                or clean_value == "__ADD_NEW_CATEGORY__"
                or str(display or "").lstrip().startswith("➕")
            ):
                continue
            values[self._normalize_category(clean_value)] = clean_value
        return values

    def _set_category_state(self, entry: AutocompleteEntry, valid: bool | None) -> None:
        """Show a neutral or invalid border around a category selector."""
        row = next((item for item in self._rows if item["category"] is entry), None)
        if not row:
            return
        color = "#dc2626" if valid is False else "#cbd5e1"
        row["category_box"].configure(highlightbackground=color)

    def _validate_category_entry(self, entry: AutocompleteEntry, require_value: bool = False) -> bool:
        """Validate one entry without creating categories or opening dialogs."""
        value = " ".join(entry.get().split())
        if not value:
            self._set_category_state(entry, valid=not require_value)
            return not require_value

        canonical = self._category_value_map().get(self._normalize_category(value))
        if not canonical:
            self._set_category_state(entry, valid=False)
            return False

        if entry.get() != canonical:
            entry.set(canonical)
        self._set_category_state(entry, valid=True)
        return True

    def validate_categories(self) -> str | None:
        """Return a user-facing error when a submitted line has no valid category."""
        allowed = self._category_value_map()
        for row_number, row in enumerate(self._rows, 1):
            description = row["description"].get().strip()
            amount = row["amount"].get().strip()
            if not (description and amount):
                continue

            entry = row["category"]
            value = " ".join(entry.get().split())
            canonical = allowed.get(self._normalize_category(value)) if value else None
            if not canonical:
                self._set_category_state(entry, valid=False)
                entry.focus_set()
                if not allowed:
                    return (
                        "No expense categories are available. Open Manage Categories "
                        "(Ctrl+G), create one, then select it on this line."
                    )
                if not value:
                    return f"Select a category or ledger account for line item #{row_number}."
                return (
                    f"'{value}' is not an existing category or ledger account on line "
                    f"#{row_number}. Select a value from the list, or create it first in "
                    "Manage Categories (Ctrl+G)."
                )

            if entry.get() != canonical:
                entry.set(canonical)
            self._set_category_state(entry, valid=True)
        return None

    def _duplicate_row(self, row_data):
        """Duplicate an existing line item row."""
        desc = row_data["description"].get()
        cat = row_data["category"].get()
        amt = row_data["amount"].get()
        self.add_row(description=desc, category=cat, amount=amt, focus_desc=True)
        self._update_total()
        return "break"

    def _on_enter_amt(self):
        """When pressing enter in amount, add a new row and focus description."""
        self._update_total()
        self.add_row(focus_desc=True)
        return "break"

    def _remove_row(self, row_frame):
        """Remove a line item row."""
        if len(self._rows) <= 1:
            return  # Keep at least one row

        self._rows = [r for r in self._rows if r["frame"] != row_frame]
        row_frame.destroy()
        self._renumber_rows()
        self._update_remove_button_states()
        self._update_total()

    def _update_remove_button_states(self):
        """
        Dynamically disable the remove button when only 1 line item exists
        so users clearly see the constraint instead of clicking a silently disabled action.
        """
        is_single = (len(self._rows) <= 1)
        for row in self._rows:
            btn = row.get("remove_btn")
            if btn:
                if is_single:
                    btn.config(state=tk.DISABLED)
                else:
                    btn.config(state=tk.NORMAL)

    def _renumber_rows(self):
        for i, row in enumerate(self._rows, 1):
            row["num_label"].config(text=str(i))

    def _update_total(self):
        total = 0.0
        for row in self._rows:
            try:
                total += float(row["amount"].get())
            except (ValueError, TypeError):
                pass
        self._total_var.set(f"Total: {self._currency} {total:,.2f}")

    def get_items(self):
        """Return list of line item dicts."""
        items = []
        for row in self._rows:
            desc = row["description"].get().strip()
            amt_str = row["amount"].get().strip()
            if desc and amt_str:
                try:
                    amount = float(amt_str)
                except ValueError:
                    amount = 0.0
                items.append({
                    "description": desc,
                    "category": row["category"].get().strip(),
                    "amount": amount,
                })
        return items

    def get_total(self):
        """Return the computed total."""
        return sum(item["amount"] for item in self.get_items())

    def clear(self):
        """Reset line items to a single empty row without unnecessary widget churn."""
        if not self._rows:
            self.add_row()
        else:
            first = self._rows[0]
            first["description"].delete(0, tk.END)
            first["category"].delete(0, tk.END)
            first["amount"].delete(0, tk.END)
            self._set_category_state(first["category"], valid=None)
            for row in self._rows[1:]:
                row["frame"].destroy()
            self._rows = [first]
        self._renumber_rows()
        self._update_remove_button_states()
        self._total_var.set(f"Total: {self._currency} 0.00")

    def set_items(self, items):
        """Populate with line items, reusing existing row widgets for maximum rendering speed."""
        if not items:
            self.clear()
            return

        needed = len(items)
        existing = len(self._rows)

        # 1. In-place update of existing rows
        for i in range(min(needed, existing)):
            item = items[i]
            row = self._rows[i]
            row["description"].delete(0, tk.END)
            desc_val = str(item.get("description", "") or "")
            if desc_val:
                row["description"].insert(0, desc_val)

            row["category"].delete(0, tk.END)
            cat_val = str(item.get("category", "") or "")
            if cat_val:
                row["category"].insert(0, cat_val)

            row["amount"].delete(0, tk.END)
            amt_val = str(item.get("amount", "") or "")
            if amt_val:
                row["amount"].insert(0, amt_val)

        # 2. Add extra rows if more items are needed
        if needed > existing:
            for i in range(existing, needed):
                item = items[i]
                self.add_row(
                    description=item.get("description", ""),
                    category=item.get("category", ""),
                    amount=item.get("amount", ""),
                )
        # 3. Remove surplus rows if any
        elif existing > needed:
            for row in self._rows[needed:]:
                row["frame"].destroy()
            self._rows = self._rows[:needed]

        self._renumber_rows()
        self._update_remove_button_states()
        self._update_total()



class MemoPanel(ttk.LabelFrame):
    """
    Panel for displaying and adding memos/comments to a voucher.
    Shows timestamped history and allows adding new memos.
    """

    def __init__(self, master, on_add_callback=None, text_height=4, **kwargs):
        super().__init__(master, text="Memos & Follow-up Notes", padding=4, **kwargs)
        self._on_add_callback = on_add_callback

        # Add new memo area
        add_frame = ttk.Frame(self)
        add_frame.pack(fill=tk.X, pady=(0, 4))

        self._memo_type_var = tk.StringVar(value="General")
        type_combo = ttk.Combobox(
            add_frame,
            textvariable=self._memo_type_var,
            values=["General", "Follow-up", "Bill Status", "Important"],
            width=11,
            state="readonly"
        )
        type_combo.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(type_combo, text="Select note category or urgency level")

        self._memo_entry = ttk.Entry(add_frame, style="Party.TEntry")
        self._memo_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._memo_entry.bind("<Return>", lambda e: self._add_memo())
        ToolTip(self._memo_entry, text="Enter follow-up note or memo (Press Enter to add)")

        add_btn = ttk.Button(add_frame, text="+ Add", command=self._add_memo, bootstyle="info-outline")
        add_btn.pack(side=tk.LEFT)
        ToolTip(add_btn, text="Add memo to voucher history")

        # Memo history display
        self._text = tk.Text(
            self, height=text_height, wrap=tk.WORD, state=tk.DISABLED,
            font=("Segoe UI", 9), relief=tk.FLAT,
            background="#f8f9fa", padx=6, pady=4
        )
        self._text.pack(fill=tk.BOTH, expand=True)

        # Tag styles
        self._text.tag_configure("timestamp", foreground="#6c757d", font=("Segoe UI", 8))
        self._text.tag_configure("type_general", foreground="#495057")
        self._text.tag_configure("type_followup", foreground="#0d6efd")
        self._text.tag_configure("type_billstatus", foreground="#198754")
        self._text.tag_configure("type_important", foreground="#dc3545", font=("Segoe UI", 9, "bold"))

    def _add_memo(self):
        text = self._memo_entry.get().strip()
        if text and self._on_add_callback:
            self._on_add_callback(text, self._memo_type_var.get())
            self._memo_entry.delete(0, tk.END)

    def load_memos(self, memos):
        """Load memo history into the display."""
        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)

        for memo in memos:
            timestamp = memo.get("created_at", "")
            if timestamp:
                try:
                    dt = timestamp[:19]
                    self._text.insert(tk.END, f"[{dt}] ", "timestamp")
                except Exception:
                    self._text.insert(tk.END, f"[{timestamp}] ", "timestamp")

            memo_type = memo.get("memo_type", "General")
            type_tag = f"type_{memo_type.lower().replace('-', '').replace(' ', '')}"
            if type_tag not in ("type_general", "type_followup", "type_billstatus", "type_important"):
                type_tag = "type_general"

            self._text.insert(tk.END, f"[{memo_type}] ", type_tag)
            self._text.insert(tk.END, f"{memo.get('memo_text', '')}\n")

        if not memos:
            self._text.insert(tk.END, "No notes yet.", "timestamp")

        self._text.config(state=tk.DISABLED)

    def clear(self):
        """Clear the memo display and entry."""
        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.config(state=tk.DISABLED)
        self._memo_entry.delete(0, tk.END)


class SearchableAccountSelector(ttk.Frame):
    """
    Searchable ledger account selector with:
    - Real-time auto-loading & live filtering popup as user types (matching code, name, type)
    - Dropdown toggle button (▼) to browse all available accounts
    - ➕ New button opening the Account creation modal popup
    - Up/Down arrow navigation, Tab/Enter selection, and smart account ID resolution
    """
    def __init__(
        self,
        master,
        company_id=None,
        default_account_type="Expense",
        allowed_types=None,
        include_unlinked=True,
        on_account_changed=None,
        **kwargs
    ):
        super().__init__(master, **kwargs)
        self.company_id = company_id or db.get_active_company_id()
        self.default_account_type = default_account_type
        self.allowed_types = allowed_types
        self.include_unlinked = include_unlinked
        self.on_account_changed = on_account_changed

        self._accounts = []
        self._id_map = {}
        self._selected_account_id = None
        self._popup_window = None
        self._listbox = None
        self._popup_items = []

        self._build_ui()
        self.reload_accounts()

    def _build_ui(self):
        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.entry_var)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        # Dropdown button
        self.drop_btn = ttk.Button(
            self, text="▼", width=3, bootstyle="secondary-outline",
            command=self._toggle_popup
        )
        self.drop_btn.pack(side=tk.LEFT, padx=(0, 4))
        ToolTip(self.drop_btn, text="Click to browse all ledger accounts")

        # ➕ New Account button
        self.new_btn = ttk.Button(
            self, text="➕ New", bootstyle="info-outline", width=6,
            command=self._open_create_account_modal
        )
        self.new_btn.pack(side=tk.LEFT)
        ToolTip(self.new_btn, text="Create a new ledger account in Chart of Accounts (Ctrl+N)")

        # Bindings on entry
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Tab>", self._on_tab)
        self.entry.bind("<Escape>", lambda e: self._close_popup())
        self.entry.bind("<FocusOut>", self._on_focus_out)
        ToolTip(self.entry, text="Type account code (e.g. 5210) or name to auto-filter accounts")

    def reload_accounts(self, select_id=None):
        """Fetch active chart of accounts and update internal mappings."""
        raw_accounts = db.get_chart_of_accounts(company_id=self.company_id, active_only=True)
        if self.allowed_types:
            self._accounts = [a for a in raw_accounts if a.get("account_type") in self.allowed_types]
        else:
            # Sort with preferred default type first
            self._accounts = sorted(
                raw_accounts,
                key=lambda a: (0 if a.get("account_type") == self.default_account_type else 1, a.get("account_code", ""))
            )

        self._id_map = {}
        for a in self._accounts:
            lbl = f"[{a['account_code']}] {a['account_name']} ({a['account_type']})"
            self._id_map[a["id"]] = (lbl, a)

        if select_id is not None:
            self.set_account_id(select_id)
        elif self._selected_account_id is not None:
            self.set_account_id(self._selected_account_id)
        elif self.include_unlinked and not self.entry_var.get():
            self.entry_var.set("-- Auto-match / Unlinked --")

    def set_account_id(self, account_id):
        """Programmatically set selected account by ID."""
        self._selected_account_id = account_id
        if account_id and account_id in self._id_map:
            lbl, _ = self._id_map[account_id]
            self.entry_var.set(lbl)
        else:
            self._selected_account_id = None
            if self.include_unlinked:
                self.entry_var.set("-- Auto-match / Unlinked --")
            else:
                self.entry_var.set("")

    def get_account_id(self):
        """Resolve and return the integer account ID (or None)."""
        text = self.entry_var.get().strip()
        if not text or "auto-match" in text.lower() or "unlinked" in text.lower():
            return None

        # Check if selected ID matches text
        if self._selected_account_id and self._selected_account_id in self._id_map:
            lbl, _ = self._id_map[self._selected_account_id]
            if lbl == text:
                return self._selected_account_id

        # Match by exact code in bracket or start
        for aid, (lbl, a) in self._id_map.items():
            code = a.get("account_code", "")
            if text == code or text == f"[{code}]" or lbl.startswith(f"[{text}]") or text == lbl:
                self._selected_account_id = aid
                return aid

        # Match by substring
        text_lower = text.lower()
        for aid, (lbl, a) in self._id_map.items():
            if text_lower in lbl.lower() or text_lower in a.get("account_name", "").lower():
                self._selected_account_id = aid
                return aid

        return self._selected_account_id

    def get_text(self):
        return self.entry_var.get().strip()

    def _on_key_release(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab", "Shift_L", "Shift_R",
                            "Control_L", "Control_R", "Alt_L", "Alt_R", "Next", "Prior"):
            return

        typed = self.entry_var.get().strip().lower()
        self._filter_and_show_popup(typed)

    def _filter_and_show_popup(self, query=""):
        items = []
        if self.include_unlinked:
            items.append({
                "id": None,
                "display": "⚪ -- Auto-match / Unlinked --",
                "raw_label": "-- Auto-match / Unlinked --",
                "is_action": False
            })

        for a in self._accounts:
            code = a.get("account_code", "")
            name = a.get("account_name", "")
            atype = a.get("account_type", "")
            subcat = a.get("sub_category", "") or ""
            disp = f"[{code}] {name} ({atype})"
            
            if not query or query in code.lower() or query in name.lower() or query in atype.lower() or query in subcat.lower():
                items.append({
                    "id": a["id"],
                    "display": f"📊 [{code}] {name}  [{atype}]",
                    "raw_label": disp,
                    "is_action": False
                })

        # Add create new option
        items.append({
            "id": "NEW",
            "display": "➕ [+ Create New Ledger Account...]",
            "raw_label": "+ Create New Ledger Account...",
            "is_action": True
        })

        self._show_popup(items)

    def _toggle_popup(self):
        if self._popup_window and self._popup_window.winfo_exists():
            self._close_popup()
        else:
            self._filter_and_show_popup("")
            self.entry.focus_set()

    def _show_popup(self, items):
        self._close_popup()
        if not items:
            return

        self._popup_items = items
        self._popup_window = tk.Toplevel(self)
        self._popup_window.wm_overrideredirect(True)
        self._popup_window.attributes("-topmost", True)

        container = tk.Frame(self._popup_window, bg="#0f172a", bd=1, relief="solid")
        container.pack(fill=tk.BOTH, expand=True)

        hint_frame = tk.Frame(container, bg="#1e293b", padx=6, pady=3)
        hint_frame.pack(fill=tk.X)
        tk.Label(
            hint_frame,
            text="📒 Select Ledger Account (↑↓ Navigate • Enter/Click to Pick)",
            bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 8, "bold"), anchor="w"
        ).pack(side=tk.LEFT)

        body_frame = tk.Frame(container, bg="#0f172a")
        body_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(body_frame, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            body_frame,
            height=min(len(items), 9),
            font=("Segoe UI", 9),
            selectbackground="#2563eb",
            selectforeground="white",
            bg="#0f172a",
            fg="#f8fafc",
            bd=0,
            highlightthickness=0,
            exportselection=False,
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=self._listbox.yview)

        if len(items) > 9:
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for item in items:
            self._listbox.insert(tk.END, f"  {item['display']}")

        # Select first match
        self._listbox.select_set(0)
        self._listbox.activate(0)

        # Position popup directly under entry
        self.update_idletasks()
        try:
            rx = self.entry.winfo_rootx()
            ry = self.entry.winfo_rooty()
            eh = self.entry.winfo_height()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
        except Exception:
            rx, ry, eh, sw, sh = 100, 100, 24, 1200, 800

        w = max(self.winfo_width(), 420)
        h = min(len(items), 9) * 22 + 28
        y = ry + eh + 2
        if y + h > sh - 40:
            y = max(10, ry - h - 2)

        self._popup_window.geometry(f"{w}x{h}+{rx}+{y}")

        self._listbox.bind("<ButtonRelease-1>", lambda e: self._on_select_item())
        self._listbox.bind("<Return>", lambda e: self._on_select_item())
        self._listbox.bind("<Tab>", lambda e: (self._on_select_item(), "break")[1])
        self._listbox.bind("<Escape>", lambda e: (self._close_popup(), self.entry.focus_set(), "break")[2])

    def _on_select_item(self):
        if not self._listbox or not self._listbox.curselection():
            return
        idx = self._listbox.curselection()[0]
        if idx >= len(self._popup_items):
            return

        item = self._popup_items[idx]
        self._close_popup()

        if item.get("is_action") and item["id"] == "NEW":
            self._open_create_account_modal()
            return

        aid = item["id"]
        raw = item.get("raw_label", item["display"])
        self._selected_account_id = aid
        self.entry_var.set(raw)

        if self.on_account_changed:
            self.on_account_changed(aid)

        self.entry.focus_set()

    def _on_arrow_down(self, event):
        if self._popup_window and self._popup_window.winfo_exists() and self._listbox:
            curr = self._listbox.curselection()
            idx = (curr[0] + 1) if curr else 0
            if idx < self._listbox.size():
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(idx)
                self._listbox.activate(idx)
                self._listbox.see(idx)
            return "break"
        else:
            self._filter_and_show_popup("")
            return "break"

    def _on_arrow_up(self, event):
        if self._popup_window and self._popup_window.winfo_exists() and self._listbox:
            curr = self._listbox.curselection()
            idx = (curr[0] - 1) if curr else 0
            if idx >= 0:
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(idx)
                self._listbox.activate(idx)
                self._listbox.see(idx)
            return "break"

    def _on_return(self, event):
        if self._popup_window and self._popup_window.winfo_exists() and self._listbox:
            self._on_select_item()
            return "break"
        return None

    def _on_tab(self, event):
        if self._popup_window and self._popup_window.winfo_exists() and self._listbox:
            self._on_select_item()
            return "break"
        return None

    def _on_focus_out(self, event):
        # Allow click inside popup without immediate dismiss
        self.after(200, self._check_focus_out)

    def _check_focus_out(self):
        try:
            focused = self.focus_get()
            if self._popup_window and self._popup_window.winfo_exists():
                if focused == self._listbox or focused == self.entry or focused == self.drop_btn:
                    return
            self._close_popup()
        except Exception:
            self._close_popup()

    def _close_popup(self):
        if self._popup_window and self._popup_window.winfo_exists():
            try:
                self._popup_window.destroy()
            except Exception:
                pass
        self._popup_window = None
        self._listbox = None

    def _open_create_account_modal(self):
        self._close_popup()
        from ui.coa_dialog import AccountEditModal
        AccountEditModal(
            self.winfo_toplevel(),
            company_id=self.company_id,
            account_data={"account_type": self.default_account_type},
            on_saved=self._on_account_created
        )

    def _on_account_created(self, account_id=None):
        self.reload_accounts(select_id=account_id)
        if account_id and self.on_account_changed:
            self.on_account_changed(account_id)
        self.entry.focus_set()
