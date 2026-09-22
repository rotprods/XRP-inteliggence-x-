# XRP Prospective Breakout Experiment — 2026-09-22

Experiment ID: `H-XRP-BREAKOUT-150-20260922`

Mode: READ_ONLY / SHADOW_ONLY / NON_EXECUTION

Purpose: freeze the live $1.50→$2 thesis before the outcome is known and measure whether the research system is too slow, appropriately selective, or structurally missing evidence.

This document is **not** a trading instruction.

## 1. Human-supplied observation freeze

Two KuCoin XRP/USDT screenshots were supplied prospectively.

### Screenshot A — 15m

Approximate local observation time shown in artifact: 16:56 Europe/Madrid, 2026-09-22.

Visible values:

- XRP/USDT: 1.56078
- displayed change: +3.78%
- 24h high: 1.59620
- 24h low: 1.48068
- 24h XRP volume: 98.73M XRP
- 24h quote volume: 150.78M USDT
- visible 15m MACD:
  - MACD: 0.00172
  - DIF: 0.00898
  - DEA: 0.00811

Artifact SHA-256:

`bcc0f6a97065eb5f20dfc518165caab5bfe546ea2565f424241466eaa26afefa`

### Screenshot B — 8h

Visible values:

- XRP/USDT: 1.56031
- displayed change: +3.73%
- 24h high: 1.59620
- 24h low: 1.48068
- prior visible swing high: 1.69945
- prior visible low: 0.98677
- visible 8h MACD:
  - MACD: 0.04130
  - DIF: 0.04226
  - DEA: 0.02161

Artifact SHA-256:

`35ddc07af1e4721b3f585c80e89e8559b52c644ec4d8fd3cdb50ad0dddfce5a2`

These screenshots are user-supplied observation artifacts, not canonical exchange API truth.

## 2. Independent public context available on 2026-09-22

Public market reporting on the same day showed a broad crypto rebound:

- CoinDesk reported XRP roughly around $1.52 and approximately +7% on the day.
- CoinDesk also reported that more than $1B of crypto positions had been liquidated over 24h, with a large majority of those liquidations being shorts.
- The report explicitly noted that once the forced-liquidation impulse slowed, the next stage would depend more on actual buyers rather than forced short covering.
- The Block also reported XRP around $1.49 during the rebound.

These sources establish that the move was broad and material, but they do **not** prove the XRP move at the screenshot timestamp was spot-led.

Public context references:

- CoinDesk: `Dogecoin leads market rebound with 15% pump, bitcoin steady above $85,000`, 2026-09-22.
- The Block: `Bitcoin taps $85,000 for first time since January as crypto short liquidations surge`, 2026-09-21.

## 3. Frozen hypothesis

Do not encode:

> XRP will hit $2.

Encode:

> XRP is attempting to transition from the $1.50 region into a higher-price regime. If price acceptance is independently confirmed and the move is supported by spot/order-flow rather than dangerous leverage expansion, the $2 barrier becomes a prospective research target for later resolution.

Reference price at freeze:

`~1.56 USDT`

Research breakout acceptance level:

`1.60`

Primary prospective barrier:

`2.00`

The $1.60 level is chosen because the supplied 24h high was 1.59620: price had approached but had not clearly demonstrated acceptance above $1.60 in the supplied evidence.

## 4. State machine

Allowed research states:

`NO_DATA`

`BREAKOUT_UNCONFIRMED`

`SPOT_CONFIRMED_BREAKOUT`

`LEVERAGED_BREAKOUT`

`FAILED_BREAKOUT`

No state grants execution authority.

## 5. Current strict evidence assessment

At freeze time the screenshot proves only one venue directly.

Therefore the canonical research engine must treat the following as unresolved until exact API evidence is captured:

- independent multi-provider price consensus;
- spot aggressive buy/sell flow and CVD;
- local order-book absorption/replenishment;
- open-interest delta;
- funding state;
- basis;
- liquidation attribution;
- XRP/BTC and XRP/ETH relative-strength confirmation at the same prediction boundary.

The human visual interpretation is:

`BREAKOUT ATTEMPT / UNCONFIRMED`

The strict machine state remains:

`NO_DATA`

until independent consensus is reconstructed for the same prediction boundary.

This distinction is intentional.

## 6. SPOT_CONFIRMED_BREAKOUT gate

The shadow system may mark `SPOT_CONFIRMED_BREAKOUT` only when all applicable evidence passes:

1. independent price consensus is valid;
2. the defined breakout level is accepted rather than merely wicked through;
3. spot-flow confirmation is positive;
4. XRP relative strength against BTC/ETH confirms rather than lags;
5. leverage expansion is absent or non-dominant;
6. funding is not structurally dangerous;
7. critical source freshness/alignment gates pass.

If leverage expansion is dominant:

`LEVERAGED_BREAKOUT`

If consensus/critical evidence is missing:

`NO_DATA` or `BREAKOUT_UNCONFIRMED`

If the breakout fails:

`FAILED_BREAKOUT`

## 7. Shadow opportunity question

The question to score later is not:

> Why did we fail to buy XRP?

It is:

> At which timestamp did enough ex-ante evidence first exist for the system to mark a shadow long candidate, and what happened afterward?

For every future state transition freeze:

- assessment_id;
- observed_at;
- exact SourceSnapshot IDs;
- state;
- reference price;
- support;
- contradictions;
- missing evidence;
- horizon;
- later MFE;
- later MAE;
- $2 touch result;
- return at 1h/4h/1d/1w;
- false-positive / false-negative classification.

This creates an opportunity-cost dataset rather than hindsight.

## 8. Present interpretation

The screenshots show genuine upward price structure across 15m and 8h and a test of the 1.5962 region.

But same-day market reporting also describes a broad crypto rebound heavily influenced by short liquidations.

That combination is exactly why the system should distinguish:

`PRICE IS RISING`

from

`SPOT-CONFIRMED XRP BREAKOUT`.

At this freeze, the latter is not yet proven by the available canonical evidence.

## 9. Safety invariants

`probability_calibrated = false`

`production_ready = false`

`decision_authority = false`

`execution_weight = 0.0`

The experiment records what the system would have known and when. It does not place or size a position.

## 10. Next executable wave

Immediately capture / reconstruct the same-boundary evidence for:

1. Coinbase / Kraken / Binance or other genuinely independent XRP spot price observations;
2. aggregate trade CVD;
3. depth/absorption/replenishment;
4. OI delta and velocity;
5. funding;
6. basis;
7. liquidations;
8. XRP/BTC;
9. XRP/ETH;
10. BTC / broad risk regime.

Then freeze the first evidence-complete state transition and never reinterpret it after the outcome.
