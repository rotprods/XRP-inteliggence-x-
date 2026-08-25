# E3 — Calibration and model governance

## Objective

Turn heuristic regime scores into measured, horizon-specific probabilities with explicit uncertainty and stable promotion rules.

## Metrics

- Brier score and log loss;
- calibration curve and expected calibration error;
- directional accuracy;
- precision, recall and false-alert rate by regime;
- maximum adverse/favorable excursion;
- lead time and regime-duration error;
- provider substitution and missing-source sensitivity.

## Experiments

- expanding and rolling walk-forward validation;
- embargo and purge-gap sensitivity;
- component ablations;
- expert-weight stability;
- threshold sensitivity;
- provider substitution;
- event-feature decay;
- champion/challenger comparisons.

## Acceptance criteria

- every model version has a model card, immutable configuration and training-data manifest;
- probabilities are calibrated separately for 1h, 4h, 1d and 1w;
- confidence is capped by data status;
- low-confidence outputs are blocked;
- promotion requires a predeclared metric improvement without material risk regression;
- no model is promoted from an in-sample chart or a single historical analogue.
