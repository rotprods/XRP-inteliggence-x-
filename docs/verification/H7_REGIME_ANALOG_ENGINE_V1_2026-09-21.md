# H7 Regime + Historical Analog Engine V1 — Durable Checkpoint

Date: 2026-09-21

## Mission

Add a point-in-time historical regime/analogue research layer after canonical H6 baseline promotion.

This layer is not the live scorer and does not modify `regime.py`.

Its purpose is to support challenger research and historical retrieval without turning similarity into truth.

Hard invariants:

- READ_ONLY / SHADOW_ONLY / NON_EXECUTION
- `truth_claim=false`
- `probability_calibrated=false`
- `decision_authority=false`
- `execution_weight=0.0`
- historical analogue candidates must satisfy `candidate.prediction_time < query.prediction_time`.

## Canonical parent

H7 branch:

`research/regime-analog-engine-v1`

was created directly from:

`main@c8d78343c2a4a71e43d067fcf04b646ef80ddad7`

where canonical H6 B0–B4 baseline skill gate is already merged.

No other open PR or branch claimed regime/analogue scope at branch creation.

## Regime candidate surface

`HistoricalRegime`:

- CAPITULATION
- ACCUMULATION
- RECOVERY
- RISK_ON
- SPOT_LED_EXPANSION
- LEVERAGED_EXPANSION
- LONG_CROWDING
- DISTRIBUTION
- DELEVERAGING
- BREAKOUT
- FAILED_BREAKOUT
- NO_DATA

Regime classification is explicitly a candidate/heuristic assessment, not causal truth.

The classifier consumes configurable feature paths rather than hard-coding one feature schema.

Required conceptual inputs:

- short return;
- medium return;
- XRP relative strength;
- spot/order-flow evidence;
- OI change;
- funding;
- liquidation stress;
- depth imbalance.

Thresholds are versioned/configurable and validated fail-closed.

Missing required features yield `NO_DATA`.

No-rule-match also remains unresolved rather than being forced into a bullish/bearish class.

## Historical analogue search

`HistoricalAnalogSearchResult`:

- query feature row identity;
- query prediction time;
- horizon;
- distance metric;
- exact feature key set;
- strictly-prior candidate count;
- missing-feature exclusion count;
- content-addressed historical universe digest;
- content-addressed scaler digest;
- ranked analogue IDs/timestamps/distances;
- optional candidate-regime counts.

Supported metrics:

- EUCLIDEAN;
- MANHATTAN;
- COSINE.

Point-in-time law:

1. same horizon only;
2. historical row ID must be unique;
3. `candidate.prediction_time < query.prediction_time`;
4. candidate must contain all selected analogue features;
5. scaler mean/std is fitted on the strictly-prior candidate universe only;
6. query is transformed with that past-only scaler;
7. no outcome/label is read by analogue search.

Future rows, same-time rows and wrong-horizon rows are excluded.

A duplicate historical ID fails closed.

Insufficient complete history fails closed.

## Stability gauntlet

`AnalogStabilityReport` tests retrieval sensitivity through:

- Euclidean vs Manhattan vs cosine distance;
- leave-one-feature-out ablations;
- top-k analogue-set overlap.

The report can mark retrieval as unstable.

A stable report still carries:

- `truth_claim=false`;
- `probability_calibrated=false`;
- `decision_authority=false`;
- `execution_weight=0.0`.

Similarity/centrality never promotes a historical narrative to fact.

## Tests

`tests/test_regime_analog_v1.py` covers:

- all eleven named regime candidates;
- NO_DATA due to missing required evidence;
- unresolved/no-rule match;
- invalid regime thresholds;
- future-row exclusion;
- wrong-horizon exclusion;
- missing-feature exclusion;
- duplicate historical identity rejection;
- deterministic order-independent search;
- all three distance metrics;
- degenerate cosine handling;
- past-only scaler;
- stability variants;
- no-variant fail-closed state;
- policy validation.

Synthetic fixtures prove mechanics only. They are not XRP market evidence.

## Verification truth

At checkpoint creation:

- exact-head FAST: NOT_RUN;
- Ruff: NOT_RUN;
- strict mypy: NOT_RUN;
- Bandit: NOT_RUN;
- full pytest/changed-line coverage: NOT_RUN;
- DEEP/RELEASE: NOT_RUN.

No PASS is inferred from inspection.

## Promotion path

1. Regenerate deterministic source manifest.
2. Open one H7 draft PR against current main.
3. Run one bounded FAST.
4. Fix only the first evidence-backed failing gate.
5. Require compile, Ruff lint/format, strict mypy, Bandit, hermetic tests, changed-line coverage 100%, manifest contracts and wheel PASS.
6. Merge only with exact-head protection.

## Next frontier after H7

- add an OOS analogue/regime challenger that consumes only TRAIN rows;
- compare it against the canonical H6 baseline registry;
- reject H7 challenger unless it demonstrates OOS improvement;
- then proceed to H8 calibration only for challengers with proven skill.
