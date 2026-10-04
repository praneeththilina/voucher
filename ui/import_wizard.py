"""
Bulk Import Wizard.
Step-by-step wizard to map columns and import vouchers from CSV.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import os

import database as db


class ImportWizardDialog(tk.Toplevel):
    """Step-by-step wizard for importing vouchers."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self.title("Bulk Import Wizard")
        self.geometry("800x600")
        self.minsize(700, 500)
        self.transient(parent)
        self.grab_set()

        self._company_id = db.get_active_company_id()
        self._filepath = None
        self._column_map = {}
        self._preview_data = None
        
        self._build_ui()
        self._show_step(1)

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()

    def _build_ui(self):
        # ── Header ──
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)
        self._title_lbl = tk.Label(header, text="Step 1: Select File", font=("Segoe UI", 12, "bold"),
                                   bg="#0f172a", fg="#ffffff")
        self._title_lbl.pack(anchor="w")

        # ── Step Container ──
        self._container = ttk.Frame(self)
        self._container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        self._step1 = self._create_step1()
        self._step2 = self._create_step2()
        self._step3 = self._create_step3()
        self._steps = [self._step1, self._step2, self._step3]

        # ── Footer Buttons ──
        footer = ttk.Frame(self, padding=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        self._btn_prev = ttk.Button(footer, text="< Back", command=self._prev_step, bootstyle="secondary")
        self._btn_prev.pack(side=tk.LEFT)
        
        self._btn_next = ttk.Button(footer, text="Next >", command=self._next_step, bootstyle="primary")
        self._btn_next.pack(side=tk.RIGHT, padx=(8, 0))
        
        ttk.Button(footer, text="Cancel", command=self.destroy, bootstyle="secondary-outline").pack(side=tk.RIGHT)

        self._current_step = 1

    def _create_step1(self):
        f = ttk.Frame(self._container)
        
        ttk.Label(f, text="Welcome to the Bulk Import Wizard", font=("Segoe UI", 11, "bold")).pack(pady=(0, 16))
        ttk.Label(f, text="Import vouchers from a CSV file. The file should have a header row.",
                  wraplength=600).pack(pady=(0, 24))
                  
        sel_frame = ttk.Frame(f)
        sel_frame.pack(fill=tk.X, pady=8)
        
        self._file_var = tk.StringVar()
        ttk.Entry(sel_frame, textvariable=self._file_var, state="readonly", width=50).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(sel_frame, text="Browse...", command=self._browse_file).pack(side=tk.LEFT)
        
        # Batch History
        ttk.Separator(f).pack(fill=tk.X, pady=24)
        ttk.Label(f, text="Recent Imports", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        
        cols = ("date", "file", "success", "failed")
        self._hist_tree = ttk.Treeview(f, columns=cols, show="headings", height=5)
        self._hist_tree.heading("date", text="Date")
        self._hist_tree.heading("file", text="File")
        self._hist_tree.heading("success", text="Imported")
        self._hist_tree.heading("failed", text="Failed")
        
        self._hist_tree.column("date", width=120)
        self._hist_tree.column("file", width=200)
        self._hist_tree.column("success", width=80, anchor="center")
        self._hist_tree.column("failed", width=80, anchor="center")
        self._hist_tree.pack(fill=tk.BOTH, expand=True)
        
        self._refresh_history()
        return f

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self
        )
        if path:
            self._filepath = path
            self._file_var.set(os.path.basename(path))

    def _refresh_history(self):
        self._hist_tree.delete(*self._hist_tree.get_children())
        batches = db.get_import_batches(self._company_id)
        for b in batches[:5]:
            self._hist_tree.insert("", tk.END, values=(
                b["created_at"][:16],
                b["source_filename"],
                b["successful_records"],
                b["failed_records"]
            ))

    def _create_step2(self):
        f = ttk.Frame(self._container)
        ttk.Label(f, text="Map Columns", font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))
        ttk.Label(f, text="We attempted to auto-match your CSV columns. Please verify the mapping below.").pack(pady=(0, 16))
        
        self._map_frame = ttk.Frame(f)
        self._map_frame.pack(fill=tk.BOTH, expand=True)
        
        # Will be populated in _prepare_step2
        return f

    def _prepare_step2(self):
        for w in self._map_frame.winfo_children():
            w.destroy()
            
        if not self._filepath: return False
        
        import csv
        try:
            with open(self._filepath, "r", encoding="utf-8-sig") as file:
                reader = csv.reader(file)
                self._headers = next(reader, [])
        except Exception as e:
            messagebox.showerror("File Error", f"Could not read file: {e}", parent=self)
            return False
            
        if not self._headers:
            messagebox.showerror("Empty File", "No headers found in the file.", parent=self)
            return False
            
        self._column_map = db.auto_detect_import_columns(self._filepath)
        
        header_opts = ["-- Ignore --"] + self._headers
        self._map_vars = {}
        
        fields = [
            ("date", "Date *"),
            ("paid_to", "Payee *"),
            ("total_amount", "Amount *"),
            ("description", "Description"),
            ("category", "Category"),
            ("payment_method", "Payment Method"),
            ("cash_given_by", "Cash Given By")
        ]
        
        for i, (key, label) in enumerate(fields):
            ttk.Label(self._map_frame, text=label).grid(row=i, column=0, sticky="w", pady=4, padx=8)
            
            var = tk.StringVar(value="-- Ignore --")
            if key in self._column_map and self._column_map[key] < len(self._headers):
                var.set(self._headers[self._column_map[key]])
                
            cb = ttk.Combobox(self._map_frame, textvariable=var, values=header_opts, state="readonly", width=30)
            cb.grid(row=i, column=1, sticky="ew", pady=4, padx=8)
            self._map_vars[key] = var
            
        return True

    def _create_step3(self):
        f = ttk.Frame(self._container)
        ttk.Label(f, text="Preview & Import", font=("Segoe UI", 11, "bold")).pack(pady=(0, 8))
        
        self._preview_stats = ttk.Label(f, text="")
        self._preview_stats.pack(anchor="w", pady=(0, 8))
        
        cols = ("row", "date", "payee", "amount", "status")
        self._prev_tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        self._prev_tree.heading("row", text="Row")
        self._prev_tree.heading("date", text="Date")
        self._prev_tree.heading("payee", text="Payee")
        self._prev_tree.heading("amount", text="Amount")
        self._prev_tree.heading("status", text="Validation")
        
        self._prev_tree.column("row", width=50, anchor="center")
        self._prev_tree.column("date", width=80)
        self._prev_tree.column("payee", width=150)
        self._prev_tree.column("amount", width=80, anchor="e")
        self._prev_tree.column("status", width=250)
        
        self._prev_tree.pack(fill=tk.BOTH, expand=True, pady=8)
        
        self._btn_do_import = ttk.Button(f, text="Start Import", command=self._do_import, bootstyle="success")
        self._btn_do_import.pack(pady=8)
        
        return f

    def _prepare_step3(self):
        # Build actual index map from vars
        final_map = {}
        for key, var in self._map_vars.items():
            val = var.get()
            if val != "-- Ignore --" and val in self._headers:
                final_map[key] = self._headers.index(val)
                
        self._column_map = final_map
        
        # Check required
        if "date" not in final_map or "paid_to" not in final_map or "total_amount" not in final_map:
            messagebox.showwarning("Missing Mapping", "Date, Payee, and Amount must be mapped.", parent=self)
            return False
            
        headers, rows, _, errors = db.preview_import(self._filepath, self._column_map, max_rows=10)
        
        self._prev_tree.delete(*self._prev_tree.get_children())
        
        err_dict = {}
        for e in errors:
            if e.startswith("Row "):
                parts = e.split(":", 1)
                if len(parts) == 2:
                    num = int(parts[0].replace("Row ", "").strip())
                    err_dict[num] = parts[1].strip()
                    
        for i, row in enumerate(rows):
            row_num = i + 1
            date_val = row[final_map["date"]] if "date" in final_map else ""
            payee_val = row[final_map["paid_to"]] if "paid_to" in final_map else ""
            amt_val = row[final_map["total_amount"]] if "total_amount" in final_map else ""
            
            status = "❌ " + err_dict[row_num] if row_num in err_dict else "✅ OK"
            
            item_id = self._prev_tree.insert("", tk.END, values=(
                str(row_num), date_val, payee_val, amt_val, status
            ))
            if row_num in err_dict:
                self._prev_tree.item(item_id, tags=("error",))
                
        self._prev_tree.tag_configure("error", foreground="#ef4444")
        
        self._preview_stats.config(text=f"Previewing first {len(rows)} rows. {len(errors)} validation error(s) found.")
        self._btn_do_import.config(state=tk.NORMAL)
        return True

    def _do_import(self):
        self._btn_do_import.config(state=tk.DISABLED, text="Importing...")
        self.update()
        
        batch_id, succ, err, msgs = db.bulk_import_vouchers_csv(self._filepath, self._column_map, self._company_id)
        
        if msgs and not succ:
            messagebox.showerror("Import Failed", "\n".join(msgs[:5]), parent=self)
        else:
            msg = f"Import Complete!\n\nSuccessfully imported: {succ}\nFailed rows: {err}"
            messagebox.showinfo("Import Success", msg, parent=self)
            self.destroy()

    def _show_step(self, step):
        for s in self._steps:
            s.pack_forget()
            
        self._steps[step - 1].pack(fill=tk.BOTH, expand=True)
        
        titles = ["Step 1: Select File", "Step 2: Map Columns", "Step 3: Preview & Import"]
        self._title_lbl.config(text=titles[step - 1])
        
        self._btn_prev.config(state=tk.NORMAL if step > 1 else tk.DISABLED)
        
        if step == len(self._steps):
            self._btn_next.pack_forget()
        else:
            self._btn_next.pack(side=tk.RIGHT, padx=(8, 0))

    def _prev_step(self):
        if self._current_step > 1:
            self._current_step -= 1
            self._show_step(self._current_step)

    def _next_step(self):
        if self._current_step == 1:
            if not self._filepath:
                messagebox.showwarning("File Required", "Please select a CSV file first.", parent=self)
                return
            if not self._prepare_step2():
                return
                
        elif self._current_step == 2:
            if not self._prepare_step3():
                return
                
        if self._current_step < len(self._steps):
            self._current_step += 1
            self._show_step(self._current_step)
