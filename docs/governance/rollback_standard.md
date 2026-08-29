# Rollback Standard

Every promotable change must identify the exact base SHA and be reversible without deleting
forensic evidence.

## Code rollback

1. Block deployment and alerts.
2. Record current branch and SHA.
3. Revert the reviewed commit or redeploy the prior signed artifact.
4. Do not force-rewrite `main` history.
5. Re-run health, schema and smoke tests.

## Data rollback

1. Stop writers.
2. Copy the affected database/object partition for forensics.
3. Restore to a new path from a verified checksum.
4. Validate schema version and record counts.
5. Replay only idempotent jobs.
6. Switch readers after verification.

## Model/config rollback

- restore the previous versioned weights and thresholds;
- preserve the rejected version and reason;
- recompute snapshots with a new run identifier;
- never rewrite historical predictions in place.
