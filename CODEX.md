# CODEX EXECUTION BRIEF

## Objective

Integrate this package into the authoritative XRP repository through one reviewable PR without creating a duplicate architecture.

## Required workflow

1. Fetch and inspect the target repository.
2. Identify current package manager, Python version, persistence layer, tests and CI.
3. Produce a file-level merge map before modifying anything.
4. Create branch `feat/xrp-cross-asset-regime-engine` from the latest default branch.
5. Apply only compatible modules; adapt paths and conventions to the repository.
6. Preserve existing public APIs unless the PR explicitly documents a breaking change.
7. Run existing tests before changes and record baseline.
8. Run all existing and new tests after changes.
9. Run format, lint, type and security checks.
10. Generate a migration report and open a draft PR.

## PR title

`feat: add XRP cross-asset regime intelligence vertical slice`

## PR acceptance evidence

- deterministic demo output;
- test report;
- API contract examples;
- architecture diagram;
- data provider matrix;
- security notes;
- no secret material;
- explicit live-data blockers;
- rollback instructions.

## Forbidden actions

- force-pushing the default branch;
- deleting existing market logic without proof;
- adding auto-trading;
- silently changing model weights;
- committing generated databases, secrets or paid datasets;
- claiming live validation when only fixtures were used.
