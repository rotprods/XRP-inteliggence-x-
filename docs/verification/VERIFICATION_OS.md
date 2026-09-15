# XRP Intelligence Engine — Verification & CI Excellence OS

**Program:** Q1 Verification Superwave
**Status:** IMPLEMENTATION ACTIVE
**Authority:** engineering verification only; production remains BLOCKED
**Repository:** `rotprods/XRP-inteliggence-x-`
**Execution model:** local-first → one clean branch → one PR → bounded CI → review → merge
**Financial boundary:** read-only intelligence; no trading, custody, wallet signing, withdrawals, private keys or paid market-data calls in CI.

---

## 1. North Star

Any materially incorrect change must have an extremely high probability of being rejected before it reaches `main`.

Coverage is evidence that code executed. It is **not** evidence that behavior is correct. The Verification OS therefore combines example tests, property invariants, mutation resistance, contract testing, temporal correctness, point-in-time research controls, fault injection, security testing, reproducible packaging, multi-runtime compatibility and cost-aware CI governance.

The target system distinguishes four independent quality domains:

1. **Engineering quality** — code compiles, types, packages and behaves according to contracts.
2. **Data quality** — evidence is fresh, complete, agreed and point-in-time valid.
3. **Predictive validity** — forecasts/scores survive leakage-safe historical and shadow evaluation.
4. **Production readiness** — operations, security, restore, SLOs and independent review pass.

Passing one domain never implies another.

---

## 2. Hard operating constraints

### 2.1 WIP

- Active implementation branch: **1**.
- Open implementation PRs: **1**.
- CI workflow files during Q1: **1**.
- Scheduled workflows: **0** until shadow mode.
- Auto-merge: **forbidden**.
- Workflow-generated commits: **forbidden**.
- CI mutation of repository state: **forbidden**.

### 2.2 Cost guardrail

CI cost is a P0 engineering constraint.

- Standard Linux runners only.
- Larger/GPU/macOS/Windows runners: prohibited unless separately approved.
- Paid API calls in CI: **0**.
- Live provider tests in automatic CI: **0**.
- FAST profile target: **<8 runner-minutes**.
- DEEP profile target: **<30 runner-minutes**.
- RELEASE profile target: **<45 runner-minutes**.
- Artifacts are retained only when they provide release evidence, and with the shortest useful retention.
- Any unexplained CI fan-out, matrix expansion, child workflow, recursive dispatch or retry loop is a STOP-THE-LINE event.

### 2.3 Circuit breakers

- Two remote failures with the same root cause → stop remote retries and reproduce locally.
- More than ten workflow runs in one hour → quarantine automatic triggers.
- Any workflow-created commit → quarantine CI.
- Any unexpected paid API call → quarantine CI and revoke/rotate affected key.
- Any mismatch between reviewed local tree and remote tree → block merge.

---

## 3. Test taxonomy

Every test belongs to an explicit class:

| Marker | Purpose | Network | FAST | DEEP | RELEASE |
|---|---|---:|---:|---:|---:|
| `unit` | deterministic isolated behavior | denied | yes | yes | yes |
| `property` | generated invariants | denied | core | yes | yes |
| `contract` | schemas/provider/API contracts | denied | yes | yes | yes |
| `integration` | multiple internal components | denied | selected | yes | yes |
| `temporal` | timestamp/cadence/revision correctness | denied | core | yes | yes |
| `storage` | persistence/idempotency/fault behavior | denied | selected | yes | yes |
| `security` | adversarial boundaries | denied | core | yes | yes |
| `api` | HTTP contract and degraded states | denied | yes | yes | yes |
| `research` | walk-forward/leakage/calibration controls | denied | core | yes | yes |
| `packaging` | clean install/reproducible artifacts | denied | smoke | yes | yes |
| `slow` | expensive deterministic suites | denied | no | optional | yes |
| `live` | real provider verification | explicit manual only | no | no | separate gate |

Automatic tests are hermetic. A test that accidentally opens a socket is a failure, not a flaky infrastructure event.

---

## 4. Deterministic test environment

Default test runtime:

