# GOAL — XRP Intelligence OS

## North Star

Build a scientifically auditable, provenance-first, point-in-time XRP intelligence system that can transform historical and live multi-source evidence into reproducible forecast distributions across `1h`, `4h`, `1d`, `1w`, `1m`, `3m` and `1y`, with explicit uncertainty, falsification and calibration, while remaining strictly read-only and non-executing.

The canonical evidence chain is:

`RAW SOURCES -> PIT DATA PLANE -> PROVENANCE / SOURCE DIGESTS -> NORMALIZATION / ENTITY RESOLUTION -> GRAPHIFY -> COS20D -> SEMANTICBRAIN -> MARKET MICROSTRUCTURE / DERIVATIVES -> FEATURE/LABEL FIREWALL -> DATASETVERSION -> PURGED WALK-FORWARD -> H6 BASELINES -> H7 REGIME/ANALOG CHALLENGER -> H8 CALIBRATION -> H9 DISTRIBUTION/BARRIERS -> H10 FORECAST LEDGER -> H11 LIVE STATE -> H12 CONTINUOUS SCIENTIFIC LOOP`

No downstream layer may manufacture evidence missing upstream.

## Success condition

A forecast is scientifically useful only when it can be reconstructed from immutable source evidence, bound to an immutable `DatasetVersion`, generated without future leakage, frozen before the outcome, resolved later against an independently versioned label, scored OOS, calibrated only when sample/gate requirements permit it, and reproduced from versioned code/data/model artifacts.

Valid scientific outputs include negative results such as:

- `NO_DEMONSTRATED_SKILL`;
- `NO_DEMONSTRATED_REGIME_SKILL`;
- `INSUFFICIENT_EVIDENCE`;
- `NOT_CALIBRATED`;
- `NO_DATA`.

The project must preserve those outcomes rather than optimize them away.

## Primary outputs

For every eligible timestamp and horizon, the research system may produce:

- point-in-time source/evidence snapshot;
- regime/state classification with data-quality context;
- source agreement/disagreement and freshness;
- spot microstructure and order-flow evidence;
- derivatives evidence including OI, funding and basis where supported;
- XRP/BTC and XRP/ETH relative state;
- macro / liquidity / XRPL / RLUSD / event evidence when temporally eligible;
- Graphify/COS20D/SemanticBrain evidence and contradictions;
- historical analogues restricted to states strictly earlier than prediction time;
- baseline and challenger OOS scores;
- calibrated probabilities only after canonical calibration gates pass;
- distribution/barrier outputs only after upstream calibration/sample gates pass;
- explicit supporting evidence, contradicting evidence, uncertainty and epistemic state.

## Current canonical frontier

The merged lineage already contains the Verification OS, COS20D/SemanticBrain/Graphify foundation, Binance/public-market microstructure and derivatives evidence plane, PIT historical evidence substrate, feature/label firewall, purged chronological walk-forward, frozen OOS/calibration evidence core, immutable `DatasetVersion`, OOS ledger integrity, B0-B4 baseline gate, H7 regime/analog engine and OOS challenger.

The current scientific frontier is **real point-in-time historical evidence**. Mechanics alone do not demonstrate XRP predictive skill.

The next proof requires an actual immutable XRP `DatasetVersion` built through the existing `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2` seam and then executed through matched H6 baseline versus H7 regime/analog OOS evaluation.

Large retained historical backfill remains **BLOCKED** until the selected provider's current terms/regional restrictions and the repository retention policy are explicitly reconciled and accepted. Deterministic fixtures, provider-contract research, adapter engineering and tiny bounded samples where permitted remain allowed.

## Temporal / provenance acceptance law

1. Every external datum preserves provider/source identity and relevant `observed_at`, `available_at`, `fetched_at`, freshness and immutable digest/receipt lineage.
2. Future-fetched retrospective data is never silently relabelled as `STRICT_REPLAY`.
3. `RECONSTRUCTED_PIT` requires an explicit reconstruction basis; otherwise the datum is `INELIGIBLE` for ex-ante claims.
4. Independent-source requirements are semantic; duplicated upstream exposure does not count as independent confirmation.
5. `XRP_USD` and `XRP_USDT` remain distinct unless a versioned basis policy explicitly maps them.
6. Features and future labels remain physically/logically separated.
7. Walk-forward evaluation is chronological, purged and horizon-embargoed; no random split.
8. Calibration fitting and final evaluation remain separated.

## Three Definitions of Done

### ENGINEERING_DONE

Implementation, code/security/QA review, deterministic tests, exact candidate identity, reproducible artifacts and required verification gates are complete for the scope.

### SCIENTIFIC_DONE

Real OOS evidence, leakage controls, baseline comparison, falsification, uncertainty and calibration/sample adequacy are demonstrated for the claimed output.

### OPERATIONAL_DONE

Observability, immutable ledgers, reproducibility, rollback/recovery, security, release gates and required shadow evidence are complete.

A goal is globally done only when all required dimensions pass.

## Hard non-goals / forbidden authority

This repository does **not** provide or perform:

- trading or order execution;
- leverage actions;
- position sizing;
- account mutation;
- wallet signing;
- custody;
- withdrawals;
- private-key or seed handling;
- guaranteed price-direction claims;
- gate weakening to obtain a green result;
- calibrated-probability claims from raw scores or inadequate samples;
- narrative/riddle/numerology execution evidence.

Persistent safety state until an explicit canonical release contract proves otherwise:

- `execution_weight=0.0` for narrative material;
- `decision_authority=false`;
- `probability_calibrated=false` unless artifact-scoped calibration gates pass;
- `production_ready=false`;
- production **BLOCKED**.

## Release-level acceptance criteria

A production-readiness claim is forbidden until, at minimum:

1. provider and source licensing/retention constraints are recorded and accepted;
2. independent-source coverage is demonstrated for critical market evidence;
3. PIT historical evidence and immutable `DatasetVersion` reproduction pass;
4. feature/label firewall and chronological walk-forward gates pass;
5. H6 baselines and challengers are evaluated on matched OOS folds;
6. H8 calibration/sample gates pass for every probability claim;
7. distribution/barrier outputs are validated per horizon and event definition;
8. forecast/outcome ledgers are append-only and reproducible;
9. drift, provider outages and missingness fail closed;
10. security, DEEP/RELEASE, restore/recovery, shadow-duration and independent review gates pass.
