# 📋 Voucher Manager — SME Payment Voucher, Check Printing & Financial ERP Platform

[![Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](https://github.com/praneeththilina/voucher/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Database](https://img.shields.io/badge/database-SQLite%2030%20Migrations-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/tests-248%20passed%20%7C%20100%25-brightgreen.svg)](tests/)
[![Cloud Sync](https://img.shields.io/badge/cloud-Google%20Firebase%20NoSQL-FFCA28.svg?logo=firebase&logoColor=black)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **A fast, elegant, enterprise-grade desktop financial & bookkeeping platform** designed for Small and Medium Enterprises (SMEs). From issuing payment vouchers and printing millimeter-accurate bank checks to double-entry general ledger bookkeeping, AP/AR aging, 3-way match purchase orders, confidential payroll payslips, statutory VAT returns, and multi-page financial statements (P&L, Balance Sheet, Cash Flow) — with **zero monthly subscription fees**.

---

## 🧭 Visual System Architecture (v4.0)

```text
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                            VOUCHER MANAGER & SME BOOKKEEPING DESKTOP v4.0                       │
 │                                                                                                  │
 │ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌────────────────────────────┐ │
 │ │Tab 1: Voucher List│ │ Tab 2: Entry Form │ │Tab 3: Cash Float  │ │ Tab 4: Visual Analytics    │ │
 │ │     (Ctrl+1)      │ │     (Ctrl+2)      │ │     (Ctrl+3)      │ │        (Ctrl+4)            │ │
 │ │                   │ │                   │ │                   │ │                            │ │
 │ │• Live Search/Sort │ │• Multi-Currency   │ │• Petty Cash Drawer│ │• Monthly Spend Trends      │ │
 │ │• Compact Action Bar│ │• Live Forex Rates │ │• Top-Ups & Inflow │ │• Category Breakdown        │ │
 │ │• Multi-Select Act.│ │• Approval Badges  │ │• Reimbursements   │ │• Payee Leaderboards        │ │
 │ │• Batch Print/CSV  │ │• Paper-Saving PDF │ │• Running Balances │ │• Due Date Aging Rep.       │ │
 │ └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘ └────────────┬───────────────┘ │
 │           │                     │                     │                        │                 │
 └───────────┼─────────────────────┼─────────────────────┼────────────────────────┼─────────────────┘
             ▼                     ▼                     ▼                        ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                             COMPACT ACTION BAR & COMMERCIAL MODULES                              │
 │                                                                                                  │
 │   ⚡ Voucher Actions ▾     📒 Accounting ▾        💼 AP & AR ▾        📁 Operations ▾    ⚡ Alerts │
 │   • Duplicate / Cancel    • Chart of Accounts    • Suppliers Dir.    • Categories/Budgets       │
 │   • Issue Bank Check      • General Ledger & TB  • AP Invoices & Age • Staff & Payroll Runs     │
 │   • Batch Print Pending   • New Journal Entry    • Purchase Orders   • Payees & Floats          │
 │   • Approvals & Audit     • Financial Reports    • Goods Receiving   • Expense Claims           │
 │   • CSV Bulk Import/Export• Tax Rates & VAT Return• AR Customer Invoices• Recurring Schedules   │
 └─────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                               ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                               CORE ENGINES & STATUTORY REPORTING                                 │
 │  • Millimeter Check Printer      • Multi-Page Platypus Financial Reports (P&L, Balance Sheet)  │
 │  • Three-Way PO/GRN Matching     • Statutory VAT Return (Boxes 1-5 & Schedules)                  │
 │  • Staff Payslip PDF Generator   • Account Budget Variance Analytics (Annual / Monthly)         │
 └─────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                               ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                           LOCAL SQLITE ENGINE (Offline-First, Zero Lag)                          │
 │  • ACID WAL Mode  • 30 Applied Schema Migrations  • Sub-millisecond queries in data/vouchers.db  │
 └─────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                               │ (Non-blocking background sync)
                                               ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                        GOOGLE CLOUD FIRESTORE / DRIVE (Multi-Terminal Sync)                      │
 │  • Multi-Workstation Cloud Sync (Vouchers, Floats, Users) • Automated Daily Cloud Backups        │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Comprehensive Feature Matrix

### 🖋️ 1. Bank Check Printing Engine (v3.0)
- **Millimeter-Accurate Calibration**: Precise vector check canvas rendering compliant with Sri Lankan and international bank clearing specifications.
- **Pre-Configured Bank Stock Templates**: Instant presets for **Bank of Ceylon (BOC)**, **Commercial Bank of Ceylon**, **Hatton National Bank (HNB)**, and **Sampath Bank**.
- **Visual Template Designer**: Adjust date boxes, payee line, numeric amount box, amount-in-words line, and "A/C PAYEE ONLY" crossing.
- **Cheque Register & Reconciliation**: Status tracking (`Draft`, `Printed`, `Issued`, `Cleared`, `Voided`, `Bounced`) with checkbook register and bank reconciliation matching.
- **Algorithmic Amount-in-Words**: Automatic English capitalization with currency and cent subdivisions.

### 📒 2. Chart of Accounts (COA) & General Ledger (v3.5)
- **Standard 5-Group Structure**: Pre-seeded standard chart of accounts:
  - `1000–1999`: **Assets** (Cash, Petty Cash, Bank Accounts, Accounts Receivable)
  - `2000–2999`: **Liabilities** (Accounts Payable, Tax Payable, Accruals)
  - `3000–3999`: **Equity** (Owner's Capital, Retained Earnings)
  - `4000–4999`: **Income** (Sales Revenue, Service Revenue, Discounts Received)
  - `5000–5999`: **Expenses** (Cost of Goods Sold, Rent, Salaries, Utilities, Travel)
- **Manual Double-Entry Journaling**: Multi-line balanced journal entries with debit/credit balance validation.
- **Automated Voucher Journaling**: Payment vouchers automatically generate balanced double-entry journals linking cash/bank accounts to specific expense ledgers.
- **Real-Time Trial Balance**: Instant debit/credit reconciliation statement.

### 🏢 3. Accounts Payable (AP) & Supplier Bills (v3.5)
- **Supplier Master Directory**: Vendor contacts, payment terms, tax numbers, and credit balances.
- **Multi-Line AP Invoices**: Itemized bills with tax rates, line totals, discounts, and payment terms.
- **Prompt Payment Discounts**: Auto-journals early payment discounts to `4310 Discounts Received`.
- **AP Aging Analysis**: Interactive aging buckets (**Current, 1–30, 31–60, 61–90, 90+ days**) with PDF/CSV reports.
- **Supplier Invoice PDF Generator**: Standard commercial bill format with letterhead branding.

### 👥 4. Accounts Receivable (AR) & Customer Invoicing (v3.8)
- **Customer Directory**: Customer profiles, tax registration, credit limits, and outstanding balances.
- **Customer Tax Invoices**: Professional tax invoicing with automatic invoice number sequencing (`INV-YYYY-XXXX`).
- **Payment Receipts**: Record partial or full payments, issuing numbered receipts with balance updates.
- **AR Aging Analysis**: Accounts receivable aging buckets to track overdue client collections.
- **Customer Tax Invoice & Receipt PDF Generator**: High-definition invoice and receipt printing.

### 📊 5. Financial Reporting Engine (v3.8)
- **Publication-Quality Platypus PDF Engine**: Multi-page financial reports using ReportLab with two-pass `NumberedCanvas` ("Page X of Y"), company branding, and double-underline grand totals.
- **Profit & Loss Statement (Income Statement)**: Revenue, Cost of Goods Sold, Gross Profit, Operating Expenses, and Net Profit.
- **Balance Sheet (Statement of Financial Position)**: Total Assets, Total Liabilities, Equity, and Balanced Net Position.
- **Cash Flow Statement**: Cash flow from Operating, Investing, and Financing activities (Indirect method).
- **Interactive 4-Tab GUI Dashboard**: Real-time KPI summary cards, period presets, and 1-click PDF/CSV export.

### 📦 6. Purchase Orders & Goods Receiving (GRN) (v4.0)
- **Procurement Order Management**: Multi-line vendor purchase orders (`PO-YYYY-XXXX`) with tax and terms.
- **Goods Received Notes (GRN)**: Warehouse receiving inspection slips (`GRN-YYYY-XXXX`) tracking received and rejected quantities.
- **Live Quantity Tracking**: PO lines dynamically track `received_qty` with status transitions (`Draft` → `Issued` → `Partially Received` → `Fully Received`).
- **Automated 3-Way Matching**: Convert approved POs and GRNs directly into Accounts Payable Supplier Invoices with zero manual data re-entry.
- **PO & GRN PDF Generator**: Formal vendor Purchase Orders and Goods Received inspection slips.

### 👥 7. Basic Payroll & Employee Expense Claims (v4.0)
- **Staff Directory**: Employee records with auto-generated employee codes (`EMP-0001`), designations, NIC, and bank details.
- **Monthly Payroll Wizard**: Interactive batch processing of monthly pay runs (`YYYY-MM`) calculating basic salary, allowances, overtime, gross pay, employee deductions (EPF 8%, PAYE/APIT tax), and net pay.
- **1-Click Payroll Payout Voucher**: Automatically generates payment vouchers under `Salaries & Wages` with General Ledger auto-journaling (Debit Salaries `5110`, Credit Bank `1120` / Cash `1110`).
- **Confidential Payslip PDF**: Individual payslips with side-by-side earnings vs deductions, net pay badge, and bank details.
- **Executive Monthly Payroll Sheet**: Master payroll summary for bank dispatch and director review.
- **Employee Expense Claims**: Staff reimbursement claims (`CLM-YYYY-XXXX`) with itemized receipts and voucher integration.

### 🏛️ 8. Tax Management & VAT / GST Statutory Returns (v4.0)
- **Configurable Tax Rate Presets**: Pre-seeded with `Standard VAT 18%` (default), `Zero Rated (0%)`, `Exempt (0%)`, and `Withholding Tax 5%`.
- **Official VAT Return Calculation**:
  - **Box 1**: Total Taxable Sales / Supplies (excl. VAT)
  - **Box 2**: Total Output VAT Charged on Sales
  - **Box 3**: Total Taxable Purchases / Inputs (excl. VAT)
  - **Box 4**: Total Input VAT Paid on Purchases
  - **Box 5**: Net VAT Payable to Tax Authority / (Net Tax Credit / Refund Due)
- **Official Statutory VAT Return PDF**: Complete filing statement with Schedule A (Sales), Schedule B (Purchases), and Authorized Taxpayer Declaration block.

### 🎯 9. Budgets & Advanced Variance Analytics (v4.0)
- **Account-Level Budget Allocations**: Set monthly or annual budgets per Chart of Accounts expense/income ledger.
- **Live Spending Variance Tracking**: Real-time variance comparison against posted General Ledger transactions and vouchers.
- **3-Tier Financial Status Badges**:
  - 🟢 **Within Budget** (< 80% utilization)
  - 🟡 **Warning** (80%–100% utilization ceiling)
  - 🔴 **Exceeded** (> 100% over-budget alert)
- **Annual Spread Wizard**: Distribute an annual budget equally across 12 calendar months with 1 click.
- **Budget Variance PDF Statement**: Executive report with KPI cards, account breakdown, and dual sign-off blocks.

### ⚡ 10. Compact Action Bar & Seamless Navigation
- **Single-Row Action Bar**: Replaces multi-row clutter with four streamlined dropdown menus:
  - `⚡ Voucher Actions ▾`: Duplicate, Issue Check, Batch Print, Approvals, Lifecycle, CSV Import/Export, and Audit History.
  - `📒 Accounting ▾`: Chart of Accounts, General Ledger, New Journal Entry, Financial Reports, Tax & VAT, Bank Recon, Exchange Rates.
  - `💼 AP & AR ▾`: Suppliers Directory, AP Invoices & Aging, Purchase Orders & GRN, Customers Directory, AR Invoices & Receipts.
  - `📁 Operations ▾`: Expense Categories & Budgets, Budgets & Variance, Payees Directory, Cash Floats, Payroll & HR, Recurring Schedules, Analytics.
- **`MenuActionProxy` Architecture**: Maintains 100% compatibility with Role-Based Access Control (RBAC) permission checks and programmatic shortcuts.

---

## ⌨️ Complete Keyboard Shortcut Guide

| Category | Shortcut | Function |
| :--- | :--- | :--- |
| **Tab Navigation** | `Ctrl+1` | Switch to **Tab 1: Voucher List** |
| | `Ctrl+2` | Switch to **Tab 2: New Voucher Form** |
| | `Ctrl+3` | Switch to **Tab 3: Cash Float & Drawer Manager** |
| | `Ctrl+4` | Switch to **Tab 4: Visual Analytics Dashboard** |
| | `Esc` | Return to Voucher List / Dismiss any active dialog |
| **User & Access** | `Ctrl+Shift+L` | **Switch User / Shift Change (PIN Authentication)** |
| **Voucher Actions** | `Ctrl+N` | Start a fresh Voucher (clears form and focuses Payee) |
| | `Ctrl+S` | Save current Voucher |
| | `Ctrl+Enter` | Save & immediately open Print / PDF Preview |
| | `Ctrl+P` | Print selected voucher(s) |
| | `Ctrl+Shift+P` | Batch print all unprinted active vouchers |
| | `Ctrl+E` | Edit highlighted voucher in form |
| | `Ctrl+D` | Duplicate highlighted voucher into a new draft |
| | `Ctrl+W` | Clear form inputs |
| | `Alt+A` | Add a new line item row |
| | `Del` | Cancel (disable) selected voucher |
| | `Shift+Del` | Permanently delete cancelled voucher (Admin password protected) |
| **Accounting & ERP**| `Ctrl+Shift+O` | Open **Chart of Accounts** Ledger |
| | `Ctrl+Shift+G` | Open **General Ledger & Trial Balance** |
| | `Ctrl+Shift+J` | Open **New Journal Entry** Dialog |
| | `Ctrl+Shift+B` | Open **Bank Statement Reconciliation** |
| | `Ctrl+Shift+A` | Open **Smart Alert Center** |
| | `Ctrl+Shift+R` | Open **Recurring Payment Schedules** |
| | `Ctrl+Shift+I` | Open **Bulk CSV Import Wizard** |
| | `Ctrl+Shift+U` | Open **User Management & RBAC** |
| **Management** | `Ctrl+F` | Focus Search Box in voucher list |
| | `Ctrl+K` | Quick-switch active company profile |
| | `Ctrl+G` | Open Category & Monthly Budget Manager |
| | `Ctrl+M` | Open Payee & Personnel Directory Manager |
| | `Ctrl+T` | Open Reusable Voucher Template Manager |
| | `Ctrl+Shift+T` | Open Voucher Tag & Label Manager |
| | `Ctrl+Shift+S` | Open Payee Statement & Vendor Ledger |
| | `Ctrl+I` | Open Expense Analytics & Visual Charts |
| | `Ctrl+,` | Open System Settings & Cloud Sync Configuration |
| | `F5` | Force refresh active list view |
| | `F1` | Open About Dialog & Release Notes |

---

## 🚀 Installation & Getting Started

### Option A: Portable Standalone Executable (Recommended for Non-Developers)
No Python, Git, or dependencies required!

1. Download `VoucherManager-windows.zip` from the [**Latest Releases**](https://github.com/praneeththilina/voucher/releases/latest).
2. Extract the archive to any convenient directory (e.g. `C:\VoucherManager\` or a portable USB drive).
3. Double-click `VoucherManager.exe` to launch immediately!
4. On first launch, the app automatically initializes `data/vouchers.db` with all 30 schema migrations and pre-seeded default accounts.

> [!TIP]
> **Sub-Second Instant Startup (< 0.5s)**: Voucher Manager uses a folder bundle architecture with pre-extracted dependencies in `_internal/`. Unlike traditional single-file exes, it never uncompresses megabytes into temporary folders on every launch, giving you instant startup and zero lag.

---

### Option B: Running from Source (Developers)

```powershell
# 1. Clone the repository
git clone https://github.com/praneeththilina/voucher.git
cd voucher

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install required dependencies
pip install -r requirements.txt

# 4. Run application
python main.py

# 5. Run full test suite (248 tests)
python -m unittest discover -s tests -p "test_*.py"

# 6. Build production standalone executable
python build_exe.py
```

---

## 🧪 Comprehensive Test Suite (248 Tests Passing)

The repository features comprehensive automated test coverage across 33 test suites:

```text
Ran 248 tests in 199.593s
OK
```

| Test Suite | Module Under Test | Covered Scenarios |
| :--- | :--- | :--- |
| `test_check_printer.py` | `check_printer.py` | Check PDF generation, coordinates, millimeter scaling |
| `test_check_database.py` | `database.py` | Check register CRUD, voiding, clearing, bank recon matching |
| `test_check_integration.py`| UI & Vouchers | 1-click check issuing from payment vouchers |
| `test_chart_of_accounts.py`| `database.py` | 5-group COA hierarchy, accounts CRUD, system guards |
| `test_general_ledger.py` | `database.py` | Double-entry journals, balance validation, auto-journaling |
| `test_ap_invoices.py` | `database.py` | AP bills, payments, discount balancing, aging buckets |
| `test_ar_invoices.py` | `database.py` | AR customer invoices, receipts, AR aging buckets |
| `test_financial_reports.py`| `reports/` | Multi-page P&L, Balance Sheet, Cash Flow, Trial Balance |
| `test_purchase_orders.py` | `database.py`, `po_printer` | POs, GRN receiving, partial receipts, 3-way matching |
| `test_payroll.py` | `database.py`, `payroll_printer`| Staff master, payroll runs, payslip PDFs, expense claims |
| `test_tax_manager.py` | `database.py`, `reports/vat_return`| Tax presets, statutory VAT Return (Boxes 1-5), PDF |
| `test_budgets.py` | `database.py`, `reports/budget_vs_actual`| Account budgets, monthly/annual variance, burn rates |
| `test_currency.py` | `currency_service.py` | Live exchange rates, custom currencies, conversions |
| `test_database.py` | `database.py` | Core vouchers, floats, migrations, caching, concurrency |
| `test_widgets.py` | `ui/` | Action Bar dropdowns, RBAC proxy, keyboard shortcuts |
| *+ 18 additional suites* | *Core & Integrations* | Full regression safety |

---

## 🏢 Multi-Company Profile Management

Manage multiple separate legal entities within the same application:
- **Zero Confusion**: Each company maintains isolated voucher numbering, petty cash floats, Chart of Accounts, supplier bills, customer invoices, and payroll runs.
- **Quick Switching (`Ctrl+K`)**: Switch active company in less than a second from the header.
- **Automated Provisioning**: Every new company profile automatically provisions its own default Cash Float, Chart of Accounts, and default VAT tax presets.

---

## 🔒 Security & Data Sovereignty

- **100% Offline-First**: Your financial records, customer list, and supplier bills reside locally in SQLite (`data/vouchers.db`) under ACID transactions.
- **Role-Based Access Control (RBAC)**: 5 user tiers (`Viewer`, `Data Entry`, `Cashier`, `Manager`, `Admin`) with PBKDF2-HMAC-SHA256 password/PIN hashing.
- **Audit Trails**: Non-destructive cancellation with immutable audit logging for all critical operations (voucher voids, check cancellations, journal entries).

---

## 👨‍💻 Author & Maintainer

- **Developer**: Praneeth Thilina
- **GitHub**: [@praneeththilina](https://github.com/praneeththilina)
- **Repository**: [https://github.com/praneeththilina/voucher](https://github.com/praneeththilina/voucher)

---

## 📄 License

This project is licensed under the **MIT License** — feel free to use, modify, and deploy it for your personal or commercial business operations.
