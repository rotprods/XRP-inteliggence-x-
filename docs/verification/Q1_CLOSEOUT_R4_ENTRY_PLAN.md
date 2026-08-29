# Q1 Closeout and R4 Entry — Implementation Plan

## Mission

Promote the verified Q1 Verification OS into the canonical GitHub repository through one
reviewable commit and one bounded PR, then start R4 only after the engineering gate is proven.
The promotion must not recreate workflow amplification, generate paid API traffic, or blur
engineering quality with market validity.

## Hard constraints

- Canonical repository: `rotprods/XRP-inteliggence-x-`.
- Base branch: `main` at the verified README-only baseline until promotion.
- Active implementation branch: `feat/q1-verification-os`.
- Maximum open implementation PRs: one.
- Maximum workflow files: one.
- Standard GitHub-hosted Ubuntu runner only.
- No schedule, matrix fan-out, auto-retry, auto-merge, workflow-generated commit, release upload,
  paid provider call, trading, custody, signing, withdrawal, wallet seed or private-key surface.
- Repeated remote failure with the same root cause stops CI and returns remediation local-first.

## Stage C0 — Source and cost lock

1. Re-read remote `main`, branch refs, open PRs and active workflow runs.
2. Prove `main` has not changed from the recorded baseline.
3. Keep all implementation work local until the source tree, manifest and tests agree.
4. Estimate the only automatic run: one FAST PR run, budget <= 8 runner-minutes.

### Exit

- No queued/running workflows.
- No open competing PR.
- One canonical local source tree.

## Stage C1 — Evidence hygiene

1. Remove duplicate alpha-1 reports and generated demo outputs from source control.
2. Retain only current Q1 machine evidence, repository verification and concise test report.
3. Rebuild `release/MANIFEST.sha256` after the cleanup.
4. Keep runtime databases, coverage files, wheels, SBOMs and raw provider payloads outside Git.

### Exit

- No stale or contradictory release evidence.
- Manifest contains only canonical source and governance files.

## Stage C2 — Local verification

Required local checks:

```text
compile / AST
238 deterministic tests PASS
Hypothesis module present but clean-runner execution pending
network denied by default
paid API calls = 0
source manifest PASS
repository contract PASS
```

Clean-runner-only checks remain explicit, never represented as local PASS:

```text
Hypothesis generated corpus
Ruff + formatting
strict mypy
Bandit
independent diff coverage
pip-audit
CycloneDX SBOM
Python 3.11 / 3.12 / 3.13
mutation score >= 90%
clean wheel install
```

## Stage C3 — Atomic remote promotion

1. Reuse content-addressed Git blobs and trees already verified against the local tree.
2. Create the final release subtree and root tree.
3. Create one commit whose parent is the current `main` SHA.
4. Move only `feat/q1-verification-os` to that commit.
5. Do not touch `main`.

### Exit

- One remote implementation SHA.
- No `.bootstrap` or recovery workflows.
- Exactly one `ci.yml`.

## Stage C4 — Remote read-back

1. Fetch the branch recursively from GitHub.
2. Compare path inventory, file modes and Git blob SHAs with the local tree.
3. Recompute the SHA-256 source manifest from the remote contents.
4. Fail closed on any missing, extra or mismatched file.

### Exit

- Remote tree equals reviewed local tree.
- Manifest verification returns zero failures.

## Stage C5 — One PR and one FAST run

1. Open one draft PR from `feat/q1-verification-os` to `main`.
2. The PR body records scope, non-goals, evidence, cost boundary and rollback.
3. Permit the single pull-request FAST workflow run.
4. Record elapsed runner time and all gate outcomes.
5. Do not retry automatically.

### Exit

- FAST PASS, or FAIL_CLOSED with one root-cause report.

## Stage C6 — Controlled remediation

If FAST fails:

1. Reproduce locally.
2. Convert the defect into a regression test.
3. Produce one consolidated remediation commit.
4. Allow at most one further FAST run for the same wave.
5. A repeated same-root-cause failure quarantines remote CI.

## Stage C7 — Deep qualification and freeze

After FAST is stable:

1. Run DEEP manually: full Hypothesis, seed replay, independent diff-cover, audit, SBOM and
   Python 3.11/3.12/3.13.
2. Run RELEASE manually: mutation score >= 90%, reproducible wheels and clean wheel install.
3. Obtain independent review.
4. Configure `main` protection only after required checks are stable.
5. Freeze Q1 as the verification baseline.

## R4 entry gate

R4 may begin only when Q1 FAST is stable. R4 remains read-only and shadow-only.

### R4.0 — Provider registry and quote semantics

- Coinbase and Kraken for USD spot.
- Binance and KuCoin for USDT spot.
- USD and USDT never silently fused.
- XRPL methods restricted to the explicit read-only allowlist.

### R4.1 — Provider health recorder

Record provider, asset, timestamps, latency, status, payload SHA-256, schema validity, freshness,
failure class and adapter version for every probe.

### R4.2 — Fail-closed consensus

- fewer than two independent sources: no consensus;
- stale or future observation: no consensus;
- quote mismatch: no consensus;
- excessive spread: conflict;
- outlier: quarantine and recompute;
- provider duplication cannot increase independent source count.

### R4.3 — Seven-day regional shadow observation

Measure uptime, latency p50/p95/p99, freshness, rate limits, schema drift and substitution behavior.
No live market conclusion or alert is promoted before this evidence exists.

## Definition of done

Q1 closeout is complete only when:

- remote/local tree identity is proven;
- the single FAST run is green within budget;
- no paid API call or unexpected network test occurs;
- DEEP and RELEASE evidence is explicit;
- independent review and rollback are recorded;
- `main` protection is proven from a fresh read;
- production remains blocked until live-data, historical, calibration, shadow and SRE gates pass.
