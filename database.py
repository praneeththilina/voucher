"""
Database layer for the Voucher Printing Tool.
Handles all SQLite operations including CRUD for vouchers,
line items, categories, people, attachments, memos, settings.
"""

import sqlite3
import os
import sys
import uuid
import hashlib
from datetime import datetime, timedelta, date as _date

DEFAULT_ADMIN_PASSWORD = "12345"


def get_app_base_dir():
    """Get the persistent base directory of the application."""
    if getattr(sys, "frozen", False):
        # Running as a compiled PyInstaller executable
        return os.path.dirname(os.path.abspath(sys.executable))
    # Running in normal Python environment
    return os.path.dirname(os.path.abspath(__file__))


DB_DIR = os.path.join(get_app_base_dir(), "data")
DB_PATH = os.path.join(DB_DIR, "vouchers.db")
ATTACHMENTS_DIR = os.path.join(DB_DIR, "attachments")
BACKUP_DIR = os.path.join(DB_DIR, "backups")
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_database(reason="auto"):
    """
    Safely creates a timestamped snapshot of vouchers.db.
    Retains the last 5 backups to conserve disk space.
    """
    if not os.path.exists(DB_PATH):
        return None
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"vouchers_backup_{ts}_{reason}.db"
        dest_path = os.path.join(BACKUP_DIR, backup_filename)

        source_conn = sqlite3.connect(DB_PATH)
        dest_conn = sqlite3.connect(dest_path)
        with dest_conn:
            source_conn.backup(dest_conn)
        dest_conn.close()
        source_conn.close()

        # Rotate backups (keep last 5)
        existing = sorted([
            os.path.join(BACKUP_DIR, f)
            for f in os.listdir(BACKUP_DIR)
            if f.startswith("vouchers_backup_") and f.endswith(".db")
        ], key=os.path.getmtime)
        while len(existing) > 5:
            oldest = existing.pop(0)
            try:
                os.remove(oldest)
            except Exception:
                pass
        return dest_path
    except Exception as e:
        print(f"Notice: Database backup skipped/failed: {e}")
        return None


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations(cursor):
    """
    Automatic Non-Destructive Database Migration Pipeline.
    Tracks schema versions in `schema_migrations` and applies additions safely.
    NEVER deletes or drops user records.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    applied = {
        row[0] for row in cursor.execute("SELECT version FROM schema_migrations").fetchall()
    }

    def _ensure_col(table, col_name, col_def):
        try:
            cols = [c[1].lower() for c in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            if col_name.lower() not in cols:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
        except Exception as e:
            print(f"Notice: Ensuring column {table}.{col_name}: {e}")

    # Migration 1: Base columns across people, categories, attachments, companies
    if 1 not in applied:
        _ensure_col("people", "is_active", "INTEGER DEFAULT 1")
        _ensure_col("categories", "is_active", "INTEGER DEFAULT 1")
        _ensure_col("attachments", "file_path", "TEXT")
        _ensure_col("attachments", "file_size", "INTEGER")
        _ensure_col("companies", "voucher_format", "TEXT DEFAULT 'date_based'")
        _ensure_col("companies", "custom_prefix", "TEXT DEFAULT 'V-'")
        _ensure_col("companies", "custom_start", "INTEGER DEFAULT 1")
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (1, 'base_schema_columns')")

    # Migration 2: Multi-company support & performance indexes
    if 2 not in applied:
        _ensure_col("vouchers", "company_id", "INTEGER NOT NULL DEFAULT 1")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_comp_date ON vouchers (company_id, date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vouchers_comp_status ON vouchers (company_id, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_vid ON attachments (voucher_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_line_items_vid ON line_items (voucher_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memos_vid ON memos (voucher_id)")
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (2, 'multi_company_and_indexes')")

    # Migration 3: Monthly numbering format support (e.g. 26AUG_01)
    if 3 not in applied:
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (3, 'monthly_numbering_support')")


def init_db():
    """Initialize the database schema and run non-destructive migrations."""
    # Pre-migration safety backup
    backup_database(reason="pre_migration")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL COLLATE NOCASE,
            usage_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL DEFAULT 1,
            voucher_number TEXT NOT NULL,
            date TEXT NOT NULL,
            paid_to TEXT NOT NULL,
            cash_given_by TEXT NOT NULL,
            spent_by TEXT,
            total_amount REAL NOT NULL DEFAULT 0,
            bill_status TEXT DEFAULT 'Pending',
            status TEXT DEFAULT 'Active',
            prepared_by TEXT,
            approved_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            printed INTEGER DEFAULT 0,
            UNIQUE(company_id, voucher_number)
        );

        CREATE TABLE IF NOT EXISTS line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT,
            file_size INTEGER,
            file_data BLOB,
            file_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_id INTEGER NOT NULL,
            memo_text TEXT NOT NULL,
            memo_type TEXT DEFAULT 'General',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (voucher_id) REFERENCES vouchers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            tagline TEXT DEFAULT '',
            address TEXT DEFAULT '',
            contact TEXT DEFAULT '',
            email TEXT DEFAULT '',
            logo BLOB,
            voucher_format TEXT DEFAULT 'date_based',
            custom_prefix TEXT DEFAULT 'V-',
            custom_start INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Seed default Company 1 and Company 2 profiles
    cursor.execute("""
        INSERT OR IGNORE INTO companies (id, name, tagline, address, contact, email, voucher_format, custom_prefix, custom_start)
        VALUES (1, 'Company 1', 'Main Company', '', '', '', 'date_based', 'V-', 1)
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO companies (id, name, tagline, address, contact, email, voucher_format, custom_prefix, custom_start)
        VALUES (2, 'Company 2', 'Secondary Profile', '', '', '', 'date_based', 'C2-', 1)
    """)

    # Run non-destructive automatic schema migrations
    run_migrations(cursor)

    # Enable WAL mode and NORMAL synchronous for high-performance concurrent writes
    try:
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass

    # Default settings: default active company = 1 & admin password hash
    default_admin_hash = hashlib.sha256(DEFAULT_ADMIN_PASSWORD.encode("utf-8")).hexdigest()
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_password_hash', ?)",
        (default_admin_hash,)
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('active_company_id', '1')"
    )
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('voucher_format', 'date_based')"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('custom_prefix', 'V-')"
    )
    cursor.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('custom_start', '1')"
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Company Profiles & Active Company Management
# ---------------------------------------------------------------------------

def get_active_company_id():
    """Return the currently active company ID (1 or 2, default 1)."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = 'active_company_id'").fetchone()
    conn.close()
    if row:
        try:
            return int(row["value"])
        except ValueError:
            return 1
    return 1


