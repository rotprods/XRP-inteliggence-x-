# Binance XRP Order-Book Intelligence V1

Status: READ_ONLY / SHADOW / NON_EXECUTION.

## Implemented

- Binance Spot REST depth snapshot: `GET /api/v3/depth`.
- XRPUSDT, BTCUSDT and ETHUSDT allowlist.
- Strict supported depth limits.
- Bid/ask level validation and crossed-book rejection.
- Mid price, spread bps and top-of-book microprice.
- Cumulative bid/ask notional and imbalance at ±10/25/50/100 bps.
- Payload hash provenance inherited from the hardened provider transport.
- No API key, account stream, order endpoint, wallet, leverage or execution capability.

## Truth boundary

A REST snapshot is not a reconstructed local order book and cannot establish wall persistence,
cancellation/spoof behavior, queue dynamics or event-by-event CVD. Those require the official
Binance diff-depth WebSocket protocol with snapshot/update-id synchronization and reconnect
recovery.

Accordingly V1 metrics are observation features only. They MUST NOT independently emit LONG/SHORT
instructions or increase narrative execution weight.

## V2 exact frontier

1. Buffer `<symbol>@depth@100ms` diff events.
2. Fetch REST snapshot and discard events with final update ID <= snapshot lastUpdateId.
3. Require first retained event to bridge the snapshot update ID according to Binance sequencing.
4. Apply bids/asks by absolute quantity; quantity zero removes a level.
5. Detect gaps/out-of-order events and fail closed to resnapshot.
6. Compute wall persistence/cancellation, order-flow imbalance, microprice drift and depth velocity.
7. Join public aggregate trades for taker-side CVD.
8. Add USD-M futures read-only OI, funding, mark/index basis and taker buy/sell statistics.
9. Persist point-in-time snapshots with `observed_at/available_at/fetched_at`.
10. Keep the entire microstructure plane shadow-only until leakage/freshness/reconnect tests pass.

## Decision contract

`WAIT_FOR_CONFIRMATION` remains the safe default when live microstructure is stale, incomplete,
unsynchronized, single-source, or unavailable. A visible wall in one snapshot is never sufficient
evidence of durable support/resistance.
