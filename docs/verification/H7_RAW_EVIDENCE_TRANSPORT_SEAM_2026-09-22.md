# H7 Raw-Evidence Transport Seam — 2026-09-22

Status: **BOUNDED IMPLEMENTATION + PROVIDER-PROVENANCE CONVERGENCE COMPLETE ON ISOLATED BRANCH · NOT PROMOTED**

## Exact live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical base: `main@a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Base tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed immediately before mutation: **none**.
- Latest merged PR: `#30`.
- Latest exact verified feature head before this wave: `cf8b736a31647f5695211edf8d36b199bbe989ee`.
- Verification OS run `35660067501`, FAST job `106532947585`: **PASS** for that older exact feature head.
- Exact-current-main FAST: **NOT_RUN**.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`.
- `probability_calibrated=false`.
- `decision_authority=false`.
- narrative `execution_weight=0.0`.

## Collision audit

The following current-main descendants were already present:

1. `docs/h7-provider-contract-reconciliation-20260922@760bca2ee67a5014f6438c442b7b9bb21f7aad61`
   - owns provider terms / retention governance material;
2. `fix/h7-adapter-provider-provenance-v1@042a135a5cda516ea3f8175bd06de60320f2649f`
   - contained the `HistoricalAdapterV2` provider-binding guard and adversarial test;
3. `docs/h7-root-contract-reconciliation-20260922@741333f28091d0ebc003cc1e22f16b442baf1065`
   - owns root operating-contract reconciliation;
4. `docs/h7-kraken-historical-adapter-design-20260922@b9dbf0d054e1487bc28ee101ee71648166e97621`
   - documents the non-duplicative Kraken H7 adapter contract and identifies the raw-evidence transport seam as a safe precursor.

No open PRs were observed before this convergence mutation. This branch intentionally absorbed only the already-isolated provider-identity guard because it is disjoint from the provider transport files and directly strengthens the same H7 historical-ingestion lineage. Provider-governance and root-contract branches remain untouched.

## Why this change is necessary

Canonical historical ingestion already has the correct architecture:

`HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2 -> DurableManifest -> DatasetVersion`.

Canonical public-market providers already share the hardened asynchronous `MarketDataProvider` transport. Before this seam, `_request_json()` intentionally returned parsed JSON, latency and payload SHA-256, but it did not expose the exact bounded response bytes or a transport-boundary fetch timestamp. A historical adapter therefore could not construct a `BackfillPageV2.raw_payload` / `FetchReceipt` from the same hardened request without either duplicating the HTTP stack or performing a second fetch.

A second client would duplicate SSRF/DNS/redirect/size/retry/secret-redaction controls and would create two competing provenance paths. This branch closes that seam once inside the existing transport.

A second defect was also reconciled from the existing provider-provenance hardening branch: `BackfillRunnerV2.job_key()` binds a run to `adapter.provider`, but `_validate_page()` did not previously require `page.receipt.provider == adapter.provider`. A buggy or adversarial adapter could therefore claim one provider identity while returning a self-consistent page from another provider. The converged branch now fails closed before any raw payload, observation, partition or checkpoint persistence.

## Bounded implementation

Branch: `fix/h7-raw-evidence-transport-v1`

Raw-transport implementation head before first checkpoint: `f187c087acaeb4ef315f05e9507ee023a7bf497b`.

Provider-provenance convergence implementation head before this checkpoint: `3595bacf6619a057b96b03cf736234d20478957e`.

Changed runtime files:

- `src/xrp_regime_engine/providers/base.py`
  - adds frozen `RawJsonEvidence` carrying parsed JSON, the **exact bounded raw response bytes**, response SHA-256, latency and a UTC `fetched_at` captured immediately after the response body is consumed;
  - parsed and raw payload fields are excluded from dataclass `repr` to reduce accidental log propagation;
  - factors existing transport behavior into protected `_request_json_evidence(...)`;
  - keeps `_request_json(...)` backward compatible by delegating and returning the original `(payload, latency_ms, payload_sha256)` tuple;
  - preserves HTTPS/allowlisted-host checks, DNS public-address validation, allowed-method policy, bounded response size, retry behavior, no redirect following, `trust_env=False`, JSON-root validation and sanitized transport errors.

- `src/xrp_regime_engine/historical_backfill_v2.py`
  - now requires `page.receipt.provider == adapter.provider` before any persistence path;
  - preserves all existing dataset/fetch/digest/source/timestamp page validation.

Changed focused tests:

- `tests/test_provider_base.py`
  - verifies exact raw bytes and SHA-256 are preserved;
  - verifies `fetched_at` is captured within the acquisition interval;
  - verifies parsed/raw provider content and query values are not emitted by `repr`;
  - existing tests continue to exercise the backward-compatible `_request_json()` path, retries, response-size rejection, non-JSON rejection, error redaction and method/path fail-closed behavior.

- `tests/test_historical_adapter_provider_binding.py`
  - adversarial adapter claims `kraken` while returning a valid `coinbase` receipt/observation pair;
  - asserts the run is rejected before raw blobs, fetch receipts, observations or checkpoints are persisted.

No provider endpoint, credential, private route, order route, account mutation, trading capability, wallet/custody capability, leverage action, paid API requirement, model authority or narrative weight was added.

## Review

- CODE REVIEW: **PASS for the bounded combined diff** — one shared transport seam plus one pre-persistence provider-identity guard; no second HTTP/backfill architecture.
- ARCHITECTURE REVIEW: **PASS** — both changes strengthen the same `HistoricalAdapterV2 -> BackfillRunnerV2` seam rather than creating a parallel ingestion path.
- SECURITY REVIEW: **PASS for the bounded diff** — existing host/method/DNS/redirect/size/retry controls remain intact; errors still do not propagate raw query material; raw/parsed payloads are omitted from `repr`; no new execution authority exists.
- PROVENANCE REVIEW: **PASS** — future `FetchReceipt` creation can bind to the exact transport bytes/time and runner persistence now binds receipt provider to adapter identity.
- SOURCE-INDEPENDENCE REVIEW: **PASS** — one provider cannot be accepted under another provider's adapter identity; no independent-source threshold was weakened.
- TEMPORAL REVIEW: **PASS** — `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` and future-information semantics remain unchanged.
- EXECUTION SAFETY: **PASS** — still READ_ONLY / SHADOW_ONLY / NON_EXECUTION.
- COLLISION REVIEW: **PASS for observed remote state** — branch remained a direct descendant of `main@a9ad231...`; open PR count was zero at mutation time; absence of unpushed/local writers cannot be proven.

## Verification evidence

Paid/remote CI was intentionally not triggered merely to create activity.

Existing local-equivalent evidence for the raw transport seam:

- Python syntax compile of the changed transport seam: **PASS**.
- Focused mocked-transport execution of `_request_json_evidence(...)`: **PASS**.
- Exact raw-byte equality: **PASS**.
- Raw-payload SHA-256 equality: **PASS**.
- UTC fetch-time interval assertion: **PASS**.
- backward-compatible `_request_json(...)` tuple behavior: **PASS**.
- disallowed `DELETE` method remains rejected: **PASS**.
- parsed/raw payload and request query value absent from `RawJsonEvidence.__repr__`: **PASS**.

Existing local-equivalent evidence for the provider-identity guard was preserved byte-for-byte from `fix/h7-adapter-provider-provenance-v1`:

- changed `historical_backfill_v2.py` blob now matches the previously reviewed guard blob `6238affdc84b13461c131984516ae17a971076e1`: **PASS by content identity**;
- adversarial test blob now matches `340aa8a54062adadd97e5c9c985621aaa45d2f0b`: **PASS by content identity**;
- prior guard checkpoint recorded syntax compile and isolated mismatch-before-persistence execution: **PASS for those identical blobs**.

Current combined branch comparison against `main@a9ad23126bcedfc6bec3a338693a3b1dace31236`:

- branch status: **ahead**, not behind;
- ahead by 5 commits before this checkpoint update;
- changed runtime files: exactly 2;
- changed tests: exactly 2;
- checkpoint docs: 1;
- no unrelated architecture or execution surface observed.

Unavailable in this runtime:

- complete repository materialization: **BLOCKED** because direct GitHub clone cannot resolve `github.com` from the container;
- full repository pytest: **NOT_RUN**;
- Ruff: **NOT_RUN**;
- strict mypy: **NOT_RUN**;
- Bandit: **NOT_RUN**;
- changed-line coverage: **NOT_RUN**;
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / expected stale** because source, tests and this checkpoint changed;
- exact branch FAST CI: **NOT_RUN by design**;
- DEEP: **NOT_RUN**;
- RELEASE: **NOT_RUN**.

No gate has been weakened and this branch is not asserted merge-ready.

## Promotion blocker / resume condition

`H7_PROVIDER_INGESTION_SEAM_PROMOTION = BLOCKED` until:

1. live `main`, open PRs and current H7 branch scopes are re-read;
2. a complete checkout or equivalent canonical runner executes focused provider tests plus the full hermetic suite;
3. Ruff, strict mypy and Bandit pass;
4. changed-line coverage meets the canonical 100% requirement;
5. `release/MANIFEST.sha256` is regenerated from the exact candidate tree and repository/source-manifest verification passes;
6. provider-governance reconciliation is reviewed separately; a code PASS does not authorize a large retained historical corpus;
7. only then, if promotion is warranted, one bounded FAST run is used on the exact candidate head; failures are fixed at cause, never by weakening thresholds.

## Historical-data blocker

This transport/provenance seam does **not** authorize a large retained historical corpus.

The provider-contract reconciliation keeps `LARGE_RETAINED_BACKFILL = BLOCKED` until provider-specific terms/region/retention/derived-feature use are mapped and owner retention acceptance is recorded. Retrospective data fetched after a historical prediction time must remain `RECONSTRUCTED_PIT` with a valid reconstruction basis or `INELIGIBLE`; it must never be relabelled `STRICT_REPLAY`.

## Next convergent action

On the next cold start:

1. re-read `main`, open PRs and all H7 descendants;
2. treat `fix/h7-adapter-provider-provenance-v1` as **functionally absorbed into this candidate** unless live state has changed; do not reimplement it again;
3. reconcile provider-governance/root-contract documentation branches without merging stale or overlapping state wholesale;
4. validate this combined H7 ingestion seam on a complete checkout and regenerate the deterministic manifest;
5. after the seam is verified, implement **one** deterministic provider-specific historical adapter/parser on `HistoricalAdapterV2`, with Kraken USD as the currently documented independent-source candidate;
6. use minimal/synthetic fixtures first; do not perform a large retained backfill without the governance resume condition;
7. only after a valid real DatasetVersion exists, run matched H6 B0-B4 versus H7 regime/analog evidence and preserve `NO_DEMONSTRATED_REGIME_SKILL` / `INSUFFICIENT_EVIDENCE` as valid outcomes;
8. keep production **BLOCKED** until all canonical scientific, DEEP/RELEASE, SRE/restore and independent-review gates pass.
