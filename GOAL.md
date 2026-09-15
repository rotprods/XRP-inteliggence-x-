# GOAL — XRP Cross-Asset Regime Engine

## North Star

Create an auditable, provider-resilient and statistically disciplined system that continuously estimates whether XRP is in accumulation, early reversal, confirmed trend, overextension, distribution, capitulation or range conditions across multiple horizons.

## Primary decision outputs

For each timestamp and horizon (`1h`, `4h`, `1d`, `1w`) the engine must produce:

- regime label;
- bull, bear, squeeze and distribution scores;
- confidence and data-quality scores;
- key drivers and invalidations;
- support/resistance context;
- provider freshness and agreement;
- historical analogues with similarity and caveats;
- an explicit statement of what is known, inferred and unavailable.

## Non-goals for the current release

- automatic order execution;
- leverage or position sizing recommendations;
- claims of guaranteed price direction;
- opaque neural-network output without explanation;
- reliance on a single exchange or a single news source;
- retrospective backtests that leak future data.

## Acceptance criteria for beta

1. At least two independent spot providers for XRP and BTC.
2. At least one derivatives provider with OI and funding.
3. Macro series with release-time awareness or vintages where required.
4. Reproducible historical store from 2017 onward where data exists.
5. Walk-forward validation and probability calibration.
6. Provider freshness, disagreement and outage handling.
7. API, CLI, scheduled snapshots, alerts and audit log.
8. No production signal when critical data quality falls below threshold.
9. Documented source licences, rate limits and retention rules.
10. CI passing, security review complete and deployment runbook tested.
