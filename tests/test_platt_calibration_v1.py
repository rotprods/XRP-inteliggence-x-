from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.calibration_evidence_v1 import ResolvedPredictionRecord
from xrp_regime_engine.oos_predictions_v1 import OOSPrediction, ResolvedOOSOutcome
from xrp_regime_engine.platt_calibration_v1 import (
    apply_platt_candidate,
    candidate_evaluation_records,
    fit_platt_calibrator_candidate,
)
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def record(
    index: int,
    score: float,
    actual: bool,
    event: str = "return_gt_0",
    horizon: ResearchHorizon = ResearchHorizon.H1,
    resolved_offset: int = 2,
) -> ResolvedPredictionRecord:
    return ResolvedPredictionRecord(
        str(index),
        T0 + timedelta(days=index),
        horizon,
        event,
        score,
        actual,
        T0 + timedelta(days=index, hours=resolved_offset),
    )


def fit_records() -> tuple[ResolvedPredictionRecord, ...]:
    return tuple(
        record(index, score, actual)
        for index, (score, actual) in enumerate(
            (
                (0.2, False),
                (0.3, True),
                (0.4, False),
                (0.5, True),
                (0.6, False),
                (0.7, True),
            )
        )
    )


def test_fit_uses_only_strictly_resolved_pre_cutoff_samples() -> None:
    rows = fit_records() + (record(6, 0.8, True, resolved_offset=24),)
    cutoff = T0 + timedelta(days=6)
    candidate = fit_platt_calibrator_candidate(
        rows,
        fit_cutoff=cutoff,
        min_samples=4,
        min_class_count=2,
    )
    assert candidate.fit_sample_count == 6
    assert candidate.purged_count == 1
    assert candidate.probability_calibrated is False
    assert candidate.execution_weight == 0
    assert candidate.fit_prediction_ids == tuple(str(index) for index in range(6))


