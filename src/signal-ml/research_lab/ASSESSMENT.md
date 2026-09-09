# Research Laboratory — Environment Assessment (2026-09-09)

Per §26: assessment before training. Status: **assessment complete, baseline experiment pending**.

## 1. Current Environment

| Resource | Workstation (Arch) | nlp30 (10.224.2.30) |
|---|---|---|
| CPU | i5-13400, 16 threads | Xeon Gold 6430, 8 cores |
| RAM | 15Gi + 31Gi swap | 60Gi + 11Gi swap |
| GPU | none | none |
| Disk free | 243G | 11G (tight) |
| Python | 3.14.7 venv | 3.14.4 venv |
| Torch | 2.13.0+cpu | 2.14.0+cu130 (no GPU usable) |
| sklearn/pandas | 1.9.0 / 2.3.3 | 1.9.0 / 3.0.5 |
| Docker | 5 healthy containers | docker 27 |
| DB | local docker (bot stack) | none dedicated |

**Compute verdict:** all training CPU-only. Deep models must be modest (TCN/LSTM-small viable;
TFT proven OOM/dead-end twice). nlp30 = big-memory trainer; workstation = fast iteration + tests.

## 2. Existing Assets (reuse, don't rebuild)

- `data/` 75 CSVs 505MB: 35×1h (2022→2026), some 4h/5m/15m, **7 funding CSVs**
- `data.py`: `fetch_funding_history` + `fetch_open_interest_history` + backward-looking merge
  (`funding_rate_last`, `funding_rate_chg_3`, `oi_change_1`) with causality rules
- `features/builder.py`: 38-42 features, accepts derivative columns when present
- `labeling/`: triple-barrier (pairs grid, ATR multiples, ambiguous-tie rules)
- `training/`: `barrier_pipeline.py` (HGB incumbent), `lstm_pipeline.py`, `tft_pipeline.py` (both rejected)
- `evaluation/`: league runner + per-strategy trade CSV artifacts
- Tests: 28 files in `tests/ml-engine/` (backtest, barriers, calibration, features, league...)
- Holdout predictions CSV (162k rows) from incumbent — raw material for economics sweep
- AWS paper-trading stack (api + signal-ml + dashboard healthy, PAPER mode)

## 3. Known Results (experiment memory, §15)

| Experiment | Metric | Verdict |
|---|---|---|
| HGB pooled 42f (incumbent) | strict LL 0.7959, edge −0.122 ATR | baseline |
| HGB 4y-burst 8.8M×1000iter | strict LL 0.8068/0.8135, PF 0.28–1.07 | worse, archived |
| MTF 45f challenger | LL 0.7968, edge −0.428 | REJECT |
| TFT v1/v2 | LL 4.66, net −38% | REJECT |
| League 54 combos | 50/54 WEAK | none pass gate |
| rsi_pullback 15m | +0.7–0.9%, 5–8 trades | MODERATE only |

**Key economics finding:** bracket 1.5/1.0 ATR with fee 0.4 ATR → EV = 0.41×1.5 − 0.50×1.0 − 0.4
= **−0.285 ATR/trade BY CONSTRUCTION**. No model class can profit under this geometry.
=> geometry sweep must precede any deep training.

## 4. Immediate Roadmap

1. **E0 (cheap, hours):** bracket-geometry × confidence-band sweep on existing holdout CSV.
   Adopt any geometry clearing PF > 1.1 net → engine + bot brackets.
2. **E1 (baseline, §27):** OHLCV+returns+vol+volume features; HGB vs LR on identical labels,
   walk-forward, strict holdout, fees in backtest. This is the reference every later model must beat.
3. **E2:** funding/OI ablation on the 7 funded symbols (Δ strict LL, Δ PF).
4. **E3 (medium):** TCN (Conv1D dilated) sequence model, focal loss, batch-streamed loader
   (fixes OOM), gated vs E1 HGB. LSTM replaced by TCN; TFT stays rejected.
5. **E4+:** cross-asset features, then only if evidence demands: GNN etc.

Gate: strict-holdout LL improvement AND net PF > incumbent AND ≥30 trades. Honest REJECT otherwise.
