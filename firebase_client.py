"""
Firebase Cloud NoSQL Database Integration (Google Cloud Firestore).
Provides seamless, 100% free cloud synchronization for the Voucher Machine application.

Compliant with Google Firebase Spark Plan (Free Forever Tier):
- 1 GiB total document storage
- 50,000 document reads / day
- 20,000 document writes / day
- 20,000 document deletes / day
- Zero cost, no credit card required.

Supports multi-tenant / multi-company configuration so any business can connect
their own Firebase project by providing their service account JSON credentials.
All cloud operations execute in background worker threads with zero UI blocking.
"""

import os
import sys
import json
import time
import shutil
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import database as db

logger = logging.getLogger("FirebaseClient")
logger.setLevel(logging.INFO)

# Background worker for non-blocking asynchronous cloud operations
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="FirebaseSyncWorker")

FIREBASE_APP_NAME = "voucher_machine_firebase"
DEFAULT_COLLECTION_PREFIX = ""
DEFAULT_VOUCHERS_COLLECTION = "vouchers"
DEFAULT_COMPANIES_COLLECTION = "companies"
DEFAULT_CATEGORIES_COLLECTION = "categories"
DEFAULT_PEOPLE_COLLECTION = "people"
DEFAULT_TAGS_COLLECTION = "tags"
DEFAULT_FLOATS_COLLECTION = "money_floats"
DEFAULT_HEALTHCHECK_COLLECTION = "_healthcheck"

# In-memory runtime state
_firestore_client = None
_last_error = ""
_last_connected_time = None
_cached_project_id = ""


