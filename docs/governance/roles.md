# Ownership and Review Roles

## Accountable owner

- **Project owner and product authority:** Roberto Ortega (`@rotprods`).
- Owns the North Star, scope, release priority and final go/no-go decision.

## Required review roles

A pull request may be authored by one person or agent, but release evidence must cover
all of the following review functions:

| Review function | Required evidence |
|---|---|
| Architecture | No duplicate implementation, stable public boundaries and rollback path |
| Data engineering | Provenance, quote semantics, timestamps, freshness and provider failure modes |
| Quant research | Point-in-time correctness, leakage controls, calibration and benchmark comparison |
| Security | Read-only permissions, SSRF controls, secret handling and dependency review |
| QA | Reproducible tests, coverage, build artifact and acceptance criteria |
| Operations | SLOs, incident response, backups, restore and no-data behaviour |

For an engineering alpha, one reviewer may cover multiple functions. A production release
requires at least one independent reviewer who did not author the release commit. The
project owner may not self-approve a production release without that independent review.

## CODEOWNERS policy

`@rotprods` owns the repository by default. Sensitive areas require explicit review focus:

- `.github/` — CI and repository governance;
- `src/xrp_regime_engine/providers/` — external input and SSRF boundary;
- `src/xrp_regime_engine/regime.py` — decision semantics;
- `src/xrp_regime_engine/backtest.py` — research validity;
- `config/weights.json` and `config/thresholds.json` — model behaviour;
- `release/` — promotion evidence.
