from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from scripts.audit_historical_candles_v05 import load_manifest_records
from xrp_regime_engine.historical_store import (
    DatasetManifest,
    HistoricalRecord,
    JSONLPartitionStore,
    ManifestStore,
)


UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def record() -> HistoricalRecord:
    return HistoricalRecord(
        dataset="xrp_usd_spot_3600s",
        record_id="candle-0",
        observed_at=BASE,
        available_at=BASE + timedelta(hours=1),
        source="coinbase",
        revision=0,
        values={"open": "1", "high": "1.2", "low": "0.9", "close": "1.1", "volume": "100"},
        raw_payload_sha256="a" * 64,
    )


def create_manifest(root: Path) -> Path:
    partition = JSONLPartitionStore(root).write_partition(
        dataset="xrp_usd_spot_3600s",
        partition_key="date=2026-01-01",
        records=(record(),),
    )
    manifest = DatasetManifest.build(
        dataset="xrp_usd_spot_3600s",
        schema_version="candle.v1",
        created_at=BASE + timedelta(days=1),
        partitions=(partition,),
    )
    relative = ManifestStore(root).put(manifest)
    return root / relative


def test_load_manifest_records_verifies_hash_and_partitions(tmp_path: Path) -> None:
    manifest = create_manifest(tmp_path)
    dataset, records = load_manifest_records(tmp_path, manifest)
    assert dataset == "xrp_usd_spot_3600s"
    assert len(records) == 1
    assert records[0].record_id == "candle-0"


def test_load_manifest_records_rejects_manifest_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "manifest.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inside"):
        load_manifest_records(root, outside)


def test_load_manifest_records_rejects_tampered_manifest(tmp_path: Path) -> None:
    manifest = create_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["total_rows"] = 999
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash"):
        load_manifest_records(tmp_path, manifest)


def test_load_manifest_records_rejects_empty_or_non_object_manifest(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        load_manifest_records(tmp_path, empty)

    no_partitions = tmp_path / "no-partitions.json"
    unsigned = {
        "dataset": "xrp",
        "schema_version": "v1",
        "created_at": BASE.isoformat(),
        "partitions": [],
        "total_rows": 0,
    }
    from xrp_regime_engine.historical_store import canonical_json_bytes, sha256_hex

    no_partitions.write_text(
        json.dumps({**unsigned, "manifest_sha256": sha256_hex(canonical_json_bytes(unsigned))}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no partitions"):
        load_manifest_records(tmp_path, no_partitions)
