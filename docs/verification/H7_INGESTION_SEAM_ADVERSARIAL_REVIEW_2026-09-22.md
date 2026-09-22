# H7 Ingestion Seam Adversarial Review — 2026-09-22

Status: **READ-ONLY ADVERSARIAL REVIEW COMPLETE · PROMOTION BLOCKED PENDING CORRECTNESS GAPS**

## Exact live truth at review start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- Latest canonical exact verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS run/job for that older tree: `35660067501` / `106532947585` — **PASS**
- Exact-current-main workflow evidence: **NOT_RUN**
- Active-looking H7 ingestion candidate: `fix/h7-raw-evidence-transport-v1@4a2dac81944fb0c7101e1bfe2a3be68a9cd58843`
- Candidate relation to main: **ahead by 9, behind by 0**
- Candidate changed files vs main: 6 total — 2 runtime files, 2 tests, 2 verification docs
- Candidate exact-head workflow evidence: **NOT_RUN**
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision decision

The H7 ingestion branch was updated at `2026-09-22T03:36:29Z` and is therefore treated as an active writer scope. This review does **not** modify that branch, `historical_backfill_v2.py`, `providers/base.py`, its tests, provider-governance files, root-contract files, or the Kraken adapter design branch.

The only repository mutation from this wave is this isolated review/checkpoint document on `docs/h7-ingestion-seam-adversarial-review-20260922`, created from the exact canonical main above. No PR was opened and no remote CI was triggered merely to create activity.

## Scope reviewed

Current H7 candidate path:

`MarketDataProvider -> RawJsonEvidence -> HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2 -> DurableManifest -> DatasetVersion`

The review re-read:

- `src/xrp_regime_engine/providers/base.py` at `4a2dac81944fb0c7101e1bfe2a3be68a9cd58843`;
- `src/xrp_regime_engine/historical_backfill_v2.py` at that same head;
- `tests/test_provider_base.py` at that same head;
- canonical `historical_contract.py` and `tests/test_historical_backfill_v2.py` from `main@a9ad231...`;
- the H7 raw-evidence, provider-provenance, provider-contract and Kraken adapter checkpoints.

## Findings

### F1 — Parsed payload is not cryptographically bound to raw payload

Severity: **HIGH for provenance correctness before provider-adapter promotion**

`RawJsonEvidence.__post_init__` recomputes `SHA256(raw_payload)`, validates latency and timezone-awareness, but it does **not** verify that `payload` is the JSON value encoded by `raw_payload`.

The hardened transport itself constructs them consistently, but the dataclass is a reusable provenance object and can be instantiated directly. A buggy/adversarial caller can therefore construct:

- valid non-empty raw bytes;
- a matching digest for those bytes;
- a different parsed `payload` object;
- otherwise valid metadata.

That object passes the current self-validation contract while allowing observations to be derived from content different from the bytes that the receipt/digest proves.

Required repair before treating `RawJsonEvidence` as self-validating:

1. parse `raw_payload` with the same fail-closed JSON-root rule;
2. require semantic equality with `payload`, or stop accepting externally supplied `payload` and derive it from raw bytes in one constructor/factory;
3. add adversarial tests for raw/payload disagreement, duplicate-key policy if relevant, malformed encoding and non-object/list roots;
4. preserve `repr=False` for both parsed and raw provider content.

Promotion status for the current H7 ingestion candidate: **BLOCKED** until this is explicitly resolved or an ADR narrows the object contract so direct construction cannot claim self-validating provenance.

### F2 — Transport evidence still does not bind request identity to the exact response

Severity: **HIGH for FetchReceipt provenance**

The current `RawJsonEvidence` carries parsed JSON, exact raw bytes, response digest, latency and transport-boundary `fetched_at`, but it does not carry the sanitized canonical request URI or a canonical request fingerprint derived at the transport boundary.

A future provider-specific adapter must therefore reconstruct `FetchReceipt.canonical_uri` and `request_fingerprint` separately from the evidence object. That leaves a split-brain seam where the response bytes/time are proven by one path while request identity is recomputed by another.

This is weaker than the already-recorded Kraken design contract, which called for the shared raw-evidence primitive to expose a sanitized canonical request URI/fingerprint input.

Required resolution before first real provider adapter promotion:

- expose a transport-derived sanitized request descriptor/fingerprint input alongside `RawJsonEvidence`, or
- introduce an immutable request+response evidence envelope produced only by the hardened transport;
- never include credentials/secrets in that identity;
- preserve host/method/DNS/redirect/size/retry controls;
- add tests proving semantically identical requests produce stable identities and that changed query semantics change the fingerprint.

No second HTTP client should be introduced to solve this.

### F3 — BackfillRunner does not enforce the requested historical window

Severity: **HIGH before real corpus materialization**

`BackfillRunnerV2.run(adapter, window)` passes the window to the adapter, but `_validate_page(adapter, page)` does not receive the window and does not verify that persisted observations are inside it.

