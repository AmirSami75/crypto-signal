from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any


DEFAULT_PROXY_URL = "http://127.0.0.1:10808"


@dataclass(frozen=True)
class MarketConfig:
    """The market the legacy pipeline trains on, and the set the pooled one trains on.

    `symbol` is still singular because the legacy close-to-close pipeline and the `signal` command each
    speak about exactly one market. `symbols` is the pooled training set, and it is a superset rather than
    a replacement: the pooled model is trained across all of them and answers for markets in none of them.
    """

    symbol: str
    interval: str
    start: str
    end: str | None
    raw_data_path: Path

    #: Every symbol the pooled model is trained on, `symbol` first. One entry is legal and means a pooled
    #: bundle trained on a single market — servable, and honest about its reach in `metadata["symbols"]`.
    symbols: tuple[str, ...]

    #: Where per-symbol CSVs live, as `<SYMBOL>_<INTERVAL>.csv`. Defaults to `raw_data_path`'s directory,
    #: because that is where the existing download already puts them.
    data_dir: Path

    def csv_path(self, symbol: str) -> Path:
        """Where a pooled symbol's candles live.

        `symbol` keeps `raw_data_path` verbatim so a config naming a file that does not follow the
        convention keeps working; every other symbol is derived from the convention.
        """
        if symbol.upper() == self.symbol:
            return self.raw_data_path
        return self.data_dir / f"{symbol.upper()}_{self.interval}.csv"


@dataclass(frozen=True)
class FeatureConfig:
    prediction_horizon: int
    label_threshold: float

    #: When true, the trainer attaches higher-timeframe context features (h4_trend_ema_ratio,
    #: h4_atr_pct, h4_close_vs_ema20) to the feature matrix so the model learns to consume MTF
    #: confluence. The backend sends matching context candles at inference time; a mismatch
    #: (trained with MTF but served without, or vice versa) is detected and warned.
    mtf_context: bool = False

    #: Which higher-timeframe interval to train/with, e.g. "4h". Must match the backend's
    #: Trading:MtfContextInterval. Ignored when mtf_context is false.
    mtf_higher_interval: str = "4h"


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
class BarrierConfig:
    """What bet the barrier-conditional model is trained to answer, and how honestly it is measured.

    Every field here changes the *question* the model has been asked, which is why none of them are
    hard-coded: `max_horizon` is how long a bet is allowed to stay open, `grid_atr` is the span of
    barrier distances the model has seen, and a request outside that span is extrapolation the serving
    layer has to flag. The engine reads `max_horizon` and `atr_window` back out of the bundle for exactly
    this reason — a serving default that disagrees with the label would ask the model about a bet nobody
    trained it on.
    """

    max_horizon: int
    pairs_per_candle: int
    atr_window: int
    grid_atr: tuple[float, ...]
    min_risk_reward: float
    max_risk_reward: float

    #: Share of candles held back and never fitted, calibrated or selected on. Carved off by timestamp
    #: before anything else touches the data.
    holdout_fraction: float

    #: The fit / calibrate / assess split of what remains. The assess block is where the calibration
    #: decision and the reported confidence reach come from.
    calibration_blocks: tuple[float, float, float]
    calibration_method: str

    #: Symbols that also get a dedicated `<SYMBOL>_<INTERVAL>.joblib`, trained on their own history alone.
    #: An override is an optimisation over the pooled bundle, so this list can be empty.
    per_symbol_overrides: tuple[str, ...]

    #: The barrier pair the holdout bracket backtest trades. One pair, because the backtest answers "what
    #: would this model have earned placing *this* bracket", and averaging incomparable brackets into one
    #: equity curve would answer nothing.
    backtest_take_profit_atr: float
    backtest_stop_loss_atr: float
    backtest_minimum_confidence: float

    #: Whether the holdout backtest and the research `signal` command are allowed to take the short side.
    #: Separate from `backtest.allow_short`, which governs the legacy close-to-close model where "SELL"
    #: means exit to cash: reusing that flag here would make enabling shorts on the barrier model silently
    #: redefine the baseline the barrier work is measured against. At serving time this is a *per-request*
    #: input, so this field only decides what the training report measured.
    allow_short: bool


