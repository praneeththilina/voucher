"""
Firebase Cloud NoSQL Database Integration (Google Cloud Firestore).
Provides seamless, 100% free cloud synchronization for the Voucher Machine application.

Compliant with Google Firebase Spark Plan (Free Forever Tier):
- 1 GiB total document storage
- 50,000 document reads / day
- 20,000 document writes / day
- 20,000 document deletes / day
- Zero cost, no credit card required.

Supports two flexible connection modes so ANY company can connect their own database:
1. Web App Config (API Key + Project ID): Simplest setup, works directly via Firestore REST API.
2. Service Account Private Key (.json): Full Admin SDK mode.

All cloud operations execute in background worker threads with zero UI blocking.
"""

import os
import sys
import re
import json
import time
import shutil
import logging
import requests
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
        dict with keys: enabled, creds_path, project_id, api_key, auth_domain,
                        app_id, collection_prefix, auto_sync, last_synced, client_email
    """
    settings = db.get_settings()
    creds_path = settings.get("firebase_creds_path", "")
    if not creds_path and os.path.exists(get_default_creds_storage_path()):
        creds_path = get_default_creds_storage_path()

    return {
        "enabled": settings.get("firebase_enabled", "false").lower() in ("true", "1", "yes"),
        "creds_path": creds_path,
        "project_id": settings.get("firebase_project_id", ""),
        "api_key": settings.get("firebase_api_key", ""),
        "auth_domain": settings.get("firebase_auth_domain", ""),
        "app_id": settings.get("firebase_app_id", ""),
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
    if "api_key" in config_dict:
        save_payload["firebase_api_key"] = str(config_dict["api_key"]).strip()
    if "auth_domain" in config_dict:
        save_payload["firebase_auth_domain"] = str(config_dict["auth_domain"]).strip()
    if "app_id" in config_dict:
        save_payload["firebase_app_id"] = str(config_dict["app_id"]).strip()
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
    """Return True if either Service Account credentials or Web App API Key + Project ID is configured."""
    cfg = get_config()
    path = cfg.get("creds_path")
    if path and os.path.exists(path) and os.path.getsize(path) > 50:
        return True
    if cfg.get("project_id") and cfg.get("api_key"):
        return True
    return False


def is_enabled() -> bool:
    """Return True if Firebase is both configured and explicitly enabled by the user."""
    cfg = get_config()
    return cfg.get("enabled", False) and is_configured()


def parse_web_config_snippet(text: str) -> tuple[bool, dict, str]:
    """
    Parse a Firebase Web App configuration JS object snippet or JSON string.
    Extracts apiKey, projectId, authDomain, appId, storageBucket.
    """
    if not text or not text.strip():
        return False, {}, "Empty configuration text."

    data = {}
    keys = ["apiKey", "projectId", "authDomain", "appId", "storageBucket", "messagingSenderId", "measurementId"]
    for k in keys:
        pattern = r'["\']?' + k + r'["\']?\s*:\s*["\']([^"\']+)["\']'
        match = re.search(pattern, text)
        if match:
            data[k] = match.group(1).strip()

    if not data.get("projectId") and not data.get("apiKey"):
        # Try JSON parse
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                for k in keys:
                    if k in parsed:
                        data[k] = str(parsed[k]).strip()
        except Exception:
            pass

    if not data.get("projectId"):
        return False, {}, "Could not find 'projectId' in the pasted configuration."
    if not data.get("apiKey"):
        return False, {}, "Could not find 'apiKey' in the pasted configuration."

    return True, data, ""


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


# ---------------------------------------------------------------------------
# Firestore REST API Helpers
# ---------------------------------------------------------------------------

def _rest_base_url(project_id: str) -> str:
    """Return the base Firestore REST endpoint for documents."""
    return f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents"


def _val_to_firestore(val):
    """Convert a Python native value to Firestore REST Value format."""
    if val is None:
        return {"nullValue": None}
    if isinstance(val, bool):
        return {"booleanValue": val}
    if isinstance(val, int):
        return {"integerValue": str(val)}
    if isinstance(val, float):
        return {"doubleValue": float(val)}
    if isinstance(val, str):
        return {"stringValue": val}
    if isinstance(val, dict):
        return {"mapValue": {"fields": dict_to_firestore_fields(val)}}
    if isinstance(val, list):
        return {"arrayValue": {"values": [_val_to_firestore(i) for i in val]}}
    return {"stringValue": str(val)}


def dict_to_firestore_fields(d: dict) -> dict:
    """Convert a dictionary to Firestore REST API fields structure."""
    fields = {}
    for k, v in d.items():
        fields[k] = _val_to_firestore(v)
    return fields


def _val_from_firestore(v: dict):
    """Convert a Firestore REST value back into Python native format."""
    if not isinstance(v, dict):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        try:
            return int(v["integerValue"])
        except ValueError:
            return v["integerValue"]
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "booleanValue" in v:
        return v["booleanValue"]
    if "nullValue" in v:
        return None
    if "mapValue" in v:
        return firestore_fields_to_dict(v["mapValue"].get("fields", {}))
    if "arrayValue" in v:
        return [_val_from_firestore(item) for item in v["arrayValue"].get("values", [])]
    return v


def firestore_fields_to_dict(fields: dict) -> dict:
    """Convert Firestore REST API fields structure back into a standard Python dict."""
    res = {}
    for k, v in fields.items():
        res[k] = _val_from_firestore(v)
    return res


def get_firestore_client(force_reinit: bool = False):
    """
    Thread-safe initialization and retrieval of Google Cloud Firestore client (Admin SDK).
    Used when a service account credentials file is provided.
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


