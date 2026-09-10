# E11-lite — HGB Baseline vs DeepLOB on S-razmi BTC LOB

**Status: COMPLETE — REJECT (2026-09-10)**
**Data**: S-razmi MIT BTCUSDT-perp LOB, 2023-01-09 → 2023-01-20 (3,730,870 rows,
250 ms median cadence, median spread 0.05 bps). Read-only; gitignored.
**Design**: trailing-24h rolling z-score per LOB column (W = 345,600 rows) →
non-overlapping (100, 40) snapshot windows (33,851); 3-class mid-price labels
(down/flat/up) at k = 10 and k = 50 rows ahead with dead zone = DEV median
|move| (θ₁₀ = 0.80 USD, θ₅₀ = 3.10 USD); HGB on flattened windows FIRST on the
same rows; DeepLOB trains only if HGB dev LL margin > 0 (primary: k = 50);
economics maps test P(up) − P(down) into 15 m bins → fee-aware net outcome
(TP 1.5 / SL 1.0 ATR, H = 48 = 12 h, futures 0.05 % taker + 0.02 % slip) via
`labels/fee_aware.py`, sequential non-overlapping book on strict-holdout last
3 days (288 bins), purge of horizon rows at boundaries, 2000× bootstrap CI,
20× shuffled-direction null.
**Splits**: train 16,628 / dev 6,889 / test 10,334 windows; 1 purged.

## Result

| model | horizon | dev LL vs base | margin | auc_dir | test margin |
|---|---|---|---|---|---|
| HGB | k = 10 | 0.9772 vs 1.0422 | **−0.0650** | 0.7242 | −0.1014 |
| HGB | k = 50 (primary) | 1.0395 vs 1.0398 | **−0.0003** | 0.5924 | −0.0063 |
| DeepLOB | k = 50 | — (not trained: gate SKIP) | — | — | — |

Economics (HGB-k50 test signals): **5 sequential trades, expectancy −0.40 ATR,
PF 0.49, bootstrap CI lower −1.34, null 0/20.**

**VERDICT: REJECT.** No cell passes: LL margin ≤ 0 at both horizons (DeepLOB
gate correctly SKIPped — training it on a negative-margin baseline would only
spend compute to re-confirm), sequential expectancy negative, CI lower < 0.

## Notes

- k = 10 shows a curious split: directional AUC 0.72 but LL *worse* than base
  rate — the flat HGB ranks up/down pairs yet its probabilities are badly
  miscalibrated (overconfident on 4000 raw snapshot features). Ranking without
  calibration is not a trade: at k = 50, the monetizable horizon, even the
  ranking decays to 0.59.
- Test window is only 3 days / 288 fifteen-minute bins → max ~6
  non-overlapping 12 h trades; power is thin by construction, but the sign of
  every cell (negative margin, negative expectancy) leaves no ambiguity.
- Closes the tick-level cell E9 left open at the model level: second-level LOB
  snapshots carry no *fee-beating* sign at futures taker costs on this venue
  and period. The remaining path to tick edge is maker/HFT execution, not a
  classifier — consistent with the E9 recommendation (freeze directional
  research; own L2 recorder + maker execution as product decision).

Artifacts: `experiments/run_e11lite.py`, `results/e11lite_meta.json`,
`results/e11lite_run.log` (exit 0).
