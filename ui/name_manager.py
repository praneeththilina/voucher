"""
Name Manager Dialog
Allows users to add, rename, and toggle active/inactive status for people names.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox

import database as db


class NameManagerDialog(tk.Toplevel):
    """Modal dialog for managing person names and payee directory details."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("👤 Payee & Name Manager")
        self.resizable(True, True)
        self.geometry("640x480")
        self.transient(parent)
        self.grab_set()
        self._people_map = {}

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
        ToolTip(self._search_entry, text="Filter people names")

        # ── Treeview ───────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "default_category", "contact", "tax_id", "status")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15, selectmode="browse")
        self._tree.heading("name", text="Person / Payee Name")
        self._tree.heading("default_category", text="Default Category")
        self._tree.heading("contact", text="Phone / Contact")
        self._tree.heading("tax_id", text="Tax ID / Reg")
        self._tree.heading("status", text="Status")

        self._tree.column("name", width=170, anchor="w")
        self._tree.column("default_category", width=130, anchor="w")
        self._tree.column("contact", width=110, anchor="w")
        self._tree.column("tax_id", width=90, anchor="w")
        self._tree.column("status", width=75, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<space>", lambda e: self._toggle())
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._update_button_states())
        self._tree.tag_configure("inactive", foreground="#888888")

        # ── Buttons ────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_frame.pack(fill=tk.X)

        self._add_btn = ttk.Button(btn_frame, text="➕ Add (Ins)", command=self._add, bootstyle="success")
        self._add_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._add_btn, text="Add new person (Insert)")

        self._edit_btn = ttk.Button(btn_frame, text="✏️ Edit (F2)", command=self._edit, bootstyle="primary", state=tk.DISABLED)
        self._edit_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._edit_btn, text="Rename selected person (F2)")

        self._toggle_btn = ttk.Button(btn_frame, text="🔄 Toggle Active (Space)", command=self._toggle, bootstyle="warning-outline", state=tk.DISABLED)
        self._toggle_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._toggle_btn, text="Toggle selected person active/inactive (Space)")

        self._stmt_btn = ttk.Button(btn_frame, text="📜 Statement", command=self._open_statement, bootstyle="info-outline", state=tk.DISABLED)
        self._stmt_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._stmt_btn, text="View payment statement for selected person")

        self._export_btn = ttk.Button(btn_frame, text="📊 Export CSV", command=self._export_csv, bootstyle="info-outline")
        self._export_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._export_btn, text="Export payee and vendor directory to CSV spreadsheet")

        self._close_btn = ttk.Button(btn_frame, text="Close (Esc)", command=self.destroy, bootstyle="secondary")
        self._close_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(self._close_btn, text="Close dialog (Escape)")

    def _update_button_states(self):
        """Enable Edit/Toggle/Statement buttons only when a row is selected in the Treeview."""
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        if hasattr(self, "_edit_btn") and self._edit_btn:
            self._edit_btn.config(state=state)
        if hasattr(self, "_toggle_btn") and self._toggle_btn:
            self._toggle_btn.config(state=state)
        if hasattr(self, "_stmt_btn") and self._stmt_btn:
            self._stmt_btn.config(state=state)

    def _open_statement(self):
        """Open Payee Statement for selected person."""
        pid = self._get_selected_id()
        if pid is None:
            return
        row = self._tree.item(str(pid))["values"]
        name = row[0]
        from ui.payee_statement import PayeeStatementDialog
        dlg = PayeeStatementDialog(self, initial_payee=name)
        dlg.lift()
        dlg.focus_force()

    def _export_csv(self):
        """Export payee / vendor directory to CSV."""
        from tkinter import filedialog
        from datetime import datetime

        default_filename = f"Payee_Directory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="Export Payee Directory to CSV",
            initialfile=default_filename,
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        try:
            db.export_people_to_csv(filepath)
            messagebox.showinfo(
                "Export Successful",
                f"Payee directory successfully exported to:\n{filepath}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}", parent=self)

    def _refresh(self):
        query = self._search_var.get().lower().strip()
        self._tree.delete(*self._tree.get_children())
        self._people_map = {}
        rows = db.get_all_people_full()
        for row in rows:
            self._people_map[row["id"]] = row
            if query:
                match_name = query in row["name"].lower()
                match_cat = query in (row.get("default_category") or "").lower()
                match_phone = query in (row.get("phone") or "").lower()
                match_tax = query in (row.get("tax_id") or "").lower()
                if not (match_name or match_cat or match_phone or match_tax):
                    continue
            status = "✅ Active" if row["is_active"] else "⛔ Inactive"
            tags = () if row["is_active"] else ("inactive",)
            cat_disp = row.get("default_category") or "—"
            phone_disp = row.get("phone") or "—"
            tax_disp = row.get("tax_id") or "—"
            self._tree.insert("", "end", iid=str(row["id"]),
                              values=(row["name"], cat_disp, phone_disp, tax_disp, status), tags=tags)
        self._update_button_states()

    def _get_selected_id(self):
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    def _add(self):
        _PersonEditorDialog(self, title="Add Payee / Person", on_save=self._do_add)

    def _do_add(self, data):
        name = data.get("name", "").strip()
        if not name:
            return
        result = db.add_person(
            name=name,
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            tax_id=data.get("tax_id", ""),
            default_category=data.get("default_category", ""),
            notes=data.get("notes", "")
        )
        if result is None:
            messagebox.showwarning("Duplicate", f"Person '{name}' already exists.", parent=self)
        else:
            self._refresh()

    def _edit(self):
        pid = self._get_selected_id()
        if pid is None:
            return
        pdata = self._people_map.get(pid)
        if not pdata:
            return
        _PersonEditorDialog(
            self, title="Edit Payee / Person", initial_data=pdata,
            on_save=lambda d: self._do_edit(pid, d)
        )

    def _do_edit(self, pid, data):
        new_name = data.get("name", "").strip()
        if not new_name:
            return
        ok = db.update_person(
            person_id=pid,
            new_name=new_name,
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            tax_id=data.get("tax_id", ""),
            default_category=data.get("default_category", ""),
            notes=data.get("notes", "")
        )
        if not ok:
            messagebox.showwarning("Duplicate", f"Person '{new_name}' already exists.", parent=self)
        self._refresh()

    def _toggle(self):
        pid = self._get_selected_id()
        if pid is None:
            return
        db.toggle_person_active(pid)
        self._refresh()


