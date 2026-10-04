"""
Smart Alerts Center UI.
Provides a slide-in panel or dialog to view and manage proactive alerts.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

import database as db


class AlertCenterDialog(tk.Toplevel):
    """Dialog displaying the Alert Center."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()  # Prevent visual glitching while rendering
        self.title("Alerts & Notifications")
        self.geometry("480x600")
        self.minsize(400, 500)
        self.transient(parent)
        
        # Don't grab_set() so user can keep it open while working
        
        self._company_id = db.get_active_company_id()
        
        # Generate new alerts before showing
        db.generate_alerts(self._company_id)
        
        self._build_ui()
        self._refresh_list()

        # Place on the right side of parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() - self.winfo_width() - 20
        py = parent.winfo_rooty() + 60
        self.geometry(f"+{max(0,px)}+{max(0,py)}")
        self.deiconify()

        self.lift()
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
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=12)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="🔔 Alerts Center", font=("Segoe UI", 12, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(side=tk.LEFT)
                 
        ttk.Button(header, text="Mark All Read", command=self._mark_all_read,
                   bootstyle="secondary-link").pack(side=tk.RIGHT)

        # Scrollable list
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._canvas = tk.Canvas(list_frame, bg="#f8fafc", highlightthickness=0)

        def _on_alert_scroll(*args):
            self._canvas.yview(*args)
            self._canvas.update_idletasks()

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=_on_alert_scroll)
        
        self._content = ttk.Frame(self._canvas)
        self._content.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        
        # Need to capture window ID to resize it when canvas resizes
        self._window_id = self._canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        
        self._canvas.configure(yscrollcommand=scrollbar.set)
        
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Footer
        footer = ttk.Frame(self, padding=8)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(footer, text="Dismiss All", command=self._dismiss_all,
                   bootstyle="warning-outline").pack(side=tk.LEFT)
                   
        ttk.Button(footer, text="Settings", command=self._open_settings,
                   bootstyle="info-outline").pack(side=tk.LEFT, padx=8)
                   
        ttk.Button(footer, text="Close", command=self.destroy,
                   bootstyle="secondary").pack(side=tk.RIGHT)

    def _on_canvas_configure(self, event):
        # Make the inner frame expand to canvas width
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _refresh_list(self):
        for w in self._content.winfo_children():
            w.destroy()
            
        alerts = db.get_active_alerts(self._company_id)
        
        if not alerts:
            tk.Label(self._content, text="You're all caught up!\nNo active alerts.", 
                     font=("Segoe UI", 10), fg="#94a3b8", justify="center").pack(pady=40)
            return
            
        colors = {
            "critical": ("#fee2e2", "#ef4444", "🔴"),
            "warning": ("#fef3c7", "#f59e0b", "🟡"),
            "info": ("#eff6ff", "#3b82f6", "🔵")
        }

        for a in alerts:
            bg_color, fg_color, icon = colors.get(a["severity"], colors["info"])
            if a["is_read"]:
                bg_color = "#ffffff"  # Read alerts have white background
            
            card = tk.Frame(self._content, bg=bg_color, highlightbackground="#e2e8f0", highlightthickness=1)
            card.pack(fill=tk.X, pady=4, padx=4)
            
            # Left edge color strip
            strip = tk.Frame(card, bg=fg_color, width=4)
            strip.pack(side=tk.LEFT, fill=tk.Y)
            
            # Content area
            inner = tk.Frame(card, bg=bg_color, padx=12, pady=10)
            inner.pack(fill=tk.BOTH, expand=True)
            
            # Header
            hdr = tk.Frame(inner, bg=bg_color)
            hdr.pack(fill=tk.X)
            tk.Label(hdr, text=f"{icon} {a['title']}", font=("Segoe UI", 10, "bold"), 
                     bg=bg_color, fg="#0f172a").pack(side=tk.LEFT)
            
            # Message
            tk.Label(inner, text=a["message"], font=("Segoe UI", 9), 
                     bg=bg_color, fg="#475569", justify="left", wraplength=380).pack(anchor="w", pady=(4, 8))
            
            # Actions
            acts = tk.Frame(inner, bg=bg_color)
            acts.pack(fill=tk.X)
            
            ttk.Button(acts, text="Dismiss", 
                       command=lambda aid=a["id"]: self._dismiss_single(aid),
                       bootstyle="secondary-link").pack(side=tk.RIGHT)
                       
            if not a["is_read"]:
                ttk.Button(acts, text="Mark Read", 
                           command=lambda aid=a["id"]: self._mark_read_single(aid),
                           bootstyle="info-link").pack(side=tk.RIGHT, padx=8)

        self._bind_mousewheel_recursive(self._content)

    def _mark_all_read(self):
        db.mark_all_alerts_read(self._company_id)
        self._refresh_list()

    def _dismiss_all(self):
        if messagebox.askyesno("Dismiss All", "Are you sure you want to dismiss all active alerts?", parent=self):
            db.dismiss_all_alerts(self._company_id)
            self._refresh_list()

    def _mark_read_single(self, alert_id):
        db.mark_alert_read(alert_id)
        self._refresh_list()

    def _dismiss_single(self, alert_id):
        db.dismiss_alert(alert_id)
        self._refresh_list()

    def _open_settings(self):
        """Open alert preferences configuration dialog."""
        dlg = AlertPreferencesDialog(self, company_id=self._company_id, on_save=self._refresh_list)
        self.wait_window(dlg)
        self._refresh_list()


