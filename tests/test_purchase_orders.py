"""
tests/test_purchase_orders.py
Unit tests for Purchase Orders (PO) & Goods Received Notes (GRN) Module (v4.0).
Tests PO CRUD, auto-numbering, line items, GRN partial/full receipt updates,
GRN rollback, 3-way matching AP invoice generation, and ReportLab PDF output.
"""

import os
import tempfile
import unittest
from datetime import datetime

import database as db
import po_printer


class TestPurchaseOrders(unittest.TestCase):
    """Test suite verifying POs, GRNs, 3-way matching, and PDF generation."""

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

        self.company_id = 1
        self.created_temp_files = []

        # Create a test supplier
        self.supplier_id = db.create_supplier({
            "company_id": self.company_id,
            "name": "Global Tech Hardware Ltd",
            "contact_person": "Alex Mercer",
            "email": "alex@globaltech.com",
            "phone": "+94 11 234 5678",
            "address": "45 Hardware Lane, Colombo 03",
            "tax_number": "VAT-998877",
            "payment_terms": "Net 30",
        })

    def tearDown(self):
        for fpath in self.created_temp_files:
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

        try:
            os.close(self.db_fd)
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass

        db.DB_PATH = self.orig_db_path

    def test_po_crud_and_autonumbering(self):
        """Test PO creation, auto-numbering, retrieval, line calculation, and update."""
        next_num = db.get_next_po_number(self.company_id)
        current_year = datetime.now().year
        self.assertEqual(next_num, f"PO-{current_year}-0001")

        lines = [
            {
                "item_code": "LAP-01",
                "description": "Dell Latitude 5540 Core i7",
                "quantity": 5.0,
                "unit": "Units",
                "unit_price": 250000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 1250000.0,
                "notes": "With 3-year warranty",
            },
            {
                "item_code": "MON-24",
                "description": "Dell 24-inch UltraSharp Monitors",
                "quantity": 10.0,
                "unit": "Units",
                "unit_price": 45000.0,
                "tax_rate": 18.0,
                "tax_amount": 81000.0,
                "line_total": 450000.0,
                "notes": "HDMI cables included",
            },
        ]

        po_data = {
            "company_id": self.company_id,
            "po_number": next_num,
            "po_date": "2026-10-01",
            "delivery_date": "2026-10-15",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "payment_terms": "Net 30",
            "shipping_address": "Main Office Warehouse, Colombo",
            "status": "Issued",
            "subtotal": 1700000.0,
            "tax_amount": 81000.0,
            "total_amount": 1781000.0,
            "notes": "Urgent procurement for engineering team",
            "terms_conditions": "Subject to QA hardware inspection upon delivery.",
        }

        po_id = db.create_purchase_order(po_data, lines)
        self.assertGreater(po_id, 0)

        # Retrieve PO
        po = db.get_purchase_order(po_id)
        self.assertIsNotNone(po)
        self.assertEqual(po["po_number"], f"PO-{current_year}-0001")
        self.assertEqual(po["supplier_name"], "Global Tech Hardware Ltd")
        self.assertEqual(po["total_amount"], 1781000.0)
        self.assertEqual(po["status"], "Issued")
        self.assertEqual(len(po["lines"]), 2)
        self.assertEqual(po["lines"][0]["received_qty"], 0.0)
        self.assertEqual(po["lines"][1]["received_qty"], 0.0)

        # Check next number increment
        next_num_2 = db.get_next_po_number(self.company_id)
        self.assertEqual(next_num_2, f"PO-{current_year}-0002")

        # Update PO status
        db.update_po_status(po_id, "Confirmed")
        updated_po = db.get_purchase_order(po_id)
        self.assertEqual(updated_po["status"], "Confirmed")

        # List POs
        all_pos = db.get_purchase_orders(self.company_id)
        self.assertEqual(len(all_pos), 1)

    def test_grn_partial_and_full_receipt(self):
        """Test Goods Received Notes (GRN) workflow, line received_qty increment and PO status auto-update."""
        po_lines = [
            {
                "item_code": "ROUT-01",
                "description": "Cisco Catalyst Switch 24-Port",
                "quantity": 10.0,
                "unit": "Units",
                "unit_price": 80000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 800000.0,
            }
        ]
        po_id = db.create_purchase_order({
            "company_id": self.company_id,
            "po_number": "PO-TEST-001",
            "po_date": "2026-10-02",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "status": "Issued",
            "subtotal": 800000.0,
            "tax_amount": 0.0,
            "total_amount": 800000.0,
        }, po_lines)

        po = db.get_purchase_order(po_id)
        line_id = po["lines"][0]["id"]

        # 1. Partial receipt: Receive 4 out of 10
        next_grn_num = db.get_next_grn_number(self.company_id)
        current_year = datetime.now().year
        self.assertEqual(next_grn_num, f"GRN-{current_year}-0001")

        grn_1_id = db.create_goods_received_note({
            "company_id": self.company_id,
            "grn_number": next_grn_num,
            "grn_date": "2026-10-05",
            "po_id": po_id,
            "po_number": po["po_number"],
            "supplier_id": self.supplier_id,
            "supplier_name": po["supplier_name"],
            "delivery_note_ref": "DN-8812",
            "carrier": "DHL Express",
            "received_by": "Warehouse Supervisor",
            "inspection_status": "Passed",
            "notes": "First partial batch received in good condition",
        }, [
            {
                "po_line_id": line_id,
                "item_code": "ROUT-01",
                "description": "Cisco Catalyst Switch 24-Port",
                "ordered_qty": 10.0,
                "received_qty": 4.0,
                "accepted_qty": 4.0,
                "rejected_qty": 0.0,
                "unit": "Units",
                "remarks": "Box 1 & 2 inspected",
            }
        ])

        # Verify PO updated to Partially Received
        po_after_grn1 = db.get_purchase_order(po_id)
        self.assertEqual(po_after_grn1["status"], "Partially Received")
        self.assertEqual(po_after_grn1["lines"][0]["received_qty"], 4.0)

        # 2. Final receipt: Receive remaining 6 units
        grn_2_num = db.get_next_grn_number(self.company_id)
        self.assertEqual(grn_2_num, f"GRN-{current_year}-0002")

        grn_2_id = db.create_goods_received_note({
            "company_id": self.company_id,
            "grn_number": grn_2_num,
            "grn_date": "2026-10-08",
            "po_id": po_id,
            "po_number": po["po_number"],
            "supplier_id": self.supplier_id,
            "supplier_name": po["supplier_name"],
            "delivery_note_ref": "DN-8899",
            "carrier": "DHL Express",
            "received_by": "Warehouse Supervisor",
            "inspection_status": "Passed",
            "notes": "Balance batch received",
        }, [
            {
                "po_line_id": line_id,
                "item_code": "ROUT-01",
                "description": "Cisco Catalyst Switch 24-Port",
                "ordered_qty": 10.0,
                "received_qty": 6.0,
                "accepted_qty": 6.0,
                "rejected_qty": 0.0,
                "unit": "Units",
                "remarks": "Box 3 & 4 inspected",
            }
        ])

        # Verify PO updated to Fully Received
        po_after_grn2 = db.get_purchase_order(po_id)
        self.assertEqual(po_after_grn2["status"], "Fully Received")
        self.assertEqual(po_after_grn2["lines"][0]["received_qty"], 10.0)

        # Verify GRN listing for PO
        po_grns = db.get_goods_received_notes_for_po(po_id)
        self.assertEqual(len(po_grns), 2)

    def test_grn_deletion_and_rollback(self):
        """Test that deleting a GRN rolls back the received quantities on PO lines."""
        po_lines = [
            {
                "item_code": "SRV-01",
                "description": "Rackmount Server Chassis",
                "quantity": 2.0,
                "unit": "Units",
                "unit_price": 500000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 1000000.0,
            }
        ]
        po_id = db.create_purchase_order({
            "company_id": self.company_id,
            "po_number": "PO-ROLLBACK-01",
            "po_date": "2026-10-03",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "status": "Issued",
            "subtotal": 1000000.0,
            "tax_amount": 0.0,
            "total_amount": 1000000.0,
        }, po_lines)

        po = db.get_purchase_order(po_id)
        line_id = po["lines"][0]["id"]

        grn_id = db.create_goods_received_note({
            "company_id": self.company_id,
            "grn_number": "GRN-ROLLBACK-01",
            "grn_date": "2026-10-04",
            "po_id": po_id,
            "po_number": po["po_number"],
            "supplier_id": self.supplier_id,
            "supplier_name": po["supplier_name"],
            "received_by": "Logistics Officer",
        }, [
            {
                "po_line_id": line_id,
                "item_code": "SRV-01",
                "description": "Rackmount Server Chassis",
                "ordered_qty": 2.0,
                "received_qty": 2.0,
                "accepted_qty": 2.0,
                "rejected_qty": 0.0,
                "unit": "Units",
            }
        ])

        po_rec = db.get_purchase_order(po_id)
        self.assertEqual(po_rec["status"], "Fully Received")
        self.assertEqual(po_rec["lines"][0]["received_qty"], 2.0)

        # Delete GRN
        deleted = db.delete_goods_received_note(grn_id)
        self.assertTrue(deleted)

        # PO line received_qty rolled back
        po_rolled_back = db.get_purchase_order(po_id)
        self.assertEqual(po_rolled_back["lines"][0]["received_qty"], 0.0)
        self.assertEqual(po_rolled_back["status"], "Issued")

    def test_three_way_matching_ap_invoice_generation(self):
        """Test automated 3-way matching conversion from PO to AP Invoice."""
        po_lines = [
            {
                "item_code": "CAB-CAT6",
                "description": "Cat6 Network Cable Roll 305m",
                "quantity": 10.0,
                "unit": "Rolls",
                "unit_price": 18000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 180000.0,
            }
        ]
        po_id = db.create_purchase_order({
            "company_id": self.company_id,
            "po_number": "PO-MATCH-001",
            "po_date": "2026-10-04",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "payment_terms": "Net 30",
            "status": "Issued",
            "subtotal": 180000.0,
            "tax_amount": 0.0,
            "total_amount": 180000.0,
        }, po_lines)

        # Convert to AP Invoice
        inv_id = db.create_ap_invoice_from_po(
            po_id=po_id,
            invoice_number="INV-GT-9921",
            invoice_date="2026-10-05",
            due_date="2026-11-04"
        )
        self.assertGreater(inv_id, 0)

        # Retrieve created AP Invoice
        res = db.get_ap_invoice(inv_id)
        self.assertIsNotNone(res)
        inv = res["invoice"]
        self.assertEqual(inv["supplier_id"], self.supplier_id)
        self.assertEqual(inv["po_id"], po_id)
        self.assertEqual(inv["total_amount"], 180000.0)

        # Verify auto-journal double entry created for AP Invoice
        jes = db.get_journal_entries(self.company_id, search=inv["invoice_number"])
        self.assertTrue(len(jes) > 0)
        je = db.get_journal_entry(jes[0]["id"])
        self.assertIsNotNone(je)
        # Check balanced entry
        debits = sum(l["debit_amount"] for l in je["lines"])
        credits = sum(l["credit_amount"] for l in je["lines"])
        self.assertAlmostEqual(debits, 180000.0, places=2)
        self.assertAlmostEqual(credits, 180000.0, places=2)

    def test_po_pdf_generation(self):
        """Test PDF generation for Purchase Order."""
        lines = [
            {
                "item_code": "LAP-01",
                "description": "Dell Latitude 5540 Core i7 Laptop",
                "quantity": 2.0,
                "unit": "Units",
                "unit_price": 250000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 500000.0,
            }
        ]
        po_id = db.create_purchase_order({
            "company_id": self.company_id,
            "po_number": "PO-PDF-001",
            "po_date": "2026-10-06",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "payment_terms": "Net 30",
            "status": "Issued",
            "subtotal": 500000.0,
            "tax_amount": 0.0,
            "total_amount": 500000.0,
            "notes": "Delivery within 5 business days",
            "terms_conditions": "Full manufacturer warranty applies.",
        }, lines)

        po = db.get_purchase_order(po_id)
        comp = db.get_company(self.company_id)

        fd, out_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.created_temp_files.append(out_path)

        res_path = po_printer.generate_purchase_order_pdf(po, comp, output_path=out_path)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 2000)

    def test_grn_pdf_generation(self):
        """Test PDF generation for Goods Received Note."""
        po_lines = [
            {
                "item_code": "MON-24",
                "description": "Dell 24-inch Monitors",
                "quantity": 5.0,
                "unit": "Units",
                "unit_price": 45000.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "line_total": 225000.0,
            }
        ]
        po_id = db.create_purchase_order({
            "company_id": self.company_id,
            "po_number": "PO-GRNPDF-001",
            "po_date": "2026-10-06",
            "supplier_id": self.supplier_id,
            "supplier_name": "Global Tech Hardware Ltd",
            "status": "Issued",
            "subtotal": 225000.0,
            "tax_amount": 0.0,
            "total_amount": 225000.0,
        }, po_lines)
        po = db.get_purchase_order(po_id)

        grn_id = db.create_goods_received_note({
            "company_id": self.company_id,
            "grn_number": "GRN-PDF-001",
            "grn_date": "2026-10-07",
            "po_id": po_id,
            "po_number": po["po_number"],
            "supplier_id": self.supplier_id,
            "supplier_name": po["supplier_name"],
            "delivery_note_ref": "DN-4431",
            "carrier": "Transporter Logistics",
            "received_by": "Storekeeper John",
            "inspection_status": "Passed",
            "notes": "All monitors intact without carton damage",
        }, [
            {
                "po_line_id": po["lines"][0]["id"],
                "item_code": "MON-24",
                "description": "Dell 24-inch Monitors",
                "ordered_qty": 5.0,
                "received_qty": 5.0,
                "accepted_qty": 5.0,
                "rejected_qty": 0.0,
                "unit": "Units",
            }
        ])

        grn = db.get_goods_received_note(grn_id)
        comp = db.get_company(self.company_id)

        fd, out_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.created_temp_files.append(out_path)

        res_path = po_printer.generate_grn_pdf(grn, comp, output_path=out_path)
        self.assertTrue(os.path.exists(res_path))
        self.assertGreater(os.path.getsize(res_path), 2000)


if __name__ == "__main__":
    unittest.main()
