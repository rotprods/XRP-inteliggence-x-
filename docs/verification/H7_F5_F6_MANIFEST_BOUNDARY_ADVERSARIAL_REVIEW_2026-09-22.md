# H7 F5/F6 Manifest Boundary Adversarial Review — 2026-09-22

Status: **READ-ONLY ADVERSARIAL REVIEW COMPLETE · F5/F6 BLOCK REAL DATASETVERSION PROMOTION · NO CI SPEND**

## Exact live truth at review start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed immediately before mutation: **none**
- Latest merged PR: `#30`
- Latest exact verified canonical feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS for that older exact head: run `35660067501`, FAST job `106532947585` — **PASS**
- Active convergent H7 ingestion lineage: `fix/h7-window-resume-law-v1@d29b3845e55804b1c5a1402fd3ce112d76e744b9`
- Active lineage relation to current main at the preceding checkpoint: direct fast-forward descendant; F3/F4 hardening present; F5 unresolved
- Exact active-lineage FAST: **NOT_RUN**
- Local-equivalent full repository verification: **NOT_RUN** because this automation runtime cannot materialize the repository through a normal Git checkout/network path
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision decision

`fix/h7-window-resume-law-v1` is the newest observed code-bearing lineage for the historical ingestion/store seam. This wave does **not** modify that branch or its source/test files. The review is persisted on the isolated documentation branch `docs/h7-f5-f6-manifest-boundary-review-20260922`, created from exact head `d29b3845e55804b1c5a1402fd3ce112d76e744b9`.

No PR is opened by this wave and no remote verification workflow is intentionally triggered. This avoids colliding with an active source writer and avoids spending CI on a tree already known to be non-promotion-ready.

## Reviewed boundary

The scientific identity chain under review is:

`Raw evidence -> FetchReceipt -> HistoricalObservation -> DurablePartition -> job-scoped DurableManifest -> DatasetVersion -> H6/H7 OOS evidence`

The active lineage already hardens response/raw-request provenance and the backfill window/generation law. The previous checkpoint correctly identified F5: `HistoricalEvidenceStoreV2.finalize_manifest()` still enumerates all partitions for a dataset rather than the partitions owned by the exact backfill job.

This review follows that defect one boundary further into `DatasetVersion` and finds an additional provenance gap that must be closed with F5 rather than after real-corpus promotion.

## F5 — Dataset-global manifest contamination

Status: **FAIL / HIGH-SEVERITY PROVENANCE BLOCKER**

Current store finalization uses dataset-global partition enumeration. There is no durable authoritative `job_key -> partition_id` relation and no exact producing job scope in `DurableManifest` identity. Two disjoint jobs for the same dataset can therefore contaminate one another's manifest partition universe.

The previously recorded implementation law remains correct: durable idempotent job membership, job-scoped verified loading, no dataset-global fallback, crash-safe checkpoint ordering, job identity in manifest scope, explicit persisted-schema evolution, and adversarial two-job/restart/corruption tests.

## F6 — DurableManifest identity is not self-authenticating

Status: **FAIL / HIGH-SEVERITY SCIENTIFIC-LINEAGE BLOCKER**

`DatasetVersion` itself was hardened in PR #30 so that its advertised ID/hash must match its canonical payload. The immediately upstream `DurableManifest` boundary does not yet provide the same guarantee.

Current `DurableManifest` is a frozen dataclass carrying:

- `manifest_id`
- `manifest_sha256`
- `dataset`
- `schema_version`
- `created_at`
- `partition_ids`
- `total_rows`
- `relative_path`

but it has no self-validation tying `manifest_id` and `manifest_sha256` to the canonical manifest content represented by those fields. It also does not carry job scope. Direct construction is used by existing DatasetVersion tests, which proves that callers can presently supply a syntactically plausible manifest object without going through a verified durable-store read.

`build_dataset_version()` performs useful structural checks: manifest IDs and partition IDs must be unique; every manifest partition must be supplied; partition dataset must match manifest dataset; manifest row count must match supplied partitions; and the supplied partition universe must exactly equal manifest references. However, it consumes `manifest.manifest_id` and `manifest.manifest_sha256` as trusted source-manifest identity. It does not recompute the manifest digest from canonical manifest content or verify a persisted manifest artifact before committing that reference into DatasetVersion identity.

### Failure mode

A buggy or adversarial caller can create a `DurableManifest` with:

- a syntactically valid `manifest:sha256:<64-hex>` ID;
- an arbitrary syntactically valid `manifest_sha256`;
- a compatible dataset/schema;
- valid supplied partition IDs;
- a matching `total_rows`;
- an arbitrary/forged manifest identity not derived from the manifest's actual canonical payload.

The current DatasetVersion builder can then construct a perfectly self-consistent **DatasetVersion** hash that commits to a false upstream manifest reference. In that situation DatasetVersion proves its own payload integrity but not the authenticity of the source-manifest identity it cites.

F5 alone does not close this. Job scoping determines *which* partitions a manifest may contain; F6 ensures the resulting manifest identity cryptographically proves *what that manifest actually contains*.

## Required convergent F5/F6 implementation law

The active source lineage should close F5 and F6 as one bounded provenance change rather than layering another manifest architecture:

