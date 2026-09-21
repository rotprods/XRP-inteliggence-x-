from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

import pytest

from xrp_regime_engine.research_horizon import ResearchHorizon
from xrp_regime_engine.return_distribution_v1 import (
    OOSReturnDistributionCandidate,
    REQUIRED_QUANTILES,
    ResolvedReturnDistribution,
    build_return_distribution_evidence,
    resolve_return_distribution,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
FEATURE = "feature:sha256:" + "a" * 64
SNAP = "snapshot:sha256:" + "b" * 64


@dataclass
class Fold:
    fold_id: str = "fold"
    horizon: ResearchHorizon = ResearchHorizon.H1
    cutoff_at: datetime = T0 - timedelta(minutes=1)
    train_feature_row_ids: tuple[str, ...] = ("x", "y")
    test_feature_row_ids: tuple[str, ...] = (FEATURE,)
    test_prediction_start: datetime = T0
    test_prediction_end: datetime = T0


@dataclass
class Label:
    label_id: str = "label"
    feature_row_id: str = FEATURE
    prediction_time: datetime = T0
    horizon: ResearchHorizon = ResearchHorizon.H1
    label_end_at: datetime = T0 + timedelta(hours=1)
    resolved_at: datetime = T0 + timedelta(hours=1)
    future_return: float = 0.03


def candidate(**kwargs: object) -> OOSReturnDistributionCandidate:
    args: dict[str, object] = {
        "fold": Fold(),
        "feature_row_id": FEATURE,
        "prediction_time": T0,
        "horizon": ResearchHorizon.H1,
        "model_id": "m",
        "model_version": "v1",
        "model_training_cutoff": T0 - timedelta(minutes=1),
        "source_snapshot_ids": (SNAP,),
        "quantiles": {
            0.10: -0.1,
            0.25: -0.03,
            0.50: 0.01,
            0.75: 0.05,
            0.90: 0.12,
        },
    }
    args.update(kwargs)
    return OOSReturnDistributionCandidate.build(**args)  # type: ignore[arg-type]


def test_candidate_is_deterministic_non_authoritative_and_quantile_access() -> None:
    first = candidate()
    second = candidate()
    assert first == second
    assert first.distribution_calibrated is False
    assert first.execution_weight == 0
    assert first.quantile(0.5) == pytest.approx(0.01)
    with pytest.raises(KeyError):
        first.quantile(0.33)


def test_candidate_rejects_bad_quantiles_and_oos_contract() -> None:
    with pytest.raises(ValueError, match="exactly P10"):
        candidate(quantiles={0.1: 0})
    with pytest.raises(ValueError, match="non-decreasing"):
        candidate(
            quantiles={
                0.10: 0,
                0.25: -1,
                0.50: 0,
                0.75: 1,
                0.90: 2,
            }
        )
    with pytest.raises(ValueError, match="finite"):
        candidate(
            quantiles={
                0.10: -1,
                0.25: 0,
                0.50: 1,
                0.75: 2,
                0.90: float("inf"),
            }
        )
    with pytest.raises(ValueError, match="fold horizon"):
        candidate(horizon=ResearchHorizon.H4)
    with pytest.raises(ValueError, match="fold test set"):
        candidate(feature_row_id="feature:sha256:" + "c" * 64)
    with pytest.raises(ValueError, match="test interval"):
        candidate(prediction_time=T0 + timedelta(seconds=1))
    with pytest.raises(ValueError, match="fold cutoff"):
        candidate(model_training_cutoff=T0)
    with pytest.raises(ValueError, match="source snapshot"):
        candidate(source_snapshot_ids=())
    with pytest.raises(ValueError, match="training feature set"):
        candidate(fold=Fold(train_feature_row_ids=()))


def test_resolve_distribution_and_guards() -> None:
    distribution = candidate()
    label = Label()
    resolved = resolve_return_distribution(distribution, label)
    assert resolved.actual_return == pytest.approx(0.03)

    with pytest.raises(ValueError, match="feature_row_id"):
        resolve_return_distribution(
            distribution,
            replace(label, feature_row_id="x"),
        )
    with pytest.raises(ValueError, match="prediction_time"):
        resolve_return_distribution(
            distribution,
            replace(
                label,
                prediction_time=T0 + timedelta(seconds=1),
            ),
        )
    with pytest.raises(ValueError, match="horizon"):
        resolve_return_distribution(
            distribution,
            replace(label, horizon=ResearchHorizon.H4),
        )
    with pytest.raises(ValueError, match="label_end_at"):
        resolve_return_distribution(
            distribution,
            replace(label, resolved_at=T0),
        )
    with pytest.raises(ValueError, match="future_return"):
        resolve_return_distribution(
            distribution,
            replace(label, future_return=float("nan")),
        )


def row(
    index: int,
    actual: float,
    horizon: ResearchHorizon = ResearchHorizon.H1,
) -> ResolvedReturnDistribution:
    prediction = T0 + timedelta(days=index)
    distribution = candidate(
        prediction_time=prediction,
        fold=Fold(
            test_prediction_start=prediction,
            test_prediction_end=prediction,
            cutoff_at=prediction - timedelta(minutes=1),
        ),
        model_training_cutoff=prediction - timedelta(minutes=1),
    )
    return ResolvedReturnDistribution(
        distribution.distribution_id,
        "label",
        distribution.feature_row_id,
        distribution.prediction_time,
        horizon,
        distribution.prediction_time + timedelta(hours=1),
        distribution.prediction_time + timedelta(hours=1),
        actual,
        distribution.quantiles,
    )


def test_distribution_evidence_metrics() -> None:
    rows = (
        row(0, -0.02),
        row(1, 0.01),
        row(2, 0.04),
        row(3, 0.10),
    )
    evidence = build_return_distribution_evidence(rows)
    assert evidence.sample_count == 4
    assert len(evidence.quantile_evidence) == 5
    assert 0 <= evidence.interval_50_coverage <= 1
    assert 0 <= evidence.interval_80_coverage <= 1
    assert evidence.median_absolute_error >= 0
    assert evidence.distribution_calibrated is False
    levels = tuple(item.quantile for item in evidence.quantile_evidence)
    assert levels == REQUIRED_QUANTILES


def test_distribution_evidence_rejects_bad_group_and_rows() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        build_return_distribution_evidence(())
    with pytest.raises(ValueError, match="one horizon"):
        build_return_distribution_evidence(
            (
                row(0, 0),
                row(1, 0, horizon=ResearchHorizon.H4),
            )
        )
    broken = replace(
        row(0, 0),
        quantiles=((0.10, 0),),
    )
    with pytest.raises(ValueError, match="canonical levels"):
        build_return_distribution_evidence((broken,))
    crossing = replace(
        row(0, 0),
        quantiles=(
            (0.10, 1),
            (0.25, 0),
            (0.50, 2),
            (0.75, 3),
            (0.90, 4),
        ),
    )
    with pytest.raises(ValueError, match="crossing"):
        build_return_distribution_evidence((crossing,))
    with pytest.raises(ValueError, match="timezone-aware"):
        build_return_distribution_evidence(
            (
                replace(
                    row(0, 0),
                    prediction_time=datetime(2026, 1, 1),
                ),
            )
        )
    with pytest.raises(ValueError, match="actual_return"):
        build_return_distribution_evidence(
            (
                replace(
                    row(0, 0),
                    actual_return=float("inf"),
                ),
            )
        )


def test_candidate_identity_validation_edges() -> None:
    with pytest.raises(ValueError, match="model_id"):
        candidate(model_id=" ")
    with pytest.raises(ValueError, match="snapshot:sha256"):
        candidate(source_snapshot_ids=("bad",))
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        candidate(
            source_snapshot_ids=(
                "snapshot:sha256:" + "G" * 64,
            )
        )
    with pytest.raises(ValueError, match="unique"):
        candidate(fold=Fold(train_feature_row_ids=("x", "x")))