- timezone: UTC;
- locale: deterministic/default UTF-8 environment;
- `PYTHONHASHSEED=0` in CI;
- explicit random seed recorded for fuzz/replay;
- temporary DB/filesystem per test;
- proxy inheritance disabled;
- credential environment scrubbed unless a test explicitly injects a fake value;
- outbound network denied by default;
- no global mutable test state;
- no test ordering dependency;
- no retry-until-green plugin.

A failing randomized test must report a replayable seed/example.

---

## 5. Coverage policy

Coverage thresholds are risk-weighted.

### Global

- line coverage: **>=95%**;
- branch coverage: **>=92%**.

### Critical modules

Critical modules include:

- `models.py`;
- `consensus.py`;
- `features.py`;
- `regime.py`;
- `backtest.py`;
- `storage.py`;
- `api.py`;
- `providers/base.py`;
- provider adapters promoted to canonical live status.

Targets:

- critical line coverage: **>=98%** where feasible;
- critical branch coverage: **>=95%**;
- changed executable lines: **100%** coverage.

Global coverage can never compensate for a weak critical module.

---

## 6. Property-based testing

Hypothesis-generated tests verify invariants, not specific examples.

Mandatory properties include:

- `0 <= confidence <= 1`;
- `0 <= bull_score <= 100`;
- `0 <= bear_score <= 100`;
- `bull_score + bear_score == 100` within numeric tolerance;
- NaN/Inf never pass validated market contracts;
- OHLC geometry is preserved;
- negative volume is rejected;
- one provider never yields valid independent consensus;
- reordering providers cannot change a valid median consensus;
- duplicating one provider cannot increase independent-provider count;
- USD and USDT cannot be fused silently;
- stale/future observations cannot become valid live evidence;
- missing values are not silently reinterpreted as zero;
- score/config hashing is deterministic and input-sensitive.

---

## 7. Provider contract gauntlet

Every provider promoted beyond prototype status receives frozen fixtures for:

- normal response;
- missing field;
- explicit null;
- wrong type;
- HTTP 400/401/403/404;
- HTTP 429 and `Retry-After`;
- HTTP 500/502/503;
- timeout/connect error;
- HTML or wrong content type;
- malformed JSON;
- oversized body and invalid content length;
- future timestamp;
- stale timestamp;
- duplicate candles;
- out-of-order candles;
- negative volume;
- invalid OHLC geometry;
- unexpected symbol;
- USD/USDT mismatch;
- schema drift.

Providers initially covered: Coinbase, Kraken, Binance, KuCoin when canonical, XRPL and FRED/ALFRED.

CI uses fixtures/mock transports only. Real providers are exercised exclusively by a separate manual live-validation gate.

---

## 8. Temporal correctness gauntlet

`observed_at`, `available_at` and `fetched_at` are separate concepts and must remain separate in code, storage and research.

Tests cover:

- naive timestamps;
- timezone conversion;
- out-of-order inputs;
- duplicate timestamps;
- DST boundaries;
- leap day;
- future observations;
- `available_at > decision_time`;
- revised macro values;
- missing/low-precision release time;
- stale market candles;
- cadence/horizon mismatch;
- silent forward-fill across unknown release boundaries.

A point-in-time backtest must fail if future information is injected.

---

## 9. Research/backtest integrity

Allowed evaluation:

- expanding walk-forward;
- rolling walk-forward;
- explicit embargo;
- train-only transforms/calibration;
- point-in-time dataset versions;
- versioned provider universe;
- immutable dataset/config/model digests.

Forbidden:

- random train/test split for time series;
- transforms fit on future/test rows;
- latest revised macro values substituted into historical decisions;
- future-derived feature columns;
- silent fill across unknown information boundaries.

The suite includes a **leakage canary**: an intentionally future-derived feature must be detected/rejected by the research validation layer.

---

## 10. Storage fault injection

Persistence must survive or fail safely under:

- duplicate writes;
- idempotent retries;
- transaction rollback;
- corrupt SQLite file;
- locked database;
- concurrent reads;
- bounded concurrent writes;
- partial transaction exception;
- schema-version mismatch;
- malformed/truncated JSON;
- backup/restore;
- checksum mismatch;
- disk/write exception simulation.

Restore is not complete until checksums, schema version, record counts and representative snapshots are verified.

