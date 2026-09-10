# research_lab ops — scheduled retrain + drift monitor

Read-only automation around the incumbent pipeline. These scripts **observe and
propose**; they never promote a model and never touch bots, risk, or serving.

| Script | Purpose | Writes |
|---|---|---|
| `drift_check.py` | PSI per feature, live window vs training reference + PASS/WARN/FAIL | stdout only (nothing on disk) |
| `retrain.sh` | Re-runs incumbent `train`, then the E-gate subset | `research_lab/candidates/retrain_<date>/`, `research_lab/results/retrain_<date>.json` |

## Drift check

```bash
.venv/bin/python research_lab/ops/drift_check.py --symbol BTCUSDT --interval 1h
.venv/bin/python research_lab/ops/drift_check.py --symbol BTCUSDT --interval 1h --live-window 720 --json
# Score exactly the traded population instead of the trailing window:
.venv/bin/python research_lab/ops/drift_check.py --live-csv /path/to/decisions_candles.csv
```

- Reference = full local CSV history minus the trailing `--live-window` candles (default 720 ≈ 30d @1h); live = trailing window (or `--live-csv`).
- Features rebuilt with the shared `crypto_signal.features.build_features`.
- Thresholds: PSI ≥ 0.10 → WARN, ≥ 0.25 → FAIL, or ≥ 3 features ≥ WARN → FAIL.
- Exit codes: 0 PASS · 1 WARN · 2 FAIL · 3 operational error — wire the exit code straight into alerting.

## Retrain

```bash
research_lab/ops/retrain.sh --dry-run            # plan only, trains nothing
research_lab/ops/retrain.sh                      # train + gate
research_lab/ops/retrain.sh --refresh            # redownload candles first
research_lab/ops/retrain.sh --skip-gate          # train only, stub result json
research_lab/ops/retrain.sh --config config.toml --date 2026-09-10
```

E-gate subset: strict-holdout log-loss margin > 0 vs the incumbent baseline in
`artifacts/metadata.json` **AND** floor economics (expectancy > 0, PF > 1,
≥ 30 trades) from the candidate metadata. Missing/unreadable fields → honest
`REJECT`, never a silent PASS. Verdict lands in
`research_lab/results/retrain_<date>.json`.

## Suggested cron (docs only — not installed)

```cron
# Drift monitor: daily 06:05 UTC; non-zero exit pages the on-call.
5 6 * * * cd /opt/crypto-signal/src/signal-ml && .venv/bin/python research_lab/ops/drift_check.py --symbol BTCUSDT --interval 1h >> /var/log/drift_check.log 2>&1
# Scheduled retrain: weekly Sunday 07:00 UTC; never promotes.
0 7 * * 0 cd /opt/crypto-signal/src/signal-ml && research_lab/ops/retrain.sh --date $(date -u +\%F) >> /var/log/retrain.log 2>&1
```

Never use `glm-5.3-flash` for these cron jobs (user rule: current-model crons only).

## Promotion (manual) + rollback

1. Review `research_lab/results/retrain_<date>.json` — promote only on `PASS`.
2. Sanity-scan the candidate bundle in `research_lab/candidates/retrain_<date>/`.
3. Promote: copy the candidate `models/` bundle into `artifacts/models/` (back up the incumbent first), restart the serving container.
4. Rollback: restore the backed-up incumbent bundle to `artifacts/models/`, restart serving. Previous candidates remain untouched under `research_lab/candidates/` for forensics.
5. Rollback triggers: post-promotion drift_check FAIL, live PF < 1 over the evaluation window, or any serving error attributable to the new bundle.
