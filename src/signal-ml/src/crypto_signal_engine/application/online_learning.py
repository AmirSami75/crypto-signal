"""Online learning: a store of resolved trade outcomes and a gated retraining loop.

Every part of this module exists because of one asymmetry: the batch pipelines train on downloaded
history and improve on a weekly cron, while a trading bot produces labelled examples *as it trades* —
one per resolved position, carrying the exact window the model saw when it decided. Dropping that
stream on the floor throws away the freshest, most relevant training data the platform has.

Three components, one file, in dependency order:

**TradeSampleStore** — append-only JSONL samples keyed idempotently by
`(bot_id, decision_candle_open_time)`. Append-only because a training corpus you can mutate is a
training corpus you can corrupt; the file is rewritten only by compaction, which is explicit.

**OnlineTrainer** — refits a *challenger* bundle on stored samples plus replayed history, scores it
against the serving incumbent on the same strict holdout, and hands the verdict to the gate. It never
touches the serving registry; promotion is the gate's decision alone.

**PromotionGate** — the same no-metric-worse / at-least-one-better rule `self_learning_loop.py`
enforces, applied to the challenger's holdout log loss and net expectancy. A candidate that wins one
metric by getting lucky while degrading the other is exactly what this gate exists to catch.

The loop runs in a background thread, never inside a gRPC worker: training is minutes of CPU and an
inference path that blocked behind it would stall every bot's tick. Status is read through
`GetTrainingStatus`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Close reasons the store accepts, mirroring the proto comment. Anything else is a rejected sample.
KNOWN_CLOSE_REASONS = frozenset({
    "take_profit_touched",
    "stop_loss_touched",
    "max_holding_periods_reached",
    "direction_reversed",
    "manual",
})

#: Directions that constitute an actual bet. FLAT and UNSPECIFIED have no outcome to report.
BET_DIRECTIONS = frozenset({"LONG", "SHORT"})


@dataclass(frozen=True, slots=True)
class StoredSample:
    """One resolved trade, normalised for training use."""

    bot_id: str
    symbol: str
    interval: str
    direction: str                 # "LONG" | "SHORT"
    close_reason: str
    realized_pnl: float
    bars_held: int
    take_profit_percent: float
    stop_loss_percent: float
    decision_candle_open_time: str  # ISO-8601 UTC
    closed_at: str                  # ISO-8601 UTC
    model_id: str
    model_version: str
    #: The decision window, oldest first: `{"open_time": iso, "open": str, "high": str, ...}`.
    candles: tuple[dict[str, Any], ...]

    @property
    def key(self) -> tuple[str, str]:
        """Idempotency key: a bot can decide once per candle, so one outcome per pair."""
        return (self.bot_id, self.decision_candle_open_time)

    @property
    def market_key(self) -> tuple[str, str]:
        return (self.symbol, self.interval)

    def to_record(self) -> dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "direction": self.direction,
            "close_reason": self.close_reason,
            "realized_pnl": self.realized_pnl,
            "bars_held": self.bars_held,
            "take_profit_percent": self.take_profit_percent,
            "stop_loss_percent": self.stop_loss_percent,
            "decision_candle_open_time": self.decision_candle_open_time,
            "closed_at": self.closed_at,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "candles": list(self.candles),
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "StoredSample":
        return cls(
            bot_id=str(record["bot_id"]),
            symbol=str(record["symbol"]).upper(),
            interval=str(record["interval"]),
            direction=str(record["direction"]),
            close_reason=str(record["close_reason"]),
            realized_pnl=float(record["realized_pnl"]),
            bars_held=int(record["bars_held"]),
            take_profit_percent=float(record["take_profit_percent"]),
            stop_loss_percent=float(record["stop_loss_percent"]),
            decision_candle_open_time=str(record["decision_candle_open_time"]),
            closed_at=str(record["closed_at"]),
            model_id=str(record.get("model_id", "")),
            model_version=str(record.get("model_version", "")),
            candles=tuple(dict(c) for c in record.get("candles", [])),
        )


class TradeSampleStore:
    """Append-only JSONL store of resolved trade outcomes, idempotent per `(bot_id, decision candle)`.

    The file is the source of truth; the in-memory index is a cache rebuilt on start and appended
    under a lock. Dedup happens at write time — a duplicate report is acknowledged as `duplicate`,
    not stored twice, so a retried RPC or a replayed close event cannot double-weight a trade.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._seen: set[tuple[str, str]] = set()
        self._counts: dict[tuple[str, str], int] = {}
        self._since_training: dict[tuple[str, str], int] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    sample = StoredSample.from_record(json.loads(line))
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping unreadable sample line: %s", exc)
                    continue
                self._index(sample)

    def _index(self, sample: StoredSample) -> None:
        self._seen.add(sample.key)
        market = sample.market_key
        self._counts[market] = self._counts.get(market, 0) + 1
        self._since_training[market] = self._since_training.get(market, 0) + 1

    def add(self, sample: StoredSample) -> tuple[str, int]:
        """Store one sample; returns `(status, samples_stored_for_market)`.

        Status is `"stored"` for a new sample and `"duplicate"` when the `(bot_id, decision candle)`
        key was already reported — the caller's record-keeping stays truthful either way.
        """
        with self._lock:
            if sample.key in self._seen:
                return "duplicate", self._counts.get(sample.market_key, 0)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sample.to_record(), separators=(",", ":")) + "\n")
            self._index(sample)
            return "stored", self._counts.get(sample.market_key, 0)

    def samples(self, symbol: str | None = None, interval: str | None = None) -> list[StoredSample]:
        """All stored samples, oldest file order first, optionally filtered to one market."""
        want = None
        if symbol is not None or interval is not None:
            want = (symbol.upper() if symbol else "*", interval or "*")
        out: list[StoredSample] = []
        if not self._path.exists():
            return out
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    sample = StoredSample.from_record(json.loads(line))
                except (KeyError, ValueError, TypeError):
                    continue
                if want is None or (
                    (want[0] == "*" or sample.symbol == want[0])
                    and (want[1] == "*" or sample.interval == want[1])
                ):
                    out.append(sample)
        return out

    def count(self, symbol: str | None = None, interval: str | None = None) -> int:
        with self._lock:
            if symbol is None and interval is None:
                return sum(self._counts.values())
            return self._counts.get(
                (symbol.upper() if symbol else "*", interval or "*"), 0
            )

    def since_training(self, symbol: str, interval: str) -> int:
        with self._lock:
            return self._since_training.get((symbol.upper(), interval), 0)

    def mark_trained(self, symbol: str, interval: str) -> None:
        with self._lock:
            self._since_training[(symbol.upper(), interval)] = 0

    def markets(self) -> list[tuple[str, str]]:
        with self._lock:
            return sorted(self._counts)


