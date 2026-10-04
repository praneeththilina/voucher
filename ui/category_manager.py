"""
Category Manager Dialog
Allows users to add, rename, and toggle active/inactive status for expense categories.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox, filedialog
from datetime import datetime

import database as db


class CategoryManagerDialog(tk.Toplevel):
    """Modal dialog for managing expense categories."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("📁 Category Manager")
        self.resizable(True, True)
        self.geometry("640x500")
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.focus_force()
        self.after(50, lambda: self._search_entry.focus_set())

        # Keyboard shortcuts
        def _close(e=None):
            self.destroy()
            return "break"

        self.bind("<Escape>", _close)
        self.bind("<Insert>", lambda e: self._add())
        self.bind("<F2>", lambda e: self._edit())
        self.bind("<F3>", lambda e: self._set_budget())

    def _build_ui(self):
        # ── Title bar ──────────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(12, 10, 12, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="Expense Category Manager",
            font=("Segoe UI", 13, "bold"), bootstyle="primary"
        ).pack(side=tk.LEFT)

        hint = ttk.Label(header, text="Ins=Add  F2=Edit  F3=Budget  Space=Toggle", font=("Segoe UI", 8), bootstyle="secondary")
        hint.pack(side=tk.RIGHT, padx=4)

        # ── Search bar ─────────────────────────────────────────────────────
        search_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:", bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=28)
        self._search_entry.pack(side=tk.LEFT)
        self._search_entry.bind("<Escape>", lambda e: (self.destroy(), "break")[1])
        ToolTip(self._search_entry, text="Filter expense categories by name")

        # ── Treeview ───────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "budget", "usage", "status")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14, selectmode="browse")
        self._tree.heading("name", text="Category Name")
        self._tree.heading("budget", text="Monthly Budget (LKR)")
        self._tree.heading("usage", text="Uses")
        self._tree.heading("status", text="Status")
        self._tree.column("name", width=220, anchor="w")
        self._tree.column("budget", width=150, anchor="e")
        self._tree.column("usage", width=55, anchor="center")
        self._tree.column("status", width=85, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<space>", lambda e: self._toggle())
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._update_button_states())
        self._tree.tag_configure("inactive", foreground="#888888")
        self._tree.tag_configure("over_budget", foreground="#dc2626")
        self._tree.tag_configure("near_limit", foreground="#d97706")

        # ── Action buttons ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_frame.pack(fill=tk.X)

        self._add_btn = ttk.Button(btn_frame, text="➕ Add (Ins)", command=self._add, bootstyle="success")
        self._add_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._add_btn, text="Add new category (Insert)")

        self._edit_btn = ttk.Button(btn_frame, text="✏️ Edit (F2)", command=self._edit, bootstyle="primary", state=tk.DISABLED)
        self._edit_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._edit_btn, text="Rename selected category (F2)")

        self._budget_btn = ttk.Button(btn_frame, text="💰 Set Budget (F3)", command=self._set_budget, bootstyle="info-outline", state=tk.DISABLED)
        self._budget_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._budget_btn, text="Set or update monthly expense budget limit (F3)")

        self._toggle_btn = ttk.Button(btn_frame, text="🔄 Toggle Active (Space)", command=self._toggle, bootstyle="warning-outline", state=tk.DISABLED)
        self._toggle_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._toggle_btn, text="Toggle selected category active/inactive (Space)")

        self._export_btn = ttk.Button(btn_frame, text="📥 Export CSV", command=self._export_csv, bootstyle="secondary-outline")
        self._export_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._export_btn, text="Export category directory and budget report to CSV file")

        self._close_btn = ttk.Button(btn_frame, text="Close (Esc)", command=self.destroy, bootstyle="secondary")
        self._close_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(self._close_btn, text="Close dialog (Escape)")

    def _update_button_states(self):
        """Enable Edit/Budget/Toggle buttons only when a row is selected in the Treeview."""
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        if hasattr(self, "_edit_btn") and self._edit_btn:
            self._edit_btn.config(state=state)
        if hasattr(self, "_budget_btn") and self._budget_btn:
            self._budget_btn.config(state=state)
        if hasattr(self, "_toggle_btn") and self._toggle_btn:
            self._toggle_btn.config(state=state)

    def _refresh(self):
        """Reload data from DB and repopulate tree."""
        query = self._search_var.get().lower().strip()
        self._tree.delete(*self._tree.get_children())
        rows = db.get_all_categories_full()

        # Get budget status for current month to identify over-budget / near-limit categories
        budget_map = {b["id"]: b for b in db.get_category_budgets()}

        for row in rows:
            if query and query not in row["name"].lower():
                continue
            status = "✅ Active" if row["is_active"] else "⛔ Inactive"
            b_val = float(row.get("monthly_budget") or 0.0)
            b_str = f"LKR {b_val:,.2f}" if b_val > 0 else "—"

            tags = []
            if not row["is_active"]:
                tags.append("inactive")
            else:
                b_info = budget_map.get(row["id"])
                if b_info and b_val > 0:
                    if b_info.get("status_badge") == "🔴 Over Budget":
                        tags.append("over_budget")
                        b_str += " ⚠️"
                    elif b_info.get("status_badge") == "🟠 Near Limit":
                        tags.append("near_limit")

            self._tree.insert("", "end", iid=str(row["id"]),
                              values=(row["name"], b_str, row["usage_count"], status), tags=tuple(tags))
        self._update_button_states()

    def _get_selected_id(self):
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        _NameInputDialog(self, title="Add Category", prompt="Enter new category name:", on_save=self._do_add)

    def _do_add(self, name):
        if not name.strip():
            return
        result = db.add_category(name.strip())
        if result is None:
            messagebox.showwarning("Duplicate", f"Category '{name}' already exists.", parent=self)
        else:
            self._refresh()

    def _edit(self):
        cat_id = self._get_selected_id()
        if cat_id is None:
            return
        row = self._tree.item(str(cat_id))["values"]
        current_name = row[0]
        _NameInputDialog(self, title="Edit Category", prompt="Rename category:", initial=current_name,
                         on_save=lambda n: self._do_edit(cat_id, n))

    def _do_edit(self, cat_id, new_name):
        if not new_name.strip():
            return
        ok = db.update_category(cat_id, new_name.strip())
        if not ok:
            messagebox.showwarning("Duplicate", f"Category '{new_name}' already exists.", parent=self)
        self._refresh()

    def _set_budget(self):
        cat_id = self._get_selected_id()
        if cat_id is None:
            return
        row_vals = self._tree.item(str(cat_id))["values"]
        c_name = row_vals[0]
        curr_b_str = row_vals[1]

        full_row = next((r for r in db.get_all_categories_full() if r["id"] == cat_id), None)
        curr_budget = full_row["monthly_budget"] if full_row else 0.0

        _NameInputDialog(
            self,
            title="Set Category Monthly Budget",
            prompt=f"Enter monthly budget limit for '{c_name}' (LKR):\nSet to 0 to clear budget.",
            initial=str(curr_budget) if curr_budget > 0 else "",
            on_save=lambda val: self._do_set_budget(cat_id, val)
        )

    def _do_set_budget(self, cat_id, val_str):
        clean_val = val_str.strip().replace(",", "")
        if not clean_val:
            b_val = 0.0
        else:
            try:
                b_val = float(clean_val)
                if b_val < 0:
                    messagebox.showwarning("Invalid Budget", "Monthly budget cannot be negative.", parent=self)
                    return
            except ValueError:
                messagebox.showwarning("Invalid Input", "Please enter a valid numeric budget amount.", parent=self)
                return

        db.set_category_budget(cat_id, b_val)
        self._refresh()

    def _toggle(self):
        cat_id = self._get_selected_id()
        if cat_id is None:
            return
        db.toggle_category_active(cat_id)
        self._refresh()

    def _export_csv(self):
        """Prompt for file path and export category directory & budget report to CSV."""
        default_filename = f"category_directory_budget_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Categories & Budget Report to CSV",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            db.export_categories_to_csv(filepath)
            messagebox.showinfo("Export Successful", f"Category report exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export categories:\n{e}", parent=self)


class _NameInputDialog(tk.Toplevel):
    """Simple modal input dialog for a single name value."""

    def __init__(self, parent, title, prompt, on_save, initial=""):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ttk.Label(self, text=prompt, padding=(12, 10, 12, 4)).pack(fill=tk.X)

        self._var = tk.StringVar(value=initial)
        entry = ttk.Entry(self, textvariable=self._var, width=36)
        entry.pack(padx=12, pady=4, fill=tk.X)
        entry.select_range(0, tk.END)
        entry.focus_set()

        btn_frame = ttk.Frame(self, padding=(12, 6, 12, 12))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Save", bootstyle="success",
                   command=lambda: self._save(on_save)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", bootstyle="secondary",
                   command=self.destroy).pack(side=tk.LEFT)

        self.bind("<Return>", lambda e: self._save(on_save))
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _save(self, on_save):
        on_save(self._var.get())
        self.destroy()
