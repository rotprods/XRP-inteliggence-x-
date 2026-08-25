# Live Provider Plane v0.4

## Objective

Create a small, defensible read-only provider core before expanding coverage. Reliability, provenance and replacement are more important than provider count.

## Initial spot matrix

| Provider | Pair | Role | Authentication | Notes |
|---|---|---|---|---|
| Coinbase Exchange | XRP/USD | Primary | None | Independent USD quote |
| Kraken | XRP/USD | Primary | None | Independent USD quote |
| KuCoin | XRP/USDT | Secondary | None | Stablecoin quote, never silently mixed with USD |
| Binance | XRP/USDT | Secondary | None | Regional availability must be evidenced |

## Invariants

1. Requests are GET-only and credential-free.
2. URLs require HTTPS, port 443 and an explicit host allowlist.
3. DNS resolution rejects private, loopback, link-local, multicast, reserved and unspecified addresses.
4. Redirects and environment proxy inheritance are disabled.
5. Payload size and JSON root type are bounded.
6. Raw payload bytes receive SHA-256 provenance.
7. Retry is bounded; protocol errors do not loop.
8. Circuit breakers isolate failing providers.
9. A failed provider cannot fail the entire probe plane.
10. USD and USDT consensus groups remain separate unless an explicit FX/stablecoin normalization model is supplied.

## Failure model

```text
provider request
  ├─ valid JSON 200 → normalize → quote → healthy
  ├─ 429 / 5xx → bounded retry → circuit accounting
  ├─ redirect / non-JSON / malformed payload → terminal protocol failure
  ├─ stale or future timestamp → quote rejection
  └─ circuit open → fail closed without network request
```

## Production gate

Public probes demonstrate reachability, not production readiness. Promotion requires sustained regional evidence, contract tests for every enabled adapter, rate-limit documentation, provider substitution drills, storage manifests and freshness/latency SLOs.

No adapter may expose trading, withdrawal, custody or signing functionality.
