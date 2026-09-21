# Dataset Version V1 Gauntlet Checkpoint — 2026-09-21

## Scope and authority

Repository truth outranks chat assumptions. This checkpoint records the first bounded H4 Dataset Factory step after canonical PR #20 promotion.

Hard boundary remains `READ_ONLY / SHADOW_ONLY / NON_EXECUTION`:

- no trading or order placement;
- no custody, signing, withdrawals, private keys or seed handling;
- no leverage or position sizing;
- no calibrated-probability or production-readiness claim;
- `execution_weight=0.0`, `decision_authority=false`, `probability_calibrated=false`, `production_ready=false` remain blocked.

## Reconstructed truth

- PR #20 final exact branch HEAD before merge: `faf225bcfcd763b1f381788734783f5b7690c7da`.
- Exact-head FAST workflow `35635769110`: **PASS**.
- PR #20 was squash-merged with expected-head protection.
- Canonical `main` after merge: `f09c948354dce49c7c266394e329f73fbc51cf0f`.
- No open PRs existed immediately after that merge.
- Experimental descendants `research/oos-calibration-evidence-v1`, `research/oos-return-distribution-v1`, and `research/calibration-promotion-gate-v1` were built from the pre-merge lineage and must not be merged as-is after the squash promotion.
- The merged H3→H12 plan places immutable DatasetVersion / Dataset Factory before executable OOS/calibration promotion.

## Bounded H4 implementation

Branch: `research/dataset-version-v1`, created from exact canonical main `f09c948354dce49c7c266394e329f73fbc51cf0f`.

Added `src/xrp_regime_engine/dataset_version_v1.py` with a content-addressed research dataset contract binding:

- source manifest IDs + hashes;
- durable partition IDs + hashes;
- feature schema version;
- label schema version;
- created/cutoff timestamps;
- strict replay vs reconstructed PIT fractions;
- provider coverage;
- optional provider-specific cadence gap report;
- deterministic dataset version identity;
- explicit reconstructed-PIT opt-in;
- fail-closed rejection of unavailable-at-cutoff evidence, duplicate identities, row-count mismatches, manifest/partition mismatches, and unsafe temporal configuration.

Added `tests/test_dataset_version_v1.py` covering determinism, order independence, future-evidence rejection, reconstructed-PIT opt-in, manifest/partition integrity, row-count integrity, duplicate identity rejection, gap detection, invalid cadence, temporal freeze ordering, provider coverage validation, corrupt identity rejection and absence of execution surfaces.

## Review status

- code review: **PASS by bounded inspection**, subject to exact-head automated verification;
- security review: **PASS by bounded inspection** — no network, credentials, subprocesses, account mutation or execution authority added;
- PIT/leakage review: **PASS by design inspection** — evidence is classified at `cutoff_at`, ineligible data fail closed, reconstructed PIT requires explicit opt-in;
- compile/Ruff/mypy/Bandit/hermetic tests/changed-line coverage/manifest/wheel: **NOT_RUN** at checkpoint creation;
- DEEP/RELEASE: **NOT_RUN**.

## Next exact action

1. Re-read branch HEAD and open one draft PR only if no concurrent writer has claimed this scope.
2. Use the existing FAST profile once on the exact head.
3. Fix only the first real failing gate; do not rerun CI blindly or weaken thresholds.
4. Regenerate `release/MANIFEST.sha256` only after source/tests/checkpoint stabilize.
5. Require compile, Ruff lint/format, strict mypy, Bandit, hermetic tests, changed-line coverage 100%, repository/source-manifest contract and wheel PASS before promotion.
6. After H4 is green, continue to executable OOS prediction ledger + baseline skill gate. Do not promote calibration/distribution descendants until reconciled onto canonical main and supported by genuine OOS evidence.
