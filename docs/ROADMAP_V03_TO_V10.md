# Roadmap: v0.3 alpha → v1.0 read-only production

## M0 — v0.3.0-alpha: canonical engineering foundation

- clean repository tree and branch strategy;
- reproducible package, CLI, API and tests;
- governance, provenance and confidence gates;
- provider assurance boundary;
- CI/build/security evidence;
- production explicitly blocked.

## M1 — v0.4: live ingestion and operational storage

- validated Coinbase/Kraken/KuCoin/Binance regional adapters;
- derivatives adapters for OI, funding, basis and liquidations;
- XRPL ledger, DEX and AMM metrics;
- FRED/macro/equity/commodity registry;
- immutable raw payload hashes and provider health;
- Postgres/Parquet operational persistence;
- no-data and degraded modes.

## M2 — v0.5-beta: point-in-time research

- BTC/XRP/ETH and cross-asset historical backfill;
- macro vintages and trading-calendar alignment;
- 2017, 2018, 2020, 2021, 2022, 2023, 2024–25 and 2026 event windows;
- purged walk-forward validation;
- Brier score, calibration error and regime precision;
- ablation, stability and provider-substitution tests.

## M3 — v0.7: immutable shadow service

- append-only prediction ledger;
- outcome joins only after horizon expiry;
- provider/SLO dashboards;
- daily and weekly reports;
- incident, backup and restore drills;
- champion/challenger comparison.

## M4 — v0.9-rc: production candidate

- 30+ days of uninterrupted shadow evidence;
- calibrated confidence thresholds;
- false-alert and adverse-excursion limits;
- security and dependency/container scans;
- signed build manifest and SBOM;
- rollback rehearsal.

## M5 — v1.0: read-only production

- stable regime, confidence, driver, invalidation and provider-health API;
- mobile/dashboard summaries;
- alerts that state uncertainty and data status;
- no custody, signing, trading or order execution.
