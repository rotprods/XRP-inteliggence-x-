# Data-Source Licence Register

This document records engineering assumptions, not legal approval. Every provider must be
revalidated against its current official terms before production retention or redistribution.

| Source | Intended use | Credentials | Stored data | Redistribution | Status |
|---|---|---|---|---|---|
| Coinbase Exchange public market data | XRP/BTC/ETH USD spot observations | None for public endpoints | Raw response hash; normalized candles after approval | Not assumed | Research-only pending current terms review |
| Kraken public market data | Independent USD spot observations | None | Raw response hash; normalized candles after approval | Not assumed | Research-only pending current terms review |
| Binance public market data | USDT-quoted spot observations only | None | Raw response hash; normalized candles after approval | Not assumed | Regional access and terms review required |
| KuCoin public market data | Candidate USDT fallback | None | None in current foundation | Not assumed | Adapter not yet canonical |
| FRED / ALFRED | Macro observations and vintages | FRED API key | Normalized series plus release/vintage metadata | Subject to source terms | Engineering integration; vintage validation pending |
| XRP Ledger public servers | Network health and allowlisted read-only RPC results | None | Payload hash and normalized metrics | Not assumed | Engineering integration; server diversity pending |
| Ripple official publications | Corporate announcements | None | URL, timestamps, extracted metadata | Short excerpts/metadata only | Planned |
| SEC official sources | Regulatory/legal events | None | Metadata, dates and source links | Metadata only | Planned |
| SWIFT official sources | Payment-infrastructure events | None | Metadata, dates and source links | Metadata only | Planned |
| Licensed equities/derivatives vendor | Equities, OI, funding, liquidations | Paid key | As permitted by contract | Contract-specific | Not selected |

## Mandatory metadata per source

- canonical provider identifier;
- official terms URL and review date;
- allowed use and retention period;
- whether derived features may be stored;
- rate limits and regional restrictions;
- attribution requirements;
- redistribution prohibition;
- owner and next review date.

No large historical backfill may be promoted until this register records the selected source's
current terms and the project owner accepts the retention policy.
