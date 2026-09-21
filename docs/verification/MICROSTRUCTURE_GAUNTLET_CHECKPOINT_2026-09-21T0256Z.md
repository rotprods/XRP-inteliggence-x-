# Microstructure Gauntlet Checkpoint — 2026-09-21T02:56Z

## Scope

Bounded read-only hardening wave on PR #15 (`feat/binance-microstructure-v1`). No trading, order placement, wallet/custody, signing, leverage sizing, credentials, private endpoints, or production promotion was added or authorized.

## Persistent truth inspected before change

- Parent PR #13: OPEN / DRAFT / mergeable at exact HEAD `ca0187a477ce587153ec9919b727a998e7878e7d`.
- Parent FAST run `35547315028`, job `106175441465`: dependency consistency PASS, schema reproduction PASS, compile PASS, Ruff lint PASS, Ruff format FAIL with 28 files still requiring deterministic formatting. Downstream strict mypy, Bandit, hermetic tests/coverage, contracts and wheel build remain NOT_RUN/SKIPPED.
- Child PR #15 pre-wave HEAD: `d77238cc6b22a5370e0f046bdc4299d630f0ca57`.
- Parent/child histories remain diverged from merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.

## Implemented

### 1. Depth stream provenance

`DepthDelta` now optionally carries `available_at` and `fetched_at` in addition to `observed_at`. Partial provenance pairs are rejected. Complete event provenance must satisfy:

`observed_at <= available_at <= fetched_at`

`LocalOrderBook` carries the last event provenance forward. `DepthDynamics` now exposes first/last observed, available and fetched envelopes plus `provenance_complete`.

A REST snapshot deliberately does **not** synthesize `available_at`; the first diff-derived interval therefore remains provenance-incomplete unless both boundaries genuinely have source timing. This avoids inventing publication-time facts from fetch time.

### 2. aggTrade provenance

`AggregateTrade` now optionally carries `available_at` and `fetched_at` with the same fail-closed ordering contract. `compute_order_flow()` derives:

- first / last observed timestamps;
- first / last available timestamps;
- first / last fetched timestamps;
- `provenance_complete`.

Legacy trades without source availability/fetch timestamps remain supported only as provenance-incomplete shadow evidence.

### 3. Provenance-derived cross-stream windows

`reconcile_depth_with_order_flow()` now derives both depth and trade-flow window durations from first/last observed envelopes whenever possible. A caller-provided `flow_window_seconds` is a compatibility fallback only when provenance-derived windows are unavailable; when complete provenance exists, caller duration is ignored and explicitly flagged.

This removes a prior trust surface where a caller could supply a duration inconsistent with the underlying observations.

### 4. Prediction-time leakage gate

Code review identified that complete provenance alone was insufficient to call a record point-in-time eligible: the latest fetch could still occur after the intended prediction time.

The reconciler therefore now accepts optional `prediction_time` and remains fail-closed:

- complete provenance + no prediction time -> `PREDICTION_TIME_REQUIRED`, `point_in_time_eligible=false`;
- complete provenance + `latest_fetched_at <= prediction_time` -> point-in-time compatibility may be eligible;
- any required observation/fetch after prediction time -> `FUTURE_KNOWLEDGE_BLOCKED`, compatibility notionals are suppressed, `evidence_eligible=false`, `point_in_time_eligible=false`.

Even when point-in-time compatibility is eligible, `regime_eligible=false` and `execution_weight=0.0` remain invariant. This wave does not grant predictive, calibrated, or execution authority.

## Code / security review

PASS for bounded scope:

- no network-write or exchange-order capability added;
- no credential, API-key, wallet, signing or custody path added;
- no leverage sizing or trade recommendation path added;
- no causal claim is promoted from displayed-depth/trade compatibility;
- caller-supplied duration cannot override complete provenance windows;
- future-fetched information is blocked at an explicit prediction time;
- all new compatibility outputs remain SHADOW_ONLY and `execution_weight=0.0`.

## Targeted QA evidence

Local-equivalent isolated harness on Python 3.13.5:

- compile of bounded modules: PASS;
- targeted deterministic tests: 8 PASS in 0.05 s;
- covered complete aggTrade provenance envelope;
- covered rejection of partial provenance;
- covered complete second-delta depth provenance envelope;
- covered provenance-derived window calculation;
- covered missing prediction-time fail-closed state;
- covered caller-window ignored when provenance exists;
- covered future-fetched-data suppression;
- covered legacy incomplete-provenance fallback remaining point-in-time ineligible.

No Ruff executable was present in this runtime. No full repository pytest/coverage, Ruff, strict mypy or Bandit claim is made.

## Evidence state

- PASS — bounded Python compile.
- PASS — targeted deterministic provenance/leakage harness.
- PASS — bounded manual code/security review.
- PASS — PR #15 remains OPEN / DRAFT / mergeable after wave.
- NOT_RUN — full PR #15 pytest + branch coverage.
- NOT_RUN — Ruff lint / Ruff format for PR #15.
- NOT_RUN — strict mypy for PR #15.
- NOT_RUN — Bandit for PR #15.
- NOT_RUN — inherited repository/source-manifest/wheel gates for PR #15.
- FAIL — parent PR #13 Ruff format gate from existing FAST evidence; 28 files remain.
- BLOCKED — reconciliation/promotion of PR #15 onto parent until parent verification converges.
- BLOCKED — probability calibration.
- BLOCKED — production readiness.

No new workflow run was manually started for this wave. Exact post-test code/test HEAD before this checkpoint file: `5639f49eef51f8b6a7dc13bd76d88938632275ac`.

## Next highest-value sequence

1. Finish parent PR #13 Ruff-format remediation in one consolidated deterministic batch without weakening style policy; reveal only the next evidenced gate.
2. Align freshness/availability across depth, aggTrades, OI, funding and basis using the same `observed_at / available_at / fetched_at / prediction_time` contract.
3. Keep cross-stream evidence fail-closed when any required stream is stale, future-fetched, provenance-incomplete or temporally misaligned.
4. Reconcile PR #15 onto a sufficiently green exact parent HEAD and run inherited verification.
5. Only after those gates, build an **uncalibrated** evidence vector. Bayesian/posterior probability outputs remain forbidden until leakage-safe point-in-time walk-forward calibration is evidenced.
