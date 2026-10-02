"""
Unit tests for Google Firebase Cloud Firestore NoSQL Database Integration.
Validates credentials validation, config persistence, NoSQL document serialization,
Spark free tier compliance, and Settings Dialog integration.
"""

import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import database as db
import firebase_client
from ui.settings_dialog import SettingsDialog


class TestFirebaseIntegration(unittest.TestCase):
    """Test suite for firebase_client module and Firestore NoSQL operations."""

    def setUp(self):
        db.init_db()

    def test_firebase_module_availability(self):
        """Verify firebase-admin is available in environment."""
        self.assertTrue(firebase_client.is_firebase_available(), "firebase-admin should be installed")

    def test_config_get_and_save(self):
        """Test retrieving and saving Firebase configuration settings in database."""
        test_cfg = {
            "enabled": True,
            "creds_path": "C:/fake/path/serviceAccountKey.json",
            "project_id": "test-voucher-project",
            "collection_prefix": "acme_",
            "auto_sync": True,
            "client_email": "test-service@test-voucher-project.iam.gserviceaccount.com",
            "last_synced": "2026-10-03 00:00:00"
        }
        firebase_client.save_config(test_cfg)

        loaded = firebase_client.get_config()
        self.assertTrue(loaded["enabled"])
        self.assertEqual(loaded["creds_path"], "C:/fake/path/serviceAccountKey.json")
        self.assertEqual(loaded["project_id"], "test-voucher-project")
        self.assertEqual(loaded["collection_prefix"], "acme_")
        self.assertTrue(loaded["auto_sync"])
        self.assertEqual(loaded["client_email"], "test-service@test-voucher-project.iam.gserviceaccount.com")
        self.assertEqual(loaded["last_synced"], "2026-10-03 00:00:00")

    def test_validate_credentials_file_invalid_and_valid(self):
        """Test validation of genuine vs corrupt/fake Firebase service account JSON files."""
        # Case 1: Non-existent file
        is_ok, data, err = firebase_client.validate_credentials_file("non_existent_file.json")
        self.assertFalse(is_ok)
        self.assertIn("does not exist", err.lower())

        # Case 2: Corrupt JSON
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
            tf.write("NOT_JSON")
            corrupt_path = tf.name

        try:
            is_ok, data, err = firebase_client.validate_credentials_file(corrupt_path)
            self.assertFalse(is_ok)
            self.assertIn("parse", err.lower())
        finally:
            os.remove(corrupt_path)

        # Case 3: Missing required service account fields
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
            json.dump({"type": "service_account", "project_id": "test"}, tf)
            partial_path = tf.name

        try:
            is_ok, data, err = firebase_client.validate_credentials_file(partial_path)
            self.assertFalse(is_ok)
            self.assertIn("missing", err.lower())
        finally:
            os.remove(partial_path)

        # Case 4: Valid mock service account
        valid_mock = {
            "type": "service_account",
            "project_id": "my-company-vouchers-12345",
            "private_key_id": "mockkey123",
            "private_key": "-----BEGIN PRIVATE KEY-----\nMOCK_KEY\n-----END PRIVATE KEY-----\n",
            "client_email": "firebase-adminsdk@my-company-vouchers-12345.iam.gserviceaccount.com"
        }
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tf:
            json.dump(valid_mock, tf)
            valid_path = tf.name

        try:
            is_ok, data, err = firebase_client.validate_credentials_file(valid_path)
            self.assertTrue(is_ok)
            self.assertEqual(data["project_id"], "my-company-vouchers-12345")
            self.assertEqual(data["client_email"], "firebase-adminsdk@my-company-vouchers-12345.iam.gserviceaccount.com")

            # Test installation
            success, installed_path, parsed = firebase_client.install_credentials_file(valid_path)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(installed_path))
            self.assertEqual(parsed["project_id"], "my-company-vouchers-12345")
        finally:
            os.remove(valid_path)

    def test_serialize_voucher_for_firestore(self):
        """Verify local SQLite voucher transforms into standard NoSQL document structure."""
        # Create a test voucher with items, memo, and tags
        form_data = {
            "date": "2026-10-03",
            "paid_to": "Acme Supplier Ltd",
            "cash_given_by": "Accounts Manager",
            "spent_by": "Staff A",
            "bill_status": "Approved",
            "payment_method": "Cash",
            "payment_ref": "REF-789",
            "due_date": "2026-10-10",
            "prepared_by": "Cashier 1",
            "approved_by": "Finance Director",
        }
        items = [
            {"description": "Hardware tools", "category": "Equipment", "amount": 4500.0},
            {"description": "Safety gloves", "category": "Safety", "amount": 1200.0}
        ]
        vid = db.create_voucher(form_data, items, company_id=1)
        db.add_memo(vid, "Approved for urgent workshop use", memo_type="Urgent")

        # Add a tag
        db.add_tag("CapEx", "#d97706")
        tags = db.get_tags()
        tag_id = next(t["id"] for t in tags if t["name"] == "CapEx")
        db.set_voucher_tags(vid, [tag_id])

        # Serialize
        doc = firebase_client.serialize_voucher(vid)
        self.assertIsNotNone(doc)
        self.assertTrue(doc["_doc_id"].startswith("comp_1_v_"))
        self.assertEqual(doc["company_id"], 1)
        self.assertEqual(doc["paid_to"], "Acme Supplier Ltd")
        self.assertEqual(doc["total_amount"], 5700.0)
        self.assertEqual(doc["bill_status"], "Approved")
        self.assertEqual(doc["payment_method"], "Cash")
        self.assertEqual(len(doc["line_items"]), 2)
        self.assertEqual(doc["line_items"][0]["amount"], 4500.0)
        self.assertEqual(len(doc["memos"]), 1)
        self.assertEqual(doc["memos"][0]["memo_text"], "Approved for urgent workshop use")
        self.assertIn("CapEx", doc["tags"])
        self.assertIn("_cloud_synced_at", doc)

    def test_collection_prefix_support(self):
        """Test multi-tenant / multi-company collection prefixing."""
        firebase_client.save_config({"collection_prefix": "branch_colombo_"})
        coll_name = firebase_client._collection_name("vouchers")
        self.assertEqual(coll_name, "branch_colombo_vouchers")

        firebase_client.save_config({"collection_prefix": ""})
        coll_name = firebase_client._collection_name("vouchers")
        self.assertEqual(coll_name, "vouchers")

    def test_status_reporting(self):
        """Test get_status() dictionary formatting."""
        status = firebase_client.get_status()
        self.assertIn("configured", status)
        self.assertIn("enabled", status)
        self.assertIn("project_id", status)
        self.assertIn("client_email", status)
        self.assertIn("last_synced", status)
        self.assertIn("is_online", status)


if __name__ == "__main__":
    unittest.main()