The canonical tests validate the `BackfillWindowV2` shape and many receipt/observation provenance invariants, but no runner-level adversarial test currently rejects an adapter that returns observations before `window.start` or at/after `window.end`.

A buggy/adversarial adapter can therefore persist observations outside the requested job window under a job key that cryptographically claims that window.

Required fail-closed repair before real provider data:

- validate every observation against the canonical window boundary before `record_fetch`/partition persistence;
- define the interval law explicitly, preferably `[start, end)` for event/candle timestamps unless the dataset contract requires otherwise;
- add tests for before-start, exactly-start, immediately-before-end, exactly-end and after-end;
- for candle datasets, separately define whether `observed_at` means open time or close time and reject incomplete/current candles at the adapter contract.

This is a pre-existing canonical seam issue, not introduced by the current raw-transport branch. It should be converged into the same H7 ingestion lineage only after re-checking writer ownership; do not open a competing historical architecture.

### F4 — Resume identity can mix adapter/parser generations unless version law is explicit

Severity: **MEDIUM / DECISION REQUIRED**

`BackfillRunnerV2.job_key()` currently binds provider, dataset, schema version and requested window. Individual `FetchReceipt` records carry ingestion and parser versions, but those versions are not part of the backfill job key.

If an interrupted job is resumed after adapter/parser behavior changes while `schema_version` remains unchanged, one logical backfill job can span multiple parser/ingestion generations.

This may be acceptable only if the manifest/DatasetVersion contract explicitly permits heterogeneous receipt versions and records them as part of identity. Otherwise the job key or resume gate should bind an adapter/parser version.

Before real corpus promotion, decide and test one law:

- homogeneous parser/ingestion generation per backfill job, fail closed on resume mismatch; or
- explicitly heterogeneous jobs with manifest-level version inventory and deterministic identity.

Do not leave the behavior implicit.

## Positive findings

- Candidate is a direct descendant of current main and contains no unrelated architecture in the compared diff.
- Provider identity is now checked before observation/partition/checkpoint persistence.
- Raw bytes are size-bounded, response digest is recomputed, redirects remain disabled, `trust_env=False` remains in place and public-address DNS checks are preserved.
- `RawJsonEvidence` now rejects negative latency, empty bytes, forged digests and naive fetch times and normalizes aware timestamps to UTC.
- No trading/order/account/custody/wallet/private-key/leverage capability was added.
- `STRICT_REPLAY`, `RECONSTRUCTED_PIT`, `INELIGIBLE`, independent-source semantics and narrative `execution_weight=0.0` were not weakened.
- No paid provider call or paid CI was used in this review.

## Code / security / QA verdict

- CODE REVIEW: **FAIL for promotion, PASS for direction** — architecture convergence is correct, but F1/F2 must be resolved before this becomes the provenance substrate for a provider-specific adapter.
- SECURITY REVIEW: **PASS for the reviewed diff** — no new execution/credential surface was found; existing transport hardening remains intact. DNS validation is still a pre-connect check rather than connection pinning, but that is pre-existing transport debt and was not widened here.
- TEMPORAL / PIT REVIEW: **BLOCKED before real corpus** — F3 means the runner does not yet independently guarantee its own declared window.
- PROVENANCE REVIEW: **BLOCKED** — F1 and F2 leave response/content and request/response identity gaps.
- SOURCE-INDEPENDENCE REVIEW: **PASS for current changes** — provider identity guard strengthens, rather than weakens, source accounting.
- QA: static/adversarial review **PASS as review evidence**; exact candidate full pytest/Ruff/mypy/Bandit/coverage/manifest/wheel remain **NOT_RUN**.
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**
- production: **BLOCKED**

## Next highest-value action

Do not add Kraken/Binance/Coinbase provider-specific historical code yet.

1. Cold-start from live GitHub again and confirm `fix/h7-raw-evidence-transport-v1` has not moved and has no other active writer.
2. Converge F1 and F2 on that existing ingestion lineage, not a new transport architecture.
3. Converge F3 into the same historical-ingestion lineage only after confirming file-scope ownership of `historical_backfill_v2.py`.
4. Decide F4 explicitly and encode it in tests/manifest law.
5. Regenerate deterministic `release/MANIFEST.sha256` only from the exact final candidate tree.
6. Run focused tests + canonical local-equivalent quality suite when a materialized checkout is available.
7. Use at most one bounded exact-head FAST run only when the candidate is genuinely promotion-ready; fix the first real failure without weakening a gate.
8. Only after that, implement one deterministic provider-specific `HistoricalAdapterV2` parser/adapter, with minimal/synthetic fixtures first and no large retained corpus until governance approval.
9. Preserve real negative outcomes (`NO_DEMONSTRATED_REGIME_SKILL`, `INSUFFICIENT_EVIDENCE`) and keep production **BLOCKED** until all scientific, DEEP/RELEASE, restore/SRE and independent-review gates pass.

## Durable handoff

This checkpoint intentionally does not claim ownership of the active H7 ingestion source files. Its purpose is to stop a premature provider-adapter wave from building on an evidence seam that is close, but not yet provenance-complete.