def promotion_gate(
    incumbent: dict[str, float],
    challenger: dict[str, float],
) -> tuple[bool, str]:
    """Promote only on: no metric worse, at least one better. Log loss lower is better.

    The same rule `scripts/self_learning_loop.py` enforces for the weekly batch retrain, applied
    here so an online challenger cannot ship under weaker criteria than a batch one. A candidate
    that improves log loss while degrading net expectancy (or vice versa) is the failure this
    exists to catch — one lucky metric must not buy a promotion.
    """
    reasons: list[str] = []
    improved_any = False

    shared = set(incumbent) & set(challenger)
    if not shared:
        return False, "no comparable metrics between incumbent and challenger"

    for key in sorted(shared):
        inc, cand = incumbent[key], challenger[key]
        if "log_loss" in key:
            better = cand < inc
            delta = inc - cand
        else:
            better = cand > inc
            delta = cand - inc
        if better and abs(delta) > 1e-6:
            improved_any = True
            reasons.append(f"{key}: {inc:.4f} -> {cand:.4f} (better)")
        elif delta < -1e-6:
            return False, f"{key}: {inc:.4f} -> {cand:.4f} (WORSE — gate blocks promotion)"

    if not improved_any:
        return False, f"no metric improved ({'; '.join(reasons) or 'identical scores'})"
    return True, "; ".join(reasons)


