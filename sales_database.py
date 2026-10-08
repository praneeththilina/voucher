"""Sales items, inventory and customer-payment accounting services."""

from __future__ import annotations

from datetime import datetime

import database as db


def _setting_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_sales_preferences(company_id: int | None = None) -> dict:
    """Return company-scoped sales, VAT, discount and inventory settings."""
    company_id = company_id or db.get_active_company_id()
    prefix = f"company:{company_id}:sales:"
    return {
        "inventory_enabled": _setting_bool(
            db.get_app_setting(prefix + "inventory_enabled", "0")
        ),
        "sales_tax_enabled": _setting_bool(
            db.get_app_setting(prefix + "sales_tax_enabled", "1"), True
        ),
        "discounts_enabled": _setting_bool(
            db.get_app_setting(prefix + "discounts_enabled", "1"), True
        ),
        "allow_negative_stock": _setting_bool(
            db.get_app_setting(prefix + "allow_negative_stock", "0")
        ),
    }


def save_sales_preferences(company_id: int, values: dict) -> bool:
    """Persist company-scoped sales preferences."""
    prefix = f"company:{int(company_id)}:sales:"
    keys = (
        "inventory_enabled",
        "sales_tax_enabled",
        "discounts_enabled",
        "allow_negative_stock",
    )
    return all(
        db.set_app_setting(prefix + key, "1" if values.get(key) else "0")
        for key in keys
    )


