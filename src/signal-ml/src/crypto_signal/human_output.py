from __future__ import annotations

from pathlib import Path
from typing import Any


def number(value: int | float, decimals: int = 0) -> str:
    return f"{value:,.{decimals}f}"


def percent(value: float, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.2%}"


def duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1_000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} seconds"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {remaining:.0f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m"


def format_download_summary(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "DOWNLOAD COMPLETE",
            "-----------------",
            f"Market:       {payload['symbol']} ({payload['interval']} candles)",
            f"Rows:         {payload['rows']:,}",
            f"First candle: {payload['first_candle']}",
            f"Last candle:  {payload['last_candle']}",
            f"Time gaps:    {payload['gap_count']:,}",
            f"Saved CSV:    {payload['path']}",
        ]
    )


def _classification_lines(title: str, metrics: dict[str, Any]) -> list[str]:
    report = metrics["report"]
    return [
        title,
        f"  Ordinary accuracy: {percent(float(report['accuracy']))}",
        f"  Balanced accuracy: {percent(float(metrics['balanced_accuracy']))}",
        f"  Macro F1 score:     {percent(float(metrics['macro_f1']))}",
        f"  Log loss:           {float(metrics['log_loss']):.4f} (lower is better)",
        "  Per class:",
        f"    SELL  precision={percent(float(report['SELL']['precision']))} "
        f"recall={percent(float(report['SELL']['recall']))}",
        f"    HOLD  precision={percent(float(report['HOLD']['precision']))} "
        f"recall={percent(float(report['HOLD']['recall']))}",
        f"    BUY   precision={percent(float(report['BUY']['precision']))} "
        f"recall={percent(float(report['BUY']['recall']))}",
    ]


def _backtest_lines(name: str, metrics: dict[str, Any]) -> list[str]:
    return [
        name,
        f"  Total return:       {percent(float(metrics['cumulative_return']), signed=True)}",
        f"  Annualized return:  {percent(float(metrics['cagr']), signed=True)}",
        f"  Maximum drawdown:   {percent(float(metrics['max_drawdown']))}",
        f"  Sharpe ratio:       {float(metrics['sharpe_zero_rate']):.3f}",
        f"  Market exposure:    {percent(float(metrics['exposure']))}",
        f"  Position changes:   {int(metrics['position_changes']):,}",
    ]


def format_training_summary(metadata: dict[str, Any], artifact_dir: Path) -> str:
    rows = metadata["rows"]
    counts = metadata["class_counts"]
    total_classes = sum(int(value) for value in counts.values())
    cv = metadata["walk_forward_cv"]
    holdout = metadata["strict_holdout"]
    lines = [
        "TRAINING AND BACKTEST COMPLETE",
        "==============================",
        f"Market:                {metadata['symbol']} ({metadata['interval']} candles)",
        f"Data range:            {metadata['data_range']['first']} to {metadata['data_range']['last']}",
        f"Raw candles:           {rows['raw']:,}",
        f"Usable labeled rows:   {rows['supervised']:,}",
        f"Development rows:      {rows['development']:,}",
        f"Safety/purge gap:      {rows['purged_gap']:,}",
        f"Untouched test rows:   {rows['strict_holdout']:,}",
        f"Features per candle:   {len(metadata['feature_columns']):,}",
        f"Training compute time: {duration(float(metadata.get('duration_seconds', 0.0)))}",
        "",
        "TARGET CLASS BALANCE",
        f"  SELL: {int(counts.get('-1', 0)):,} "
        f"({int(counts.get('-1', 0)) / total_classes:.1%})",
        f"  HOLD: {int(counts.get('0', 0)):,} "
        f"({int(counts.get('0', 0)) / total_classes:.1%})",
        f"  BUY:  {int(counts.get('1', 0)):,} "
        f"({int(counts.get('1', 0)) / total_classes:.1%})",
        "",
        f"WALK-FORWARD VALIDATION ({len(cv['folds'])} chronological folds)",
    ]
    for fold in cv["folds"]:
        lines.append(
            f"  Fold {fold['fold']}: train={fold['train_rows']:,}, "
            f"validate={fold['validation_rows']:,}, "
            f"balanced accuracy={percent(float(fold['balanced_accuracy']))}, "
            f"macro F1={percent(float(fold['macro_f1']))}"
        )
    lines.extend([""] + _classification_lines("Combined validation metrics", cv["combined"]))
    lines.extend([""] + _classification_lines("STRICT UNTOUCHED TEST METRICS", holdout["classification"]))
    lines.extend([""] + _backtest_lines("ML STRATEGY (after configured costs)", holdout["backtest"]["strategy"]))
    lines.extend([""] + _backtest_lines("BUY AND HOLD BENCHMARK", holdout["backtest"]["buy_and_hold"]))
    lines.extend(
        [
            "",
            f"Artifacts: {artifact_dir}",
            "Important: historical results do not guarantee future profit.",
        ]
    )
    return "\n".join(lines)


