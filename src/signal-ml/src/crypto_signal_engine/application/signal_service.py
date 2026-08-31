"""`GetSignal`: one market, one bet, one answer.

Thin on purpose. Everything that could be got wrong — validating the window, resolving the model,
pricing both sides, formatting the money — lives in `candles`, `evaluator` and `domain`, and this file's
only job is to say which of those results go in which field. A service that computed anything of its own
would be a second place for the two RPCs to disagree.
"""

from __future__ import annotations

from crypto_signal.domain import Direction

from .evaluator import (
    LABEL_SCHEME,
    UNRECORDED_CALIBRATION,
    MarketEvaluator,
)
from .models import (
    Capabilities,
    MarketSummary,
    ModelDescription,
    SignalRequest,
    SignalResult,
)
from .candles import normalise_market, validate_request_id

PROTOCOL_VERSION = "crypto_signal.ml.v1"

#: What this engine can be asked for, reported by `GetCapabilities` so a caller can check rather than
#: assume. `predict_signal` is deliberately absent: the close-to-close RPC is gone, and a caller still
#: looking for it should find out from this list, not from an unimplemented-method error.
CAPABILITIES: tuple[str, ...] = (
    "barrier_conditional_signal",
    "directional_long_short",
    "bracket_levels",
    "bot_decision_advice",
    "pooled_cross_symbol_model",
    "decimal_string_prices",
    "online_trade_outcome_capture",
)

SUPPORTED_OPERATIONS: tuple[str, ...] = (
    "GetCapabilities",
    "GetModelInfo",
    "GetSignal",
    "EvaluateBotDecision",
    "RecordTradeOutcome",
    "GetTrainingStatus",
)


class SignalService:
    def __init__(
        self,
        evaluator: MarketEvaluator,
        service_name: str,
        service_version: str,
        operating_mode: str,
    ) -> None:
        self._evaluator = evaluator
        self._service_name = service_name
        self._service_version = service_version
        self._operating_mode = operating_mode

    def get_signal(self, request: SignalRequest) -> SignalResult:
        assessment = self._evaluator.assess(
            request_id=request.request_id,
            symbol=request.symbol,
            interval=request.interval,
            candles=request.candles,
            parameters=request.parameters,
            expected_model_version=request.expected_model_version,
        )
        window = assessment.window
        direction = assessment.choice.direction

        # A FLAT answer still quotes levels, for the long side it declined. The alternative is an empty
        # bracket, which reads as "no levels exist" when what happened is "these levels were not worth
        # taking" — and an operator comparing a declined signal against the candle that followed needs
        # the prices to compare against.
        levels = assessment.levels(Direction.LONG if direction is Direction.FLAT else direction)

        # On FLAT, report the best candidate's confidence/EV. Zero here had the same blinding
        # effect as on the advisor: a signal that looked and found 28% is information — "0.0000"
        # is not, and the calibration loop cannot grade an opinion that was erased.
        best_confidence = (
            assessment.confidence_of(direction)
            if direction is not Direction.FLAT
            else max(
                (candidate.confidence for candidate in assessment.choice.candidates),
                default=0.0,
            )
        )
        best_ev = (
            assessment.expected_value_of(direction)
            if direction is not Direction.FLAT
            else max(
                (candidate.expected_value_atr for candidate in assessment.choice.candidates),
                default=0.0,
            )
        )

        return SignalResult(
            request_id=request.request_id,
            symbol=window.symbol,
            interval=window.interval,
            direction=direction,
            levels=levels,
            confidence=best_confidence,
            probabilities=assessment.probabilities(direction),
            expected_value=best_ev,
            long_confidence=assessment.confidence_of(Direction.LONG),
            short_confidence=assessment.confidence_of(Direction.SHORT),
            candle_open_time=window.candle_open_time,
            valid_until=window.valid_until,
            model=assessment.stamp,
            input_digest_sha256=window.input_digest_sha256,
            rationale=assessment.choice.rationale,
            warning=assessment.warning,
            barrier_extrapolated=assessment.barrier_extrapolated,
            processing_milliseconds=assessment.elapsed_milliseconds,
        )

    def get_model_info(self, request_id: str, symbol: str, interval: str) -> ModelDescription:
        """Describe the model that *would* answer for a market, without asking it anything.

        An empty symbol resolves the wildcard, which is how a caller discovers the pooled model's
        identity without naming a market it does not intend to trade.
        """
        validate_request_id(request_id)
        registry = self._evaluator.registry
        canonical_symbol, canonical_interval = normalise_market(symbol or "BTCUSDT", interval)
        wildcard_only = not symbol.strip()

        model = registry.resolve(canonical_symbol, canonical_interval)
        descriptor = model.descriptor
        low, high = self._evaluator.barrier_atr_bounds

        return ModelDescription(
            request_id=request_id,
            ready=True,
            model_id=descriptor.model_id,
            model_version=descriptor.model_version,
            project_version=descriptor.project_version,
            # The bundle's own identity, not the symbol that was asked about: a pooled model answering
            # for ETHUSDT reports "*", so the response cannot be read as "there is an ETHUSDT model".
            symbol="*" if descriptor.is_pooled else descriptor.symbols[0],
            interval=descriptor.interval,
            trained_at=descriptor.trained_at,
            feature_count=descriptor.feature_count,
            is_wildcard=descriptor.is_pooled or wildcard_only,
            label_scheme=LABEL_SCHEME,
            calibration_method=descriptor.calibration_method or UNRECORDED_CALIBRATION,
            default_max_holding_periods=(
                self._evaluator.default_max_holding_periods or descriptor.max_horizon
            ),
            minimum_barrier_atr=low,
            maximum_barrier_atr=high,
            confidence_ceiling=descriptor.confidence_ceiling or 0.0,
            confidence_reach=descriptor.confidence_attainment,
        )

    def get_capabilities(self, request_id: str) -> Capabilities:
        """What is loaded and answerable, read from the registry rather than from configuration.

        `supported_markets` lists what actually loaded, so a bundle that failed validation does not
        appear here even though its file is on disk. That is the point of reporting it: an operator who
        dropped in `ETHUSDT_1h.joblib` and does not see it listed knows to look at `rejections()`.
        """
        validate_request_id(request_id)
        registry = self._evaluator.registry
        markets: list[MarketSummary] = []
        wildcard_ready = False

        for descriptor in registry.available():
            wildcard_ready = wildcard_ready or descriptor.is_pooled
            # A pooled bundle is one row reading "*", not one row per pair it happened to be trained on:
            # it answers markets outside that list too, so enumerating them would understate its reach
            # while looking like an exhaustive list. A dedicated bundle lists what it covers.
            symbols = ("*",) if descriptor.is_pooled else descriptor.symbols
            for symbol in symbols:
                markets.append(
                    MarketSummary(
                        symbol=symbol,
                        interval=descriptor.interval,
                        model_id=descriptor.model_id,
                        model_version=descriptor.model_version,
                        is_wildcard=descriptor.is_pooled,
                    )
                )

        return Capabilities(
            request_id=request_id,
            service=self._service_name,
            service_version=self._service_version,
            protocol_version=PROTOCOL_VERSION,
            capabilities=CAPABILITIES,
            supported_operations=SUPPORTED_OPERATIONS,
            model_ready=bool(markets),
            minimum_candles=self._evaluator.minimum_candles,
            maximum_candles=self._evaluator.maximum_candles,
            operating_mode=self._operating_mode,
            wildcard_model_ready=wildcard_ready,
            supported_markets=tuple(markets),
        )
