# Backlog epics

## E1 — Provider assurance and live data plane

Deliver independently validated spot, derivatives, macro and XRPL ingestion with provenance, freshness, failover and degraded-mode behavior.

## E2 — Point-in-time historical lake

Build reproducible historical datasets with availability timestamps, macro vintages, trading-calendar alignment and immutable manifests.

## E3 — Calibration and model governance

Calibrate horizon-specific probabilities, measure false alerts, run ablations and maintain champion/challenger promotion evidence.

## E4 — Immutable shadow operation

Persist predictions before outcomes, hash-chain records, join realized returns after horizon expiry and operate for at least 30 days.

## E5 — SRE, security and read-only release

Implement SLOs, metrics, incident/restore drills, secret rotation, dependency/container scans, SBOM, signed manifests and rollback.

Each epic is blocked from production until the acceptance criteria in `docs/RELEASE_GATES.md` are evidenced.
