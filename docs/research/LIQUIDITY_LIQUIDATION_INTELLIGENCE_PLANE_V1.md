# Liquidity + Liquidation Intelligence Plane V1

Date: 2026-09-22

Mode: READ_ONLY / SHADOW_ONLY / NON_EXECUTION

## Mission

Make XRP breakout/regime research explicitly depend on external liquidity, derivatives, liquidation and on-chain liquidity evidence rather than price candles alone.

The system must distinguish:

1. **PRIMARY_OBSERVED**
   - direct venue / ledger observations;
   - highest evidence authority.

2. **AGGREGATED_OBSERVED**
   - multi-venue aggregated observations;
   - useful, but lower authority than direct primary-source observations.

3. **INFERRED_MODEL**
   - calculated heatmaps, liquidation clusters, whale/position models or similar analytics;
   - useful as contextual evidence only;
   - never promoted to factual pending orders.

## Implemented surfaces

### CEX liquidity / order flow

- bid depth USD;
- ask depth USD;
- depth imbalance;
- large limit bids/asks;
- taker buy/sell ratio.

### Derivatives

- open interest USD;
- OI delta USD;
- OI velocity USD/min;
- funding;
- basis;
- executed long liquidations;
- executed short liquidations;
- executed liquidation imbalance.

### Estimated liquidation structure

- long-liquidation clusters below market;
- short-liquidation clusters above market;
- nearest-cluster distance;
- ±1%, ±2%, ±5% liquidation-band exposure;
- inferred liquidation bias;
- estimated-cluster-notional / observed-book-depth ratio.

Liquidation clusters are **INFERRED_MODEL** by contract.

A heatmap is not evidence that a particular exchange account has an open liquidation order at a given level.

### XRPL liquidity

- AMM XRP reserve;
- AMM quote reserve;
- effective 10k-notional AMM slippage;
- DEX funded bid amount;
- DEX funded ask amount;
- DEX spread.

For XRPL order books, funded liquidity is preferred over nominal offer size.

### Flow / institutional context

- verified exchange inflow XRP;
- verified exchange outflow XRP;
- ETF net flow USD;
- whale-long and whale-short notional when the provider supplies defensible provenance.

## External source semantics

### Binance public market data

Authority:
`PRIMARY_OBSERVED`

Candidate inputs:

- open interest;
- funding;
- mark/index basis;
- order book;
- taker buy/sell;
- liquidation events where publicly observable.

Do not use account mutation or authenticated trading endpoints.

### CoinGlass

Observed analytics:
`AGGREGATED_OBSERVED`

Candidate inputs:

- OI;
- funding;
- executed liquidation history;
- taker ratios;
- large order-book observations;
- whale analytics;
- ETF/on-chain analytics.

Liquidation heatmap/map:
`INFERRED_MODEL`

The CoinGlass documentation describes liquidation heatmaps as **calculated** liquidation levels based on market data and leverage levels.

Therefore they can influence:

- short-liquidation-fuel context;
- long-flush-risk context;
- liquidity magnet research;
- sensitivity analysis;

but cannot independently prove pending exchange liquidations.

### XRP Ledger

`amm_info`:
`PRIMARY_OBSERVED`

Use validated-ledger state for:

- pool reserves;
- LP token state;
- derived effective slippage.

`book_offers`:
`PRIMARY_OBSERVED`

Use:

- funded offer quantities;
- issuer-aware market identity;
- spread / effective depth.

## Point-in-time rules

Every observation carries:

- observed_at;
- available_at;
- fetched_at;
- provider;
- venue;
- symbol;
- source_id;
- payload_sha256;
- authority;
- confidence;
- optional model_id.

Prediction-time eligibility requires:

`available_at <= prediction_time`
and
`fetched_at <= prediction_time`.

Future and stale inputs are rejected before aggregation.

## LiquidityLiquidationState

The content-addressed state emits:

- provider sets split by observed vs inferred;
- observed/inferred sample counts;
- stale/future rejection flags;
- CEX depth;
- OI/funding/basis;
- taker ratio;
- executed liquidation imbalance;
- XRPL AMM/DEX liquidity;
- flow/ETF/whale context;
- liquidation-band structure;
- nearest liquidation clusters;
- inferred liquidation bias;
- cluster-to-book-depth ratio.

Hard invariants:

`decision_authority = false`
`execution_weight = 0.0`

## Breakout liquidity context

`LiquidityBreakoutContext` translates the plane into research posture:

- NO_DATA
- SPOT_SUPPORTIVE
- LEVERAGE_LED
- SHORT_LIQUIDATION_FUEL
- FRAGILE
- NEUTRAL

### SPOT_SUPPORTIVE

Requires, at minimum:

- PIT-eligible observed provider coverage;
- supportive CEX depth imbalance;
- buy-dominant taker flow;
- no detected OI expansion;
- funding/basis not dangerous.

### LEVERAGE_LED

Spot support exists but OI delta + OI velocity are expanding.

### FRAGILE

Examples:

- OI expanding while funding/basis are crowded;
- nearby estimated long-liquidation cluster dominates.

### SHORT_LIQUIDATION_FUEL

Spot support exists and an **inferred** short-liquidation cluster lies near current price.

This is contextual research evidence, not a reason to execute.

## XRP $1.50→$2 experiment integration

PR #32 currently freezes the prospective XRP breakout experiment independently.

This liquidity plane must later feed that state machine with:

- spot_flow_confirmed;
- leverage_expansion;
- funding_dangerous;
- liquidity fragility;
- inferred squeeze/flush structure;
- effective XRPL liquidity.

Integration should happen only after each branch is independently FAST-green to avoid writer collision.

## Source docs

- Binance Developer Docs:
  - public derivatives market data: OI, funding, mark/index, depth, taker buy/sell.
- CoinGlass API V4:
  - liquidation history;
  - heatmap/map;
  - OI/funding;
  - order-book analytics;
  - whale/ETF/on-chain metrics.
- XRPL public API:
  - `amm_info`
  - `book_offers`

## Scientific law

The system may use estimated liquidation clusters to ask:

> If price reaches this region, how much modeled forced-liquidation fuel may exist?

It must not say:

> There are definitely $X of pending liquidations at this exact price.

unless a primary source actually exposes that fact.

## Next executable wave

1. FAST-verify this plane.
2. Add provider adapters for missing public metrics.
3. Add paid-provider connector only if credentials/plan are explicitly available.
4. Produce the first live LiquidityLiquidationState for XRP.
5. Feed it into the prospective breakout observer after PR #32 convergence.
6. Freeze state transitions and resolve them later against MFE/MAE/$2-touch outcomes.
