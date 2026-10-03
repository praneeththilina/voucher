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


if __name__ == "__main__":
    unittest.main()
