# Scientific Calibration Release Gate V1 — Durable Checkpoint

Date: 2026-09-21

## Mission

Build the artifact-scoped scientific promotion layer required before XRP forecasts may even be considered for calibrated-probability review.

This checkpoint does **not** assert calibrated probabilities, production readiness, decision authority, or execution authority.

Hard invariants remain:

- `probability_calibrated=false`
- `distribution_calibrated=false`
- `production_ready=false`
- `decision_authority=false`
- `execution_weight=0.0`

## Canonical upstream truth

- PR #20 is merged to canonical `main`.
- PR #21 owns frozen OOS predictions + binary calibration evidence + Platt calibration.
- PR #22 owns immutable DatasetVersion V1.
- This branch was created as a child of PR #21 exact head `4b73194a9d543f5d8928d03d96853dda80ca2a4c`.
- PR #21 subsequently advanced to `3aa6937a9cde7dfc81f0c0a91c006c125d43421c`; therefore this branch **must be reconciled onto the eventual green PR #21 head before promotion**.
- PR #21 FAST run `35637301846` / job `106457772108` currently reaches compile + Ruff lint PASS and fails first at Ruff format on five PR #21-owned files. This branch did not mutate them.

## New scientific surfaces

### Binary / barrier promotion

`calibration_promotion_binary_v1.py` provides:

- binary evidence policy;
- temporal stability matrix;
- regime stability matrix;
- artifact-scoped promotion decision;
- canonical XRP barrier matrix;
- 7 horizons:
  - 1h
  - 4h
  - 1d
  - 1w
  - 1m
  - 3m
  - 1y
- 9 canonical XRP barriers:
  - $2
  - $3
  - $3.65
  - $5
  - $7.34
  - $10
  - $17
  - $26.6
  - $50
- complete matrix size: **63 cells**.

A passing artifact becomes only:

`ELIGIBLE_FOR_CALIBRATION_REVIEW`

It does not become production-ready or execution-authorized.

### Return-distribution promotion

`distribution_promotion_v1.py` adds independent promotion gates for P10/P25/P50/P75/P90 return distributions.

Required evidence includes:

- sample count;
- per-quantile empirical coverage;
- per-quantile coverage error;
- P25–P75 interval coverage;
- P10–P90 interval coverage;
- median absolute error;
- temporal stability;
- regime stability.

### Aggregate scientific release

`scientific_calibration_release_v1.py` requires simultaneously:

1. one eligible `return_gt_0` directional decision for **every one of the 7 horizons**;
2. one eligible P10/P25/P50/P75/P90 distribution decision for **every one of the 7 horizons**;
3. the full **7 × 9 = 63** barrier calibration matrix with no missing/duplicate cells;
4. a content-addressed `dataset-version:sha256:<digest>` binding.

Incomplete evidence returns a deterministic `BLOCKED` report with exact missing/blocked reasons.

Malformed or internally inconsistent evidence fails closed by exception.

Even a fully complete report remains:

- `probability_calibrated=false`
- `distribution_calibrated=false`
- `production_ready=false`
- `decision_authority=false`
- `execution_weight=0.0`

and only emits:

`ELIGIBLE_FOR_SCIENTIFIC_REVIEW`.

## Collision control

This branch does not edit the six files currently owned by PR #21:

- `oos_predictions_v1.py`
- `calibration_evidence_v1.py`
- `platt_calibration_v1.py`
- their three canonical test files.

It also does not edit PR #22 DatasetVersion code.

## Verification truth

For this aggregate gate branch:

- repository clone/full pytest: **NOT_RUN** in this runtime because outbound DNS is unavailable;
- Ruff: **NOT_RUN** locally because Ruff is not installed in this runtime;
- exact-head FAST: **NOT_RUN**;
- DEEP/RELEASE: **NOT_RUN**.

Previously isolated donor layers were built with targeted deterministic regression coverage before canonical transplantation, but this checkpoint does not substitute that evidence for exact-head repository FAST.

## Promotion sequence

1. Let PR #21 converge to exact-head FAST green.
2. Reconcile this branch onto that exact green SHA.
3. Reconcile/bind canonical DatasetVersion V1 after PR #22 promotion without duplicating its implementation.
4. Regenerate deterministic source manifest.
5. Run one bounded FAST verification.
6. Fix only the first evidence-backed failing gate.
7. Require compile, Ruff lint/format, strict mypy, Bandit, hermetic tests, 100% changed-line coverage, repository/manifest contracts, and wheel build.
8. Only after genuine historical OOS evidence exists should thresholds be evaluated for real promotion decisions.
9. DEEP/RELEASE, shadow operation, SRE/restore and independent review remain separate blockers.

## Next scientific frontier

After this gate is canonical and verified:

- build actual horizon/event calibration artifacts from real OOS ledgers;
- populate all 63 barrier cells;
- populate 7 return-distribution artifacts;
- quantify temporal and regime stability;
- emit the first real `ScientificCalibrationReleaseReport`;
- only then design the Bayesian posterior as a consumer of proven calibrated evidence, never as a mechanism for manufacturing confidence.
