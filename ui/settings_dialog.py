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
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

import database as db
import firebase_client


class SettingsDialog(tk.Toplevel):
    """Application settings dialog supporting company profiles & Firebase Cloud Database."""

    def __init__(self, parent, on_saved_callback=None, initial_tab=0):
        super().__init__(parent)
        self.title("⚙️ Settings: Profiles & Firebase Cloud Database")
        self.resizable(True, True)
        self.geometry("780x640")
        self.minsize(700, 580)
        self.transient(parent)
        self.grab_set()

        self._on_saved_callback = on_saved_callback
        self._initial_tab = initial_tab
        self._companies_data = {}  # {company_id: {...widgets and variables...}}

        self._build_ui()
        self._load_all_values()

        # Handle requested initial tab (0: Company 1, 1: Company 2, 2: Firebase)
        if str(initial_tab).lower() in ("cloud", "firebase", "2"):
            try:
                self._notebook.select(2)
            except Exception:
                pass
        elif isinstance(initial_tab, int) and 0 <= initial_tab < 3:
            try:
                self._notebook.select(initial_tab)
            except Exception:
                pass

        # Center dialog
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

        self.lift()
        self.focus_force()

        self.bind("<Escape>", lambda e: (self.destroy(), "break")[1])
        self.bind("<Return>", lambda e: self._save())

    def _build_ui(self):
        # ── Top Title Bar ──────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="⚙️ Settings: Profiles, Voucher Headers & Firebase Cloud NoSQL",
            font=("Segoe UI", 12, "bold"), bootstyle="primary"
        ).pack(side=tk.LEFT)

        sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ── Notebook with Company 1, Company 2, and Firebase Cloud ─────────
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        tab1 = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(tab1, text="  🏢 Company 1 Profile  ")
        self._build_company_tab(tab1, company_id=1)

        tab2 = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(tab2, text="  🏢 Company 2 Profile  ")
        self._build_company_tab(tab2, company_id=2)

        tab3 = ttk.Frame(self._notebook, padding=8)
        self._notebook.add(tab3, text="  ☁️ Firebase Cloud Database (NoSQL)  ")
        self._build_firebase_tab(tab3)

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

    def _build_company_tab(self, parent, company_id):
        """Build the profile settings form for a specific company ID."""
        data_dict = {
            "name_var": tk.StringVar(),
            "tagline_var": tk.StringVar(),
            "address_var": tk.StringVar(),
            "contact_var": tk.StringVar(),
            "email_var": tk.StringVar(),
            "fmt_var": tk.StringVar(value="date_based"),
            "prefix_var": tk.StringVar(value=f"C{company_id}-" if company_id == 2 else "V-"),
            "start_var": tk.StringVar(value="1"),
            "logo_bytes": None,      # None = unchanged, b"" = remove, bytes = new logo
            "photo_img": None,       # Image reference
        }
        self._companies_data[company_id] = data_dict

        # Outer grid with 2 columns: Left = Details & Format, Right = Logo Card
        content_frame = ttk.Frame(parent)
        content_frame.pack(fill=tk.BOTH, expand=True)

        left_col = ttk.Frame(content_frame)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right_col = ttk.Frame(content_frame, width=170)
        right_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))

        # ── 1. Company Header Information ──────────────────────────────────
        info_group = ttk.LabelFrame(left_col, text="  Header & Contact Details  ", padding=(10, 6, 10, 8))
        info_group.pack(fill=tk.X, pady=(0, 8))

        fields = [
            ("Company Name:", data_dict["name_var"], 28),
            ("Tagline / Slogan:", data_dict["tagline_var"], 28),
            ("Physical Address:", data_dict["address_var"], 28),
            ("Contact / Phone:", data_dict["contact_var"], 24),
            ("Email Address:", data_dict["email_var"], 24),
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

        # Thumbnail canvas / label
        logo_preview = tk.Label(
            logo_group, text="No Logo\nUploaded",
            bg="#f1f5f9", fg="#64748b", font=("Segoe UI", 8),
            relief="groove", width=16, height=6
        )
        logo_preview.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        data_dict["logo_preview"] = logo_preview

        # Upload / Remove buttons
        btn_box = ttk.Frame(logo_group)
        btn_box.pack(fill=tk.X)

        ttk.Button(
            btn_box, text="📂 Choose...",
            command=lambda cid=company_id: self._choose_logo(cid),
            bootstyle="outline-primary"
        ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))

        ttk.Button(
            btn_box, text="🗑️",
            command=lambda cid=company_id: self._remove_logo(cid),
            bootstyle="outline-danger"
        ).pack(side=tk.LEFT)

        ttk.Label(
            logo_group, text="Supports PNG, JPG, BMP\nScaled to fit headers.",
            font=("Segoe UI", 7), bootstyle="secondary", justify="center"
        ).pack(pady=(4, 0))

        # ── 3. Numbering Format Configuration ──────────────────────────────
        num_group = ttk.LabelFrame(left_col, text="  Voucher Numbering Scheme  ", padding=(10, 6, 10, 8))
        num_group.pack(fill=tk.X)

        # Option A: Daily Date-Based
        rb0 = ttk.Radiobutton(
            num_group, text="Daily Date-Based (e.g. 26OCT03_01)",
            variable=data_dict["fmt_var"], value="date_based",
            command=lambda: self._on_format_change(company_id)
        )
        rb0.grid(row=0, column=0, columnspan=3, sticky="w", pady=1)

        ttk.Label(num_group, text="Format: YYMMMDD_## • Resets daily. Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=1, column=0, sticky="w", padx=(16, 0), pady=(0, 3)
        )
        data_dict["preview_date_lbl"] = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        data_dict["preview_date_lbl"].grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 3))

        # Option B: Monthly Date-Based
        rb1 = ttk.Radiobutton(
            num_group, text="Monthly Sequential (e.g. 26AUG_01)",
            variable=data_dict["fmt_var"], value="month_based",
            command=lambda: self._on_format_change(company_id)
        )
        rb1.grid(row=2, column=0, columnspan=3, sticky="w", pady=1)

        ttk.Label(num_group, text="Format: YYMMM_## • Resets monthly. Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=3, column=0, sticky="w", padx=(16, 0), pady=(0, 3)
        )
        data_dict["preview_month_lbl"] = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        data_dict["preview_month_lbl"].grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 3))

        # Option C: Custom Sequential
        rb2 = ttk.Radiobutton(
            num_group, text="Custom Prefix + Sequential Number",
            variable=data_dict["fmt_var"], value="custom",
            command=lambda: self._on_format_change(company_id)
        )
        rb2.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 1))

        ttk.Label(num_group, text="Prefix:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=5, column=0, sticky="w", padx=(16, 4)
        )
        prefix_ent = ttk.Entry(num_group, textvariable=data_dict["prefix_var"], width=10)
        prefix_ent.grid(row=5, column=1, sticky="w", padx=2, pady=1)
        data_dict["prefix_entry"] = prefix_ent
        data_dict["prefix_var"].trace_add("write", lambda *_: self._update_preview(company_id))

        ttk.Label(num_group, text="Start #:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=5, column=2, sticky="w", padx=(8, 4)
        )
        start_ent = ttk.Entry(num_group, textvariable=data_dict["start_var"], width=8)
        start_ent.grid(row=5, column=3, sticky="w", padx=2, pady=1)
        data_dict["start_entry"] = start_ent
        data_dict["start_var"].trace_add("write", lambda *_: self._update_preview(company_id))

        ttk.Label(num_group, text="Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=6, column=0, sticky="w", padx=(16, 4), pady=(1, 0)
        )
        data_dict["preview_custom_lbl"] = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        data_dict["preview_custom_lbl"].grid(row=6, column=1, columnspan=3, sticky="w", pady=(1, 0))

    def _build_firebase_tab(self, parent):
        """Build the Firebase Cloud Firestore NoSQL configuration tab."""
        self._fb_enabled_var = tk.BooleanVar(value=False)
        self._fb_creds_path_var = tk.StringVar()
        self._fb_project_id_var = tk.StringVar()
        self._fb_client_email_var = tk.StringVar()
        self._fb_prefix_var = tk.StringVar()
        self._fb_auto_sync_var = tk.BooleanVar(value=True)
        self._fb_status_text_var = tk.StringVar(value="Status: Not Configured")
        self._fb_last_sync_var = tk.StringVar(value="Last Synced: Never")

        # Scrollable container so all sections fit comfortably on any screen resolution
        canvas = tk.Canvas(parent, highlightthickness=0, bg="#f8fafc")
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, padding=(4, 4, 10, 4))

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

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
            text="Any company can connect their own free Firebase project. No credit card required.\n"
                 "• Free Quotas: 1 GiB Cloud Storage • 50,000 Reads/Day • 20,000 Writes/Day • Real-Time Cloud Sync",
            font=("Segoe UI", 8), bg="#f0fdf4", fg="#14532d", justify="left"
        ).pack(anchor="w", pady=(4, 0))

        # ── 2. Firebase Credentials & Project Setup ────────────────────────
        cred_group = ttk.LabelFrame(scrollable_frame, text="  1. Connect Your Firebase Database  ", padding=(12, 8, 12, 10))
        cred_group.pack(fill=tk.X, pady=(0, 10))

        # Credentials JSON File Row
        r0 = ttk.Frame(cred_group)
        r0.pack(fill=tk.X, pady=(2, 4))
        ttk.Label(r0, text="Service Account Key (.json):", font=("Segoe UI", 8, "bold"), width=24).pack(side=tk.LEFT)
        self._fb_creds_entry = ttk.Entry(r0, textvariable=self._fb_creds_path_var)
        self._fb_creds_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(
            r0, text="📂 Browse Key...",
            command=self._browse_firebase_key, bootstyle="outline-primary"
        ).pack(side=tk.LEFT)

        self._fb_key_feedback_lbl = ttk.Label(
            cred_group, text="Upload your Firebase Service Account JSON private key file.",
            font=("Segoe UI", 8), bootstyle="secondary"
        )
        self._fb_key_feedback_lbl.pack(anchor="w", pady=(0, 6))

        # Project ID & Email Rows
        grid_f = ttk.Frame(cred_group)
        grid_f.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(grid_f, text="Firebase Project ID:", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=3, padx=(0, 8))
        proj_ent = ttk.Entry(grid_f, textvariable=self._fb_project_id_var, width=28)
        proj_ent.grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(grid_f, text="Service Account Email:", font=("Segoe UI", 8, "bold")).grid(row=1, column=0, sticky="w", pady=3, padx=(0, 8))
        email_ent = ttk.Entry(grid_f, textvariable=self._fb_client_email_var, width=38, state="readonly")
        email_ent.grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(grid_f, text="Collection Prefix (Optional):", font=("Segoe UI", 8, "bold")).grid(row=2, column=0, sticky="w", pady=3, padx=(0, 8))
        prefix_ent = ttk.Entry(grid_f, textvariable=self._fb_prefix_var, width=20)
        prefix_ent.grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(grid_f, text="(e.g. 'branch1_' to isolate collections, or blank for default 'vouchers')", font=("Segoe UI", 8), bootstyle="secondary").grid(row=2, column=2, sticky="w", padx=(6, 0))

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
        guide_group = ttk.LabelFrame(scrollable_frame, text="  3. How Any Company Can Set Up Free Firebase (3-Minute Guide)  ", padding=(12, 8, 12, 10))
        guide_group.pack(fill=tk.X, pady=(0, 6))

        steps_text = (
            "1. Open https://console.firebase.google.com and sign in with any Google account.\n"
            "2. Click 'Add project' (e.g. 'MyCompany-Vouchers'). The Spark Plan is 100% Free.\n"
            "3. In the left menu, click 'Build' > 'Firestore Database' > 'Create database' (choose nearest location).\n"
            "4. Go to Project Settings ⚙️ (top-left gear icon) > 'Service accounts' tab.\n"
            "5. Click 'Generate new private key' to download your credentials (.json) file.\n"
            "6. Click 'Browse Key...' above, select the downloaded file, and click 'Test Connection'. You're done!"
        )
        tk.Label(
            guide_group, text=steps_text,
            font=("Segoe UI", 8), justify="left", fg="#334155"
        ).pack(anchor="w", pady=(2, 6))

        g_btn_row = ttk.Frame(guide_group)
        g_btn_row.pack(fill=tk.X)
        ttk.Button(
            g_btn_row, text="🌐 Open Firebase Console in Browser",
            command=lambda: webbrowser.open("https://console.firebase.google.com/"),
            bootstyle="info-outline"
        ).pack(side=tk.LEFT)

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
            # Auto-enable cloud sync checkbox for convenience
            self._fb_enabled_var.set(True)
        else:
            self._fb_key_feedback_lbl.config(text=f"❌ {dest_or_err}", bootstyle="danger")
            messagebox.showerror("Invalid Firebase Key", dest_or_err, parent=self)

    def _on_fb_enabled_toggle(self):
        """Handle toggle of Firebase Cloud Sync checkbox."""
        if self._fb_enabled_var.get() and not self._fb_creds_path_var.get():
            messagebox.showinfo(
                "Credentials Needed",
                "Please browse and select your Firebase Service Account JSON key first.",
                parent=self
            )

    def _test_firebase_connection(self):
        """Run non-blocking connection test to Google Cloud Firestore."""
        creds_path = self._fb_creds_path_var.get().strip()
        project_id = self._fb_project_id_var.get().strip()

        if not creds_path or not os.path.exists(creds_path):
            messagebox.showwarning(
                "Missing Credentials",
                "Please select a valid Firebase Service Account JSON file first.",
                parent=self
            )
            return

        self._fb_test_btn.config(state="disabled")
        self._fb_status_text_var.set("⚡ Connecting & Testing Firestore...")
        self._fb_status_lbl.config(fg="#d97706")

        def _worker():
            ok, msg, latency = firebase_client.test_connection(creds_path, project_id)
            def _ui_done():
                self._fb_test_btn.config(state="normal")
                if ok:
                    self._fb_status_text_var.set(f"🟢 Connected: {project_id} ({latency}ms) - Free Spark Active")
                    self._fb_status_lbl.config(fg="#16a34a")
                    messagebox.showinfo("Firebase Connected", msg, parent=self)
                else:
                    self._fb_status_text_var.set("🔴 Connection Failed")
                    self._fb_status_lbl.config(fg="#dc2626")
                    messagebox.showerror("Firebase Connection Error", msg, parent=self)

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

    def _update_sync_progress(self, pct, msg):
        """Update progress bar and label safely on main UI thread."""
        try:
            self._fb_progress_bar["value"] = pct
            self._fb_progress_msg.config(text=msg)
        except Exception:
            pass

    def _load_all_values(self):
        """Load settings, company data, and Firebase configuration from database."""
        # 1. Company profiles
        for company_id in (1, 2):
            comp = db.get_company(company_id) or {}
            c_data = self._companies_data[company_id]

            c_data["name_var"].set(comp.get("name", f"Company {company_id}"))
            c_data["tagline_var"].set(comp.get("tagline", ""))
            c_data["address_var"].set(comp.get("address", ""))
            c_data["contact_var"].set(comp.get("contact", ""))
            c_data["email_var"].set(comp.get("email", ""))
            c_data["fmt_var"].set(comp.get("voucher_format") or "date_based")
            c_data["prefix_var"].set(comp.get("custom_prefix") or (f"C{company_id}-" if company_id == 2 else "V-"))
            c_data["start_var"].set(str(comp.get("custom_start") or 1))

            # Load existing logo preview
            logo_blob = comp.get("logo")
            if logo_blob:
                self._display_logo_preview(company_id, logo_blob)

            self._on_format_change(company_id)

        # 2. Firebase settings
        fb_cfg = firebase_client.get_config()
        self._fb_enabled_var.set(fb_cfg["enabled"])
        self._fb_creds_path_var.set(fb_cfg["creds_path"])
        self._fb_project_id_var.set(fb_cfg["project_id"])
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
                text=f"Loaded credentials for project '{p_id}'. Click 'Test Connection' to verify.",
                bootstyle="success"
            )
        else:
            self._fb_status_text_var.set("Status: Not Configured")
            self._fb_status_lbl.config(fg="#64748b")

    def _choose_logo(self, company_id):
        """File dialog to choose image file for logo."""
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Choose Logo for Company {company_id}",
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif"),
                ("All Files", "*.*")
            ]
        )
        if path:
            try:
                with open(path, "rb") as f:
                    raw_bytes = f.read()
                self._companies_data[company_id]["logo_bytes"] = raw_bytes
                self._display_logo_preview(company_id, raw_bytes)
            except Exception as e:
                messagebox.showerror("Image Error", f"Could not load image file:\n{e}", parent=self)

    def _remove_logo(self, company_id):
        """Remove company logo."""
        self._companies_data[company_id]["logo_bytes"] = b""  # Empty bytes means delete
        self._companies_data[company_id]["photo_img"] = None
        preview = self._companies_data[company_id]["logo_preview"]
        preview.config(image="", text="No Logo\nUploaded")

    def _display_logo_preview(self, company_id, img_bytes):
        """Render a neat thumbnail in the preview label."""
        try:
            pil_img = Image.open(io.BytesIO(img_bytes))
            if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                rgba = pil_img.convert("RGBA")
                bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                pil_img = Image.alpha_composite(bg, rgba).convert("RGB")
            # Resize thumbnail preserving aspect ratio
            pil_img.thumbnail((120, 70), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(pil_img)
            self._companies_data[company_id]["photo_img"] = photo
            preview = self._companies_data[company_id]["logo_preview"]
            preview.config(image=photo, text="")
        except Exception:
            preview = self._companies_data[company_id]["logo_preview"]
            preview.config(image="", text="[Image error]")

    def _on_format_change(self, company_id):
        c_data = self._companies_data[company_id]
        fmt = c_data["fmt_var"].get()
        state = "normal" if fmt == "custom" else "disabled"
        c_data["prefix_entry"].configure(state=state)
        c_data["start_entry"].configure(state=state)
        self._update_preview(company_id)

    def _update_preview(self, company_id):
        c_data = self._companies_data[company_id]
        fmt = c_data["fmt_var"].get()
        prefix = c_data["prefix_var"].get()
        start = c_data["start_var"].get()

        override = {
            "voucher_format": fmt,
            "custom_prefix": prefix,
            "custom_start": start
        }
        try:
            preview = db.preview_next_voucher_number(settings_override=override, company_id=company_id)
        except Exception:
            preview = "Error"

        if fmt == "date_based":
            c_data["preview_date_lbl"].config(text=preview)
            c_data["preview_month_lbl"].config(text="")
            c_data["preview_custom_lbl"].config(text="")
        elif fmt == "month_based":
            c_data["preview_month_lbl"].config(text=preview)
            c_data["preview_date_lbl"].config(text="")
            c_data["preview_custom_lbl"].config(text="")
        else:
            c_data["preview_custom_lbl"].config(text=preview)
            c_data["preview_date_lbl"].config(text="")
            c_data["preview_month_lbl"].config(text="")

    def _save(self):
        """Save settings, company profiles, and Firebase configuration."""
        for company_id in (1, 2):
            c_data = self._companies_data[company_id]
            name = c_data["name_var"].get().strip()
            if not name:
                messagebox.showwarning("Validation", f"Company {company_id} name cannot be empty.", parent=self)
                self._notebook.select(company_id - 1)
                return

            fmt = c_data["fmt_var"].get()
            prefix = c_data["prefix_var"].get().strip()
            start_str = c_data["start_var"].get().strip()

            if fmt == "custom":
                if not prefix:
                    messagebox.showwarning("Validation", f"Company {company_id} prefix cannot be empty.", parent=self)
                    self._notebook.select(company_id - 1)
                    return
                try:
                    start_num = int(start_str)
                    if start_num < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showwarning("Validation", f"Company {company_id} start number must be a positive integer.", parent=self)
                    self._notebook.select(company_id - 1)
                    return
            else:
                start_num = 1

            save_payload = {
                "name": name,
                "tagline": c_data["tagline_var"].get().strip(),
                "address": c_data["address_var"].get().strip(),
                "contact": c_data["contact_var"].get().strip(),
                "email": c_data["email_var"].get().strip(),
                "voucher_format": fmt,
                "custom_prefix": prefix,
                "custom_start": start_num,
            }

            # Only include logo if user changed or removed it
            if c_data["logo_bytes"] is not None:
                save_payload["logo"] = c_data["logo_bytes"]

            db.save_company(company_id, save_payload)

        # Save Firebase settings
        fb_cfg = {
            "enabled": self._fb_enabled_var.get(),
            "creds_path": self._fb_creds_path_var.get().strip(),
            "project_id": self._fb_project_id_var.get().strip(),
            "client_email": self._fb_client_email_var.get().strip(),
            "collection_prefix": self._fb_prefix_var.get().strip(),
            "auto_sync": self._fb_auto_sync_var.get(),
        }
        firebase_client.save_config(fb_cfg)

        # Trigger client reinit if enabled
        if fb_cfg["enabled"] and fb_cfg["creds_path"]:
            threading.Thread(target=lambda: firebase_client.get_firestore_client(force_reinit=True), daemon=True).start()

        messagebox.showinfo("Saved", "Settings, company profiles, and Firebase cloud configuration saved successfully.", parent=self)
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
