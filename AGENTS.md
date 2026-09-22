# AGENTS — XRP Intelligence OS Operating Contract

This repository is a **READ_ONLY / SHADOW_ONLY / NON_EXECUTION** research system. Repository truth outranks chat memory and stale handoffs.

## 1. Mandatory cold start

Before any mutation, every agent must:

1. Fetch the exact `main` HEAD and tree.
2. List open PRs and current remote branch heads.
3. Inspect the latest verification evidence for the candidate lineage.
4. Read `GOAL.md`, `STATE.md`, `TASKS.md`, `DECISIONS.md`, `CODEX.md`, `HANDOFF.md` and `docs/research/XRP_PHASE_H3_H12_MASTER_EXECUTION_PLAN.md`.
5. Reconcile stale documentation against live GitHub truth; never let a handoff override a newer repository state.
6. Inspect active-looking branch scopes before claiming files or semantics.
7. Refuse to overwrite a newer writer. Use exact-head / CAS semantics wherever the tool supports them.

## 2. Authority and continuity

- GitHub repository state is engineering truth.
- `STATE.md` and `HANDOFF.md` are recovery pointers, not substitutes for live reconciliation.
- `GOAL.md` defines the North Star and hard boundaries.
- `DECISIONS.md` contains durable architectural law unless explicitly superseded.
- Generated graphs, indexes, embeddings, caches and memory projections are reconstructible derivatives, not authority.
- Do not create a second `MEMORY.md` authority by default. A new memory surface requires an explicit ADR defining scope, precedence and reconstruction semantics.

## 3. Concurrency / anti-collision law

- Single writer per semantic/file scope.
- Prefer completing or hardening the canonical lineage over creating parallel architectures.
- PR #13/#15 SemanticBrain/COS20D/Graphify and microstructure work is already ancestry of `main`; do not reopen or rebuild it in parallel.
- Historical ingestion must extend `HistoricalAdapterV2 -> BackfillRunnerV2 -> HistoricalEvidenceStoreV2`; do not create another backfill stack.
- Treat recent unmerged remote branches as active-looking until reconciled. A branch with no PR is not automatically abandoned.
- Stale historical branches are `SALVAGE_ONLY`: transplant unique semantics file-by-file; never merge wholesale without reconciliation.
- If collision risk cannot be resolved, work on a disjoint READY scope and record the blocker.

## 4. Temporal / provenance law

Every external datum must preserve, where applicable:

- provider and source identity;
- `observed_at`;
- `available_at`;
- `fetched_at`;
- freshness / quality state;
- immutable source digest or receipt lineage.

Never silently substitute stale or future-fetched data for point-in-time evidence.

Retrospective data fetched after a historical prediction time may be `RECONSTRUCTED_PIT` only when reconstruction is defensible and provenance-complete; otherwise it is `INELIGIBLE`. It must never be relabelled as `STRICT_REPLAY`.

Independent-source requirements are semantic, not cosmetic: two feeds sharing the same upstream or one exchange represented through two endpoints do not automatically constitute independent evidence. `XRP_USD` and `XRP_USDT` remain distinct unless a versioned basis policy explicitly maps them.

## 5. Scientific law

Preserve the distinction between observation, inference, scenario and recommendation.

Hard requirements:

- immutable `DatasetVersion` before model training;
- physically/logically separate future labels;
- purged chronological walk-forward with horizon-specific embargo;
- no random split;
- OOS predictions frozen before outcome resolution;
- H6 baselines before complex challengers;
- H7 analog/regime retrieval restricted to states strictly earlier than `prediction_time`;
- fitting, calibration and final evaluation separated;
- negative outcomes such as `NO_DEMONSTRATED_REGIME_SKILL` and `INSUFFICIENT_EVIDENCE` preserved rather than optimized away;
- raw scores are not calibrated probabilities;
- `probability_calibrated=false` until artifact-scoped sample and calibration gates pass.

Narrative, riddles, numerology and unsupported causal stories remain research context only and have `execution_weight=0.0`.

## 6. Engineering / security / QA law

- Add or update tests for every scoring, schema, adapter, provenance, temporal or persistence change.
- Prefer standard library or existing dependencies before adding packages.
- Keep credentials, private keys, seeds, account tokens and secrets out of source, logs, fixtures, screenshots, docs and artifacts.
- No order placement, leverage action, position sizing, account mutation, wallet signing, custody, withdrawals or private-key handling.
- Public market connectors are read-only.
- CI verifies; it never authors implementation or autonomously mutates repository state.
- Do not weaken lint, format, type, security, coverage, provenance, temporal, reproducibility or source-manifest gates to make a run green.
- Do not consume remote/paid CI merely to create activity. Reuse exact-head evidence or local-equivalent evidence where valid.
- Never convert `NOT_RUN` or `BLOCKED` into `PASS`.

## 7. Definition of Done

A work unit is not globally done merely because code exists.

**ENGINEERING_DONE** requires implementation, review, tests, exact candidate identity and reproducible artifacts/gates appropriate to the scope.

**SCIENTIFIC_DONE** requires real OOS evidence, leakage audit, baselines, falsification, calibration/sample adequacy where relevant.

**OPERATIONAL_DONE** requires observability, immutable evidence, reproducibility, rollback, security and release gates.

Production remains **BLOCKED** until all required dimensions pass canonically.

## 8. Work-unit protocol

For every bounded wave record:

- work-unit ID / goal;
- scope and dependencies;
- branch and start HEAD;
- expected outputs;
- code/security/QA review result;
- `PASS / FAIL / BLOCKED / NOT_RUN` evidence;
- end candidate HEAD;
- blockers and exact resume condition;
- next highest-value READY action.

Execution loop:

`RECONSTRUCT -> SELECT -> CLAIM/ISOLATE -> INSPECT -> IMPLEMENT -> REVIEW -> TEST -> FIX -> VERIFY -> CHECKPOINT -> CONTINUE`

If the useful authorized frontier is exhausted, stop rather than inventing work.

## Roles

- **Orchestrator:** live-truth reconciliation, state, task graph, collision control and release gate.
- **Data engineer:** providers, normalization, point-in-time storage and provenance.
- **Quant researcher:** features, walk-forward, baselines, calibration and leakage controls.
- **Market analyst:** economic interpretation, falsification and scenario taxonomy.
- **XRPL analyst:** ledger metrics, accounts, AMMs, DEX and network health.
- **SRE:** scheduling, observability, freshness, recovery and incident response.
- **Security reviewer:** secrets, supply chain, permissions, network surfaces and threat model.
- **QA reviewer:** deterministic tests, fixtures, reproducibility and acceptance evidence.