---

## 11. API contract testing

Versioned API surfaces receive golden/schema tests for:

- `/health`;
- `/ready`;
- regime snapshots;
- explanation;
- provider health;
- consensus/audit when promoted.

Required behavior:

- 200 healthy/readable;
- 503 no-data or operationally blocked readiness;
- 404 absent resource where semantically appropriate;
- 4xx invalid request;
- exact JSON/content type;
- no secrets;
- no traceback leakage;
- stable versioned response contracts;
- blocked/degraded state cannot masquerade as healthy output.

---

## 12. Security/adversarial testing

Automatic tests attempt:

- localhost/private/link-local/multicast/reserved IP access;
- cloud metadata endpoints;
- DNS resolution to non-public addresses;
- redirects to private infrastructure;
- credentials embedded in URLs;
- malformed DNS response;
- oversized payloads;
- secret leakage through exception/log text;
- forbidden XRPL RPC methods;
- forbidden source primitives for trade/order/sign/withdraw/custody/private-key behavior.

High/critical findings block promotion.

---

## 13. Mutation testing

Mutation testing answers whether tests detect incorrect code, not merely execute it.

Targets:

- critical-module mutation score: **>=90%**;
- selected overall mutation score: **>=80%**.

Mutation testing runs only in DEEP/RELEASE profiles because of cost. Surviving meaningful mutants become explicit regression tests or documented equivalent-mutant exclusions.

---

## 14. Packaging and reproducibility

Release verification:

1. clean source tree;
2. build wheel A;
3. clean build state;
4. build wheel B;
5. require identical SHA-256;
6. install wheel into a fresh virtual environment;
7. import package;
8. run CLI doctor/help;
9. run schema export and API smoke;
10. validate source manifest;
11. generate SBOM;
12. run dependency audit.

The deployed artifact must be the artifact that passed verification.

---

## 15. Python compatibility

- FAST: Python 3.11.
- DEEP/RELEASE: Python 3.11, 3.12 and 3.13.
- No automatic matrix fan-out until cost and flake stability are demonstrated.

---

## 16. Unified CI profiles

One workflow file implements three bounded profiles.

### FAST

Runs on reviewed PR changes once the foundation is stable:

- repository contract;
- compile;
- Ruff lint/format;
- strict mypy;
- unit tests;
- core property tests;
- contracts;
- temporal/security core;
- global + critical-module coverage;
- changed-line coverage;
- packaging smoke.

### DEEP

Manual only. Adds:

- complete property suite;
- provider fixture gauntlet;
- storage fault injection;
- research/leakage suite;
- multi-Python compatibility;
- dependency audit;
- SBOM;
- repeated-seed flake detection.

### RELEASE

Manual only. Adds:

- mutation testing;
- reproducible double build;
- fresh-venv wheel install;
- restore drill;
- schema/manifest full comparison;
- release evidence bundle.

No profile writes implementation code, commits, creates PRs, merges or publishes a release automatically.

---

## 17. Flake policy

Flaky tests are defects.

- No retry-until-green behavior.
- Critical corpus is replayed with multiple seeds in DEEP/RELEASE.
- Any nondeterministic failure blocks release until reproduced and fixed.
- Failing seeds/examples are persisted in quality evidence.

---

## 18. Machine-readable quality evidence

Every controlled verification run emits a single quality record containing at least:

```json
{
  "tests": 0,
  "failed": 0,
  "line_coverage": 0.0,
  "branch_coverage": 0.0,
  "critical_branch_coverage": 0.0,
  "changed_line_coverage": 0.0,
  "mutation_score": null,
  "mypy_errors": 0,
  "ruff_errors": 0,
  "security_high_critical": 0,
  "unexpected_network_calls": 0,
  "paid_api_calls": 0,
  "flake_failures": 0,
  "wheel_reproducible": false,
  "python_versions": [],
  "runner_minutes": null
}
```

A green badge without evidence is insufficient.

---

## 19. Branch protection target

After FAST CI is stable:

- PR required for `main`;
- direct and force push disabled;
- conversation resolution required;
- required FAST quality check;
- CODEOWNERS review for provider, regime, backtest, config, workflow and release surfaces;
- release gates remain manually approved.

