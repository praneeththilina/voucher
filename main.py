"""
SME Voucher Printing Tool
=========================
Entry point for the application.

Usage:
    python main.py

Requirements:
    pip install -r requirements.txt
"""

from app import VoucherApp


def main():
    app = VoucherApp()
    app.run()


if __name__ == "__main__":
    main()
