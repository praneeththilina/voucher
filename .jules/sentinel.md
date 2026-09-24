## 2026-03-31 - Backup Database Path Traversal Prevention
**Vulnerability:** `backup_database(reason)` in `database.py` interpolated the `reason` argument directly into the backup filename string (`f"vouchers_backup_{ts}_{reason}.db"`), allowing potential directory traversal sequence injection (`../`) if untrusted or dynamic reason strings were passed.
**Learning:** Functions accepting label or reason parameters that build file names must treat those inputs as potentially untrusted strings and filter path characters before passing them to file system APIs.
**Prevention:** Sanitize filename components with `os.path.basename()` and character filtering (`isalnum()`), and enforce strict base directory boundary checks using `os.path.commonpath`.

## 2026-03-30 - Attachment File Path Traversal Prevention
**Vulnerability:** Attachment file operations (`get_attachment_data`, `delete_attachment`, `permanently_delete_voucher`, `clear_all_vouchers`) relied on stored `file_path` database strings without verifying that target files resided inside `ATTACHMENTS_DIR`. Additionally, user-supplied filenames in `_save_attachment_file` were not stripped of directory components.
**Learning:** Even when files are saved internally, database records or incoming attachment filenames with relative path sequences (`../`) can lead to arbitrary file read or deletion risks if path confinement is not explicitly enforced using `os.path.commonpath`.
**Prevention:** Always sanitize filenames with `os.path.basename()` before creating disk paths, and validate that absolute file paths reside strictly within the intended base directory using `os.path.commonpath([abs_target, abs_base]) == abs_base` before reading or deleting files.
