# DECISIONS

## ADR-001 — Multi-provider consensus is mandatory

A price or feature is not considered production-grade when sourced from only one provider unless the snapshot explicitly declares degraded mode.

## ADR-002 — Separate horizons

`1h`, `4h`, `1d` and `1w` models are computed independently. A weekly bottoming thesis must not be presented as an intraday trade signal.

## ADR-003 — Explainability before model complexity

The first production model is a weighted, calibrated and fully decomposable regime engine. More complex models may be added as challengers, never as an untraceable replacement.

## ADR-004 — Point-in-time correctness

Macro observations, news events and revised datasets must preserve `available_at`, not merely their economic observation date. Backtests must never consume data before it was public.

## ADR-005 — No auto-trading in alpha/beta

The engine is read-only. Any future execution service must be a separate bounded system with independent credentials, controls and human approval.

## ADR-006 — Storage starts with SQLite

SQLite provides a zero-infrastructure, auditable baseline. Production can migrate to Postgres/Timescale or ClickHouse after data volume and concurrency justify it.

## ADR-007 — XRP Ledger is a distinct evidence layer

XRPL activity is not conflated with Ripple corporate announcements or XRP exchange price. Each has separate provenance and weights.

## ADR-008 — Cacao is exploratory, not causal

Cocoa may be stored for broad commodity research but has zero default decision weight. Energy, yields, DXY, equities and BTC receive materially higher priors.

## ADR-009 — CI verifies; it never authors the repository

GitHub Actions may lint, type-check, test, scan and build artifacts. Workflows may not generate implementation code, modify branches, create further workflows, open cascading controllers or merge pull requests.

## ADR-010 — Local-first promotion with WIP limits

Only one implementation branch, one open PR and one CI workflow may exist during foundation recovery. Two repeated remote failures with the same cause trip a circuit breaker and force local reproduction.

## ADR-011 — Data quality is a gate, not market direction

Provider agreement, freshness and coverage cannot add bullish or bearish weight. They control whether an otherwise directional score may be displayed or alerted.

## ADR-012 — Confidence terms are explicitly separated

`data_confidence`, `model_confidence` and `directional_conviction` have different semantics. The aggregate operational `confidence` is not a calibrated probability of correctness.

## ADR-013 — USD and stablecoin quote markets are distinct

`XRP_USD` and `XRP_USDT` are separate canonical symbols. A USDT venue cannot silently populate a USD series. Cross-quote normalization requires an explicit, versioned stablecoin basis policy.
