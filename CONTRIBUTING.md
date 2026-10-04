# Contributing to Voucher Manager

Thank you for your interest in contributing to **Voucher Manager**! We welcome contributions from developers, accountants, UI/UX designers, and open-source enthusiasts.

Whether you're fixing a bug, adding a new feature, improving documentation, or optimizing performance, here is how you can get started.

---

## 📋 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md) at all times. Please treat fellow contributors with respect, empathy, and professionalism.

---

## 🛠️ Setting Up Your Local Environment

### 1. Prerequisites
- **Python 3.10+** (Python 3.10, 3.11, 3.12, or 3.13 on Windows)
- **Git**

### 2. Fork & Clone
1. Fork the repository on GitHub by clicking the **Fork** button at the top right of [praneeththilina/voucher](https://github.com/praneeththilina/voucher).
2. Clone your fork locally:
   ```bash
   git clone https://github.com/<your-username>/voucher.git
   cd voucher
   ```

### 3. Virtual Environment Setup
```powershell
# Create a virtual environment
python -m venv venv

# Activate on Windows PowerShell
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Running the App Locally
```powershell
python main.py
```

### 5. Running the Test Suite
Before making changes, verify that the existing test suite passes:
```powershell
python -m unittest discover tests
```

---

## 💡 How to Contribute

### Reporting Bugs
If you find a bug or unexpected behavior:
1. Search the [Issues tab](https://github.com/praneeththilina/voucher/issues) to see if it has already been reported.
2. If not, open a new issue using the **Bug Report** template.
3. Include clear steps to reproduce, expected vs. actual behavior, operating system version, and relevant error tracebacks.

### Suggesting Enhancements
Have an idea for a feature or workflow improvement?
1. Open a new issue using the **Feature Request** template.
2. Describe the problem your feature solves and how it benefits SMEs or daily operations.

### Submitting Pull Requests (PRs)
1. **Create a branch**:
   ```bash
   git checkout -b feature/my-new-feature
   # or
   git checkout -b fix/issue-description
   ```
2. **Make your changes**:
   - Write clean, readable Python code adhering to PEP 8 standards.
   - Preserve backward compatibility with existing SQLite schemas.
   - Keep Tkinter UI responsive (do not run long-running network or disk operations on the main thread).
   - **Never hardcode personal credentials, API keys, or project secrets.** Always use generic mock placeholders in unit tests.
3. **Add or update unit tests**:
   - Add corresponding test cases in the `tests/` directory.
   - Ensure the full test suite runs and passes:
     ```powershell
     python -m unittest discover tests
     ```
4. **Commit your changes**:
   - Write clear, descriptive commit messages:
     ```bash
     git commit -m "feat(ui): add payment method summary card"
     # or
     git commit -m "fix(printer): prevent text clipping in line item table"
     ```
5. **Push and open a PR**:
   ```bash
   git push origin feature/my-new-feature
   ```
   Open a Pull Request on GitHub against the `main` branch. Fill out the PR template completely.

---

## 🏗️ Project Architecture Overview

```text
voucher/
├── app.py                  # Main VoucherApp application class & window management
├── main.py                 # Application entry point
├── database.py             # SQLite database layer (transactions, queries, migrations)
├── printer.py              # ReportLab 2-per-page A4 PDF rendering engine
├── updater.py              # GitHub Releases auto-update engine
├── firebase_client.py      # Google Cloud Firestore NoSQL sync client
├── gdrive_client.py        # Google Drive cloud backup manager
├── build_exe.py            # PyInstaller standalone executable build script
├── ui/
│   ├── main_window.py      # Main window & 4-tab layout (List, Form, Cash Float, Analytics)
│   ├── analytics_dashboard.py # BI analytics, charts, budget vs actuals, category metrics
│   ├── float_manager.py    # Cash Float & Drawer ledger tracking module
│   ├── dialogs.py          # Modal dialogs (About, What's New, Clear Vouchers, Delete, etc.)
│   ├── widgets.py          # Custom Tkinter/ttkbootstrap reusable widgets
│   ├── category_manager.py # Expense category & monthly budget management
│   ├── name_manager.py     # Payee, Approver, and Personnel directory
│   ├── pdf_viewer.py       # High-definition internal PDF viewer (pypdfium2)
│   ├── template_manager.py # Reusable voucher template manager
│   ├── settings_dialog.py  # Header branding, Cloud sync & terminal management
│   ├── payee_statement.py  # Payee account statement generation
│   ├── tag_manager.py      # Voucher tag & label management
│   ├── currency_ui.py      # Multi-Currency & daily FX exchange rate management
│   ├── bank_reconciliation.py # Bank statement import & auto-reconciliation engine
│   ├── user_manager.py     # Role-Based Access Control (Admin/Manager/Clerk/Auditor)
│   ├── approval_dialog.py  # Multi-tier approval workflow & action dialogs
│   ├── recurring_manager.py # Recurring scheduled voucher templates & generation
│   ├── import_wizard.py    # CSV/Excel bulk voucher import wizard
│   └── alert_center.py     # Proactive alerts & system notification drawer
└── tests/                  # Automated unit test suite
```

---

## 🔒 Security Best Practices for Contributors

- **Zero Secret Policy**: Never commit real API keys, credentials JSON files, passwords, or personal contact info.
- Verify `git status` before committing to ensure `data/`, `*.db`, or credential files are not accidentally staged.
- All credential files (`serviceAccountKey*.json`, `credentials.json`, `token.json`) are ignored in `.gitignore`.

---

## 📄 License
By contributing to Voucher Manager, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
