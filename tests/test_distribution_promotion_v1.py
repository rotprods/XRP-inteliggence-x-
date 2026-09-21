from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.distribution_promotion_v1 import (
    DistributionCalibrationPolicy,
    DistributionPromotionState,
    DistributionSlice,
    DistributionStabilityAxis,
    DistributionStabilityPolicy,
    assess_distribution_evidence,
    build_distribution_stability_matrix,
    evaluate_distribution_promotion,
)
from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.return_distribution_v1 import (
    QuantileEvidence,
    ReturnDistributionEvidenceV1,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)


def evidence(
    ident="d",
    *,
    start=T0,
    horizon=ResearchHorizon.H1,
    samples=300,
    errors=(0.01, -0.01, 0, 0.01, -0.01),
    i50=0.52,
    i80=0.79,
    mae=0.03,
):
    quantiles = tuple(
        QuantileEvidence(level, 0.02, level + error, error)
        for level, error in zip(LEVELS, errors, strict=True)
    )
    return ReturnDistributionEvidenceV1(
        ident,
        "a" * 64,
        horizon,
        samples,
        start,
        start + timedelta(days=1),
        quantiles,
        i50,
        i80,
        mae,
    )


def policy(**kwargs):
    data = dict(
        min_samples=100,
        max_abs_quantile_coverage_error=0.05,
        max_interval_50_error=0.1,
        max_interval_80_error=0.1,
        max_median_absolute_error=0.1,
    )
    data.update(kwargs)
    return DistributionCalibrationPolicy(**data)


def spolicy(**kwargs):
    data = dict(
        min_slices=2,
        max_quantile_error_spread=0.05,
        max_interval_50_spread=0.1,
        max_interval_80_spread=0.1,
    )
    data.update(kwargs)
    return DistributionStabilityPolicy(**data)


