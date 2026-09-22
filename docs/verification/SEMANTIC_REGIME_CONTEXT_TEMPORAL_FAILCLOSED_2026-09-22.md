# Semantic Regime Context Temporal Fail-Closed Hardening — 2026-09-22

Status: **BOUNDED HARDENING COMPLETE ON ISOLATED CHILD · NOT PROMOTED**

## Cold-start live truth

- Repository: `rotprods/XRP-inteliggence-x-`
- Canonical base: `main@a9ad23126bcedfc6bec3a338693a3b1dace31236`
- Base tree: `d1ae1f00f3edc72dc0eee594928b908862ce3e00`
- Open PRs observed before mutation: **none**.
- Canonical #13 SemanticBrain/COS20D/Graphify and #15 microstructure/derivatives lineages are already merged; they were not duplicated or reopened.
- Historical-ingestion work is active separately. In particular, `fix/fetch-receipt-content-address-integrity-v1` was observed at `b89c0af428ba839e63cf8ca6d0b2b93fdf0eee62`, 22 commits ahead of the same `main` merge base and modifying historical/provider scopes. This wave intentionally did not touch those files.
- Isolation branch: `fix/semantic-regime-context-temporal-failclosed-v1`.
- Implementation/test head before this checkpoint: `5d26ff8c23ea20f0079817cf83319ba5065b77fd`.
- Mode remains **READ_ONLY / SHADOW_ONLY / NON_EXECUTION**.
- `production_ready=false`, `probability_calibrated=false`, `decision_authority=false`, narrative `execution_weight=0.0`.

## Defect

`build_regime_context()` previously filtered future evidence only when `available_at` was already a Python `datetime`. A serialized ISO-8601 timestamp, a missing timestamp, a malformed value or a naive timestamp could bypass the point-in-time gate and enter the semantic regime context.

That violated the repository's fail-closed temporal-availability law at the SemanticBrain → Regime Engine boundary, especially for reconstructed/serialized records such as index payloads.

## Bounded change

Changed only the SemanticBrain integration boundary and its targeted tests before this checkpoint:

- `src/xrp_regime_engine/semantic_brain/integration.py`
- `tests/semantic_brain/test_semantic_brain.py`

`_required_available_at()` now:

- accepts timezone-aware `datetime` values;
- parses ISO-8601 strings, including terminal `Z`;
- rejects missing/non-datetime/non-string values;
- rejects malformed ISO timestamps;
- rejects timezone-naive timestamps;
- allows the existing context builder to exclude evidence whose validated availability is after `decision_at`.

The existing contract that a naive `decision_at` is normalized to UTC is preserved. Narrative evidence remains non-directional and `narrative_execution_weight` remains exactly `0.0`.

Content SHA-256 for the two modified files at the implementation/test head:

- `integration.py`: `7a065fad86bef29a324633455b23282ed4b2dbd42e26c15ed6e5ff6cef60de6b`
- `test_semantic_brain.py`: `096fae507bd61385694a08a669afdffe30e033138aa7e43dc11885c7102cf2c7`

## Code / security / QA review

- CODE: **PASS (bounded review)** — one existing boundary hardened; no second SemanticBrain, Graphify, regime or provider architecture.
- TEMPORAL/PIT: **PASS for targeted invariant** — serialized future evidence is excluded and unknown/ambiguous availability fails closed.
- SECURITY: **PASS for bounded review** — no credentials, network, filesystem, subprocess, account mutation, signing, custody, order or leverage surface added.
- SOURCE INDEPENDENCE: **UNCHANGED** — no provider-count/fusion policy changed.
- NARRATIVE AUTHORITY: **UNCHANGED / PASS** — `execution_weight=0.0` preserved.
- Isolated compile/targeted invariant harness: **PASS**.
- Targeted harness result: **7 passed**.
- Remote workflow run for exact implementation/test head `5d26ff8c23ea20f0079817cf83319ba5065b77fd`: **none observed**.

## Canonical gate truth

- full repository compile: **NOT_RUN**
- Ruff lint/format: **NOT_RUN**
- strict mypy: **NOT_RUN**
- Bandit: **NOT_RUN**
- full hermetic pytest + branch coverage: **NOT_RUN**
- changed-line coverage: **NOT_RUN**
- deterministic source manifest: **NOT_RUN / expected stale**
- wheel: **NOT_RUN**
- DEEP: **NOT_RUN**
- RELEASE: **NOT_RUN**
- production: **BLOCKED**

No paid CI was triggered merely to create activity.

## Exact blocker

This runtime cannot materialize the repository from GitHub because outbound GitHub DNS/network access from the local execution container is unavailable. The canonical manifest generator, full local suite, Ruff, mypy and Bandit therefore could not be executed against the complete repository. Hand-editing the deterministic manifest without the canonical generator would weaken the verification contract, so it was intentionally not done.

Creating a PR was also deferred because it may trigger remote CI. A paid/external FAST run should not be spent until the complete local/canonical-equivalent gates and deterministic manifest are ready.

## Resume condition / next action

1. Cold-start again from live `main`, open PRs and this exact branch head; abort/reconcile if another writer has advanced the same SemanticBrain integration scope.
2. Materialize the full repository in a runtime with the dev toolchain.
3. Run format/lint, strict mypy, Bandit and the targeted/full hermetic tests locally.
4. Fix causal failures without weakening gates.
5. Regenerate `release/MANIFEST.sha256` with the canonical generator at the final candidate tree, including this checkpoint file.
6. Re-run local repository/manifest and wheel gates.
7. Only then open/reconcile a promotion PR and spend at most one bounded exact-head FAST verification run.
8. Keep the concurrent H7 historical-ingestion lineage separate; do not transplant or overwrite it from this branch.
9. Preserve production **BLOCKED** until scientific, DEEP/RELEASE, restore/SRE and independent-review gates pass.
