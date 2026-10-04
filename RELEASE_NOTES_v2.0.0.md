# 🚀 Voucher Manager v2.0.0 — Major Enterprise Milestone

A milestone update transforming **Voucher Manager** into an enterprise-grade multi-currency financial management platform with live background exchange rate updates, bank statement reconciliation, multi-tier user role permissions (RBAC), real-time multi-terminal Google Cloud Firestore synchronization, approval workflows, automated recurring payments, proactive alerts, visual analytics reporting, and zero-ghosting smooth rendering.

---

### ✨ What's New in v2.0.0

- 💱 **Multi-Currency Engine & Live Exchange Rates**:
  - Native multi-currency support on payment vouchers across 9 major world currencies: **USD, EUR, GBP, AED, INR, JPY, CNY, AUD, SGD** with automatic conversion to company base currency (**LKR**).
  - Background live exchange rates integration with **ExchangeRate-API Open Access** (`open.er-api.com`), requiring no API keys or credit cards.
  - Historical exchange rate storage and daily database caching for complete financial audit integrity.
  - **Custom World Currencies**: Add and manage custom world currencies with custom 3-letter ISO codes, symbols, and decimal precision.

- 🏦 **Bank Statement Reconciliation & Auto-Matching**:
  - Import external bank statements via CSV and automatically match them against recorded payment vouchers.
  - Configurable variance tolerance and date thresholds for fuzzy matching.
  - Multi-account management: register multiple commercial bank accounts and track reconciled vs. unreconciled balances.
  - Direct 1-click batch reconciliation with automatic audit trail entries.

- 👥 **User Management & Role-Based Access Control (RBAC)**:
  - 5-tier role permission hierarchy:
    - **Viewer**: Read-only access to vouchers and financial reports.
    - **Data Entry**: Create, edit, and duplicate payment vouchers.
    - **Cashier**: Print vouchers, manage cash floats, top-ups, and templates.
    - **Manager**: Authorize/reject vouchers, cancel, export, and manage categories/tags.
    - **Admin**: Full unrestricted system access, user management, and cloud configurations.
  - Salted PBKDF2 (SHA-256 with 100,000 iterations) secure PIN authentication.
  - Quick **Switch User / Shift Change** dialog accessible anytime via `Ctrl+Shift+L` or header badge.
  - Admin-only protected User Management dialog with master password fallback.

- ☁️ **Full Multi-User / Multi-Terminal Firebase Cloud Sync**:
  - Complete synchronization of `users`, `approvers`, `vouchers` (including V2 multi-currency fields), `money_floats`, and `float_topups` to Google Cloud Firestore NoSQL.
  - Multi-workstation real-time collaboration with non-blocking background synchronization on startup.
  - Cloud pull and upload actions accessible directly from the header status bar and User Manager dialog.

- 🛡️ **Voucher Approval Workflows & Multi-Tier Authorization**:
  - PIN-protected multi-level authorization for payment vouchers exceeding company approval thresholds.
  - Visual status badges (**Pending Approval**, **Approved**, **Rejected**) with approval timestamps and comments.
  - Independent approver profile management with distinct approval level limits (Level 1 & Level 2).

- 📅 **Automated Recurring Voucher Schedules**:
  - Configure automated recurring payments with flexible intervals: **Daily, Weekly, Monthly, Quarterly, Yearly**.
  - Automatic due-date detection and background voucher creation on application launch.
  - Notification toast alerting how many recurring vouchers were auto-generated.

- 🔔 **Smart Alert & Notification Center**:
  - Centralized notification panel alerting users of:
    - **Overdue Vouchers** past their payment due date.
    - **Low Cash Float Balances** approaching minimum thresholds.
    - **Pending Approvals** awaiting managerial authorization.
    - **Upcoming Recurring Payments** due within 7 days.
  - Direct 1-click actions: Mark read, dismiss, or navigate to corresponding vouchers.

- 📊 **Visual Analytics & Spending Dashboard (Tab 4)**:
  - At-a-glance financial insights with responsive native charts:
    - **Monthly Spending Trend** (12-month historical bar chart).
    - **Expense Breakdown by Category** (horizontal percentage distribution).
    - **Top Payees Leaderboard** (spending ranking by vendor).
    - **Due Date Aging Report** (Overdue, Due Today, Due This Week, Due This Month, Future).
    - **Payment Method Distribution** (Cash, Cheque, Bank Transfer, Online).
  - Executive CSV Export: 1-click comprehensive financial workbook export.

- ⚡ **Zero-Ghosting Smooth Scrolling & UI Responsiveness**:
  - Complete re-engineering of canvas scrolling on Windows GDI: immediate idle paint invalidation eliminating visual smearing, duplicate bars, and ghost trailing text.
  - Dynamic viewport auto-stretch maintaining perfect alignment across maximized and high-DPI displays.
  - Universal recursive mousewheel binding ensuring smooth scrolling over any widget, card, or label.
  - Pop-in and flicker elimination across all modal dialogs using pre-render withdrawal and post-center revelation.

- 📥 **Bulk CSV Import Wizard**:
  - 4-step guided import wizard for migrating payment records from legacy accounting software or spreadsheets.
  - Interactive visual column mapping with automatic header detection and pre-import data preview.

---

### 📦 Installation & Upgrade
- **Portable Binary**: Download `VoucherManager.exe` below. It is fully portable with zero external runtime requirements.
- **In-App Auto-Update**: Existing installations will automatically detect the v2.0.0 update via **Help -> Check for Updates**.
- **Database Safety**: Existing v1.x databases are automatically and non-destructively migrated to the v2.0 schema on first launch.
