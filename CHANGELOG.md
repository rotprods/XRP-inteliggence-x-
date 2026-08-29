# Changelog

## 0.2.0-alpha.2 — 2026-08-28

- Added the Q1 closeout and R4 entry implementation plan with hard cost and promotion gates.
- Pruned duplicate historical/demo release evidence from the canonical source tree.
- Added the canonical `Verification OS` specification and Todoist execution graph.
- Expanded the deterministic suite from the recovered 55-test baseline to more than 230 local tests.
- Reached 100% application line and branch coverage locally, including all configured critical modules.
- Added a 100% changed-executable-line coverage gate that includes untracked new source files.
- Added hermetic pytest execution: credentials/proxies scrubbed, UTC/random state fixed and network denied by default.
- Added Hypothesis property suites and FAST/DEEP/RELEASE generation profiles.
- Added provider contract/adversarial fixtures for Binance, Coinbase, Kraken, KuCoin, FRED and XRPL.
- Added the current read-only KuCoin Unified API spot kline adapter with strict USDT semantics.
- Added future-candle rejection to multi-provider consensus.
- Added point-in-time `available_at` filtering to research, rolling-window support and explicit embargo.
- Added SQLite corruption, transaction, backup/restore and resource-leak regression tests.
- Fixed a connection leak when SQLite configuration failed before the context-manager yield.
- Added mutation-score, flake-seed replay and machine-readable quality-evidence tooling.
- Added deterministic double-wheel comparison, SBOM and dependency-audit gates.
- Replaced the alpha manual workflow design with one cost-bounded FAST/DEEP/RELEASE Verification OS workflow.
- Kept CI read-only: no code generation, commits, releases, merges, scheduled runs, paid providers or larger runners.

## 0.2.0-alpha.1 — 2026-08-25

- Recovered the verified `0.1.0-alpha` source into a clean local Git baseline.
- Removed generated caches, bytecode, demo databases and runtime artifacts from source control.
- Removed synthetic derivatives, provider-quality and XRPL values from the generic feature path.
- Added explicit missing-value semantics and full-window feature requirements.
- Corrected flat-market RSI from false `100` to neutral `50`.
- Separated data confidence, model confidence and directional conviction.
- Removed data quality from directional bull/bear scoring; it now acts only as an output gate.
- Made price consensus fail closed for insufficient, stale, misaligned or conflicting providers.
- Added strict OHLC, timestamp, finite-value and payload-hash validation.
- Separated Binance USDT markets from USD asset semantics.
- Added provider host allowlists, HTTPS enforcement, bounded bodies, no redirects, no environment proxies, safe retries and secret-safe errors.
- Added an explicit read-only XRPL RPC method allowlist.
- Added FRED date-precision availability metadata using `realtime_start`.
- Hardened SQLite with WAL, busy timeouts, schema metadata, upserts and audit records.
- Replaced automatic CI triggers with one manual, bounded verification workflow.
- Expanded deterministic tests for failure modes, providers, configuration, confidence and security boundaries.

## 0.1.0-alpha — 2026-08-24

- Added canonical control plane and engineering baseline.
- Added deterministic demo pipeline and SQLite store.
- Added provider adapters and consensus layer.
- Added cross-asset feature engine and explainable regime scorer.
- Added FastAPI, CLI, JSON schemas, tests, Docker and CI.
- Added GitHub/Codex integration brief and release manifest workflow.
