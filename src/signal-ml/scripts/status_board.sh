#!/usr/bin/env bash
# One screen of truth for a local crypto-signal box.
#
# Reads only: container health, the scanner's last pass, the league's progress and the served model.
# Written for the handover case — someone who has just ssh'd in and needs to know what is supposed to
# be running before they restart anything.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

line() { printf '%s\n' "────────────────────────────────────────────────────────────"; }

echo "crypto-signal · $(date '+%Y-%m-%d %H:%M:%S %Z')"
line
echo "containers"
docker ps --filter name=crypto-signal --format '  {{.Names}}\t{{.Status}}' | sort
line
echo "api"
curl -s -m 5 http://127.0.0.1:8000/health/ready | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print('  ' + str(d.get('status')) + ' | ' + str(d.get('timestamp')))
    for dep in d.get('dependencies', []):
        print('    ' + dep['name'] + ': ' + dep['status'])
except Exception as exc:
    print('  unreachable (' + str(exc) + ')')
"
echo "  dashboard: $(curl -s -o /dev/null -w '%{http_code}' -m 5 http://127.0.0.1:5173/ || echo down)"
line
echo "scanner (last 5 passes)"
docker logs --since 6h crypto-signal-api-1 2>&1 \
  | grep -E "Scanner pass .* complete|Market scanner cycle failed" \
  | tail -5 | sed 's/^/  /'
line
echo "served model"
echo "  (authenticated endpoint — check the dashboard's ML page, or GET /api/v1/ml/model with a token)"
line
echo "league"
if [ -f artifacts/model_league/results.jsonl ]; then
  echo "  rows:   $(wc -l < artifacts/model_league/results.jsonl)"
  echo "  errors: $(python3 -c "import json;print(sum(1 for l in open('artifacts/model_league/results.jsonl') if json.loads(l).get('status')=='error'))" 2>/dev/null || echo '?')"
  tail -2 artifacts/model_league/campaign.log | sed 's/^/  /'
else
  echo "  no campaign on disk"
fi
line
echo "calibration (fast loop)"
if [ -f artifacts/online/calibration.json ]; then
  python3 -c "
import json
d = json.load(open('artifacts/online/calibration.json'))
print('  markets: ' + str(len(d.get('markets', {}))) + ' | updated ' + str(d.get('updated_at', '?')))
" 2>/dev/null || echo "  unreadable"
else
  echo "  no samples yet (needs closed trades to learn from)"
fi
