"""
Category Manager Dialog
Allows users to add, edit, link to general ledger accounts, configure budgets,
and toggle active/inactive status for expense categories.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox, filedialog
from datetime import datetime

import database as db


class CategoryEditDialog(tk.Toplevel):
    """Modal dialog for creating or editing an expense category with linked ledger account and budget."""

    def __init__(self, parent, company_id=None, cat_data=None, on_saved=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.cat_data = cat_data
        self.on_saved = on_saved
        self.is_edit = cat_data is not None
        self._acct_map = {}
        self._all_combo_vals = []

        title_text = "Edit Category" if self.is_edit else "Add New Category"
        self.title(f"📁 {title_text}")
        self.resizable(False, False)
        self.geometry("560x320")
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._populate_accounts()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-n>", lambda e: self._open_new_account_modal())
        self.bind("<Control-N>", lambda e: self._open_new_account_modal())

    def _build_ui(self):
        container = ttk.Frame(self, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Header note
        ttk.Label(
            container,
            text="Link category to a Chart of Accounts ledger for automated double-entry posting.",
            font=("Segoe UI", 9, "italic"),
            bootstyle="secondary"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        # Category Name
        ttk.Label(container, text="Category Name *:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(container, textvariable=self.name_var, width=38)
        self.name_entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        self.name_entry.focus_set()

        # Linked Ledger Account (Searchable + Filterable + Create Account Button)
        ttk.Label(container, text="Linked Ledger Account:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 8))
        
        acct_box = ttk.Frame(container)
        acct_box.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        self.account_var = tk.StringVar()
        self.account_combo = ttk.Combobox(acct_box, textvariable=self.account_var, width=28)
        self.account_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        
        # Real-time search filter binding on key release
        self.account_combo.bind("<KeyRelease>", self._on_acct_keyrelease)
        self.account_combo.bind("<<ComboboxSelected>>", self._on_acct_selected)
        ToolTip(self.account_combo, text="Type account code or name to search & filter in real-time, or select from dropdown")

        self._new_acct_btn = ttk.Button(
            acct_box, text="➕ New", bootstyle="info-outline", width=6,
            command=self._open_new_account_modal
        )
        self._new_acct_btn.pack(side=tk.LEFT)
        ToolTip(self._new_acct_btn, text="Create a new Chart of Accounts ledger account (Ctrl+N)")

        # Monthly Budget
        ttk.Label(container, text="Monthly Budget (LKR):", font=("Segoe UI", 9)).grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.budget_var = tk.StringVar(value="0.00")
        self.budget_entry = ttk.Entry(container, textvariable=self.budget_var, width=38)
        self.budget_entry.grid(row=3, column=1, sticky="ew", pady=(0, 16))

        # Action Buttons
        btn_box = ttk.Frame(container)
        btn_box.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(btn_box, text="Save", bootstyle="success", command=self._save).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_box, text="Cancel", bootstyle="secondary", command=self.destroy).pack(side=tk.LEFT)

    def _populate_accounts(self, select_account_id=None):
        """Fetch chart of accounts, populate the filterable list and select the target account."""
        accounts = db.get_chart_of_accounts(company_id=self.company_id, active_only=True)
        # Prioritize Expense accounts first, then others
        accounts.sort(key=lambda a: (0 if a.get("account_type") == "Expense" else 1, a.get("account_code", "")))

        self._acct_map = {"-- Auto-match / Unlinked --": None}
        self._all_combo_vals = ["-- Auto-match / Unlinked --", "+ Create New Ledger Account..."]
        
        target_label = None
        
        # Determine which account ID to select
        if select_account_id is not None:
            active_aid = select_account_id
        elif self.cat_data:
            active_aid = self.cat_data.get("account_id")
        else:
            active_aid = None

        for a in accounts:
            lbl = f"[{a['account_code']}] {a['account_name']} ({a['account_type']})"
            self._acct_map[lbl] = a["id"]
            self._all_combo_vals.append(lbl)
            if active_aid and a["id"] == active_aid:
                target_label = lbl

        self.account_combo["values"] = self._all_combo_vals

        if target_label:
            self.account_var.set(target_label)
        elif not self.account_var.get() or self.account_var.get() == "-- Auto-match / Unlinked --":
            self.account_var.set(self._all_combo_vals[0])

        if self.cat_data and select_account_id is None:
            self.name_var.set(self.cat_data.get("name", ""))
            b_val = float(self.cat_data.get("monthly_budget") or 0.0)
            if b_val > 0:
                self.budget_var.set(f"{b_val:.2f}")

    def _on_acct_keyrelease(self, event=None):
        """Live filtering when typing inside the Linked Ledger Account combobox."""
        if event and event.keysym in ("Up", "Down", "Return", "Tab", "Escape", "Left", "Right"):
            return

        typed = self.account_var.get().strip().lower()
        if not typed:
            self.account_combo["values"] = self._all_combo_vals
            return

        filtered = [
            val for val in self._all_combo_vals
            if typed in val.lower() or val.startswith("+ Create")
        ]
        
        if not filtered:
            filtered = ["-- Auto-match / Unlinked --", "+ Create New Ledger Account..."]
            
        self.account_combo["values"] = filtered

    def _on_acct_selected(self, event=None):
        """Handle combobox selection, opening create modal if special item picked."""
        val = self.account_var.get().strip()
        if val == "+ Create New Ledger Account...":
            self.account_var.set("-- Auto-match / Unlinked --")
            self._open_new_account_modal()

    def _open_new_account_modal(self, event=None):
        """Open the Account creation popup modal."""
        from ui.coa_dialog import AccountEditModal
        AccountEditModal(
            self,
            company_id=self.company_id,
            account_data={"account_type": "Expense"},
            on_saved=self._on_account_created
        )

    def _on_account_created(self, new_account_id=None):
        """Callback after new ledger account is saved in the AccountEditModal."""
        self._populate_accounts(select_account_id=new_account_id)
        self.lift()
        self.focus_force()

    def _resolve_account_id(self, text):
        """Resolve account ID from exact label or typed partial text/code."""
        if not text:
            return None
        text_clean = text.strip()
        
        # 1. Exact match in map
        if text_clean in self._acct_map:
            return self._acct_map[text_clean]

        # 2. Check if user typed "-- Auto-match" or "unlinked"
        if "auto-match" in text_clean.lower() or "unlinked" in text_clean.lower():
            return None

        # 3. Match by account code (e.g. '5210' or '[5210]')
        for lbl, aid in self._acct_map.items():
            if aid is None:
                continue
            if f"[{text_clean}]" in lbl or lbl.startswith(f"[{text_clean}"):
                return aid

        # 4. Match by substring in label
        text_lower = text_clean.lower()
        for lbl, aid in self._acct_map.items():
            if aid is not None and text_lower in lbl.lower():
                return aid

        return None

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Category name is required.", parent=self)
            self.name_entry.focus_set()
            return

        acct_label = self.account_var.get()
        acct_id = self._resolve_account_id(acct_label)

        # Budget parsing
        b_clean = self.budget_var.get().strip().replace(",", "")
        b_val = 0.0
        if b_clean:
            try:
                b_val = float(b_clean)
                if b_val < 0:
                    messagebox.showwarning("Validation Error", "Monthly budget cannot be negative.", parent=self)
                    return
            except ValueError:
                messagebox.showwarning("Validation Error", "Please enter a valid numeric budget amount.", parent=self)
                return

        if self.is_edit:
            cat_id = self.cat_data["id"]
            ok = db.update_category(cat_id, new_name=name, account_id=acct_id)
            if not ok:
                messagebox.showwarning("Duplicate", f"Category '{name}' already exists.", parent=self)
                return
            db.set_category_budget(cat_id, b_val)
        else:
            cat_id = db.add_category(name, account_id=acct_id)
            if cat_id is None:
                messagebox.showwarning("Duplicate", f"Category '{name}' already exists.", parent=self)
                return
            if b_val > 0:
                db.set_category_budget(cat_id, b_val)

        if self.on_saved:
            self.on_saved()
        self.destroy()


class CategoryManagerDialog(tk.Toplevel):
    """Modal dialog for managing expense categories."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.company_id = company_id or db.get_active_company_id()
        self.title("📁 Category Manager")
        self.resizable(True, True)
        self.geometry("820x520")
        self.minsize(700, 420)
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

        cols = ("name", "budget", "linked_account", "usage", "status")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14, selectmode="browse")
        self._tree.heading("name", text="Category Name")
        self._tree.heading("budget", text="Monthly Budget (LKR)")
        self._tree.heading("linked_account", text="Linked Ledger Account")
        self._tree.heading("usage", text="Uses")
        self._tree.heading("status", text="Status")
        self._tree.column("name", width=190, anchor="w")
        self._tree.column("budget", width=140, anchor="e")
        self._tree.column("linked_account", width=220, anchor="w")
        self._tree.column("usage", width=55, anchor="center")
        self._tree.column("status", width=85, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<Return>", lambda e: self._edit())
        self._tree.bind("<KP_Enter>", lambda e: self._edit())
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
        ToolTip(self._add_btn, text="Add new category with linked ledger account (Insert)")

        self._edit_btn = ttk.Button(btn_frame, text="✏️ Edit (F2)", command=self._edit, bootstyle="primary", state=tk.DISABLED)
        self._edit_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._edit_btn, text="Edit category name and linked ledger account (F2)")

        self._budget_btn = ttk.Button(btn_frame, text="💰 Set Budget (F3)", command=self._set_budget, bootstyle="info-outline", state=tk.DISABLED)
        self._budget_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._budget_btn, text="Set or update monthly expense budget limit (F3)")

        self._toggle_btn = ttk.Button(btn_frame, text="🔄 Toggle Active (Space)", command=self._toggle, bootstyle="warning-outline", state=tk.DISABLED)
        self._toggle_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._toggle_btn, text="Toggle selected category active/inactive (Space)")

        self._export_btn = ttk.Button(btn_frame, text="📥 Export CSV", command=self._export_csv, bootstyle="secondary-outline")
        self._export_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._export_btn, text="Export category directory and budget report to CSV file")

        self._coa_btn = ttk.Button(btn_frame, text="📒 Chart of Accounts", command=self._open_coa, bootstyle="secondary-outline")
        self._coa_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._coa_btn, text="Open Chart of Accounts manager to view or create ledger accounts")

        self._close_btn = ttk.Button(btn_frame, text="Close (Esc)", command=self.destroy, bootstyle="secondary")
        self._close_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(self._close_btn, text="Close dialog (Escape)")

    def _open_coa(self):
        """Open the Chart of Accounts window."""
        from ui.coa_dialog import ChartOfAccountsDialog
        ChartOfAccountsDialog(self, company_id=self.company_id)

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
        rows = db.get_all_categories_full(company_id=self.company_id)

        # Get budget status for current month to identify over-budget / near-limit categories
        budget_map = {b["id"]: b for b in db.get_category_budgets()}

        for row in rows:
            if query and query not in row["name"].lower():
                continue
            status = "✅ Active" if row["is_active"] else "⛔ Inactive"
            b_val = float(row.get("monthly_budget") or 0.0)
            b_str = f"LKR {b_val:,.2f}" if b_val > 0 else "—"

            if row.get("linked_account_code"):
                linked_str = f"[{row['linked_account_code']}] {row.get('linked_account_name')}"
            else:
                linked_str = "Auto-match (Unlinked)"

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
                              values=(row["name"], b_str, linked_str, row["usage_count"], status), tags=tuple(tags))
        self._update_button_states()

    def _get_selected_id(self):
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        CategoryEditDialog(self, company_id=self.company_id, on_saved=self._refresh)

    def _do_add(self, name):
        """Fallback helper for direct script/test calls."""
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
        rows = db.get_all_categories_full(company_id=self.company_id)
        row_data = next((r for r in rows if r["id"] == cat_id), None)
        if not row_data:
            return
        CategoryEditDialog(self, company_id=self.company_id, cat_data=row_data, on_saved=self._refresh)

    def _do_edit(self, cat_id, new_name):
        """Fallback helper for direct script/test calls."""
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

        full_row = next((r for r in db.get_all_categories_full(company_id=self.company_id) if r["id"] == cat_id), None)
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
            db.export_categories_to_csv(filepath, company_id=self.company_id)
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
