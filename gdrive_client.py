"""
Google Drive Cloud Storage Client for Voucher Machine.
Provides safe, free (15 GB) cloud synchronization of voucher attachments
(receipts, bills, PDFs) and database backup snapshots.

Supports:
1. Google Drive Synced Folder Mode (Zero API keys required, works seamlessly
   with Google Drive for Desktop / Mirror folders).
2. Automatic folder structure organization (by month & voucher number).
3. Non-blocking asynchronous sync worker for instant UI responsiveness.
4. Automatic SQLite database snapshot backup to Google Drive for total disaster recovery.
"""

import os
import shutil
import string
import logging
import threading
from datetime import datetime

import database as db

logger = logging.getLogger("VoucherMachine.GDrive")

DEFAULT_SUBFOLDER_ATTACHMENTS = "Voucher_Attachments"
DEFAULT_SUBFOLDER_BACKUPS = "Database_Backups"


# ---------------------------------------------------------------------------
# Path Detection & Validation
# ---------------------------------------------------------------------------

def detect_google_drive_paths() -> list[str]:
    """
    Search Windows file system for common Google Drive desktop sync directories.
    Returns a list of existing candidate directory paths.
    """
    candidates = []
    user_home = os.path.expanduser("~")

    # Check G:\ and standard Google Drive for Desktop virtual drive
    for letter in ["G", "H", "I", "F", "D", "E"]:
        drive_root = f"{letter}:\\"
        drive_my_drive = os.path.join(drive_root, "My Drive")
        if os.path.exists(drive_my_drive):
            candidates.append(drive_my_drive)
        elif os.path.exists(drive_root):
            # Check if volume name or contents contain Google Drive markers
            try:
                subdirs = [f.name.lower() for f in os.scandir(drive_root) if f.is_dir()]
                if "my drive" in subdirs or "other computers" in subdirs:
                    candidates.append(drive_root)
            except Exception:
                pass

    # Check User Profile folders
    profile_candidates = [
        os.path.join(user_home, "Google Drive"),
        os.path.join(user_home, "My Drive"),
        os.path.join(user_home, "GoogleDrive"),
    ]
    for p in profile_candidates:
        if os.path.exists(p) and p not in candidates:
            candidates.append(p)

    return candidates


def validate_folder_path(path: str) -> tuple[bool, str]:
    """
    Validate if a given folder path is usable for storing attachments.
    Returns: (is_valid, error_message_or_normalized_path)
    """
    if not path or not path.strip():
        return False, "Folder path cannot be empty."

    norm_path = os.path.abspath(path.strip())
    try:
        os.makedirs(norm_path, exist_ok=True)
        # Test write permission
        test_file = os.path.join(norm_path, ".vm_write_test")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        if os.path.exists(test_file):
            os.remove(test_file)
        return True, norm_path
    except Exception as e:
        return False, f"Folder path is not accessible or writable: {e}"


# ---------------------------------------------------------------------------
# Configuration Persistence
# ---------------------------------------------------------------------------

def get_config() -> dict:
    """
    Retrieve Google Drive configuration from settings table.
    Returns:
        dict with keys: enabled, folder_path, backup_database, organize_by_month, last_synced
    """
    settings = db.get_settings()
    enabled_str = settings.get("gdrive_enabled", "false").lower()
    folder_path = settings.get("gdrive_folder_path", "").strip()

    # If no folder path configured yet, try auto-detecting one
    if not folder_path:
        detected = detect_google_drive_paths()
        if detected:
            folder_path = detected[0]

    return {
        "enabled": enabled_str in ("true", "1", "yes"),
        "folder_path": folder_path,
        "backup_database": settings.get("gdrive_backup_database", "true").lower() in ("true", "1", "yes"),
        "organize_by_month": settings.get("gdrive_organize_by_month", "true").lower() in ("true", "1", "yes"),
        "last_synced": settings.get("gdrive_last_synced", ""),
    }


