"""The market assessment both RPCs are built from.

`GetSignal` and `EvaluateBotDecision` ask the model the identical question — "at these barriers, on this
window, which side has an edge?" — and differ only in what they do with the answer: one reports it, the
other weighs it against a position already open. Putting the shared part here is not just deduplication.
If the two RPCs each resolved their own model and built their own feature row, a bot could act on a
different assessment than the dashboard displayed for the same candle, and the audit trail would record
two digests for one market. One evaluator makes that impossible by construction.

What this module adds beyond wiring:

* **Percentages are validated against the direction they are asked about, not just for positivity.** A
  120% take-profit is a perfectly good long and an impossible short — it prices the asset below zero —
  so the check depends on which sides are in play.
* **Extrapolation is reported, not refused.** A barrier outside the grid the model was trained across,
  or a holding period other than the one it was labelled at, still gets an answer, with the caveat in
  `warning`. Refusing would be defensible; silently answering would not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import time

import pandas as pd

from crypto_signal.domain import (
    ADVERSE_WINS_TIE_BREAK,
    BarrierPair,
    Direction,
    atr_multiple,
    quantize,
)
from crypto_signal.features.mtf import attach_higher_tf_features
from crypto_signal.modeling.direction import DirectionCandidate, DirectionChoice, choose_direction

from .candles import CandleWindow, build_window, normalise_market, validate_request_id
from .errors import InvalidInferenceRequest
from .models import (
    BarrierProbabilitiesResult,
    CandleInput,
    LevelsResult,
    ModelStamp,
    TradeParametersInput,
)
from .context_helpers import _candles_to_dataframe, _candle_close_time

_PERCENT = Decimal(100)

#: The label definition, fixed by `labeling.triple_barrier` and reported verbatim over the wire. A
#: caller comparing engine output against its own backtest needs to know the tie-break rule, and the
#: rule is a property of how the model was taught rather than of any one bundle.
LABEL_SCHEME = ADVERSE_WINS_TIE_BREAK

#: What the engine says when a bundle records no calibration. Stated rather than left blank: silence
#: reads as "calibrated, method unknown", and the truth is the opposite.
UNRECORDED_CALIBRATION = "unrecorded; treat confidence as an uncalibrated model score"


@dataclass(frozen=True, slots=True)
class Assessment:
    """One market, one bet, one model's verdict on both directions.

    Carries the whole context a response needs — window, model identity, the barrier pair in the units
    the model consumed, and the choice — so neither service has to reach back into the registry.
    """

    window: CandleWindow
    stamp: ModelStamp
    barriers: BarrierPair
    choice: DirectionChoice
    parameters: TradeParametersInput
    max_holding_periods: int
    minimum_confidence: float
    warning: str
    #: True when either requested barrier fell outside the span the model was fitted across, so its
    #: probability — and therefore the expected value derived from it — is an extension of the fitted
    #: surface rather than a measurement on it. A duplicate of one clause of `warning`, and deliberately
    #: so: a risk engine must be able to gate on this without matching prose, and a 2%/1% request lands
    #: outside the span whenever the market is quiet enough, which is often. Measured on BTCUSDT at an
    #: ATR of 0.11% of price, a 2% target is 18.5 ATR and the expected value reads +4.1 per unit risked;
    #: sizing on that number is sizing on an artefact.
    barrier_extrapolated: bool
    started: float

    @property
    def elapsed_milliseconds(self) -> float:
        return (time.perf_counter() - self.started) * 1_000

    def levels(self, direction: Direction) -> LevelsResult:
        """The prices this bet resolves to, for one direction.

        Prices are computed in `Decimal` from the entry that arrived on the wire, so what the response
        quotes is what .NET stores. The ATR multiples alongside them come from the float pass that the
        model actually consumed — the two describe the same barriers, in the two types the contract
        requires each of them to be in.
        """
        if direction is Direction.FLAT:
            raise ValueError("FLAT has no levels; ask for the direction you are considering")

        entry = self.window.entry_price
        take_profit_percent = self.parameters.take_profit_percent
        stop_loss_percent = self.parameters.stop_loss_percent
        if direction is Direction.LONG:
            take_profit = entry * (Decimal(1) + take_profit_percent / _PERCENT)
            stop_loss = entry * (Decimal(1) - stop_loss_percent / _PERCENT)
        else:
            take_profit = entry * (Decimal(1) - take_profit_percent / _PERCENT)
            stop_loss = entry * (Decimal(1) + stop_loss_percent / _PERCENT)

        return LevelsResult(
            entry_price=quantize(entry),
            take_profit_price=quantize(take_profit),
            stop_loss_price=quantize(stop_loss),
            atr=quantize(self.window.atr),
            risk_reward_ratio=self.barriers.risk_reward_ratio,
            take_profit_atr=self.barriers.take_profit_atr,
            stop_loss_atr=self.barriers.stop_loss_atr,
        )

    def candidate(self, direction: Direction) -> DirectionCandidate | None:
        return self.choice.candidate_for(direction)

    def probabilities(self, direction: Direction) -> BarrierProbabilitiesResult:
        """First-touch probabilities for one side, or zeros when that side was not priced.

        Zeros rather than an exception: a FLAT answer still has to fill the field, and a caller reading
        three zeros can see that no distribution was reported. They do not sum to 1, which is the point.
        """
        candidate = self.candidate(direction)
        if candidate is None:
            return BarrierProbabilitiesResult(0.0, 0.0, 0.0)
        outcome = candidate.probabilities
        return BarrierProbabilitiesResult(
            take_profit_first=outcome.win,
            stop_loss_first=outcome.loss,
            timeout=outcome.timeout,
        )

    def confidence_of(self, direction: Direction) -> float:
        candidate = self.candidate(direction)
        return candidate.confidence if candidate is not None else 0.0

    def expected_value_of(self, direction: Direction) -> float:
        candidate = self.candidate(direction)
        return candidate.expected_value_atr if candidate is not None else 0.0


class MarketEvaluator:
    """Resolves a model for a market and asks it about a bet.

    Holds no per-request state: every call resolves through the registry, which is what lets a model be
    replaced on disk without a restart, and what keeps this object safe to share across gRPC workers.
    """

    def __init__(
        self,
        registry,
        minimum_candles: int,
        maximum_candles: int,
        default_max_holding_periods: int,
        default_minimum_confidence: float,
        barrier_atr_bounds: tuple[float, float],
    ) -> None:
        self._registry = registry
        self._minimum_candles = minimum_candles
        self._maximum_candles = maximum_candles
        self._default_max_holding_periods = default_max_holding_periods
        self._default_minimum_confidence = default_minimum_confidence
        self._barrier_atr_bounds = barrier_atr_bounds

    @property
    def registry(self):
        return self._registry

    @property
    def minimum_candles(self) -> int:
        return self._minimum_candles

    @property
    def maximum_candles(self) -> int:
        return self._maximum_candles

    @property
    def default_max_holding_periods(self) -> int:
        return self._default_max_holding_periods

    @property
    def barrier_atr_bounds(self) -> tuple[float, float]:
        return self._barrier_atr_bounds

    def describe(self, model) -> ModelStamp:
        descriptor = model.descriptor
        return ModelStamp(
            model_id=descriptor.model_id,
            model_version=descriptor.model_version,
            trained_at=descriptor.trained_at,
            used_wildcard=descriptor.is_pooled,
        )

    def assess(
        self,
        request_id: str,
        symbol: str,
        interval: str,
        candles: tuple[CandleInput, ...],
        parameters: TradeParametersInput,
        expected_model_version: str = "",
        allow_short: bool | None = None,
        context_candles: tuple[CandleInput, ...] = (),
        context_interval: str = "",
    ) -> Assessment:
        """Validate a request, resolve a model, and price both directions.

        `allow_short` overrides the parameters when the caller has a reason the parameters cannot express
        — a spot bot cannot short whatever its configuration says. Left None, the parameters govern.
        """
        started = time.perf_counter()
        validate_request_id(request_id)
        canonical_symbol, canonical_interval = normalise_market(symbol, interval)

        permit_short = parameters.allow_short if allow_short is None else allow_short
        self._validate_parameters(parameters, permit_short)

        # Resolve before building the window: the ATR window is a property of the model, and computing
        # features with a different one than the model was trained on would feed it a column whose name
        # it recognises and whose meaning has changed.
        model = self._registry.resolve(canonical_symbol, canonical_interval)
        descriptor = model.descriptor

        if expected_model_version and expected_model_version != descriptor.model_version:
            raise InvalidInferenceRequest(
                f"Requested model version {expected_model_version} is not the one loaded for "
                f"{canonical_symbol} {canonical_interval} ({descriptor.model_version}); the model "
                "changed between the caller's last read and this call"
            )

        # A recurrent model reads a window of candles, so the request must carry at least `lookback`.
        minimum_candles = self._minimum_candles
        if descriptor.is_sequence:
            minimum_candles = max(minimum_candles, descriptor.lookback)

        window = build_window(
            symbol=canonical_symbol,
            interval=canonical_interval,
            candles=candles,
            parameters=parameters,
            minimum_candles=minimum_candles,
            maximum_candles=self._maximum_candles,
            atr_window=descriptor.atr_window,
        )

        entry = float(window.entry_price)
        barriers = BarrierPair(
            take_profit_atr=atr_multiple(entry, float(parameters.take_profit_percent), window.atr),
            stop_loss_atr=atr_multiple(entry, float(parameters.stop_loss_percent), window.atr),
        )

        minimum_confidence = (
            parameters.minimum_confidence
            if parameters.minimum_confidence > 0
            else self._default_minimum_confidence
        )
        max_holding_periods = (
            parameters.max_holding_periods
            if parameters.max_holding_periods > 0
            else (self._default_max_holding_periods or descriptor.max_horizon)
        )

        if descriptor.is_sequence:
            # Feed the recurrent model a window of `lookback` candles, not the single latest row.
            model_features = window.features.frame.iloc[-descriptor.lookback :].copy()
        else:
            model_features = window.features.frame.loc[[window.latest_index]].copy()

        # When the caller supplies higher-timeframe context, attach MTF features to the
        # model input. The model must have been trained with those columns (they appear
        # in feature_columns); if it has MTF columns in its training set but no context
        # arrived, that is a caller-side misconfiguration we surface as a warning rather
        # than silently scoring on missing data.
        model_features, mtf_warning = self._attach_context_features(
            model_features, descriptor.feature_columns, context_candles, context_interval,
            window.candles,
        )

        choice = choose_direction(
            model,
            model_features,
            barriers,
            allow_short=permit_short,
            minimum_confidence=minimum_confidence,
            feature_columns=descriptor.feature_columns,
        )

        warning = self._warning(window, descriptor, barriers, max_holding_periods, choice)
        effective_warning = f"{warning} | {mtf_warning}" if mtf_warning else warning
        return Assessment(
            window=window,
            stamp=self.describe(model),
            barriers=barriers,
            choice=choice,
            parameters=parameters,
            max_holding_periods=max_holding_periods,
            minimum_confidence=minimum_confidence,
            warning=effective_warning,
            barrier_extrapolated=self._is_extrapolated(barriers),
            started=started,
        )

    def _attach_context_features(
        self,
        model_features: pd.DataFrame,
        feature_columns: tuple[str, ...],
        context_candles: tuple[CandleInput, ...],
        context_interval: str,
        lower_candles: tuple[CandleInput, ...],
    ) -> tuple[pd.DataFrame, str]:
        """Attach higher-TF context columns to the model feature row.

        MTF columns must appear in the model's training ``feature_columns`` to be
        consumed — an estimator simply ignores extra columns.  If context candles
        are supplied but the model was not trained with MTF columns, we warn so
        the caller knows the context is being silently dropped.
        """
        if not context_candles or not context_interval:
            return model_features, ""

        higher_df = _candles_to_dataframe(context_candles, context_interval)
        lower_df = _candles_to_dataframe(lower_candles, context_interval)

        lower_with_mtf = attach_higher_tf_features(lower_df, higher_df)

        mtf_columns = [c for c in lower_with_mtf.columns if c not in lower_df.columns]

        lower_with_mtf = lower_with_mtf.set_index("close_time")

        close_times = pd.DatetimeIndex(
            [_candle_close_time(c) for c in lower_candles]
        )
        if len(close_times) >= len(model_features):
            aligned_close = close_times[-len(model_features):]
        else:
            aligned_close = close_times
        mtf_for_rows = lower_with_mtf.reindex(aligned_close, method="ffill")[mtf_columns]
        mtf_for_rows.index = model_features.index

        model_features = model_features.join(mtf_for_rows)

        trained_mtf = [c for c in mtf_columns if c in feature_columns]
        if trained_mtf:
            missing = [c for c in trained_mtf if model_features[c].isna().any()]
            if missing:
                return model_features, (
                    f"MTF columns present in model but some are NaN after context "
                    f"attachment — model may produce unreliable scores: {missing}"
                )
            return model_features, ""

        return model_features, (
            f"higher-TF context supplied ({context_interval}) but model "
            f"was not trained with MTF features; context ignored"
        )

    def _validate_parameters(self, parameters: TradeParametersInput, allow_short: bool) -> None:
        """Reject a bet that has no prices, or none for the sides being considered."""
        for name, value in (
            ("take_profit_percent", parameters.take_profit_percent),
            ("stop_loss_percent", parameters.stop_loss_percent),
        ):
            if not value.is_finite():
                raise InvalidInferenceRequest(f"parameters.{name} must be finite, got {value}")
            if value <= 0:
                raise InvalidInferenceRequest(
                    f"parameters.{name} must be greater than zero, got {value}; a barrier at the entry "
                    "price is touched immediately"
                )
        if parameters.stop_loss_percent >= _PERCENT:
            raise InvalidInferenceRequest(
                "parameters.stop_loss_percent must be below 100: a long stopping out at or below a "
                "price of zero is a level no market reaches"
            )
        if allow_short and parameters.take_profit_percent >= _PERCENT:
            raise InvalidInferenceRequest(
                "parameters.take_profit_percent must be below 100 when shorts are allowed: a short's "
                "target would be at or below a price of zero"
            )
        if not 0.0 <= parameters.minimum_confidence < 1.0:
            raise InvalidInferenceRequest(
                f"parameters.minimum_confidence must be in [0, 1), got "
                f"{parameters.minimum_confidence}; a threshold of 1 can never be met"
            )

    def _barriers_outside_bounds(self, barriers: BarrierPair) -> tuple[tuple[str, float], ...]:
        """Which of the two requested barriers sit outside the span the model was fitted across.

        The single source for both the `barrier_extrapolated` flag and the extrapolation clause of
        `warning`. Deliberately one method rather than the same inequality written twice: the failure
        mode of two copies is a response whose bool says "measured" and whose prose says "extrapolated",
        and a caller that believes whichever of the two it happened to read first.
        """
        low, high = self._barrier_atr_bounds
        return tuple(
            (name, value)
            for name, value in (
                ("take_profit_atr", barriers.take_profit_atr),
                ("stop_loss_atr", barriers.stop_loss_atr),
            )
            if not low <= value <= high
        )

    def _is_extrapolated(self, barriers: BarrierPair) -> bool:
        return bool(self._barriers_outside_bounds(barriers))

    def _warning(
        self,
        window: CandleWindow,
        descriptor,
        barriers: BarrierPair,
        max_holding_periods: int,
        choice: DirectionChoice,
    ) -> str:
        """Every non-fatal caveat, joined. Advisory output — never an execution instruction."""
        notes: list[str] = list(window.warnings)

        low, high = self._barrier_atr_bounds
        outside = [f"{name}={value:.2f}" for name, value in self._barriers_outside_bounds(barriers)]
        if outside:
            notes.append(
                f"barrier extrapolation: {', '.join(outside)} lies outside the {low:g}-{high:g} ATR "
                "range the model was trained across, so its probability there is an extension of the "
                "fitted surface rather than a measurement on it"
            )

        if max_holding_periods != descriptor.max_horizon:
            notes.append(
                f"holding period {max_holding_periods} differs from the {descriptor.max_horizon} "
                "candles the labels were built at; the timeout probability describes the trained "
                "horizon, not the requested one"
            )

        if descriptor.confidence_ceiling is not None and not descriptor.is_reachable(
            self._default_minimum_confidence if self._default_minimum_confidence > 0 else 0.0
        ):
            notes.append(
                f"the configured confidence floor is above this model's measured ceiling of "
                f"{descriptor.confidence_ceiling:.3f}, so it will answer FLAT indefinitely"
            )

        if choice.warning:
            notes.append(choice.warning)

        return " | ".join(notes)
