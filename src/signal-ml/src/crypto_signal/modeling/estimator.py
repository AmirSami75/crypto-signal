from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    f1_score,
    log_loss,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.utils.class_weight import compute_sample_weight

from ..config import ModelConfig
from ..log_setup import get_logger
from .splitting import TimeGroupedSplit, candles_between


ALL_CLASSES = np.array([-1, 0, 1], dtype=int)
logger = get_logger(__name__)


def build_model(config: ModelConfig, verbose: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=config.learning_rate,
        max_iter=config.max_iter,
        max_leaf_nodes=config.max_leaf_nodes,
        min_samples_leaf=config.min_samples_leaf,
        l2_regularization=config.l2_regularization,
        # sklearn's automatic validation split is not chronological. Disable it
        # here so early stopping cannot quietly introduce temporal leakage.
        early_stopping=False,
        random_state=config.random_state,
        verbose=verbose,
    )


def fit_model(
    X: pd.DataFrame,
    y: pd.Series,
    config: ModelConfig,
    class_weight: str | None = "balanced",
) -> HistGradientBoostingClassifier:
    """Fit the estimator, optionally reweighting the classes.

    `class_weight` is a real choice, not a knob, and the two callers want opposite things.

    Reweighting buys balanced accuracy and macro F1 by making the scarce class as costly to miss as the
    common one — right when the output is an argmax label, which is what the legacy close-to-close
    pipeline reports. But it fits the model to a distribution that is not the one it will be asked
    about, so the scores it returns are not probabilities of anything real, and a calibrator can only
    partly undo the damage. Measured on BTCUSDT 1h: balanced weighting calibrates to an expected
    calibration error of 0.039 and leaves **0.04%** of rows above 0.60 confidence — a model that would
    never clear an operator's threshold. The same fit unweighted calibrates to 0.010 and keeps 9.4%.

    So: `"balanced"` when you want labels, `None` when you want probabilities. `fit_calibrated_model`
    passes None.
    """
    if y.nunique() < 2:
        raise ValueError("Training data must contain at least two target classes")
    started = time.perf_counter()
    class_counts = y.value_counts().sort_index().to_dict()
    logger.info(
        "Model fit started | rows=%s | features=%s | classes=%s | max_iter=%s | class_weight=%s",
        f"{len(X):,}",
        f"{X.shape[1]:,}",
        class_counts,
        config.max_iter,
        class_weight or "none",
    )
    model = build_model(config, verbose=1)
    weights = compute_sample_weight(class_weight=class_weight, y=y) if class_weight else None
    model.fit(X, y, sample_weight=weights)
    logger.info(
        "Model fit finished | iterations=%s | elapsed=%.2fs",
        getattr(model, "n_iter_", config.max_iter),
        time.perf_counter() - started,
    )
    return model


def build_regressor(config: ModelConfig, verbose: int = 0) -> HistGradientBoostingRegressor:
    """The points head: same features, same folds, but it predicts realized R instead of a class.

    A classifier trained on which barrier came first answers a *different* question from "what does
    this trade pay": it is scored by log-loss, where a 51 %/49 % split costs almost nothing to get
    wrong, while the product is scored in R where that same split is a coin flip around zero. Fitting
    the quantity the decision is actually made on is the point of this head. `squared_error` rather
    than an absolute loss because the tail (a timeout that drifts to 2R) is real and should not be
    silently capped by a robust loss.
    """
    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=config.learning_rate,
        max_iter=config.max_iter,
        max_leaf_nodes=config.max_leaf_nodes,
        min_samples_leaf=config.min_samples_leaf,
        l2_regularization=config.l2_regularization,
        early_stopping=False,
        random_state=config.random_state,
        verbose=verbose,
    )


def fit_regressor(
    X: pd.DataFrame,
    r: pd.Series,
    config: ModelConfig,
    sample_weight: np.ndarray | pd.Series | None = None,
) -> HistGradientBoostingRegressor:
    """Fit the points head. `sample_weight` is where "learn from the losses" enters training.

    The loop that accumulates live outcomes passes weights that raise losing trades above winning ones,
    so the same mistake made twice costs twice as much to ignore. Nothing here picks the weights: the
    caller owns that policy, and a plain batch train passes `None`.
    """
    if len(X) != len(r):
        raise ValueError(f"X has {len(X)} rows but the R target has {len(r)}")
    if r.nunique() < 2:
        raise ValueError("The R target is constant; a regressor would learn only its mean")
    started = time.perf_counter()
    model = build_regressor(config, verbose=1)
    model.fit(X, r, sample_weight=sample_weight)
    logger.info(
        "Points head fit finished | rows=%s | iterations=%s | elapsed=%.2fs",
        f"{len(X):,}",
        getattr(model, "n_iter_", config.max_iter),
        time.perf_counter() - started,
    )
    return model


