# E13cal — Incumbent Calibration (temperature + isotonic)

**Status: COMPLETE — CALIBRATION-REJECT (2026-09-10)** · 27s
**Question**: the incumbent ranks (E11-lite: AUC 0.72) but are its probabilities priced right?
If temperature/isotonic improves holdout LL + ECE + floor precision, ship the calibrator;
else leave serving untouched.

## Setup
- 1h production universe, fee-aware labels (TP 1.5/SL 1.0, H=24, lab costs),
  1.42M dev rows / 175k cal-dev / 175k eval (strict, purged). Label balance stable
  (0.397 / 0.395 / 0.389).

## Result — triple fail, serving stays as-is

| metric | before | temperature (T=1.063) | isotonic |
|---|---|---|---|
| holdout LL | **0.65858** | 0.65875 (worse) | 0.65975 (worse) |
| ECE (15 bins) | **0.00363** | 0.00896 (worse) | 0.00478 (worse) |
| floor-0.40 precision / recall / coverage | **0.418 / 0.506 / 0.471** | 0.414 / 0.608 / 0.572 | 0.435 / 0.060 / 0.054 |

Gate (LL strictly better AND ECE reduced AND precision not worse): all three false.

## Reading
The incumbent is already well-calibrated (ECE 0.36% is excellent for a 42-feature
tree model on noisy labels) — there is nothing for post-hoc calibration to fix.
Temperature flattening only inflates coverage with worse precision; isotonic collapses
to near-no-trade (recall 0.06). This is the correct REJECT: calibration cannot create
information, and here there was no miscalibration to correct.

## Decision
No `e13calibrator.json` promoted (correctly absent). Serving path untouched.
The 0.40 floor's 0.418 precision stands as the honest number.

## Artifacts
`run_e13cal.py`, `results/e13cal_meta.json`, `results/e13cal_run.log`
