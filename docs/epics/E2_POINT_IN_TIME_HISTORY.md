# E2 — Point-in-time historical lake

## Objective

Create a reproducible historical dataset for BTC, XRP, ETH and cross-asset context that contains only information genuinely available at each simulated decision time.

## Required history

- XRP/USD, XRP/BTC, BTC/USD, ETH/USD and ETH/BTC;
- BTC dominance and broad crypto market proxies;
- Treasury 2Y/10Y/30Y, real yields, broad dollar, financial conditions and liquidity;
- S&P 500, Nasdaq, VIX, Coinbase, Strategy and miner basket;
- gold, WTI, Brent, gasoline, natural gas and exploratory cocoa;
- available OI, funding, basis and liquidation history;
- XRPL ledger, transaction, fee, DEX, AMM and RLUSD history;
- verified Ripple, SEC and SWIFT event timestamps.

## Event windows

2017 repricing, 2018 capitulation, 2020 SEC event, 2021 bull cycle, 2022 liquidity/credit shock, 2023 legal repricing, 2024–25 institutional expansion and 2026 correction/reversal.

## Acceptance criteria

- every record distinguishes event, observation and availability times;
- macro revisions use point-in-time vintages where available;
- calendars/timezones are normalized without invalid forward filling;
- raw and normalized partitions have manifests and checksums;
- transformations fit inside training windows only;
- purged walk-forward and embargo tests pass;
- survivorship and unavailable-history limitations are published;
- large datasets remain outside Git.
