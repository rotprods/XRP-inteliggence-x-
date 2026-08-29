# XRP Cross-Asset Regime Engine

Read-only, provenance-aware decision intelligence for monitoring XRP through a multi-layer market model:

1. macro and liquidity conditions;
2. equities and crypto-sensitive equities;
3. Bitcoin and broad crypto structure;
4. alt rotation and XRP relative strength;
5. spot and derivatives microstructure;
6. XRP Ledger and verified Ripple/regulatory events;
7. provider coverage, freshness, agreement and model reliability.

The engine does **not** promise price certainty, execute trades, sign wallets, manage private keys or provide custody. It produces timestamped, explainable regime snapshots and blocks output when critical evidence is stale, conflicting or incomplete.

## Current state

- Version: `0.2.0a2`
- Phase: **local foundation hardening**
- Canonical repository: `https://github.com/rotprods/XRP-inteliggence-x-`
- Remote promotion: intentionally paused until the local tree passes all gates
- Production decision use: **BLOCKED**

## Confidence semantics

The API separates four concepts:

- `bull_score`: directional expert score, not a calibrated probability;
- `data_confidence`: provider coverage, freshness, agreement and feature availability;
- `model_confidence`: heuristic completeness and component coherence;
- `directional_conviction`: distance of the directional score from neutral.

`confidence` is an operational combination of data and model confidence. It is **not** the probability that a forecast is correct. `probability_calibrated` remains false until point-in-time walk-forward calibration is complete.

## Quick start — deterministic demo

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
make check
python -m xrp_regime_engine.cli demo --output state/demo
```

The demo is network-free. Derivatives, provider-quality and XRPL supplemental values are explicitly marked synthetic and are never injected by the generic feature pipeline.

## Read-only API

```bash
python -m xrp_regime_engine.cli api
```

Endpoints:

- `GET /health`
- `GET /ready`
- `GET /v1/regime/xrp/{1h|4h|1d|1w}`
- `GET /v1/explain/xrp/{1h|4h|1d|1w}`
- `GET /v1/providers/health`

## Live mode boundary

`xrp-regime snapshot` deliberately exits with code `2`. Live orchestration remains blocked until provider validation, persistence, SLO and release gates are implemented. Public adapters are read-only and enforce HTTPS, allowlisted hosts, bounded payloads, no redirects, no environment proxies and safe error redaction.

USD and USDT are separate asset semantics. Binance USDT markets are never labelled as USD.

## Engineering workflow

The recovery flow is local-first:

```text
Drive artifact
→ safe extraction
→ local Git
→ tests and evidence
→ one clean branch
→ one manual CI workflow
→ one draft PR
→ review
→ merge
```

GitHub Actions verifies code; it does not generate, repair, commit or merge code.

## Canonical control-plane order

1. `GOAL.md`
2. `STATE.md`
3. `TASKS.md`
4. `DECISIONS.md`
5. `AGENTS.md`
6. `docs/architecture.md`
7. `docs/data_contracts.md`
8. `docs/model_card.md`
9. `CODEX.md`

## Critical path

1. Promote the locally verified foundation through one clean PR.
2. Validate a small read-only provider core regionally.
3. Build immutable point-in-time historical storage.
4. Run leakage-safe walk-forward research and calibration.
5. Operate immutable shadow mode for at least 30 days.