@dataclass(frozen=True)
class BacktestConfig:
    fee_rate: float
    slippage_rate: float
    allow_short: bool


@dataclass(frozen=True)
class LstmSection:
    """Experimental recurrent model hyper-parameters. Optional; the engine ignores it when absent."""

    lookback: int = 24
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    learning_rate: float = 1e-3
    batch_size: int = 256
    epochs: int = 12
    weight_decay: float = 1e-5


@dataclass(frozen=True)
class LstmV2Section:
    """The advanced recurrent model: attention pooling, early stopping, seed ensemble, temperature.

    Optional like `[lstm]`. Absent fields take the dataclass defaults; the section itself may be
    absent entirely, in which case `load_config` fills in `LstmV2Section()`.
    """

    lookback: int = 32
    hidden_size: int = 96
    num_layers: int = 2
    dropout: float = 0.25
    learning_rate: float = 1e-3
    batch_size: int = 256
    epochs: int = 40
    weight_decay: float = 1e-4
    patience: int = 6
    validation_fraction: float = 0.15
    ensemble_seeds: int = 3
    seed_base: int = 20260831


@dataclass(frozen=True)
class OutputConfig:
    artifact_dir: Path

    #: The serving registry: `<SYMBOL>_<INTERVAL>.joblib` bundles and a pooled `_pooled_<INTERVAL>.joblib`.
    #: A subdirectory of `artifact_dir` rather than `artifact_dir` itself, because a training run also
    #: writes reports, CSVs and plots there, and the engine loads every file it finds in the registry.
    model_dir: Path

    #: Where the legacy close-to-close run writes. Separate so its `REPORT.md` and `metadata.json` cannot
    #: overwrite the barrier run's — the two describe different models and are not interchangeable.
    legacy_dir: Path


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
    barrier: BarrierConfig
    model: ModelConfig
    backtest: BacktestConfig
    output: OutputConfig
    network: NetworkConfig
    logging: LoggingConfig
    source_path: Path
    lstm: LstmSection = LstmSection()
    lstm_v2: LstmV2Section = LstmV2Section()


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _symbol_list(raw: Any, lead: str | None) -> tuple[str, ...]:
    """Upper-cased, de-duplicated, order-preserving, with `lead` guaranteed first when given.

    Order matters more than it looks: it decides which symbol's rows a pooled dataset is concatenated from
    first, and therefore the tie-break inside one candle open. Keeping it stable keeps two training runs on
    the same data byte-identical.
    """
    symbols: list[str] = []
    if lead:
        symbols.append(lead.upper())
    for value in raw:
        candidate = str(value).strip().upper()
        if candidate and candidate not in symbols:
            symbols.append(candidate)
    return tuple(symbols)


def _three_blocks(raw: Any) -> tuple[float, float, float]:
    values = tuple(float(value) for value in raw)
    if len(values) != 3:
        raise ValueError(
            f"calibration_blocks needs exactly three shares (fit, calibrate, assess), got {len(values)}"
        )
    return values


