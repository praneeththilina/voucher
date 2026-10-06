# 🚀 Voucher Manager v4.0.0 — Major SME Financial & Bookkeeping ERP Milestone

A transformational milestone establishing **Voucher Manager** as a complete, self-contained desktop Bookkeeping & Financial ERP platform for Small and Medium Enterprises (SMEs). Building upon our high-performance payment voucher and multi-currency foundation, v4.0.0 delivers millimeter-accurate bank check printing, double-entry General Ledger bookkeeping, complete Accounts Payable & Accounts Receivable management, 3-way matching purchase procurement, monthly staff payroll & payslips, statutory VAT return filing, multi-page financial statements, and account-level budgeting — all 100% offline-first with zero recurring subscription fees.

---

### 🌟 Release Highlights & What's New in v4.0.0

#### 🖋️ 1. Bank Check Printing Engine (v3.0)
- **Millimeter-Accurate Positioning**: ReportLab vector check canvas compliant with international bank clearing standards.
- **Stock Templates for Major Banks**: Pre-configured templates for **Bank of Ceylon (BOC)**, **Commercial Bank of Ceylon**, **Hatton National Bank (HNB)**, and **Sampath Bank**.
- **Visual Drag-and-Drop Designer**: Calibrate coordinate offsets (mm), toggle "A/C PAYEE ONLY" crossing, and preview live test checks.
- **Check Register & Audit Trail**: Track checks through complete lifecycle states (`Draft`, `Printed`, `Issued`, `Cleared`, `Voided`, `Bounced`).
- **Bank Reconciliation Integration**: Reconcile checks directly against imported bank statements.
- **Algorithmic Amount-in-Words**: Automatic English capital words generator with currency and cent subdivisions.

#### 📒 2. Chart of Accounts & General Ledger Double-Entry (v3.5)
- **Standard 5-Group COA Structure**: Pre-seeded standard accounts (`1000–1999 Assets`, `2000–2999 Liabilities`, `3000–3999 Equity`, `4000–4999 Income`, `5000–5999 Expenses`).
- **Balanced Double-Entry Journaling**: Multi-line manual journal wizard enforcing exact mathematical balance ($\sum \text{Debits} = \sum \text{Credits}$).
- **Voucher Auto-Journaling**: Payment vouchers automatically generate double-entry general ledger records matching expense categories to specific accounts.
- **Real-Time Trial Balance**: Instant financial audit balance statement.

#### 🏢 3. Accounts Payable (AP) & Supplier Bills (v3.5)
- **Supplier Master Directory**: Vendor contact details, payment terms, tax registration numbers, and ledger balances.
- **Multi-Line AP Invoices**: Itemized bills with tax rates, line totals, discounts, and payment terms.
- **Prompt Payment Discounts**: Auto-journals early settlement discounts to account `4310 Discounts Received`.
- **AP Aging Analysis**: Interactive aging buckets (**Current, 1–30, 31–60, 61–90, 90+ days**) with exportable reports.
- **Supplier Bill PDF Printing**: High-definition invoice printing with company letterhead.

#### 👥 4. Accounts Receivable (AR) & Customer Invoicing (v3.8)
- **Customer Directory**: Customer profiles, tax registration, credit limits, and outstanding balances.
- **Customer Tax Invoices**: Automatic sequential invoice numbering (`INV-YYYY-XXXX`).
- **Payment Receipts**: Record partial or full payments, issuing numbered receipts with balance updates.
- **AR Aging Analysis**: Accounts receivable aging buckets to track overdue client collections.
- **Customer Tax Invoice & Receipt PDF Generator**: High-definition invoice and receipt printing.

#### 📊 5. Multi-Page Financial Reporting Engine (v3.8)
- **Platypus PDF Engine with `NumberedCanvas`**: Multi-page publication-quality financial reports with running headers and dynamic "Page X of Y" footers.
- **Profit & Loss Statement (Income Statement)**: Revenue, Cost of Goods Sold, Gross Profit, Operating Expenses, and Net Profit.
- **Balance Sheet (Statement of Financial Position)**: Total Assets, Total Liabilities, Equity, and Net Position.
- **Cash Flow Statement**: Operating, Investing, and Financing activities (Indirect method).
- **Interactive 4-Tab GUI Dashboard**: Real-time KPI summary cards, period presets, and 1-click PDF/CSV export.

