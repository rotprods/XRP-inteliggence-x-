# Public Provider Endpoint Limitations

## General

- Public endpoints provide no contractual SLA unless explicitly stated by the provider.
- Regional access, symbols, candle closure semantics, rate limits and response schemas can change.
- Exchange maintenance can resemble missing or stale market data.
- Public data may be delayed relative to paid institutional feeds.
- A successful HTTP response does not guarantee economic correctness.

## Quote semantics

- Coinbase and Kraken adapters in this foundation represent USD-quoted markets.
- Binance represents USDT-quoted markets and must not populate USD series.
- Cross-quote fusion is blocked until a versioned stablecoin-basis policy exists.

## Historical use

- Exchange history can contain gaps, revisions or delisted symbols.
- FRED observation dates are not sufficient for point-in-time research; vintages/release
  availability must be preserved.
- Public XRPL servers can differ in load, retention and supported API methods.

## Production requirement

Before a provider becomes canonical, record at least seven days of regional health evidence,
latency, failures, schema drift, freshness and observed rate-limit behaviour.