def save_config(cfg: dict):
    """Save Google Drive configuration dictionary to database settings."""
    save_dict = {}
    if "enabled" in cfg:
        save_dict["gdrive_enabled"] = "true" if cfg["enabled"] else "false"
    if "folder_path" in cfg:
        save_dict["gdrive_folder_path"] = str(cfg["folder_path"]).strip()
    if "backup_database" in cfg:
        save_dict["gdrive_backup_database"] = "true" if cfg["backup_database"] else "false"
    if "organize_by_month" in cfg:
        save_dict["gdrive_organize_by_month"] = "true" if cfg["organize_by_month"] else "false"
    if "last_synced" in cfg:
        save_dict["gdrive_last_synced"] = str(cfg["last_synced"])

    db.save_settings(save_dict)


def is_enabled() -> bool:
    """Check if Google Drive synchronization is enabled and the target folder is valid."""
    cfg = get_config()
    if not cfg["enabled"]:
        return False
    path = cfg.get("folder_path")
    return bool(path and os.path.exists(path))


# ---------------------------------------------------------------------------
# Attachment Synchronization Logic
# ---------------------------------------------------------------------------

def _clean_filesystem_name(name: str) -> str:
    """Sanitize filename for safe cross-platform folder naming."""
    return "".join(c for c in name if c.isalnum() or c in "._- ") or "Attachment"


def sync_voucher_attachments(voucher_id: int) -> tuple[int, list[str]]:
    """
    Synchronize all attachments of a specific voucher to the configured Google Drive folder.
    Returns: (synced_count, list_of_synced_dest_paths)
    """
    if not is_enabled():
        return 0, []

    cfg = get_config()
    root_folder = cfg["folder_path"]
    v_full = db.get_voucher(voucher_id)
    if not v_full or not v_full.get("voucher"):
        return 0, []

    v = v_full["voucher"]
    attachments = v_full.get("attachments", [])
    if not attachments:
        return 0, []

    # Format destination folder
    v_date = v.get("date") or datetime.now().strftime("%Y-%m-%d")
    month_str = v_date[:7] if cfg.get("organize_by_month") else "All"
    raw_vnum = v.get("voucher_number") or f"ID_{voucher_id}"
    safe_vnum = _clean_filesystem_name(str(raw_vnum))

    dest_dir = os.path.join(
        root_folder,
        DEFAULT_SUBFOLDER_ATTACHMENTS,
        month_str,
        f"Voucher_{safe_vnum}"
    )
    os.makedirs(dest_dir, exist_ok=True)

    synced_paths = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = db.get_connection()

    try:
        for att in attachments:
            att_id = att["id"]
            orig_filename = att.get("filename") or f"file_{att_id}.dat"
            safe_filename = _clean_filesystem_name(orig_filename)
            dest_file_path = os.path.join(dest_dir, safe_filename)

            # Retrieve attachment data
            att_data = db.get_attachment_data(att_id, conn=conn)
            if not att_data:
                continue

            file_bytes = att_data.get("file_data")
            local_path = att_data.get("file_path")

            # Copy file or write bytes (Security: Enforce strict path confinement within ATTACHMENTS_DIR)
            if local_path and db._is_safe_attachment_path(local_path) and os.path.exists(local_path):
                shutil.copy2(local_path, dest_file_path)
            elif file_bytes:
                with open(dest_file_path, "wb") as f:
                    f.write(file_bytes)
            else:
                continue

            synced_paths.append(dest_file_path)

            # Update DB with gdrive metadata
            try:
                conn.execute("""
                    UPDATE attachments
                    SET gdrive_path = ?, gdrive_synced_at = ?
                    WHERE id = ?
                """, (dest_file_path, now_str, att_id))
            except Exception:
                pass

        conn.commit()

        # Update last synced time
        save_config({"last_synced": now_str})

        # Also backup database snapshot if enabled
        if cfg.get("backup_database"):
            backup_database_to_gdrive()

        return len(synced_paths), synced_paths

    finally:
        conn.close()


