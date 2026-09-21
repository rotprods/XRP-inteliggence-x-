from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.calibration_evidence_v1 import CalibrationEvidenceV1
from xrp_regime_engine.research_horizon import ResearchHorizon


class PromotionState(StrEnum):
    BLOCKED = "BLOCKED"
    ELIGIBLE_FOR_CALIBRATION_REVIEW = "ELIGIBLE_FOR_CALIBRATION_REVIEW"


class StabilityAxis(StrEnum):
    TEMPORAL = "TEMPORAL"
    REGIME = "REGIME"


CANONICAL_FORECAST_HORIZONS = (
    ResearchHorizon.H1,
    ResearchHorizon.H4,
    ResearchHorizon.D1,
    ResearchHorizon.W1,
    ResearchHorizon.M1,
    ResearchHorizon.M3,
    ResearchHorizon.Y1,
)
CANONICAL_XRP_BARRIERS = (2.0, 3.0, 3.65, 5.0, 7.34, 10.0, 17.0, 26.6, 50.0)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _finite(value: float, field: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _nonempty(value: str, field: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{field} is required")
    return result


def _barrier_key(value: float) -> str:
    return format(_finite(value, "barrier"), ".12g")


@dataclass(frozen=True, slots=True)
class BinaryCalibrationPolicy:
    min_samples: int = 200
    min_class_count: int = 20
    max_ece: float = 0.05
    max_calibration_gap: float = 0.12
    max_abs_intercept: float = 0.25
    min_slope: float = 0.75
    max_slope: float = 1.25
    min_brier_improvement: float = 0.0

    def __post_init__(self) -> None:
        if self.min_samples < 1 or self.min_class_count < 1:
            raise ValueError("sample thresholds must be positive")
        if any(
            _finite(value, name) < 0
            for name, value in (
                ("max_ece", self.max_ece),
                ("max_calibration_gap", self.max_calibration_gap),
                ("max_abs_intercept", self.max_abs_intercept),
                ("min_brier_improvement", self.min_brier_improvement),
            )
        ):
            raise ValueError("calibration thresholds cannot be negative")
        if self.min_slope <= 0 or self.max_slope < self.min_slope:
            raise ValueError("slope bounds are invalid")


@dataclass(frozen=True, slots=True)
class StabilityPolicy:
    min_slices: int = 3
    max_brier_spread: float = 0.05
    max_ece_spread: float = 0.04
    max_slope_spread: float = 0.40

    def __post_init__(self) -> None:
        if self.min_slices < 1:
            raise ValueError("min_slices must be positive")
        if any(
            _finite(value, name) < 0
            for name, value in (
                ("max_brier_spread", self.max_brier_spread),
                ("max_ece_spread", self.max_ece_spread),
                ("max_slope_spread", self.max_slope_spread),
            )
        ):
            raise ValueError("stability thresholds cannot be negative")


@dataclass(frozen=True, slots=True)
class BinaryAssessment:
    eligible: bool
    reasons: tuple[str, ...]


def assess_binary_evidence(
    evidence: CalibrationEvidenceV1,
    policy: BinaryCalibrationPolicy,
) -> BinaryAssessment:
    if evidence.sample_count != evidence.positive_count + evidence.negative_count:
        raise ValueError("class counts do not sum to sample_count")
    if evidence.evaluation_end < evidence.evaluation_start:
        raise ValueError("evaluation interval is reversed")
    if evidence.probability_calibrated or evidence.decision_authority or evidence.execution_weight != 0:
        raise ValueError("upstream evidence must remain non-authoritative")
    for name, value in (
        ("brier_score", evidence.brier_score),
        ("log_loss", evidence.log_loss),
        ("ece", evidence.ece),
        ("maximum_calibration_gap", evidence.maximum_calibration_gap),
    ):
        _finite(value, name)
    if not 0 <= evidence.brier_score <= 1 or not 0 <= evidence.ece <= 1:
        raise ValueError("bounded calibration metrics must be within [0, 1]")
    if not 0 <= evidence.maximum_calibration_gap <= 1 or evidence.log_loss < 0:
        raise ValueError("calibration gap/log loss is invalid")
    if sum(item.count for item in evidence.reliability_bins) != evidence.sample_count:
        raise ValueError("reliability bins do not cover sample_count")

    reasons: list[str] = []
    if evidence.sample_count < policy.min_samples:
        reasons.append("INSUFFICIENT_SAMPLE_COUNT")
    if evidence.positive_count < policy.min_class_count:
        reasons.append("INSUFFICIENT_POSITIVE_CLASS")
    if evidence.negative_count < policy.min_class_count:
        reasons.append("INSUFFICIENT_NEGATIVE_CLASS")
    if evidence.ece > policy.max_ece:
        reasons.append("ECE_ABOVE_LIMIT")
    if evidence.maximum_calibration_gap > policy.max_calibration_gap:
        reasons.append("MAX_CALIBRATION_GAP_ABOVE_LIMIT")
    if evidence.calibration_intercept is None:
        reasons.append("CALIBRATION_INTERCEPT_MISSING")
    elif abs(_finite(evidence.calibration_intercept, "calibration_intercept")) > policy.max_abs_intercept:
        reasons.append("CALIBRATION_INTERCEPT_OUTSIDE_LIMIT")
    if evidence.calibration_slope is None:
        reasons.append("CALIBRATION_SLOPE_MISSING")
    elif not policy.min_slope <= _finite(evidence.calibration_slope, "calibration_slope") <= policy.max_slope:
        reasons.append("CALIBRATION_SLOPE_OUTSIDE_LIMIT")
    if evidence.reference_base_rate_brier is None:
        reasons.append("REFERENCE_BRIER_MISSING")
    elif evidence.brier_score > _finite(evidence.reference_base_rate_brier, "reference_base_rate_brier") - policy.min_brier_improvement:
        reasons.append("NO_BRIER_IMPROVEMENT_OVER_BASE_RATE")
    return BinaryAssessment(not reasons, tuple(reasons))


@dataclass(frozen=True, slots=True)
class CalibrationSlice:
    axis: StabilityAxis
    slice_id: str
    evidence: CalibrationEvidenceV1

    def __post_init__(self) -> None:
        _nonempty(self.slice_id, "slice_id")


@dataclass(frozen=True, slots=True)
class CalibrationStabilityMatrix:
    matrix_id: str
    axis: StabilityAxis
    horizon: ResearchHorizon
    event_key: str
    slice_ids: tuple[str, ...]
    brier_spread: float
    ece_spread: float
    slope_spread: float | None
    eligible: bool
    reasons: tuple[str, ...]
    probability_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def build_stability_matrix(
    slices: Sequence[CalibrationSlice],
    *,
    evidence_policy: BinaryCalibrationPolicy,
    stability_policy: StabilityPolicy,
    required_slice_ids: Sequence[str] = (),
) -> CalibrationStabilityMatrix:
    if not slices:
        raise ValueError("slices cannot be empty")
    axis = slices[0].axis
    horizon = slices[0].evidence.horizon
    event_key = slices[0].evidence.event_key
    if any(item.axis is not axis for item in slices):
        raise ValueError("stability matrix cannot mix axes")
    if any(item.evidence.horizon is not horizon or item.evidence.event_key != event_key for item in slices):
        raise ValueError("stability matrix cannot mix horizon/event_key")
    ids = [item.slice_id for item in slices]
    if len(ids) != len(set(ids)):
        raise ValueError("slice_id values must be unique")
    ordered = tuple(sorted(slices, key=lambda item: item.slice_id))
    if axis is StabilityAxis.TEMPORAL:
        chronology = sorted(ordered, key=lambda item: item.evidence.evaluation_start)
        if any(
            left.evidence.evaluation_end >= right.evidence.evaluation_start
            for left, right in zip(chronology, chronology[1:], strict=False)
        ):
            raise ValueError("temporal slices must not overlap")
    required = {_nonempty(item, "required_slice_id") for item in required_slice_ids}
    reasons: list[str] = []
    if len(ordered) < stability_policy.min_slices:
        reasons.append("INSUFFICIENT_STABILITY_SLICES")
    if required - set(ids):
        reasons.append("REQUIRED_STABILITY_SLICES_MISSING")
    for item in ordered:
        assessment = assess_binary_evidence(item.evidence, evidence_policy)
        reasons.extend(f"SLICE:{item.slice_id}:{reason}" for reason in assessment.reasons)
    briers = [item.evidence.brier_score for item in ordered]
    eces = [item.evidence.ece for item in ordered]
    slopes = [item.evidence.calibration_slope for item in ordered]
    brier_spread = max(briers) - min(briers)
    ece_spread = max(eces) - min(eces)
    slope_spread = None
    if all(value is not None for value in slopes):
        values = [float(value) for value in slopes if value is not None]
        slope_spread = max(values) - min(values)
    if brier_spread > stability_policy.max_brier_spread:
        reasons.append("BRIER_INSTABILITY")
    if ece_spread > stability_policy.max_ece_spread:
        reasons.append("ECE_INSTABILITY")
    if slope_spread is None:
        reasons.append("SLOPE_STABILITY_UNAVAILABLE")
    elif slope_spread > stability_policy.max_slope_spread:
        reasons.append("SLOPE_INSTABILITY")
    material = {
        "axis": axis.value,
        "horizon": horizon.value,
        "event_key": event_key,
        "slice_ids": [item.slice_id for item in ordered],
        "evidence_ids": [item.evidence.evidence_id for item in ordered],
        "brier_spread": brier_spread,
        "ece_spread": ece_spread,
        "slope_spread": slope_spread,
        "reasons": sorted(reasons),
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return CalibrationStabilityMatrix(
        f"calibration-stability:sha256:{digest}", axis, horizon, event_key,
        tuple(item.slice_id for item in ordered), brier_spread, ece_spread,
        slope_spread, not reasons, tuple(sorted(reasons))
    )


@dataclass(frozen=True, slots=True)
class CalibrationPromotionDecision:
    decision_id: str
    horizon: ResearchHorizon
    event_key: str
    evidence_id: str
    state: PromotionState
    reasons: tuple[str, ...]
    probability_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def evaluate_promotion(
    evidence: CalibrationEvidenceV1,
    *,
    temporal: CalibrationStabilityMatrix,
    regime: CalibrationStabilityMatrix,
    policy: BinaryCalibrationPolicy,
) -> CalibrationPromotionDecision:
    assessment = assess_binary_evidence(evidence, policy)
    for matrix, axis in ((temporal, StabilityAxis.TEMPORAL), (regime, StabilityAxis.REGIME)):
        if matrix.axis is not axis:
            raise ValueError("stability axis mismatch")
        if matrix.horizon is not evidence.horizon or matrix.event_key != evidence.event_key:
            raise ValueError("stability matrix does not match evidence")
    reasons = list(assessment.reasons)
    if not temporal.eligible:
        reasons.append("TEMPORAL_STABILITY_BLOCKED")
    if not regime.eligible:
        reasons.append("REGIME_STABILITY_BLOCKED")
    state = PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW if not reasons else PromotionState.BLOCKED
    material = {
        "horizon": evidence.horizon.value,
        "event_key": evidence.event_key,
        "evidence_id": evidence.evidence_id,
        "temporal_matrix_id": temporal.matrix_id,
        "regime_matrix_id": regime.matrix_id,
        "state": state.value,
        "reasons": sorted(reasons),
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return CalibrationPromotionDecision(
        f"calibration-promotion:sha256:{digest}", evidence.horizon,
        evidence.event_key, evidence.evidence_id, state, tuple(sorted(reasons))
    )


@dataclass(frozen=True, slots=True)
class BarrierCalibrationCell:
    horizon: ResearchHorizon
    barrier: float
    event_key: str
    state: PromotionState
    reasons: tuple[str, ...]
    decision_id: str | None


@dataclass(frozen=True, slots=True)
class BarrierCalibrationMatrix:
    matrix_id: str
    horizons: tuple[ResearchHorizon, ...]
    barriers: tuple[float, ...]
    cells: tuple[BarrierCalibrationCell, ...]
    state: PromotionState
    probability_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def _matrix_lookup(
    matrices: Sequence[CalibrationStabilityMatrix], axis: StabilityAxis
) -> dict[tuple[ResearchHorizon, str], CalibrationStabilityMatrix]:
    result: dict[tuple[ResearchHorizon, str], CalibrationStabilityMatrix] = {}
    for matrix in matrices:
        if matrix.axis is not axis:
            raise ValueError("stability matrix axis mismatch")
        key = (matrix.horizon, matrix.event_key)
        if key in result:
            raise ValueError("duplicate stability matrix")
        result[key] = matrix
    return result


def build_barrier_matrix(
    evidences: Sequence[CalibrationEvidenceV1],
    *,
    horizons: Sequence[ResearchHorizon] = CANONICAL_FORECAST_HORIZONS,
    barriers: Sequence[float] = CANONICAL_XRP_BARRIERS,
    temporal_matrices: Sequence[CalibrationStabilityMatrix],
    regime_matrices: Sequence[CalibrationStabilityMatrix],
    policy: BinaryCalibrationPolicy,
) -> BarrierCalibrationMatrix:
    h = tuple(dict.fromkeys(horizons))
    b = tuple(sorted({_finite(value, "barrier") for value in barriers}))
    if not h or not b or any(value <= 0 for value in b):
        raise ValueError("barrier matrix requires horizons and positive barriers")
    evidence_map: dict[tuple[ResearchHorizon, str], CalibrationEvidenceV1] = {}
    for item in evidences:
        key = (item.horizon, item.event_key)
        if key in evidence_map:
            raise ValueError("duplicate calibration evidence")
        evidence_map[key] = item
    temporal = _matrix_lookup(temporal_matrices, StabilityAxis.TEMPORAL)
    regime = _matrix_lookup(regime_matrices, StabilityAxis.REGIME)
    cells: list[BarrierCalibrationCell] = []
    for horizon in h:
        for barrier in b:
            event_key = f"touch_price:{_barrier_key(barrier)}"
            key = (horizon, event_key)
            ev = evidence_map.get(key)
            t = temporal.get(key)
            r = regime.get(key)
            reasons: list[str] = []
            decision_id = None
            if ev is None:
                reasons.append("MISSING_CALIBRATION_EVIDENCE")
            if t is None:
                reasons.append("MISSING_TEMPORAL_STABILITY")
            if r is None:
                reasons.append("MISSING_REGIME_STABILITY")
            if ev is not None and t is not None and r is not None:
                decision = evaluate_promotion(ev, temporal=t, regime=r, policy=policy)
                decision_id = decision.decision_id
                reasons.extend(decision.reasons)
            state = PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW if not reasons else PromotionState.BLOCKED
            cells.append(BarrierCalibrationCell(horizon, barrier, event_key, state, tuple(sorted(reasons)), decision_id))
    state = PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW if all(
        cell.state is PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW for cell in cells
    ) else PromotionState.BLOCKED
    material = {
        "horizons": [item.value for item in h],
        "barriers": list(b),
        "cells": [(cell.horizon.value, cell.event_key, cell.state.value, cell.decision_id) for cell in cells],
        "state": state.value,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return BarrierCalibrationMatrix(
        f"barrier-calibration-matrix:sha256:{digest}", h, b, tuple(cells), state
    )
