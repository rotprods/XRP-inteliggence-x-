# Walk-Forward OOS Gauntlet Checkpoint — 2026-09-21T16:10Z

## Scope and authority

This checkpoint records the bounded continuation from merged PIT Historical Evidence V2 into the historical feature/label and walk-forward research surface. Repository truth outranks older chat or handoff assumptions.

Hard boundary remains `READ_ONLY / SHADOW_ONLY / NON_EXECUTION`:

- no trading or order placement;
- no custody, wallet signing, withdrawals, private keys or seed handling;
- no leverage or position sizing;
- no calibrated-probability or production-readiness claim;
- `execution_weight=0.0`, `decision_authority=false`, `probability_calibrated=false`, `production_ready=false` remain blocked.

## Reconstructed repository truth

- `main` exact HEAD: `d22ab82bac05750338b33dba0e061db8104c34ac`.
- PR #18 is merged. Its final feature-branch HEAD was `df74f2a2d11533fd52c73a4d7765ed7eeef05d22`.
- Exact-head PR #18 FAST: workflow `35618193983` — **PASS**.
- PR #15 and PR #13 are already in the canonical main lineage.
- PR #17 is closed without merge and remains salvage-only; do not revive it as a parallel architecture.
- No open pull requests were present at this wave's initial inspection.
- Main `STATE.md` and root `HANDOFF.md` are historical Q1-era documents and contain stale SHAs; the newer PIT handoff plus live GitHub state are stronger authority.

## Active canonical continuation

Existing branch: `research/walk-forward-oos-v1`.

Before this bounded wave:

- exact branch HEAD: `47f01fd951800e92508ac9c1ec825a7f740649b3`;
- compare against `main`: **15 ahead / 0 behind**;
- merge base: exact current `main@d22ab82bac05750338b33dba0e061db8104c34ac`;
- no workflow run existed for that branch because no PR existed;
- branch already carried the reconciled historical store, historical backfill, feature/label firewall and canonical horizon contracts on top of merged PIT V2.

This wave deliberately reused that branch rather than creating a duplicate architecture.

## Bounded implementation

Implementation commit: `2825334e9486d9757f5c71613c34a85bd7c158ec`.

Added `src/xrp_regime_engine/walk_forward_v1.py` with:

- expanding and rolling chronological fold modes;
- deterministic fold identities;
- single-horizon enforcement;
- feature/label identity and prediction-time consistency checks;
- training eligibility only when `label.resolved_at < test_prediction_start - embargo`;
- strict exclusion at the exact cutoff boundary;
- explicit embargo support;
- rolling-window train caps;
- non-overlapping test-window configuration;
- fail-closed behavior when no leakage-safe fold can be constructed;
- fold plans expose immutable feature/label IDs and timing metadata, not execution decisions.

Test commit: `a3ad2b05aa55aec6de565ccf2e8319727461783a`.

Added `tests/test_walk_forward_v1.py` covering:

- deterministic order-independent joins;
- feature/label identity mismatch;
- missing and orphan labels;
- mixed-horizon rejection;
- duplicate prediction-time rejection;
- purge at an equal label-resolution/test boundary;
- explicit post-resolution embargo;
- rolling-window train-size cap;
- deterministic fold identity;
- no-fold fail-closed behavior;
- invalid overlapping test windows;
- missing rolling bound;
- negative embargo.

## Review evidence

### Code review — PASS by bounded inspection

The change adds one isolated planner plus one dedicated test module. It does not modify existing production/runtime provider, microstructure, SemanticBrain, Graphify, COS20D, storage or execution surfaces. The planner consumes the already-established `HistoricalFeatureRow`, `FutureOutcomeLabel` and `ResearchHorizon` contracts instead of defining parallel equivalents.

### Security review — PASS by bounded inspection

The new module introduces no network access, credentials, subprocesses, filesystem writes, account mutation, provider mutation, trading, wallet operations or execution authority. Inputs are deterministic in-memory research rows. Fail-closed validation is preserved.

### Temporal/leakage review — PASS by design inspection

A training row is eligible only when its future label is already resolved strictly before the embargo-adjusted test prediction cutoff. Equality is excluded. Horizons cannot be mixed within one fold plan. Test folds cannot overlap through configuration.

### QA evidence

- Python parse/syntax check for the new module: **PASS**.
- Python parse/syntax check for the new tests: **PASS**.
- Hermetic repository pytest/coverage gate on the new exact HEAD: **NOT_RUN** at checkpoint creation.
- Ruff / strict mypy / Bandit on the new exact HEAD: **NOT_RUN** at checkpoint creation.
- Changed-line coverage: **NOT_RUN** at checkpoint creation.
- Repository/source-manifest contract: expected to require regeneration because new tracked source/test/checkpoint files were added; do not weaken this gate.
- DEEP / RELEASE gates: **NOT_RUN**.

## Collision and convergence notes

The branch was re-read immediately before the writes and remained at the observed exact HEAD. No open PR claimed this scope. This wave did not create a new branch or alter main.

## Next exact action

1. Open one draft PR from `research/walk-forward-oos-v1` to exact current `main` so the existing bounded FAST profile can verify the accumulated canonical continuation once.
2. Inspect only the first failing gate on the exact PR head.
3. If the deterministic manifest is stale, refresh it from `scripts/build_manifest.py` / the workflow's exact expected manifest; do not suppress or bypass the contract.
4. Fix root causes locally/in-branch, not by CI retry loops.
5. Require compile, Ruff lint/format, strict mypy, Bandit, hermetic tests, coverage, changed-line coverage, manifest/repository contracts and wheel build to pass before promotion.
6. After this layer is green, continue to OOS fold execution/baselines; calibrated probabilities, Bayesian posterior and production readiness remain blocked until genuine OOS/calibration evidence exists.
