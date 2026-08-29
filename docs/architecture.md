# System Architecture

```mermaid
flowchart TD
    A[Provider Registry] --> B[Ingestion Orchestrator]
    B --> C1[Spot Crypto Adapters]
    B --> C2[Derivatives Adapters]
    B --> C3[Macro / Equities / Commodities]
    B --> C4[XRPL / Ripple Events]
    C1 --> D[Raw Event Store + Payload Hashes]
    C2 --> D
    C3 --> D
    C4 --> D
    D --> E[Normalization + Point-in-Time Availability]
    E --> F[Provider Consensus + Data Quality]
    F --> G[Feature Store]
    G --> H1[1h Regime Model]
    G --> H2[4h Regime Model]
    G --> H3[1d Regime Model]
    G --> H4[1w Regime Model]
    H1 --> I[Explanation + Confidence]
    H2 --> I
    H3 --> I
    H4 --> I
    I --> J[API / Dashboard / Alerts / Reports]
    J --> K[Audit Log and Human Review]
```

## Data planes

### Raw plane

Immutable provider payload reference, response hash, fetch timestamp, source URI, status and licence metadata.

### Normalized plane

Canonical symbols, UTC timestamps, units and point-in-time availability. No feature logic is allowed here.

### Feature plane

Versioned features with training window and source coverage. Every feature snapshot points to the normalized observations used.

### Decision plane

Horizon-specific regime scores, confidence, drivers, invalidations and historical analogues.

## Failure semantics

- A provider outage lowers coverage and confidence.
- A provider conflict creates a `CONFLICT` flag and can block alerts.
- Stale spot data blocks intraday outputs but may not block weekly macro reports.
- Missing derivatives data degrades `1h/4h` more heavily than `1w`.
- Revised macro data must not rewrite historical backtest inputs without a new dataset version.
