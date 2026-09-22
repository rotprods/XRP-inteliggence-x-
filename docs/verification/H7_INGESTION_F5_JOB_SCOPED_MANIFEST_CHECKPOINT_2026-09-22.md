# H7 Ingestion Convergence — F5 Job-Scoped Manifest Checkpoint — 2026-09-22

Status: **F3/F4 HARDENING PRESENT · F5 REAL-CORPUS BLOCKER CONFIRMED · NO CI SPEND**

## Exact live truth before this checkpoint

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Active convergent ingestion lineage: `fix/h7-window-resume-law-v1`
- Exact pre-checkpoint branch HEAD: `fe4917c7fc784c917816d037977957e40010d554`
- Exact pre-checkpoint tree: `d576c5ff98f4c98c227ecb19469b50428513afef`
- Relation to main at inspection: **ahead 15 / behind 0**
- Open PRs observed immediately before mutation: **none**
- Latest merged PR: `#30`
- Latest exact verified canonical feature head remains `cf8b736a31647f5695211edf8d36b199bbe989ee` from PR #30, Verification OS run `35660067501` / FAST job `106532947585` — **PASS**.
- Exact `fix/h7-window-resume-law-v1@fe4917...` workflow evidence: **NOT_RUN**.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- Production: **BLOCKED**.
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision decision

No competing open PR was observed. The newest remote code lineage on the H7 ingestion seam is the branch above; it is a fast-forward descendant of canonical main and already contains the earlier raw-evidence/provenance hardening. This checkpoint is appended to that lineage rather than creating another architecture or branch.

The mutation is documentation-only because the next source fix spans durable store schema, manifest identity, resume semantics and adversarial tests. A partial workaround in `BackfillRunnerV2` would leave the scientific identity defect unresolved and would be worse than preserving the blocker explicitly.

## F3 — exact backfill window law

**PASS BY CODE INSPECTION / TEST EXECUTION NOT_RUN ON THIS HEAD**

The active lineage validates every historical observation against the declared half-open backfill window:

`window.start <= observation.observed_at < window.end`

Observations outside that interval fail closed before persistence. The window identity is part of the content-addressed backfill `job_key`.

This closes the previously identified risk that an adapter page could persist observations outside the requested acquisition interval.

## F4 — adapter generation / provenance law

**PASS BY CODE INSPECTION / TEST EXECUTION NOT_RUN ON THIS HEAD**

The active lineage now treats `ingestion_version` and `parser_version` as required adapter generation identity and binds both into the `job_key`. It also requires each page receipt to match the adapter provider, ingestion version and parser version before observations are persisted.

Observation provenance remains bound to the page receipt through `fetch_id`, payload digest, provider, source and fetch timestamp. The existing raw-evidence transport additionally binds parsed JSON to exact bounded raw bytes and to a sanitized canonical request fingerprint.

## F5 — dataset-global manifest contamination

**FAIL / HIGH-SEVERITY PROVENANCE BLOCKER BEFORE REAL DATASETVERSION PROMOTION**

`HistoricalEvidenceStoreV2.finalize_manifest(...)` still selects partitions via:

`list_partitions(dataset)`

That is a dataset-global enumeration. `BackfillRunnerV2` passes only `dataset`, `schema_version` and `created_at` into finalization. The durable store has no authoritative `job_key -> partition_id` membership relation, and the produced `DurableManifest` does not bind its partition universe to the exact producing backfill job/window/generation.

Therefore two different backfill jobs for the same dataset can contaminate each other's scientific manifest:

1. job A persists partition A;
2. job B, with a distinct window and therefore distinct `job_key`, persists partition B;
3. job B completes;
4. dataset-global finalization can include A + B;
5. a downstream `DatasetVersion` may then claim an immutable identity whose partition universe exceeds job B's declared acquisition scope.

F3 and F4 do not close this defect: they prove validity of pages written by a job, not ownership of every partition later swept into its manifest.

## Required F5 implementation law

The next source mutation on this exact lineage must implement all of the following as one bounded provenance change:

