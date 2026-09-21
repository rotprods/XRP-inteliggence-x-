# /nextiterationmetaprompt — XRP Intelligence OS

Cold-start from rotprods/XRP-inteliggence-x-. Do not trust this document as current repository state. Reconstruct main HEAD, open PRs, branches, verification evidence, handoffs, manifests and active claims first.

## /northstar
Complete the chain:
RAW SOURCES -> PIT DATA PLANE -> PROVENANCE/LINEAGE -> NORMALIZATION -> GRAPHIFY -> COS20D -> SEMANTICBRAIN -> MICROSTRUCTURE -> DERIVATIVES -> CROSS-ASSET/MACRO/FUNDAMENTALS -> HISTORICAL FEATURE STORE -> SEPARATE LABEL STORE -> REGIME ENGINE -> PURGED WALK-FORWARD/OOS -> CALIBRATION -> BAYESIAN/ENSEMBLE POSTERIOR -> 1H/4H/1D/1W/1M/3M/1Y DISTRIBUTIONS -> FORECAST LEDGER -> OUTCOME RESOLVER -> CONTINUOUS RECALIBRATION.

## /goal graph
G0 verification convergence
G1 PIT data plane
G2 provenance/lineage
G3 microstructure
G4 derivatives
G5 cross-asset
G6 macro/liquidity
G7 XRPL/RLUSD/ETF fundamentals
G8 event/regulatory graph
G9 Graphify/COS20D/SemanticBrain
G10 historical feature store
G11 separate future label store
G12 regime engine
G13 purged walk-forward/OOS
G14 calibration
G15 probabilistic forecast distributions
G16 barrier/touch engine
G17 live state observer
G18 adversarial falsification
G19 scientific/release audit
G20 dataset factory
G21 model registry
G22 forecast ledger
G23 outcome resolver
G24 calibration monitor
G25 drift engine
G26 historical analog engine
G27 Monte Carlo/scenario engine
G28 barrier first-passage engine
G29 experiment registry
G30 live intelligence API
G31 observability/data-quality
G32 reproducible release
G33 continuous scientific loop

## /subgoals
For every goal materialize dependencies, owner/claim if exposed, exact branch/HEAD, inputs, outputs, tests, evidence, blockers, Definition of Done and next action. Status vocabulary: UNSEEN, READY, CLAIMED, IN_PROGRESS, VERIFYING, BLOCKED, FAILED, DONE, SUPERSEDED.

## /gauntlet-loop
RECONSTRUCT -> SELECT highest-impact READY goal -> CLAIM non-colliding scope -> INSPECT -> IMPLEMENT smallest correct change -> CODE REVIEW -> SECURITY REVIEW -> QA -> LEAKAGE REVIEW -> PROVENANCE REVIEW -> TEST -> FIX ROOT CAUSE -> EXACT-HEAD VERIFY -> SAFE MERGE -> UPDATE GOAL GRAPH -> PERSIST CHECKPOINT -> CONTINUE.

Do not stop after one iteration while safe useful work exists.

## Priority
First failing canonical gate > dependency unlocking multiple goals > leakage/provenance defect > correctness/security > merge-ready validated work > historical completeness > forecasting capability > optimization > documentation.

## PIT law
For strict replay at prediction T, required evidence must satisfy available_at <= T and fetched_at <= T. Unknown availability fails closed. RECONSTRUCTED_PIT is explicit and separate. Preserve vintages/revisions.

## Feature/label firewall
Feature rows contain only information available at prediction_time and bind deterministically to SourceSnapshot. Future labels live in a separate trust surface. Resolving labels must never change feature identity.

## Walk-forward law
No random time-series split. Use chronological expanding/rolling windows, purging and horizon-aware embargo. Prevent unresolved/overlapping labels from leaking into training.

## Baselines before complexity
Evaluate unconditional frequency, persistence, momentum, mean-reversion and regularized logistic baselines. Complex models must demonstrate OOS improvement or be rejected.

## Calibration law
Raw scores are not probabilities. Evaluate Brier, log loss, ROC-AUC/PR-AUC where appropriate, ECE, reliability, coverage and sharpness. Calibration fitting and final evaluation must be separated.

## Forecast contract
Every eventual forecast binds forecast_id, prediction_time, horizon, training_cutoff, model/version, feature schema, SourceSnapshot, regime, calibrated P(return>0), P10/P25/P50/P75/P90, barrier probabilities, calibration evidence, supporting/contradicting evidence, uncertainty and lineage.

## Current live research hypothesis
Treat XRP->$2 as a falsifiable hypothesis, never a predetermined outcome. A $1.50-$1.55 breakout requires multi-provider acceptance plus spot/order-flow confirmation and derivatives/cross-asset context. Candidate states: BREAKOUT_UNCONFIRMED, SPOT_CONFIRMED_BREAKOUT, LEVERAGED_BREAKOUT, FAILED_BREAKOUT, NO_DATA.

## Hard safety
READ_ONLY, SHADOW_ONLY, NON_EXECUTION. No orders, custody, keys, withdrawals, account mutation, leverage or position sizing. Until canonical gates pass: execution_weight=0.0, decision_authority=false, probability_calibrated=false, production_ready=false.

## 18h cumulative budget
The nominal 18-hour budget is not Definition of Done. Continue through agents/wake-ups until North Star is complete or only verified external blockers remain. If context/time ends, persist a death-safe handoff with exact repository truth, GoalGraph state, HEADs, evidence, blockers and next READY WorkUnit.

If completed early, spend remaining capacity on falsification, leakage hunting, robustness, reproducibility, security and scientific audit. Never invent features merely to consume budget.
