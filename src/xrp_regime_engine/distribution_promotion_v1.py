from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.return_distribution_v1 import REQUIRED_QUANTILES, ReturnDistributionEvidenceV1


class DistributionPromotionState(StrEnum):
    BLOCKED = "BLOCKED"
    ELIGIBLE_FOR_CALIBRATION_REVIEW = "ELIGIBLE_FOR_CALIBRATION_REVIEW"


class DistributionStabilityAxis(StrEnum):
    TEMPORAL = "TEMPORAL"
    REGIME = "REGIME"


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


@dataclass(frozen=True, slots=True)
class DistributionCalibrationPolicy:
    min_samples: int = 200
    max_abs_quantile_coverage_error: float = 0.07
    max_interval_50_error: float = 0.10
    max_interval_80_error: float = 0.10
    max_median_absolute_error: float | None = None

    def __post_init__(self) -> None:
        if self.min_samples < 1:
            raise ValueError("min_samples must be positive")
        for name, value in (
            ("max_abs_quantile_coverage_error", self.max_abs_quantile_coverage_error),
            ("max_interval_50_error", self.max_interval_50_error),
            ("max_interval_80_error", self.max_interval_80_error),
        ):
            if _finite(value, name) < 0:
                raise ValueError("distribution thresholds cannot be negative")
        if self.max_median_absolute_error is not None and _finite(
            self.max_median_absolute_error, "max_median_absolute_error"
        ) < 0:
            raise ValueError("max_median_absolute_error cannot be negative")


@dataclass(frozen=True, slots=True)
class DistributionStabilityPolicy:
    min_slices: int = 3
    max_quantile_error_spread: float = 0.05
    max_interval_50_spread: float = 0.10
    max_interval_80_spread: float = 0.10

    def __post_init__(self) -> None:
        if self.min_slices < 1:
            raise ValueError("min_slices must be positive")
        if any(
            _finite(value, name) < 0
            for name, value in (
                ("max_quantile_error_spread", self.max_quantile_error_spread),
                ("max_interval_50_spread", self.max_interval_50_spread),
                ("max_interval_80_spread", self.max_interval_80_spread),
            )
        ):
            raise ValueError("distribution stability thresholds cannot be negative")


@dataclass(frozen=True, slots=True)
class DistributionAssessment:
    eligible: bool
    reasons: tuple[str, ...]


def assess_distribution_evidence(
    evidence: ReturnDistributionEvidenceV1,
    policy: DistributionCalibrationPolicy,
) -> DistributionAssessment:
    if evidence.evaluation_end < evidence.evaluation_start:
        raise ValueError("evaluation interval is reversed")
    if evidence.distribution_calibrated or evidence.decision_authority or evidence.execution_weight != 0:
        raise ValueError("upstream distribution evidence must remain non-authoritative")
    if tuple(item.quantile for item in evidence.quantile_evidence) != REQUIRED_QUANTILES:
        raise ValueError("canonical P10/P25/P50/P75/P90 evidence is required")
    reasons: list[str] = []
    if evidence.sample_count < policy.min_samples:
        reasons.append("INSUFFICIENT_SAMPLE_COUNT")
    for item in evidence.quantile_evidence:
        pinball = _finite(item.mean_pinball_loss, "mean_pinball_loss")
        coverage = _finite(item.empirical_coverage, "empirical_coverage")
        error = _finite(item.coverage_error, "coverage_error")
        if pinball < 0 or not 0 <= coverage <= 1:
            raise ValueError("quantile evidence is structurally invalid")
        if not math.isclose(error, coverage - item.quantile, abs_tol=1e-12):
            raise ValueError("coverage_error is inconsistent")
        if abs(error) > policy.max_abs_quantile_coverage_error:
            reasons.append(f"QUANTILE_COVERAGE:{format(item.quantile, '.2f')}")
    i50 = _finite(evidence.interval_50_coverage, "interval_50_coverage")
    i80 = _finite(evidence.interval_80_coverage, "interval_80_coverage")
    if not 0 <= i50 <= 1 or not 0 <= i80 <= 1:
        raise ValueError("interval coverage must be within [0, 1]")
    if abs(i50 - 0.50) > policy.max_interval_50_error:
        reasons.append("INTERVAL_50_COVERAGE_OUTSIDE_LIMIT")
    if abs(i80 - 0.80) > policy.max_interval_80_error:
        reasons.append("INTERVAL_80_COVERAGE_OUTSIDE_LIMIT")
    mae = _finite(evidence.median_absolute_error, "median_absolute_error")
    if mae < 0:
        raise ValueError("median_absolute_error cannot be negative")
    if policy.max_median_absolute_error is not None and mae > policy.max_median_absolute_error:
        reasons.append("MEDIAN_ABSOLUTE_ERROR_ABOVE_LIMIT")
    return DistributionAssessment(not reasons, tuple(reasons))


@dataclass(frozen=True, slots=True)
class DistributionSlice:
    axis: DistributionStabilityAxis
    slice_id: str
    evidence: ReturnDistributionEvidenceV1

    def __post_init__(self) -> None:
        _nonempty(self.slice_id, "slice_id")


