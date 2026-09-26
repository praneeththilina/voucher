"""
Build Script: Compile Voucher Manager into a Standalone Windows Executable (.exe)
================================================================================
Bundles all Python dependencies, ttkbootstrap assets, ReportLab fonts, 
pypdfium2 native DLLs, and GUI into a single portable 'VoucherManager.exe'.

Usage:
    .\\venv\\Scripts\\python.exe build_exe.py
"""

import sys
import os
import subprocess
import shutil

# Ensure stdout handles UTF-8 safely on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def build_executable():
    print("=" * 70)
    print("  Starting Standalone EXE Compilation for Voucher Manager")
    print("=" * 70)

    # Verify PyInstaller is installed
    try:
        import PyInstaller
        print(f"[OK] PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("[ERROR] PyInstaller is not installed in this environment.")
        sys.exit(1)

    # App icon if available
    icon_args = []
    if os.path.exists("assets/icon.ico"):
        icon_args = ["--icon", "assets/icon.ico"]

    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",                           # Windowed app (no black terminal window)
        "--onefile",                             # Single standalone .exe file
        "--name", "VoucherManager",              # Executable output name: VoucherManager.exe
        "--collect-all", "ttkbootstrap",         # Include all themes, styles, json, and icons
        "--collect-all", "pypdfium2",            # Include native pdfium.dll and bindings
        "--collect-all", "reportlab",            # Include fonts, hyphenation dictionaries
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "sqlite3",
        "--hidden-import", "updater",
        "--hidden-import", "ui.main_window",
        "--hidden-import", "ui.dialogs",
        "--hidden-import", "ui.widgets",
        "--hidden-import", "ui.template_manager",
        "--hidden-import", "ui.float_manager",
        "--clean",                               # Clean cache before build
        *icon_args,
        "main.py"
    ]

    print("\nExecuting PyInstaller command:")
    print(" ".join(pyinstaller_cmd))
    print("\nCompiling... (this may take 1-2 minutes to package all binaries)\n")

    result = subprocess.run(pyinstaller_cmd)

    if result.returncode == 0:
        exe_path = os.path.abspath(os.path.join("dist", "VoucherManager.exe"))
        print("\n" + "=" * 70)
        print("  *** COMPILATION SUCCESSFUL! ***")
        print("=" * 70)
        print(f"\nStandalone Executable Location:\n  {exe_path}")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"File Size: {size_mb:.2f} MB")
        print("\nDistribution Note:")
        print("  - Users can copy 'VoucherManager.exe' to any folder or USB drive.")
        print("  - On first run, it automatically creates a 'data/' folder next to itself")
        print("    to store vouchers.db and attachments safely and permanently.")
        print("=" * 70)
    else:
        print(f"\n[ERROR] Compilation failed with exit code: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build_executable()
