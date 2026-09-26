"""
Settings Dialog
Configure voucher header customization, two independent company profiles,
logo upload (saved in DB as BLOB), and voucher numbering format.
"""

import io
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image, ImageTk

import database as db


class SettingsDialog(tk.Toplevel):
    """Application settings dialog supporting two independent company profiles."""

    def __init__(self, parent, on_saved_callback=None):
        super().__init__(parent)
        self.title("⚙️ Voucher & Company Profile Settings")
        self.resizable(False, False)
        self.geometry("640x560")
        self.transient(parent)
        self.grab_set()

        self._on_saved_callback = on_saved_callback
        self._companies_data = {}  # {company_id: {...widgets and variables...}}

        self._build_ui()
        self._load_all_values()

        # Center dialog
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

        self.lift()
        self.focus_force()

        self.bind("<Escape>", lambda e: (self.destroy(), "break")[1])
        self.bind("<Return>", lambda e: self._save())

    def _build_ui(self):
        # ── Top Title Bar ──────────────────────────────────────────────────
        header = ttk.Frame(self, padding=(16, 12, 16, 6))
        header.pack(fill=tk.X)
        ttk.Label(
            header, text="⚙️ Settings: Voucher Header & Company Profiles",
            font=("Segoe UI", 12, "bold"), bootstyle="primary"
        ).pack(side=tk.LEFT)

        sep = ttk.Separator(self, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, padx=12, pady=(0, 6))

        # ── Notebook with Company 1 and Company 2 ──────────────────────────
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))

        tab1 = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(tab1, text="  🏢 Company 1 Profile  ")
        self._build_company_tab(tab1, company_id=1)

        tab2 = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(tab2, text="  🏢 Company 2 Profile  ")
        self._build_company_tab(tab2, company_id=2)

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
            text="* Logo stored in DB as BLOB; headers reflect immediately on printed vouchers.",
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
        logo_preview.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        data_dict["logo_preview"] = logo_preview

        ttk.Button(
            logo_group, text="📁 Upload Logo...",
            command=lambda: self._choose_logo(company_id),
            bootstyle="primary-outline", width=14
        ).pack(fill=tk.X, pady=2)

        ttk.Button(
            logo_group, text="❌ Remove Logo",
            command=lambda: self._remove_logo(company_id),
            bootstyle="danger-outline", width=14
        ).pack(fill=tk.X, pady=2)

        # ── 3. Voucher Numbering Format ────────────────────────────────────
        num_group = ttk.LabelFrame(left_col, text="  Independent Voucher Numbering  ", padding=(10, 6, 10, 8))
        num_group.pack(fill=tk.X)

        # 3.1 Daily Date-based
        rb1 = ttk.Radiobutton(
            num_group, text="Daily Date-based  (e.g. V-20260918-001, resets daily)",
            variable=data_dict["fmt_var"], value="date_based",
            command=lambda: self._on_format_change(company_id)
        )
        rb1.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 1))

        ttk.Label(num_group, text="Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=1, column=0, sticky="w", padx=(16, 4)
        )
        data_dict["preview_date_lbl"] = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        data_dict["preview_date_lbl"].grid(row=1, column=1, columnspan=2, sticky="w", pady=(0, 2))

        # 3.2 Monthly Format (e.g. 26AUG_01)
        rb_month = ttk.Radiobutton(
            num_group, text="Monthly Format  (e.g. 26AUG_01, resets monthly)",
            variable=data_dict["fmt_var"], value="month_based",
            command=lambda: self._on_format_change(company_id)
        )
        rb_month.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2, 1))

        ttk.Label(num_group, text="Preview:", font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=3, column=0, sticky="w", padx=(16, 4)
        )
        data_dict["preview_month_lbl"] = ttk.Label(num_group, text="", font=("Consolas", 8, "bold"), bootstyle="success")
        data_dict["preview_month_lbl"].grid(row=3, column=1, columnspan=2, sticky="w", pady=(0, 2))

        # 3.3 Custom Prefix + Sequential
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

    def _load_all_values(self):
        """Load settings and company data from database."""
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
        """Save settings and both company profiles."""
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

        messagebox.showinfo("Saved", "Company profiles and voucher header settings saved successfully.", parent=self)
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
