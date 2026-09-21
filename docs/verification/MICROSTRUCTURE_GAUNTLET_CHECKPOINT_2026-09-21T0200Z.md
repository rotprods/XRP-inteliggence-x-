# Microstructure Gauntlet Checkpoint — 2026-09-21T02:00Z

## Persistent truth inspected before writes

- Repository: `rotprods/XRP-inteliggence-x-`
- Parent PR #13: OPEN / DRAFT / GitHub `mergeable=true`
- Parent branch: `feat/q1-verification-os`
- Parent exact HEAD: `ca0187a477ce587153ec9919b727a998e7878e7d`
- Parent FAST evidence: run `35547315028`, job `106175441465`
- Parent gate state remains: dependency consistency PASS; schema reproduction PASS; compile PASS; Ruff lint PASS; Ruff format FAIL with 28 files remaining; downstream strict mypy/Bandit/tests/coverage/contracts/build NOT_RUN/SKIPPED.
- Child PR #15: OPEN / DRAFT / GitHub `mergeable=true`
- Child branch: `feat/binance-microstructure-v1`
- Child pre-wave HEAD: `0d408ca3bd5e35d6bf6f4b4597cc29f954d660db`
- Parent/child comparison before writes: diverged; child 26 commits ahead and 7 behind parent; merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.
- No workflow run existed for the inspected child pre-wave HEAD; no remote CI was spent in this wave.

The parent formatter scope was not modified because the persistent gate explicitly requests a consolidated deterministic formatting pass and this runtime does not have the repository checkout/formatter surface required to perform that pass reliably. The child wave therefore advanced the already-planned, isolated microstructure frontier without weakening promotion gates.

## Bounded implementation

Added `src/xrp_regime_engine/trade_attribution.py` and `tests/test_trade_attribution.py`.

The new layer reconciles displayed-depth removal with contemporaneous aggregate aggressive trade flow using conservative quote-notional compatibility accounting:

- aggressive sells are compared only with displayed bid removal;
- aggressive buys are compared only with displayed ask removal;
- trade-compatible displayed removal is bounded by `min(depth_removed, aggressive_trade)` per side;
- unexplained displayed removal is retained only as `removal_candidate_residual_notional`;
- aggressive trade not matched by displayed removal is tracked separately;
- removal coverage is emitted only when displayed removal exists.

This layer does **not** claim cancellation, spoofing, replenishment, execution causality, support/resistance, or predictive direction.

## Fail-closed temporal and epistemic gates

`reconcile_depth_with_order_flow()` rejects or degrades state when:

- symbols differ;
- event timestamps are naive;
- alignment/window policies are non-finite or non-positive;
- observed notionals are negative or non-finite;
- depth elapsed time is invalid;
- stream end-times exceed the configured skew tolerance;
- aggregation windows exceed the configured duration tolerance.

When stream timing is misaligned, compatibility values and residuals are emitted as `None`, `evidence_eligible=false`, and `regime_eligible=false`.

Even when event timing is aligned, V1 remains `regime_eligible=false` because the current `DepthDynamics` / `OrderFlowState` pair does not yet carry complete cross-stream `available_at` / `fetched_at` provenance. Every state therefore includes `POINT_IN_TIME_PROVENANCE_INCOMPLETE`, `CAUSAL_ATTRIBUTION_UNPROVEN`, `causal_attribution_confirmed=false`, and `execution_weight=0.0`.

This prevents the new compatibility feature from entering point-in-time regime inference or backtests before provenance is complete.

## Implementation commits

- `d8e6e329cdd1e16e384afadf6d52571484bf66ed` — initial compatibility accounting.
- `ab221436b8a16637510779418f60f82b946c664c` — deterministic regression suite.
- `a235a20eee7465cf106d4a9e80b169a0beef68cd` — strict-input validation and removal of dynamic kwargs typing risk.
- `003e0a0faa458b1487159726e420f69b704c5d7e` — invalid observed-notional regression.
- `6a26703508c59de2070b16e1c555a22d21fa9d90` — explicit point-in-time regime ineligibility.
- `9fc9b6a648964090448d5ff6816b3de5ed7f29c7` — regression lock for provenance/regime boundary.

