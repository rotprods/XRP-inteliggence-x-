from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.dataset_version_v1 import DatasetVersion, ProviderCoverage, build_dataset_version
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import DurableManifest, DurablePartition

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
DATASET_SHA = sha256(b"dataset").hexdigest()
MANIFEST_SHA = sha256(b"manifest").hexdigest()
PARTITION_SHA = sha256(b"partition").hexdigest()
OTHER_PARTITION_SHA = sha256(b"other-partition").hexdigest()
PAYLOAD_SHA = sha256(b"payload").hexdigest()
REQUEST_SHA = sha256(b"request").hexdigest()


def coverage() -> ProviderCoverage:
    return ProviderCoverage(
        provider="coinbase",
        observation_count=1,
        minimum_observed_at=T0 - timedelta(hours=1),
        maximum_observed_at=T0 - timedelta(hours=1),
        minimum_fetched_at=T0 - timedelta(minutes=30),
        maximum_fetched_at=T0 - timedelta(minutes=30),
    )


def version() -> DatasetVersion:
    return DatasetVersion(
        dataset_version_id=f"dataset-version:sha256:{DATASET_SHA}",
        dataset_sha256=DATASET_SHA,
        dataset_key="xrp-research-1h",
        schema_version="1",
        source_manifest_ids=(f"manifest:sha256:{MANIFEST_SHA}",),
        source_manifest_hashes=(MANIFEST_SHA,),
        partition_ids=(f"partition:sha256:{PARTITION_SHA}",),
        partition_hashes=(PARTITION_SHA,),
        feature_schema_version="features-v1",
        label_schema_version="labels-v1",
        created_at=T0 + timedelta(minutes=1),
        cutoff_at=T0,
        total_rows=1,
        strict_replay_fraction=1.0,
        reconstructed_pit_fraction=0.0,
        provider_coverage=(coverage(),),
        gaps=(),
    )


def observation() -> HistoricalObservation:
    fetched_at = T0 - timedelta(minutes=30)
    receipt = FetchReceipt.create(
        source_id="source:coinbase",
        provider="coinbase",
        canonical_uri="https://example.com/coinbase",
        endpoint="/market",
        request_fingerprint=REQUEST_SHA,
        fetched_at=fetched_at,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version="2",
        parser_version="2",
    )
    return HistoricalObservation(
        observation_id="obs:a",
        dataset="xrp_spot_1h",
        record_id="2026-01-02T11:00:00Z",
        provider="coinbase",
        source_id="source:coinbase",
        symbol="XRP_USD",
        instrument="spot",
        observed_at=T0 - timedelta(hours=1),
        fetched_at=fetched_at,
        fetch_id=receipt.fetch_id,
        payload_sha256=PAYLOAD_SHA,
        values={"close": 1.5},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="provider_exact",
        available_at=T0 - timedelta(minutes=45),
    )


def partition(digest: str = PARTITION_SHA) -> DurablePartition:
    return DurablePartition(
        partition_id=f"partition:sha256:{digest}",
        dataset="xrp_spot_1h",
        partition_key=f"part={digest[:8]}",
        relative_path=f"normalized/xrp_spot_1h/{digest}.jsonl",
        file_sha256=digest,
        row_count=1,
        minimum_observed_at=T0 - timedelta(hours=1),
        maximum_observed_at=T0 - timedelta(hours=1),
        minimum_fetched_at=T0 - timedelta(minutes=30),
        maximum_fetched_at=T0 - timedelta(minutes=30),
    )


def manifest(*partition_ids: str) -> DurableManifest:
    return DurableManifest(
        manifest_id=f"manifest:sha256:{MANIFEST_SHA}",
        manifest_sha256=MANIFEST_SHA,
        dataset="xrp_spot_1h",
        schema_version="1",
        created_at=T0 + timedelta(minutes=1),
        partition_ids=partition_ids,
        total_rows=len(partition_ids),
        relative_path=f"manifests/xrp_spot_1h/1/{MANIFEST_SHA}.json",
    )


