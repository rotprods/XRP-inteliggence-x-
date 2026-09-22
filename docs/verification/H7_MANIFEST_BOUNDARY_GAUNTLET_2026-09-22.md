# H7 Manifest Boundary Gauntlet — 2026-09-22

Status: **ISOLATED ADVERSARIAL QA ADDED · SOURCE FIX DEFERRED TO AVOID COLLISION · NO CI SPEND**

## Live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- PR #13 (Verification OS + COS20D/SemanticBrain/Graphify): merged and canonical parent.
- PR #15 (Binance/public-market microstructure + derivatives evidence): merged and canonical parent.
- Latest merged PR observed: `#30`.
- Open PRs observed immediately before mutation: **none**.
- Canonical mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Active H7 lineage / collision decision

The newest observed source-bearing H7 ingestion/store lineage is:

- `fix/h7-window-resume-law-v1@d29b3845e55804b1c5a1402fd3ce112d76e744b9`
- relation to canonical `main`: fast-forward descendant; no open PR.
- exact-head FAST: **NOT_RUN**.

A newer documentation-only adversarial review exists at:

- `docs/h7-f5-f6-manifest-boundary-review-20260922@4f9a4af6777bf2e561c61753113683c8142878f3`
- parent: `d29b3845e55804b1c5a1402fd3ce112d76e744b9`
- it identifies F5 dataset-global manifest contamination and F6 non-self-authenticating `DurableManifest` identity as blockers before real DatasetVersion promotion.

A sibling hardening lineage also exists:

- `fix/fetch-receipt-content-address-integrity-v1@b89c0af428ba839e63cf8ca6d0b2b93fdf0eee62`
- compared with `fix/h7-window-resume-law-v1`, the branches are **diverged** with merge-base `fe4917c7fc784c917816d037977957e40010d554`.
- the sibling contains `FetchReceipt` identity/storage hardening and must be reconciled before any single H7 ingestion candidate is promoted.

Because the active source scope spans `historical_store_v2.py`, `historical_backfill_v2.py`, `historical_contract.py` and associated tests, this wave deliberately did **not** mutate those files or overwrite either source branch. Isolation is required to preserve single-writer-per-scope behavior.

## Bounded change

Created isolated QA child:

- branch: `test/h7-manifest-boundary-gauntlet-v1`
- exact parent: `4f9a4af6777bf2e561c61753113683c8142878f3`
- exact test implementation HEAD before this checkpoint: `ab3effcac6b9bf8086a3792b550d3c46fb3a7901`
- runtime source changes: **none**
- added test module: `tests/test_h7_manifest_boundary_gauntlet.py`

The module encodes three adversarial invariants using the current public API rather than inventing a parallel store/manifest interface:

1. **F5 two-job isolation** — two disjoint backfill jobs for the same dataset must each finalize exactly their own partition universe.
2. **F5 resume determinism** — after a second same-dataset job adds unrelated partitions, resuming an already completed first job must reproduce the first job's original manifest identity and partition set without refetching.
3. **F6 upstream authenticity** — `build_dataset_version()` must reject a syntactically valid but forged `DurableManifest` ID/hash pair rather than committing the forged upstream identity into an otherwise self-consistent DatasetVersion.

These tests are intentionally written as promotion gates for the convergent F5/F6 source repair. They do not weaken any existing quality threshold and do not mark known-broken behavior as expected success.

## Why this is the highest-value safe action

Current source inspection proves the real-corpus boundary is not promotion-safe yet:

- `HistoricalEvidenceStoreV2.finalize_manifest()` enumerates `list_partitions(dataset)`, so manifest scope is dataset-global rather than job-scoped.
- completed-checkpoint resume re-finalizes through that same dataset-global path, so unrelated later partitions can change a completed job's manifest identity.
- `DurableManifest` has no self-validation binding `manifest_id` / `manifest_sha256` to canonical manifest content.
- `build_dataset_version()` structurally validates supplied manifest partition references, but treats `manifest.manifest_id` and `manifest.manifest_sha256` as trusted upstream identity.

The source repair is therefore real and high priority, but mutating it in this run would collide with an active source-bearing H7 lineage. A focused adversarial harness reduces ambiguity for the source writer without creating another architecture.

