# H7 Manifest Upstream Authenticity — 2026-09-22

Status: **BOUNDED F6 TRUST-BOUNDARY HARDENING COMPLETE BY INSPECTION · F5 STILL BLOCKED · NO CI SPEND**

## Live truth before mutation

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Open PRs observed at start and rechecked before checkpoint: **none**
- Canonical merged SemanticBrain/COS20D/Graphify parent: PR `#13`
- Canonical merged Binance/public-market microstructure parent: PR `#15`
- Latest merged scientific/provenance hardening: PR `#30`
- Latest verified canonical feature evidence remains PR `#30` head `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501`, FAST job `106532947585`: **PASS for that older exact tree only**
- H7 source-bearing provenance lineage selected as safe base: `fix/fetch-receipt-content-address-integrity-v1@b89c0af428ba839e63cf8ca6d0b2b93fdf0eee62`
- Sibling F5 checkpoint lineage: `fix/h7-window-resume-law-v1@d29b3845e55804b1c5a1402fd3ce112d76e744b9`
- Those siblings diverge at merge-base `fe4917c7fc784c917816d037977957e40010d554`; the unique `d29b...` commit is documentation-only F5 blocker evidence, while `b89c...` retains the richer source hardening lineage.
- Existing adversarial QA child: `test/h7-manifest-boundary-gauntlet-v1@a788c45e40a407719d690b0a301dcb5fdfa5e5ec`
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision decision

The active F5 defect spans `historical_store_v2.py`, `historical_backfill_v2.py`, durable schema/membership and resume semantics. A fresh QA branch already targets that boundary. This wave therefore did **not** mutate the store/backfill F5 scope.

Isolation was used from the richer `b89c...` source lineage and the bounded mutation was restricted to the downstream DatasetVersion trust boundary plus its fixtures/tests:

- branch: `fix/h7-manifest-upstream-authenticity-v1`
- exact base: `b89c0af428ba839e63cf8ca6d0b2b93fdf0eee62`
- implementation/test HEAD before this checkpoint: `38e81cb0ab41be1938314c658178be849861b8cd`
- relation to base: **ahead 3 / behind 0**
- relation to canonical `main`: **ahead 25 / behind 0**, merge-base exactly canonical `main`

No parallel SemanticBrain, Graphify, COS20D, Regime Engine, provider client, historical store, order path or trading architecture was created.

## F6 gap closed at the DatasetVersion trust boundary

Before this change, `build_dataset_version()` structurally checked manifest partition references and row counts but trusted `DurableManifest.manifest_id` and `manifest_sha256` as supplied upstream. A caller could use direct construction or `dataclasses.replace()` to substitute a syntactically valid forged ID/hash pair while keeping the same manifest content, and the forged identity could then be committed into an otherwise self-consistent `DatasetVersion`.

The bounded source change adds `_validate_manifest_identity(...)` inside `dataset_version_v1.py` and requires every manifest to pass it before DatasetVersion material is hashed.

The validation now:

1. requires a syntactically valid `manifest:sha256:<digest>` ID;
2. requires a syntactically valid lowercase SHA-256 manifest digest;
3. requires `manifest_id == manifest:sha256:<manifest_sha256>`;
4. canonicalizes `manifest.created_at` through the existing timezone-aware UTC law;
5. reconstructs the manifest's canonical partition material from the exact partitions referenced by that manifest;
6. uses the same deterministic `(partition_key, partition_id)` ordering as durable store finalization;
7. reconstructs the existing canonical payload fields exactly: `dataset`, `schema_version`, `created_at`, `partitions`, `total_rows`;
8. preserves the durable file identity convention by hashing canonical JSON plus the terminal newline;
9. rejects a manifest whose supplied SHA-256 does not equal the reconstructed canonical digest.

The structural checks intentionally run before the digest check so existing fail-closed errors for missing partitions, cross-dataset references and row-count mismatch retain their more specific cause.

## Test hardening

`tests/test_dataset_version_v1.py` and `tests/test_dataset_version_v1_edges.py` no longer use an arbitrary constant manifest hash for success fixtures. Their valid fixtures now derive the manifest digest from the same canonical durable payload shape.

A focused adversarial test was added:

- build an otherwise valid manifest;
- replace both `manifest_id` and `manifest_sha256` with a mutually consistent but false digest;
- require `build_dataset_version()` to reject it with a manifest content-addressed identity error.

This directly covers the F6 attack encoded independently in `test/h7-manifest-boundary-gauntlet-v1` without copying a second runtime architecture.

## Review

