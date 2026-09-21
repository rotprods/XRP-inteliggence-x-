from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from xrp_regime_engine.historical_contract import EligibilityClass
from xrp_regime_engine.historical_features_v1 import FeatureStoreV1, HistoricalFeatureRow
from xrp_regime_engine.research_horizon import ResearchHorizon

T0 = datetime(2026, 1, 2, 12, tzinfo=UTC)
SNAP = "snapshot:sha256:" + "a" * 64


def row(**kwargs: object) -> HistoricalFeatureRow:
    args = {
        "feature_time": T0,
        "prediction_time": T0,
        "horizon": ResearchHorizon.D1,
        "feature_schema_version": "features-v1",
        "provider_universe_version": "providers-v1",
        "eligibility_class": EligibilityClass.STRICT_REPLAY,
        "source_snapshot_ids": (SNAP,),
        "evidence_ids": ("evidence:1",),
        "feature_families": {
            "market": {"trailing_return_1h": 0.01, "missing": None},
            "macro": {"dxy_change": -0.1},
        },
        "quality_flags": ("OK",),
    }
    args.update(kwargs)
    return HistoricalFeatureRow.build(**args)  # type: ignore[arg-type]


def test_feature_row_is_deterministic_and_normalized() -> None:
    a = row(source_snapshot_ids=(SNAP, SNAP), quality_flags=("OK", "OK"))
    b = row()
    assert a.feature_row_id == b.feature_row_id
    assert a.feature_sha256 == b.feature_sha256
    assert a.source_snapshot_ids == (SNAP,)
    assert a.feature_families["market"]["trailing_return_1h"] == 0.01


def test_feature_row_rejects_future_time_and_ineligible_evidence() -> None:
    with pytest.raises(ValueError, match="feature_time"):
        row(feature_time=T0 + timedelta(seconds=1))
    with pytest.raises(ValueError, match="ineligible"):
        row(eligibility_class=EligibilityClass.INELIGIBLE)


@pytest.mark.parametrize(
    "field",
    ["future_return_1d", "label_x", "target_y", "touch_5", "outcome_z", "mfe", "mae_1d"],
)
def test_feature_row_rejects_outcome_names(field: str) -> None:
    with pytest.raises(ValueError, match="forbidden"):
        row(feature_families={"market": {field: 1.0}})


def test_feature_values_and_structure_are_strict() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        row(feature_families={})
    with pytest.raises(ValueError, match="cannot be empty"):
        row(feature_families={"market": {}})
    with pytest.raises(ValueError, match="not bool"):
        row(feature_families={"market": {"x": True}})
    with pytest.raises(ValueError, match="finite"):
        row(feature_families={"market": {"x": float("inf")}})
    with pytest.raises(ValueError, match="required"):
        row(feature_families={"": {"x": 1.0}})
    with pytest.raises(ValueError, match="required"):
        row(feature_families={"market": {"": 1.0}})


def test_snapshot_and_version_validation() -> None:
    with pytest.raises(ValueError, match="at least one"):
        row(source_snapshot_ids=())
    with pytest.raises(ValueError, match="snapshot:sha256"):
        row(source_snapshot_ids=("bad",))
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        row(source_snapshot_ids=("snapshot:sha256:" + "G" * 64,))
    with pytest.raises(ValueError, match="feature_schema_version"):
        row(feature_schema_version=" ")
    with pytest.raises(ValueError, match="provider_universe_version"):
        row(provider_universe_version=" ")


def test_payload_round_trip_and_digest_tamper() -> None:
    original = row()
    loaded = HistoricalFeatureRow.from_payload(original.to_payload())
    assert loaded == original
    tampered = original.to_payload()
    tampered["feature_sha256"] = "0" * 64
    with pytest.raises(RuntimeError, match="digest"):
        HistoricalFeatureRow.from_payload(tampered)


def test_payload_shape_corruption_is_detected() -> None:
    payload = row().to_payload()
    payload["feature_families"] = []
    with pytest.raises(RuntimeError, match="feature_families"):
        HistoricalFeatureRow.from_payload(payload)
    payload = row().to_payload()
    payload["feature_families"] = {"market": []}
    with pytest.raises(RuntimeError, match="feature family"):
        HistoricalFeatureRow.from_payload(payload)


def test_feature_store_round_trip_and_idempotency(tmp_path: Path) -> None:
    store = FeatureStoreV1(tmp_path / "features.db")
    item = row()
    assert store.load(item.feature_row_id) is None
    store.save(item)
    store.save(item)
    assert store.count() == 1
    assert store.load(item.feature_row_id) == item
    assert "historical_feature_rows" in store.table_names()
    assert "future_outcome_labels" not in store.table_names()


def test_feature_store_role_collision_and_payload_collision(tmp_path: Path) -> None:
    db = tmp_path / "features.db"
    store = FeatureStoreV1(db)
    item = row()
    store.save(item)
    with store._connection() as connection:
        connection.execute(
            "UPDATE historical_feature_rows SET payload_json='{}' WHERE feature_row_id=?",
            (item.feature_row_id,),
        )
    with pytest.raises(ValueError, match="collision"):
        store.save(item)


def test_feature_store_rejects_bad_timeout_and_corrupt_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout"):
        FeatureStoreV1(tmp_path / "x.db", busy_timeout_ms=0)
    store = FeatureStoreV1(tmp_path / "y.db")
    item = row()
    store.save(item)
    with store._connection() as connection:
        connection.execute(
            "UPDATE historical_feature_rows SET payload_json='[]' WHERE feature_row_id=?",
            (item.feature_row_id,),
        )
    with pytest.raises(RuntimeError, match="root"):
        store.load(item.feature_row_id)


def test_feature_row_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        row(feature_time=datetime(2026, 1, 2, 12))
