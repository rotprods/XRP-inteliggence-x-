# Model Card — Explainable Regime Scorer v0.2 alpha

## Intended use

Prioritize monitoring, frame scenarios and identify when XRP conditions materially change across `1h`, `4h`, `1d` and `1w`. The scorer is decision support, not a deterministic predictor or execution system.

## Inputs

- macro/liquidity;
- equities and crypto-sensitive equities;
- BTC/ETH and market breadth;
- XRP relative strength;
- derivatives structure;
- XRPL activity;
- provider coverage, freshness and agreement.

## Outputs

- bull and bear scores;
- regime label;
- squeeze and distribution risk;
- data confidence;
- model confidence;
- directional conviction;
- operational confidence;
- output block reasons;
- drivers, invalidations and prototype similarities.

## Confidence semantics

- `bull_score / 100` is a raw expert score, not calibrated probability.
- `data_confidence` measures whether the evidence plane is usable.
- `model_confidence` measures heuristic completeness and component coherence.
- `directional_conviction` measures distance from neutral.
- `confidence` combines operational data/model confidence and must not be described as forecast accuracy.

Data quality has zero directional weight. It can only permit, degrade or block output.

## Known limitations

- Initial weights are expert priors.
- Historical prototypes are illustrative and not empirical nearest-neighbour forecasts.
- Derivatives and XRPL inputs are absent unless explicitly supplied.
- Market relationships can change structurally.
- FRED availability currently has date precision, not exact release-time precision.
- Point-in-time backfill, calibration and immutable shadow evaluation remain incomplete.

## Promotion criteria

The engine cannot expose calibrated probabilities until it passes:

1. versioned point-in-time backfill;
2. expanding and rolling walk-forward evaluation with embargo;
3. reliability curves and Brier decomposition;
4. false-alert, ablation and weight-stability reviews;
5. provider-substitution tests;
6. at least 30 days of immutable shadow predictions and realized outcomes.