@dataclass(frozen=True, slots=True)
class DistributionStabilityMatrix:
    matrix_id: str
    axis: DistributionStabilityAxis
    horizon: ResearchHorizon
    slice_ids: tuple[str, ...]
    max_quantile_error_spread: float
    interval_50_spread: float
    interval_80_spread: float
    eligible: bool
    reasons: tuple[str, ...]
    distribution_calibrated: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def build_distribution_stability_matrix(
    slices: Sequence[DistributionSlice],
    *,
    evidence_policy: DistributionCalibrationPolicy,
    stability_policy: DistributionStabilityPolicy,
    required_slice_ids: Sequence[str] = (),
) -> DistributionStabilityMatrix:
    if not slices:
        raise ValueError("slices cannot be empty")
    axis = slices[0].axis
    horizon = slices[0].evidence.horizon
    if any(item.axis is not axis or item.evidence.horizon is not horizon for item in slices):
        raise ValueError("distribution stability matrix cannot mix axis/horizon")
    ids = [item.slice_id for item in slices]
    if len(ids) != len(set(ids)):
        raise ValueError("slice_id values must be unique")
    ordered = tuple(sorted(slices, key=lambda item: item.slice_id))
    if axis is DistributionStabilityAxis.TEMPORAL:
        chronology = sorted(ordered, key=lambda item: item.evidence.evaluation_start)
        if any(
            left.evidence.evaluation_end >= right.evidence.evaluation_start
            for left, right in zip(chronology, chronology[1:], strict=False)
        ):
            raise ValueError("temporal distribution slices must not overlap")
    reasons: list[str] = []
    if len(ordered) < stability_policy.min_slices:
        reasons.append("INSUFFICIENT_STABILITY_SLICES")
    required = {_nonempty(item, "required_slice_id") for item in required_slice_ids}
    if required - set(ids):
        reasons.append("REQUIRED_STABILITY_SLICES_MISSING")
    for item in ordered:
        assessment = assess_distribution_evidence(item.evidence, evidence_policy)
        reasons.extend(f"SLICE:{item.slice_id}:{reason}" for reason in assessment.reasons)
    errors = [
        max(abs(metric.coverage_error) for metric in item.evidence.quantile_evidence)
        for item in ordered
    ]
    i50 = [item.evidence.interval_50_coverage for item in ordered]
    i80 = [item.evidence.interval_80_coverage for item in ordered]
    error_spread = max(errors) - min(errors)
    i50_spread = max(i50) - min(i50)
    i80_spread = max(i80) - min(i80)
    if error_spread > stability_policy.max_quantile_error_spread:
        reasons.append("QUANTILE_COVERAGE_INSTABILITY")
    if i50_spread > stability_policy.max_interval_50_spread:
        reasons.append("INTERVAL_50_INSTABILITY")
    if i80_spread > stability_policy.max_interval_80_spread:
        reasons.append("INTERVAL_80_INSTABILITY")
    material = {
        "axis": axis.value,
        "horizon": horizon.value,
        "slice_ids": [item.slice_id for item in ordered],
        "evidence_ids": [item.evidence.evidence_id for item in ordered],
        "error_spread": error_spread,
        "i50_spread": i50_spread,
        "i80_spread": i80_spread,
        "reasons": sorted(reasons),
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return DistributionStabilityMatrix(
        f"distribution-stability:sha256:{digest}",
        axis,
        horizon,
        tuple(item.slice_id for item in ordered),
        error_spread,
        i50_spread,
        i80_spread,
        not reasons,
        tuple(sorted(reasons)),
    )


@dataclass(frozen=True, slots=True)
class DistributionPromotionDecision:
    decision_id: str
    horizon: ResearchHorizon
    evidence_id: str
    state: DistributionPromotionState
    reasons: tuple[str, ...]
    distribution_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0


def evaluate_distribution_promotion(
    evidence: ReturnDistributionEvidenceV1,
    *,
    temporal: DistributionStabilityMatrix,
    regime: DistributionStabilityMatrix,
    policy: DistributionCalibrationPolicy,
) -> DistributionPromotionDecision:
    assessment = assess_distribution_evidence(evidence, policy)
    for matrix, axis in (
        (temporal, DistributionStabilityAxis.TEMPORAL),
        (regime, DistributionStabilityAxis.REGIME),
    ):
        if matrix.axis is not axis:
            raise ValueError("distribution stability axis mismatch")
        if matrix.horizon is not evidence.horizon:
            raise ValueError("distribution stability horizon mismatch")
    reasons = list(assessment.reasons)
    if not temporal.eligible:
        reasons.append("TEMPORAL_STABILITY_BLOCKED")
    if not regime.eligible:
        reasons.append("REGIME_STABILITY_BLOCKED")
    state = (
        DistributionPromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
        if not reasons
        else DistributionPromotionState.BLOCKED
    )
    material = {
        "horizon": evidence.horizon.value,
        "evidence_id": evidence.evidence_id,
        "temporal_matrix_id": temporal.matrix_id,
        "regime_matrix_id": regime.matrix_id,
        "state": state.value,
        "reasons": sorted(reasons),
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return DistributionPromotionDecision(
        f"distribution-promotion:sha256:{digest}",
        evidence.horizon,
        evidence.evidence_id,
        state,
        tuple(sorted(reasons)),
    )
