"""
Auto-Update Engine for Voucher Manager
======================================
Interacts with GitHub Releases API to detect new versions, stream download
executable updates with progress reporting, and execute seamless atomic replacement.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from urllib.parse import urlparse
import subprocess
from datetime import datetime

GITHUB_REPO = "praneeththilina/voucher"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
USER_AGENT = "VoucherManager-Updater/1.1"


def parse_version(v_str):
    """
    Parse a version string like 'v1.1.7' or '1.2.0-beta' into a tuple of ints for comparison.
    Example: 'v1.1.7' -> (1, 1, 7)
    """
    if not v_str:
        return (0, 0, 0)
    cleaned = v_str.strip().lstrip("vV")
    # Take only the numerical part before any hyphen or suffix
    base = cleaned.split("-")[0].split("+")[0]
    parts = []
    for p in base.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def check_for_updates(current_version, repo=GITHUB_REPO, timeout=6):
    """
    Check GitHub Releases for a newer version of Voucher Manager.

    Returns:
        dict with keys:
            update_available: bool
            latest_version: str
            current_version: str
            release_name: str
            release_notes: str
            download_url: str or None
            asset_size: int
            published_at: str
            html_url: str
            error: str or None
    """
    result = {
        "update_available": False,
        "latest_version": current_version,
        "current_version": current_version,
        "release_name": "",
        "release_notes": "",
        "download_url": None,
        "asset_size": 0,
        "published_at": "",
        "html_url": f"https://github.com/{repo}/releases",
        "error": None,
    }

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                result["error"] = f"GitHub API returned status {response.status}"
                return result

            data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            latest_ver = tag_name.lstrip("vV").strip()
            result["latest_version"] = latest_ver
            result["release_name"] = data.get("name") or f"Release {tag_name}"
            result["release_notes"] = data.get("body") or "No release notes provided."
            result["published_at"] = data.get("published_at", "")
            result["html_url"] = data.get("html_url", result["html_url"])

            # Find matching Windows binary asset (.exe)
            for asset in data.get("assets", []):
                name = asset.get("name", "").lower()
                if name.endswith(".exe"):
                    result["download_url"] = asset.get("browser_download_url")
                    result["asset_size"] = asset.get("size", 0)
                    break

            # Compare versions
            current_parsed = parse_version(current_version)
            latest_parsed = parse_version(latest_ver)

            if latest_parsed > current_parsed:
                result["update_available"] = True

    except urllib.error.HTTPError as e:
        if e.code == 404:
            result["error"] = "No releases found on GitHub repository yet."
        else:
            result["error"] = f"GitHub API error: {e.code} {e.reason}"
    except urllib.error.URLError as e:
        result["error"] = "Could not connect to GitHub. Please check your internet connection."
    except Exception as e:
        result["error"] = str(e)

    return result


def _is_safe_download_url(url: str) -> bool:
    """Security check: Validate that update download URL is strictly HTTPS from trusted GitHub domains."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        hostname = (parsed.hostname or "").lower()
        allowed_domains = ("github.com", "githubusercontent.com")
        return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)
    except Exception:
        return False


def download_update(download_url, target_path, progress_callback=None, cancel_event=None):
    """
    Stream download the new binary asset with progress callbacks.

    Args:
        download_url: URL to download from
        target_path: Local file path to save executable
        progress_callback: func(downloaded_bytes, total_bytes, percent)
        cancel_event: threading.Event to signal abort

    Returns:
        bool: True if completed successfully, False if cancelled or failed
    """
    if not _is_safe_download_url(download_url):
        raise ValueError(f"Insecure or untrusted download URL: {download_url}")

    req = urllib.request.Request(
        download_url,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536  # 64 KB

            with open(target_path, "wb") as out_file:
                while True:
                    if cancel_event and cancel_event.is_set():
                        out_file.close()
                        try:
                            os.remove(target_path)
                        except Exception:
                            pass
                        return False

                    chunk = response.read(chunk_size)
                    if not chunk:
                        break

                    out_file.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback:
                        percent = (downloaded / total_size * 100) if total_size > 0 else 0
                        progress_callback(downloaded, total_size, percent)

        return True

    except Exception as e:
        try:
            if os.path.exists(target_path):
                os.remove(target_path)
        except Exception:
            pass
        raise e


def apply_update_and_restart(new_exe_path):
    """
    Execute atomic executable swap on Windows using a detached helper batch script.
    Leaves the user's data/ folder completely untouched.
    """
    is_frozen = getattr(sys, "frozen", False)
    current_exe = os.path.abspath(sys.executable if is_frozen else sys.argv[0])
    app_dir = os.path.dirname(current_exe)

    # Batch script to perform delayed swap
    bat_path = os.path.join(app_dir, "update_and_restart.bat")

    batch_content = f"""@echo off
setlocal enabledelayedexpansion
title Updating Voucher Manager...

echo Waiting for Voucher Manager to close...
timeout /t 2 /nobreak > nul

set /a retries=0
:RETRY
copy /y "{os.path.abspath(new_exe_path)}" "{current_exe}" > nul 2>&1
if errorlevel 1 (
    set /a retries+=1
    if !retries! lss 25 (
        timeout /t 1 /nobreak > nul
        goto RETRY
    ) else (
        echo Failed to replace executable. File may be locked.
        pause
        exit /b 1
    )
)

echo Update successfully installed. Starting new version...
start "" "{current_exe}"

:: Clean up temporary installer and this script
del /f /q "{os.path.abspath(new_exe_path)}" > nul 2>&1
(goto) 2>nul & del "%~f0"
"""

    with open(bat_path, "w", encoding="ascii", errors="ignore") as f:
        f.write(batch_content)

    # Spawn the batch script detached without console window
    CREATE_NO_WINDOW = 0x08000000
    subprocess.Popen(
        ["cmd.exe", "/c", bat_path],
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )

    # Exit the running Python application immediately so the file lock is released
    sys.exit(0)