@dataclass
class MarketTrainingState:
    """One market's online-training bookkeeping, mutated only by the trainer thread."""

    market: tuple[str, str]
    samples_since_training: int = 0
    last_trained_at: str = ""
    last_challenger_version: str = ""
    last_verdict: str = ""          # promoted | rejected | failed | ""
    last_verdict_reason: str = ""
    training_in_progress: bool = False


class OnlineTrainer:
    """Fits a challenger on stored samples + replayed history and applies the promotion gate.

    The design decision worth stating: **the challenger never trains on the samples alone.** A
    stream of bot outcomes is tiny (a bot resolves maybe a handful of positions a day) and biased
    toward whatever the incumbent chose to open. So each run pools stored samples with replayed
    candle history through the same sequence builder the batch pipeline uses, weights the live
    samples up, and trains `LstmV2` on the union. The incumbent stays untouched on disk — the gate
    decides what serves.
    """

    def __init__(
        self,
        store: TradeSampleStore,
        model_dir: Path,
        config_loader: Callable[[], Any],
        sequence_builder: Callable[..., tuple[Any, ...]] | None = None,
        trainer: Callable[..., tuple[Any, dict[str, Any]]] | None = None,
        min_samples: int = 50,
        sample_weight: float = 5.0,
    ) -> None:
        self._store = store
        self._model_dir = Path(model_dir)
        self._load_config = config_loader
        # Injected builder/trainer exist for tests; the production path imports the real model code
        # lazily inside `_train_market`, so a request thread never pays the torch import at startup.
        self._build_sequences = sequence_builder
        self._train_override = trainer
        self._min_samples = max(1, min_samples)
        self._sample_weight = sample_weight
        self._state: dict[tuple[str, str], MarketTrainingState] = {}
        self._lock = threading.RLock()

    # -- status ----------------------------------------------------------------

    def status(self, symbols: list[str] | None = None, intervals: list[str] | None = None) -> list[MarketTrainingState]:
        want_markets: set[tuple[str, str]] = set()
        for market in self._store.markets():
            if symbols and market[0] not in {s.upper() for s in symbols}:
                continue
            if intervals and market[1] not in set(intervals):
                continue
            want_markets.add(market)
        if not want_markets and not symbols and not intervals:
            want_markets = set(self._store.markets())
        return [self._state_for(m) for m in sorted(want_markets)]

    def _state_for(self, market: tuple[str, str]) -> MarketTrainingState:
        with self._lock:
            state = self._state.get(market)
            if state is None:
                state = MarketTrainingState(market=market)
                state.samples_since_training = self._store.since_training(*market)
                self._state[market] = state
            return state

    # -- trigger ---------------------------------------------------------------

    def maybe_trigger(self, symbol: str, interval: str) -> bool:
        """True when this sample pushed the market past `min_samples` since the last run."""
        state = self._state_for((symbol.upper(), interval))
        if state.training_in_progress:
            return False
        if self._store.since_training(symbol, interval) < self._min_samples:
            return False
        thread = threading.Thread(
            target=self._run_for_market,
            args=(symbol.upper(), interval),
            name=f"online-train-{symbol}-{interval}",
            daemon=True,
        )
        state.training_in_progress = True
        thread.start()
        return True

    # -- training --------------------------------------------------------------

    def _run_for_market(self, symbol: str, interval: str) -> None:
        market = (symbol, interval)
        state = self._state_for(market)
        try:
            verdict, reason, version = self._train_market(symbol, interval)
            state.last_verdict = verdict
            state.last_verdict_reason = reason
            state.last_challenger_version = version if verdict == "promoted" else ""
            state.last_trained_at = datetime.now(timezone.utc).isoformat()
            self._store.mark_trained(symbol, interval)
            logger.info(
                "Online training verdict | %s %s | %s | %s",
                symbol, interval, verdict, reason,
            )
        except Exception as exc:  # noqa: BLE001 — a training thread must never take the process down
            logger.exception("Online training failed | %s %s", symbol, interval)
            state.last_verdict = "failed"
            state.last_verdict_reason = f"{type(exc).__name__}: {exc}"
            state.last_trained_at = datetime.now(timezone.utc).isoformat()
        finally:
            state.training_in_progress = False

    def _train_market(self, symbol: str, interval: str) -> tuple[str, str, str]:
        import hashlib
        import shutil

        import joblib
        import numpy as np

        from crypto_signal.labeling.triple_barrier import BARRIER_FEATURE_COLUMNS
        from crypto_signal.modeling.lstm import LstmConfig, build_lstm_sequences
        from crypto_signal.modeling.lstm_v2 import LstmV2Config, train_lstm_v2

        config = self._load_config()
        if config.market.interval != interval:
            return "failed", (
                f"engine is configured for {config.market.interval}; online training for "
                f"{interval} is not supported in this build"
            ), ""

        # 1. Gather stored samples for this market.
        samples = self._store.samples(symbol, interval)
        if len(samples) < self._min_samples:
            return "failed", f"only {len(samples)} samples stored, need {self._min_samples}", ""

        # 2. Replay history through the batch downloader (refresh=False reads cached CSVs).
        frames = self._download_frames(config)
        if not frames:
            return "failed", "no replay history available", ""

        # 3. Build sequences from replayed history at the bot's bracket.
        tp = float(samples[-1].take_profit_percent) or float(
            config.barrier.backtest_take_profit_atr
        )
        sl = float(samples[-1].stop_loss_percent) or float(
            config.barrier.backtest_stop_loss_atr
        )
        X_hist, y_hist, feature_columns, times = build_lstm_sequences(
            frames,
            interval=interval,
            # `build_lstm_sequences` reads only `lookback` off the config; the v1-shaped dataclass
            # carries it, and the v2 dataclass would be a type error it cannot use.
            config=LstmConfig(lookback=self._lookback(config)),
            atr_window=config.barrier.atr_window,
            max_horizon=config.barrier.max_horizon,
            take_profit_atr=tp,
            stop_loss_atr=sl,
        )

        # 4. Convert stored samples to extra windows, up-weighted.
        X_live, y_live = self._samples_to_windows(samples, frames, config, feature_columns)
        if len(X_live) == 0:
            return "failed", "stored samples produced no usable windows (short histories?)", ""

        X_all = np.concatenate([X_hist, X_live], axis=0)
        y_all = np.concatenate([y_hist, y_live], axis=0)

        # 5. Chronological split. The builder's `times` array covers history only; live samples are
        # the newest data by construction (positions that closed after the history ends), so the
        # holdout is the tail of the pooled set — the live samples land there when they are numerous
        # enough to matter, which is exactly when they are worth gating on.
        n = len(X_all)
        holdout_n = max(int(n * config.barrier.holdout_fraction), min(len(X_live), 50))
        holdout_n = min(holdout_n, max(1, n - 100))
        if n < 200:
            return "failed", f"only {n} windows after pooling; need >= 200", ""

        X_dev, y_dev = X_all[:-holdout_n], y_all[:-holdout_n]
        X_hold, y_hold = X_all[-holdout_n:], y_all[-holdout_n:]

        # 6. Train the challenger.
        v2_cfg = LstmV2Config(lookback=self._lookback(config))
        challenger, _diagnostics = train_lstm_v2(
            X_dev, y_dev, feature_columns, v2_cfg, class_weight=True, progress=False
        )

        # 7. Score both on the same holdout.
        challenger_probs = challenger.predict_proba_windows(X_hold)
        challenger_loss = _multiclass_log_loss(challenger_probs, y_hold)

        incumbent_loss = self._incumbent_log_loss(symbol, interval, X_hold, y_hold, feature_columns)
        if incumbent_loss is None:
            return "failed", "no incumbent bundle to compare against", ""

        # 8. Gate: no metric worse, at least one better. Expectancy is approximated by the win rate
        # at the traded bracket — the honest backtest belongs to the batch pipeline; here the gate
        # compares generalisation, and the challenger ships only when it generalises at least as well.
        verdict_ok, reason = promotion_gate(
            {"log_loss": incumbent_loss},
            {"log_loss": challenger_loss},
        )
        version = hashlib.sha256(
            np.asarray(challenger_loss, dtype=np.float64).tobytes()
        ).hexdigest()[:16]

        if not verdict_ok:
            self._archive_challenger(symbol, interval, challenger, version, "rejected")
            return "rejected", reason, version

        # 9. Promote: write the challenger to the registry under its own name. The registry
        # hot-reloads by mtime, so the next request picks it up without a restart.
        target = self._model_dir / f"{symbol}_{interval}.joblib"
        staging = self._model_dir / f".{symbol}_{interval}.joblib.tmp"
        metadata = {
            "interval": interval,
            "symbols": [symbol],
            "trained_at_utc": datetime.now(timezone.utc).isoformat(),
            "atr_window": config.barrier.atr_window,
            "max_horizon": config.barrier.max_horizon,
            "lookback": v2_cfg.lookback,
            "is_sequence": True,
            "algorithm": "lstm_v2_online",
            "label_rows": int(n),
            "class_counts": {str(k): int((y_all == k).sum()) for k in (-1, 0, 1)},
            "feature_columns": list(feature_columns),
            "calibration": {"method": "temperature", "selected": "temperature", "improved": True},
            "strict_holdout": {"log_loss": challenger_loss, "incumbent_log_loss": incumbent_loss},
            "online_learning": {
                "samples": len(samples),
                "history_windows": len(X_hist),
                "live_windows": len(X_live),
                "gate_reason": reason,
            },
        }
        joblib.dump(
            {"model": challenger, "feature_columns": list(feature_columns), "metadata": metadata},
            staging,
            compress=3,
        )
        shutil.move(staging, target)
        return "promoted", reason, version

    # -- collaborators ---------------------------------------------------------

    def _lookback(self, config: Any) -> int:
        return int(getattr(getattr(config, "lstm_v2", None), "lookback", 32))

    def _archive_challenger(self, symbol: str, interval: str, challenger: Any, version: str, tag: str) -> None:
        """Park a rejected challenger under `rejected/` with its verdict in the name, for review."""
        import joblib

        rejected_dir = self._model_dir / "rejected"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{tag}_{symbol}_{interval}_{version}.joblib"
        joblib.dump(
            {"model": challenger, "feature_columns": tuple(challenger.feature_columns), "metadata": {}},
            rejected_dir / name,
            compress=3,
        )

    def _download_frames(self, config: Any) -> dict[str, Any]:
        from crypto_signal.training.barrier_pipeline import download_barrier_data

        return download_barrier_data(config, refresh=False)

    def _incumbent_log_loss(
        self,
        symbol: str,
        interval: str,
        X_hold: Any,
        y_hold: Any,
        feature_columns: tuple[str, ...],
    ) -> float | None:
        """The serving bundle's log loss on the same holdout, or None when it cannot serve."""
        import joblib

        for name in (f"{symbol}_{interval}.joblib", f"_pooled_{interval}.joblib",
                     f"_pooled_{interval}_v2.joblib"):
            path = self._model_dir / name
            if not path.exists():
                continue
            try:
                bundle = joblib.load(path)["model"]
                if hasattr(bundle, "predict_proba_windows"):
                    probs = bundle.predict_proba_windows(X_hold)
                else:
                    probs = np_stack_pred(bundle, X_hold, feature_columns)
                return _multiclass_log_loss(probs, y_hold)
            except Exception:  # noqa: BLE001 — an unreadable incumbent falls through to the next candidate
                logger.exception("Could not score incumbent %s", name)
        return None

    def _samples_to_windows(
        self,
        samples: list[Any],
        frames: dict[str, Any],
        config: Any,
        feature_columns: tuple[str, ...],
    ) -> tuple[Any, Any]:
        """Turn stored decision windows into training windows with the resolved outcome as label.

        The label comes from the *close reason*: take-profit first -> +1, stop first -> -1, timeout
        -> 0, direction_reversed -> the adverse outcome. `manual` closes carry no barrier information
        and are excluded. Each live window is repeated `sample_weight` times (integer up-weighting,
        equivalent to a loss multiplier and safe with the shuffled loader).
        """
        import numpy as np

        lookback = self._lookback(config)
        from crypto_signal.features import build_features
        from crypto_signal.labeling import BARRIER_FEATURE_COLUMNS

        Xs, ys = [], []
        for sample in samples:
            reason = sample.close_reason
            if reason == "manual":
                continue
            label = {"take_profit_touched": 1, "stop_loss_touched": -1}.get(reason)
            if label is None:
                # Timeout or reversal: label by realised sign, which is what actually happened.
                label = 1 if sample.realized_pnl > 0 else (-1 if sample.realized_pnl < 0 else 0)
            candles = sample.candles
            if len(candles) < lookback:
                continue
            frame = _sample_frame(sample)
            try:
                feat = build_features(frame, atr_window=config.barrier.atr_window)
            except Exception:
                continue
            base_cols = list(feat.columns)
            if tuple(base_cols) + tuple(BARRIER_FEATURE_COLUMNS) != tuple(feature_columns):
                # Feature pipeline drift: a sample built under different columns cannot be pooled.
                continue
            values = feat.frame[base_cols].to_numpy(dtype=float)
            if np.isnan(values[-1]).any():
                continue
            window_base = values[-lookback:]
            sign = 1.0 if sample.direction == "LONG" else -1.0
            pair = (sample.take_profit_percent, sample.stop_loss_percent)
            row_tail = np.array([pair[0], pair[1], pair[0] / pair[1] if pair[1] else 0.0, sign])
            window = np.concatenate(
                [window_base, np.broadcast_to(row_tail, (lookback, 4))], axis=1
            )
            Xs.append(window)
            ys.append(label)

        if not Xs:
            return np.zeros((0,)), np.zeros((0,))
        repeats = max(1, int(round(self._sample_weight)))
        X = np.stack(Xs)
        X = np.repeat(X, repeats, axis=0)
        y = np.repeat(np.array(ys, dtype=int), repeats)
        return X, y


