# Backtesting and Research Protocol

## Mandatory controls

- Expanding or rolling windows only.
- No random train/test split for time series.
- Embargo around label horizons.
- Feature transforms fitted inside each training window.
- Point-in-time availability for macro and news.
- Provider universe fixed or explicitly versioned.
- Costs and slippage included before any future execution research.

## Core metrics

- Brier score and calibration curve;
- directional accuracy by horizon;
- precision and recall by regime label;
- false alert rate;
- maximum adverse and favourable excursion;
- stability by market cycle;
- sensitivity to weights and thresholds;
- performance after removing each data family.

## Shadow mode

Operate at least 30 days without influencing trades. Archive every emitted snapshot and compare it with subsequent outcomes and analyst annotations.
