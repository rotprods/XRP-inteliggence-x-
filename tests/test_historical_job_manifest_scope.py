from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from xrp_regime_engine.historical_backfill_v2 import (
    BackfillPageV2,
    BackfillRunnerV2,
    BackfillWindowV2,
)
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import HistoricalEvidenceStoreV2

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
REQUEST_SHA = sha256(b"job-manifest-scope").hexdigest()


def _material(
    label: str,
    *,
    dataset: str,
    observed_at: datetime,
    fetched_at: datetime,
) -> tuple[bytes, FetchReceipt, HistoricalObservation]:
    raw = f'{{"page":"{label}"}}'.encode()
    payload_sha = sha256(raw).hexdigest()
    receipt = FetchReceipt.create(
        source_id="source:coinbase",
        provider="coinbase",
        canonical_uri=f"https://example.com/coinbase/{label}",
        endpoint="/history",
        request_fingerprint=REQUEST_SHA,
        fetched_at=fetched_at,
        payload_sha256=payload_sha,
        ingestion_version="2",
        parser_version="2",
    )
    observation = HistoricalObservation(
        observation_id=f"obs:{label}",
        dataset=dataset,
        record_id=f"record:{label}",
        provider="coinbase",
        source_id=receipt.source_id,
        symbol="XRP_USD",
        instrument="spot",
        observed_at=observed_at,
        fetched_at=fetched_at,
        fetch_id=receipt.fetch_id,
        payload_sha256=payload_sha,
        values={"close": 2.0},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="provider_exact",
        available_at=observed_at,
    )
    return raw, receipt, observation


class SinglePageAdapter:
    provider = "coinbase"
    schema_version = "historical-observation-v2"
    ingestion_version = "2"
    parser_version = "2"

    def __init__(
        self,
        *,
        label: str,
        observed_at: datetime,
        fetched_at: datetime,
        partition_key: str,
        dataset: str = "xrp_spot_1h",
    ) -> None:
        self.label = label
        self.observed_at = observed_at
        self.fetched_at = fetched_at
        self.partition_key = partition_key
        self.dataset = dataset
        self.fetch_calls = 0

    def initial_cursor(self, window: BackfillWindowV2) -> dict[str, object]:
        del window
        return {"page": self.label}

    def fetch_page(
        self,
        window: BackfillWindowV2,
        cursor: dict[str, object],
    ) -> BackfillPageV2:
        del window, cursor
        self.fetch_calls += 1
        raw, receipt, observation = _material(
            self.label,
            dataset=self.dataset,
            observed_at=self.observed_at,
            fetched_at=self.fetched_at,
        )
        return BackfillPageV2(
            raw_payload=raw,
            receipt=receipt,
            observations=(observation,),
            partition_key=self.partition_key,
            next_cursor=None,
            completed=True,
        )


def _window(start: datetime, end: datetime) -> BackfillWindowV2:
    return BackfillWindowV2(start=start, end=end, interval_seconds=3600)


def test_two_jobs_same_dataset_finalize_only_owned_partitions(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)

    adapter_a = SinglePageAdapter(
        label="a",
        observed_at=T0 - timedelta(minutes=90),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=10",
    )
    window_a = _window(T0 - timedelta(hours=2), T0 - timedelta(hours=1))
    result_a = runner.run(adapter_a, window_a)

    adapter_b = SinglePageAdapter(
        label="b",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=2),
        partition_key="date=2026-01-02-hour=11",
    )
    window_b = _window(T0 - timedelta(hours=1), T0)
    result_b = runner.run(adapter_b, window_b)

    assert result_a.manifest is not None
    assert result_b.manifest is not None
    assert result_a.manifest.job_key == result_a.job_key
    assert result_b.manifest.job_key == result_b.job_key
    assert len(result_a.manifest.partition_ids) == 1
    assert len(result_b.manifest.partition_ids) == 1
    assert set(result_a.manifest.partition_ids).isdisjoint(result_b.manifest.partition_ids)


def test_completed_job_manifest_is_stable_after_unrelated_same_dataset_job(
    tmp_path: Path,
) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)
    window_a = _window(T0 - timedelta(hours=2), T0 - timedelta(hours=1))

    adapter_a = SinglePageAdapter(
        label="stable-a",
        observed_at=T0 - timedelta(minutes=90),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=10",
    )
    first = runner.run(adapter_a, window_a)
    assert first.manifest is not None

    runner.run(
        SinglePageAdapter(
            label="unrelated-b",
            observed_at=T0 - timedelta(minutes=30),
            fetched_at=T0 + timedelta(minutes=2),
            partition_key="date=2026-01-02-hour=11",
        ),
        _window(T0 - timedelta(hours=1), T0),
    )

    resumed_adapter = SinglePageAdapter(
        label="stable-a",
        observed_at=T0 - timedelta(minutes=90),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=10",
    )
    resumed = runner.run(resumed_adapter, window_a)

    assert resumed.resumed is True
    assert resumed_adapter.fetch_calls == 0
    assert resumed.manifest is not None
    assert resumed.manifest.manifest_id == first.manifest.manifest_id
    assert resumed.manifest.partition_ids == first.manifest.partition_ids


def test_completed_checkpoint_without_membership_fails_closed(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)
    window = _window(T0 - timedelta(hours=1), T0)
    adapter = SinglePageAdapter(
        label="membership",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=11",
    )
    result = runner.run(adapter, window)

    with sqlite3.connect(store.database_path) as connection:
        connection.execute("DELETE FROM job_partitions WHERE job_key=?", (result.job_key,))

    resumed_adapter = SinglePageAdapter(
        label="membership",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=11",
    )
    with pytest.raises(ValueError, match="job manifest requires"):
        runner.run(resumed_adapter, window)
    assert resumed_adapter.fetch_calls == 0


def test_job_manifest_revalidates_partition_file_on_resume(tmp_path: Path) -> None:
    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)
    window = _window(T0 - timedelta(hours=1), T0)
    adapter = SinglePageAdapter(
        label="corrupt",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=11",
    )
    result = runner.run(adapter, window)
    assert result.manifest is not None
    partition = store.list_job_partitions(job_key=result.job_key, dataset=adapter.dataset)[0]
    (store.root / partition.relative_path).write_bytes(b"corrupt\n")

    with pytest.raises(RuntimeError, match="SHA-256"):
        runner.run(
            SinglePageAdapter(
                label="corrupt",
                observed_at=T0 - timedelta(minutes=30),
                fetched_at=T0 + timedelta(minutes=1),
                partition_key="date=2026-01-02-hour=11",
            ),
            window,
        )


def test_v1_catalog_migrates_additively_without_synthesizing_membership(
    tmp_path: Path,
) -> None:
    database = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO store_metadata(key, value) VALUES ('schema_version', '1')"
        )

    store = HistoricalEvidenceStoreV2(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        version = connection.execute(
            "SELECT value FROM store_metadata WHERE key='schema_version'"
        ).fetchone()
        membership_count = connection.execute("SELECT COUNT(*) FROM job_partitions").fetchone()

    assert version == ("2",)
    assert membership_count == (0,)


def test_unknown_catalog_schema_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE store_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO store_metadata(key, value) VALUES ('schema_version', '99')"
        )

    with pytest.raises(RuntimeError, match="unsupported historical store schema_version"):
        HistoricalEvidenceStoreV2(tmp_path)