1. Add durable, idempotent `job_key -> partition_id` membership in `HistoricalEvidenceStoreV2`.
2. Register membership only for a partition produced by that job and before the associated checkpoint is considered advanced.
3. Preserve crash safety: a crash may leave immutable unreferenced material, but must never allow a completed checkpoint to manufacture membership or fall back to dataset-global partitions.
4. Add a job-scoped partition loader that verifies every member exists, verifies file SHA-256 and row count, and verifies the member dataset matches the job's dataset.
5. Finalize runner-produced manifests from the exact job membership set, never `list_partitions(dataset)`.
6. Bind `job_key` into the manifest canonical payload/identity (or an equivalent content-addressed scope field), so window/provider/parser/ingestion identity cannot be detached from the manifest.
7. Completed-checkpoint resume must fail closed if job membership is absent/corrupt; no dataset-global fallback.
8. Replaying an already persisted page must be idempotent and must not duplicate membership.
9. Keep dataset-global partition enumeration only as a diagnostic/store primitive, not as the scientific manifest boundary.
10. Increment/migrate the historical store schema deliberately if the new durable relation changes persisted schema; never silently reinterpret an existing store.

## Minimum adversarial QA gate for F5

The implementation is not promotable until focused tests prove:

- two disjoint jobs, same dataset, one partition each -> each manifest contains only its own partition;
- job B cannot absorb job A merely because the dataset matches;
- restart/resume preserves exact membership;
- repeated persistence is idempotent;
- completed checkpoint + missing membership -> fail closed;
- member partition missing/corrupt -> fail closed;
- membership pointing to a partition from another dataset -> fail closed;
- adding unrelated same-dataset partitions cannot change a reproducible job manifest;
- manifest identity is deterministic across restart for the same job scope;
- F3 half-open window and F4 provider/parser/ingestion binding remain intact after the store change.

## Review result for the current exact head

- CODE REVIEW: **BLOCKED for real-corpus promotion** because F5 remains open; existing F3/F4 hardening is convergent and should be preserved.
- PROVENANCE REVIEW: **FAIL for real DatasetVersion promotion** until manifest scope is job-bound.
- TEMPORAL/PIT REVIEW: **BLOCKED for real corpus** because an exact page window does not yet imply an exact final manifest window.
- SECURITY REVIEW: **PASS for the inspected lineage** — no order placement, private/account endpoints, custody, signing, keys, withdrawals, leverage or position-sizing capability was added by F3/F4 or this checkpoint.
- SOURCE-INDEPENDENCE REVIEW: **UNCHANGED / PRESERVED** — provider identity remains explicit; USD and USDT evidence must remain semantically distinct unless a versioned basis policy exists.
- NARRATIVE AUTHORITY: **PASS** — narrative/riddle material remains `execution_weight=0.0`.
- Exact-head compile/Ruff/mypy/Bandit/pytest/coverage/repository-manifest/wheel: **NOT_RUN** for `fe4917...` in this environment.
- GitHub workflow evidence for `fe4917...`: **NOT_RUN**.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Production: **BLOCKED**.

## Why no PR / CI was opened

The active branch contains source/test/document changes not yet reflected in `release/MANIFEST.sha256`, and F5 is a known real-corpus blocker. Opening a PR merely to trigger FAST would knowingly spend CI on a non-promotion-ready tree. The correct order is cause fix -> focused QA -> deterministic manifest refresh -> one bounded exact-head FAST candidate.

Local-equivalent full-repository execution is also **NOT_RUN** in the current automation environment because the repository cannot be materialized through a normal Git checkout here; no PASS is inferred from inspection.

## Exact resume condition

On the next cold start:

1. re-read `main`, open PRs and `fix/h7-window-resume-law-v1` exact HEAD;
2. if another writer has advanced this same store/backfill scope, do not overwrite it — inspect whether F5 is already solved and continue from that head;
3. otherwise implement F5 on this same lineage, not a new backfill architecture;
4. run focused store/backfill tests locally-equivalent if the repository becomes materializable;
5. fix causes only; do not weaken provenance, type, security, coverage or temporal gates;
6. refresh `release/MANIFEST.sha256` only from the exact final candidate tree;
7. use at most one bounded FAST run when the candidate is genuinely promotion-ready;
8. only after F3/F4/F5 are green should a provider-specific historical parser/adapter be promoted;
9. large retained history remains blocked by the repository's data-source licence/retention governance gate;
10. after a tiny permitted immutable real DatasetVersion exists, execute matched H6 B0-B4 vs H7 regime/analog OOS evaluation and preserve `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE` exactly if observed.

No trading or execution authority is introduced by this checkpoint.
