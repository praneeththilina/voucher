"""
tests/test_cash_flow_forecast.py
Unit tests for Cash Flow Forecast & Payment Obligations Engine and UI Dialog.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import database as db
from reports.cash_flow_forecast import (
    generate_cash_flow_forecast,
    export_cash_flow_forecast_csv,
    generate_cash_flow_forecast_pdf,
)


class TestCashFlowForecastEngine(unittest.TestCase):
    """Test suite for Cash Flow Forecast calculation logic, CSV export, and PDF generation."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.DB_PATH = self.db_path
        db.init_db()

        self.conn = db.get_connection()
        self.company_id = db.get_active_company_id(self.conn)

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_generate_cash_flow_forecast_empty(self):
        """Verify forecast calculation with starting database state."""
        forecast = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=30,
            min_reserve=0.0,
            conn=self.conn
        )

        self.assertEqual(forecast["company_id"], self.company_id)
        self.assertEqual(forecast["period"]["horizon_days"], 30)
        self.assertEqual(len(forecast["timeline"]), 31)  # start_date through end_date (inclusive)
        self.assertFalse(forecast["has_deficit_alert"])

    def test_generate_cash_flow_forecast_with_inflows_outflows(self):
        """Verify forecast aggregation with AR invoices, AP invoices, and recurring schedules."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        due_in_10 = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")

        # Create Customer and AR Invoice
        cust_id = db.create_customer({
            "name": "Test Client Corp",
            "contact_person": "John Doe",
        }, conn=self.conn)

        db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": cust_id,
            "invoice_number": "INV-TEST-001",
            "invoice_date": today_str,
            "due_date": due_in_10,
            "subtotal": 5000.0,
            "total_amount": 5000.0,
        }, [{"description": "Services", "quantity": 1, "unit_price": 5000.0, "amount": 5000.0}], conn=self.conn)

        # Create Supplier and AP Invoice
        supp_id = db.create_supplier({
            "name": "Test Vendor Ltd",
        }, conn=self.conn)

        db.create_ap_invoice({
            "company_id": self.company_id,
            "supplier_id": supp_id,
            "invoice_number": "BILL-TEST-001",
            "invoice_date": today_str,
            "due_date": due_in_10,
            "subtotal": 2000.0,
            "total_amount": 2000.0,
        }, [{"description": "Supplies", "quantity": 1, "unit_price": 2000.0, "amount": 2000.0}], conn=self.conn)

        # Create Recurring Schedule
        db.create_recurring_schedule({
            "schedule_name": "Monthly Office Rent",
            "payee_name": "Landlord Inc",
            "amount": 1000.0,
            "frequency": "Monthly",
            "next_run": due_in_10,
            "is_active": 1
        }, company_id=self.company_id)

        forecast = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=30,
            min_reserve=0.0,
            conn=self.conn
        )

        self.assertAlmostEqual(forecast["total_projected_inflows"], 5000.0)
        self.assertAlmostEqual(forecast["total_projected_outflows"], 3000.0)  # 2000 AP + 1000 Recurring
        self.assertAlmostEqual(forecast["net_projected_flow"], 2000.0)

    def test_deficit_alert_detection(self):
        """Verify deficit alert trigger when projected balance drops below reserve threshold."""
        forecast = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=30,
            min_reserve=1000000.0,  # High reserve threshold to force alert
            conn=self.conn
        )

        self.assertTrue(forecast["has_deficit_alert"])
        self.assertGreater(len(forecast["deficit_dates"]), 0)

    def test_export_cash_flow_forecast_csv_sanitization(self):
        """Verify CSV export writes file and sanitizes formula injection characters."""
        # Add customer with potential formula string
        cust_id = db.create_customer({
            "name": "=CMD|' /C calc'!A0",
        }, conn=self.conn)

        today_str = datetime.now().strftime("%Y-%m-%d")
        db.create_ar_invoice({
            "company_id": self.company_id,
            "customer_id": cust_id,
            "invoice_number": "INV-FORMULA-1",
            "invoice_date": today_str,
            "due_date": today_str,
            "subtotal": 100.0,
            "total_amount": 100.0,
        }, [{"description": "Item", "quantity": 1, "unit_price": 100.0, "amount": 100.0}], conn=self.conn)

        forecast = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=30,
            conn=self.conn
        )

        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(csv_fd)

        try:
            res_path = export_cash_flow_forecast_csv(forecast, csv_path)
            self.assertTrue(os.path.exists(res_path))

            with open(csv_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
                self.assertIn("'=CMD|", content)
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

    def test_generate_cash_flow_forecast_pdf(self):
        """Verify PDF report generation produces a valid non-empty file."""
        forecast = generate_cash_flow_forecast(
            company_id=self.company_id,
            horizon_days=30,
            conn=self.conn
        )

        pdf_fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(pdf_fd)

        try:
            res_path = generate_cash_flow_forecast_pdf(forecast, pdf_path)
            self.assertTrue(os.path.exists(res_path))
            self.assertGreater(os.path.getsize(res_path), 100)
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)


class TestCashFlowForecastUI(unittest.TestCase):
    """UI test suite for CashFlowForecastDialog."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    @patch("tkinter.Toplevel.grab_set")
    def test_dialog_instantiation(self, mock_grab_set):
        """Verify CashFlowForecastDialog instantiates and populates KPI metrics without error."""
        import tkinter as tk
        import ttkbootstrap as tb
        from ui.cash_flow_forecast_dialog import CashFlowForecastDialog

        root = tb.Window(themename="cosmo")
        root.withdraw()

        try:
            dialog = CashFlowForecastDialog(root)
            self.assertIsNotNone(dialog.forecast_data)
            self.assertEqual(dialog.forecast_data["period"]["horizon_days"], 30)
            dialog.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
