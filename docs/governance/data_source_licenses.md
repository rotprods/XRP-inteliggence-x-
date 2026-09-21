# Data-Source Licence Register

This document is an engineering risk gate, not legal advice or legal approval. Every provider
must be revalidated against its current official terms, regional availability and applicable
retention/redistribution rules before production retention or redistribution.

Last engineering review: **2026-09-22**.

## Current source decisions

| Source | Intended research use | Official access evidence reviewed | Credentials | Retention / derived features | Redistribution | Regional / rate notes | Status |
|---|---|---|---|---|---|---|---|
| Binance public market data | XRP/BTC/ETH USDT spot, order-book/trades and public derivatives observations | Binance documents public historical Spot data at `https://data.binance.vision/`; Developer Docs document `https://data-api.binance.vision` for `NONE`-security public endpoints; Spot product terms page reviewed 2026-09-22 | None for the public endpoints in scope | **Not approved for a large retained corpus.** Raw-response hash is allowed; normalized retained history requires owner acceptance of the retention policy and provider-specific terms interpretation | Not assumed | Availability and product access may vary by region; rate/schema/endpoint behaviour must be monitored. USDT must never be relabelled USD | **BLOCKED for large retained backfill; bounded read-only smoke only** |
| Kraken public market data | Independent XRP/BTC/ETH USD spot observations and historical OHLCVT | Kraken support page, updated 2026-09-16, documents downloadable OHLCVT CSV for each currency pair from market inception and states the files may be used in code; EEA Terms effective 2026-06-29 reviewed | None for public market-data paths in scope | Official download/use-in-code evidence is stronger than for the other candidates, but long-term project retention/derived-feature policy has not yet been accepted by the owner | Not assumed | Spain is in the EEA terms scope. Public APIs remain rate-limited and have no project-specific SLA | **Research-only; owner retention acceptance still required** |
| Coinbase Exchange / Advanced Trade public market data | Independent XRP/BTC/ETH USD spot observations | Current Coinbase developer documentation exposes real-time market-data interfaces; Coinbase Developer Platform Terms last modified 2026-06-23 reviewed | None for public market-data endpoints selected for research | Public access is confirmed; this review did not establish an explicit retained-history or redistribution licence for the intended corpus | Not assumed | Endpoint/product terms may differ across Coinbase products; only explicitly public, unauthenticated market-data routes are eligible for this project | **Research-only pending retention/terms mapping** |
| KuCoin public market data | Candidate USDT fallback | Not revalidated in this 2026-09-22 wave | None in current public adapter | None approved beyond existing engineering fixtures | Not assumed | Must be revalidated before promotion | Adapter exists; not canonical for retained history |
| FRED / ALFRED | Macro observations and vintages | Existing engineering integration; official terms/vintage semantics require dedicated review | FRED API key | Normalized series plus release/vintage metadata, subject to source terms | Subject to source terms | Point-in-time use requires real vintage/release availability, not observation dates alone | Engineering integration; vintage validation pending |
| XRP Ledger public servers | Network health and allowlisted read-only RPC results | Existing public-server integration | None | Payload hash and normalized metrics | Not assumed | Independent server diversity and retention behaviour must be evidenced | Engineering integration; server diversity pending |
| Ripple official publications | Corporate announcements | Official-source ingestion planned | None | URL, timestamps and extracted metadata; short excerpts only | No full-content redistribution assumed | Source timestamps and later edits must be preserved | Planned |
| SEC official sources | Regulatory/legal events | Official-source ingestion planned | None | Metadata, dates and source links | Metadata only | Availability time and amendments must be preserved | Planned |
| SWIFT official sources | Payment-infrastructure events | Official-source ingestion planned | None | Metadata, dates and source links | Metadata only | Availability time and revisions must be preserved | Planned |
| Licensed equities/derivatives vendor | Equities, OI, funding, liquidations | No vendor selected | Paid key | As permitted by contract | Contract-specific | Paid calls are prohibited unless explicitly authorized | Not selected |

## Engineering gate decision — 2026-09-22

The current review establishes that suitable **public read-only access paths exist**, but it does
**not** promote any exchange to unrestricted historical-retention authority.

The following gates therefore apply:

- `LARGE_RETAINED_BACKFILL = BLOCKED` until the selected provider's applicable terms are mapped
  to the intended retention/derived-feature use and the project owner explicitly accepts the
  retention policy.
- `BOUNDED_EPHEMERAL_SMOKE = ALLOWED` only for public unauthenticated read-only market-data
  endpoints, with tiny bounded responses, no paid calls, no account state, no trading actions and
  no redistribution. Unless retention is separately approved, discard raw provider payloads after
  parsing and retain only the minimum deterministic evidence needed for the smoke result.
- `DETERMINISTIC_SYNTHETIC_FIXTURES = ALLOWED`; provider-derived fixtures must remain minimal and
  must not be used to evade a source's retention or redistribution restrictions.
- A historical observation fetched **after** its prediction time must never be labelled
  `STRICT_REPLAY`. It is eligible only as `RECONSTRUCTED_PIT` when a valid reconstruction basis is
  recorded; otherwise it is `INELIGIBLE`.
- Binance `XRPUSDT` remains `XRP_USDT`; Coinbase/Kraken USD observations remain USD. Cross-quote
  fusion is blocked until a versioned stablecoin-basis policy exists.
- Independent-source requirements remain fail-closed. One exchange, one venue family, or copied
  upstream data must not be represented as independent confirmation.

## Mandatory metadata per selected source

Before a source can back a promoted retained DatasetVersion, record:

- canonical provider identifier;
- exact official documentation and terms URLs;
- review date and reviewer/owner;
- applicable region/entity;
- allowed use and retention period;
- whether normalized observations and derived features may be stored;
- rate limits and regional restrictions;
- attribution requirements;
- redistribution prohibition or permission;
- owner acceptance of the project retention policy;
- next review date.

No large historical backfill may be promoted until every mandatory field required by the selected
source is resolved. Absence of an explicit prohibition is **not** evidence of permission.