def set_active_company_id(company_id):
    """Set the currently active company ID (1 or 2)."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_company_id', ?)",
        (str(company_id),)
    )
    conn.commit()
    conn.close()


def get_company(company_id):
    """Return the company profile dict for the given company_id."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_companies():
    """Return list of all company profile dicts ordered by id."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM companies ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_company(company_id, data):
    """
    Save or update company profile fields.
    data can contain:
      - name, tagline, address, contact, email, voucher_format, custom_prefix, custom_start
      - logo: bytes to update logo, b"" to remove/clear logo, or omitted to leave unchanged
    """
    conn = get_connection()
    exists = conn.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO companies (id, name) VALUES (?, ?)",
            (company_id, data.get("name", f"Company {company_id}"))
        )

    fields = []
    params = []
    for key in ["name", "tagline", "address", "contact", "email", "voucher_format", "custom_prefix", "custom_start"]:
        if key in data:
            fields.append(f"{key} = ?")
            params.append(data[key])

    if "logo" in data:
        logo_val = data["logo"]
        if logo_val == b"":
            fields.append("logo = NULL")
        elif isinstance(logo_val, (bytes, bytearray)):
            fields.append("logo = ?")
            params.append(logo_val)

    if fields:
        params.append(company_id)
        sql = f"UPDATE companies SET {', '.join(fields)} WHERE id = ?"
        conn.execute(sql, params)
        conn.commit()

    conn.close()


# ---------------------------------------------------------------------------
# Voucher CRUD
# ---------------------------------------------------------------------------

def get_next_voucher_number(company_id=None, voucher_date=None):
    """
    Generate the next voucher number for the given company (or active company)
    based on the company's configured format and optional voucher_date.
    Formats:
      - 'date_based' : YYYYMMDD-001 format, resets daily based on voucher_date.
                       Guarantees no collision by verifying against existing vouchers in DB.
      - 'custom'     : <prefix><zero-padded number>  e.g. V-0042
    """
    if company_id is None:
        company_id = get_active_company_id()

    conn = get_connection()
    comp = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if comp:
        fmt = comp["voucher_format"] or "date_based"
        custom_prefix = comp["custom_prefix"] or "V-"
        try:
            custom_start = int(comp["custom_start"] or 1)
        except ValueError:
            custom_start = 1
    else:
        settings = _get_all_settings(conn)
        fmt = settings.get("voucher_format", "date_based")
        custom_prefix = settings.get("custom_prefix", "V-")
        try:
            custom_start = int(settings.get("custom_start", "1"))
        except ValueError:
            custom_start = 1

    if fmt == "date_based":
        if voucher_date:
            clean_date = str(voucher_date).replace("-", "").replace("/", "").strip()
            if len(clean_date) >= 8 and clean_date[:8].isdigit():
                date_prefix = clean_date[:8]
            else:
                date_prefix = _date.today().strftime("%Y%m%d")
        else:
            date_prefix = _date.today().strftime("%Y%m%d")

        # Query all vouchers matching V-{date_prefix} or {date_prefix} for this company
        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND (voucher_number LIKE ? OR voucher_number LIKE ?) ORDER BY id DESC",
            (company_id, f"V-{date_prefix}%", f"{date_prefix}%")
        ).fetchall()
        max_seq = 0
        for r in rows:
            vn = r["voucher_number"]
            if vn.startswith(f"V-{date_prefix}-"):
                suffix = vn[len(f"V-{date_prefix}-"):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass
            elif vn.startswith(f"{date_prefix}-"):
                suffix = vn[len(date_prefix) + 1:]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass
            elif vn.startswith(date_prefix):
                suffix = vn[len(date_prefix):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass

        seq = max_seq + 1
        # Loop to ensure candidate does not collide with any available voucher for this company in DB
        while True:
            candidate = f"V-{date_prefix}-{seq:03d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            seq += 1
    elif fmt == "month_based":
        # Monthly Format: e.g. 26AUG_01 (resets to 01 each month based on voucher_date)
        dt = None
        if voucher_date:
            try:
                s = str(voucher_date).strip()
                clean_date = s.replace("-", "").replace("/", "").strip()
                if len(clean_date) >= 8 and clean_date[:8].isdigit():
                    dt = datetime.strptime(clean_date[:8], "%Y%m%d")
                elif len(s) >= 10:
                    dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except Exception:
                dt = None
        if dt is None:
            dt = datetime.now()

        month_names = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
        month_prefix = f"{dt.year % 100:02d}{month_names[dt.month - 1]}_"

        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND voucher_number LIKE ? ORDER BY id DESC",
            (company_id, f"{month_prefix}%")
        ).fetchall()
        max_seq = 0
        for r in rows:
            vn = r["voucher_number"]
            if vn.startswith(month_prefix):
                suffix = vn[len(month_prefix):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass

        seq = max_seq + 1
        while True:
            candidate = f"{month_prefix}{seq:02d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            seq += 1
    else:
        # Custom format
        prefix = custom_prefix
        start = custom_start
        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND voucher_number LIKE ? ORDER BY id DESC",
            (company_id, f"{prefix}%")
        ).fetchall()
        max_num = 0
        for r in rows:
            vn = r["voucher_number"]
            val_str = vn[len(prefix):].strip()
            try:
                n = int(val_str)
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
        next_num = max(start, max_num + 1)
        width = max(4, len(str(next_num)))
        while True:
            candidate = f"{prefix}{next_num:0{width}d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            next_num += 1


def create_voucher(data, line_items, attachment_list=None, company_id=None):
    """
    Create a new voucher with line items and optional attachments for a specific company.

    Args:
        data: dict with keys: date, paid_to, cash_given_by, spent_by,
              bill_status, prepared_by, approved_by, optional voucher_number, optional company_id
        line_items: list of dicts with keys: description, category, amount
        attachment_list: list of dicts with keys: filename, file_data, file_type
        company_id: optional company ID (defaults to active company)

    Returns:
        The new voucher id.
    """
    if company_id is None:
        company_id = data.get("company_id") or get_active_company_id()

    conn = get_connection()
    cursor = conn.cursor()

    v_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    desired_vn = data.get("voucher_number")
    if desired_vn:
        exists = cursor.execute(
            "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
            (company_id, desired_vn)
        ).fetchone()
        if not exists:
            voucher_number = desired_vn
        else:
            voucher_number = get_next_voucher_number(company_id=company_id, voucher_date=v_date)
    else:
        voucher_number = get_next_voucher_number(company_id=company_id, voucher_date=v_date)

    total = sum(item["amount"] for item in line_items)

    try:
        cursor.execute("""
            INSERT INTO vouchers (company_id, voucher_number, date, paid_to, cash_given_by,
                spent_by, total_amount, bill_status, prepared_by, approved_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_id,
            voucher_number,
            v_date,
            data["paid_to"],
            data.get("cash_given_by", ""),
            data.get("spent_by") or data["paid_to"],
            total,
            data.get("bill_status", "Pending"),
            data.get("prepared_by", ""),
            data.get("approved_by", ""),
        ))

        voucher_id = cursor.lastrowid

        for item in line_items:
            cursor.execute("""
                INSERT INTO line_items (voucher_id, description, category, amount)
                VALUES (?, ?, ?, ?)
            """, (voucher_id, item["description"], item.get("category", ""), item["amount"]))

            # Update category usage count
            if item.get("category"):
                _upsert_category(cursor, item["category"])

        if attachment_list:
            for att in attachment_list:
                disk_path, f_size = _save_attachment_file(voucher_id, att["filename"], att["file_data"])
                cursor.execute("""
                    INSERT INTO attachments (voucher_id, filename, file_path, file_size, file_type, file_data)
                    VALUES (?, ?, ?, ?, ?, NULL)
                """, (voucher_id, att["filename"], disk_path, f_size, att.get("file_type", "")))

        # Remember people
        if data.get("paid_to"):
            _upsert_person(cursor, data["paid_to"])
        if data.get("cash_given_by"):
            _upsert_person(cursor, data["cash_given_by"])
        if data.get("spent_by"):
            _upsert_person(cursor, data["spent_by"])

        conn.commit()
        return voucher_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_voucher(voucher_id, data, line_items, attachment_list=None):
    """
    Update an existing voucher. Replaces all line items.
    New attachments are appended (existing ones kept unless explicitly removed).
    """
    conn = get_connection()
    cursor = conn.cursor()

    total = sum(item["amount"] for item in line_items)

    try:
        cursor.execute("""
            UPDATE vouchers SET
                date = ?, paid_to = ?, cash_given_by = ?, spent_by = ?,
                total_amount = ?, bill_status = ?, prepared_by = ?,
                approved_by = ?, updated_at = ?
            WHERE id = ?
        """, (
            data.get("date"),
            data["paid_to"],
            data["cash_given_by"],
            data.get("spent_by") or data["paid_to"],
            total,
            data.get("bill_status", "Pending"),
            data.get("prepared_by", ""),
            data.get("approved_by", ""),
            datetime.now().isoformat(),
            voucher_id,
        ))

        # Replace line items
        cursor.execute("DELETE FROM line_items WHERE voucher_id = ?", (voucher_id,))
        for item in line_items:
            cursor.execute("""
                INSERT INTO line_items (voucher_id, description, category, amount)
                VALUES (?, ?, ?, ?)
            """, (voucher_id, item["description"], item.get("category", ""), item["amount"]))

            if item.get("category"):
                _upsert_category(cursor, item["category"])

        # Append new attachments
        if attachment_list:
            for att in attachment_list:
                disk_path, f_size = _save_attachment_file(voucher_id, att["filename"], att["file_data"])
                cursor.execute("""
                    INSERT INTO attachments (voucher_id, filename, file_path, file_size, file_type, file_data)
                    VALUES (?, ?, ?, ?, ?, NULL)
                """, (voucher_id, att["filename"], disk_path, f_size, att.get("file_type", "")))

        # Remember people
        _upsert_person(cursor, data["paid_to"])
        _upsert_person(cursor, data["cash_given_by"])
        if data.get("spent_by"):
            _upsert_person(cursor, data["spent_by"])

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def cancel_voucher(voucher_id):
    """Soft-cancel a voucher (mark status as Cancelled)."""
    conn = get_connection()
    conn.execute(
        "UPDATE vouchers SET status = 'Cancelled', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), voucher_id)
    )
    conn.commit()
    conn.close()


