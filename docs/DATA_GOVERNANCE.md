# Data governance

## Data layers

1. **Raw** — immutable provider payload, retrieval timestamp, HTTP metadata and SHA-256.
2. **Normalized** — canonical symbol, unit, timezone and schema validation.
3. **Features** — deterministic transformations with explicit lookback and version.
4. **Regime snapshots** — scores, probabilities, confidence, drivers, invalidations and source health.
5. **Evaluation** — outcomes joined only after the relevant horizon expires.

## Time semantics

Every observation should distinguish:

- `event_at`: when the market or source event occurred;
- `observed_at`: when the system retrieved it;
- `available_at`: earliest time it could legitimately enter a decision;
- `revised_at`: when a provider revision became available, where applicable.

Backtests may consume data only when `available_at <= decision_at`.

## Provenance minimum

- provider and endpoint;
- source symbol and canonical symbol;
- retrieval timestamp and latency;
- freshness class;
- raw payload hash;
- parser/schema version;
- quality flags and fallback path;
- licensing/retention classification.

## Failure policy

- malformed payload: reject and record;
- stale source: exclude or decay weight;
- provider disagreement: reduce confidence and possibly block output;
- insufficient independent sources: `NO_DATA` or `DEGRADED`;
- missing macro series: never silently forward-fill beyond an economically valid window;
- unknown provenance: exclude from production scoring.

## Storage policy

Large historical datasets and raw payloads do not belong in Git. Git contains schemas, small fixtures, manifests, checksums and reproducible ingestion code. Operational databases and object storage must be access-controlled, encrypted and recoverable.

## Personal and financial data

The market engine must not ingest wallet seeds, private keys, exchange credentials, personal bank statements or user-specific tax records. Personal XRP context belongs in the separate Sovereign Escape OS boundary and is linked only through explicit, minimal contracts.