def get_sales_items(
    company_id: int | None = None,
    active_only: bool = True,
    search: str | None = None,
    item_type: str | None = None,
    conn=None,
) -> list[dict]:
    """Return product/service items with their linked ledger accounts."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        company_id = company_id or db.get_active_company_id(conn)
        sql = """
            SELECT s.*,
                   ia.account_code AS income_account_code,
                   ia.account_name AS income_account_name,
                   aa.account_code AS inventory_account_code,
                   aa.account_name AS inventory_account_name,
                   ca.account_code AS cogs_account_code,
                   ca.account_name AS cogs_account_name,
                   tr.name AS tax_rate_name,
                   tr.rate AS tax_rate
            FROM sales_items s
            LEFT JOIN chart_of_accounts ia ON ia.id = s.income_account_id
            LEFT JOIN chart_of_accounts aa ON aa.id = s.inventory_asset_account_id
            LEFT JOIN chart_of_accounts ca ON ca.id = s.cogs_account_id
            LEFT JOIN tax_rates tr ON tr.id = s.tax_rate_id
            WHERE s.company_id = ?
        """
        params: list[object] = [company_id]
        if active_only:
            sql += " AND s.is_active = 1"
        if item_type:
            sql += " AND s.item_type = ?"
            params.append(item_type)
        if search:
            sql += " AND (s.name LIKE ? OR s.sku LIKE ? OR s.description LIKE ?)"
            term = f"%{search}%"
            params.extend((term, term, term))
        sql += " ORDER BY s.name COLLATE NOCASE ASC"
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        if close_conn:
            conn.close()


def get_sales_item(item_id: int, conn=None) -> dict | None:
    """Return one product/service item."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM sales_items WHERE id = ?", (int(item_id),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        if close_conn:
            conn.close()


def save_sales_item(data: dict, item_id: int | None = None, conn=None) -> int:
    """Create or update a product/service item and accounting links."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        company_id = int(data.get("company_id") or db.get_active_company_id(conn))
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError("Item name is required.")
        item_kind = str(data.get("item_type") or "Service").strip()
        if item_kind not in {"Service", "Non-inventory", "Inventory"}:
            raise ValueError("Invalid item type.")
        inventory_enabled = get_sales_preferences(company_id)["inventory_enabled"]
        existing_item = get_sales_item(item_id, conn=conn) if item_id else None
        if (
            item_kind == "Inventory"
            and not inventory_enabled
            and not (existing_item and existing_item.get("item_type") == "Inventory")
        ):
            raise ValueError("Enable inventory tracking in Preferences first.")
        payload = (
            name,
            str(data.get("sku") or "").strip(),
            item_kind,
            str(data.get("description") or "").strip(),
            float(data.get("sales_price") or 0.0),
            data.get("income_account_id"),
            1 if data.get("taxable", True) else 0,
            data.get("tax_rate_id"),
            float(data.get("purchase_cost") or 0.0),
            data.get("expense_account_id"),
            data.get("inventory_asset_account_id"),
            data.get("cogs_account_id"),
            float(data.get("quantity_on_hand") or 0.0),
            float(data.get("reorder_point") or 0.0),
            str(data.get("as_of_date") or "").strip(),
            1 if data.get("is_active", True) else 0,
        )
        with conn:
            if item_id:
                row = conn.execute(
                    "SELECT company_id FROM sales_items WHERE id = ?",
                    (int(item_id),),
                ).fetchone()
                if not row or int(row["company_id"]) != company_id:
                    raise ValueError("Sales item not found for this company.")
                conn.execute("""
                    UPDATE sales_items SET
                        name = ?, sku = ?, item_type = ?, description = ?,
                        sales_price = ?, income_account_id = ?, taxable = ?,
                        tax_rate_id = ?, purchase_cost = ?, expense_account_id = ?,
                        inventory_asset_account_id = ?, cogs_account_id = ?,
                        quantity_on_hand = ?, reorder_point = ?, as_of_date = ?,
                        is_active = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, payload + (int(item_id),))
                return int(item_id)
            cursor = conn.execute("""
                INSERT INTO sales_items (
                    company_id, name, sku, item_type, description, sales_price,
                    income_account_id, taxable, tax_rate_id, purchase_cost,
                    expense_account_id, inventory_asset_account_id,
                    cogs_account_id, quantity_on_hand, reorder_point,
                    as_of_date, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (company_id,) + payload)
            return int(cursor.lastrowid)
    finally:
        if close_conn:
            conn.close()


def deactivate_sales_item(item_id: int, conn=None) -> bool:
    """Deactivate an item without damaging historical invoice references."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        with conn:
            result = conn.execute(
                "UPDATE sales_items SET is_active = 0, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (int(item_id),),
            )
        return result.rowcount > 0
    finally:
        if close_conn:
            conn.close()


def get_inventory_movements(item_id: int, conn=None) -> list[dict]:
    """Return the stock audit trail for an inventory item."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        rows = conn.execute("""
            SELECT * FROM inventory_movements
            WHERE item_id = ? ORDER BY movement_date DESC, id DESC
        """, (int(item_id),)).fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_conn:
            conn.close()


def prepare_invoice_lines(
    lines_data: list[dict], invoice_data: dict
) -> tuple[list[dict], dict]:
    """Calculate item, subtotal and discount lines for the AR engine."""
    if not lines_data:
        raise ValueError("An invoice must contain at least one line item.")
    prepared: list[dict] = []
    running_base = 0.0
    running_tax = 0.0
    line_discounts = 0.0
    for source in lines_data:
        line = dict(source)
        line_kind = str(line.get("line_type") or "Item")
        line["line_type"] = line_kind
        if line_kind == "Subtotal":
            line.update(
                quantity=0.0,
                unit_price=0.0,
                tax_rate=0.0,
                tax_amount=0.0,
                line_total=round(running_base + running_tax, 2),
            )
        elif line_kind == "Discount":
            discount_kind = str(line.get("discount_type") or "Percent")
            value = max(0.0, float(line.get("discount_value") or 0.0))
            if discount_kind == "Percent":
                amount = round(running_base * value / 100.0, 2)
            else:
                amount = min(round(value, 2), max(0.0, running_base))
            tax_reduction = (
                round(running_tax * amount / running_base, 2)
                if running_base > 0.0
                else 0.0
            )
            line_discounts += amount
            line.update(
                quantity=0.0,
                unit_price=0.0,
                tax_rate=0.0,
                tax_amount=-tax_reduction,
                line_total=-(amount + tax_reduction),
                discount_type=discount_kind,
                discount_value=value,
            )
            running_base = max(0.0, running_base - amount)
            running_tax = max(0.0, running_tax - tax_reduction)
        else:
            quantity = float(line.get("quantity") or 0.0)
            price = float(line.get("unit_price") or 0.0)
            tax_rate = float(line.get("tax_rate") or 0.0)
            if quantity <= 0.0:
                raise ValueError("Item quantities must be greater than zero.")
            base = round(quantity * price, 2)
            tax = round(base * tax_rate, 2)
            line.update(
                quantity=quantity,
                unit_price=price,
                tax_rate=tax_rate,
                tax_amount=tax,
                line_total=round(base + tax, 2),
            )
            running_base += base
            running_tax += tax
        prepared.append(line)

    item_subtotal = sum(
        float(line.get("quantity") or 0.0)
        * float(line.get("unit_price") or 0.0)
        for line in prepared
        if line.get("line_type") == "Item"
    )
    discount_kind = str(invoice_data.get("discount_type") or "Amount")
    discount_value = max(
        0.0,
        float(
            invoice_data.get(
                "discount_value", invoice_data.get("discount_amount", 0.0)
            )
            or 0.0
        ),
    )
    header_discount = (
        round(item_subtotal * discount_value / 100.0, 2)
        if discount_kind == "Percent"
        else round(discount_value, 2)
    )
    normalized = dict(invoice_data)
    normalized["discount_type"] = discount_kind
    normalized["discount_value"] = discount_value
    normalized["discount_amount"] = round(line_discounts + header_discount, 2)
    return prepared, normalized


def invoice_totals(lines_data: list[dict], invoice_data: dict) -> dict:
    """Return consistent invoice totals for previews and persistence."""
    lines, normalized = prepare_invoice_lines(lines_data, invoice_data)
    subtotal = sum(
        float(line.get("quantity") or 0.0)
        * float(line.get("unit_price") or 0.0)
        for line in lines
    )
    tax = sum(float(line.get("tax_amount") or 0.0) for line in lines)
    discount = float(normalized.get("discount_amount") or 0.0)
    return {
        "lines": lines,
        "subtotal": round(subtotal, 2),
        "tax": round(tax, 2),
        "discount": round(discount, 2),
        "total": max(0.0, round(subtotal + tax - discount, 2)),
    }


def _store_invoice_metadata(
    invoice_id: int, lines_data: list[dict], invoice_data: dict, conn
) -> None:
    conn.execute(
        "UPDATE ar_invoices SET discount_type = ?, discount_value = ? "
        "WHERE id = ?",
        (
            invoice_data.get("discount_type", "Amount"),
            float(invoice_data.get("discount_value") or 0.0),
            invoice_id,
        ),
    )
    rows = conn.execute(
        "SELECT id FROM ar_invoice_lines WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()
    if len(rows) != len(lines_data):
        raise ValueError("Invoice line metadata is out of sync.")
    for row, line in zip(rows, lines_data):
        conn.execute("""
            UPDATE ar_invoice_lines
            SET item_id = ?, line_type = ?, discount_type = ?,
                discount_value = ?, line_total = ?, tax_amount = ?
            WHERE id = ?
        """, (
            line.get("item_id"),
            line.get("line_type", "Item"),
            line.get("discount_type", ""),
            float(line.get("discount_value") or 0.0),
            float(line.get("line_total") or 0.0),
            float(line.get("tax_amount") or 0.0),
            row["id"],
        ))


def _validate_inventory(
    company_id: int,
    invoice_id: int | None,
    lines_data: list[dict],
    status: str,
    conn,
) -> None:
    preferences = get_sales_preferences(company_id)
    if not preferences["inventory_enabled"] or status in {"Draft", "Cancelled"}:
        return
    required: dict[int, float] = {}
    for line in lines_data:
        if line.get("line_type") != "Item" or not line.get("item_id"):
            continue
        item = get_sales_item(int(line["item_id"]), conn=conn)
        if item and item["item_type"] == "Inventory":
            required[item["id"]] = required.get(item["id"], 0.0) + float(
                line.get("quantity") or 0.0
            )
    previous: dict[int, float] = {}
    if invoice_id:
        rows = conn.execute("""
            SELECT item_id, SUM(quantity_change) AS quantity
            FROM inventory_movements
            WHERE source_type = 'ar_invoice' AND source_id = ?
            GROUP BY item_id
        """, (invoice_id,)).fetchall()
        previous = {
            row["item_id"]: float(row["quantity"] or 0.0) for row in rows
        }
    for item_id, required_quantity in required.items():
        item = get_sales_item(item_id, conn=conn)
        available = float(item["quantity_on_hand"] or 0.0) - previous.get(
            item_id, 0.0
        )
        if (
            required_quantity > available + 0.000001
            and not preferences["allow_negative_stock"]
        ):
            raise ValueError(
                f"Insufficient stock for {item['name']}. "
                f"Available: {available:,.2f}; requested: {required_quantity:,.2f}."
            )


def _reverse_inventory(invoice_id: int, conn) -> None:
    rows = conn.execute("""
        SELECT item_id, quantity_change FROM inventory_movements
        WHERE source_type = 'ar_invoice' AND source_id = ?
    """, (invoice_id,)).fetchall()
    for row in rows:
        conn.execute(
            "UPDATE sales_items SET quantity_on_hand = quantity_on_hand - ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (float(row["quantity_change"]), row["item_id"]),
        )
    conn.execute(
        "DELETE FROM inventory_movements "
        "WHERE source_type = 'ar_invoice' AND source_id = ?",
        (invoice_id,),
    )


def _sync_inventory(
    invoice_id: int, lines_data: list[dict], status: str, conn
) -> None:
    invoice = conn.execute(
        "SELECT company_id, invoice_date, invoice_number "
        "FROM ar_invoices WHERE id = ?",
        (invoice_id,),
    ).fetchone()
    if not invoice:
        return
    _reverse_inventory(invoice_id, conn)
    preferences = get_sales_preferences(invoice["company_id"])
    if not preferences["inventory_enabled"] or status in {"Draft", "Cancelled"}:
        return
    for line in lines_data:
        if line.get("line_type") != "Item" or not line.get("item_id"):
            continue
        item = get_sales_item(int(line["item_id"]), conn=conn)
        if not item or item["item_type"] != "Inventory":
            continue
        change = -float(line.get("quantity") or 0.0)
        conn.execute(
            "UPDATE sales_items SET quantity_on_hand = quantity_on_hand + ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (change, item["id"]),
        )
        conn.execute("""
            INSERT INTO inventory_movements (
                company_id, item_id, movement_date, quantity_change,
                unit_cost, source_type, source_id, notes
            ) VALUES (?, ?, ?, ?, ?, 'ar_invoice', ?, ?)
        """, (
            invoice["company_id"],
            item["id"],
            invoice["invoice_date"],
            change,
            float(item.get("purchase_cost") or 0.0),
            invoice_id,
            f"Invoice {invoice['invoice_number']}",
        ))


def _append_cogs_journal(
    invoice_id: int, lines_data: list[dict], conn
) -> None:
    invoice = conn.execute(
        "SELECT company_id, status FROM ar_invoices WHERE id = ?",
        (invoice_id,),
    ).fetchone()
    if not invoice or invoice["status"] in {"Draft", "Cancelled"}:
        return
    entry = conn.execute("""
        SELECT id FROM journal_entries
        WHERE source_module = 'ar_invoice' AND source_id = ?
        ORDER BY id DESC LIMIT 1
    """, (invoice_id,)).fetchone()
    if not entry:
        return
    totals: dict[tuple[int, int], float] = {}
    for line in lines_data:
        if line.get("line_type") != "Item" or not line.get("item_id"):
            continue
        item = get_sales_item(int(line["item_id"]), conn=conn)
        if not item or item["item_type"] != "Inventory":
            continue
        amount = round(
            float(line.get("quantity") or 0.0)
            * float(item.get("purchase_cost") or 0.0),
            2,
        )
        if amount <= 0.0:
            continue
        cogs_id = item.get("cogs_account_id")
        asset_id = item.get("inventory_asset_account_id")
        if not cogs_id:
            account = db.get_account_by_code(
                "5110", invoice["company_id"], conn=conn
            )
            cogs_id = account["id"] if account else None
        if not asset_id:
            account = db.get_account_by_code(
                "1310", invoice["company_id"], conn=conn
            )
            asset_id = account["id"] if account else None
        if cogs_id and asset_id:
            key = (int(cogs_id), int(asset_id))
            totals[key] = totals.get(key, 0.0) + amount
    next_order = int(
        conn.execute(
            "SELECT COALESCE(MAX(line_order), 0) FROM journal_lines "
            "WHERE entry_id = ?",
            (entry["id"],),
        ).fetchone()[0]
    ) + 1
    for (cogs_id, asset_id), amount in totals.items():
        conn.execute("""
            INSERT INTO journal_lines (
                entry_id, account_id, debit_amount, credit_amount,
                description, line_order
            ) VALUES (?, ?, ?, 0, '[Inventory COGS]', ?)
        """, (entry["id"], cogs_id, round(amount, 2), next_order))
        next_order += 1
        conn.execute("""
            INSERT INTO journal_lines (
                entry_id, account_id, debit_amount, credit_amount,
                description, line_order
            ) VALUES (?, ?, 0, ?, '[Inventory Asset]', ?)
        """, (entry["id"], asset_id, round(amount, 2), next_order))
        next_order += 1


def create_ar_invoice(
    invoice_data: dict, lines_data: list[dict], conn=None
) -> int:
    """Create an item-aware invoice with discounts, VAT and stock postings."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        prepared, normalized = prepare_invoice_lines(lines_data, invoice_data)
        company_id = int(
            normalized.get("company_id") or db.get_active_company_id(conn)
        )
        _validate_inventory(
            company_id,
            None,
            prepared,
            normalized.get("status", "Draft"),
            conn,
        )
        invoice_id = db.create_ar_invoice(normalized, prepared, conn=conn)
        with conn:
            _store_invoice_metadata(invoice_id, prepared, normalized, conn)
            _sync_inventory(
                invoice_id,
                prepared,
                normalized.get("status", "Draft"),
                conn,
            )
            _append_cogs_journal(invoice_id, prepared, conn)
        return invoice_id
    finally:
        if close_conn:
            conn.close()


def update_ar_invoice(
    invoice_id: int,
    invoice_data: dict,
    lines_data: list[dict],
    conn=None,
) -> bool:
    """Update an item-aware invoice and safely reapply its stock movement."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        prepared, normalized = prepare_invoice_lines(lines_data, invoice_data)
        row = conn.execute(
            "SELECT company_id FROM ar_invoices WHERE id = ?", (invoice_id,)
        ).fetchone()
        if not row:
            raise ValueError("AR Invoice not found.")
        _validate_inventory(
            row["company_id"],
            invoice_id,
            prepared,
            normalized.get("status", "Draft"),
            conn,
        )
        result = db.update_ar_invoice(
            invoice_id, normalized, prepared, conn=conn
        )
        with conn:
            _store_invoice_metadata(invoice_id, prepared, normalized, conn)
            _sync_inventory(
                invoice_id,
                prepared,
                normalized.get("status", "Draft"),
                conn,
            )
            _append_cogs_journal(invoice_id, prepared, conn)
        return result
    finally:
        if close_conn:
            conn.close()


def delete_ar_invoice(
    invoice_id: int, conn=None
) -> tuple[bool, str]:
    """Delete an invoice and restore stock committed by that invoice."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        result = db.delete_ar_invoice(invoice_id, conn=conn)
        if result[0]:
            with conn:
                _reverse_inventory(invoice_id, conn)
        return result
    finally:
        if close_conn:
            conn.close()


def _recalculate_invoice_paid(invoice_id: int, conn) -> None:
    invoice = conn.execute(
        "SELECT total_amount, status FROM ar_invoices WHERE id = ?",
        (invoice_id,),
    ).fetchone()
    if not invoice:
        return
    paid = float(
        conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM ar_receipts "
            "WHERE invoice_id = ?",
            (invoice_id,),
        ).fetchone()[0]
    )
    total = float(invoice["total_amount"] or 0.0)
    if invoice["status"] == "Cancelled":
        status = "Cancelled"
    elif paid >= total - 0.001:
        status = "Paid"
    elif paid > 0.001:
        status = "Partially Paid"
    else:
        status = "Unpaid"
    conn.execute(
        "UPDATE ar_invoices SET paid_amount = ?, status = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (round(paid, 2), status, invoice_id),
    )


