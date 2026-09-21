from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.calibration_evidence_v1 import CalibrationEvidenceV1, ReliabilityBin
from xrp_regime_engine.calibration_promotion_binary_v1 import (
    CANONICAL_FORECAST_HORIZONS,
    CANONICAL_XRP_BARRIERS,
    BinaryCalibrationPolicy,
    CalibrationSlice,
    PromotionState,
    StabilityAxis,
    StabilityPolicy,
    assess_binary_evidence,
    build_barrier_matrix,
    build_stability_matrix,
    evaluate_promotion,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def evidence(
    ident="e",
    *,
    event="return_gt_0",
    horizon=ResearchHorizon.H1,
    start=T0,
    samples=300,
    pos=150,
    brier=0.15,
    ece=0.02,
    gap=0.04,
    intercept=0.05,
    slope=1.0,
    ref=0.25,
):
    return CalibrationEvidenceV1(
        ident,
        "a" * 64,
        horizon,
        event,
        samples,
        pos,
        samples - pos,
        start,
        start + timedelta(days=1),
        brier,
        0.5,
        ece,
        gap,
        0.7,
        intercept,
        slope,
        0.5,
        ref,
        (ReliabilityBin(0, 1, samples, 0.5, 0.5, 0),),
    )


def policy(**kwargs):
    data = dict(
        min_samples=100,
        min_class_count=20,
        max_ece=0.05,
        max_calibration_gap=0.1,
        max_abs_intercept=0.2,
        min_slope=0.8,
        max_slope=1.2,
        min_brier_improvement=0.01,
    )
    data.update(kwargs)
    return BinaryCalibrationPolicy(**data)


def spolicy(**kwargs):
    data = dict(
        min_slices=2,
        max_brier_spread=0.05,
        max_ece_spread=0.04,
        max_slope_spread=0.4,
    )
    data.update(kwargs)
    return StabilityPolicy(**data)


def matrix(axis, *, event="return_gt_0", horizon=ResearchHorizon.H1):
    return build_stability_matrix(
        (
            CalibrationSlice(axis, "a", evidence("a", event=event, horizon=horizon, start=T0)),
            CalibrationSlice(
                axis,
                "b",
                evidence("b", event=event, horizon=horizon, start=T0 + timedelta(days=2)),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
    )


def test_policy_and_assessment() -> None:
    assert assess_binary_evidence(evidence(), policy()).eligible
    bad = evidence(
        samples=30,
        pos=5,
        brier=0.3,
        ece=0.2,
        gap=0.3,
        intercept=0.5,
        slope=2,
        ref=0.25,
    )
    reasons = set(assess_binary_evidence(bad, policy()).reasons)
    assert {
        "INSUFFICIENT_SAMPLE_COUNT",
        "INSUFFICIENT_POSITIVE_CLASS",
        "ECE_ABOVE_LIMIT",
        "MAX_CALIBRATION_GAP_ABOVE_LIMIT",
        "CALIBRATION_INTERCEPT_OUTSIDE_LIMIT",
        "CALIBRATION_SLOPE_OUTSIDE_LIMIT",
        "NO_BRIER_IMPROVEMENT_OVER_BASE_RATE",
    } <= reasons
    missing = assess_binary_evidence(
        evidence(intercept=None, slope=None, ref=None),
        policy(),
    )
    assert {
        "CALIBRATION_INTERCEPT_MISSING",
        "CALIBRATION_SLOPE_MISSING",
        "REFERENCE_BRIER_MISSING",
    } <= set(missing.reasons)
    for ctor in (
        lambda: policy(min_samples=0),
        lambda: policy(max_ece=-1),
        lambda: policy(min_slope=2, max_slope=1),
        lambda: spolicy(min_slices=0),
        lambda: spolicy(max_ece_spread=-1),
    ):
        with pytest.raises(ValueError):
            ctor()


def test_assessment_structural_guards() -> None:
    with pytest.raises(ValueError, match="class counts"):
        assess_binary_evidence(replace(evidence(), negative_count=1), policy())
    with pytest.raises(ValueError, match="reversed"):
        assess_binary_evidence(
            replace(evidence(), evaluation_end=T0 - timedelta(days=1)),
            policy(),
        )
    with pytest.raises(ValueError, match="non-authoritative"):
        assess_binary_evidence(replace(evidence(), decision_authority=True), policy())
    with pytest.raises(ValueError, match="finite"):
        assess_binary_evidence(replace(evidence(), brier_score=float("nan")), policy())
    with pytest.raises(ValueError, match="bounded"):
        assess_binary_evidence(replace(evidence(), ece=2), policy())
    with pytest.raises(ValueError, match="gap/log"):
        assess_binary_evidence(replace(evidence(), log_loss=-1), policy())
    with pytest.raises(ValueError, match="reliability"):
        assess_binary_evidence(replace(evidence(), reliability_bins=()), policy())


def test_stability_success_required_instability_and_guards() -> None:
    temporal = matrix(StabilityAxis.TEMPORAL)
    assert temporal.eligible
    missing = build_stability_matrix(
        (
            CalibrationSlice(StabilityAxis.REGIME, "bull", evidence("a")),
            CalibrationSlice(
                StabilityAxis.REGIME,
                "bear",
                evidence("b", start=T0 + timedelta(days=2)),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
        required_slice_ids=("bull", "bear", "range"),
    )
    assert "REQUIRED_STABILITY_SLICES_MISSING" in missing.reasons
    unstable = build_stability_matrix(
        (
            CalibrationSlice(
                StabilityAxis.REGIME,
                "a",
                evidence("a", brier=0.1, ece=0.01, slope=0.8),
            ),
            CalibrationSlice(
                StabilityAxis.REGIME,
                "b",
                evidence(
                    "b",
                    start=T0 + timedelta(days=2),
                    brier=0.2,
                    ece=0.06,
                    slope=1.3,
                ),
            ),
        ),
        evidence_policy=policy(max_ece=0.1, min_slope=0.5, max_slope=1.5),
        stability_policy=spolicy(),
    )
    assert {"BRIER_INSTABILITY", "ECE_INSTABILITY", "SLOPE_INSTABILITY"} <= set(
        unstable.reasons
    )
    one = build_stability_matrix(
        (CalibrationSlice(StabilityAxis.REGIME, "a", evidence()),),
        evidence_policy=policy(),
        stability_policy=spolicy(),
    )
    assert "INSUFFICIENT_STABILITY_SLICES" in one.reasons
    noslope = build_stability_matrix(
        (
            CalibrationSlice(
                StabilityAxis.REGIME,
                "a",
                evidence("a", slope=None),
            ),
            CalibrationSlice(
                StabilityAxis.REGIME,
                "b",
                evidence("b", start=T0 + timedelta(days=2), slope=None),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
    )
    assert "SLOPE_STABILITY_UNAVAILABLE" in noslope.reasons
    with pytest.raises(ValueError, match="empty"):
        build_stability_matrix(
            (),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="mix axes"):
        build_stability_matrix(
            (
                CalibrationSlice(StabilityAxis.TEMPORAL, "a", evidence()),
                CalibrationSlice(
                    StabilityAxis.REGIME,
                    "b",
                    evidence("b", start=T0 + timedelta(days=2)),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="overlap"):
        build_stability_matrix(
            (
                CalibrationSlice(StabilityAxis.TEMPORAL, "a", evidence()),
                CalibrationSlice(
                    StabilityAxis.TEMPORAL,
                    "b",
                    evidence("b", start=T0 + timedelta(hours=12)),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )


def test_promotion_gate() -> None:
    ev = evidence()
    temporal = matrix(StabilityAxis.TEMPORAL)
    regime = matrix(StabilityAxis.REGIME)
    decision = evaluate_promotion(
        ev,
        temporal=temporal,
        regime=regime,
        policy=policy(),
    )
    assert decision.state is PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
    assert (
        not decision.probability_calibrated
        and not decision.production_ready
        and decision.execution_weight == 0
    )
    blocked = evaluate_promotion(
        ev,
        temporal=replace(temporal, eligible=False),
        regime=replace(regime, eligible=False),
        policy=policy(),
    )
    assert blocked.state is PromotionState.BLOCKED
    assert {"TEMPORAL_STABILITY_BLOCKED", "REGIME_STABILITY_BLOCKED"} <= set(
        blocked.reasons
    )
    with pytest.raises(ValueError, match="axis mismatch"):
        evaluate_promotion(
            ev,
            temporal=regime,
            regime=regime,
            policy=policy(),
        )
    with pytest.raises(ValueError, match="does not match"):
        evaluate_promotion(
            evidence(event="x"),
            temporal=temporal,
            regime=regime,
            policy=policy(),
        )


def barrier_data(barrier=5.0):
    event = f"touch_price:{barrier:g}"
    ev = evidence("bar", event=event)
    return (
        ev,
        matrix(StabilityAxis.TEMPORAL, event=event),
        matrix(StabilityAxis.REGIME, event=event),
    )


def test_barrier_matrix_and_canonical_shape() -> None:
    ev, temporal, regime = barrier_data()
    result = build_barrier_matrix(
        (ev,),
        horizons=(ResearchHorizon.H1,),
        barriers=(5,),
        temporal_matrices=(temporal,),
        regime_matrices=(regime,),
        policy=policy(),
    )
    assert result.state is PromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
    assert result.cells[0].event_key == "touch_price:5"
    missing = build_barrier_matrix(
        (),
        horizons=(ResearchHorizon.H1,),
        barriers=(5,),
        temporal_matrices=(),
        regime_matrices=(),
        policy=policy(),
    )
    assert missing.state is PromotionState.BLOCKED
    assert {
        "MISSING_CALIBRATION_EVIDENCE",
        "MISSING_TEMPORAL_STABILITY",
        "MISSING_REGIME_STABILITY",
    } <= set(missing.cells[0].reasons)
    canonical = build_barrier_matrix(
        (),
        temporal_matrices=(),
        regime_matrices=(),
        policy=policy(),
    )
    assert canonical.horizons == CANONICAL_FORECAST_HORIZONS
    assert canonical.barriers == CANONICAL_XRP_BARRIERS
    assert len(canonical.cells) == 63
    with pytest.raises(ValueError, match="requires"):
        build_barrier_matrix(
            (),
            horizons=(),
            barriers=(5,),
            temporal_matrices=(),
            regime_matrices=(),
            policy=policy(),
        )
    with pytest.raises(ValueError, match="duplicate calibration"):
        build_barrier_matrix(
            (ev, ev),
            horizons=(ResearchHorizon.H1,),
            barriers=(5,),
            temporal_matrices=(temporal,),
            regime_matrices=(regime,),
            policy=policy(),
        )
    with pytest.raises(ValueError, match="axis mismatch"):
        build_barrier_matrix(
            (ev,),
            horizons=(ResearchHorizon.H1,),
            barriers=(5,),
            temporal_matrices=(regime,),
            regime_matrices=(regime,),
            policy=policy(),
        )
    with pytest.raises(ValueError, match="duplicate stability"):
        build_barrier_matrix(
            (ev,),
            horizons=(ResearchHorizon.H1,),
            barriers=(5,),
            temporal_matrices=(temporal, temporal),
            regime_matrices=(regime,),
            policy=policy(),
        )


def test_remaining_fail_closed_branches() -> None:
    with pytest.raises(ValueError, match="slice_id"):
        CalibrationSlice(StabilityAxis.REGIME, " ", evidence())
    low_negative = evidence(samples=30, pos=25, ref=0.5)
    assert "INSUFFICIENT_NEGATIVE_CLASS" in assess_binary_evidence(
        low_negative,
        policy(min_samples=20, min_class_count=10, min_brier_improvement=0),
    ).reasons
    item = CalibrationSlice(StabilityAxis.REGIME, "a", evidence("a"))
    with pytest.raises(ValueError, match="horizon/event_key"):
        build_stability_matrix(
            (
                item,
                CalibrationSlice(
                    StabilityAxis.REGIME,
                    "b",
                    evidence("b", event="x"),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="unique"):
        build_stability_matrix(
            (
                item,
                CalibrationSlice(
                    StabilityAxis.REGIME,
                    "a",
                    evidence("b"),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
