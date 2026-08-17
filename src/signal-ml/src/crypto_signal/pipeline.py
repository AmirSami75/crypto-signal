from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd

from .backtest import run_backtest
from . import __version__
from .config import AppConfig
from .data import (
    fetch_historical_ohlcv,
    fetch_recent_ohlcv,
    load_ohlcv,
    save_ohlcv,
    validate_ohlcv,
)
from .features import make_features, make_supervised
from .model import (
    ALL_CLASSES,
    aligned_probabilities,
    classification_metrics,
    fit_model,
    probabilities_to_signals,
    walk_forward_validation,
)
from .log_setup import get_logger


SIGNAL_NAMES = {-1: "SELL", 0: "HOLD", 1: "BUY"}
logger = get_logger(__name__)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    logger.debug("JSON artifact written | path=%s", path)


def download_data(config: AppConfig) -> dict[str, Any]:
    started = time.perf_counter()
    logger.info(
        "Download pipeline started | symbol=%s | interval=%s",
        config.market.symbol,
        config.market.interval,
    )
    frame = fetch_historical_ohlcv(
        symbol=config.market.symbol,
        interval=config.market.interval,
        start=config.market.start,
        end=config.market.end,
        proxy_url=config.network.proxy_url,
        timeout=config.network.timeout_seconds,
    )
    save_ohlcv(frame, config.market.raw_data_path)
    quality = validate_ohlcv(frame, config.market.interval)
    result = {
        "path": str(config.market.raw_data_path),
        "symbol": config.market.symbol,
        "interval": config.market.interval,
        "first_candle": frame["timestamp"].iloc[0].isoformat(),
        "last_candle": frame["timestamp"].iloc[-1].isoformat(),
        **quality,
        "duration_seconds": time.perf_counter() - started,
    }
    logger.info(
        "Download pipeline finished | rows=%s | elapsed=%.2fs | path=%s",
        f"{len(frame):,}",
        result["duration_seconds"],
        config.market.raw_data_path,
    )
    return result


def _load_or_download(config: AppConfig, refresh: bool) -> pd.DataFrame:
    if refresh or not config.market.raw_data_path.exists():
        logger.info(
            "Market data download required | refresh=%s | exists=%s",
            refresh,
            config.market.raw_data_path.exists(),
        )
        download_data(config)
    else:
        logger.info("Reusing existing market CSV | path=%s", config.market.raw_data_path)
    return load_ohlcv(config.market.raw_data_path, config.market.interval)


def _prediction_frame(
    dataset: pd.DataFrame,
    probabilities: np.ndarray,
    probability_threshold: float,
) -> pd.DataFrame:
    predicted_classes = ALL_CLASSES[np.argmax(probabilities, axis=1)]
    signals = probabilities_to_signals(probabilities, probability_threshold)
    return pd.DataFrame(
        {
            "timestamp": dataset["timestamp"].to_numpy(),
            "close": dataset["close"].to_numpy(dtype=float),
            "actual_class": dataset["target"].to_numpy(dtype=int),
            "predicted_class": predicted_classes,
            "probability_sell": probabilities[:, 0],
            "probability_hold": probabilities[:, 1],
            "probability_buy": probabilities[:, 2],
            "signal": signals,
            "signal_name": [SIGNAL_NAMES[int(value)] for value in signals],
        }
    )


def _plot_equity(backtest: pd.DataFrame, destination: Path) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.plot(backtest["timestamp"], backtest["strategy_equity"], label="ML strategy")
    axis.plot(backtest["timestamp"], backtest["benchmark_equity"], label="Buy & hold")
    axis.set_title("Strict holdout equity curve (net of configured trading costs)")
    axis.set_ylabel("Growth of 1 unit")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(destination, dpi=160)
    plt.close(figure)
    logger.info("Equity chart saved | path=%s", destination)


def _config_snapshot(config: AppConfig) -> dict[str, Any]:
    return {
        "market": {
            "symbol": config.market.symbol,
            "interval": config.market.interval,
            "start": config.market.start,
            "end": config.market.end,
            "raw_data_path": str(config.market.raw_data_path),
        },
        "features": asdict(config.features),
        "model": asdict(config.model),
        "backtest": asdict(config.backtest),
        "output": {"artifact_dir": str(config.output.artifact_dir)},
        "network": {
            "proxy_enabled": config.network.proxy_url is not None,
            "proxy_url": config.network.proxy_url,
            "timeout_seconds": config.network.timeout_seconds,
        },
        "logging": {
            "level": config.logging.level,
            "log_file": str(config.logging.log_file),
        },
    }