def get_customer_payments(
    company_id: int | None = None,
    customer_id: int | None = None,
    unapplied_only: bool = False,
    conn=None,
) -> list[dict]:
    """Return customer payments and their remaining unapplied balance."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        company_id = company_id or db.get_active_company_id(conn)
        sql = """
            SELECT p.*, c.name AS customer_name,
                   ba.account_name AS bank_account_name
            FROM customer_payments p
            JOIN customers c ON c.id = p.customer_id
            LEFT JOIN bank_accounts ba ON ba.id = p.bank_account_id
            WHERE p.company_id = ?
        """
        params: list[object] = [company_id]
        if customer_id:
            sql += " AND p.customer_id = ?"
            params.append(customer_id)
        if unapplied_only:
            sql += " AND p.unapplied_amount > 0.001"
        sql += " ORDER BY p.payment_date DESC, p.id DESC"
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        if close_conn:
            conn.close()


def get_unapplied_bank_receipts(
    company_id: int | None = None, conn=None
) -> list[dict]:
    """Return unmatched imported bank credits available as customer receipts."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        company_id = company_id or db.get_active_company_id(conn)
        rows = conn.execute("""
            SELECT bt.*, ba.account_name, ba.bank_name, ba.currency
            FROM bank_transactions bt
            JOIN bank_accounts ba ON ba.id = bt.bank_account_id
            WHERE ba.company_id = ? AND bt.credit_amount > 0.001
              AND COALESCE(bt.customer_payment_id, 0) = 0
              AND bt.is_matched = 0
            ORDER BY bt.transaction_date DESC, bt.id DESC
        """, (company_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        if close_conn:
            conn.close()


def _payment_accounts(company_id: int, method: str, conn):
    if method == "Cash":
        debit = db.get_account_by_code("1110", company_id, conn=conn)
    elif method == "Undeposited Funds":
        debit = db.get_account_by_code("1190", company_id, conn=conn)
    else:
        debit = db.get_account_by_code(
            "1120", company_id, conn=conn
        ) or db.get_account_by_code("1130", company_id, conn=conn)
    debit = debit or db.get_account_by_code("1110", company_id, conn=conn)
    return (
        debit,
        db.get_account_by_code("1210", company_id, conn=conn),
        db.get_account_by_code("2190", company_id, conn=conn),
    )


def create_customer_payment(
    payment_data: dict,
    allocations: list[dict] | None = None,
    conn=None,
) -> int:
    """Record one currency-consistent receipt and allocate it to open invoices."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        company_id = int(
            payment_data.get("company_id") or db.get_active_company_id(conn)
        )
        customer_id = int(payment_data["customer_id"])
        amount = round(float(payment_data["amount"]), 2)
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")
        customer = db.get_customer_by_id(customer_id, conn=conn)
        if not customer or int(customer["company_id"]) != company_id:
            raise ValueError("Customer not found for this company.")
        payment_date = payment_data.get(
            "payment_date", datetime.now().strftime("%Y-%m-%d")
        )
        db.assert_accounting_period_open(
            company_id, payment_date, "record this customer payment", conn=conn
        )
        currency, settlement_rate = db.normalize_transaction_currency(
            company_id,
            payment_data.get("currency") or customer.get("currency"),
            payment_data.get("exchange_rate"),
            payment_date,
            conn=conn,
        )
        db.ensure_counterparty_currency(
            "customer", customer_id, company_id, currency, conn=conn
        )

        checked: list[tuple[dict, float, float]] = []
        applied = 0.0
        applied_historical_base = 0.0
        for allocation in allocations or []:
            allocation_amount = round(float(allocation.get("amount") or 0), 2)
            if allocation_amount <= 0:
                continue
            invoice_row = conn.execute(
                "SELECT * FROM ar_invoices WHERE id = ? AND company_id = ? "
                "AND customer_id = ?",
                (int(allocation["invoice_id"]), company_id, customer_id),
            ).fetchone()
            if not invoice_row:
                raise ValueError("An allocated invoice does not belong to this customer.")
            invoice = dict(invoice_row)
            if (invoice.get("currency") or currency).upper() != currency:
                raise ValueError("A payment cannot be applied across different currencies.")
            balance = float(invoice["total_amount"] - invoice["paid_amount"])
            if allocation_amount > balance + 0.001:
                raise ValueError(
                    f"Allocation for {invoice['invoice_number']} exceeds its open balance."
                )
            _, invoice_rate = db.normalize_transaction_currency(
                company_id, currency, invoice.get("exchange_rate"),
                invoice.get("invoice_date"), conn=conn
            )
            historical_base = round(allocation_amount * invoice_rate, 2)
            checked.append((invoice, allocation_amount, historical_base))
            applied += allocation_amount
            applied_historical_base += historical_base
        applied = round(applied, 2)
        applied_historical_base = round(applied_historical_base, 2)
        if applied > amount + 0.001:
            raise ValueError("Invoice allocations exceed the payment amount.")
        unapplied = round(amount - applied, 2)
        method = str(payment_data.get("payment_method") or "Cash")
        reference = str(payment_data.get("reference") or "").strip()
        bank_transaction_id = payment_data.get("bank_transaction_id")
        bank_account_id = payment_data.get("bank_account_id")
        if bank_transaction_id:
            bank_row = conn.execute(
                """
                SELECT bt.*, ba.company_id, ba.currency
                FROM bank_transactions bt
                JOIN bank_accounts ba ON ba.id = bt.bank_account_id
                WHERE bt.id = ?
                """,
                (int(bank_transaction_id),),
            ).fetchone()
            if not bank_row or int(bank_row["company_id"]) != company_id:
                raise ValueError("Bank receipt not found for this company.")
            if (bank_row["currency"] or currency).upper() != currency:
                raise ValueError("Imported bank receipt currency does not match the customer.")
            bank_credit = round(float(bank_row["credit_amount"] or 0), 2)
            if abs(bank_credit - amount) > 0.001:
                raise ValueError(
                    "Use the full imported bank receipt amount. Any remainder stays as customer credit."
                )
            bank_account_id = bank_row["bank_account_id"]
            reference = reference or bank_row["reference"] or bank_row["description"]

        payment_account_id = payment_data.get("payment_account_id")
        if payment_account_id:
            debit_account = db.validate_currency_account(
                payment_account_id, company_id, currency, conn=conn
            )
        else:
            home = db.get_company_base_currency(company_id, conn=conn).upper()
            if currency != home:
                raise ValueError(f"Select a {currency} cash or bank ledger account.")
            debit_account, _, _ = _payment_accounts(company_id, method, conn)
            if not debit_account:
                raise ValueError("No suitable home-currency receipt account exists.")
            payment_account_id = debit_account["id"]

        base_amount = round(amount * settlement_rate, 2)
        unapplied_base = round(unapplied * settlement_rate, 2)
        receivable = db.get_account_by_code("1210", company_id, conn=conn)
        advance = db.get_account_by_code("2190", company_id, conn=conn)
        if applied and not receivable:
            raise ValueError("Accounts Receivable ledger 1210 is missing.")
        if unapplied and not advance:
            raise ValueError("Customer Advances ledger 2190 is missing.")

        journal_lines = [{
            "account_id": payment_account_id,
            "debit_amount": base_amount,
            "credit_amount": 0.0,
            "description": f"Receipt - {customer['name']}",
        }]
        if applied:
            journal_lines.append({
                "account_id": receivable["id"],
                "debit_amount": 0.0,
                "credit_amount": applied_historical_base,
                "description": "Applied to customer invoices",
            })
        if unapplied:
            journal_lines.append({
                "account_id": advance["id"],
                "debit_amount": 0.0,
                "credit_amount": unapplied_base,
                "description": "Unapplied customer credit",
            })
        difference = round(
            base_amount - applied_historical_base - unapplied_base, 2
        )
        if difference > 0:
            fx = db.get_account_by_code("4985", company_id, conn=conn)
            journal_lines.append({
                "account_id": fx["id"], "debit_amount": 0.0,
                "credit_amount": difference,
                "description": "Realized foreign exchange gain",
            })
        elif difference < 0:
            fx = db.get_account_by_code("5985", company_id, conn=conn)
            journal_lines.append({
                "account_id": fx["id"], "debit_amount": abs(difference),
                "credit_amount": 0.0,
                "description": "Realized foreign exchange loss",
            })

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO customer_payments (
                    company_id, customer_id, payment_date, amount,
                    applied_amount, unapplied_amount, payment_method,
                    reference, bank_account_id, bank_transaction_id,
                    notes, created_by, currency, exchange_rate, base_amount,
                    payment_account_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, customer_id, payment_date, amount, applied,
                    unapplied, method, reference, bank_account_id,
                    bank_transaction_id, str(payment_data.get("notes") or "").strip(),
                    str(payment_data.get("created_by") or "User"), currency,
                    settlement_rate, base_amount, payment_account_id,
                ),
            )
            payment_id = int(cursor.lastrowid)
            for invoice, allocation_amount, _historical_base in checked:
                conn.execute(
                    "INSERT INTO customer_payment_applications "
                    "(payment_id, invoice_id, amount) VALUES (?, ?, ?)",
                    (payment_id, invoice["id"], allocation_amount),
                )
                conn.execute(
                    """
                    INSERT INTO ar_receipts (
                        invoice_id, company_id, receipt_date, amount,
                        payment_method, reference, bank_account_id, notes,
                        created_by, customer_payment_id, currency,
                        exchange_rate, base_amount, payment_account_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice["id"], company_id, payment_date,
                        allocation_amount, method, reference, bank_account_id,
                        str(payment_data.get("notes") or "").strip(),
                        str(payment_data.get("created_by") or "User"), payment_id,
                        currency, settlement_rate,
                        round(allocation_amount * settlement_rate, 2),
                        payment_account_id,
                    ),
                )
                _recalculate_invoice_paid(invoice["id"], conn)
            if bank_transaction_id:
                conn.execute(
                    "UPDATE bank_transactions SET customer_payment_id = ?, "
                    "is_matched = 1, reconciliation_status = 'matched', "
                    "match_confidence = 1 WHERE id = ?",
                    (payment_id, int(bank_transaction_id)),
                )
            db.create_journal_entry(
                {
                    "company_id": company_id,
                    "entry_date": payment_date,
                    "reference": reference or f"CP-{payment_id}",
                    "description": f"Customer payment - {customer['name']}",
                    "entry_type": "Receipt",
                    "source_module": "customer_payment",
                    "source_id": payment_id,
                    "created_by": payment_data.get("created_by") or "System",
                    "transaction_currency": currency,
                    "exchange_rate": settlement_rate,
                    "foreign_amount": amount,
                },
                journal_lines,
                conn=conn,
            )
        return payment_id
    finally:
        if close_conn:
            conn.close()

def apply_customer_payment(
    payment_id: int, allocations: list[dict], conn=None
) -> float:
    """Apply an existing customer credit to one or more open invoices."""
    close_conn = conn is None
    if conn is None:
        conn = db.get_connection()
    try:
        payment = conn.execute(
            "SELECT * FROM customer_payments WHERE id = ?",
            (int(payment_id),),
        ).fetchone()
        if not payment:
            raise ValueError("Customer payment not found.")
        payment = dict(payment)
        remaining = float(payment["unapplied_amount"] or 0)
        total = round(
            sum(
                max(0.0, float(item.get("amount") or 0))
                for item in allocations
            ),
            2,
        )
        if total <= 0:
            raise ValueError("Enter an amount to apply.")
        if total > remaining + 0.001:
            raise ValueError("Applications exceed the remaining customer credit.")
        checked: list[tuple[dict, float]] = []
        for item in allocations:
            amount = round(float(item.get("amount") or 0), 2)
            if amount <= 0:
                continue
            invoice = conn.execute(
                "SELECT * FROM ar_invoices WHERE id = ? AND company_id = ? "
                "AND customer_id = ?",
                (
                    int(item["invoice_id"]),
                    payment["company_id"],
                    payment["customer_id"],
                ),
            ).fetchone()
            if not invoice:
                raise ValueError(
                    "Invoice does not belong to this payment's customer."
                )
            balance = float(
                invoice["total_amount"] - invoice["paid_amount"]
            )
            if amount > balance + 0.001:
                raise ValueError(
                    f"Application for {invoice['invoice_number']} "
                    "exceeds its balance."
                )
            checked.append((dict(invoice), amount))
        today = datetime.now().strftime("%Y-%m-%d")
        db.assert_accounting_period_open(
            payment["company_id"],
            today,
            "apply this customer credit",
            conn=conn,
        )
        with conn:
            for invoice, amount in checked:
                existing = conn.execute(
                    "SELECT id FROM customer_payment_applications "
                    "WHERE payment_id = ? AND invoice_id = ?",
                    (payment_id, invoice["id"]),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE customer_payment_applications "
                        "SET amount = amount + ?, applied_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?",
                        (amount, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO customer_payment_applications "
                        "(payment_id, invoice_id, amount) VALUES (?, ?, ?)",
                        (payment_id, invoice["id"], amount),
                    )
                conn.execute("""
                    INSERT INTO ar_receipts (
                        invoice_id, company_id, receipt_date, amount,
                        payment_method, reference, bank_account_id, notes,
                        created_by, customer_payment_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    invoice["id"],
                    payment["company_id"],
                    today,
                    amount,
                    "Customer Credit",
                    payment["reference"],
                    payment["bank_account_id"],
                    "Applied from unapplied receipt",
                    "System",
                    payment_id,
                ))
                _recalculate_invoice_paid(invoice["id"], conn)
            conn.execute(
                "UPDATE customer_payments "
                "SET applied_amount = applied_amount + ?, "
                "unapplied_amount = unapplied_amount - ? WHERE id = ?",
                (total, total, payment_id),
            )
        _, receivable, advance = _payment_accounts(
            payment["company_id"], payment["payment_method"], conn
        )
        if receivable and advance:
            db.create_journal_entry({
                "company_id": payment["company_id"],
                "entry_date": today,
                "reference": payment["reference"] or f"CP-{payment_id}",
                "description": "Apply unapplied customer credit",
                "entry_type": "Receipt Allocation",
                "source_module": "customer_payment_application",
                "source_id": payment_id,
            }, [
                {
                    "account_id": advance["id"],
                    "debit_amount": total,
                    "credit_amount": 0.0,
                    "description": "Release customer advance",
                },
                {
                    "account_id": receivable["id"],
                    "debit_amount": 0.0,
                    "credit_amount": total,
                    "description": "Reduce accounts receivable",
                },
            ], conn=conn)
        return round(remaining - total, 2)
    finally:
        if close_conn:
            conn.close()
