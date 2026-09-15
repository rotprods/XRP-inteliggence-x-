# Threat Model

## Assets

- provider credentials;
- model configuration and weights;
- historical datasets and licences;
- audit integrity;
- alert destinations;
- future execution boundaries.

## Threats

- poisoned or malformed provider payloads;
- stale or compromised APIs;
- SSRF and DNS rebinding through configurable endpoints;
- redirects to private infrastructure;
- secret leakage through URLs, errors or logs;
- oversized payload exhaustion;
- rate-limit cascades;
- dependency compromise;
- alert spam or suppression;
- unreviewed weight manipulation;
- point-in-time leakage;
- semantic mixing of USD and USDT;
- unauthorized expansion from market data into trading permissions;
- recursive CI/workflow amplification.

## Implemented controls

- HTTPS and explicit provider-host allowlists;
- rejection of credentials in base URLs;
- public-IP DNS validation in non-mocked execution;
- no redirects and no environment proxy inheritance;
- bounded timeout, attempts and response bytes;
- `429`/`5xx` retry classification;
- safe error messages and log redaction;
- strict JSON-root, provider payload and Pydantic contract validation;
- raw payload SHA-256;
- fail-closed multi-provider consensus;
- strict read-only XRPL RPC allowlist;
- no trade, custody, key or signing modules;
- one manual CI workflow with no repository write permission.

## Remaining controls

- dependency and container scans in remote CI;
- signed release manifest;
- secret-manager integration and rotation drill;
- DNS rebinding integration test in deployed network;
- immutable shadow ledger and restore drill;
- incident runbooks exercised against real provider outages.
