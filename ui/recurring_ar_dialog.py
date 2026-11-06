"""UI Dialog for managing Recurring AR Invoice Schedules."""

import os
import tkinter as tk
from tkinter import messagebox, filedialog
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
import sales_database as sdb
from ui.widgets import ToolTip


class RecurringAREditModal(tb.Toplevel):
    """Modal for creating or editing a recurring AR invoice schedule."""

    def __init__(self, parent, schedule=None, on_save_callback=None):
        super().__init__(parent)
        self.title("Edit Recurring AR Schedule" if schedule else "New Recurring AR Schedule")
        self.geometry("750x600")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.schedule = schedule
        self.on_save_callback = on_save_callback
        self.company_id = db.get_active_company_id()

        self._load_master_data()
        self._build_ui()
        if self.schedule:
            self._populate_fields()

    def _load_master_data(self):
        self.customers = db.get_customers(self.company_id, active_only=True)
        self.customer_names = [f"{c['name']} (ID: {c['id']})" for c in self.customers]
        self.customer_map = {f"{c['name']} (ID: {c['id']})": c['id'] for c in self.customers}

        self.items = sdb.get_sales_items(self.company_id, active_only=True)
        self.item_names = [f"{i['name']} - {i.get('sales_price', 0.0):.2f}" for i in self.items]
        self.item_map = {f"{i['name']} - {i.get('sales_price', 0.0):.2f}": i for i in self.items}

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 5}

        # Form Header Controls
        form_frame = tb.LabelFrame(self, text="Schedule Header", padding=10)
        form_frame.pack(fill=X, padx=10, pady=5)

        # Name
        tb.Label(form_frame, text="Schedule Name:").grid(row=0, column=0, sticky=W, **pad)
        self.name_var = tk.StringVar()
        tb.Entry(form_frame, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky=W, **pad)

        # Customer
        tb.Label(form_frame, text="Customer:").grid(row=0, column=2, sticky=W, **pad)
        self.customer_var = tk.StringVar()
        self.customer_cb = tb.Combobox(
            form_frame, textvariable=self.customer_var, values=self.customer_names, width=30, state="readonly"
        )
        self.customer_cb.grid(row=0, column=3, sticky=W, **pad)

        # Frequency
        tb.Label(form_frame, text="Frequency:").grid(row=1, column=0, sticky=W, **pad)
        self.freq_var = tk.StringVar(value="Monthly")
        tb.Combobox(
            form_frame, textvariable=self.freq_var,
            values=["Weekly", "Monthly", "Quarterly", "Yearly"], width=15, state="readonly"
        ).grid(row=1, column=1, sticky=W, **pad)

        # Next Run Date
        tb.Label(form_frame, text="Next Run Date (YYYY-MM-DD):").grid(row=1, column=2, sticky=W, **pad)
        self.next_run_var = tk.StringVar(value=tb.datetime.now().strftime("%Y-%m-%d"))
        tb.Entry(form_frame, textvariable=self.next_run_var, width=15).grid(row=1, column=3, sticky=W, **pad)

        # Terms & Auto Post
        tb.Label(form_frame, text="Payment Terms (Days):").grid(row=2, column=0, sticky=W, **pad)
        self.terms_var = tk.StringVar(value="30")
        tb.Entry(form_frame, textvariable=self.terms_var, width=15).grid(row=2, column=1, sticky=W, **pad)

        self.auto_post_var = tk.BooleanVar(value=False)
        tb.Checkbutton(
            form_frame, text="Auto-Post Invoice (Create as Unpaid instead of Draft)",
            variable=self.auto_post_var
        ).grid(row=2, column=2, columnspan=2, sticky=W, **pad)

        # Notes
        tb.Label(form_frame, text="Notes:").grid(row=3, column=0, sticky=W, **pad)
        self.notes_var = tk.StringVar()
        tb.Entry(form_frame, textvariable=self.notes_var, width=65).grid(row=3, column=1, columnspan=3, sticky=W, **pad)

        # Line Items Frame
        items_frame = tb.LabelFrame(self, text="Schedule Line Items", padding=10)
        items_frame.pack(fill=BOTH, expand=True, padx=10, pady=5)

        # Add item controls
        add_box = tb.Frame(items_frame)
        add_box.pack(fill=X, pady=5)

        tb.Label(add_box, text="Item:").pack(side=LEFT, padx=2)
        self.add_item_var = tk.StringVar()
        self.add_item_cb = tb.Combobox(add_box, textvariable=self.add_item_var, values=self.item_names, width=25, state="readonly")
        self.add_item_cb.pack(side=LEFT, padx=2)
        self.add_item_cb.bind("<<ComboboxSelected>>", self._on_item_select)

        tb.Label(add_box, text="Desc:").pack(side=LEFT, padx=2)
        self.add_desc_var = tk.StringVar()
        tb.Entry(add_box, textvariable=self.add_desc_var, width=20).pack(side=LEFT, padx=2)

        tb.Label(add_box, text="Qty:").pack(side=LEFT, padx=2)
        self.add_qty_var = tk.StringVar(value="1.0")
        tb.Entry(add_box, textvariable=self.add_qty_var, width=6).pack(side=LEFT, padx=2)

        tb.Label(add_box, text="Price:").pack(side=LEFT, padx=2)
        self.add_price_var = tk.StringVar(value="0.00")
        tb.Entry(add_box, textvariable=self.add_price_var, width=10).pack(side=LEFT, padx=2)

        tb.Button(add_box, text="Add Item", bootstyle=SUCCESS, command=self._add_line_item).pack(side=LEFT, padx=5)

        # Items Treeview
        columns = ("item_id", "description", "qty", "price", "amount")
        self.tree = tb.Treeview(items_frame, columns=columns, show="headings", height=8)
        self.tree.heading("item_id", text="Item ID")
        self.tree.heading("description", text="Description")
        self.tree.heading("qty", text="Quantity")
        self.tree.heading("price", text="Unit Price")
        self.tree.heading("amount", text="Total Amount")

        self.tree.column("item_id", width=80, anchor=CENTER)
        self.tree.column("description", width=250, anchor=W)
        self.tree.column("qty", width=80, anchor=E)
        self.tree.column("price", width=100, anchor=E)
        self.tree.column("amount", width=100, anchor=E)
        self.tree.pack(fill=BOTH, expand=True, side=LEFT)

        sb = tb.Scrollbar(items_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)

        tb.Button(items_frame, text="Remove Selected Line", bootstyle=DANGER_OUTLINE, command=self._remove_line_item).pack(anchor=E, pady=5)

        # Action Buttons
        btn_box = tb.Frame(self, padding=10)
        btn_box.pack(fill=X)

        tb.Button(btn_box, text="Cancel", bootstyle=SECONDARY, command=self.destroy).pack(side=RIGHT, padx=5)
        tb.Button(btn_box, text="Save Schedule", bootstyle=PRIMARY, command=self._save).pack(side=RIGHT, padx=5)

    def _on_item_select(self, event=None):
        val = self.add_item_var.get()
        if val in self.item_map:
            item = self.item_map[val]
            self.add_desc_var.set(item.get("description") or item.get("name") or "")
            self.add_price_var.set(f"{float(item.get('sales_price') or 0.0):.2f}")

    def _add_line_item(self):
        desc = self.add_desc_var.get().strip()
        if not desc:
            messagebox.showwarning("Validation Error", "Line item description is required.", parent=self)
            return
        try:
            qty = float(self.add_qty_var.get())
            if qty <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Validation Error", "Quantity must be greater than zero.", parent=self)
            return

        try:
            price = float(self.add_price_var.get())
        except ValueError:
            messagebox.showwarning("Validation Error", "Unit price must be a valid number.", parent=self)
            return

        item_val = self.add_item_var.get()
        item_id = self.item_map[item_val]["id"] if item_val in self.item_map else None

        amount = round(qty * price, 2)
        self.tree.insert("", END, values=(item_id or "", desc, f"{qty:.2f}", f"{price:.2f}", f"{amount:.2f}"))

        # Clear inputs
        self.add_item_var.set("")
        self.add_desc_var.set("")
        self.add_qty_var.set("1.0")
        self.add_price_var.set("0.00")

    def _remove_line_item(self):
        sel = self.tree.selection()
        if sel:
            for item in sel:
                self.tree.delete(item)

    def _populate_fields(self):
        self.name_var.set(self.schedule.get("schedule_name") or "")
        cust_id = self.schedule.get("customer_id")
        for k, v in self.customer_map.items():
            if v == cust_id:
                self.customer_var.set(k)
                break
        self.freq_var.set(self.schedule.get("frequency", "monthly").capitalize())
        self.next_run_var.set(self.schedule.get("next_run_date") or "")
        self.terms_var.set(str(self.schedule.get("terms_days") or 30))
        self.auto_post_var.set(bool(self.schedule.get("auto_post")))
        self.notes_var.set(self.schedule.get("notes") or "")

        for it in self.schedule.get("items", []):
            qty = float(it.get("quantity") or 1.0)
            price = float(it.get("unit_price") or 0.0)
            amount = float(it.get("amount") or (qty * price))
            self.tree.insert("", END, values=(
                it.get("item_id") or "",
                it.get("description") or "",
                f"{qty:.2f}",
                f"{price:.2f}",
                f"{amount:.2f}",
            ))

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Validation Error", "Schedule name is required.", parent=self)
            return

        cust_val = self.customer_var.get()
        if cust_val not in self.customer_map:
            messagebox.showwarning("Validation Error", "Please select a valid customer.", parent=self)
            return
        customer_id = self.customer_map[cust_val]

        # Gather lines
        lines = []
        for child in self.tree.get_children():
            row = self.tree.item(child)["values"]
            lines.append({
                "item_id": int(row[0]) if row[0] else None,
                "description": row[1],
                "quantity": float(row[2]),
                "unit_price": float(row[3]),
            })

        if not lines:
            messagebox.showwarning("Validation Error", "At least one line item is required.", parent=self)
            return

        try:
            terms = int(self.terms_var.get())
        except ValueError:
            terms = 30

        payload = {
            "company_id": self.company_id,
            "schedule_name": name,
            "customer_id": customer_id,
            "frequency": self.freq_var.get().lower(),
            "next_run_date": self.next_run_var.get().strip(),
            "terms_days": terms,
            "auto_post": self.auto_post_var.get(),
            "notes": self.notes_var.get().strip(),
            "status": self.schedule.get("status", "active") if self.schedule else "active",
        }

        try:
            if self.schedule:
                sdb.update_recurring_ar_schedule(self.schedule["id"], payload, lines)
            else:
                sdb.create_recurring_ar_schedule(payload, lines)

            if self.on_save_callback:
                self.on_save_callback()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Error Saving Schedule", str(exc), parent=self)


