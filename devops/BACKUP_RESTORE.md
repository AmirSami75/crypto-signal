# Backup & restore runbook

## What gets backed up

`devops/backup_db.sh` (install on host cron, nightly) dumps the `crypto_signal` Postgres
database in custom format (`pg_dump -Fc`) and **verifies each dump with `pg_restore --list`**
before keeping it. A dump that fails verification is deleted and the script exits non-zero.

Retention:

| Class | Kept | Cadence |
|---|---|---|
| Nightly | 14 | every day 03:10 |
| Weekly | 8 | Sundays (copy of that night's dump) |

Backups land in `~/backups/crypto-signal/`. That directory is on the host disk — for real
disaster tolerance, sync it off-machine (rclone/Borg/restic to remote storage). A backup on
the same disk as the database survives a bad migration, not a dead disk.

## What is NOT in the backups

- **Sealed exchange API keys**: they are AES-GCM ciphertext *in* the DB, so they do come along —
  but they are unreadable without `API_Settings__Sercurity__KeyEncryptionKey`. Back that key up
  separately (password manager / secret manager). Losing it means every stored connection must be
  re-entered; there is no recovery path by design.
- Model artifacts (`src/signal-ml/artifacts/`) — reproducible from data + config via
  `scripts/self_learning_loop.py`.

## Restore procedure

```bash
# 1. Stop writers — bots making decisions during a restore corrupt state.
docker stop crypto-signal-api-1

# 2. Inspect the dump first (always).
docker exec -i crypto-signal-db-1 pg_restore --list < ~/backups/crypto-signal/nightly_YYYY-MM-DD_HHMMSS.dump | head

# 3. Drop and recreate the schema, then restore into it.
docker exec -i crypto-signal-db-1 psql -U crypto_signal -d postgres \
  -c "DROP DATABASE IF EXISTS crypto_signal;" \
  -c "CREATE DATABASE crypto_signal OWNER crypto_signal;"
docker exec -i crypto-signal-db-1 pg_restore -U crypto_signal -d crypto_signal \
  --no-owner --jobs=4 \
  < ~/backups/crypto-signal/nightly_YYYY-MM-DD_HHMMSS.dump

# 4. Restart and verify health before enabling anything that trades.
docker start crypto-signal-api-1
curl -s http://127.0.0.1:8000/health/ready | jq .status   # expect "healthy"

# 5. Sanity: bot count, latest decision timestamp.
docker exec crypto-signal-db-1 psql -U crypto_signal -d crypto_signal \
  -c 'SELECT count(*) FROM "TradingBots" WHERE "IsDeleted" = false;' \
  -c 'SELECT max("CandleOpenTime") FROM "StrategyDecisions";'
```

## Testing the backup

A restore you have never rehearsed is a hypothesis. Quarterly: restore the newest nightly into
a scratch database (`crypto_signal_restore_test`) and compare row counts of the hot tables.
The scratch DB needs no API running.