def load_config(path: str | Path) -> AppConfig:
    source = Path(path).resolve()
    with source.open("rb") as handle:
        raw = tomllib.load(handle)

    base = source.parent
    market_raw = raw["market"]
    feature_raw = raw["features"]
    barrier_raw = raw.get("barrier", {})
    model_raw = raw["model"]
    backtest_raw = raw["backtest"]
    output_raw = raw["output"]
    network_raw = raw.get("network", {})
    logging_raw = raw.get("logging", {})

    raw_proxy = str(network_raw.get("proxy_url", DEFAULT_PROXY_URL)).strip()
    proxy_url = None if raw_proxy.lower() in {"", "none", "off", "disabled"} else raw_proxy

    end = str(market_raw.get("end", "")).strip() or None
    symbol = str(market_raw["symbol"]).upper()
    interval = str(market_raw["interval"])
    raw_data_path = _resolve(base, str(market_raw["raw_data_path"]))
    artifact_dir = _resolve(base, str(output_raw["artifact_dir"]))
    config = AppConfig(
        market=MarketConfig(
            symbol=symbol,
            interval=interval,
            start=str(market_raw["start"]),
            end=end,
            raw_data_path=raw_data_path,
            # `symbol` leads the pooled set whether or not the config lists it, so a run can never train a
            # "pooled" model that omits the market the rest of the config is about.
            symbols=_symbol_list(market_raw.get("symbols", []), symbol),
            data_dir=(
                _resolve(base, str(market_raw["data_dir"]))
                if market_raw.get("data_dir")
                else raw_data_path.parent
            ),
        ),
        features=FeatureConfig(
            prediction_horizon=int(feature_raw["prediction_horizon"]),
            label_threshold=float(feature_raw["label_threshold"]),
            mtf_context=bool(feature_raw.get("mtf_context", False)),
            mtf_higher_interval=str(feature_raw.get("mtf_higher_interval", "4h")),
        ),
        barrier=BarrierConfig(
            max_horizon=int(barrier_raw.get("max_horizon", 24)),
            pairs_per_candle=int(barrier_raw.get("pairs_per_candle", 6)),
            atr_window=int(barrier_raw.get("atr_window", 14)),
            grid_atr=tuple(float(value) for value in barrier_raw.get("grid_atr", (0.5, 1.0, 1.5, 2.0, 3.0))),
            min_risk_reward=float(barrier_raw.get("min_risk_reward", 0.4)),
            max_risk_reward=float(barrier_raw.get("max_risk_reward", 4.0)),
            holdout_fraction=float(barrier_raw.get("holdout_fraction", 0.2)),
            calibration_blocks=_three_blocks(barrier_raw.get("calibration_blocks", (0.6, 0.2, 0.2))),
            calibration_method=str(barrier_raw.get("calibration_method", "isotonic")),
            per_symbol_overrides=_symbol_list(barrier_raw.get("per_symbol_overrides", []), None),
            backtest_take_profit_atr=float(barrier_raw.get("backtest_take_profit_atr", 1.5)),
            backtest_stop_loss_atr=float(barrier_raw.get("backtest_stop_loss_atr", 1.0)),
            backtest_minimum_confidence=float(barrier_raw.get("backtest_minimum_confidence", 0.5)),
            allow_short=bool(barrier_raw.get("allow_short", True)),
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
            artifact_dir=artifact_dir,
            model_dir=(
                _resolve(base, str(output_raw["model_dir"]))
                if output_raw.get("model_dir")
                else artifact_dir / "models"
            ),
            legacy_dir=(
                _resolve(base, str(output_raw["legacy_dir"]))
                if output_raw.get("legacy_dir")
                else artifact_dir / "legacy"
            ),
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
        lstm_v2=LstmV2Section(
            **{
                key: _coerce_scalar(key, value)
                for key, value in (raw.get("lstm_v2", {}) or {}).items()
                if key in LstmV2Section.__dataclass_fields__
            }
        ),
    )
    validate_config(config)
    return config


def _coerce_scalar(key: str, value: Any) -> Any:
    """TOML gives the right primitive types already; this exists to reject unknown keys loudly."""
    fields = LstmV2Section.__dataclass_fields__
    if key not in fields:
        raise ValueError(f"unknown key in [lstm_v2]: {key!r}")
    return value


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
    _validate_barrier(config)
    _validate_lstm_v2(config)
    if config.network.timeout_seconds < 1:
        raise ValueError("network timeout_seconds must be at least 1")
    if config.logging.level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("logging level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    if config.logging.max_bytes < 1 or config.logging.backup_count < 0:
        raise ValueError("logging max_bytes must be positive and backup_count non-negative")



def _validate_barrier(config: AppConfig) -> None:
    """Reject a barrier configuration that would train a model nobody can serve honestly.

    Every check here corresponds to something the serving layer or the report would otherwise have to
    discover at request time. The two worth naming:

    - **A `max_horizon` of 1 is not a bet**, it is a single candle's high/low, and a horizon far beyond a
      day forces a purge gap so wide the CV folds stop containing much.
    - **The grid must produce at least one pair.** An empty grid is the one failure mode that survives all
      the way to a trained bundle: the labeller raises, but only after the download and the feature build.
    """
    barrier = config.barrier
    if not 1 < barrier.max_horizon <= 720:
        raise ValueError(f"barrier.max_horizon must be between 2 and 720 candles, got {barrier.max_horizon}")
    if barrier.pairs_per_candle < 1:
        raise ValueError("barrier.pairs_per_candle must be at least 1")
    if barrier.atr_window < 2:
        raise ValueError("barrier.atr_window must be at least 2 candles")
    if not barrier.grid_atr or min(barrier.grid_atr) <= 0:
        raise ValueError("barrier.grid_atr must list positive ATR multiples")
    if not 0 < barrier.min_risk_reward <= barrier.max_risk_reward:
        raise ValueError("barrier risk-reward bounds must satisfy 0 < min <= max")
    if not any(
        barrier.min_risk_reward <= take_profit / stop_loss <= barrier.max_risk_reward
        for take_profit in barrier.grid_atr
        for stop_loss in barrier.grid_atr
    ):
        raise ValueError(
            "No pair in barrier.grid_atr satisfies the risk-reward bounds, so the dataset would be empty"
        )
    if not 0.05 <= barrier.holdout_fraction <= 0.5:
        raise ValueError("barrier.holdout_fraction must be between 0.05 and 0.5")
    if min(barrier.calibration_blocks) <= 0:
        raise ValueError("every share in barrier.calibration_blocks must be positive")
    if abs(sum(barrier.calibration_blocks) - 1.0) > 1e-6:
        raise ValueError(
            f"barrier.calibration_blocks must sum to 1.0, got {sum(barrier.calibration_blocks):.4f}"
        )
    if barrier.calibration_method not in {"isotonic", "sigmoid"}:
        raise ValueError("barrier.calibration_method must be isotonic or sigmoid")
    unknown = [
        symbol for symbol in barrier.per_symbol_overrides if symbol not in config.market.symbols
    ]
    if unknown:
        # An override is trained on that symbol's own history, so it has to be one of the symbols the run
        # actually loads. Silently skipping it would produce a registry missing the override a caller was
        # told to expect.
        raise ValueError(
            f"barrier.per_symbol_overrides names {unknown}, which market.symbols does not include"
        )
    if min(barrier.backtest_take_profit_atr, barrier.backtest_stop_loss_atr) <= 0:
        raise ValueError("barrier backtest barrier distances must be positive")
    if not 0 <= barrier.backtest_minimum_confidence < 1:
        raise ValueError("barrier.backtest_minimum_confidence must be in [0, 1)")


def _validate_lstm_v2(config: AppConfig) -> None:
    """Reject an `[lstm_v2]` section that would train or serve dishonestly."""
    v2 = config.lstm_v2
    if v2.lookback < 2:
        raise ValueError("lstm_v2.lookback must be at least 2 candles")
    if v2.hidden_size < 8 or v2.num_layers < 1:
        raise ValueError("lstm_v2.hidden_size must be >= 8 and num_layers >= 1")
    if not 0 <= v2.dropout < 1:
        raise ValueError("lstm_v2.dropout must be in [0, 1)")
    if v2.learning_rate <= 0 or v2.weight_decay < 0:
        raise ValueError("lstm_v2.learning_rate must be positive and weight_decay non-negative")
    if v2.epochs < 1 or v2.batch_size < 1:
        raise ValueError("lstm_v2.epochs and batch_size must be at least 1")
    if v2.patience < 1:
        raise ValueError("lstm_v2.patience must be at least 1")
    if not 0.05 <= v2.validation_fraction < 0.5:
        raise ValueError("lstm_v2.validation_fraction must be in [0.05, 0.5)")
    if v2.ensemble_seeds < 1 or v2.ensemble_seeds > 10:
        raise ValueError("lstm_v2.ensemble_seeds must be between 1 and 10")
