from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from xrp_regime_engine.calibration_promotion_binary_v1 import (
    CANONICAL_FORECAST_HORIZONS,
    CANONICAL_XRP_BARRIERS,
    BarrierCalibrationMatrix,
    CalibrationPromotionDecision,
    PromotionState,
)
from xrp_regime_engine.distribution_promotion_v1 import (
    DistributionPromotionDecision,
    DistributionPromotionState,
)
from xrp_regime_engine.research_horizon import ResearchHorizon


class ScientificCalibrationState(StrEnum):
    BLOCKED = "BLOCKED"
    ELIGIBLE_FOR_SCIENTIFIC_REVIEW = "ELIGIBLE_FOR_SCIENTIFIC_REVIEW"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_id(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise ValueError(f"{field} must use {prefix}<digest>")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field} must contain a lowercase SHA-256 digest")
    return value


def _barrier_key(value: float) -> str:
    return format(value, ".12g")


def _validate_directional_decision(decision: CalibrationPromotionDecision) -> None:
    _content_id(decision.decision_id, "calibration-promotion:sha256:", "decision_id")
    if decision.event_key != "return_gt_0":
        raise ValueError("directional decision event_key must be return_gt_0")
    if (
        decision.probability_calibrated
        or decision.production_ready
        or decision.decision_authority
        or decision.execution_weight != 0.0
    ):
        raise ValueError("directional promotion input must remain non-authoritative")


def _validate_distribution_decision(decision: DistributionPromotionDecision) -> None:
    _content_id(decision.decision_id, "distribution-promotion:sha256:", "decision_id")
    if (
        decision.distribution_calibrated
        or decision.production_ready
        or decision.decision_authority
        or decision.execution_weight != 0.0
    ):
        raise ValueError("distribution promotion input must remain non-authoritative")


def _validate_barrier_matrix(matrix: BarrierCalibrationMatrix) -> None:
    _content_id(matrix.matrix_id, "barrier-calibration-matrix:sha256:", "barrier_matrix_id")
    if (
        matrix.probability_calibrated
        or matrix.production_ready
        or matrix.decision_authority
        or matrix.execution_weight != 0.0
    ):
        raise ValueError("barrier matrix input must remain non-authoritative")
    if len(matrix.horizons) != len(set(matrix.horizons)):
        raise ValueError("barrier matrix horizons must be unique")
    if len(matrix.barriers) != len(set(matrix.barriers)):
        raise ValueError("barrier matrix barriers must be unique")
    canonical_horizons = set(CANONICAL_FORECAST_HORIZONS)
    canonical_barriers = set(CANONICAL_XRP_BARRIERS)
    if not set(matrix.horizons) <= canonical_horizons:
        raise ValueError("barrier matrix contains unsupported horizon")
    if not set(matrix.barriers) <= canonical_barriers:
        raise ValueError("barrier matrix contains unsupported barrier")
    seen: set[tuple[ResearchHorizon, float]] = set()
    for cell in matrix.cells:
        key = (cell.horizon, cell.barrier)
        if key in seen:
            raise ValueError("barrier matrix contains duplicate cell")
        seen.add(key)
        if cell.horizon not in matrix.horizons or cell.barrier not in matrix.barriers:
            raise ValueError("barrier cell lies outside declared matrix axes")
        expected_event = f"touch_price:{_barrier_key(cell.barrier)}"
        if cell.event_key != expected_event:
            raise ValueError("barrier cell event_key does not match barrier")


@dataclass(frozen=True, slots=True)
class ScientificCalibrationReleaseReport:
    report_id: str
    report_sha256: str
    dataset_version_id: str
    required_horizons: tuple[ResearchHorizon, ...]
    required_barriers: tuple[float, ...]
    directional_decision_ids: tuple[str, ...]
    distribution_decision_ids: tuple[str, ...]
    barrier_matrix_id: str
    barrier_cell_count: int
    directional_coverage_complete: bool
    distribution_coverage_complete: bool
    barrier_coverage_complete: bool
    state: ScientificCalibrationState
    reasons: tuple[str, ...]
    probability_calibrated: bool = False
    distribution_calibrated: bool = False
    production_ready: bool = False
    decision_authority: bool = False
    execution_weight: float = 0.0

    @property
    def scientific_review_eligible(self) -> bool:
        return self.state is ScientificCalibrationState.ELIGIBLE_FOR_SCIENTIFIC_REVIEW

    def to_payload(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "report_sha256": self.report_sha256,
            "dataset_version_id": self.dataset_version_id,
            "required_horizons": [item.value for item in self.required_horizons],
            "required_barriers": list(self.required_barriers),
            "directional_decision_ids": list(self.directional_decision_ids),
            "distribution_decision_ids": list(self.distribution_decision_ids),
            "barrier_matrix_id": self.barrier_matrix_id,
            "barrier_cell_count": self.barrier_cell_count,
            "directional_coverage_complete": self.directional_coverage_complete,
            "distribution_coverage_complete": self.distribution_coverage_complete,
            "barrier_coverage_complete": self.barrier_coverage_complete,
            "state": self.state.value,
            "reasons": list(self.reasons),
            "probability_calibrated": self.probability_calibrated,
            "distribution_calibrated": self.distribution_calibrated,
            "production_ready": self.production_ready,
            "decision_authority": self.decision_authority,
            "execution_weight": self.execution_weight,
        }


