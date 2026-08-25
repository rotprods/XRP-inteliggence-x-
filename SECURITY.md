# Security policy

## Supported versions

Only the latest tagged release and the active release-candidate branch receive security fixes. Alpha releases are not production-approved.

## Reporting

Use GitHub private security advisories for vulnerabilities. Do not open a public issue containing exploit details, API keys, wallet seeds, private keys, personal financial information or provider credentials.

## Security boundary

This repository is a read-only market-intelligence system. It must not implement trading, custody, wallet signing, private-key management, withdrawals or order execution. A change that introduces any such capability requires a separate repository, threat model, legal review and explicit approval.

## Provider credentials

- read-only scopes only;
- minimum privilege and provider-specific secrets;
- secrets stored in environment/repository secret stores, never Git or Drive prose;
- rotation and revocation procedures documented;
- secret values redacted from logs and exceptions.

## Data and network controls

- HTTPS allowlists for outbound provider calls;
- DNS/IP validation against loopback, private, link-local, multicast and reserved networks;
- bounded timeouts, response sizes and retries;
- schema validation before normalization;
- raw payload hashing and provenance;
- fail-closed behavior for stale, conflicting or insufficient data.

## Disclosure response

1. acknowledge the report;
2. reproduce and classify severity;
3. contain exposed credentials or endpoints;
4. patch on a private branch;
5. verify with regression/security tests;
6. publish an advisory and release notes when appropriate;
7. update the threat model and prevention controls.
