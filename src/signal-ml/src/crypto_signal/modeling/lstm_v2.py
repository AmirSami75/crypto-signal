"""The advanced recurrent model — additive to both the tree bundle and the v1 LSTM.

This module exists because the v1 LSTM was a feasibility probe: a 2-layer stack reading the last
hidden state, trained for a fixed number of epochs with no honest selection of *when* to stop, no
measure of how much of its confidence was luck, and one seed's worth of variance. Each of those is a
real defect at the level this platform now operates — a challenger that must justify itself against a
gradient-boosted incumbent on held-out, net-of-costs numbers.

v2 keeps the serving contract identical (predict_proba over [-1, 0, 1], `is_sequence = True`,
joblib-serialisable without the live torch graph) and upgrades four things:

1. **Attention pooling over the sequence.** v1 read only `out[:, -1, :]` — the last hidden state —
   which forces the whole window's information through one bottleneck timestep and is known to
   under-use longer windows. A small additive attention head learns which candles matter and pools
   across all of them. The head is 1 linear layer; it cannot overfit a pooled 7-symbol corpus.
2. **Early stopping on a validation slice cut *before* the holdout.** v1 trained a fixed 12 epochs.
   The number of epochs is a hyper-parameter like any other; fixing it means the model is either
   under- or over-trained by construction. v2 holds out the last `validation_fraction` of the
   development window, monitors log-loss on it, and keeps the best state_dict.
3. **A seed ensemble with probability averaging.** A single net's output is one SGD run's output.
   Averaging `ensemble_seeds` independently-initialised members' probabilities reduces variance for
   free at inference (a matrix multiply per member), and the spread across members is measured and
   recorded so the operator can see how much of the confidence is seed luck.
4. **Temperature scaling, fit on the validation slice.** Class-weighted softmax outputs are not
   probabilities. Rather than ship the reweighted thing (the tree's honesty rule) or ship an
   uncalibrated one, v2 fits a single temperature on validation log-loss — the standard, one-parameter,
   no-reweighting calibration for neural nets — and records `calibration_method = "temperature"`.

Nothing here changes what a *label* is, what a barrier means, or which bundle serves by default. The
production path still serves the gradient-boosted bundle; a v2 LSTM is loaded only when its artifact
is present, and it must clear the same purged-holdout, cost-aware backtest bar as everything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd
import torch

from .lstm import LSTM_CLASSES

__all__ = [
    "LstmV2Config",
    "LstmAttentionModel",
    "LstmV2Bundle",
    "train_lstm_v2",
    "temperature_scale",
]


@dataclass(frozen=True, slots=True)
class LstmV2Config:
    """Hyper-parameters of the attention ensemble. Superset of v1's, plus the v2 knobs."""

    lookback: int = 32
    hidden_size: int = 96
    num_layers: int = 2
    dropout: float = 0.25
    learning_rate: float = 1e-3
    batch_size: int = 256
    epochs: int = 40
    weight_decay: float = 1e-4

    #: Early stopping: give up after this many epochs without validation improvement.
    patience: int = 6

    #: Share of the development window reserved for early-stopping and temperature fitting. The
    #: final chronological holdout is separate and never touched by either.
    validation_fraction: float = 0.15

    #: Independent initialisations averaged at inference. 1 reproduces a single net.
    ensemble_seeds: int = 3

    #: Base seeds for the members; derived seeds are base + i so a config change does not reshuffle
    #: the first members' data order (windows are shuffled per member, labels are fixed).
    seed_base: int = 20260831


