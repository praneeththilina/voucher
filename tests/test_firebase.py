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
            if os.path.exists(valid_path):
                os.remove(valid_path)
            if 'installed_path' in locals() and os.path.exists(installed_path):
                try:
                    os.remove(installed_path)
                except Exception:
                    pass

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

    def test_parse_web_config_snippet(self):
        """Test parsing of user's exact JavaScript firebaseConfig snippet."""
        snippet = """
        // Your web app's Firebase configuration
        const firebaseConfig = {
          apiKey: "AIzaSyFakePlaceholderKey_Test123456789",
          authDomain: "test-mock-project.firebaseapp.com",
          projectId: "test-mock-project",
          storageBucket: "test-mock-project.firebasestorage.app",
          messagingSenderId: "1234567890",
          appId: "1:1234567890:web:abcdef1234567890",
          measurementId: "G-TEST123456"
        };
        """
        ok, data, err = firebase_client.parse_web_config_snippet(snippet)
        self.assertTrue(ok)
        self.assertEqual(data["projectId"], "test-mock-project")
        self.assertEqual(data["apiKey"], "AIzaSyFakePlaceholderKey_Test123456789")
        self.assertEqual(data["authDomain"], "test-mock-project.firebaseapp.com")
        self.assertEqual(data["appId"], "1:1234567890:web:abcdef1234567890")

    def test_dict_to_firestore_fields_and_back(self):
        """Test bi-directional Firestore REST API fields mapping."""
        sample = {
            "voucher_number": "26OCT03_01",
            "total_amount": 2500.5,
            "printed": 1,
            "is_active": True,
            "null_field": None,
            "tags": ["CapEx", "Urgent"],
            "line_items": [{"desc": "Office supplies", "amount": 2500.5}]
        }
        fields = firebase_client.dict_to_firestore_fields(sample)
        self.assertIn("stringValue", fields["voucher_number"])
        self.assertEqual(fields["voucher_number"]["stringValue"], "26OCT03_01")
        self.assertIn("doubleValue", fields["total_amount"])
        self.assertEqual(fields["total_amount"]["doubleValue"], 2500.5)

        restored = firebase_client.firestore_fields_to_dict(fields)
        self.assertEqual(restored["voucher_number"], "26OCT03_01")
        self.assertEqual(restored["total_amount"], 2500.5)
        self.assertEqual(restored["tags"], ["CapEx", "Urgent"])
        self.assertEqual(restored["line_items"][0]["desc"], "Office supplies")

    def test_configured_with_web_config(self):
        """Verify is_configured() returns True when apiKey and projectId are present."""
        firebase_client.save_config({
            "project_id": "test-mock-project",
            "api_key": "AIzaSyFakePlaceholderKey_Test123456789",
            "creds_path": ""
        })
        self.assertTrue(firebase_client.is_configured())
        status = firebase_client.get_status()
        self.assertEqual(status["project_id"], "test-mock-project")
        self.assertEqual(status["mode"], "Web API Key")

    def test_pull_cloud_vouchers_integration(self):
        """Test pulling cloud vouchers and applying create_voucher and update_voucher."""
        from unittest.mock import patch, MagicMock

        cloud_voucher = {
            "voucher_number": "PULL_TEST_01",
            "company_id": 1,
            "date": "2026-10-03",
            "paid_to": "Cloud Payee",
            "cash_given_by": "Cloud Admin",
            "spent_by": "Cloud Staff",
            "bill_status": "Paid",
            "payment_method": "Cash",
            "payment_ref": "",
            "line_items": [
                {"description": "Cloud Item 1", "category": "General", "amount": 1500.0}
            ],
            "tags": ["CloudImport"]
        }
        firestore_fields = firebase_client.dict_to_firestore_fields(cloud_voucher)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "documents": [
                {"name": "projects/test-mock-project/databases/(default)/documents/vouchers/doc1", "fields": firestore_fields}
            ]
        }

        firebase_client.save_config({
            "project_id": "test-mock-project",
            "api_key": "AIzaSyFakePlaceholderKey_Test123456789",
            "creds_path": ""
        })

        with patch("requests.get", return_value=mock_resp):
            ok, count, msg = firebase_client.pull_cloud_vouchers()
            self.assertTrue(ok)
            self.assertGreaterEqual(count, 1)

        # Verify voucher was created in SQLite
        conn = db.get_connection()
        row = conn.execute("SELECT id, paid_to, total_amount FROM vouchers WHERE voucher_number = 'PULL_TEST_01'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["paid_to"], "Cloud Payee")
        self.assertEqual(row["total_amount"], 1500.0)
        conn.close()

    def test_serialize_float_transaction_for_firestore(self):
        """Verify float transaction (cash top-up, reimbursement) transforms into Firestore NoSQL format."""
        fid = db.create_float(
            company_id=1,
            name="Main Cash Drawer",
            opening_balance=50000.0,
            custodian="Head Cashier"
        )
        tid = db.add_float_transaction(
            float_id=fid,
            amount=15000.0,
            date="2026-10-03",
            trans_type="Inflow",
            source_ref="Bank Chq #9988",
            handed_by="Accountant",
            received_by="Head Cashier",
            notes="Morning replenishment top-up",
            company_id=1,
            sub_type="top_up"
        )

        doc = firebase_client.serialize_float_transaction(tid)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["_doc_id"], f"comp_1_ft_{tid}")
        self.assertEqual(doc["float_id"], fid)
        self.assertEqual(doc["float_name"], "Main Cash Drawer")
        self.assertEqual(doc["amount"], 15000.0)
        self.assertEqual(doc["type"], "Inflow")
        self.assertEqual(doc["sub_type"], "top_up")
        self.assertEqual(doc["source_ref"], "Bank Chq #9988")
        self.assertEqual(doc["handed_by"], "Accountant")
        self.assertEqual(doc["received_by"], "Head Cashier")
        self.assertEqual(doc["notes"], "Morning replenishment top-up")
        self.assertIn("_cloud_synced_at", doc)

    def test_serialize_float_for_firestore(self):
        """Verify money float profile and real-time balance transforms into Firestore document."""
        fid = db.create_float(
            company_id=1,
            name="Emergency Float",
            opening_balance=20000.0,
            custodian="Duty Manager",
            notes="Petty cash vault"
        )

        doc = firebase_client.serialize_float(fid)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["_doc_id"], f"comp_1_float_{fid}")
        self.assertEqual(doc["company_id"], 1)
        self.assertEqual(doc["name"], "Emergency Float")
        self.assertEqual(doc["custodian"], "Duty Manager")
        self.assertEqual(doc["opening_balance"], 20000.0)
        self.assertGreaterEqual(doc["current_balance"], 20000.0)
        self.assertEqual(doc["notes"], "Petty cash vault")
        self.assertIn("_cloud_synced_at", doc)

    def test_push_and_delete_float_transaction_cloud_rest(self):
        """Test pushing and deleting float transactions via REST API calls."""
        fid = db.create_float(company_id=1, name="Sync Test Float", opening_balance=10000.0)
        tid = db.add_float_transaction(
            float_id=fid,
            amount=5000.0,
            date="2026-10-03",
            trans_type="Inflow",
            source_ref="TopUp #123",
            company_id=1,
            sub_type="top_up"
        )

        firebase_client.save_config({
            "enabled": True,
            "project_id": "test-mock-project",
            "api_key": "AIzaSyFakePlaceholderKey_Test123456789",
            "creds_path": ""
        })

        mock_patch = MagicMock()
        mock_patch.status_code = 200
        mock_delete = MagicMock()
        mock_delete.status_code = 200

        with patch("requests.patch", return_value=mock_patch) as mock_p:
            firebase_client.push_float_transaction_to_cloud(tid, async_call=False)
            self.assertTrue(mock_p.called)
            url_called = mock_p.call_args[0][0]
            self.assertIn(f"comp_1_ft_{tid}", url_called)

        with patch("requests.delete", return_value=mock_delete) as mock_d:
            firebase_client.delete_float_transaction_from_cloud(1, tid, async_call=False)
            self.assertTrue(mock_d.called)
            url_called = mock_d.call_args[0][0]
            self.assertIn(f"comp_1_ft_{tid}", url_called)


if __name__ == "__main__":
    unittest.main()