def format_signal_summary(payload: dict[str, Any]) -> str:
    probabilities = payload["probabilities"]
    return "\n".join(
        [
            "LATEST RESEARCH SIGNAL",
            "----------------------",
            f"Market:        {payload['symbol']} ({payload['interval']})",
            f"Candle time:   {payload['candle_open_time_utc']}",
            f"Close price:   {float(payload['close_price']):,.8f}",
            f"Signal:        {payload['signal']}",
            f"SELL chance:   {percent(float(probabilities['SELL']))}",
            f"HOLD chance:   {percent(float(probabilities['HOLD']))}",
            f"BUY chance:    {percent(float(probabilities['BUY']))}",
            f"Min confidence: {percent(float(payload['probability_threshold']))}",
            f"Data source:   {payload['data_source']}",
            f"Meaning:       {payload['sell_semantics']}",
            "Warning: research output only; no real order was placed.",
        ]
    )


def format_barrier_download_summary(payload: dict[str, Any]) -> str:
    """One line per pooled symbol, because the interesting failure is a short row count on one of them."""
    lines = [
        "CANDLE DOWNLOAD COMPLETE",
        "========================",
        f"Interval: {payload['interval']} | symbols: {len(payload['symbols'])}",
        "",
    ]
    for symbol, span in payload["symbols"].items():
        lines.append(
            f"  {symbol:<10} {span['candles']:>8,} candles  "
            f"{span['start'][:10]} to {span['end'][:10]}  gaps={span['gap_count']:,}"
        )
    lines.extend(["", f"Saved under: {payload['data_dir']}"])
    return "\n".join(lines)


def format_barrier_training_summary(metadata: dict[str, Any]) -> str:
    """What was trained, how well it scored, and how far its confidence reaches.

    The reach line is the one that stops a wasted afternoon: a model whose 99th-percentile confidence is
    0.69 will never satisfy a 0.75 minimum, and the symptom of setting one is a bot that reports FLAT
    forever rather than an error anyone can search for.
    """
    barrier = metadata["barrier"]
    lines = [
        "BARRIER TRAINING COMPLETE",
        "=========================",
        f"Interval:        {metadata['interval']} candles",
        f"Pooled symbols:  {', '.join(metadata['symbols'])}",
        f"Bundles written: {len(metadata['bundles'])}",
        f"Horizon:         {barrier['max_horizon']} candles"
        f" | ATR window: {barrier['atr_window']}"
        f" | grid: {', '.join(f'{value:g}' for value in barrier['grid_atr'])} ATR",
        f"Elapsed:         {duration(float(metadata['elapsed_seconds']))}",
    ]
    for bundle in metadata["bundles"]:
        serves = "every symbol at this interval" if bundle["is_pooled"] else ", ".join(bundle["symbols"])
        holdout = bundle["strict_holdout"]
        combined = bundle["walk_forward_cv"]["combined"]
        calibration = bundle["calibration"]
        reach = (calibration.get("reach") or {}) if isinstance(calibration, dict) else {}
        lines.extend(
            [
                "",
                f"{bundle['stem']}.joblib",
                f"  Serves:            {serves}",
                f"  Labeled rows:      {bundle['rows']:,} over {bundle['candles']:,} candles",
                f"  Features:          {bundle['feature_count']:,}",
                f"  Walk-forward:      log loss {float(combined['log_loss']):.4f}, "
                f"balanced accuracy {percent(float(combined['balanced_accuracy']))}",
                f"  Strict holdout:    log loss {float(holdout['log_loss']):.4f}, "
                f"balanced accuracy {percent(float(holdout['balanced_accuracy']))} "
                f"over {bundle['holdout_rows']:,} rows",
                # `selected` is what shipped; `method` is what was attempted. The report keeps both
                # because "isotonic" appearing alone reads as "this model is calibrated" even on the runs
                # where the correction was measured, judged worse, and discarded.
                f"  Calibration:       shipped {calibration['selected']} "
                f"(attempted {calibration['method']})",
            ]
        )
        if reach.get("ceiling") is not None:
            attainment = reach.get("attainment") or {}
            reachable = ", ".join(
                f"{threshold}->{percent(float(share))}" for threshold, share in sorted(attainment.items())
            )
            lines.append(f"  Confidence reach:  ceiling {float(reach['ceiling']):.3f} | {reachable}")
        lines.extend(_bracket_lines(bundle.get("bracket_backtest") or {}))
    lines.extend(
        [
            "",
            f"Registry: {metadata['model_dir']}",
            "Report:   REPORT.md in that directory",
            "Important: historical results do not guarantee future profit, and a signal is evidence,",
            "not authorization. The orchestrator decides whether to act on one.",
        ]
    )
    return "\n".join(lines)


