# H7 Backfill Manifest Job-Scope Review — 2026-09-22

Status: **READ-ONLY ADVERSARIAL REVIEW COMPLETE · NEW HIGH-SEVERITY CORRECTNESS BLOCKER RECORDED · SOURCE MUTATION DEFERRED TO ACTIVE INGESTION LINEAGE**

## Exact live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- Latest exact verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS for that older exact feature head: run `35660067501` / FAST job `106532947585` — **PASS**
- Exact-current-main workflow evidence: **NOT_RUN**
- Active H7 ingestion writer observed: `fix/h7-provenance-envelope-v1@65e909b3183c044da287c8e0ba68fb440cbb0543`
- Active H7 writer relation to canonical main: **ahead by 12 / behind by 0**
- That lineage already owns `providers/base.py`, `historical_backfill_v2.py` and their focused tests; this review does not modify those files.
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Why this wave was selected

The active H7 ingestion lineage is recent and must be treated as an owned writer scope. The previously recorded F1/F2 provenance-envelope gaps have been hardened on that lineage; F3 window enforcement and F4 parser/ingestion-generation resume law are already specified by separate checkpoints.

The safest useful action was therefore a disjoint read-only adversarial review of the durable store/manifest boundary, because a real DatasetVersion must not be assembled from partitions outside the exact backfill job that claims to have produced it.

No PR was opened and no remote CI was triggered merely to create activity.

## New finding F5 — manifest finalization is dataset-global, not backfill-job scoped

Severity: **HIGH before any real DatasetVersion corpus is materialized**

Current `HistoricalEvidenceStoreV2.finalize_manifest(...)` obtains its partition set with:

`list_partitions(dataset)`

which returns **every durable partition registered for that dataset in the store**.

Current `BackfillRunnerV2` calls `finalize_manifest(...)` with only:

- `dataset`;
- `schema_version`;
- `created_at`.

Although `persist_partition_then_checkpoint(...)` receives `job_key`, the store does not persist a `job_key -> partition_id` membership relation and `DurableManifest` does not encode the originating backfill job/window.

### Failure mode

Given one store root and one dataset such as `xrp_spot_1h`:

1. job A backfills window A and persists partition A;
2. job B later backfills a disjoint window B and persists partition B;
3. job B completes;
4. job B finalizes a manifest by dataset;
5. the resulting manifest includes both partition A and partition B, regardless of whether partition A belonged to job B.

Therefore a completed backfill can produce a manifest whose content extends beyond the exact job/window encoded by its `job_key`.

This remains possible even after F3 adds perfect `[start,end)` validation to each page, because F3 validates newly persisted observations while finalization still sweeps historical partitions from other jobs for the same dataset.

### Scientific/provenance impact

If such a manifest is promoted into `DatasetVersion`, downstream H6/H7 OOS evidence can be attributed to an immutable dataset identity whose partition universe was not actually produced by the declared backfill job/window.

Consequences include:

- cross-window contamination;
- non-local manifest drift as unrelated same-dataset jobs are added to the store;
- inability to prove that a DatasetVersion corresponds to one requested historical acquisition scope;
- possible accidental inclusion of partitions acquired under different provider/parser/ingestion generations;
- weakened forensic reconstruction of real-data H6/H7 experiments.

This is a provenance identity defect, not a trading/execution issue.

## Existing test gap

`test_resume_manifest_reconstructs_all_durable_partitions` proves restart/resume behavior for **one** job and one dataset. It does not create two distinct backfill jobs/windows for the same dataset and therefore does not falsify dataset-global manifest contamination.

The current manifest-determinism test likewise uses a single dataset partition set and cannot detect job-scope leakage.

## Required convergence law

Before the first real retained corpus is promoted, every backfill-produced manifest must be scoped to the exact producing job.

Preferred V1 law:

1. persist an explicit durable `job_key -> partition_id` membership relation;
2. register membership before advancing the associated checkpoint;
3. make membership idempotent on replay/resume;
4. finalize runner-produced manifests from the partition set belonging to that `job_key`, not from all partitions in the dataset;
5. fail closed if a referenced partition is missing, corrupt, belongs to another dataset, or cannot be proven as a member of the job;
6. bind the manifest to the job identity (directly in manifest material or through an equally explicit content-addressed job-scope field) so the requested window/generation cannot be silently detached from the manifest;
7. preserve the generic store's ability to enumerate dataset partitions for diagnostics, but do not use dataset-global enumeration as the runner's scientific manifest boundary.