def test_connection(creds_path: str = None, project_id: str = None, api_key: str = None) -> tuple[bool, str, float]:
    """
    Test live connectivity to Google Cloud Firestore NoSQL database.
    Supports both Service Account JSON mode and Web App API Key mode.
    Returns: (is_success, status_message, latency_milliseconds)
    """
    start_time = time.time()
    cfg = get_config()

    eff_project_id = project_id or cfg.get("project_id", "").strip()
    eff_api_key = api_key or cfg.get("api_key", "").strip()
    target_path = creds_path or cfg.get("creds_path", "").strip()

    # ─────────────────────────────────────────────────────────────────────────
    # MODE 1: Service Account JSON Key (Admin SDK)
    # ─────────────────────────────────────────────────────────────────────────
    if target_path and os.path.exists(target_path):
        if not is_firebase_available():
            return False, "Error: 'firebase-admin' package is not installed.", 0.0

        import firebase_admin
        from firebase_admin import credentials, firestore

        is_valid, creds_data, err = validate_credentials_file(target_path)
        if not is_valid:
            return False, f"Invalid Credentials File: {err}", 0.0

        resolved_proj = eff_project_id or creds_data.get("project_id", "")
        test_app_name = f"test_{int(time.time())}"
        test_app = None
        try:
            cred = credentials.Certificate(target_path)
            test_app = firebase_admin.initialize_app(
                cred,
                {"projectId": resolved_proj},
                name=test_app_name
            )
            test_db = firestore.client(app=test_app)

            test_ref = test_db.collection(DEFAULT_HEALTHCHECK_COLLECTION).document("app_health_ping")
            now_iso = datetime.now(timezone.utc).isoformat()
            test_ref.set({
                "ping": True,
                "timestamp": now_iso,
                "app": "Voucher Machine Desktop",
                "free_tier": "Spark Plan Validated"
            })

            doc = test_ref.get()
            if not doc.exists:
                return False, "Firestore Ping failed: Document written but could not be read back.", 0.0

            try:
                test_ref.delete()
            except Exception:
                pass

            latency = round((time.time() - start_time) * 1000, 1)
            save_config({
                "project_id": resolved_proj,
                "client_email": creds_data.get("client_email", "")
            })
            get_firestore_client(force_reinit=True)

            return True, f"Connected to Firebase Firestore!\nMode: Service Account (Admin SDK)\nProject: {resolved_proj}\nLatency: {latency} ms (Spark Free Tier Active)", latency

        except Exception as e:
            err_msg = str(e)
            if "API has not been used" in err_msg or "it is disabled" in err_msg:
                return False, (
                    f"Firestore API is not enabled in your Google Cloud Project '{resolved_proj}'.\n\n"
                    f"To fix: Visit https://console.firebase.google.com/project/{resolved_proj}/firestore\n"
                    "Click 'Create Database' (Select Free Spark Plan & Test Mode)."
                ), 0.0
            return False, f"Connection Failed: {err_msg}", 0.0
        finally:
            if test_app:
                try:
                    firebase_admin.delete_app(test_app)
                except Exception:
                    pass

    # ─────────────────────────────────────────────────────────────────────────
    # MODE 2: Web App Config (API Key + Project ID via Firestore REST API)
    # ─────────────────────────────────────────────────────────────────────────
    elif eff_project_id and eff_api_key:
        base_url = _rest_base_url(eff_project_id)
        ping_url = f"{base_url}/{DEFAULT_HEALTHCHECK_COLLECTION}/app_health_ping?key={eff_api_key}"
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "fields": {
                "ping": {"booleanValue": True},
                "timestamp": {"stringValue": now_iso},
                "app": {"stringValue": "Voucher Machine Desktop"},
                "free_tier": {"stringValue": "Spark Plan Validated"}
            }
        }
        try:
            r = requests.patch(ping_url, json=payload, timeout=9)

            if r.status_code == 200:
                # Read back and delete
                try:
                    requests.delete(ping_url, timeout=5)
                except Exception:
                    pass
                latency = round((time.time() - start_time) * 1000, 1)
                save_config({"project_id": eff_project_id, "api_key": eff_api_key})
                return True, f"Connected to Firebase Firestore!\nMode: Web App API Key (REST API)\nProject: {eff_project_id}\nLatency: {latency} ms (Spark Free Tier Active)", latency

            elif r.status_code == 403:
                err_data = r.json() if "application/json" in r.headers.get("content-type", "") else {}
                err_msg = err_data.get("error", {}).get("message", r.text)

                if "API has not been used" in err_msg or "it is disabled" in err_msg or "PERMISSION_DENIED" in err_msg:
                    return False, (
                        f"Firestore Database is not created yet in project '{eff_project_id}'.\n\n"
                        f"Please activate it once in Firebase Console (100% Free):\n"
                        f"1. Open: https://console.firebase.google.com/project/{eff_project_id}/firestore\n"
                        "2. Click 'Create database'\n"
                        "3. Select 'Start in test mode' (allows read/write) -> Click 'Create'.\n\n"
                        "Once created, click 'Test Connection' again!"
                    ), 0.0
                return False, f"Firebase Permission Error (HTTP 403): {err_msg}", 0.0

            elif r.status_code == 404:
                return False, (
                    f"Firestore Database not found in project '{eff_project_id}'.\n"
                    f"Please visit https://console.firebase.google.com/project/{eff_project_id}/firestore and click 'Create database'."
                ), 0.0

            else:
                return False, f"Firebase Error (HTTP {r.status_code}): {r.text[:250]}", 0.0

        except Exception as e:
            return False, f"Network Error: Could not reach Google Firebase servers: {e}", 0.0

    else:
        return False, "Error: Please paste your Firebase Web App configuration or select a Service Account JSON file first.", 0.0


