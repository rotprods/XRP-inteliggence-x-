# STATE — 2026-09-22

Repository truth outranks this file. Every agent must cold-start from live GitHub state before mutation.

## Current phase

`H7_REAL_DATA_EVIDENCE_FRONTIER`

## Canonical repository truth at checkpoint

- Repository: `rotprods/XRP-inteliggence-x-`
- Default branch: `main`
- Canonical main before this state refresh: `3e98ad62a12dc12dfeb3dd5978fa087efe1dff58`
- Canonical tree at that merge: `e68932267df72f4c86d106733da0d7741ce88330`
- Latest merged PR: `#30` — DatasetVersion content-address integrity hardening.
- Open PRs observed at reconciliation: **none**.
- Remote branch inventory contains many historical/stale branches; they are salvage-only unless reconciled against current main.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`
- `probability_calibrated=false`
- `decision_authority=false`
- `execution_weight=0.0`

## Canonical integrated lineage

The active main lineage already contains:

- PR #13 — Verification OS + provenance-first COS20D / SemanticBrain foundation.
- PR #15 — Binance XRP spot microstructure + derivatives evidence plane.
- PR #18 — point-in-time historical evidence contract V2.
- PR #20 — historical feature/label firewall + purged chronological walk-forward.
- PR #21 — frozen OOS prediction + calibration evidence core.
- PR #22 — immutable DatasetVersion V1.
- PR #24 — fail-closed OOS ledger content-address integrity.
- PR #25 — executable B0-B4 baseline skill gate.
- PR #26 — PIT regime + historical analog engine V1.
- PR #27 — regime/analog OOS challenger against H6 baselines.
- PR #30 — DatasetVersion identity bound to its canonical payload.

PR #13/#15 are therefore parents of the canonical lineage, not active implementation branches. Do not reopen or rebuild them in parallel.

## Verification truth

Latest exact verified feature head:

- branch: `fix/dataset-version-content-address-integrity-v1`
- exact verified HEAD: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS run: `35660067501`
- FAST job: `106532947585`
- result: **PASS**
- dependency consistency: PASS
- schema reproduction: PASS
- compile: PASS
- Ruff lint: PASS
- Ruff format: PASS
- strict mypy: PASS
- Bandit: PASS
- hermetic tests + branch coverage: PASS
- changed-line coverage 100%: PASS
- repository/source-manifest contracts: PASS
- wheel build: PASS
- runner budget: PASS
- DEEP: NOT_RUN
- RELEASE: NOT_RUN

The merged main commit `3e98ad62a12dc12dfeb3dd5978fa087efe1dff58` has the same tree as the exact verified PR #30 head, but no separate workflow run was observed for that merge SHA. Treat source-tree equivalence as evidence, not as an exact-main-head CI PASS.

## Scientific truth

Engineering mechanics have advanced through H7, but **real XRP predictive skill remains unproven**.

The canonical next scientific requirement is an actual DatasetVersion-backed historical XRP corpus executed through H6/H7. Synthetic fixtures prove mechanics only. A real run may correctly end in `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE`; neither result may be optimized away.

The repository already contains the generic `HistoricalAdapterV2` / `BackfillRunnerV2` / `HistoricalEvidenceStoreV2` substrate, but no provider-specific implementation of `HistoricalAdapterV2` was found on canonical main during this reconciliation. This is the immediate engineering gap before a real corpus can be materialized.

## Governance blocker on large historical backfill

`docs/governance/data_source_licenses.md` currently states that Binance public market data still requires regional-access/current-terms review and that no large historical backfill may be promoted until the selected source terms are recorded and the project owner accepts the retention policy.

Therefore:

- adapter engineering and bounded deterministic fixtures are allowed;
- a large retained historical corpus is **BLOCKED** pending the governance condition above;
- future-fetched data must never be relabeled as `STRICT_REPLAY`;
- USD and USDT quote series must remain semantically distinct unless a versioned basis policy exists.

## H8/H9 salvage status

Historical branches such as `research/scientific-calibration-release-v1`, `research/calibration-promotion-gate-v1` and `research/oos-return-distribution-v1` contain potentially useful calibration/distribution work, but they diverge from current main and include duplicated older upstream files.

They are **SALVAGE_ONLY**:

- never merge wholesale;
- compare file-by-file against current main;
- transplant only genuinely unique semantics after the real-data H6/H7 evidence frontier is resolved;
- preserve `probability_calibrated=false` until artifact-scoped OOS calibration gates actually pass.

## Coordination / collision truth

- Open PRs observed: none.
- No remote branch in the inspected inventory superseded current `main`.
- This does not prove absence of unpushed/local agents.
- Re-read main, open PRs, branch heads and relevant file scopes before every mutation.
- Use exact-head/CAS semantics; a stale write is a blocker, not permission to overwrite.

## Highest-value READY sequence

1. Reconcile current provider terms/licensing/retention status for the selected historical sources.
2. Implement one bounded provider-specific historical adapter on top of the existing `HistoricalAdapterV2` contract; do not create a second backfill architecture.
3. Prefer an independent-source corpus design rather than treating one exchange as scientific truth.
4. Materialize a tiny bounded research sample first and validate receipts, `available_at`, replay classification, provider identity, gaps and DatasetVersion reproducibility.
5. Execute H6 baseline and H7 regime/analog challenger on that real DatasetVersion.
6. Persist the result even when negative or insufficient.
7. Only then reconcile/salvage H8 calibration and H9 distribution/barrier work onto canonical main.
8. DEEP/RELEASE, shadow duration, SRE/restore and independent review remain separate blockers.

## Documentation debt

`GOAL.md`, `TASKS.md` and older handoffs still contain pre-H7/Q1-era state. They must not override live GitHub truth or the H3→H12 master execution plan. Reconcile them deliberately; do not silently rewrite the North Star during an engineering wave.

## Hard boundaries

- no trading or order placement;
- no leverage actions or position sizing;
- no wallet signing, custody, withdrawals, private keys or seeds;
- no CI-generated commits or autonomous repository mutation;
- no paid provider use merely to create evidence;
- no weakening lint/type/security/coverage/provenance/temporal gates;
- no narrative/riddle execution authority;
- production remains **BLOCKED**.
