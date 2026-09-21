from dataclasses import replace

import pytest

from xrp_regime_engine.calibration_promotion_binary_v1 import (
    CANONICAL_FORECAST_HORIZONS,
    CANONICAL_XRP_BARRIERS,
    BarrierCalibrationCell,
    BarrierCalibrationMatrix,
    CalibrationPromotionDecision,
    PromotionState,
)
from xrp_regime_engine.distribution_promotion_v1 import (
    DistributionPromotionDecision,
    DistributionPromotionState,
)
from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.scientific_calibration_release_v1 import (
    ScientificCalibrationState,
    build_scientific_calibration_release_report,
)

DATASET = "dataset-version:sha256:" + "a" * 64


def directional(
    horizon: ResearchHorizon,
    *,
    eligible: bool = True,
) -> CalibrationPromotionDecision:
    digest = CANONICAL_FORECAST_HORIZONS.index(horizon) + 1
    return CalibrationPromotionDecision(
        decision_id="calibration-promotion:sha256:" + f"{digest:064x}",
        horizon=horizon,
        event_key="return_gt_0",
        evidence_id=f"evidence:{horizon.value}",
        state=(
            PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
            if eligible
            else PromotionState.BLOCKED
        ),
        reasons=() if eligible else ("BLOCKED",),
    )


def distribution(
    horizon: ResearchHorizon,
    *,
    eligible: bool = True,
) -> DistributionPromotionDecision:
    digest = CANONICAL_FORECAST_HORIZONS.index(horizon) + 100
    return DistributionPromotionDecision(
        decision_id="distribution-promotion:sha256:" + f"{digest:064x}",
        horizon=horizon,
        evidence_id=f"distribution:{horizon.value}",
        state=(
            DistributionPromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
            if eligible
            else DistributionPromotionState.BLOCKED
        ),
        reasons=() if eligible else ("BLOCKED",),
    )


def full_barrier_matrix(
    *,
    eligible: bool = True,
) -> BarrierCalibrationMatrix:
    cells = []
    counter = 1000
    for horizon in CANONICAL_FORECAST_HORIZONS:
        for barrier in CANONICAL_XRP_BARRIERS:
            counter += 1
            cells.append(
                BarrierCalibrationCell(
                    horizon=horizon,
                    barrier=barrier,
                    event_key=f"touch_price:{format(barrier, '.12g')}",
                    state=(
                        PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
                        if eligible
                        else PromotionState.BLOCKED
                    ),
                    reasons=() if eligible else ("BLOCKED",),
                    decision_id="calibration-promotion:sha256:" + f"{counter:064x}",
                )
            )
    return BarrierCalibrationMatrix(
        matrix_id="barrier-calibration-matrix:sha256:" + "b" * 64,
        horizons=CANONICAL_FORECAST_HORIZONS,
        barriers=CANONICAL_XRP_BARRIERS,
        cells=tuple(cells),
        state=(
            PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
            if eligible
            else PromotionState.BLOCKED
        ),
    )


def all_directional():
    return tuple(directional(horizon) for horizon in CANONICAL_FORECAST_HORIZONS)


def all_distribution():
    return tuple(distribution(horizon) for horizon in CANONICAL_FORECAST_HORIZONS)


def test_full_scientific_gate_is_deterministic_but_not_production_authority() -> None:
    forward = build_scientific_calibration_release_report(
        dataset_version_id=DATASET,
        directional_decisions=all_directional(),
        distribution_decisions=all_distribution(),
        barrier_matrix=full_barrier_matrix(),
    )
    reverse = build_scientific_calibration_release_report(
        dataset_version_id=DATASET,
        directional_decisions=tuple(reversed(all_directional())),
        distribution_decisions=tuple(reversed(all_distribution())),
        barrier_matrix=full_barrier_matrix(),
    )
    assert forward == reverse
    assert forward.state is ScientificCalibrationState.ELIGIBLE_FOR_SCIENTIFIC_REVIEW
    assert forward.scientific_review_eligible
    assert forward.directional_coverage_complete
    assert forward.distribution_coverage_complete
    assert forward.barrier_coverage_complete
    assert forward.barrier_cell_count == 63
    assert not forward.probability_calibrated
    assert not forward.distribution_calibrated
    assert not forward.production_ready
    assert not forward.decision_authority
    assert forward.execution_weight == 0
    assert forward.to_payload()["state"] == "ELIGIBLE_FOR_SCIENTIFIC_REVIEW"