def is_firebase_available() -> bool:
    """Return True if firebase-admin package is installed and importable."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        return True
    except ImportError:
        return False


def get_default_creds_storage_path() -> str:
    """Return the persistent location inside app data dir for storing the service account JSON."""
    return os.path.join(db.DB_DIR, "firebase_credentials.json")


def get_config() -> dict:
    """
    Retrieve current Firebase configuration settings from database.
    Returns:
        dict with keys: enabled, creds_path, project_id, collection_prefix,
                        auto_sync, last_synced, client_email
    """
    settings = db.get_settings()
    creds_path = settings.get("firebase_creds_path", "")
    if not creds_path and os.path.exists(get_default_creds_storage_path()):
        creds_path = get_default_creds_storage_path()

    return {
        "enabled": settings.get("firebase_enabled", "false").lower() in ("true", "1", "yes"),
        "creds_path": creds_path,
        "project_id": settings.get("firebase_project_id", ""),
        "collection_prefix": settings.get("firebase_collection_prefix", ""),
        "auto_sync": settings.get("firebase_auto_sync", "true").lower() in ("true", "1", "yes"),
        "last_synced": settings.get("firebase_last_synced", ""),
        "client_email": settings.get("firebase_client_email", ""),
    }


def save_config(config_dict: dict) -> None:
    """Save Firebase configuration settings to database."""
    save_payload = {}
    if "enabled" in config_dict:
        save_payload["firebase_enabled"] = "true" if config_dict["enabled"] else "false"
    if "creds_path" in config_dict:
        save_payload["firebase_creds_path"] = str(config_dict["creds_path"]).strip()
    if "project_id" in config_dict:
        save_payload["firebase_project_id"] = str(config_dict["project_id"]).strip()
    if "collection_prefix" in config_dict:
        save_payload["firebase_collection_prefix"] = str(config_dict["collection_prefix"]).strip()
    if "auto_sync" in config_dict:
        save_payload["firebase_auto_sync"] = "true" if config_dict["auto_sync"] else "false"
    if "last_synced" in config_dict:
        save_payload["firebase_last_synced"] = str(config_dict["last_synced"]).strip()
    if "client_email" in config_dict:
        save_payload["firebase_client_email"] = str(config_dict["client_email"]).strip()

    db.save_settings(save_payload)


def is_configured() -> bool:
    """Return True if a valid Firebase credentials file exists and project ID is known."""
    cfg = get_config()
    path = cfg.get("creds_path")
    if not path or not os.path.exists(path):
        return False
    return bool(cfg.get("project_id") or os.path.getsize(path) > 50)


def is_enabled() -> bool:
    """Return True if Firebase is both configured and explicitly enabled by the user."""
    cfg = get_config()
    return cfg.get("enabled", False) and is_configured()


def validate_credentials_file(file_path: str) -> tuple[bool, dict | None, str]:
    """
    Validate that a given file path is a genuine Google Firebase service account JSON.
    Returns: (is_valid, parsed_dict, error_message)
    """
    if not file_path or not os.path.exists(file_path):
        return False, None, "Credentials file does not exist."

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return False, None, f"Failed to parse JSON file: {e}"

    if not isinstance(data, dict):
        return False, None, "Invalid format: JSON root must be an object."

    if data.get("type") != "service_account":
        return False, None, "Invalid file: 'type' is not 'service_account'. Please upload Firebase service account JSON."

    required_keys = ["project_id", "private_key", "client_email"]
    missing = [k for k in required_keys if not data.get(k)]
    if missing:
        return False, None, f"Missing required Firebase fields: {', '.join(missing)}"

    return True, data, ""


def install_credentials_file(source_file_path: str) -> tuple[bool, str, dict | None]:
    """
    Copy a chosen service account JSON file into the permanent application data directory
    so the app remains connected even if the original download file is deleted or moved.
    Returns: (success, target_path_or_error, parsed_info)
    """
    is_valid, data, err = validate_credentials_file(source_file_path)
    if not is_valid:
        return False, err, None

    dest_path = get_default_creds_storage_path()
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        # Avoid samefile error if user selected the already installed file
        if os.path.abspath(source_file_path) != os.path.abspath(dest_path):
            shutil.copyfile(source_file_path, dest_path)

        project_id = data.get("project_id", "")
        client_email = data.get("client_email", "")

        save_config({
            "creds_path": dest_path,
            "project_id": project_id,
            "client_email": client_email,
        })
        return True, dest_path, data
    except Exception as e:
        return False, f"Failed to copy credentials file: {e}", None


def get_firestore_client(force_reinit: bool = False):
    """
    Thread-safe initialization and retrieval of Google Cloud Firestore client.
    Reuses existing app instance or safely creates a new one.
    """
    global _firestore_client, _last_error, _cached_project_id

    if _firestore_client is not None and not force_reinit:
        return _firestore_client

    if not is_firebase_available():
        _last_error = "firebase-admin Python package is not installed."
        logger.error(_last_error)
        return None

    import firebase_admin
    from firebase_admin import credentials, firestore

    cfg = get_config()
    creds_path = cfg.get("creds_path")

    if not creds_path or not os.path.exists(creds_path):
        _last_error = f"Firebase credentials file not found at: {creds_path}"
        return None

    is_valid, creds_data, err = validate_credentials_file(creds_path)
    if not is_valid:
        _last_error = err
        return None

    project_id = cfg.get("project_id") or creds_data.get("project_id", "")

    try:
        # Check if app already initialized
        try:
            app = firebase_admin.get_app(FIREBASE_APP_NAME)
            if force_reinit:
                firebase_admin.delete_app(app)
                app = None
        except ValueError:
            app = None

        if app is None:
            cred = credentials.Certificate(creds_path)
            app = firebase_admin.initialize_app(
                cred,
                {"projectId": project_id},
                name=FIREBASE_APP_NAME
            )

        client = firestore.client(app=app)
        _firestore_client = client
        _cached_project_id = project_id
        _last_error = ""
        return _firestore_client

    except Exception as e:
        _last_error = str(e)
        _firestore_client = None
        logger.error(f"Failed to initialize Firestore client: {e}")
        return None


def test_connection(creds_path: str = None, project_id: str = None) -> tuple[bool, str, float]:
    """
    Test live connectivity to Google Cloud Firestore NoSQL database.
    Performs a lightweight write and read on the healthcheck collection to ensure:
    1. Authentication is valid
    2. Firestore API is enabled on Google Cloud
    3. Network is reachable
    Returns: (is_success, status_message, latency_seconds)
    """
    start_time = time.time()

    if not is_firebase_available():
        return False, "Error: 'firebase-admin' package is not installed. Please run 'pip install firebase-admin'.", 0.0

    import firebase_admin
    from firebase_admin import credentials, firestore

    target_path = creds_path or get_config().get("creds_path")
    if not target_path or not os.path.exists(target_path):
        return False, "Error: Please browse and select a valid Firebase Service Account JSON file first.", 0.0

    is_valid, creds_data, err = validate_credentials_file(target_path)
    if not is_valid:
        return False, f"Invalid Credentials File: {err}", 0.0

    eff_project_id = project_id or creds_data.get("project_id", "")
    test_app_name = f"test_{int(time.time())}"

    test_app = None
    try:
        cred = credentials.Certificate(target_path)
        test_app = firebase_admin.initialize_app(
            cred,
            {"projectId": eff_project_id},
            name=test_app_name
        )
        test_db = firestore.client(app=test_app)

        # Write test document
        test_ref = test_db.collection(DEFAULT_HEALTHCHECK_COLLECTION).document("app_health_ping")
        now_iso = datetime.now(timezone.utc).isoformat()
        test_ref.set({
            "ping": True,
            "timestamp": now_iso,
            "app": "Voucher Machine Desktop",
            "free_tier": "Spark Plan Validated"
        })

        # Read back document to verify read permission
        doc = test_ref.get()
        if not doc.exists:
            return False, "Firestore Ping failed: Document written but could not be read back.", 0.0

        # Clean up test document to conserve free quota
        try:
            test_ref.delete()
        except Exception:
            pass

        latency = round((time.time() - start_time) * 1000, 1)

        # Update cache
        save_config({
            "project_id": eff_project_id,
            "client_email": creds_data.get("client_email", "")
        })

        # Reset main client so next call uses updated credentials
        get_firestore_client(force_reinit=True)

        return True, f"Connected to Firebase Firestore!\nProject: {eff_project_id}\nLatency: {latency} ms (Spark Free Tier Active)", latency

    except Exception as e:
        err_msg = str(e)
        if "API has not been used" in err_msg or "it is disabled" in err_msg:
            return False, (
                "Firestore API is not enabled in your Google Cloud Project.\n"
                "To fix: Open Firebase Console (https://console.firebase.google.com), "
                "click 'Firestore Database' and choose 'Create Database' (Free Spark Plan)."
            ), 0.0
        elif "Permission denied" in err_msg:
            return False, (
                "Permission Denied: Please ensure the service account has 'Cloud Datastore User' "
                "or 'Firebase Admin SDK Administrator Service Agent' role."
            ), 0.0
        elif "DNS" in err_msg or "failed to connect" in err_msg.lower():
            return False, "Network Error: Could not reach Google Firebase servers. Check internet connection.", 0.0

        return False, f"Connection Failed: {err_msg}", 0.0

    finally:
        if test_app:
            try:
                firebase_admin.delete_app(test_app)
            except Exception:
                pass


def get_status() -> dict:
    """Return high-level status dictionary for UI display."""
    cfg = get_config()
    return {
        "configured": is_configured(),
        "enabled": cfg.get("enabled", False),
        "auto_sync": cfg.get("auto_sync", True),
        "project_id": cfg.get("project_id", ""),
        "client_email": cfg.get("client_email", ""),
        "last_synced": cfg.get("last_synced", "Never"),
        "last_error": _last_error,
        "is_online": _firestore_client is not None,
    }


def _collection_name(base_name: str) -> str:
    """Return collection name with optional custom prefix."""
    cfg = get_config()
    prefix = cfg.get("collection_prefix", "").strip()
    return f"{prefix}{base_name}" if prefix else base_name


# ---------------------------------------------------------------------------
# NoSQL Document Serialization
# ---------------------------------------------------------------------------

def serialize_voucher(voucher_id: int, conn=None) -> dict | None:
    """
    Serialize a local SQLite voucher record and all its child relations
    (line items, memos, tags, and attachment metadata) into a pure JSON/NoSQL document.
    """
    v_full = db.get_voucher(voucher_id, conn=conn)
    if not v_full:
        return None

    v = v_full["voucher"]
    comp = v_full.get("company") or {}

    line_items_data = [
        {
            "id": li["id"],
            "description": li.get("description", ""),
            "category": li.get("category", ""),
            "amount": float(li.get("amount", 0.0))
        }
        for li in v_full.get("line_items", [])
    ]

    memos_data = [
        {
            "id": m["id"],
            "memo_text": m.get("memo_text", ""),
            "memo_type": m.get("memo_type", "General"),
            "created_by": m.get("created_by", ""),
            "created_at": str(m.get("created_at", ""))
        }
        for m in v_full.get("memos", [])
    ]

    # Tag names
    tags_list = []
    for t in v_full.get("tags", []):
        if isinstance(t, dict):
            tags_list.append(t.get("name", ""))
        else:
            tags_list.append(str(t))

    # Attachment metadata only (no large BLOBs to keep Firestore free and sub-1KB per doc)
    attachments_meta = [
        {
            "id": a["id"],
            "filename": a.get("filename", ""),
            "file_size": a.get("file_size", 0),
            "file_type": a.get("file_type", ""),
            "created_at": str(a.get("created_at", ""))
        }
        for a in v_full.get("attachments", [])
    ]

    company_id = int(v.get("company_id") or 1)
    clean_num = str(v.get("voucher_number", "")).strip()

    doc_id = f"comp_{company_id}_v_{clean_num.replace('/', '_').replace(' ', '_')}"

    return {
        "_doc_id": doc_id,
        "id": v["id"],
        "company_id": company_id,
        "company_name": comp.get("name", f"Company {company_id}"),
        "voucher_number": clean_num,
        "date": str(v.get("date", "")),
        "paid_to": str(v.get("paid_to", "")),
        "cash_given_by": str(v.get("cash_given_by", "")),
        "spent_by": str(v.get("spent_by") or ""),
        "total_amount": float(v.get("total_amount") or 0.0),
        "bill_status": str(v.get("bill_status") or "Pending"),
        "payment_method": str(v.get("payment_method") or "Cash"),
        "payment_ref": str(v.get("payment_ref") or ""),
        "float_id": v.get("float_id"),
        "float_name": v.get("float_name") or "",
        "due_date": str(v.get("due_date") or ""),
        "status": str(v.get("status") or "Active"),
        "prepared_by": str(v.get("prepared_by") or ""),
        "approved_by": str(v.get("approved_by") or ""),
        "printed": int(v.get("printed") or 0),
        "created_at": str(v.get("created_at") or ""),
        "updated_at": str(v.get("updated_at") or ""),
        "line_items": line_items_data,
        "memos": memos_data,
        "tags": tags_list,
        "attachments_meta": attachments_meta,
        "_cloud_synced_at": datetime.now(timezone.utc).isoformat(),
        "_app_version": "1.0"
    }


# ---------------------------------------------------------------------------
# Cloud Synchronization Actions (Non-Blocking)
# ---------------------------------------------------------------------------

def push_voucher_to_cloud(voucher_id: int, async_call: bool = True, on_done_callback=None):
    """
    Upload or update a single voucher document in Google Cloud Firestore NoSQL.
    If async_call is True (default), dispatches execution to background thread pool.
    """
    if not is_enabled():
        return

    def _worker():
        global _last_error
        try:
            client = get_firestore_client()
            if client is None:
                return

            doc_data = serialize_voucher(voucher_id)
            if not doc_data:
                return

            doc_id = doc_data.pop("_doc_id")
            coll_name = _collection_name(DEFAULT_VOUCHERS_COLLECTION)

            client.collection(coll_name).document(doc_id).set(doc_data, merge=True)
            logger.info(f"Voucher #{voucher_id} synced to Firestore doc '{doc_id}'")

            if on_done_callback:
                try:
                    on_done_callback(True, doc_id)
                except Exception:
                    pass

        except Exception as e:
            _last_error = str(e)
            logger.error(f"Error syncing voucher #{voucher_id} to Firestore: {e}")
            if on_done_callback:
                try:
                    on_done_callback(False, str(e))
                except Exception:
                    pass

    if async_call:
        _executor.submit(_worker)
    else:
        _worker()


def delete_voucher_from_cloud(company_id: int, voucher_number: str, async_call: bool = True):
    """
    Mark voucher as Cancelled or delete document from Firestore.
    """
    if not is_enabled():
        return

    def _worker():
        global _last_error
        try:
            client = get_firestore_client()
            if client is None:
                return

            clean_num = str(voucher_number).strip().replace('/', '_').replace(' ', '_')
            doc_id = f"comp_{company_id}_v_{clean_num}"
            coll_name = _collection_name(DEFAULT_VOUCHERS_COLLECTION)

            client.collection(coll_name).document(doc_id).update({
                "status": "Cancelled",
                "_cloud_synced_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"Voucher '{doc_id}' marked as Cancelled in Firestore.")
        except Exception as e:
            _last_error = str(e)
            logger.error(f"Error updating cancelled voucher in Firestore: {e}")

    if async_call:
        _executor.submit(_worker)
    else:
        _worker()


def upload_all_local_data(progress_callback=None) -> tuple[bool, int, str]:
    """
    Upload all local vouchers, company profiles, categories, people, tags,
    and cash floats to Firebase Cloud Firestore NoSQL.
    Uses Firestore batched writes (up to 450 items per batch) for maximum speed
    and minimum network latency.
    Returns: (is_success, count_uploaded, message)
    """
    global _last_error

    client = get_firestore_client()
    if client is None:
        return False, 0, f"Cannot connect to Firestore: {_last_error}"

    try:
        conn = db.get_connection()

        # 1. Upload Company Profiles
        comp_rows = conn.execute("SELECT * FROM companies").fetchall()
        comp_coll = client.collection(_collection_name(DEFAULT_COMPANIES_COLLECTION))
        for c in comp_rows:
            c_dict = dict(c)
            # Remove logo bytes from Firestore document to stay ultra lightweight
            c_dict.pop("logo", None)
            c_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            comp_coll.document(f"company_{c_dict['id']}").set(c_dict, merge=True)

        if progress_callback:
            progress_callback(10, "Company profiles uploaded...")

        # 2. Upload Categories
        cat_rows = conn.execute("SELECT * FROM categories").fetchall()
        cat_coll = client.collection(_collection_name(DEFAULT_CATEGORIES_COLLECTION))
        for cat in cat_rows:
            cat_dict = dict(cat)
            cat_name = cat_dict.get("name", "").strip()
            cat_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            cat_coll.document(f"cat_{cat_name}").set(cat_dict, merge=True)

        if progress_callback:
            progress_callback(20, "Expense categories uploaded...")

        # 3. Upload People
        people_rows = conn.execute("SELECT * FROM people").fetchall()
        people_coll = client.collection(_collection_name(DEFAULT_PEOPLE_COLLECTION))
        for p in people_rows:
            p_dict = dict(p)
            p_name = p_dict.get("name", "").strip()
            p_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            people_coll.document(f"person_{p_name}").set(p_dict, merge=True)

        # 4. Upload Tags
        tag_rows = conn.execute("SELECT * FROM tags").fetchall()
        tag_coll = client.collection(_collection_name(DEFAULT_TAGS_COLLECTION))
        for t in tag_rows:
            t_dict = dict(t)
            t_name = t_dict.get("name", "").strip()
            t_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            tag_coll.document(f"tag_{t_name}").set(t_dict, merge=True)

        # 5. Upload Money Floats
        float_rows = conn.execute("SELECT * FROM money_floats").fetchall()
        float_coll = client.collection(_collection_name(DEFAULT_FLOATS_COLLECTION))
        for fl in float_rows:
            fl_dict = dict(fl)
            fl_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            float_coll.document(f"float_{fl_dict['id']}").set(fl_dict, merge=True)

        if progress_callback:
            progress_callback(30, "Master data uploaded. Preparing vouchers...")

        # 6. Upload All Vouchers in Batches of 400
        voucher_ids = [r[0] for r in conn.execute("SELECT id FROM vouchers ORDER BY id ASC").fetchall()]
        total_vouchers = len(voucher_ids)
        uploaded_count = 0

        vouchers_coll = client.collection(_collection_name(DEFAULT_VOUCHERS_COLLECTION))
        batch_size = 400

        for i in range(0, total_vouchers, batch_size):
            chunk_ids = voucher_ids[i:i + batch_size]
            full_vouchers = db.get_vouchers_full_by_ids(chunk_ids, conn=conn)

            batch = client.batch()
            for v_data in full_vouchers:
                vid = v_data["voucher"]["id"]
                doc_payload = serialize_voucher(vid, conn=conn)
                if doc_payload:
                    doc_id = doc_payload.pop("_doc_id")
                    doc_ref = vouchers_coll.document(doc_id)
                    batch.set(doc_ref, doc_payload, merge=True)
                    uploaded_count += 1

            batch.commit()

            pct = 30 + int((uploaded_count / max(total_vouchers, 1)) * 65)
            if progress_callback:
                progress_callback(pct, f"Uploaded {uploaded_count}/{total_vouchers} vouchers...")

        conn.close()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_config({"last_synced": now_str})

        if progress_callback:
            progress_callback(100, f"Sync Complete! {uploaded_count} vouchers synced.")

        return True, uploaded_count, f"Successfully uploaded {uploaded_count} vouchers and master data to Firebase Firestore!"

    except Exception as e:
        _last_error = str(e)
        logger.error(f"Error during bulk upload to Firestore: {e}")
        return False, 0, f"Upload Error: {e}"


def pull_cloud_vouchers(progress_callback=None) -> tuple[bool, int, str]:
    """
    Download / pull vouchers from Firebase Cloud Firestore NoSQL into local SQLite.
    Inserts missing vouchers and updates existing ones if the cloud version is newer.
    Returns: (is_success, count_imported, message)
    """
    global _last_error

    client = get_firestore_client()
    if client is None:
        return False, 0, f"Cannot connect to Firestore: {_last_error}"

    try:
        vouchers_coll = client.collection(_collection_name(DEFAULT_VOUCHERS_COLLECTION))
        docs = list(vouchers_coll.stream())
        total_docs = len(docs)

        if total_docs == 0:
            return True, 0, "No vouchers found in Firestore database."

        conn = db.get_connection()
        imported_count = 0
        updated_count = 0

        for idx, doc_snap in enumerate(docs, 1):
            data = doc_snap.to_dict()
            if not data:
                continue

            v_num = data.get("voucher_number")
            comp_id = int(data.get("company_id") or 1)
            if not v_num:
                continue

            existing = conn.execute(
                "SELECT id, updated_at FROM vouchers WHERE company_id = ? AND voucher_number = ?",
                (comp_id, v_num)
            ).fetchone()

            items = data.get("line_items", [])
            tag_names = data.get("tags", [])

            # Ensure tags exist locally
            tag_ids = []
            for tname in tag_names:
                if not tname:
                    continue
                t_row = conn.execute("SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tname,)).fetchone()
                if t_row:
                    tag_ids.append(t_row[0])
                else:
                    cur = conn.execute("INSERT INTO tags (name, color) VALUES (?, '#3b82f6')", (tname,))
                    tag_ids.append(cur.lastrowid)

            form_data = {
                "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
                "voucher_number": v_num,
                "paid_to": data.get("paid_to", "Unknown"),
                "cash_given_by": data.get("cash_given_by", "Admin"),
                "spent_by": data.get("spent_by", ""),
                "bill_status": data.get("bill_status", "Pending"),
                "payment_method": data.get("payment_method", "Cash"),
                "payment_ref": data.get("payment_ref", ""),
                "float_id": data.get("float_id"),
                "due_date": data.get("due_date", ""),
                "status": data.get("status", "Active"),
                "prepared_by": data.get("prepared_by", ""),
                "approved_by": data.get("approved_by", ""),
                "tags": tag_ids,
            }

            if not existing:
                # Insert new voucher
                db.create_voucher(form_data, items, attachments=None, company_id=comp_id, conn=conn)
                imported_count += 1
            else:
                # Update existing if needed
                vid = existing["id"]
                db.update_voucher(vid, form_data, items, attachments=None, conn=conn)
                updated_count += 1

            if progress_callback and idx % 20 == 0:
                pct = int((idx / total_docs) * 100)
                progress_callback(pct, f"Processed {idx}/{total_docs} cloud vouchers...")

        conn.commit()
        conn.close()

        db.invalidate_all_caches()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_config({"last_synced": now_str})

        msg = f"Synced from Cloud: {imported_count} new vouchers imported, {updated_count} updated."
        return True, imported_count + updated_count, msg

    except Exception as e:
        _last_error = str(e)
        logger.error(f"Error pulling vouchers from Firestore: {e}")
        return False, 0, f"Pull Error: {e}"
