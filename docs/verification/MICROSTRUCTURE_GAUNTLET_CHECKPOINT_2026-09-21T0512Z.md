# Microstructure Gauntlet Checkpoint — 2026-09-21T05:12Z

## Scope

Bounded read-only integration wave on PR #15 (`feat/binance-microstructure-v1`). This wave routes temporal-window construction through the existing cross-stream point-in-time/provenance gate before any window can become evidence-eligible. No trading, order placement, credentials, private endpoints, custody, signing, withdrawals, leverage sizing, calibrated probability, or production promotion was added or authorized.

## Persistent truth inspected before change

- Parent PR #13: OPEN / DRAFT / mergeable at exact HEAD `ca0187a477ce587153ec9919b727a998e7878e7d`.
- Parent FAST run `35547315028`, job `106175441465`: dependency consistency PASS, schema reproduction PASS, compile PASS, Ruff lint PASS, Ruff format FAIL; downstream strict mypy, Bandit, hermetic tests/coverage, repository/source-manifest contracts and wheel build remain NOT_RUN/SKIPPED.
- PR #15 pre-wave exact HEAD: `581ce3c2159143c4031a994ab7795207de28bc1c`, OPEN / DRAFT / mergeable.
- Exact parent/child comparison before this wave: child 52 commits ahead / 7 behind parent, merge base `b8143ce873f9b3469c2cd78ed1d5389a1c0f1989`.
- Exact PR #15 pre-wave HEAD had no associated pull-request workflow run.
- Existing `assess_cross_stream_alignment()` already failed closed for missing, stale, future-fetched, provenance-incomplete, symbol-mismatched and excessively skewed streams, but temporal-window construction was still callable independently.

## Implemented

### 1. Cross-stream-gated temporal construction

Added `src/xrp_regime_engine/temporal_alignment.py` with `AlignedTemporalWindow` and `build_aligned_temporal_window()`.

The integration path now performs:

1. `assess_cross_stream_alignment()` over displayed-depth dynamics, aggregate-trade flow, funding/basis and open interest;
2. immediate fail-closed return with `window=None` when cross-stream evidence eligibility fails;
3. only then `build_temporal_window()` for the requested point-in-time horizon;
4. rejection of temporal-window symbol mismatch against the aligned stream symbol;
5. suppression of sparse, stale or excessive-ingestion-lag windows from downstream evidence exposure;
6. explicit `execution_weight=0.0` at the integration boundary.

Passing this gate means only that the temporal window is eligible for later shadow evidence construction. It does not authorize a regime label, probability, trade, position size or order.

### 2. Regression coverage

Added `tests/test_temporal_alignment.py` covering:

- complete aligned streams expose an eligible temporal window;
- incomplete derivative provenance blocks the window and preserves funding/basis provenance flags;
- a sparse temporal window remains blocked even after cross-stream alignment passes;
- temporal-sample symbol mismatch fails closed.

### 3. Formatting preflight

The new source and test files were syntax-compiled locally. Two >88-character source lines found during preflight were wrapped before checkpoint persistence; the new files have no remaining >88-character lines under the same simple length preflight.

## Code / security review

PASS for this bounded scope:

- composition only over existing read-only observation classes;
- no execution, order, account, wallet, signing, custody, withdrawal or leverage capability added;
- no credentials or private Binance endpoints introduced;
- blocked provenance never exposes a temporal window;
- symbol mismatch fails closed;
- sparse/stale/lagged temporal windows are not evidence-eligible;
- no Bayesian/posterior probability or calibrated prediction added;
- `execution_weight=0.0` remains explicit.

## Targeted QA evidence

Available local-equivalent evidence:

- Python syntax compilation for the new module and test file: PASS;
- targeted gate-behavior harness: PASS, 4 checks covering blocked alignment, sparse-window suppression, eligible-window pass-through and symbol-mismatch failure;
- exact repository pytest suite: NOT_RUN;
- Ruff executable: unavailable in this runtime, so full Ruff lint/format remains NOT_RUN for PR #15;
- strict mypy: NOT_RUN;
- Bandit: NOT_RUN;
- no CI workflow was manually started merely to create evidence.

## Newly surfaced deterministic repository-contract blocker

`release/MANIFEST.sha256` on PR #15 does not contain existing PR #15-added source paths such as `src/xrp_regime_engine/microstructure.py`, and it also does not contain the new `src/xrp_regime_engine/temporal_alignment.py`. `scripts/build_manifest.py` includes all repository files except explicitly excluded generated/runtime paths, and `scripts/verify_repository.py` requires the checked-in manifest to equal a freshly rendered manifest.

Therefore the repository/source-manifest gate is deterministically stale on the current child branch even though that CI step has not yet run. Do not regenerate the child manifest before parent reconciliation: PR #15 is seven commits behind PR #13, and the parent formatter wave has itself changed files whose hashes participate in the manifest.

## Evidence state

- PASS — temporal construction is now routed through the cross-stream eligibility gate.
- PASS — blocked alignment cannot expose a downstream temporal window.
- PASS — sparse/stale/lagged temporal windows remain fail-closed at the integration boundary.
- PASS — symbol mismatch fails closed.
- PASS — targeted 4-check gate-behavior harness.
- PASS — bounded manual code/security review.
- PASS — new-file syntax and simple line-length preflight.
- NOT_RUN — full PR #15 pytest + branch coverage.
- NOT_RUN — Ruff lint / Ruff format for PR #15.
- NOT_RUN — strict mypy for PR #15.
- NOT_RUN — Bandit for PR #15.
- FAIL (deterministic static proof) — current PR #15 release manifest is stale relative to branch-visible source files.
- FAIL — parent PR #13 Ruff format gate remains the latest authoritative parent CI failure.
- BLOCKED — reconciliation/promotion of PR #15 until parent verification converges.
- BLOCKED — manifest regeneration until child is reconciled onto the exact sufficiently-green parent HEAD.
- BLOCKED — Bayesian/posterior probability calibration.
- BLOCKED — production readiness.

## Exact commits in this wave before checkpoint

- `60c031b50ae5dc4a13ec62a2f944c70f65ce4509` — add cross-stream-gated temporal integration;
- `f1cc90077994951e7f5c97f70766e8e31273da78` — add regression coverage;
- `3413e26f94b9f5ab071f0c29a4d25760dea67fd9` — preformat integration source after local line-length review.

## Next highest-value sequence

1. Finish the parent PR #13 Ruff-format convergence without weakening policy and reveal the next authoritative gate.
2. Reconcile PR #15 onto that exact parent HEAD rather than continuing long-lived divergence.
3. Regenerate `release/MANIFEST.sha256` only after reconciliation, then run the inherited repository/source-manifest contract.
4. Run the full inherited PR #15 gauntlet: Ruff, strict mypy, Bandit, hermetic tests/coverage, repository contracts and wheel build.
5. Only after those gates are green, construct an uncalibrated evidence vector from the aligned temporal layer. Bayesian/posterior probabilities remain forbidden until leakage-safe point-in-time walk-forward calibration is evidenced.
