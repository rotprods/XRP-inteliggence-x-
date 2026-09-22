# H7 Window + Generation Gauntlet — 2026-09-22

Status: **BOUNDED QA HARDENING COMPLETE ON ISOLATED CHILD · NOT PROMOTED**

## Live truth before mutation

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Open PRs observed immediately before mutation: **none**
- Canonical merged SemanticBrain/COS20D/Graphify parent: PR `#13`
- Canonical merged Binance/public-market microstructure parent: PR `#15`
- Latest merged scientific/provenance hardening: PR `#30`
- Existing H7 ingestion parent: `fix/h7-window-resume-law-v1@fe4917c7fc784c917816d037977957e40010d554`
- Parent relation to `main`: **ahead 15 / behind 0**, merge-base exactly `main@a9ad231...`
- Parent exact workflow runs observed: **0 / NOT_RUN**
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- Production: **BLOCKED**
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

The parent branch already contains the existing transport/provenance hardening plus the H7 runner laws:

- adapter provider identity bound to receipt provider;
- raw-response provenance hardening;
- sanitized request identity;
- `[window.start, window.end)` observation law;
- homogeneous parser/ingestion generation bound into the backfill job key;
- receipt parser/ingestion generation required to match the adapter.

This wave did not create a second historical adapter, store, Graphify plane, SemanticBrain, Regime Engine, provider client or market-execution path.

## Gap found

The runner source had implemented the window/generation laws, but the immediately following test commits only added `ingestion_version = "2"` and `parser_version = "2"` to existing adapters. The required adversarial D1/D2 cases were not present as dedicated tests.

That leaves a fail-closed provenance/temporal change insufficiently falsified before any provider-specific adapter can safely build on it.

## Bounded change

Isolation was used to avoid overwriting an active-looking H7 lineage.

- child branch: `test/h7-window-generation-gauntlet-v1`
- parent exact HEAD: `fe4917c7fc784c917816d037977957e40010d554`
- test implementation commit: `bf8dea22a72b2aa21a28c8f226221b6cbe465b0d`
- runtime source changes in this wave: **none**
- added file: `tests/test_h7_window_generation_gauntlet.py`

The gauntlet adds explicit coverage for:

1. `observed_at = start - 1 microsecond` -> reject before persistence;
2. `observed_at = start` -> admissible;
3. `observed_at = end - 1 microsecond` -> admissible;
4. `observed_at = end` -> reject before persistence;
5. `observed_at = end + 1 microsecond` -> reject before persistence;
6. mixed page containing one valid and one out-of-window observation -> whole page rejects before any raw blob, receipt, observation or checkpoint is persisted;
7. stable job identity for unchanged adapter generation;
8. parser-version change -> different backfill job key;
9. ingestion-version change -> different backfill job key;
10. receipt ingestion generation mismatch -> reject before persistence;
11. receipt parser generation mismatch -> reject before persistence;
12. empty/whitespace parser or ingestion generation -> reject before job identity is accepted.

## Code / security / QA review

- CODE REVIEW: **PASS for bounded test-only diff** — one new focused test module; no production source or architecture changed.
- ARCHITECTURE REVIEW: **PASS** — tests target the single canonical `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2` seam.
- SECURITY REVIEW: **PASS** — no credentials, endpoints, mutation authority, order routes, custody, wallet, private keys, withdrawals, leverage or subprocess/network capability added.
- TEMPORAL/PIT REVIEW: **PASS by inspection** — tests enforce the half-open historical window and do not weaken `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` or `INELIGIBLE` semantics.
- SOURCE-INDEPENDENCE REVIEW: **UNCHANGED / PASS** — provider identity/independence thresholds are untouched.
- EXECUTION SAFETY: **PASS** — no trading or decision authority; production remains blocked.
- COLLISION REVIEW: **PASS for observed remote state** — zero open PRs were observed and the child was created from the exact H7 parent rather than mutating the parent ref. Unpushed/local writers cannot be proven absent.

## Verification evidence

No remote CI was triggered and no paid runner was consumed merely to create activity.

Available evidence:

- exact new test module Python syntax compilation using local `compile(...)`: **PASS**;
- GitHub compare child vs parent: **ahead 1 / behind 0** at the implementation checkpoint, with exactly one added test file and no source changes: **PASS**;
- direct container checkout / `git ls-remote`: **BLOCKED** by `Could not resolve host: github.com`;
- local Ruff binary: **NOT_RUN / unavailable** in this runtime;
- focused pytest against exact repository tree: **NOT_RUN** because the exact checkout cannot be materialized in the container runtime;
- full hermetic pytest + branch coverage: **NOT_RUN**;
- strict mypy: **NOT_RUN**;
- Bandit: **NOT_RUN**;
- changed-line coverage: **NOT_RUN**;
- deterministic `release/MANIFEST.sha256`: **NOT_RUN / expected stale** on the H7 candidate lineage;
- exact-head FAST for this child: **NOT_RUN by design**;
- DEEP: **NOT_RUN**;
- RELEASE: **NOT_RUN**.

Latest canonical exact verified feature evidence remains PR #30 head `cf8b736a31647f5695211edf8d36b199bbe989ee`, Verification OS run `35660067501`, FAST job `106532947585`: **PASS for that older exact source tree only**.

## Additional provenance finding for the next wave

A separate content-address integrity issue remains visible in the canonical historical contract and should be handled as its own bounded scope rather than mixed into this QA-only wave:

`FetchReceipt.create()` derives `fetch_id` from the canonical acquisition payload, but `FetchReceipt` has no self-validating `__post_init__`. Direct construction or `dataclasses.replace()` can therefore retain an old syntactically valid `fetch_id` after changing content-bearing receipt fields. `HistoricalEvidenceStoreV2.record_fetch()` detects a collision only when that forged ID is already present; a first insert does not recompute the receipt identity.

This is structurally analogous to the DatasetVersion stale-ID defect hardened in PR #30 and is important because `fetch_id` anchors observation/source provenance.

Do not fix it by weakening collision checks. The safe next scope is to bind every `FetchReceipt` instance to the same canonical payload used by `FetchReceipt.create()`, add direct-construction/`replace()` adversarial tests, and verify first-insert rejection before provider-specific historical ingestion is promoted.

## Resume condition / next action

1. Cold-start again from live `main`, open PRs and H7 branch heads.
2. If the H7 parent has advanced independently, reconcile rather than overwrite.
3. Materialize the exact candidate tree when a canonical-equivalent runner is available.
4. Execute this gauntlet plus the full hermetic/quality suite.
5. Fix only observed failures; never lower thresholds.
6. Regenerate `release/MANIFEST.sha256` from the final exact candidate tree.
7. Spend at most one bounded exact-head FAST run only when the candidate is genuinely promotion-ready.
8. In a separate bounded scope, harden `FetchReceipt` content-address identity before adding a provider-specific historical adapter.
9. Large retained backfill remains **BLOCKED** until source licence/region/retention policy is accepted and recorded.
10. Preserve negative scientific outcomes; production stays **BLOCKED** until all scientific, DEEP/RELEASE, SRE/restore and independent-review gates pass.
