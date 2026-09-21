from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

from xrp_regime_engine.oos_predictions_v1 import OOSPrediction, ResolvedOOSOutcome
from xrp_regime_engine.research_horizon import ResearchHorizon


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _bounded_probability(value: float, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 <= numeric <= 1:
        raise ValueError(f"{field} must be finite and within [0, 1]")
    return numeric


@dataclass(frozen=True, slots=True)
class ResolvedPredictionRecord:
    prediction_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    event_key: str
    raw_score: float
    actual: bool
    resolved_at: datetime


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_score: float | None
    empirical_rate: float | None
    absolute_gap: float | None

    def to_payload(self) -> dict[str, object]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "mean_score": self.mean_score,
            "empirical_rate": self.empirical_rate,
            "absolute_gap": self.absolute_gap,
        }


@dataclass(frozen=True, slots=True)
class CalibrationEvidenceV1:
    evidence_id: str
    evidence_sha256: str
    horizon: ResearchHorizon
    event_key: str
    sample_count: int
    positive_count: int
    negative_count: int
    evaluation_start: datetime
    evaluation_end: datetime
    brier_score: float
    log_loss: float
    ece: float
    maximum_calibration_gap: float
    roc_auc: float | None
    calibration_intercept: float | None
    calibration_slope: float | None
    reference_base_rate: float | None
    reference_base_rate_brier: float | None
    reliability_bins: tuple[ReliabilityBin, ...]
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    def to_payload(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.evidence_sha256,
            "horizon": self.horizon.value,
            "event_key": self.event_key,
            "sample_count": self.sample_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "evaluation_start": self.evaluation_start.isoformat(),
            "evaluation_end": self.evaluation_end.isoformat(),
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "ece": self.ece,
            "maximum_calibration_gap": self.maximum_calibration_gap,
            "roc_auc": self.roc_auc,
            "calibration_intercept": self.calibration_intercept,
            "calibration_slope": self.calibration_slope,
            "reference_base_rate": self.reference_base_rate,
            "reference_base_rate_brier": self.reference_base_rate_brier,
            "reliability_bins": [item.to_payload() for item in self.reliability_bins],
            "probability_calibrated": self.probability_calibrated,
            "decision_authority": self.decision_authority,
            "execution_weight": self.execution_weight,
        }


def join_resolved_predictions(
    predictions: Sequence[OOSPrediction],
    outcomes: Sequence[ResolvedOOSOutcome],
) -> tuple[ResolvedPredictionRecord, ...]:
    if not predictions or not outcomes:
        raise ValueError("predictions and outcomes cannot be empty")
    prediction_by_id: dict[str, OOSPrediction] = {}
    for prediction in predictions:
        if prediction.prediction_id in prediction_by_id:
            raise ValueError(f"duplicate prediction_id: {prediction.prediction_id}")
        prediction_by_id[prediction.prediction_id] = prediction
    outcome_by_prediction: dict[str, ResolvedOOSOutcome] = {}
    for outcome in outcomes:
        if outcome.prediction_id in outcome_by_prediction:
            raise ValueError(f"duplicate outcome for prediction_id: {outcome.prediction_id}")
        outcome_by_prediction[outcome.prediction_id] = outcome
    missing = sorted(set(prediction_by_id) - set(outcome_by_prediction))
    orphan = sorted(set(outcome_by_prediction) - set(prediction_by_id))
    if missing or orphan:
        raise ValueError(
            f"prediction/outcome identity mismatch: missing={missing!r}, orphan={orphan!r}"
        )
    records: list[ResolvedPredictionRecord] = []
    for prediction_id, prediction in prediction_by_id.items():
        outcome = outcome_by_prediction[prediction_id]
        if prediction.feature_row_id != outcome.feature_row_id:
            raise ValueError("prediction/outcome feature_row_id mismatch")
        if prediction.event_key != outcome.event_key:
            raise ValueError("prediction/outcome event_key mismatch")
        if prediction.horizon is not outcome.horizon:
            raise ValueError("prediction/outcome horizon mismatch")
        if prediction.prediction_time != outcome.prediction_time:
            raise ValueError("prediction/outcome prediction_time mismatch")
        if outcome.resolved_at < outcome.label_end_at:
            raise ValueError("outcome resolved before label_end_at")
        records.append(
            ResolvedPredictionRecord(
                prediction_id=prediction_id,
                prediction_time=prediction.prediction_time,
                horizon=prediction.horizon,
                event_key=prediction.event_key,
                raw_score=prediction.raw_score,
                actual=outcome.actual,
                resolved_at=outcome.resolved_at,
            )
        )
    ordered = tuple(
        sorted(records, key=lambda item: (item.prediction_time, item.prediction_id))
    )
    horizons = {item.horizon for item in ordered}
    events = {item.event_key for item in ordered}
    if len(horizons) != 1 or len(events) != 1:
        raise ValueError("calibration evidence must contain one horizon and one event_key")
    return ordered


def _roc_auc(records: Sequence[ResolvedPredictionRecord]) -> float | None:
    positives = [item.raw_score for item in records if item.actual]
    negatives = [item.raw_score for item in records if not item.actual]
    if not positives or not negatives:
        return None
    wins = 0.0
    total = len(positives) * len(negatives)
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / total


