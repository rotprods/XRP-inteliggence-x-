from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xrp_regime_engine.future_labels_v1 import (
    BarrierSet,
    FutureLabelStoreV1,
    FutureOutcomeLabel,
    PricePoint,
    build_future_outcome_label,
    canonical_xrp_barrier_set,
)
from xrp_regime_engine.historical_features_v1 import FeatureStoreV1
from xrp_regime_engine.research_horizon import ResearchHorizon, horizon_end_at

T0 = datetime(2026, 1, 2, 12, tzinfo=UTC)
FEATURE_ID = "feature:sha256:" + "a" * 64


def path_for(horizon: ResearchHorizon = ResearchHorizon.H1) -> tuple[PricePoint, ...]:
    end = horizon_end_at(T0, horizon)
    mid = T0 + (end - T0) / 2
    return (
        PricePoint(mid, 110.0),
        PricePoint(end, 105.0),
    )


def label(**kwargs: object) -> FutureOutcomeLabel:
    args = {
        "feature_row_id": FEATURE_ID,
        "prediction_time": T0,
        "horizon": ResearchHorizon.H1,
        "start_price": 100.0,
        "price_path": path_for(),
        "resolved_at": T0 + timedelta(hours=2),
        "barrier_set": BarrierSet.build(
            version="test-v1",
            absolute_prices=(95.0, 105.0, 120.0),
            return_thresholds=(0.05, 0.10),
        ),
    }
    args.update(kwargs)
    return build_future_outcome_label(**args)  # type: ignore[arg-type]


def test_barrier_set_is_sorted_deduplicated_and_deterministic() -> None:
    first = BarrierSet.build(
        version="v1",
        absolute_prices=(3.0, 2.0, 3.0),
        return_thresholds=(0.10, 0.01, 0.10),
    )
    second = BarrierSet.build(
        version="v1",
        absolute_prices=(2.0, 3.0),
        return_thresholds=(0.01, 0.10),
    )
    assert first == second
    assert first.absolute_prices == (2.0, 3.0)
    assert first.to_payload()["barrier_set_id"] == first.barrier_set_id
    assert canonical_xrp_barrier_set().absolute_prices[-1] == 50.0


def test_barrier_set_validation() -> None:
    with pytest.raises(ValueError, match="version"):
        BarrierSet.build(version=" ", absolute_prices=(2.0,), return_thresholds=())
    with pytest.raises(ValueError, match="cannot be empty"):
        BarrierSet.build(version="v", absolute_prices=(), return_thresholds=())
    with pytest.raises(ValueError, match="finite and positive"):
        BarrierSet.build(version="v", absolute_prices=(0.0,), return_thresholds=())
    with pytest.raises(ValueError, match="finite and positive"):
        BarrierSet.build(
            version="v",
            absolute_prices=(),
            return_thresholds=(float("inf"),),
        )


def test_price_point_validation() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PricePoint(datetime(2026, 1, 2), 1.0)
    with pytest.raises(ValueError, match="finite and positive"):
        PricePoint(T0, 0.0)


def test_label_calculates_returns_excursions_drawdown_and_touches() -> None:
    item = label()
    assert item.future_return == pytest.approx(0.05)
    assert item.maximum_favorable_excursion == pytest.approx(0.10)
    assert item.maximum_adverse_excursion == pytest.approx(0.0)
    assert item.maximum_drawdown == pytest.approx(105 / 110 - 1)
    assert item.realized_log_volatility > 0
    assert item.positive_return_touches["0.05"] is True
    assert item.positive_return_touches["0.1"] is True
    assert item.negative_return_touches["0.05"] is False
    assert item.absolute_price_touches["105"] is True
    assert item.absolute_price_touches["120"] is False
    assert item.absolute_price_touches["95"] is False