---

## 20. Q1 implementation graph

1. Q1.0 — cost/source lock.
2. Q1.1 — persist this canonical spec.
3. Q1.2 — hermetic pytest architecture.
4. Q1.3 — global/critical/changed-line coverage gates.
5. Q1.4 — property-based tests.
6. Q1.5 — provider contract gauntlet.
7. Q1.6 — temporal correctness.
8. Q1.7 — backtest leakage canaries.
9. Q1.8 — storage fault injection.
10. Q1.9 — API contracts.
11. Q1.10 — adversarial security.
12. Q1.11 — mutation testing.
13. Q1.12 — reproducible builds/SBOM/audit.
14. Q1.13 — Python 3.11/3.12/3.13.
15. Q1.14 — unified CI profiles.
16. Q1.15 — flake detection/seed replay.
17. Q1.16 — machine-readable evidence.
18. Q1.17 — adversarial code review.
19. Q1.18 — one clean Verification OS PR.
20. Q1.19 — `main` branch protection.
21. Q1.20 — freeze the Q1 release gate.

Todoist execution surface: section **XRP Intelligence Engine — Verification OS** in `Ecosistema rotprods Perfeccion`.

---

## 21. Definition of Done

Q1 is complete only when the evidence demonstrates:

- all required tests PASS;
- global line coverage >=95%;
- global branch coverage >=92%;
- critical branch coverage >=95%;
- changed executable line coverage =100%;
- critical mutation score >=90%;
- Ruff errors =0;
- Ruff format diff =0;
- strict mypy errors =0;
- Bandit high/critical =0;
- dependency critical vulnerabilities =0 or explicitly blocked/accepted with rationale;
- provider contract gauntlet PASS;
- temporal gauntlet PASS;
- leakage canary rejected correctly;
- storage fault-injection PASS;
- API contracts PASS;
- reproducible wheel PASS;
- Python 3.11/3.12/3.13 PASS;
- unexpected network calls =0;
- paid API calls =0;
- flaky failures =0;
- remote/local tree reconciliation PASS;
- branch protection active;
- production status remains BLOCKED until data, calibration, shadow and operations gates are separately satisfied.


---

## 22. Execution checkpoint — 2026-08-28

Current local Q1 evidence after the first implementation pass:

- 238 tests PASS; Hypothesis property module is skipped locally because the offline runtime cannot install Hypothesis.
- Global line coverage: 100%.
- Global branch coverage: 100%.
- Critical-module line/branch coverage: 100% / 100%.
- Changed executable line coverage: 100%.
- Provider contract coverage includes Coinbase, Kraken, Binance, KuCoin, FRED and XRPL.
- KuCoin Unified API adapter is implemented with USDT-only quote semantics.
- Temporal contracts cover timezone-aware indexes, duplicates, revisions, availability and horizon/cadence mismatch.
- Backtest research supports expanding/rolling windows, embargo and point-in-time availability filtering.
- Storage fault suite covers transaction rollback, corruption, locking, schema failure and backup/restore.
- Hermetic test runtime denies unexpected network access and scrubs proxy/secret environment variables.
- Three deterministic shuffled-seed replays pass without flakes.
- Reproducible final `0.2.0a2` wheel: PASS with two byte-identical builds; SHA-256 `4e6a21a17d041f5f3ef21dd237c11fd268a6d77531e52c6de1c4a9e0d1851f9b`. Local wheel import and CLI smoke using the host dependency set also PASS.

Still pending and therefore **not** claimed as PASS:

- actual Hypothesis execution on a clean network-enabled dependency-install runner;
- Ruff and Ruff format;
- strict mypy;
- Bandit;
- mutation testing;
- pip-audit and reproducible CycloneDX SBOM generation;
- Python 3.11/3.12/3.13 compatibility;
- remote clean PR and bounded CI run;
- main branch protection.

Cost rule for the remaining remote gate: one standard Ubuntu runner job, no matrix, no paid provider calls, no larger runner, no artifact upload, no recursive retries. DEEP uses three randomized seed replays, not five, to keep the cost bound deterministic.

- Local Q1 implementation commit: `7b60d76c9c96a6a19381d40f47f5ebd4ea00b16d`.
