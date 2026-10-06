# Security Policy

## Supported Versions

We actively provide security patches and updates for the following versions of Voucher Manager:

| Version | Supported          |
| :---    | :---               |
| 4.0.x   | :white_check_mark: |
| 3.x     | :white_check_mark: |
| 2.0.x   | :white_check_mark: |
| 1.4.x   | :white_check_mark: |
| 1.3.x   | :x:                |
| < 1.3   | :x:                |

We strongly encourage all users to run the latest released version via the in-app automatic updater or by downloading the latest release from the [Releases page](https://github.com/praneeththilina/voucher/releases/latest).

---

## Reporting a Vulnerability

The Voucher Manager project takes security seriously. If you discover a potential security vulnerability, please disclose it responsibly.

### How to Report Privately

Please **DO NOT** report security vulnerabilities through public GitHub issues, discussions, or pull requests.

Instead, please submit a report privately using GitHub's **Private Vulnerability Reporting**:
1. Go to the repository's [Security Tab](https://github.com/praneeththilina/voucher/security).
2. Click on **Advisories** in the left sidebar.
3. Click the **Report a vulnerability** button.
4. Fill in the details of the vulnerability, including:
   - A description of the issue.
   - Clear steps to reproduce or a proof of concept.
   - The potential impact on users or systems.
   - Any suggested mitigations or patches.

### Response Timeline
- We will acknowledge receipt of your vulnerability report within **48 hours**.
- We will verify and assess the vulnerability and keep you updated throughout the investigation.
- Once a fix is verified, a patch will be released, and credit will be given in the release notes (unless you request anonymity).

---

## Security Best Practices for Users & Administrators

1. **Protect Administrative Passwords**:
   - The default administrator password for purging vouchers and clearing database records should be customized for production environments.
2. **Restrict Cloud API Keys**:
   - If using Google Firebase Cloud sync, always restrict your API keys in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) strictly to the **Cloud Firestore API**.
3. **Database & File Backups**:
   - Regularly backup your local `data/` folder or enable the integrated **Google Drive Automated Backup** to protect against hardware failure.
4. **Never Commit Secrets**:
   - Never share your `serviceAccountKey*.json` or private credentials publicly. Keep all credential files protected by `.gitignore`.
