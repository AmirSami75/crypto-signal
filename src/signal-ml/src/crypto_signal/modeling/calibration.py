"""Turning a gradient-boosting score into a probability the risk engine can threshold on.

`HistGradientBoostingClassifier.predict_proba` returns numbers between 0 and 1 that sum to 1, which
makes them look like probabilities. Whether they *are* probabilities is an empirical question — take
every signal the model scored 0.62, count how many actually reached take-profit first, and see whether
the answer is 62%. This module asks that question, answers it with a reliability curve on candles
neither the estimator nor the calibrator was fitted to, and applies a correction only if the
correction measurably helps.

The order of those two steps is the point, and it is the opposite of what this module was written
expecting. Measured on BTCUSDT 1h, the *unweighted* estimator is already well calibrated — an expected
calibration error of 0.0104 across the range and 0.0051 restricted to scores above 0.50 — and isotonic
regression layered on top makes it **worse where it matters**: 0.0210 above 0.50, four times the error,
while shrinking the rows above 0.60 confidence from 17,867 to 12,898. So the calibrator is not
load-bearing here. What was load-bearing was the class weighting, which is a different fix entirely.

That gap is invisible in accuracy or F1, and it is fatal downstream. The .NET risk engine's minimum
confidence is a *number*, `0.62` or whatever the operator sets, compared directly against what this
engine reports. If 0.62 does not mean "wins 62% of the time" then the operator's risk limit means
nothing, position sizing derived from it is wrong, and the expected value in `domain.expectancy` —
which multiplies these probabilities by real barrier distances — is wrong in the same direction for
every trade.

**The estimator underneath is fitted unweighted**, and that — not the calibrator — is what makes the
scores trustworthy. `fit_model`'s balanced class weights and isotonic calibration pull in opposite
directions: the weights inflate the scores, isotonic deflates them back, and the resolution lost in the
round trip lands entirely at the top of the range where the decisions are. Measured, the pair leaves
**0.04%** of rows above 0.60 confidence against 9.4% unweighted, and calibrates to an expected error of
0.039 against 0.010. A model that cannot clear an operator's threshold is not a conservative model, it
is a broken one. So `fit_calibrated_model` passes `class_weight=None`, and the balanced weighting stays
where it belongs: on the legacy pipeline that reports argmax labels and never quotes a probability.

**Isotonic rather than Platt**, when a correction is applied at all. Platt scaling fits a sigmoid, which
assumes the distortion has a particular shape; a boosted tree's does not — it is flat in the middle and
steep at the ends. Isotonic assumes only monotonicity, that a higher score is never a lower true
probability, which is the one thing that genuinely holds.

**A monotone correction cannot add resolution, only remove it,** which is why it can lose. Isotonic
regression maps scores to a step function, and every score inside a step becomes indistinguishable from
its neighbours. On an already-calibrated model the steps buy nothing and cost the ordering *within* each
one — visible here as the 0.70-0.80 bin going from 753 rows to 2. That is not the top of the range being
corrected, it is the top of the range being vacated, and a naive worst-case-error comparison reads the
vacancy as an improvement because the bin it was failing in no longer has rows in it. Hence
`decision_region_error`, which weights by coverage and is measured over the scores a threshold would
actually select, and hence `improved` refusing a correction that shrinks reach.

**What the ceiling means.** Even done right, the calibrated win probability on BTCUSDT 1h reaches about
0.65 at the 99th percentile and essentially never 0.75. That is not a defect to tune away — the market
does not offer many bets that win three times in four, and a model claiming otherwise is miscalibrated
by definition. It is however an operational trap: an operator who sets a minimum confidence of 0.75
gets silence, not safety, and has no way to tell the difference. So the report carries the ceiling, and
callers are expected to surface it rather than let a threshold be set past it.

**Three blocks, not two.** The estimator is fitted on the first, the calibrator on the second over a
`FrozenEstimator` so it never refits and never sees the estimator's own training rows, and the third is
scored by neither. (`cv="prefit"` was the old spelling of this; sklearn 1.9 removed it in favour of the
wrapper, which is the clearer statement anyway — the estimator is frozen, and the calibrator is a
separate monotone function fitted on top.)
Reliability measured on the calibrator's own slice is a curve of its residuals and comes back looking
perfect no matter how bad the underlying model is. The price is that the shipped estimator trains on
60% of the history rather than all of it — cheap at 694k rows, and the alternative is a confidence
number nobody can trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import time
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import brier_score_loss, log_loss

from ..config import ModelConfig
from ..log_setup import get_logger
from .estimator import ALL_CLASSES, aligned_probabilities, classification_metrics, fit_model
from .splitting import chronological_blocks

logger = get_logger(__name__)

#: Fit / calibrate / assess. The estimator gets the largest share because it has the most to learn; the
#: calibrator is fitting a one-dimensional monotone function per class and needs far less.
DEFAULT_BLOCKS: tuple[float, float, float] = (0.6, 0.2, 0.2)

#: Bins for the reliability curve. Ten is the convention and it reads well in a report; more bins on
#: 130k assessment rows would mostly show sampling noise.
DEFAULT_BINS = 10

#: Bins thinner than this are reported but excluded from the worst-case error. A bin holding one row
#: whose trade happened to win reads as a 0.28 calibration gap, which is sampling noise wearing the
#: costume of a defect — and it hides the real gaps by being larger than all of them.
MIN_BIN_COUNT_FOR_ERROR = 100

#: Percentile of the win probability reported as the practical confidence ceiling. Not the maximum: the
#: single most confident row in a 138k-row block is an outlier by construction, and an operator setting a
#: threshold needs the level a signal actually reaches with some regularity.
CONFIDENCE_CEILING_QUANTILE = 0.99

#: Thresholds the report measures attainment at, so a caller can see what a given floor would cost.
CONFIDENCE_THRESHOLDS: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75)

#: Where the decision region starts. Calibration below this is close to irrelevant: no operator opens a
#: position on a bet the model says is worse than a coin flip, so an error there costs nothing, while the
#: same error above it sizes a real trade wrongly. Global ECE averages the two together and so cannot
#: distinguish a model that is honest where it counts from one that is honest where it doesn't.
DECISION_FLOOR = 0.50

#: How much reach a correction may cost before it is rejected outright. A calibrator that halves the
#: rows clearing 0.60 has not made the model safer, it has made it quieter, and the two are only
#: distinguishable from the outside if something refuses the trade.
MAX_COVERAGE_LOSS = 0.10


@dataclass(frozen=True, slots=True)
class ReliabilityCurve:
    """Predicted probability against observed frequency, bin by bin.

    The diagonal is perfect calibration. Below it the model is overconfident — the failure that matters
    here, because it is the one that talks an operator into a trade.
    """

    label: int
    bin_edges: tuple[float, ...]
    predicted: tuple[float, ...]
    observed: tuple[float, ...]
    counts: tuple[int, ...]
    brier: float

    @property
    def expected_calibration_error(self) -> float:
        """Mean gap between claim and reality, weighted by how often each claim is made."""
        total = sum(self.counts)
        if total == 0:
            return 0.0
        return float(
            sum(
                count * abs(predicted - observed)
                for count, predicted, observed in zip(self.counts, self.predicted, self.observed)
            )
            / total
        )

    @property
    def maximum_calibration_error(self) -> float:
        """Worst gap across bins holding enough rows to mean anything.

        See `MIN_BIN_COUNT_FOR_ERROR`. Falls back to every non-empty bin only when no bin clears the
        floor, which means the assessment block was too small to judge calibration at all.
        """
        gaps = [
            abs(predicted - observed)
            for count, predicted, observed in zip(self.counts, self.predicted, self.observed)
            if count >= MIN_BIN_COUNT_FOR_ERROR
        ]
        if not gaps:
            gaps = [
                abs(predicted - observed)
                for count, predicted, observed in zip(self.counts, self.predicted, self.observed)
                if count > 0
            ]
        return float(max(gaps)) if gaps else 0.0

    def decision_region_error(self, floor: float = DECISION_FLOOR) -> float:
        """Calibration error over the bins a threshold at `floor` would select, weighted by coverage.

        The number to judge a correction by. `expected_calibration_error` spreads its weight across the
        whole range, most of which sits below any threshold an operator would set, so a model can improve
        it by getting better at scores nobody acts on while getting worse at the ones they do.
        """
        weighted = total = 0.0
        for edge, predicted, observed, count in zip(
            self.bin_edges, self.predicted, self.observed, self.counts
        ):
            if edge >= floor and count >= MIN_BIN_COUNT_FOR_ERROR:
                weighted += count * abs(predicted - observed)
                total += count
        return float(weighted / total) if total else 0.0

    def coverage(self, floor: float = DECISION_FLOOR) -> int:
        """Rows landing at or above `floor` — how much of the distribution a threshold there keeps."""
        return int(
            sum(
                count
                for edge, count in zip(self.bin_edges, self.counts)
                if edge >= floor
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "bin_edges": list(self.bin_edges),
            "predicted": list(self.predicted),
            "observed": list(self.observed),
            "counts": list(self.counts),
            "brier": self.brier,
            "expected_calibration_error": self.expected_calibration_error,
            "maximum_calibration_error": self.maximum_calibration_error,
            "decision_region_error": self.decision_region_error(),
            "decision_region_coverage": self.coverage(),
            "thin_bins": [
                index for index, count in enumerate(self.counts) if 0 < count < MIN_BIN_COUNT_FOR_ERROR
            ],
        }


@dataclass(frozen=True, slots=True)
class ConfidenceReach:
    """How high the calibrated win probability actually goes, and how often.

    Exists because "no signal today" and "no signal ever, because the floor is above the ceiling" look
    identical from the outside. Serving surfaces this so a caller can be told its threshold is
    unreachable instead of discovering it through months of silence.
    """

    ceiling: float
    maximum: float
    attainment: tuple[tuple[float, float], ...]

    def share_above(self, threshold: float) -> float:
        """Share of scored bets that reached `threshold`, interpolating between measured points."""
        for level, share in self.attainment:
            if abs(level - threshold) < 1e-9:
                return share
        below = [pair for pair in self.attainment if pair[0] <= threshold]
        return below[-1][1] if below else 1.0

    def is_reachable(self, threshold: float, minimum_share: float = 0.001) -> bool:
        """Whether a floor leaves enough of the distribution above it to ever fire."""
        return self.share_above(threshold) >= minimum_share

    def as_dict(self) -> dict[str, Any]:
        return {
            "ceiling": self.ceiling,
            "ceiling_quantile": CONFIDENCE_CEILING_QUANTILE,
            "maximum": self.maximum,
            "attainment": {f"{level:.2f}": share for level, share in self.attainment},
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """What calibration cost and what it bought, measured on candles neither stage was fitted to."""

    method: str
    blocks: tuple[float, ...]
    gap_candles: int
    fit_rows: int
    calibration_rows: int
    assessment_rows: int
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    curves_before: tuple[ReliabilityCurve, ...] = ()
    curves_after: tuple[ReliabilityCurve, ...] = ()
    reach: ConfidenceReach | None = None

    @property
    def improved(self) -> bool:
        """Whether the correction earned its place on the held-back block.

        Three conditions, all of which must hold, and the reasoning behind each is the reason this is a
        method rather than a single metric comparison:

        1. **Lower error in the decision region.** Not global ECE — a correction can improve the average
           by getting better at scores below any usable threshold while getting worse above it, which is
           precisely what isotonic does to an already-calibrated model here (0.0051 -> 0.0210 above 0.50
           while global ECE moves only 0.0104 -> 0.0117).
        2. **No meaningful loss of reach.** A correction that empties the top of the range has not
           improved calibration there, it has stopped predicting there, and every bin-based error measure
           reads that as success because the failing bin no longer holds rows.
        3. **No worse on the proper scoring rules.** Log loss and Brier over the full distribution, as a
           backstop against a change that satisfies the first two by accident.

        Deliberately *not* judged on balanced accuracy or macro F1. Those reward over-predicting the
        scarce class, which is the distortion calibration exists to remove — the same fit that improves
        log loss from 0.89 to 0.80 drops balanced accuracy from 0.60 to 0.52, and treating that as a
        regression would mean rejecting every well-calibrated model.
        """
        before = self._win_curve(self.curves_before)
        after = self._win_curve(self.curves_after)
        if before is None or after is None:
            return False
        kept = after.coverage()
        had = before.coverage()
        retained = kept / had if had else 1.0
        return (
            after.decision_region_error() <= before.decision_region_error()
            and retained >= 1.0 - MAX_COVERAGE_LOSS
            and after.brier <= before.brier + 1e-6
            and float(self.after.get("log_loss", float("inf")))
            <= float(self.before.get("log_loss", float("inf"))) + 1e-6
        )

    @property
    def selected(self) -> str:
        """Which model `fit_calibrated_model` returned: the correction, or the estimator underneath."""
        return self.method if self.improved else "identity"

    @property
    def selected_metrics(self) -> dict[str, Any]:
        """Metrics for the model that actually shipped.

        `before` and `after` describe the two candidates in the order they were produced, which reads as
        "the old one and the new one" and is wrong exactly when the correction loses — then `before` *is*
        the shipped model. A caller writing a report or a capabilities response wants this instead.
        """
        return self.after if self.improved else self.before

    @property
    def selected_curves(self) -> tuple[ReliabilityCurve, ...]:
        """Reliability curves for the model that actually shipped. See `selected_metrics`."""
        return self.curves_after if self.improved else self.curves_before

    def markdown(self) -> str:
        """The report section a human reads before trusting a confidence number.

        Lives here rather than in the training pipeline because the numbers and what they mean are the
        same fact. A reliability table without the thin-bin caveat invites someone to act on a bin
        holding four rows, and a reach table without the unreachable marker invites a threshold that
        produces silence.
        """
        win = self._win_curve(self.selected_curves)
        lines = [
            "## Calibration",
            "",
            f"Fitted on {self.fit_rows:,} rows, corrected on {self.calibration_rows:,}, assessed on "
            f"{self.assessment_rows:,} — three chronological blocks split on candle boundaries with a "
            f"{self.gap_candles}-candle purge between them, so the reliability below is measured on "
            "candles neither stage was fitted to.",
            "",
        ]

        if self.improved:
            lines.append(
                f"**Applied the {self.method} correction.** It lowered calibration error in the decision "
                f"region (scores at or above {DECISION_FLOOR:.2f}) without costing reach."
            )
        else:
            before = self._win_curve(self.curves_before)
            after = self._win_curve(self.curves_after)
            lines.append(
                f"**Shipped the estimator uncorrected.** The {self.method} candidate did not earn its "
                f"place: decision-region error {before.decision_region_error():.4f} → "
                f"{after.decision_region_error():.4f} over {before.coverage():,} → {after.coverage():,} "
                f"rows above {DECISION_FLOOR:.2f}. A monotone correction cannot add resolution, only "
                "remove it, so on an already-calibrated model it empties the top of the range rather "
                "than fixing it."
            )

        if win is not None:
            lines += [
                "",
                f"Win-class reliability — expected error {win.expected_calibration_error:.4f}, worst "
                f"bin {win.maximum_calibration_error:.4f}, Brier {win.brier:.4f}, decision region "
                f"{win.decision_region_error():.4f}.",
                "",
                "| Claimed | Observed | Rows |",
                "|---:|---:|---:|",
            ]
            for index, count in enumerate(win.counts):
                if count == 0:
                    continue
                thin = " ⚠" if count < MIN_BIN_COUNT_FOR_ERROR else ""
                lines.append(
                    f"| {win.predicted[index]:.3f} | {win.observed[index]:.3f} | {count:,}{thin} |"
                )
            if any(0 < count < MIN_BIN_COUNT_FOR_ERROR for count in win.counts):
                lines += [
                    "",
                    f"⚠ Fewer than {MIN_BIN_COUNT_FOR_ERROR} rows: the observed frequency is sampling "
                    "noise and is excluded from the worst-case figure above.",
                ]

        if self.reach is not None:
            lines += [
                "",
                "### What confidence this model can actually reach",
                "",
                f"Ceiling (p{CONFIDENCE_CEILING_QUANTILE * 100:.0f}) "
                f"**{self.reach.ceiling:.3f}**, single highest {self.reach.maximum:.3f}.",
                "",
                "| Minimum confidence | Share of bets clearing it | |",
                "|---:|---:|---|",
            ]
            for level, share in self.reach.attainment:
                verdict = "" if self.reach.is_reachable(level) else "**never fires**"
                lines.append(f"| {level:.2f} | {share:.2%} | {verdict} |")
            lines += [
                "",
                "A minimum confidence set above the ceiling produces no signals at all, which is "
                "indistinguishable from a quiet market from the outside. Read this table before "
                "choosing a threshold.",
            ]

        return "\n".join(lines) + "\n"

    @staticmethod
    def _win_curve(curves: tuple[ReliabilityCurve, ...]) -> ReliabilityCurve | None:
        for curve in curves:
            if curve.label == 1:
                return curve
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "blocks": list(self.blocks),
            "gap_candles": self.gap_candles,
            "fit_rows": self.fit_rows,
            "calibration_rows": self.calibration_rows,
            "assessment_rows": self.assessment_rows,
            "improved": self.improved,
            "selected": self.selected,
            "selected_metrics": self.selected_metrics,
            "reach": self.reach.as_dict() if self.reach is not None else None,
            "before": self.before,
            "after": self.after,
            "curves_before": [curve.as_dict() for curve in self.curves_before],
            "curves_after": [curve.as_dict() for curve in self.curves_after],
        }


def reliability_curve(
    y_true: np.ndarray | pd.Series,
    probabilities: np.ndarray,
    label: int,
    bins: int = DEFAULT_BINS,
) -> ReliabilityCurve:
    """One class's reliability curve, one-vs-rest.

    Empty bins are reported with a count of zero and their midpoint as both coordinates rather than
    dropped, so a curve always has the same shape and two runs stay comparable.
    """
    truth = (np.asarray(y_true).astype(int) == int(label)).astype(int)
    index = int(np.flatnonzero(ALL_CLASSES == int(label))[0])
    scores = np.asarray(probabilities, dtype=np.float64)[:, index]

    edges = np.linspace(0.0, 1.0, bins + 1)
    # `right=False` everywhere except the last bin, which must own 1.0 or a perfectly confident
    # prediction falls outside every bin.
    slot = np.clip(np.digitize(scores, edges[1:-1], right=False), 0, bins - 1)

    predicted: list[float] = []
    observed: list[float] = []
    counts: list[int] = []
    for position in range(bins):
        rows = slot == position
        count = int(np.count_nonzero(rows))
        midpoint = float((edges[position] + edges[position + 1]) / 2.0)
        counts.append(count)
        predicted.append(float(scores[rows].mean()) if count else midpoint)
        observed.append(float(truth[rows].mean()) if count else midpoint)

    return ReliabilityCurve(
        label=int(label),
        bin_edges=tuple(float(edge) for edge in edges),
        predicted=tuple(predicted),
        observed=tuple(observed),
        counts=tuple(counts),
        brier=float(brier_score_loss(truth, scores)),
    )


def _assess(y_true: pd.Series | np.ndarray, probabilities: np.ndarray, bins: int) -> dict[str, Any]:
    metrics = classification_metrics(y_true, probabilities)
    metrics["log_loss"] = float(log_loss(np.asarray(y_true).astype(int), probabilities, labels=ALL_CLASSES))
    return metrics


def measure_confidence_reach(
    probabilities: np.ndarray,
    thresholds: tuple[float, ...] = CONFIDENCE_THRESHOLDS,
) -> ConfidenceReach:
    """How high the win probability climbs on a block of scored rows, and how often it gets there.

    The model is bidirectional: one estimator answers both LONG and SHORT bets, and a row's decision
    confidence lives in whichever side wins the argmax. Measuring only the BUY column would halve
    attainment by construction (every SHORT-side confident row is discarded), so reach is measured on
    the per-row maximum class probability — the number an operator's threshold actually gates on.
    """
    probabilities = np.asarray(probabilities, dtype=np.float64)
    if probabilities.size == 0:
        raise ValueError("no rows to measure confidence reach on")
    wins = probabilities.max(axis=1)
    return ConfidenceReach(
        ceiling=float(np.quantile(wins, CONFIDENCE_CEILING_QUANTILE)),
        maximum=float(wins.max()),
        attainment=tuple(
            (float(threshold), float(np.mean(wins >= threshold))) for threshold in thresholds
        ),
    )


def fit_calibrated_model(
    X: pd.DataFrame,
    y: pd.Series,
    times: np.ndarray,
    config: ModelConfig,
    gap: int,
    blocks: tuple[float, ...] = DEFAULT_BLOCKS,
    method: str = "isotonic",
    bins: int = DEFAULT_BINS,
) -> tuple[CalibratedClassifierCV, CalibrationReport]:
    """Fit an estimator, fit a correction on later candles, and judge both on later ones still.

    Returns whichever of the two scored better in the decision region — `report.selected` says which —
    together with the report that justifies the choice. The correction is a candidate, not a foregone
    conclusion: on an already-calibrated estimator isotonic regression removes resolution it cannot
    replace, and this function is where that gets caught instead of shipped.

    The returned model is a plain scikit-learn classifier either way, so callers score it identically
    and never branch on which one they got.
    """
    if len(blocks) != 3:
        raise ValueError(f"expected three blocks (fit, calibrate, assess), got {len(blocks)}")
    if len(times) != len(X):
        raise ValueError(f"times has {len(times)} entries for {len(X)} rows; they must line up")

    fit_rows, calibration_rows, assessment_rows = chronological_blocks(times, blocks, gap=gap)
    logger.info(
        "Calibration split | fit=%s | calibrate=%s | assess=%s | purge=%s candles",
        f"{len(fit_rows):,}",
        f"{len(calibration_rows):,}",
        f"{len(assessment_rows):,}",
        gap,
    )

    X_fit, y_fit = X.iloc[fit_rows], y.iloc[fit_rows]
    X_calibrate, y_calibrate = X.iloc[calibration_rows], y.iloc[calibration_rows]
    X_assess, y_assess = X.iloc[assessment_rows], y.iloc[assessment_rows]

    # Unweighted: see `fit_model`. Balanced weights and isotonic calibration fight each other, and
    # the model loses — every score above 0.60 disappears.
    estimator = fit_model(X_fit, y_fit, config, class_weight=None)

    if y_calibrate.nunique() < len(ALL_CLASSES):
        raise ValueError(
            f"The calibration block holds only classes {sorted(y_calibrate.unique())}; isotonic "
            "regression needs every class present or the missing one gets no mapping at all"
        )

    started = time.perf_counter()
    # Frozen, so `fit` below fits only the isotonic mapping. Without the wrapper CalibratedClassifierCV
    # would cross-validate a *fresh* estimator on the calibration block, throwing away the fitted one and
    # calibrating a model trained on a fifth of the data.
    calibrated = CalibratedClassifierCV(FrozenEstimator(estimator), method=method)
    calibrated.fit(X_calibrate, y_calibrate)
    logger.info("Calibration fitted | method=%s | elapsed=%.2fs", method, time.perf_counter() - started)

    raw_probabilities = aligned_probabilities(estimator, X_assess)
    calibrated_probabilities = aligned_probabilities(calibrated, X_assess)

    report = CalibrationReport(
        method=method,
        blocks=tuple(float(block) for block in blocks),
        gap_candles=int(gap),
        fit_rows=len(fit_rows),
        calibration_rows=len(calibration_rows),
        assessment_rows=len(assessment_rows),
        before=_assess(y_assess, raw_probabilities, bins),
        after=_assess(y_assess, calibrated_probabilities, bins),
        curves_before=tuple(
            reliability_curve(y_assess, raw_probabilities, label, bins) for label in ALL_CLASSES
        ),
        curves_after=tuple(
            reliability_curve(y_assess, calibrated_probabilities, label, bins) for label in ALL_CLASSES
        ),
    )

    # The reach has to describe the model that ships, not the one that lost the comparison: it is what
    # `GetCapabilities` reports and what the risk engine checks a threshold against, so measuring it on
    # the discarded candidate would tell an operator their floor is reachable when it is not.
    model = calibrated if report.improved else estimator
    report = replace(
        report,
        reach=measure_confidence_reach(
            calibrated_probabilities if report.improved else raw_probabilities
        ),
    )

    win_before = CalibrationReport._win_curve(report.curves_before)
    win_after = CalibrationReport._win_curve(report.curves_after)
    logger.info(
        "Calibration assessed | win-class ECE %.4f -> %.4f | decision-region error %.4f -> %.4f | "
        "reach above %.2f %s -> %s rows | Brier %.4f -> %.4f",
        win_before.expected_calibration_error,
        win_after.expected_calibration_error,
        win_before.decision_region_error(),
        win_after.decision_region_error(),
        DECISION_FLOOR,
        f"{win_before.coverage():,}",
        f"{win_after.coverage():,}",
        win_before.brier,
        win_after.brier,
    )
    reach = report.reach
    logger.info(
        "Confidence reach | ceiling(p%.0f)=%.3f | max=%.3f | %s",
        CONFIDENCE_CEILING_QUANTILE * 100,
        reach.ceiling,
        reach.maximum,
        " ".join(f">={level:.2f}:{share:.2%}" for level, share in reach.attainment),
    )
    unreachable = [level for level, _ in reach.attainment if not reach.is_reachable(level)]
    if unreachable:
        logger.warning(
            "A minimum confidence of %s would never fire on this model; the practical ceiling is %.3f",
            " or ".join(f"{level:.2f}" for level in unreachable),
            reach.ceiling,
        )
    if report.improved:
        logger.info("Selected the %s calibrator: it lowered error in the decision region", method)
    else:
        # Not a failure, and not something to warn about: it means the estimator was already calibrated,
        # which is the outcome to hope for. What *would* deserve a warning is shipping a correction that
        # made the decision region worse, and this branch is what prevents it.
        logger.info(
            "Selected the uncalibrated estimator: the %s correction did not lower error in the "
            "decision region (%.4f -> %.4f) or cost too much reach (%s -> %s rows above %.2f). Its "
            "scores are already calibrated to %.4f there, so no correction is applied.",
            method,
            win_before.decision_region_error(),
            win_after.decision_region_error(),
            f"{win_before.coverage():,}",
            f"{win_after.coverage():,}",
            DECISION_FLOOR,
            win_before.decision_region_error(),
        )
    return model, report
