# System Architecture Documentation — Voucher Manager v4.0

## 1. Executive Summary & Architectural Goals

**Voucher Manager v4.0** is an enterprise-grade, offline-first financial desktop platform built in Python for Small and Medium Enterprises (SMEs). Expanding beyond core payment voucher management, v4.0 incorporates a complete bookkeeping ERP suite:
- Precision millimeter-accurate bank check printing (v3.0)
- Chart of Accounts (COA) & balanced double-entry General Ledger (v3.5)
- Accounts Payable (AP) supplier invoices, payments, and aging (v3.5)
- Accounts Receivable (AR) customer tax invoices, receipts, and aging (v3.8)
- Multi-page financial reporting engine (P&L, Balance Sheet, Cash Flow, Trial Balance) (v3.8)
- Purchase Orders (PO), Goods Received Notes (GRN), and 3-way matching (v4.0)
- Staff payroll runs, confidential payslips, and employee expense claims (v4.0)
- Tax rate management and statutory VAT / GST return filing (v4.0)
- Account-level budgeting, annual spread, and live variance analytics (v4.0)
- Multi-terminal cloud synchronization via Google Cloud Firestore

### Primary Architectural Principles:
1. **Zero-Data-Loss & Data Sovereignty**: Each legal entity lives in its own SQLite file under data/companies, using ACID WAL mode and isolated attachment and backup directories.
2. **Double-Entry Integrity**: Every operational transaction (vouchers, supplier payments, customer receipts, payroll disbursements) maintains mathematical double-entry balance ($\sum \text{Debits} = \sum \text{Credits}$) with automated journal generation.
3. **High-Performance Hybrid Storage**: Separation of structured metadata (SQLite) from unstructured binary assets (disk filesystem) keeps queries sub-millisecond even with tens of thousands of records.
4. **Role-Based Access Control (RBAC)**: A login-first application gate, salted PBKDF2 password hashing, offline recovery keys, distinct operational roles, and dynamic UI enforcement.
5. **Multi-Page Precision Vector Rendering**: ReportLab Platypus engine with two-pass `NumberedCanvas` ("Page X of Y") for all official documents (checks, vouchers, tax invoices, purchase orders, payslips, and statutory financial statements).

---

## 2. Technology Stack & Component Matrix

| Layer | Component / Library | Architectural Role & Justification |
|---|---|---|
| **Core Runtime** | Python 3.10 – 3.14 (64-bit) | Modern language runtime with native typing and multi-threading capabilities. |
| **GUI Framework** | `Tkinter` + `ttkbootstrap` | Native Windows controls with CSS-like theming and high-DPI scaling. |
| **Relational Database** | `sqlite3` (WAL & Foreign Keys) | Embedded, zero-configuration SQL engine with 30 applied schema migrations. |
| **Cloud NoSQL Database** | `google-cloud-firestore` / REST | Multi-terminal synchronization for vouchers, floats, users, and approvers. |
| **Forex Rates Engine** | `open.er-api.com` REST API | Open Access daily exchange rate synchronization for global currencies to LKR base. |
| **PDF Generation Engine** | `reportlab` (Platypus & Canvas) | Millimeter-accurate vector PDF rendering for checks, vouchers, invoices, and financial reports. |
| **PDF Rasterization** | `pypdfium2` (Google PDFium wrapper) | Native C++ PDF rendering engine for zero-dependency in-app PDF previewing. |
| **Image Processing** | `Pillow` (PIL) | Aspect-ratio preserving scaling, logo processing, and receipt encoding. |
| **Security & Cryptography** | `hashlib` (PBKDF2-HMAC-SHA256) | Salted password and PIN hashing with 100,000 iterations against brute-force attacks. |
| **Distribution** | `PyInstaller` + Folder Bundle | Fast-launching folder bundle with pre-extracted dependencies in `_internal/`. |

---

## 3. High-Level Architecture Diagram

