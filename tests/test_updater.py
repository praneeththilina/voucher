"""
Unit tests for version parsing and updater module (updater.py).
"""

import unittest
import updater


class TestUpdaterModule(unittest.TestCase):

    def test_parse_version(self):
        self.assertEqual(updater.parse_version("1.1.6"), (1, 1, 6))
        self.assertEqual(updater.parse_version("v1.1.7"), (1, 1, 7))
        self.assertEqual(updater.parse_version("V2.0.0-beta"), (2, 0, 0))
        self.assertEqual(updater.parse_version("1.0"), (1, 0, 0))
        self.assertEqual(updater.parse_version("invalid"), (0, 0, 0))

        self.assertEqual(updater.parse_version("v1.3.0"), (1, 3, 0))
        self.assertGreater(updater.parse_version("v1.3.0"), updater.parse_version("v1.2.0"))
        self.assertEqual(updater.parse_version("v1.2.0"), (1, 2, 0))
        self.assertGreater(updater.parse_version("v1.2.0"), updater.parse_version("v1.1.7"))
        self.assertGreater(updater.parse_version("v1.1.7"), updater.parse_version("v1.1.6"))
        self.assertGreater(updater.parse_version("2.0.0"), updater.parse_version("1.9.9"))

    def test_safe_download_url_validation(self):
        self.assertTrue(updater._is_safe_download_url("https://github.com/praneeththilina/voucher/releases/download/v1.2.0/voucher.exe"))
        self.assertTrue(updater._is_safe_download_url("https://objects.githubusercontent.com/github-production-release-asset-268400/v1.2.0.exe"))

        self.assertFalse(updater._is_safe_download_url("http://github.com/praneeththilina/voucher/releases/download/v1.2.0/voucher.exe"))
        self.assertFalse(updater._is_safe_download_url("file:///etc/passwd"))
        self.assertFalse(updater._is_safe_download_url("https://evil.com/malicious.exe"))
        self.assertFalse(updater._is_safe_download_url("https://github.com.attacker.com/fake.exe"))
        self.assertFalse(updater._is_safe_download_url(""))

    def test_download_update_rejects_insecure_urls(self):
        with self.assertRaises(ValueError):
            updater.download_update("http://github.com/repo/app.exe", "/tmp/app.exe")

        with self.assertRaises(ValueError):
            updater.download_update("https://malicious-site.com/app.exe", "/tmp/app.exe")

    def test_apply_update_and_restart_validates_path(self):
        with self.assertRaises(FileNotFoundError):
            updater.apply_update_and_restart("non_existent_update_file_12345.exe")

        with self.assertRaises(ValueError):
            updater.apply_update_and_restart("")

        with self.assertRaises(ValueError):
            updater.apply_update_and_restart(None)

    def test_is_onedir_installation(self):
        # Must return a boolean without throwing exceptions
        res = updater.is_onedir_installation()
        self.assertIsInstance(res, bool)

    def test_apply_update_and_restart_zip_validation(self):
        with self.assertRaises(FileNotFoundError):
            updater.apply_update_and_restart("non_existent_update_file_12345.zip")

        import tempfile
        import os
        with tempfile.NamedTemporaryFile(suffix="_&_exploit.zip", delete=False) as tmp:
            tmp_name = tmp.name
        try:
            with self.assertRaises(ValueError):
                updater.apply_update_and_restart(tmp_name)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)

    def test_check_for_updates_asset_selection(self):
        from unittest.mock import patch, MagicMock
        import io

        mock_release = {
            "tag_name": "v9.9.9",
            "name": "Release v9.9.9",
            "body": "Test changelog",
            "assets": [
                {
                    "name": "VoucherManager.exe",
                    "browser_download_url": "https://github.com/praneeththilina/voucher/releases/download/v9.9.9/VoucherManager.exe",
                    "size": 50000000
                },
                {
                    "name": "VoucherManager-windows.zip",
                    "browser_download_url": "https://github.com/praneeththilina/voucher/releases/download/v9.9.9/VoucherManager-windows.zip",
                    "size": 45000000
                }
            ]
        }

        # Mock onedir installation -> Should choose .zip
        with patch("updater.is_onedir_installation", return_value=True):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                import json
                mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                res = updater.check_for_updates("1.0.0")
                self.assertTrue(res["update_available"])
                self.assertTrue(res["download_url"].endswith(".zip"))

        # Mock non-onedir installation -> Should choose .exe
        with patch("updater.is_onedir_installation", return_value=False):
            with patch("urllib.request.urlopen") as mock_url:
                mock_resp = MagicMock()
                mock_resp.status = 200
                import json
                mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                mock_url.return_value = mock_resp

                res = updater.check_for_updates("1.0.0")
                self.assertTrue(res["update_available"])
                self.assertTrue(res["download_url"].endswith(".exe"))

    def test_check_for_updates_fallback_when_assets_empty(self):
        """Verify that when no binary assets are uploaded, a fallback archive URL is provided."""
        from unittest.mock import patch, MagicMock
        import json

        mock_release = {
            "tag_name": "v3.0.0",
            "name": "Release v3.0.0",
            "body": "Release without binary assets",
            "assets": [],  # Empty assets
            "zipball_url": "https://api.github.com/repos/praneeththilina/voucher/zipball/v3.0.0"
        }

        with patch("urllib.request.urlopen") as mock_url:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = json.dumps(mock_release).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            mock_url.return_value = mock_resp

            res = updater.check_for_updates("1.0.0")
            self.assertTrue(res["update_available"])
            self.assertIsNotNone(res["download_url"])
            self.assertTrue(res["download_url"].startswith("https://"))

    def test_safe_download_url_github_cdn(self):
        """Verify GitHub API and CDN redirect domains are trusted."""
        self.assertTrue(updater._is_safe_download_url("https://api.github.com/repos/praneeththilina/voucher/zipball/v1.0.0"))
        self.assertTrue(updater._is_safe_download_url("https://codeload.github.com/praneeththilina/voucher/legacy.zip/refs/tags/v1.0.0"))

    def test_update_available_dialog_in_place_download_and_countdown(self):
        """Verify that UpdateAvailableDialog displays download controls and handles automated countdown."""
        import tkinter as tk
        from unittest.mock import patch
        import ui.dialogs as dialogs

        root = tk.Tk()
        root.withdraw()
        try:
            info = {
                "latest_version": "4.1.0",
                "current_version": "4.0.0",
                "release_name": "Release v4.1.0",
                "release_notes": "- New feature test",
                "download_url": "https://github.com/praneeththilina/voucher/releases/download/v4.1.0/VoucherManager.zip",
                "asset_size": 25000000,
                "html_url": "https://github.com/praneeththilina/voucher/releases/tag/v4.1.0",
            }

            dlg = dialogs.UpdateAvailableDialog(root, info)
            self.assertTrue(dlg.winfo_exists())
            self.assertEqual(dlg._btn_row.winfo_manager(), "pack")
            self.assertEqual(dlg._dl_panel.winfo_manager(), "")

            # Mock download_update so it does not perform real network traffic in unit test
            with patch("updater.download_update", return_value=True):
                dlg._start_in_app_download()
                dlg.update()

                # Panel should now be packed (visible) and initial buttons unpacked
                self.assertEqual(dlg._btn_row.winfo_manager(), "")
                self.assertEqual(dlg._dl_panel.winfo_manager(), "pack")
                self.assertEqual(dlg._dl_pbar["value"], 0)

                # Simulate download complete
                dlg._on_download_success()
                dlg.update()

                self.assertEqual(dlg._dl_pbar["value"], 100)
                self.assertTrue(dlg._countdown_active)
                self.assertIn(dlg._countdown_secs, (2, 3))

                # Cancel auto-restart countdown
                dlg._cancel_auto_restart()
                dlg.update()
                self.assertFalse(dlg._countdown_active)

            dlg.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()


