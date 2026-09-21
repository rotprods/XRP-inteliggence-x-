from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.calibration_evidence_v1 import (
    ResolvedPredictionRecord,
    build_calibration_evidence,
    join_resolved_predictions,
)
from xrp_regime_engine.oos_predictions_v1 import OOSPrediction, ResolvedOOSOutcome
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def rec(
    index: int,
    score: float,
    actual: bool,
    event: str = "return_gt_0",
    horizon: ResearchHorizon = ResearchHorizon.H1,
) -> ResolvedPredictionRecord:
    return ResolvedPredictionRecord(
        f"p{index}",
        T0 + timedelta(hours=index),
        horizon,
        event,
        score,
        actual,
        T0 + timedelta(hours=index + 2),
    )


def test_calibration_metrics_perfect_separation() -> None:
    rows = (
        rec(0, 0.1, False),
        rec(1, 0.2, False),
        rec(2, 0.8, True),
        rec(3, 0.9, True),
    )
    evidence = build_calibration_evidence(
        rows,
        n_bins=5,
        reference_base_rate=0.5,
    )
    assert evidence.sample_count == 4
    assert evidence.positive_count == 2
    assert evidence.negative_count == 2
    assert evidence.brier_score < 0.05
    assert evidence.roc_auc == 1.0
    assert evidence.reference_base_rate_brier == pytest.approx(0.25)
    assert evidence.probability_calibrated is False
    assert evidence.decision_authority is False
    assert evidence.execution_weight == 0


def test_calibration_bins_ece_and_empty_bins() -> None:
    evidence = build_calibration_evidence(
        (rec(0, 0.0, False), rec(1, 1.0, True)),
        n_bins=4,
    )
    assert len(evidence.reliability_bins) == 4
    assert sum(item.count for item in evidence.reliability_bins) == 2
    assert evidence.ece == 0


def test_calibration_single_class_has_no_auc_or_slope() -> None:
    evidence = build_calibration_evidence(
        (rec(0, 0.1, False), rec(1, 0.2, False))
    )
    assert evidence.roc_auc is None
    assert evidence.calibration_intercept is None
    assert evidence.calibration_slope is None


def test_calibration_validation() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        build_calibration_evidence(())
    with pytest.raises(ValueError, match="n_bins"):
        build_calibration_evidence((rec(0, 0.1, False),), n_bins=1)
    with pytest.raises(ValueError, match="epsilon"):
        build_calibration_evidence((rec(0, 0.1, False),), epsilon=0.5)
    with pytest.raises(ValueError, match="reference_base_rate"):
        build_calibration_evidence(
            (rec(0, 0.1, False),),
            reference_base_rate=2,
        )
    with pytest.raises(ValueError, match="one horizon"):
        build_calibration_evidence(
            (
                rec(0, 0.1, False),
                rec(1, 0.2, True, horizon=ResearchHorizon.H4),
            )
        )
    with pytest.raises(ValueError, match="one horizon"):
        build_calibration_evidence(
            (rec(0, 0.1, False), rec(1, 0.2, True, event="other"))
        )
    with pytest.raises(ValueError, match="raw_score"):
        build_calibration_evidence((rec(0, 2, False),))


def make_pred(
    index: int,
    event: str = "return_gt_0",
    horizon: ResearchHorizon = ResearchHorizon.H1,
) -> OOSPrediction:
    return OOSPrediction(
        "oos-prediction:sha256:" + f"{index + 1:064x}",
        "0" * 64,
        "fold",
        "feature:sha256:" + f"{index + 1:064x}",
        T0 + timedelta(hours=index),
        horizon,
        event,
        "m",
        "v",
        T0 - timedelta(days=1),
        "1" * 64,
        1,
        "f",
        "p",
        ("snapshot:sha256:" + "a" * 64,),
        0.2,
    )


