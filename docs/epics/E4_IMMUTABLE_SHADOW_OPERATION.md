# E4 — Immutable shadow operation

## Objective

Operate the engine in real time without executing financial actions, preserving each prediction before its outcome is known.

## Prediction record

- prediction ID and UTC timestamp;
- asset and horizon;
- regime and probability vector;
- confidence and data-state ceiling;
- drivers and invalidations;
- provider health and source agreement;
- model/config version;
- previous record hash and current record hash.

## Outcome record

Outcomes are stored separately and joined only after the horizon expires. The original prediction is never edited.

## Acceptance criteria

- append-only, hash-chained ledger verifies end to end;
- duplicate IDs and chain breaks are rejected;
- tampering tests fail as expected;
- realized returns are joined after 1h/4h/1d/1w expiry;
- daily calibration, false-alert and data-quality metrics are produced;
- provider incidents and missing-data intervals remain visible;
- at least 30 consecutive days of evidence exist before production review;
- shadow mode never submits orders or requests wallet credentials.
