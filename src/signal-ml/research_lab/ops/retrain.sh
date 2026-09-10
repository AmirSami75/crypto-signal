#!/usr/bin/env bash
# Scheduled-retrain wrapper around the INCUMBENT training pipeline.
#
# What it does:
#   1. Trains the incumbent barrier model (python -m crypto_signal train)
#      using a TEMPORARY config copy whose output dirs point at
#      research_lab/candidates/retrain_<date>/ — the live serving registry
#      in artifacts/ is never touched, so promotion stays manual.
#   2. Runs the E-gate subset (strict-holdout LL margin > 0 vs incumbent
#      baseline + floor economics: expectancy > 0, PF > 1, >= 30 trades).
#   3. Writes research_lab/results/retrain_<date>.json with metrics + verdict.
#
# What it NEVER does: promote a model, edit bots/risk/serving, install cron.
#
# Usage:
#   research_lab/ops/retrain.sh [--config config.toml] [--date YYYY-MM-DD] [--refresh] [--skip-gate]
#   research_lab/ops/retrain.sh --dry-run   # print plan only, train nothing
set -euo pipefail

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LAB_DIR/.."   # signal-ml repo root (config.toml, data/, artifacts/ live here)

CONFIG="config.toml"
STAMP="$(date -u +%F)"
REFRESH=""
SKIP_GATE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2 ;;
    --date) STAMP="$2"; shift 2 ;;
    --refresh) REFRESH="--refresh"; shift ;;
    --skip-gate) SKIP_GATE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "retrain.sh: unknown flag $1" >&2; exit 3 ;;
  esac
done

CANDIDATE_DIR="research_lab/candidates/retrain_${STAMP}"
RESULT_JSON="research_lab/results/retrain_${STAMP}.json"
PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi

if [[ "$DRY_RUN" == "1" ]]; then
  echo "retrain.sh DRY-RUN (nothing trained, nothing written except this plan):"
  echo "  config:      $CONFIG"
  echo "  candidate:   $CANDIDATE_DIR/"
  echo "  result:      $RESULT_JSON"
  echo "  train cmd:   $PY -m crypto_signal --config <tmp-config> train $REFRESH"
  echo "  gate:        E-gate subset (LL margin>0 vs incumbent, floor economics)"
  echo "  promotion:   MANUAL ONLY (copy $CANDIDATE_DIR bundle -> artifacts/models/)"
  mkdir -p "$(dirname "$RESULT_JSON")"
  $PY - "$RESULT_JSON" "$STAMP" "$CONFIG" <<'EOF'
import json, sys
from datetime import datetime, timezone
result_json, stamp, config = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {
    "date": stamp,
    "dry_run": True,
    "config": config,
    "verdict": "DRY_RUN",
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "note": "Dry run: training and gate skipped. Re-run without --dry-run.",
}
with open(result_json, "w") as f:
    json.dump(payload, f, indent=2, sort_keys=True)
print(f"wrote {result_json}")
EOF
  exit 0
fi

mkdir -p "$CANDIDATE_DIR" research_lab/results
TMP_CONFIG="$(mktemp "$CANDIDATE_DIR/config.XXXXXX.toml")"
trap 'rm -f "$TMP_CONFIG"' EXIT

# Point all training outputs at the candidate dir; serving registry untouched.
$PY - "$CONFIG" "$TMP_CONFIG" "$CANDIDATE_DIR" <<'EOF'
import re, sys
src, dst, cand = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(src).read()
text = re.sub(r'^artifact_dir\s*=.*$', f'artifact_dir = "{cand}/reports"', text, flags=re.M)
text = re.sub(r'^model_dir\s*=.*$', f'model_dir = "{cand}/models"', text, flags=re.M)
text = re.sub(r'^legacy_dir\s*=.*$', f'legacy_dir = "{cand}/legacy"', text, flags=re.M)
open(dst, "w").write(text)
print(f"staged temp config {dst} -> outputs under {cand}/")
EOF

