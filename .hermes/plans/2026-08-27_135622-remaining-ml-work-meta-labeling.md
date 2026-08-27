# Remaining Crypto-signal ML Work — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Convert the engine from "honest but fee-losing on 1h" to "nets positive after fees" by building the one model-side lever that targets fee-break-even selection (meta-labeling), plus the two governance levers recorded in `docs/ml-improvement-plan.md` (uniqueness weights, DSR trial log).

**Architecture:** A secondary binary classifier stacked on the existing triple-barrier estimator answers the *serving* question directly — "does *this* setup's net return clear the fee-adjusted break-even?" — instead of "which class wins". Its output becomes the sole gate in `choose_direction`/`bot_advisor`. Uniqueness weights correct the sample-inflation from overlapping barrier variants; a trial log + Deflated Sharpe make future config searches honest.

**Tech Stack:** Python / scikit-learn (HistGradientBoostingClassifier), pandas, joblib. Same venv as the rest of `src/signal-ml`.

**Status line (why this is what's left):** The audit + bracket sweep already *closed* four candidates as measured-negligible: funding/OI features (~0), seed ensembles (+0.02pp), isotonic recalibration, vol-tercile gating. The plan file proved the binding constraint is **fees (≈0.30 ATR) against a fixed bracket needing ~64% TP-first while the engine tops out ~62%**. No single-bracket classifier change fixes that. Meta-labeling is the remaining lever that selects a *subset* whose realized TP rate is high enough to clear fees — it is not asking the classifier to do more, it is asking a new classifier to pick where the existing edge net-pays.

---

## Current context / assumptions

- Model: `artifacts/models/_pooled_1h.joblib` (HistGradientBoostingClassifier, 42 features, 3 classes `[-1,0,1]` = stop-first/timeout/tp-first, purged holdout). Serving path gates on `P(TP-first)` (= class +1), which caps ≈0.47.
- Fee: `config.toml [backtest] fee_rate=0.0010, slippage_rate=0.0005` ≈ 0.30 ATR round trip on the 1.5/1.0 ATR bracket.
- Baseline net expectancy on holdout is **−0.303 ATR averaged over floors 0.40–0.55** (flat-negative).
- Tests live at `tests/ml-engine/` (325 passing). Run `pytest ../../tests/ml-engine` from `src/signal-ml`.
- Venv: `src/signal-ml/.venv`. Commit identity: `sudoix <novino.amir@gmail.com>`.
- Assumption: we keep a single pooled bidirectional model and stack the meta-labeler on it. Do **not** retrain the primary in this workstream.

---

## Approach / step-by-step plan

### Task 1: Add the meta-feature + binary label builder (TDD)

**Objective:** Produce, per barrier-variant row, the boolean label `profitable = (net_return_atr > 0)` and the meta feature set the meta-learner consumes (primary model's `P(TP-first)`, plus the four barrier-context columns already in `BARRIER_FEATURE_COLUMNS`).

**Files:**
- Create: `src/signal-ml/src/crypto_signal/labeling/meta_label.py`
- Test: `tests/ml-engine/test_meta_label.py`

**Step 1 — write failing test:**
```python
def test_profitable_label_is_net_return_sign():
    from crypto_signal.labeling.meta_label import build_meta_labels
    frame = pd.DataFrame({"net_return_atr": [-0.1, 0.0, 0.5], ...})
    labels = build_meta_labels(frame)
    assert list(labels) == [False, False, True]  # 0.0 is not `> 0` -> not profitable
```

**Step 2 — run to confirm failure:** `pytest ../../tests/ml-engine/test_meta_label.py -v` → Expected FAIL (module missing).

**Step 3 — implement** a small builder that (a) recomputes `net_return_atr` exactly as `bracket.py` does (gross − fee − slippage, signed by direction) on the holdout/eval rows, or better reads it from the backtest trades when available; and (b) emits `meta_profitable`, `meta_p_win` (the primary's class-+1 probability), and re-emits `take_profit_atr`, `stop_loss_atr`, `risk_reward_ratio`, `direction_sign`.

**Step 4 — run to confirm pass.**

**Step 5 — commit:** `git add src/signal-ml/src/crypto_signal/labeling/meta_label.py tests/ml-engine/test_meta_label.py && git commit`

### Task 2: Fit the meta-learner and measure its gate (experiment script first)

**Objective:** Find whether a binary classifier on `[p_win, tp, sl, rr, direction]` can pick a holdout subset whose **net** expectancy is positive. This is the go/no-go —**do not wire it into serving until it clears fees on the purged holdout.**

**Files:**
- Create (scratch, not committed as product): `src/signal-ml/scripts/experiments/meta_label_gate.py`
- Read-only reference: `src/signal-ml/src/crypto_signal/evaluation/bracket.py` (for net-return semantics)

**Step 1 — build the eval frame:** score the pooled holdout with the primary model; per row compute `net return_atr` (reuse Task 1 builder); train a `HistGradientBoostingClassifier` (balanced, `probability=True` or log-odds) on the 2020–2023 block; evaluate on the 2023+ purged block.

**Step 2 — report:** per meta-confidence floor (0.50/0.55/0.60/0.65), output n-trades and **net E[ATR]** plus TP-first rate, per symbol. Pass criterion: **at least one floor clears net \> +0.05 ATR on ≥ 3 of 7 symbols with ≥ 50 trades.** Log the output to `docs/ml-improvement-plan.md`.

**Step 3 — verify:** run `python src/signal-ml/scripts/experiments/meta_label_gate.py`, confirm the reported numbers (do not hand-wave).

**Step 4 — commit** only if it passes (exp script + appended plan section).

### Task 3: Wire meta-label as the serving gate (only if Task 2 passes)

**Objective:** Replace the `P(win) >= floor` test in the serving decision with `meta_profitable_prob >= meta_floor`, while still requiring the primary to have *some* directional view.

**Files:**
- Modify: `src/signal-ml/src/crypto_signal/modeling/direction.py:133` (`choose_direction`)
- Modify: `src/signal-ml/src/crypto_signal/training/barrier_pipeline.py` (`_decide_window` + bundle metadata to carry the meta model)
- Modify: `src/signal-ml/src/crypto_signal_engine/application/bot_advisor.py` (gate mapping)
- Test: `tests/ml-engine/test_direction_agreement.py`, `tests/ml-engine/test_bot_advisor.py`

**Step 1 — failing test:** a direction whose primary `P(win)=0.45` but meta `p_profitable=0.62` is **taken**; one with meta `p_profitable=0.40` is **FLAT**, even when primary `P(win)>=0.50`.
**Step 2 — implement:** load the meta bundle in the registry; gate on its probability; keep EV check.
**Step 3–4 — run the two test files** (must pass), then the full suite: `pytest ../../tests/ml-engine -q` → 325+ (expect the new tests on top).
**Step 5 — commit.**

### Task 4: Sample-uniqueness weights (AFML ch.4)

**Objective:** Weight overlapping barrier-variant rows by inverse concurrency; reduces the effective-sample inflation that lets a few hot candles dominate the meta/primary fit.

**Files:**
- Modify: `src/signal-ml/src/crypto_signal/labeling/triple_barrier.py` (emit `uniqueness` column)
- Modify: `src/signal-ml/src/crypto_signal/modeling/estimator.py` (`fit_model` sample_weight path)
- Test: `tests/ml-engine/test_triple_barrier.py`

**Deliverable:** `uniqueness` equals `1 / (number of variants sharing the same candle's forward window)`. Verify the *sum of weights* ≈ unique-candle count, and that re-training with weights changes feature importances (sanity) without regressing the Task 2 gate. Commit.

### Task 5: DSR trial log + Deflated Sharpe

**Objective:** Every config/bracket experiment logs its N, metric, and n-trials; the report prints Deflated Sharpe so a "best" config can't quietly be a multiple-testing artifact.

**Files:**
- Create: `src/signal-ml/src/crypto_signal/evaluation/deflated_sharpe.py`
- Modify: `src/signal-ml/src/crypto_signal/training/barrier_pipeline.py` (append trial row)
- Test: `tests/ml-engine/test_deflated_sharpe.py`

**Deliverable:** closed-form DSR after Bailey & López de Prado (JPM 2014); trial log appended under `artifacts/trials.jsonl`. Commit.

### Task 6 (documentation / decision gate — no code, or ops)

**Objective:** Record the two **non-model** fee levers and hand the go/no-go to the operator; no classifier work left at 1h beyond meta-labeling.

**Files:**
- Modify: `docs/ml-improvement-plan.md`

**Deliverable:** a short "operational levers" table: maker-only / fee-tier (ops), switch the traded bracket to max-RR variant cleared by Task 2, or move to 15m only if the edge-per-fee ratio is positive there (re-run Task 2 gate at 15m before anything real). This is the **manual-approval / paper-first** gate per the production posture.

---

## Files likely to change (summary)

- Create: `src/signal-ml/src/crypto_signal/labeling/meta_label.py`, `src/signal-ml/scripts/experiments/meta_label_gate.py`, `src/signal-ml/src/crypto_signal/evaluation/deflated_sharpe.py`
- Modify: `direction.py`, `triple_barrier.py`, `estimator.py`, `barrier_pipeline.py`, `bot_advisor.py`
- Tests: 5 new/updated test files under `tests/ml-engine/`
- Docs: `src/signal-ml/docs/ml-improvement-plan.md`

## Tests / validation

- Per-task: exact `pytest` target, expected pass count.
- Full suite: `cd src/signal-ml && .venv/bin/python -m pytest ../../tests/ml-engine -q` → must stay green (currently 325).
- Task 2 gate is the only acceptance gate that blocks Task 3 — do not wire meta-labeling into serving on negative or flat expectancy.

## Risks, tradeoffs, open questions

- **Risk: meta-label doesn't clear fees either.** Then the honest outcome is "stop tuning the 1h model; pursue ops fee levers or a bracket/market shift" — that is a valid plan outcome, recorded, not papered over. This workstream is explicitly allowed to conclude "no model-side fix exists at 1h".
- **Risk: overfitting the meta gate to the holdout.** Mitigate with purged split, reporting per-symbol, and a **forward paper window** after wiring — never re-tune on the same holdout.
- **Tradeoff:** meta-labeling adds a second model + latency + a registry dependency. Cost is small (one extra predict); only pay it if Task 2 passes.
- **Open question:** should the meta feature set include funding/OI (built but measured ~0 for the primary)? Cheap to add to the meta features since they're now computed — decide by a quick column-add in Task 2, not by assumption.

---

## Execution handoff

Plan complete. Ready to execute **task-by-task with subagent-driven-development**: dispatch a fresh subagent per task with full context, two-stage review (spec compliance then code quality), proceed only when both approve. Shall I proceed with Task 1 (meta-label label builder)?