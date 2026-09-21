from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    EligibilityClass,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import HistoricalEvidenceStoreV2

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
RAW = b'{"close":"2.00"}'
RAW_SHA = sha256(RAW).hexdigest()
REQUEST_SHA = sha256(b"request").hexdigest()


def receipt(
    *,
    provider: str = "coinbase",
    fetched_at: datetime = T0,
    payload_sha256: str = RAW_SHA,
) -> FetchReceipt:
    return FetchReceipt.create(
        source_id=f"source:{provider}",
        provider=provider,
        canonical_uri=f"https://example.com/{provider}/market",
        endpoint="/market",
        request_fingerprint=REQUEST_SHA,
        fetched_at=fetched_at,
        payload_sha256=payload_sha256,
        ingestion_version="2",
        parser_version="2",
    )


def observation(
    item_id: str,
    fetch: FetchReceipt,
    *,
    dataset: str = "xrp_spot_1h",
    provider: str | None = None,
    available_at: datetime | None = None,
    reconstruction_basis_id: str | None = None,
    revision: int = 0,
    value: float = 2.0,
) -> HistoricalObservation:
    actual_provider = provider or fetch.provider
    return HistoricalObservation(
        observation_id=item_id,
        dataset=dataset,
        record_id=f"{item_id}:record",
        provider=actual_provider,
        source_id=fetch.source_id,
        symbol="XRP_USD" if actual_provider == "coinbase" else "XRP_USDT",
        instrument="spot",
        observed_at=T0 - timedelta(hours=1),
        fetched_at=fetch.fetched_at,
        fetch_id=fetch.fetch_id,
        payload_sha256=fetch.payload_sha256,
        values={"close": value},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="provider_exact",
        available_at=available_at or (T0 - timedelta(minutes=1)),
        revision_sequence=revision,
        reconstruction_basis_id=reconstruction_basis_id,
    )


def registered_observation(
    store: HistoricalEvidenceStoreV2,
    item_id: str,
    *,
    provider: str = "coinbase",
    fetched_at: datetime = T0,
    available_at: datetime | None = None,
    reconstruction_basis_id: str | None = None,
    value: float = 2.0,
) -> HistoricalObservation:
    fetch = receipt(provider=provider, fetched_at=fetched_at)
    store.record_fetch(RAW, fetch)
    return observation(
        item_id,
        fetch,
        provider=provider,
        available_at=available_at,
        reconstruction_basis_id=reconstruction_basis_id,
        value=value,
    )


