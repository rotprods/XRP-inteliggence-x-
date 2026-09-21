# Production-Readiness Checklist

Production means a read-only intelligence service. Trading/custody remains out of scope.

## Governance

- [ ] Independent reviewer approved the release.
- [ ] Risk, licence, secrets and incident registers are current.
- [ ] Release and rollback artifacts are immutable and verifiable.

## Data

- [ ] Two or more independent spot providers per quote group.
- [ ] Regional availability and rate limits measured.
- [ ] Raw hashes, provenance and point-in-time availability retained.
- [ ] USD/USDT and calendar semantics validated.
- [ ] Partial outage, stale, disagreement and clock-skew drills PASS.

## Model

- [ ] Walk-forward and embargo evaluation PASS.
- [ ] Baselines, ablations and provider substitution documented.
- [ ] Probabilities calibrated and reliability curves acceptable.
- [ ] Confidence semantics exposed correctly.
- [ ] Thirty-day immutable shadow evaluation complete.

## Engineering and security

- [ ] Tests, coverage, lint, format, type, Bandit and dependency audit PASS.
- [ ] Container scan and SBOM complete.
- [ ] SSRF, payload, redaction and malformed-data tests PASS.
- [ ] No trading, signing, withdrawal or custody primitives.

## Operations

- [ ] Freshness, availability and snapshot-latency SLOs defined and measured.
- [ ] Metrics, alert acknowledgement and escalation configured.
- [ ] Backup and restore drill PASS.
- [ ] No-data and incident-banner states tested.

Any unchecked item keeps production status `BLOCKED`.
