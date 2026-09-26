## 2026-04-01 - CSV Formula Injection Prevention in CSV Exports
**Vulnerability:** User-supplied inputs (payee names, line item descriptions, categories, payment references, float descriptions) exported to CSV files across `export_vouchers_to_csv`, `export_expense_summary_to_csv`, and `export_float_ledger_to_csv` could start with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`), causing CSV Formula / DDE Injection (CWE-1236) when opened in spreadsheet programs like Excel or Calc.
**Learning:** Standard CSV writers do not escape leading formula trigger characters in string cells. User inputs exported to CSV spreadsheets must be defensively sanitized to prevent command or formula execution.
**Prevention:** Use a helper (`_sanitize_csv_cell`) that inspects cell values and prepends a single quote (`'`) whenever a string value (after stripping leading whitespace) begins with `=`, `+`, `-`, `@`, `\t`, or `\r`.

## 2026-03-31 - Backup Database Path Traversal Prevention
**Vulnerability:** `backup_database(reason)` in `database.py` interpolated the `reason` argument directly into the backup filename string (`f"vouchers_backup_{ts}_{reason}.db"`), allowing potential directory traversal sequence injection (`../`) if untrusted or dynamic reason strings were passed.
**Learning:** Functions accepting label or reason parameters that build file names must treat those inputs as potentially untrusted strings and filter path characters before passing them to file system APIs.
**Prevention:** Sanitize filename components with `os.path.basename()` and character filtering (`isalnum()`), and enforce strict base directory boundary checks using `os.path.commonpath`.

## 2026-03-30 - Attachment File Path Traversal Prevention
**Vulnerability:** Attachment file operations (`get_attachment_data`, `delete_attachment`, `permanently_delete_voucher`, `clear_all_vouchers`) relied on stored `file_path` database strings without verifying that target files resided inside `ATTACHMENTS_DIR`. Additionally, user-supplied filenames in `_save_attachment_file` were not stripped of directory components.
**Learning:** Even when files are saved internally, database records or incoming attachment filenames with relative path sequences (`../`) can lead to arbitrary file read or deletion risks if path confinement is not explicitly enforced using `os.path.commonpath`.
**Prevention:** Always sanitize filenames with `os.path.basename()` before creating disk paths, and validate that absolute file paths reside strictly within the intended base directory using `os.path.commonpath([abs_target, abs_base]) == abs_base` before reading or deleting files.
