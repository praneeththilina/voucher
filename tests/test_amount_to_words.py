"""
Unit tests for check_printer.amount_to_words engine.
"""

import unittest
from check_printer import amount_to_words


class TestAmountToWords(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(amount_to_words(0), "Zero Only")
        self.assertEqual(amount_to_words(0.0), "Zero Only")
        self.assertEqual(amount_to_words("0"), "Zero Only")

    def test_single_digits(self):
        self.assertEqual(amount_to_words(1), "One Only")
        self.assertEqual(amount_to_words(5), "Five Only")
        self.assertEqual(amount_to_words(9), "Nine Only")

    def test_teens(self):
        self.assertEqual(amount_to_words(10), "Ten Only")
        self.assertEqual(amount_to_words(11), "Eleven Only")
        self.assertEqual(amount_to_words(15), "Fifteen Only")
        self.assertEqual(amount_to_words(19), "Nineteen Only")

    def test_tens(self):
        self.assertEqual(amount_to_words(20), "Twenty Only")
        self.assertEqual(amount_to_words(25), "Twenty-Five Only")
        self.assertEqual(amount_to_words(99), "Ninety-Nine Only")

    def test_hundreds(self):
        self.assertEqual(amount_to_words(100), "One Hundred Only")
        self.assertEqual(amount_to_words(105), "One Hundred Five Only")
        self.assertEqual(amount_to_words(342), "Three Hundred Forty-Two Only")
        self.assertEqual(amount_to_words(999), "Nine Hundred Ninety-Nine Only")

    def test_thousands(self):
        self.assertEqual(amount_to_words(1000), "One Thousand Only")
        self.assertEqual(amount_to_words(1050), "One Thousand Fifty Only")
        self.assertEqual(amount_to_words(50000), "Fifty Thousand Only")
        self.assertEqual(amount_to_words(125750), "One Hundred Twenty-Five Thousand Seven Hundred Fifty Only")

    def test_millions(self):
        self.assertEqual(amount_to_words(1000000), "One Million Only")
        self.assertEqual(amount_to_words(2500000), "Two Million Five Hundred Thousand Only")
        self.assertEqual(amount_to_words(125000000), "One Hundred Twenty-Five Million Only")

    def test_billions(self):
        self.assertEqual(amount_to_words(1000000000), "One Billion Only")
        self.assertEqual(amount_to_words(1500000000), "One Billion Five Hundred Million Only")

    def test_cents_and_decimals(self):
        self.assertEqual(amount_to_words(0.50), "Zero and 50/100")
        self.assertEqual(amount_to_words(125750.50), "One Hundred Twenty-Five Thousand Seven Hundred Fifty and 50/100")
        self.assertEqual(amount_to_words(10.05), "Ten and 05/100")
        self.assertEqual(amount_to_words(99.99), "Ninety-Nine and 99/100")

    def test_negative(self):
        self.assertTrue(amount_to_words(-500).startswith("Negative"))


if __name__ == "__main__":
    unittest.main()
