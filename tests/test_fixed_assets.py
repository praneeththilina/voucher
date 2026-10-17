"""
Unit tests for Fixed Asset Register & Depreciation Management Engine.
Covers Migration 38, asset CRUD, straight-line depreciation calculation,
monthly wizard auto-journaling to GL, disposal gain/loss handling,
and CSV export with formula injection sanitization.
"""

import os
import tempfile
import unittest
import database as db


class TestFixedAssets(unittest.TestCase):
    def setUp(self):
        """Set up an isolated in-memory or temp SQLite database for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_fixed_assets.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path

        # Run database initialization and migrations (including Migration 38)
        db.init_db()
        self.conn = db.get_connection()
        self.company_id = 1

    def tearDown(self):
        """Clean up temp database file."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
        db.DB_PATH = self.orig_db_path
        if os.path.exists(self.test_dir):
            import shutil
            shutil.rmtree(self.test_dir)

    def test_get_next_asset_code(self):
        """Test sequential asset code generation."""
        code1 = db.get_next_asset_code(self.company_id)
        self.assertEqual(code1, "AST-0001")

        db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "Test Asset 1",
            "cost_basis": 100000.0,
            "salvage_value": 10000.0,
            "useful_life_months": 36,
            "purchase_date": "2025-01-01",
        })

        code2 = db.get_next_asset_code(self.company_id)
        self.assertEqual(code2, "AST-0002")

    def test_asset_crud_and_validation(self):
        """Test creating, reading, updating, deleting fixed assets and validation checks."""
        # Validation: missing asset_name
        with self.assertRaises(ValueError):
            db.create_fixed_asset({
                "company_id": self.company_id,
                "asset_code": "AST-0001",
                "asset_name": "   ",
                "cost_basis": 1000.0,
                "salvage_value": 100.0,
                "useful_life_months": 12,
            })

        # Validation: salvage_value >= cost_basis
        with self.assertRaises(ValueError):
            db.create_fixed_asset({
                "company_id": self.company_id,
                "asset_code": "AST-0001",
                "asset_name": "Invalid Asset",
                "cost_basis": 1000.0,
                "salvage_value": 1000.0,
                "useful_life_months": 12,
            })

        # Create valid asset
        asset_id = db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "Office Server",
            "category": "Computers & IT",
            "cost_basis": 360000.0,
            "salvage_value": 36000.0,
            "useful_life_months": 36,
            "purchase_date": "2025-01-15",
            "notes": "Main rack server",
        })
        self.assertIsNotNone(asset_id)

        asset = db.get_fixed_asset(asset_id)
        self.assertEqual(asset["asset_name"], "Office Server")
        self.assertEqual(asset["net_book_value"], 360000.0)

        # Update asset
        ok = db.update_fixed_asset(asset_id, {
            "asset_name": "Office Server Pro",
            "cost_basis": 360000.0,
            "salvage_value": 36000.0,
            "useful_life_months": 36,
            "purchase_date": "2025-01-15",
        })
        self.assertTrue(ok)
        asset_updated = db.get_fixed_asset(asset_id)
        self.assertEqual(asset_updated["asset_name"], "Office Server Pro")

        # Delete asset
        del_ok = db.delete_fixed_asset(asset_id)
        self.assertTrue(del_ok)
        self.assertIsNone(db.get_fixed_asset(asset_id))

    def test_calculate_monthly_depreciation(self):
        """Test straight-line monthly depreciation logic."""
        asset_id = db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "Delivery Truck",
            "cost_basis": 360000.0,
            "salvage_value": 36000.0,
            "useful_life_months": 36,
            "purchase_date": "2025-01-01",
        })

        # Depreciable base = 360,000 - 36,000 = 324,000
        # Monthly depreciation = 324,000 / 36 = 9,000
        deprec = db.calculate_monthly_depreciation(asset_id, target_period="2025-01-31")
        self.assertEqual(deprec, 9000.0)

    def test_run_depreciation_wizard_and_gl_posting(self):
        """Test batch monthly depreciation wizard and GL journal creation."""
        asset_id = db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "Delivery Van",
            "category": "Vehicles",
            "cost_basis": 1200000.0,
            "salvage_value": 200000.0,
            "useful_life_months": 50,  # Depreciable base 1,000,000 / 50 = 20,000 / month
            "purchase_date": "2025-01-01",
        })

        results = db.run_depreciation_wizard(self.company_id, "2025-01-31")
        self.assertEqual(results["processed_count"], 1)
        self.assertEqual(results["total_depreciation"], 20000.0)
        self.assertIsNotNone(results["journal_entry_id"])

        asset = db.get_fixed_asset(asset_id)
        self.assertEqual(asset["accumulated_depreciation"], 20000.0)
        self.assertEqual(asset["net_book_value"], 1180000.0)

        # Verify running wizard for same period skips already depreciated assets
        results2 = db.run_depreciation_wizard(self.company_id, "2025-01-31")
        self.assertEqual(results2["processed_count"], 0)
        self.assertEqual(results2["total_depreciation"], 0.0)

    def test_dispose_fixed_asset_gain_loss(self):
        """Test asset disposal with gain or loss calculation and status update."""
        asset_id = db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "Forklift",
            "category": "Machinery",
            "cost_basis": 500000.0,
            "salvage_value": 50000.0,
            "useful_life_months": 45,
            "purchase_date": "2025-01-01",
        })

        # Run 1 month depreciation (Depreciable base = 450,000 / 45 = 10,000)
        db.run_depreciation_wizard(self.company_id, "2025-01-31")

        # Current book value = 500,000 - 10,000 = 490,000
        # Dispose for 510,000 -> Gain of 20,000
        ok = db.dispose_fixed_asset(
            asset_id=asset_id,
            disposal_date="2025-02-01",
            disposal_amount=510000.0,
            notes="Sold to third party",
        )
        self.assertTrue(ok)

        asset = db.get_fixed_asset(asset_id)
        self.assertEqual(asset["status"], "Disposed")
        self.assertEqual(asset["disposal_amount"], 510000.0)

    def test_export_fixed_asset_register_to_csv(self):
        """Test exporting asset register to CSV with formula injection sanitization."""
        db.create_fixed_asset({
            "company_id": self.company_id,
            "asset_code": "AST-0001",
            "asset_name": "=CMD|' /C calc'!A0",  # Formula injection attempt
            "category": "Equipment",
            "cost_basis": 100000.0,
            "salvage_value": 10000.0,
            "useful_life_months": 12,
            "purchase_date": "2025-01-01",
        })

        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        os.close(csv_fd)
        try:
            ok = db.export_fixed_asset_register_to_csv(csv_path, company_id=self.company_id)
            self.assertTrue(ok)

            with open(csv_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            self.assertIn("FIXED ASSET REGISTER & DEPRECIATION SCHEDULE", content)
            # Ensure formula injection single quote prefix is present
            self.assertIn("'=CMD|' /C calc'!A0", content)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)


if __name__ == "__main__":
    unittest.main()
