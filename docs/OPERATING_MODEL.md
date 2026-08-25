# Operating model

## Canonical surfaces

- **GitHub**: executable code, tests, CI, branches, pull requests, tags and releases.
- **Drive**: North Star, state, decisions, large research artifacts, datasets, handoffs and recovery packages.
- **Database/object storage**: raw and normalized observations, features, snapshots and shadow outcomes.
- **Chat**: temporary execution context only.

## Wave contract

Every execution wave must end with:

1. a single explicit mission;
2. code, data, research or infrastructure that can be inspected;
3. tests and evidence;
4. atomic commits and a PR or documented branch state;
5. reconciled tasks, decisions and blockers;
6. a handoff that another agent can resume without the original chat.

## Pull-request stack

- foundation and repository governance;
- provider assurance and normalized data contracts;
- macro/derivatives/XRPL ingestion;
- feature and regime engine;
- point-in-time history and calibration;
- immutable shadow operation;
- API, reporting and alerts;
- SRE, security and release automation.

Each PR must be independently reviewable and reversible. Large historical data is referenced by manifest rather than committed.

## Decision authority

A model or agent may propose and implement code, but it may not:

- represent an uncalibrated score as a guaranteed forecast;
- bypass provenance or confidence gates;
- add trading/custody functionality to this repository;
- rewrite past shadow predictions;
- promote a release without gate evidence.

## Production definition

Production means a stable **read-only intelligence service** with auditable data, calibrated uncertainty, provider/SLO evidence, incident response and rollback. It does not mean an autonomous trading system.
