# Data Contracts

## Timestamp semantics

- `observed_at`: economic or market timestamp represented by the datum.
- `available_at`: earliest verified moment the engine could have known the datum.
- `fetched_at`: time the provider response reached the system.

Backtests filter on `available_at <= prediction_time`. Date-precision availability must be labelled as such and cannot be silently treated as an exact intraday release timestamp.

## Provenance minimum

Every external value includes:

- provider identifier;
- source URI or endpoint family without credentials;
- observed, available and fetched timestamps;
- SHA-256 of the raw response payload;
- data-quality flags;
- adapter/dataset version where applicable.

## Missing values

Missing, stale or unavailable inputs remain `null`. They are never silently replaced with zero. Neutral values are emitted only when zero is economically and mathematically meaningful, such as a flat z-score.

## OHLC invariants

- prices are finite and strictly positive;
- volume is finite and non-negative;
- `close_time > open_time`;
- `high >= max(open, close, low)`;
- `low <= min(open, close, high)`.

## Quote-currency semantics

USD and USDT are distinct canonical quote currencies. Binance `XRPUSDT` maps to `XRP_USDT`, never `XRP_USD`. Any future cross-quote normalization must record the stablecoin basis source and timestamp.

## Price consensus

1. Deduplicate by provider.
2. Require aligned asset, interval and close boundary.
3. Require at least two independent providers.
4. With three or more providers, remove relative-median outliers.
5. Recompute median, spread, freshness and agreement.
6. Return no value when coverage, freshness or agreement fails.
7. Emit provider count, rejected count, flags and validity.

## Point-in-time macro

Economic observation date is not release date. FRED `realtime_start` is retained as date-precision availability metadata. True release-time and vintage research requires a versioned calendar/vintage source before production backtesting.
