"""The research CLI: download candles, train the barrier model, ask it about one bet.

The default commands drive the **barrier-conditional** pipeline — the model the gRPC engine serves. The
`-legacy` variants drive the original close-to-close model, which is kept only as the baseline its
successor is measured against. They are separate commands rather than a flag because they train different
models with different labels into different directories, and a single `train --legacy` would make the
question "which model is in artifacts?" depend on shell history.

Training runs on the host, never in the container: only `testnet.binance.vision` is reachable from inside
the compose network, and the mainnet history these models learn from is not.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from .config import load_config
from .human_output import (
    format_barrier_download_summary,
    format_barrier_signal_summary,
    format_barrier_training_summary,
    format_download_summary,
    format_lstm_training_summary,
    format_signal_summary,
    format_training_summary,
)
from .log_setup import configure_logging, get_logger
from .training import (
    download_barrier_candles,
    download_data,
    latest_barrier_signal,
    latest_signal,
    train_and_backtest,
    train_barrier_model,
    train_lstm_bundle,
)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crypto-signal",
        description="Leakage-aware crypto ML research signals",
    )
    parser.add_argument("--config", default="config.toml", help="Path to TOML config")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of the beginner-friendly summary",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download_parser = subparsers.add_parser(
        "download", help="Download closed historical candles for every configured symbol"
    )
    download_parser.add_argument(
        "--refresh", action="store_true", help="Redownload even when a CSV already exists"
    )

    train_lstm_parser = subparsers.add_parser(
        "train-lstm",
        help="Train the experimental LSTM sequence model and write _pooled_<INTERVAL>.joblib",
    )
    train_lstm_parser.add_argument(
        "--refresh", action="store_true", help="Redownload historical data first"
    )

    train_lstm_v2_parser = subparsers.add_parser(
        "train-lstm-v2",
        help="Train the attention-ensemble LSTM v2 and write _pooled_<INTERVAL>_v2.joblib",
    )
    train_lstm_v2_parser.add_argument(
        "--refresh", action="store_true", help="Redownload historical data first"
    )

    train_parser = subparsers.add_parser(
        "train", help="Train the barrier-conditional model and write the serving registry"
    )
    train_parser.add_argument(
        "--refresh", action="store_true", help="Redownload historical data first"
    )

    signal_parser = subparsers.add_parser(
        "signal", help="Ask the trained model about one requested bet"
    )
    signal_parser.add_argument(
        "--symbol", help="Market to ask about; defaults to the configured primary symbol"
    )
    signal_parser.add_argument(
        "--take-profit",
        type=float,
        default=2.0,
        help="Requested take-profit distance, in percent of the entry price",
    )
    signal_parser.add_argument(
        "--stop-loss",
        type=float,
        default=1.0,
        help="Requested stop-loss distance, in percent of the entry price",
    )
    signal_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the local CSV instead of requesting recent candles",
    )

    legacy_train = subparsers.add_parser(
        "train-legacy", help="Train the original close-to-close model into artifacts/legacy"
    )
    legacy_train.add_argument(
        "--refresh", action="store_true", help="Redownload historical data first"
    )
    legacy_signal = subparsers.add_parser(
        "signal-legacy", help="Generate the newest close-to-close signal"
    )
    legacy_signal.add_argument(
        "--offline",
        action="store_true",
        help="Use the local CSV instead of requesting recent candles",
    )
    subparsers.add_parser(
        "download-legacy", help="Download candles for the primary symbol only"
    )
    subparsers.add_parser(
        "demo",
        help="Train and signal on the bundled synthetic market, without touching the network",
    )
    run_league_parser = subparsers.add_parser(
        "run-league",
        help="Backtest and rank the Strategy Zoo over symbols x intervals (walk-forward)",
    )
    run_league_parser.add_argument(
        "--symbols",
        default=",".join(config_placeholder_symbols()),
        help="Comma-separated symbols (default: the config's pooled symbol list)",
    )
    run_league_parser.add_argument(
        "--intervals",
        default="1h",
        help="Comma-separated intervals, e.g. 1h,15m (default: 1h)",
    )
    run_league_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Redownload historical data first",
    )
    run_league_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local CSVs only; skip symbols whose CSV is missing",
    )
    run_league_parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to a partial league JSON: skip (strategy, symbol, interval) pairs it already has",
    )
    return parser


def config_placeholder_symbols() -> list[str]:
    """A lazy default so `--help` works without a config file on disk."""
    try:
        from .config import load_config
        from pathlib import Path

        return list(load_config(Path("config.toml")).market.symbols)
    except Exception:
        return ["BTCUSDT"]


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(Path(args.config))
    configure_logging(config.logging)
    logger = get_logger(__name__)
    started = time.perf_counter()
    logger.info(
        "Command started | command=%s | config=%s | json_output=%s",
        args.command,
        config.source_path,
        args.json,
    )
    try:
        if args.command == "download":
            downloaded = download_barrier_candles(config, refresh=args.refresh)
            if args.json:
                _print_json(downloaded)
            else:
                print(format_barrier_download_summary(downloaded))
        elif args.command == "train":
            trained = train_barrier_model(config, refresh=args.refresh)
            if args.json:
                _print_json(trained)
            else:
                print(format_barrier_training_summary(trained))
        elif args.command == "train-lstm":
            trained = train_lstm_bundle(config, refresh=args.refresh)
            if args.json:
                _print_json(trained)
            else:
                print(format_lstm_training_summary(trained))
        elif args.command == "train-lstm-v2":
            from .training.lstm_pipeline import train_lstm_v2_bundle

            trained = train_lstm_v2_bundle(config, refresh=args.refresh)
            if args.json:
                _print_json(trained)
            else:
                holdout = trained.get("strict_holdout", {})
                backtest = (holdout.get("backtest") or {}).get("strategy") or {}
                diag = trained.get("diagnostics", {})
                print("LSTM v2 training complete")
                print(f"  bundle: _pooled_{trained.get('interval')}_v2.joblib")
                print(f"  holdout log loss: {holdout.get('log_loss', float('nan')):.4f}")
                print(
                    f"  holdout net return: {backtest.get('cumulative_return', float('nan')) * 100:.2f}%"
                )
                print(f"  temperature: {diag.get('temperature_mean', float('nan')):.3f}")
                print(f"  members: {diag.get('validation_log_loss_members', [])}")
                print(f"  seed spread (mean std): {diag.get('seed_spread_mean_std', 0.0):.4f}")
        elif args.command == "signal":
            signal = latest_barrier_signal(
                config,
                symbol=args.symbol,
                take_profit_percent=args.take_profit,
                stop_loss_percent=args.stop_loss,
                offline=args.offline,
            )
            if args.json:
                _print_json(signal)
            else:
                print(format_barrier_signal_summary(signal))
        elif args.command == "demo":
            # Offline end to end, so the walkthrough works on a machine with no proxy and no exchange
            # access. `config.demo.toml` points at bundled synthetic candles.
            trained = train_barrier_model(config, refresh=False)
            signal = latest_barrier_signal(config, offline=True)
            if args.json:
                _print_json({"training": trained, "latest_signal": signal})
            else:
                print(format_barrier_training_summary(trained))
                print("\n")
                print(format_barrier_signal_summary(signal))
        elif args.command == "download-legacy":
            downloaded = download_data(config)
            if args.json:
                _print_json(downloaded)
            else:
                print(format_download_summary(downloaded))
        elif args.command == "train-legacy":
            trained = train_and_backtest(config, refresh=args.refresh)
            if args.json:
                _print_json(trained)
            else:
                print(format_training_summary(trained, config.output.legacy_dir))
        elif args.command == "signal-legacy":
            signal = latest_signal(config, use_network=not args.offline)
            if args.json:
                _print_json(signal)
            else:
                print(format_signal_summary(signal))
        elif args.command == "run-league":
            from .evaluation.league_report import run_league_command

            result = run_league_command(
                config,
                symbols=[s.strip().upper() for s in args.symbols.split(",") if s.strip()],
                intervals=[i.strip() for i in args.intervals.split(",") if i.strip()],
                refresh=args.refresh,
                offline=args.offline,
                resume=Path(args.resume) if args.resume else None,
            )
            if args.json:
                _print_json({"artifact": str(result["artifact_path"]), "rows": result["rows"]})
            else:
                print(result["table"])
        else:
            raise AssertionError(f"Unknown command: {args.command}")
    except Exception:
        logger.exception("Command failed | command=%s", args.command)
        raise
    finally:
        logger.info(
            "Command finished | command=%s | elapsed=%.2fs",
            args.command,
            time.perf_counter() - started,
        )


if __name__ == "__main__":
    main()