def _bracket_lines(backtest: dict[str, Any]) -> list[str]:
    per_symbol = backtest.get("symbols") or {}
    if not per_symbol:
        return []
    lines = [
        f"  Bracket backtest:  {backtest['take_profit_atr']:g} ATR target vs "
        f"{backtest['stop_loss_atr']:g} ATR stop, taken above "
        f"{percent(float(backtest['minimum_confidence']))} confidence"
    ]
    for symbol, result in per_symbol.items():
        statistics = result["trades"]
        profit_factor = statistics["profit_factor"]
        lines.append(
            f"    {symbol:<10} {statistics['trades']:>6,} trades  "
            f"win {percent(float(statistics['win_rate_resolved']))}  "
            f"expectancy {float(statistics['expectancy_atr']):+.4f} ATR  "
            f"fee {float(statistics['mean_fee_atr']):.3f} ATR  "
            f"profit factor {'n/a' if profit_factor is None else f'{float(profit_factor):.2f}'}"
        )
        # The fee alone does not say whether it was the fee that did the damage. These two rungs do: a win
        # rate above the before-fees bar and below the net one is a model with a real directional edge that
        # the venue is eating, which is a bracket to widen rather than a model to retrain. Printed only when
        # both exist — a side with no realised win has no magnitude to solve against, and inventing one from
        # the requested distance is how a yardstick starts flattering.
        before_fees = statistics.get("break_even_win_rate_before_fees")
        net = statistics.get("break_even_win_rate")
        if before_fees is not None and net is not None:
            lines.append(
                f"    {'':<10} break-even: {percent(float(before_fees))} before fees, "
                f"{percent(float(net))} net"
            )
    return lines


def format_lstm_training_summary(metadata: dict[str, Any]) -> str:
    """A plain report for the experimental LSTM run.

    Deliberately modest: the LSTM is additive and unproven, so the headline is the cost-aware backtest
    versus buy-and-hold, not a victory lap. See `docs/ml-improvement-plan.md` for why it must clear the
    same bar as the tree before promotion.
    """
    backtest = (metadata.get("strict_holdout") or {}).get("backtest", {})
    strategy = backtest.get("strategy", {})
    benchmark = backtest.get("buy_and_hold", {})
    lines = [
        "LSTM TRAINING COMPLETE (experimental)",
        "=====================================",
        f"Interval:        {metadata['interval']} candles",
        f"Pooled symbols:  {', '.join(metadata['symbols'])}",
        f"Lookback:        {metadata.get('lookback')} candles",
        f"Label rows:      {metadata.get('label_rows'):,}",
        f"Horizon:         {metadata.get('max_horizon')} candles | ATR window: {metadata.get('atr_window')}",
        "",
        "Strict holdout backtest (net of fees + slippage)",
        f"  Strategy cumulative return:  {strategy.get('cumulative_return', float('nan')):.2%}",
        f"  Buy & hold cumulative return: {benchmark.get('cumulative_return', float('nan')):.2%}",
        f"  Strategy Sharpe:              {strategy.get('sharpe_zero_rate', float('nan')):.3f}",
        f"  Strategy max drawdown:        {strategy.get('max_drawdown', float('nan')):.2%}",
        "",
        "WARNING: experimental recurrent model. It is not promoted over the gradient-boosted bundle",
        "unless it clears the same purged-holdout, cost-aware backtest bar. See docs/ml-improvement-plan.md.",
    ]
    return "\n".join(lines)


