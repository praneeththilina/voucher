# 📋 Voucher Manager — SME Payment Voucher & Financial Platform

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](https://github.com/praneeththilina/voucher/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Database](https://img.shields.io/badge/database-SQLite%20Offline--First-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Cloud Sync](https://img.shields.io/badge/cloud-Google%20Firebase%20NoSQL-FFCA28.svg?logo=firebase&logoColor=black)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **A fast, elegant, enterprise-grade desktop financial platform** designed for businesses to issue payment vouchers, manage multi-currency rates, reconcile bank statements, enforce role-based permissions (RBAC), print paper-saving A4 slips, track petty cash float drawers in real-time, and synchronize live across multiple terminals via Google Cloud Firestore — with zero monthly subscriptions.

---

## 🧭 Visual System Architecture

```text
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                   VOUCHER MANAGER DESKTOP v2.0                              │
 │                                                                                             │
 │ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐ ┌───────────────────────┐ │
 │ │Tab 1: Voucher List│ │ Tab 2: Entry Form │ │Tab 3: Cash Float  │ │ Tab 4: Analytics Dash │ │
 │ │     (Ctrl+1)      │ │     (Ctrl+2)      │ │     (Ctrl+3)      │ │       (Ctrl+4)        │ │
 │ │                   │ │                   │ │                   │ │                       │ │
 │ │• Live Search/Sort │ │• Multi-Currency   │ │• Petty Cash Drawers│• Monthly Spend Trends  │ │
 │ │• Due Date Tracking│ │• Live Forex Rates │ │• Top-Ups & Inflows│ │• Category Breakdown   │ │
 │ │• Multi-Select Act.│ │• Approval Badges  │ │• Reimbursements   │ │• Payee Leaderboard    │ │
 │ │• Batch Print/CSV  │ │• Paper-Saving PDF │ │• Running Balances │ │• Due Date Aging Rep.  │ │
 │ └─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘ └───────────┬───────────┘ │
 │           │                     │                     │                       │             │
 └───────────┼─────────────────────┼─────────────────────┼───────────────────────┼─────────────┘
             ▼                     ▼                     ▼                       ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │                         ENTERPRISE V2 MODULES & PERMISSION GUARDS                           │
 │ • User Management & PBKDF2 RBAC • Bank Statement Reconciliation • Alert Notification Center │
 │ • PIN Approval Authorization   • Recurring Auto-Schedules       • Bulk CSV Import Wizard    │
 └─────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │                        LOCAL SQLITE ENGINE (Offline-First, Zero Lag)                        │
 │ • Instant sub-millisecond responses  • Data resides in local data/vouchers.db               │
 └─────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                           │ (Non-blocking background thread)
                                           ▼
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │                      GOOGLE CLOUD FIRESTORE / GOOGLE DRIVE (Multi-Terminal)                 │
 │ • Multi-User Real-Time Sync (Vouchers, Floats, Users, Approvers) • 100% Free Spark Tier    │
 └─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Highlight Features

### 💱 1. Multi-Currency Engine & Live Background Forex Rates
- **Global Currency Support**: Create vouchers in **USD, EUR, GBP, AED, INR, JPY, CNY, AUD, SGD** with automatic conversion to base currency (**LKR**).
- **Background Daily Forex Fetch**: Direct connection to **ExchangeRate-API Open Access** (`open.er-api.com`) with zero API key or credit card requirements. Historical rates stored daily in database.
- **Custom World Currencies**: Add and track custom currencies with custom ISO codes, symbols, and decimal precision.

### 🏦 2. Bank Statement Reconciliation & Auto-Matching
- **CSV Statement Ingestion**: Import commercial bank statements and match records against payment vouchers.
- **Intelligent Fuzzy Matching**: Configurable variance tolerances and date window thresholds.
- **Multi-Account Tracking**: Reconcile multiple bank accounts with side-by-side transaction validation.

### 👥 3. User Management & Role-Based Access Control (RBAC)
- **5 Tiered Roles**: **Viewer**, **Data Entry**, **Cashier**, **Manager**, and **Admin**.
- **Dynamic UI Enforcement**: Unauthorized command buttons, menus, and shortcuts are dynamically disabled.
- **Secure PIN Encryption**: Salted PBKDF2 with SHA-256 and 100,000 iterations for bulletproof credential security.
- **Quick Shift Change**: Switch users instantly via `Ctrl+Shift+L` or header status badge.

### ☁️ 4. Multi-Terminal Google Cloud Firestore Sync
- **True Multi-User Operation**: Synchronizes vouchers, money floats, top-ups, users, and approvers across multiple office PCs.
- **Offline-First Resilience**: Work completely offline with zero latency; automatically pushes and pulls updates when internet is restored.
- **100% Free Forever**: Fully compatible with Google Cloud Firestore's Spark Free Tier.

### 🛡️ 5. Approval Workflows & PIN Authorization
- **Managerial Authorization**: Restrict voucher settlement above custom company thresholds until authorized.
- **2-Tier Approver Profiles**: Distinct limits for Level 1 and Level 2 approvers with status audit trails.

### 📅 6. Automated Recurring Vouchers & Due Date Engine
- **Flexible Scheduling**: Set up recurring expenses (**Daily, Weekly, Monthly, Quarterly, Yearly**).
- **Startup Auto-Generation**: Automatically generates due vouchers on application launch with toast notifications.

### 🔔 7. Smart Alert & Notification Center
- Proactive alerts for overdue payments, low cash float balances, pending approvals, and upcoming recurring bills.

### 📊 8. Visual Analytics & Spending Dashboard (Tab 4)
- **Interactive Visual Reporting**: 12-month spending trends, categorical breakdown progress bars, top vendor leaderboards, and due date aging buckets.
- **Zero-Ghosting Smooth Scrolling**: Immediate idle paint invalidation and responsive auto-stretch architecture eliminating tearing and lag on Windows.

### 💰 9. Petty Cash Float & Fund Reimbursement
- **Multi-Drawer Tracking**: Manage multiple floats (e.g. *Front Office Register*, *Main Petty Cash*, *Warehouse Float*).
- **Live Header Badge**: Persistent top bar widget displays current balance with visual warning colors.
- **1-Click Fund Reimbursement**: Settle spent vouchers in bulk to replenish drawer balances with audit trails.

### 🖨️ 10. Print-Ready 2-per-Page A4 PDF Layout
- **Saves 50% Paper**: Renders two complete half-page vouchers on standard A4 paper with transparent logo blending.
- **Built-in PDF Viewer**: Powered by `pypdfium2` — inspect, zoom, navigate, or print without external viewer software.

---

## 🚀 Download & Instant Setup

### 📦 Windows Portable Release (Recommended)
1. Navigate to [**Latest Releases**](https://github.com/praneeththilina/voucher/releases/latest) and download `VoucherManager-windows.zip`.
2. Extract the archive to any convenient directory on your PC (e.g. `C:\Tools\VoucherManager` or a portable USB drive).
3. Double-click `VoucherManager.exe` to launch immediately!

> [!TIP]
> **Sub-Second Instant Startup (< 0.5s)**: Voucher Manager uses an optimized folder bundle architecture with pre-extracted dependencies in `_internal/`. Unlike standard single-file executables, it never writes or unpacks dozens of megabytes into `AppData\Local\Temp` on launch, delivering lightning-fast startup and smooth shutdown.
>
> **100% Data Preservation**: All financial data, vouchers, categories, and receipt attachments reside exclusively in `data/vouchers.db` adjacent to the executable. Your data is never touched or overwritten when updating the application.

---

### 💻 Running from Source Code (Developers)
```powershell
# 1. Clone the repository
git clone https://github.com/praneeththilina/voucher.git
cd voucher

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# 3. Install all required dependencies
pip install -r requirements.txt

# 4. Run application
python main.py

# 5. Compile high-performance distribution bundle
python build_exe.py
```

---

## ⌨️ Complete Keyboard Shortcut Guide

Power users can navigate 100% of daily operations without ever touching the mouse:

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
| | `Ctrl+P` | Print selected voucher(s) from list or form |
| | `Ctrl+Shift+P` | Batch print all unprinted active vouchers |
| | `Ctrl+E` | Edit highlighted voucher in form |
| | `Ctrl+D` | Duplicate highlighted voucher into a new draft |
| | `Ctrl+W` | Clear form inputs |
| | `Alt+A` | Add a new line item row |
| | `Del` | Cancel (disable) selected voucher |
| | `Shift+Del` | Permanently delete cancelled voucher (Admin password protected) |
| **Management Modules** | `Ctrl+F` | Focus Search Box in voucher list |
| | `Ctrl+K` | Quick-switch or select active company profile |
| | `Ctrl+G` | Open Category & Monthly Budget Manager |
| | `Ctrl+M` | Open Payee & Personnel Directory Manager |
| | `Ctrl+T` | Open Reusable Voucher Template Manager |
| | `Ctrl+Shift+T` | Open Voucher Tag & Label Manager |
| | `Ctrl+Shift+S` | Open Payee Statement & Vendor Ledger Generator |
| | `Ctrl+I` | Open Expense Analytics & Visual Charts |
| | `Ctrl+,` | Open Header Settings & Firebase Cloud Sync Configuration |
| | `F5` | Force refresh active list view |
| | `F1` | Open About Dialog & "What's New" release notes |

---

## 🚀 Quick Start Guide

### Option A: Portable Standalone Executable (Recommended for Non-Developers)
No Python, Git, or dependencies required!

1. Head to the **[Latest Release](https://github.com/praneeththilina/voucher/releases/latest)** page.
2. Download `VoucherManager.exe`.
3. Place `VoucherManager.exe` into any folder (e.g. `C:\VoucherManager\`) or a USB flash drive.
4. Double-click to run! On first launch, it will automatically create a local `data/` directory to store your SQLite database and attachments securely.

> [!TIP]
> **Built-in Self Updater**: Whenever a new update is released on GitHub, the app notifies you automatically on launch. Clicking **Update** downloads and replaces the executable seamlessly with 1 click.

---

### Option B: Running from Source Code (Developers)

#### 1. Clone & Set Up Virtual Environment
```powershell
# Clone the repository
git clone https://github.com/praneeththilina/voucher.git
cd voucher

# Create a clean virtual environment
python -m venv venv

# Activate on Windows PowerShell
.\venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt
```

#### 2. Run the Application
```powershell
python main.py
```

#### 3. Compile Standalone `.exe` with PyInstaller
```powershell
python build_exe.py
```
The compiled single-file binary will be generated at `dist/VoucherManager.exe`.

---

## 📖 Practical User Workflows

### 📝 Workflow 1: Creating & Printing Your First Voucher in 30 Seconds

1. Press `Ctrl+2` (or `Ctrl+N`) to open the voucher form.
2. The voucher number is generated automatically (e.g., `26OCT_01`).
3. **Date**: Defaults to today. Click the arrow button to shift forward or choose a due date.
4. **Paid To**: Type payee name (e.g., `Keells Super`). Type `@` to select from existing saved vendors.
5. **Cash Given By** & **Spent By**: Enter the person releasing the cash and the person making the purchase.
6. **Line Items**:
   - Type description (e.g., `Office Coffee & Tea Supplies`).
   - Press `Tab` and pick an expense category (e.g., `Refreshments`).
   - Press `Tab` and enter the amount (e.g., `2500`).
   - Press `Enter` to automatically add a new line item if needed.
7. **Select Float**: Choose which drawer the cash came from (e.g., `Main Cash Float`).
8. Press `Ctrl+Enter` to **Save & Print**. The high-definition PDF preview opens instantly!

---

### 💵 Workflow 2: Managing Petty Cash Floats & Fund Reimbursements

```text
 ┌──────────────────────┐      Cash Spent      ┌──────────────────────┐
 │   Petty Cash Float   │ ───────────────────> │   Voucher Created    │
 │ (Bal: LKR 25,000.00) │                      │ (Pending Reimbursed) │
 └──────────┬───────────┘                      └──────────┬───────────┘
            │                                             │
            │           Reimbursement Claim Settled       │
            └─────────────────────────────────────────────┘
                     Float Restored to Full Value
```

1. Press `Ctrl+3` to switch to **Tab 3: Cash Float & Drawers**.
2. **Top-Up Float**: Click `➕ Top-Up Float` to deposit cash into the drawer. Select date, enter amount, custodian name, and click Save.
3. **Spending**: As vouchers are created on Tab 2 with this float selected, drawer outflows deduct automatically in real-time.
4. **Fund Reimbursement**:
   - When the drawer runs low, click `🔄 Fund Reimbursement`.
   - The dialog lists all active unreimbursed vouchers linked to this float.
   - Select the vouchers being claimed for replenishment.
   - Enter the reimbursement check/cash reference and save.
   - The drawer balance is restored by the exact total, and all vouchers are stamped as `Reimbursed` in the ledger.

---

### 🔥 Workflow 3: Setting Up Free Google Firebase Cloud Sync

You can sync your vouchers and cash top-ups across multiple computers or backup your data in real-time using Google's free Firestore database:

> [!NOTE]
> **100% Free Forever**: Google Firebase's Spark Tier gives you 1 GB of storage, 50,000 document reads, and 20,000 writes every day for free with no credit card required.

1. **Create Free Project**:
   - Visit the [Firebase Console](https://console.firebase.google.com/).
   - Click **Add project** (e.g. `MyBusiness-Vouchers`). Disable Google Analytics (not needed) and click **Create Project**.
2. **Enable Firestore Database**:
   - In the left sidebar, navigate to **Build** > **Firestore Database**.
   - Click **Create database**.
   - Choose a nearby region (e.g., `asia-south1` or `us-central1`), select **Start in production mode**, and click **Create**.
3. **Generate Service Account Private Key**:
   - Click the gear icon ⚙️ next to *Project Overview* > **Project settings**.
   - Select the **Service accounts** tab.
   - Click **Generate new private key** > **Generate key**.
   - A `.json` credential file will be downloaded to your computer.
4. **Link Key in Voucher Manager**:
   - Open Voucher Manager, press `Ctrl+,` (Settings).
   - Go to the **☁️ Firebase Cloud Database** tab.
   - Click **📂 Browse Key File...** and select the downloaded `.json` file.
   - Click **⚡ Test Connection**. You will see: `Connection successful! Firestore read/write verified.`
   - Check the **Enable Firebase Cloud Sync** checkbox and click **Save Settings**.
5. **Sync**:
   - All new vouchers, cash top-ups, reimbursements, and float adjustments will now push directly to Firebase in the background!
   - Use the **⬆️ Push All Local Vouchers to Cloud** button to back up historical records in one click.

---

### 📁 Workflow 4: Setting Up 15 GB Free Google Drive Backups

1. Open **Settings (`Ctrl+,`)** > **💾 Google Drive Backup** tab.
2. Select your Google Drive credentials (`credentials.json`).
3. Click **Connect Google Drive**. A browser window opens prompting you to authenticate your Google Account.
4. Choose an automated backup interval (e.g., *Daily at App Close* or *Manual 1-Click Backup*).
5. Your SQLite database (`vouchers.db`) and receipt attachments are securely zipped and timestamped in a dedicated Google Drive folder.

---

## 🏢 Dual Company Profile Management

Manage two completely independent business entities within the same application:

```text
 ┌────────────────────────────────────────────────────────┐
 │            ACTIVE COMPANY HEADER SWITCHER              │
 │                                                        │
 │   [🏢 ACME Industrial Ltd]      [🔄 Switch to (Ctrl+K)]│
 └───────────────────────────┬────────────────────────────┘
                             │ Toggle
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │   [🏢 Apex Trading Co]          [🔄 Switch to (Ctrl+K)]│
 └────────────────────────────────────────────────────────┘
```

- **Dynamic Multi-Company Support**: Manage 2, 5, 20, or any number of distinct company entities seamlessly.
- **Header Switcher**: Click `🔄 Switch Company ▾` to open the quick-switcher menu, switch active profile, or add a new profile on the fly.
- **Keyboard Convenience**: Press `Ctrl+K` to instantly toggle when you have 2 companies, or open the quick-switcher dropdown menu when managing 3 or more companies.
- **Automated Provisioning**: Every new company automatically receives its own isolated `Main Cash Float`, voucher sequence, and branding logo.
- Each profile maintains its own:
  - Corporate logo, address, phone numbers, and email headers.
  - Numbering series and sequence counters.
  - Separate money float drawers and petty cash ledgers.
  - Independent monthly expense budgets.

---

## 🔒 Security & Data Integrity

- **Offline-First Security**: Your financial data is saved locally on your computer inside `data/vouchers.db` using ACID-compliant SQLite transactions.
- **Administrative Protection**: Permanent deletion of disabled vouchers and the *Clear All Records* utility require password authorization (Default administrative password: `Praneeth1991`).
- **Timing-Attack Resistance**: Password comparisons use Python's `hmac.compare_digest` to prevent timing inspection attacks.
- **Path Traversal Sanitization**: All file attachment imports are sanitized to prevent directory traversal vulnerabilities.

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><b>1. Where is my database and receipt files stored?</b></summary>
All files are saved in the <code>data/</code> folder located in the same directory as the executable:
<ul>
  <li><code>data/vouchers.db</code>: SQLite database containing all records, categories, vendors, and floats.</li>
  <li><code>data/attachments/</code>: Stored receipt photographs, PDFs, and invoices.</li>
</ul>
To back up your system manually, simply copy the <code>data/</code> folder to an external drive.
</details>

<details>
<summary><b>2. Why does the printout show 2 vouchers per page?</b></summary>
Standard office printers use A4 paper. Printing 1 small voucher per page wastes 70% of the sheet. Voucher Manager formats vouchers side-by-side (2-per-page portrait) so you can slice the sheet in half, saving 50% on paper costs.
</details>

<details>
<summary><b>3. How do I change the default voucher number format?</b></summary>
Press <code>Ctrl+,</code> to open <b>Settings</b>. In the <b>Voucher Numbering</b> section, choose:
<ul>
  <li><b>Monthly Format (YYMMM_NN)</b>: e.g. <code>26OCT_01</code> (resets every month).</li>
  <li><b>Daily Format (V-YYYYMMDD-001)</b>: resets each morning.</li>
  <li><b>Custom Sequential Prefix</b>: e.g. <code>PV-0001</code>.</li>
</ul>
</details>

<details>
<summary><b>4. Can multiple staff members use the app simultaneously?</b></summary>
Yes! By connecting the same <b>Firebase Cloud Project</b> to multiple machines, each computer works locally with zero lag and streams records to the cloud. You can pull cloud changes across desks with the <b>Download from Cloud</b> feature.
</details>

---

## 👨‍💻 Author & Maintainer

- **Developer**: Praneeth Thilina
- **GitHub**: [@praneeththilina](https://github.com/praneeththilina)
- **Repository**: [https://github.com/praneeththilina/voucher](https://github.com/praneeththilina/voucher)

---

## 📄 License

This project is licensed under the **MIT License** — feel free to use, customize, and deploy it for your personal or commercial business needs.
