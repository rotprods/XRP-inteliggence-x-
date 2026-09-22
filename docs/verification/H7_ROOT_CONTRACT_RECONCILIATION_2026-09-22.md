# H7 Root Contract Reconciliation — 2026-09-22

Status: **BOUNDED NON-COLLIDING GOVERNANCE HARDENING COMPLETE · NOT PROMOTED**

## Exact live truth at wave start

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical `main`: `a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Canonical main tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed: **none**
- Latest merged PR: `#30`
- Latest previously exact-verified feature head: `cf8b736a31647f5695211edf8d36b199bbe989ee`
- Verification OS evidence for that feature head: run `35660067501`, FAST job `106532947585` — **PASS**
- Exact-current-main CI: **NOT_RUN**; no new remote CI was triggered for this documentation wave.
- Mode: **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**
- Production: **BLOCKED**
- `probability_calibrated=false`
- `decision_authority=false`
- narrative `execution_weight=0.0`

## Collision reconciliation

Two newer remote scopes were treated as active-looking and intentionally not modified:

1. `docs/h7-provider-contract-reconciliation-20260922@760bca2ee67a5014f6438c442b7b9bb21f7aad61`
   - provider/licensing reconciliation checkpoint only;
2. `fix/h7-adapter-provider-provenance-v1@042a135a5cda516ea3f8175bd06de60320f2649f`
   - fail-closed adapter-provider identity guard, focused adversarial test and checkpoint.

This wave used the isolated branch:

`docs/h7-root-contract-reconciliation-20260922`

Start HEAD:

`a9ad23126bcedfc6bec3a338693a3b1dace31236`

Candidate documentation head before this checkpoint:

`2d271176cd2a1c200872848d4c91ce6a83a509ed`

No runtime, adapter, historical-store, microstructure, model, calibration or active provider-contract files were touched.

## Why this wave was selected

`STATE.md` and `HANDOFF.md` already identify the H7 real-data frontier, but root `AGENTS.md` and `GOAL.md` still reflected the August foundation contract and only four horizons. That stale root contract could send a cold-start agent toward duplicate PR #13/#15 architecture, incomplete horizons or weaker continuity rules.

Because provider-contract and historical-adapter work was already active on newer branches, the highest-value safe non-colliding action was to reconcile root operating law with the canonical H3→H12 lineage rather than duplicate those implementation scopes.

## Bounded changes

### `AGENTS.md`

Reconciled the operating contract to require:

- live GitHub cold-start before mutation;
- branch/PR/verification reconciliation;
- single-writer-per-semantic/file-scope behavior;
- explicit treatment of recent no-PR branches as active-looking until reconciled;
- no rebuilding PR #13/#15 SemanticBrain/COS20D/Graphify/microstructure ancestry;
- reuse of the existing `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2` seam;
- `STRICT_REPLAY` / `RECONSTRUCTED_PIT` fail-closed temporal law;
- semantic independent-source requirements;
- immutable DatasetVersion + Feature/Label firewall + purged chronological walk-forward;
- H6-before-H7 and calibration/final-evaluation separation;
- negative scientific outcomes as first-class evidence;
- no new `MEMORY.md` authority without an explicit ADR;
- explicit `PASS / FAIL / BLOCKED / NOT_RUN` work-unit evidence;
- no paid/remote CI merely to create activity;
- three Definitions of Done.

### `GOAL.md`

Reconciled the North Star to the current scientific system:

- seven horizons: `1h`, `4h`, `1d`, `1w`, `1m`, `3m`, `1y`;
- explicit provenance-first chain through Graphify, COS20D, SemanticBrain, microstructure, DatasetVersion, H6/H7, H8-H12;
- real OOS evidence and immutable reconstruction as the success condition;
- current H7 real point-in-time historical evidence frontier;
- large retained backfill governance blocker;
- temporal/source-independence law;
- three Definitions of Done;
- explicit non-execution boundaries and production **BLOCKED**.

## Code / security / QA review

- CODE REVIEW: **PASS** for scope — documentation-only change; no runtime behavior, API, model, network or persistence code changed.
- SECURITY REVIEW: **PASS** — no credentials, keys, secrets, account endpoints, order routes, wallet/custody or leverage surfaces introduced.
- TEMPORAL / PROVENANCE REVIEW: **PASS** — root contract now explicitly preserves `available_at`, `STRICT_REPLAY`, `RECONSTRUCTED_PIT`, independent-source and USD/USDT separation rules.
- COLLISION REVIEW: **PASS for observed remote scopes** — active-looking H7 provider branches were left untouched.
- QA CONTENT REVIEW: **PASS** — resulting `AGENTS.md` and `GOAL.md` were re-read from exact candidate head `2d271176...` and are consistent with `STATE.md`, `HANDOFF.md`, `DECISIONS.md` and the H3→H12 master plan.
- Runtime tests: **NOT_RUN / N/A for documentation-only scope**.
- Ruff / mypy / Bandit: **NOT_RUN / N/A for documentation-only scope**.
- DEEP: **NOT_RUN**.
- RELEASE: **NOT_RUN**.
- Exact branch remote CI: **NOT_RUN** by design; no PR was opened merely to consume CI.

## Known gate debt before promotion

`release/MANIFEST.sha256` still reflects canonical main and is therefore expected stale for the changed `AGENTS.md` and `GOAL.md` files. This branch is intentionally **not merge-ready** until the repository's canonical manifest generator is run against the exact candidate tree and the resulting manifest is verified.

`TASKS.md` also remains historically broad/stale and was deliberately not rewritten in this bounded wave. It should be reconciled separately because replacing the full work breakdown while provider-adapter work is active would expand scope unnecessarily.

## Resume condition

Before promotion of this documentation candidate:

1. re-read live `main`, open PRs and active branch heads;
2. confirm no newer root-contract writer exists;
3. regenerate/check `release/MANIFEST.sha256` from the exact candidate tree;
4. reuse local-equivalent checks if available; use at most one bounded FAST run only if promotion genuinely requires it;
5. merge only with expected-head protection and then verify resulting `main`.

## Next highest-value scientific action

Do not reopen PR #13/#15 or build another historical stack.

The next scientific WorkUnit remains:

1. reconcile/salvage the active provider-contract and adapter-provenance branches;
2. implement one provider-specific `HistoricalAdapterV2` through the canonical historical seam when that scope is free;
3. begin with deterministic/minimal fixtures and fail-closed provider/temporal provenance;
4. only after retention approval, materialize a tiny bounded real sample;
5. freeze an immutable DatasetVersion and execute matched H6 B0-B4 versus H7 regime/analog OOS evaluation;
6. preserve `NO_DEMONSTRATED_REGIME_SKILL` or `INSUFFICIENT_EVIDENCE` if that is what the evidence shows.