class RecurringARManagerDialog(tb.Toplevel):
    """Management dialog for Recurring AR Invoice Schedules."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Recurring Accounts Receivable (AR) Invoices")
        self.geometry("950x550")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.company_id = db.get_active_company_id()
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 5}

        # Header bar
        top_bar = tb.Frame(self, padding=10)
        top_bar.pack(fill=X)

        tb.Label(top_bar, text="Recurring AR Schedules", font=("Helvetica", 14, "bold")).pack(side=LEFT)

        # Action Buttons on Top Bar
        tb.Button(top_bar, text="Process Due Now", bootstyle=SUCCESS, command=self._process_due).pack(side=RIGHT, padx=5)
        tb.Button(top_bar, text="Export CSV", bootstyle=INFO_OUTLINE, command=self._export_csv).pack(side=RIGHT, padx=5)

        # Filters
        filter_bar = tb.Frame(self, padding=10)
        filter_bar.pack(fill=X)

        tb.Label(filter_bar, text="Status:").pack(side=LEFT, padx=2)
        self.status_filter_var = tk.StringVar(value="All")
        status_cb = tb.Combobox(
            filter_bar, textvariable=self.status_filter_var,
            values=["All", "Active", "Paused"], width=10, state="readonly"
        )
        status_cb.pack(side=LEFT, padx=5)
        status_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        tb.Label(filter_bar, text="Search:").pack(side=LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = tb.Entry(filter_bar, textvariable=self.search_var, width=25)
        search_entry.pack(side=LEFT, padx=2)
        search_entry.bind("<KeyRelease>", lambda e: self._refresh())

        # Main Treeview
        tree_frame = tb.Frame(self, padding=10)
        tree_frame.pack(fill=BOTH, expand=True)

        columns = ("id", "name", "customer", "frequency", "next_run", "last_run", "status", "auto_post", "total")
        self.tree = tb.Treeview(tree_frame, columns=columns, show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Schedule Name")
        self.tree.heading("customer", text="Customer")
        self.tree.heading("frequency", text="Frequency")
        self.tree.heading("next_run", text="Next Run Date")
        self.tree.heading("last_run", text="Last Run Date")
        self.tree.heading("status", text="Status")
        self.tree.heading("auto_post", text="Auto Post")
        self.tree.heading("total", text="Total Amount")

        self.tree.column("id", width=50, anchor=CENTER)
        self.tree.column("name", width=180, anchor=W)
        self.tree.column("customer", width=180, anchor=W)
        self.tree.column("frequency", width=90, anchor=CENTER)
        self.tree.column("next_run", width=100, anchor=CENTER)
        self.tree.column("last_run", width=100, anchor=CENTER)
        self.tree.column("status", width=80, anchor=CENTER)
        self.tree.column("auto_post", width=80, anchor=CENTER)
        self.tree.column("total", width=110, anchor=E)

        self.tree.pack(fill=BOTH, expand=True, side=LEFT)

        sb = tb.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", lambda e: self._edit_schedule())
        self.tree.bind("<Return>", lambda e: self._edit_schedule())
        self.tree.bind("<KP_Enter>", lambda e: self._edit_schedule())
        self.tree.bind("<Delete>", lambda e: self._delete_schedule())

        # Bottom Action Buttons
        bot_bar = tb.Frame(self, padding=10)
        bot_bar.pack(fill=X)

        tb.Button(bot_bar, text="New Schedule", bootstyle=PRIMARY, command=self._new_schedule).pack(side=LEFT, padx=5)
        tb.Button(bot_bar, text="Edit Schedule", bootstyle=SECONDARY, command=self._edit_schedule).pack(side=LEFT, padx=5)
        tb.Button(bot_bar, text="Toggle Active/Pause", bootstyle=WARNING, command=self._toggle_status).pack(side=LEFT, padx=5)
        tb.Button(bot_bar, text="Delete Schedule", bootstyle=DANGER_OUTLINE, command=self._delete_schedule).pack(side=LEFT, padx=5)
        tb.Button(bot_bar, text="Close", bootstyle=SECONDARY, command=self.destroy).pack(side=RIGHT, padx=5)

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        st = self.status_filter_var.get()
        status_param = None if st == "All" else st.lower()
        search_param = self.search_var.get().strip() or None

        schedules = sdb.get_recurring_ar_schedules(
            company_id=self.company_id,
            status=status_param,
            search=search_param,
        )

        for s in schedules:
            self.tree.insert("", END, iid=str(s["id"]), values=(
                s["id"],
                s["schedule_name"],
                s["customer_name"],
                s["frequency"].capitalize(),
                s["next_run_date"],
                s.get("last_run_date") or "-",
                s["status"].capitalize(),
                "Yes" if s.get("auto_post") else "No",
                f"{s.get('total_amount', 0.0):.2f}",
            ))

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])

    def _get_selected_schedule_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Selection Required", "Please select a schedule from the list.", parent=self)
            return None
        return int(sel[0])

    def _new_schedule(self):
        RecurringAREditModal(self, on_save_callback=self._refresh)

    def _edit_schedule(self):
        sid = self._get_selected_schedule_id()
        if sid:
            sched = sdb.get_recurring_ar_schedule(sid)
            if sched:
                RecurringAREditModal(self, schedule=sched, on_save_callback=self._refresh)

    def _toggle_status(self):
        sid = self._get_selected_schedule_id()
        if sid:
            sched = sdb.get_recurring_ar_schedule(sid)
            if sched:
                new_status = "paused" if sched["status"] == "active" else "active"
                sdb.update_recurring_ar_schedule(sid, {"schedule_name": sched["schedule_name"], "customer_id": sched["customer_id"], "status": new_status})
                self._refresh()

    def _delete_schedule(self):
        sid = self._get_selected_schedule_id()
        if sid:
            if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this recurring schedule?", parent=self):
                sdb.delete_recurring_ar_schedule(sid)
                self._refresh()

    def _process_due(self):
        created = sdb.process_due_recurring_ar_schedules(company_id=self.company_id)
        if created:
            msg = f"Successfully generated {len(created)} recurring invoice(s):\n\n"
            for c in created:
                msg += f"• {c['schedule_name']} -> Invoice #{c['invoice_id']} ({c['status']})\n"
            messagebox.showinfo("Recurring Invoices Generated", msg, parent=self)
        else:
            messagebox.showinfo("No Due Invoices", "There are no recurring AR schedules due as of today.", parent=self)
        self._refresh()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Export Recurring AR Schedules",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"recurring_ar_schedules_{tb.datetime.now().strftime('%Y%m%d')}.csv"
        )
        if path:
            try:
                sdb.export_recurring_ar_schedules_to_csv(path, company_id=self.company_id)
                messagebox.showinfo("Export Successful", f"Schedules exported to:\n{path}", parent=self)
            except Exception as exc:
                messagebox.showerror("Export Failed", str(exc), parent=self)
