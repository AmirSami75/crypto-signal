from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from .config import load_config
from .human_output import (
    format_download_summary,
    format_signal_summary,
    format_training_summary,
)
from .log_setup import configure_logging, get_logger
from .pipeline import download_data, latest_signal, train_and_backtest


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

    subparsers.add_parser("download", help="Download closed historical Binance candles")
    train_parser = subparsers.add_parser("train", help="Train, validate, and backtest")
    train_parser.add_argument(
        "--refresh", action="store_true", help="Redownload historical data first"
    )
    signal_parser = subparsers.add_parser("signal", help="Generate the newest signal")
    signal_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the local CSV instead of requesting recent candles",
    )
    subparsers.add_parser(
        "demo", help="Train on bundled synthetic data and generate an offline signal"
    )
    run_parser = subparsers.add_parser("run-all", help="Download, train, and signal")
    run_parser.add_argument(
        "--offline-signal",
        action="store_true",
        help="Use downloaded local data for the final signal",
    )
    return parser


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
            downloaded = download_data(config)
            if args.json:
                _print_json(downloaded)
            else:
                print(format_download_summary(downloaded))
        elif args.command == "train":
            trained = train_and_backtest(config, refresh=args.refresh)
            if args.json:
                _print_json(trained)
            else:
                print(format_training_summary(trained, config.output.artifact_dir))
        elif args.command == "signal":
            signal = latest_signal(config, use_network=not args.offline)
            if args.json:
                _print_json(signal)
            else:
                print(format_signal_summary(signal))
        elif args.command == "demo":
            trained = train_and_backtest(config, refresh=False)
            signal = latest_signal(config, use_network=False)
            if args.json:
                _print_json({"training": trained, "latest_signal": signal})
            else:
                print(format_training_summary(trained, config.output.artifact_dir))
                print("\n")
                print(format_signal_summary(signal))
        elif args.command == "run-all":
            downloaded = download_data(config)
            trained = train_and_backtest(config, refresh=False)
            signal = latest_signal(config, use_network=not args.offline_signal)
            if args.json:
                _print_json(
                    {
                        "download": downloaded,
                        "training": trained,
                        "latest_signal": signal,
                    }
                )
            else:
                print(format_download_summary(downloaded))
                print("\n")
                print(format_training_summary(trained, config.output.artifact_dir))
                print("\n")
                print(format_signal_summary(signal))
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
