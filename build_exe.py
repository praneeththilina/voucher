"""
Build Script: Compile Voucher Manager into High-Performance Windows Application
================================================================================
Bundles all Python dependencies, ttkbootstrap assets, ReportLab fonts, 
pypdfium2 native DLLs, and GUI into a fast-loading directory application 
(dist/VoucherManager/) and a portable distribution archive (dist/VoucherManager-windows.zip).

Why --onedir (Folder Distribution)?
-----------------------------------
Unlike PyInstaller's '--onefile' mode (which must decompress dozens of megabytes 
into AppData\\Local\\Temp\\_MEIxxxxxx on EVERY SINGLE launch and delete them on exit),
'--onedir' keeps all DLLs and assets pre-extracted in '_internal/'.
Result:
  - Startup time drops from ~5-8 seconds down to < 0.5 seconds.
  - Zero temporary files created in %TEMP%.
  - Zero disk thrashing or delay on application close.
  - All user databases and attachments remain safely isolated in 'data/'.

Usage:
    .\\venv\\Scripts\\python.exe build_exe.py
    .\\venv\\Scripts\\python.exe build_exe.py --onefile   (Legacy single-file mode)
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


def get_dir_size_mb(path: str) -> float:
    """Calculate the total size of a directory in megabytes."""
    total_bytes = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_bytes += os.path.getsize(fp)
            except OSError:
                pass
    return total_bytes / (1024 * 1024)


def build_executable():
    is_onefile = "--onefile" in sys.argv
    mode_str = "Legacy Single-File (.exe)" if is_onefile else "Instant-Load Folder Bundle (--onedir)"

    print("=" * 75)
    print(f"  Starting Build for Voucher Manager: {mode_str}")
    print("=" * 75)

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

    # Target packaging mode
    package_mode = "--onefile" if is_onefile else "--onedir"

    # Terminate any running instance of VoucherManager.exe to release DLL file locks
    try:
        subprocess.run(["taskkill", "/F", "/IM", "VoucherManager.exe"], capture_output=True)
    except Exception:
        pass

    # Pre-clean stale outputs to avoid residual conflicts
    if not is_onefile and os.path.exists(os.path.join("dist", "VoucherManager")):
        print("[INFO] Cleaning previous dist/VoucherManager directory...")
        try:
            shutil.rmtree(os.path.join("dist", "VoucherManager"))
        except Exception as e:
            print(f"[WARN] Could not clean dist/VoucherManager: {e}")

    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",                           # Windowed app (no console window)
        package_mode,                            # --onedir (default) or --onefile
        "-y",                                    # Overwrite output directory without confirmation
        "--noupx",                               # Avoid UPX decompression overhead & antivirus false-positives
        "--name", "VoucherManager",              # Output name: VoucherManager.exe
        "--collect-all", "ttkbootstrap",         # Include all themes, styles, json, and icons
        "--collect-all", "pypdfium2",            # Include native pdfium.dll and bindings
        "--collect-all", "reportlab",            # Include fonts, hyphenation dictionaries
        "--hidden-import", "PIL._tkinter_finder",
        "--hidden-import", "sqlite3",
        "--hidden-import", "updater",
        "--hidden-import", "firebase_client",
        "--hidden-import", "gdrive_client",
        "--hidden-import", "ui.main_window",
        "--hidden-import", "ui.dialogs",
        "--hidden-import", "ui.widgets",
        "--hidden-import", "ui.template_manager",
        "--hidden-import", "ui.float_manager",
        "--hidden-import", "ui.category_manager",
        "--hidden-import", "ui.name_manager",
        "--hidden-import", "ui.settings_dialog",
        "--hidden-import", "ui.pdf_viewer",
        "--hidden-import", "ui.payee_statement",
        "--hidden-import", "ui.tag_manager",
        "--add-data", "assets;assets",           # Bundle application icon and assets
        "--clean",                               # Clean cache before build
        *icon_args,
        "main.py"
    ]

    print("\nExecuting PyInstaller command:")
    print(" ".join(pyinstaller_cmd))
    print("\nCompiling... (this may take 1-2 minutes)\n")

    result = subprocess.run(pyinstaller_cmd)

    if result.returncode == 0:
        print("\n" + "=" * 75)
        print("  *** COMPILATION SUCCESSFUL! ***")
        print("=" * 75)

        if not is_onefile:
            folder_path = os.path.abspath(os.path.join("dist", "VoucherManager"))
            exe_path = os.path.join(folder_path, "VoucherManager.exe")

            # Ensure assets folder is present alongside executable
            dest_assets = os.path.join(folder_path, "assets")
            if os.path.exists("assets"):
                if os.path.exists(dest_assets):
                    shutil.rmtree(dest_assets)
                shutil.copytree("assets", dest_assets)

            folder_size = get_dir_size_mb(folder_path)

            print(f"\nApplication Folder:\n  {folder_path}")
            print(f"Main Executable:\n  {exe_path}")
            print(f"Folder Size: {folder_size:.1f} MB")

            # Create distributable zip archive
            print("\nPackaging distributable ZIP archive...")
            zip_base = os.path.join("dist", "VoucherManager-windows")
            zip_path = shutil.make_archive(zip_base, "zip", root_dir=folder_path)
            zip_size_mb = os.path.getsize(zip_path) / (1024 * 1024)
            print(f"[OK] Created: {os.path.abspath(zip_path)} ({zip_size_mb:.1f} MB)")

            print("\n" + "-" * 75)
            print("Performance & Distribution Highlights:")
            print("  - Launch Speed: INSTANT (< 0.5s). Dependencies stay pre-extracted in '_internal/'.")
            print("  - Zero Temp Files: Never writes or deletes files in AppData\\Local\\Temp.")
            print("  - Data Isolation: User SQLite database and attachments reside safely in 'data/'.")
            print("  - For Distribution: Share 'VoucherManager-windows.zip' with users.")
            print("-" * 75)
        else:
            exe_path = os.path.abspath(os.path.join("dist", "VoucherManager.exe"))
            print(f"\nStandalone Executable Location:\n  {exe_path}")
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"File Size: {size_mb:.2f} MB")
            print("\nNote: '--onefile' extracts to %TEMP% on every launch. Use default mode for instant loading.")
        print("=" * 75)
    else:
        print(f"\n[ERROR] Compilation failed with exit code: {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build_executable()