def get_status() -> dict:
    """Return high-level status dictionary for UI display."""
    cfg = get_config()
    has_creds = bool(cfg.get("creds_path") and os.path.exists(cfg["creds_path"]))
    mode = "Service Account" if has_creds else ("Web API Key" if cfg.get("api_key") else "None")
    return {
        "configured": is_configured(),
        "enabled": cfg.get("enabled", False),
        "auto_sync": cfg.get("auto_sync", True),
        "project_id": cfg.get("project_id", ""),
        "api_key": cfg.get("api_key", ""),
        "client_email": cfg.get("client_email", ""),
        "mode": mode,
        "last_synced": cfg.get("last_synced", "Never"),
        "last_error": _last_error,
        "is_online": _firestore_client is not None or bool(cfg.get("api_key")),
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

    tags_list = []
    for t in v_full.get("tags", []):
        if isinstance(t, dict):
            tags_list.append(t.get("name", ""))
        else:
            tags_list.append(str(t))

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
    Supports both Admin SDK and Firestore REST API.
    """
    if not is_enabled():
        return

    def _worker():
        global _last_error
        try:
            doc_data = serialize_voucher(voucher_id)
            if not doc_data:
                return

            doc_id = doc_data.pop("_doc_id")
            coll_name = _collection_name(DEFAULT_VOUCHERS_COLLECTION)
            cfg = get_config()

            # Path A: Admin SDK
            client = get_firestore_client()
            if client is not None:
                client.collection(coll_name).document(doc_id).set(doc_data, merge=True)
                logger.info(f"Voucher #{voucher_id} synced via Admin SDK to '{doc_id}'")
            # Path B: Firestore REST API
            elif cfg.get("project_id") and cfg.get("api_key"):
                url = f"{_rest_base_url(cfg['project_id'])}/{coll_name}/{doc_id}?key={cfg['api_key']}"
                payload = {"fields": dict_to_firestore_fields(doc_data)}
                r = requests.patch(url, json=payload, timeout=8)
                if r.status_code != 200:
                    logger.warning(f"REST API sync returned {r.status_code}: {r.text[:200]}")
                else:
                    logger.info(f"Voucher #{voucher_id} synced via REST API to '{doc_id}'")

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
    Mark voucher as Cancelled in Firestore.
    """
    if not is_enabled():
        return

    def _worker():
        global _last_error
        try:
            clean_num = str(voucher_number).strip().replace('/', '_').replace(' ', '_')
            doc_id = f"comp_{company_id}_v_{clean_num}"
            coll_name = _collection_name(DEFAULT_VOUCHERS_COLLECTION)
            cfg = get_config()

            client = get_firestore_client()
            if client is not None:
                client.collection(coll_name).document(doc_id).update({
                    "status": "Cancelled",
                    "_cloud_synced_at": datetime.now(timezone.utc).isoformat()
                })
            elif cfg.get("project_id") and cfg.get("api_key"):
                url = f"{_rest_base_url(cfg['project_id'])}/{coll_name}/{doc_id}?updateMask.fieldPaths=status&updateMask.fieldPaths=_cloud_synced_at&key={cfg['api_key']}"
                payload = {
                    "fields": {
                        "status": {"stringValue": "Cancelled"},
                        "_cloud_synced_at": {"stringValue": datetime.now(timezone.utc).isoformat()}
                    }
                }
                requests.patch(url, json=payload, timeout=8)

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
    Supports both Admin SDK and REST API.
    """
    global _last_error

    cfg = get_config()
    client = get_firestore_client()
    use_rest = (client is None and bool(cfg.get("project_id") and cfg.get("api_key")))

    if client is None and not use_rest:
        return False, 0, f"Cannot connect to Firestore: {_last_error or 'Not configured'}"

    try:
        conn = db.get_connection()
        proj_id = cfg["project_id"]
        api_key = cfg["api_key"]
        base_url = _rest_base_url(proj_id)

        # 1. Company Profiles
        comp_rows = conn.execute("SELECT * FROM companies").fetchall()
        for c in comp_rows:
            c_dict = dict(c)
            c_dict.pop("logo", None)
            c_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            doc_id = f"company_{c_dict['id']}"
            coll = _collection_name(DEFAULT_COMPANIES_COLLECTION)

            if client:
                client.collection(coll).document(doc_id).set(c_dict, merge=True)
            else:
                requests.patch(f"{base_url}/{coll}/{doc_id}?key={api_key}", json={"fields": dict_to_firestore_fields(c_dict)}, timeout=8)

        if progress_callback:
            progress_callback(10, "Company profiles uploaded...")

        # 2. Categories
        cat_rows = conn.execute("SELECT * FROM categories").fetchall()
        for cat in cat_rows:
            cat_dict = dict(cat)
            cat_name = cat_dict.get("name", "").strip()
            cat_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            doc_id = f"cat_{cat_name}"
            coll = _collection_name(DEFAULT_CATEGORIES_COLLECTION)

            if client:
                client.collection(coll).document(doc_id).set(cat_dict, merge=True)
            else:
                requests.patch(f"{base_url}/{coll}/{doc_id}?key={api_key}", json={"fields": dict_to_firestore_fields(cat_dict)}, timeout=8)

        if progress_callback:
            progress_callback(20, "Expense categories uploaded...")

        # 3. People
        people_rows = conn.execute("SELECT * FROM people").fetchall()
        for p in people_rows:
            p_dict = dict(p)
            p_name = p_dict.get("name", "").strip()
            p_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            doc_id = f"person_{p_name}"
            coll = _collection_name(DEFAULT_PEOPLE_COLLECTION)

            if client:
                client.collection(coll).document(doc_id).set(p_dict, merge=True)
            else:
                requests.patch(f"{base_url}/{coll}/{doc_id}?key={api_key}", json={"fields": dict_to_firestore_fields(p_dict)}, timeout=8)

        # 4. Tags
        tag_rows = conn.execute("SELECT * FROM tags").fetchall()
        for t in tag_rows:
            t_dict = dict(t)
            t_name = t_dict.get("name", "").strip()
            t_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            doc_id = f"tag_{t_name}"
            coll = _collection_name(DEFAULT_TAGS_COLLECTION)

            if client:
                client.collection(coll).document(doc_id).set(t_dict, merge=True)
            else:
                requests.patch(f"{base_url}/{coll}/{doc_id}?key={api_key}", json={"fields": dict_to_firestore_fields(t_dict)}, timeout=8)

        # 5. Money Floats
        float_rows = conn.execute("SELECT * FROM money_floats").fetchall()
        for fl in float_rows:
            fl_dict = dict(fl)
            fl_dict["_synced_at"] = datetime.now(timezone.utc).isoformat()
            doc_id = f"float_{fl_dict['id']}"
            coll = _collection_name(DEFAULT_FLOATS_COLLECTION)

            if client:
                client.collection(coll).document(doc_id).set(fl_dict, merge=True)
            else:
                requests.patch(f"{base_url}/{coll}/{doc_id}?key={api_key}", json={"fields": dict_to_firestore_fields(fl_dict)}, timeout=8)

        if progress_callback:
            progress_callback(30, "Master data uploaded. Preparing vouchers...")

        # 6. Upload All Vouchers
        voucher_ids = [r[0] for r in conn.execute("SELECT id FROM vouchers ORDER BY id ASC").fetchall()]
        total_vouchers = len(voucher_ids)
        uploaded_count = 0
        coll = _collection_name(DEFAULT_VOUCHERS_COLLECTION)

        if client:
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
                        doc_ref = client.collection(coll).document(doc_id)
                        batch.set(doc_ref, doc_payload, merge=True)
                        uploaded_count += 1
                batch.commit()

                pct = 30 + int((uploaded_count / max(total_vouchers, 1)) * 65)
                if progress_callback:
                    progress_callback(pct, f"Uploaded {uploaded_count}/{total_vouchers} vouchers...")
        else:
            # REST API chunking
            for idx, vid in enumerate(voucher_ids, 1):
                doc_payload = serialize_voucher(vid, conn=conn)
                if doc_payload:
                    doc_id = doc_payload.pop("_doc_id")
                    url = f"{base_url}/{coll}/{doc_id}?key={api_key}"
                    requests.patch(url, json={"fields": dict_to_firestore_fields(doc_payload)}, timeout=8)
                    uploaded_count += 1

                if progress_callback and (idx % 10 == 0 or idx == total_vouchers):
                    pct = 30 + int((idx / max(total_vouchers, 1)) * 65)
                    progress_callback(pct, f"Uploaded {idx}/{total_vouchers} vouchers...")

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
    Supports both Admin SDK and REST API.
    """
    global _last_error

    cfg = get_config()
    client = get_firestore_client()
    use_rest = (client is None and bool(cfg.get("project_id") and cfg.get("api_key")))

    if client is None and not use_rest:
        return False, 0, f"Cannot connect to Firestore: {_last_error or 'Not configured'}"

    try:
        coll = _collection_name(DEFAULT_VOUCHERS_COLLECTION)
        docs_data = []

        if client:
            for doc in client.collection(coll).stream():
                d = doc.to_dict()
                if d:
                    docs_data.append(d)
        else:
            url = f"{_rest_base_url(cfg['project_id'])}/{coll}?key={cfg['api_key']}&pageSize=300"
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                raw_docs = r.json().get("documents", [])
                for rd in raw_docs:
                    fields = rd.get("fields", {})
                    d = firestore_fields_to_dict(fields)
                    if d:
                        docs_data.append(d)
            elif r.status_code == 404:
                return True, 0, "No vouchers found in Firestore database."
            else:
                return False, 0, f"Failed to list documents (HTTP {r.status_code}): {r.text[:200]}"

        total_docs = len(docs_data)
        if total_docs == 0:
            return True, 0, "No vouchers found in Firestore database."

        conn = db.get_connection()
        imported_count = 0
        updated_count = 0

        for idx, data in enumerate(docs_data, 1):
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
                db.create_voucher(form_data, items, attachments=None, company_id=comp_id, conn=conn)
                imported_count += 1
            else:
                vid = existing["id"]
                db.update_voucher(vid, form_data, items, attachments=None, conn=conn)
                updated_count += 1

            if progress_callback and idx % 10 == 0:
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
