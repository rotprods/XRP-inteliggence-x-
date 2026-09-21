# Operations Runbook

## Start demo

```bash
make install
make demo
make test
```

## Start API

```bash
export XRP_ENGINE_DB_PATH=state/demo/engine.sqlite3
make api
```

## Provider conflict

1. Freeze alert escalation for affected horizon.
2. Compare timestamp alignment and symbol mapping.
3. Check provider status and exchange maintenance.
4. Inspect raw payload hashes and relative spread.
5. Quarantine the outlier provider; do not delete its evidence.
6. Restore after two healthy checks and document the incident.

## Stale data

1. Mark snapshot `DEGRADED`.
2. Block high-confidence alerts.
3. Confirm scheduler, DNS, provider and clock health.
4. Backfill missed intervals idempotently.
5. Recompute only affected snapshots with a new version.

## Database restore

1. Stop writers.
2. Verify latest backup checksum.
3. Restore to a new path.
4. Run schema and snapshot validation.
5. Switch readers.
6. Preserve corrupted file for forensics.