def regression_metrics(
    r_true: pd.Series | np.ndarray,
    r_pred: np.ndarray,
    *,
    threshold: float = 0.0,
) -> dict[str, Any]:
    """What a points model is judged on: does the R it predicts show up when the trade is taken.

    `expectancy_at_threshold` is the number the gate should use — the realized mean R of the rows the
    policy would actually trade — together with a one-sided lower bound so a handful of lucky trades
    cannot pass a promotion. `spearman` says whether the ranking carries information at all, and
    `top_decile_r` says what the best-ranked tenth actually paid. MAE/RMSE are reported because they
    are the honest failure numbers when the mean is flat.
    """
    actual = np.asarray(r_true, dtype=float)
    predicted = np.asarray(r_pred, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError(f"r_true {actual.shape} and r_pred {predicted.shape} must align")
    if len(actual) == 0:
        return {}

    errors = predicted - actual
    selected = predicted >= threshold
    payload: dict[str, Any] = {
        "rows": int(len(actual)),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "mean_predicted_r": float(np.mean(predicted)),
        "mean_realized_r": float(np.mean(actual)),
        "spearman": _spearman(predicted, actual),
        "selected_share": float(np.mean(selected)),
        "expectancy_at_threshold": _expectancy(actual, selected),
    }
    if len(actual) >= 10:
        cutoff = np.quantile(predicted, 0.9)
        top = actual[predicted >= cutoff]
        payload["top_decile_r"] = float(np.mean(top)) if len(top) else 0.0
    return payload


def _expectancy(actual: np.ndarray, selected: np.ndarray) -> dict[str, Any]:
    sample = actual[selected]
    if len(sample) == 0:
        return {"trades": 0, "mean_r": 0.0, "stderr": 0.0, "lower_bound_95": 0.0, "win_rate": 0.0}
    mean = float(np.mean(sample))
    stderr = float(np.std(sample, ddof=1) / np.sqrt(len(sample))) if len(sample) > 1 else 0.0
    return {
        "trades": int(len(sample)),
        "mean_r": mean,
        "stderr": stderr,
        # One-sided 95 % lower bound: the number to gate on, so a positive mean from ten trades
        # cannot claim an edge it has not earned.
        "lower_bound_95": mean - 1.645 * stderr,
        "win_rate": float(np.mean(sample > 0)),
    }


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Rank correlation without a scipy dependency: Pearson on average ranks."""
    if len(x) < 2:
        return 0.0
    ranks_x = _average_ranks(x)
    ranks_y = _average_ranks(y)
    rx = ranks_x - ranks_x.mean()
    ry = ranks_y - ranks_y.mean()
    denominator = float(np.sqrt(np.sum(rx**2) * np.sum(ry**2)))
    return float(np.sum(rx * ry) / denominator) if denominator else 0.0


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(len(values), dtype=float)
    # Average ties so a model that predicts the same score for a block of rows is not rewarded for
    # the arbitrary order pandas handed them in.
    sorted_values = values[order]
    start = 0
    for index in range(1, len(sorted_values) + 1):
        if index == len(sorted_values) or sorted_values[index] != sorted_values[start]:
            if index - start > 1:
                ranks[order[start:index]] = ranks[order[start:index]].mean()
            start = index
    return ranks


def aligned_probabilities(
    model: HistGradientBoostingClassifier,
    X: pd.DataFrame,
) -> np.ndarray:
    raw = model.predict_proba(X)
    aligned = np.zeros((len(X), len(ALL_CLASSES)), dtype=float)
    class_to_index = {int(label): index for index, label in enumerate(ALL_CLASSES)}
    for raw_index, label in enumerate(model.classes_):
        aligned[:, class_to_index[int(label)]] = raw[:, raw_index]
    return aligned


def probabilities_to_signals(
    probabilities: np.ndarray,
    probability_threshold: float,
) -> np.ndarray:
    down = probabilities[:, 0]
    up = probabilities[:, 2]
    signals = np.zeros(len(probabilities), dtype=int)
    signals[(up >= probability_threshold) & (up > down)] = 1
    signals[(down >= probability_threshold) & (down > up)] = -1
    return signals


def classification_metrics(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, Any]:
    predictions = ALL_CLASSES[np.argmax(probabilities, axis=1)]
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "macro_f1": float(f1_score(y_true, predictions, average="macro", zero_division=0)),
        "log_loss": float(log_loss(y_true, probabilities, labels=ALL_CLASSES)),
        "report": classification_report(
            y_true,
            predictions,
            labels=ALL_CLASSES,
            target_names=["SELL", "HOLD", "BUY"],
            zero_division=0,
            output_dict=True,
        ),
    }


def walk_forward_validation(
    X: pd.DataFrame,
    y: pd.Series,
    config: ModelConfig,
    gap: int,
) -> dict[str, Any]:
    """Row-positional chronological folds — correct when one row is one observation.

    This is the legacy horizon-return path, where each candle contributes exactly one row. The
    barrier-augmented dataset emits many rows per candle and must use
    `walk_forward_validation_by_time` instead; see `modeling.splitting`.
    """
    splitter = TimeSeriesSplit(n_splits=config.cv_splits, gap=gap)
    return _run_folds(X, y, config, gap, splitter.split(X), unit="rows")


def walk_forward_validation_by_time(
    X: pd.DataFrame,
    y: pd.Series,
    times: np.ndarray,
    config: ModelConfig,
    gap: int,
) -> dict[str, Any]:
    """Chronological folds whose boundaries and purge gap are counted in candles, not rows.

    The path for the barrier-augmented dataset: `times` is one candle open per row, and every row sharing
    an open lands on the same side of every boundary. `gap` is the label's maximum look-ahead in candles.
    """
    if len(times) != len(X):
        raise ValueError(f"times has {len(times)} entries for {len(X)} rows; they must line up")
    splitter = TimeGroupedSplit(n_splits=config.cv_splits, gap=gap)
    return _run_folds(X, y, config, gap, splitter.split(times), unit="candles", times=times)


def _run_folds(
    X: pd.DataFrame,
    y: pd.Series,
    config: ModelConfig,
    gap: int,
    splits: Iterable[tuple[np.ndarray, np.ndarray]],
    unit: str,
    times: np.ndarray | None = None,
) -> dict[str, Any]:
    """Fit and score one estimator per fold. Shared so the two split strategies cannot drift apart."""
    started = time.perf_counter()
    logger.info(
        "Walk-forward validation started | rows=%s | folds=%s | purge_gap=%s %s",
        f"{len(X):,}",
        config.cv_splits,
        gap,
        unit,
    )
    fold_metrics: list[dict[str, Any]] = []
    all_true: list[int] = []
    all_probabilities: list[np.ndarray] = []

    for fold, (train_indices, validation_indices) in enumerate(splits, start=1):
        X_train = X.iloc[train_indices]
        y_train = y.iloc[train_indices]
        X_valid = X.iloc[validation_indices]
        y_valid = y.iloc[validation_indices]
        if y_train.nunique() < 2:
            raise ValueError(f"Fold {fold} has fewer than two classes in training data")
        logger.info(
            "Fold %s/%s started | train_rows=%s | validation_rows=%s",
            fold,
            config.cv_splits,
            f"{len(train_indices):,}",
            f"{len(validation_indices):,}",
        )
        model = fit_model(X_train, y_train, config)
        probabilities = aligned_probabilities(model, X_valid)
        metrics = classification_metrics(y_valid, probabilities)
        fold_metrics.append(
            {
                "fold": fold,
                "train_rows": len(train_indices),
                "validation_rows": len(validation_indices),
                "train_end": int(train_indices[-1]),
                "validation_start": int(validation_indices[0]),
                "purged_candles": (
                    candles_between(times, train_indices, validation_indices)
                    if times is not None
                    else None
                ),
                "balanced_accuracy": metrics["balanced_accuracy"],
                "macro_f1": metrics["macro_f1"],
                "log_loss": metrics["log_loss"],
            }
        )
        logger.info(
            "Fold %s/%s finished | balanced_accuracy=%.2f%% | macro_f1=%.2f%% | log_loss=%.4f",
            fold,
            config.cv_splits,
            metrics["balanced_accuracy"] * 100,
            metrics["macro_f1"] * 100,
            metrics["log_loss"],
        )
        all_true.extend(y_valid.astype(int).tolist())
        all_probabilities.append(probabilities)

    combined = classification_metrics(np.asarray(all_true), np.vstack(all_probabilities))
    logger.info(
        "Walk-forward validation finished | balanced_accuracy=%.2f%% | macro_f1=%.2f%% | elapsed=%.2fs",
        combined["balanced_accuracy"] * 100,
        combined["macro_f1"] * 100,
        time.perf_counter() - started,
    )
    return {
        "config": asdict(config),
        "gap": gap,
        "gap_unit": unit,
        "folds": fold_metrics,
        "combined": combined,
    }