After the already-decided F4 law is implemented, `job_key` should also bind homogeneous `parser_version` and `ingestion_version`, so manifest job scope inherits provider/dataset/schema/window/parser/ingestion identity.

## Minimum adversarial test matrix

1. two disjoint jobs, same dataset, one partition each -> each job manifest contains only its own partition;
2. job B cannot absorb job A partition merely because dataset matches;
3. restart/resume preserves job membership deterministically;
4. replaying an already persisted page is idempotent and does not duplicate membership;
5. checkpoint failure may leave an immutable unreferenced/member partition, but must not advance a completed checkpoint incorrectly;
6. a completed checkpoint with missing job-partition membership -> **FAIL CLOSED**, not dataset-global fallback;
7. corrupt/missing member partition -> **FAIL CLOSED**;
8. job membership referring to another dataset -> **FAIL CLOSED**;
9. manifest identity remains deterministic across restart for the same exact job partition set;
10. adding an unrelated same-dataset job does not change a previously reproducible job manifest when the same `created_at`/job material is replayed.

## Code / security / QA review

- CODE REVIEW: **FAIL for real-corpus promotion / PASS for current research-only direction** — runner/store architecture is coherent, but the manifest boundary is not yet job-scoped.
- PROVENANCE REVIEW: **BLOCKED** — F5 permits dataset-global partition contamination across distinct job scopes.
- TEMPORAL/PIT REVIEW: **BLOCKED for real DatasetVersion promotion** — an exact page window cannot guarantee an exact final manifest window while unrelated partitions can be swept in at finalization.
- SECURITY REVIEW: **PASS for inspected code** — no order/private/account/wallet/custody/leverage surface was introduced by this review.
- SOURCE-INDEPENDENCE REVIEW: **UNCHANGED** — the finding is orthogonal to provider independence but becomes more important when multiple provider-specific jobs coexist.
- QA REVIEW: **BLOCKED before real corpus** — a two-job same-dataset adversarial regression test is missing.
- compile/Ruff/mypy/Bandit/full pytest/coverage/manifest/wheel for an implementation candidate: **NOT_RUN** because this wave is review/documentation only.
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**
- Production: **BLOCKED**

## Collision decision

No source mutation was made because `fix/h7-provenance-envelope-v1@65e909b...` is a recent active writer over the same ingestion lineage, including `historical_backfill_v2.py`.

This checkpoint is isolated on `docs/h7-manifest-job-scope-review-20260922` from exact canonical `main@a9ad231...` and changes only this document.

## Exact blocker and resume condition

`REAL_DATASETVERSION_PROMOTION = BLOCKED` until F3, F4 and F5 converge on one canonical ingestion lineage and the resulting candidate passes canonical quality gates.

Resume implementation only after cold-start confirms the active H7 ingestion writer is free or has explicitly incorporated these laws.

Then:

1. implement F3 `[start,end)` runner enforcement;
2. implement F4 homogeneous parser/ingestion generation in `job_key` + receipt binding;
3. implement F5 durable job-partition membership and job-scoped manifest finalization;
4. add focused adversarial tests for all three laws;
5. regenerate `release/MANIFEST.sha256` only from the exact final candidate tree;
6. run compile, Ruff lint/format, strict mypy, Bandit, hermetic pytest + branch coverage, 100% changed-line coverage, repository/source-manifest contracts and wheel locally-equivalent where available;
7. spend at most one bounded exact-head FAST run only when genuinely promotion-ready;
8. fix causes, never lower thresholds;
9. only then implement/promote one provider-specific historical adapter/parser and create a tiny bounded real DatasetVersion;
10. run matched H6 B0-B4 vs H7 regime/analog OOS evidence and preserve `NO_DEMONSTRATED_REGIME_SKILL` / `INSUFFICIENT_EVIDENCE` exactly when observed.

## Durable next action

On the next cold start, re-read live `main`, open PRs, `fix/h7-provenance-envelope-v1`, `docs/h7-window-resume-law-review-20260922`, and this checkpoint. Do not start Kraken/Binance/Coinbase historical adapter implementation until the ingestion seam is provenance-complete and job-scoped.