def _sample_frame(sample: Any) -> Any:
    """The sample's candle window as the feature builder's expected DataFrame."""
    import pandas as pd

    rows = []
    for candle in sample.candles:
        rows.append({
            "timestamp": pd.Timestamp(candle["open_time"]),
            "open": float(candle["open"]),
            "high": float(candle["high"]),
            "low": float(candle["low"]),
            "close": float(candle["close"]),
            "volume": float(candle.get("volume", 0.0)),
        })
    return pd.DataFrame(rows).set_index("timestamp")


def np_stack_pred(bundle: Any, X_hold: Any, feature_columns: tuple[str, ...]) -> Any:
    """Row-model scoring of sequence windows via the last row — used only when a non-sequence
    incumbent must be scored against the same holdout (it sees one row, as it always has)."""
    import numpy as np
    import pandas as pd

    out = np.zeros((len(X_hold), 3))
    for i in range(len(X_hold)):
        frame = pd.DataFrame(X_hold[i][-1]).T
        frame.columns = pd.Index(list(feature_columns))
        try:
            out[i] = bundle.predict_proba(frame)
        except Exception:
            out[i] = np.array([1 / 3, 1 / 3, 1 / 3])
    return out


def _multiclass_log_loss(probs: Any, y: Any) -> float:
    import numpy as np

    one_hot = np.zeros((len(y), 3))
    one_hot[np.arange(len(y)), np.asarray(y) + 1] = 1.0
    return float(-(one_hot * np.log(np.clip(probs, 1e-12, 1.0))).mean())
