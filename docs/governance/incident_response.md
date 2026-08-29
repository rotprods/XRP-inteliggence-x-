# Incident Response

## Severity

| Level | Definition | Examples | Response target |
|---|---|---|---|
| SEV-0 | Financial execution or secret compromise | Trading permission introduced; private key exposed | Immediate shutdown and credential revocation |
| SEV-1 | Materially misleading output or integrity failure | Cross-quote corruption; future leakage; tampered shadow ledger | Quarantine outputs within 15 minutes |
| SEV-2 | Major data/service degradation | Multiple providers down; database write failure | Triage within 1 hour |
| SEV-3 | Limited defect without invalidating published outputs | One fallback provider degraded; dashboard defect | Triage within 1 business day |

## Response sequence

1. **Detect:** record timestamp, affected version, provider/horizon and evidence hashes.
2. **Contain:** block affected outputs and alerts; revoke credentials if relevant.
3. **Preserve:** retain logs, raw payload hashes, database copy and commit SHA.
4. **Diagnose:** distinguish provider, code, data-contract, model and infrastructure failure.
5. **Recover:** restore to a clean path or roll back to the last verified commit.
6. **Validate:** replay affected inputs and run the relevant release gate.
7. **Communicate:** update incident banner, state and owner.
8. **Learn:** publish a blameless post-incident report and preventive task.

## CI amplification circuit breaker

- More than 10 runs in one hour: disable all automatic triggers.
- Two failures with the same root cause: stop remote retries and reproduce locally.
- A workflow that commits code, creates workflows or starts recursive controllers: quarantine immediately.
