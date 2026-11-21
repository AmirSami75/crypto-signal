#!/bin/bash
# Keep the model-league campaign alive until its deadline.
#
# The runner is resumable (it skips any model that already has a row), so a restart costs only the
# candidate that was in flight. The watchdog checks every two minutes, stops at the same wall-clock
# deadline the runner uses, and never starts a second copy: `pgrep` matches both the runner and its
# per-model children, which all carry the same command line.
set -u
cd "$(dirname "$0")/../.." || exit 1

DEADLINE="${1:-2355}"
LOG="artifacts/model_league/watchdog.log"
mkdir -p artifacts/model_league
echo "[watchdog] started $(date '+%F %T') · deadline $DEADLINE" >> "$LOG"

while [ "$(date +%H%M)" -lt "$DEADLINE" ]; do
  if ! pgrep -f "python -m scripts.model_league.runner" > /dev/null 2>&1; then
    echo "[watchdog] runner absent at $(date '+%F %T') — restarting" >> "$LOG"
    .venv/bin/python -m scripts.model_league.runner \
      --until "${DEADLINE:0:2}:${DEADLINE:2:2}" \
      --intervals 1h,5m \
      --seeds 42,7 \
      --symbols-1h BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT \
      --symbols-5m BTCUSDT \
      --digest-minutes 90 >> artifacts/model_league/campaign.log 2>&1 &
    disown
    sleep 10
  fi
  sleep 120
done
echo "[watchdog] deadline reached $(date '+%F %T')" >> "$LOG"