```mermaid
graph TD
    subgraph UI_Layer [Presentation & Interaction Layer (Tkinter / ttkbootstrap)]
        LG[LoginScreen / Company File Selector]
        MW[MainWindow / Accountant Centre + Operational Tabs]
        AC[Accountant Centre / KPI + Work Queue]
        AB[Compacted Action Bar & MenuActionProxy]
        CE[Voucher Creation Form]
        AD[Visual Analytics Dashboard]
        CHK[Check Register & Template Designer]
        COA[Chart of Accounts Dialog]
        GL[General Ledger & Journal Wizard]
        AP[AP Invoices & Supplier Manager]
        AR[AR Invoices & Customer Manager]
        PO[Purchase Orders & GRN Manager]
        PAY[Payroll Wizard & Staff Directory]
        TAX[Tax Rates & VAT Return Calculator]
        BDG[Budget Manager & Variance Analytics]
        REP[Financial Reports Dashboard]
        DRILL[Read-only Transaction / Journal Drill-down]
        PV[Embedded PdfViewerDialog]
    end

    subgraph Business_Logic [Service & Engine Layer]
        CP[Check Printing Engine (check_printer.py)]
        IP[Invoice Printer (invoice_printer.py)]
        PP[PO & GRN Printer (po_printer.py)]
        PYP[Payroll Printer (payroll_printer.py)]
        RP[Financial Report Printer (reports/report_printer.py)]
        VR[VAT Return Engine (reports/vat_return.py)]
        BA[Budget Variance Engine (reports/budget_vs_actual.py)]
        FC[Firebase Cloud Sync Client]
        FX[Exchange Rate Client]
    end

    subgraph Data_Storage [Persistent Storage Layer]
        REG[Non-secret Company Registry]
        DB[(SQLite: one database per company - 32 Migrations)]
        FS[Per-company Attachment Storage]
        BK[Per-company Backups and Preserved Legacy Source]
    end

    %% Wiring
    LG --> REG & DB
    LG --> MW
    MW --> AB
    AB --> CHK & COA & GL & AP & AR & PO & PAY & TAX & BDG & REP
    MW --> CE & AD & DB
    CHK --> CP --> PV
    AP --> IP --> PV
    AR --> IP --> PV
    PO --> PP --> PV
    PAY --> PYP --> PV
    REP --> DRILL --> GL
    REP --> RP --> PV
    TAX --> VR --> PV
    BDG --> BA --> PV
    GL --> DB
    FC --> DB
```

---

## 4. Database Schema & Migration Architecture (Migrations 1 to 32)

The persistence layer uses a forward-only schema migration pipeline managed in `database.py`:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               DATABASE EVOLUTION TIMELINE                              │
├────────────────────────────────┬───────────────────────────────────────────────────────┤
│ Migrations 1 – 21 (v1.0 – v2.0)│ Core vouchers, multi-currency, floats, approvers, RBAC│
│ Migration 22 (v3.0)            │ checks, bank_check_templates, check_signatories       │
│ Migrations 23 – 24 (v3.5)      │ chart_of_accounts, journal_entries, journal_lines     │
│ Migration 25 (v3.5)            │ suppliers, ap_invoices, ap_invoice_lines, ap_payments │
│ Migration 26 (v3.8)            │ customers, ar_invoices, ar_invoice_lines, ar_receipts │
│ Migration 27 (v4.0)            │ purchase_orders, po_lines, goods_received_notes, GRN   │
│ Migration 28 (v4.0)            │ employees, payroll_runs, payroll_lines, expense_claims │
│ Migration 29 (v4.0)            │ tax_rates, default VAT presets                        │
│ Migration 30 (v4.0)            │ budgets (monthly & annual account allocations)        │
│ Migration 31 (v4.0)            │ cash-flow forecasting scenarios and projections       │
│ Migration 32 (v4.0)            │ accounting period close and reopen controls            │
└────────────────────────────────┴───────────────────────────────────────────────────────┘
```

### 4.1. Core Schema Highlights

#### 1. Chart of Accounts & General Ledger (v3.5)
```sql
CREATE TABLE chart_of_accounts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER NOT NULL DEFAULT 1,
    account_code TEXT    NOT NULL,
    account_name TEXT    NOT NULL,
    account_type TEXT    NOT NULL, -- 'Asset', 'Liability', 'Equity', 'Income', 'Expense'
    parent_id    INTEGER DEFAULT NULL,
    is_system    INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1,
    notes        TEXT    DEFAULT '',
    UNIQUE(company_id, account_code)
);

CREATE TABLE journal_entries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER NOT NULL DEFAULT 1,
    entry_number TEXT    NOT NULL,
    entry_date   TEXT    NOT NULL,
    reference    TEXT    DEFAULT '',
    description  TEXT    NOT NULL,
    is_posted    INTEGER DEFAULT 1,
    source       TEXT    DEFAULT 'Manual' -- 'Manual', 'Voucher', 'AP_Payment', 'AR_Receipt', 'Payroll'
);

CREATE TABLE journal_lines (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id      INTEGER NOT NULL,
    account_id    INTEGER NOT NULL,
    debit_amount  REAL    NOT NULL DEFAULT 0.0,
    credit_amount REAL    NOT NULL DEFAULT 0.0,
    memo          TEXT    DEFAULT '',
    FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
);
```

#### 2. Three-Way Matching: Purchase Orders & Goods Receiving (v4.0)
```sql
CREATE TABLE purchase_orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     INTEGER NOT NULL DEFAULT 1,
    supplier_id    INTEGER NOT NULL,
    po_number      TEXT    NOT NULL,
    order_date     TEXT    NOT NULL,
    subtotal       REAL    NOT NULL DEFAULT 0.0,
    tax_amount     REAL    NOT NULL DEFAULT 0.0,
    total_amount   REAL    NOT NULL DEFAULT 0.0,
    status         TEXT    DEFAULT 'Draft', -- 'Draft', 'Issued', 'Partially Received', 'Fully Received', 'Cancelled'
    UNIQUE(company_id, po_number)
);

