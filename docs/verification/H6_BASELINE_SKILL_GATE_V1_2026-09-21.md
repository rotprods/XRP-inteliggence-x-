# H6 Baseline Skill Gate V1 — Durable Checkpoint

Date: 2026-09-21

## Mission

Turn the canonical point-in-time walk-forward substrate into executable, reproducible baseline science before any complex XRP model is allowed to compete.

This checkpoint implements the planned baseline ladder:

- B0 — unconditional/base-rate probability;
- B1 — persistence / first-order transition baseline;
- B2 — momentum baseline;
- B3 — mean-reversion baseline;
- B4 — L2-regularized logistic baseline.

The layer is READ_ONLY / SHADOW_ONLY / NON_EXECUTION.

Hard invariants remain:

- `probability_calibrated=false`
- `production_ready=false`
- `decision_authority=false`
- `execution_weight=0.0`
- final holdout remains untouched.

## Canonical lineage

- PR #20 historical feature/label + walk-forward foundation is merged.
- PR #21 frozen OOS prediction + calibration evidence core is merged.
- PR #22 DatasetVersion V1 is merged.
- PR #24 OOS ledger content-addressed integrity hardening is merged; canonical main: `41c69e8666954dfd08e6e9d44632ba9457299e9a`.
- Branch `research/baseline-skill-gate-main-v2` remains the sole H6 promotion branch. Its PR merge-ref must be verified against the current main before merge.
- H6 consumes canonical `DatasetVersion`, `HistoricalFeatureRow`, `FutureOutcomeLabel`, `WalkForwardFoldPlan`, hardened `OOSPrediction`, and calibration-evidence contracts. It does not duplicate them.

## New runtime surfaces

### baseline_models_v1.py

Deterministic fold-local fitting:

- B0 smoothed event frequency;
- B1 transition/persistence state using training labels only;
- B2 standardized momentum signal;
- B3 standardized inverse/mean-reversion signal;
- B4 regularized logistic regression.

All feature normalization and logistic fitting happens inside the supplied training rows.

No global scaler is permitted.

Each fit emits:

`baseline-fit:sha256:<digest>`

binding:

- baseline kind;
- event key;
- selected feature keys;
- learned parameters;
- exact training feature_row_ids.

### baseline_oos_factory_v1.py

For every fold and baseline:

TRAIN ROWS
→ FIT
→ immutable fit_id
→ TEST FEATURE
→ OOSPrediction
→ later label resolution
→ CalibrationEvidence

Each run binds:

- DatasetVersion ID;
- exact fold IDs;
- exact baseline fit IDs;
- OOS prediction IDs;
- OOS outcome IDs;
- Brier/log-loss evidence;
- development-only challenger status.

B0 is mandatory and acts as reference.

A challenger is rejected when any configured gate fails:

- insufficient OOS sample;
- insufficient positive class;
- insufficient negative class;
- no Brier improvement over B0;
- unacceptable log-loss regression.

A selected development challenger is **not** a final champion.

### baseline_research_matrix_v1.py

Canonical binary event surface:

- `return_gt_0`;
- +1%, +2%, +5%, +10% touches;
- -1%, -2%, -5%, -10% touches;
- XRP absolute touch barriers:
  - $2
  - $3
  - $3.65
  - $5
  - $7.34
  - $10
  - $17
  - $26.6
  - $50

Total: 18 event keys.

Canonical horizons:

- 1h
- 4h
- 1d
- 1w
- 1m
- 3m
- 1y

Full canonical matrix:

**18 × 7 = 126 OOS baseline research cells.**

Missing horizon data is explicit:

`MISSING_HORIZON_DATA`

rather than guessed or silently skipped.

### baseline_model_registry_v1.py

Content-addressed registry over matrix/run/evidence identity.

Registry key:

`horizon | event_key | baseline_kind`

Records:

- DatasetVersion;
- run ID;
- evidence ID;
- Brier;
- log loss;
- sample count;
- reference/challenger/rejected state.

The registry exposes development challengers but grants no production authority.

## Epistemic boundary

The synthetic unit fixtures used to verify deterministic mechanics are not XRP market evidence.

They cannot be cited as model performance.

The first real skill result requires actual DatasetVersion-backed historical feature/label data.

## Current verification truth

- Parent PR #21 FAST: PASS at exact head `c6b874ad50b25b256d64a8ea7f51739400354270`.
- H6 exact-head repository FAST: NOT_RUN.
- H6 Ruff/mypy/Bandit/full pytest: NOT_RUN.
- DEEP/RELEASE: NOT_RUN.
- New code must not be promoted until reconciled with the eventual canonical merge of PR #21 and the FAST gate passes.

## Promotion path

1. Keep H6 isolated while PR #21 is promoted.
2. After PR #21 merge, recreate/reconcile H6 onto exact canonical main.
3. Bind a promoted DatasetVersion from H4/PR #22.
4. Regenerate manifest.
5. Run one bounded FAST.
6. Fix only the first evidence-backed failing gate.
7. Require compile/Ruff lint+format/strict mypy/Bandit/hermetic tests/100% changed-line coverage/manifest/wheel PASS.
8. Populate real 126-cell baseline matrix from historical data.
9. Complex models may enter only after demonstrating OOS improvement over this baseline registry.

## Next frontier

After H6 is canonical:

- execute real historical DatasetVersions;
- produce first B0–B4 OOS evidence for 1h/4h/1d;
- expand to 1w/1m/3m/1y only when sample history is methodologically sufficient;
- build H7 regime/analog challengers;
- reject any complex challenger that cannot beat the baseline skill gate under OOS uncertainty.
