from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from xrp_regime_engine.historical_store import HistoricalRecord, PointInTimeCatalog
from xrp_regime_engine.research_snapshot import (
    DatasetRequirement,
    ResearchSnapshotBuilder,
    ResearchSnapshotStore,
    SnapshotUnavailable,
)


UTC = timezone.utc
DECISION = datetime(2026, 1, 10, 12, tzinfo=UTC)


def record(
    dataset: str,
    record_id: str,
    *,
    observed_at: datetime,
    available_at: datetime,
    revision: int = 0,
    value: float = 1.0,
) -> HistoricalRecord:
    return HistoricalRecord(
        dataset=dataset,
        record_id=record_id,
        observed_at=observed_at,
        available_at=available_at,
        source="test",
        revision=revision,
        values={"value": value},
        raw_payload_sha256=(dataset[0] * 64),
    )


def catalog(tmp_path: Path) -> PointInTimeCatalog:
    return PointInTimeCatalog(tmp_path / "catalog.sqlite")


def add(catalog: PointInTimeCatalog, *records: HistoricalRecord) -> None:
    for index, item in enumerate(records):
        assert catalog.add(item, partition_path=f"partition-{index}") is True


def requirement(
    dataset: str,
    *,
    required: bool = True,
    minimum_records: int = 1,
    lookback_days: int = 30,
    max_age_days: int = 2,
) -> DatasetRequirement:
    return DatasetRequirement(
        dataset=dataset,
        lookback=timedelta(days=lookback_days),
        minimum_records=minimum_records,
        maximum_latest_age=timedelta(days=max_age_days),
        required=required,
    )


def test_snapshot_uses_only_information_available_at_decision_time(tmp_path: Path) -> None:
    store = catalog(tmp_path)
    original = record(
        "dgs10",
        "DGS10:2026-01-09",
        observed_at=datetime(2026, 1, 9, tzinfo=UTC),
        available_at=datetime(2026, 1, 9, 18, tzinfo=UTC),
        revision=0,
        value=4.2,
    )
    future_revision = record(
        "dgs10",
        "DGS10:2026-01-09",
        observed_at=datetime(2026, 1, 9, tzinfo=UTC),
        available_at=datetime(2026, 1, 12, tzinfo=UTC),
        revision=1,
        value=4.1,
    )
    xrp = record(
        "xrp_usd",
        "XRP-USD:2026-01-10T11",
        observed_at=datetime(2026, 1, 10, 11, tzinfo=UTC),
        available_at=datetime(2026, 1, 10, 12, tzinfo=UTC),
        value=1.25,
    )
    add(store, original, future_revision, xrp)

    snapshot = ResearchSnapshotBuilder(store).build(
        decision_time=DECISION,
        created_at=DECISION + timedelta(seconds=1),
        requirements=(
            requirement("dgs10", max_age_days=2),
            requirement("xrp_usd", lookback_days=1, max_age_days=1),
        ),
    )
    datasets = {dataset.dataset: dataset for dataset in snapshot.datasets}
    assert datasets["dgs10"].records[0].revision == 0
    assert datasets["dgs10"].records[0].values["value"] == 4.2
    assert snapshot.record_count == 2
    assert len(snapshot.snapshot_sha256) == 64


def test_snapshot_is_deterministic_across_requirement_order(tmp_path: Path) -> None:
    store = catalog(tmp_path)
    add(
        store,
        record(
            "a",
            "a-1",
            observed_at=DECISION - timedelta(hours=1),
            available_at=DECISION,
        ),
        record(
            "b",
            "b-1",
            observed_at=DECISION - timedelta(hours=2),
            available_at=DECISION - timedelta(hours=1),
        ),
    )
    builder = ResearchSnapshotBuilder(store)
    first = builder.build(
        decision_time=DECISION,
        created_at=DECISION,
        requirements=(requirement("a"), requirement("b")),
    )
    second = builder.build(
        decision_time=DECISION,
        created_at=DECISION + timedelta(minutes=1),
        requirements=(requirement("b"), requirement("a")),
    )
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert [dataset.dataset for dataset in first.datasets] == ["a", "b"]


def test_required_missing_stale_or_insufficient_dataset_blocks_snapshot(tmp_path: Path) -> None:
    store = catalog(tmp_path)
    builder = ResearchSnapshotBuilder(store)
    with pytest.raises(SnapshotUnavailable, match="0 record"):
        builder.build(
            decision_time=DECISION,
            requirements=(requirement("missing"),),
        )

    old = record(
        "old",
        "old-1",
        observed_at=DECISION - timedelta(days=10),
        available_at=DECISION - timedelta(days=9),
    )
    add(store, old)
    with pytest.raises(SnapshotUnavailable, match="freshness"):
        builder.build(
            decision_time=DECISION,
            requirements=(requirement("old", lookback_days=30, max_age_days=2),),
        )

    recent = record(
        "small",
        "small-1",
        observed_at=DECISION - timedelta(hours=1),
        available_at=DECISION,
    )
    add(store, recent)
    with pytest.raises(SnapshotUnavailable, match="minimum 2"):
        builder.build(
            decision_time=DECISION,
            requirements=(requirement("small", minimum_records=2),),
        )


def test_optional_dataset_can_be_empty(tmp_path: Path) -> None:
    snapshot = ResearchSnapshotBuilder(catalog(tmp_path)).build(
        decision_time=DECISION,
        requirements=(requirement("optional", required=False, minimum_records=100),),
    )
    assert snapshot.record_count == 0
    assert snapshot.datasets[0].record_count == 0
    assert snapshot.datasets[0].required is False


def test_builder_rejects_invalid_configuration_and_created_at(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="lookback"):
        requirement("x", lookback_days=0)
    with pytest.raises(ValueError, match="minimum_records"):
        DatasetRequirement("x", timedelta(days=1), -1, timedelta(days=1))
    with pytest.raises(ValueError, match="maximum_latest_age"):
        DatasetRequirement("x", timedelta(days=1), 1, timedelta(days=-1))

    builder = ResearchSnapshotBuilder(catalog(tmp_path))
    with pytest.raises(ValueError, match="at least one"):
        builder.build(decision_time=DECISION, requirements=())
    with pytest.raises(ValueError, match="unique"):
        builder.build(
            decision_time=DECISION,
            requirements=(requirement("x", required=False), requirement("x", required=False)),
        )
    with pytest.raises(ValueError, match="created_at"):
        builder.build(
            decision_time=DECISION,
            created_at=DECISION - timedelta(seconds=1),
            requirements=(requirement("x", required=False),),
        )


def test_snapshot_store_is_immutable_verifiable_and_path_safe(tmp_path: Path) -> None:
    store = catalog(tmp_path)
    add(
        store,
        record(
            "xrp",
            "xrp-1",
            observed_at=DECISION - timedelta(hours=1),
            available_at=DECISION,
        ),
    )
    snapshot = ResearchSnapshotBuilder(store).build(
        decision_time=DECISION,
        created_at=DECISION,
        requirements=(requirement("xrp"),),
    )
    snapshots = ResearchSnapshotStore(tmp_path / "snapshots")
    relative = snapshots.put(snapshot)
    assert snapshots.put(snapshot) == relative
    payload = snapshots.read(relative)
    assert payload["snapshot_sha256"] == snapshot.snapshot_sha256
    assert payload["record_count"] == 1

    path = tmp_path / "snapshots" / relative
    tampered = json.loads(path.read_text())
    tampered["record_count"] = 99
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity"):
        snapshots.read(relative)
    with pytest.raises(ValueError, match="escapes"):
        snapshots.read("../outside.json")
