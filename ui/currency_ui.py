"""
Multi-Currency & Exchange Rate UI components.
Allows users to select currencies on vouchers, manage exchange rates,
fetch live rates via background API, and add custom currencies.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import simpledialog, messagebox
import threading
import database as db


class CurrencySelector(ttk.Frame):
    """A composite widget for selecting a currency and optionally adjusting its exchange rate."""

    def __init__(self, parent, company_id, on_change=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._company_id = company_id
        self._on_change = on_change

        self.base_currency = db.get_company_base_currency(company_id)

        # UI
        ttk.Label(self, text="Currency:").pack(side=tk.LEFT, padx=(0, 4))

        self.currency_var = tk.StringVar(value=self.base_currency)
        self.combo = ttk.Combobox(self, textvariable=self.currency_var, width=6, state="readonly")
        self.combo.pack(side=tk.LEFT)
        self.combo.bind("<<ComboboxSelected>>", self._handle_change)

        self.rate_var = tk.StringVar(value="1.0000")
        self.rate_lbl = ttk.Label(self, textvariable=self.rate_var, font=("Segoe UI", 8), foreground="#64748b")
        self.rate_lbl.pack(side=tk.LEFT, padx=(8, 0))

        self.refresh_currencies()

    def refresh_currencies(self):
        currencies = db.get_currencies(active_only=True)
        self.combo["values"] = [c["code"] for c in currencies]

    def _handle_change(self, event=None):
        code = self.currency_var.get()
        if code == self.base_currency:
            self.rate_var.set("1.0000")
        else:
            rate = db.get_exchange_rate(code, self.base_currency)
            if rate:
                self.rate_var.set(f"Rate: {rate['rate']:.4f}")
            else:
                self.rate_var.set("Rate: Unknown")

        if self._on_change:
            self._on_change(code)

    def get_currency(self):
        return self.currency_var.get()

    def get_rate(self):
        if self.currency_var.get() == self.base_currency:
            return 1.0
        rate = db.get_exchange_rate(self.currency_var.get(), self.base_currency)
        return rate["rate"] if rate else 1.0

    def set_currency(self, code, rate=None):
        """Programmatically set the selected currency and optional exchange rate."""
        if not code:
            code = self.base_currency
        self.currency_var.set(code)
        if code == self.base_currency:
            self.rate_var.set("1.0000")
        elif rate is not None:
            self.rate_var.set(f"Rate: {float(rate):.4f}")
        else:
            self._handle_change()

    def reset(self):
        """Reset to the base currency."""
        self.base_currency = db.get_company_base_currency(self._company_id)
        self.currency_var.set(self.base_currency)
        self.rate_var.set("1.0000")


class AddCurrencyDialog(tk.Toplevel):
    """Modal dialog for adding a new/custom currency."""

    def __init__(self, parent, on_added=None):
        super().__init__(parent)
        self.withdraw()  # Prevent opening glitch
        self.title("Add New Currency")
        self.geometry("380x300")
        self.resizable(False, False)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._on_added = on_added
        self._build_ui()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="➕ Add Custom Currency", font=("Segoe UI", 11, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Add any ISO world currency (e.g., CAD, SAR, CHF, MYR, KWD)",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(self, padding=16)
        content.pack(fill=tk.BOTH, expand=True)

        ttk.Label(content, text="Currency Code (3 letters):").grid(row=0, column=0, sticky="w", pady=4)
        self._code_var = tk.StringVar()
        code_entry = ttk.Entry(content, textvariable=self._code_var, width=10)
        code_entry.grid(row=0, column=1, sticky="w", padx=8, pady=4)
        code_entry.focus_set()

        ttk.Label(content, text="Currency Name:").grid(row=1, column=0, sticky="w", pady=4)
        self._name_var = tk.StringVar()
        ttk.Entry(content, textvariable=self._name_var, width=22).grid(row=1, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(content, text="Symbol (Optional):").grid(row=2, column=0, sticky="w", pady=4)
        self._sym_var = tk.StringVar()
        ttk.Entry(content, textvariable=self._sym_var, width=10).grid(row=2, column=1, sticky="w", padx=8, pady=4)

        ttk.Label(content, text="Decimal Places:").grid(row=3, column=0, sticky="w", pady=4)
        self._dec_var = tk.StringVar(value="2")
        ttk.Combobox(content, textvariable=self._dec_var, values=["0", "2", "3", "4"],
                     state="readonly", width=6).grid(row=3, column=1, sticky="w", padx=8, pady=4)

        btn_row = ttk.Frame(content)
        btn_row.grid(row=4, column=0, columnspan=2, pady=(16, 0), sticky="e")

        ttk.Button(btn_row, text="Add Currency", command=self._save_currency,
                   bootstyle="success").pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btn_row, text="Cancel", command=self.destroy,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT)

    def _save_currency(self):
        code = self._code_var.get().strip().upper()
        name = self._name_var.get().strip()
        sym = self._sym_var.get().strip()

        if not code or len(code) != 3:
            messagebox.showwarning("Validation Error", "Currency Code must be a 3-letter ISO code (e.g. SAR, CAD).", parent=self)
            return

        if not name:
            name = code

        try:
            decs = int(self._dec_var.get())
        except ValueError:
            decs = 2

        if db.add_currency(code, name, symbol=sym, decimal_places=decs):
            messagebox.showinfo("Success", f"Currency '{code} - {name}' added successfully!", parent=self)
            if self._on_added:
                self._on_added(code)
            self.destroy()
        else:
            messagebox.showerror("Error", f"Failed to add currency '{code}'. It may already exist.", parent=self)


class ExchangeRateManagerDialog(tk.Toplevel):
    """Dialog to view, edit, add custom currencies, and automatically fetch exchange rates."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual pop-in
        self.title("Exchange Rate Engine & Currencies")
        self.geometry("480x560")
        self.minsize(420, 440)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._company_id = db.get_active_company_id()
        self._base = db.get_company_base_currency(self._company_id)
        self._entries = {}

        self._build_ui()
        self._load_currency_rows()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _on_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120))
        self._canvas.yview_scroll(delta, "units")
        self._canvas.update_idletasks()
        return "break"

    def _bind_mousewheel_recursive(self, widget):
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="💱 Exchange Rate Engine", font=("Segoe UI", 12, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text=f"Base Currency: {self._base}  |  1 Unit of Foreign Currency = X {self._base}",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        # Top Tool Bar
        top_tools = ttk.Frame(self, padding=(12, 6))
        top_tools.pack(fill=tk.X)

        ttk.Button(top_tools, text="➕ Add Currency", command=self._open_add_currency,
                   bootstyle="primary-outline").pack(side=tk.LEFT)

        self._fetch_btn = ttk.Button(top_tools, text="🔄 Fetch Online Rates", command=self._fetch_online,
                                     bootstyle="info")
        self._fetch_btn.pack(side=tk.RIGHT)

        # Scrollable Area for Currencies
        canvas_container = ttk.Frame(self, padding=(12, 4))
        canvas_container.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(canvas_container, bg="#ffffff", highlightthickness=0)

        def _on_curr_scroll(*args):
            self._canvas.yview(*args)
            self._canvas.update_idletasks()

        scrollbar = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=_on_curr_scroll)
        self._list_frame = ttk.Frame(self._canvas)

        self._list_frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=scrollbar.set)

        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(self._canvas_window, width=e.width))
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel support
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Footer Buttons
        footer = ttk.Frame(self, padding=(12, 10))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="Save Rates", command=self._save_rates,
                   bootstyle="success").pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(footer, text="Done / Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _load_currency_rows(self):
        for widget in self._list_frame.winfo_children():
            widget.destroy()

        self._entries.clear()
        currencies = db.get_currencies(active_only=True)

        for i, c in enumerate(currencies):
            code = c["code"]
            if code == self._base:
                continue

            rate_info = db.get_exchange_rate(code, self._base)
            current_rate = rate_info["rate"] if rate_info else 1.0

            row = tk.Frame(self._list_frame, bg="#ffffff" if i % 2 == 0 else "#f8fafc", padx=8, pady=5)
            row.pack(fill=tk.X)

            sym = f" ({c['symbol']})" if c.get("symbol") else ""
            label_text = f"1 {code}{sym} - {c.get('name', '')} ="
            tk.Label(row, text=label_text, font=("Segoe UI", 9),
                     bg=row["bg"], fg="#0f172a", width=24, anchor="w").pack(side=tk.LEFT)

            var = tk.StringVar(value=f"{current_rate:.4f}")
            entry = ttk.Entry(row, textvariable=var, width=12)
            entry.pack(side=tk.LEFT, padx=(4, 6))
            self._entries[code] = var

            tk.Label(row, text=self._base, font=("Segoe UI", 8), bg=row["bg"], fg="#64748b").pack(side=tk.LEFT)

            # Delete button (only for custom currencies, keep standard ones safe)
            del_btn = ttk.Button(row, text="✕", command=lambda cur_code=code: self._delete_currency(cur_code),
                                 bootstyle="danger-link")
            del_btn.pack(side=tk.RIGHT, padx=(0, 4))

        self._bind_mousewheel_recursive(self._list_frame)

    def _open_add_currency(self):
        """Open the Add Currency modal dialog."""
        dlg = AddCurrencyDialog(self, on_added=self._on_currency_added)
        self.wait_window(dlg)

    def _on_currency_added(self, new_code):
        # Refresh the list
        self._load_currency_rows()
        # Automatically fetch exchange rate for the newly added currency in background
        self._fetch_online()

    def _delete_currency(self, code):
        if messagebox.askyesno("Delete Currency", f"Are you sure you want to remove '{code}' from the currency list?", parent=self):
            db.delete_currency(code)
            self._load_currency_rows()

    def _fetch_online(self):
        self._fetch_btn.config(text="⏳ Fetching...", state="disabled")

        def worker():
            try:
                stored = db.fetch_and_store_daily_exchange_rates(base_currency=self._base, force=True)
                if not stored:
                    raise ValueError("Could not retrieve exchange rates from open.er-api.com.")

                def on_success():
                    for code, var in self._entries.items():
                        if code in stored:
                            var.set(f"{stored[code]:.4f}")
                    self._fetch_btn.config(text="🔄 Fetch Online Rates", state="normal")
                    messagebox.showinfo(
                        "Rates Updated",
                        f"Successfully fetched live rates for {len(stored)} currencies and stored them in the database!",
                        parent=self
                    )

                self.after(0, on_success)
            except Exception as e:
                def on_fail(err_msg):
                    self._fetch_btn.config(text="🔄 Fetch Online Rates", state="normal")
                    messagebox.showwarning(
                        "Connection / Offline",
                        f"Could not retrieve exchange rates:\n{err_msg}\nYou can still enter rates manually.",
                        parent=self
                    )

                self.after(0, on_fail, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _save_rates(self):
        today = db.datetime.now().strftime("%Y-%m-%d")
        for code, var in self._entries.items():
            try:
                rate = float(var.get())
                db.update_exchange_rate(code, self._base, rate, rate_date=today, source="manual")
            except ValueError:
                pass
        messagebox.showinfo("Saved", "All exchange rates saved successfully to database.", parent=self)
        self.destroy()


def show_exchange_rate_manager(parent):
    """Helper function to instantiate and show the ExchangeRateManagerDialog."""
    dlg = ExchangeRateManagerDialog(parent)
    return dlg
