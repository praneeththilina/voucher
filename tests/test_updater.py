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

        self.assertGreater(updater.parse_version("v1.1.7"), updater.parse_version("v1.1.6"))
        self.assertGreater(updater.parse_version("2.0.0"), updater.parse_version("1.9.9"))


if __name__ == "__main__":
    unittest.main()
