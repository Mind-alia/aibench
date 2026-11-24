# Task: invoice totals

The repository contains an empty module `invoice.py`. Implement the two functions below, using only the Python standard
library (Python 3.11 or newer). Add your own tests under `tests/` (standard `unittest` is enough) and make sure they pass.

## 1. `parse_amount(text: str) -> Decimal`

Turns an amount written by a person into a `decimal.Decimal` holding exactly the value written (no rounding, so
`"2,345"` gives `Decimal("2.345")`). Rules:

- Whitespace around the amount is ignored.
- An optional currency marker, `€` or `EUR` (any case), may stand at the start or at the end, with or without a space,
  but not at both ends.
- An optional sign, `-` or `+`, may stand right before the first digit (after a leading currency marker).
- The amount must start and end with a digit.
- **Decimal separator.** If both `,` and `.` appear, the one that appears last is the decimal separator. If only one of
  them appears, exactly once, it is the decimal separator. If only one of them appears several times, it is a thousands
  separator (`"1.234.567"` is 1234567).
- **Thousands separators** are spaces (regular space, U+00A0 or U+202F) or the punctuation mark that is not the decimal
  separator. One amount uses one kind only. The first group has 1 to 3 digits and every later group exactly 3 digits.
- Anything else raises `ValueError`, including a value that is not a string.

Examples: `"1 234,56 €"` → 1234.56; `"1,234.56"` → 1234.56; `"1.234"` → 1.234; `"€ 3"` → 3; `"-12,5"` → -12.5.
Rejected: `""`, `"abc"`, `"12,3,4"`, `"1 23,4"`, `",5"`, `"5,"`, `"--5"`, `"€12€"`.

## 2. `compute_totals(lines, default_vat_rate=Decimal("0.20")) -> dict`

`lines` is a non-empty list of dicts with the keys:

- `description`: a non-empty string (spaces alone do not count);
- `quantity`: an `int` or a `Decimal`, strictly positive (`bool` is refused);
- `unit_price`: a string read with `parse_amount`, an `int` or a `Decimal` (may be negative, for a discount line);
- `vat_rate` (optional, default `default_vat_rate`): an `int` or a `Decimal` between 0 and 1 inclusive.

For each line, `net = quantity × unit_price` rounded to the cent, then `vat = net × vat_rate` rounded to the cent. Rounding
is half up (away from zero on .5). Return:

```python
{"net": Decimal, "vat": Decimal, "gross": Decimal, "vat_by_rate": {rate: Decimal}}
```

where `net` and `vat` are the sums of the rounded line values, `gross = net + vat`, every amount has two decimals, and
`vat_by_rate` maps each rate used to the sum of its lines' VAT. Floats anywhere, a missing key, an empty list, a
non-positive quantity or a rate outside [0, 1] raise `ValueError`.
