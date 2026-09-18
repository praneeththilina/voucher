"""
Reusable custom widgets for the Voucher Printing Tool.
- AutocompleteEntry: Text entry with dropdown suggestions
- LineItemFrame: Dynamic table for adding/removing expense line items
- MemoPanel: Scrollable memo history with add capability
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


from datetime import datetime, timedelta, date
import calendar
from ttkbootstrap.widgets import DateEntry


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
        kwargs.setdefault("dateformat", "%Y-%m-%d")
        kwargs.setdefault("startdate", date.today())
        kwargs.setdefault("width", 11)
        super().__init__(master, **kwargs)

        # Ensure initial value is cleanly formatted YYYY-MM-DD
        cur = self.entry.get().strip()
        if len(cur) > 10:
            self.set_date(cur[:10])

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
                            "Control_L", "Control_R", "Alt_L", "Alt_R"):
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
        if not typed:
            self._close_listbox()
            return

        suggestions = self._suggestions_callback()
        matches = [s for s in suggestions if typed.lower() in s.lower()]
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

    # ── Normal autocomplete popup ──────────────────────────────────────────

    def _show_listbox(self, items):
        """Show a simple string list popup."""
        self._close_listbox()
        self._listbox_window = tk.Toplevel(self)
        self._listbox_window.wm_overrideredirect(True)
        self._listbox_window.attributes("-topmost", True)

        self._listbox = tk.Listbox(
            self._listbox_window,
            height=min(len(items), 8),
            font=("Segoe UI", 9),
            selectbackground="#3b82f6",
            selectforeground="white",
            exportselection=False,
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)
        for item in items:
            self._listbox.insert(tk.END, item)

        if items:
            self._listbox.select_set(0)
            self._listbox.activate(0)

        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        w = max(self.winfo_width(), 200)
        self._listbox_window.geometry(f"{w}x{min(len(items), 8) * 22}+{x}+{y}")

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
        """Normal autocomplete select."""
        if self._listbox and self._listbox.curselection():
            selected = self._listbox.get(self._listbox.curselection())
            self.delete(0, tk.END)
            self.insert(0, selected)
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
            try:
                focused = self.focus_get()
                if self._listbox and focused == self._listbox:
                    return
                if self._listbox_window and focused == self._listbox_window:
                    return
            except Exception:
                pass
            self._close_listbox()
        self.after(200, _check_and_close)

    def _close_listbox(self, event=None):
        self._at_mode = False
        if self._listbox_window:
            try:
                self._listbox_window.destroy()
            except Exception:
                pass
            self._listbox_window = None
            self._listbox = None


class LineItemFrame(ttk.LabelFrame):
    """
    A dynamic frame for managing multiple line items (expense lines).
    Each row has: Description, Category (autocomplete), Amount, and a remove button.
    """

    def __init__(self, master, categories_callback=None, at_trigger_callback=None, **kwargs):
        super().__init__(master, text="Expense Line Items", padding=4, **kwargs)
        self._categories_callback = categories_callback or (lambda: [])
        self._at_callback = at_trigger_callback  # callback -> [(label, type_hint), ...]
        self._rows = []

        # Header row with light soft slate background
        header = tk.Frame(self, bg="#e2e8f0", padx=4, pady=3)
        header.pack(fill=tk.X, pady=(0, 3))

        tk.Label(header, text="#", width=3, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#334155", anchor="center").pack(side=tk.LEFT, padx=2)
        tk.Label(header, text="Description", font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#334155", anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        tk.Label(header, text="📁 Category (Suggestions / @)", width=24, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#166534", anchor="w").pack(side=tk.LEFT, padx=2)
        tk.Label(header, text="💵 Amount", width=16, font=("Segoe UI", 9, "bold"), bg="#e2e8f0", fg="#854d0e", anchor="w").pack(side=tk.LEFT, padx=2)
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
        self._add_btn.pack(side=tk.LEFT)

        ttk.Label(
            btn_frame, text="(Press Enter in Amount to add next row)",
            font=("Segoe UI", 8), foreground="#6c757d"
        ).pack(side=tk.LEFT, padx=10)

        # Styled Total badge with soft green tint
        total_badge = tk.Frame(btn_frame, bg="#dcfce7", padx=8, pady=2, highlightbackground="#86efac", highlightthickness=1)
        total_badge.pack(side=tk.RIGHT, padx=6)
        self._total_var = tk.StringVar(value="Total: 0.00")
        tk.Label(
            total_badge, textvariable=self._total_var,
            font=("Segoe UI", 12, "bold"), bg="#dcfce7", fg="#15803d"
        ).pack()

        # Start with one empty row
        self.add_row()

    def add_row(self, description="", category="", amount="", focus_desc=False):
        """Add a new line item row."""
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

        cat_entry = AutocompleteEntry(
            row_frame,
            suggestions_callback=self._categories_callback,
            at_trigger_callback=self._at_callback,
            style="Category.TEntry",
            width=24
        )
        cat_entry.pack(side=tk.LEFT, padx=2)
        if category:
            cat_entry.insert(0, category)

        amt_entry = ttk.Entry(row_frame, width=16, style="Amount.TEntry")
        amt_entry.pack(side=tk.LEFT, padx=2)
        if amount:
            amt_entry.insert(0, str(amount))
        amt_entry.bind("<KeyRelease>", lambda e: self._update_total())
        amt_entry.bind("<Return>", lambda e: self._on_enter_amt())

        remove_btn = ttk.Button(
            row_frame, text="✕", width=3,
            command=lambda: self._remove_row(row_frame),
            bootstyle="danger-outline"
        )
        remove_btn.pack(side=tk.LEFT, padx=2)

        row_data = {
            "frame": row_frame,
            "num_label": num_label,
            "description": desc_entry,
            "category": cat_entry,
            "amount": amt_entry,
            "remove_btn": remove_btn,
        }
        self._rows.append(row_data)
        self._renumber_rows()

        if focus_desc:
            desc_entry.focus_set()

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
        self._update_total()

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
        self._total_var.set(f"Total: {total:,.2f}")

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
        """Clear all rows and add one empty row."""
        for row in self._rows:
            row["frame"].destroy()
        self._rows = []
        self._total_var.set("Total: 0.00")
        self.add_row()

    def set_items(self, items):
        """Populate with existing line items."""
        self.clear()
        # Remove the default empty row
        if self._rows:
            self._rows[0]["frame"].destroy()
            self._rows = []

        for item in items:
            self.add_row(
                description=item.get("description", ""),
                category=item.get("category", ""),
                amount=item.get("amount", ""),
            )
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

        self._memo_entry = ttk.Entry(add_frame, style="Party.TEntry")
        self._memo_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._memo_entry.bind("<Return>", lambda e: self._add_memo())

        add_btn = ttk.Button(add_frame, text="+ Add", command=self._add_memo, bootstyle="info-outline")
        add_btn.pack(side=tk.LEFT)

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
