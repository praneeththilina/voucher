"""QuickBooks-style business performance dashboard for voucher analytics."""

from __future__ import annotations

import csv
import math
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk

import database as db


BG = "#f3f4f6"
SURFACE = "#ffffff"
BORDER = "#d1d5db"
TEXT = "#1f2937"
MUTED = "#6b7280"
GREEN = "#2ca01c"
BLUE = "#2563eb"
AMBER = "#d97706"
RED = "#dc2626"
PURPLE = "#7c3aed"
ROW_ALT = "#f8fafc"
CHART_COLORS = (GREEN, BLUE, AMBER, PURPLE, "#0891b2", "#e11d48", "#475569")


class AnalyticsDashboard(ttk.Frame):
    """Fast, drillable business-performance workspace."""

    PERIODS = ("This Month", "Last Month", "This Year", "All Time")

    def __init__(
        self,
        parent,
        drilldown_callback: Callable[[str, str], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self._drilldown_callback = drilldown_callback
        self._company_id = db.get_active_company_id()
        self._date_filter = self.PERIODS[0]
        self._trend_data: list[dict] = []
        self._category_data: list[dict] = []
        self._payee_data: list[dict] = []
        self._aging_data: dict = {}
        self._payment_data: list[dict] = []
        self._chart_after_id: str | None = None
        self._kpi_vars: dict[str, tk.StringVar] = {}
        self._kpi_subtitle_vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self._build_styles()
        self._build_header()
        self._build_scroll_area()
        self._build_content()

    def _build_styles(self) -> None:
        style = ttk.Style()
        style.configure(
            "Analytics.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=27,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Analytics.Treeview.Heading",
            background="#f8fafc",
            foreground="#475569",
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padding=(6, 5),
        )
        style.map(
            "Analytics.Treeview",
            background=[("selected", "#d9f2d7")],
            foreground=[("selected", TEXT)],
        )

    def _build_header(self) -> None:
        header = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        header.pack(fill=tk.X, padx=8, pady=(8, 0))
        title_area = tk.Frame(header, bg=SURFACE)
        title_area.pack(side=tk.LEFT, padx=16, pady=10)
        tk.Label(
            title_area,
            text="Business performance",
            font=("Segoe UI", 15, "bold"),
            bg=SURFACE,
            fg=TEXT,
        ).pack(anchor="w")
        self._company_var = tk.StringVar(value="Voucher analytics")
        tk.Label(
            title_area,
            textvariable=self._company_var,
            font=("Segoe UI", 8),
            bg=SURFACE,
            fg=MUTED,
        ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(header, bg=SURFACE)
        actions.pack(side=tk.RIGHT, padx=12, pady=10)
        tk.Label(
            actions,
            text="Report period",
            font=("Segoe UI", 8),
            bg=SURFACE,
            fg=MUTED,
        ).pack(side=tk.LEFT, padx=(0, 5))
        self._period_var = tk.StringVar(value=self.PERIODS[0])
        self._period_combo = ttk.Combobox(
            actions,
            textvariable=self._period_var,
            values=self.PERIODS,
            state="readonly",
            width=14,
        )
        self._period_combo.pack(side=tk.LEFT, padx=(0, 8))
        self._period_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self.refresh(),
        )
        ttk.Button(
            actions,
            text="Export CSV",
            command=self._export_csv,
            bootstyle="secondary-outline",
            width=12,
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            actions,
            text="Refresh",
            command=self.refresh,
            bootstyle="success",
            width=10,
        ).pack(side=tk.LEFT)

    def _build_scroll_area(self) -> None:
        host = tk.Frame(self, bg=BG)
        host.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._scroll_canvas = tk.Canvas(
            host,
            bg=BG,
            borderwidth=0,
            highlightthickness=0,
        )
        self._scrollbar = ttk.Scrollbar(
            host,
            orient=tk.VERTICAL,
            command=self._scroll_canvas.yview,
        )
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)
        self._content_frame = tk.Frame(self._scroll_canvas, bg=BG)
        self._content_window = self._scroll_canvas.create_window(
            (0, 0),
            window=self._content_frame,
            anchor="nw",
        )
        self._scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._scroll_canvas.bind("<Configure>", self._on_canvas_configure)
        self._content_frame.bind(
            "<Configure>",
            lambda _event: self._update_scroll_region(),
        )
        self._scroll_canvas.bind("<MouseWheel>", self._on_mousewheel)

    def _build_content(self) -> None:
        self._content_frame.columnconfigure(0, weight=1)
        cards = tk.Frame(self._content_frame, bg=BG)
        cards.grid(row=0, column=0, sticky="ew", padx=4, pady=(10, 4))
        for column in range(5):
            cards.columnconfigure(column, weight=1, uniform="kpi")
        specs = (
            ("spent", "TOTAL SPENT", GREEN),
            ("count", "VOUCHERS", BLUE),
            ("average", "AVERAGE VOUCHER", PURPLE),
            ("pending", "BILLS PENDING", AMBER),
            ("overdue", "OVERDUE", RED),
        )
        for column, (key, title, color) in enumerate(specs):
            self._create_kpi_card(cards, column, key, title, color)

        primary = tk.Frame(self._content_frame, bg=BG)
        primary.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        primary.columnconfigure(0, weight=2)
        primary.columnconfigure(1, weight=1)

        trend_panel, trend_body = self._create_panel(
            primary,
            "Spending trend",
            "Last 12 months",
        )
        trend_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._trend_canvas = tk.Canvas(
            trend_body,
            bg=SURFACE,
            height=220,
            borderwidth=0,
            highlightthickness=0,
        )
        self._trend_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        self._trend_canvas.bind("<Configure>", self._schedule_chart_redraw)

        category_panel, self._category_body = self._create_panel(
            primary,
            "Spending by category",
            "Selected period",
        )
        category_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        details = tk.Frame(self._content_frame, bg=BG)
        details.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        details.columnconfigure(0, weight=5, uniform="details")
        details.columnconfigure(1, weight=4, uniform="details")
        details.columnconfigure(2, weight=4, uniform="details")

        payee_panel, payee_body = self._create_panel(
            details,
            "Top payees",
            "Double-click to view vouchers",
        )
        payee_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._payee_tree = self._create_tree(
            payee_body,
            (
                ("payee", "Payee", 170, "w"),
                ("count", "Vouchers", 62, "center"),
                ("amount", "Amount", 100, "e"),
            ),
        )
        self._payee_tree.bind("<Double-1>", self._drill_payee)

        aging_panel, aging_body = self._create_panel(
            details,
            "Bills that need attention",
            "Due-date commitments",
        )
        aging_panel.grid(row=0, column=1, sticky="nsew", padx=4)
        self._aging_tree = self._create_tree(
            aging_body,
            (
                ("bucket", "Due", 110, "w"),
                ("count", "No.", 46, "center"),
                ("amount", "Amount", 92, "e"),
            ),
        )
        self._aging_tree.bind("<Double-1>", self._drill_aging)

        payment_panel, payment_body = self._create_panel(
            details,
            "How you paid",
            "Selected period",
        )
        payment_panel.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self._payment_tree = self._create_tree(
            payment_body,
            (
                ("method", "Method", 105, "w"),
                ("count", "No.", 42, "center"),
                ("share", "Share", 70, "e"),
            ),
        )
        self._payment_tree.bind("<Double-1>", self._drill_payment)

        footer = tk.Frame(self._content_frame, bg=BG)
        footer.grid(row=3, column=0, sticky="ew", padx=6, pady=(4, 10))
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            footer,
            textvariable=self._status_var,
            font=("Segoe UI", 8),
            bg=BG,
            fg=MUTED,
        ).pack(side=tk.LEFT)
        tk.Label(
            footer,
            text="Tip: double-click a detail row to open matching vouchers.",
            font=("Segoe UI", 8),
            bg=BG,
            fg=MUTED,
        ).pack(side=tk.RIGHT)
        self._bind_mousewheel_recursive(self._content_frame)

    def _create_kpi_card(
        self,
        parent: tk.Widget,
        column: int,
        key: str,
        title: str,
        color: str,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 4, 0),
        )
        tk.Frame(card, bg=color, height=4).pack(fill=tk.X)
        body = tk.Frame(card, bg=SURFACE)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 9))
        tk.Label(
            body,
            text=title,
            font=("Segoe UI", 7, "bold"),
            bg=SURFACE,
            fg=MUTED,
        ).pack(anchor="w")
        self._kpi_vars[key] = tk.StringVar(value="—")
        self._kpi_subtitle_vars[key] = tk.StringVar(value="")
        tk.Label(
            body,
            textvariable=self._kpi_vars[key],
            font=("Segoe UI", 15, "bold"),
            bg=SURFACE,
            fg=color,
        ).pack(anchor="w", pady=(3, 1))
        tk.Label(
            body,
            textvariable=self._kpi_subtitle_vars[key],
            font=("Segoe UI", 7),
            bg=SURFACE,
            fg=MUTED,
        ).pack(anchor="w")

    @staticmethod
    def _create_panel(
        parent: tk.Widget,
        title: str,
        subtitle: str,
    ) -> tuple[tk.Frame, tk.Frame]:
        panel = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        header = tk.Frame(panel, bg=SURFACE)
        header.pack(fill=tk.X, padx=14, pady=(11, 7))
        tk.Label(
            header,
            text=title,
            font=("Segoe UI", 10, "bold"),
            bg=SURFACE,
            fg=TEXT,
        ).pack(side=tk.LEFT)
        tk.Label(
            header,
            text=subtitle,
            font=("Segoe UI", 7),
            bg=SURFACE,
            fg=MUTED,
        ).pack(side=tk.RIGHT)
        tk.Frame(panel, bg="#e5e7eb", height=1).pack(fill=tk.X)
        body = tk.Frame(panel, bg=SURFACE)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        return panel, body

    @staticmethod
    def _create_tree(
        parent: tk.Widget,
        definitions: tuple[tuple[str, str, int, str], ...],
    ) -> ttk.Treeview:
        columns = tuple(item[0] for item in definitions)
        tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            height=6,
            style="Analytics.Treeview",
            selectmode="browse",
        )
        for key, heading, width, anchor in definitions:
            tree.heading(key, text=heading)
            tree.column(key, width=width, minwidth=40, anchor=anchor)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=(2, 6))
        return tree

    def _on_canvas_configure(self, event) -> None:
        if event.width > 20:
            self._scroll_canvas.itemconfigure(
                self._content_window,
                width=event.width,
            )

    def _update_scroll_region(self) -> None:
        bbox = self._scroll_canvas.bbox("all")
        if bbox:
            self._scroll_canvas.configure(scrollregion=bbox)

    def _on_mousewheel(self, event):
        if self._scroll_canvas.winfo_exists():
            self._scroll_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _bind_mousewheel_recursive(self, widget: tk.Widget) -> None:
        try:
            widget.bind("<MouseWheel>", self._on_mousewheel)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def refresh(self) -> None:
        """Load all dashboard data through one reusable database connection."""
        self._date_filter = self._period_var.get()
        self._status_var.set("Refreshing business performance…")
        self.update_idletasks()
        conn = db.get_connection()
        try:
            self._company_id = db.get_active_company_id(conn)
            company = db.get_company(self._company_id, conn=conn) or {}
            kpis = db.get_dashboard_kpis(
                self._company_id,
                self._date_filter,
                conn=conn,
            )
            trend = db.get_monthly_spending_trend(
                self._company_id,
                months=12,
                conn=conn,
            )
            categories = db.get_category_spending_breakdown(
                self._company_id,
                self._date_filter,
                conn=conn,
            )
            payees = db.get_top_payees(
                self._company_id,
                limit=8,
                date_filter=self._date_filter,
                conn=conn,
            )
            aging = db.get_due_date_aging(self._company_id, conn=conn)
            payments = db.get_payment_method_distribution(
                self._company_id,
                self._date_filter,
                conn=conn,
            )
        except Exception as exc:
            self._status_var.set(f"Could not refresh analytics: {exc}")
            return
        finally:
            conn.close()

        self._company_var.set(
            f"{company.get('name') or 'Active company'}  |  "
            "Cash-basis voucher analytics"
        )
        self._update_kpis(kpis)
        self._trend_data = self._normalize_monthly_trend(trend)
        self._category_data = categories
        self._payee_data = payees
        self._aging_data = aging
        self._payment_data = payments
        self._draw_trend_chart()
        self._render_categories()
        self._render_payees()
        self._render_aging()
        self._render_payments()
        self._status_var.set(
            f"Updated {datetime.now():%d %b %Y, %I:%M %p}  |  "
            f"Period: {self._date_filter}"
        )
        self._bind_mousewheel_recursive(self._content_frame)
        self._update_scroll_region()

    def _update_kpis(self, kpis: dict) -> None:
        total = float(kpis.get("total_spent", 0) or 0)
        count = int(kpis.get("voucher_count", 0) or 0)
        average = float(kpis.get("avg_voucher_size", 0) or 0)
        pending = int(kpis.get("bills_pending", 0) or 0)
        overdue_count = int(kpis.get("overdue_count", 0) or 0)
        overdue_amount = float(kpis.get("overdue_amount", 0) or 0)
        self._kpi_vars["spent"].set(f"LKR {total:,.2f}")
        self._kpi_vars["count"].set(f"{count:,}")
        self._kpi_vars["average"].set(f"LKR {average:,.2f}")
        self._kpi_vars["pending"].set(f"{pending:,}")
        self._kpi_vars["overdue"].set(f"{overdue_count:,}")
        self._kpi_subtitle_vars["spent"].set(self._date_filter.lower())
        self._kpi_subtitle_vars["count"].set("in selected period")
        self._kpi_subtitle_vars["average"].set("per voucher")
        self._kpi_subtitle_vars["pending"].set("open in selected period")
        self._kpi_subtitle_vars["overdue"].set(
            f"LKR {overdue_amount:,.2f} outstanding"
        )

    @staticmethod
    def _normalize_monthly_trend(
        trend: list[dict],
        months: int = 12,
        as_of: datetime | None = None,
    ) -> list[dict]:
        """Fill missing months so sparse data stays correctly scaled."""
        anchor = as_of or datetime.now()
        source = {str(row["month"]): row for row in trend}
        result = []
        anchor_index = anchor.year * 12 + anchor.month - 1
        for offset in range(months - 1, -1, -1):
            month_index = anchor_index - offset
            year, zero_month = divmod(month_index, 12)
            key = f"{year:04d}-{zero_month + 1:02d}"
            row = source.get(key, {})
            result.append(
                {
                    "month": key,
                    "total": float(row.get("total", 0) or 0),
                    "count": int(row.get("count", 0) or 0),
                }
            )
        return result

    def _schedule_chart_redraw(self, _event=None) -> None:
        if self._chart_after_id is not None:
            try:
                self.after_cancel(self._chart_after_id)
            except tk.TclError:
                pass
        self._chart_after_id = self.after(50, self._draw_trend_chart)

    def _draw_trend_chart(self) -> None:
        self._chart_after_id = None
        canvas = self._trend_canvas
        if not canvas.winfo_exists():
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 520)
        height = max(canvas.winfo_height(), 220)
        left, right, top, bottom = 62, 18, 18, 38
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        values = [row["total"] for row in self._trend_data]
        max_value = max(values, default=0)
        if max_value <= 0:
            canvas.create_text(
                width / 2,
                height / 2 - 8,
                text="No voucher spending in the last 12 months",
                fill=MUTED,
                font=("Segoe UI", 10, "bold"),
            )
            canvas.create_text(
                width / 2,
                height / 2 + 14,
                text="New vouchers will appear here automatically.",
                fill="#9ca3af",
                font=("Segoe UI", 8),
            )
            return

        axis_max = self._nice_axis_max(max_value)
        for step in range(5):
            ratio = step / 4
            y = top + plot_height * ratio
            value = axis_max * (1 - ratio)
            canvas.create_line(left, y, width - right, y, fill="#e5e7eb")
            canvas.create_text(
                left - 8,
                y,
                text=self._compact_amount(value),
                anchor="e",
                fill="#94a3b8",
                font=("Segoe UI", 7),
            )

        slot_width = plot_width / max(len(self._trend_data), 1)
        bar_width = min(30, max(8, slot_width * 0.54))
        baseline = top + plot_height
        for index, row in enumerate(self._trend_data):
            center = left + slot_width * (index + 0.5)
            bar_height = (row["total"] / axis_max) * plot_height
            if bar_height:
                canvas.create_rectangle(
                    center - bar_width / 2,
                    baseline - bar_height,
                    center + bar_width / 2,
                    baseline,
                    fill=GREEN,
                    outline="",
                )
            month = datetime.strptime(row["month"], "%Y-%m")
            label = month.strftime("%b")
            if month.month == 1 or index == 0:
                label = month.strftime("%b\n%y")
            canvas.create_text(
                center,
                baseline + 9,
                text=label,
                anchor="n",
                justify="center",
                fill=MUTED,
                font=("Segoe UI", 7),
            )
        canvas.create_text(
            width - right,
            top,
            text=f"12-month total  LKR {sum(values):,.0f}",
            anchor="ne",
            fill=TEXT,
            font=("Segoe UI", 8, "bold"),
        )

    @staticmethod
    def _nice_axis_max(value: float) -> float:
        if value <= 0:
            return 1.0
        exponent = math.floor(math.log10(value))
        scale = 10**exponent
        normalized = value / scale
        for step in (1, 2, 2.5, 5, 10):
            if normalized <= step:
                return step * scale
        return 10 * scale

    @staticmethod
    def _compact_amount(value: float) -> str:
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}m"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.0f}k"
        return f"{value:.0f}"

    def _render_categories(self) -> None:
        for widget in self._category_body.winfo_children():
            widget.destroy()
        if not self._category_data:
            self._empty_state(
                self._category_body,
                "No categorized spending for this period.",
            )
            return
        for index, row in enumerate(self._category_data[:7]):
            category = str(row.get("category") or "Uncategorized")
            total = float(row.get("total", 0) or 0)
            percentage = float(row.get("percentage", 0) or 0)
            item = tk.Frame(self._category_body, bg=SURFACE, cursor="hand2")
            item.pack(fill=tk.X, padx=10, pady=(5, 1))
            top = tk.Frame(item, bg=SURFACE)
            top.pack(fill=tk.X)
            tk.Label(
                top,
                text=category,
                font=("Segoe UI", 8),
                bg=SURFACE,
                fg=TEXT,
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                top,
                text=f"LKR {total:,.0f}  ·  {percentage:.0f}%",
                font=("Segoe UI", 8, "bold"),
                bg=SURFACE,
                fg=TEXT,
            ).pack(side=tk.RIGHT)
            bar = tk.Canvas(
                item,
                height=6,
                bg="#e5e7eb",
                highlightthickness=0,
            )
            bar.pack(fill=tk.X, pady=(3, 0))
            color = CHART_COLORS[index % len(CHART_COLORS)]
            bar.bind(
                "<Configure>",
                lambda event, cv=bar, pct=percentage, fill=color:
                self._paint_progress(cv, event.width, pct, fill),
            )
            for target in (item, top):
                target.bind(
                    "<Double-1>",
                    lambda _event, value=category:
                    self._drilldown("category", value),
                )

    @staticmethod
    def _paint_progress(
        canvas: tk.Canvas,
        width: int,
        percentage: float,
        color: str,
    ) -> None:
        canvas.delete("all")
        filled = max(0, min(width, width * percentage / 100))
        if filled:
            canvas.create_rectangle(
                0,
                0,
                filled,
                6,
                fill=color,
                outline="",
            )

    def _render_payees(self) -> None:
        self._clear_tree(self._payee_tree)
        for index, row in enumerate(self._payee_data):
            self._payee_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    row.get("payee") or "Unspecified",
                    f"{int(row.get('count', 0) or 0):,}",
                    f"{float(row.get('total', 0) or 0):,.2f}",
                ),
                tags=("alt",) if index % 2 else (),
            )
        self._payee_tree.tag_configure("alt", background=ROW_ALT)

    def _render_aging(self) -> None:
        self._clear_tree(self._aging_tree)
        definitions = (
            ("overdue", "Overdue"),
            ("due_today", "Due today"),
            ("due_this_week", "Due this week"),
            ("due_this_month", "Due this month"),
            ("future", "Future"),
        )
        for index, (key, label) in enumerate(definitions):
            row = self._aging_data.get(key, {})
            tags = ("overdue",) if key == "overdue" else (
                ("alt",) if index % 2 else ()
            )
            self._aging_tree.insert(
                "",
                tk.END,
                iid=key,
                values=(
                    label,
                    f"{int(row.get('count', 0) or 0):,}",
                    f"{float(row.get('total', 0) or 0):,.2f}",
                ),
                tags=tags,
            )
        self._aging_tree.tag_configure("overdue", foreground=RED)
        self._aging_tree.tag_configure("alt", background=ROW_ALT)

    def _render_payments(self) -> None:
        self._clear_tree(self._payment_tree)
        grand_total = sum(
            float(row.get("total", 0) or 0)
            for row in self._payment_data
        ) or 1
        for index, row in enumerate(self._payment_data):
            total = float(row.get("total", 0) or 0)
            self._payment_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    row.get("payment_method") or "Unspecified",
                    f"{int(row.get('count', 0) or 0):,}",
                    f"{total / grand_total * 100:.0f}%",
                ),
                tags=("alt",) if index % 2 else (),
            )
        self._payment_tree.tag_configure("alt", background=ROW_ALT)

    @staticmethod
    def _clear_tree(tree: ttk.Treeview) -> None:
        children = tree.get_children()
        if children:
            tree.delete(*children)

    @staticmethod
    def _empty_state(parent: tk.Widget, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            font=("Segoe UI", 9),
            bg=SURFACE,
            fg=MUTED,
        ).pack(expand=True, pady=50)

    def _drill_payee(self, _event=None) -> None:
        selection = self._payee_tree.selection()
        if not selection:
            return
        try:
            row = self._payee_data[int(selection[0])]
        except (ValueError, IndexError):
            return
        self._drilldown("payee", str(row.get("payee") or ""))

    def _drill_aging(self, _event=None) -> None:
        selection = self._aging_tree.selection()
        if not selection:
            return
        due_filters = {
            "overdue": "Overdue",
            "due_today": "Due Today",
            "due_this_week": "Due This Week",
            "due_this_month": "Due This Month",
            "future": "Has Due Date",
        }
        self._drilldown(
            "due",
            due_filters.get(selection[0], "Has Due Date"),
        )

    def _drill_payment(self, _event=None) -> None:
        selection = self._payment_tree.selection()
        if not selection:
            return
        try:
            row = self._payment_data[int(selection[0])]
        except (ValueError, IndexError):
            return
        self._drilldown(
            "payment",
            str(row.get("payment_method") or ""),
        )

    def _drilldown(self, kind: str, value: str) -> None:
        if not value:
            return
        if self._drilldown_callback is None:
            self._status_var.set(f"Drill-down selected: {value}")
            return
        self._drilldown_callback(kind, value)

    def _export_csv(self) -> None:
        period = self._period_var.get()
        filename = (
            f"business_performance_{period.lower().replace(' ', '_')}_"
            f"{datetime.now():%Y%m%d}.csv"
        )
        filepath = filedialog.asksaveasfilename(
            title="Export business performance",
            defaultextension=".csv",
            initialfile=filename,
            filetypes=(("CSV Files", "*.csv"), ("All Files", "*.*")),
            parent=self,
        )
        if not filepath:
            return
        try:
            conn = db.get_connection()
            try:
                kpis = db.get_dashboard_kpis(
                    self._company_id,
                    period,
                    conn=conn,
                )
                categories = db.get_category_spending_breakdown(
                    self._company_id,
                    period,
                    conn=conn,
                )
                payees = db.get_top_payees(
                    self._company_id,
                    date_filter=period,
                    limit=15,
                    conn=conn,
                )
                trend = self._normalize_monthly_trend(
                    db.get_monthly_spending_trend(
                        self._company_id,
                        months=12,
                        conn=conn,
                    )
                )
                aging = db.get_due_date_aging(
                    self._company_id,
                    conn=conn,
                )
            finally:
                conn.close()

            with open(
                filepath,
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as report_file:
                writer = csv.writer(report_file)
                writer.writerow(["BUSINESS PERFORMANCE"])
                writer.writerow(db._sanitize_csv_row(["Period", period]))
                writer.writerow(
                    ["Generated At", f"{datetime.now():%Y-%m-%d %H:%M:%S}"]
                )
                writer.writerow([])
                writer.writerow(["KEY PERFORMANCE INDICATORS"])
                writer.writerow(["Total Spent", f"{kpis['total_spent']:.2f}"])
                writer.writerow(["Voucher Count", kpis["voucher_count"]])
                writer.writerow(
                    ["Average Voucher", f"{kpis['avg_voucher_size']:.2f}"]
                )
                writer.writerow(["Bills Pending", kpis["bills_pending"]])
                writer.writerow(["Overdue Count", kpis["overdue_count"]])
                writer.writerow(
                    ["Overdue Amount", f"{kpis['overdue_amount']:.2f}"]
                )
                writer.writerow([])
                writer.writerow(["12-MONTH SPENDING TREND"])
                writer.writerow(["Month", "Total Spent", "Voucher Count"])
                for row in trend:
                    writer.writerow(
                        [row["month"], f"{row['total']:.2f}", row["count"]]
                    )
                writer.writerow([])
                writer.writerow(["SPENDING BY CATEGORY"])
                writer.writerow(["Category", "Total Spent", "Voucher Count"])
                for row in categories:
                    writer.writerow(
                        db._sanitize_csv_row(
                            [
                                row["category"],
                                f"{row['total']:.2f}",
                                row["count"],
                            ]
                        )
                    )
                writer.writerow([])
                writer.writerow(["TOP PAYEES"])
                writer.writerow(["Payee", "Total Spent", "Voucher Count"])
                for row in payees:
                    writer.writerow(
                        db._sanitize_csv_row(
                            [
                                row["payee"],
                                f"{row['total']:.2f}",
                                row["count"],
                            ]
                        )
                    )
                writer.writerow([])
                writer.writerow(["DUE DATE AGING"])
                writer.writerow(["Bucket", "Count", "Total Amount"])
                for key in (
                    "overdue",
                    "due_today",
                    "due_this_week",
                    "due_this_month",
                    "future",
                ):
                    row = aging[key]
                    writer.writerow(
                        [
                            key.replace("_", " ").title(),
                            row["count"],
                            f"{row['total']:.2f}",
                        ]
                    )
            messagebox.showinfo(
                "Export complete",
                f"Business performance exported to:\n{filepath}",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror(
                "Export failed",
                f"Could not export analytics:\n{exc}",
                parent=self,
            )