def sync_voucher_attachments_async(voucher_id: int):
    """Run voucher attachment sync in a non-blocking background daemon thread."""
    def _worker():
        try:
            sync_voucher_attachments(voucher_id)
        except Exception as e:
            logger.error(f"Error syncing voucher #{voucher_id} attachments to Google Drive: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def sync_all_existing_attachments(progress_callback=None) -> tuple[bool, int, str]:
    """
    Scan all vouchers in the local database and back up any attachments to Google Drive.
    progress_callback: Optional callable(percent_int, status_text)
    Returns: (is_success, count_synced, status_message)
    """
    if not is_enabled():
        return False, 0, "Google Drive storage is not enabled or folder path is invalid."

    conn = db.get_connection()
    try:
        voucher_ids = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT voucher_id FROM attachments ORDER BY voucher_id ASC"
            ).fetchall()
        ]
    finally:
        conn.close()

    total_vouchers = len(voucher_ids)
    if total_vouchers == 0:
        return True, 0, "No attachments found in local database."

    total_synced_files = 0
    for idx, vid in enumerate(voucher_ids, 1):
        try:
            count, _ = sync_voucher_attachments(vid)
            total_synced_files += count
        except Exception as e:
            logger.warning(f"Failed to sync attachments for voucher #{vid}: {e}")

        if progress_callback:
            pct = int((idx / total_vouchers) * 100)
            progress_callback(pct, f"Synced {idx}/{total_vouchers} vouchers ({total_synced_files} files)...")

    # Also back up database snapshot
    backup_database_to_gdrive()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_config({"last_synced": now_str})

    msg = f"Successfully synced {total_synced_files} attachment file(s) across {total_vouchers} voucher(s) to Google Drive!"
    return True, total_synced_files, msg


# ---------------------------------------------------------------------------
# Database Cloud Backup to Google Drive
# ---------------------------------------------------------------------------

def backup_database_to_gdrive() -> str | None:
    """
    Create a fresh timestamped snapshot of vouchers.db and copy it to Google Drive.
    Rotates old backups in Google Drive to keep the latest 5.
    Returns: Destination path or None.
    """
    if not is_enabled():
        return None

    cfg = get_config()
    root_folder = cfg["folder_path"]
    backup_dir = os.path.join(root_folder, DEFAULT_SUBFOLDER_BACKUPS)
    try:
        os.makedirs(backup_dir, exist_ok=True)
        local_backup = db.backup_database(reason="gdrive_auto")
        if not local_backup or not os.path.exists(local_backup):
            return None

        filename = os.path.basename(local_backup)
        dest_path = os.path.join(backup_dir, filename)
        shutil.copy2(local_backup, dest_path)

        # Rotate backups in Google Drive folder (keep last 5)
        existing = sorted([
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith("vouchers_backup_") and f.endswith(".db")
        ], key=os.path.getmtime)

        while len(existing) > 5:
            oldest = existing.pop(0)
            try:
                os.remove(oldest)
            except Exception:
                pass

        logger.info(f"Database backup saved to Google Drive: {dest_path}")
        return dest_path

    except Exception as e:
        logger.error(f"Failed to copy database backup to Google Drive: {e}")
        return None


# ---------------------------------------------------------------------------
# Status & System Integration Helpers
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """
    Get current summary status of Google Drive integration.
    Returns dict with keys: enabled, folder_path, folder_exists, total_attachments, synced_attachments, last_synced
    """
    cfg = get_config()
    folder_path = cfg.get("folder_path", "")
    folder_exists = bool(folder_path and os.path.exists(folder_path))

    conn = db.get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0]
        # Count synced if column exists
        cols = [c[1].lower() for c in conn.execute("PRAGMA table_info(attachments)").fetchall()]
        if "gdrive_path" in cols:
            synced = conn.execute(
                "SELECT COUNT(*) FROM attachments WHERE gdrive_path IS NOT NULL AND gdrive_path != ''"
            ).fetchone()[0]
        else:
            synced = 0
    except Exception:
        total = 0
        synced = 0
    finally:
        conn.close()

    return {
        "enabled": cfg["enabled"],
        "folder_path": folder_path,
        "folder_exists": folder_exists,
        "backup_database": cfg["backup_database"],
        "total_attachments": total,
        "synced_attachments": synced,
        "last_synced": cfg.get("last_synced", ""),
    }


def open_gdrive_folder() -> bool:
    """Open the configured Google Drive folder in Windows File Explorer."""
    cfg = get_config()
    folder = cfg.get("folder_path")
    if folder and os.path.exists(folder):
        try:
            os.startfile(folder)
            return True
        except Exception as e:
            logger.error(f"Could not open Google Drive folder: {e}")
            return False
    return False
