# HANDOFF — XRP Intelligence OS Live Truth

Date: 2026-09-22

This handoff is a recovery pointer, not authority over live repository state. Cold-start from GitHub before any mutation.

## Identity

- Repository: `rotprods/XRP-inteliggence-x-`
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- Main observed before this documentation refresh: `3e98ad62a12dc12dfeb3dd5978fa087efe1dff58`
- Main tree at that checkpoint: `e68932267df72f4c86d106733da0d7741ce88330`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- Production: **BLOCKED**
- Calibrated probability claim: **FALSE**
- Decision authority: **FALSE**
- Execution weight: **0.0**

## Cold-start sequence

1. Fetch exact `main` HEAD and tree.
2. List open PRs and current remote branch heads.
3. Inspect latest verification runs for the candidate exact head.
4. Read `AGENTS.md`, `GOAL.md`, `STATE.md`, `TASKS.md`, `DECISIONS.md` and `CODEX.md`, but treat live GitHub truth as higher authority when state documents are stale.
5. Read `docs/research/XRP_PHASE_H3_H12_MASTER_EXECUTION_PLAN.md`.
6. Inspect relevant durable verification checkpoints before claiming a scope.
7. Confirm no active writer owns the same semantic/file scope.
8. Use expected-head/CAS semantics for every mutation; never overwrite a newer writer.
9. Do not trigger remote CI merely to create activity.
10. Persist PASS / FAIL / BLOCKED / NOT_RUN explicitly.

## Canonical lineage already merged

- #13 Verification OS + COS20D / SemanticBrain.
- #15 Binance/public-market microstructure and derivatives evidence.
- #18 PIT historical evidence V2.
- #20 feature/label firewall + purged walk-forward.
- #21 frozen OOS + calibration evidence core.
- #22 DatasetVersion V1.
- #24 OOS ledger integrity.
- #25 B0-B4 baseline skill gate.
- #26 PIT regime + historical analog engine.
- #27 regime/analog OOS falsification harness.
- #30 DatasetVersion canonical-payload integrity.

Do not restart #13/#15 or create parallel SemanticBrain, Graphify, microstructure, historical-store, walk-forward, baseline or regime architectures.

## Latest verification evidence

PR #30 exact verified head:

`cf8b736a31647f5695211edf8d36b199bbe989ee`

Verification OS:

- run `35660067501`
- FAST job `106532947585`
- compile: PASS
- dependency consistency: PASS
- schema reproduction: PASS
- Ruff lint/format: PASS
- strict mypy: PASS
- Bandit: PASS
- hermetic tests + branch coverage: PASS
- changed-line coverage 100%: PASS
- repository/source-manifest contracts: PASS
- wheel: PASS
- runner budget: PASS
- DEEP: NOT_RUN
- RELEASE: NOT_RUN

The merge commit observed on main had the same source tree as that verified branch head, but no separate workflow run was found for the merge SHA. Do not relabel that as exact-main-head CI PASS.

## Current scientific frontier

H7 mechanics exist and are verified as engineering artifacts. **Real XRP regime skill is not demonstrated yet.**

The next scientific proof requires an actual immutable `DatasetVersion` built from point-in-time historical evidence and then run through:

`H6 baselines → H7 regime/analog challenger → matched OOS comparison`

Valid outcomes include:

- `ELIGIBLE_REGIME_CHALLENGER`
- `NO_DEMONSTRATED_REGIME_SKILL`
- `INSUFFICIENT_EVIDENCE`

Negative evidence must be preserved.

## Immediate gap discovered

Canonical main has a generic historical ingestion substrate:

- `HistoricalAdapterV2`
- `BackfillRunnerV2`
- `HistoricalEvidenceStoreV2`
- durable receipts/manifests/checkpoints

but no provider-specific `HistoricalAdapterV2` implementation was found in the current tree during reconciliation.

The next bounded engineering WorkUnit should therefore extend this existing adapter seam, not create a second backfill system.

## Governance blocker / resume condition

Large historical retention/backfill is currently **BLOCKED** by the repository's own data-source licence register until the selected provider's current terms/regional restrictions are recorded and the project owner accepts the retention policy.

Resume real-corpus promotion when that condition is satisfied.

Before then, safe work includes:

- provider contract research;
- adapter implementation against public read-only endpoints;
- deterministic fixtures;
- tiny bounded smoke samples where permitted;
- provenance/temporal/security tests;
- independent-source design.

Never call a future-fetched source `STRICT_REPLAY`.

## Stale branch salvage

`research/scientific-calibration-release-v1`, `research/calibration-promotion-gate-v1` and `research/oos-return-distribution-v1` are divergent historical branches. They contain potentially useful H8/H9 semantics, including calibration promotion and return-distribution layers, but must be treated as **SALVAGE_ONLY**.

When H8 is ready:

1. compare each donor file with current main;
2. transplant only unique semantics;
3. rebind to canonical DatasetVersion/OOS identities;
4. regenerate manifest;
5. run one bounded exact-head FAST;
6. preserve `probability_calibrated=false` unless real OOS sample/calibration gates pass.

## Known documentation debt

At this checkpoint, root `STATE.md` and this handoff are being refreshed because prior root state still described August Q1. `GOAL.md` and `TASKS.md` also contain older scope/status and require a separate deliberate reconciliation. They must not override current live GitHub state or the H3→H12 plan.

## Hard boundaries

No trading, orders, leverage actions, position sizing, account mutation, custody, wallet signing, withdrawals, private keys or seeds.

No gate weakening.

Narrative/riddle evidence remains `execution_weight=0.0`.

Production remains **BLOCKED** until all canonical engineering, scientific and operational gates pass.
