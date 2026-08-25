# E1 — Provider assurance and live data plane

## Objective

Produce trustworthy, timestamped and auditable observations from independent providers without allowing a single stale or malformed source to dictate XRP regime output.

## Work packages

- spot: Coinbase, Kraken, KuCoin and regional Binance availability;
- derivatives: OI, funding, basis, liquidations and long/short imbalance;
- macro: rates, real yields, broad dollar, financial conditions and liquidity;
- equities: S&P 500, Nasdaq, VIX, Coinbase, Strategy and miner basket;
- commodities: gold, WTI, Brent, gasoline, natural gas; cocoa exploratory weight `0`;
- XRPL: ledger close, transactions, fees, DEX, AMM, trust lines and RLUSD activity;
- Ripple/SEC/SWIFT events with source trust, materiality and decay.

## Acceptance criteria

- every observation includes provider, endpoint, source/canonical symbol, `observed_at`, `available_at`, latency and raw hash;
- at least two independent spot prices are required for a critical consensus;
- outliers, stale data and clock skew are rejected;
- disagreement degrades confidence or blocks output;
- partial outages produce `DEGRADED` or `NO_DATA`, not invented continuity;
- contract tests cover malformed responses and provider failover;
- endpoint licensing and retention constraints are documented;
- no API credential has trading scope.
