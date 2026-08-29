from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from xrp_regime_engine.features import compute_features
from xrp_regime_engine.models import Horizon
from xrp_regime_engine.regime import score_regime


@dataclass(frozen=True)
class BacktestResult:
    observations: int
    directional_accuracy: float
    raw_score_brier: float
    average_confidence: float
    average_data_confidence: float
    average_model_confidence: float
    probability_calibrated: bool = False


def _validate_research_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("research frame index must be a DatetimeIndex")
    if frame.index.tz is None:
        raise ValueError("research frame timestamps must be timezone-aware")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("research frame timestamps must be monotonic increasing")
    if frame.index.has_duplicates:
        raise ValueError("research frame timestamps must be unique")
    return frame.index


def _validate_available_at(
    frame: pd.DataFrame,
    available_at: pd.Series | None,
    *,
    require_point_in_time: bool,
) -> pd.Series | None:
    index = _validate_research_index(frame)
    if available_at is None:
        if require_point_in_time:
            raise ValueError("point-in-time research requires available_at timestamps")
        return None
    if not available_at.index.equals(index):
        raise ValueError("available_at index must exactly match the research frame index")
    normalized = pd.to_datetime(available_at, utc=True, errors="coerce", format="mixed")
    if normalized.isna().any():
        raise ValueError("available_at contains missing or invalid timestamps")
    observed_utc = index.tz_convert("UTC")
    if (normalized.array < observed_utc.array).any():
        raise ValueError("available_at cannot precede observed_at")
    return pd.Series(normalized.array, index=index, name="available_at")


def expanding_walk_forward(
    frame: pd.DataFrame,
    min_train: int = 365,
    step: int = 7,
    forward: int = 7,
    *,
    supplemental: Mapping[str, float | None] | None = None,
    available_at: pd.Series | None = None,
    require_point_in_time: bool = False,
    train_window: int | None = None,
    embargo: int = 0,
) -> BacktestResult:
    """Evaluate the expert score without pretending it is calibrated probability.

    The returned ``raw_score_brier`` uses ``bull_score / 100`` as a raw score.
    It is a diagnostic only; ``probability_calibrated`` remains false until a
    leakage-safe calibration layer is trained on point-in-time data.

    When ``available_at`` is supplied, every simulated decision sees only rows
    whose availability timestamp is less than or equal to the decision time.
    ``require_point_in_time=True`` makes that contract mandatory for release
    research instead of silently falling back to observation-time history.

    ``train_window=None`` is expanding-window validation; a finite ``train_window``
    enables rolling-window validation. ``embargo`` inserts untouched observations
    between the decision point and the forward label to make label separation
    explicit in research experiments.
    """

    if min_train < 30 or step < 1 or forward < 1:
        raise ValueError("min_train, step and forward must be positive")
    if embargo < 0:
        raise ValueError("embargo must be non-negative")
    if train_window is not None and train_window < min_train:
        raise ValueError("train_window cannot be smaller than min_train")
    if "XRP_USD" not in frame.columns:
        raise ValueError("research frame must contain XRP_USD")

    index = _validate_research_index(frame)
    availability = _validate_available_at(
        frame,
        available_at,
        require_point_in_time=require_point_in_time,
    )

    outcomes: list[int] = []
    raw_scores: list[float] = []
    confidences: list[float] = []
    data_confidences: list[float] = []
    model_confidences: list[float] = []

    for end in range(min_train, len(frame) - forward - embargo, step):
        decision_time = index[end - 1]
        start = 0 if train_window is None else max(0, end - train_window)
        history = frame.iloc[start:end].copy()
        if availability is not None:
            known_mask = availability.iloc[start:end] <= decision_time
            history = history.loc[known_mask.to_numpy()]
            if len(history) < min_train:
                continue
        features = compute_features(history, supplemental=supplemental)
        snapshot = score_regime(features, Horizon.D1)
        current = float(frame["XRP_USD"].iloc[end - 1])
        future = float(frame["XRP_USD"].iloc[end + embargo + forward - 1])
        outcome = int(future > current)
        raw_score = snapshot.bull_score / 100
        outcomes.append(outcome)
        raw_scores.append(raw_score)
        confidences.append(snapshot.confidence)
        data_confidences.append(snapshot.data_confidence)
        model_confidences.append(snapshot.model_confidence)

    if not outcomes:
        raise ValueError("not enough observations for walk-forward evaluation")

    predicted = [int(value >= 0.5) for value in raw_scores]
    accuracy = float(np.mean([a == b for a, b in zip(predicted, outcomes, strict=True)]))
    raw_brier = float(
        np.mean([(score - actual) ** 2 for score, actual in zip(raw_scores, outcomes, strict=True)])
    )
    return BacktestResult(
        observations=len(outcomes),
        directional_accuracy=accuracy,
        raw_score_brier=raw_brier,
        average_confidence=float(np.mean(confidences)),
        average_data_confidence=float(np.mean(data_confidences)),
        average_model_confidence=float(np.mean(model_confidences)),
    )