def _report_markdown(metadata: dict[str, Any]) -> str:
    test = metadata["strict_holdout"]["classification"]
    strategy = metadata["strict_holdout"]["backtest"]["strategy"]
    benchmark = metadata["strict_holdout"]["backtest"]["buy_and_hold"]
    return f"""# Model run report

Generated: {metadata['trained_at_utc']}

Market: `{metadata['symbol']}` at `{metadata['interval']}` candles  
Development rows: {metadata['rows']['development']:,}  
Purged gap rows: {metadata['rows']['purged_gap']:,}  
Untouched holdout rows: {metadata['rows']['strict_holdout']:,}

## Strict holdout classification

- Ordinary accuracy: {test['report']['accuracy']:.2%}
- Balanced accuracy: {test['balanced_accuracy']:.2%}
- Macro F1: {test['macro_f1']:.2%}
- Log loss: {test['log_loss']:.4f}

## Strict holdout backtest

| Metric | ML strategy | Buy & hold |
|---|---:|---:|
| Cumulative return | {strategy['cumulative_return']:.2%} | {benchmark['cumulative_return']:.2%} |
| CAGR | {strategy['cagr']:.2%} | {benchmark['cagr']:.2%} |
| Sharpe (zero rate) | {strategy['sharpe_zero_rate']:.3f} | {benchmark['sharpe_zero_rate']:.3f} |
| Maximum drawdown | {strategy['max_drawdown']:.2%} | {benchmark['max_drawdown']:.2%} |
| Exposure | {strategy['exposure']:.2%} | {benchmark['exposure']:.2%} |

These are research results, not a promise of future performance. The holdout must not be
reused repeatedly for model selection. After any strategy change, begin a new forward paper-
trading window.
"""


