"""
ui/cash_flow_forecast_dialog.py
Interactive Cash Flow Forecast & Payment Obligations UI Dialog.

Features:
- Forecast Horizon Selector (30, 60, 90 days)
- Minimum Safety Reserve Threshold Input
- Real-Time Summary KPI Cards (Starting Cash, Inflows, Outflows, Ending Cash)
- Deficit Warning Banner Alert for negative or low projected balances
- Interactive Tabbed Treeviews (Daily Projection Timeline, AR Inflows, AP/Recurring Outflows)
- Publication-Quality PDF Generation & CSV Export
"""

import os
from tkinter import filedialog, messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *

import database as db
from reports.cash_flow_forecast import (
    generate_cash_flow_forecast,
    export_cash_flow_forecast_csv,
    generate_cash_flow_forecast_pdf,
)
from ui.pdf_viewer import PdfViewerDialog


class CashFlowForecastDialog(tb.Toplevel):
    """Interactive Cash Flow Forecast & Obligations Dialog."""

    def __init__(self, parent, company_id=None):
        super().__init__(parent)
        self.parent = parent
        self.company_id = company_id or db.get_active_company_id()
        self.forecast_data = None

        comp = db.get_company(self.company_id) or {}
        comp_name = comp.get("name") or "Main Enterprise"
        self.title(f"Cash Flow Forecast & Payment Obligations — {comp_name}")
        self.geometry("1020x700")
        self.minsize(920, 600)

        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._refresh_forecast()

    def _build_ui(self):
        """Construct dialog layout."""
        main_container = tb.Frame(self, padding=12)
        main_container.pack(fill=BOTH, expand=YES)

        # 1. Top Control Bar
        ctrl_frame = tb.Labelframe(main_container, text="Forecast Configuration & Parameters", padding=10, bootstyle="primary")
        ctrl_frame.pack(fill=X, pady=(0, 10))

        tb.Label(ctrl_frame, text="Forecast Horizon:", font=("Helvetica", 9, "bold")).pack(side=LEFT, padx=(0, 5))
        self.cmb_horizon = tb.Combobox(ctrl_frame, values=["30 Days", "60 Days", "90 Days"], width=12, state="readonly")
        self.cmb_horizon.set("30 Days")
        self.cmb_horizon.pack(side=LEFT, padx=(0, 15))
        self.cmb_horizon.bind("<<ComboboxSelected>>", lambda e: self._refresh_forecast())

        tb.Label(ctrl_frame, text="Min Reserve Threshold:", font=("Helvetica", 9, "bold")).pack(side=LEFT, padx=(0, 5))
        self.ent_reserve = tb.Entry(ctrl_frame, width=12)
        self.ent_reserve.insert(0, "0.00")
        self.ent_reserve.pack(side=LEFT, padx=(0, 15))

        btn_refresh = tb.Button(ctrl_frame, text="🔄 Refresh Forecast", bootstyle="primary", command=self._refresh_forecast)
        btn_refresh.pack(side=LEFT, padx=5)

        # 2. Deficit Alert Banner Frame (Dynamic)
        self.alert_frame = tb.Frame(main_container, padding=8)
        self.alert_label = tb.Label(self.alert_frame, text="", font=("Helvetica", 10, "bold"))
        self.alert_label.pack(side=LEFT, fill=X, expand=YES)

        # 3. KPI Summary Cards Frame
        kpi_frame = tb.Frame(main_container)
        kpi_frame.pack(fill=X, pady=(0, 10))

        self.card_starting = self._create_kpi_card(kpi_frame, "Starting Cash", "0.00", "secondary")
        self.card_starting.pack(side=LEFT, fill=X, expand=YES, padx=3)

        self.card_inflows = self._create_kpi_card(kpi_frame, "AR Inflows (+)", "0.00", "success")
        self.card_inflows.pack(side=LEFT, fill=X, expand=YES, padx=3)

        self.card_outflows = self._create_kpi_card(kpi_frame, "AP/Recurring Outflows (-)", "0.00", "danger")
        self.card_outflows.pack(side=LEFT, fill=X, expand=YES, padx=3)

        self.card_net = self._create_kpi_card(kpi_frame, "Net Change", "0.00", "info")
        self.card_net.pack(side=LEFT, fill=X, expand=YES, padx=3)

        self.card_ending = self._create_kpi_card(kpi_frame, "Projected Ending Cash", "0.00", "primary")
        self.card_ending.pack(side=LEFT, fill=X, expand=YES, padx=3)

        # 4. Notebook for Detailed Tables
        self.notebook = tb.Notebook(main_container, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=YES, pady=(0, 10))

        # Tab 1: Daily Projection Timeline
        self.tab_timeline = tb.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_timeline, text="📅 Daily Projection Timeline")
        self._build_timeline_tab()

        # Tab 2: Expected Inflows (AR Collections)
        self.tab_inflows = tb.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_inflows, text="📈 Expected Inflows (AR)")
        self._build_inflows_tab()

        # Tab 3: Expected Outflows (AP & Recurring)
        self.tab_outflows = tb.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_outflows, text="📉 Expected Outflows (AP/Recurring)")
        self._build_outflows_tab()

        # 5. Bottom Action Bar
        act_bar = tb.Frame(main_container)
        act_bar.pack(fill=X)

        btn_pdf = tb.Button(act_bar, text="📄 Preview / Export PDF", bootstyle="success", command=self._export_pdf)
        btn_pdf.pack(side=LEFT, padx=(0, 6))

        btn_csv = tb.Button(act_bar, text="📊 Export CSV", bootstyle="info", command=self._export_csv)
        btn_csv.pack(side=LEFT, padx=6)

        btn_close = tb.Button(act_bar, text="Close", bootstyle="secondary-outline", command=self.destroy)
        btn_close.pack(side=RIGHT)

    def _create_kpi_card(self, parent, title, value_str, style_color):
        """Create a styled KPI summary card container."""
        card = tb.Labelframe(parent, text=title, padding=8, bootstyle=style_color)
        lbl = tb.Label(card, text=value_str, font=("Helvetica", 12, "bold"), bootstyle=style_color)
        lbl.pack(anchor=CENTER)
        card.lbl_value = lbl
        return card

    def _build_timeline_tab(self):
        """Build treeview for daily timeline."""
        cols = ("date", "inflow", "outflow", "net_flow", "projected_balance", "status")
        self.tv_timeline = tb.Treeview(self.tab_timeline, columns=cols, show="headings", height=12)

        self.tv_timeline.heading("date", text="Date")
        self.tv_timeline.heading("inflow", text="Expected Inflow (+)")
        self.tv_timeline.heading("outflow", text="Expected Outflow (-)")
        self.tv_timeline.heading("net_flow", text="Net Daily Flow")
        self.tv_timeline.heading("projected_balance", text="Projected Cash Balance")
        self.tv_timeline.heading("status", text="Reserve Status")

        self.tv_timeline.column("date", width=120, anchor=CENTER)
        self.tv_timeline.column("inflow", width=140, anchor=E)
        self.tv_timeline.column("outflow", width=140, anchor=E)
        self.tv_timeline.column("net_flow", width=140, anchor=E)
        self.tv_timeline.column("projected_balance", width=160, anchor=E)
        self.tv_timeline.column("status", width=140, anchor=CENTER)

        sb = tb.Scrollbar(self.tab_timeline, orient=VERTICAL, command=self.tv_timeline.yview)
        self.tv_timeline.configure(yscrollcommand=sb.set)

        self.tv_timeline.pack(side=LEFT, fill=BOTH, expand=YES)
        sb.pack(side=RIGHT, fill=Y)

        self.tv_timeline.tag_configure("deficit", background="#FEE2E2", foreground="#991B1B")
        self.tv_timeline.tag_configure("normal", background="#FFFFFF")

    def _build_inflows_tab(self):
        """Build treeview for expected inflows."""
        cols = ("type", "ref", "party", "due_date", "effective_date", "amount")
        self.tv_inflows = tb.Treeview(self.tab_inflows, columns=cols, show="headings", height=12)

        self.tv_inflows.heading("type", text="Type")
        self.tv_inflows.heading("ref", text="Ref #")
        self.tv_inflows.heading("party", text="Customer Name")
        self.tv_inflows.heading("due_date", text="Due Date")
        self.tv_inflows.heading("effective_date", text="Effective Date")
        self.tv_inflows.heading("amount", text="Amount")

        self.tv_inflows.column("type", width=100, anchor=CENTER)
        self.tv_inflows.column("ref", width=120, anchor=W)
        self.tv_inflows.column("party", width=240, anchor=W)
        self.tv_inflows.column("due_date", width=110, anchor=CENTER)
        self.tv_inflows.column("effective_date", width=110, anchor=CENTER)
        self.tv_inflows.column("amount", width=130, anchor=E)

        sb = tb.Scrollbar(self.tab_inflows, orient=VERTICAL, command=self.tv_inflows.yview)
        self.tv_inflows.configure(yscrollcommand=sb.set)

        self.tv_inflows.pack(side=LEFT, fill=BOTH, expand=YES)
        sb.pack(side=RIGHT, fill=Y)

    def _build_outflows_tab(self):
        """Build treeview for expected outflows."""
        cols = ("type", "ref", "party", "due_date", "effective_date", "amount")
        self.tv_outflows = tb.Treeview(self.tab_outflows, columns=cols, show="headings", height=12)

        self.tv_outflows.heading("type", text="Type")
        self.tv_outflows.heading("ref", text="Ref #")
        self.tv_outflows.heading("party", text="Supplier / Payee Name")
        self.tv_outflows.heading("due_date", text="Due Date")
        self.tv_outflows.heading("effective_date", text="Effective Date")
        self.tv_outflows.heading("amount", text="Amount")

        self.tv_outflows.column("type", width=130, anchor=CENTER)
        self.tv_outflows.column("ref", width=120, anchor=W)
        self.tv_outflows.column("party", width=240, anchor=W)
        self.tv_outflows.column("due_date", width=110, anchor=CENTER)
        self.tv_outflows.column("effective_date", width=110, anchor=CENTER)
        self.tv_outflows.column("amount", width=130, anchor=E)

        sb = tb.Scrollbar(self.tab_outflows, orient=VERTICAL, command=self.tv_outflows.yview)
        self.tv_outflows.configure(yscrollcommand=sb.set)

        self.tv_outflows.pack(side=LEFT, fill=BOTH, expand=YES)
        sb.pack(side=RIGHT, fill=Y)

    def _refresh_forecast(self):
        """Calculate and refresh UI with forecast results."""
        hz_str = self.cmb_horizon.get()
        hz_days = 30
        if "60" in hz_str:
            hz_days = 60
        elif "90" in hz_str:
            hz_days = 90

        try:
            min_res = float(self.ent_reserve.get() or "0")
        except ValueError:
            min_res = 0.0

        self.forecast_data = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=hz_days,
            min_reserve=min_res
        )

        d = self.forecast_data
        curr = d["currency"]

        # Update KPI Cards
        self.card_starting.lbl_value.configure(text=f"{curr} {d['starting_cash']:,.2f}")
        self.card_inflows.lbl_value.configure(text=f"{curr} {d['total_projected_inflows']:,.2f}")
        self.card_outflows.lbl_value.configure(text=f"{curr} {d['total_projected_outflows']:,.2f}")

        net_val = d["net_projected_flow"]
        net_prefix = "+" if net_val >= 0 else ""
        self.card_net.lbl_value.configure(text=f"{net_prefix}{curr} {net_val:,.2f}")
        self.card_ending.lbl_value.configure(text=f"{curr} {d['projected_ending_cash']:,.2f}")

        # Update Deficit Banner
        if d["has_deficit_alert"]:
            self.alert_frame.pack(fill=X, pady=(0, 10), before=self.card_starting.master)
            self.alert_frame.configure(bootstyle="danger")
            msg = f"⚠️ CASH DEFICIT WARNING: Projected cash drops to a low of {curr} {d['lowest_projected_balance']:,.2f} on {d['lowest_projected_balance_date']}!"
            self.alert_label.configure(text=msg, bootstyle="inverse-danger")
        else:
            self.alert_frame.pack_forget()

        # Update Timeline Treeview
        for item in self.tv_timeline.get_children():
            self.tv_timeline.delete(item)

        for row in d["timeline"]:
            st_text = "⚠️ DEFICIT WARNING" if row["is_deficit"] else "✅ SAFE"
            tag = "deficit" if row["is_deficit"] else "normal"
            self.tv_timeline.insert("", END, values=(
                row["date"],
                f"{row['inflow']:,.2f}" if row['inflow'] > 0 else "-",
                f"{row['outflow']:,.2f}" if row['outflow'] > 0 else "-",
                f"{row['net_flow']:,.2f}",
                f"{row['projected_balance']:,.2f}",
                st_text
            ), tags=(tag,))

        # Update Inflows Treeview
        for item in self.tv_inflows.get_children():
            self.tv_inflows.delete(item)

        for it in d["inflows"]:
            self.tv_inflows.insert("", END, values=(
                it["type"],
                it["ref"],
                it["party"],
                it["due_date"],
                it["effective_date"],
                f"{it['amount']:,.2f}"
            ))

        # Update Outflows Treeview
        for item in self.tv_outflows.get_children():
            self.tv_outflows.delete(item)

        for it in d["outflows"]:
            self.tv_outflows.insert("", END, values=(
                it["type"],
                it["ref"],
                it["party"],
                it["due_date"],
                it["effective_date"],
                f"{it['amount']:,.2f}"
            ))

    def _export_pdf(self):
        """Generate and preview PDF report."""
        if not self.forecast_data:
            return

        try:
            pdf_path = generate_cash_flow_forecast_pdf(self.forecast_data)
            PdfViewerDialog(self, pdf_path, title="Cash Flow Forecast Report")
        except Exception as e:
            messagebox.showerror("PDF Export Error", f"Failed to generate PDF report:\n{e}", parent=self)

    def _export_csv(self):
        """Export forecast to CSV file."""
        if not self.forecast_data:
            return

        out_path = filedialog.asksaveasfilename(
            parent=self,
            title="Save Cash Flow Forecast CSV",
            defaultextension=".csv",
            filetypes=[("CSV Spreadsheet", "*.csv"), ("All Files", "*.*")],
            initialfile=f"cash_flow_forecast_{self.forecast_data['period']['horizon_days']}d.csv"
        )
        if not out_path:
            return

        try:
            export_cash_flow_forecast_csv(self.forecast_data, out_path)
            messagebox.showinfo("CSV Export Success", f"Forecast exported successfully to:\n{out_path}", parent=self)
        except Exception as e:
            messagebox.showerror("CSV Export Error", f"Failed to export CSV:\n{e}", parent=self)
