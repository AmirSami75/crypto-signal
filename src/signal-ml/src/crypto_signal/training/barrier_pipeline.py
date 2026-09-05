"""Training the barrier-conditional model: candles in, a servable registry out.

The pipeline's shape is driven by one requirement — **the model that ships must be the model that was
measured.** Everything a caller will later act on (the calibrated confidence, the confidence ceiling,
the attainment table the risk engine thresholds against) is a property of one fitted artifact, so the
numbers in `metadata.json` have to come from that same artifact rather than from a stand-in that was
refitted on more data afterwards.

That is why the split is four blocks deep, and why they are cut in this order:

```text
|<------------------- development ------------------->|  gap  |<-- strict holdout -->|
|<-- fit -->| gap |<- calibrate ->| gap |<- assess -->|
```

The strict holdout is carved off **first**, by timestamp, and nothing downstream fits, calibrates or
*selects* on it. Inside what remains, `fit_calibrated_model` fits the estimator, fits the calibration
correction on later candles, and decides on later candles still whether the correction earned its place.
The returned model is then scored once on the strict holdout, and that score is what the report claims.

The legacy pipeline refits a "production model" on every labelled row before saving it. That is
tempting — more data is more data — but it makes `confidence_ceiling` and `attainment` describe a model
that never ships, and those two numbers are exactly what the .NET risk engine will refuse trades on.

Both directions of every bet are labelled, so the short side needs no second model: the same estimator
is asked with `direction_sign` flipped and the same two barrier distances, and its `+1` class means "the
take-profit came first" from that bet's own point of view. Mirroring the *barriers* instead — reading a
long's labels backwards for the short — would score every candle that straddles both barriers as a short
win, when the adverse-wins rule makes it a loss for both sides. See `labeling.triple_barrier` and
`modeling.direction`, which each explain the trap from their own end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .. import __version__
from ..config import AppConfig, BarrierConfig
from ..data import fetch_historical_ohlcv, load_ohlcv, save_ohlcv, validate_ohlcv
from ..domain import BarrierPair, Direction, OutcomeProbabilities, expected_value, percent_from_atr
from ..evaluation import BracketCosts, run_bracket_backtest
from ..features import WARMUP_COLUMNS, build_features
from ..labeling import (
    BARRIER_FEATURE_COLUMNS,
    BarrierDataset,
    barrier_grid,
    build_barrier_dataset,
)
from ..log_setup import get_logger
from ..modeling import (
    ALL_CLASSES,
    CalibrationReport,
    aligned_probabilities,
    classification_metrics,
    fit_calibrated_model,
    walk_forward_validation_by_time,
)
from ..modeling.splitting import chronological_blocks
from .artifacts import write_json, write_text

logger = get_logger(__name__)

#: The pooled bundle's filename. The engine reads intent out of this name: `_pooled_<interval>` offers to
#: answer for symbols the model never saw, while `<SYMBOL>_<interval>` stays scoped to its own pair even
#: when it was trained on a pooled set. Getting this wrong is not a cosmetic error — it decides whether a
#: request for an unlisted market is answered or refused.
POOLED_STEM = "_pooled"

#: Column offsets into an `ALL_CLASSES`-ordered probability row. Derived from the array rather than written
#: as `2` and `0`, so that reordering the classes moves these with it instead of leaving a literal that has
#: quietly started to mean "timeout". `OutcomeProbabilities.from_class_probabilities` reads the same row the
#: same way, and `_expected_values` checks the two against each other on every call.
WIN_CLASS_INDEX = int(np.flatnonzero(ALL_CLASSES == 1)[0])

#: The expected-value floor a backtest decision has to clear, in ATR units. Zero, and the same number
#: `choose_direction` defaults `minimum_expected_value_atr` to: a bet that does not pay for how often
#: it loses is not a bet either path takes. Named here rather than written as a bare `0.0` so the two
#: floors are visibly the same decision rather than coincidentally equal literals.
MINIMUM_EXPECTED_VALUE_ATR = 0.0
LOSS_CLASS_INDEX = int(np.flatnonzero(ALL_CLASSES == -1)[0])

#: Features are fitted at single precision. The estimator bins its inputs to `uint8` before it splits on
#: them, so the eighth significant digit cannot change a threshold, and the pooled frame is large enough
#: that halving it is the difference between fitting in memory and fitting in swap.
FIT_DTYPE = np.float32


@dataclass(frozen=True, slots=True)
class TrainedBundle:
    """One artifact, its measurements, and where it landed.

    `calibration` is the live report object, not the dictionary already inside `metrics`: the report knows
    how to render its own reliability and reach tables (`CalibrationReport.markdown`), and re-deriving
    those tables from the serialized form in the pipeline would put the thin-bin caveat and the
    unreachable-threshold marker in a second place that can disagree with the first.
    """

    stem: str
    path: Path
    symbols: tuple[str, ...]
    is_pooled: bool
    rows: int
    candles: int
    metrics: dict[str, Any]
    calibration: CalibrationReport


def download_barrier_data(config: AppConfig, refresh: bool = False) -> dict[str, pd.DataFrame]:
    """Every pooled symbol's candles, from disk or from the exchange.

    Runs on the host, never in the container: only `testnet.binance.vision` is reachable from inside the
    compose network and the mainnet history the model is trained on is not. A symbol that is neither on
    disk nor downloadable is an error rather than a silent omission — a pooled bundle that quietly
    trained on four of seven markets would still report seven in `metadata["symbols"]`.
    """
    frames: dict[str, pd.DataFrame] = {}
    for symbol in config.market.symbols:
        path = config.market.csv_path(symbol)
        if refresh or not path.exists():
            logger.info("Downloading candles | symbol=%s | interval=%s", symbol, config.market.interval)
            frame = fetch_historical_ohlcv(
                symbol,
                config.market.interval,
                config.market.start,
                end=config.market.end,
                proxy_url=config.network.proxy_url,
                timeout=config.network.timeout_seconds,
            )
            save_ohlcv(frame, path)
        else:
            frame = load_ohlcv(path, config.market.interval)
        quality = validate_ohlcv(frame, config.market.interval)
        logger.info(
            "Candles ready | symbol=%s | rows=%s | range=%s..%s | gaps=%s",
            symbol,
            f"{len(frame):,}",
            frame["timestamp"].iloc[0].isoformat(),
            frame["timestamp"].iloc[-1].isoformat(),
            quality["gap_count"],
        )
        frames[symbol] = frame
    return frames


def download_barrier_candles(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    """`download_barrier_data`, reported rather than returned — the CLI's `download` command.

    Kept separate because the training path wants the frames and the command wants a summary it can print,
    and a function that returns both invites a caller to hold seven full candle frames it never reads.
    """
    frames = download_barrier_data(config, refresh=refresh)
    return {
        "interval": config.market.interval,
        "data_dir": str(config.market.data_dir),
        "symbols": {
            symbol: {
                "candles": int(len(frame)),
                "start": frame["timestamp"].iloc[0].isoformat(),
                "end": frame["timestamp"].iloc[-1].isoformat(),
                "gap_count": int(validate_ohlcv(frame, config.market.interval)["gap_count"]),
            }
            for symbol, frame in frames.items()
        },
    }


def train_barrier_model(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    """Train the pooled model plus any per-symbol overrides, and write the serving registry.

    Returns the metadata it wrote, so the CLI can render a summary without re-reading the file.
    """
    started = time.perf_counter()
    barrier = config.barrier
    model_dir = config.output.model_dir
    model_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Barrier training started | symbols=%s | interval=%s | max_horizon=%s | pairs_per_candle=%s",
        ",".join(config.market.symbols),
        config.market.interval,
        barrier.max_horizon,
        barrier.pairs_per_candle,
    )
    frames = download_barrier_data(config, refresh=refresh)

    pooled = _train_one(
        stem=f"{POOLED_STEM}_{config.market.interval}",
        frames=frames,
        config=config,
        is_pooled=True,
    )
    bundles = [pooled]

    # An override is an *optimisation* over the pooled bundle, not a prerequisite for serving its symbol:
    # the registry falls back to pooled when one is missing or broken. So a failed override is logged and
    # skipped rather than allowed to abort a run whose primary artifact already succeeded.
    for symbol in barrier.per_symbol_overrides:
        try:
            bundles.append(
                _train_one(
                    stem=f"{symbol}_{config.market.interval}",
                    frames={symbol: frames[symbol]},
                    config=config,
                    is_pooled=False,
                )
            )
        except Exception:
            logger.exception(
                "Per-symbol override failed | symbol=%s | the pooled bundle still serves it", symbol
            )

    metadata = {
        "project_version": __version__,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "interval": config.market.interval,
        "symbols": list(config.market.symbols),
        "model_dir": str(model_dir),
        "barrier": {
            "max_horizon": barrier.max_horizon,
            "pairs_per_candle": barrier.pairs_per_candle,
            "atr_window": barrier.atr_window,
            "grid_atr": list(barrier.grid_atr),
            "risk_reward_bounds": [barrier.min_risk_reward, barrier.max_risk_reward],
            "holdout_fraction": barrier.holdout_fraction,
            "calibration_blocks": list(barrier.calibration_blocks),
            "calibration_method": barrier.calibration_method,
            "allow_short": barrier.allow_short,
            "backtest_take_profit_atr": barrier.backtest_take_profit_atr,
            "backtest_stop_loss_atr": barrier.backtest_stop_loss_atr,
            "backtest_minimum_confidence": barrier.backtest_minimum_confidence,
        },
        "data_range": {
            symbol: {
                "start": frame["timestamp"].iloc[0].isoformat(),
                "end": frame["timestamp"].iloc[-1].isoformat(),
                "candles": int(len(frame)),
            }
            for symbol, frame in frames.items()
        },
        "bundles": [
            {
                "stem": bundle.stem,
                "path": str(bundle.path),
                "symbols": list(bundle.symbols),
                "is_pooled": bundle.is_pooled,
                "rows": bundle.rows,
                "candles": bundle.candles,
                **bundle.metrics,
            }
            for bundle in bundles
        ],
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }
    # Both files land in the registry directory, next to the artifacts they describe. The registry globs
    # `*.joblib` and ignores everything else, so this is safe, and a reader who found a bundle has the
    # numbers behind it in the same place rather than in a sibling directory that can fall out of step.
    write_json(model_dir / "metadata.json", metadata)
    write_text(model_dir / "REPORT.md", _report_markdown(metadata, bundles))
    logger.info(
        "Barrier training finished | bundles=%s | elapsed=%.1fs | report=%s",
        len(bundles),
        metadata["elapsed_seconds"],
        model_dir / "REPORT.md",
    )
    return metadata


def _report_markdown(metadata: dict[str, Any], bundles: list[TrainedBundle]) -> str:
    """The document a human reads before letting a bot act on this model.

    Ordered by what a reader has to decide, not by the order the pipeline computed things. The first
    question is "which markets does this answer for, and how far does its confidence actually reach" —
    because a threshold above the reach produces silence rather than caution — so coverage and the
    calibration tables come before the per-fold detail. The bracket backtest is reported per symbol and
    never averaged: one number over seven markets hides the market that lost on every trade.
    """
    barrier = metadata["barrier"]
    lines = [
        "# Barrier model run report",
        "",
        f"Generated: {metadata['trained_at_utc']}",
        "",
        f"Interval: `{metadata['interval']}`  ",
        f"Pooled symbols: {', '.join(f'`{symbol}`' for symbol in metadata['symbols'])}  ",
        f"Bundles written: {len(bundles)} in `{metadata['model_dir']}`  ",
        f"Elapsed: {metadata['elapsed_seconds']:,.1f}s",
        "",
        "Every row carries its own `(take_profit_atr, stop_loss_atr)` pair and a `direction_sign` as",
        "features, and its label is stated from that bet's own point of view: `1` means the take-profit",
        "came first, for a short exactly as for a long. One model therefore answers any requested",
        "bracket on either side — the two sides differ by `direction_sign`, not by swapping the two",
        "distances, because swapping them would score a candle that straddles both barriers as a short",
        "win when the adverse-wins rule makes it a loss for both sides.",
        "",
        "## Barrier configuration",
        "",
        "| Setting | Value |",
        "|---|---:|",
        f"| Maximum horizon | {barrier['max_horizon']} candles |",
        f"| ATR window | {barrier['atr_window']} |",
        f"| Barrier grid (ATR) | {', '.join(f'{value:g}' for value in barrier['grid_atr'])} |",
        f"| Risk:reward bounds | {barrier['risk_reward_bounds'][0]:g} – "
        f"{barrier['risk_reward_bounds'][1]:g} |",
        f"| Pairs sampled per candle | {barrier['pairs_per_candle']} |",
        f"| Strict holdout fraction | {barrier['holdout_fraction']:.0%} |",
        f"| Calibration blocks | {', '.join(f'{value:.0%}' for value in barrier['calibration_blocks'])} |",
        f"| Calibration attempted | `{barrier['calibration_method']}` |",
        f"| Short side measured | {'yes' if barrier['allow_short'] else 'no'} |",
        f"| Backtest bracket | {barrier['backtest_take_profit_atr']:g} ATR target vs "
        f"{barrier['backtest_stop_loss_atr']:g} ATR stop, above "
        f"{barrier['backtest_minimum_confidence']:.0%} confidence |",
        "",
        "## Candle coverage",
        "",
        "| Symbol | From | To | Candles |",
        "|---|---|---|---:|",
    ]
    for symbol, span in metadata["data_range"].items():
        lines.append(
            f"| `{symbol}` | {span['start'][:10]} | {span['end'][:10]} | {span['candles']:,} |"
        )

    for bundle in bundles:
        lines.extend(_bundle_section(bundle))

    lines.extend(
        [
            "",
            "---",
            "",
            "These are research measurements, not a promise of future performance. The strict holdout was",
            "scored once, by the artifact that shipped; re-scoring it after a change turns it into a",
            "selection set and the numbers above stop meaning what they say. Every equity figure assumes",
            "one full position at a time, so a bot trading a fixed quote notional will not reproduce it —",
            "the per-trade statistics are the transferable ones. A signal is evidence, not authorization.",
            "",
        ]
    )
    return "\n".join(lines)


def _bundle_section(bundle: TrainedBundle) -> list[str]:
    """One artifact's measurements: what it was fitted on, how it scored, what it would have earned."""
    metrics = bundle.metrics
    holdout = metrics["strict_holdout"]
    cv = metrics["walk_forward_cv"]
    combined = cv["combined"]
    coverage = "every symbol at this interval (pooled)" if bundle.is_pooled else ", ".join(bundle.symbols)
    lines = [
        "",
        f"## `{bundle.path.name}`",
        "",
        f"Serves: {coverage}  ",
        f"Trained on: {bundle.rows:,} labelled rows over {bundle.candles:,} candles, "
        f"{metrics['feature_count']} features  ",
        f"Split: {metrics['development_rows']:,} development / {metrics['holdout_rows']:,} strict holdout  ",
        # Read off the report rather than out of the serialized dict: `method` there is what was
        # *attempted* and `selected` is what shipped, and a reader of this line who has them the wrong way
        # round concludes the model is calibrated when it is not.
        f"Calibration shipped: `{bundle.calibration.selected}` "
        f"(attempted `{bundle.calibration.method}`)",
        "",
        "Label balance — `1` take-profit first, `-1` stop-loss first, `0` neither inside the horizon:",
        "",
        "| Label | Rows | Share |",
        "|---|---:|---:|",
    ]
    total = sum(metrics["class_counts"].values()) or 1
    for label in ("1", "0", "-1"):
        count = metrics["class_counts"].get(label, 0)
        lines.append(f"| `{label}` | {count:,} | {count / total:.1%} |")

    lines.extend(
        [
            "",
            "### Scores",
            "",
            f"Walk-forward is {len(cv['folds'])} purged folds over the development block, split on candle",
            f"boundaries with a {cv['gap']}-{cv['gap_unit'][:-1]} gap. The strict holdout is later candles",
            "still, scored once by the artifact that shipped.",
            "",
            "| Metric | Walk-forward | Strict holdout |",
            "|---|---:|---:|",
            f"| Log loss | {combined['log_loss']:.4f} | {holdout['log_loss']:.4f} |",
            f"| Balanced accuracy | {combined['balanced_accuracy']:.2%} | "
            f"{holdout['balanced_accuracy']:.2%} |",
            f"| Macro F1 | {combined['macro_f1']:.2%} | {holdout['macro_f1']:.2%} |",
            "",
            "Balanced accuracy is reported for continuity, not as the target. It rewards predicting the",
            "scarce class more often, which is the distortion calibration exists to remove — log loss is",
            "the number that tracks whether a confidence can be thresholded on.",
        ]
    )

    backtest = metrics.get("bracket_backtest") or {}
    per_symbol = backtest.get("symbols") or {}
    if per_symbol:
        lines.extend(
            [
                "",
                "### Holdout bracket backtest",
                "",
                f"One fixed bracket — {backtest['take_profit_atr']:g} ATR take-profit against "
                f"{backtest['stop_loss_atr']:g} ATR stop — taken whenever confidence clears "
                f"{backtest['minimum_confidence']:.0%}, walked candle by candle over the holdout window.",
                "Fills are at the next candle's open with slippage charged both ways, and an ambiguous",
                "candle (high touches the target *and* low touches the stop) is settled as the loss,",
                "because intrabar order is unknowable and optimism here invents profit that never existed.",
                "",
                "| Symbol | Trades | Win rate | Break-even: asked | before fees | net | Edge | "
                "Win (ATR) | Loss (ATR) | Fee (ATR) | Expectancy (ATR) | Bars held |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for symbol, result in per_symbol.items():
            statistics = result["trades"]
            lines.append(
                f"| `{symbol}` | {statistics['trades']:,} | {statistics['win_rate_resolved']:.1%} | "
                f"{_percent_or_na(statistics['break_even_win_rate_requested'])} | "
                f"{_percent_or_na(statistics['break_even_win_rate_before_fees'])} | "
                f"{_percent_or_na(statistics['break_even_win_rate'])} | "
                f"{_percent_or_na(statistics['edge_over_break_even'], signed=True)} | "
                f"{_number_or_na(statistics['average_win_atr'], signed=True, places=3)} | "
                f"{_number_or_na(statistics['average_loss_atr'], signed=True, places=3)} | "
                f"{statistics['mean_fee_atr']:.3f} | {statistics['expectancy_atr']:+.4f} | "
                f"{statistics['mean_bars_held']:.1f} |"
            )
        lines.extend(
            [
                "",
                "**Read the three break-even columns as a ladder.** *Asked* is the rate the requested",
                "bracket would need with no costs at all — the rung the model's own `expected_value` is",
                "quoted against, and the one that is not a grade. *Before fees* uses what the barriers were",
                "actually worth from the fill, so it charges the entry gap and the stop's slippage but not",
                "the venue's cut. *Net* charges everything, and it is an accounting identity rather than a",
                "yardstick: the achieved rate is above it exactly when expectancy is positive, so `Edge`",
                "and `Expectancy (ATR)` can never disagree in sign.",
                "",
                "Where the win rate lands between the last two rungs is the diagnosis. Above *before fees*",
                "and below *net* is a model with a real directional edge that the fees are eating — a",
                "bracket that is too narrow for the venue, whose remedy is a wider target, not a better",
                "model. Below both is the model being wrong about direction. `Fee (ATR)` is the size of the",
                "problem in the units the barriers were requested in: at an ATR worth 0.6% of price against",
                "a 0.1% round trip it approaches 0.4, which is over a third of a 1-ATR stop.",
                "",
                "`Win (ATR)` and `Loss (ATR)` are net of fees and split on which barrier resolved, so they",
                "reconstruct `Expectancy (ATR)` directly. Their percent equivalents in `metadata.json` do",
                "not, and cannot: a percent average mixes bets whose barriers sat at different fractions of",
                "price, so a model that wins in quiet bars and loses in volatile ones reports a mean win",
                "smaller than its mean loss on a bracket that requested the reverse. That is the shape of an",
                "inverted bracket produced by a simulator that never inverted one, which is why the ATR",
                "columns are the ones on this table.",
            ]
        )

    lines.extend(["", bundle.calibration.markdown()])
    return lines


def _percent_or_na(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.1%}" if signed else f"{value:.1%}"


def _number_or_na(value: float | None, signed: bool = False, places: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.{places}f}" if signed else f"{value:.{places}f}"


def _train_one(
    stem: str,
    frames: dict[str, pd.DataFrame],
    config: AppConfig,
    is_pooled: bool,
) -> TrainedBundle:
    """Label, split, validate, fit, measure and persist one bundle."""
    barrier = config.barrier
    symbols = tuple(sorted(frames))
    logger.info("Bundle %s | labelling %s symbol(s)", stem, len(frames))

    dataset = build_barrier_dataset(
        frames,
        config.market.interval,
        max_horizon=barrier.max_horizon,
        pairs_per_candle=barrier.pairs_per_candle,
        grid=barrier_grid(barrier.grid_atr, barrier.min_risk_reward, barrier.max_risk_reward),
        atr_window=barrier.atr_window,
        mtf_context=config.features.mtf_context,
        mtf_higher_interval=config.features.mtf_higher_interval,
    )
    rows, candles = len(dataset), dataset.candle_count
    logger.info(
        "Bundle %s | rows=%s | candles=%s | classes=%s",
        stem,
        f"{rows:,}",
        f"{candles:,}",
        dataset.class_counts,
    )

    development, holdout = _carve_holdout(dataset, barrier)
    X = dataset.X.astype(FIT_DTYPE)
    y = dataset.y
    times = dataset.times

    # Purged, time-grouped walk-forward on the development block only. Split on unique candle opens, not
    # row positions: every barrier variant of one candle shares that candle's features and its forward
    # window, so a positional split trains on some variants and scores on the rest.
    cv = walk_forward_validation_by_time(
        X.iloc[development],
        y.iloc[development],
        times[development],
        config.model,
        gap=barrier.max_horizon,
    )
    combined = cv["combined"]
    logger.info(
        "Bundle %s | walk-forward folds=%s | log_loss=%.4f | balanced_accuracy=%.4f",
        stem,
        len(cv["folds"]),
        combined["log_loss"],
        combined["balanced_accuracy"],
    )

    model, calibration = fit_calibrated_model(
        X.iloc[development],
        y.iloc[development],
        times[development],
        config.model,
        gap=barrier.max_horizon,
        blocks=barrier.calibration_blocks,
        method=barrier.calibration_method,
    )
    logger.info(
        "Bundle %s | calibration attempted=%s | shipped=%s", stem, calibration.method, calibration.selected
    )

    holdout_probabilities = aligned_probabilities(model, X.iloc[holdout])
    holdout_metrics = classification_metrics(y.iloc[holdout], holdout_probabilities)
    logger.info(
        "Bundle %s | strict holdout rows=%s | log_loss=%.4f | balanced_accuracy=%.4f",
        stem,
        f"{len(holdout):,}",
        holdout_metrics["log_loss"],
        holdout_metrics["balanced_accuracy"],
    )

    backtests = _backtest_holdout(
        model=model,
        dataset=dataset,
        holdout=holdout,
        frames=frames,
        config=config,
    )

    path = config.output.model_dir / f"{stem}.joblib"
    joblib.dump(
        {
            "model": model,
            "feature_columns": list(dataset.feature_columns),
            "metadata": _bundle_metadata(
                symbols=symbols,
                config=config,
                calibration=calibration,
                rows=rows,
                candles=candles,
            ),
        },
        path,
        compress=3,
    )
    logger.info("Bundle %s | written | path=%s | size=%.1fMB", stem, path, path.stat().st_size / 1e6)

    return TrainedBundle(
        stem=stem,
        path=path,
        symbols=symbols,
        is_pooled=is_pooled,
        rows=rows,
        candles=candles,
        metrics={
            "feature_count": len(dataset.feature_columns),
            "class_counts": {str(label): count for label, count in dataset.class_counts.items()},
            "development_rows": int(len(development)),
            "holdout_rows": int(len(holdout)),
            "walk_forward_cv": _rename_report_classes(cv),
            "strict_holdout": _rename_report_classes(holdout_metrics),
            "calibration": _rename_report_classes(calibration.as_dict()),
            "bracket_backtest": backtests,
        },
        calibration=calibration,
    )


def _carve_holdout(dataset: BarrierDataset, barrier: BarrierConfig) -> tuple[np.ndarray, np.ndarray]:
    """Split off the block nothing is allowed to learn from, or select on.

    Cut by timestamp with a `max_horizon` purge gap, because a barrier label reaches that far forward: a
    development row whose forward window overlaps the holdout has already seen part of the answer.
    """
    development, holdout = chronological_blocks(
        dataset.times,
        (1.0 - barrier.holdout_fraction, barrier.holdout_fraction),
        gap=barrier.max_horizon,
    )
    logger.info(
        "Strict holdout carved | development=%s rows | holdout=%s rows | purge=%s candles",
        f"{len(development):,}",
        f"{len(holdout):,}",
        barrier.max_horizon,
    )
    return development, holdout


def _bundle_metadata(
    symbols: tuple[str, ...],
    config: AppConfig,
    calibration: CalibrationReport,
    rows: int,
    candles: int,
) -> dict[str, Any]:
    """The dictionary the serving registry reads back out of the artifact.

    Two fields are load-bearing and easy to get subtly wrong:

    - `atr_window` and `max_horizon` are the *questions the labels answered*. Serving reads them from
      here rather than from its own configuration, so a deployment default that disagrees with the
      training run cannot ask the model about a bet nobody trained it on.
    - `calibration["method"]` records what **shipped**, which is `report.selected`, not `report.method`.
      The latter is what was *attempted*: when the correction loses, the raw estimator ships and the
      registry would otherwise report an isotonic calibration on a bundle that has none.
    """
    return {
        "interval": config.market.interval,
        "symbols": list(symbols),
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_version": __version__,
        "atr_window": config.barrier.atr_window,
        "max_horizon": config.barrier.max_horizon,
        "label_rows": rows,
        "label_candles": candles,
        "barrier_atr_bounds": [min(config.barrier.grid_atr), max(config.barrier.grid_atr)],
        "calibration": {
            # `method` is what *shipped*, because that is the key the serving registry and `GetModelInfo`
            # read. `selected` and `attempted` repeat it in the vocabulary `CalibrationReport.as_dict` uses,
            # where `method` means what was attempted — so a reader moving between this bundle and the
            # registry's `metadata.json` is not reading one key name with two opposite meanings.
            "method": calibration.selected,
            "selected": calibration.selected,
            "attempted": calibration.method,
            "improved": calibration.improved,
            "reach": calibration.reach.as_dict() if calibration.reach is not None else None,
        },
    }


#: `classification_metrics` names the three classes for the legacy close-to-close model, where they really
#: were trading actions. Under the barrier convention they are outcomes of a bet that has already been
#: chosen: `-1` is "the stop came first", `0` is "neither barrier inside the horizon", `+1` is "the
#: take-profit came first". Leaving them as SELL/HOLD/BUY in `metadata.json` invites a reader to conclude
#: the model recommends selling 51% of the time, when what it said was that 51% of *long* bets at those
#: barriers lost. The rename happens at this boundary rather than in `classification_metrics` because the
#: legacy pipeline's own report is correct with the action names.
BARRIER_CLASS_NAMES = {"SELL": "stop_loss_first", "HOLD": "timeout", "BUY": "take_profit_first"}


def _rename_report_classes(payload: Any) -> Any:
    """Rewrite every nested `report` dict's class keys into the barrier convention's vocabulary.

    Walks the whole structure because the same per-class report appears in each CV fold, in the combined
    figure, in the strict holdout and twice inside the calibration report. Renaming only the copies a
    caller happens to read now is how the two vocabularies end up in one file.
    """
    if isinstance(payload, dict):
        renamed = {key: _rename_report_classes(value) for key, value in payload.items()}
        report = renamed.get("report")
        if isinstance(report, dict) and BARRIER_CLASS_NAMES.keys() <= report.keys():
            renamed["report"] = {BARRIER_CLASS_NAMES.get(key, key): value for key, value in report.items()}
        return renamed
    if isinstance(payload, list):
        return [_rename_report_classes(item) for item in payload]
    return payload


def _backtest_holdout(
    model,
    dataset: BarrierDataset,
    holdout: np.ndarray,
    frames: dict[str, pd.DataFrame],
    config: AppConfig,
) -> dict[str, Any]:
    """What this model would have earned placing one fixed bracket over the holdout window.

    One barrier pair, per symbol, and both of those choices are deliberate:

    - **One pair**, because the backtest answers "what would this model have earned placing *this*
      bracket". Averaging a 0.5-ATR bet and a 3-ATR bet into one equity curve answers nothing.
    - **Per symbol**, because the simulator walks a single price series forward. Concatenating symbols
      would let it carry a position across a symbol boundary and settle a BTC trade against ETH candles.
    """
    barrier = config.barrier
    pair = BarrierPair(
        take_profit_atr=barrier.backtest_take_profit_atr,
        stop_loss_atr=barrier.backtest_stop_loss_atr,
    )
    holdout_times = pd.unique(dataset.times[holdout])
    if len(holdout_times) == 0:
        return {}

    window = pd.DataFrame({"timestamp": holdout_times})
    results: dict[str, Any] = {
        "take_profit_atr": pair.take_profit_atr,
        "stop_loss_atr": pair.stop_loss_atr,
        "minimum_confidence": barrier.backtest_minimum_confidence,
        "symbols": {},
    }

    for symbol, raw in sorted(frames.items()):
        decisions = _decide_window(
            model=model,
            raw=raw,
            window=window,
            pair=pair,
            dataset=dataset,
            config=config,
        )
        if decisions.empty:
            logger.warning("Bracket backtest skipped | symbol=%s | no holdout candles in range", symbol)
            continue
        _trades, metrics = run_bracket_backtest(
            decisions,
            config.market.interval,
            barrier.max_horizon,
            BracketCosts(
                fee_rate=config.backtest.fee_rate,
                slippage_rate=config.backtest.slippage_rate,
            ),
        )
        results["symbols"][symbol] = metrics
        statistics = metrics["trades"]
        logger.info(
            "Bracket backtest | symbol=%s | trades=%s | win_rate_resolved=%.3f | "
            "break_even_net=%s | fee_atr=%.3f | expectancy=%.4f%% | expectancy_atr=%+.4f",
            symbol,
            statistics["trades"],
            statistics["win_rate_resolved"],
            _number_or_na(statistics["break_even_win_rate"], places=3),
            statistics["mean_fee_atr"],
            statistics["expectancy_percent"],
            statistics["expectancy_atr"],
        )
    return results


def _decide_window(
    model,
    raw: pd.DataFrame,
    window: pd.DataFrame,
    pair: BarrierPair,
    dataset: BarrierDataset,
    config: AppConfig,
) -> pd.DataFrame:
    """Score every holdout candle of one symbol and turn the verdicts into a decisions frame.

    Vectorised rather than a loop over `choose_direction`, because the holdout is tens of thousands of
    candles and each call is a separate `predict_proba`. The selection rule is the same one
    `modeling.direction` applies — expected value decides, ties go to the higher confidence, and a bet
    below either floor is FLAT — and `test_direction_selection_matches_the_vectorised_backtest` is what
    keeps the two from drifting apart.
    """
    features = build_features(raw, atr_window=config.barrier.atr_window)
    # `features.frame` carries only feature columns — no timestamp and no OHLC — and shares `raw`'s index,
    # which is exactly how the labeller pairs the two. Rebuilding that positional join here rather than
    # merging on a timestamp column keeps the convention in one place; a merge on a column the feature
    # frame does not have produces an empty result, not an error.
    frame = features.frame.copy()
    frame["timestamp"] = pd.to_datetime(raw["timestamp"].to_numpy(), utc=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = raw[column].astype(float).to_numpy()
    frame["atr"] = features.atr.to_numpy(dtype=np.float64)

    # The same warm-up rule the labeller applied, so the backtest scores the population the model was
    # trained on. Dropping every row with any NaN feature would be a *different*, wider filter: the
    # estimator handles a NaN split natively and training kept those rows.
    warm = features.frame[list(WARMUP_COLUMNS)].notna().all(axis=1).to_numpy()
    selected = pd.to_datetime(pd.Series(window["timestamp"].to_numpy()), utc=True)
    frame = frame.loc[
        warm & frame["timestamp"].isin(selected).to_numpy() & (frame["atr"].to_numpy() > 0)
    ].reset_index(drop=True)
    if frame.empty:
        return frame

    long_probabilities = _score_side(model, frame, features.columns, pair, Direction.LONG, dataset)
    short_probabilities = _score_side(model, frame, features.columns, pair, Direction.SHORT, dataset)

    long_value = _expected_values(long_probabilities, pair)
    short_value = _expected_values(short_probabilities, pair)
    # `+1` is "the take-profit came first" for *whichever* bet was priced, so both sides read the same
    # class. The labeller states its verdict from the bet's own point of view and `direction_sign` is what
    # distinguishes the two rows; reading `P(-1)` as a short's win would be reading the long's label
    # backwards, which the adverse-wins rule makes wrong on exactly the straddling candles that matter.
    long_confidence = long_probabilities[:, WIN_CLASS_INDEX]
    short_confidence = short_probabilities[:, WIN_CLASS_INDEX]

    # Both floors, because `choose_direction` applies both and this is the same rule. Its
    # `minimum_expected_value_atr` defaults to 0.0, so a bet whose confidence clears the floor while its
    # expected value does not is FLAT on the serving path — and a backtest that took it would be grading
    # trades the engine refuses to place. Not reachable at the shipped 1.5/1.0 bracket, where a 0.5
    # confidence is worth +0.25 ATR or better; immediately reachable at a lower `backtest_minimum_
    # confidence` (0.3 prices a 1.5/1.0 long at -0.20 ATR) or at any sub-1 reward-to-risk bracket, both
    # of which the config permits. `test_direction_selection_matches_the_vectorised_backtest` pins it.
    floor = config.barrier.backtest_minimum_confidence
    long_ok = (long_confidence >= floor) & (long_value >= MINIMUM_EXPECTED_VALUE_ATR)
    short_ok = (
        (short_confidence >= floor)
        & (short_value >= MINIMUM_EXPECTED_VALUE_ATR)
        & config.barrier.allow_short
    )
    # Expected value decides; a tie goes to the higher confidence, exactly as `choose_direction` does.
    take_long = long_ok & (
        ~short_ok | (long_value > short_value) | ((long_value == short_value) & (long_confidence >= short_confidence))
    )
    take_short = short_ok & ~take_long

    direction = np.where(take_long, int(Direction.LONG), np.where(take_short, int(Direction.SHORT), 0))
    entry = frame["close"].to_numpy(dtype=np.float64)
    atr = frame["atr"].to_numpy(dtype=np.float64)
    # The same distances go to both sides. `take_profit_atr` is how far the *profit* barrier sits from the
    # entry, and `levels_for` puts it above the entry for a long and below it for a short — so swapping
    # the pair for a short would ask for a bet with the reward and risk exchanged, not the mirror of this
    # one. The mirror is already in `direction_sign` and in where the prices land.
    take_profit_percent = np.array(
        [percent_from_atr(price, pair.take_profit_atr, bar) if price > 0 else 0.0
         for price, bar in zip(entry, atr)]
    )
    stop_loss_percent = np.array(
        [percent_from_atr(price, pair.stop_loss_atr, bar) if price > 0 else 0.0
         for price, bar in zip(entry, atr)]
    )

    return pd.DataFrame(
        {
            "timestamp": frame["timestamp"],
            "open": frame["open"],
            "high": frame["high"],
            "low": frame["low"],
            "close": frame["close"],
            "atr": atr,
            "direction": direction,
            "take_profit_percent": take_profit_percent,
            "stop_loss_percent": stop_loss_percent,
        }
    )


def _score_side(
    model,
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    pair: BarrierPair,
    direction: Direction,
    dataset: BarrierDataset,
) -> np.ndarray:
    """One direction's class probabilities for a whole window, in `ALL_CLASSES` order.

    The barrier columns are written in `BARRIER_FEATURE_COLUMNS` order and the matrix is then selected by
    the dataset's own column list, because a fitted tree addresses its inputs by position: the same four
    numbers in a different order produce a confident wrong answer rather than an error.
    """
    rows = frame[list(feature_columns)].copy()
    values = {
        "take_profit_atr": pair.take_profit_atr,
        "stop_loss_atr": pair.stop_loss_atr,
        "risk_reward_ratio": pair.risk_reward_ratio,
        "direction_sign": float(direction.sign),
    }
    for column in BARRIER_FEATURE_COLUMNS:
        rows[column] = values[column]
    return aligned_probabilities(model, rows[list(dataset.feature_columns)].astype(FIT_DTYPE))


def _expected_values(probabilities: np.ndarray, pair: BarrierPair) -> np.ndarray:
    """Expected value in ATR units, per row, from `ALL_CLASSES`-ordered probabilities.

    A vectorised restatement of `domain.expected_value`, which is scalar because the serving path prices
    two bets per request and this one prices tens of thousands. The first row is checked against the
    domain function on every call: it is one extra `predict_proba`-free comparison, and it is the only
    thing standing between a copied formula here and a silent divergence from the number the engine
    reports for the same bet.

    A timeout is valued at zero, the same default the serving evaluator uses. Valuing it at the horizon
    close instead lifts apparent expectancy on *both* sides of one series at once, which is arithmetically
    impossible and is how a backtest talks itself into a profit that is not there.
    """
    win = probabilities[:, WIN_CLASS_INDEX]
    loss = probabilities[:, LOSS_CLASS_INDEX]
    values = win * pair.take_profit_atr - loss * pair.stop_loss_atr
    if len(values):
        reference = expected_value(OutcomeProbabilities.from_class_probabilities(probabilities[0]), pair)
        if not np.isclose(values[0], reference, atol=1e-9):
            raise AssertionError(
                f"vectorised expected value {values[0]!r} disagrees with domain.expected_value "
                f"{reference!r}; the backtest and the engine would price the same bet differently"
            )
    return values


def latest_barrier_signal(
    config: AppConfig,
    symbol: str | None = None,
    take_profit_percent: float | None = None,
    stop_loss_percent: float | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """Ask the registry's own bundle what it would do on the newest candle.

    A convenience for the CLI, and deliberately not a second implementation of the serving path: the
    percentages are converted to ATR multiples and handed to the same `choose_direction` the gRPC engine
    calls, so a discrepancy between this output and the engine's is a bug in one of them rather than a
    difference of opinion.
    """
    from ..domain import format_decimal, levels_for  # local: keeps the import graph free of a cycle
    from ..modeling import choose_direction

    market = symbol.upper() if symbol else config.market.symbol
    take_profit = take_profit_percent if take_profit_percent is not None else 2.0
    stop_loss = stop_loss_percent if stop_loss_percent is not None else 1.0

    bundle_path = _resolve_bundle(config, market)
    bundle = joblib.load(bundle_path)
    model = bundle["model"]
    feature_columns = tuple(bundle["feature_columns"])
    metadata = bundle["metadata"]

    path = config.market.csv_path(market)
    if offline or not config.network.proxy_url:
        raw = load_ohlcv(path, config.market.interval)
    else:
        raw = fetch_historical_ohlcv(
            market,
            config.market.interval,
            config.market.start,
            end=config.market.end,
            proxy_url=config.network.proxy_url,
            timeout=config.network.timeout_seconds,
        )

    features = build_features(raw, atr_window=int(metadata["atr_window"]))
    usable = features.frame.dropna(subset=list(features.columns))
    if usable.empty:
        raise ValueError(f"{market} has no candle with a complete feature row; the warm-up is incomplete")
    index = usable.index[-1]
    atr = float(features.atr.loc[index])
    entry = float(raw.loc[index, "close"])
    if atr <= 0:
        raise ValueError(f"{market} has a non-positive ATR on its newest candle, so barriers are undefined")

    pair = BarrierPair(
        take_profit_atr=take_profit * entry / (atr * 100.0),
        stop_loss_atr=stop_loss * entry / (atr * 100.0),
    )
    choice = choose_direction(
        model,
        features.frame.loc[[index], list(features.columns)],
        pair,
        allow_short=config.barrier.allow_short,
        feature_columns=feature_columns,
    )
    quoted = Direction.LONG if choice.direction is Direction.FLAT else choice.direction
    levels = levels_for(quoted, entry, take_profit, stop_loss, atr=atr)

    return {
        "symbol": market,
        "interval": config.market.interval,
        "candle_open_time": raw.loc[index, "timestamp"].isoformat(),
        "bundle": bundle_path.name,
        "model_symbols": list(metadata.get("symbols", [])),
        "calibration_method": (metadata.get("calibration") or {}).get("method"),
        "direction": choice.direction.name,
        "confidence": choice.confidence,
        "expected_value_atr": choice.expected_value_atr,
        "requested": {
            "take_profit_percent": take_profit,
            "stop_loss_percent": stop_loss,
            "take_profit_atr": pair.take_profit_atr,
            "stop_loss_atr": pair.stop_loss_atr,
        },
        # Prices as fixed-place decimal strings, through the same helper the gRPC mappers use. A raw
        # `str(float)` here would print `27162.830464550505` — eight digits of arithmetic noise past what
        # any venue quotes — and would not match the characters the engine sends for the same candle.
        "levels": {
            "entry_price": format_decimal(levels.entry_price),
            "take_profit_price": format_decimal(levels.take_profit_price),
            "stop_loss_price": format_decimal(levels.stop_loss_price),
            "risk_reward_ratio": levels.risk_reward_ratio,
            "atr": format_decimal(levels.atr),
        },
        # A FLAT answer still prices the long side, because "what would this bet have looked like" is the
        # first question asked of a refusal. Saying so explicitly is the difference between levels that
        # are context and levels that read as a recommendation.
        "levels_are_hypothetical": choice.direction is Direction.FLAT,
        "quoted_direction": quoted.name,
        "candidates": [
            {
                "direction": candidate.direction.name,
                "confidence": candidate.confidence,
                "expected_value_atr": candidate.expected_value_atr,
                "break_even": candidate.break_even,
                "probabilities": {
                    "take_profit_first": candidate.probabilities.win,
                    "stop_loss_first": candidate.probabilities.loss,
                    "timeout": candidate.probabilities.timeout,
                },
            }
            for candidate in choice.candidates
        ],
        "rationale": list(choice.rationale),
        "warning": choice.warning,
    }


def _resolve_bundle(config: AppConfig, symbol: str) -> Path:
    """Exact match, then pooled, then a clear failure — the registry's rule, applied locally."""
    model_dir = config.output.model_dir
    exact = model_dir / f"{symbol}_{config.market.interval}.joblib"
    pooled = model_dir / f"{POOLED_STEM}_{config.market.interval}.joblib"
    for candidate in (exact, pooled):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No bundle serves {symbol} {config.market.interval} in {model_dir}. "
        "Train one with `python -m crypto_signal.cli --config config.toml train`."
    )
