"""
Template Manager Dialog for managing recurring payment voucher templates.
Allows users to create, view, apply, edit, and delete templates per company profile.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

import database as db


class TemplateManagerDialog(tk.Toplevel):
    """Dialog for managing and applying recurring voucher templates."""

    def __init__(self, parent, on_apply_callback=None):
        super().__init__(parent)
        self.title("📝 Recurring Voucher Templates")
        self.geometry("680x480")
        self.minsize(580, 400)
        self.transient(parent)
        self.grab_set()

        self._on_apply_callback = on_apply_callback
        self._selected_template_id = None

        self._build_ui()
        self._refresh_templates()

        # Center on parent
        self.update_idletasks()
        px = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        py = parent.winfo_rooty() + max(0, (parent.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        active_id = db.get_active_company_id()
        comp = db.get_company(active_id) or {}
        comp_name = comp.get("name", f"Company {active_id}")

        # Top Header Banner
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="📝 Recurring Voucher Templates",
            font=("Segoe UI", 12, "bold"), bg="#0f172a", fg="#ffffff"
        ).pack(anchor="w")

        tk.Label(
            header, text=f"Active Profile: {comp_name}  |  Save frequent transactions as reusable templates.",
            font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8"
        ).pack(anchor="w", pady=(2, 0))

        # Main Body Split (Left: Template List | Right: Template Details Preview)
        body = ttk.Frame(self, padding=(12, 10))
        body.pack(fill=tk.BOTH, expand=True)

        # Left Column: List
        left_frame = ttk.LabelFrame(body, text=" Saved Templates ", padding=6)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        self._tree = ttk.Treeview(
            left_frame, columns=("name", "payee", "items"), show="headings", height=12
        )
        self._tree.heading("name", text="Template Name")
        self._tree.heading("payee", text="Paid To")
        self._tree.heading("items", text="Items")

        self._tree.column("name", width=140, anchor="w")
        self._tree.column("payee", width=110, anchor="w")
        self._tree.column("items", width=50, anchor="center")

        tree_sb = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_sb.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_template_selected)
        self._tree.bind("<Double-1>", lambda e: self._apply_template())

        # Right Column: Details Preview
        right_frame = ttk.LabelFrame(body, text=" Template Preview ", padding=8)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        self._preview_text = tk.Text(
            right_frame, wrap=tk.WORD, font=("Segoe UI", 9),
            bg="#f8fafc", fg="#0f172a", relief=tk.FLAT, state="disabled"
        )
        self._preview_text.pack(fill=tk.BOTH, expand=True)

        # Action Buttons Footer
        footer = ttk.Frame(self, padding=(12, 10))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            footer, text="✅ Apply Template",
            command=self._apply_template, bootstyle="success"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            footer, text="🗑️ Delete Template",
            command=self._delete_template, bootstyle="danger-outline"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            footer, text="Close (Esc)",
            command=self.destroy, bootstyle="secondary-outline"
        ).pack(side=tk.RIGHT)

    def _refresh_templates(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

        templates = db.get_templates()
        for t in templates:
            t_data = db.get_template(t["id"])
            item_count = len(t_data["line_items"]) if t_data else 0
            self._tree.insert(
                "", tk.END, iid=str(t["id"]),
                values=(t["template_name"], t.get("paid_to", "—"), item_count)
            )

        self._selected_template_id = None
        self._update_preview(None)

    def _on_template_selected(self, event=None):
        sel = self._tree.selection()
        if not sel:
            self._selected_template_id = None
            self._update_preview(None)
            return

        tmpl_id = int(sel[0])
        self._selected_template_id = tmpl_id
        t_data = db.get_template(tmpl_id)
        self._update_preview(t_data)

    def _update_preview(self, template_data):
        self._preview_text.config(state="normal")
        self._preview_text.delete("1.0", tk.END)

        if not template_data:
            self._preview_text.insert("1.0", "Select a template to view details.")
            self._preview_text.config(state="disabled")
            return

        t = template_data["template"]
        items = template_data["line_items"]

        lines = [
            f"📋 Template Name: {t['template_name']}",
            f"👤 Paid To: {t.get('paid_to') or '—'}",
            f"💵 Cash Given By: {t.get('cash_given_by') or '—'}",
            f"💳 Payment Method: {t.get('payment_method') or 'Cash'}",
            f"📂 Bill Status: {t.get('bill_status') or 'Pending'}",
            f"✍️ Prepared By: {t.get('prepared_by') or '—'}",
            f"✔️ Approved By: {t.get('approved_by') or '—'}",
            "\n--- Line Items ---"
        ]

        total = 0.0
        for i, item in enumerate(items, 1):
            amt = item.get("amount", 0)
            total += amt
            cat_str = f" [{item['category']}]" if item.get("category") else ""
            lines.append(f"{i}. {item['description']}{cat_str}: LKR {amt:,.2f}")

        lines.append(f"\n💰 Total Template Amount: LKR {total:,.2f}")

        self._preview_text.insert("1.0", "\n".join(lines))
        self._preview_text.config(state="disabled")

    def _apply_template(self):
        if not self._selected_template_id:
            messagebox.showinfo("No Selection", "Please select a template to apply.", parent=self)
            return

        t_data = db.get_template(self._selected_template_id)
        if t_data and self._on_apply_callback:
            self.destroy()
            self._on_apply_callback(t_data)

    def _delete_template(self):
        if not self._selected_template_id:
            messagebox.showinfo("No Selection", "Please select a template to delete.", parent=self)
            return

        t_data = db.get_template(self._selected_template_id)
        if not t_data:
            return

        t_name = t_data["template"]["template_name"]
        if messagebox.askyesno(
            "Delete Template",
            f"Are you sure you want to delete template '{t_name}'?",
            parent=self, icon="warning"
        ):
            db.delete_template(self._selected_template_id)
            self._refresh_templates()