def test_low_level_value_guards_fail_closed() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(version(), created_at=T0.replace(tzinfo=None))
    with pytest.raises(ValueError, match="dataset_key is required"):
        replace(version(), dataset_key=" ")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        replace(version(), dataset_sha256="BAD")
    with pytest.raises(ValueError, match="fetched-at range"):
        ProviderCoverage(
            provider="coinbase",
            observation_count=1,
            minimum_observed_at=T0,
            maximum_observed_at=T0,
            minimum_fetched_at=T0,
            maximum_fetched_at=T0 - timedelta(seconds=1),
        )


def test_direct_version_structural_guards_fail_closed() -> None:
    current = version()
    with pytest.raises(ValueError, match="created_at cannot precede"):
        replace(current, created_at=T0 - timedelta(seconds=1))
    with pytest.raises(ValueError, match="total_rows must be positive"):
        replace(current, total_rows=0)
    with pytest.raises(ValueError, match="requires manifests"):
        replace(current, source_manifest_ids=())
    with pytest.raises(ValueError, match="manifest ids and hashes"):
        replace(current, source_manifest_hashes=())
    with pytest.raises(ValueError, match="partition ids and hashes"):
        replace(current, partition_hashes=())
    with pytest.raises(ValueError, match="source_manifest_ids must be unique"):
        replace(
            current,
            source_manifest_ids=(current.source_manifest_ids[0], current.source_manifest_ids[0]),
            source_manifest_hashes=(MANIFEST_SHA, MANIFEST_SHA),
        )
    with pytest.raises(ValueError, match="partition_ids must be unique"):
        replace(
            current,
            partition_ids=(current.partition_ids[0], current.partition_ids[0]),
            partition_hashes=(PARTITION_SHA, PARTITION_SHA),
        )
    with pytest.raises(ValueError, match="within \[0, 1\]"):
        replace(current, strict_replay_fraction=1.1, reconstructed_pit_fraction=-0.1)


def test_manifest_internal_duplicate_partition_ids_fail_closed() -> None:
    partition_id = f"partition:sha256:{PARTITION_SHA}"
    duplicate_manifest = manifest(partition_id, partition_id)
    with pytest.raises(ValueError, match="duplicate partition ids"):
        build_dataset_version(
            dataset_key="xrp-research-1h",
            schema_version="1",
            manifests=(duplicate_manifest,),
            partitions=(partition(),),
            observations=(observation(),),
            feature_schema_version="features-v1",
            label_schema_version="labels-v1",
            created_at=T0 + timedelta(minutes=1),
            cutoff_at=T0,
        )


def test_unreferenced_supplied_partition_fails_closed() -> None:
    primary = partition()
    extra = partition(OTHER_PARTITION_SHA)
    source_manifest = manifest(primary.partition_id)
    with pytest.raises(ValueError, match="exactly match manifest references"):
        build_dataset_version(
            dataset_key="xrp-research-1h",
            schema_version="1",
            manifests=(source_manifest,),
            partitions=(primary, extra),
            observations=(observation(),),
            feature_schema_version="features-v1",
            label_schema_version="labels-v1",
            created_at=T0 + timedelta(minutes=1),
            cutoff_at=T0,
        )


def test_expected_interval_without_gap_exercises_non_gap_path() -> None:
    row = observation()
    source_manifest = manifest(f"partition:sha256:{PARTITION_SHA}")
    result = build_dataset_version(
        dataset_key="xrp-research-1h",
        schema_version="1",
        manifests=(source_manifest,),
        partitions=(partition(),),
        observations=(row,),
        feature_schema_version="features-v1",
        label_schema_version="labels-v1",
        created_at=T0 + timedelta(minutes=1),
        cutoff_at=T0,
        expected_interval=timedelta(hours=1),
    )
    assert result.gaps == ()
