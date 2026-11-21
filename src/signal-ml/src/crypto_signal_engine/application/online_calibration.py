"""The fast learning loop: recalibrate a market's confidence from its own closed trades.

The slow loop (`online_learning.py`) refits a challenger and gates it — minutes to hours, and it only
runs after dozens of samples. The fast loop answers a narrower question after **every** closed trade:
*when this market's model says 62 %, how often does that bet actually win?* — and maps the model's raw
confidence onto the observed rate before the next decision is priced.

That mapping is deliberately conservative:

* It is **per market** (`SYMBOL|INTERVAL`), because calibration does not transfer across timeframes.
* It needs at least `MIN_SAMPLES` resolved trades (default 60) before it changes anything, and uses a
  Beta-style prior equal to the bin centre so ten lucky trades cannot move the curve.
* It is **monotone**: the adjusted map is forced non-decreasing, so a higher raw score can never become
  a lower probability. A non-monotone map silently turns the model's ranking against itself.
* It persists to JSON, so a restart does not forget what the market taught it, and every adjustment is
  inspectable (`status()` reports each market's sample count and ready flag).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

#: Bins over raw confidence. Fixed, because a curve whose edges move between fits cannot be compared
#: with yesterday's — and comparing is the whole point of storing it.
BIN_EDGES: tuple[float, ...] = (0.0, 0.45, 0.55, 0.65, 0.75, 0.85, 1.0001)

#: How many resolved trades a market needs before its curve is allowed to change a decision.
MIN_SAMPLES = 60

#: Prior weight, in pseudo-trades, pulling a sparse bin toward its own centre.
PRIOR_STRENGTH = 20.0

#: A curve that would move confidence by less than this is not worth the risk of applying it.
MINIMUM_EFFECT = 0.005


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    predicted: float
    won: bool
    at: str

    def to_record(self) -> dict:
        return {"p": self.predicted, "won": self.won, "at": self.at}

    @classmethod
    def from_record(cls, record: dict) -> "CalibrationPoint":
        return cls(predicted=float(record["p"]), won=bool(record["won"]), at=str(record.get("at", "")))


class MarketCurve:
    """A monotone map from raw confidence to observed win rate, fitted by isotonic regression.

    Isotonic rather than a hand-rolled running maximum: pooling adjacent violators keeps a bin that
    genuinely disagrees with its neighbour instead of flattening it, while still guaranteeing that a
    higher raw score never becomes a lower probability.
    """

    def __init__(
        self,
        model,
        centres: list[float],
        rates: list[float],
        samples: int,
        constant: float | None = None,
    ) -> None:
        self._model = model
        self._centres = centres
        self._rates = rates
        self._constant = constant
        self.samples = samples

    def __call__(self, probability: float) -> float:
        if self._constant is not None:
            # A market whose model only ever says one number has no ranking to protect; the honest
            # correction is that one number's observed rate.
            adjusted = self._constant
        else:
            adjusted = float(self._model.predict(np.array([float(probability)]))[0])
        return min(max(adjusted, 0.01), 0.99)

    def describe(self) -> dict:
        return {
            "centres": [round(float(c), 4) for c in self._centres],
            "rates": [round(float(r), 4) for r in self._rates],
            "samples": self.samples,
        }


def fit_curve(points: list[CalibrationPoint]) -> MarketCurve | None:
    """Fit the binned, shrunk, isotonic map. `None` when the sample cannot support one.

    The anchor of a bin is the **mean predicted probability of its rows**, not the bin's geometric
    centre: predictions cluster inside a bin (a market that only ever says 0.44 lands in the 0–0.45 bin),
    and anchoring on the centre would then manufacture a correction out of the binning itself.
    """
    if len(points) < MIN_SAMPLES:
        return None
    predicted = np.array([p.predicted for p in points], dtype=float)
    won = np.array([1.0 if p.won else 0.0 for p in points], dtype=float)
    if won.min() == won.max():
        return None  # all wins or all losses: a curve would memorise one outcome

    anchors: list[float] = []
    rates: list[float] = []
    weights: list[float] = []
    for lower, upper in zip(BIN_EDGES[:-1], BIN_EDGES[1:]):
        mask = (predicted >= lower) & (predicted < upper)
        count = int(mask.sum())
        if count < 10:
            continue  # too thin to say anything; not a fake identity point either
        anchor = float(predicted[mask].mean())
        observed = float(won[mask].mean())
        shrunk = (observed * count + anchor * PRIOR_STRENGTH) / (count + PRIOR_STRENGTH)
        anchors.append(anchor)
        rates.append(shrunk)
        weights.append(float(count))

    if not anchors:
        return None
    if max(abs(rate - anchor) for anchor, rate in zip(anchors, rates)) < MINIMUM_EFFECT:
        return None  # well calibrated already: applying a curve would only add a failure mode
    if len(anchors) == 1:
        return MarketCurve(None, anchors, rates, len(points), constant=rates[0])

    from sklearn.isotonic import IsotonicRegression

    model = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
    model.fit(np.asarray(anchors), np.asarray(rates), sample_weight=np.asarray(weights))
    fitted = [float(value) for value in model.predict(np.asarray(anchors))]
    return MarketCurve(model, anchors, fitted, len(points))


class CalibrationStore:
    """Per-market outcome history and the curve it supports. Thread-safe and append-only on disk."""

    def __init__(self, path: Path, max_points_per_market: int = 2_000) -> None:
        self._path = Path(path)
        self._max = max_points_per_market
        self._lock = threading.RLock()
        self._points: dict[tuple[str, str], list[CalibrationPoint]] = {}
        self._load()

    # ── persistence ─────────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            for key, records in payload.get("markets", {}).items():
                symbol, _, interval = key.partition("|")
                self._points[(symbol, interval)] = [
                    CalibrationPoint.from_record(record) for record in records
                ]
            logger.info("Calibration store loaded | markets=%s", len(self._points))
        except Exception:  # noqa: BLE001 — a corrupt store must not stop the engine from serving
            logger.exception("Calibration store could not be read; starting empty")
            self._points = {}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "markets": {
                f"{symbol}|{interval}": [point.to_record() for point in points]
                for (symbol, interval), points in self._points.items()
            },
        }
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    # ── writes ──────────────────────────────────────────────────────────────
    def add(self, symbol: str, interval: str, predicted: float, won: bool) -> int:
        key = (symbol.upper(), interval)
        with self._lock:
            points = self._points.setdefault(key, [])
            points.append(
                CalibrationPoint(
                    predicted=float(predicted),
                    won=bool(won),
                    at=datetime.now(timezone.utc).isoformat(),
                )
            )
            if len(points) > self._max:
                del points[: len(points) - self._max]
            self._persist()
            return len(points)

    # ── reads ───────────────────────────────────────────────────────────────
    def curve(self, symbol: str, interval: str) -> MarketCurve | None:
        with self._lock:
            points = list(self._points.get((symbol.upper(), interval), ()))
        return fit_curve(points)

    def adjuster(self, symbol: str, interval: str) -> Callable[[np.ndarray], np.ndarray] | None:
        """A vectorised adjuster for a `(n, 3)` probability matrix, or `None` when not ready."""
        curve = self.curve(symbol, interval)
        if curve is None:
            return None

        def _apply(probabilities: np.ndarray) -> np.ndarray:
            matrix = np.array(probabilities, dtype=float, copy=True)
            if matrix.ndim != 2 or matrix.shape[1] != 3:
                return probabilities
            raw_win = matrix[:, 2]
            adjusted_win = np.array([curve(value) for value in raw_win], dtype=float)
            # Keep the distribution honest: the loss and timeout masses shrink in proportion to the
            # win mass that was moved, so the row still sums to one and no branch is invented.
            remaining_old = np.maximum(1.0 - raw_win, 1e-9)
            remaining_new = np.maximum(1.0 - adjusted_win, 1e-9)
            scale = remaining_new / remaining_old
            matrix[:, 0] *= scale
            matrix[:, 1] *= scale
            matrix[:, 2] = adjusted_win
            totals = matrix.sum(axis=1, keepdims=True)
            return matrix / np.where(totals > 0, totals, 1.0)

        return _apply

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "symbol": symbol,
                    "interval": interval,
                    "samples": len(points),
                    "ready": len(points) >= MIN_SAMPLES,
                }
                for (symbol, interval), points in sorted(self._points.items())
            ]
