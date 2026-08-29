# HANDOFF — Q1 Verification OS

## Identity

- Project: XRP Cross-Asset Regime Engine
- Engineering package: `0.2.0a2`
- Authority: `SHADOW_ONLY`
- Canonical verification spec: `docs/verification/VERIFICATION_OS.md`
- Local branch: `feat/q1-verification-os`
- Verified Q1 implementation commit: `7b60d76c9c96a6a19381d40f47f5ebd4ea00b16d`
- GitHub target: `rotprods/XRP-inteliggence-x-`
- Remote `main` baseline: `05cf97517bee99f70b4216ff8823c237a9d5c6bf`

## Resume sequence

1. Read `GOAL.md`.
2. Read `STATE.md`.
3. Read `docs/verification/VERIFICATION_OS.md`.
4. Read `docs/verification/Q1_CLOSEOUT_R4_ENTRY_PLAN.md`.
5. Read Q1 section in `TASKS.md`.
6. Run `python -m compileall -q src tests scripts`.
7. Run the hermetic pytest/coverage gate.
8. Run `scripts/check_coverage_policy.py` and `scripts/check_changed_line_coverage.py`.
9. Run `scripts/build_manifest.py --check` and `scripts/verify_repository.py`.
10. On a network-capable clean runner, execute Ruff, mypy, Bandit, Hypothesis, dependency audit, SBOM, multi-Python and mutation gates.
11. Promote only as one clean PR; never rebuild via GitHub Actions.

## Verified locally

- 238 deterministic tests PASS; one property module is skipped only because Hypothesis is unavailable in this offline runtime.
- 100% line and branch coverage over the application package.
- 100% coverage for every configured critical module.
- 100% changed executable line coverage against the forensic baseline.
- unexpected network denied during tests.
- provider failure/adversarial contracts including KuCoin Unified API fixtures.
- point-in-time availability, rolling/expanding walk-forward and embargo semantics.
- SQLite leak regression, corruption, rollback, backup and restore tests.
- deterministic package build mechanism.

## Remote-only/manual gates

- Hypothesis generated examples.
- Ruff + format.
- strict mypy.
- Bandit.
- diff-cover independent cross-check.
- pip-audit and CycloneDX SBOM.
- Python 3.11/3.12/3.13.
- mutmut release gate.

## Cost rules

- one workflow file;
- PR FAST profile + manual DEEP/RELEASE only;
- standard `ubuntu-latest` only;
- no matrix fan-out;
- no scheduled workflow;
- no paid API calls;
- no automatic retries;
- repeated same-root-cause CI failure stops remote execution and returns remediation local-first.

## Do not confuse gates

Engineering verification PASS does not imply calibrated prediction or production readiness. Production remains BLOCKED until live-data, historical, calibration, shadow and SRE gates independently pass.
