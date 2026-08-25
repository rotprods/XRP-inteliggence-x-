from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from xrp_regime_engine.historical_backfill import (
    BackfillPage,
    BackfillRunner,
    BackfillWindow,
    NormalizedPageRecord,
)
from xrp_regime_engine.historical_store import (
    BackfillCheckpointStore,
    ContentAddressedRawStore,
    DatasetManifest,
    HistoricalRecord,
    JSONLPartitionStore,
    ManifestStore,
    PointInTimeCatalog,
)


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)
RAW_HASH = "a" * 64


def record(
    record_id: str,
    *,
    observed_at: datetime = BASE,
    available_at: datetime | None = None,
    revision: int = 0,
    value: float = 1.0,
) -> HistoricalRecord:
    return HistoricalRecord(
        dataset="xrp_usd_3600s",
        record_id=record_id,
        observed_at=observed_at,
        available_at=available_at or observed_at + timedelta(hours=1),
        source="test_source",
        revision=revision,
        values={"close": value},
        raw_payload_sha256=RAW_HASH,
    )


def test_raw_store_is_content_addressed_idempotent_and_verifiable(tmp_path: Path) -> None:
    store = ContentAddressedRawStore(tmp_path)
    payload = b'{"price":"1.23"}'
    envelope = store.put(
        provider="coinbase",
        payload=payload,
        received_at=BASE + timedelta(hours=2),
        observed_at=BASE,
        source_url="https://api.example.test/ticker?pair=XRP-USD",
        attributes={"dataset": "xrp_usd"},
    )
    duplicate = store.put(
        provider="coinbase",
        payload=payload,
        received_at=BASE + timedelta(hours=2),
        observed_at=BASE,
        source_url="https://api.example.test/ticker?pair=XRP-USD",
        attributes={"dataset": "xrp_usd"},
    )
    assert duplicate == envelope
    assert store.read(envelope) == payload
    store.verify(envelope)
    assert (tmp_path / envelope.payload_path).exists()
    assert (tmp_path / envelope.metadata_path).exists()


def test_raw_store_rejects_unsafe_provider_credentials_and_corruption(tmp_path: Path) -> None:
    store = ContentAddressedRawStore(tmp_path)
    with pytest.raises(ValueError, match="unsafe"):
        store.put(
            provider="../coinbase",
            payload=b"{}",
            received_at=BASE,
            source_url="https://api.example.test",
        )
    with pytest.raises(ValueError, match="credentials"):
        store.put(
            provider="coinbase",
            payload=b"{}",
            received_at=BASE,
            source_url="https://user:pass@api.example.test",
        )
    envelope = store.put(
        provider="coinbase",
        payload=b'{"ok":true}',
        received_at=BASE,
        source_url="https://api.example.test",
    )
    (tmp_path / envelope.payload_path).write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="integrity"):
        store.read(envelope)


def test_historical_record_enforces_availability_and_hash_contracts() -> None:
    with pytest.raises(ValueError, match="available_at"):
        record("bad", available_at=BASE - timedelta(seconds=1))
    with pytest.raises(ValueError, match="SHA-256"):
        HistoricalRecord(
            dataset="xrp",
            record_id="bad-hash",
            observed_at=BASE,
            available_at=BASE,
            source="test",
            revision=0,
            values={},
            raw_payload_sha256="not-a-hash",
        )


