# COS 20D — XRP Intelligence Coordinate System

Each node, claim, event or derived state may be projected onto twenty explicit dimensions. Values are features for analysis/retrieval, not probabilities of truth.

| D | Dimension | Question |
|---|---|---|
| D01 | Temporal | When did it occur, become observable and become available? |
| D02 | Provenance | Who/what is the originating source and custody chain? |
| D03 | Evidence | How strong and independently corroborated is the evidence? |
| D04 | Contradiction | What credible evidence disputes or falsifies it? |
| D05 | Causality | Is there a mechanism, mere correlation, or no demonstrated link? |
| D06 | Market | What asset, venue, horizon, liquidity and price regime is implicated? |
| D07 | MacroLiquidity | Rates, yields, DXY, central-bank balance sheets, credit/liquidity. |
| D08 | CrossAsset | BTC/ETH/equities/VIX/gold/energy/FX relationships. |
| D09 | Regulatory | Jurisdiction, legislation, regulator, court case and legal status. |
| D10 | Institutional | Banks, payment networks, funds, corporates and governance actors. |
| D11 | Payments | Correspondent banking, nostro/vostro, settlement, messaging, rails. |
| D12 | Ledger | XRPL/DLT ledger activity, AMM/DEX, fees, transactions, tokenization. |
| D13 | Technology | Protocol, interoperability, programmability, AI-agent/payment stack. |
| D14 | Geopolitical | States, sanctions, conflict, chokepoints, trade and strategic risk. |
| D15 | EnergyCommodity | Oil/gas/commodity transmission into inflation and liquidity. |
| D16 | NetworkInfluence | Documented employment, ownership, partnership, lobbying and control edges. |
| D17 | Narrative | Social narratives, memes, riddles, virality and information diffusion. |
| D18 | Prediction | Ex-ante claim, target, horizon, specificity and resolution outcome. |
| D19 | Behavioral | Positioning, reflexivity, attention, crowding and hindsight/cherry-pick risk. |
| D20 | OperationalRisk | Freshness, outages, disagreement, leakage, licensing and release-gate state. |

## Canonical epistemic status

`FACT | STRONG_EVIDENCE | PLAUSIBLE | HYPOTHESIS | CLAIM_ONLY | DISPUTED | REFUTED | NO_DATA`

### Promotion rules

- `CLAIM_ONLY -> PLAUSIBLE`: a coherent mechanism plus at least one credible source; still not fact.
- `PLAUSIBLE -> STRONG_EVIDENCE`: primary evidence and independent corroboration with temporal consistency.
- `STRONG_EVIDENCE -> FACT`: directly documented/observable proposition whose scope is narrowly stated and whose provenance is reproducible.
- Any contradiction can lower status; strong primary counterevidence can produce `DISPUTED` or `REFUTED`.
- Repetition, social engagement, graph degree, embedding similarity, gematria/numerology and post-event resemblance never promote epistemic status.

## Typed entities

`Person, Organization, Government, Regulator, CentralBank, CommercialBank, Network, Protocol, Asset, Stablecoin, CBDC, Legislation, CourtCase, Event, MarketInstrument, Commodity, Geography, Chokepoint, Technology, Claim, Prediction, Source, Document, APIEndpoint, Dataset`.

## Typed temporal relations

`FOUNDED, EMPLOYED_BY, INVESTED_IN, PARTNERED_WITH, REGULATES, SUED, SETTLED, PILOTED_WITH, USES_TECHNOLOGY, ISSUES, SETTLES_WITH, PROVIDES_LIQUIDITY, COMPETES_WITH, DEPENDS_ON, SANCTIONED_BY, FUNDS, LOBBIED, VOTED_ON, CORRELATES_WITH, CLAIMS, CONTRADICTS, SUPPORTS, PREDICTED, OCCURRED_AT, AFFECTS_MARKET, SOURCE_OF`.

Every edge MUST carry `edge_id`, `source_ids`, `evidence_status`, `confidence`, `valid_from`, `valid_to`, `observed_at`, `available_at`, and `retrieved_at`. Causal edges additionally require `mechanism` and `causal_grade`; correlation alone must never be serialized as causation.
