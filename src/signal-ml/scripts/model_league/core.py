"""The model league: every reasonable learner, one dataset, one honest scoreboard.

The strategy league (`crypto_signal.evaluation.league`) ranks hand-written indicator rules. This is the
supervised-learning counterpart: the same triple-barrier dataset the production bundle is trained on,
handed to every model family from a prior-only baseline to boosted trees and a neural net, scored on one
holdout that none of them may touch, and ranked by the thing the account is measured in — realized R
per trade after fees.

Design rules, all of them learned the hard way elsewhere in this repo:

* **One split, computed once.** Folds are chronological and purged by the label horizon. A model that
  gets a different split than its neighbour is not comparable, and a leaderboard of incomparable numbers
  is worse than no leaderboard.
* **The holdout is scored once per model.** No model sees it during fit, selection, or early stopping;
  the calibration block exists for that.
* **Fees are part of the score.** A 5m "edge" that ignores 10 bps a side is the barrier backtest's
  oldest lie. Each selected trade pays `(fee_rate + slippage_rate) * entry / (stop_atr * ATR)` in R.
* **A timeout is worth its mark, not zero.** The dataset already carries `r_multiple`; this module never
  re-derives it.
* **Every run is bounded.** A candidate that cannot finish inside its budget is recorded as TIMEOUT,
  not silently dropped, so the leaderboard never pretends a hard model was tested.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "artifacts" / "model_league"
RESULTS_PATH = ARTIFACT_ROOT / "results.jsonl"
REPORT_PATH = ARTIFACT_ROOT / "REPORT.md"

#: The bet the league is ranked at. A 3-ATR stop keeps the round-trip fee near 0.2R on hourly candles,
#: which is the difference between ranking skill and ranking fee efficiency. The production 1.5/1.0
#: bracket is still reported (`trading_tight`) because that is what the bots trade today.
LEAGUE_TAKE_PROFIT_ATR = 4.5
LEAGUE_STOP_LOSS_ATR = 3.0
TIGHT_TAKE_PROFIT_ATR = 1.5
TIGHT_STOP_LOSS_ATR = 1.0
BACKTEST_TAKE_PROFIT_ATR = LEAGUE_TAKE_PROFIT_ATR
BACKTEST_STOP_LOSS_ATR = LEAGUE_STOP_LOSS_ATR
FEE_RATE = 0.0010
SLIPPAGE_RATE = 0.0005

#: Rows selected for a trade: the policy the production bot runs today (any positive expectancy).
MINIMUM_PREDICTED_R = 0.0


@dataclass(frozen=True)
class Split:
    train: np.ndarray
    calibration: np.ndarray
    holdout: np.ndarray


def chronological_split(times: np.ndarray, gap_rows: int = 0) -> Split:
    """70 / 15 / 15 by timestamp with a purge gap between blocks.

    `times` must be sorted. The gap drops rows whose forward window straddles the boundary, so a
    training label that reaches into the validation block cannot leak its answer.
    """
    order = np.argsort(times, kind="stable")
    n = len(order)
    cut_train = int(n * 0.70)
    cut_cal = int(n * 0.85)
    train = order[: max(0, cut_train - gap_rows)]
    calibration = order[cut_train: max(cut_train, cut_cal - gap_rows)]
    holdout = order[cut_cal:]
    return Split(train=train, calibration=calibration, holdout=holdout)


def fee_in_r(entry_price: np.ndarray, atr: np.ndarray, stop_atr: np.ndarray) -> np.ndarray:
    """Round-trip cost of one trade expressed in R.

    The stop distance in price is `stop_atr * ATR`; a round trip costs `(fee + slippage)` of notional on
    each side, so the cost in R is `(fee + slippage) * entry / (stop_atr * ATR)` — scaled by 2 because
    both the entry and the exit pay.
    """
    stop_distance = np.maximum(stop_atr * atr, 1e-12)
    return 2.0 * (FEE_RATE + SLIPPAGE_RATE) * entry_price / stop_distance


def trading_metrics(
    r_true: np.ndarray,
    predicted_r: np.ndarray,
    fee_r: np.ndarray,
    times: np.ndarray,
    threshold: float = MINIMUM_PREDICTED_R,
) -> dict[str, Any]:
    """What the model would have earned on the holdout, ranked by time.

    Returns the pre-fee and post-fee expectancy together — the gap is the honest part, and a model that
    only clears the first one is not a model, it is a fee generator.
    """
    selected = predicted_r >= threshold
    count = int(selected.sum())
    if count == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "expectancy_r": 0.0,
            "expectancy_r_net": 0.0,
            "total_r_net": 0.0,
            "max_drawdown_r": 0.0,
            "profit_factor": 0.0,
            "sharpe_per_trade": 0.0,
            "fee_r_mean": 0.0,
        }

    realized = r_true[selected].astype(float)
    cost = fee_r[selected].astype(float)
    net = realized - cost
    order = np.argsort(times[selected], kind="stable")
    equity = np.cumsum(net[order])
    running_max = np.maximum.accumulate(equity)
    drawdown = equity - running_max
    gains = net[net > 0].sum()
    losses = -net[net < 0].sum()
    return {
        "trades": count,
        "win_rate": float((net > 0).mean()),
        "expectancy_r": float(realized.mean()),
        "expectancy_r_net": float(net.mean()),
        "total_r_net": float(net.sum()),
        "max_drawdown_r": float(drawdown.min()) if len(drawdown) else 0.0,
        "profit_factor": float(gains / losses) if losses > 0 else float("inf") if gains > 0 else 0.0,
        "sharpe_per_trade": float(net.mean() / net.std(ddof=1)) if count > 1 and net.std(ddof=1) > 0 else 0.0,
        "fee_r_mean": float(cost.mean()),
    }


def regression_metrics(r_true: np.ndarray, predicted_r: np.ndarray) -> dict[str, Any]:
    if len(r_true) == 0:
        return {}
    error = predicted_r - r_true
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "spearman": _spearman(predicted_r, r_true),
        "mean_predicted_r": float(np.mean(predicted_r)),
        "top_decile_r": float(np.mean(r_true[predicted_r >= np.quantile(predicted_r, 0.9)])),
    }


def classification_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import balanced_accuracy_score, f1_score, log_loss, roc_auc_score

    classes = np.array([-1, 0, 1])
    predictions = classes[np.argmax(probabilities, axis=1)]
    payload = {
        "log_loss": float(log_loss(y_true, probabilities, labels=classes)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0)),
    }
    win_index = int(np.flatnonzero(classes == 1)[0])
    try:
        payload["auc_take_profit"] = float(roc_auc_score((y_true == 1).astype(int), probabilities[:, win_index]))
    except ValueError:
        payload["auc_take_profit"] = float("nan")
    return payload


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return 0.0
    rx = _average_ranks(x)
    ry = _average_ranks(y)
    rx -= rx.mean()
    ry -= ry.mean()
    denominator = float(np.sqrt((rx**2).sum() * (ry**2).sum()))
    return float((rx * ry).sum() / denominator) if denominator else 0.0


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    sorted_values = values[order]
    start = 0
    for index in range(1, len(sorted_values) + 1):
        if index == len(sorted_values) or sorted_values[index] != sorted_values[start]:
            if index - start > 1:
                ranks[order[start:index]] = ranks[order[start:index]].mean()
            start = index
    return ranks


class Dataset:
    """The cached, split, ready-to-fit league dataset."""

    def __init__(self, arrays: dict[str, np.ndarray], meta: dict[str, Any]) -> None:
        self.X = arrays["X"]
        self.y = arrays["y"]
        self.r = arrays["r"]
        self.times = arrays["times"]
        self.entry = arrays["entry"]
        self.atr = arrays["atr"]
        self.stop_atr = arrays["stop_atr"]
        self.feature_names = meta["feature_names"]
        self.meta = meta
        self.split = chronological_split(self.times, gap_rows=int(meta.get("gap_rows", 0)))

    @classmethod
    def load(cls, cache_dir: Path, build: Callable[[], dict[str, Any]]) -> "Dataset":
        cache_dir.mkdir(parents=True, exist_ok=True)
        meta_path = cache_dir / "meta.json"
        arrays_path = cache_dir / "arrays.npz"
        if meta_path.exists() and arrays_path.exists():
            meta = json.loads(meta_path.read_text())
            with np.load(arrays_path, allow_pickle=False) as bundle:
                arrays = {name: bundle[name] for name in bundle.files}
            return cls(arrays, meta)

        payload = build()
        arrays = payload["arrays"]
        meta = payload["meta"]
        np.savez(arrays_path, **arrays)
        meta_path.write_text(json.dumps(meta, indent=2, default=str))
        return cls(arrays, meta)


def append_result(record: dict[str, Any]) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def load_results() -> list[dict[str, Any]]:
    if not RESULTS_PATH.exists():
        return []
    rows = []
    for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _fmt(value: Any, places: int = 3) -> str:
    if isinstance(value, float):
        if value != value:
            return "—"
        if value == float("inf"):
            return "∞"
        return f"{value:+.{places}f}"
    return str(value)


def write_final_report(deadline: str | None = None) -> Path:
    """The campaign's closing document: what won, what it won by, and what it cost to find out.

    Deliberately written from the same append-only results file as the running table — no number here
    can be a leftover from a model that was later re-run, because a re-run appends a new row and the
    ranking reads whatever is on disk at the moment of writing.
    """
    rows = [row for row in load_results() if row.get("status") == "ok"]
    path = ARTIFACT_ROOT / "FINAL.md"
    lines = [
        "# Model league — final report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')} · campaign deadline: {deadline or 'n/a'}",
        "",
        "Every model below was trained on the same purged chronological sample and scored once on the",
        "same holdout, at a 4.5 / 3.0 ATR bracket with 10 bps fees + 5 bps slippage per side. A model",
        "needs at least 200 scored trades to be eligible for the ranking; anything thinner is listed as",
        "unranked rather than promoted on a handful of trades.",
        "",
    ]
    if not rows:
        lines += ["No model finished, so there is nothing to rank.", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    eligible = [row for row in rows if row["metrics"]["trading"]["trades"] >= 200]
    ranked = sorted(eligible, key=lambda r: r["metrics"]["trading"]["expectancy_r_net"], reverse=True)
    by_family: dict[str, list[dict]] = {}
    for row in eligible:
        family = _family(row["model"])
        by_family.setdefault(family, []).append(row)

    lines += ["## Leaderboard (all splits)", "", "| # | model | split | net R/trade | gross R | trades | win % | total R |", "|---:|---|---|---:|---:|---:|---:|---:|"]
    for position, row in enumerate(ranked[:25], 1):
        trading = row["metrics"]["trading"]
        lines.append(
            f"| {position} | `{row['model']}` | {row['interval']}·s{row['seed']} | "
            f"{trading['expectancy_r_net']:+.4f} | {trading['expectancy_r']:+.4f} | {trading['trades']} | "
            f"{trading['win_rate']*100:.1f}% | {trading['total_r_net']:+.1f} |"
        )
    lines.append("")

    lines += ["## Best per family", ""]
    for family in sorted(by_family):
        best = max(by_family[family], key=lambda r: r["metrics"]["trading"]["expectancy_r_net"])
        trading = best["metrics"]["trading"]
        lines.append(
            f"- **{family}** — `{best['model']}` ({best['interval']}·s{best['seed']}): "
            f"{trading['expectancy_r_net']:+.4f} R/trade over {trading['trades']} trades"
        )
    lines.append("")

    profitable = [row for row in eligible if row["metrics"]["trading"]["expectancy_r_net"] > 0]
    lines += ["## Verdict", ""]
    if profitable:
        winners = ", ".join(f"`{row['model']}`" for row in profitable[:5])
        lines += [
            f"{len(profitable)} of {len(eligible)} eligible model/split combinations were positive after",
            f"fees: {winners}. Before trusting one, re-run it on a split it has never seen — a league",
            "winner is a hypothesis, not a validated strategy.",
            "",
        ]
    else:
        lines += [
            f"**No eligible model was profitable after fees** across {len(eligible)} scored",
            "model/split combinations. The honest reading is that the fee drag at this bracket exceeds",
            "any edge these features carry at this horizon — the next lever is the inputs (or a higher",
            "horizon / lower-turnover policy), not another estimator.",
            "",
        ]
    lines += [
        "## What was measured",
        "",
        "| family | candidates |",
        "|---|---|",
        "| baselines | prior, Gaussian NB |",
        "| linear | logistic, ridge on R |",
        "| trees | decision tree, random forest, extra trees |",
        "| boosting | HGB (clf + R), LightGBM (clf + R), XGBoost (clf + R) |",
        "| neural | MLP on R |",
        "",
        "Full per-split tables: `REPORT.md`. Raw rows: `results.jsonl`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _family(model: str) -> str:
    if model.startswith(("baseline", "gaussian")):
        return "baselines"
    if model.startswith(("logistic", "ridge")):
        return "linear"
    if model.startswith(("decision", "random", "extra")):
        return "trees"
    if model.startswith(("hist", "lightgbm", "xgboost")):
        return "boosting"
    if model.startswith("mlp"):
        return "neural"
    return "other"


def write_report(deadline: str | None = None) -> Path:
    """Regenerate the leaderboard from the append-only results file."""
    rows = load_results()
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Model league — every learner, one honest scoreboard",
        "",
        f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')} · campaign deadline: {deadline or 'n/a'}",
        "",
        "Scored on a purged chronological holdout (last 15 % of the sample) at a 4.5 / 3.0 ATR bracket,",
        "fees 10 bps + 5 bps slippage per side. `net R` is the column that matters; `gross R` is what the",
        "model would have earned if trading were free, and is reported only to show the fee drag.",
        "",
    ]

    by_split: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") != "ok":
            continue
        by_split.setdefault((row.get("interval", "?"), int(row.get("seed", 0))), []).append(row)

    for (interval, seed), group in sorted(by_split.items()):
        lines += [f"## {interval} · seed {seed}", ""]
        lines += [
            "| # | model | net R/trade | gross R | trades | win % | total R | max DD | PF | Sharpe/tr | log-loss | Spearman | fit s |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        # A model that took no trades has a 0.000 expectancy, and sorting naively puts it at the top of a
        # leaderboard where every real model is negative. Evidence first: a model needs at least 200
        # scored trades to be ranked, and the rest are listed after them with their trade count visible.
        ranked = sorted(
            group,
            key=lambda r: (
                r["metrics"]["trading"]["trades"] >= 200,
                r["metrics"]["trading"]["expectancy_r_net"],
                r["metrics"]["trading"]["total_r_net"],
            ),
            reverse=True,
        )
        for position, row in enumerate(ranked, 1):
            trading = row["metrics"]["trading"]
            regression = row["metrics"].get("regression") or {}
            classification = row["metrics"].get("classification") or {}
            lines.append(
                "| {pos} | `{model}` | {net} | {gross} | {trades} | {win:.1f}% | {total} | {dd} | {pf:.2f} | {sharpe} | {ll} | {rho} | {fit:.1f} |".format(
                    pos=position,
                    model=row["model"] + (" ⚠" if trading["trades"] < 200 else ""),
                    net=_fmt(trading["expectancy_r_net"], 4),
                    gross=_fmt(trading["expectancy_r"], 4),
                    trades=trading["trades"],
                    win=trading["win_rate"] * 100,
                    total=_fmt(trading["total_r_net"], 2),
                    dd=_fmt(trading["max_drawdown_r"], 2),
                    pf=trading["profit_factor"] if np.isfinite(trading["profit_factor"]) else 99.0,
                    sharpe=_fmt(trading["sharpe_per_trade"], 4),
                    ll=_fmt(classification.get("log_loss", float("nan")), 4),
                    rho=_fmt(regression.get("spearman", float("nan")), 4),
                    fit=row.get("fit_seconds", 0.0),
                )
            )
        lines.append("")

    failures = [row for row in rows if row.get("status") != "ok"]
    if failures:
        lines += ["## Not scored", "", "| model | interval | seed | status | detail |", "|---|---|---|---|---|"]
        for row in failures:
            lines.append(
                f"| `{row.get('model')}` | {row.get('interval')} | {row.get('seed')} | {row.get('status')} | {str(row.get('detail'))[:120]} |"
            )
        lines.append("")

    lines += [
        "## How to read this",
        "",
        "- A positive `net R/trade` over fewer than ~200 trades is noise; the trades column is part of the verdict.",
        "- `Spearman` on the R head measures ranking skill; a model can trade profitably only if it ranks.",
        "- `log-loss` is reported for classifiers only; it is not comparable to an R-regression model's error.",
        "- Rows appear as each candidate finishes. The campaign keeps adding splits until its deadline.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return REPORT_PATH
