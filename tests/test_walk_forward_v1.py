from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.future_labels_v1 import (
    PricePoint,
    build_future_outcome_label,
    canonical_xrp_barrier_set,
)
from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon, horizon_end_at
from xrp_regime_engine.walk_forward_v1 import (
    LabeledFeatureRow,
    WalkForwardConfig,
    WalkForwardMode,
    build_walk_forward_folds,
    join_labeled_rows,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _feature(
    index: int,
    prediction: datetime,
    *,
    horizon: ResearchHorizon = ResearchHorizon.H1,
) -> HistoricalFeatureRow:
    digest = sha256(f"snapshot-{index}".encode()).hexdigest()
    return HistoricalFeatureRow.build(
        feature_time=prediction,
        prediction_time=prediction,
        horizon=horizon,
        feature_schema_version="features-v1",
        provider_universe_version="providers-v1",
        eligibility_class=EligibilityClass.STRICT_REPLAY,
        source_snapshot_ids=(f"snapshot:sha256:{digest}",),
        feature_families={"market": {"index": index}},
    )


def _label(
    feature: HistoricalFeatureRow,
    *,
    resolved_at: datetime | None = None,
):
    end_at = horizon_end_at(feature.prediction_time, feature.horizon)
    return build_future_outcome_label(
        feature_row_id=feature.feature_row_id,
        prediction_time=feature.prediction_time,
        horizon=feature.horizon,
        start_price=1.0,
        price_path=(PricePoint(at=end_at, price=1.01),),
        resolved_at=end_at if resolved_at is None else resolved_at,
        barrier_set=canonical_xrp_barrier_set(),
    )


def test_join_is_order_independent() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(3))
    labels = tuple(_label(feature) for feature in features)

    forward = join_labeled_rows(features, labels)
    reverse = join_labeled_rows(tuple(reversed(features)), tuple(reversed(labels)))

    assert tuple(row.feature.feature_row_id for row in forward) == tuple(
        row.feature.feature_row_id for row in reverse
    )


def test_labeled_row_rejects_identity_mismatch() -> None:
    first = _feature(0, T0)
    second = _feature(1, T0 + timedelta(days=1))

    with pytest.raises(ValueError, match="same feature_row_id"):
        LabeledFeatureRow(feature=first, label=_label(second))


def test_join_rejects_missing_and_orphan_labels() -> None:
    first = _feature(0, T0)
    second = _feature(1, T0 + timedelta(days=1))

    with pytest.raises(ValueError, match="missing labels"):
        join_labeled_rows((first, second), (_label(first),))

    orphan = _feature(2, T0 + timedelta(days=2))
    with pytest.raises(ValueError, match="orphan labels"):
        join_labeled_rows((first,), (_label(first), _label(orphan)))


def test_join_rejects_mixed_horizons_and_duplicate_prediction_times() -> None:
    one_hour = _feature(0, T0)
    four_hour = _feature(1, T0 + timedelta(days=1), horizon=ResearchHorizon.H4)
    with pytest.raises(ValueError, match="exactly one research horizon"):
        join_labeled_rows((one_hour, four_hour), (_label(one_hour), _label(four_hour)))

    same_time = _feature(2, T0)
    with pytest.raises(ValueError, match="prediction_time values must be unique"):
        join_labeled_rows((one_hour, same_time), (_label(one_hour), _label(same_time)))


def test_expanding_window_purges_label_resolved_at_test_boundary() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(4))
    labels = (
        _label(features[0]),
        _label(features[1], resolved_at=features[2].prediction_time),
        _label(features[2]),
        _label(features[3]),
    )
    rows = join_labeled_rows(features, labels)

    folds = build_walk_forward_folds(rows, config=WalkForwardConfig(min_train_size=1))

    second_fold = folds[1]
    assert second_fold.test_feature_row_ids == (features[2].feature_row_id,)
    assert second_fold.train_feature_row_ids == (features[0].feature_row_id,)
    assert second_fold.purged_count == 1


def test_explicit_embargo_applies_after_label_resolution() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(5))
    rows = join_labeled_rows(features, tuple(_label(feature) for feature in features))

    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(min_train_size=1, embargo=timedelta(days=2)),
    )

    first = folds[0]
    assert first.test_prediction_start == features[3].prediction_time
    assert first.train_feature_row_ids == (features[0].feature_row_id,)
    assert first.purged_count == 2
    assert first.cutoff_at == features[1].prediction_time


def test_rolling_window_caps_training_rows() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(8))
    rows = join_labeled_rows(features, tuple(_label(feature) for feature in features))

    folds = build_walk_forward_folds(
        rows,
        config=WalkForwardConfig(
            min_train_size=2,
            mode=WalkForwardMode.ROLLING,
            max_train_size=3,
        ),
    )

    assert len(folds[-1].train_feature_row_ids) == 3
    assert folds[-1].train_feature_row_ids == tuple(
        feature.feature_row_id for feature in features[4:7]
    )


def test_fold_identity_is_deterministic() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(5))
    labels = tuple(_label(feature) for feature in features)
    config = WalkForwardConfig(min_train_size=2)

    forward = build_walk_forward_folds(join_labeled_rows(features, labels), config=config)
    reverse = build_walk_forward_folds(
        join_labeled_rows(tuple(reversed(features)), tuple(reversed(labels))),
        config=config,
    )

    assert tuple(fold.fold_id for fold in forward) == tuple(fold.fold_id for fold in reverse)


def test_no_fold_when_all_labels_resolve_too_late() -> None:
    features = tuple(_feature(i, T0 + timedelta(days=i)) for i in range(4))
    late = T0 + timedelta(days=30)
    labels = tuple(_label(feature, resolved_at=late) for feature in features)
    rows = join_labeled_rows(features, labels)

    with pytest.raises(ValueError, match="no leakage-safe"):
        build_walk_forward_folds(rows, config=WalkForwardConfig(min_train_size=1))


def test_valid_config_smoke() -> None:
    config = WalkForwardConfig(
        min_train_size=2,
        test_size=2,
        step_size=2,
        mode=WalkForwardMode.ROLLING,
        max_train_size=5,
        embargo=timedelta(hours=1),
    )
    assert config.effective_step_size == 2


def test_config_rejects_overlapping_test_windows() -> None:
    with pytest.raises(ValueError, match="prevent overlapping test folds"):
        WalkForwardConfig(min_train_size=1, test_size=2, step_size=1)


def test_config_requires_rolling_bound() -> None:
    with pytest.raises(ValueError, match="requires max_train_size"):
        WalkForwardConfig(min_train_size=1, mode=WalkForwardMode.ROLLING)


def test_config_rejects_negative_embargo() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        WalkForwardConfig(min_train_size=1, embargo=timedelta(seconds=-1))
