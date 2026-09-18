"""
Name Manager Dialog
Allows users to add, rename, and toggle active/inactive status for people names.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

import database as db


class NameManagerDialog(tk.Toplevel):
    """Modal dialog for managing person names used in vouchers."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("👤 Name Manager")
        self.resizable(True, True)
        self.geometry("460x460")
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

        def _close(e=None):
            self.destroy()
            return "break"

        self.bind("<Escape>", _close)
        self.bind("<Insert>", lambda e: self._add())
        self.bind("<F2>", lambda e: self._edit())

    def _build_ui(self):
        # ── Header ──────────────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(12, 10, 12, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="People / Name Manager",
            font=("Segoe UI", 13, "bold"), bootstyle="info"
        ).pack(side=tk.LEFT)
        ttk.Label(header, text="Ins=Add  F2=Edit  Space=Toggle", font=("Segoe UI", 8), bootstyle="secondary").pack(side=tk.RIGHT)

        # ── Search ─────────────────────────────────────────────────────────
        search_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:", bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh())
        self._search_entry = ttk.Entry(search_frame, textvariable=self._search_var, width=28)
        self._search_entry.pack(side=tk.LEFT)
        self._search_entry.bind("<Escape>", lambda e: (self.destroy(), "break")[1])

        # ── Treeview ───────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "status")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15, selectmode="browse")
        self._tree.heading("name", text="Person Name")
        self._tree.heading("status", text="Status")
        self._tree.column("name", width=300, anchor="w")
        self._tree.column("status", width=90, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<space>", lambda e: self._toggle())
        self._tree.tag_configure("inactive", foreground="#888888")

        # ── Buttons ────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="➕ Add (Ins)", command=self._add, bootstyle="success").pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="✏️ Edit (F2)", command=self._edit, bootstyle="primary").pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="🔄 Toggle Active (Space)", command=self._toggle, bootstyle="warning-outline").pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Close (Esc)", command=self.destroy, bootstyle="secondary").pack(side=tk.RIGHT, padx=3)

    def _refresh(self):
        query = self._search_var.get().lower().strip()
        self._tree.delete(*self._tree.get_children())
        rows = db.get_all_people_full()
        for row in rows:
            if query and query not in row["name"].lower():
                continue
            status = "✅ Active" if row["is_active"] else "⛔ Inactive"
            tags = () if row["is_active"] else ("inactive",)
            self._tree.insert("", "end", iid=str(row["id"]),
                              values=(row["name"], status), tags=tags)

    def _get_selected_id(self):
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        _NameInputDialog(self, title="Add Person", prompt="Enter person name:", on_save=self._do_add)

    def _do_add(self, name):
        if not name.strip():
            return
        result = db.add_person(name.strip())
        if result is None:
            messagebox.showwarning("Duplicate", f"Person '{name}' already exists.", parent=self)
        else:
            self._refresh()

    def _edit(self):
        pid = self._get_selected_id()
        if pid is None:
            return
        row = self._tree.item(str(pid))["values"]
        current_name = row[0]
        _NameInputDialog(self, title="Edit Name", prompt="Update person name:", initial=current_name,
                         on_save=lambda n: self._do_edit(pid, n))

    def _do_edit(self, pid, new_name):
        if not new_name.strip():
            return
        ok = db.update_person(pid, new_name.strip())
        if not ok:
            messagebox.showwarning("Duplicate", f"Person '{new_name}' already exists.", parent=self)
        self._refresh()

    def _toggle(self):
        pid = self._get_selected_id()
        if pid is None:
            return
        db.toggle_person_active(pid)
        self._refresh()


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
