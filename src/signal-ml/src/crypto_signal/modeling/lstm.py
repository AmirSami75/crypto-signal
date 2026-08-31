"""An experimental recurrent signal model — additive to the gradient-boosted baseline.

This module exists because the operator asked for a model that learns from the *sequence* of candles
leading up to a decision, not just the latest feature row. A gradient-boosted tree sees one row at a
time; an LSTM sees a window of `lookback` consecutive candles and can in principle pick up momentum and
reversal structure across that span.

It is deliberately **additive and experimental**:

- The production path keeps serving the histogram-gradient-boosting bundle by default. This model is only
  loaded when a `_pooled_<INTERVAL>.joblib` (or per-symbol) bundle whose metadata says
  `is_sequence = True` is present, and it is reported separately as experimental.
- The `docs/ml-improvement-plan.md` explicitly rejects deep learning on 1h bars ("no robust dominance
  after costs"). Nothing here changes that verdict. A trained LSTM must clear the same purged-holdout,
  cost-aware backtest bar as the tree — net of fees and slippage — or it stays flagged experimental and
  is never auto-promoted over the existing bundle.

Serving contract (same as every other estimator the engine loads):

- `predict_proba(X)` returns probabilities in `ALL_CLASSES` order `[-1, 0, 1]`, where `-1` is
  "the stop came first", `0` is "neither barrier inside the horizon", and `+1` is "the take-profit came
  first" — for a **long** bet at the canonical bracket the bundle was trained on.
- `classes_` is `np.array([-1, 0, 1])` so the serving layer can hand the bundle to the same code path.
- `is_sequence` is `True`, which tells the evaluator to feed a window of `lookback` candles rather than
  the single latest row.

The short side is derived by mirroring the long probabilities: a short bet's take-profit is the long
bet's stop, and vice versa, so `short_probs = long_probs[::-1]`. This keeps one network and a single
label while still pricing both directions in `choose_direction`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from ..domain.barriers import Direction
from ..labeling.triple_barrier import BarrierPair, label_triple_barrier
from .estimator import ALL_CLASSES


#: The class the LSTM predicts for a long bet, in `predict_proba` column order.
LSTM_CLASSES = np.array([-1, 0, 1], dtype=int)


@dataclass(frozen=True, slots=True)
class LstmConfig:
    """Hyper-parameters of the recurrent net and its input window.

    `lookback` is load-bearing: it is written into the bundle metadata and read back by the serving
    layer, because feeding the model a window of a different length than it trained on is a silent
    mis-feature, exactly like an ATR window mismatch on the tree.
    """

    lookback: int = 24
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    learning_rate: float = 1e-3
    batch_size: int = 256
    epochs: int = 12
    weight_decay: float = 1e-5


def _import_torch():
    """Torch is imported at module load; this helper exists so call sites read clearly."""
    return torch


class LstmSignalModel(torch.nn.Module):
    """A small stacked-LSTM classifier over a window of scale-free candle features.

    The window is `(lookback, n_features)`; the output is a 3-class probability over the long-bet
    triple-barrier outcome. It is intentionally tiny — the point is a correct sequence signal, not to
    win a parameter-count contest, and a small net trains in seconds on a CPU.
    """

    def __init__(self, n_features: int, config: LstmConfig) -> None:
        super().__init__()
        self.config = config
        self.n_features = n_features
        self.lstm = torch.nn.LSTM(
            input_size=n_features,
            hidden_size=config.hidden_size,
            num_layers=config.num_layers,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            batch_first=True,
        )
        self.head = torch.nn.Linear(config.hidden_size, LSTM_CLASSES.shape[0])

    def forward(self, x: "Any") -> "Any":
        """`x`: `(batch, lookback, n_features)` -> logits `(batch, 3)`."""
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        return self.head(last)

    def _infer(self, window: np.ndarray) -> np.ndarray:
        """`window`: `(lookback, n_features)` -> `(1, 3)` probabilities over `LSTM_CLASSES`."""
        self.eval()
        tensor = torch.as_tensor(window, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            logits = self.forward(tensor)
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
        return probs.astype(float)


class LstmBundle:
    """The estimator the registry loads: wraps `LstmSignalModel` with the serving contract.

    It is joblib-serialisable without pickling the live torch graph — only the hyper-parameters, the
    feature column order and the fitted `state_dict` are stored, and the module is rebuilt on load. That
    keeps artifacts small and avoids the version-skew surprises of pickling `nn.Module` objects.
    """

    def __init__(
        self,
        module: LstmSignalModel,
        feature_columns: tuple[str, ...],
        config: LstmConfig,
    ) -> None:
        self._module = module
        self.feature_columns = tuple(str(c) for c in feature_columns)
        self.config = config
        self.classes_ = np.array(LSTM_CLASSES, dtype=int)
        #: Tells the evaluator to feed a window, not a single row.
        self.is_sequence = True

    # -- serving contract ----------------------------------------------------

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """`X` is a window of `lookback` candles (rows) with the training feature columns.

        Returns `(1, 3)` long-bet probabilities in `[-1, 0, 1]` order. The serving layer mirrors these
        to price the short side.
        """
        if len(X) != self.config.lookback:
            raise ValueError(
                f"LSTM expects exactly {self.config.lookback} candles, got {len(X)}"
            )
        window = X[list(self.feature_columns)].to_numpy(dtype=float)
        if np.isnan(window).any():
            raise ValueError("LSTM window contains NaN features; supply a complete history")
        return self._module._infer(window)

    # -- persistence ----------------------------------------------------------

    def __getstate__(self) -> dict[str, Any]:
        return {
            "feature_columns": self.feature_columns,
            "config": self.config,
            "state_dict": self._module.state_dict(),
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        config: LstmConfig = state["config"]
        module = LstmSignalModel(n_features=len(state["feature_columns"]), config=config)
        module.load_state_dict(state["state_dict"])
        self._module = module
        self.feature_columns = tuple(state["feature_columns"])
        self.config = config
        self.classes_ = np.array(LSTM_CLASSES, dtype=int)
        self.is_sequence = True


def train_lstm(
    X: np.ndarray,
    y: np.ndarray,
    feature_columns: tuple[str, ...],
    config: LstmConfig,
    class_weight: bool = True,
    progress: bool = True,
) -> LstmBundle:
    """Fit an `LstmBundle` on `(N, lookback, n_features)` windows and `(N,)` labels in `{-1,0,1}`.

    Mirrors the gradient-boosting convention: `class_weight="balanced"` reweights scarce classes for a
    better ranking, but the raw softmax is what ships — the same honesty the tree pipeline applies, since
    a calibrated probability is the operator's expectation and a reweighted one is not a probability.
    """
    torch = _import_torch()
    device = torch.device("cpu")
    model = LstmSignalModel(n_features=X.shape[-1], config=config).to(device)

    tensors_x = torch.as_tensor(X, dtype=torch.float32)
    # Labels are in {-1, 0, 1}; `CrossEntropyLoss` expects class indices 0..2, so shift by one. The
    # network's output columns stay in `[-1, 0, 1]` order (see `LSTM_CLASSES`), which is what the serving
    # layer consumes, so the shift is purely an internal training detail.
    tensors_y = torch.as_tensor(y + 1, dtype=torch.long)
    dataset = torch.utils.data.TensorDataset(tensors_x, tensors_y)
    loader = torch.utils.data.DataLoader(dataset, batch_size=config.batch_size, shuffle=True)

    weights = None
    if class_weight:
        counts = np.bincount(y + 1, minlength=3).astype(float)
        counts = np.where(counts == 0, 1.0, counts)
        inv = (1.0 / counts) * (counts.sum() / 3.0)
        weights = torch.as_tensor(inv, dtype=torch.float32)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    optim = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )

    model.train()
    for epoch in range(config.epochs):
        epoch_loss = 0.0
        batches = 0
        for batch_x, batch_y in loader:
            optim.zero_grad()
            logits = model.forward(batch_x)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            optim.step()
            epoch_loss += float(loss.item())
            batches += 1
        if progress:
            from ..log_setup import get_logger

            get_logger(__name__).info(
                "LSTM epoch %s/%s | loss=%.4f", epoch + 1, config.epochs, epoch_loss / max(batches, 1)
            )

    return LstmBundle(module=model, feature_columns=feature_columns, config=config)


def build_lstm_sequences(
    frames: dict[str, pd.DataFrame],
    interval: str,
    config: LstmConfig,
    atr_window: int,
    max_horizon: int,
    take_profit_atr: float,
    stop_loss_atr: float,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], np.ndarray]:
    """Turn candle frames into `(N, lookback, n_features)` windows and triple-barrier labels.

    Each window carries the `lookback` scale-free candle features plus the bet's barrier columns
    (`take_profit_atr`, `stop_loss_atr`, `risk_reward_ratio`) and a `direction_sign` (+1/-1), exactly the
    columns the tree model sees — so the LSTM is conditioned on the same bet it is scoring. Both directions
    are labelled per candle (long and short bets at the canonical bracket), so one network answers for
    either side at serving time by flipping `direction_sign` across the window.

    Windows never cross a symbol boundary, so there is no leakage between unrelated markets. Labels are in
    `{-1, 0, 1}` = stop / timeout / take-profit first. Returns `X`, `y`, `feature_columns` and `times`
    (the open time of each window's latest candle) so the caller can split chronologically with a purge.
    """
    from ..features import build_features
    from ..labeling.triple_barrier import BARRIER_FEATURE_COLUMNS

    lookback = config.lookback
    windows: list[np.ndarray] = []
    labels: list[int] = []
    times: list[Any] = []
    feature_columns: tuple[str, ...] | None = None

    for symbol in sorted(frames):
        raw = frames[symbol].reset_index(drop=True)
        timestamps = raw["timestamp"].to_numpy()
        close = raw["close"].astype(float).to_numpy()
        high = raw["high"].astype(float).to_numpy()
        low = raw["low"].astype(float).to_numpy()

        feat = build_features(raw, atr_window=atr_window)
        base_cols = list(feat.columns)
        base = feat.frame[base_cols].copy()
        atr = feat.atr.astype(float).to_numpy()
        if feature_columns is None:
            # Match the tree's feature order: base scale-free columns, then the barrier columns.
            feature_columns = tuple(base_cols) + tuple(BARRIER_FEATURE_COLUMNS)
        elif tuple(base_cols) + tuple(BARRIER_FEATURE_COLUMNS) != feature_columns:
            raise ValueError(f"feature columns differ for {symbol}; pooling would misalign")

        pair = BarrierPair(take_profit_atr=take_profit_atr, stop_loss_atr=stop_loss_atr)
        risk_reward = pair.take_profit_atr / pair.stop_loss_atr
        complete = ~base.isna().any(axis=1).to_numpy()

        # Labelled once per direction for the whole series (the labeller is vectorised), then indexed per
        # candle — calling it per candle would rescan the series and be quadratic.
        tagged_long = label_triple_barrier(high, low, close, atr, Direction.LONG, pair, max_horizon=max_horizon)
        tagged_short = label_triple_barrier(high, low, close, atr, Direction.SHORT, pair, max_horizon=max_horizon)
        labels_by_direction = {
            Direction.LONG: tagged_long,
            Direction.SHORT: tagged_short,
        }

        values = base.to_numpy(dtype=float)
        for i in range(lookback - 1, len(base)):
            if not complete[i] or not complete[i - lookback + 1 : i + 1].all():
                continue
            window_base = values[i - lookback + 1 : i + 1]
            for direction in (Direction.LONG, Direction.SHORT):
                tagged = labels_by_direction[direction]
                outcome = int(tagged.outcome[i])
                if not bool(tagged.resolved[i]):
                    continue
                row_tail = np.array(
                    [take_profit_atr, stop_loss_atr, risk_reward, float(direction.sign)]
                )
                window = np.concatenate(
                    [window_base, np.broadcast_to(row_tail, (lookback, 4))], axis=1
                )
                windows.append(window)
                labels.append(outcome)
                times.append(timestamps[i])

    if not windows:
        raise ValueError("no usable LSTM sequences; need more candles or a smaller lookback")
    if feature_columns is None:  # pragma: no cover - only if frames were empty
        raise ValueError("no features produced; frames were empty")

    X = np.stack(windows, axis=0)
    y = np.array(labels, dtype=int)
    return X, y, feature_columns, np.asarray(times)