def test_same_raw_bytes_keep_distinct_fetch_receipts(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    first = receipt(fetched_at=T0)
    second = receipt(fetched_at=T0 + timedelta(minutes=1))

    left = store.record_fetch(RAW, first)
    right = store.record_fetch(RAW, second)

    assert left.payload_sha256 == right.payload_sha256 == RAW_SHA
    assert first.fetch_id != second.fetch_id
    assert store.raw_blob_count() == 1
    assert store.fetch_receipt_count() == 2


def test_record_fetch_rejects_payload_digest_mismatch(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    wrong = receipt(payload_sha256=sha256(b"other").hexdigest())
    with pytest.raises(ValueError, match="does not match"):
        store.record_fetch(RAW, wrong)
    assert store.raw_blob_count() == 0


def test_raw_blob_corruption_is_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    blob = store.put_raw(RAW)
    (tmp_path / blob.relative_path).write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="integrity"):
        store.read_raw(blob.payload_sha256)


def test_fetch_id_collision_is_fail_closed(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    original = receipt()
    store.record_fetch(RAW, original)
    conflicting = replace(original, provider="kraken")
    with pytest.raises(ValueError, match="fetch_id collision"):
        store.record_fetch(RAW, conflicting)


def test_observation_requires_registered_matching_receipt(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    fetch = receipt()
    item = observation("missing", fetch)
    with pytest.raises(ValueError, match="not registered"):
        store.save_observation(item)

    store.record_fetch(RAW, fetch)
    mismatched = replace(item, provider="kraken")
    with pytest.raises(ValueError, match="does not match"):
        store.save_observation(mismatched)


def test_observation_id_collision_is_fail_closed(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    fetch = receipt()
    store.record_fetch(RAW, fetch)
    first = observation("same", fetch, value=2.0)
    second = observation("same", fetch, value=3.0)
    store.save_observation(first)
    with pytest.raises(ValueError, match="observation_id collision"):
        store.save_observation(second)


def test_partition_is_order_independent_and_idempotent(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    a = registered_observation(store, "a")
    b = registered_observation(store, "b", provider="binance")

    first = store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(a, b),
    )
    second = store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(b, a),
    )

    assert first.partition_id == second.partition_id
    assert first.file_sha256 == second.file_sha256
    assert len(store.list_partitions("xrp_spot_1h")) == 1
    store.verify_partition(first)


def test_partition_rejects_unsafe_key_and_duplicate_ids(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    a = registered_observation(store, "a")
    with pytest.raises(ValueError, match="unsafe"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="../escape",
            observations=(a,),
        )
    with pytest.raises(ValueError, match="observation_id"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(a, a),
        )


def test_resume_manifest_reconstructs_all_durable_partitions(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    day_one = registered_observation(store, "day-one")
    p1 = store.persist_partition_then_checkpoint(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-01",
        observations=(day_one,),
        job_key="coinbase:xrp",
        cursor={"page": 2},
        completed=False,
        updated_at=T0,
    )

    resumed = HistoricalEvidenceStoreV2(tmp_path)
    checkpoint = resumed.load_checkpoint("coinbase:xrp")
    assert checkpoint is not None
    assert checkpoint.cursor == {"page": 2}

    day_two = registered_observation(
        resumed,
        "day-two",
        fetched_at=T0 + timedelta(minutes=1),
        available_at=T0,
    )
    p2 = resumed.persist_partition_then_checkpoint(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(day_two,),
        job_key="coinbase:xrp",
        cursor={"done": True},
        completed=True,
        updated_at=T0 + timedelta(minutes=2),
    )
    manifest = resumed.finalize_manifest(
        dataset="xrp_spot_1h",
        schema_version="historical-observation-v2",
        created_at=T0 + timedelta(minutes=3),
    )

    assert set(manifest.partition_ids) == {p1.partition_id, p2.partition_id}
    assert manifest.total_rows == 2
    assert resumed.load_checkpoint("coinbase:xrp").completed is True


def test_checkpoint_cannot_reopen_completed_job(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    store.save_checkpoint(
        job_key="job",
        cursor={"done": True},
        completed=True,
        updated_at=T0,
    )
    with pytest.raises(ValueError, match="cannot be reopened"):
        store.save_checkpoint(
            job_key="job",
            cursor={"page": 1},
            completed=False,
            updated_at=T0 + timedelta(seconds=1),
        )


def test_checkpoint_failure_never_erases_durable_partition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")

    def fail_checkpoint(**kwargs: object) -> None:
        raise RuntimeError("checkpoint unavailable")

    monkeypatch.setattr(store, "save_checkpoint", fail_checkpoint)
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        store.persist_partition_then_checkpoint(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(item,),
            job_key="job",
            cursor={"page": 2},
            completed=False,
            updated_at=T0,
        )

    assert store.load_checkpoint("job") is None
    assert len(store.list_partitions("xrp_spot_1h")) == 1


def test_corrupt_partition_blocks_manifest_finalization(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    partition = store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(item,),
    )
    (tmp_path / partition.relative_path).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA-256"):
        store.finalize_manifest(
            dataset="xrp_spot_1h",
            schema_version="v2",
            created_at=T0,
        )


def test_manifest_is_deterministic_across_restart(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(item,),
    )
    first = store.finalize_manifest(
        dataset="xrp_spot_1h",
        schema_version="v2",
        created_at=T0,
    )

    restarted = HistoricalEvidenceStoreV2(tmp_path)
    second = restarted.finalize_manifest(
        dataset="xrp_spot_1h",
        schema_version="v2",
        created_at=T0,
    )
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.relative_path == second.relative_path


def test_as_of_preserves_provider_independence(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    coinbase = registered_observation(store, "coinbase")
    binance = registered_observation(store, "binance", provider="binance")
    store.save_observation(coinbase)
    store.save_observation(binance)

    selected = store.as_of(dataset="xrp_spot_1h", prediction_time=T0)
    assert {item.provider for item in selected} == {"coinbase", "binance"}


def test_reconstructed_history_is_opt_in(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(
        store,
        "historical",
        fetched_at=T0 + timedelta(days=30),
        reconstruction_basis_id="archive:vintage:2026-01-02",
    )
    store.save_observation(item)

    assert store.as_of(dataset="xrp_spot_1h", prediction_time=T0) == ()
    selected = store.as_of(
        dataset="xrp_spot_1h",
        prediction_time=T0,
        allow_reconstructed=True,
    )
    assert selected == (item,)
    assert item.eligibility_at(T0) is EligibilityClass.RECONSTRUCTED_PIT


def test_manifest_requires_durable_partition(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    with pytest.raises(ValueError, match="durable partition"):
        store.finalize_manifest(
            dataset="xrp_spot_1h",
            schema_version="v2",
            created_at=T0,
        )


def test_quick_check_passes_for_fresh_store(tmp_path: Path) -> None:
    assert HistoricalEvidenceStoreV2(tmp_path).quick_check()


def test_constructor_and_digest_validation_edges(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="busy_timeout"):
        HistoricalEvidenceStoreV2(tmp_path / "bad", busy_timeout_ms=0)

    store = HistoricalEvidenceStoreV2(tmp_path / "good")
    with pytest.raises(ValueError, match="SHA-256"):
        store.read_raw("not-a-digest")
    with pytest.raises(ValueError, match="cannot be empty"):
        store.put_raw(b"")
    with pytest.raises(KeyError):
        store.read_raw("0" * 64)
    with pytest.raises(ValueError, match="timezone-aware"):
        store.finalize_manifest(
            dataset="xrp_spot_1h",
            schema_version="v2",
            created_at=datetime(2026, 1, 2, 12, 0),
        )


def test_raw_existing_file_and_registry_corruption_are_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    blob = store.put_raw(RAW)
    path = tmp_path / blob.relative_path
    path.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="collision or corruption"):
        store.put_raw(RAW)

    path.write_bytes(RAW)
    with store._connection() as connection:
        connection.execute(
            "UPDATE raw_blobs SET byte_count=999 WHERE payload_sha256=?",
            (RAW_SHA,),
        )
    with pytest.raises(RuntimeError, match="registry collision"):
        store.put_raw(RAW)


def test_raw_read_success_and_observation_count(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    fetch = receipt()
    store.record_fetch(RAW, fetch)
    item = observation("one", fetch)
    store.save_observation(item)
    assert store.read_raw(RAW_SHA) == RAW
    assert store.observation_count() == 1


def test_atomic_write_failure_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.historical_store_v2 as module

    original_replace = module.os.replace

    def fail_replace(source: object, target: object) -> None:
        del source, target
        raise OSError("replace failed")

    monkeypatch.setattr(module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        HistoricalEvidenceStoreV2(tmp_path).put_raw(RAW)
    monkeypatch.setattr(module.os, "replace", original_replace)
    assert list((tmp_path / "raw").rglob("*.blob")) == []
    assert [path for path in (tmp_path / "raw").rglob(".*") if path.is_file()] == []


def test_record_fetch_is_idempotent(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    fetch = receipt()
    first = store.record_fetch(RAW, fetch)
    second = store.record_fetch(RAW, fetch)
    assert first == second
    assert store.fetch_receipt_count() == 1


def test_partition_rejects_empty_and_foreign_dataset(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    with pytest.raises(ValueError, match="at least one"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(),
        )
    item = registered_observation(store, "foreign")
    foreign = replace(item, dataset="other_dataset")
    with pytest.raises(ValueError, match="another dataset"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(foreign,),
        )


def test_existing_partition_and_registry_corruption_are_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    partition = store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(item,),
    )
    path = tmp_path / partition.relative_path
    original = path.read_bytes()
    path.write_bytes(b"corrupt\n")
    with pytest.raises(RuntimeError, match="partition integrity"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(item,),
        )

    path.write_bytes(original)
    with store._connection() as connection:
        connection.execute(
            "UPDATE partitions SET row_count=999 WHERE partition_id=?",
            (partition.partition_id,),
        )
    with pytest.raises(RuntimeError, match="registry collision"):
        store.write_partition(
            dataset="xrp_spot_1h",
            partition_key="date=2026-01-02",
            observations=(item,),
        )


def test_partition_row_count_verification_fails_closed(tmp_path: Path) -> None:
    from dataclasses import replace as dc_replace

    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    partition = store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(item,),
    )
    with pytest.raises(RuntimeError, match="row count"):
        store.verify_partition(dc_replace(partition, row_count=2))


def test_manifest_file_and_registry_collisions_are_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    store.write_partition(
        dataset="xrp_spot_1h",
        partition_key="date=2026-01-02",
        observations=(item,),
    )
    manifest = store.finalize_manifest(
        dataset="xrp_spot_1h",
        schema_version="v2",
        created_at=T0,
    )
    manifest_path = tmp_path / manifest.relative_path
    original = manifest_path.read_bytes()
    manifest_path.write_bytes(b"tampered\n")
    with pytest.raises(RuntimeError, match="manifest integrity"):
        store.finalize_manifest(
            dataset="xrp_spot_1h",
            schema_version="v2",
            created_at=T0,
        )

    manifest_path.write_bytes(original)
    with store._connection() as connection:
        connection.execute(
            "UPDATE manifests SET payload_json='{}' WHERE manifest_id=?",
            (manifest.manifest_id,),
        )
    with pytest.raises(RuntimeError, match="registry collision"):
        store.finalize_manifest(
            dataset="xrp_spot_1h",
            schema_version="v2",
            created_at=T0,
        )


def test_checkpoint_validation_and_corrupt_cursor_detection(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    with pytest.raises(ValueError, match="job_key"):
        store.save_checkpoint(
            job_key=" ",
            cursor={},
            completed=False,
            updated_at=T0,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        store.save_checkpoint(
            job_key="job",
            cursor={},
            completed=False,
            updated_at=datetime(2026, 1, 2, 12, 0),
        )

    store.save_checkpoint(
        job_key="job",
        cursor={"page": 1},
        completed=False,
        updated_at=T0,
    )
    with store._connection() as connection:
        connection.execute(
            "UPDATE checkpoints SET cursor_json='[]' WHERE job_key='job'"
        )
    with pytest.raises(RuntimeError, match="cursor must be an object"):
        store.load_checkpoint("job")


def test_corrupt_stored_observation_shape_is_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    store.save_observation(item)
    with store._connection() as connection:
        connection.execute(
            "UPDATE observations SET payload_json='[]' WHERE observation_id='a'"
        )
    with pytest.raises(RuntimeError, match="root must be an object"):
        store.load_observations("xrp_spot_1h")


def test_corrupt_stored_observation_values_are_detected(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    item = registered_observation(store, "a")
    store.save_observation(item)
    with store._connection() as connection:
        row = connection.execute(
            "SELECT payload_json FROM observations WHERE observation_id='a'"
        ).fetchone()
        payload = __import__("json").loads(str(row["payload_json"]))
        payload["values"] = []
        connection.execute(
            "UPDATE observations SET payload_json=? WHERE observation_id='a'",
            (__import__("json").dumps(payload, separators=(",", ":")),),
        )
    with pytest.raises(RuntimeError, match="values must be an object"):
        store.load_observations("xrp_spot_1h")


def test_date_only_observation_round_trip(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    fetch = receipt(provider="fred", fetched_at=T0 + timedelta(days=1))
    store.record_fetch(RAW, fetch)
    item = HistoricalObservation(
        observation_id="date-only",
        dataset="macro",
        record_id="series:2026-01-02",
        provider="fred",
        source_id=fetch.source_id,
        symbol="DGS10",
        instrument="macro",
        observed_at=T0 - timedelta(days=1),
        fetched_at=fetch.fetched_at,
        fetch_id=fetch.fetch_id,
        payload_sha256=fetch.payload_sha256,
        values={"value": 4.2},
        availability_precision=AvailabilityPrecision.DATE_ONLY,
        availability_policy="fred_vintage_date",
        available_date=date(2026, 1, 2),
        revision_sequence=0,
        reconstruction_basis_id="alfred:vintage:2026-01-02",
    )
    store.save_observation(item)
    loaded = store.load_observations("macro")
    assert loaded == (item,)


def test_atomic_write_without_directory_fsync_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import xrp_regime_engine.historical_store_v2 as module

    monkeypatch.delattr(module.os, "O_DIRECTORY", raising=False)
    store = HistoricalEvidenceStoreV2(tmp_path)
    blob = store.put_raw(RAW)
    assert store.read_raw(blob.payload_sha256) == RAW
