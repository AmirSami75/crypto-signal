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
