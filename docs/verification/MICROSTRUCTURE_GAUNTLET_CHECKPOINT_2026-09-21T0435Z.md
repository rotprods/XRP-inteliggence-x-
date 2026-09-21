# Microstructure Gauntlet Checkpoint — 2026-09-21T04:35Z

## Scope

Bounded read-only hardening wave on PR #15 (`feat/binance-microstructure-v1`). This wave captures local derivative fetch time at the Binance USD-M ingestion boundary without inventing upstream availability time. No trading, order placement, wallet/custody, signing, leverage sizing, credentials, private endpoints, calibrated probability, or production promotion was added or authorized.

## Persistent truth inspected before change

- Parent PR #13: OPEN / DRAFT / mergeable at exact HEAD `ca0187a477ce587153ec9919b727a998e7878e7d`.
- Parent FAST run `35547315028`, job `106175441465`: dependency consistency PASS, schema reproduction PASS, compile PASS, Ruff lint PASS, Ruff format FAIL with 28 files remaining. Strict mypy, Bandit, hermetic tests/coverage, repository/source-manifest contracts and wheel build remain NOT_RUN/SKIPPED after the formatter failure.
- PR #15 pre-wave exact HEAD: `7f3dd86fc7eb5ba2bff01e29d998e0cd3a7c640f`, OPEN / DRAFT / mergeable.
- Existing cross-stream gate already required derivative `fetched_at` and independently justified `available_at`; provider ingestion did not yet populate the locally knowable fetch timestamp.
- No new workflow run was manually started.

## Implemented

### 1. Derivative ingestion fetch timestamp

`BinanceFuturesProvider.fetch_funding()` and `fetch_open_interest()` now capture `fetched_at = datetime.now(UTC)` immediately after the bounded public REST response has been received and decoded by `_request_json()`.

This timestamp means only: **the local ingestion process had received the response by this wall-clock instant**.

It does not claim:

- upstream publication time;
- exchange matching-engine event time beyond the endpoint's supplied `time` field;
- causal ordering across independent streams;
- trading eligibility or predictive direction.

`available_at` remains `None` because these endpoints do not independently expose a publication boundary that can be justified from the payload. Therefore `provenance_complete` remains false for live REST derivative snapshots until a separate availability boundary is evidenced.

### 2. Fail-closed clock ordering

Existing derivative validation requires `observed_at <= fetched_at`. If Binance supplies an exchange `time` later than the local ingestion clock, construction fails closed and the provider converts the validation error into a sanitized `ProviderError`. The code does not silently clamp or rewrite the upstream timestamp.

### 3. Regression coverage

Added `tests/test_binance_futures_provenance.py` covering:

- funding captures a timezone-aware local `fetched_at` within the request-call interval;
- open interest captures a timezone-aware local `fetched_at` within the request-call interval;
- `available_at` is not synthesized;
- `provenance_complete` remains false without evidenced availability;
- payload SHA-256 provenance remains present;
- a future exchange timestamp relative to the local ingestion clock fails closed.

The test helper and Optional timestamp assertions were tightened for strict type-checking compatibility.

## Code / security review

PASS for this bounded scope:

- only public GET-only USD-M market-data methods are touched;
- no execution, order, position, account, wallet, signing, custody or withdrawal capability added;
- no credentials or private endpoints added;
- no availability timestamp is fabricated from fetch time;
- no source timestamp is clamped to local time;
- future exchange timestamps fail closed rather than being accepted;
- payload hashes remain retained;
- `execution_weight=0.0`, SHADOW_ONLY interpretation, probability calibration BLOCKED and production BLOCKED remain unchanged.

## Targeted QA evidence

Available local-equivalent evidence on Python 3.13.5:

- targeted derivative-ingestion provenance harness: PASS, 3 checks;
- future exchange timestamp fail-closed path: PASS;
- Ruff executable: unavailable in this runtime;
- strict mypy: unavailable in this runtime;
- Bandit: unavailable in this runtime.

The exact pre-checkpoint code/test HEAD `7c781a06f9645a6bc11a192829315e93dbce8404` had no associated workflow run when checked. No CI run was manually started merely to create evidence.

## Evidence state

- PASS — derivative local fetch-time capture is implemented.
- PASS — unsupported upstream `available_at` remains unset.
- PASS — 3-check targeted behavioral harness.
- PASS — bounded manual code/security review.
- PASS — PR #15 remained OPEN / DRAFT / mergeable after the code/test writes.
- NOT_RUN — full PR #15 pytest + branch coverage.
- NOT_RUN — Ruff lint / Ruff format for PR #15.
- NOT_RUN — strict mypy for PR #15.
- NOT_RUN — Bandit for PR #15.
- NOT_RUN — inherited repository/source-manifest/wheel gates for PR #15.
- FAIL — parent PR #13 Ruff format gate from existing FAST evidence; 28 files remain.
- BLOCKED — reconciliation/promotion of PR #15 until parent verification converges.
- BLOCKED — Bayesian/posterior probability calibration.
- BLOCKED — production readiness.

## Branch divergence

Comparison against parent HEAD `ca0187a477ce587153ec9919b727a998e7878e7d` at pre-checkpoint code/test HEAD `2e6362f8db81c96cbdabc0a1d96f03773a6736ee` showed PR #15 diverged, 50 commits ahead and 7 commits behind, with merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.

## Next highest-value sequence

1. Finish parent PR #13 Ruff-format remediation without weakening policy and reveal the next evidenced gate.
2. Route temporal feature construction through `assess_cross_stream_alignment()` so stale, future-fetched, provenance-incomplete, symbol-mismatched or skewed streams cannot enter an evidence vector.
3. Keep derivative `available_at` absent unless an independently justified upstream availability boundary is introduced.
4. Reconcile PR #15 onto a sufficiently green exact parent HEAD and run the inherited verification gauntlet.
5. Only after those gates, construct an **uncalibrated** evidence vector. Bayesian/posterior probabilities remain forbidden until leakage-safe point-in-time walk-forward calibration is evidenced.