def make_out(
    prediction: OOSPrediction,
    actual: bool = False,
) -> ResolvedOOSOutcome:
    return ResolvedOOSOutcome(
        "oos-outcome:sha256:" + "b" * 64,
        "b" * 64,
        prediction.prediction_id,
        "label",
        prediction.feature_row_id,
        prediction.event_key,
        prediction.horizon,
        prediction.prediction_time,
        prediction.prediction_time + timedelta(hours=1),
        prediction.prediction_time + timedelta(hours=1),
        actual,
    )


def test_join_resolved_predictions_and_mismatch_guards() -> None:
    first = make_pred(0)
    second = make_pred(1)
    first_outcome = make_out(first)
    second_outcome = make_out(second, True)
    joined = join_resolved_predictions(
        (second, first),
        (second_outcome, first_outcome),
    )
    assert [item.prediction_id for item in joined] == [
        first.prediction_id,
        second.prediction_id,
    ]

    with pytest.raises(ValueError, match="cannot be empty"):
        join_resolved_predictions((), ())
    with pytest.raises(ValueError, match="duplicate prediction"):
        join_resolved_predictions((first, first), (first_outcome,))
    with pytest.raises(ValueError, match="duplicate outcome"):
        join_resolved_predictions((first,), (first_outcome, first_outcome))
    with pytest.raises(ValueError, match="identity mismatch"):
        join_resolved_predictions((first,), (second_outcome,))
    with pytest.raises(ValueError, match="feature_row_id"):
        join_resolved_predictions(
            (first,),
            (replace(first_outcome, feature_row_id="x"),),
        )
    with pytest.raises(ValueError, match="event_key"):
        join_resolved_predictions(
            (first,),
            (replace(first_outcome, event_key="x"),),
        )
    with pytest.raises(ValueError, match="horizon"):
        join_resolved_predictions(
            (first,),
            (replace(first_outcome, horizon=ResearchHorizon.H4),),
        )
    with pytest.raises(ValueError, match="prediction_time"):
        join_resolved_predictions(
            (first,),
            (
                replace(
                    first_outcome,
                    prediction_time=T0 + timedelta(days=1),
                ),
            ),
        )
    with pytest.raises(ValueError, match="resolved before"):
        join_resolved_predictions(
            (first,),
            (replace(first_outcome, resolved_at=first.prediction_time),),
        )


def test_join_rejects_mixed_prediction_groups() -> None:
    first = make_pred(0)
    second = make_pred(1, horizon=ResearchHorizon.H4)
    first_outcome = make_out(first)
    second_outcome = make_out(second, True)
    with pytest.raises(ValueError, match="one horizon"):
        join_resolved_predictions(
            (first, second),
            (first_outcome, second_outcome),
        )

    third = make_pred(1, event="other")
    third_outcome = make_out(third, True)
    with pytest.raises(ValueError, match="one horizon"):
        join_resolved_predictions(
            (first, third),
            (first_outcome, third_outcome),
        )


def test_auc_ties_and_logistic_diagnostic_convergence() -> None:
    rows = (
        rec(0, 0.2, False),
        rec(1, 0.4, True),
        rec(2, 0.6, False),
        rec(3, 0.8, True),
        rec(4, 0.4, False),
    )
    evidence = build_calibration_evidence(rows, n_bins=5)
    assert evidence.roc_auc is not None
    assert 0 <= evidence.roc_auc <= 1
    assert evidence.calibration_intercept is not None
    assert evidence.calibration_slope is not None
    assert evidence.to_payload()["evidence_id"] == evidence.evidence_id


def test_private_logistic_max_iteration_zero_and_naive_record() -> None:
    from xrp_regime_engine.calibration_evidence_v1 import _logistic_recalibration

    rows = (rec(0, 0.2, False), rec(1, 0.8, True))
    assert _logistic_recalibration(
        rows,
        epsilon=1e-12,
        max_iterations=0,
    ) == (0.0, 1.0)

    bad = ResolvedPredictionRecord(
        "x",
        datetime(2026, 1, 1),
        ResearchHorizon.H1,
        "return_gt_0",
        0.5,
        True,
        T0,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_calibration_evidence((bad,))
