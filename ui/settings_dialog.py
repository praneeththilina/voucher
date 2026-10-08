"""
Settings Dialog
Configure voucher header customization, two independent company profiles,
logo upload (saved in DB as BLOB), voucher numbering format, and
Google Firebase Cloud Firestore NoSQL Database integration (100% Free Spark Tier).
"""

import io
import os
import webbrowser
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

import database as db
import firebase_client
import gdrive_client


class SettingsDialog(tk.Toplevel):
    """Application settings dialog supporting company profiles & Firebase Cloud Database."""

    def __init__(self, parent, on_saved_callback=None, initial_tab=0):
        super().__init__(parent)
        self.withdraw()  # Prevent visual glitching while constructing UI
        self.title("⚙️ Settings: Profiles, Firebase & Google Drive")
        self.resizable(True, True)
        self.geometry("820x680")
        self.minsize(740, 600)
        self.transient(parent)
        self.grab_set()

        self._on_saved_callback = on_saved_callback
        self._initial_tab = initial_tab
        self._companies_data = {}  # {company_id: {...widgets and variables...}}

        self._build_ui()
        self._load_all_values()

        # Handle requested initial tab (0: Company Profiles, 1: Firebase, 2: Google Drive)
        if str(initial_tab).lower() in ("cloud", "firebase", "1", "2"):
            try:
                self._notebook.select(1)
            except Exception:
                pass
        elif str(initial_tab).lower() in ("gdrive", "drive", "attachments", "3"):
            try:
                self._notebook.select(2)
            except Exception:
                pass
        elif isinstance(initial_tab, int) and 0 <= initial_tab < 3:
            try:
                self._notebook.select(initial_tab)
            except Exception:
                pass
        else:
            try:
                cid_int = int(initial_tab)
                if cid_int in self._companies_data:
                    self._notebook.select(0)
                    self._refresh_company_selector(select_cid=cid_int)
            except Exception:
                pass

        # Center dialog
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")
        self.deiconify()

        self.lift()
        self.focus_force()

        self.bind("<Escape>", lambda e: (self.destroy(), "break")[1])
        self.bind("<Return>", lambda e: self._save())

    def _build_ui(self):
        # ── Top Title Bar ──────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="⚙️ Settings: Profiles, Firebase Cloud & Google Drive Storage",
            font=("Segoe UI", 12, "bold"), bootstyle="primary"
        ).pack(side=tk.LEFT)

        sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ── Notebook with Company Profiles, Firebase Cloud, and Google Drive ─
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        tab_comp = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(tab_comp, text="  🏢 Company Profiles  ")
        self._build_companies_manager_tab(tab_comp)

        tab_fb = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(tab_fb, text="  ☁️ Firebase Cloud Database (NoSQL)  ")
        self._build_firebase_tab(tab_fb)

        tab_gd = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(tab_gd, text="  📁 Google Drive (15 GB Free)  ")
        self._build_gdrive_tab(tab_gd)


        # ── Bottom Action Bar ──────────────────────────────────────────────
        btn_frame = ttk.Frame(self, padding=(14, 6, 14, 12))
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(
            btn_frame, text="💾 Save All Settings (Enter)",
            command=self._save, bootstyle="success"
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            btn_frame, text="Cancel (Esc)",
            command=self.destroy, bootstyle="secondary"
        ).pack(side=tk.LEFT)

        ttk.Button(
            btn_frame, text="🗑️ Clear All Vouchers...",
            command=self._open_clear_vouchers, bootstyle="danger-outline"
        ).pack(side=tk.LEFT, padx=(14, 0))

        ttk.Label(
            btn_frame,
            text="* Offline-first engine: local SQLite is always instant; Firebase syncs in background.",
            font=("Segoe UI", 8), bootstyle="secondary"
        ).pack(side=tk.RIGHT)

    def _build_companies_manager_tab(self, parent):
        """Build the profile editor for the company stored in this file."""
        self._current_cid = None

        # Top Bar: the single company profile stored in this database
        top_bar = ttk.Frame(parent, padding=(4, 2, 4, 10))
        top_bar.pack(fill=tk.X)

        ttk.Label(
            top_bar, text="🏢 Company in this file:",
            font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 8))

        self._comp_selector_cb = ttk.Combobox(top_bar, state="disabled", width=38, font=("Segoe UI", 9))
        self._comp_selector_cb.pack(side=tk.LEFT, padx=(0, 10))
        self._comp_selector_cb.bind("<<ComboboxSelected>>", self._on_company_selected)

        self._active_status_badge = ttk.Label(
            top_bar, text="",
            font=("Segoe UI", 8, "bold"), bootstyle="success"
        )
        self._active_status_badge.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(
            top_bar,
            text="To use another company, close this file and sign in again.",
            font=("Segoe UI", 8),
            bootstyle="secondary",
        ).pack(side=tk.RIGHT, padx=(8, 0))
