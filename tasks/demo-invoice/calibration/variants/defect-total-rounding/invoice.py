"""Invoice totals: amounts written by people, and totals with per-line VAT."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
SPACES = frozenset("   ")
DIGITS = frozenset("0123456789")
CURRENCY_MARKERS = ("€", "eur")


def _strip_currency(text: str) -> str:
    """Remove one currency marker at the start or at the end; refuse one at both ends."""
    lowered = text.lower()
    at_start = next((m for m in CURRENCY_MARKERS if lowered.startswith(m)), None)
    at_end = next((m for m in CURRENCY_MARKERS if lowered.endswith(m)), None)
    if at_start and at_end and len(text) > len(at_start):
        raise ValueError(f"currency marker at both ends: {text!r}")
    if at_start:
        text = text[len(at_start):]
    elif at_end:
        text = text[: -len(at_end)]
    return text.strip("".join(SPACES))


def _decimal_separator(body: str) -> str | None:
    commas, dots = body.count(","), body.count(".")
    if commas and dots:
        return "," if body.rfind(",") > body.rfind(".") else "."
    if commas == 1:
        return ","
    if dots == 1:
        return "."
    return None


def _integer_digits(integer: str, thousands: str | None, original: str) -> str:
    """Check the digit grouping of the integer part and return its digits."""
    separators = SPACES | ({thousands} if thousands else set())
    kinds = {"space" if ch in SPACES else ch for ch in integer if ch in separators}
    if len(kinds) > 1:
        raise ValueError(f"mixed thousands separators: {original!r}")
    groups, current = [], ""
    for ch in integer:
        if ch in separators:
            groups.append(current)
            current = ""
        elif ch in DIGITS:
            current += ch
        else:
            raise ValueError(f"not an amount: {original!r}")
    groups.append(current)
    if len(groups) > 1 and (not 1 <= len(groups[0]) <= 3 or any(len(g) != 3 for g in groups[1:])):
        raise ValueError(f"bad digit grouping: {original!r}")
    if any(not g for g in groups):
        raise ValueError(f"not an amount: {original!r}")
    return "".join(groups)


def parse_amount(text: str) -> Decimal:
    """Read an amount such as '1 234,56 €' or '1,234.56' into the exact Decimal written."""
    if not isinstance(text, str):
        raise ValueError(f"an amount must be a string, not {type(text).__name__}")
    body = _strip_currency(text.strip())
    sign = ""
    if body[:1] in ("-", "+"):
        sign, body = body[0], body[1:]
    if not body or body[0] not in DIGITS or body[-1] not in DIGITS:
        raise ValueError(f"not an amount: {text!r}")
    decimal_sep = _decimal_separator(body)
    if decimal_sep is None:
        thousands = "," if "," in body else ("." if "." in body else None)
        return Decimal(sign + _integer_digits(body, thousands, text))
    if body.count(decimal_sep) != 1:
        raise ValueError(f"more than one decimal separator: {text!r}")
    integer, fraction = body.split(decimal_sep)
    if not fraction or any(ch not in DIGITS for ch in fraction):
        raise ValueError(f"not an amount: {text!r}")
    thousands = "." if decimal_sep == "," else ","
    return Decimal(f"{sign}{_integer_digits(integer, thousands, text)}.{fraction}")


def _number(value, what: str) -> Decimal:
    """An int or a finite Decimal; floats and bools are refused so no binary rounding sneaks in."""
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError(f"{what} must be an int or a Decimal, not {type(value).__name__}")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError(f"{what} must be finite, got {value!r}")
    return number


def _unit_price(value) -> Decimal:
    return parse_amount(value) if isinstance(value, str) else _number(value, "unit_price")


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def compute_totals(lines, default_vat_rate=Decimal("0.20")) -> dict:
    """Totals of an invoice: each line's net and VAT are rounded to the cent before they are added up."""
    if not isinstance(lines, list) or not lines:
        raise ValueError("an invoice needs a non-empty list of lines")
    default_rate = _number(default_vat_rate, "default_vat_rate")
    if not 0 <= default_rate <= 1:
        raise ValueError("default_vat_rate must be between 0 and 1")
    net_total = vat_total = Decimal("0.00")
    vat_by_rate: dict[Decimal, Decimal] = {}
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError(f"line {index}: expected a dict")
        missing = [key for key in ("description", "quantity", "unit_price") if key not in line]
        if missing:
            raise ValueError(f"line {index}: missing {', '.join(missing)}")
        if not isinstance(line["description"], str) or not line["description"].strip():
            raise ValueError(f"line {index}: description must be a non-empty string")
        quantity = _number(line["quantity"], "quantity")
        if quantity <= 0:
            raise ValueError(f"line {index}: quantity must be positive")
        rate = _number(line.get("vat_rate", default_rate), "vat_rate")
        if not 0 <= rate <= 1:
            raise ValueError(f"line {index}: vat_rate must be between 0 and 1")
        net = _round(quantity * _unit_price(line["unit_price"]))
        net_total += net
        vat_by_rate[rate] = vat_by_rate.get(rate, Decimal("0.00")) + net
    vat_by_rate = {rate: _round(net * rate) for rate, net in vat_by_rate.items()}
    vat_total = sum(vat_by_rate.values(), Decimal("0.00"))
    return {
        "net": _round(net_total),
        "vat": _round(vat_total),
        "gross": _round(net_total + vat_total),
        "vat_by_rate": {rate: _round(vat) for rate, vat in vat_by_rate.items()},
    }