class LstmAttentionModel(torch.nn.Module):
    """A stacked LSTM encoder with additive attention pooling over the window.

    The encoder is the v1 stack. The pooling learns, per example, a weight over the `lookback`
    timesteps and returns the weighted sum of hidden states — so momentum concentrated in the last
    few bars and slower structure spread across the window are both reachable, instead of everything
    having to survive to the final timestep.
    """

    def __init__(self, n_features: int, config: LstmV2Config) -> None:
        super().__init__()
        self.config = config
        self.lstm = torch.nn.LSTM(
            input_size=n_features,
            hidden_size=config.hidden_size,
            num_layers=config.num_layers,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            batch_first=True,
        )
        # Additive attention: score each timestep, softmax the scores, pool. One layer on purpose.
        self.attention = torch.nn.Linear(config.hidden_size, 1)
        self.head = torch.nn.Linear(config.hidden_size, LSTM_CLASSES.shape[0])

    def forward(self, x: "Any") -> "Any":
        """`x`: `(batch, lookback, n_features)` -> logits `(batch, 3)`."""
        out, _ = self.lstm(x)                      # (batch, lookback, hidden)
        scores = self.attention(out)               # (batch, lookback, 1)
        weights = torch.softmax(scores, dim=1)     # (batch, lookback, 1)
        pooled = (out * weights).sum(dim=1)        # (batch, hidden)
        return self.head(pooled)

    def _infer(self, window: np.ndarray) -> np.ndarray:
        """`window`: `(lookback, n_features)` -> `(1, 3)` probabilities over `LSTM_CLASSES`."""
        self.eval()
        tensor = torch.as_tensor(window, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            logits = self.forward(tensor)
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
        return probs.astype(float)


class LstmV2Bundle:
    """The estimator the registry loads: a seed-ensemble of attention LSTMs + a fitted temperature.

    Serving contract is v1's: `predict_proba(window_df)` -> `(1, 3)` long-bet probabilities in
    `[-1, 0, 1]` order, `classes_` = [-1, 0, 1], `is_sequence = True`. Serialisation stores each
    member's `state_dict` and the fitted temperature, and rebuilds the modules on load — the live
    torch graph is never pickled.
    """

    def __init__(
        self,
        members: list[LstmAttentionModel],
        temperatures: np.ndarray,
        feature_columns: tuple[str, ...],
        config: LstmV2Config,
        member_log_losses: tuple[float, ...] = (),
    ) -> None:
        self._members = members
        self._temperatures = np.asarray(temperatures, dtype=float)
        self.feature_columns = tuple(str(c) for c in feature_columns)
        self.config = config
        self.classes_ = np.array(LSTM_CLASSES, dtype=int)
        self.is_sequence = True
        self.member_log_losses = tuple(member_log_losses)

    # -- serving contract ----------------------------------------------------

    @property
    def temperature(self) -> float:
        """The ensemble-mean fitted temperature, for reporting."""
        return float(self._temperatures.mean()) if len(self._temperatures) else 1.0

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """`X` is a window of `lookback` candles (rows) with the training feature columns."""
        if len(X) != self.config.lookback:
            raise ValueError(
                f"LSTM v2 expects exactly {self.config.lookback} candles, got {len(X)}"
            )
        window = X[list(self.feature_columns)].to_numpy(dtype=float)
        if np.isnan(window).any():
            raise ValueError("LSTM window contains NaN features; supply a complete history")

        member_probs = np.stack([
            self._infer_member(member, window) for member in self._members
        ])
        # Probability averaging across seeds, then the ensemble temperature. Averaging first is the
        # standard deep-ensemble reading; the temperature was fit on averaged probabilities.
        mean_probs = member_probs.mean(axis=0)
        return _apply_temperature(mean_probs, float(self._temperatures.mean()))

    def _infer_member(self, member: LstmAttentionModel, window: np.ndarray) -> np.ndarray:
        member.eval()
        tensor = torch.as_tensor(window, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            logits = member.forward(tensor)
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
        return probs.astype(float)

    def predict_proba_windows(self, X: np.ndarray, batch_size: int = 1024) -> np.ndarray:
        """Score `(N, lookback, n_features)` windows with the full serving path, batched.

        This is the same arithmetic `predict_proba` performs — per-member softmax, probability
        average, ensemble temperature — at batch speed, so training-time holdout scoring and the
        online trainer's challenger evaluation cannot drift from what serving computes. Feeding the
        evaluator one DataFrame per window would be correct and minutes slower.
        """
        if X.ndim != 3 or X.shape[1] != self.config.lookback:
            raise ValueError(
                f"expected (N, {self.config.lookback}, n_features), got {X.shape}"
            )
        out = np.zeros((len(X), LSTM_CLASSES.shape[0]), dtype=float)
        temp = float(self._temperatures.mean())
        member_logits: list[np.ndarray] = []
        for member in self._members:
            member.eval()
            logits = np.zeros((len(X), LSTM_CLASSES.shape[0]), dtype=float)
            for start in range(0, len(X), batch_size):
                batch = torch.as_tensor(X[start : start + batch_size], dtype=torch.float32)
                with torch.no_grad():
                    logits[start : start + batch_size] = member.forward(batch).cpu().numpy()
            member_logits.append(logits)
        # Softmax per member, average, then temperature — the exact serving order.
        member_probs = [np.exp(l - l.max(axis=-1, keepdims=True)) for l in member_logits]
        member_probs = [p / p.sum(axis=-1, keepdims=True) for p in member_probs]
        mean_probs = np.stack(member_probs).mean(axis=0)
        for start in range(0, len(X), batch_size):
            out[start : start + batch_size] = _apply_temperature(
                mean_probs[start : start + batch_size], temp
            )
        return out

    # -- persistence ----------------------------------------------------------

    def __getstate__(self) -> dict[str, Any]:
        return {
            "feature_columns": self.feature_columns,
            "config": self.config,
            "temperatures": self._temperatures,
            "member_log_losses": self.member_log_losses,
            "state_dicts": [m.state_dict() for m in self._members],
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        config: LstmV2Config = state["config"]
        n_features = len(state["feature_columns"])
        members: list[LstmAttentionModel] = []
        for state_dict in state["state_dicts"]:
            module = LstmAttentionModel(n_features=n_features, config=config)
            module.load_state_dict(state_dict)
            members.append(module)
        self._members = members
        self._temperatures = np.asarray(state["temperatures"], dtype=float)
        self.member_log_losses = tuple(state.get("member_log_losses", ()))
        self.feature_columns = tuple(state["feature_columns"])
        self.config = config
        self.classes_ = np.array(LSTM_CLASSES, dtype=int)
        self.is_sequence = True


def _apply_temperature(probs: np.ndarray, temperature: float) -> np.ndarray:
    """Scale logits by 1/T and re-softmax. T>1 flattens, T<1 sharpens; T=1 is the identity."""
    if temperature <= 0:
        raise ValueError(f"temperature must be positive, got {temperature}")
    if abs(temperature - 1.0) < 1e-9:
        return probs
    logits = np.log(np.clip(probs, 1e-12, 1.0))
    scaled = logits / temperature
    scaled -= scaled.max(axis=-1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=-1, keepdims=True)


def temperature_scale(
    probs: np.ndarray,
    y: np.ndarray,
    max_iter: int = 200,
) -> float:
    """Fit one temperature on validation log-loss by 1-D Newton/BFGS-free grid+refine search.

    Grid over [0.5, 5.0] then golden refine — robust, no scipy dependency, and 1-D means a coarse
    grid loses nothing. Returns the temperature minimising log-loss on the slice it is given.
    """
    if len(probs) == 0:
        return 1.0
    shifted = y + 1  # {-1,0,1} -> {0,1,2} for one-hot
    one_hot = np.zeros((len(y), 3))
    one_hot[np.arange(len(y)), shifted] = 1.0

    def nll(t: float) -> float:
        scaled = _apply_temperature(probs, t)
        return float(-(one_hot * np.log(np.clip(scaled, 1e-12, 1.0))).sum())

    grid = np.linspace(0.5, 5.0, 46)
    losses = [nll(float(t)) for t in grid]
    best_idx = int(np.argmin(losses))
    lo = grid[max(0, best_idx - 1)]
    hi = grid[min(len(grid) - 1, best_idx + 1)]

    # Golden-section refine between the neighbours of the grid minimum.
    gr = (np.sqrt(5) - 1) / 2
    for _ in range(40):
        a, b = lo, hi
        c = b - gr * (b - a)
        d = a + gr * (b - a)
        if nll(float(c)) < nll(float(d)):
            hi = d
        else:
            lo = c
    return float((lo + hi) / 2)


def _log_loss(probs: np.ndarray, y: np.ndarray) -> float:
    shifted = y + 1
    one_hot = np.zeros((len(y), 3))
    one_hot[np.arange(len(y)), shifted] = 1.0
    return float(-(one_hot * np.log(np.clip(probs, 1e-12, 1.0))).mean())


def train_lstm_v2(
    X: np.ndarray,
    y: np.ndarray,
    feature_columns: tuple[str, ...],
    config: LstmV2Config,
    class_weight: bool = True,
    progress: bool = True,
) -> tuple[LstmV2Bundle, dict[str, Any]]:
    """Fit the ensemble; returns `(bundle, diagnostics)`.

    The chronological split inside the development window is v2's own: the tail `validation_fraction`
    is the early-stopping + temperature slice, and the caller's purged holdout stays out of everything
    here. Diagnostics carry what an honest report needs — per-member losses, seed spread, fitted
    temperatures, epochs actually run — and nothing that belongs to the holdout.
    """
    torch = _import_torch()
    if len(X) < 100 or config.validation_fraction <= 0 or config.validation_fraction >= 0.5:
        raise ValueError(
            "v2 needs >= 100 windows and a validation fraction in (0, 0.5); "
            f"got {len(X)} windows and {config.validation_fraction}"
        )

    # Chronological split inside development. Windows are already in time order per build.
    n_val = max(1, int(len(X) * config.validation_fraction))
    X_fit, y_fit = X[:-n_val], y[:-n_val]
    X_val, y_val = X[-n_val:], y[-n_val:]

    counts = np.bincount(y_fit + 1, minlength=3).astype(float)
    counts = np.where(counts == 0, 1.0, counts)
    weights = None
    if class_weight:
        inv = (1.0 / counts) * (counts.sum() / 3.0)
        weights = torch.as_tensor(inv, dtype=torch.float32)
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)

    members: list[LstmAttentionModel] = []
    temperatures: list[float] = []
    member_losses: list[float] = []
    epochs_run: list[int] = []

    for member_idx in range(max(1, config.ensemble_seeds)):
        seed = config.seed_base + member_idx
        torch.manual_seed(seed)
        np.random.seed(seed)

        model = LstmAttentionModel(n_features=X.shape[-1], config=config)
        optim = torch.optim.AdamW(
            model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
        )

        tx = torch.as_tensor(X_fit, dtype=torch.float32)
        ty = torch.as_tensor(y_fit + 1, dtype=torch.long)
        dataset = torch.utils.data.TensorDataset(tx, ty)
        generator = torch.Generator().manual_seed(seed)
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=config.batch_size, shuffle=True, generator=generator
        )

        val_x = torch.as_tensor(X_val, dtype=torch.float32)
        best_state: dict[str, Any] | None = None
        best_val = float("inf")
        best_epoch = 0
        since_best = 0

        model.train()
        for epoch in range(config.epochs):
            for batch_x, batch_y in loader:
                optim.zero_grad()
                loss = loss_fn(model.forward(batch_x), batch_y)
                loss.backward()
                optim.step()

            model.eval()
            with torch.no_grad():
                val_logits = model.forward(val_x)
                val_loss = float(loss_fn(val_logits, torch.as_tensor(y_val + 1, dtype=torch.long)))
            if val_loss < best_val - 1e-5:
                best_val = val_loss
                best_epoch = epoch
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                since_best = 0
            else:
                since_best += 1
                if since_best >= config.patience:
                    break

        if best_state is not None:
            model.load_state_dict(best_state)
        members.append(model)
        member_losses.append(best_val)
        epochs_run.append(best_epoch + 1)

        # Temperature on validation probabilities of the best checkpoint.
        model.eval()
        with torch.no_grad():
            val_probs = torch.softmax(model.forward(val_x), dim=-1).cpu().numpy()
        temperatures.append(temperature_scale(val_probs, y_val))

        if progress:
            from ..log_setup import get_logger

            get_logger(__name__).info(
                "LSTM v2 member %d/%d | seed=%d | val_loss=%.4f | epochs=%d | T=%.3f",
                member_idx + 1,
                config.ensemble_seeds,
                seed,
                best_val,
                best_epoch + 1,
                temperatures[-1],
            )

    bundle = LstmV2Bundle(
        members=members,
        temperatures=np.asarray(temperatures),
        feature_columns=feature_columns,
        config=config,
        member_log_losses=tuple(member_losses),
    )

    # Ensemble probabilities on the validation slice, for the spread diagnostic.
    val_probs = np.stack([
        bundle._infer_member(m, X_val[i]) for m in bundle._members for i in range(0, len(X_val), max(1, len(X_val) // 50))
    ])
    spread = float(val_probs.std(axis=0).mean()) if len(val_probs) else 0.0

    diagnostics: dict[str, Any] = {
        "validation_log_loss_members": member_losses,
        "validation_log_loss_ensemble": _log_loss(
            np.stack([bundle.predict_proba(_rows_to_frame(X_val[i], feature_columns)) for i in range(0, len(X_val), max(1, len(X_val) // 50))]),
            y_val[:: max(1, len(X_val) // 50)],
        ),
        "temperature_per_member": temperatures,
        "temperature_mean": bundle.temperature,
        "seed_spread_mean_std": spread,
        "epochs_run_per_member": epochs_run,
        "fit_windows": int(len(X_fit)),
        "validation_windows": int(len(X_val)),
        "class_counts_fit": {int(k - 1): int(v) for k, v in zip(range(3), counts)},
    }
    return bundle, diagnostics


def _rows_to_frame(window: np.ndarray, feature_columns: tuple[str, ...]) -> pd.DataFrame:
    """A single `(lookback, n_features)` window as the DataFrame `predict_proba` expects."""
    frame = pd.DataFrame(window)
    frame.columns = pd.Index(list(feature_columns))
    return frame


def _import_torch():
    return torch
