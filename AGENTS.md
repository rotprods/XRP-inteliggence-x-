# AGENTS — Operating Contract

Every agent working on this repository must:

1. Read `GOAL.md`, `STATE.md`, `TASKS.md`, `DECISIONS.md` and `CODEX.md` before changing code.
2. Preserve the distinction between observation, inference, scenario and recommendation.
3. Never silently substitute stale data for live data.
4. Add provenance, `observed_at`, `available_at`, provider and freshness to every external datum.
5. Add or update tests for every scoring, schema or adapter change.
6. Avoid adding a dependency when the standard library or an existing dependency is sufficient.
7. Keep credentials out of source, logs, fixtures, screenshots and Drive documents.
8. Never add automatic trading permissions to a market-data connector.
9. Update `STATE.md`, `TASKS.md` and `CHANGELOG.md` when a release gate changes.
10. Produce a handoff containing branch, commit, tests, blockers, data caveats and rollback steps.

## Roles

- **Orchestrator:** owns state, task graph and release gate.
- **Data engineer:** providers, normalization, storage and provenance.
- **Quant researcher:** features, backtests, calibration and leakage controls.
- **Market analyst:** economic interpretation and scenario taxonomy.
- **XRPL analyst:** ledger metrics, accounts, AMMs, DEX and network health.
- **SRE:** scheduling, observability, freshness and incident response.
- **Security reviewer:** secrets, supply chain, permissions and threat model.
- **QA reviewer:** deterministic tests, fixtures and acceptance evidence.
