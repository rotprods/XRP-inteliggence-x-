# M3 Regime-Analog OOS Challenger V1 — Durable Checkpoint

Date: 2026-09-21

## Mission

Test whether the newly canonical H7 regime/analog engine demonstrates out-of-sample predictive skill beyond the already merged H6 B0–B4 baseline ladder.

This is a falsification layer, not a forecast product.

Hard invariants remain:

- READ_ONLY / SHADOW_ONLY / NON_EXECUTION;
- final holdout untouched;
- probability_calibrated=false;
- production_ready=false;
- decision_authority=false;
- execution_weight=0.0.

## Canonical lineage

- H6 baseline skill gate merged on main via PR #25.
- H7 regime + historical analog engine merged on main via PR #26.
- H7 canonical merge SHA: `fe66eb4cf13e3dd9e5b4693dd6d8bdb0b650ee9f`.
- Challenger branch: `research/h7-regime-analog-oos-challenger-v1`, created directly from that SHA.

## Fair-comparison law

The challenger is not compared against an H6 score computed on a different sample.

For each event/horizon:

1. H7 emits predictions only when the query state and analog evidence are ready.
2. The ready test feature_row_ids define the evaluation subset.
3. H6 baseline predictions are filtered to those exact same feature_row_ids.
4. Brier/log-loss are recalculated on that same subset.
5. The best H6 reference/eligible challenger on the matched subset becomes the comparator.

This prevents an apparent H7 gain caused solely by selective coverage.

## Training law

For every walk-forward fold:

- only `fold.train_feature_row_ids` may enter the analog history;
- every training label must satisfy `resolved_at < fold.cutoff_at`;
- training feature rows are classified into content-addressed RegimeState records;
- query state is classified from the test feature only;
- historical analog search applies the H7 strict `candidate.prediction_time < query.prediction_time` law;
- the test label is not used until after OOSPrediction is frozen.

## Analog probability

A test score is a similarity-weighted historical event frequency over matched training analogs.

Optional prior shrinkage uses only the fold-local smoothed training event rate.

No future label, future state, global scaler or post-outcome analog interpretation is permitted.

## Lineage

Each emitted OOS prediction binds:

- baseline DatasetVersion ID;
- fold ID;
- model fit ID;
- feature_row_id;
- query RegimeState ID;
- HistoricalAnalogReport ID;
- optional AnalogSensitivityReport ID;
- matched historical state IDs;
- matched historical feature_row_ids;
- SourceSnapshot IDs through OOSPrediction.

## Sensitivity gate

When enabled, a prediction is suppressed unless the configured sensitivity matrix is stable across:

- distance metrics;
- feature ablations;
- lookback windows;
- provider-universe alternatives.

Suppression is explicit and outcome-independent.

## Skill states

`ELIGIBLE_REGIME_CHALLENGER`

Only when sample/class/coverage gates pass and H7 improves over the best eligible H6 comparator on the same OOS subset.

`NO_DEMONSTRATED_REGIME_SKILL`

When evidence is sufficient but Brier/log-loss skill does not beat H6.

`INSUFFICIENT_EVIDENCE`

When sample size, class support, analog readiness or suppression coverage is insufficient.

A negative result is scientifically valid and must not be optimized away.

## Adversarial tests

The initial gauntlet includes:

- synthetic regime signal where analog skill should exceed noise-only H6 baselines;
- future rows outside folds must not alter any result;
- missing required regime signal suppresses the test case without reading its outcome;
- impossible improvement threshold yields NO_DEMONSTRATED_REGIME_SKILL;
- insufficient analog history yields INSUFFICIENT_EVIDENCE;
- oversized minimum OOS sample yields INSUFFICIENT_EVIDENCE even after predictions exist;
- event/fold identity mismatch fails closed;
- unresolved training labels fail closed;
- policy bounds fail closed;
- matched analog feature IDs must be a subset of the corresponding fold train IDs.

Synthetic fixtures validate mechanics only. They are not XRP performance evidence.

## Current verification truth

At checkpoint creation:

- exact-head FAST: NOT_RUN;
- Ruff/mypy/Bandit/hermetic tests/changed-line coverage: NOT_RUN;
- manifest: not yet reconciled;
- DEEP/RELEASE: NOT_RUN.

## Next action

Open one draft PR against exact canonical main and run Verification OS.

Fix only the first real failing gate.

After FAST green, this module may be merged as the executable M3 falsification harness.

Real XRP regime skill remains unproven until an actual DatasetVersion-backed historical corpus is executed through it.
