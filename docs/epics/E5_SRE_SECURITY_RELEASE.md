# E5 — SRE, security and read-only release

## Objective

Make the intelligence service observable, recoverable and secure while preserving its non-custodial, non-executing boundary.

## Reliability

- idempotent scheduled jobs and job locks;
- retry queues and dead-letter records;
- provider availability, freshness and snapshot-latency SLOs;
- metrics endpoint and incident banner;
- backup policy and restore drills;
- schema migrations and rollback rehearsal.

## Security

- least-privilege read-only provider credentials;
- secret inventory and rotation procedure;
- log redaction;
- SSRF/allowlist enforcement;
- dependency, SAST and container scans;
- SBOM and signed build manifest;
- malformed payload, clock skew, partial outage and corruption drills;
- private security-advisory workflow.

## Acceptance criteria

- CI/build/security gates are green;
- production secrets are never present in Git, Drive documents or logs;
- SLO evidence covers the shadow period;
- restore and rollback are demonstrated;
- release artifacts have checksums and provenance;
- production API remains read-only and exposes uncertainty/data status;
- custody, signing and order execution remain out of scope.
