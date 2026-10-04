"""
Tag Manager Dialog
Allows users to create, edit, color-code, and delete custom voucher tags & expense labels.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import messagebox, colorchooser

import database as db

TAG_PALETTE = [
    ("#16a34a", "Green"),
    ("#dc2626", "Red"),
    ("#2563eb", "Blue"),
    ("#9333ea", "Purple"),
    ("#d97706", "Orange"),
    ("#0891b2", "Cyan"),
    ("#475569", "Slate"),
    ("#db2777", "Pink"),
]


class TagManagerDialog(tk.Toplevel):
    """Modal dialog for managing voucher tags and labels."""

    def __init__(self, parent, on_tags_changed_callback=None):
        super().__init__(parent)
        self.title("🏷️ Tag & Label Manager")
        self.resizable(True, True)
        self.geometry("540x500")
        self.transient(parent)
        self.grab_set()

        self.on_tags_changed_callback = on_tags_changed_callback

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
        self.bind("<Delete>", lambda e: self._delete())

    def _build_ui(self):
        # ── Title bar ──────────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(12, 10, 12, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="🏷️ Voucher Tag & Label Manager",
            font=("Segoe UI", 13, "bold"), bootstyle="primary"
        ).pack(side=tk.LEFT)

        hint = ttk.Label(header, text="Ins=Add  F2=Edit  Del=Delete", font=("Segoe UI", 8), bootstyle="secondary")
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
        ToolTip(self._search_entry, text="Filter tags by name")

        # ── Treeview ───────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self, padding=(12, 0, 12, 6))
        tree_frame.pack(fill=tk.BOTH, expand=True)

        cols = ("name", "color", "usage")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=14, selectmode="browse")
        self._tree.heading("name", text="Tag / Label Name")
        self._tree.heading("color", text="Color Code")
        self._tree.heading("usage", text="Vouchers Tagged")
        self._tree.column("name", width=250, anchor="w")
        self._tree.column("color", width=110, anchor="center")
        self._tree.column("usage", width=110, anchor="center")

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.LEFT, fill=tk.Y)

        self._tree.bind("<Double-1>", lambda e: self._edit())
        self._tree.bind("<Return>", lambda e: self._edit())
        self._tree.bind("<KP_Enter>", lambda e: self._edit())
        self._tree.bind("<<TreeviewSelect>>", lambda e: self._update_button_states())

        # ── Action buttons ─────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(12, 4, 12, 12))
        btn_frame.pack(fill=tk.X)

        self._add_btn = ttk.Button(btn_frame, text="➕ Add Tag (Ins)", command=self._add, bootstyle="success")
        self._add_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._add_btn, text="Create new tag (Insert)")

        self._edit_btn = ttk.Button(btn_frame, text="✏️ Edit (F2)", command=self._edit, bootstyle="primary", state=tk.DISABLED)
        self._edit_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._edit_btn, text="Edit tag name or color (F2)")

        self._del_btn = ttk.Button(btn_frame, text="🗑️ Delete (Del)", command=self._delete, bootstyle="danger-outline", state=tk.DISABLED)
        self._del_btn.pack(side=tk.LEFT, padx=3)
        ToolTip(self._del_btn, text="Delete selected tag (Delete)")

        self._close_btn = ttk.Button(btn_frame, text="Close (Esc)", command=self.destroy, bootstyle="secondary")
        self._close_btn.pack(side=tk.RIGHT, padx=3)
        ToolTip(self._close_btn, text="Close dialog (Escape)")

    def _update_button_states(self):
        """Enable Edit/Delete buttons when a tag row is selected."""
        state = tk.NORMAL if self._tree.selection() else tk.DISABLED
        if hasattr(self, "_edit_btn") and self._edit_btn:
            self._edit_btn.config(state=state)
        if hasattr(self, "_del_btn") and self._del_btn:
            self._del_btn.config(state=state)

    def _refresh(self):
        """Reload tags from DB and populate treeview."""
        query = self._search_var.get().lower().strip()
        self._tree.delete(*self._tree.get_children())
        rows = db.get_all_tags_full()
        for row in rows:
            if query and query not in row["name"].lower():
                continue
            self._tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row["name"], row["color"], row["usage_count"])
            )
        self._update_button_states()
        if self.on_tags_changed_callback:
            try:
                self.on_tags_changed_callback()
            except Exception:
                pass

    def _get_selected_tag(self):
        sel = self._tree.selection()
        if not sel:
            return None, None, None
        tag_id = int(sel[0])
        vals = self._tree.item(sel[0])["values"]
        return tag_id, str(vals[0]), str(vals[1])

    def _add(self):
        _TagInputDialog(self, title="Add New Tag", prompt="Enter tag name:", on_save=self._do_add)

    def _do_add(self, name, color):
        if not name.strip():
            return
        result = db.add_tag(name.strip(), color=color)
        if result is None:
            messagebox.showwarning("Duplicate Tag", f"Tag '{name}' already exists.", parent=self)
        else:
            self._refresh()

    def _edit(self):
        tag_id, current_name, current_color = self._get_selected_tag()
        if tag_id is None:
            return
        _TagInputDialog(
            self, title="Edit Tag", prompt="Rename tag or update color:",
            initial_name=current_name, initial_color=current_color,
            on_save=lambda n, c: self._do_edit(tag_id, n, c)
        )

    def _do_edit(self, tag_id, new_name, new_color):
        if not new_name.strip():
            return
        ok = db.update_tag(tag_id, new_name.strip(), color=new_color)
        if not ok:
            messagebox.showwarning("Duplicate Tag", f"Tag '{new_name}' already exists.", parent=self)
        self._refresh()

    def _delete(self):
        tag_id, name, _ = self._get_selected_tag()
        if tag_id is None:
            return
        if messagebox.askyesno("Confirm Delete", f"Delete tag '{name}'?\nThis will remove the tag from all associated vouchers.", parent=self):
            db.delete_tag(tag_id)
            self._refresh()


class _TagInputDialog(tk.Toplevel):
    """Modal input dialog for tag name and color selection."""

    def __init__(self, parent, title, prompt, on_save, initial_name="", initial_color="#3b82f6"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._color_var = tk.StringVar(value=initial_color)

        ttk.Label(self, text=prompt, padding=(12, 10, 12, 4), font=("Segoe UI", 9, "bold")).pack(fill=tk.X)

        self._name_var = tk.StringVar(value=initial_name)
        entry = ttk.Entry(self, textvariable=self._name_var, width=36)
        entry.pack(padx=12, pady=4, fill=tk.X)
        entry.select_range(0, tk.END)
        entry.focus_set()

        # Color selection row
        color_frame = ttk.Frame(self, padding=(12, 6, 12, 6))
        color_frame.pack(fill=tk.X)

        ttk.Label(color_frame, text="Tag Color:").pack(side=tk.LEFT, padx=(0, 6))

        self._preview_lbl = tk.Label(
            color_frame, text="  Tag Badge Preview  ",
            bg=self._color_var.get(), fg="#ffffff",
            font=("Segoe UI", 9, "bold"), padx=6, pady=2
        )
        self._preview_lbl.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            color_frame, text="🎨 Custom...", command=self._pick_custom_color,
            bootstyle="secondary-outline"
        ).pack(side=tk.LEFT)

        # Quick palette row
        pal_frame = ttk.Frame(self, padding=(12, 0, 12, 8))
        pal_frame.pack(fill=tk.X)
        ttk.Label(pal_frame, text="Palette:", font=("Segoe UI", 8), bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 4))

        for hex_code, name in TAG_PALETTE:
            btn = tk.Button(
                pal_frame, bg=hex_code, width=2, height=1, relief=tk.FLAT, bd=1,
                command=lambda c=hex_code: self._set_color(c)
            )
            btn.pack(side=tk.LEFT, padx=2)
            ToolTip(btn, text=name)

        btn_frame = ttk.Frame(self, padding=(12, 6, 12, 12))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Save Tag", bootstyle="success",
                   command=lambda: self._save(on_save)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Cancel", bootstyle="secondary",
                   command=self.destroy).pack(side=tk.LEFT)

        self.bind("<Return>", lambda e: self._save(on_save))
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _set_color(self, hex_code):
        self._color_var.set(hex_code)
        self._preview_lbl.config(bg=hex_code)

    def _pick_custom_color(self):
        res = colorchooser.askcolor(color=self._color_var.get(), parent=self, title="Choose Tag Color")
        if res and res[1]:
            self._set_color(res[1])

    def _save(self, on_save):
        on_save(self._name_var.get(), self._color_var.get())
        self.destroy()
