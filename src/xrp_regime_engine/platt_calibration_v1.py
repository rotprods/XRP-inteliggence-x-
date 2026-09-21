from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from xrp_regime_engine.calibration_evidence_v1 import (
    ResolvedPredictionRecord,
    _logistic_recalibration,
)
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
        allow_nan=False,
    )


def _probability(value: float, field: str) -> float:
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 <= numeric <= 1:
        raise ValueError(f"{field} must be finite and within [0, 1]")
    return numeric


def _logit(value: float, epsilon: float) -> float:
    clipped = min(max(value, epsilon), 1 - epsilon)
    return math.log(clipped / (1 - clipped))


@dataclass(frozen=True, slots=True)
class PlattCalibratorCandidate:
    calibrator_id: str
    calibrator_sha256: str
    horizon: ResearchHorizon
    event_key: str
    fit_cutoff: datetime
    fit_prediction_ids: tuple[str, ...]
    fit_sample_count: int
    purged_count: int
    positive_count: int
    negative_count: int
    intercept: float
    slope: float
    epsilon: float
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    def transform(self, raw_score: float) -> float:
        score = _probability(raw_score, "raw_score")
        linear = max(
            min(
                self.intercept + self.slope * _logit(score, self.epsilon),
                35.0,
            ),
            -35.0,
        )
        return 1.0 / (1.0 + math.exp(-linear))

    def to_payload(self) -> dict[str, object]:
        return {
            "calibrator_id": self.calibrator_id,
            "calibrator_sha256": self.calibrator_sha256,
            "horizon": self.horizon.value,
            "event_key": self.event_key,
            "fit_cutoff": self.fit_cutoff.isoformat(),
            "fit_prediction_ids": list(self.fit_prediction_ids),
            "fit_sample_count": self.fit_sample_count,
            "purged_count": self.purged_count,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "intercept": self.intercept,
            "slope": self.slope,
            "epsilon": self.epsilon,
            "probability_calibrated": self.probability_calibrated,
            "decision_authority": self.decision_authority,
            "execution_weight": self.execution_weight,
        }