- CODE REVIEW: **PASS by bounded diff inspection** — one provenance validator in the existing DatasetVersion compiler; fixture updates only; no unrelated runtime surface.
- ARCHITECTURE REVIEW: **PASS** — the change strengthens the existing `DurableManifest -> DatasetVersion` trust boundary and does not create another manifest/store/compiler path.
- SECURITY REVIEW: **PASS by inspection** — no network authority, credentials, secrets, account endpoints, subprocess capability, orders, custody, wallets, signing, withdrawals, leverage or position sizing added.
- TEMPORAL/PIT REVIEW: **PRESERVED** — no `available_at`, `fetched_at`, cutoff, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` or ineligibility law was weakened.
- SOURCE-INDEPENDENCE REVIEW: **PRESERVED** — provider identities and independent-source requirements are untouched.
- NARRATIVE AUTHORITY: **PRESERVED** — narrative/riddle material remains `execution_weight=0.0`.
- EXECUTION SAFETY: **PASS** — no trading or decision authority; production remains blocked.

## Verification evidence

No PR was opened and no remote workflow was intentionally triggered merely to create activity.

- GitHub compare `b89c... -> 38e81...`: **PASS**, ahead 3 / behind 0; exactly `dataset_version_v1.py` plus its two existing test modules changed.
- Source diff review: **PASS by inspection** for the intended F6 trust-boundary behavior.
- Existing adversarial QA semantics from `test/h7-manifest-boundary-gauntlet-v1`: **SATISFIED BY INSPECTION** for the forged ID/hash case; the exact test was not executed on this branch.
- Isolated canonical-payload reproduction using Python's stdlib JSON/SHA-256 with the repository's manifest field ordering/newline convention: **PASS**; a forged digest differs from the reconstructed canonical digest.
- Direct container checkout / `git clone` of this exact branch: **BLOCKED** by `Could not resolve host: github.com`.
- Exact repository Python compile: **NOT_RUN** because the exact checkout cannot be materialized in this runtime.
- Focused pytest: **NOT_RUN**.
- Full hermetic pytest + branch coverage: **NOT_RUN**.
- Ruff lint: **NOT_RUN**.
- Ruff format: **NOT_RUN**.
- strict mypy: **NOT_RUN**.
- Bandit: **NOT_RUN**.
- changed-line coverage: **NOT_RUN**.
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / STALE by construction** after branch changes.
- exact-head FAST workflow runs observed for `38e81...`: **0 / NOT_RUN**.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Production: **BLOCKED**.

No PASS is inferred for an unexecuted gate.

## Residual F6 limitation

This wave authenticates a `DurableManifest` at the DatasetVersion trust boundary. `DurableManifest` itself still has no object-level `__post_init__` capable of reconstructing its full identity in isolation because its current dataclass carries only partition IDs, while the durable manifest digest covers the complete partition records.

Therefore F6 is **closed for DatasetVersion admission of stale/forged manifest ID/hash against supplied partition material**, but object-level standalone self-authentication should be unified with the forthcoming F5 manifest redesign rather than inventing a second canonical payload now.

The downstream boundary also still relies on the durable store to verify partition files. This change does not claim that an arbitrary detached `DurablePartition` object proves file existence or file contents.

## Remaining critical blocker — F5

Real immutable DatasetVersion promotion remains **BLOCKED** because current runner/store manifest finalization is dataset-global rather than job-scoped.

The convergent next source scope remains:

1. reconcile this branch's F6 hardening with the active H7 store/backfill lineage rather than overwriting either;
2. add durable idempotent `job_key -> partition_id` membership;
3. register membership before checkpoint advancement;
4. make completed-checkpoint resume fail closed on absent/corrupt membership with no dataset-global fallback;
5. load/verify only job-owned partitions, including file SHA-256, row count and dataset consistency;
6. finalize scientific manifests from exact job membership;
7. bind immutable job/acquisition scope into the canonical manifest payload/identity;
8. implement explicit historical-store schema migration-or-reject semantics;
9. run the three existing manifest-boundary adversarial tests plus restart/corruption/migration cases;
10. normalize formatting and regenerate `release/MANIFEST.sha256` only from the exact final reconciled candidate;
11. spend at most one bounded exact-head FAST run only when that candidate is genuinely promotion-ready.

Large retained historical backfill remains **BLOCKED** pending accepted source licence / regional restriction / retention governance. Only after a tiny permitted immutable real DatasetVersion exists should H6 B0-B4 be compared with H7 regime/analog on matched OOS evidence. Preserve `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE` if that is what the evidence shows.

No trading, order execution, custody, private-key, leverage or account-mutation authority is introduced by this wave.
