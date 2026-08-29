# Secrets Inventory

Secret **values are never recorded here**. This is a control inventory for expected secret
names, scope and rotation.

| Secret identifier | Purpose | Required scope | Storage | Rotation | Current state |
|---|---|---|---|---|---|
| `FRED_API_KEY` | FRED/ALFRED API access | Read-only economic data | Local environment / approved CI secret | 90 days or on exposure | Optional, not configured in source |
| `MARKET_DATA_VENDOR_API_KEY` | Future licensed equities/derivatives source | Read-only market data | Environment-specific secret manager | Contract/provider policy | Not selected |
| `ALERT_WEBHOOK_URL` | Future outbound notification boundary | Send only to approved endpoint | Environment-specific secret manager | On recipient change/exposure | Not enabled |

## Explicitly forbidden credentials

- exchange trading keys;
- withdrawal permissions;
- XRP wallet seeds or private keys;
- custody credentials;
- brokerage credentials;
- personal banking credentials.

## Controls

1. Secret names may appear in documentation; values may not.
2. CI logs and exception messages are redacted.
3. Each environment receives a separate key.
4. Keys use minimum read-only scopes and IP restrictions where available.
5. Exposure triggers immediate revocation, incident registration and clean-history review.