echo "== [1/3] training incumbent -> $CANDIDATE_DIR/ =="
# shellcheck disable=SC2086
$PY -m crypto_signal --config "$TMP_CONFIG" train $REFRESH

echo "== [2/3] E-gate subset =="
GATE_VERDICT="SKIPPED"
if [[ "$SKIP_GATE" == "0" ]]; then
  # E-gate subset, inline: strict-holdout LL margin > 0 vs the incumbent
  # baseline in artifacts/metadata.json, plus floor economics
  # (expectancy > 0, PF > 1, >= 30 trades) from the candidate metadata.
  # Missing fields -> honest REJECT, never a silent PASS.
  if $PY - "$CANDIDATE_DIR" "$RESULT_JSON" "$STAMP" <<'EOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
cand, result_json, stamp = sys.argv[1], sys.argv[2], sys.argv[3]
meta_p = Path(cand) / "reports" / "metadata.json"
payload = {"date": stamp, "candidate_dir": cand,
           "checked_at_utc": datetime.now(timezone.utc).isoformat()}
try:
    meta = json.loads(meta_p.read_text())
    hold = meta.get("strict_holdout", {})
    ll = hold.get("log_loss") or hold.get("combined", {}).get("log_loss")
    inc = json.loads(Path("artifacts/metadata.json").read_text())
    inc_hold = inc.get("strict_holdout", {})
    inc_ll = inc_hold.get("log_loss") or inc_hold.get("combined", {}).get("log_loss")
    ll_margin = (inc_ll - ll) if (ll is not None and inc_ll is not None) else None
    bt = hold.get("backtest", {})
    exp = bt.get("expectancy_atr") if isinstance(bt, dict) else None
    pf = bt.get("profit_factor") if isinstance(bt, dict) else None
    ntr = bt.get("trades") if isinstance(bt, dict) else None
    econ_pass = (exp is not None and exp > 0 and pf is not None and pf > 1
                 and ntr is not None and ntr >= 30)
    ll_pass = ll_margin is not None and ll_margin > 0
    payload.update({"holdout_log_loss": ll, "incumbent_log_loss": inc_ll,
                    "ll_margin": ll_margin, "expectancy_atr": exp,
                    "profit_factor": pf, "trades": ntr,
                    "ll_gate": ll_pass, "economics_gate": econ_pass,
                    "verdict": "PASS" if (ll_pass and econ_pass) else "REJECT"})
except Exception as exc:
    payload.update({"verdict": "REJECT", "error": f"gate inputs unreadable: {exc}"})
Path(result_json).write_text(json.dumps(payload, indent=2, sort_keys=True, default=str))
print(f"wrote {result_json} verdict={payload['verdict']}")
sys.exit(0 if payload["verdict"] == "PASS" else 1)
EOF
  then
    GATE_VERDICT="$( $PY -c "import json;print(json.load(open('$RESULT_JSON')).get('verdict','?'))" )"
  else
    echo "E-gate: REJECT (see $RESULT_JSON)" >&2
    GATE_VERDICT="REJECT"
  fi
else
  echo "gate skipped (--skip-gate); writing stub result json"
  $PY - "$RESULT_JSON" "$STAMP" "$CANDIDATE_DIR" <<'EOF'
import json, sys
from datetime import datetime, timezone
result_json, stamp, cand = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump({"date": stamp, "candidate_dir": cand, "verdict": "GATE_SKIPPED",
           "checked_at_utc": datetime.now(timezone.utc).isoformat()},
          open(result_json, "w"), indent=2, sort_keys=True)
print(f"wrote {result_json}")
EOF
fi

echo "== [3/3] done =="
echo "candidate:  $CANDIDATE_DIR/"
echo "result:     $RESULT_JSON"
echo "gate:       $GATE_VERDICT"
echo "promotion:  MANUAL ONLY — review $RESULT_JSON, then copy the bundle to artifacts/models/ yourself."