## Verification ledger

| Gate | Result | Evidence |
|---|---|---|
| Exact-head reconstruction | PASS | PR #13 `ca0187a...`; PR #15 `0d408ca...` before writes |
| Parent/child divergence inspection | PASS | child 26 ahead / 7 behind parent; merge base `b8143ce...` |
| Bounded implementation | PASS | six commits listed above |
| Targeted compile | PASS | isolated Python compile of the new compatibility module with interface-compatible local dataclass surfaces |
| Targeted deterministic logic harness | PASS | aligned compatibility, temporal skew fail-closed behavior, residual accounting, no-removal handling, symbol/timestamp/policy/input rejection |
| Latest fail-closed invariant harness | PASS | aligned state remains `regime_eligible=false`, `causal_attribution_confirmed=false`, `execution_weight=0.0`; misaligned state emits no compatibility values |
| Code review | PASS | removed dynamic `**dict` constructor pattern to reduce strict-mypy risk; validates all safety-critical scalar inputs |
| Security review | PASS | no credentials, private/account endpoints, order placement, wallet/custody/signing, leverage sizing, dynamic code execution, new network surface or dependencies |
| Causal-claim safety | PASS | compatibility-only terminology; no cancellation/spoofing attribution |
| Point-in-time promotion | BLOCKED | complete `available_at` / `fetched_at` provenance is not yet present for both paired streams |
| Full PR #15 pytest/coverage | NOT_RUN | no clean repository checkout in this runtime; no inferred PASS |
| PR #15 Ruff/mypy/Bandit | NOT_RUN | same constraint; no inferred PASS |
| Parent Ruff format | FAIL | run `35547315028`: 28 files remain |
| Parent downstream gates | NOT_RUN | blocked behind formatter gate |
| Probability calibration | BLOCKED | no leakage-safe walk-forward calibration evidence |
| Production readiness | BLOCKED | canonical live-history, calibrated model, immutable shadow period, SLO/restore and independent release review remain outstanding |

## Code / security / QA review

The compatibility computation is deliberately side-aware and bounded. It cannot manufacture more trade-compatible removal than either the displayed removal or aggressive trade observed on that side. Stream misalignment removes the derived numbers instead of carrying stale pairings forward.

The first implementation used a dynamic kwargs dictionary to reduce duplication. Review identified that pattern as unnecessary strict-typing risk, so the constructors were made explicit before checkpointing. Review also added finite/non-negative validation around observational notionals because the dataclasses themselves can be manually instantiated outside provider helpers.

The key remaining epistemic limitation is explicit rather than hidden: `OrderFlowState.observed_at` is only the latest observation timestamp and the compatibility call currently receives `flow_window_seconds` from the caller. Until both streams have immutable point-in-time provenance envelopes, this feature is descriptive shadow evidence only and must not feed regime probability or execution logic.

## Next convergence frontier

1. Complete PR #13's 28-file Ruff-format batch in a collision-safe environment, then spend at most one bounded FAST run to reveal the next real parent gate.
2. Add first/last observation plus `available_at` / `fetched_at` provenance to the depth and aggTrade stream envelopes; make cross-stream pairing derive its own window rather than trusting caller-supplied duration.
3. Promote trade-compatibility to `regime_eligible=true` only after those provenance gates pass and exact prediction-time availability is demonstrated.
4. Extend freshness alignment across depth, aggTrades, OI, funding and basis; stale/misaligned inputs must degrade to NO_DATA/MIXED.
5. Reconcile PR #15 onto a sufficiently green parent and run the full inherited verification gauntlet before any promotion.
6. Bayesian/posterior probabilities remain forbidden until point-in-time walk-forward calibration is evidenced.

## Rollback

Revert, newest first: `9fc9b6a648964090448d5ff6816b3de5ed7f29c7`, `6a26703508c59de2070b16e1c555a22d21fa9d90`, `003e0a0faa458b1487159726e420f69b704c5d7e`, `a235a20eee7465cf106d4a9e80b169a0beef68cd`, `ab221436b8a16637510779418f60f82b946c664c`, `d8e6e329cdd1e16e384afadf6d52571484bf66ed`.
