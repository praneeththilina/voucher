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


if __name__ == "__main__":
    unittest.main()
