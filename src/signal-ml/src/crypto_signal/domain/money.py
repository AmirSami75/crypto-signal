"""Decimal strings at the boundary.

Money leaves this service as text, not as `double`. The engine computes in float64 — that is what the
model and the feature pipeline speak — but the moment a price is going to be stored, hashed into an
input digest, or compared against what the exchange reports, it becomes a decimal string with a fixed
number of places. The .NET orchestrator parses it straight into `decimal`, so the price the engine
computed and the price the database records are the same characters.

Fixed places, not trimmed: "100.00000000" and "100.0" are the same number and different bytes, and an
audit chain that hashes its inputs cares about the bytes.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

#: Binance reports klines to eight decimal places, and the venue's precision is the only one that
#: matters for a price that will be compared against a fill.
DEFAULT_PRICE_PLACES = 8


def quantize(value: float | Decimal | str, places: int = DEFAULT_PRICE_PLACES) -> Decimal:
    """Round to `places` decimal places, half-to-even.

    Floats go through `repr` rather than straight into `Decimal`, because `Decimal(0.1)` is
    0.1000000000000000055511151231257827021181583404541015625 and `Decimal(repr(0.1))` is the 0.1 the
    caller meant. The shortest round-trip repr is the honest reading of a float64.
    """
    if isinstance(value, float):
        source = Decimal(repr(value))
    elif isinstance(value, Decimal):
        source = value
    else:
        source = Decimal(str(value))

    if not source.is_finite():
        raise ValueError(f"Cannot quantize a non-finite price: {value!r}")

    return source.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)


def format_decimal(value: float | Decimal | str, places: int = DEFAULT_PRICE_PLACES) -> str:
    """Render a price for the wire. Always `places` digits after the point, never scientific notation."""
    return f"{quantize(value, places):f}"


def parse_money(text: str, field: str = "value") -> Decimal:
    """Read a decimal string from the wire without going through a float.

    The inbound half of the contract's decimal-string rule. A price that arrives as `"63214.07"` and is
    parsed to float is already 63214.070000000000291038304567337036132812500, and the difference
    survives into whatever the engine echoes back — so a decision replayed from the audit log fails to
    match itself over a rounding step nobody performed deliberately. `Decimal(text)` reads the digits
    that were sent.

    Rejects the empty string rather than reading it as zero: a missing price is missing, and a zero
    price is a free trade. Conflating them is how absent market data turns into a position.
    """
    if text is None or text == "":
        raise ValueError(f"{field} is required and cannot be empty")
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{field} is not a decimal number: {text!r}") from error
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite, got {text!r}")
    return parsed


def parse_decimal(text: str, field: str = "value") -> float:
    """The same read, narrowed to the float64 the feature pipeline works in.

    For quantities that are about to become arithmetic — a candle price entering the feature builder, a
    percentage entering an ATR conversion — where the float is the point. Anything that will be stored,
    hashed or echoed should use `parse_money` and stay exact.
    """
    return float(parse_money(text, field))
