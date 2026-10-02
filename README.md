# 📋 Voucher Manager — SME Payment Voucher Tool

[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)](https://github.com/praneeththilina/voucher)
[![Python](https://img.shields.io/badge/python-3.10%20|%203.11%20|%203.12%20|%203.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://microsoft.com/windows)

A modern, high-performance desktop application for managing, tracking, and printing SME payment vouchers. Built with Python, Tkinter (`ttkbootstrap` Cosmo theme), ReportLab for print-ready 2-per-page A4 PDF voucher generation, and `pypdfium2` for internal high-definition PDF previewing.

---

## ✨ Features

- **☁️ Firebase Cloud NoSQL Database (Google Cloud Firestore)**:
  - **100% Free Database (Spark Plan)**: Zero cost forever, no credit card required (1 GiB storage, 50,000 reads/day, 20,000 writes/day).
  - **Multi-Tenant / Any Company Support**: Any business can plug in their own free Firebase project by uploading their `serviceAccountKey.json`.
  - **Offline-First Hybrid Architecture**: Local SQLite provides instant, zero-latency desktop operation; Firebase pushes live in background threads without UI blocking.
  - **Bi-Directional Sync**: 1-click bulk upload of all local records to Cloud, or download/pull cloud records to local.
- **Petty Cash & Money Float Manager**: Complete multi-float tracking (opening balance, top-ups, outflows, adjustments, custodians, running balances, and column header sorting with latest transactions on top).
- **Live Float Balance Header Badge**: Quick-launch button and real-time status in the main header bar displaying current balance and active float.
- **Accountant-Grade CSV Export**: Multi-section financial workbook format (Executive KPIs, Detailed Transaction Register, Category Breakdown, Payment Summaries).
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

## 🔥 Connecting Free Firebase Database (NoSQL)

Any company or organization can connect their own free Google Firebase project:

1. **Create Free Project**: Open [Firebase Console](https://console.firebase.google.com/) and create a project (e.g. `MyCompany-Vouchers`). The **Spark Plan is 100% Free forever** with no credit card required.
2. **Enable Firestore**: In the left sidebar, click **Build** > **Firestore Database** > **Create database** (Test mode or Production mode).
3. **Generate Key**: Click the **Project Settings ⚙️** icon > **Service accounts** tab > Click **Generate new private key** to download your JSON file.
4. **Connect in App**: Open the Voucher Manager, click **Settings (Ctrl+,)** > **☁️ Firebase Cloud Database** tab > Click **📂 Browse Key...** and select your downloaded JSON file.
5. **Test**: Click **⚡ Test Connection** to verify live connectivity. Toggle **Enable Firebase Cloud Sync** to start syncing vouchers in real-time!

---

## 👨‍💻 Developer Details

- **Developer**: Praneeth Thilina
