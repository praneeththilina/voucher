"""
Analytics Dashboard — Tab 4: Visual Charts & Reports.
Provides at-a-glance spending insights using Tkinter Canvas native drawing.
No external charting dependencies required.
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap import ToolTip
from tkinter import filedialog, messagebox
from datetime import datetime
import math
import csv

import database as db


# ---------------------------------------------------------------------------
# Chart Color Palette (Modern, Accessible)
# ---------------------------------------------------------------------------
CHART_COLORS = [
    "#3b82f6",  # Blue
    "#22c55e",  # Green
    "#f59e0b",  # Amber
    "#ef4444",  # Red
    "#8b5cf6",  # Violet
    "#06b6d4",  # Cyan
    "#ec4899",  # Pink
    "#f97316",  # Orange
    "#14b8a6",  # Teal
    "#a855f7",  # Purple
    "#64748b",  # Slate
    "#84cc16",  # Lime
]


class AnalyticsDashboard(ttk.Frame):
    """Embedded analytics dashboard frame for Tab 4 of the main notebook."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._company_id = db.get_active_company_id()
        self._date_filter = "This Month"
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # ── Top Control Bar ──
        top_bar = tk.Frame(self, bg="#f8fafc", highlightbackground="#e2e8f0", highlightthickness=1)
        top_bar.pack(fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(top_bar, text="  Analytics Dashboard", font=("Segoe UI", 13, "bold"),
                 bg="#f8fafc", fg="#0f172a").pack(side=tk.LEFT, padx=(8, 16), pady=8)

        tk.Label(top_bar, text="Period:", font=("Segoe UI", 9), bg="#f8fafc", fg="#475569").pack(side=tk.LEFT)

        self._period_var = tk.StringVar(value="This Month")
        period_combo = ttk.Combobox(top_bar, textvariable=self._period_var, width=14,
                                    values=["This Month", "Last Month", "This Year", "All Time"],
                                    state="readonly")
        period_combo.pack(side=tk.LEFT, padx=(4, 12), pady=6)
        period_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(top_bar, text="Refresh", command=self.refresh,
                   bootstyle="info-outline").pack(side=tk.RIGHT, padx=8, pady=6)
        ttk.Button(top_bar, text="📊 Export CSV", command=self._export_csv,
                   bootstyle="secondary-outline").pack(side=tk.RIGHT, padx=4, pady=6)

        # ── Scrollable Content Area ──
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._scroll_canvas = tk.Canvas(canvas_frame, bg="#ffffff", highlightthickness=0, borderwidth=0)
        self._scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self._on_scroll)
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        self._content_frame = tk.Frame(self._scroll_canvas, bg="#ffffff")
        self._content_window = self._scroll_canvas.create_window((0, 0), window=self._content_frame, anchor="nw")

        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self._content_frame.bind("<Configure>", self._on_content_configure)

        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._scroll_canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _on_canvas_configure(self, event):
        """Keep the content frame stretched to the full viewport width."""
        if event.width > 10:
            self._scroll_canvas.itemconfig(self._content_window, width=event.width)

    def _on_content_configure(self, event=None):
        """Update scrollable region when content changes."""
        self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))

    def _on_scroll(self, *args):
        """Scroll the canvas and flush pending paint tasks to prevent Windows ghosting."""
        self._scroll_canvas.yview(*args)
        self._scroll_canvas.update_idletasks()

    def _on_mousewheel(self, event):
        """Smooth mousewheel scroll that updates immediately."""
        delta = int(-1 * (event.delta / 120))
        self._scroll_canvas.yview_scroll(delta, "units")
        self._scroll_canvas.update_idletasks()
        return "break"

    def _bind_mousewheel_recursive(self, widget):
        """Recursively bind mouse wheel to all descendant widgets so scroll works anywhere."""
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def refresh(self):
        """Refresh all dashboard data and redraw charts."""
        self._company_id = db.get_active_company_id()
        self._date_filter = self._period_var.get()

        # Clear existing content
        for widget in self._content_frame.winfo_children():
            widget.destroy()

        try:
            self._draw_kpi_cards()
            self._draw_spending_trend()
            self._draw_category_breakdown()
            self._draw_payee_leaderboard()
            self._draw_due_date_aging()
            self._draw_payment_distribution()
        except Exception as e:
            tk.Label(self._content_frame, text=f"Error loading dashboard: {e}",
                     font=("Segoe UI", 10), fg="#ef4444", bg="#ffffff").pack(pady=20)

        # Propagate mouse wheel bindings across all dynamically created children
        self._bind_mousewheel_recursive(self._content_frame)
        self._on_content_configure()

    def _draw_kpi_cards(self):
        """Draw the top KPI summary cards."""
        stats = db.get_voucher_stats(self._company_id)
        aging = db.get_due_date_aging(self._company_id)

        cards_frame = tk.Frame(self._content_frame, bg="#ffffff")
        cards_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        kpi_data = [
            ("Total Spent", f"{stats.get('total_amount', 0):,.2f}", "#3b82f6", "LKR"),
            ("Vouchers", str(stats.get("total_vouchers", 0)), "#22c55e", "active"),
            ("Overdue", str(aging["overdue"]["count"]), "#ef4444",
             f"{aging['overdue']['total']:,.0f}"),
            ("Bills Pending", str(stats.get("bills_pending", 0)), "#f59e0b", "vouchers"),
        ]

        for i, (title, value, color, subtitle) in enumerate(kpi_data):
            card = tk.Frame(cards_frame, bg=color, padx=2, pady=2)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)

            inner = tk.Frame(card, bg="#ffffff", padx=12, pady=10)
            inner.pack(fill=tk.BOTH, expand=True)

            tk.Label(inner, text=title, font=("Segoe UI", 8), bg="#ffffff", fg="#64748b").pack(anchor="w")
            tk.Label(inner, text=value, font=("Segoe UI", 16, "bold"), bg="#ffffff", fg=color).pack(anchor="w")
            tk.Label(inner, text=subtitle, font=("Segoe UI", 8), bg="#ffffff", fg="#94a3b8").pack(anchor="w")

    def _draw_spending_trend(self):
        """Draw monthly spending bar chart."""
        trend = db.get_monthly_spending_trend(self._company_id, months=12)
        if not trend:
            return

        section = tk.LabelFrame(self._content_frame, text="  Monthly Spending Trend (Last 12 Months)",
                                font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff", padx=8, pady=8)
        section.pack(fill=tk.X, padx=8, pady=(8, 4))

        chart_w, chart_h = 700, 180
        canvas = tk.Canvas(section, width=chart_w, height=chart_h, bg="#ffffff",
                           highlightthickness=0)
        canvas.pack(fill=tk.X, expand=True, pady=4)

        if not trend:
            canvas.create_text(chart_w // 2, chart_h // 2, text="No data available",
                               font=("Segoe UI", 10), fill="#94a3b8")
            return

        max_val = max(t["total"] for t in trend) or 1
        bar_w = max(20, (chart_w - 60) // max(len(trend), 1))
        x_offset = 50

        # Y-axis labels
        for i in range(5):
            y = 10 + (chart_h - 40) * i / 4
            val = max_val * (4 - i) / 4
            canvas.create_text(x_offset - 5, y, text=f"{val:,.0f}", anchor="e",
                               font=("Segoe UI", 7), fill="#94a3b8")
            canvas.create_line(x_offset, y, chart_w - 10, y, fill="#f1f5f9", width=1)

        # Bars
        for i, t in enumerate(trend):
            x = x_offset + i * bar_w + 5
            bar_height = (t["total"] / max_val) * (chart_h - 50) if max_val > 0 else 0
            y_top = chart_h - 30 - bar_height
            y_bot = chart_h - 30

            canvas.create_rectangle(x, y_top, x + bar_w - 8, y_bot,
                                    fill="#3b82f6", outline="#2563eb", width=1)

            # Month label
            month_label = t["month"][-2:] if len(t["month"]) >= 7 else t["month"]
            canvas.create_text(x + (bar_w - 8) // 2, y_bot + 10, text=month_label,
                               font=("Segoe UI", 7), fill="#64748b")

            # Value on top of bar (if tall enough)
            if bar_height > 20:
                canvas.create_text(x + (bar_w - 8) // 2, y_top - 8,
                                   text=f"{t['total']:,.0f}", font=("Segoe UI", 6), fill="#475569")

    def _draw_category_breakdown(self):
        """Draw category spending breakdown as horizontal bars."""
        breakdown = db.get_category_spending_breakdown(self._company_id, self._date_filter)
        if not breakdown:
            return

        section = tk.LabelFrame(self._content_frame, text="  Expense Breakdown by Category",
                                font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff", padx=8, pady=8)
        section.pack(fill=tk.X, padx=8, pady=(8, 4))

        max_val = max(b["total"] for b in breakdown) or 1

        for i, b in enumerate(breakdown[:10]):
            row = tk.Frame(section, bg="#ffffff")
            row.pack(fill=tk.X, pady=3)

            color = CHART_COLORS[i % len(CHART_COLORS)]

            # Category name
            tk.Label(row, text=f"{b['category']}", font=("Segoe UI", 9),
                     bg="#ffffff", fg="#0f172a", width=18, anchor="w").pack(side=tk.LEFT, padx=(0, 8))

            # Progress bar canvas (eliminates .place() desync and tearing)
            bar_pct = (b["total"] / max_val)
            bar_canvas = tk.Canvas(row, height=14, bg="#f1f5f9", highlightthickness=0)
            bar_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

            def _paint_cat(event, cv=bar_canvas, pct=bar_pct, col=color):
                cv.delete("all")
                w = max(4, int(event.width * pct))
                cv.create_rectangle(0, 0, w, event.height, fill=col, outline="")

            bar_canvas.bind("<Configure>", _paint_cat)

            # Amount and percentage
            tk.Label(row, text=f"{b['total']:,.0f} ({b['percentage']:.0f}%)",
                     font=("Segoe UI", 8), bg="#ffffff", fg="#64748b",
                     width=18, anchor="e").pack(side=tk.RIGHT)

    def _draw_payee_leaderboard(self):
        """Draw top payees by spending."""
        payees = db.get_top_payees(self._company_id, limit=8, date_filter=self._date_filter)
        if not payees:
            return

        section = tk.LabelFrame(self._content_frame, text="  Top Payees by Spending",
                                font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff", padx=8, pady=8)
        section.pack(fill=tk.X, padx=8, pady=(8, 4))

        max_val = max(p["total"] for p in payees) or 1

        for i, p in enumerate(payees):
            row = tk.Frame(section, bg="#ffffff")
            row.pack(fill=tk.X, pady=3)

            color = CHART_COLORS[i % len(CHART_COLORS)]
            rank = f"#{i + 1}"

            tk.Label(row, text=rank, font=("Segoe UI", 8, "bold"),
                     bg="#ffffff", fg=color, width=3).pack(side=tk.LEFT)

            tk.Label(row, text=p["payee"], font=("Segoe UI", 9),
                     bg="#ffffff", fg="#0f172a", width=20, anchor="w").pack(side=tk.LEFT, padx=(4, 8))

            bar_pct = (p["total"] / max_val)
            bar_canvas = tk.Canvas(row, height=14, bg="#f1f5f9", highlightthickness=0)
            bar_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

            def _paint_payee(event, cv=bar_canvas, pct=bar_pct, col=color):
                cv.delete("all")
                w = max(4, int(event.width * pct))
                cv.create_rectangle(0, 0, w, event.height, fill=col, outline="")

            bar_canvas.bind("<Configure>", _paint_payee)

            tk.Label(row, text=f"{p['total']:,.0f} ({p['count']} v.)",
                     font=("Segoe UI", 8), bg="#ffffff", fg="#64748b",
                     width=18, anchor="e").pack(side=tk.RIGHT)

    def _draw_due_date_aging(self):
        """Draw due date aging buckets."""
        aging = db.get_due_date_aging(self._company_id)

        section = tk.LabelFrame(self._content_frame, text="  Due Date Aging Report",
                                font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff", padx=8, pady=8)
        section.pack(fill=tk.X, padx=8, pady=(8, 4))

        buckets = [
            ("Overdue", aging["overdue"], "#ef4444"),
            ("Due Today", aging["due_today"], "#f59e0b"),
            ("Due This Week", aging["due_this_week"], "#3b82f6"),
            ("Due This Month", aging["due_this_month"], "#22c55e"),
            ("Future", aging["future"], "#64748b"),
        ]

        for label, data, color in buckets:
            row = tk.Frame(section, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)

            indicator = tk.Frame(row, bg=color, width=8, height=8)
            indicator.pack(side=tk.LEFT, padx=(0, 8))
            indicator.pack_propagate(False)

            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg="#ffffff", fg="#0f172a", width=16, anchor="w").pack(side=tk.LEFT)

            tk.Label(row, text=f"{data['count']} voucher(s)",
                     font=("Segoe UI", 9), bg="#ffffff", fg="#475569",
                     width=14, anchor="w").pack(side=tk.LEFT, padx=(8, 0))

            tk.Label(row, text=f"{data['total']:,.2f}",
                     font=("Segoe UI", 9, "bold"), bg="#ffffff", fg=color,
                     anchor="e").pack(side=tk.RIGHT, padx=(0, 8))

    def _draw_payment_distribution(self):
        """Draw payment method distribution."""
        dist = db.get_payment_method_distribution(self._company_id, self._date_filter)
        if not dist:
            return

        section = tk.LabelFrame(self._content_frame, text="  Payment Method Distribution",
                                font=("Segoe UI", 10, "bold"), fg="#0f172a", bg="#ffffff", padx=8, pady=8)
        section.pack(fill=tk.X, padx=8, pady=(8, 12))

        total = sum(d["total"] for d in dist) or 1

        for i, d in enumerate(dist):
            row = tk.Frame(section, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)

            color = CHART_COLORS[i % len(CHART_COLORS)]
            pct = (d["total"] / total) * 100

            indicator = tk.Frame(row, bg=color, width=12, height=12)
            indicator.pack(side=tk.LEFT, padx=(0, 8))
            indicator.pack_propagate(False)

            tk.Label(row, text=d["payment_method"], font=("Segoe UI", 9, "bold"),
                     bg="#ffffff", fg="#0f172a", width=14, anchor="w").pack(side=tk.LEFT)

            tk.Label(row, text=f"{d['count']} voucher(s)",
                     font=("Segoe UI", 8), bg="#ffffff", fg="#64748b",
                     width=12, anchor="w").pack(side=tk.LEFT, padx=(8, 0))

            tk.Label(row, text=f"{d['total']:,.2f} ({pct:.0f}%)",
                     font=("Segoe UI", 9), bg="#ffffff", fg=color,
                     anchor="e").pack(side=tk.RIGHT, padx=(0, 8))

    def _export_csv(self):
        """Export current analytics breakdown and KPIs to CSV."""
        period = self._period_var.get()
        default_filename = f"analytics_report_{period.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = filedialog.asksaveasfilename(
            title="Export Analytics Data",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self
        )
        if not filepath:
            return

        try:
            kpis = db.get_dashboard_kpis(self._company_id, period)
            cats = db.get_category_spending_breakdown(self._company_id, period)
            payees = db.get_top_payees_analytics(self._company_id, period, limit=15)
            aging = db.get_due_date_aging(self._company_id)

            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["ANALYTICS & EXPENSE REPORT"])
                writer.writerow(["Period", period])
                writer.writerow(["Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                writer.writerow(["KEY PERFORMANCE INDICATORS (KPIs)"])
                writer.writerow(["Total Spent", f"{kpis.get('total_spent', 0):.2f}"])
                writer.writerow(["Voucher Count", kpis.get("voucher_count", 0)])
                writer.writerow(["Avg Voucher Size", f"{kpis.get('avg_voucher_size', 0):.2f}"])
                writer.writerow(["Overdue Count", kpis.get("overdue_count", 0)])
                writer.writerow(["Overdue Amount", f"{kpis.get('overdue_amount', 0):.2f}"])
                writer.writerow([])
                writer.writerow(["SPENDING BY CATEGORY"])
                writer.writerow(["Category", "Total Spent", "Voucher Count"])
                for c in cats:
                    writer.writerow([c["category"], f"{c['total']:.2f}", c["count"]])
                writer.writerow([])
                writer.writerow(["TOP PAYEES"])
                writer.writerow(["Payee", "Total Spent", "Voucher Count"])
                for p in payees:
                    writer.writerow([p["payee"], f"{p['total']:.2f}", p["count"]])
                writer.writerow([])
                writer.writerow(["DUE DATE AGING"])
                writer.writerow(["Bucket", "Count", "Total Amount"])
                for b_name in ["overdue", "due_today", "due_this_week", "due_this_month", "future"]:
                    writer.writerow([b_name.replace("_", " ").title(), aging[b_name]["count"], f"{aging[b_name]['total']:.2f}"])

            messagebox.showinfo("Export Successful", f"Analytics data exported successfully to:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export analytics: {e}", parent=self)

