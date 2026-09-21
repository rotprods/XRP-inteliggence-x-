# Pull Request Plan

## Branch

`feat/xrp-cross-asset-regime-engine`

## Commit sequence

1. `chore: add XRP engine control plane and package metadata`
2. `feat: add canonical data models and SQLite storage`
3. `feat: add public market and XRPL provider adapters`
4. `feat: add cross-asset feature and regime engines`
5. `feat: add API CLI alerts and deterministic demo`
6. `test: add consensus scoring storage and API coverage`
7. `docs: add architecture model card runbook and threat model`
8. `ci: add Python test and manifest workflow`

## Review order

1. Architecture and repository compatibility.
2. Data semantics and point-in-time correctness.
3. Scoring logic and limitations.
4. Security and secrets.
5. Tests and operational evidence.