1. Add durable, idempotent `job_key -> partition_id` membership to `HistoricalEvidenceStoreV2`.
2. Register membership for a job-produced partition before advancing the corresponding checkpoint; a crash may leave immutable unreferenced material, but a completed checkpoint must never be ahead of authoritative membership.
3. Load job-scoped partitions through a verifier that rejects missing members, missing files, SHA-256 mismatch, row-count mismatch and cross-dataset membership.
4. Finalize runner-produced manifests exclusively from exact job membership; retain dataset-global `list_partitions(dataset)` only as a diagnostic/store primitive.
5. Bind `job_key` or an equivalent immutable acquisition-scope identity into the manifest canonical payload.
6. Define a canonical manifest payload containing sufficient immutable evidence to recompute identity — at minimum job scope, dataset, schema version, deterministic creation/freeze semantics, ordered partition IDs plus partition content hashes, and total rows. Do not let filesystem location become accidental scientific identity unless explicitly intended.
7. Enforce `manifest_id == "manifest:sha256:" + manifest_sha256` and recompute `manifest_sha256` from the canonical payload at construction/read time. `dataclasses.replace()` with content-bearing field changes and a stale digest must fail closed, mirroring the DatasetVersion hardening law.
8. Prefer a canonical `build_manifest(...)`/verified loader path. If direct dataclass construction remains public, `DurableManifest.__post_init__` must be sufficient to reject forged identity/content pairs.
9. Add a verified persisted-manifest loader or equivalent read path that checks registry payload, on-disk bytes/digest and reconstructed `DurableManifest` identity before downstream DatasetVersion use.
10. Increment the historical store schema deliberately for new job-membership/manifest metadata. The current metadata initialization must not silently relabel an existing incompatible v1 store as a newer schema. Either execute an explicit validated migration or fail closed with a clear migration requirement.
11. Completed-checkpoint resume must reconstruct exactly the same job-scoped manifest identity. Missing/corrupt membership is an error; dataset-global fallback is forbidden.
12. Keep F3 `[start,end)` enforcement and F4 provider/parser/ingestion generation binding intact.
13. Preserve source independence: provider identities remain explicit and USD/USDT series remain semantically distinct unless a versioned basis policy explicitly joins them.
14. Preserve all execution boundaries: no orders, custody, keys, signing, withdrawals, leverage, account mutation or position sizing; narrative evidence remains `execution_weight=0.0`.

## Minimum adversarial QA gate

The source change is not promotion-ready until tests demonstrate all of the following:

- two disjoint jobs for one dataset each finalize only their own partition set;
- adding unrelated same-dataset partitions cannot alter an existing job manifest;
- restart/resume preserves exact job membership and deterministic manifest identity;
- repeated persistence/replay is idempotent and does not duplicate membership;
- completed checkpoint with absent membership fails closed;
- missing/corrupt member partition fails closed;
- cross-dataset membership fails closed;
- manifest ID/hash disagreement fails closed;
- content-bearing manifest mutation with a stale ID/hash fails closed;
- a syntactically valid but forged direct `DurableManifest` cannot enter DatasetVersion construction as authenticated provenance;
- the canonical manifest builder/loader round-trips a valid manifest deterministically;
- legacy/incompatible persisted store schema is explicitly migrated or rejected, never silently rewritten;
- F3 window boundary and F4 provider/parser/ingestion binding remain green;
- DatasetVersion's existing canonical-payload integrity remains green.

## Code / security / QA verdict

- CODE REVIEW: **BLOCKED for promotion** — F5 and F6 are both real provenance defects at the real-corpus boundary; the convergent repair surface is clear and remains inside the existing architecture.
- PROVENANCE REVIEW: **FAIL** until job-scoped membership and self-authenticating manifest identity are implemented together.
- TEMPORAL/PIT REVIEW: **BLOCKED for real corpus** because an exact page window is not yet guaranteed to produce an exact, authenticated final manifest universe.
- SECURITY REVIEW: **PASS for this read-only review** — no execution, credential, account, wallet, custody, private-key or leverage surface is introduced.
- SOURCE-INDEPENDENCE REVIEW: **PASS / PRESERVED**.
- NARRATIVE AUTHORITY: **PASS / PRESERVED** at `execution_weight=0.0`.
- Exact active-head compile/Ruff/mypy/Bandit/pytest/coverage/repository-manifest/wheel: **NOT_RUN**.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Production: **BLOCKED**.

## Why no source mutation, PR or CI in this wave

The active source branch is a live convergence scope and F5/F6 spans store schema, manifest model, runner finalization, DatasetVersion trust boundary and adversarial tests. Writing a partial fix from a parallel branch would violate single-writer convergence and create competing provenance semantics.

A PR would also trigger FAST verification while the exact candidate is knowingly not promotion-ready and `release/MANIFEST.sha256` has not been regenerated from the final source tree. This wave therefore spends no CI merely to create activity.

## Exact resume condition / next action

On the next cold start:

1. Re-read `main`, open PRs, branch heads and `fix/h7-window-resume-law-v1` exact HEAD.
2. If that source lineage advanced, inspect whether F5/F6 are already solved and continue from its exact new head; never overwrite it from this review branch.
3. If source ownership is free, implement F5/F6 on the single existing H7 ingestion lineage, touching only the minimum store/runner/manifest/DatasetVersion/test surfaces necessary.
4. Run focused local-equivalent tests if a materialized checkout is available, then broader compile/Ruff/mypy/Bandit/hermetic coverage gates.
5. Fix causes only; do not weaken provenance, temporal, security, type or coverage gates.
6. Regenerate deterministic `release/MANIFEST.sha256` only from the exact final candidate tree.
7. Use at most one bounded exact-head FAST run when the candidate is genuinely promotion-ready.
8. Only after F3/F4/F5/F6 are green should a provider-specific historical adapter be promoted.
9. Large retained historical backfill remains independently BLOCKED by source-license/current-terms/regional/retention governance until explicitly cleared.
10. Once a tiny permitted immutable real DatasetVersion exists, execute matched H6 B0-B4 versus H7 regime/analog OOS evaluation and preserve `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE` exactly if that is the result.

No calibrated-probability, decision-authority, production-readiness or trading claim is made by this checkpoint.
