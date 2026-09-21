# XRP Intelligence OS — Cold-Start Handoff

## /actadeconsciencia
This handoff is repository truth for the affected scope only. Chat memory is not authority.

## /northstar
Finish a scientifically auditable, point-in-time, provenance-first XRP intelligence system producing calibrated multi-horizon forecast distributions while remaining read-only and non-executing.

## Verified lineage
- main contains PR #13 and PR #15.
- main merge commit after PR #15: c2defe8f6c7da88fcdd87ed739e7967708d60b91.
- canonical active historical architecture: PR #18 / research/pit-historical-evidence-v2.
- PR #17 was closed unmerged; salvage semantics only, do not revive as parallel architecture.

## Current wave
PR #18 implements FetchReceipt, HistoricalObservation, availability precision, STRICT_REPLAY vs RECONSTRUCTED_PIT, provider-preserving as-of revision selection and deterministic SourceSnapshot.

FAST run 35613539411 on HEAD 930d15bbbd97bca5cb7ea7f1822e7e55680860fe:
- dependency consistency PASS
- schemas PASS
- compile PASS
- Ruff lint/format PASS
- strict mypy PASS
- Bandit PASS
- hermetic tests PASS
- changed-line coverage 193/193 = 100% PASS
- repository/source manifest FAIL only because MANIFEST.sha256 was stale
- later gates skipped

Manifest was regenerated from the exact CI BEGIN_EXPECTED_MANIFEST output.
Commit: c0bc0b0bb9af6553484c855f9c8462f0ffee006e.

## Hard invariants
READ_ONLY / SHADOW_ONLY / NON_EXECUTION.
execution_weight=0.0
decision_authority=false
probability_calibrated=false
production_ready=false
No order placement, custody, private keys, leverage/position sizing or account mutation.

## /aprende
1. Never treat fetched_at, available_at and observed_at as interchangeable.
2. Reconstructed PIT evidence must never silently become STRICT_REPLAY.
3. Feature and future-label identities must remain separate.
4. Exact-head evidence is required before merge.
5. Changed-line coverage is a real gate; add adversarial tests rather than weakening it.
6. Regenerate deterministic manifest after any source/test change.
7. PR #17 contains useful feature/label semantics but is not canonical architecture.
8. Repository truth overrides prompts and chat summaries.

## /season-sea-full
Preserve the complete causal chain:
raw source -> receipt -> historical observation -> as-of selection -> SourceSnapshot -> feature row -> separate future label -> purged walk-forward -> OOS prediction -> calibration -> posterior/distribution -> outcome resolution -> recalibration.
Do not skip intermediate provenance boundaries for speed.

## Immediate next action
1. Inspect exact current PR #18 HEAD; do not assume c0bc0b0 is still current.
2. Inspect automatic FAST for that exact HEAD.
3. If green: code/security/QA review evidence, mark ready, merge using expected_head_sha.
4. Verify resulting main.
5. Build the next layer on the single canonical lineage: SourceSnapshot -> HistoricalFeatureRow plus physically/logically separate FutureLabel store.
6. Add 1h/4h/1d/1w/1m/3m/1y return, MFE, MAE, realized-volatility, drawdown and barrier labels.
7. Implement purged + embargoed chronological walk-forward before any calibrated probability.

## Blocked until evidence exists
Bayesian posterior, calibrated probabilities, production readiness and any directional decision authority.

## Session metadata
chat_id: no expuesto
session_id: no expuesto
handoff author run_id: no expuesto