def restore_voucher(voucher_id):
    """Restore a cancelled voucher back to Active."""
    conn = get_connection()
    conn.execute(
        "UPDATE vouchers SET status = 'Active', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), voucher_id)
    )
    conn.commit()
    conn.close()


def permanently_delete_voucher(voucher_id):
    """
    Permanently delete a specific voucher,
    including its line items, attachments (and files on disk), and memos.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 1. Clean up disk attachments
        rows = cursor.execute(
            "SELECT file_path FROM attachments WHERE voucher_id = ?", (voucher_id,)
        ).fetchall()
        for r in rows:
            fp = r["file_path"]
            if fp and os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass

        # 2. Delete related rows
        cursor.execute("DELETE FROM line_items WHERE voucher_id = ?", (voucher_id,))
        cursor.execute("DELETE FROM attachments WHERE voucher_id = ?", (voucher_id,))
        cursor.execute("DELETE FROM memos WHERE voucher_id = ?", (voucher_id,))
        cursor.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def mark_as_printed(voucher_ids):
    """Mark one or more vouchers as printed."""
    conn = get_connection()
    for vid in voucher_ids:
        conn.execute("UPDATE vouchers SET printed = 1 WHERE id = ?", (vid,))
    conn.commit()
    conn.close()


def get_voucher(voucher_id):
    """Get a single voucher with all its details, including its company profile."""
    conn = get_connection()
    voucher = conn.execute("SELECT * FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if not voucher:
        conn.close()
        return None

    line_items = conn.execute(
        "SELECT * FROM line_items WHERE voucher_id = ? ORDER BY id", (voucher_id,)
    ).fetchall()

    attachments = conn.execute(
        "SELECT id, voucher_id, filename, file_type, created_at FROM attachments WHERE voucher_id = ? ORDER BY id",
        (voucher_id,)
    ).fetchall()

    memos = conn.execute(
        "SELECT * FROM memos WHERE voucher_id = ? ORDER BY created_at DESC", (voucher_id,)
    ).fetchall()

    v_dict = dict(voucher)
    comp_id = v_dict.get("company_id") or 1
    company = conn.execute("SELECT * FROM companies WHERE id = ?", (comp_id,)).fetchone()

    conn.close()

    return {
        "voucher": v_dict,
        "line_items": [dict(li) for li in line_items],
        "attachments": [dict(a) for a in attachments],
        "memos": [dict(m) for m in memos],
        "company": dict(company) if company else None,
    }


def _save_attachment_file(voucher_id, filename, file_data):
    """Save attachment bytes to disk and return (disk_path, file_size)."""
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    disk_name = f"v{voucher_id}_{uuid.uuid4().hex[:8]}_{safe_name}"
    disk_path = os.path.join(ATTACHMENTS_DIR, disk_name)
    with open(disk_path, "wb") as f:
        f.write(file_data)
    return disk_path, len(file_data)


def get_attachment_data(attachment_id):
    """Get attachment details and binary content from disk or DB."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM attachments WHERE id = ?", (attachment_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    res = dict(row)
    # Read file from disk if file_path is available
    file_path = res.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "rb") as f:
                res["file_data"] = f.read()
        except Exception:
            pass
    return res


