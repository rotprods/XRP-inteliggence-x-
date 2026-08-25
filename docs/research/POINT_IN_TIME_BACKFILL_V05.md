# Point-in-Time Backfill v0.5

## Why this layer exists

A historical model is invalid if it can see data before that data was available. Every normalized record therefore carries two clocks:

- `observed_at`: when the market/economic fact occurred;
- `available_at`: when the engine could legitimately have consumed it.

For candles, availability begins at close. For revised macro series, availability begins at each vintage publication. Training, validation and analogues query the catalog with `available_at <= decision_time`.

## Durable write sequence

```text
HTTP page
  ↓
immutable raw bytes + SHA-256 + provenance envelope
  ↓
normalized HistoricalRecord values
  ↓
atomic date partition
  ↓
point-in-time catalog insert
  ↓
checkpoint advance
  ↓
immutable dataset manifest
```

The checkpoint is never advanced before the raw payload, normalized partition and catalog entries are durable.

## Initial datasets

- Coinbase XRP/USD hourly candles;
- Binance XRP/USDT hourly candles.

USD and USDT stay separate. Adding an explicit stablecoin/FX normalization model is a later, separately tested capability.

## Storage model

The alpha uses dependency-light primitives:

- content-addressed raw bytes;
- deterministic JSONL partitions;
- SQLite point-in-time catalog and checkpoints;
- SHA-256 dataset manifests.

After schemas and replay behavior are proven, large datasets can migrate to Parquet + DuckDB/Polars without changing the semantic contracts.

## Idempotency and recovery

- Identical raw bytes reuse the same content object.
- Every provenance envelope is immutable.
- Partition file names derive from content hashes.
- Duplicate catalog revisions use `INSERT OR IGNORE`.
- Backfill cursors are cycle-checked.
- Completed jobs return without refetching.
- Corrupt payloads, partitions or manifests fail closed.

## Research windows

The configuration registers explicit 2017, 2018, 2020, 2021, 2022, 2023, 2024–25 and 2026 windows. Labels are research metadata, not targets injected into training data.

## Production boundary

This implementation creates the reproducible substrate. Production remains blocked until:

- full provider-specific backfills complete;
- missing intervals and revisions are quantified;
- macro vintages are added;
- dataset licenses are recorded;
- manifests and restore drills are verified;
- walk-forward calibration and shadow evaluation are executed.
