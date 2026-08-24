"""Which way a position faces.

The integer values are deliberate: ``LONG`` is ``+1`` and ``SHORT`` is ``-1`` so that a signed
position size, a signed return and this enum all agree, and ``FLAT`` is ``0`` because no position is
no direction. These are *not* the protobuf numbers — `TradeDirection` in the contract numbers its
values from zero, as proto3 requires, and `direction_to_wire` / `direction_from_wire` do that
translation in one place.
"""

from __future__ import annotations

from enum import IntEnum


class Direction(IntEnum):
    SHORT = -1
    FLAT = 0
    LONG = 1

    @property
    def is_open(self) -> bool:
        """True for a direction that describes a position, false for FLAT."""
        return self is not Direction.FLAT

    @property
    def sign(self) -> int:
        """+1 long, -1 short, 0 flat. Multiply a price move by this to get the position's P&L."""
        return int(self.value)

    @property
    def opposite(self) -> Direction:
        return Direction(-self.value)


# The contract's TradeDirection numbering. Kept as a literal table rather than derived from the
# generated enum so that this module stays importable during training, where the gRPC stubs and their
# protobuf dependency are not installed.
_WIRE_BY_DIRECTION: dict[Direction, int] = {
    Direction.LONG: 1,
    Direction.SHORT: 2,
    Direction.FLAT: 3,
}
_DIRECTION_BY_WIRE: dict[int, Direction] = {wire: side for side, wire in _WIRE_BY_DIRECTION.items()}

WIRE_UNSPECIFIED = 0


def direction_to_wire(direction: Direction) -> int:
    return _WIRE_BY_DIRECTION[direction]


def direction_from_wire(value: int) -> Direction:
    """Translate a contract TradeDirection.

    UNSPECIFIED becomes FLAT: a request that did not say which way it faces is not carrying a
    position, and guessing LONG because it is the first named value is how a default becomes a trade.
    """
    if value == WIRE_UNSPECIFIED:
        return Direction.FLAT
    try:
        return _DIRECTION_BY_WIRE[value]
    except KeyError as error:
        raise ValueError(f"Unknown TradeDirection value {value!r}") from error
