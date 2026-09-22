from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from xrp_regime_engine.dataset_version_v1 import build_dataset_version
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
REQUEST_SHA = sha256(b"h7-manifest-gauntlet").hexdigest()


def _material(
    label: str,
    *,
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
        dataset="xrp_spot_1h",
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
    dataset = "xrp_spot_1h"
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
    ) -> None:
        self.label = label
        self.observed_at = observed_at
        self.fetched_at = fetched_at
        self.partition_key = partition_key
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
    return BackfillWindowV2(
        start=start,
        end=end,
        interval_seconds=3600,
    )


def test_two_disjoint_jobs_same_dataset_must_not_cross_contaminate_manifests(
    tmp_path: Path,
) -> None:
    """F5: each scientific manifest must contain only partitions owned by its job."""

    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)

    adapter_a = SinglePageAdapter(
        label="a",
        observed_at=T0 - timedelta(minutes=90),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=10",
    )
    adapter_b = SinglePageAdapter(
        label="b",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=2),
        partition_key="date=2026-01-02-hour=11",
    )
    result_a = runner.run(
        adapter_a,
        _window(T0 - timedelta(hours=2), T0 - timedelta(hours=1)),
    )
    result_b = runner.run(
        adapter_b,
        _window(T0 - timedelta(hours=1), T0),
    )

    assert result_a.manifest is not None
    assert result_b.manifest is not None
    assert len(result_a.manifest.partition_ids) == 1
    assert len(result_b.manifest.partition_ids) == 1
    assert set(result_a.manifest.partition_ids).isdisjoint(result_b.manifest.partition_ids)


def test_completed_job_manifest_identity_must_be_stable_after_unrelated_same_dataset_job(
    tmp_path: Path,
) -> None:
    """F5: resuming a completed job cannot sweep later same-dataset partitions."""

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
    original_manifest_id = first.manifest.manifest_id
    original_partition_ids = first.manifest.partition_ids

    adapter_b = SinglePageAdapter(
        label="unrelated-b",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=2),
        partition_key="date=2026-01-02-hour=11",
    )
    runner.run(
        adapter_b,
        _window(T0 - timedelta(hours=1), T0),
    )

    resumed_adapter_a = SinglePageAdapter(
        label="stable-a",
        observed_at=T0 - timedelta(minutes=90),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=10",
    )
    resumed = runner.run(resumed_adapter_a, window_a)

    assert resumed.resumed is True
    assert resumed_adapter_a.fetch_calls == 0
    assert resumed.manifest is not None
    assert resumed.manifest.manifest_id == original_manifest_id
    assert resumed.manifest.partition_ids == original_partition_ids


def test_dataset_version_rejects_forged_manifest_identity(
    tmp_path: Path,
) -> None:
    """F6: DatasetVersion must not trust a syntactically valid forged manifest ID/hash."""

    store = HistoricalEvidenceStoreV2(tmp_path)
    runner = BackfillRunnerV2(store)
    adapter = SinglePageAdapter(
        label="forged-manifest-source",
        observed_at=T0 - timedelta(minutes=30),
        fetched_at=T0 + timedelta(minutes=1),
        partition_key="date=2026-01-02-hour=11",
    )
    result = runner.run(
        adapter,
        _window(T0 - timedelta(hours=1), T0),
    )
    assert result.manifest is not None

    forged_digest = sha256(b"not-the-canonical-manifest-payload").hexdigest()
    forged_manifest = replace(
        result.manifest,
        manifest_id=f"manifest:sha256:{forged_digest}",
        manifest_sha256=forged_digest,
    )
    partitions = store.list_partitions(adapter.dataset)
    observations = store.load_observations(adapter.dataset)

    with pytest.raises(ValueError, match="manifest"):
        build_dataset_version(
            dataset_key=adapter.dataset,
            schema_version=adapter.schema_version,
            manifests=(forged_manifest,),
            partitions=partitions,
            observations=observations,
            feature_schema_version="feature-v1",
            label_schema_version="label-v1",
            created_at=T0 + timedelta(hours=2),
            cutoff_at=T0 + timedelta(hours=1),
            allow_reconstructed=False,
        )
