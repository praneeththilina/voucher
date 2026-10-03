# 📋 Voucher Manager v1.4.0

A major release delivering instantaneous tab transitions, embedded Cash Float & Drawer management directly in the main window, live Firebase Cloud synchronization for cash top-ups and drawer movements, and high-definition landscape branding.

---

### ✨ What's New in v1.4.0

- 💰 **Embedded Money Float Tab (`Ctrl+3`)**:
  - The complete Cash Float & Drawer Manager is now embedded directly in the main screen as **Tab 3** with quick keyboard navigation (`Ctrl+3`).
  - Pinned action button bars on cash top-up and adjustment popups ensure command buttons are always immediately visible without manual window expansion.
  - Seamless petty cash fund reimbursement workflow: 1-click settlement of spent vouchers against cash drawer balances.

- ⚡ **Zero-Lag Instantaneous Tab Transitions**:
  - Eliminated UI thread latency across all tabs through lazy dirty-state float ledger refreshes.
  - Company logo LANCZOS sub-pixel resampling is cached in memory, preventing repeated CPU image decoding on tab updates.
  - Form canvas geometry calculations are debounced with a 35ms timer to prevent widget layout cascades.
  - All tab geometries are pre-warmed once at startup for silky-smooth 60 FPS tab switching.

- ☁️ **Firebase Cloud Top-Up & Float Sync**:
  - Cash top-ups, reimbursements, cash transactions, and running balances sync live to Google Firebase Firestore in real-time.
  - Fixed background progress reporting so cloud syncing runs cleanly without worker exceptions.

- 🏢 **High-Resolution Corporate Header Logo**:
  - Expanded header logo display dimensions from 36x30 to 170x44 for crystal-clear landscape branding that matches printed voucher quality.

- 💾 **Google Drive Cloud Storage**:
  - 15 GB free cloud backup integration for vouchers database and attachments with automated pre-update safety backups.

- 🔌 **Firebase Web App REST API Connection**:
  - Connect with ease using Firebase Web App configuration (API Key + Project ID) with zero credit card requirements.

- 🔄 **Automated In-App Updates**:
  - Non-blocking background version checks with 1-click automated self-updating delivery.

---

### 📦 Installation & Auto-Update
- **Direct Download**: Download `VoucherManager.exe` below. It is completely portable and requires no installation.
- **Auto-Updater**: If you are running an existing version, simply click **Help -> Check for Updates** or accept the automatic update prompt.
