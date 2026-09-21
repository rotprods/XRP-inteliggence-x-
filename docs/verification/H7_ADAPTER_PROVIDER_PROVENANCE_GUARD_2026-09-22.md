# H7 Historical Adapter Provider Provenance Guard — 2026-09-22

Status: **BOUNDED FAIL-CLOSED HARDENING COMPLETE ON ISOLATED BRANCH · NOT PROMOTED**

## Exact live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical base: `main@a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Base tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed immediately before mutation: **none**
- Latest merged PR: `#30`
- Existing active-looking remote scope observed: `docs/h7-provider-contract-reconciliation-20260922@760bca2ee67a5014f6438c442b7b9bb21f7aad61`
- That branch changes only `docs/verification/H7_PROVIDER_CONTRACT_RECONCILIATION_2026-09-22.md`; this wave intentionally avoided that file/scope.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- Production: **BLOCKED**
- `probability_calibrated=false`
- `decision_authority=false`
- `execution_weight=0.0`

## Defect found

`BackfillRunnerV2.job_key()` binds a run to `adapter.provider`, but `_validate_page()` previously verified only that each observation matched the page receipt. It did **not** verify that `page.receipt.provider == adapter.provider`.

A buggy or adversarial adapter could therefore claim one provider identity in its job key (for example `kraken`) while returning a self-consistent receipt and observations from another provider (for example `coinbase`). The runner would accept and persist that page under the claimed adapter run.

That creates a provenance/independence failure: provider attribution can diverge from the identity used to define the backfill job, contaminating provider-universe accounting and any later independent-source evidence gate.

## Bounded change

Branch: `fix/h7-adapter-provider-provenance-v1`

Pre-checkpoint implementation head: `8aa127350efdd5323d6642a23d167fc897314ccd`

Files changed before this checkpoint:

- `src/xrp_regime_engine/historical_backfill_v2.py`
  - fail closed when `page.receipt.provider != adapter.provider` before any raw payload, observation, partition or checkpoint persistence;
- `tests/test_historical_adapter_provider_binding.py`
  - adversarial adapter claims `kraken` while returning a valid `coinbase` receipt/observation pair;
  - asserts the run is rejected and raw blobs, fetch receipts, observations and checkpoints remain empty.

No provider-specific adapter, second historical architecture, model logic, source weighting, trading route or network capability was added.

## Review

- CODE REVIEW: **PASS** — two-line runtime guard plus one focused adversarial test; no unrelated source changes.
- SECURITY REVIEW: **PASS** — no credentials, secrets, order routes, account mutation, wallet/custody, leverage, subprocess or new network surface.
- PROVENANCE REVIEW: **PASS** — adapter identity is now bound to receipt provider before persistence.
- SOURCE-INDEPENDENCE REVIEW: **PASS** — prevents one provider's data being accepted under another provider's adapter identity.
- TEMPORAL REVIEW: **PASS** — `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT` and future-information semantics are unchanged.
- COLLISION REVIEW: **PASS for observed remote scopes** — open PR count was zero; the provider-contract reconciliation branch touched a disjoint documentation file. Absence of unpushed/local writers cannot be proven.

## Verification evidence

Local-equivalent evidence was run without paid remote CI:

- Python syntax compile of modified `historical_backfill_v2.py`: **PASS**
- Python syntax compile of the new adversarial test: **PASS**
- isolated execution of the added `_validate_page()` provider-mismatch guard: **PASS** (mismatch raises before persistence path)
- full repository pytest: **NOT_RUN** — repository checkout could not be materialized in the runtime because external DNS/network access is unavailable
- Ruff: **NOT_RUN**
- strict mypy: **NOT_RUN**
- Bandit: **NOT_RUN**
- deterministic source manifest: **NOT_RUN / expected stale** because source/tests/checkpoint changed
- exact branch FAST CI: **NOT_RUN** by design; no PR was opened merely to consume CI
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**

Latest previously canonical exact-head verification remains PR #30 feature head `cf8b736a31647f5695211edf8d36b199bbe989ee`, run `35660067501`, FAST job `106532947585` — **PASS** for that older source tree only.

## Promotion blocker / resume condition

This branch is intentionally **not** merge-ready yet.

Before promotion:

1. re-read live `main`, open PRs and branch scopes;
2. reconcile with any provider-adapter implementation branch that may appear;
3. run the repository's canonical manifest generator/check and regenerate `release/MANIFEST.sha256` only from the exact candidate tree;
4. run the focused adversarial test plus the full hermetic suite locally if an equivalent checkout is available;
5. only then, if a PR is warranted, use one bounded FAST run and fix the first real failing gate without lowering thresholds;
6. preserve `READ_ONLY / SHADOW_ONLY / NON_EXECUTION` and production **BLOCKED**.

## Next highest-value non-colliding action

Do **not** duplicate the already-observed provider-contract reconciliation work. The next scientific frontier remains one provider-specific implementation of the existing `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2` seam, preferably after reconciling the active provider-contract branch and current licensing/retention constraints. Any such adapter must inherit this provider-identity guard and must classify retrospective future-fetched data as `RECONSTRUCTED_PIT` or `INELIGIBLE`, never silently as `STRICT_REPLAY`.
