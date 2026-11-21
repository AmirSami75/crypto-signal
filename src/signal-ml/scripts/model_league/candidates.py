"""The candidates: every model family worth putting on the same dataset.

Deliberately broad and deliberately shallow. The league's question is "which family learns this market",
not "what is the best hyper-parameter of each family" — a tuned winner that took three hours to find is
still the same family, and the campaign has hours, not weeks. Every entry names its own training budget
so a slow learner cannot starve the queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

CLASSES = np.array([-1, 0, 1], dtype=int)


def expected_r_from_proba(probabilities: np.ndarray, take_profit_atr: np.ndarray, stop_loss_atr: np.ndarray) -> np.ndarray:
    """Expected R implied by a three-class classifier, under the same timeout-at-zero rule the engine uses."""
    win = probabilities[:, int(np.flatnonzero(CLASSES == 1)[0])]
    loss = probabilities[:, int(np.flatnonzero(CLASSES == -1)[0])]
    reward = take_profit_atr / np.maximum(stop_loss_atr, 1e-9)
    return win * reward - loss


@dataclass(frozen=True)
class Candidate:
    name: str
    kind: str  # "classifier" | "regressor"
    build: Callable[[int], Any]
    timeout_seconds: int = 900
    max_train_rows: int | None = None
    note: str = ""

    def estimator(self, seed: int) -> Any:
        return self.build(seed)


def _scaled(model: Any) -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("model", model)])


def candidates() -> list[Candidate]:
    """The queue. Order is intentional: cheap and interpretable first, then the heavy hitters."""
    return [
        Candidate(
            name="baseline_prior",
            kind="classifier",
            build=lambda seed: _PriorModel(),
            timeout_seconds=120,
            note="class priors from the training block; the floor every model must beat",
        ),
        Candidate(
            name="logistic",
            kind="classifier",
            build=lambda seed: _scaled(
                LogisticRegression(max_iter=300, n_jobs=-1, random_state=seed)
            ),
            timeout_seconds=900,
            note="linear in the log-odds; the cheapest honest learner",
        ),
        Candidate(
            name="ridge_r",
            kind="regressor",
            build=lambda seed: _scaled(Ridge(alpha=1.0)),
            timeout_seconds=600,
            note="linear regression on realized R",
        ),
        Candidate(
            name="gaussian_nb",
            kind="classifier",
            build=lambda seed: GaussianNB(),
            timeout_seconds=300,
            note="distributional baseline; strong when features are near-normal, otherwise a floor",
        ),
        Candidate(
            name="decision_tree",
            kind="classifier",
            build=lambda seed: DecisionTreeClassifier(
                max_depth=8, min_samples_leaf=200, random_state=seed
            ),
            timeout_seconds=600,
            note="one axis-aligned tree, depth 8",
        ),
        Candidate(
            name="random_forest",
            kind="classifier",
            build=lambda seed: RandomForestClassifier(
                n_estimators=300,
                min_samples_leaf=40,
                max_features="sqrt",
                n_jobs=-1,
                random_state=seed,
            ),
            timeout_seconds=1800,
            max_train_rows=200_000,
            note="bagged trees; the classic tabular workhorse",
        ),
        Candidate(
            name="extra_trees",
            kind="classifier",
            build=lambda seed: ExtraTreesClassifier(
                n_estimators=400,
                min_samples_leaf=40,
                max_features="sqrt",
                n_jobs=-1,
                random_state=seed,
            ),
            timeout_seconds=1800,
            max_train_rows=200_000,
            note="randomized splits; often beats RF on noisy financial features",
        ),
        Candidate(
            name="hist_gb_clf",
            kind="classifier",
            build=lambda seed: HistGradientBoostingClassifier(
                learning_rate=0.05,
                max_iter=300,
                max_leaf_nodes=31,
                min_samples_leaf=40,
                l2_regularization=1.0,
                early_stopping=False,
                random_state=seed,
            ),
            timeout_seconds=1500,
            note="the production family (three-class)",
        ),
        Candidate(
            name="hist_gb_r",
            kind="regressor",
            build=lambda seed: HistGradientBoostingRegressor(
                loss="squared_error",
                learning_rate=0.05,
                max_iter=300,
                max_leaf_nodes=31,
                min_samples_leaf=40,
                l2_regularization=1.0,
                early_stopping=False,
                random_state=seed,
            ),
            timeout_seconds=1500,
            note="the production points head (R regression)",
        ),
        Candidate(
            name="lightgbm_clf",
            kind="classifier",
            build=lambda seed: _lightgbm(seed, classifier=True),
            timeout_seconds=1500,
            note="leaf-wise boosting with histogram splits",
        ),
        Candidate(
            name="lightgbm_r",
            kind="regressor",
            build=lambda seed: _lightgbm(seed, classifier=False),
            timeout_seconds=1500,
            note="LightGBM on realized R",
        ),
        Candidate(
            name="xgboost_clf",
            kind="classifier",
            build=lambda seed: _xgboost(seed, classifier=True),
            timeout_seconds=1500,
            note="depth-wise boosting; the other half of the GBDT canon",
        ),
        Candidate(
            name="xgboost_r",
            kind="regressor",
            build=lambda seed: _xgboost(seed, classifier=False),
            timeout_seconds=1500,
            note="XGBoost on realized R",
        ),
        Candidate(
            name="mlp_r",
            kind="regressor",
            build=lambda seed: _scaled(
                MLPRegressor(
                    hidden_layer_sizes=(64, 32),
                    activation="relu",
                    alpha=1e-4,
                    batch_size=512,
                    learning_rate_init=1e-3,
                    max_iter=25,
                    early_stopping=True,
                    n_iter_no_change=3,
                    random_state=seed,
                )
            ),
            timeout_seconds=1800,
            max_train_rows=150_000,
            note="a small feed-forward net; the bridge to the deep challengers",
        ),
    ]


def _lightgbm(seed: int, *, classifier: bool) -> Any:
    from lightgbm import LGBMClassifier, LGBMRegressor

    common = dict(
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        n_jobs=-1,
        random_state=seed,
        verbosity=-1,
    )
    return LGBMClassifier(**common) if classifier else LGBMRegressor(**common)


class _XgbClassifier:
    """XGBoost wants labels 0..n-1, the league uses -1/0/1; this adapter maps both ways."""

    classes_ = CLASSES

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._model = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_XgbClassifier":
        from xgboost import XGBClassifier

        self._model = XGBClassifier(**self._kwargs)
        self._model.fit(X, (y + 1).astype(int))
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self._model.predict_proba(X)


def _xgboost(seed: int, *, classifier: bool) -> Any:
    from xgboost import XGBRegressor

    common = dict(
        n_estimators=400,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=10,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        tree_method="hist",
        n_jobs=-1,
        random_state=seed,
        verbosity=0,
    )
    return _XgbClassifier(**common) if classifier else XGBRegressor(**common)


class _PriorModel:
    """Predicts the training-set class distribution for every row — the league's zero point."""

    classes_ = CLASSES

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_PriorModel":
        counts = np.array([(y == label).sum() for label in CLASSES], dtype=float)
        self._priors = counts / max(counts.sum(), 1.0)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return np.tile(self._priors, (len(X), 1))