## Code / security / QA review

- CODE REVIEW: **PASS for bounded test-only diff** — one new focused test module, no runtime/source mutation.
- ARCHITECTURE REVIEW: **PASS** — tests exercise the existing `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2 -> DurableManifest -> DatasetVersion` chain only.
- PROVENANCE REVIEW: **FAIL on current source behavior for F5/F6 by inspection**; the new tests encode the required fail-closed contract.
- TEMPORAL/PIT REVIEW: **UNCHANGED / PRESERVED** — no `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT`, cutoff or window semantics were weakened.
- SOURCE-INDEPENDENCE REVIEW: **UNCHANGED / PRESERVED** — provider identities and independent-source requirements remain explicit.
- SECURITY REVIEW: **PASS for this wave** — no credentials, network client, private/account endpoint, order route, custody, signing, keys, withdrawals, leverage or position-sizing capability added.
- EXECUTION SAFETY: **PASS** — no trading or decision authority; production remains blocked.
- COLLISION REVIEW: **PASS for observed remote state** — no open PRs; source branches were left untouched; the QA work is isolated on a child branch. Unpushed/local writers cannot be proven absent.

## Verification evidence

No remote workflow or paid CI was intentionally triggered.

- Python syntax compilation of the exact new test module content before commit: **PASS**.
- GitHub compare `4f9a4af... -> test/h7-manifest-boundary-gauntlet-v1@ab3effc...`: **PASS**, ahead 1 / behind 0, exactly one added test file, zero source changes.
- Expected F5 current-source result: **FAIL by code inspection** because manifest finalization is dataset-global and completed resume re-finalizes from the same global partition set.
- Expected F6 current-source result: **FAIL by code inspection** because forged manifest identity is not recomputed/authenticated before DatasetVersion construction.
- Focused pytest on exact branch: **NOT_RUN** — exact repository checkout is not materialized in this execution environment.
- Full hermetic pytest + branch coverage: **NOT_RUN**.
- Ruff lint/format: **NOT_RUN**.
- strict mypy: **NOT_RUN**.
- Bandit: **NOT_RUN**.
- changed-line coverage: **NOT_RUN**.
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / expected stale** because a test/checkpoint file was added on this isolated branch.
- exact-head FAST for this branch: **NOT_RUN by design**; no CI was spent on a candidate known not to be source-complete.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Production: **BLOCKED**.

Latest previously verified canonical feature evidence remains PR #30 head `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501`, FAST job `106532947585` — **PASS for that older exact source tree only**.

## Resume condition / next action

1. Cold-start again from current `main`, open PRs and all H7 source heads.
2. Reconcile `fix/h7-window-resume-law-v1` with the sibling `fix/fetch-receipt-content-address-integrity-v1`; do not discard either proven hardening set and do not merge either wholesale without inspection.
3. Implement F5 and F6 on the single reconciled source lineage:
   - durable idempotent `job_key -> partition_id` membership;
   - job-scoped verified partition loading;
   - checkpoint ordering that cannot get ahead of membership;
   - no dataset-global fallback for scientific manifests;
   - canonical self-authenticating `DurableManifest` payload/identity including immutable job/acquisition scope;
   - explicit historical-store schema evolution/migration-or-reject semantics.
4. Rebase/cherry-pick `tests/test_h7_manifest_boundary_gauntlet.py` onto that exact candidate and make all three adversarial tests pass by fixing causes only.
5. Add the remaining F5/F6 corruption/restart/migration tests from the adversarial review before promotion.
6. Run focused + full hermetic quality gates locally-equivalent if available.
7. Refresh `release/MANIFEST.sha256` only from the exact final candidate tree.
8. Use at most one bounded exact-head FAST run when the candidate is genuinely promotion-ready.
9. Large retained historical backfill remains **BLOCKED** pending source licence/region/retention governance acceptance.
10. Only after a tiny permitted immutable real DatasetVersion exists should H6 B0-B4 vs H7 regime/analog be executed on real XRP history; preserve `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE` if observed.

No trading, order execution, custody, private-key, leverage or account-mutation authority is introduced by this wave.
