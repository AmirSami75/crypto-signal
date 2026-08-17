from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


DEFAULT_PROXY_URL = "http://127.0.0.1:10808"


@dataclass(frozen=True)
class MarketConfig:
    symbol: str
    interval: str
    start: str
    end: str | None
    raw_data_path: Path


@dataclass(frozen=True)
class FeatureConfig:
    prediction_horizon: int
    label_threshold: float


@dataclass(frozen=True)
class ModelConfig:
    test_fraction: float
    cv_splits: int
    probability_threshold: float
    random_state: int
    max_iter: int
    learning_rate: float
    max_leaf_nodes: int
    min_samples_leaf: int
    l2_regularization: float


@dataclass(frozen=True)
class BacktestConfig:
    fee_rate: float
    slippage_rate: float
    allow_short: bool


@dataclass(frozen=True)
class OutputConfig:
    artifact_dir: Path


@dataclass(frozen=True)
class NetworkConfig:
    proxy_url: str | None
    timeout_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    log_file: Path
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class AppConfig:
    market: MarketConfig
    features: FeatureConfig
    model: ModelConfig
    backtest: BacktestConfig
    output: OutputConfig
    network: NetworkConfig
    logging: LoggingConfig
    source_path: Path


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def load_config(path: str | Path) -> AppConfig:
    source = Path(path).resolve()
    with source.open("rb") as handle:
        raw = tomllib.load(handle)

    base = source.parent
    market_raw = raw["market"]
    feature_raw = raw["features"]
    model_raw = raw["model"]
    backtest_raw = raw["backtest"]
    output_raw = raw["output"]
    network_raw = raw.get("network", {})
    logging_raw = raw.get("logging", {})

    raw_proxy = str(network_raw.get("proxy_url", DEFAULT_PROXY_URL)).strip()
    proxy_url = None if raw_proxy.lower() in {"", "none", "off", "disabled"} else raw_proxy

    end = str(market_raw.get("end", "")).strip() or None
    config = AppConfig(
        market=MarketConfig(
            symbol=str(market_raw["symbol"]).upper(),
            interval=str(market_raw["interval"]),
            start=str(market_raw["start"]),
            end=end,
            raw_data_path=_resolve(base, str(market_raw["raw_data_path"])),
        ),
        features=FeatureConfig(
            prediction_horizon=int(feature_raw["prediction_horizon"]),
            label_threshold=float(feature_raw["label_threshold"]),
        ),
        model=ModelConfig(
            test_fraction=float(model_raw["test_fraction"]),
            cv_splits=int(model_raw["cv_splits"]),
            probability_threshold=float(model_raw["probability_threshold"]),
            random_state=int(model_raw["random_state"]),
            max_iter=int(model_raw["max_iter"]),
            learning_rate=float(model_raw["learning_rate"]),
            max_leaf_nodes=int(model_raw["max_leaf_nodes"]),
            min_samples_leaf=int(model_raw["min_samples_leaf"]),
            l2_regularization=float(model_raw["l2_regularization"]),
        ),
        backtest=BacktestConfig(
            fee_rate=float(backtest_raw["fee_rate"]),
            slippage_rate=float(backtest_raw["slippage_rate"]),
            allow_short=bool(backtest_raw["allow_short"]),
        ),
        output=OutputConfig(
            artifact_dir=_resolve(base, str(output_raw["artifact_dir"])),
        ),
        network=NetworkConfig(
            proxy_url=proxy_url,
            timeout_seconds=int(network_raw.get("timeout_seconds", 30)),
        ),
        logging=LoggingConfig(
            level=str(logging_raw.get("level", "INFO")).upper(),
            log_file=_resolve(
                base,
                str(
                    logging_raw.get(
                        "log_file",
                        Path(str(output_raw["artifact_dir"])) / "logs" / "crypto_signal.log",
                    )
                ),
            ),
            max_bytes=int(logging_raw.get("max_bytes", 5_000_000)),
            backup_count=int(logging_raw.get("backup_count", 3)),
        ),
        source_path=source,
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.features.prediction_horizon < 1:
        raise ValueError("prediction_horizon must be at least 1")
    if config.features.label_threshold <= 0:
        raise ValueError("label_threshold must be positive")
    if not 0.05 <= config.model.test_fraction <= 0.5:
        raise ValueError("test_fraction must be between 0.05 and 0.5")
    if config.model.cv_splits < 2:
        raise ValueError("cv_splits must be at least 2")
    if not 1 / 3 <= config.model.probability_threshold < 1:
        raise ValueError("probability_threshold must be in [1/3, 1)")
    if min(config.backtest.fee_rate, config.backtest.slippage_rate) < 0:
        raise ValueError("fee and slippage rates cannot be negative")
    if config.network.timeout_seconds < 1:
        raise ValueError("network timeout_seconds must be at least 1")
    if config.logging.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("logging level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    if config.logging.max_bytes < 1 or config.logging.backup_count < 0:
        raise ValueError("logging max_bytes must be positive and backup_count non-negative")

