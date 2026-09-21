# H7 Regime + Historical Analog Engine V1 — Durable Checkpoint

Date: 2026-09-21

## Mission

Replace prototype-name similarity with a real point-in-time regime/analog research substrate.

This layer is READ_ONLY / SHADOW_ONLY / NON_EXECUTION.

Hard invariants:

- similarity does not create truth;
- historical analogs must be strictly earlier than prediction_time;
- normalization must fit on eligible historical states only;
- future states never influence analog selection or normalizer statistics;
- ambiguous or insufficient evidence returns NO_DATA;
- decision_authority=false;
- execution_weight=0.0.

## Canonical lineage

- PR #20 merged historical store/features/labels/walk-forward.
- PR #21 merged frozen OOS prediction + calibration evidence.
- PR #22 merged DatasetVersion V1.
- PR #25 merged H6 B0-B4 baseline skill gate.
- Canonical main at H7 branch creation:
  `c8d78343c2a4a71e43d067fcf04b646ef80ddad7`.
- No open PR existed at H7 claim time.
- Branch: `research/h7-regime-analog-engine-v1`.

## Problem corrected

Legacy `regime.py` includes descriptive hard-coded prototype analogues such as:

- 2017_XRP_EXPANSION
- 2022_LIQUIDITY_STRESS
- 2023_LEGAL_REPRICING

Those prototypes remain heuristic descriptive surfaces. They are not point-in-time historical analog evidence.

H7 introduces a separate evidence-safe engine built from actual `HistoricalFeatureRow` records.

## Regime State V1

Canonical research regimes:

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

Classification is configurable through `RegimeSignalSpec` and `RegimeClassifierPolicy`.

Each signal declares:

- semantic signal name;
- dotted feature key;
- center;
- scale;
- direction.

Signals are normalized to [-1, 1].

Required signals and minimum coverage are explicit.

Missing critical evidence or ambiguous rule separation returns `NO_DATA` rather than a guessed regime.

Every state is content-addressed:

`regime-state:sha256:<digest>`

and binds:

- feature_row_id;
- prediction_time;
- horizon;
- policy_id;
- normalized signals;
- signal coverage;
- regime;
- confidence;
- provider universe version;
- SourceSnapshot IDs.

## Historical Analog V1

Analog eligibility requires:

- same research horizon;
- candidate prediction_time strictly earlier than query prediction_time;
- optional lookback bound;
- optional same-regime constraint;
- optional provider-universe filter;
- all selected analog features present.

Future states are excluded before normalization.

Normalizer mean/std is fit only on eligible historical candidate states.

Supported distance metrics:

- Euclidean;
- Manhattan;
- Cosine.

Each report records:

- exact query state;
- selected signals;
- normalizer digest;
- eligible candidate count;
- metric;
- top-k state IDs;
- distances;
- similarities;
- candidate regimes;
- provider-universe versions.

If history is insufficient:

`NO_DATA / INSUFFICIENT_STRICTLY_PRIOR_HISTORY`.

## Sensitivity / Falsification

`run_analog_sensitivity` can stress retrieval across:

- distance metric changes;
- feature ablation;
- lookback-window changes;
- alternate provider-universe feature compilations.

Outputs include:

- ready scenario count;
- minimum top-k Jaccard overlap;
- top-regime agreement rate;
- explicit instability reasons.

Provider-removal sensitivity requires alternate feature rows compiled from the corresponding provider universe; H7 does not fake provider-removal counterfactuals.

## Epistemic rule

Historical analogy is retrieval evidence.

It is not:

- causal proof;
- factual identity;
- a calibrated probability;
- a forecast by itself;
- a reason to override contradictory market evidence.

## Current verification truth

At checkpoint creation:

- H7 exact-head FAST: NOT_RUN.
- Ruff/mypy/Bandit/full pytest: NOT_RUN.
- DEEP/RELEASE: NOT_RUN.
- Parent canonical main is green through merged H6 lineage.

Promotion requires one exact-head FAST run and repair of only the first real failing gate.

## Next frontier after H7 core is green

Build the regime/analog challenger:

TRAIN fold
→ classify training states
→ resolve only training outcomes available before cutoff
→ retrieve strictly-prior analogs for each test prediction
→ freeze analog-derived OOS score
→ resolve outcome later
→ compare against H6 B0-B4 registry.

Milestone target:

M3 Regime-Conditional Skill evaluated.

If analog/regime skill does not beat baseline OOS:

`NO_DEMONSTRATED_REGIME_SKILL`

is the correct scientific result.
