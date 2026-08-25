"""`EvaluateBotDecision`: what to do next, given a bot's configuration and whatever it already holds.

Stateless. Everything the engine is allowed to know arrives in the request, and the answer is a verb plus
the evidence behind it — never an order. .NET decides whether to act, sizes the trade, checks it against
the risk engine and submits it; see `docs/ARCHITECTURE.md`.

The order the checks run in is the whole design, because several can be true at once and the wrong
precedence is expensive:

1. **Did the bracket already resolve?** Before anything about the model, because a position that hit its
   stop is closed whether or not the model still likes it. Asking the model first and closing second is
   how a losing position gets held on a fresh opinion.
2. **Has it been held too long?** A bet that never resolved is not a bet that is still working.
3. **Has the thesis reversed?** Only now, and only against the *opposite* side clearing the same bar the
   entry had to clear — a position should not be closed because conviction merely faded.
4. **Can the stop be tightened?** Last, and never loosened.

The touch test is `domain.barriers.first_touch`, the same function the labeller and the backtester call.
That is not tidiness: if the advisor resolved an ambiguous candle in the trade's favour while the labeller
resolved it against, the model would be trained on one rule and operated under another, and the
discrepancy would show up as live results quietly worse than the backtest.
"""

from __future__ import annotations

from decimal import Decimal

from crypto_signal.domain import Direction, Outcome, TouchResult, first_touch, quantize

from .errors import InvalidInferenceRequest
from .evaluator import Assessment, MarketEvaluator
from .models import (
    BotAction,
    BotDecisionRequest,
    BotDecisionResult,
    LevelsResult,
    OpenPositionInput,
)

_PERCENT = Decimal(100)