def test_fit_rejects_mixed_insufficient_and_bad_policy() -> None:
    rows = fit_records()
    with pytest.raises(ValueError, match="cannot be empty"):
        fit_platt_calibrator_candidate((), fit_cutoff=T0)
    with pytest.raises(ValueError, match="min_samples"):
        fit_platt_calibrator_candidate(
            rows,
            fit_cutoff=T0,
            min_samples=1,
        )
    with pytest.raises(ValueError, match="min_class_count"):
        fit_platt_calibrator_candidate(
            rows,
            fit_cutoff=T0,
            min_class_count=0,
        )
    with pytest.raises(ValueError, match="epsilon"):
        fit_platt_calibrator_candidate(rows, fit_cutoff=T0, epsilon=0.5)
    with pytest.raises(ValueError, match="one horizon"):
        fit_platt_calibrator_candidate(
            rows + (record(9, 0.5, True, horizon=ResearchHorizon.H4),),
            fit_cutoff=T0 + timedelta(days=20),
            min_samples=2,
            min_class_count=1,
        )
    with pytest.raises(ValueError, match="not enough"):
        fit_platt_calibrator_candidate(
            rows,
            fit_cutoff=T0,
            min_samples=2,
            min_class_count=1,
        )
    one_class = tuple(record(index, 0.1 + index * 0.1, False) for index in range(4))
    with pytest.raises(ValueError, match="both classes"):
        fit_platt_calibrator_candidate(
            one_class,
            fit_cutoff=T0 + timedelta(days=10),
            min_samples=2,
            min_class_count=1,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        fit_platt_calibrator_candidate(
            rows,
            fit_cutoff=datetime(2026, 1, 1),
            min_samples=2,
            min_class_count=1,
        )


def prediction(
    index: int = 10,
    event: str = "return_gt_0",
    horizon: ResearchHorizon = ResearchHorizon.H1,
    when: datetime | None = None,
) -> OOSPrediction:
    timestamp = when or T0 + timedelta(days=index)
    return OOSPrediction(
        "oos-prediction:sha256:" + f"{index + 1:064x}",
        "a" * 64,
        "fold",
        "feature:sha256:" + f"{index + 1:064x}",
        timestamp,
        horizon,
        event,
        "m",
        "v",
        T0,
        "b" * 64,
        4,
        "f",
        "p",
        ("snapshot:sha256:" + "c" * 64,),
        0.55,
    )


def outcome(
    item: OOSPrediction,
    actual: bool = True,
) -> ResolvedOOSOutcome:
    return ResolvedOOSOutcome(
        "oos-outcome:sha256:" + "d" * 64,
        "d" * 64,
        item.prediction_id,
        "label",
        item.feature_row_id,
        item.event_key,
        item.horizon,
        item.prediction_time,
        item.prediction_time + timedelta(hours=1),
        item.prediction_time + timedelta(hours=2),
        actual,
    )


def calibrator():
    return fit_platt_calibrator_candidate(
        fit_records(),
        fit_cutoff=T0 + timedelta(days=6),
        min_samples=4,
        min_class_count=2,
    )


def test_apply_candidate_is_deterministic_non_authoritative_and_bounded() -> None:
    fitted = calibrator()
    item = prediction()
    first = apply_platt_candidate(fitted, item)
    second = apply_platt_candidate(fitted, item)
    assert first == second
    assert 0 <= first.calibrated_probability <= 1
    assert first.probability_calibrated is False
    assert first.decision_authority is False
    assert first.execution_weight == 0
    assert 0 <= fitted.transform(0) <= 1
    assert 0 <= fitted.transform(1) <= 1
    assert fitted.to_payload()["calibrator_id"] == fitted.calibrator_id


def test_apply_rejects_wrong_group_and_pre_cutoff() -> None:
    fitted = calibrator()
    with pytest.raises(ValueError, match="horizon"):
        apply_platt_candidate(
            fitted,
            prediction(horizon=ResearchHorizon.H4),
        )
    with pytest.raises(ValueError, match="event_key"):
        apply_platt_candidate(fitted, prediction(event="other"))
    with pytest.raises(ValueError, match="fit_cutoff"):
        apply_platt_candidate(fitted, prediction(when=T0))
    with pytest.raises(ValueError, match=r"within \[0, 1\]"):
        fitted.transform(2)


def test_candidate_evaluation_records_join_and_guards() -> None:
    fitted = calibrator()
    first_prediction = prediction(10)
    second_prediction = prediction(11)
    first_candidate = apply_platt_candidate(fitted, first_prediction)
    second_candidate = apply_platt_candidate(fitted, second_prediction)
    first_outcome = outcome(first_prediction, False)
    second_outcome = outcome(second_prediction, True)

    rows = candidate_evaluation_records(
        (second_candidate, first_candidate),
        (second_outcome, first_outcome),
    )
    assert [row.prediction_id for row in rows] == [
        first_prediction.prediction_id,
        second_prediction.prediction_id,
    ]

    with pytest.raises(ValueError, match="cannot be empty"):
        candidate_evaluation_records((), ())
    with pytest.raises(ValueError, match="duplicate candidate"):
        candidate_evaluation_records(
            (first_candidate, first_candidate),
            (first_outcome,),
        )
    with pytest.raises(ValueError, match="duplicate outcome"):
        candidate_evaluation_records(
            (first_candidate,),
            (first_outcome, first_outcome),
        )
    with pytest.raises(ValueError, match="identity mismatch"):
        candidate_evaluation_records(
            (first_candidate,),
            (second_outcome,),
        )
    with pytest.raises(ValueError, match="horizon or event"):
        candidate_evaluation_records(
            (first_candidate,),
            (replace(first_outcome, event_key="x"),),
        )
    with pytest.raises(ValueError, match="prediction_time"):
        candidate_evaluation_records(
            (first_candidate,),
            (
                replace(
                    first_outcome,
                    prediction_time=first_outcome.prediction_time
                    + timedelta(seconds=1),
                ),
            ),
        )


def test_fit_rejects_singular_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    import xrp_regime_engine.platt_calibration_v1 as module

    monkeypatch.setattr(
        module,
        "_logistic_recalibration",
        lambda records, epsilon: (None, None),
    )
    with pytest.raises(ValueError, match="singular or non-finite"):
        fit_platt_calibrator_candidate(
            fit_records(),
            fit_cutoff=T0 + timedelta(days=6),
            min_samples=4,
            min_class_count=2,
        )
