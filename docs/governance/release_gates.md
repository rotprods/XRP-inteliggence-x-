# Release Gates

## Gate F0 — Canonical source

- one authoritative repository and branch;
- clean tree with no caches, databases or generated runtime state;
- manifest matches the committed source;
- rollback commit identified.

## Gate F1 — Engineering foundation

- compile PASS on supported Python versions;
- tests and branch coverage threshold PASS;
- Ruff, formatting, mypy and Bandit PASS;
- wheel build PASS;
- JSON schemas and compatibility tests PASS;
- one bounded manual CI workflow;
- read-only repository contract PASS.

## Gate D1 — Live provider plane

- at least two independent providers per quote group;
- USD and USDT kept separate;
- measured regional availability, latency, freshness and rate limits;
- provider substitution and partial-outage tests;
- immutable raw hashes and normalized provenance.

## Gate R1 — Historical research

- point-in-time datasets and licences approved;
- no future leakage or random time-series split;
- walk-forward and embargo tests;
- baselines, ablations, Brier score and reliability curves;
- model card and limitations updated.

## Gate S1 — Shadow operation

- at least 30 chronological days of immutable predictions;
- predictions cannot be rewritten after outcomes occur;
- provider incidents, false alerts and calibration drift measured;
- SLO, backup, restore and incident drills complete.

## Gate P1 — Read-only production

- all previous gates PASS;
- independent review complete;
- production checklist signed;
- no trading, custody or signing capability;
- alert and API outputs retain confidence, provenance and blocking state.

A lower gate may pass while production remains blocked. No demo result can satisfy R1, S1 or P1.
