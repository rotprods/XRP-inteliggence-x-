# Provider Matrix

| Data family | Primary | Secondary | Tertiary/fallback | Credential | Production notes |
|---|---|---|---|---|---|
| XRP/BTC/ETH spot | Coinbase Exchange / Kraken (USD) | Binance / KuCoin (USDT) | independent licensed fallback | Usually none for public endpoints | Validate regional access and candle semantics |
| Crypto derivatives | Binance Futures | CoinGlass or another licensed vendor | CSV export | Varies | Normalise contract units and exchange coverage |
| Macro rates/liquidity | FRED/ALFRED | Treasury/Fed source feeds | Licensed terminal export | FRED key | Preserve vintages and release timestamps |
| Equities/indices | Licensed market-data vendor | Exchange-authorised vendor | Daily CSV | Key/licence | Yahoo-like unofficial feeds are not canonical |
| Commodities | Licensed futures/market vendor | FRED spot series where suitable | CSV | Varies | Cocoa remains exploratory zero-weight |
| XRPL | Trusted xrpld/Clio endpoint | Second independent server | Self-hosted node | None for public methods | Compare critical results across servers |
| Ripple/SEC/SWIFT events | Official RSS/press/legal sources | Reputable wire service | Manual annotation | None | Separate corporate narrative from token utility |
| ETF flows | Authorised issuer/vendor data | Licensed aggregator | Manual verified import | Often paid | Do not scrape unreliable social dashboards |
