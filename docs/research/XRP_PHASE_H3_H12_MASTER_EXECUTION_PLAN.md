# XRP Intelligence OS — Phase H3→H12 Master Execution Plan

Status: canonical execution plan after merged PIT Historical Evidence V2 (#18).
Authority: repository truth overrides this document whenever they diverge.
Mode: READ_ONLY / SHADOW_ONLY / NON_EXECUTION.

## 0. North Star

Produce scientifically auditable, point-in-time, provenance-complete and calibrated XRP forecast distributions across 1h, 4h, 1d, 1w, 1m, 3m and 1y, with explicit uncertainty, falsification, historical calibration and no execution authority.

The system is successful only when a frozen forecast can be reconstructed from immutable source evidence, resolved later against an independently versioned label, scored OOS, calibrated, and reproduced from a versioned dataset/model artifact.

## 1. Critical path

H3 Feature/Label Firewall
→ H4 Dataset Factory
→ H5 Executable Walk-Forward
→ H6 Baseline Skill Gate
→ H7 Regime/Analog Engine
→ H8 Calibration
→ H9 Distribution + Barrier Engine
→ H10 Forecast Ledger + Outcome Resolver
→ H11 Live State Observer
→ H12 Scientific Release / Continuous Loop

No downstream phase may manufacture evidence missing upstream.

## 2. H3 — finish PR #20

### Existing surface
- HistoricalEvidenceStoreV2
- HistoricalFeatureRow
- FutureOutcomeLabel in a separate label store
- canonical horizons 1h/4h/1d/1w/1m/3m/1y
- return/MFE/MAE/realized log-vol/max drawdown
- XRP barriers 2/3/3.65/5/7.34/10/17/26.6/50
- expanding/rolling walk-forward planner
- purge/embargo semantics

### Immediate gauntlet
1. Fix only the exact Ruff-format diff exposed by FAST run 35624444459.
2. Run/reuse exact-head FAST evidence.
3. Attack the first newly exposed failing gate only.
4. Require 100% changed executable line coverage.
5. Regenerate deterministic source manifest after final tracked changes.
6. Require repository/source-manifest contract PASS and wheel PASS.
7. Review code/security/QA/leakage/provenance.
8. Mark ready and merge only with expected_head_sha.
9. Verify resulting main before creating a child.

### H3 acceptance
- feature DB and label DB have distinct store roles;
- feature compiler rejects target/future/label/touch/outcome/MFE/MAE leakage surfaces;
- resolving a label never changes feature_row_id;
- label cannot resolve before horizon end;
- exact horizon-end observation required;
- duplicated timestamps fail closed;
- walk-forward training row is eligible only after label resolution plus embargo;
- equality at cutoff fails closed;
- horizon contamination impossible by contract;
- deterministic fold IDs;
- restart/idempotency/corruption tests PASS.

## 3. H4 — Dataset Factory

Create DatasetVersion as an immutable research artifact.

Required identity:
dataset_version_id
schema_version
source_manifest_ids
partition_ids
feature_schema_version
label_schema_version
created_at
cutoff_at
strict_replay_fraction
reconstructed_pit_fraction
provider coverage
time coverage
gap report
quality report
sha256

Partition strategy:
provider / instrument / timeframe / UTC date.

Required capabilities:
incremental backfill;
restart-safe checkpoints;
content-addressed raw blobs;
deduplication;
schema migrations;
gap detection;
provider disagreement metrics;
coverage matrix;
reconstruction classification;
dataset freeze;
dataset diff;
reproducible manifest.

Gate: a model cannot train from mutable/unversioned datasets.

## 4. H5 — Executable Purged Walk-Forward

Transform fold planning into an execution ledger.

For each horizon:
train_cutoff
purge interval
embargo interval
test_start
test_end
dataset_version
feature_schema
label_schema
model candidate
prediction IDs

Hard law:
training_label.resolved_at < test_prediction_time - embargo.

Never random split.

Support:
expanding window;
rolling window;
minimum train observations;
minimum positive/negative events;
minimum regime observations;
fold suppression when insufficient evidence.

Persist every OOS prediction before outcome aggregation.

## 5. H6 — Baseline Skill Gate

Champion candidates begin simple:
B0 unconditional event frequency;
B1 persistence;
B2 momentum;
B3 mean reversion;
B4 regularized logistic regression.

Metrics:
Brier;
log loss;
ROC-AUC when valid;
PR-AUC when valid;
balanced accuracy only as secondary;
calibration intercept/slope;
ECE;
coverage;
sharpness.

A complex model is rejected unless it improves OOS metrics with uncertainty and survives regime/fold sensitivity.

No model selection on final holdout.

## 6. H7 — Regime + Historical Analog Engine

Regime candidates:
CAPITULATION
ACCUMULATION
RECOVERY
RISK_ON
SPOT_LED_EXPANSION
LEVERAGED_EXPANSION
LONG_CROWDING
DISTRIBUTION
DELEVERAGING
BREAKOUT
FAILED_BREAKOUT
NO_DATA

Inputs may include:
price/returns/volatility;
XRP/BTC and XRP/ETH;
BTC dominance/breadth;
CVD/order flow;
depth/replenishment/churn;
OI/funding/basis/liquidations;
macro/liquidity;
ETF;
XRPL/RLUSD;
event graph/COS20D.

Historical analog search must use only states strictly earlier than prediction_time.

Measure analog stability under:
feature ablation;
distance metric changes;
window changes;
regime changes;
provider removal.

Similarity is evidence retrieval, not truth.

## 7. H8 — Calibration Engine

Separate:
model fitting;
calibration fitting;
final OOS evaluation.

Methods:
uncalibrated;
Platt;
isotonic;
only additional methods if sample size justifies them.

Report per horizon and regime:
Brier;
log loss;
ECE;
reliability bins;
coverage;
sharpness;
sample size;
positive-event count;
confidence interval/bootstrap uncertainty.

Probability output remains blocked if sample size/calibration gates fail.

## 8. H9 — Distribution + Barrier Engine

Only after H8.

Outputs:
P(return > 0);
P(return > ±1/2/5/10%);
P10/P25/P50/P75/P90;
expected return only with uncertainty;
MAE/MFE distribution;
volatility distribution.

Barrier engine:
2, 3, 3.65, 5, 7.34, 10, 17, 26.6, 50 USD.

Distinguish:
touch probability;
close-above probability;
first-passage time;
terminal-price probability.

Do not infer long-horizon barriers from short-horizon classifiers.

INSUFFICIENT_EVIDENCE is a first-class output.

## 9. H10 — Forecast Ledger + Outcome Resolver

Freeze each forecast before resolution:
forecast_id
prediction_time
horizon
dataset_version
model_version
calibrator_version
SourceSnapshot
feature_row_id
regime
distribution
barrier probabilities
supporting evidence
contradicting evidence
quality flags
epistemic state.

Outcome resolver later binds:
label_id
resolved_at
realized outcome
score metrics
calibration bucket.

Forecast records are append-only.

## 10. H11 — Live XRP State Observer

Research states:
BREAKOUT_UNCONFIRMED
SPOT_CONFIRMED_BREAKOUT
LEVERAGED_BREAKOUT
FAILED_BREAKOUT
NO_DATA.

Current $1.50→$2 thesis must be registered prospectively, never retrofitted.

Evidence:
independent price consensus;
spot volume;
CVD;
depth/replenishment;
OI delta;
funding;
basis;
liquidations;
XRP/BTC;
XRP/ETH;
BTC/risk regime.

Persist the pre-outcome hypothesis, confirmation criteria, invalidation criteria and resolution horizon.

No state grants execution authority.

## 11. H12 — Continuous Scientific Loop

INGEST
→ SNAPSHOT
→ FEATURES
→ FORECAST
→ FREEZE
→ WAIT
→ RESOLVE
→ SCORE
→ CALIBRATE
→ DRIFT CHECK
→ CHAMPION/CHALLENGER
→ VERSION
→ FORECAST AGAIN.

Drift:
feature drift;
provider drift;
missingness drift;
calibration drift;
regime drift;
concept drift.

Model promotion requires predeclared gates.

## 12. Parallel data expansion tracks

Run only when non-colliding with critical path.

A. Crypto cross-asset:
BTC/ETH/SOL/XLM, XRP/BTC, XRP/ETH, dominance, breadth, stablecoin liquidity.

B. Macro PIT/vintage:
Fed/SOFR/Treasuries/real yields/DXY/USDJPY/VIX/SPX/Nasdaq/gold/WTI/Brent/BOJ/ECB/BoE.

C. Institutional:
XRP ETF flows/AUM, CME futures, basis/hedging caveats.

D. XRPL/RLUSD:
transactions/accounts/DEX/AMM/TVL/RWA/MPT/burn; RLUSD supply/reserves/liquidity/usage.

E. Competitive rails:
SWIFT, Agorá, tokenized deposits, USDC/USDT, Stellar, Ethereum/L2, Solana, permissioned rails.

Every dataset must declare strict replay vs reconstructed PIT capability.

## 13. Falsification matrix

For every thesis maintain counter-thesis.

T1 XRP breaks $2.
C1 rally fails at/above resistance or is leverage-led.

T2 ETF demand absorbs supply.
C2 AUM is hedged/basis exposure or economically weak for XRP spot.

T3 RLUSD increases XRP value capture.
C3 RLUSD substitutes XRP settlement inventory.

T4 XRPL growth appreciates XRP.
C4 network activity grows without meaningful token value capture.

T5 institutional Ripple adoption benefits XRP.
C5 Ripple succeeds through non-XRP products/rails.

T6 XRP becomes bridge liquidity.
C6 tokenized deposits/stablecoins/interoperability reduce bridge-asset demand.

Contradicting evidence is a required forecast field.

## 14. Three Definitions of Done

ENGINEERING_DONE:
implementation + tests + exact-head gates + reproducible artifact.

SCIENTIFIC_DONE:
OOS evidence + leakage audit + baselines + falsification + calibration/sample adequacy.

OPERATIONAL_DONE:
observability + immutable ledger + reproducibility + rollback + security + release gates.

A goal is globally DONE only when all required dimensions are satisfied.

## 15. Hard gates

Never convert NOT_RUN into PASS.
Never weaken coverage/lint/type/security gates.
Never merge without exact HEAD.
Never use future-fetched evidence as strict replay.
Never allow feature store to read label store.
Never fit calibration on final evaluation.
Never publish calibrated probabilities from raw scores.
Never turn narrative/riddles into execution evidence.
Never grant execution authority.

Persistent invariants:
execution_weight=0.0
decision_authority=false
production_ready=false
until explicit canonical release contracts prove otherwise.

## 16. Work-unit protocol

Each WorkUnit:
work_unit_id
goal_id/subgoal_id
scope
dependencies
claim/owner if exposed
branch
start_head
expected outputs
tests
risk class
Definition of Done
verification evidence
end_head
next READY node.

Loop:
RECONSTRUCT → SELECT → CLAIM → INSPECT → IMPLEMENT → REVIEW → TEST → FIX → VERIFY → MERGE → CHECKPOINT → CONTINUE.

## 17. Merge train

#20 green
→ expected-head merge
→ verify main
→ H4 Dataset Factory PR
→ H5 executable OOS PR
→ H6 baselines PR
→ H7 regime/analog PR
→ H8 calibration PR
→ H9 distribution/barrier PR
→ H10 ledger/resolver PR
→ H11 live observer PR
→ H12 continuous scientific loop
→ DEEP/RELEASE.

Do not stack many unverified descendants.

## 18. Exit condition

The nominal work budget is not Definition of Done.

If blocked:
persist exact blocker and work another independent READY node.

If context expires:
persist exact main/PR/HEAD, gate evidence, GoalGraph delta and next WorkUnit.

If all safe work is exhausted:
stop rather than inventing work.
