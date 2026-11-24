import unittest
from decimal import Decimal

from invoice import compute_totals, parse_amount


class ParseAmountTest(unittest.TestCase):
    def test_french_amount_with_currency(self):
        self.assertEqual(parse_amount("1 234,56 €"), Decimal("1234.56"))

    def test_english_grouping(self):
        self.assertEqual(parse_amount("1,234.56"), Decimal("1234.56"))

    def test_single_dot_is_decimal(self):
        self.assertEqual(parse_amount("1.234"), Decimal("1.234"))

    def test_rejects_bad_grouping(self):
        for text in ("12,3,4", "1 23,4", "€12€", "", "abc"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_amount(text)


class ComputeTotalsTest(unittest.TestCase):
    def test_per_line_rounding_half_up(self):
        totals = compute_totals([{"description": "bolts", "quantity": 3, "unit_price": "0,335"}])
        self.assertEqual(totals["net"], Decimal("1.01"))

    def test_vat_by_rate(self):
        totals = compute_totals([
            {"description": "work", "quantity": 1, "unit_price": "100", "vat_rate": Decimal("0.20")},
            {"description": "book", "quantity": 1, "unit_price": "10", "vat_rate": Decimal("0.055")},
        ])
        self.assertEqual(totals["vat_by_rate"][Decimal("0.055")], Decimal("0.55"))
        self.assertEqual(totals["gross"], Decimal("130.55"))

    def test_refuses_float(self):
        with self.assertRaises(ValueError):
            compute_totals([{"description": "x", "quantity": 1, "unit_price": 1.5}])


if __name__ == "__main__":
    unittest.main()