class _PersonEditorDialog(tk.Toplevel):
    """Modal editor dialog for person/payee contact details and default category."""

    def __init__(self, parent, title, on_save, initial_data=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        init = initial_data or {}
        self._name_var = tk.StringVar(value=init.get("name", ""))
        self._category_var = tk.StringVar(value=init.get("default_category", ""))
        self._phone_var = tk.StringVar(value=init.get("phone", ""))
        self._email_var = tk.StringVar(value=init.get("email", ""))
        self._tax_id_var = tk.StringVar(value=init.get("tax_id", ""))
        self._notes_var = tk.StringVar(value=init.get("notes", ""))

        form = ttk.Frame(self, padding=(16, 14, 16, 12))
        form.pack(fill=tk.BOTH, expand=True)

        # Name Field
        ttk.Label(form, text="Person / Payee Name: *", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 2))
        name_entry = ttk.Entry(form, textvariable=self._name_var, width=38)
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
        name_entry.focus_set()
        name_entry.select_range(0, tk.END)

        # Default Category Combobox
        ttk.Label(form, text="Default Category:").grid(row=1, column=0, sticky="w", pady=(0, 2))
        cats = [""] + db.get_categories(active_only=True)
        cat_combo = ttk.Combobox(form, textvariable=self._category_var, values=cats, width=36)
        cat_combo.grid(row=1, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))
        ToolTip(cat_combo, text="Default expense category auto-filled when creating vouchers for this payee")

        # Phone / Contact Field
        ttk.Label(form, text="Phone / Contact:").grid(row=2, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=self._phone_var, width=38).grid(row=2, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))

        # Email Field
        ttk.Label(form, text="Email Address:").grid(row=3, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=self._email_var, width=38).grid(row=3, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))

        # Tax ID / Reg No
        ttk.Label(form, text="Tax ID / Reg No:").grid(row=4, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=self._tax_id_var, width=38).grid(row=4, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))

        # Notes Field
        ttk.Label(form, text="Notes:").grid(row=5, column=0, sticky="w", pady=(0, 2))
        ttk.Entry(form, textvariable=self._notes_var, width=38).grid(row=5, column=1, sticky="ew", pady=(0, 6), padx=(8, 0))

        # Action Buttons
        btn_frame = ttk.Frame(self, padding=(16, 0, 16, 14))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="💾 Save Details", bootstyle="success",
                   command=lambda: self._save(on_save)).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_frame, text="Cancel", bootstyle="secondary-outline",
                   command=self.destroy).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._save(on_save))
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _save(self, on_save):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Person / Payee Name is required.", parent=self)
            return
        data = {
            "name": name,
            "default_category": self._category_var.get().strip(),
            "phone": self._phone_var.get().strip(),
            "email": self._email_var.get().strip(),
            "tax_id": self._tax_id_var.get().strip(),
            "notes": self._notes_var.get().strip(),
        }
        on_save(data)
        self.destroy()