def _logistic_recalibration(
    records: Sequence[ResolvedPredictionRecord],
    *,
    epsilon: float,
    max_iterations: int = 100,
) -> tuple[float | None, float | None]:
    if not any(item.actual for item in records) or all(item.actual for item in records):
        return None, None
    x = [
        math.log(
            min(max(item.raw_score, epsilon), 1 - epsilon)
            / (1 - min(max(item.raw_score, epsilon), 1 - epsilon))
        )
        for item in records
    ]
    y = [1.0 if item.actual else 0.0 for item in records]
    intercept = 0.0
    slope = 1.0
    for _ in range(max_iterations):
        probabilities = []
        for value in x:
            linear = max(min(intercept + slope * value, 35.0), -35.0)
            probabilities.append(1.0 / (1.0 + math.exp(-linear)))
        g0 = sum(
            actual - probability
            for actual, probability in zip(y, probabilities, strict=True)
        )
        g1 = sum(
            (actual - probability) * value
            for actual, probability, value in zip(y, probabilities, x, strict=True)
        )
        w = [probability * (1 - probability) for probability in probabilities]
        h00 = sum(w)
        h01 = sum(weight * value for weight, value in zip(w, x, strict=True))
        h11 = sum(
            weight * value * value for weight, value in zip(w, x, strict=True)
        )
        determinant = h00 * h11 - h01 * h01
        if determinant <= 1e-15:
            return None, None
        delta_intercept = (h11 * g0 - h01 * g1) / determinant
        delta_slope = (-h01 * g0 + h00 * g1) / determinant
        intercept += delta_intercept
        slope += delta_slope
        if max(abs(delta_intercept), abs(delta_slope)) < 1e-10:
            return intercept, slope
    return intercept, slope


def build_calibration_evidence(
    records: Sequence[ResolvedPredictionRecord],
    *,
    n_bins: int = 10,
    epsilon: float = 1e-12,
    reference_base_rate: float | None = None,
) -> CalibrationEvidenceV1:
    if not records:
        raise ValueError("records cannot be empty")
    if n_bins < 2:
        raise ValueError("n_bins must be >= 2")
    if not 0 < epsilon < 0.5:
        raise ValueError("epsilon must be within (0, 0.5)")
    if reference_base_rate is not None:
        reference_base_rate = _bounded_probability(
            reference_base_rate, "reference_base_rate"
        )
    ordered = tuple(
        sorted(records, key=lambda item: (item.prediction_time, item.prediction_id))
    )
    horizons = {item.horizon for item in ordered}
    events = {item.event_key for item in ordered}
    if len(horizons) != 1 or len(events) != 1:
        raise ValueError("calibration evidence must contain one horizon and one event_key")
    for item in ordered:
        _utc(item.prediction_time, "prediction_time")
        _utc(item.resolved_at, "resolved_at")
        _bounded_probability(item.raw_score, "raw_score")
    y = [1.0 if item.actual else 0.0 for item in ordered]
    p = [item.raw_score for item in ordered]
    brier = sum(
        (score - actual) ** 2 for score, actual in zip(p, y, strict=True)
    ) / len(p)
    log_loss = -sum(
        actual * math.log(min(max(score, epsilon), 1 - epsilon))
        + (1 - actual)
        * math.log(1 - min(max(score, epsilon), 1 - epsilon))
        for score, actual in zip(p, y, strict=True)
    ) / len(p)

    bins: list[ReliabilityBin] = []
    weighted_gap = 0.0
    maximum_gap = 0.0
    for index in range(n_bins):
        lower = index / n_bins
        upper = (index + 1) / n_bins
        members = [
            (score, actual)
            for score, actual in zip(p, y, strict=True)
            if (lower <= score < upper)
            or (index == n_bins - 1 and score == 1.0)
        ]
        if not members:
            bins.append(ReliabilityBin(lower, upper, 0, None, None, None))
            continue
        mean_score = sum(score for score, _ in members) / len(members)
        empirical_rate = sum(actual for _, actual in members) / len(members)
        gap = abs(mean_score - empirical_rate)
        weighted_gap += gap * len(members)
        maximum_gap = max(maximum_gap, gap)
        bins.append(
            ReliabilityBin(
                lower,
                upper,
                len(members),
                mean_score,
                empirical_rate,
                gap,
            )
        )
    ece = weighted_gap / len(ordered)
    intercept, slope = _logistic_recalibration(ordered, epsilon=epsilon)
    reference_brier = None
    if reference_base_rate is not None:
        reference_brier = sum(
            (reference_base_rate - actual) ** 2 for actual in y
        ) / len(y)

    material: dict[str, object] = {
        "horizon": ordered[0].horizon.value,
        "event_key": ordered[0].event_key,
        "prediction_ids": [item.prediction_id for item in ordered],
        "sample_count": len(ordered),
        "positive_count": int(sum(y)),
        "negative_count": len(y) - int(sum(y)),
        "evaluation_start": ordered[0].prediction_time.isoformat(),
        "evaluation_end": ordered[-1].prediction_time.isoformat(),
        "brier_score": brier,
        "log_loss": log_loss,
        "ece": ece,
        "maximum_calibration_gap": maximum_gap,
        "roc_auc": _roc_auc(ordered),
        "calibration_intercept": intercept,
        "calibration_slope": slope,
        "reference_base_rate": reference_base_rate,
        "reference_base_rate_brier": reference_brier,
        "reliability_bins": [item.to_payload() for item in bins],
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return CalibrationEvidenceV1(
        evidence_id=f"calibration-evidence:sha256:{digest}",
        evidence_sha256=digest,
        horizon=ordered[0].horizon,
        event_key=ordered[0].event_key,
        sample_count=len(ordered),
        positive_count=int(sum(y)),
        negative_count=len(y) - int(sum(y)),
        evaluation_start=ordered[0].prediction_time,
        evaluation_end=ordered[-1].prediction_time,
        brier_score=brier,
        log_loss=log_loss,
        ece=ece,
        maximum_calibration_gap=maximum_gap,
        roc_auc=cast(float | None, material["roc_auc"]),
        calibration_intercept=intercept,
        calibration_slope=slope,
        reference_base_rate=reference_base_rate,
        reference_base_rate_brier=reference_brier,
        reliability_bins=tuple(bins),
    )
