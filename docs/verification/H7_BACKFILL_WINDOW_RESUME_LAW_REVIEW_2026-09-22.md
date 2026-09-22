# H7 Backfill Window + Resume Law Review — 2026-09-22

Status: **READ-ONLY DESIGN/QA WAVE COMPLETE · SOURCE MUTATION DEFERRED TO ACTIVE INGESTION LINEAGE**

## Live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- PR #13 SemanticBrain/COS20D/Graphify foundation: **MERGED**
- PR #15 Binance/public-market microstructure + derivatives intelligence: **MERGED**
- Latest exact verified feature head remains `cf8b736a31647f5695211edf8d36b199bbe989ee`; Verification OS run `35660067501` / FAST job `106532947585`: **PASS for that older exact tree only**.
- Active child ingestion lineage observed: `fix/h7-provenance-envelope-v1@65e909b3183c044da287c8e0ba68fb440cbb0543`.
- That child was updated at `2026-09-22T04:46:50Z`, is a descendant of `fix/h7-raw-evidence-transport-v1`, and is therefore treated as an **active writer scope**.
- Exact-head workflow runs for `65e909b...`: **0 / NOT_RUN**.
- Mode remains `READ_ONLY / SHADOW_ONLY / NON_EXECUTION`.
- `production_ready=false`, `probability_calibrated=false`, `decision_authority=false`, narrative `execution_weight=0.0`.

## Collision decision

This wave does **not** modify:

- `src/xrp_regime_engine/providers/base.py`;
- `src/xrp_regime_engine/historical_backfill_v2.py`;
- their tests;
- provider-governance/root-contract files;
- Kraken/provider-specific adapter branches.

Reason: `fix/h7-provenance-envelope-v1` is active and already owns the transport/provenance seam while inheriting the runner provider-identity change. The only repository mutation from this wave is this isolated checkpoint document, branched from exact canonical `main`.

No PR was opened and no remote CI was triggered merely to create activity.

## Evidence reviewed

### Current H7 runner contract

At `fix/h7-provenance-envelope-v1@65e909b...`:

`BackfillRunnerV2.job_key()` binds only:

- `adapter.provider`;
- `adapter.dataset`;
- `adapter.schema_version`;
- `BackfillWindowV2.identity()`.

`BackfillRunnerV2._validate_page()` enforces provider/dataset/receipt-observation provenance equality, but it does **not** receive the requested `BackfillWindowV2` and therefore does not enforce that observations lie inside the declared historical window.

Validation happens before `record_fetch()` and before partition/checkpoint persistence, which gives a clean fail-closed insertion point for the missing checks.

### Current manifest identity

Canonical `DurableManifest` / `finalize_manifest()` binds:

- dataset;
- schema version;
- creation time;
- deterministic partition identities/content;
- total row count.

Partition/observation identity does not carry `FetchReceipt.ingestion_version` or `FetchReceipt.parser_version`, and the manifest currently has no parser/ingestion-version inventory.

Therefore allowing one logical resume job to span multiple parser/ingestion generations would create provenance ambiguity that the current manifest cannot make explicit.

## Decision D1 — Backfill window law

Adopt a generic runner-level interval law:

`window.start <= observation.observed_at < window.end`

for every persisted `HistoricalObservation`.

Rationale:

- `[start, end)` is composable across adjacent windows without overlap;
- exact `start` is valid;
- exact `end` belongs to the next window;
- the runner can enforce it generically without knowing provider pagination semantics;
- adapter-specific meaning of `observed_at` remains explicit at the adapter contract.

For OHLC/candle datasets, the provider adapter must separately define whether `observed_at` is canonical candle-open/event time and must reject incomplete/current candles. The generic runner should not silently invent close-time semantics from `interval_seconds` because the runner also supports non-candle event datasets.

### Required implementation shape

Change `_validate_page(adapter, page)` to accept `window` and reject any observation where:

- `observed_at < window.start`;
- `observed_at >= window.end`.

The check must happen before `record_fetch`, `save_observation`, partition persistence, or checkpoint advance.

### Minimum adversarial tests

Using a one-page adapter with otherwise valid provenance:

1. `observed_at = start - 1 microsecond` -> **FAIL CLOSED**; no receipt/partition/checkpoint persisted.
2. `observed_at = start` -> **PASS**.
3. `observed_at = end - 1 microsecond` -> **PASS**.
4. `observed_at = end` -> **FAIL CLOSED**; no persistence.
5. `observed_at = end + 1 microsecond` -> **FAIL CLOSED**; no persistence.
6. mixed page containing one valid and one out-of-window observation -> **FAIL CLOSED AT PAGE LEVEL**; no partial persistence.