def test_jsonl_partition_is_deterministic_and_detects_corruption(tmp_path: Path) -> None:
    store = JSONLPartitionStore(tmp_path)
    rows = (
        record("b", observed_at=BASE + timedelta(hours=1)),
        record("a", observed_at=BASE),
    )
    partition = store.write_partition(
        dataset="xrp_usd_3600s",
        partition_key="date=2026-01-01",
        records=rows,
    )
    replay = store.write_partition(
        dataset="xrp_usd_3600s",
        partition_key="date=2026-01-01",
        records=rows,
    )
    assert replay == partition
    decoded = store.read_partition(partition)
    assert [row["record_id"] for row in decoded] == ["a", "b"]
    path = tmp_path / partition.path
    path.write_text("corrupt\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="integrity"):
        store.read_partition(partition)


def test_partition_rejects_duplicate_revisions() -> None:
    store = JSONLPartitionStore("unused")
    duplicate = record("a")
    with pytest.raises(ValueError, match="duplicate"):
        store.write_partition(
            dataset="xrp_usd_3600s",
            partition_key="date=2026-01-01",
            records=(duplicate, duplicate),
        )


def test_manifest_is_deterministic_and_immutable(tmp_path: Path) -> None:
    partitions = JSONLPartitionStore(tmp_path)
    partition = partitions.write_partition(
        dataset="xrp_usd_3600s",
        partition_key="date=2026-01-01",
        records=(record("a"),),
    )
    manifest = DatasetManifest.build(
        dataset="xrp_usd_3600s",
        schema_version="candle.v1",
        created_at=BASE + timedelta(days=1),
        partitions=(partition,),
    )
    same = DatasetManifest.build(
        dataset="xrp_usd_3600s",
        schema_version="candle.v1",
        created_at=BASE + timedelta(days=1),
        partitions=(partition,),
    )
    assert manifest.manifest_sha256 == same.manifest_sha256
    relative = ManifestStore(tmp_path).put(manifest)
    assert json.loads((tmp_path / relative).read_text())["total_rows"] == 1


def test_point_in_time_catalog_returns_only_latest_available_revision(tmp_path: Path) -> None:
    catalog = PointInTimeCatalog(tmp_path / "catalog.sqlite")
    original = record("candle-1", revision=0, value=1.0, available_at=BASE + timedelta(hours=1))
    revised = record("candle-1", revision=1, value=1.1, available_at=BASE + timedelta(days=1))
    other = record(
        "candle-2",
        observed_at=BASE + timedelta(hours=1),
        available_at=BASE + timedelta(hours=2),
        value=2.0,
    )
    assert catalog.add(original, partition_path="p0") is True
    assert catalog.add(original, partition_path="p0") is False
    assert catalog.add(revised, partition_path="p1") is True
    assert catalog.add(other, partition_path="p2") is True
    early = catalog.as_of(dataset="xrp_usd_3600s", decision_time=BASE + timedelta(hours=3))
    assert {row.record_id: row.values["close"] for row in early} == {
        "candle-1": 1.0,
        "candle-2": 2.0,
    }
    late = catalog.as_of(dataset="xrp_usd_3600s", decision_time=BASE + timedelta(days=2))
    assert {row.record_id: row.values["close"] for row in late}["candle-1"] == 1.1
    assert catalog.count(dataset="xrp_usd_3600s") == 3


def test_checkpoint_store_round_trip(tmp_path: Path) -> None:
    store = BackfillCheckpointStore(tmp_path / "checkpoints.sqlite")
    assert store.load("job") is None
    store.save("job", cursor={"page": 2}, completed=False)
    assert store.load("job") == ({"page": 2}, False)
    store.save("job", cursor={"completed_at": "now"}, completed=True)
    assert store.load("job") == ({"completed_at": "now"}, True)


class TwoPageAdapter:
    provider = "test_provider"
    source = "test_source"
    dataset = "xrp_usd_3600s"
    schema_version = "candle.v1"

    def initial_cursor(self, window: BackfillWindow) -> Mapping[str, Any]:
        del window
        return {"page": 1}

    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage:
        page = int(cursor["page"])
        observed = window.start + timedelta(hours=page - 1)
        item = NormalizedPageRecord(
            record_id=f"candle-{page}",
            observed_at=observed,
            available_at=observed + timedelta(hours=1),
            values={"close": float(page)},
        )
        return BackfillPage(
            raw_payload=json.dumps({"page": page}).encode(),
            source_url=f"https://api.example.test/history?page={page}",
            received_at=window.end + timedelta(hours=1),
            records=(item,),
            next_cursor={"page": 2} if page == 1 else None,
            completed=page == 2,
            attributes={"page": page},
        )


def runner(tmp_path: Path, *, max_pages: int = 10) -> BackfillRunner:
    return BackfillRunner(
        raw_store=ContentAddressedRawStore(tmp_path),
        partition_store=JSONLPartitionStore(tmp_path),
        catalog=PointInTimeCatalog(tmp_path / "catalog.sqlite"),
        manifest_store=ManifestStore(tmp_path),
        checkpoints=BackfillCheckpointStore(tmp_path / "checkpoints.sqlite"),
        max_pages=max_pages,
    )


def test_backfill_runner_is_raw_first_resumable_and_idempotent(tmp_path: Path) -> None:
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    engine = runner(tmp_path)
    result = engine.run(TwoPageAdapter(), window)
    assert result.completed is True
    assert result.pages_fetched == 2
    assert result.raw_payloads_written == 2
    assert result.records_seen == 2
    assert result.catalog_records_inserted == 2
    assert len(result.partitions) == 2
    assert result.manifest_path is not None
    assert (tmp_path / result.manifest_path).exists()
    resumed = engine.run(TwoPageAdapter(), window)
    assert resumed.completed is True
    assert resumed.resumed is True
    assert resumed.pages_fetched == 0


class CursorCycleAdapter(TwoPageAdapter):
    def fetch_page(self, window: BackfillWindow, cursor: Mapping[str, Any]) -> BackfillPage:
        del cursor
        observed = window.start
        return BackfillPage(
            raw_payload=b'{"cycle":true}',
            source_url="https://api.example.test/history",
            received_at=window.end,
            records=(
                NormalizedPageRecord(
                    record_id="cycle",
                    observed_at=observed,
                    available_at=observed + timedelta(hours=1),
                    values={"close": 1},
                ),
            ),
            next_cursor={"page": 1},
            completed=False,
            attributes={},
        )


def test_backfill_runner_detects_cursor_cycles(tmp_path: Path) -> None:
    window = BackfillWindow(BASE, BASE + timedelta(hours=2), 3600)
    with pytest.raises(RuntimeError, match="cursor cycle"):
        runner(tmp_path).run(CursorCycleAdapter(), window)
