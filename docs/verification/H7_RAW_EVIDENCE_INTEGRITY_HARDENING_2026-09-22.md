# H7 Raw-Evidence Integrity Hardening — 2026-09-22

Status: **BOUNDED FAIL-CLOSED HARDENING COMPLETE ON EXISTING H7 INGESTION BRANCH · NOT PROMOTED**

## Live truth before mutation

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical main: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Open PRs observed: **none**.
- PR #13 and PR #15: **merged**; their SemanticBrain/COS20D/Graphify and Binance/public-market microstructure lineages are canonical and were not rebuilt.
- Existing H7 ingestion candidate: `fix/h7-raw-evidence-transport-v1@40b774e545ad5824b3d350138bdf40ad356d3dd8`.
- Existing provider-provenance branch was already functionally absorbed into that candidate.
- Provider-governance, root-contract and Kraken-design branches were treated as separate active-looking scopes and left untouched.
- Latest prior exact verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501`, FAST job `106532947585` — **PASS for that older tree only**.
- Current-main exact FAST: **NOT_RUN**.
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`, `probability_calibrated=false`, `decision_authority=false`, narrative `execution_weight=0.0`.

## Defect hardened

`RawJsonEvidence` carried exact raw bytes, a SHA-256 digest, latency and transport-boundary fetch time, but the evidence object itself did not fail closed if later constructed with inconsistent metadata. Provenance objects at this seam should be self-validating before a provider-specific historical adapter can use them to create `FetchReceipt` records.

## Bounded change

Implementation head before this checkpoint:

`3b3794833ea4449751f2fff65c43fe83d3c9369d`

Changed only the existing H7 transport lineage:

- `src/xrp_regime_engine/providers/base.py`
  - `RawJsonEvidence.__post_init__` now rejects negative latency;
  - rejects empty raw evidence;
  - recomputes SHA-256 from the exact raw bytes and rejects digest mismatch;
  - rejects naive `fetched_at` timestamps;
  - normalizes aware timestamps to UTC.
- `tests/test_provider_base.py`
  - adds focused regression coverage for forged digest, naive fetch time, negative latency and empty raw evidence;
  - verifies non-UTC aware timestamps normalize to UTC.

No endpoint, credential, order, account, funding, wallet, custody, withdrawal, leverage or execution capability was added. No historical architecture, model path, source-weight threshold or temporal eligibility law was changed.

## Code / security / QA review

- CODE REVIEW: **PASS** — one self-validation method plus focused tests; backward-compatible request surface retained.
- ARCHITECTURE REVIEW: **PASS** — hardens the existing `MarketDataProvider -> RawJsonEvidence -> HistoricalAdapterV2` seam; no parallel transport or backfill system.
- SECURITY REVIEW: **PASS** — no new network route or secret exposure; fail-closed validation reduces provenance-tampering risk.
- PROVENANCE REVIEW: **PASS** — raw bytes and advertised digest cannot diverge inside `RawJsonEvidence`; transport time must be timezone-aware and normalized.
- TEMPORAL REVIEW: **PASS** — this does not alter `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` or `INELIGIBLE` semantics.
- SOURCE-INDEPENDENCE REVIEW: **PASS** — provider identities and independent-source requirements are unchanged.
- EXECUTION SAFETY: **PASS** — READ_ONLY / SHADOW_ONLY / NON_EXECUTION preserved.
- COLLISION REVIEW: **PASS for observed remote state** — the existing H7 ingestion branch remained the claimed lineage; disjoint provider-governance/root-contract/Kraken-design branches were not modified.

## Verification evidence

Remote CI was not triggered merely to create activity.

Focused local-equivalent invariant execution:

- valid evidence with non-UTC aware timestamp normalizes to UTC: **PASS**;
- forged `payload_sha256` vs exact raw bytes: **PASS, rejected**;
- naive `fetched_at`: **PASS, rejected**;
- negative latency: **PASS, rejected**;
- empty raw payload: **PASS, rejected**.

Unavailable in this runtime:

- direct repository clone/materialization: **BLOCKED** by DNS resolution for `github.com`;
- full pytest: **NOT_RUN**;
- Ruff: **NOT_RUN**;
- strict mypy: **NOT_RUN**;
- Bandit: **NOT_RUN**;
- changed-line coverage: **NOT_RUN**;
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / expected stale**;
- exact candidate FAST: **NOT_RUN by design**;
- DEEP: **NOT_RUN**;
- RELEASE: **NOT_RUN**.

This candidate is **not merge-ready** and no stronger verification claim is made.

## Blockers and resume condition

`H7_PROVIDER_INGESTION_SEAM_PROMOTION = BLOCKED` until the exact combined candidate can be materialized on a canonical runner, the manifest is regenerated, the full hermetic/quality suite passes, changed-line coverage remains 100%, and at most one bounded exact-head FAST run confirms the real promotion candidate.

`LARGE_RETAINED_BACKFILL = BLOCKED` independently until provider-specific retention/region/derived-use policy is accepted and recorded. Future-fetched retrospective evidence must remain `RECONSTRUCTED_PIT` with a valid reconstruction basis or `INELIGIBLE`; it must never be relabelled `STRICT_REPLAY`.

## Next action

1. Cold-start from live GitHub again; do not assume this checkpoint is still latest.
2. If this exact H7 ingestion branch is still unclaimed by another writer, materialize/verify it on an environment with repository access and regenerate the deterministic manifest rather than adding more features.
3. Reconcile provider-governance/root-contract documentation separately; do not wholesale-merge stale state.
4. Only after the ingestion seam is canonically green, implement one deterministic provider-specific `HistoricalAdapterV2` parser/adapter, with Kraken USD as the documented independent-source candidate and minimal/synthetic fixtures first.
5. Preserve negative scientific outcomes and keep production **BLOCKED** until all canonical scientific, DEEP/RELEASE, restore/SRE and independent-review gates pass.