def test_downside_path_computes_mae_and_lower_barrier_touch() -> None:
    end = horizon_end_at(T0, ResearchHorizon.H1)
    barriers = BarrierSet.build(
        version="v",
        absolute_prices=(90.0, 100.0, 110.0),
        return_thresholds=(0.05, 0.10),
    )
    item = build_future_outcome_label(
        feature_row_id=FEATURE_ID,
        prediction_time=T0,
        horizon=ResearchHorizon.H1,
        start_price=100.0,
        price_path=(
            PricePoint(T0 + timedelta(minutes=30), 89.0),
            PricePoint(end, 95.0),
        ),
        resolved_at=end,
        barrier_set=barriers,
    )
    assert item.maximum_adverse_excursion == pytest.approx(-0.11)
    assert item.negative_return_touches["0.1"] is True
    assert item.absolute_price_touches["90"] is True
    assert item.absolute_price_touches["100"] is True
    assert item.absolute_price_touches["110"] is False


def test_builder_requires_valid_feature_id() -> None:
    with pytest.raises(ValueError, match="feature:sha256"):
        label(feature_row_id="bad")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        label(feature_row_id="feature:sha256:" + "G" * 64)


def test_builder_rejects_invalid_resolution_and_start_price() -> None:
    with pytest.raises(ValueError, match="resolve"):
        label(resolved_at=T0 + timedelta(minutes=30))
    with pytest.raises(ValueError, match="start_price"):
        label(start_price=0.0)


def test_builder_rejects_path_time_leakage_and_missing_endpoint() -> None:
    end = horizon_end_at(T0, ResearchHorizon.H1)
    with pytest.raises(ValueError, match="cannot be empty"):
        label(price_path=())
    with pytest.raises(ValueError, match="unique"):
        point = PricePoint(end, 101.0)
        label(price_path=(point, point))
    with pytest.raises(ValueError, match="strictly after"):
        label(price_path=(PricePoint(T0, 101.0), PricePoint(end, 102.0)))
    with pytest.raises(ValueError, match="after horizon"):
        label(
            price_path=(
                PricePoint(end, 101.0),
                PricePoint(end + timedelta(seconds=1), 102.0),
            )
        )
    with pytest.raises(ValueError, match="exact horizon-end"):
        label(price_path=(PricePoint(T0 + timedelta(minutes=30), 101.0),))


def test_equal_absolute_barrier_is_trivially_touched() -> None:
    barriers = BarrierSet.build(
        version="v",
        absolute_prices=(100.0,),
        return_thresholds=(),
    )
    item = label(barrier_set=barriers)
    assert item.absolute_price_touches["100"] is True


def test_label_payload_round_trip_and_digest_tamper() -> None:
    original = label()
    loaded = FutureOutcomeLabel.from_payload(original.to_payload())
    assert loaded == original
    tampered = original.to_payload()
    tampered["end_price"] = 999.0
    with pytest.raises(RuntimeError, match="digest"):
        FutureOutcomeLabel.from_payload(tampered)


def test_label_store_round_trip_and_isolation(tmp_path: Path) -> None:
    label_db = tmp_path / "labels.db"
    store = FutureLabelStoreV1(label_db)
    item = label()
    assert store.load(item.label_id) is None
    store.save(item)
    store.save(item)
    assert store.count() == 1
    assert store.load(item.label_id) == item
    assert "future_outcome_labels" in store.table_names()
    assert "historical_feature_rows" not in store.table_names()


def test_feature_and_label_store_cannot_share_database(tmp_path: Path) -> None:
    db = tmp_path / "research.db"
    FeatureStoreV1(db)
    with pytest.raises(ValueError, match="non-label"):
        FutureLabelStoreV1(db)

    other = tmp_path / "research2.db"
    FutureLabelStoreV1(other)
    with pytest.raises(ValueError, match="non-feature"):
        FeatureStoreV1(other)


def test_label_store_collision_timeout_and_corrupt_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout"):
        FutureLabelStoreV1(tmp_path / "bad.db", busy_timeout_ms=0)
    store = FutureLabelStoreV1(tmp_path / "labels.db")
    item = label()
    store.save(item)
    with store._connection() as connection:
        connection.execute(
            "UPDATE future_outcome_labels SET payload_json='{}' WHERE label_id=?",
            (item.label_id,),
        )
    with pytest.raises(ValueError, match="collision"):
        store.save(item)
    with store._connection() as connection:
        connection.execute(
            "UPDATE future_outcome_labels SET payload_json='[]' WHERE label_id=?",
            (item.label_id,),
        )
    with pytest.raises(RuntimeError, match="root"):
        store.load(item.label_id)
