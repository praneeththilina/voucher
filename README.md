# 📋 Voucher Manager — SME Payment Voucher Tool

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/praneeththilina/voucher)
[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://microsoft.com/windows)

A modern, high-performance desktop application for managing, tracking, and printing SME payment vouchers. Built with Python, Tkinter (`ttkbootstrap` Cosmo theme), ReportLab for print-ready 2-per-page A4 PDF voucher generation, and `pypdfium2` for internal high-definition PDF previewing.

---

## ✨ Features

- **Recurring Voucher Templates**: Save frequently reused vouchers as templates and load them instantly (`Ctrl+T`).
- **Duplicate Voucher**: 1-click duplication of existing vouchers with fresh numbering and current date.
- **Batch Bill Status Update**: Multi-select vouchers to update status (`Paid`, `Unpaid`, `Pending`) in bulk via context menu.
- **Payment Method & Reference**: Explicit tracking for payment modes (Cash, Cheque, Bank Transfer, Online) and transaction references.
- **Dual Company Profiles**: Instant company switcher (`Ctrl+K`) with independent voucher numbering sequences and settings.
- **Customizable Company Header**: Company name, address, contact, email, tagline, and logo (stored as BLOB in SQLite).
- **Flexible Voucher Numbering**:
  - Monthly format (`26AUG_01`, 2-digit year + 3-letter month + sequential order, resets monthly).
  - Daily date-based sequencing (`V-YYYYMMDD-001`, resets daily).
  - Custom prefix and starting counter sequencing.
- **Smart Line Items & Autocomplete**:
  - Fast line item entry with automatic live sum calculations.
  - `@` trigger autocomplete for instant Category and Payee lookup.
- **Internal PDF Viewer**:
  - Embedded preview with 100% default scale, page navigation, and instant launch in external PDF viewer.
  - 2 vouchers per A4 page layout with ReportLab.
- **Smart Attachment Packing**:
  - Supports image and PDF attachments.
  - Automatically packs small slips onto shared A4 pages to save paper.
- **Security & Data Management**:
  - Password-protected **Clear All Vouchers** feature (Admin password: `Praneeth1991`).
  - Password-protected permanent deletion for disabled/cancelled vouchers.
  - Hardened with constant-time password verification and attachment path traversal sanitization.
- **Standalone Windows Executable**:
  - Compiled into a single, portable `VoucherManager.exe` with zero installation required.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Ctrl+N` | New Voucher |
| `Ctrl+E` | Edit Selected Voucher |
| `Ctrl+S` | Save Voucher |
| `Ctrl+Enter` | Save & Print Voucher |
| `Ctrl+P` | Print Selected Voucher(s) |
| `Ctrl+Shift+P` | Print All Pending Vouchers |
| `Ctrl+T` | Open Template Manager |
| `Del` | Cancel (Disable) Voucher |
| `Shift+Del` | Permanently Purge Disabled Voucher (Password Required) |
| `Ctrl+K` | Switch Active Company Profile |
| `Ctrl+G` | Open Category Manager |
| `Ctrl+M` | Open Name Manager |
| `Ctrl+,` | Open Header Settings |
| `F1` | About Application & Developer Info |
| `F5` | Refresh List |
| `Esc` | Back to Voucher List / Close Popup |

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+ installed on Windows.

### 2. Installation
Clone this repository and set up a virtual environment:

```bash
git clone https://github.com/praneeththilina/voucher.git
cd voucher

python -m venv venv
.\venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Run Application
```bash
python main.py
```

### 4. Build Standalone Executable (.exe)
```bash
python build_exe.py
```
The compiled single-file binary will be generated at `dist/VoucherManager.exe`.

---

## 👨‍💻 Developer Details

- **Developer**: Praneeth Thilina
