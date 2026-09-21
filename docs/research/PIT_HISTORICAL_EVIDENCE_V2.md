# PIT HISTORICAL EVIDENCE V2 — Canonical Research Contract

Status: DESIGN + MIGRATION SPEC  
Authority: SHADOW_ONLY / READ_ONLY / NON_EXECUTION  
Base snapshot: PR #15 branch head \`81bace17e1735c991bc630b27facd947705d6dd6\`  
Historical salvage source: closed PR #3 snapshot \`ef4ecfa1064ace15cd413d7e8e447c71522ffe1f\`

This document defines the point-in-time historical evidence substrate required before any XRP forecast can be called calibrated. It does not grant probability, recommendation, position-sizing or execution authority.

The active microstructure agent owns the live evidence-lineage/storage work on PR #15. This research branch must not edit \`evidence_lineage.py\`, \`shadow_evidence.py\`, \`storage.py\`, live microstructure modules, or their tests while that parent work is active. Integration happens only after exact-head reconciliation.

---

## 1. North Star

Construct a historical dataset where every feature row answers one hard question:

> What information was legitimately knowable by this system at prediction time T?

The historical chain is:

RAW BYTES
→ FETCH RECEIPTS
→ NORMALIZED OBSERVATIONS
→ POINT-IN-TIME CATALOG
→ IMMUTABLE SOURCE SNAPSHOTS
→ HISTORICAL FEATURE ROWS
→ SEPARATE FUTURE-OUTCOME LABELS
→ WALK-FORWARD / OOS EVALUATION
→ CALIBRATION ARTIFACTS
→ OPTIONAL BAYESIAN POSTERIOR

No later stage may repair an epistemically invalid earlier stage.

Hard invariants remain:

- \`execution_weight = 0.0\`
- \`decision_authority = False\`
- \`probability_calibrated = False\`
- \`production_ready = False\`

until the relevant research, shadow and release gates independently pass.

---

## 2. Non-goals

This layer does not:

- place or simulate executable orders;
- size leverage or positions;
- manufacture missing timestamps;
- collapse USD and USDT markets;
- infer truth from Graphify/COS20/Qdrant retrieval scores;
- treat revised macro data as historically known before its vintage;
- use narrative/riddle outcomes as features unless an ex-ante, leakage-safe research protocol admits them;
- optimize desired XRP price targets on the same sample used to evaluate them;
- turn data quality into bullish/bearish weight.

---

## 3. Canonical temporal contract

The following clocks are distinct fields, not aliases:

| Field | Meaning |
|---|---|
| \`event_at\` | Time the underlying event economically occurred, when meaningful. |
| \`observed_at\` | Time represented by the observation itself. |
| \`published_at\` | Time the publisher/provider states that the datum/document was published. |
| \`available_at\` | Earliest defensible time the engine could have known the datum. |
| \`fetched_at\` | Time this system actually received the source response or artifact. |
| \`prediction_time\` | Decision boundary for one historical forecast row. |
| \`valid_from\` | Optional start of semantic validity. |
| \`valid_to\` | Optional end of semantic validity. |

Do not impose one universal total ordering across \`event_at\`, \`observed_at\` and \`published_at\`. Different source classes have different semantics. The universal prediction eligibility rule is narrower and explicit:

1. required \`available_at\` is known;
2. required \`fetched_at\` is known;
3. \`available_at <= prediction_time\`;
4. \`fetched_at <= prediction_time\`;
5. any source-specific validity/window constraints pass;
6. the provider/symbol/instrument/schema matches the requested feature.

Failure of a critical condition returns \`NO_DATA\`; it never guesses a timestamp or silently substitutes a later revision.

### 3.1 Availability precision

Every observation must record:

- \`availability_precision = EXACT | DATE_ONLY | INFERRED_CONSERVATIVE | UNKNOWN\`
- \`availability_policy\`
- \`availability_evidence_id\` where available.

\`UNKNOWN\` is ineligible for leakage-sensitive model input.

For \`DATE_ONLY\`, the date must not be silently converted to midnight and treated as exact intraday availability. Default intraday policy is fail-closed. A conservative next-boundary policy may be used only when versioned and documented.

### 3.2 Important current-code boundary

The current live \`EvidenceSourceDigest\` contract in PR #15 requires \`observed_at <= available_at <= fetched_at\` for its market-evidence roles. That is acceptable as a bounded live-role invariant, but it must not be generalized into a universal historical-source law without source-specific proof.

### 3.3 Historical reconstruction paradox

A historical backfill fetched today cannot truthfully claim that this system fetched the payload before a prediction made years ago. \`fetched_at\` is an acquisition fact and must never be backdated.

V2 therefore separates two research classes:

**STRICT_REPLAY**

- \`available_at <= T\`;
- actual local \`fetched_at <= T\`;
- represents information the running system physically possessed by T;
- this is the authority class for forward shadow/live evaluation.

**RECONSTRUCTED_PIT**

- the source/archive proves the datum or vintage was publicly available by T;
- actual local \`fetched_at\` may be later than T;
- the record is explicitly tagged retrospective/reconstructed;
- a reconstruction-basis/source-vintage identifier is mandatory;
- it may support historical model research, but it must never be presented as evidence that this system physically possessed the datum at T.

A reconstructed row must not silently satisfy the strict \`fetched_at <= T\` gate. Reports and calibration artifacts must disclose which class supplied each sample.

This distinction is especially important for pre-system history (2017–2025). Statistical calibration from reconstructed PIT history and operational calibration from forward strict replay are separate evidence claims. A future production-readiness decision must define the minimum forward strict evidence required per horizon; reconstructed history alone cannot prove live-pipeline availability.

---

## 4. Provenance objects

Historical storage must separate content identity from acquisition identity.

### 4.1 RawBlob

One immutable content-addressed object:

- \`payload_sha256\`
- byte count
- media type
- optional compression metadata

The blob says what bytes exist. It does not say when or how they were obtained.

### 4.2 FetchReceipt

One append-only acquisition event:

- \`fetch_id\`
- \`source_id\`
- provider
- canonical URI
- endpoint family
- request fingerprint without credentials
- \`fetched_at\`
- HTTP/result metadata
- \`payload_sha256\`
- ingestion version
- parser version
- response-header digest where useful
- quality flags

The same raw payload may legitimately have multiple fetch receipts. Deduplicating bytes must not erase acquisition history.

### 4.3 HistoricalObservation

Minimum normalized record:

- \`observation_id\`
- dataset
- logical \`record_id\`
- provider/source_id
- symbol
- instrument
- source_type
- event/observed/published/available/fetched clocks
- valid_from / valid_to
- availability precision/policy
- revision identifier or sequence where meaningful
- normalized values
- source snapshot/fetch IDs
- raw payload SHA-256
- document SHA-256 where applicable
- ingestion/schema/parser versions
- source authority
- quality flags

No field containing target/future outcome data belongs in this object.

---

## 5. Point-in-time catalog V2

The catalog performs as-of resolution; it is not a predictive model.

For prediction time T:

1. filter to observations whose required clocks are known;
2. reject \`available_at > T\`;
3. reject \`fetched_at > T\`;
4. enforce valid_from/valid_to where defined;
5. preserve provider/source identity;
6. resolve revisions only within the same logical source series;
7. select the latest eligible revision that was genuinely available by T;
8. leave independent providers as independent records;
9. hand cross-provider combination to an explicit consensus layer.

Never collapse two providers merely because they share the same \`record_id\`.

Never use lexical provider ordering as a tie-breaker for economic truth.

When revision ordering is ambiguous, fail closed or retain the ambiguity explicitly.

---

## 6. Immutable source snapshots

A prediction row references a frozen source snapshot, not a mutable query.

A \`SourceSnapshot\` must contain:

- \`source_snapshot_id\`
- \`prediction_time\`
- selected observation IDs
- fetch IDs
- content/document digests
- dataset/schema/parser versions
- provider universe version
- quality/freshness flags
- deterministic snapshot digest

Rebuilding the same snapshot from the same catalog state must yield the same digest.

Graphify and SemanticBrain may index these snapshots as derived/reconstructible artifacts, but retrieval must preserve the snapshot's temporal eligibility.

---

## 7. Historical Feature Store V1

Each feature row is immutable and contains only information eligible at \`prediction_time\`.

Minimum identity:

- \`feature_row_id\`
- \`feature_time\`
- \`prediction_time\`
- \`horizon\`
- feature schema version
- source snapshot IDs
- evidence IDs
- provider-universe version

Feature families:

- market;
- microstructure;
- derivatives;
- cross-asset;
- macro/liquidity;
- ETF/institutional;
- XRPL/on-chain;
- RLUSD;
- regulatory/event;
- COS20 state;
- explicit missingness/quality indicators.

Transforms such as scaling, winsorization, imputation, PCA, feature selection or learned embeddings must be fitted inside each training window. A full-sample transform is leakage.

---

## 8. Future Outcome Label Store

Labels live in a physically/logically separate research surface.

For each prediction time and horizon, calculate only after the feature row has been frozen:

- future return;
- MFE;
- MAE;
- realized volatility;
- drawdown;
- \`return > 0\`;
- threshold touches: ±1%, ±2%, ±5%, ±10%;
- versioned absolute barrier touches.

Current research barriers may include:

- $2
- $3
- $3.65
- $5
- $7.34
- $10
- $17
- $26.6
- $50

These barriers are research hypotheses, not training objectives. The set must be versioned and frozen before evaluation. Adding/removing barriers after seeing outcomes creates selection bias and requires a new research version.

The feature-building module must not import or query the future-label store.

---

## 9. v0.5 salvage matrix

The old PR #3 contains meaningful engineering work, but it must be transplanted rather than merged blindly.

| v0.5 element | Decision | V2 requirement |
|---|---|---|
| Content-addressed raw bytes | SALVAGE | Split RawBlob from FetchReceipt. |
| Atomic write + fsync + replace | SALVAGE | Retain durability and corruption checks. |
| Deterministic JSONL partitions | SALVAGE for alpha | Keep semantic contract; Parquet/DuckDB only after compatibility evidence. |
| SHA-256 dataset manifests | SALVAGE | Add schema/parser/source-config/provider-universe digests. |
| PointInTimeCatalog | REWRITE/EXTEND | Preserve provider dimension and all required clocks. |
| Backfill checkpoints | SALVAGE | Resume state must reconstruct all prior durable partitions. |
| ResearchSnapshotBuilder | SALVAGE/EXTEND | Require fetched_at, precision policy and snapshot lineage. |
| Coinbase/Binance historical candle adapters | SALVAGE AFTER REVIEW | Regional availability, pagination and source semantics must be revalidated. |
| FRED vintage discovery | SALVAGE | Vintage dates remain useful. |
| FRED \`available_at = vintage_date 00:00 UTC\` | REJECT | Date precision is not exact release-time availability. |
| Research-era event windows | KEEP AS METADATA | Never inject the human label as a feature/target. |
| Old multi-workflow CI controllers | REJECT | Keep current bounded Verification OS. |

### 9.1 Specific defect: raw metadata collision

The old store keys both raw bytes and metadata by payload digest. The same bytes fetched at a different time or through a different request can therefore collide with different metadata. V2 stores one RawBlob plus many immutable FetchReceipts.

### 9.2 Specific defect: resumed manifest incompleteness

The old BackfillRunner accumulates partitions in process memory and builds the final manifest from that list. On an interrupted/resumed job, earlier durable partitions can be absent from the resumed in-memory list. V2 manifest finalization must reconstruct the complete partition set from durable partition/catalog state, not only the current process.

### 9.3 Specific defect: cross-provider record collapse

The old catalog's as-of selection ultimately selects one row per \`record_id\`. For multi-provider historical market data this can destroy provider independence. V2 logical identity includes provider/source until an explicit consensus step.

---

## 10. FRED / ALFRED rule

FRED/ALFRED real-time periods and vintage dates are useful for reconstructing historical revisions, but a vintage/release date is not automatically an exact timestamp at which the engine could have consumed the datum.

The St. Louis Fed API itself notes that published release dates do not necessarily represent when data becomes available on FRED/ALFRED.

Therefore:

- retain vintage/realtime metadata;
- preserve date precision explicitly;
- use a verified exact release/availability timestamp where defensible;
- otherwise mark DATE_ONLY and fail closed for intraday use on that date;
- never synthesize midnight availability merely to make a backtest complete.

Reference:
- https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
- https://fred.stlouisfed.org/docs/api/fred/release_dates.html

---

## 11. Leakage Gauntlet V1

Every implementation must include deterministic negative tests.

| Attack / failure mode | Expected result |
|---|---|
| \`available_at > prediction_time\` | NO_DATA / reject |
| \`fetched_at > prediction_time\` | NO_DATA / reject |
| unknown critical availability | NO_DATA / reject |
| DATE_ONLY macro used intraday as midnight-known | reject |
| later macro revision substituted into older snapshot | reject |
| ETF flow/restatement learned after T | reject |
| on-chain metric recomputed later with changed methodology | reject or version separately |
| same provider presented under two aliases | independence gate fails |
| XRP/USD silently filled from XRP/USDT | reject |
| globally fitted scaler | test fails |
| globally fitted winsorization | test fails |
| centered/future-looking rolling statistic | test fails |
| label interval overlaps evaluation origin | training row purged |
| feature reads label store | architecture/test fails |
| Graphify claim with future availability | retrieval rejects |
| Qdrant result without temporal filter | retrieval rejects |
| same raw bytes fetched twice lose one fetch event | test fails |
| resume omits earlier durable partitions from manifest | test fails |
| duplicate/cyclic pagination cursor | fail closed |
| provider universe chosen using future availability | research invalid |
| source disappears and historical code silently substitutes another | fail closed/degraded explicit |
| barrier set changed after observing results | new research version required |
| riddle interpretation changed after outcome | invalid / quarantined |
| random train/test split used for time series | research gate fails |

Also maintain explicit leakage sentinels: deliberately contaminated fixtures must be detected. A gauntlet that only tests clean paths is insufficient.

---

## 12. Walk-forward / OOS contract

Primary validation is chronological.

For every test prediction time T:

- training features must have \`prediction_time < T\`;
- every training label must be fully resolved before T;
- equivalently, \`training_label_end_at <= T\`;
- transforms fit only on training data;
- hyperparameter/model selection uses only earlier nested research windows;
- no shuffled/random split;
- provider universe and feature schema are versioned.

Expanding-window walk-forward is the primary baseline. Rolling windows are challengers for non-stationarity analysis.

Embargo/purge lengths must derive from actual label overlap and horizon semantics, not a decorative constant.

---

## 13. Calibration contract

No single scalar metric is sufficient.

Binary event probabilities require at minimum:

- Brier score;
- log loss;
- reliability diagram / calibration curve;
- expected calibration error with documented binning;
- calibration intercept;
- calibration slope;
- discrimination/resolution metric;
- base-rate comparison;
- sample count and confidence interval by probability region;
- stability by chronological slice and detected regime.

Brier/log loss are proper scoring rules but mix calibration with other predictive properties; a low Brier score alone does not prove calibration. Reliability diagnostics remain mandatory.

Reference:
- https://scikit-learn.org/1.8/modules/calibration.html

Return-distribution quantiles P10/P25/P50/P75/P90 additionally require:

- pinball/quantile loss;
- empirical quantile coverage;
- interval coverage;
- no quantile crossing;
- chronological stability.

Touch probabilities are calibrated independently by barrier and horizon.

\`probability_calibrated\` should ultimately be an artifact-scoped state, not a blanket assertion. A calibrated 1D directional model does not make the 1M $17 touch probability calibrated.

---

## 14. Model ladder

Complexity is earned only after the historical substrate passes.

Research order:

1. empirical/base-rate benchmark;
2. simple regularized logistic/linear probabilistic baseline;
3. regime-conditioned baseline;
4. tree/boosting challenger where justified;
5. ensemble only with OOS evidence;
6. Bayesian posterior layer only after its component likelihoods/priors are point-in-time and calibrated.

The Bayesian layer cannot rescue an uncalibrated or leaked evidence plane.

---

## 15. Historical ingestion priority

Priority is determined by epistemic value and reconstructibility, not narrative attractiveness.

Phase A:
- XRP/BTC/ETH spot candles and returns;
- independent provider separation;
- XRP/BTC and XRP/ETH relative strength;
- canonical provider/source snapshots.

Phase B:
- macro vintages and release-aware datasets;
- yields, DXY/USD proxies, equities, VIX, energy;
- explicit date/exact availability precision.

Phase C:
- historical derivatives where provider history is defensible;
- OI, funding, basis and liquidations with instrument identity.

Phase D:
- ETF/institutional, XRPL, RLUSD and event datasets;
- methodology versioning and restatement handling.

Sparse history remains sparse. Missing history is not backfilled with invented values.

---

## 16. Integration with live ShadowEvidence lineage

The historical system consumes the same epistemic principles as the live system but does not reuse live-specific assumptions blindly.

Integration target:

\`eligible raw/source observations → historical source snapshot → feature row → optional ShadowEvidence-compatible evidence IDs → Graphify/COS20/SemanticBrain derived indices\`

Graphify/Qdrant remain derived and reconstructible. A retrieved semantic document must carry enough provenance to re-evaluate its temporal eligibility at T.

The current PR #15 evidence-lineage code is treated as an upstream contract under active ownership. V2 implementation must rebase onto the exact green parent before touching integration files.

---

## 17. Implementation waves and gates

### H0 — Contract freeze
Deliver:
- this canonical spec;
- v0.5 salvage map;
- temporal invariants;
- leakage gauntlet inventory.

Gate:
- no conflict with active PR #15 ownership;
- no new execution authority;
- no claim of calibration.

### H1 — Historical primitives
Deliver:
- RawBlob + FetchReceipt separation;
- HistoricalObservation V2;
- durable partition registry;
- PIT catalog V2;
- deterministic source snapshots.

Gate:
- hermetic tests;
- corruption/replay/resume tests;
- all clock/leakage adversarial tests;
- exact source manifest.

### H2 — Spot + macro backfill
Deliver:
- independently versioned spot adapters;
- FRED/ALFRED vintage reconstruction;
- availability-precision policy;
- data quality reports.

Gate:
- regional/provider validation;
- no silent quote mixing;
- reproducible sample rebuild;
- licence/source register updated.

### H3 — Feature / label separation
Deliver:
- HistoricalFeatureRow;
- FutureOutcomeLabel;
- versioned barrier sets;
- deterministic snapshot-to-feature compilation.

Gate:
- architecture prevents feature→label reads;
- future-data sentinels rejected;
- feature reproduction hash stable.

### H4 — Walk-forward research
Deliver:
- expanding/rolling evaluation;
- overlap purge;
- embargo where justified;
- baselines and ablations.

Gate:
- no random split;
- transforms fit inside folds;
- complete OOS prediction ledger immutable.

### H5 — Calibration
Deliver:
- calibration artifacts per horizon/event;
- reliability + proper-score reports;
- distribution-quantile coverage;
- uncertainty intervals and regime stability.

Gate:
- only artifact-scoped models that pass may set their own calibrated flag;
- global production readiness remains false.

---

## 18. Definition of Done for this frontier

Historical Evidence V2 is not done because code exists.

It is done when:

1. every critical training feature can expose its source snapshot and raw digest;
2. every feature is proven eligible at its prediction time;
3. historical revisions cannot leak backward;
4. fetch time cannot leak backward;
5. multiple providers remain distinguishable until explicit consensus;
6. interrupted backfills resume without losing prior partitions from manifests;
7. the same raw bytes can have multiple fetch receipts;
8. feature and future-label stores are separated;
9. walk-forward outputs are immutable and reproducible;
10. calibration claims are horizon/event specific and empirically evidenced;
11. semantic/narrative retrieval cannot bypass temporal gates;
12. \`execution_weight=0.0\`, \`decision_authority=False\`, and \`production_ready=False\` remain enforced.

Only after this frontier passes should Bayesian posterior forecasts become an engineering target.
