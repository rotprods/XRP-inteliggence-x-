# DatasetVersion Content-Address Integrity Checkpoint — 2026-09-21

## Scope

Bounded post-merge hardening of merged PR #22. This wave does not add trading, order execution, account mutation, custody, signing, private keys, withdrawals, leverage or position sizing. The project remains READ_ONLY / SHADOW_ONLY / NON_EXECUTION with `execution_weight=0.0`, `decision_authority=false`, `probability_calibrated=false`, and `production_ready=false`.

## Live repository truth at claim

- canonical `main`: `3b739b567fa8866a9290c2488e032cfb16c78acc` (merged PR #22)
- branch: `fix/dataset-version-content-address-integrity-v1`
- branch base: exact `main@3b739b567fa8866a9290c2488e032cfb16c78acc`
- implementation HEAD before this checkpoint: `595ebf155c8a4ca5a99bc984e739c9e963bdd063`
- open active scopes observed: PR #24 OOS ledger content-integrity hardening and PR #25 baseline skill gate
- neither active PR modifies `dataset_version_v1.py` or `test_dataset_version_v1_edges.py`; this scope is file-isolated from those writers

## Defect found

PR #22 correctly generated a deterministic `dataset_version_id` / `dataset_sha256` in `build_dataset_version`, but direct construction or `dataclasses.replace()` only validated digest syntax. A caller could retain an old syntactically valid digest while changing content-bearing fields such as `dataset_key`, or replace both ID and digest with another valid SHA-256, and the frozen dataclass would accept an identity that did not match its canonical payload.

That violated the H4 requirement that DatasetVersion be an immutable content-addressed research artifact and created a lineage-integrity gap similar to the OOS ledger issue being hardened independently in PR #24.

## Bounded change

`src/xrp_regime_engine/dataset_version_v1.py` now:

- requires `dataset_version_id == dataset-version:sha256:<dataset_sha256>`;
- recomputes the canonical DatasetVersion payload digest inside `__post_init__` and fails closed if it differs from `dataset_sha256`;
- requires manifest IDs and partition IDs to retain the canonical sorted ordering emitted by the builder, preventing alternate order-dependent identities for the same logical members.

`tests/test_dataset_version_v1_edges.py` now:

- constructs its baseline version through the canonical builder rather than with a forged fixture digest;
- rejects ID/digest disagreement;
- rejects a mutually consistent but forged ID+digest pair;
- rejects content mutation (`dataset_key`, `total_rows`) that retains the old content address.

## Review

- code review: PASS by bounded inspection; the new digest material matches the existing builder material field-for-field and uses the existing canonical JSON serializer;
- security review: PASS by bounded inspection; no network, filesystem, subprocess, secrets, credentials, permissions or execution surfaces added;
- temporal/PIT review: PASS by bounded inspection; no availability semantics, cutoff classification or reconstruction rules weakened;
- provenance review: PASS by bounded inspection; change strengthens DatasetVersion lineage by binding the advertised identity to the exact canonical payload;
- active-scope collision review: PASS at file scope; PR #24 and PR #25 modify disjoint implementation/test files.

## Verification evidence

- exact branch lineage vs base: PASS — branch is directly ahead of `main@3b739b567fa8866a9290c2488e032cfb16c78acc` only by this bounded scope;
- automated FAST: NOT_RUN — no PR was opened and no remote CI was consumed merely to create activity;
- compile/Ruff/mypy/Bandit/hermetic pytest/changed-line coverage/wheel: NOT_RUN in this connector-only runtime;
- deterministic source manifest: intentionally NOT_UPDATED yet because active PR #25 also modifies `release/MANIFEST.sha256`; updating it now would create avoidable shared-file collision. This branch must remain unpromoted until it is reconciled after active parent scopes settle.
- DEEP/RELEASE: NOT_RUN.

## Promotion status

BLOCKED from merge until all canonical FAST gates pass on the exact reconciled HEAD and `release/MANIFEST.sha256` is regenerated after active scopes settle. Do not weaken thresholds and do not merge this branch around a stale manifest.

## Next exact action

1. Re-read `main`, PR #24 and PR #25 exact heads; if either merged, rebase/recreate this tiny patch onto the new canonical main rather than stacking stale history.
2. Confirm no newer DatasetVersion integrity fix supersedes this branch.
3. Regenerate the deterministic source manifest only after the code/test/checkpoint set and parent lineage are stable.
4. Open one draft PR, execute one bounded FAST run, and remediate only the first evidence-backed failing gate.
5. Require compile, Ruff lint/format, strict mypy, Bandit, hermetic tests, 100% changed-line coverage, repository/source-manifest contracts and wheel PASS before any merge decision.
6. Preserve `production_ready=false` and uncalibrated/non-executing semantics regardless of engineering PASS.