#### 📦 6. Purchase Orders & Goods Receiving (GRN) (v4.0)
- **Procurement Order Management**: Multi-line vendor purchase orders (`PO-YYYY-XXXX`) with tax and terms.
- **Goods Received Notes (GRN)**: Warehouse receiving inspection slips (`GRN-YYYY-XXXX`) tracking received and rejected quantities.
- **Live Quantity Tracking**: PO lines dynamically track `received_qty` with status transitions (`Draft` → `Issued` → `Partially Received` → `Fully Received`).
- **Automated 3-Way Matching**: Convert approved POs and GRNs directly into Accounts Payable Supplier Invoices with zero manual data re-entry.
- **PO & GRN PDF Generator**: Formal vendor Purchase Orders and Goods Received inspection slips.

#### 👥 7. Basic Payroll & Employee Expense Claims (v4.0)
- **Staff Directory**: Employee records with auto-generated employee codes (`EMP-0001`), designations, NIC, and bank details.
- **Monthly Payroll Wizard**: Interactive batch processing of monthly pay runs (`YYYY-MM`) calculating basic salary, allowances, overtime, gross pay, employee deductions (EPF 8%, PAYE/APIT tax), and net pay.
- **1-Click Payroll Payout Voucher**: Automatically generates payment vouchers under `Salaries & Wages` with General Ledger auto-journaling (Debit Salaries `5110`, Credit Bank `1120` / Cash `1110`).
- **Confidential Payslip PDF**: Individual payslips with side-by-side earnings vs deductions, net pay badge, and bank details.
- **Executive Monthly Payroll Sheet**: Master payroll summary for bank dispatch and director review.
- **Employee Expense Claims**: Staff reimbursement claims (`CLM-YYYY-XXXX`) with itemized receipts and voucher integration.

#### 🏛️ 8. Tax Management & VAT / GST Statutory Returns (v4.0)
- **Configurable Tax Rate Presets**: Pre-seeded with `Standard VAT 18%` (default), `Zero Rated (0%)`, `Exempt (0%)`, and `Withholding Tax 5%`.
- **Official VAT Return Calculation**:
  - **Box 1**: Total Taxable Sales / Supplies (excl. VAT)
  - **Box 2**: Total Output VAT Charged on Sales
  - **Box 3**: Total Taxable Purchases / Inputs (excl. VAT)
  - **Box 4**: Total Input VAT Paid on Purchases
  - **Box 5**: Net VAT Payable to Tax Authority / (Net Tax Credit / Refund Due)
- **Official Statutory VAT Return PDF**: Complete filing statement with Schedule A (Sales), Schedule B (Purchases), and Authorized Taxpayer Declaration block.

#### 🎯 9. Budgets & Advanced Variance Analytics (v4.0)
- **Account-Level Budget Allocations**: Set monthly or annual budgets per Chart of Accounts expense/income ledger.
- **Live Spending Variance Tracking**: Real-time variance comparison against posted General Ledger transactions and vouchers.
- **3-Tier Financial Status Badges**:
  - 🟢 **Within Budget** (< 80% utilization)
  - 🟡 **Warning** (80%–100% utilization ceiling)
  - 🔴 **Exceeded** (> 100% over-budget alert)
- **Annual Spread Wizard**: Distribute an annual budget equally across 12 calendar months with 1 click.
- **Budget Variance PDF Statement**: Executive report with KPI cards, account breakdown, and dual sign-off blocks.

#### ⚡ 10. Compact Action Bar with MenuActionProxy
- Replaces 4 cluttered rows with a sleek single-row action bar featuring dropdown menus (`⚡ Voucher Actions`, `📒 Accounting`, `💼 AP & AR`, `📁 Operations`).
- `MenuActionProxy` ensures 100% RBAC permission enforcement, keyboard accelerators, and test compatibility.

---

### 🧪 Quality Assurance & Test Verification
- **Total Test Suites**: 33 test modules
- **Total Unit & Integration Tests**: **248 tests**
- **Test Pass Rate**: **100% (0 errors, 0 failures)**

---

### 📦 Upgrading to v4.0.0
- **Existing Users**: Upgrading to v4.0.0 is 100% non-destructive. Existing `data/vouchers.db` files are automatically migrated across all 30 schema versions on first launch with automatic backups.
- **No Data Reset**: All historical vouchers, categories, vendors, and cash floats are fully preserved and mapped to the new accounting architecture.
