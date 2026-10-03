# 📋 Voucher Manager — SME Payment Voucher & Petty Cash Tool

[![Version](https://img.shields.io/badge/version-1.4.0-blue.svg)](https://github.com/praneeththilina/voucher/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-0078D6.svg?logo=windows&logoColor=white)](https://microsoft.com/windows)
[![Database](https://img.shields.io/badge/database-SQLite%20Offline--First-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Cloud Sync](https://img.shields.io/badge/cloud-Google%20Firebase%20NoSQL-FFCA28.svg?logo=firebase&logoColor=black)](https://firebase.google.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **A fast, elegant, and accountant-friendly desktop application** designed for small-to-medium businesses (SMEs) to create payment vouchers, print 2-per-page A4 slips, track petty cash float drawers in real-time, and sync live to Google Firebase Cloud — with zero monthly subscriptions.

---

## 🧭 Visual System Architecture

```text
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                         VOUCHER MANAGER DESKTOP                             │
 │                                                                             │
 │  ┌───────────────────────┐  ┌───────────────────────┐  ┌─────────────────┐  │
 │  │  Tab 1: Voucher List  │  │   Tab 2: Entry Form   │  │   Tab 3: Float  │  │
 │  │       (Ctrl+1)        │  │       (Ctrl+2)        │  │     (Ctrl+3)    │  │
 │  │                       │  │                       │  │                 │  │
 │  │ • Live Search / Filter│  │ • Dynamic Monthly No. │  │ • Petty Cash    │  │
 │  │ • Due Date Reminders  │  │ • @ Autocomplete      │  │ • Top-Ups       │  │
 │  │ • Multi-Select Batch  │  │ • Auto Math Sums      │  │ • Reimbursements│  │
 │  │ • Multi-Tab CSV Export│  │ • Paper-Saving Slips  │  │ • Running Bal.  │  │
 │  └──────────┬────────────┘  └──────────┬────────────┘  └────────┬────────┘  │
 │             │                          │                        │           │
 └─────────────┼──────────────────────────┼────────────────────────┼───────────┘
               ▼                          ▼                        ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                LOCAL SQLITE ENGINE (Offline-First, Zero Lag)                │
 │  • Instant sub-millisecond responses  • Data resides in data/vouchers.db   │
 └───────────────────────┬─────────────────────────────────────────────────────┘
                         │ (Non-blocking background thread)
                         ▼
 ┌─────────────────────────────────────────────────────────────────────────────┐
 │                  GOOGLE CLOUD FIRESTORE / GOOGLE DRIVE                      │
 │  • Real-time NoSQL Sync • 15 GB Free Backups • 100% Free Spark Tier         │
 └─────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Highlight Features

### ⚡ 1. Zero-Lag 3-Tab Desktop Workflow
- **Tab 1: Voucher List (`Ctrl+1`)**: Instant search by voucher number, payee, or description. Filter by date ranges, bill status, payment methods, or due dates. Includes full audit trail logs and multi-select actions.
- **Tab 2: Smart Voucher Entry Form (`Ctrl+2` / `Ctrl+N`)**: Blazingly fast keyboard-driven data entry. Auto-calculates totals, supports `@` autocompletion for payees and categories, and dynamically renumbers vouchers as dates change.
- **Tab 3: Cash Float & Drawer Manager (`Ctrl+3`)**: Embedded directly in the main screen. Track petty cash opening balances, cash top-ups, daily expenses, and settlement reimbursements with a live running balance ledger.

### 💰 2. Petty Cash Float & Fund Reimbursement
- **Multi-Drawer Tracking**: Manage multiple floats (e.g. *Front Office Register*, *Main Petty Cash*, *Warehouse Float*).
- **Live Header Badge**: Persistent top bar widget displays the current balance in real-time, flashing orange/red warnings if an account becomes overdrawn.
- **1-Click Fund Reimbursement**: Settle spent vouchers in bulk to replenish the drawer. The system automatically shifts vouchers from *Pending* to *Reimbursed* with an unalterable audit log.
- **Reverse-Chronological Ledger**: Latest transactions stay at the top. Sort by any column (Date, Ref, Custodian, Inflow, Outflow, Balance) with clickable headers.

### 🖨️ 3. Print-Ready 2-per-Page A4 PDF Layout
- **Saves 50% Paper**: Intelligently renders exactly two complete half-page vouchers on standard A4 paper.
- **Built-in High-Definition PDF Viewer**: Powered by `pypdfium2` — inspect generated documents, zoom, jump pages, or launch in Adobe Acrobat directly inside the app.
- **Smart Attachment Packing**: Attaches receipts, bill photos, or PDFs. Automatically mosaics small bill slips onto shared pages to avoid wasting blank paper.
- **Crisp Corporate Branding**: Automatically converts transparent PNG logos with alpha composite blending to avoid black box artifacts.

### ☁️ 4. Google Firebase NoSQL Cloud Sync (100% Free Forever)
- **Spark Plan Compatible**: Leverages Google Cloud Firestore's free tier (1 GiB storage, 50,000 reads/day, 20,000 writes/day) — no credit card or monthly bills required.
- **Dual Connection Modes**: Connect via standard `serviceAccountKey.json` or simple Firebase Web App configuration (API Key + Project ID).
- **Offline-First Resilience**: Work completely offline with zero latency. When internet is restored, changes push to the cloud in background threads without freezing the user interface.

### 📊 5. Accountant-Grade CSV Export Engine
- Generates a multi-section financial workbook containing:
  1. **Metadata Header**: Company profile, active float, exported date, and date filter range.
  2. **Executive KPI Card**: Total transactions, period inflows, period outflows, and net cash balance.
  3. **Detailed Transaction Register**: Date, reference, description, handed by, spent by, inflow, outflow, and running balance.
  4. **Categorical Breakdown**: Subtotals summarized by expense category and payment method.

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
| | `Esc` | Return to Voucher List / Dismiss any active dialog |
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
| | `Ctrl+K` | Toggle active company profile (Company 1 ⇄ Company 2) |
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

- Press `Ctrl+K` at any moment to flip between **Company 1** and **Company 2**.
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