class BotAdvisorService:
    def __init__(self, evaluator: MarketEvaluator) -> None:
        self._evaluator = evaluator

    def evaluate(self, request: BotDecisionRequest, allow_short: bool | None = None) -> BotDecisionResult:
        assessment = self._evaluator.assess(
            request_id=request.request_id,
            symbol=request.symbol,
            interval=request.interval,
            candles=request.candles,
            parameters=request.parameters,
            expected_model_version=request.expected_model_version,
            allow_short=allow_short,
        )
        position = request.position
        if position is None:
            return self._decide_from_flat(request, assessment)
        return self._decide_with_position(request, assessment, position)

    # ── flat ──────────────────────────────────────────────────────────────────────

    def _decide_from_flat(self, request: BotDecisionRequest, assessment: Assessment) -> BotDecisionResult:
        direction = assessment.choice.direction
        if direction is Direction.FLAT:
            return self._result(
                request,
                assessment,
                action=BotAction.HOLD,
                direction=Direction.FLAT,
                reason_code=self._flat_reason(assessment),
                levels=None,
                measured=Direction.FLAT,
            )
        # `no_edge` on an OPEN reads oddly out of context, and it is still the right token: the reason
        # codes are a fixed vocabulary .NET switches on, and every one of the others names a condition
        # that did *not* happen here. What justifies an OPEN is the confidence and expected value in the
        # same response, with the rationale spelling out the arithmetic. Inventing an "edge_found" code
        # would put a string in the audit trail that the orchestrator has no case for.
        return self._result(
            request,
            assessment,
            action=BotAction.OPEN,
            direction=direction,
            reason_code="no_edge",
            levels=assessment.levels(direction),
            measured=direction,
        )

    def _flat_reason(self, assessment: Assessment) -> str:
        """Why no position was opened — distinguishing three outcomes a bare FLAT would conflate.

        An operator who sees `confidence_below_minimum` knows to look at the threshold; one who sees
        `no_edge` knows the model saw nothing either way; one who sees `short_not_allowed` knows the
        engine found a trade the configuration forbade. Collapsing them into one token would make a
        misconfigured floor indistinguishable from a quiet market.
        """
        long_side = assessment.candidate(Direction.LONG)
        short_side = assessment.candidate(Direction.SHORT)

        if not assessment.parameters.allow_short and short_side is not None:
            short_qualified = (
                short_side.confidence >= assessment.minimum_confidence
                and short_side.expected_value_atr > 0
            )
            long_qualified = long_side is not None and (
                long_side.confidence >= assessment.minimum_confidence
                and long_side.expected_value_atr > 0
            )
            if short_qualified and not long_qualified:
                return "short_not_allowed"

        best = max(
            (candidate.confidence for candidate in assessment.choice.candidates),
            default=0.0,
        )
        if best < assessment.minimum_confidence:
            return "confidence_below_minimum"
        return "no_edge"

    # ── in a position ─────────────────────────────────────────────────────────────

    def _decide_with_position(
        self,
        request: BotDecisionRequest,
        assessment: Assessment,
        position: OpenPositionInput,
    ) -> BotDecisionResult:
        if position.direction is Direction.FLAT:
            raise InvalidInferenceRequest(
                "position.direction must be LONG or SHORT; a FLAT position is no position, so omit it"
            )
        if position.quantity <= 0:
            raise InvalidInferenceRequest(
                f"position.quantity must be greater than zero, got {position.quantity}"
            )
        if position.entry_price <= 0:
            raise InvalidInferenceRequest(
                f"position.entry_price must be greater than zero, got {position.entry_price}"
            )

        working = self._working_bracket(assessment, position)

        # 1. The bracket, before any opinion about the market.
        #
        # The predicate is the outcome, not `touch.resolved`. On this path the scan window *is* the
        # horizon — `_resolve_bracket` passes `max_horizon=len(high)` because it asks what already
        # happened over the held span — so `resolved` comes back True by construction, TIMEOUT included.
        # TIMEOUT here means "neither barrier touched", which is exactly the position that must stay
        # open, and it carries `exit_price=nan`. Reading `resolved` instead would close every held
        # position on its next tick and report a stop-loss at a price of nan.
        touch = self._resolve_bracket(assessment, position, working)
        if touch.outcome is not Outcome.TIMEOUT:
            reason = (
                "take_profit_touched"
                if touch.outcome is Outcome.TAKE_PROFIT_FIRST
                else "stop_loss_touched"
            )
            rationale = [
                f"{position.direction.name} position reached its "
                f"{'take-profit' if touch.outcome is Outcome.TAKE_PROFIT_FIRST else 'stop-loss'} at "
                f"{touch.exit_price:.8f} after {touch.bars_held} candle(s)"
            ]
            if touch.ambiguous:
                rationale.append(
                    "the resolving candle reached both barriers, so this is the adverse-barrier "
                    "tie-break rather than an observed sequence"
                )
            return self._result(
                request,
                assessment,
                action=BotAction.CLOSE,
                direction=position.direction,
                reason_code=reason,
                levels=working,
                measured=position.direction,
                extra_rationale=tuple(rationale),
            )

        # 2. A bet that never resolved is not a bet still working.
        if position.bars_held >= assessment.max_holding_periods:
            return self._result(
                request,
                assessment,
                action=BotAction.CLOSE,
                direction=position.direction,
                reason_code="max_holding_periods_reached",
                levels=working,
                measured=position.direction,
                extra_rationale=(
                    f"held {position.bars_held} candle(s), at or past the "
                    f"{assessment.max_holding_periods}-candle limit, with neither barrier touched",
                ),
            )

        # 2b. A short held under a configuration that no longer permits shorting.
        if position.direction is Direction.SHORT and not assessment.parameters.allow_short:
            return self._result(
                request,
                assessment,
                action=BotAction.CLOSE,
                direction=position.direction,
                reason_code="short_not_allowed",
                levels=working,
                measured=position.direction,
                extra_rationale=(
                    "a short is open but the configuration no longer allows shorting; the position "
                    "cannot be added to and should be closed out",
                ),
            )

        # 3. A reversal, not merely fading conviction.
        opposite = Direction.SHORT if position.direction is Direction.LONG else Direction.LONG
        if assessment.choice.direction is opposite:
            return self._result(
                request,
                assessment,
                action=BotAction.CLOSE,
                direction=position.direction,
                reason_code="direction_reversed",
                levels=working,
                measured=opposite,
                extra_rationale=(
                    f"the model now favours {opposite.name} at "
                    f"{assessment.confidence_of(opposite):.3f} confidence, against an open "
                    f"{position.direction.name}",
                ),
            )

        # 4. Tighten, never loosen.
        advanced = self._advanced_stop(assessment, position, working)
        if advanced is not None:
            return self._result(
                request,
                assessment,
                action=BotAction.ADJUST_BRACKET,
                direction=position.direction,
                reason_code="trailing_stop_advanced",
                levels=advanced,
                measured=position.direction,
                extra_rationale=(
                    f"price has moved in the position's favour, so the stop can move from "
                    f"{working.stop_loss_price} to {advanced.stop_loss_price} without loosening it; "
                    f"the take-profit is unchanged",
                ),
            )

        return self._result(
            request,
            assessment,
            action=BotAction.HOLD,
            direction=position.direction,
            reason_code="no_edge",
            levels=working,
            measured=position.direction,
            extra_rationale=(
                f"{position.direction.name} position held {position.bars_held} candle(s); neither "
                "barrier touched, the model has not reversed, and the stop cannot be improved",
            ),
        )

    def _working_bracket(self, assessment: Assessment, position: OpenPositionInput) -> LevelsResult:
        """The bracket actually in force: the venue's working prices if any, else the configured ones.

        The distinction matters for a CLOSE. Reporting freshly computed levels for a position whose
        venue bracket sits somewhere else would record the wrong prices against the exit, and the audit
        chain is supposed to be able to reconstruct what the position was actually working with.

        The configured fallback is computed from the *position's* entry, not the latest close, because
        that is where the bracket would have been placed when it opened.
        """
        entry = position.entry_price
        take_profit_percent = assessment.parameters.take_profit_percent
        stop_loss_percent = assessment.parameters.stop_loss_percent
        if position.direction is Direction.LONG:
            default_take_profit = entry * (Decimal(1) + take_profit_percent / _PERCENT)
            default_stop_loss = entry * (Decimal(1) - stop_loss_percent / _PERCENT)
        else:
            default_take_profit = entry * (Decimal(1) - take_profit_percent / _PERCENT)
            default_stop_loss = entry * (Decimal(1) + stop_loss_percent / _PERCENT)

        return LevelsResult(
            entry_price=quantize(entry),
            take_profit_price=quantize(
                position.take_profit_price
                if position.take_profit_price is not None
                else default_take_profit
            ),
            stop_loss_price=quantize(
                position.stop_loss_price if position.stop_loss_price is not None else default_stop_loss
            ),
            atr=quantize(assessment.window.atr),
            risk_reward_ratio=assessment.barriers.risk_reward_ratio,
            take_profit_atr=assessment.barriers.take_profit_atr,
            stop_loss_atr=assessment.barriers.stop_loss_atr,
        )

    @staticmethod
    def _entry_index(assessment: Assessment, position: OpenPositionInput) -> int:
        """Where in the supplied window the position was filled.

        Clamped to the window rather than trusted. `bars_held` is the caller's count, and a bot restarted
        after an outage can legitimately report more bars than it has sent candles for; a bot that has
        just filled reports 0. Clamping scans what is actually here. Not clamping produces a negative
        index that silently wraps to the far end of the array and resolves the bracket against candles
        from before the position existed.
        """
        total = len(assessment.window.candles)
        bars_held = max(0, min(int(position.bars_held), total - 1))
        return total - 1 - bars_held

    def _resolve_bracket(
        self,
        assessment: Assessment,
        position: OpenPositionInput,
        working: LevelsResult,
    ) -> TouchResult:
        """Did the working bracket resolve over the candles the position has been held for?

        Answered by the shared `first_touch`, so an ambiguous candle is booked against the trade here
        exactly as it is in the labels the model was fitted to. The horizon is the held span itself —
        this asks what already happened, not what might.

        Reported rather than assumed: `OpenPosition`'s bracket prices are optional, so .NET may be
        managing the exit itself, and the engine is advisory either way. A CLOSE here means "your
        bracket is through", not "I closed it".
        """
        entry_index = self._entry_index(assessment, position)
        high, low, open_ = assessment.window.path_from(entry_index)
        return first_touch(
            high=high,
            low=low,
            open_=open_,
            entry_index=0,
            take_profit_price=float(working.take_profit_price),
            stop_loss_price=float(working.stop_loss_price),
            direction=position.direction,
            max_horizon=len(high),
        )

    def _advanced_stop(
        self,
        assessment: Assessment,
        position: OpenPositionInput,
        working: LevelsResult,
    ) -> LevelsResult | None:
        """A stop trailed from the best price the position has seen, or None if it cannot improve.

        Trailed from the high-water mark rather than the latest close, so a stop that has been advanced
        does not retreat when price pulls back — which is the entire point of a trailing stop and the one
        property a naive "recompute from the current close" implementation gets wrong.

        Three guards, each of which alone would make this unsafe to ship:
        * the new stop must be *better* than the working one, so this can only ever reduce risk;
        * it must still sit on the correct side of the current price, so advancing it does not
          manufacture an instant stop-out;
        * it must sit on the correct side of the entry or beyond it — a trail that has not yet reached
          break-even is left alone, because tightening into an unprofitable position converts ordinary
          noise into a realised loss.
        """
        held = assessment.window.candles[self._entry_index(assessment, position) :]
        if not held:
            return None

        stop_loss_percent = assessment.parameters.stop_loss_percent
        last_close = assessment.window.entry_price
        entry = position.entry_price

        if position.direction is Direction.LONG:
            watermark = max(candle.high for candle in held)
            candidate = quantize(watermark * (Decimal(1) - stop_loss_percent / _PERCENT))
            improves = candidate > working.stop_loss_price
            safe = candidate < last_close
            profitable = candidate >= entry
        else:
            watermark = min(candle.low for candle in held)
            candidate = quantize(watermark * (Decimal(1) + stop_loss_percent / _PERCENT))
            improves = candidate < working.stop_loss_price
            safe = candidate > last_close
            profitable = candidate <= entry

        if not (improves and safe and profitable):
            return None

        return LevelsResult(
            entry_price=working.entry_price,
            take_profit_price=working.take_profit_price,
            stop_loss_price=candidate,
            atr=working.atr,
            risk_reward_ratio=working.risk_reward_ratio,
            take_profit_atr=working.take_profit_atr,
            stop_loss_atr=working.stop_loss_atr,
        )

    # ── assembly ──────────────────────────────────────────────────────────────────

    def _result(
        self,
        request: BotDecisionRequest,
        assessment: Assessment,
        action: str,
        direction: Direction,
        reason_code: str,
        levels: LevelsResult | None,
        measured: Direction,
        extra_rationale: tuple[str, ...] = (),
    ) -> BotDecisionResult:
        """One place that fills the response, so no branch can forget the model stamp or the digest."""
        window = assessment.window
        return BotDecisionResult(
            request_id=request.request_id,
            symbol=window.symbol,
            interval=window.interval,
            action=action,
            direction=direction,
            reason_code=reason_code,
            confidence=assessment.confidence_of(measured),
            probabilities=assessment.probabilities(measured),
            expected_value=assessment.expected_value_of(measured),
            candle_open_time=window.candle_open_time,
            valid_until=window.valid_until,
            model=assessment.stamp,
            input_digest_sha256=window.input_digest_sha256,
            levels=levels,
            rationale=assessment.choice.rationale + extra_rationale,
            warning=assessment.warning,
            barrier_extrapolated=assessment.barrier_extrapolated,
            processing_milliseconds=assessment.elapsed_milliseconds,
        )
