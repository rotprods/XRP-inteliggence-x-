# Release gates

The repository produces **read-only market intelligence**. A green unit-test suite is necessary but not sufficient for production release.

## G0 — Repository integrity

- canonical package and ownership are unambiguous;
- no duplicate `engine_v2`, `final_engine` or parallel scoring implementations;
- source, tests and schemas are versioned;
- build and test evidence is reproducible;
- forbidden execution capabilities are absent.

## G1 — Provider assurance

- at least two independent spot sources for critical prices;
- provider provenance, latency, freshness and raw-response hash are persisted;
- stale, malformed and conflicting observations degrade confidence or block output;
- regional availability and endpoint licensing are recorded;
- provider failover and partial-outage drills pass.

## G2 — Point-in-time historical integrity

- historical observations use `observed_at` and `available_at` semantics;
- revised macro series use vintages where available;
- training transforms are fitted inside training windows only;
- walk-forward validation uses embargo/purge gaps;
- survivorship, revisions and unavailable history are documented.

## G3 — Calibration and model governance

- Brier score, calibration error, precision/recall by regime and false-alert rate are published;
- ablation, threshold-sensitivity and provider-substitution tests pass;
- champion/challenger promotion is evidence-based;
- low-confidence output is blocked rather than narrated as certainty.

## G4 — Shadow operation

- predictions are persisted before outcomes are known;
- the shadow ledger is append-only and tamper-evident;
- realized returns are joined after the evaluation horizon;
- at least 30 consecutive days of provider/SLO evidence exist;
- no historical prediction is rewritten.

## G5 — Read-only production

- freshness, availability and snapshot-latency SLOs pass;
- incident, backup and restore drills are evidenced;
- security review and dependency/container scans pass;
- rollback is executable;
- the release remains non-custodial and cannot execute orders.

Until G0–G5 pass, release status is `BLOCKED` or `SHADOW`, never `PRODUCTION`.
