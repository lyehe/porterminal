"""Run with `python -B checks.py` in a scratch copy of this demo project."""

import unittest

from invoice import total_after_discount


class DiscountChecks(unittest.TestCase):
    def test_twenty_percent_discount(self) -> None:
        self.assertEqual(total_after_discount(100, 20), 80)

    def test_ten_percent_discount(self) -> None:
        self.assertEqual(total_after_discount(50, 10), 45)

    def test_no_discount(self) -> None:
        self.assertEqual(total_after_discount(100, 0), 100)


if __name__ == "__main__":
    unittest.main()