def delete_attachment(attachment_id):
    """Delete an attachment record and remove its file from disk."""
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
        try:
            os.remove(row["file_path"])
        except Exception:
            pass
    conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    conn.close()


def clear_all_vouchers(company_id=None):
    """
    Permanently delete all vouchers, line items, attachments (including files on disk),
    and memos.
    If company_id is provided, deletes vouchers for that company only.
    If company_id is None, deletes all vouchers across all companies.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        if company_id is not None:
            # 1. Clean up disk attachments for this company
            rows = cursor.execute("""
                SELECT a.file_path FROM attachments a
                JOIN vouchers v ON a.voucher_id = v.id
                WHERE v.company_id = ?
            """, (company_id,)).fetchall()
            for r in rows:
                fp = r["file_path"]
                if fp and os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

            # 2. Get voucher IDs for this company
            v_rows = cursor.execute("SELECT id FROM vouchers WHERE company_id = ?", (company_id,)).fetchall()
            v_ids = [r["id"] for r in v_rows]
            if v_ids:
                placeholders = ",".join("?" * len(v_ids))
                cursor.execute(f"DELETE FROM line_items WHERE voucher_id IN ({placeholders})", v_ids)
                cursor.execute(f"DELETE FROM attachments WHERE voucher_id IN ({placeholders})", v_ids)
                cursor.execute(f"DELETE FROM memos WHERE voucher_id IN ({placeholders})", v_ids)
                cursor.execute(f"DELETE FROM vouchers WHERE id IN ({placeholders})", v_ids)
        else:
            # 1. Clean up all attachment files on disk
            rows = cursor.execute("SELECT file_path FROM attachments").fetchall()
            for r in rows:
                fp = r["file_path"]
                if fp and os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass

            # 2. Delete all records
            cursor.execute("DELETE FROM line_items")
            cursor.execute("DELETE FROM attachments")
            cursor.execute("DELETE FROM memos")
            cursor.execute("DELETE FROM vouchers")

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def search_vouchers(query="", status_filter="All", bill_filter="All", sort_by="date_desc", company_id=None):
    """
    Vast search across all voucher fields, line item descriptions, categories, and memos for a specific company.

    Args:
        query: search string
        status_filter: 'All', 'Active', 'Cancelled'
        bill_filter: 'All', 'Pending', 'Received', 'Partial'
        sort_by: 'date_desc', 'date_asc', 'amount_desc', 'amount_asc', 'number_desc', 'number_asc', 'paid_to_asc'
        company_id: company ID (defaults to active company)

    Returns:
        List of voucher dicts.
    """
    if company_id is None:
        company_id = get_active_company_id()

    conn = get_connection()

    sql = """
        SELECT v.*,
               (SELECT COUNT(*) FROM attachments a WHERE a.voucher_id = v.id) AS attachment_count
        FROM vouchers v
        WHERE v.company_id = ?
    """
    params = [company_id]

    if query and query.strip():
        q = f"%{query.strip()}%"
        sql += """ AND (
            v.voucher_number LIKE ? OR
            v.paid_to LIKE ? OR
            v.cash_given_by LIKE ? OR
            v.spent_by LIKE ? OR
            v.prepared_by LIKE ? OR
            v.approved_by LIKE ? OR
            v.date LIKE ? OR
            CAST(v.total_amount AS TEXT) LIKE ? OR
            v.id IN (
                SELECT voucher_id FROM line_items
                WHERE description LIKE ? OR category LIKE ? OR CAST(amount AS TEXT) LIKE ?
            ) OR
            v.id IN (
                SELECT voucher_id FROM memos
                WHERE memo_text LIKE ?
            )
        )"""
        params.extend([q, q, q, q, q, q, q, q, q, q, q, q])

    if status_filter != "All":
        sql += " AND v.status = ?"
        params.append(status_filter)

    if bill_filter != "All":
        sql += " AND v.bill_status = ?"
        params.append(bill_filter)

    # Sort mapping
    sort_orders = {
        "date_desc": "v.date DESC, v.id DESC",
        "date_asc": "v.date ASC, v.id ASC",
        "amount_desc": "v.total_amount DESC, v.id DESC",
        "amount_asc": "v.total_amount ASC, v.id ASC",
        "number_desc": "v.id DESC",
        "number_asc": "v.id ASC",
        "paid_to_asc": "v.paid_to COLLATE NOCASE ASC, v.id DESC",
    }
    order_clause = sort_orders.get(sort_by, "v.date DESC, v.id DESC")
    sql += f" ORDER BY {order_clause}"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_vouchers(company_id=None):
    """Get all vouchers for a company ordered by most recent first."""
    if company_id is None:
        company_id = get_active_company_id()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM vouchers WHERE company_id = ? ORDER BY id DESC", (company_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Memo CRUD
# ---------------------------------------------------------------------------

def add_memo(voucher_id, memo_text, memo_type="General", created_by=""):
    """Add a memo/comment to a voucher."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO memos (voucher_id, memo_text, memo_type, created_by)
        VALUES (?, ?, ?, ?)
    """, (voucher_id, memo_text, memo_type, created_by))
    conn.commit()
    conn.close()


def get_memos(voucher_id):
    """Get all memos for a voucher."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM memos WHERE voucher_id = ? ORDER BY created_at DESC",
        (voucher_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Category & People helpers
# ---------------------------------------------------------------------------

def _upsert_category(cursor, name):
    """Insert or update category usage count."""
    cursor.execute("""
        INSERT INTO categories (name, usage_count) VALUES (?, 1)
        ON CONFLICT(name) DO UPDATE SET usage_count = usage_count + 1
    """, (name.strip(),))


def _upsert_person(cursor, name):
    """Insert person if not exists."""
    if name and name.strip():
        cursor.execute(
            "INSERT OR IGNORE INTO people (name) VALUES (?)",
            (name.strip(),)
        )


def get_categories(active_only=False):
    """Get categories. If active_only, only return active ones."""
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT name FROM categories WHERE is_active=1 ORDER BY usage_count DESC, name ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM categories ORDER BY usage_count DESC, name ASC"
        ).fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_all_categories_full():
    """Get all categories with full details for the category manager."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, usage_count, is_active FROM categories ORDER BY name ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_category(name):
    """Add a new category. Returns the new id or None on conflict."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO categories (name, is_active) VALUES (?, 1)",
            (name.strip(),)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM categories WHERE name = ?", (name.strip(),)).fetchone()
        return row["id"] if row else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def update_category(cat_id, new_name):
    """Rename a category."""
    conn = get_connection()
    try:
        conn.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name.strip(), cat_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def toggle_category_active(cat_id):
    """Toggle a category between active/inactive."""
    conn = get_connection()
    row = conn.execute("SELECT is_active FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if row:
        new_state = 0 if row["is_active"] else 1
        conn.execute("UPDATE categories SET is_active = ? WHERE id = ?", (new_state, cat_id))
        conn.commit()
    conn.close()


def get_people(active_only=False):
    """Get people names. If active_only, only return active ones."""
    conn = get_connection()
    if active_only:
        rows = conn.execute(
            "SELECT name FROM people WHERE is_active=1 ORDER BY name ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name FROM people ORDER BY name ASC"
        ).fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_all_people_full():
    """Get all people with full details for the name manager."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, is_active FROM people ORDER BY name ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_person(name):
    """Add a new person. Returns id or None on duplicate."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO people (name, is_active) VALUES (?, 1)",
            (name.strip(),)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM people WHERE name = ?", (name.strip(),)).fetchone()
        return row["id"] if row else None
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def update_person(person_id, new_name):
    """Rename a person."""
    conn = get_connection()
    try:
        conn.execute("UPDATE people SET name = ? WHERE id = ?", (new_name.strip(), person_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def toggle_person_active(person_id):
    """Toggle a person between active/inactive."""
    conn = get_connection()
    row = conn.execute("SELECT is_active FROM people WHERE id = ?", (person_id,)).fetchone()
    if row:
        new_state = 0 if row["is_active"] else 1
        conn.execute("UPDATE people SET is_active = ? WHERE id = ?", (new_state, person_id))
        conn.commit()
    conn.close()


def update_bill_status(voucher_id, new_status):
    """Update the bill status of a voucher."""
    conn = get_connection()
    conn.execute(
        "UPDATE vouchers SET bill_status = ?, updated_at = ? WHERE id = ?",
        (new_status, datetime.now().isoformat(), voucher_id)
    )
    conn.commit()
    conn.close()


def export_vouchers_to_csv(vouchers, filepath):
    """
    Export list of voucher records to a CSV file with detailed breakdown.

    Args:
        vouchers: list of voucher dicts
        filepath: output CSV file path
    """
    import csv

    fieldnames = [
        "Voucher #", "Date", "Paid To", "Cash Given By", "Spent By",
        "Total Amount", "Bill Status", "Status", "Prepared By", "Approved By",
        "Printed", "Line Items Summary"
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        conn = get_connection()
        for v in vouchers:
            v_id = v["id"]
            items = conn.execute(
                "SELECT description, category, amount FROM line_items WHERE voucher_id = ?", (v_id,)
            ).fetchall()
            items_summary = "; ".join(
                f"{it['description']} ({it['category'] or 'No Cat'}): {it['amount']:.2f}" for it in items
            )

            writer.writerow({
                "Voucher #": v.get("voucher_number", ""),
                "Date": v.get("date", ""),
                "Paid To": v.get("paid_to", ""),
                "Cash Given By": v.get("cash_given_by", ""),
                "Spent By": v.get("spent_by", ""),
                "Total Amount": f"{v.get('total_amount', 0):.2f}",
                "Bill Status": v.get("bill_status", ""),
                "Status": v.get("status", ""),
                "Prepared By": v.get("prepared_by", ""),
                "Approved By": v.get("approved_by", ""),
                "Printed": "Yes" if v.get("printed") else "No",
                "Line Items Summary": items_summary,
            })
        conn.close()


def get_expense_summary(company_id=None, date_filter="all"):
    """
    Compute aggregated expense totals by Category and Payee for a company.

    Args:
        company_id: company ID (defaults to active company)
        date_filter: 'all', 'this_month', 'last_month', 'this_year'

    Returns:
        dict: {
            "by_category": [{"category": str, "amount": float, "count": int}, ...],
            "by_payee": [{"payee": str, "amount": float, "count": int}, ...],
            "grand_total": float,
            "voucher_count": int
        }
    """
    if company_id is None:
        company_id = get_active_company_id()

    conn = get_connection()

    date_clause = ""
    params = [company_id]

    now = datetime.now()
    if date_filter == "this_month":
        prefix = now.strftime("%Y-%m")
        date_clause = " AND v.date LIKE ?"
        params.append(f"{prefix}%")
    elif date_filter == "last_month":
        first_of_this_month = now.replace(day=1)
        last_month = first_of_this_month - timedelta(days=1)
        prefix = last_month.strftime("%Y-%m")
        date_clause = " AND v.date LIKE ?"
        params.append(f"{prefix}%")
    elif date_filter == "this_year":
        prefix = now.strftime("%Y")
        date_clause = " AND v.date LIKE ?"
        params.append(f"{prefix}%")

    # Category breakdown
    cat_sql = f"""
        SELECT COALESCE(NULLIF(li.category, ''), 'Uncategorized') as category,
               SUM(li.amount) as amount,
               COUNT(DISTINCT v.id) as count
        FROM line_items li
        JOIN vouchers v ON li.voucher_id = v.id
        WHERE v.company_id = ? AND v.status = 'Active' {date_clause}
        GROUP BY category
        ORDER BY amount DESC
    """
    cat_rows = conn.execute(cat_sql, params).fetchall()

    # Payee breakdown
    payee_sql = f"""
        SELECT v.paid_to as payee,
               SUM(v.total_amount) as amount,
               COUNT(v.id) as count
        FROM vouchers v
        WHERE v.company_id = ? AND v.status = 'Active' {date_clause}
        GROUP BY payee
        ORDER BY amount DESC
    """
    payee_rows = conn.execute(payee_sql, params).fetchall()

    # Grand totals
    total_sql = f"""
        SELECT COALESCE(SUM(total_amount), 0) as grand_total,
               COUNT(id) as voucher_count
        FROM vouchers v
        WHERE v.company_id = ? AND v.status = 'Active' {date_clause}
    """
    total_row = conn.execute(total_sql, params).fetchone()

    conn.close()

    return {
        "by_category": [dict(r) for r in cat_rows],
        "by_payee": [dict(r) for r in payee_rows],
        "grand_total": total_row["grand_total"] if total_row else 0.0,
        "voucher_count": total_row["voucher_count"] if total_row else 0,
    }


def get_voucher_stats(company_id=None):
    """Get summary statistics for a company (or active company)."""
    if company_id is None:
        company_id = get_active_company_id()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) as c FROM vouchers WHERE company_id = ? AND status = 'Active'", (company_id,)).fetchone()["c"]
    pending = conn.execute("SELECT COUNT(*) as c FROM vouchers WHERE company_id = ? AND status = 'Active' AND bill_status = 'Pending'", (company_id,)).fetchone()["c"]
    total_amount = conn.execute("SELECT COALESCE(SUM(total_amount), 0) as s FROM vouchers WHERE company_id = ? AND status = 'Active'", (company_id,)).fetchone()["s"]
    unprinted = conn.execute("SELECT COUNT(*) as c FROM vouchers WHERE company_id = ? AND status = 'Active' AND printed = 0", (company_id,)).fetchone()["c"]
    conn.close()
    return {
        "total_vouchers": total,
        "bills_pending": pending,
        "total_amount": total_amount,
        "unprinted": unprinted,
    }


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _get_all_settings(conn):
    """Internal: load settings dict from an open connection."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_settings():
    """Return all settings as a dict."""
    conn = get_connection()
    s = _get_all_settings(conn)
    conn.close()
    return s


def save_settings(settings_dict):
    """Upsert settings key-value pairs."""
    conn = get_connection()
    for k, v in settings_dict.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (k, str(v))
        )
    conn.commit()
    conn.close()


def verify_admin_password(provided_password: str) -> bool:
    """Verify administrator password against stored SHA-256 hash."""
    if not provided_password:
        return False
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = 'admin_password_hash'").fetchone()
    conn.close()

    provided_hash = hashlib.sha256(provided_password.strip().encode("utf-8")).hexdigest()

    if row and row["value"]:
        return provided_hash == row["value"]

    default_hash = hashlib.sha256(DEFAULT_ADMIN_PASSWORD.encode("utf-8")).hexdigest()
    return provided_hash == default_hash


def set_admin_password(new_password: str) -> None:
    """Update the administrator password with SHA-256 hash."""
    pwd_hash = hashlib.sha256(new_password.strip().encode("utf-8")).hexdigest()
    save_settings({"admin_password_hash": pwd_hash})


def preview_next_voucher_number(settings_override=None, voucher_date=None, company_id=None):
    """
    Preview what the next voucher number would look like given settings and optional voucher_date.
    Optionally pass a settings_override dict to test without saving.
    """
    if company_id is None:
        company_id = get_active_company_id()
    conn = get_connection()
    comp = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()

    base_settings = {
        "voucher_format": comp["voucher_format"] if comp else "date_based",
        "custom_prefix": comp["custom_prefix"] if comp else "V-",
        "custom_start": str(comp["custom_start"] if comp else "1"),
    }
    if settings_override:
        base_settings.update(settings_override)
    fmt = base_settings.get("voucher_format", "date_based")

    if fmt == "date_based":
        if voucher_date:
            clean_date = str(voucher_date).replace("-", "").replace("/", "").strip()
            if len(clean_date) >= 8 and clean_date[:8].isdigit():
                date_prefix = clean_date[:8]
            else:
                date_prefix = _date.today().strftime("%Y%m%d")
        else:
            date_prefix = _date.today().strftime("%Y%m%d")

        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND (voucher_number LIKE ? OR voucher_number LIKE ?) ORDER BY id DESC",
            (company_id, f"V-{date_prefix}%", f"{date_prefix}%")
        ).fetchall()
        max_seq = 0
        for r in rows:
            vn = r["voucher_number"]
            if vn.startswith(f"V-{date_prefix}-"):
                suffix = vn[len(f"V-{date_prefix}-"):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass
            elif vn.startswith(f"{date_prefix}-"):
                suffix = vn[len(date_prefix) + 1:]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass
            elif vn.startswith(date_prefix):
                suffix = vn[len(date_prefix):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass

        seq = max_seq + 1
        while True:
            candidate = f"V-{date_prefix}-{seq:03d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            seq += 1
    elif fmt == "month_based":
        # Monthly Format: e.g. 26AUG_01 (resets to 01 each month based on voucher_date)
        dt = None
        if voucher_date:
            try:
                s = str(voucher_date).strip()
                clean_date = s.replace("-", "").replace("/", "").strip()
                if len(clean_date) >= 8 and clean_date[:8].isdigit():
                    dt = datetime.strptime(clean_date[:8], "%Y%m%d")
                elif len(s) >= 10:
                    dt = datetime.strptime(s[:10], "%Y-%m-%d")
            except Exception:
                dt = None
        if dt is None:
            dt = datetime.now()

        month_names = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
        month_prefix = f"{dt.year % 100:02d}{month_names[dt.month - 1]}_"

        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND voucher_number LIKE ? ORDER BY id DESC",
            (company_id, f"{month_prefix}%")
        ).fetchall()
        max_seq = 0
        for r in rows:
            vn = r["voucher_number"]
            if vn.startswith(month_prefix):
                suffix = vn[len(month_prefix):]
                try:
                    num = int(suffix)
                    if num > max_seq:
                        max_seq = num
                except ValueError:
                    pass

        seq = max_seq + 1
        while True:
            candidate = f"{month_prefix}{seq:02d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            seq += 1
    else:
        prefix = base_settings.get("custom_prefix", "V-")
        try:
            start = int(base_settings.get("custom_start", "1"))
        except ValueError:
            start = 1
        rows = conn.execute(
            "SELECT voucher_number FROM vouchers WHERE company_id = ? AND voucher_number LIKE ? ORDER BY id DESC LIMIT 1",
            (company_id, f"{prefix}%")
        ).fetchall()
        max_num = 0
        for r in rows:
            vn = r["voucher_number"]
            val_str = vn[len(prefix):].strip()
            try:
                n = int(val_str)
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
        next_num = max(start, max_num + 1)
        width = max(4, len(str(next_num)))
        while True:
            candidate = f"{prefix}{next_num:0{width}d}"
            exists = conn.execute(
                "SELECT 1 FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (company_id, candidate)
            ).fetchone()
            if not exists:
                conn.close()
                return candidate
            next_num += 1

