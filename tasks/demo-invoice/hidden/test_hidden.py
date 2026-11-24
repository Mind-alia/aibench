"""Hidden tests of the demo task. Never shown to the agent; copied into a fresh copy of its work after it finishes."""

import importlib
import unittest
from decimal import Decimal

ACCEPTED = {
    "french_with_currency": ("1 234,56 €", "1234.56"),
    "plain_dot": ("1234.56", "1234.56"),
    "negative_comma": ("-12,5", "-12.5"),
    "plus_sign": ("+7", "7"),
    "euro_prefix_space": ("€ 3", "3"),
    "euro_suffix_glued": ("3€", "3"),
    "eur_prefix_any_case": ("Eur 12,00", "12.00"),
    "eur_suffix": ("45EUR", "45"),
    "nbsp_grouping": ("1 234,5", "1234.5"),
    "narrow_nbsp_grouping": ("12 345", "12345"),
    "dot_thousands_comma_decimal": ("1.234,56", "1234.56"),
    "comma_thousands_dot_decimal": ("1,234.56", "1234.56"),
    "repeated_dot_thousands": ("1.234.567", "1234567"),
    "single_dot_is_decimal": ("1.234", "1.234"),
    "single_comma_is_decimal": ("2,345", "2.345"),
    "sign_after_leading_currency": ("€-3,50", "-3.50"),
    "surrounding_whitespace": ("  10,00 €  ", "10.00"),
}

REJECTED = {
    "empty": "",
    "letters": "abc",
    "comma_groups_too_short": "12,3,4",
    "space_group_too_short": "1 23,4",
    "first_group_too_long": "1234 567",
    "leading_separator": ",5",
    "trailing_separator": "5,",
    "double_sign": "--5",
    "currency_both_ends": "€12€",
    "mixed_thousands": "1 234.567,89",
    "two_decimal_separators": "1.234,567,8",
    "space_inside_fraction": "12,3 4",
    "currency_only": "€",
}


def _invoice():
    return importlib.import_module("invoice")


class Parse(unittest.TestCase):
    def test_not_a_string(self):
        with self.assertRaises(ValueError):
            _invoice().parse_amount(12.5)

    def test_returns_decimal_exactly(self):
        value = _invoice().parse_amount("0,10")
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value.as_tuple().exponent, -2)


def _accept(text, expected):
    def test(self):
        value = _invoice().parse_amount(text)
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, Decimal(expected))
    return test


def _reject(text):
    def test(self):
        with self.assertRaises(ValueError):
            _invoice().parse_amount(text)
    return test


for _name, (_text, _expected) in ACCEPTED.items():
    setattr(Parse, f"test_accepts_{_name}", _accept(_text, _expected))
for _name, _text in REJECTED.items():
    setattr(Parse, f"test_rejects_{_name}", _reject(_text))


def line(price, quantity=1, rate=None, description="item"):
    entry = {"description": description, "quantity": quantity, "unit_price": price}
    if rate is not None:
        entry["vat_rate"] = rate
    return entry


class Totals(unittest.TestCase):
    def totals(self, lines, **kwargs):
        return _invoice().compute_totals(lines, **kwargs)

    def test_single_line_default_rate(self):
        result = self.totals([line("100,00")])
        self.assertEqual((result["net"], result["vat"], result["gross"]),
                         (Decimal("100.00"), Decimal("20.00"), Decimal("120.00")))

    def test_amounts_have_two_decimals(self):
        result = self.totals([line("3")])
        for key in ("net", "vat", "gross"):
            self.assertEqual(result[key].as_tuple().exponent, -2, key)

    def test_net_rounded_half_up_per_line(self):
        self.assertEqual(self.totals([line("0,335", quantity=3)])["net"], Decimal("1.01"))

    def test_half_cent_that_floats_get_wrong(self):
        self.assertEqual(self.totals([line("1,005")], default_vat_rate=Decimal("0"))["net"], Decimal("1.01"))

    def test_another_half_cent_floats_get_wrong(self):
        self.assertEqual(self.totals([line("2,675")], default_vat_rate=Decimal("0"))["net"], Decimal("2.68"))

    def test_vat_rounded_per_line(self):
        result = self.totals([line("0,03"), line("0,03"), line("0,03")])
        self.assertEqual(result["vat"], Decimal("0.03"))

    def test_no_float_drift(self):
        result = self.totals([line("0.1"), line("0.2")], default_vat_rate=Decimal("0"))
        self.assertEqual(result["net"], Decimal("0.30"))

    def test_vat_by_rate(self):
        result = self.totals([line("100", rate=Decimal("0.20")), line("10", rate=Decimal("0.055")),
                              line("50", rate=Decimal("0.2"))])
        self.assertEqual(result["vat_by_rate"][Decimal("0.20")], Decimal("30.00"))
        self.assertEqual(result["vat_by_rate"][Decimal("0.055")], Decimal("0.55"))
        self.assertEqual(len(result["vat_by_rate"]), 2)

    def test_default_rate_parameter(self):
        self.assertEqual(self.totals([line("10")], default_vat_rate=Decimal("0.10"))["vat"], Decimal("1.00"))

    def test_zero_rate_allowed(self):
        self.assertEqual(self.totals([line("10", rate=Decimal("0"))])["vat"], Decimal("0.00"))

    def test_discount_line(self):
        result = self.totals([line("100"), line("-10,00")])
        self.assertEqual(result["net"], Decimal("90.00"))
        self.assertEqual(result["gross"], Decimal("108.00"))

    def test_decimal_quantity_and_price(self):
        self.assertEqual(self.totals([line(Decimal("2.50"), quantity=Decimal("1.5"))])["net"], Decimal("3.75"))

    def test_negative_half_rounds_away_from_zero(self):
        self.assertEqual(self.totals([line("-0,005")], default_vat_rate=Decimal("0"))["net"], Decimal("-0.01"))


def _refuse(lines, **kwargs):
    def test(self):
        with self.assertRaises(ValueError):
            _invoice().compute_totals(lines, **kwargs)
    return test


REFUSED = {
    "empty_list": [],
    "zero_quantity": [line("1", quantity=0)],
    "negative_quantity": [line("1", quantity=-2)],
    "bool_quantity": [line("1", quantity=True)],
    "float_price": [line(1.5)],
    "rate_above_one": [line("1", rate=Decimal("1.5"))],
    "float_rate": [line("1", rate=0.2)],
    "missing_description": [{"quantity": 1, "unit_price": "1"}],
    "bad_price_text": [line("12,3,4")],
    "blank_description": [line("1", description="   ")],
}

for _name, _lines in REFUSED.items():
    setattr(Totals, f"test_refuses_{_name}", _refuse(_lines))
setattr(Totals, "test_refuses_unused_float_default_rate",
        _refuse([line("1", rate=Decimal("0.2"))], default_vat_rate=0.2))


if __name__ == "__main__":
    unittest.main()