CREATE TABLE goods_received_notes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     INTEGER NOT NULL DEFAULT 1,
    po_id          INTEGER NOT NULL,
    grn_number     TEXT    NOT NULL,
    received_date  TEXT    NOT NULL,
    received_by    TEXT    NOT NULL,
    inspection_status TEXT DEFAULT 'Accepted',
    UNIQUE(company_id, grn_number),
    FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
);
```

#### 3. Payroll & Expense Claims (v4.0)
```sql
CREATE TABLE employees (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     INTEGER NOT NULL DEFAULT 1,
    employee_code  TEXT    NOT NULL, -- EMP-0001
    full_name      TEXT    NOT NULL,
    designation    TEXT    DEFAULT '',
    basic_salary   REAL    NOT NULL DEFAULT 0.0,
    bank_account_no TEXT   DEFAULT '',
    is_active      INTEGER DEFAULT 1,
    UNIQUE(company_id, employee_code)
);

CREATE TABLE payroll_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     INTEGER NOT NULL DEFAULT 1,
    period         TEXT    NOT NULL, -- YYYY-MM
    total_gross    REAL    NOT NULL DEFAULT 0.0,
    total_net      REAL    NOT NULL DEFAULT 0.0,
    status         TEXT    DEFAULT 'Draft', -- 'Draft', 'Approved', 'Paid'
    voucher_id     INTEGER DEFAULT NULL
);
```

#### 4. Tax Rates & Statutory VAT Returns (v4.0)
```sql
CREATE TABLE tax_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL DEFAULT 1,
    name        TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    rate        REAL    NOT NULL DEFAULT 0.0,
    tax_type    TEXT    NOT NULL DEFAULT 'VAT',
    is_default  INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1,
    UNIQUE(company_id, code)
);
```

#### 5. Account Budgets & Variance Tracking (v4.0)
```sql
CREATE TABLE budgets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id    INTEGER NOT NULL DEFAULT 1,
    account_id    INTEGER NOT NULL,
    budget_year   INTEGER NOT NULL,
    budget_month  INTEGER NOT NULL DEFAULT 0, -- 1-12 for monthly, 0 for annual
    budget_amount REAL    NOT NULL DEFAULT 0.0,
    actual_amount REAL    DEFAULT 0.0,
    notes         TEXT    DEFAULT '',
    UNIQUE(company_id, account_id, budget_year, budget_month),
    FOREIGN KEY (account_id) REFERENCES chart_of_accounts(id)
);
```

---

## 5. Automated Accounting Logic & Auto-Journaling

### 5.1. Voucher Auto-Journaling Flow
When a payment voucher is created:
1. Voucher line items specify expense categories (e.g. `Rent Expense`, `Refreshments`).
2. The engine looks up the Chart of Accounts ID matching the category.
3. Automatically posts a balanced journal entry:
   - **DEBIT**: Category Expense Account (e.g. `5200 Rent Expense`)
   - **CREDIT**: Payment Source Account (e.g. `1110 Cash in Hand` or `1120 Bank Current Account`)

### 5.2. AP Prompt Payment Discount Balancing
When paying an AP Supplier invoice with an early settlement discount:
- **DEBIT**: `2100 Accounts Payable` (Full Invoice Amount)
- **CREDIT**: `1120 Bank Current Account` (Net Amount Paid)
- **CREDIT**: `4310 Discounts Received` (Discount Amount)
- Mathematical balance is maintained to 2 decimal places.

### 5.3. Three-Way Matching Flow
```
Purchase Order (PO) ──> Goods Received Note (GRN) ──> AP Supplier Invoice
   (Ordered Qty)             (Received Qty)                 (Billed Qty)
```
`create_ap_invoice_from_po` verifies received vs ordered quantities, billing `received_qty` if goods have arrived, linking `po_id` to `ap_invoices` for end-to-end auditability.

---

## 6. Testing Architecture

The codebase enforces strict unit and integration testing via Python's standard `unittest` framework with automated discovery:
- **Test Discovery Command**: `python -m unittest discover -s tests -p "test_*.py"`
- **Total Test Suites**: 33 modules
- **Total Unit & Integration Tests**: **297 tests**
- **Test Run Time**: ~90–120 seconds
- **Pass Rate**: **100% (0 errors, 0 failures)**
