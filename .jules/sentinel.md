## 2026-04-04 - Administrator Password Validation to Prevent Permanent Lockout DoS
**Vulnerability:** `set_admin_password` in `database.py` accepted `None`, empty (`""`), or whitespace-only password strings and computed/stored their PBKDF2 hashes. However, `verify_admin_password` short-circuited and rejected empty inputs (`if not provided_password: return False`), creating an irreversible administrator account lockout (Denial of Service) for protected operations like clearing or permanently deleting vouchers.
**Learning:** Functions updating user or administrative credentials must validate input constraints (such as non-empty/non-whitespace) before generating key derivation hashes, especially when authentication verification functions short-circuit on blank inputs.
**Prevention:** Enforce explicit input validation (`if not new_password or not new_password.strip(): raise ValueError(...)`) in password update methods prior to hashing or persisting credentials.

## 2026-04-03 - Update Executable Path Validation and Batch Script Injection Prevention
**Vulnerability:** `apply_update_and_restart(new_exe_path)` in `updater.py` interpolated executable path strings directly into a Windows batch script (`.bat`) without verifying that the file existed or sanitizing batch control characters (`"`, `\r`, `\n`, `&`, `|`, `<`, `>`, `^`, `%`). Unvalidated paths caused application exit without update completion if files were missing, or risked batch syntax breakage and command injection.
**Learning:** File paths embedded into generated `.bat` scripts for `cmd.exe` execution must be verified to exist beforehand, sanitized against batch control and quote characters, and have `%` signs escaped as `%%` to prevent environment variable expansion or command injection.
**Prevention:** Verify file existence with `os.path.isfile(path)` before spawning detached process scripts, reject paths containing batch command separators/quotes (`"`, `\r`, `\n`, `&`, `|`, `<`, `>`, `^`), and escape `%` as `%%`.

## 2026-04-02 - PBKDF2 Password Hashing with Transparent Legacy Hash Migration
**Vulnerability:** Administrator password hashes were stored as unsalted single-iteration SHA-256 hashes (`hashlib.sha256(password)`), exposing them to offline dictionary and rainbow table attacks if database settings or backup files were accessed.
**Learning:** Legacy simple hashing implementations should be upgraded to key derivation functions (PBKDF2-HMAC-SHA256) with unique per-password random salts and high iteration counts (100,000). To avoid invalidating existing user credentials, authentication logic can transparently upgrade legacy hashes to PBKDF2 upon successful verification.
**Prevention:** Always store password hashes using `hashlib.pbkdf2_hmac("sha256", password, salt, 100000)` with `os.urandom(16)` salt, and inspect stored hash prefixes to trigger automatic re-hashing when legacy hash formats are authenticated.

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