class AlertPreferencesDialog(tk.Toplevel):
    """Dialog to enable/disable specific alert types and configure threshold triggers."""

    ALERT_NAMES = {
        "overdue_payment": ("Overdue Payments", "Alerts when vouchers pass their due date"),
        "budget_warning": ("Budget Warning (%)", "Alerts when category budget reaches threshold %"),
        "budget_exceeded": ("Budget Exceeded", "Alerts when category spending exceeds 100%"),
        "float_low_balance": ("Float Low Balance (Min)", "Alerts when a cash float drops below threshold"),
        "float_overdrawn": ("Float Overdrawn", "Critical alert when a float balance goes negative"),
        "pending_approval": ("Pending Approvals", "Alerts for vouchers awaiting approval over 24h"),
        "unprinted_vouchers": ("Unprinted Vouchers", "Alerts when unprinted active vouchers accumulate"),
    }

    def __init__(self, parent, company_id=1, on_save=None):
        super().__init__(parent)
        self._company_id = company_id
        self._on_save = on_save

        self.title("Alert Preferences & Thresholds")
        self.geometry("560x520")
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._build_ui()

        # Center
        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0,px)}+{max(0,py)}")

        self.lift()
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())

    def _build_ui(self):
        header = tk.Frame(self, bg="#0f172a", padx=16, pady=10)
        header.pack(fill=tk.X)
        tk.Label(header, text="⚙️ Alert Preferences", font=("Segoe UI", 12, "bold"),
                 bg="#0f172a", fg="#ffffff").pack(anchor="w")
        tk.Label(header, text="Enable or disable proactive alert rules and set custom trigger thresholds",
                 font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(anchor="w", pady=(2, 0))

        content = ttk.Frame(self, padding=16)
        content.pack(fill=tk.BOTH, expand=True)

        prefs = db.get_alert_preferences(self._company_id)
        self._pref_widgets = {}

        for i, p in enumerate(prefs):
            atype = p["alert_type"]
            title, desc = self.ALERT_NAMES.get(atype, (atype.replace("_", " ").title(), ""))

            row = ttk.Frame(content)
            row.pack(fill=tk.X, pady=6)

            en_var = tk.BooleanVar(value=bool(p.get("is_enabled", 1)))
            cb = ttk.Checkbutton(row, text=title, variable=en_var)
            cb.pack(side=tk.LEFT)

            thresh_var = None
            if atype in ("budget_warning", "float_low_balance", "unprinted_vouchers"):
                thresh_val = p.get("threshold_value")
                if thresh_val is None:
                    thresh_val = 80.0 if atype == "budget_warning" else (5000.0 if atype == "float_low_balance" else 5)
                thresh_var = tk.StringVar(value=str(thresh_val))
                ttk.Label(row, text="Threshold:", font=("Segoe UI", 8), foreground="#64748b").pack(side=tk.LEFT, padx=(12, 4))
                ttk.Entry(row, textvariable=thresh_var, width=8).pack(side=tk.LEFT)

            self._pref_widgets[p["id"]] = (en_var, thresh_var)

        footer = ttk.Frame(self, padding=(16, 12))
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(footer, text="Save Preferences", command=self._save_preferences,
                   bootstyle="success").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(footer, text="Cancel", command=self.destroy,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT)

    def _save_preferences(self):
        for pid, (en_var, thresh_var) in self._pref_widgets.items():
            is_en = en_var.get()
            t_val = None
            if thresh_var:
                try:
                    t_val = float(thresh_var.get())
                except ValueError:
                    pass
            db.update_alert_preference(pid, is_enabled=is_en, threshold_value=t_val)

        db.generate_alerts(self._company_id)
        if self._on_save:
            self._on_save()
        messagebox.showinfo("Saved", "Alert preferences updated successfully.", parent=self)
        self.destroy()