def fit_platt_calibrator_candidate(
    records: Sequence[ResolvedPredictionRecord],
    *,
    fit_cutoff: datetime,
    min_samples: int = 20,
    min_class_count: int = 5,
    epsilon: float = 1e-12,
) -> PlattCalibratorCandidate:
    if not records:
        raise ValueError("records cannot be empty")
    cutoff = _utc(fit_cutoff, "fit_cutoff")
    if min_samples < 2:
        raise ValueError("min_samples must be >= 2")
    if min_class_count < 1:
        raise ValueError("min_class_count must be positive")
    if not 0 < epsilon < 0.5:
        raise ValueError("epsilon must be within (0, 0.5)")
    horizons = {item.horizon for item in records}
    events = {item.event_key for item in records}
    if len(horizons) != 1 or len(events) != 1:
        raise ValueError("calibrator fit requires one horizon and one event_key")
    eligible = tuple(
        sorted(
            (
                item
                for item in records
                if _utc(item.prediction_time, "prediction_time") < cutoff
                and _utc(item.resolved_at, "resolved_at") < cutoff
            ),
            key=lambda item: (item.prediction_time, item.prediction_id),
        )
    )
    purged_count = len(records) - len(eligible)
    if len(eligible) < min_samples:
        raise ValueError("not enough chronologically eligible calibration samples")
    positive_count = sum(1 for item in eligible if item.actual)
    negative_count = len(eligible) - positive_count
    if positive_count < min_class_count or negative_count < min_class_count:
        raise ValueError("calibration fit requires minimum samples from both classes")
    intercept, slope = _logistic_recalibration(eligible, epsilon=epsilon)
    if (
        intercept is None
        or slope is None
        or not math.isfinite(intercept)
        or not math.isfinite(slope)
    ):
        raise ValueError("calibration fit is singular or non-finite")
    prediction_ids = tuple(item.prediction_id for item in eligible)
    material: dict[str, object] = {
        "horizon": eligible[0].horizon.value,
        "event_key": eligible[0].event_key,
        "fit_cutoff": cutoff.isoformat(),
        "fit_prediction_ids": list(prediction_ids),
        "fit_sample_count": len(eligible),
        "purged_count": purged_count,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "intercept": intercept,
        "slope": slope,
        "epsilon": epsilon,
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return PlattCalibratorCandidate(
        calibrator_id=f"platt-candidate:sha256:{digest}",
        calibrator_sha256=digest,
        horizon=eligible[0].horizon,
        event_key=eligible[0].event_key,
        fit_cutoff=cutoff,
        fit_prediction_ids=prediction_ids,
        fit_sample_count=len(eligible),
        purged_count=purged_count,
        positive_count=positive_count,
        negative_count=negative_count,
        intercept=intercept,
        slope=slope,
        epsilon=epsilon,
    )


@dataclass(frozen=True, slots=True)
class CalibratedProbabilityCandidate:
    candidate_id: str
    candidate_sha256: str
    prediction_id: str
    calibrator_id: str
    prediction_time: datetime
    horizon: ResearchHorizon
    event_key: str
    raw_score: float
    calibrated_probability: float
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def apply_platt_candidate(
    calibrator: PlattCalibratorCandidate,
    prediction: OOSPrediction,
) -> CalibratedProbabilityCandidate:
    if prediction.horizon is not calibrator.horizon:
        raise ValueError("prediction horizon does not match calibrator")
    if prediction.event_key != calibrator.event_key:
        raise ValueError("prediction event_key does not match calibrator")
    prediction_time = _utc(prediction.prediction_time, "prediction_time")
    if prediction_time < calibrator.fit_cutoff:
        raise ValueError("prediction_time cannot precede calibrator fit_cutoff")
    probability = calibrator.transform(prediction.raw_score)
    material: dict[str, object] = {
        "prediction_id": prediction.prediction_id,
        "calibrator_id": calibrator.calibrator_id,
        "prediction_time": prediction_time.isoformat(),
        "horizon": prediction.horizon.value,
        "event_key": prediction.event_key,
        "raw_score": prediction.raw_score,
        "calibrated_probability": probability,
        "probability_calibrated": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return CalibratedProbabilityCandidate(
        candidate_id=f"calibrated-score-candidate:sha256:{digest}",
        candidate_sha256=digest,
        prediction_id=prediction.prediction_id,
        calibrator_id=calibrator.calibrator_id,
        prediction_time=prediction_time,
        horizon=prediction.horizon,
        event_key=prediction.event_key,
        raw_score=prediction.raw_score,
        calibrated_probability=probability,
    )


def candidate_evaluation_records(
    candidates: Sequence[CalibratedProbabilityCandidate],
    outcomes: Sequence[ResolvedOOSOutcome],
) -> tuple[ResolvedPredictionRecord, ...]:
    if not candidates or not outcomes:
        raise ValueError("candidates and outcomes cannot be empty")
    by_prediction: dict[str, CalibratedProbabilityCandidate] = {}
    for candidate in candidates:
        if candidate.prediction_id in by_prediction:
            raise ValueError(
                f"duplicate candidate for prediction_id: {candidate.prediction_id}"
            )
        by_prediction[candidate.prediction_id] = candidate
    outcome_by_prediction: dict[str, ResolvedOOSOutcome] = {}
    for outcome in outcomes:
        if outcome.prediction_id in outcome_by_prediction:
            raise ValueError(
                f"duplicate outcome for prediction_id: {outcome.prediction_id}"
            )
        outcome_by_prediction[outcome.prediction_id] = outcome
    missing = set(by_prediction) - set(outcome_by_prediction)
    orphan = set(outcome_by_prediction) - set(by_prediction)
    if missing or orphan:
        raise ValueError("candidate/outcome identity mismatch")
    records: list[ResolvedPredictionRecord] = []
    for prediction_id, candidate in by_prediction.items():
        outcome = outcome_by_prediction[prediction_id]
        if candidate.horizon is not outcome.horizon or candidate.event_key != outcome.event_key:
            raise ValueError("candidate/outcome horizon or event mismatch")
        if candidate.prediction_time != outcome.prediction_time:
            raise ValueError("candidate/outcome prediction_time mismatch")
        records.append(
            ResolvedPredictionRecord(
                prediction_id=prediction_id,
                prediction_time=candidate.prediction_time,
                horizon=candidate.horizon,
                event_key=candidate.event_key,
                raw_score=candidate.calibrated_probability,
                actual=outcome.actual,
                resolved_at=outcome.resolved_at,
            )
        )
    return tuple(
        sorted(records, key=lambda item: (item.prediction_time, item.prediction_id))
    )
