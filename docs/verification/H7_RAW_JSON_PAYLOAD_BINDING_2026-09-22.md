# H7 Raw JSON Payload Binding — 2026-09-22

Status: **BOUNDED PROVENANCE HARDENING COMPLETE ON EXISTING H7 INGESTION LINEAGE · NOT PROMOTED**

## Live truth before mutation

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed immediately before this wave: **none**.
- Existing candidate branch: `fix/h7-raw-evidence-transport-v1@4a2dac81944fb0c7101e1bfe2a3be68a9cd58843`.
- PR #13 / #15 and the H6/H7 lineage are already merged into canonical main; no parallel SemanticBrain, COS20D, Graphify, microstructure, historical-store, walk-forward, baseline or regime architecture was created.
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Defect found

The existing `RawJsonEvidence` guard bound `payload_sha256` to the exact `raw_payload` bytes, but direct construction could still supply a parsed `payload` that did not correspond to those bytes. A later historical adapter could therefore consume a parsed object whose provenance digest truthfully described different raw evidence.

That is a provenance split-brain at the transport-to-historical-adapter boundary. It does not require network compromise; a buggy or adversarial caller constructing `RawJsonEvidence` directly was sufficient.

## Bounded change

Existing branch only; no new branch or PR.

Implementation commit:

- `e11270d985e7ead43ebdaaa2dfefbd6e7d2d67d5` — `RawJsonEvidence.__post_init__` now reparses `raw_payload`, requires a JSON object/array root, and requires structural equality between the reparsed value and `payload`.

Focused tests:

- `ea8fb748203abf11e6620825fbe2e6cb755046c3` — rejects a self-consistent raw digest paired with a different parsed payload.
- `a967da53e4ab6b4f7fa7b8029158b72c4b37f046` — covers malformed JSON and scalar JSON-root fail-closed branches so the new defensive lines are not intentionally left unexercised.

No endpoint, credential, API key, private route, order route, account mutation, wallet/custody, withdrawal, leverage, position sizing, paid API, model-authority or narrative-weight capability was added.

## Review

- CODE REVIEW: **PASS** — the change is confined to `RawJsonEvidence` self-validation plus focused regression coverage.
- ARCHITECTURE REVIEW: **PASS** — it hardens the existing `MarketDataProvider -> RawJsonEvidence -> HistoricalAdapterV2` seam and introduces no second HTTP/backfill architecture.
- SECURITY REVIEW: **PASS** — no capability expansion; malformed/forged evidence is rejected earlier.
- PROVENANCE REVIEW: **PASS** — raw bytes, SHA-256 and parsed JSON are now mutually bound inside the evidence object.
- TEMPORAL REVIEW: **PASS** — `fetched_at`, `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` and `INELIGIBLE` semantics are unchanged.
- SOURCE-INDEPENDENCE REVIEW: **PASS** — provider identities and independent-source requirements are unchanged.
- EXECUTION SAFETY: **PASS** — no trading/execution/custody/leverage authority exists in this scope.

## Verification evidence

Focused local-equivalent invariant execution in the available runtime:

- valid object/array raw JSON + matching parsed payload: **PASS**;
- parsed payload differing from exact raw JSON: **PASS, rejected**;
- malformed raw JSON with a self-consistent SHA-256: **PASS, rejected**;
- scalar raw JSON root with a self-consistent SHA-256: **PASS, rejected**;
- aware non-UTC fetch time normalization to UTC: **PASS**.

Canonical full-repository verification is not available in this runtime because direct repository materialization previously failed DNS resolution for `github.com`. Therefore:

- full pytest/hermetic suite: **NOT_RUN**;
- Ruff lint/format: **NOT_RUN**;
- strict mypy: **NOT_RUN**;
- Bandit: **NOT_RUN**;
- changed-line coverage: **NOT_RUN**;
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / expected stale** after these source/test/checkpoint mutations;
- exact candidate FAST: **NOT_RUN by design** — no paid/remote CI was triggered merely to discover the already-known stale-manifest gate;
- DEEP: **NOT_RUN**;
- RELEASE: **NOT_RUN**.

Latest previously canonical exact-head verification remains PR #30 feature head `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501`, FAST job `106532947585` — **PASS for that older tree only**.

## Promotion state

`H7_PROVIDER_INGESTION_SEAM_PROMOTION = BLOCKED`.

Resume only when a complete canonical checkout/runner can:

1. re-read live main/open PRs/branch ownership;
2. run the focused provider tests and full hermetic suite;
3. pass Ruff, strict mypy and Bandit;
4. demonstrate canonical 100% changed-line coverage;
5. regenerate `release/MANIFEST.sha256` from the exact candidate tree and pass repository/source-manifest verification;
6. use at most one bounded exact-head FAST run on a real promotion candidate and repair causes rather than lower gates.

`LARGE_RETAINED_BACKFILL` remains independently **BLOCKED** pending the provider-governance retention/region/derived-use acceptance. Retrospective future-fetched evidence must remain `RECONSTRUCTED_PIT` with a valid reconstruction basis or `INELIGIBLE`; it must never be relabelled `STRICT_REPLAY`.

## Next action

Do not add another transport or historical architecture. First converge/verify this existing ingestion candidate and the disjoint provider-governance contract. Once the ingestion seam is canonically green and retention rules permit a bounded sample, implement one deterministic provider-specific `HistoricalAdapterV2` parser/adapter (Kraken USD is the currently documented independent-source candidate), build a tiny immutable DatasetVersion, and run matched H6 B0-B4 versus H7 regime/analog OOS evidence. Preserve `NO_DEMONSTRATED_REGIME_SKILL` and `INSUFFICIENT_EVIDENCE` exactly if observed. Production remains **BLOCKED**.