def matrix(axis):
    return build_distribution_stability_matrix(
        (
            DistributionSlice(axis, "a", evidence("a")),
            DistributionSlice(
                axis,
                "b",
                evidence("b", start=T0 + timedelta(days=2)),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
    )


def test_assessment_and_policy() -> None:
    assert assess_distribution_evidence(evidence(), policy()).eligible
    bad = evidence(
        samples=10,
        errors=(0.1, 0.1, 0.1, 0.1, 0.05),
        i50=0.8,
        i80=0.3,
        mae=0.5,
    )
    reasons = set(assess_distribution_evidence(bad, policy()).reasons)
    assert {
        "INSUFFICIENT_SAMPLE_COUNT",
        "INTERVAL_50_COVERAGE_OUTSIDE_LIMIT",
        "INTERVAL_80_COVERAGE_OUTSIDE_LIMIT",
        "MEDIAN_ABSOLUTE_ERROR_ABOVE_LIMIT",
    } <= reasons
    for ctor in (
        lambda: policy(min_samples=0),
        lambda: policy(max_interval_50_error=-1),
        lambda: spolicy(min_slices=0),
        lambda: spolicy(max_interval_80_spread=-1),
    ):
        with pytest.raises(ValueError):
            ctor()


def test_assessment_structural_guards() -> None:
    with pytest.raises(ValueError, match="reversed"):
        assess_distribution_evidence(
            replace(evidence(), evaluation_end=T0 - timedelta(days=1)),
            policy(),
        )
    with pytest.raises(ValueError, match="non-authoritative"):
        assess_distribution_evidence(
            replace(evidence(), distribution_calibrated=True),
            policy(),
        )
    with pytest.raises(ValueError, match="canonical"):
        assess_distribution_evidence(
            replace(evidence(), quantile_evidence=()),
            policy(),
        )
    quantiles = list(evidence().quantile_evidence)
    quantiles[0] = replace(
        quantiles[0],
        empirical_coverage=2,
        coverage_error=1.9,
    )
    with pytest.raises(ValueError, match="structurally"):
        assess_distribution_evidence(
            replace(evidence(), quantile_evidence=tuple(quantiles)),
            policy(),
        )
    quantiles = list(evidence().quantile_evidence)
    quantiles[0] = replace(quantiles[0], coverage_error=0.02)
    with pytest.raises(ValueError, match="inconsistent"):
        assess_distribution_evidence(
            replace(evidence(), quantile_evidence=tuple(quantiles)),
            policy(),
        )
    with pytest.raises(ValueError, match="median_absolute_error"):
        assess_distribution_evidence(
            replace(evidence(), median_absolute_error=-1),
            policy(max_median_absolute_error=None),
        )


def test_stability_and_promotion() -> None:
    temporal = matrix(DistributionStabilityAxis.TEMPORAL)
    regime = matrix(DistributionStabilityAxis.REGIME)
    assert temporal.eligible
    decision = evaluate_distribution_promotion(
        evidence(),
        temporal=temporal,
        regime=regime,
        policy=policy(),
    )
    assert (
        decision.state
        is DistributionPromotionState.ELIGIBLE_FOR_CALIBRATION_REVIEW
    )
    assert (
        not decision.distribution_calibrated
        and not decision.production_ready
        and decision.execution_weight == 0
    )
    unstable = build_distribution_stability_matrix(
        (
            DistributionSlice(
                DistributionStabilityAxis.REGIME,
                "a",
                evidence(
                    "a",
                    errors=(0, 0, 0, 0, 0),
                    i50=0.5,
                    i80=0.8,
                ),
            ),
            DistributionSlice(
                DistributionStabilityAxis.REGIME,
                "b",
                evidence(
                    "b",
                    start=T0 + timedelta(days=2),
                    errors=(0.04, 0.04, 0.04, 0.04, 0.04),
                    i50=0.65,
                    i80=0.95,
                ),
            ),
        ),
        evidence_policy=policy(
            max_abs_quantile_coverage_error=0.1,
            max_interval_50_error=0.2,
            max_interval_80_error=0.2,
        ),
        stability_policy=spolicy(max_quantile_error_spread=0.01),
    )
    assert {
        "QUANTILE_COVERAGE_INSTABILITY",
        "INTERVAL_50_INSTABILITY",
        "INTERVAL_80_INSTABILITY",
    } <= set(unstable.reasons)
    blocked = evaluate_distribution_promotion(
        evidence(),
        temporal=replace(temporal, eligible=False),
        regime=replace(regime, eligible=False),
        policy=policy(),
    )
    assert blocked.state is DistributionPromotionState.BLOCKED
    assert {
        "TEMPORAL_STABILITY_BLOCKED",
        "REGIME_STABILITY_BLOCKED",
    } <= set(blocked.reasons)


def test_stability_guards_and_remaining_branches() -> None:
    with pytest.raises(ValueError, match="slice_id"):
        DistributionSlice(
            DistributionStabilityAxis.REGIME,
            " ",
            evidence(),
        )
    with pytest.raises(ValueError, match="empty"):
        build_distribution_stability_matrix(
            (),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="mix axis/horizon"):
        build_distribution_stability_matrix(
            (
                DistributionSlice(
                    DistributionStabilityAxis.TEMPORAL,
                    "a",
                    evidence(),
                ),
                DistributionSlice(
                    DistributionStabilityAxis.REGIME,
                    "b",
                    evidence("b", start=T0 + timedelta(days=2)),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="unique"):
        build_distribution_stability_matrix(
            (
                DistributionSlice(
                    DistributionStabilityAxis.REGIME,
                    "a",
                    evidence(),
                ),
                DistributionSlice(
                    DistributionStabilityAxis.REGIME,
                    "a",
                    evidence("b"),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    with pytest.raises(ValueError, match="overlap"):
        build_distribution_stability_matrix(
            (
                DistributionSlice(
                    DistributionStabilityAxis.TEMPORAL,
                    "a",
                    evidence(),
                ),
                DistributionSlice(
                    DistributionStabilityAxis.TEMPORAL,
                    "b",
                    evidence("b", start=T0 + timedelta(hours=12)),
                ),
            ),
            evidence_policy=policy(),
            stability_policy=spolicy(),
        )
    one = build_distribution_stability_matrix(
        (
            DistributionSlice(
                DistributionStabilityAxis.REGIME,
                "a",
                evidence(),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
    )
    assert "INSUFFICIENT_STABILITY_SLICES" in one.reasons
    required = build_distribution_stability_matrix(
        (
            DistributionSlice(
                DistributionStabilityAxis.REGIME,
                "a",
                evidence(),
            ),
            DistributionSlice(
                DistributionStabilityAxis.REGIME,
                "b",
                evidence("b", start=T0 + timedelta(days=2)),
            ),
        ),
        evidence_policy=policy(),
        stability_policy=spolicy(),
        required_slice_ids=("a", "b", "range"),
    )
    assert "REQUIRED_STABILITY_SLICES_MISSING" in required.reasons
    temporal = matrix(DistributionStabilityAxis.TEMPORAL)
    regime = matrix(DistributionStabilityAxis.REGIME)
    with pytest.raises(ValueError, match="axis mismatch"):
        evaluate_distribution_promotion(
            evidence(),
            temporal=regime,
            regime=regime,
            policy=policy(),
        )
    with pytest.raises(ValueError, match="horizon mismatch"):
        evaluate_distribution_promotion(
            evidence(),
            temporal=temporal,
            regime=replace(regime, horizon=ResearchHorizon.H4),
            policy=policy(),
        )


def test_extra_policy_and_metric_fail_closed_branches() -> None:
    with pytest.raises(ValueError, match="max_median_absolute_error"):
        policy(max_median_absolute_error=-1)
    with pytest.raises(ValueError, match="finite"):
        assess_distribution_evidence(
            replace(evidence(), median_absolute_error=float("nan")),
            policy(),
        )
    with pytest.raises(ValueError, match="interval coverage"):
        assess_distribution_evidence(
            replace(evidence(), interval_50_coverage=2),
            policy(),
        )
