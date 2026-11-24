# Rubric: invoice totals

Score each criterion from 0 to 10 (total 40). Judge the code and its tests as delivered; you may run them.

1. **Correctness** (0-10): does the code follow every rule of the task? Look hard at separator handling, digit grouping,
   currency markers on both ends, per-line rounding half up, `Decimal` everywhere (no float), and the `ValueError` cases.
2. **Robustness** (0-10): unexpected inputs (types, `bool`, NaN or infinite `Decimal`, odd spacing) fail cleanly with a
   clear message instead of a wrong number.
3. **Tests** (0-10): the author's tests cover the tricky rules, not only the easy path, and would catch a regression.
4. **Design and readability** (0-10): small, clear functions, names that say what they hold, no dead code, easy to change.