def train_and_backtest(config: AppConfig, refresh: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    logger.info(
        "Training pipeline started | symbol=%s | interval=%s | refresh=%s",
        config.market.symbol,
        config.market.interval,
        refresh,
    )
    raw = _load_or_download(config, refresh=refresh)
    logger.info("Stage 1/7 complete: market data ready | rows=%s", f"{len(raw):,}")
    dataset, feature_columns = make_supervised(
        raw,
        prediction_horizon=config.features.prediction_horizon,
        threshold=config.features.label_threshold,
    )
    logger.info(
        "Stage 2/7 complete: features and labels ready | rows=%s | features=%s",
        f"{len(dataset):,}",
        f"{len(feature_columns):,}",
    )
    if len(dataset) < 800:
        raise ValueError(
            f"Only {len(dataset)} supervised rows are available; use at least 800 rows"
        )

    test_start = int(len(dataset) * (1 - config.model.test_fraction))
    development_end = test_start - config.features.prediction_horizon
    if development_end < 500:
        raise ValueError("Development split is too small after applying the purge gap")

    development = dataset.iloc[:development_end].copy()
    purged_gap = dataset.iloc[development_end:test_start].copy()
    strict_holdout = dataset.iloc[test_start:].copy()
    X_development = development[feature_columns]
    y_development = development["target"]
    X_holdout = strict_holdout[feature_columns]
    y_holdout = strict_holdout["target"]
    logger.info(
        "Stage 3/7 complete: chronological split | development=%s | purge_gap=%s | holdout=%s",
        f"{len(development):,}",
        f"{len(purged_gap):,}",
        f"{len(strict_holdout):,}",
    )

    cv_results = walk_forward_validation(
        X_development,
        y_development,
        config.model,
        gap=config.features.prediction_horizon,
    )
    logger.info("Stage 4/7 complete: walk-forward validation finished")

    logger.info("Training evaluation model on development rows only")
    evaluation_model = fit_model(X_development, y_development, config.model)
    holdout_probabilities = aligned_probabilities(evaluation_model, X_holdout)
    holdout_classification = classification_metrics(y_holdout, holdout_probabilities)
    logger.info(
        "Strict holdout classification | accuracy=%.2f%% | balanced_accuracy=%.2f%% | macro_f1=%.2f%%",
        holdout_classification["report"]["accuracy"] * 100,
        holdout_classification["balanced_accuracy"] * 100,
        holdout_classification["macro_f1"] * 100,
    )
    logger.info("Stage 5/7 complete: untouched holdout evaluated")
    predictions = _prediction_frame(
        strict_holdout,
        holdout_probabilities,
        config.model.probability_threshold,
    )
    backtest, backtest_metrics = run_backtest(
        predictions,
        interval=config.market.interval,
        fee_rate=config.backtest.fee_rate,
        slippage_rate=config.backtest.slippage_rate,
        allow_short=config.backtest.allow_short,
    )
    logger.info("Stage 6/7 complete: cost-aware backtest finished")

    logger.info("Training production model on every labeled row")
    production_model = fit_model(dataset[feature_columns], dataset["target"], config.model)
    artifact_dir = config.output.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(tz=timezone.utc).isoformat()
    elapsed = time.perf_counter() - started
    metadata: dict[str, Any] = {
        "project_version": __version__,
        "trained_at_utc": trained_at,
        "duration_seconds": elapsed,
        "symbol": config.market.symbol,
        "interval": config.market.interval,
        "data_range": {
            "first": raw["timestamp"].iloc[0].isoformat(),
            "last": raw["timestamp"].iloc[-1].isoformat(),
        },
        "data_quality": validate_ohlcv(raw, config.market.interval),
        "rows": {
            "raw": len(raw),
            "supervised": len(dataset),
            "development": len(development),
            "purged_gap": len(purged_gap),
            "strict_holdout": len(strict_holdout),
        },
        "class_counts": {
            str(key): int(value)
            for key, value in dataset["target"].value_counts().sort_index().items()
        },
        "feature_columns": feature_columns,
        "config": _config_snapshot(config),
        "walk_forward_cv": cv_results,
        "strict_holdout": {
            "classification": holdout_classification,
            "backtest": backtest_metrics,
        },
        "execution_semantics": (
            "Signals use a completed candle. The backtest applies the decided position "
            "to the following close-to-close return and charges costs on position changes."
        ),
        "sell_semantics": (
            "SELL exits to cash" if not config.backtest.allow_short else "SELL enters short"
        ),
    }
    bundle = {
        "model": production_model,
        "feature_columns": feature_columns,
        "metadata": metadata,
    }
    joblib.dump(bundle, artifact_dir / "model.joblib")
    predictions.to_csv(artifact_dir / "holdout_predictions.csv", index=False)
    backtest.to_csv(artifact_dir / "holdout_backtest.csv", index=False)
    write_json(artifact_dir / "metadata.json", metadata)
    (artifact_dir / "REPORT.md").write_text(_report_markdown(metadata), encoding="utf-8")
    _plot_equity(backtest, artifact_dir / "equity_curve.png")
    logger.info(
        "Stage 7/7 complete: model and reports saved | artifact_dir=%s",
        artifact_dir,
    )
    logger.info(
        "Training pipeline finished successfully | total_elapsed=%.2fs",
        time.perf_counter() - started,
    )
    return metadata


def latest_signal(config: AppConfig, use_network: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    logger.info(
        "Signal pipeline started | symbol=%s | interval=%s | network=%s",
        config.market.symbol,
        config.market.interval,
        use_network,
    )
    artifact_path = config.output.artifact_dir / "model.joblib"
    if not artifact_path.exists():
        raise FileNotFoundError("Train the model before requesting a signal")
    bundle = joblib.load(artifact_path)
    logger.info(
        "Saved model loaded | trained_at=%s | features=%s",
        bundle["metadata"]["trained_at_utc"],
        f"{len(bundle['feature_columns']):,}",
    )
    feature_columns: list[str] = bundle["feature_columns"]

    data_source = "Binance recent closed candles"
    if use_network:
        try:
            raw = fetch_recent_ohlcv(
                config.market.symbol,
                config.market.interval,
                limit=1000,
                proxy_url=config.network.proxy_url,
                timeout=config.network.timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "Recent market request failed; falling back to local CSV | error=%s",
                exc,
            )
            raw = load_ohlcv(config.market.raw_data_path, config.market.interval)
            data_source = f"local CSV fallback ({type(exc).__name__})"
    else:
        raw = load_ohlcv(config.market.raw_data_path, config.market.interval)
        data_source = "local CSV"

    features = make_features(raw)
    # The model handles occasional missing indicator values natively. Only require
    # the long-window features that establish the warm-up period.
    readiness_columns = [
        "log_return_1",
        "volatility_168",
        "sma_ratio_168",
        "volume_ratio_168",
    ]
    latest_index = features.dropna(subset=readiness_columns).index.max()
    if pd.isna(latest_index):
        raise ValueError("Not enough recent candles to calculate all features")
    latest_row = features.loc[[int(latest_index)], feature_columns]
    probabilities = aligned_probabilities(bundle["model"], latest_row)
    numeric_signal = int(
        probabilities_to_signals(
            probabilities, config.model.probability_threshold
        )[0]
    )
    timestamp = pd.Timestamp(raw.loc[int(latest_index), "timestamp"])
    payload = {
        "symbol": config.market.symbol,
        "interval": config.market.interval,
        "candle_open_time_utc": timestamp.isoformat(),
        "close_price": float(raw.loc[int(latest_index), "close"]),
        "signal": SIGNAL_NAMES[numeric_signal],
        "numeric_signal": numeric_signal,
        "probabilities": {
            "SELL": float(probabilities[0, 0]),
            "HOLD": float(probabilities[0, 1]),
            "BUY": float(probabilities[0, 2]),
        },
        "probability_threshold": config.model.probability_threshold,
        "data_source": data_source,
        "model_trained_at_utc": bundle["metadata"]["trained_at_utc"],
        "sell_semantics": bundle["metadata"]["sell_semantics"],
        "warning": "Research signal only; not financial advice or an execution instruction.",
    }
    write_json(config.output.artifact_dir / "latest_signal.json", payload)
    logger.info(
        "Signal pipeline finished | signal=%s | SELL=%.2f%% | HOLD=%.2f%% | BUY=%.2f%% | elapsed=%.3fs",
        payload["signal"],
        payload["probabilities"]["SELL"] * 100,
        payload["probabilities"]["HOLD"] * 100,
        payload["probabilities"]["BUY"] * 100,
        time.perf_counter() - started,
    )
    return payload
