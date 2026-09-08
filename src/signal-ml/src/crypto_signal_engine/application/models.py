"""The shapes the two questions travel in, and the one rule that governs them.

**Money is `Decimal`; everything dimensionless is `float`.** The contract says so in capitals, and the
reason is the audit chain: .NET stores prices as `decimal`, and a stored decision has to replay to the
same bytes it was recorded with. A price that arrives as the string `"63214.07"`, becomes a float, and
leaves as `"63214.069999999999"` has broken that before anyone notices, because both spellings look
like the same number in a log. Probabilities, ATR multiples, risk-reward ratios and timings are ratios
of prices rather than prices, so nothing downstream stores them as money and float is the honest type.

These are transport-agnostic on purpose. Nothing here imports protobuf, so the services can be
exercised without a wire, and the mapping between these and the generated messages lives in exactly one
place (`transport.grpc.mappers`) where a field-name change shows up as an error rather than as a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from crypto_signal.domain import Direction


@dataclass(frozen=True, slots=True)
class CandleInput:
    """One closed candle, exactly as the caller sent it.

    Prices stay `Decimal` all the way to the feature builder, which is the last moment they can be
    turned into floats without the conversion being observable: features are scale-free ratios, so a
    float there is arithmetic, not stored money.
    """

    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class TradeParametersInput:
    """The bet being asked about.

    `max_holding_periods` and `minimum_confidence` are `0` for "engine default" rather than optional,
    matching the proto — a caller that forgets to set them gets the configured default, not an
    unbounded hold or a threshold of zero.
    """

    take_profit_percent: Decimal
    stop_loss_percent: Decimal
    allow_short: bool = False
    max_holding_periods: int = 0
    minimum_confidence: float = 0.0
    take_profit_atr_multiple: float = 0.0
    stop_loss_atr_multiple: float = 0.0


@dataclass(frozen=True, slots=True)
class OpenPositionInput:
    """A position as the orchestrator sees it. The engine owns none of this.

    The bracket prices are optional because a position can exist before its bracket is working at the
    venue; `bars_held` is counted by the caller, since only the caller knows when it filled.
    """

    direction: Direction
    entry_price: Decimal
    quantity: Decimal
    opened_at: datetime | None = None
    take_profit_price: Decimal | None = None
    stop_loss_price: Decimal | None = None
    bars_held: int = 0


@dataclass(frozen=True, slots=True)
class SignalRequest:
    request_id: str
    symbol: str
    interval: str
    candles: tuple[CandleInput, ...]
    parameters: TradeParametersInput
    expected_model_version: str = ""


@dataclass(frozen=True, slots=True)
class BotDecisionRequest:
    request_id: str
    symbol: str
    interval: str
    candles: tuple[CandleInput, ...]
    parameters: TradeParametersInput
    bot_id: str = ""
    position: OpenPositionInput | None = None
    expected_model_version: str = ""

    #: Optional higher-timeframe context candles for MTF features. When present,
    #: the evaluator attaches scale-free context columns before scoring the model.
    context_candles: tuple[CandleInput, ...] = ()
    context_interval: str = ""

    def as_signal_request(self) -> SignalRequest:
        """The same market question without the position, so one evaluator serves both RPCs."""
        return SignalRequest(
            request_id=self.request_id,
            symbol=self.symbol,
            interval=self.interval,
            candles=self.candles,
            parameters=self.parameters,
            expected_model_version=self.expected_model_version,
        )


@dataclass(frozen=True, slots=True)
class LevelsResult:
    """Prices as `Decimal`, distances as `float` — the split the contract mandates, made structural.

    Both halves describe the same barriers. The prices are what an order carries; the ATR multiples are
    what the model was asked about. Keeping them in one object means a caller cannot serialise a price
    from one bet and a multiple from another.
    """

    entry_price: Decimal
    take_profit_price: Decimal
    stop_loss_price: Decimal
    atr: Decimal
    risk_reward_ratio: float
    take_profit_atr: float
    stop_loss_atr: float


@dataclass(frozen=True, slots=True)
class BarrierProbabilitiesResult:
    """First-touch probabilities for the direction reported alongside them. Sums to 1."""

    take_profit_first: float
    stop_loss_first: float
    timeout: float


@dataclass(frozen=True, slots=True)
class ModelStamp:
    """Which model answered. Stamped on every response so a decision names its author.

    `used_wildcard` is not cosmetic: a pooled answer for a symbol with no dedicated model is a
    different claim from a specialised one, and an operator reviewing a loss is entitled to know which
    they got without going to look at the registry.
    """

    model_id: str
    model_version: str
    trained_at: datetime | None
    used_wildcard: bool


@dataclass(frozen=True, slots=True)
class SignalResult:
    """What `GetSignal` answers.

    Both sides' confidences are always present, including the one that was not taken — a caller
    thresholding at 0.6 that sees `long_confidence=0.58` learns something a bare FLAT hides.
    """

    request_id: str
    symbol: str
    interval: str
    direction: Direction
    levels: LevelsResult
    confidence: float
    probabilities: BarrierProbabilitiesResult
    expected_value: float
    long_confidence: float
    short_confidence: float
    candle_open_time: datetime
    valid_until: datetime
    model: ModelStamp
    input_digest_sha256: str
    rationale: tuple[str, ...] = ()
    warning: str = ""
    processing_milliseconds: float = 0.0
    #: Either requested barrier fell outside the ATR span the model was fitted across, so `confidence`
    #: and `expected_value` are extensions of the fitted surface rather than measurements on it. Carried
    #: as a bool as well as in `warning` because a risk engine cannot gate on prose.
    barrier_extrapolated: bool = False


class BotAction:
    """The advisory verbs, as the strings the mapper turns into the proto enum.

    Deliberately plain strings rather than an `IntEnum` mirroring the proto: the application layer must
    not depend on generated code, and these are the words that also go into the audit trail, where a
    `2` would need a lookup table to read.
    """

    HOLD = "HOLD"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    ADJUST_BRACKET = "ADJUST_BRACKET"


#: The machine-readable `reason_code` vocabulary, fixed by the contract. A code outside this set is a
#: bug rather than a new case, so the services assert membership before answering.
REASON_CODES: frozenset[str] = frozenset(
    {
        "no_edge",
        "confidence_below_minimum",
        "take_profit_touched",
        "stop_loss_touched",
        "max_holding_periods_reached",
        "direction_reversed",
        "short_not_allowed",
        "trailing_stop_advanced",
    }
)


@dataclass(frozen=True, slots=True)
class BotDecisionResult:
    """What `EvaluateBotDecision` answers: one verb, and the evidence behind it.

    `levels` is present for OPEN and ADJUST_BRACKET, and on CLOSE carries the bracket that was in
    force, so the orchestrator can record what it was closing out of. It is None for a HOLD that has
    nothing to hold.
    """

    request_id: str
    symbol: str
    interval: str
    action: str
    direction: Direction
    reason_code: str
    confidence: float
    probabilities: BarrierProbabilitiesResult
    expected_value: float
    candle_open_time: datetime
    valid_until: datetime
    model: ModelStamp
    input_digest_sha256: str
    levels: LevelsResult | None = None
    rationale: tuple[str, ...] = ()
    warning: str = ""
    processing_milliseconds: float = 0.0
    #: Either requested barrier fell outside the ATR span the model was fitted across, so `confidence`
    #: and `expected_value` are extensions of the fitted surface rather than measurements on it. Carried
    #: as a bool as well as in `warning` because a risk engine cannot gate on prose.
    barrier_extrapolated: bool = False

    def __post_init__(self) -> None:
        if self.reason_code not in REASON_CODES:
            raise ValueError(
                f"reason_code {self.reason_code!r} is not in the contract's vocabulary; "
                f"expected one of {sorted(REASON_CODES)}"
            )


@dataclass(frozen=True, slots=True)
class ModelDescription:
    """`GetModelInfo` for one resolved market."""

    request_id: str
    ready: bool
    model_id: str
    model_version: str
    project_version: str
    symbol: str
    interval: str
    trained_at: datetime | None
    feature_count: int
    is_wildcard: bool
    label_scheme: str
    calibration_method: str
    default_max_holding_periods: int
    minimum_barrier_atr: float
    maximum_barrier_atr: float

    #: The highest confidence the training run measured, or 0.0 when it measured none. Reported rather
    #: than withheld because a `minimum_confidence` above it filters out every signal, and silence is
    #: indistinguishable from a correctly-working cautious model unless the ceiling is visible.
    confidence_ceiling: float = 0.0

    #: `(threshold, share-at-or-above)` on held-out data, ascending. Empty when unmeasured.
    confidence_reach: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class MarketSummary:
    """One row of `GetCapabilities.supported_markets`."""

    symbol: str
    interval: str
    model_id: str
    model_version: str
    is_wildcard: bool


@dataclass(frozen=True, slots=True)
class Capabilities:
    request_id: str
    service: str
    service_version: str
    protocol_version: str
    capabilities: tuple[str, ...]
    supported_operations: tuple[str, ...]
    model_ready: bool
    minimum_candles: int
    maximum_candles: int
    operating_mode: str
    wildcard_model_ready: bool
    supported_markets: tuple[MarketSummary, ...] = field(default_factory=tuple)