def format_barrier_signal_summary(payload: dict[str, Any]) -> str:
    """The advisory answer for one requested bet, in the order an operator reads it.

    Direction first, then the three prices, then how sure the model is and what the bet is worth — a
    confidence without an expected value is not actionable, because a 70% chance on a 1:2 bet loses money.
    """
    levels = payload["levels"]
    requested = payload["requested"]
    hypothetical = bool(payload.get("levels_are_hypothetical"))
    quoted = payload.get("quoted_direction", "LONG")
    lines = [
        "TRADE SIGNAL",
        "============",
        f"Market:        {payload['symbol']} ({payload['interval']})",
        f"Candle time:   {payload['candle_open_time']}",
        f"Direction:     {payload['direction']}",
    ]
    if hypothetical:
        # FLAT is an answer, not a failure, and the levels below are the bet that was *considered*. Printing
        # them under the same heading a live signal uses is how a reader ends up placing the trade the model
        # declined to endorse. The reason comes from the selector's own rationale rather than being restated
        # here: a confidence floor, a negative expected value and a disallowed short are three different
        # refusals, and guessing which one applied is how a config mistake looks like a quiet market.
        reason = next(
            (
                entry
                for entry in payload.get("rationale", ())
                if entry.startswith(("flat:", "no direction"))
            ),
            "no bet qualified",
        )
        lines.extend(
            [
                "",
                f"No bet taken — {reason}.",
                f"The prices below are the {quoted} the model priced and rejected, shown for context.",
            ]
        )
    lines.extend(
        [
            "",
            f"Entry:         {levels['entry_price']}",
            f"Take profit:   {levels['take_profit_price']}  "
            f"(+{requested['take_profit_percent']:g}%, {requested['take_profit_atr']:.2f} ATR)",
            f"Stop loss:     {levels['stop_loss_price']}  "
            f"(-{requested['stop_loss_percent']:g}%, {requested['stop_loss_atr']:.2f} ATR)",
            f"Reward:risk:   {float(levels['risk_reward_ratio']):.2f} | ATR {levels['atr']}",
            "",
        ]
    )
    if hypothetical:
        lines.append("Confidence:    n/a — no bet was chosen")
    else:
        lines.extend(
            [
                f"Confidence:    {percent(float(payload['confidence']))} "
                "(calibrated chance the target is reached before the stop)",
                f"Expected value: {float(payload['expected_value_atr']):+.4f} ATR per unit risked",
            ]
        )
    lines.extend(
        [
            f"Answered by:   {payload['bundle']} "
            f"(calibration: {payload['calibration_method'] or 'unrecorded'})",
            "",
            "Both sides priced:",
        ]
    )
    for candidate in payload["candidates"]:
        probabilities = candidate["probabilities"]
        lines.append(
            f"  {candidate['direction']:<6} confidence {percent(float(candidate['confidence']))}  "
            f"expected {float(candidate['expected_value_atr']):+.4f} ATR  "
            f"break-even {percent(float(candidate['break_even']))}  "
            f"timeout {percent(float(probabilities['timeout']))}"
        )
    if payload.get("rationale"):
        # The selector's own trail, verbatim. It is the only place a reader sees the short side being
        # excluded by policy rather than by the numbers.
        lines.extend(["", "Rationale:"])
        lines.extend(f"  {entry}" for entry in payload["rationale"])
    if payload.get("warning"):
        lines.extend(["", f"Warning: {payload['warning']}"])
    lines.extend(
        [
            "",
            "Advisory output only. No order was placed and none will be placed by this command.",
        ]
    )
    return "\n".join(lines)