## Decision D2 — Parser/ingestion resume law

Choose **homogeneous parser + ingestion generation per backfill job** for V1.

Do not permit implicit heterogeneous resume until a future manifest schema explicitly inventories parser/ingestion generations and proves deterministic replay semantics.

### Required implementation shape

Extend `HistoricalAdapterV2` identity with immutable:

- `ingestion_version`;
- `parser_version`.

Then:

1. include both fields in `BackfillRunnerV2.job_key()` material;
2. require `page.receipt.ingestion_version == adapter.ingestion_version`;
3. require `page.receipt.parser_version == adapter.parser_version`;
4. fail before persistence on mismatch;
5. preserve provider/dataset/schema/window identity already present.

This makes a parser or ingestion-generation change produce a new job key rather than silently resuming a prior checkpoint.

### Why this law is preferred now

The current durable manifest does not bind parser/ingestion version inventory. A heterogeneous resume law would therefore require a second coordinated schema/manifest migration before it could be considered provenance-complete. The homogeneous law is smaller, deterministic, fail-closed, and compatible with the existing single historical architecture.

### Minimum adversarial tests

1. same provider/dataset/schema/window + same parser/ingestion versions -> stable identical job key;
2. parser version changes -> different job key;
3. ingestion version changes -> different job key;
4. receipt parser version differs from adapter -> **FAIL CLOSED before persistence**;
5. receipt ingestion version differs from adapter -> **FAIL CLOSED before persistence**;
6. completed checkpoint from generation N cannot be resumed by generation N+1 because the derived job key differs;
7. no relaxation of provider, payload digest, source, fetch-time or window checks.

## Code / security / QA review

- CODE REVIEW: **PASS for design** — changes converge on the existing `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2 -> DurableManifest -> DatasetVersion` architecture; no parallel backfill/transport system is proposed.
- PROVENANCE REVIEW: **PASS for proposed law** — window identity is enforced against actual observations and resume identity becomes generation-bound.
- TEMPORAL/PIT REVIEW: **PASS for proposed law** — `[start,end)` is explicit and fail-closed; no `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` or `INELIGIBLE` rule is weakened.
- SECURITY REVIEW: **PASS for proposed law** — no network, credential, order, wallet, custody, leverage, private-key or account capability is added.
- SOURCE-INDEPENDENCE REVIEW: **UNCHANGED / PASS** — no fusion threshold or independent-source rule changes.
- EXECUTION SAFETY: **PASS** — `execution_weight=0.0`, `decision_authority=false`, production blocked.
- Focused static/adversarial review: **PASS as review evidence**.
- Exact candidate compile/Ruff/mypy/Bandit/pytest/coverage/manifest/wheel: **NOT_RUN**.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Production: **BLOCKED**.

## Local-equivalent verification blocker

A local checkout was attempted for `65e909b...`, but the runtime could not resolve `github.com`; repository materialization therefore failed before tests could execute.

Exact blocker: DNS/network resolution failure for `github.com` in the local container runtime.

No paid CI was consumed as a workaround.

Resume condition: when the active H7 writer scope is free, or after its owner explicitly converges these laws, materialize the exact candidate tree locally (or use the repository's approved bounded verification path), implement D1 + D2 on the same lineage, regenerate the deterministic manifest from the final exact tree, and run focused plus canonical gates before considering one bounded exact-head FAST run.

## Next highest-value action

1. Cold-start from live GitHub again.
2. Confirm whether `fix/h7-provenance-envelope-v1` has moved or opened a PR.
3. If still active, do not touch its source files.
4. When free, implement D1 + D2 on that same lineage; do not create a second historical runner/store.
5. Regenerate `release/MANIFEST.sha256` only from the final candidate tree.
6. Run focused tests for window boundaries, mixed-page atomic failure, version-key identity and receipt-version mismatches.
7. Run canonical compile/Ruff/mypy/Bandit/hermetic pytest/coverage/manifest/wheel locally-equivalent if possible.
8. Spend at most one bounded exact-head FAST run only when the candidate is genuinely promotion-ready.
9. Only after the ingestion seam is green, implement one deterministic provider-specific historical adapter/parser, preferably Kraken USD first because the design contract already exists.
10. Preserve negative scientific outcomes (`NO_DEMONSTRATED_REGIME_SKILL`, `INSUFFICIENT_EVIDENCE`) and keep production **BLOCKED** until all scientific, DEEP/RELEASE, restore/SRE and independent-review gates pass.
