# H7 Provenance Envelope Hardening — 2026-09-22

Status: **BOUNDED FAIL-CLOSED HARDENING COMPLETE ON ISOLATED CHILD LINEAGE · NOT PROMOTED**

## Live truth before mutation

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed before and after implementation: **none**
- PR #13 and PR #15 are already merged; no parallel SemanticBrain/COS20D/Graphify or microstructure architecture was created.
- Parent H7 ingestion lineage: `fix/h7-raw-evidence-transport-v1@4a2dac81944fb0c7101e1bfe2a3be68a9cd58843`
- Parent was intentionally not moved because it had recent writer activity; this wave used isolated child `fix/h7-provenance-envelope-v1` from that exact head.
- Latest canonical exact verified feature head remains `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501` / FAST job `106532947585` — **PASS for that older tree only**.
- Current main exact CI: **NOT_RUN**.
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`, `probability_calibrated=false`, `decision_authority=false`, narrative `execution_weight=0.0`.

## Why this wave

The adversarial H7 ingestion review identified two promotion-blocking provenance gaps in the active raw-evidence seam:

1. parsed `payload` was not cryptographically/semantically bound to the exact `raw_payload` bytes;
2. response evidence did not carry a self-consistent sanitized request identity suitable for constructing `FetchReceipt` without recomputing request provenance in a second path.

The change hardens the existing `MarketDataProvider -> RawJsonEvidence -> HistoricalAdapterV2` lineage. It does not add a provider-specific adapter, second HTTP client, second backfill system, trading surface or calibrated model path.

## Bounded implementation

Implementation head before this checkpoint document:

`f9f5720384f59c1dec3a2786472013b2b2473cb5`

Changed only:

- `src/xrp_regime_engine/providers/base.py`
- `tests/test_provider_base.py`

### Response-content binding

`RawJsonEvidence` now fails closed when:

- raw response bytes are empty;
- latency is negative or non-finite;
- advertised payload SHA-256 differs from exact bytes;
- raw bytes are malformed JSON;
- JSON contains duplicate object keys;
- JSON contains non-finite constants such as `NaN`/`Infinity`;
- JSON root is not object/array;
- parsed payload differs semantically from the exact raw JSON;
- fetch time is naive.

The transport and evidence object use the same strict decoder, eliminating parser/evidence divergence for this seam.

### Request/response identity binding

Each `RawJsonEvidence` now carries and self-checks:

- uppercase request method;
- sanitized canonical HTTPS URI;
- optional canonical JSON request-body SHA-256;
- request fingerprint = SHA-256 over `{method, canonical_uri, body_sha256}`.

Query parameters are canonically ordered. Credential-shaped query values (`api_key`, token/secret/signature/password/credential variants) are replaced with `<redacted>` before entering the evidence URI/fingerprint. The actual request still receives the original parameter value; the evidence object never stores the secret value.

This means a provider-specific historical adapter can consume transport-derived `canonical_uri` and `request_fingerprint` directly when building `FetchReceipt`, rather than reconstructing request identity independently.

## Verification evidence

No paid CI and no workflow run was triggered merely to create activity.

Available local-equivalent harness evidence on the implemented logic:

- valid raw JSON + matching parsed payload: **PASS**;
- parsed/raw disagreement: **PASS, rejected**;
- duplicate JSON object keys: **PASS, rejected**;
- non-finite JSON constant: **PASS, rejected**;
- stable fingerprint under query parameter reordering: **PASS**;
- different sensitive credential values produce the same redacted request identity: **PASS**;
- secret values absent from canonical URI: **PASS**;
- changed non-sensitive query semantics change fingerprint: **PASS**;
- POST canonical JSON body produces deterministic body digest/fingerprint: **PASS**.

Remote exact-head workflow lookup for `f9f5720384f59c1dec3a2786472013b2b2473cb5`: **0 runs**.

Canonical repository gates for this child lineage:

- compile: **NOT_RUN**
- Ruff lint/format: **NOT_RUN**
- strict mypy: **NOT_RUN**
- Bandit: **NOT_RUN**
- hermetic pytest + branch coverage: **NOT_RUN**
- changed-line coverage: **NOT_RUN**
- deterministic source manifest: **NOT_RUN / expected stale**
- wheel: **NOT_RUN**
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**

No stronger claim is made.

## Code / security / QA review

- CODE: **PASS for bounded design review** — no second provider/backfill architecture; request identity is derived once at the hardened transport boundary.
- PROVENANCE: **PASS for the two targeted gaps** — exact bytes bind parsed content; sanitized request identity binds method/URI/body digest.
- SECURITY: **PASS for the bounded change** — secrets are redacted from evidence identity and repr; no credentials/private endpoints/order/wallet/custody/leverage capability added.
- TEMPORAL/PIT: **UNCHANGED / PASS** — no weakening of `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` or `INELIGIBLE` laws.
- SOURCE INDEPENDENCE: **UNCHANGED / PASS** — no provider fusion or independent-source threshold change.
- EXECUTION SAFETY: **PASS** — read-only/non-execution boundary preserved.
- QA: targeted invariant harness **PASS**; canonical suite **NOT_RUN**.

## Remaining H7 ingestion blockers

This branch is **not merge-ready** yet.

1. `BackfillRunnerV2` still needs explicit fail-closed enforcement that persisted observations lie inside the declared `BackfillWindowV2` interval.
2. The parser/ingestion-generation resume law is still undecided: homogeneous generation per job vs explicit heterogeneous-version inventory in manifest identity.
3. Provider-specific adapter code remains deferred until the combined ingestion seam is reconciled and canonically verified.
4. Large retained historical backfill remains **BLOCKED** until provider retention/regional/derived-use policy is accepted and recorded.
5. `release/MANIFEST.sha256` must be regenerated from the final candidate tree before promotion.
6. At most one bounded exact-head FAST run should be spent only after local/canonical-equivalent gates are green.

## Resume condition / next action

On the next cold start:

1. re-fetch `main`, open PRs, parent `fix/h7-raw-evidence-transport-v1` and this child exact head;
2. if parent advanced independently, compare and reconcile rather than overwrite;
3. converge the runner-window law and parser-generation resume law on one lineage without opening a second backfill architecture;
4. run the canonical local-equivalent suite when repository materialization is available;
5. regenerate the deterministic manifest only at the final candidate tree;
6. use one exact-head FAST only when promotion-ready;
7. only then implement the deterministic Kraken USD historical parser/adapter using the existing `HistoricalAdapterV2` seam;
8. preserve real negative scientific outcomes and keep production **BLOCKED** until all canonical scientific, DEEP/RELEASE, restore/SRE and independent-review gates pass.