# Main profile form container (2 columns: Left = Form & Numbering, Right = Logo)
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True)

        left_col = ttk.Frame(content_frame)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right_col = ttk.Frame(content_frame, width=175)
        right_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))

        # Form variables for currently active edit view
        self._comp_name_var = tk.StringVar()
        self._comp_tagline_var = tk.StringVar()
        self._comp_address_var = tk.StringVar()
        self._comp_contact_var = tk.StringVar()
        self._comp_email_var = tk.StringVar()
        self._comp_fmt_var = tk.StringVar(value="date_based")
        self._comp_prefix_var = tk.StringVar(value="V-")
        self._comp_start_var = tk.StringVar(value="1")
        self._comp_fiscal_start_var = tk.StringVar(value="01-01")
        self._comp_fiscal_end_var = tk.StringVar(value="12-31")

        # ── 1. Company Header Information ──────────────────────────────────
        info_group = ttk.LabelFrame(left_col, text="  Header & Contact Details  ", padding=(10, 6, 10, 8))
        info_group.pack(fill=tk.X, pady=(0, 8))

        fields = [
            ("Company Name:", self._comp_name_var, 28),
            ("Tagline / Slogan:", self._comp_tagline_var, 28),
            ("Physical Address:", self._comp_address_var, 28),
            ("Contact / Phone:", self._comp_contact_var, 24),
            ("Email Address:", self._comp_email_var, 24),
        ]

        for row_idx, (lbl, var, w) in enumerate(fields):
            ttk.Label(info_group, text=lbl, font=("Segoe UI", 8, "bold")).grid(
                row=row_idx, column=0, sticky="w", pady=2, padx=(0, 6)
            )
            entry = ttk.Entry(info_group, textvariable=var, width=w)
            entry.grid(row=row_idx, column=1, sticky="ew", pady=2)

        info_group.columnconfigure(1, weight=1)

        # ── 2. Logo Upload & Preview Card ──────────────────────────────────
        logo_group = ttk.LabelFrame(right_col, text="  Company Logo  ", padding=(8, 8, 8, 8))
        logo_group.pack(fill=tk.BOTH, expand=True)

        self._logo_preview = tk.Label(
            logo_group, text="No Logo\nUploaded",
            bg="#f1f5f9", fg="#64748b", font=("Segoe UI", 8),
            relief="groove", width=16, height=6
        )
        self._logo_preview.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        btn_box = ttk.Frame(logo_group)
        btn_box.pack(fill=tk.X)

        ttk.Button(
            btn_box, text="📂 Choose...",
            command=self._choose_logo,
            bootstyle="outline-primary"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        ttk.Button(
            btn_box, text="🗑️",
            command=self._remove_logo,
            bootstyle="outline-danger"
        ).pack(side=tk.LEFT)

        ttk.Label(
            logo_group, text="Supports PNG, JPG, BMP\nScaled to fit headers.",
            font=("Segoe UI", 7), bootstyle="secondary", justify="center"
        ).pack(pady=(4, 0))

        # ── 3. Numbering Format Configuration ──────────────────────────────
        num_group = ttk.LabelFrame(left_col, text="  Voucher Numbering Scheme  ", padding=(10, 6, 10, 8))
        num_group.pack(fill=tk.X)

        rb0 = ttk.Radiobutton(
            num_group, text="Daily Date-Based (e.g. 26OCT03_01)",
            variable=self._comp_fmt_var, value="date_based",
            command=self._on_format_change
        )
        rb0.grid(row=0, column=0, columnspan=3, sticky="w", pady=1)

        ttk.Label(num_group, text="Format: YYMMMDD_## • Resets daily. Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=1, column=0, sticky="w", padx=(16, 0), pady=(0, 3)
        )
        self._preview_date_lbl = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        self._preview_date_lbl.grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 3))

        rb1 = ttk.Radiobutton(
            num_group, text="Monthly Sequential (e.g. 26AUG_01)",
            variable=self._comp_fmt_var, value="month_based",
            command=self._on_format_change
        )
        rb1.grid(row=2, column=0, columnspan=3, sticky="w", pady=1)

        ttk.Label(num_group, text="Format: YYMMM_## • Resets monthly. Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=3, column=0, sticky="w", padx=(16, 0), pady=(0, 3)
        )
        self._preview_month_lbl = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        self._preview_month_lbl.grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 3))

        rb2 = ttk.Radiobutton(
            num_group, text="Custom Prefix + Sequential Number",
            variable=self._comp_fmt_var, value="custom",
            command=self._on_format_change
        )
        rb2.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 1))

        ttk.Label(num_group, text="Prefix:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=5, column=0, sticky="w", padx=(16, 4)
        )
        self._prefix_entry = ttk.Entry(num_group, textvariable=self._comp_prefix_var, width=10)
        self._prefix_entry.grid(row=5, column=1, sticky="w", padx=2, pady=1)
        self._comp_prefix_var.trace_add("write", lambda *_: self._update_preview())

        ttk.Label(num_group, text="Start #:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=5, column=2, sticky="w", padx=(8, 4)
        )
        self._start_entry = ttk.Entry(num_group, textvariable=self._comp_start_var, width=8)
        self._start_entry.grid(row=5, column=3, sticky="w", padx=2, pady=1)
        self._comp_start_var.trace_add("write", lambda *_: self._update_preview())

        ttk.Label(num_group, text="Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=6, column=0, sticky="w", padx=(16, 4), pady=(1, 0)
        )
        self._preview_custom_lbl = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        self._preview_custom_lbl.grid(row=6, column=1, columnspan=3, sticky="w", pady=(1, 0))

        # ── 4. Fiscal / Tax Year Accounting Period ─────────────────────────
        fiscal_group = ttk.LabelFrame(left_col, text="  Fiscal / Tax Year Accounting Period  ", padding=(10, 6, 10, 8))
        fiscal_group.pack(fill=tk.X, pady=(8, 0))

        ttk.Label(fiscal_group, text="Opening Date (MM-DD):", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=0, sticky="w", pady=2, padx=(0, 4)
        )
        self._fiscal_start_entry = ttk.Entry(fiscal_group, textvariable=self._comp_fiscal_start_var, width=10)
        self._fiscal_start_entry.grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(fiscal_group, text="Closing Date (MM-DD):", font=("Segoe UI", 8, "bold")).grid(
            row=0, column=2, sticky="w", pady=2, padx=(12, 4)
        )
        self._fiscal_end_entry = ttk.Entry(fiscal_group, textvariable=self._comp_fiscal_end_var, width=10)
        self._fiscal_end_entry.grid(row=0, column=3, sticky="w", pady=2)

        # Quick preset buttons row
        preset_frame = ttk.Frame(fiscal_group)
        preset_frame.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 2))

        ttk.Label(preset_frame, text="Presets:", font=("Segoe UI", 7, "bold"), bootstyle="secondary").pack(side=tk.LEFT, padx=(0, 4))

        def _apply_preset(s, e):
            self._comp_fiscal_start_var.set(s)
            self._comp_fiscal_end_var.set(e)

        ttk.Button(
            preset_frame, text="Jan 1 - Dec 31 (Calendar)",
            bootstyle="link",
            command=lambda: _apply_preset("01-01", "12-31")
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            preset_frame, text="Apr 1 - Mar 31 (UK / South Asia)",
            bootstyle="link",
            command=lambda: _apply_preset("04-01", "03-31")
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            preset_frame, text="Jul 1 - Jun 30 (Mid-Year)",
            bootstyle="link",
            command=lambda: _apply_preset("07-01", "06-30")
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            preset_frame, text="Oct 1 - Sep 30 (US Fed)",
            bootstyle="link",
            command=lambda: _apply_preset("10-01", "09-30")
        ).pack(side=tk.LEFT, padx=2)

    def _sync_active_form_to_dict(self):
        """Persist currently displayed form entries back into self._companies_data dictionary."""
        if getattr(self, "_current_cid", None) is not None and self._current_cid in self._companies_data:
            entry = self._companies_data[self._current_cid]
            entry["name"] = self._comp_name_var.get().strip()
            entry["tagline"] = self._comp_tagline_var.get().strip()
            entry["address"] = self._comp_address_var.get().strip()
            entry["contact"] = self._comp_contact_var.get().strip()
            entry["email"] = self._comp_email_var.get().strip()
            entry["voucher_format"] = self._comp_fmt_var.get()
            entry["custom_prefix"] = self._comp_prefix_var.get().strip()
            entry["custom_start"] = self._comp_start_var.get().strip()
            entry["fiscal_year_start"] = self._comp_fiscal_start_var.get().strip() or "01-01"
            entry["fiscal_year_end"] = self._comp_fiscal_end_var.get().strip() or "12-31"

    def _populate_company_form(self, company_id):
        """Populate form widgets with profile data for company_id."""
        if company_id not in self._companies_data:
            return
        self._current_cid = company_id
        c = self._companies_data[company_id]

        self._comp_name_var.set(c.get("name", ""))
        self._comp_tagline_var.set(c.get("tagline", ""))
        self._comp_address_var.set(c.get("address", ""))
        self._comp_contact_var.set(c.get("contact", ""))
        self._comp_email_var.set(c.get("email", ""))
        self._comp_fmt_var.set(c.get("voucher_format") or "date_based")
        self._comp_prefix_var.set(c.get("custom_prefix") or f"C{company_id}-")
        self._comp_start_var.set(str(c.get("custom_start") or 1))
        self._comp_fiscal_start_var.set(c.get("fiscal_year_start") or "01-01")
        self._comp_fiscal_end_var.set(c.get("fiscal_year_end") or "12-31")

        active_id = db.get_active_company_id()
        if company_id == active_id:
            self._active_status_badge.config(text="● Active Company", bootstyle="success")
        else:
            self._active_status_badge.config(text="Profile (Inactive)", bootstyle="secondary")

        if c.get("logo_bytes") is not None:
            self._display_logo_preview(c["logo_bytes"])
        else:
            self._display_logo_preview(c.get("existing_logo"))

        self._on_format_change()

    def _refresh_company_selector(self, select_cid=None):
        """Refresh the combobox list of company profiles and select target company."""
        if not self._companies_data:
            return
        items = []
        cids = sorted(self._companies_data.keys())
        active_id = db.get_active_company_id()
        for cid in cids:
            name = self._companies_data[cid].get("name", f"Company {cid}")
            tag = " (Active)" if cid == active_id else ""
            items.append(f"[{cid}] {name}{tag}")

        self._comp_selector_cb["values"] = items
        target_cid = select_cid if select_cid in self._companies_data else cids[0]
        for idx, cid in enumerate(cids):
            if cid == target_cid:
                self._comp_selector_cb.current(idx)
                break
        self._populate_company_form(target_cid)

    def _on_company_selected(self, event=None):
        """User switched the profile combobox."""
        self._sync_active_form_to_dict()
        sel = self._comp_selector_cb.get()
        if not sel or not sel.startswith("["):
            return
        try:
            cid_str = sel[1:sel.index("]")]
            cid = int(cid_str)
            self._populate_company_form(cid)
        except Exception:
            pass

    def _add_new_company(self):
        """Direct users to the login screen for creating another company file."""
        messagebox.showinfo(
            "One company per file",
            "Close this company and choose Create Company on the sign-in "
            "screen. Each company is stored in its own database file.",
            parent=self,
        )
    def _delete_selected_company(self):
        """Prevent deleting the only company from inside its open file."""
        messagebox.showinfo(
            "Company file protection",
            "Company files are not deleted from inside the accounting "
            "workspace. Keep or archive the database file from the sign-in "
            "screen.",
            parent=self,
        )
    def _build_firebase_tab(self, parent):
        """Build the Firebase Cloud Firestore NoSQL configuration tab."""
        self._fb_enabled_var = tk.BooleanVar(value=True)
        self._fb_project_id_var = tk.StringVar()
        self._fb_api_key_var = tk.StringVar()
        self._fb_creds_path_var = tk.StringVar()
        self._fb_client_email_var = tk.StringVar()
        self._fb_prefix_var = tk.StringVar()
        self._fb_auto_sync_var = tk.BooleanVar(value=True)
        self._fb_status_text_var = tk.StringVar(value="Status: Not Configured")
        self._fb_last_sync_var = tk.StringVar(value="Last Synced: Never")

        # Scrollable container so all sections fit comfortably on any screen resolution
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#f8fafc")

        def _on_cloud_scroll(*args):
            canvas.yview(*args)
            canvas.update_idletasks()

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=_on_cloud_scroll)
        scrollable_frame = ttk.Frame(canvas, padding=(4, 4, 10, 4))

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        def _on_cloud_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            canvas.update_idletasks()
            return "break"

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.bind("<MouseWheel>", _on_cloud_mousewheel)
        scrollable_frame.bind("<MouseWheel>", _on_cloud_mousewheel)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── 1. Free Tier Info Banner ───────────────────────────────────────
        banner = tk.Frame(scrollable_frame, bg="#f0fdf4", highlightbackground="#86efac", highlightthickness=1, padx=12, pady=10)
        banner.pack(fill=tk.X, pady=(0, 10))

        b_title_row = tk.Frame(banner, bg="#f0fdf4")
        b_title_row.pack(fill=tk.X)
        tk.Label(
            b_title_row, text="🔥 Google Cloud Firestore NoSQL Database",
            font=("Segoe UI", 10, "bold"), bg="#f0fdf4", fg="#166534"
        ).pack(side=tk.LEFT)
        tk.Label(
            b_title_row, text="  ✅ 100% Free Database (Spark Plan)  ",
            font=("Segoe UI", 8, "bold"), bg="#15803d", fg="#ffffff", padx=6, pady=2
        ).pack(side=tk.RIGHT)

        tk.Label(
            banner,
            text="Any company can connect their own free Firebase project. Zero cost forever, no credit card required.\n"
                 "• Free Quotas: 1 GiB Cloud Storage • 50,000 Reads/Day • 20,000 Writes/Day • Real-Time Cloud Sync",
            font=("Segoe UI", 8), bg="#f0fdf4", fg="#14532d", justify="left"
        ).pack(anchor="w", pady=(4, 0))

        # ── 2. Firebase Connection Setup ───────────────────────────────────
        cred_group = ttk.LabelFrame(scrollable_frame, text="  1. Connect Your Firebase Database  ", padding=(12, 10, 12, 10))
        cred_group.pack(fill=tk.X, pady=(0, 10))

        # Fast Setup Button (Paste Web App Config snippet)
        paste_row = ttk.Frame(cred_group)
        paste_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(
            paste_row, text="📋 Paste Firebase Web Config / Snippet",
            command=self._paste_firebase_snippet, bootstyle="primary"
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            paste_row, text="🌐 Open Firestore in Firebase Console",
            command=self._open_project_console, bootstyle="outline-info"
        ).pack(side=tk.LEFT)

        self._fb_key_feedback_lbl = ttk.Label(
            cred_group, text="Paste your Firebase Web App snippet, or enter Project ID and API Key below.",
            font=("Segoe UI", 8), bootstyle="secondary"
        )
        self._fb_key_feedback_lbl.pack(anchor="w", pady=(0, 8))

        # Grid of fields
        grid_f = ttk.Frame(cred_group)
        grid_f.pack(fill=tk.X, pady=(0, 4))

        # Project ID
        ttk.Label(grid_f, text="Firebase Project ID:", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        proj_ent = ttk.Entry(grid_f, textvariable=self._fb_project_id_var, width=32)
        proj_ent.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(grid_f, text="(e.g. 'my-company-project')", font=("Segoe UI", 8), bootstyle="secondary").grid(row=0, column=2, sticky="w", padx=(6, 0))

        # Web API Key
        ttk.Label(grid_f, text="Firebase Web API Key:", font=("Segoe UI", 8, "bold")).grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        api_ent = ttk.Entry(grid_f, textvariable=self._fb_api_key_var, width=45)
        api_ent.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)

        # Collection Prefix
        ttk.Label(grid_f, text="Collection Prefix (Optional):", font=("Segoe UI", 8, "bold")).grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        prefix_ent = ttk.Entry(grid_f, textvariable=self._fb_prefix_var, width=20)
        prefix_ent.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(grid_f, text="(e.g. 'branch1_' or leave blank for 'vouchers')", font=("Segoe UI", 8), bootstyle="secondary").grid(row=2, column=2, sticky="w", padx=(6, 0))

        # Alternate Service Account Key Option
        sa_sep = ttk.Separator(cred_group, orient=tk.HORIZONTAL)
        sa_sep.pack(fill=tk.X, pady=(8, 6))

        sa_row = ttk.Frame(cred_group)
        sa_row.pack(fill=tk.X)
        ttk.Label(sa_row, text="Or Service Account Key (.json):", font=("Segoe UI", 8), bootstyle="secondary", width=24).pack(side=tk.LEFT)
        self._fb_creds_entry = ttk.Entry(sa_row, textvariable=self._fb_creds_path_var)
        self._fb_creds_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(
            sa_row, text="📂 Browse...",
            command=self._browse_firebase_key, bootstyle="outline-secondary"
        ).pack(side=tk.LEFT)

        # ── 3. Synchronization & Live Connectivity ────────────────────────
        sync_group = ttk.LabelFrame(scrollable_frame, text="  2. Cloud Sync Controls & Status  ", padding=(12, 8, 12, 10))
        sync_group.pack(fill=tk.X, pady=(0, 10))

        # Toggles
        chk_f = ttk.Frame(sync_group)
        chk_f.pack(fill=tk.X, pady=(2, 6))
        ttk.Checkbutton(
            chk_f, text="Enable Firebase Cloud Sync",
            variable=self._fb_enabled_var, bootstyle="round-toggle",
            command=self._on_fb_enabled_toggle
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Checkbutton(
            chk_f, text="Auto-sync vouchers immediately on Save / Edit / Cancel",
            variable=self._fb_auto_sync_var, bootstyle="primary"
        ).pack(side=tk.LEFT)

        # Status & Last Sync display
        stat_bar = tk.Frame(sync_group, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1, padx=10, pady=8)
        stat_bar.pack(fill=tk.X, pady=(4, 8))

        self._fb_status_lbl = tk.Label(
            stat_bar, textvariable=self._fb_status_text_var,
            font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#475569"
        )
        self._fb_status_lbl.pack(side=tk.LEFT)

        self._fb_last_sync_lbl = tk.Label(
            stat_bar, textvariable=self._fb_last_sync_var,
            font=("Segoe UI", 8), bg="#f1f5f9", fg="#64748b"
        )
        self._fb_last_sync_lbl.pack(side=tk.RIGHT)

        # Progress bar (hidden unless running)
        self._fb_prog_frame = ttk.Frame(sync_group)
        self._fb_progress_bar = ttk.Progressbar(self._fb_prog_frame, mode="determinate", bootstyle="success-striped")
        self._fb_progress_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 2))
        self._fb_progress_msg = ttk.Label(self._fb_prog_frame, text="", font=("Segoe UI", 8), bootstyle="secondary")
        self._fb_progress_msg.pack(side=tk.LEFT)

        # Action Buttons
        btn_row = ttk.Frame(sync_group)
        btn_row.pack(fill=tk.X, pady=(4, 2))

        self._fb_test_btn = ttk.Button(
            btn_row, text="⚡ Test Connection (Ping)",
            command=self._test_firebase_connection, bootstyle="outline-success"
        )
        self._fb_test_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._fb_upload_btn = ttk.Button(
            btn_row, text="⬆️ Upload All Local Data to Cloud",
            command=self._upload_all_to_cloud, bootstyle="outline-primary"
        )
        self._fb_upload_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._fb_download_btn = ttk.Button(
            btn_row, text="⬇️ Download / Pull from Cloud",
            command=self._pull_from_cloud, bootstyle="outline-secondary"
        )
        self._fb_download_btn.pack(side=tk.LEFT)

        # ── 4. Step-by-Step Free Setup Guide ───────────────────────────────
        guide_group = ttk.LabelFrame(scrollable_frame, text="  3. How Any Company Can Set Up Free Firebase in 3 Minutes  ", padding=(12, 8, 12, 10))
        guide_group.pack(fill=tk.X, pady=(0, 6))

        steps_text = (
            "1. Open https://console.firebase.google.com and create a project (e.g. 'MyCompany-Vouchers'). Free Spark Plan.\n"
            "2. In left menu, click 'Build' > 'Firestore Database' > 'Create database' > Choose location > Start in test mode.\n"
            "3. Click 'Project Settings ⚙️' > Scroll to 'Your apps' > Click '</>' (Web) > Copy the 'const firebaseConfig = { ... }'.\n"
            "4. Click '📋 Paste Firebase Web Config' above to automatically fill your Project ID and API Key.\n"
            "5. Click '⚡ Test Connection'. You're completely set up and ready to sync!"
        )
        tk.Label(
            guide_group, text=steps_text,
            font=("Segoe UI", 8), justify="left", fg="#334155"
        ).pack(anchor="w", pady=(2, 6))

    def _open_project_console(self):
        """Open the Firestore Database page for the configured project in default browser."""
        pid = self._fb_project_id_var.get().strip()
        url = f"https://console.firebase.google.com/project/{pid}/firestore" if pid else "https://console.firebase.google.com/"
        webbrowser.open(url)

    def _paste_firebase_snippet(self):
        """Extract Firebase config from clipboard or paste dialog."""
        raw_text = ""
        try:
            raw_text = self.clipboard_get()
        except Exception:
            pass

        if raw_text and ("apiKey" in raw_text or "projectId" in raw_text):
            self._apply_parsed_snippet(raw_text)
            return

        self._open_paste_snippet_dialog()

    def _apply_parsed_snippet(self, raw_text: str):
        """Parse snippet and populate form fields."""
        ok, data, err = firebase_client.parse_web_config_snippet(raw_text)
        if ok:
            p_id = data.get("projectId", "")
            key = data.get("apiKey", "")
            self._fb_project_id_var.set(p_id)
            self._fb_api_key_var.set(key)
            self._fb_enabled_var.set(True)

            self._fb_key_feedback_lbl.config(
                text=f"✅ Web Config loaded: Project '{p_id}'. Click 'Test Connection' to verify.",
                bootstyle="success"
            )
            self._fb_status_text_var.set("Status: Ready to test")
            self._fb_status_lbl.config(fg="#0284c7")
            messagebox.showinfo(
                "Firebase Config Detected",
                f"Successfully loaded configuration for:\n• Project ID: {p_id}\n• API Key: {key[:8]}...{key[-4:]}\n\nClick 'Test Connection' to test!",
                parent=self
            )
        else:
            messagebox.showerror("Parse Error", f"Could not detect Firebase Web Config:\n{err}", parent=self)

    def _open_paste_snippet_dialog(self):
        """Open a dialog window allowing the user to paste their JS firebaseConfig snippet."""
        top = tk.Toplevel(self)
        top.title("📋 Paste Firebase Web App Config")
        top.geometry("540x360")
        top.transient(self)
        top.grab_set()

        ttk.Label(
            top,
            text="Paste your 'const firebaseConfig = { ... }' JavaScript snippet below:",
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=12, pady=(12, 6))

        txt = tk.Text(top, height=11, font=("Consolas", 8))
        txt.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 10))
        txt.focus_set()

        btn_row = ttk.Frame(top, padding=(12, 0, 12, 12))
        btn_row.pack(fill=tk.X)

        def _on_submit():
            content = txt.get("1.0", tk.END).strip()
            top.destroy()
            if content:
                self._apply_parsed_snippet(content)

        ttk.Button(btn_row, text="✅ Apply Configuration", command=_on_submit, bootstyle="success").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Cancel", command=top.destroy, bootstyle="secondary").pack(side=tk.LEFT)

    def _browse_firebase_key(self):
        """Open file dialog to pick a Firebase Service Account JSON credentials file."""
        path = filedialog.askopenfilename(
            parent=self,
            title="Select Firebase Service Account JSON Key",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return

        success, dest_or_err, data = firebase_client.install_credentials_file(path)
        if success:
            self._fb_creds_path_var.set(dest_or_err)
            self._fb_project_id_var.set(data.get("project_id", ""))
            self._fb_client_email_var.set(data.get("client_email", ""))
            self._fb_key_feedback_lbl.config(
                text=f"✅ Key installed: Project '{data.get('project_id')}' ({data.get('client_email')})",
                bootstyle="success"
            )
            self._fb_status_text_var.set("Status: Ready to test")
            self._fb_status_lbl.config(fg="#0284c7")
            self._fb_enabled_var.set(True)
        else:
            self._fb_key_feedback_lbl.config(text=f"❌ {dest_or_err}", bootstyle="danger")
            messagebox.showerror("Invalid Firebase Key", dest_or_err, parent=self)

    def _on_fb_enabled_toggle(self):
        """Handle toggle of Firebase Cloud Sync checkbox."""
        if self._fb_enabled_var.get() and not self._fb_project_id_var.get() and not self._fb_creds_path_var.get():
            messagebox.showinfo(
                "Setup Needed",
                "Please paste your Firebase Web Config or enter your Project ID first.",
                parent=self
            )

    def _test_firebase_connection(self):
        """Run non-blocking connection test to Google Cloud Firestore."""
        creds_path = self._fb_creds_path_var.get().strip()
        project_id = self._fb_project_id_var.get().strip()
        api_key = self._fb_api_key_var.get().strip()

        if not (creds_path and os.path.exists(creds_path)) and not (project_id and api_key):
            messagebox.showwarning(
                "Missing Configuration",
                "Please paste your Firebase Web App configuration or browse a Service Account JSON file first.",
                parent=self
            )
            return

        self._fb_test_btn.config(state="disabled")
        self._fb_status_text_var.set("⚡ Connecting & Testing Firestore...")
        self._fb_status_lbl.config(fg="#d97706")

        def _worker():
            ok, msg, latency = firebase_client.test_connection(creds_path, project_id, api_key)
            def _ui_done():
                self._fb_test_btn.config(state="normal")
                if ok:
                    self._fb_status_text_var.set(f"🟢 Connected: {project_id} ({latency}ms) - Free Spark Active")
                    self._fb_status_lbl.config(fg="#16a34a")
                    messagebox.showinfo("Firebase Connected", msg, parent=self)
                else:
                    self._fb_status_text_var.set("🔴 Connection Attention Needed")
                    self._fb_status_lbl.config(fg="#dc2626")
                    messagebox.showwarning("Firebase Connection", msg, parent=self)

            if self.winfo_exists():
                self.after(0, _ui_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _upload_all_to_cloud(self):
        """Bulk upload all local vouchers, master data, and floats to Firestore."""
        if not firebase_client.is_configured():
            messagebox.showwarning("Not Configured", "Please connect your Firebase project first.", parent=self)
            return

        if not messagebox.askyesno(
            "Upload to Cloud",
            "This will upload all local vouchers, company profiles, categories, people, tags, and floats "
            "to your Google Firebase Cloud Firestore database.\n\nContinue?",
            parent=self
        ):
            return

        self._fb_upload_btn.config(state="disabled")
        self._fb_download_btn.config(state="disabled")
        self._fb_prog_frame.pack(fill=tk.X, pady=(4, 6))
        self._fb_progress_bar["value"] = 5
        self._fb_progress_msg.config(text="Connecting to Firestore...")

        def _progress(pct, msg):
            if self.winfo_exists():
                self.after(0, lambda: self._update_sync_progress(pct, msg))

        def _worker():
            ok, count, msg = firebase_client.upload_all_local_data(progress_callback=_progress)
            def _ui_done():
                self._fb_upload_btn.config(state="normal")
                self._fb_download_btn.config(state="normal")
                self._fb_prog_frame.pack_forget()
                if ok:
                    cfg = firebase_client.get_config()
                    self._fb_last_sync_var.set(f"Last Synced: {cfg.get('last_synced')}")
                    messagebox.showinfo("Upload Complete", msg, parent=self)
                else:
                    messagebox.showerror("Upload Error", msg, parent=self)

            if self.winfo_exists():
                self.after(0, _ui_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_sync_progress(self, pct, msg):
        """Update Firebase cloud sync progress bar and status text."""
        try:
            if hasattr(self, "_fb_progress_bar") and self._fb_progress_bar.winfo_exists():
                self._fb_progress_bar["value"] = pct
            if hasattr(self, "_fb_progress_msg") and self._fb_progress_msg.winfo_exists():
                self._fb_progress_msg.config(text=msg)
        except Exception:
            pass

    def _pull_from_cloud(self):
        """Pull vouchers from Firestore down to local SQLite database."""
        if not firebase_client.is_configured():
            messagebox.showwarning("Not Configured", "Please connect your Firebase project first.", parent=self)
            return

        if not messagebox.askyesno(
            "Download from Cloud",
            "This will download vouchers from Google Firebase Cloud Firestore and merge them into your local database.\n\nContinue?",
            parent=self
        ):
            return

        self._fb_upload_btn.config(state="disabled")
        self._fb_download_btn.config(state="disabled")
        self._fb_prog_frame.pack(fill=tk.X, pady=(4, 6))
        self._fb_progress_bar["value"] = 5
        self._fb_progress_msg.config(text="Fetching vouchers from Firestore...")

        def _progress(pct, msg):
            if self.winfo_exists():
                self.after(0, lambda: self._update_sync_progress(pct, msg))

        def _worker():
            ok, count, msg = firebase_client.pull_cloud_vouchers(progress_callback=_progress)
            def _ui_done():
                self._fb_upload_btn.config(state="normal")
                self._fb_download_btn.config(state="normal")
                self._fb_prog_frame.pack_forget()
                if ok:
                    cfg = firebase_client.get_config()
                    self._fb_last_sync_var.set(f"Last Synced: {cfg.get('last_synced')}")
                    messagebox.showinfo("Sync Complete", msg, parent=self)
                else:
                    messagebox.showerror("Sync Error", msg, parent=self)

            if self.winfo_exists():
                self.after(0, _ui_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _build_gdrive_tab(self, parent):
        """Construct the Google Drive cloud storage and backup settings tab."""
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#ffffff")

        def _on_gdrive_scroll(*args):
            canvas.yview(*args)
            canvas.update_idletasks()

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=_on_gdrive_scroll)
        scrollable_frame = ttk.Frame(canvas, padding=12)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        def _on_gdrive_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            canvas.update_idletasks()
            return "break"

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.bind("<MouseWheel>", _on_gdrive_mousewheel)
        scrollable_frame.bind("<MouseWheel>", _on_gdrive_mousewheel)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._gd_enabled_var = tk.BooleanVar(value=False)
        self._gd_folder_path_var = tk.StringVar(value="")
        self._gd_organize_var = tk.BooleanVar(value=True)
        self._gd_backup_db_var = tk.BooleanVar(value=True)
        self._gd_status_text_var = tk.StringVar(value="Status: Not Configured")
        self._gd_last_sync_var = tk.StringVar(value="Last Synced: Never")
        self._gd_stats_var = tk.StringVar(value="Attachments: 0 total")

        # 1. Info Banner
        banner = tk.Frame(scrollable_frame, bg="#eff6ff", highlightbackground="#93c5fd", highlightthickness=1, padx=12, pady=10)
        banner.pack(fill=tk.X, pady=(0, 10))

        b_title_row = tk.Frame(banner, bg="#eff6ff")
        b_title_row.pack(fill=tk.X)
        tk.Label(
            b_title_row, text="📁 Google Drive Cloud Storage & Safe Backup",
            font=("Segoe UI", 10, "bold"), bg="#eff6ff", fg="#1e40af"
        ).pack(side=tk.LEFT)
        tk.Label(
            b_title_row, text="  ✅ 15 GB Free Storage Forever  ",
            font=("Segoe UI", 8, "bold"), bg="#2563eb", fg="#ffffff", padx=6, pady=2
        ).pack(side=tk.RIGHT)

        tk.Label(
            banner,
            text="Every Google account includes 15 GB of 100% free cloud storage with zero expiration.\n"
                 "• Automatically syncs voucher attachments (receipts, bills, PDFs) to your Google Drive.\n"
                 "• Automatically saves SQLite database snapshots for full disaster recovery.",
            font=("Segoe UI", 8), bg="#eff6ff", fg="#1e3a8a", justify="left"
        ).pack(anchor="w", pady=(4, 0))

        # 2. Folder Configuration
        cfg_group = ttk.LabelFrame(scrollable_frame, text="  1. Google Drive Folder Setup  ", padding=(12, 10, 12, 10))
        cfg_group.pack(fill=tk.X, pady=(0, 10))

        chk_row = ttk.Frame(cfg_group)
        chk_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(
            chk_row, text="Enable Google Drive Attachment & Database Sync",
            variable=self._gd_enabled_var, bootstyle="round-toggle",
            command=self._on_gd_enabled_toggle
        ).pack(side=tk.LEFT)

        path_lbl_row = ttk.Frame(cfg_group)
        path_lbl_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(path_lbl_row, text="Google Drive Folder Path:", font=("Segoe UI", 8, "bold")).pack(side=tk.LEFT)
        ttk.Label(path_lbl_row, text="(e.g. 'G:\\My Drive\\Vouchers' or 'C:\\Users\\...\\Google Drive')", font=("Segoe UI", 8), bootstyle="secondary").pack(side=tk.LEFT, padx=(6, 0))

        path_entry_row = ttk.Frame(cfg_group)
        path_entry_row.pack(fill=tk.X, pady=(0, 6))

        self._gd_entry = ttk.Entry(path_entry_row, textvariable=self._gd_folder_path_var)
        self._gd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ttk.Button(
            path_entry_row, text="📂 Browse...",
            command=self._browse_gdrive_folder, bootstyle="outline-primary"
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            path_entry_row, text="🔍 Auto-Detect",
            command=self._auto_detect_gdrive, bootstyle="info-outline"
        ).pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(
            path_entry_row, text="📁 Open Folder",
            command=self._open_gdrive_explorer, bootstyle="secondary-outline"
        ).pack(side=tk.LEFT)

        self._gd_feedback_lbl = ttk.Label(
            cfg_group, text="", font=("Segoe UI", 8), bootstyle="secondary"
        )
        self._gd_feedback_lbl.pack(anchor="w", pady=(0, 6))

        opt_box = ttk.Frame(cfg_group)
        opt_box.pack(fill=tk.X, pady=(4, 0))

        ttk.Checkbutton(
            opt_box, text="Organize attachments into subfolders by Month (e.g. Voucher_Attachments/2026-10/Voucher_XXXX/)",
            variable=self._gd_organize_var, bootstyle="primary"
        ).pack(anchor="w", pady=2)

        ttk.Checkbutton(
            opt_box, text="Automatically copy SQLite database snapshots (vouchers.db) to Google Drive",
            variable=self._gd_backup_db_var, bootstyle="primary"
        ).pack(anchor="w", pady=2)

        # 3. Synchronization & Backup Controls
        sync_group = ttk.LabelFrame(scrollable_frame, text="  2. Cloud Backup Tools & Status  ", padding=(12, 10, 12, 10))
        sync_group.pack(fill=tk.X, pady=(0, 10))

        stat_bar = tk.Frame(sync_group, bg="#f1f5f9", highlightbackground="#cbd5e1", highlightthickness=1, padx=10, pady=8)
        stat_bar.pack(fill=tk.X, pady=(0, 8))

        self._gd_status_lbl = tk.Label(
            stat_bar, textvariable=self._gd_status_text_var,
            font=("Segoe UI", 9, "bold"), bg="#f1f5f9", fg="#475569"
        )
        self._gd_status_lbl.pack(side=tk.LEFT)

        self._gd_last_sync_lbl = tk.Label(
            stat_bar, textvariable=self._gd_last_sync_var,
            font=("Segoe UI", 8), bg="#f1f5f9", fg="#64748b"
        )
        self._gd_last_sync_lbl.pack(side=tk.RIGHT)

        stats_f = ttk.Frame(sync_group)
        stats_f.pack(fill=tk.X, pady=(0, 8))
        self._gd_stats_lbl = ttk.Label(stats_f, textvariable=self._gd_stats_var, font=("Segoe UI", 8), bootstyle="secondary")
        self._gd_stats_lbl.pack(side=tk.LEFT)

        btn_row = ttk.Frame(sync_group)
        btn_row.pack(fill=tk.X, pady=(0, 6))

        self._gd_sync_all_btn = ttk.Button(
            btn_row, text="🚀 Sync All Existing Attachments Now",
            command=self._sync_all_gdrive_attachments, bootstyle="primary"
        )
        self._gd_sync_all_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._gd_backup_db_btn = ttk.Button(
            btn_row, text="💾 Backup Database Snapshot to Google Drive",
            command=self._backup_db_to_gdrive, bootstyle="outline-success"
        )
        self._gd_backup_db_btn.pack(side=tk.LEFT)

        # Progress bar frame
        self._gd_prog_frame = ttk.Frame(sync_group)
        self._gd_progress_bar = ttk.Progressbar(self._gd_prog_frame, orient=tk.HORIZONTAL, mode="determinate", bootstyle="primary-striped")
        self._gd_progress_bar.pack(fill=tk.X, pady=(4, 2))
        self._gd_progress_msg = ttk.Label(self._gd_prog_frame, text="", font=("Segoe UI", 8), bootstyle="secondary")
        self._gd_progress_msg.pack(anchor="w")

    def _on_gd_enabled_toggle(self):
        enabled = self._gd_enabled_var.get()
        if enabled:
            path = self._gd_folder_path_var.get().strip()
            if not path:
                self._auto_detect_gdrive()
            else:
                self._validate_gd_path_display(path)
        else:
            self._gd_status_text_var.set("Status: Disabled")
            self._gd_status_lbl.config(fg="#64748b")

    def _validate_gd_path_display(self, path):
        ok, res = gdrive_client.validate_folder_path(path)
        if ok:
            self._gd_feedback_lbl.config(text=f"✅ Folder found & accessible: {res}", bootstyle="success")
            self._gd_status_text_var.set("Status: Connected & Ready")
            self._gd_status_lbl.config(fg="#16a34a")
        else:
            self._gd_feedback_lbl.config(text=f"⚠️ {res}", bootstyle="warning")
            self._gd_status_text_var.set("Status: Folder Inaccessible")
            self._gd_status_lbl.config(fg="#dc2626")

    def _browse_gdrive_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Select Google Drive Sync Folder")
        if folder:
            self._gd_folder_path_var.set(folder)
            self._validate_gd_path_display(folder)
            self._gd_enabled_var.set(True)

    def _auto_detect_gdrive(self):
        detected = gdrive_client.detect_google_drive_paths()
        if detected:
            self._gd_folder_path_var.set(detected[0])
            self._validate_gd_path_display(detected[0])
            self._gd_enabled_var.set(True)
            messagebox.showinfo("Google Drive Detected", f"Found Google Drive at:\n{detected[0]}", parent=self)
        else:
            messagebox.showinfo(
                "Auto-Detect",
                "Google Drive for Desktop was not detected at standard drive paths (e.g. 'G:\\My Drive').\n\n"
                "Please click 'Browse...' to select your Google Drive folder, or download Google Drive for Desktop from google.com/drive.",
                parent=self
            )

    def _open_gdrive_explorer(self):
        path = self._gd_folder_path_var.get().strip()
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Folder Not Found", "The specified folder does not exist or has not been chosen.", parent=self)

    def _sync_all_gdrive_attachments(self):
        path = self._gd_folder_path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Folder Required", "Please select a valid Google Drive folder first.", parent=self)
            return

        gdrive_client.save_config({
            "enabled": True,
            "folder_path": path,
            "backup_database": self._gd_backup_db_var.get(),
            "organize_by_month": self._gd_organize_var.get(),
        })

        self._gd_sync_all_btn.config(state="disabled")
        self._gd_backup_db_btn.config(state="disabled")
        self._gd_prog_frame.pack(fill=tk.X, pady=(4, 6))
        self._gd_progress_bar["value"] = 5
        self._gd_progress_msg.config(text="Scanning attachments to sync...")

        def _progress(pct, msg):
            if self.winfo_exists():
                self.after(0, lambda: self._update_gd_progress(pct, msg))

        def _worker():
            ok, count, msg = gdrive_client.sync_all_existing_attachments(progress_callback=_progress)
            def _ui_done():
                self._gd_sync_all_btn.config(state="normal")
                self._gd_backup_db_btn.config(state="normal")
                self._gd_prog_frame.pack_forget()
                self._refresh_gd_stats()
                if ok:
                    messagebox.showinfo("Sync Complete", msg, parent=self)
                else:
                    messagebox.showerror("Sync Error", msg, parent=self)
            if self.winfo_exists():
                self.after(0, _ui_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_gd_progress(self, pct, msg):
        try:
            self._gd_progress_bar["value"] = pct
            self._gd_progress_msg.config(text=msg)
        except Exception:
            pass

    def _backup_db_to_gdrive(self):
        path = self._gd_folder_path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showwarning("Folder Required", "Please select a valid Google Drive folder first.", parent=self)
            return
        gdrive_client.save_config({"enabled": True, "folder_path": path})
        dest = gdrive_client.backup_database_to_gdrive()
        if dest:
            self._refresh_gd_stats()
            messagebox.showinfo("Backup Saved", f"Database snapshot successfully backed up to Google Drive:\n\n{dest}", parent=self)
        else:
            messagebox.showerror("Backup Failed", "Could not save database backup to Google Drive. Check folder permissions.", parent=self)

    def _refresh_gd_stats(self):
        st = gdrive_client.get_status()
        self._gd_last_sync_var.set(f"Last Synced: {st.get('last_synced') or 'Never'}")
        self._gd_stats_var.set(f"Attachments in DB: {st['total_attachments']} | Synced to Drive: {st['synced_attachments']} | Free Cloud: 15 GB")

    def _load_all_values(self):

        """Load settings, company data, and Firebase configuration from database."""
        # 1. Company profiles
        self._companies_data = {}
        all_comps = db.get_all_companies()
        if not all_comps:
            all_comps = [db.get_company(1) or {"id": 1, "name": "Company 1"}]

        for comp in all_comps:
            company_id = comp["id"]
            self._companies_data[company_id] = {
                "id": company_id,
                "name": comp.get("name", f"Company {company_id}"),
                "tagline": comp.get("tagline", ""),
                "address": comp.get("address", ""),
                "contact": comp.get("contact", ""),
                "email": comp.get("email", ""),
                "voucher_format": comp.get("voucher_format") or "date_based",
                "custom_prefix": comp.get("custom_prefix") or (f"C{company_id}-" if company_id != 1 else "V-"),
                "custom_start": str(comp.get("custom_start") or 1),
                "fiscal_year_start": comp.get("fiscal_year_start") or "01-01",
                "fiscal_year_end": comp.get("fiscal_year_end") or "12-31",
                "logo_bytes": None,
                "existing_logo": comp.get("logo"),
                "photo_img": None
            }

        # Select currently active company by default
        active_id = db.get_active_company_id()
        init_cid = active_id if active_id in self._companies_data else min(self._companies_data.keys())
        self._refresh_company_selector(select_cid=init_cid)

        # 2. Firebase settings
        fb_cfg = firebase_client.get_config()
        self._fb_enabled_var.set(fb_cfg["enabled"])
        self._fb_project_id_var.set(fb_cfg["project_id"])
        self._fb_api_key_var.set(fb_cfg["api_key"])
        self._fb_creds_path_var.set(fb_cfg["creds_path"])
        self._fb_client_email_var.set(fb_cfg.get("client_email", ""))
        self._fb_prefix_var.set(fb_cfg["collection_prefix"])
        self._fb_auto_sync_var.set(fb_cfg["auto_sync"])
        last_sync = fb_cfg.get("last_synced") or "Never"
        self._fb_last_sync_var.set(f"Last Synced: {last_sync}")

        if firebase_client.is_configured():
            p_id = fb_cfg.get("project_id") or "Configured"
            self._fb_status_text_var.set(f"Status: Configured ({p_id})")
            self._fb_status_lbl.config(fg="#16a34a")
            self._fb_key_feedback_lbl.config(
                text=f"Loaded configuration for project '{p_id}'. Click 'Test Connection' to verify.",
                bootstyle="success"
            )
        else:
            self._fb_status_text_var.set("Status: Not Configured")
            self._fb_status_lbl.config(fg="#64748b")

        # 3. Google Drive settings
        gd_cfg = gdrive_client.get_config()
        self._gd_enabled_var.set(gd_cfg["enabled"])
        self._gd_folder_path_var.set(gd_cfg["folder_path"])
        self._gd_organize_var.set(gd_cfg["organize_by_month"])
        self._gd_backup_db_var.set(gd_cfg["backup_database"])
        self._refresh_gd_stats()

        if gd_cfg["enabled"] and gd_cfg["folder_path"]:
            self._validate_gd_path_display(gd_cfg["folder_path"])
        else:
            self._gd_status_text_var.set("Status: Disabled" if not gd_cfg["enabled"] else "Status: Path Needed")
            self._gd_status_lbl.config(fg="#64748b")


    def _choose_logo(self):
        """File dialog to choose image file for logo."""
        if not getattr(self, "_current_cid", None):
            return
        cid = self._current_cid
        cname = self._companies_data[cid].get("name", f"Company {cid}")
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Choose Logo for {cname}",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                ("All Files", "*.*")
            ]
        )
        if path:
            try:
                with open(path, "rb") as f:
                    raw_bytes = f.read()
                self._companies_data[cid]["logo_bytes"] = raw_bytes
                self._display_logo_preview(raw_bytes)
            except Exception as e:
                messagebox.showerror("Image Error", f"Could not load image file:\n{e}", parent=self)

    def _remove_logo(self):
        """Remove company logo."""
        if not getattr(self, "_current_cid", None):
            return
        cid = self._current_cid
        self._companies_data[cid]["logo_bytes"] = b""  # Empty bytes means delete
        self._companies_data[cid]["photo_img"] = None
        self._logo_preview.config(image="", text="No Logo\nUploaded")

    def _display_logo_preview(self, img_bytes):
        """Render a neat thumbnail in the preview label."""
        if not img_bytes:
            self._logo_preview.config(image="", text="No Logo\nUploaded")
            return
        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                rgba = pil_img.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                pil_img = Image.alpha_composite(bg, rgba).convert("RGB")
            # Resize thumbnail preserving aspect ratio
            pil_img.thumbnail((140, 70), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(pil_img)
            self._active_logo_photo = photo
            self._logo_preview.config(image=photo, text="")
        except Exception:
            self._logo_preview.config(image="", text="[Image error]")

    def _on_format_change(self):
        """Handle voucher numbering format radio button change."""
        fmt = self._comp_fmt_var.get()
        state = "normal" if fmt == "custom" else "disabled"
        self._prefix_entry.configure(state=state)
        self._start_entry.configure(state=state)
        self._update_preview()

    def _update_preview(self):
        """Update voucher numbering preview labels."""
        if not getattr(self, "_current_cid", None):
            return
        fmt = self._comp_fmt_var.get()
        prefix = self._comp_prefix_var.get()
        start = self._comp_start_var.get()

        override = {
            "voucher_format": fmt,
            "custom_prefix": prefix,
            "custom_start": start
        }
        try:
            preview = db.preview_next_voucher_number(settings_override=override, company_id=self._current_cid)
        except Exception:
            preview = "Error"

        if fmt == "date_based":
            self._preview_date_lbl.config(text=preview)
            self._preview_month_lbl.config(text="")
            self._preview_custom_lbl.config(text="")
        elif fmt == "month_based":
            self._preview_month_lbl.config(text=preview)
            self._preview_date_lbl.config(text="")
            self._preview_custom_lbl.config(text="")
        else:
            self._preview_custom_lbl.config(text=preview)
            self._preview_date_lbl.config(text="")
            self._preview_month_lbl.config(text="")

    def _save(self):
        """Save settings, company profiles, and Firebase configuration."""
        self._sync_active_form_to_dict()

        for company_id, c_data in self._companies_data.items():
            name = c_data.get("name", "").strip()
            if not name:
                messagebox.showwarning("Validation", f"Company ID {company_id} name cannot be empty.", parent=self)
                self._comp_selector_cb.set(f"[{company_id}] {name}")
                self._populate_company_form(company_id)
                return

            fmt = c_data.get("voucher_format", "date_based")
            prefix = c_data.get("custom_prefix", "").strip()
            start_str = str(c_data.get("custom_start", "1")).strip()

            if fmt == "custom":
                if not prefix:
                    messagebox.showwarning("Validation", f"Company '{name}' prefix cannot be empty.", parent=self)
                    self._populate_company_form(company_id)
                    return
                try:
                    start_num = int(start_str)
                    if start_num < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning("Validation", f"Company '{name}' start number must be a positive integer.", parent=self)
                    self._populate_company_form(company_id)
                    return
            else:
                start_num = 1

            save_payload = {
                "name": name,
                "tagline": c_data.get("tagline", "").strip(),
                "address": c_data.get("address", "").strip(),
                "contact": c_data.get("contact", "").strip(),
                "email": c_data.get("email", "").strip(),
                "voucher_format": fmt,
                "custom_prefix": prefix,
                "custom_start": start_num,
                "fiscal_year_start": c_data.get("fiscal_year_start") or "01-01",
                "fiscal_year_end": c_data.get("fiscal_year_end") or "12-31",
            }

            # Only include logo if user changed or removed it
            if c_data.get("logo_bytes") is not None:
                save_payload["logo"] = c_data["logo_bytes"]

            db.save_company(company_id, save_payload)

        # Save Firebase settings
        fb_cfg = {
            "enabled": self._fb_enabled_var.get(),
            "project_id": self._fb_project_id_var.get().strip(),
            "api_key": self._fb_api_key_var.get().strip(),
            "creds_path": self._fb_creds_path_var.get().strip(),
            "client_email": self._fb_client_email_var.get().strip(),
            "collection_prefix": self._fb_prefix_var.get().strip(),
            "auto_sync": self._fb_auto_sync_var.get(),
        }
        firebase_client.save_config(fb_cfg)

        # Trigger client reinit if service account key is enabled
        if fb_cfg["enabled"] and fb_cfg["creds_path"]:
            threading.Thread(target=lambda: firebase_client.get_firestore_client(force_reinit=True), daemon=True).start()

        # Save Google Drive settings
        gd_cfg = {
            "enabled": self._gd_enabled_var.get(),
            "folder_path": self._gd_folder_path_var.get().strip(),
            "backup_database": self._gd_backup_db_var.get(),
            "organize_by_month": self._gd_organize_var.get(),
        }
        gdrive_client.save_config(gd_cfg)

        messagebox.showinfo("Saved", "Settings, company profiles, Firebase cloud, and Google Drive configuration saved successfully.", parent=self)

        if self._on_saved_callback:
            try:
                self._on_saved_callback()
            except Exception:
                pass
        self.destroy()

    def _open_clear_vouchers(self):
        """Open the password-protected clear vouchers dialog."""
        from ui import dialogs
        def on_cleared(scope):
            if self._on_saved_callback:
                try:
                    self._on_saved_callback()
                except Exception:
                    pass
        dialogs.ClearVouchersDialog(self, on_success_callback=on_cleared)