def build_scientific_calibration_release_report(
    *,
    dataset_version_id: str,
    directional_decisions: Sequence[CalibrationPromotionDecision],
    distribution_decisions: Sequence[DistributionPromotionDecision],
    barrier_matrix: BarrierCalibrationMatrix,
) -> ScientificCalibrationReleaseReport:
    dataset_id = _content_id(
        dataset_version_id,
        "dataset-version:sha256:",
        "dataset_version_id",
    )
    _validate_barrier_matrix(barrier_matrix)

    directional_by_horizon: dict[ResearchHorizon, CalibrationPromotionDecision] = {}
    for decision in directional_decisions:
        _validate_directional_decision(decision)
        if decision.horizon in directional_by_horizon:
            raise ValueError("duplicate directional decision for horizon")
        directional_by_horizon[decision.horizon] = decision
    if not set(directional_by_horizon) <= set(CANONICAL_FORECAST_HORIZONS):
        raise ValueError("directional decisions contain unsupported horizon")

    distribution_by_horizon: dict[ResearchHorizon, DistributionPromotionDecision] = {}
    for decision in distribution_decisions:
        _validate_distribution_decision(decision)
        if decision.horizon in distribution_by_horizon:
            raise ValueError("duplicate distribution decision for horizon")
        distribution_by_horizon[decision.horizon] = decision
    if not set(distribution_by_horizon) <= set(CANONICAL_FORECAST_HORIZONS):
        raise ValueError("distribution decisions contain unsupported horizon")

    reasons: list[str] = []
    for horizon in CANONICAL_FORECAST_HORIZONS:
        directional = directional_by_horizon.get(horizon)
        if directional is None:
            reasons.append(f"MISSING_DIRECTIONAL:{horizon.value}")
        elif directional.state is not PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW:
            reasons.append(f"BLOCKED_DIRECTIONAL:{horizon.value}")

        distribution = distribution_by_horizon.get(horizon)
        if distribution is None:
            reasons.append(f"MISSING_DISTRIBUTION:{horizon.value}")
        elif (
            distribution.state
            is not DistributionPromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
        ):
            reasons.append(f"BLOCKED_DISTRIBUTION:{horizon.value}")

    expected_barrier_cells = {
        (horizon, barrier)
        for horizon in CANONICAL_FORECAST_HORIZONS
        for barrier in CANONICAL_XRP_BARRIERS
    }
    actual_barrier_cells = {(cell.horizon, cell.barrier) for cell in barrier_matrix.cells}
    for horizon, barrier in sorted(
        expected_barrier_cells - actual_barrier_cells,
        key=lambda item: (
            CANONICAL_FORECAST_HORIZONS.index(item[0]),
            item[1],
        ),
    ):
        reasons.append(f"MISSING_BARRIER:{horizon.value}:{_barrier_key(barrier)}")
    for cell in barrier_matrix.cells:
        if cell.state is not PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW:
            reasons.append(f"BLOCKED_BARRIER:{cell.horizon.value}:{_barrier_key(cell.barrier)}")
    if barrier_matrix.state is not PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW:
        reasons.append("BARRIER_MATRIX_BLOCKED")

    directional_complete = set(directional_by_horizon) == set(CANONICAL_FORECAST_HORIZONS)
    distribution_complete = set(distribution_by_horizon) == set(CANONICAL_FORECAST_HORIZONS)
    barrier_complete = (
        set(barrier_matrix.horizons) == set(CANONICAL_FORECAST_HORIZONS)
        and set(barrier_matrix.barriers) == set(CANONICAL_XRP_BARRIERS)
        and actual_barrier_cells == expected_barrier_cells
        and len(barrier_matrix.cells) == len(expected_barrier_cells)
    )
    if not barrier_complete:
        reasons.append("BARRIER_COVERAGE_INCOMPLETE")

    unique_reasons = tuple(sorted(set(reasons)))
    state = (
        ScientificCalibrationState.ELIGIBLE_FOR_SCIENTIFIC_REVIEW
        if not unique_reasons
        else ScientificCalibrationState.BLOCKED
    )
    directional_ids = tuple(
        directional_by_horizon[horizon].decision_id
        for horizon in CANONICAL_FORECAST_HORIZONS
        if horizon in directional_by_horizon
    )
    distribution_ids = tuple(
        distribution_by_horizon[horizon].decision_id
        for horizon in CANONICAL_FORECAST_HORIZONS
        if horizon in distribution_by_horizon
    )
    material: dict[str, object] = {
        "dataset_version_id": dataset_id,
        "required_horizons": [item.value for item in CANONICAL_FORECAST_HORIZONS],
        "required_barriers": list(CANONICAL_XRP_BARRIERS),
        "directional_decision_ids": list(directional_ids),
        "distribution_decision_ids": list(distribution_ids),
        "barrier_matrix_id": barrier_matrix.matrix_id,
        "barrier_cell_count": len(barrier_matrix.cells),
        "directional_coverage_complete": directional_complete,
        "distribution_coverage_complete": distribution_complete,
        "barrier_coverage_complete": barrier_complete,
        "state": state.value,
        "reasons": list(unique_reasons),
        "probability_calibrated": False,
        "distribution_calibrated": False,
        "production_ready": False,
        "decision_authority": False,
        "execution_weight": 0.0,
    }
    digest = sha256(_canonical(material).encode()).hexdigest()
    return ScientificCalibrationReleaseReport(
        report_id=f"scientific-calibration-release:sha256:{digest}",
        report_sha256=digest,
        dataset_version_id=dataset_id,
        required_horizons=CANONICAL_FORECAST_HORIZONS,
        required_barriers=CANONICAL_XRP_BARRIERS,
        directional_decision_ids=directional_ids,
        distribution_decision_ids=distribution_ids,
        barrier_matrix_id=barrier_matrix.matrix_id,
        barrier_cell_count=len(barrier_matrix.cells),
        directional_coverage_complete=directional_complete,
        distribution_coverage_complete=distribution_complete,
        barrier_coverage_complete=barrier_complete,
        state=state,
        reasons=unique_reasons,
    )
