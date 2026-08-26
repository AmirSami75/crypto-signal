#!/usr/bin/env bash
# Nightly Postgres backup for crypto-signal.
#
# Keeps the last 14 nightly dumps plus one per week (Sundays) for 8 weeks. Restores are documented
# in devops/BACKUP_RESTORE.md — read that before you ever need this in anger.
#
# Install on the host cron:
#   10 3 * * * /home/sudoix/Desktop/project/crypto-signal/devops/backup_db.sh >> /var/log/cs_backup.log 2>&1
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/crypto-signal}"
KEEP_NIGHTLY=14
KEEP_WEEKLY=8
CONTAINER="crypto-signal-db-1"
DB_USER="crypto_signal"
DB_NAME="crypto_signal"

mkdir -p "$BACKUP_DIR"
stamp="$(date +%Y-%m-%d_%H%M%S)"
dow="$(date +%u)" # 1..7, 7 = Sunday

target="$BACKUP_DIR/nightly_${stamp}.dump"
echo "[$(date -Is)] dumping to $target"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$target"

# Verify the archive actually reads back — a dump you cannot restore is a rumour of a backup.
if ! docker exec -i "$CONTAINER" pg_restore --list < "$target" >/dev/null 2>&1; then
  echo "[$(date -Is)] FATAL: dump failed verification; removing $target" >&2
  rm -f "$target"
  exit 1
fi

# Sundays also become the weekly copy.
if [ "$dow" = "7" ]; then
  cp "$target" "$BACKUP_DIR/weekly_${stamp}.dump"
fi

# Retention: prune by name rather than mtime so an old untouched file is not silently immortal.
# `|| true` matters: when no files match, ls exits non-zero and pipefail would kill the script
# AFTER a successful dump — a backup job that fails on its own success.
ls -1t "$BACKUP_DIR"/nightly_*.dump 2>/dev/null | tail -n +$((KEEP_NIGHTLY + 1)) | xargs -r rm -f -- || true
ls -1t "$BACKUP_DIR"/weekly_*.dump 2>/dev/null | tail -n +$((KEEP_WEEKLY + 1)) | xargs -r rm -f -- || true

echo "[$(date -Is)] ok ($(du -h "$target" | cut -f1))"
