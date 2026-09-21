# Microstructure Gauntlet Checkpoint — 2026-09-21T04:08Z

## Scope

Bounded read-only hardening wave on PR #15 (`feat/binance-microstructure-v1`). The wave aligns depth, aggTrades, open interest, funding and mark/index basis under a common point-in-time freshness contract. No trading, order placement, wallet/custody, signing, leverage sizing, credentials, private endpoints, calibrated probability, or production promotion was added or authorized.

## Persistent truth inspected before change

- Parent PR #13: OPEN / DRAFT / mergeable at exact HEAD `ca0187a477ce587153ec9919b727a998e7878e7d`.
- Parent FAST run `35547315028`, job `106175441465`: dependency consistency PASS, schema reproduction PASS, compile PASS, Ruff lint PASS, Ruff format FAIL with 28 files remaining. Strict mypy, Bandit, hermetic tests/coverage, repository/source-manifest contracts and wheel build remain NOT_RUN/SKIPPED after the formatter failure.
- PR #15 pre-wave exact HEAD: `96f5f1ef29d3aa1295d5ed03fbe28d064ba53da8`, OPEN / DRAFT / mergeable.
- Parent/child histories remain diverged from merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.
- No new workflow run was manually started.

## Implemented

### 1. Derivatives point-in-time provenance contract

`FundingState` and `OpenInterestState` now support optional `available_at`, `fetched_at`, and `payload_sha256` fields.

Validation is fail-closed for known facts:

- all supplied timestamps must be timezone-aware;
- `available_at` cannot precede `observed_at`;
- `fetched_at` cannot precede `observed_at`;
- when both are known, `available_at <= fetched_at`;
- payload digests must be lowercase 64-character SHA-256 hex strings.

`provenance_complete` is true only when both availability and fetch timestamps are known. Missing availability is not synthesized.

### 2. Binance USD-M payload provenance retained

The public read-only futures adapter now retains the SHA-256 payload digest already produced by the hardened provider transport for both premium-index/funding and open-interest responses.

The adapter deliberately does **not** claim a source `available_at` timestamp when the endpoint does not expose a separately evidenced publication time. Therefore these REST snapshots remain point-in-time provenance-incomplete until the ingestion layer can supply an independently justified availability boundary.

### 3. Cross-stream freshness and alignment gate

Added `stream_alignment.py` with a pure observational gate across:

- displayed depth dynamics;
- aggregate-trade flow;
- open interest;
- funding;
- mark/index basis, which intentionally shares the funding snapshot provenance.

The gate checks, per stream:

- presence;
- complete provenance;
- future observation / availability / fetch leakage relative to `prediction_time`;
- stream-specific maximum age;
- cross-stream observed-time skew.

Any missing, provenance-incomplete, stale, future-fetched, or temporally misaligned required stream fails closed.

Passing this gate means only that the evidence is temporally aligned enough for later shadow analysis. It does **not** authorize a regime label, probability, trade recommendation, position size or order. `regime_eligible=false` and `execution_weight=0.0` remain explicit invariants.

### 4. Regression coverage

Added deterministic tests covering:

- complete aligned streams -> point-in-time/evidence eligible while regime remains ineligible;
- incomplete funding/basis provenance -> fail closed;
- future-fetched open interest -> blocked;
- stale open interest -> blocked;
- cross-stream skew -> blocked independently of individual stream age;
- mixed symbols -> rejected;
- invalid derivative timestamp ordering and malformed payload digest -> rejected.

## Code / security review

PASS for this bounded scope:

- no network-write or exchange-order capability added;
- no API key, wallet, signing, custody or withdrawal path added;
- no leverage sizing or position recommendation added;
- no private endpoint added;
- no source availability timestamp is invented;
- provider payload hashes are retained without granting causal or predictive authority;
- cross-stream eligibility fails closed on missing or temporally invalid evidence;
- probability calibration remains blocked;
- `regime_eligible=false` and `execution_weight=0.0` remain invariant.

## Targeted QA evidence

Local-equivalent isolated harness on Python 3.13.5:

- bounded module compilation: PASS;
- deterministic alignment/provenance tests: 6 PASS in 0.05 s;
- Ruff executable: unavailable in this runtime;
- strict mypy: unavailable in this runtime;
- Bandit: unavailable in this runtime.

The isolated harness validates the bounded logic and interfaces but is not represented as a substitute for the repository's inherited full verification gauntlet.

## Evidence state

- PASS — bounded Python compile.
- PASS — 6 deterministic cross-stream alignment/provenance checks.
- PASS — bounded manual code/security review.
- PASS — PR #15 remained OPEN / DRAFT / mergeable after code/test writes.
- NOT_RUN — full PR #15 pytest + branch coverage.
- NOT_RUN — Ruff lint / Ruff format for PR #15.
- NOT_RUN — strict mypy for PR #15.
- NOT_RUN — Bandit for PR #15.
- NOT_RUN — inherited repository/source-manifest/wheel gates for PR #15.
- FAIL — parent PR #13 Ruff format gate from existing FAST evidence; 28 files remain.
- BLOCKED — reconciliation/promotion of PR #15 until parent verification converges.
- BLOCKED — Bayesian/posterior probability calibration.
- BLOCKED — production readiness.

Exact post-test code/test HEAD before this checkpoint file: `014707244b9bf2e2463687ab0f25bad5ddf2fade`.

## Branch divergence

Comparison against parent HEAD `ca0187a477ce587153ec9919b727a998e7878e7d` immediately before this checkpoint showed PR #15 diverged, 47 commits ahead and 7 commits behind, with merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.

## Next highest-value sequence

1. Finish parent PR #13 Ruff-format remediation in one consolidated deterministic batch without weakening policy, then reveal only the next evidenced gate.
2. At the ingestion boundary, capture `fetched_at` for derivative snapshots and populate `available_at` only when the upstream endpoint supplies an independently justified publication boundary; never infer it from fetch time.
3. Route temporal feature construction through the new cross-stream alignment gate so stale, future-fetched, provenance-incomplete, symbol-mismatched or skewed streams cannot enter an evidence vector.
4. Reconcile PR #15 onto a sufficiently green exact parent HEAD and run the inherited verification gauntlet.
5. Only after those gates, construct an **uncalibrated** evidence vector. Bayesian/posterior probabilities remain forbidden until leakage-safe point-in-time walk-forward calibration is evidenced.