def test_missing_surfaces_fail_closed_with_exact_reasons() -> None:
    matrix = full_barrier_matrix()
    incomplete_matrix = replace(
        matrix,
        cells=matrix.cells[:-1],
        state=PromotionState.BLOCKED,
    )
    report = build_scientific_calibration_release_report(
        dataset_version_id=DATASET,
        directional_decisions=all_directional()[:-1],
        distribution_decisions=all_distribution()[:-1],
        barrier_matrix=incomplete_matrix,
    )
    assert report.state is ScientificCalibrationState.BLOCKED
    assert not report.scientific_review_eligible
    assert not report.directional_coverage_complete
    assert not report.distribution_coverage_complete
    assert not report.barrier_coverage_complete
    reasons = set(report.reasons)
    assert "MISSING_DIRECTIONAL:1y" in reasons
    assert "MISSING_DISTRIBUTION:1y" in reasons
    assert "MISSING_BARRIER:1y:50" in reasons
    assert "BARRIER_COVERAGE_INCOMPLETE" in reasons
    assert "BARRIER_MATRIX_BLOCKED" in reasons


def test_blocked_subgates_propagate() -> None:
    directional_items = list(all_directional())
    directional_items[0] = directional(ResearchHorizon.H1, eligible=False)
    distribution_items = list(all_distribution())
    distribution_items[1] = distribution(ResearchHorizon.H4, eligible=False)
    matrix = full_barrier_matrix()
    blocked_cell = replace(
        matrix.cells[0],
        state=PromotionState.BLOCKED,
        reasons=("NO_DATA",),
    )
    matrix = replace(
        matrix,
        cells=(blocked_cell, *matrix.cells[1:]),
        state=PromotionState.BLOCKED,
    )
    report = build_scientific_calibration_release_report(
        dataset_version_id=DATASET,
        directional_decisions=directional_items,
        distribution_decisions=distribution_items,
        barrier_matrix=matrix,
    )
    reasons = set(report.reasons)
    assert "BLOCKED_DIRECTIONAL:1h" in reasons
    assert "BLOCKED_DISTRIBUTION:4h" in reasons
    assert "BLOCKED_BARRIER:1h:2" in reasons
    assert "BARRIER_MATRIX_BLOCKED" in reasons


def test_content_identity_and_duplicate_guards() -> None:
    with pytest.raises(ValueError, match="dataset_version_id"):
        build_scientific_calibration_release_report(
            dataset_version_id="bad",
            directional_decisions=all_directional(),
            distribution_decisions=all_distribution(),
            barrier_matrix=full_barrier_matrix(),
        )
    duplicate_directional = (*all_directional(), directional(ResearchHorizon.H1))
    with pytest.raises(ValueError, match="duplicate directional"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=duplicate_directional,
            distribution_decisions=all_distribution(),
            barrier_matrix=full_barrier_matrix(),
        )
    duplicate_distribution = (*all_distribution(), distribution(ResearchHorizon.H1))
    with pytest.raises(ValueError, match="duplicate distribution"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=all_directional(),
            distribution_decisions=duplicate_distribution,
            barrier_matrix=full_barrier_matrix(),
        )


def test_non_authoritative_and_directional_contract_guards() -> None:
    bad_directional = replace(
        directional(ResearchHorizon.H1),
        event_key="touch_price:5",
    )
    with pytest.raises(ValueError, match="return_gt_0"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(bad_directional,),
            distribution_decisions=(),
            barrier_matrix=full_barrier_matrix(),
        )
    authoritative = replace(
        directional(ResearchHorizon.H1),
        probability_calibrated=True,
    )
    with pytest.raises(ValueError, match="non-authoritative"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(authoritative,),
            distribution_decisions=(),
            barrier_matrix=full_barrier_matrix(),
        )
    authoritative_distribution = replace(
        distribution(ResearchHorizon.H1),
        distribution_calibrated=True,
    )
    with pytest.raises(ValueError, match="non-authoritative"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(authoritative_distribution,),
            barrier_matrix=full_barrier_matrix(),
        )
    with pytest.raises(ValueError, match="non-authoritative"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(full_barrier_matrix(), production_ready=True),
        )


def test_barrier_matrix_structural_guards() -> None:
    matrix = full_barrier_matrix()
    with pytest.raises(ValueError, match="horizons must be unique"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(
                matrix,
                horizons=(ResearchHorizon.H1, ResearchHorizon.H1),
            ),
        )
    with pytest.raises(ValueError, match="barriers must be unique"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(matrix, barriers=(2.0, 2.0)),
        )
    duplicate_cell = (*matrix.cells, matrix.cells[0])
    with pytest.raises(ValueError, match="duplicate cell"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(matrix, cells=duplicate_cell),
        )
    wrong_event = replace(matrix.cells[0], event_key="touch_price:999")
    with pytest.raises(ValueError, match="event_key"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(matrix, cells=(wrong_event, *matrix.cells[1:])),
        )
    outside_axes = replace(matrix.cells[0], barrier=3.0)
    with pytest.raises(ValueError, match="duplicate cell"):
        build_scientific_calibration_release_report(
            dataset_version_id=DATASET,
            directional_decisions=(),
            distribution_decisions=(),
            barrier_matrix=replace(matrix, cells=(outside_axes, *matrix.cells[1:])),
        )
