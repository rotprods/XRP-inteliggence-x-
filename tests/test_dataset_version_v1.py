from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from xrp_regime_engine.dataset_version_v1 import (
    DatasetGap,
    DatasetVersion,
    ProviderCoverage,
    build_dataset_version,
)
from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
)
from xrp_regime_engine.historical_store_v2 import DurableManifest, DurablePartition

T0 = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
REQUEST_SHA = sha256(b"request").hexdigest()
PAYLOAD_SHA = sha256(b"payload").hexdigest()
PARTITION_SHA = sha256(b"partition").hexdigest()
MANIFEST_SHA = sha256(b"manifest").hexdigest()


def receipt(provider: str, fetched_at: datetime) -> FetchReceipt:
    return FetchReceipt.create(
        source_id=f"source:{provider}",
        provider=provider,
        canonical_uri=f"https://example.com/{provider}",
        endpoint="/market",
        request_fingerprint=REQUEST_SHA,
        fetched_at=fetched_at,
        payload_sha256=PAYLOAD_SHA,
        ingestion_version="2",
        parser_version="2",
    )


def observation(
    observation_id: str,
    *,
    provider: str = "coinbase",
    observed_at: datetime = T0 - timedelta(hours=2),
    available_at: datetime = T0 - timedelta(hours=1),
    fetched_at: datetime = T0 - timedelta(minutes=30),
    reconstructed: bool = False,
) -> HistoricalObservation:
    fetch = receipt(provider, fetched_at)
    return HistoricalObservation(
        observation_id=observation_id,
        dataset="xrp_spot_1h",
        record_id=observed_at.isoformat(),
        provider=provider,
        source_id=f"source:{provider}",
        symbol="XRP_USD",
        instrument="spot",
        observed_at=observed_at,
        fetched_at=fetched_at,
        fetch_id=fetch.fetch_id,
        payload_sha256=PAYLOAD_SHA,
        values={"close": 1.5},
        availability_precision=AvailabilityPrecision.EXACT,
        availability_policy="provider_exact",
        available_at=available_at,
        reconstruction_basis_id="archive:v1" if reconstructed else None,
    )


def partition(*, row_count: int = 2) -> DurablePartition:
    return DurablePartition(
        partition_id=f"partition:sha256:{PARTITION_SHA}",
        dataset="xrp_spot_1h",
        partition_key="provider=multi_date=2026-01-02",
        relative_path=f"normalized/xrp_spot_1h/part-{PARTITION_SHA}.jsonl",
        file_sha256=PARTITION_SHA,
        row_count=row_count,
        minimum_observed_at=T0 - timedelta(hours=2),
        maximum_observed_at=T0 - timedelta(hours=1),
        minimum_fetched_at=T0 - timedelta(minutes=30),
        maximum_fetched_at=T0 - timedelta(minutes=20),
    )


def manifest(*, row_count: int = 2, partition_id: str | None = None) -> DurableManifest:
    pid = partition_id or f"partition:sha256:{PARTITION_SHA}"
    return DurableManifest(
        manifest_id=f"manifest:sha256:{MANIFEST_SHA}",
        manifest_sha256=MANIFEST_SHA,
        dataset="xrp_spot_1h",
        schema_version="1",
        created_at=T0 + timedelta(minutes=1),
        partition_ids=(pid,),
        total_rows=row_count,
        relative_path=f"manifests/xrp_spot_1h/1/{MANIFEST_SHA}.json",
    )


def build(**overrides: object) -> DatasetVersion:
    kwargs: dict[str, object] = {
        "dataset_key": "xrp-research-1h",
        "schema_version": "1",
        "manifests": (manifest(),),
        "partitions": (partition(),),
        "observations": (
            observation("a", provider="coinbase"),
            observation(
                "b",
                provider="kraken",
                observed_at=T0 - timedelta(hours=1),
                available_at=T0 - timedelta(minutes=45),
                fetched_at=T0 - timedelta(minutes=20),
            ),
        ),
        "feature_schema_version": "features-v1",
        "label_schema_version": "labels-v1",
        "created_at": T0 + timedelta(minutes=1),
        "cutoff_at": T0,
    }
    kwargs.update(overrides)
    return build_dataset_version(**kwargs)  # type: ignore[arg-type]


def test_dataset_version_is_deterministic_and_order_independent() -> None:
    left = build()
    observations = tuple(reversed(build.__globals__["build"].__defaults__ or ()))
    del observations
    right = build(
        observations=(
            observation(
                "b",
                provider="kraken",
                observed_at=T0 - timedelta(hours=1),
                available_at=T0 - timedelta(minutes=45),
                fetched_at=T0 - timedelta(minutes=20),
            ),
            observation("a", provider="coinbase"),
        )
    )
    assert left.dataset_version_id == right.dataset_version_id
    assert left.dataset_sha256 == right.dataset_sha256
    assert tuple(item.provider for item in left.provider_coverage) == ("coinbase", "kraken")
    assert left.strict_replay_fraction == 1.0
    assert left.reconstructed_pit_fraction == 0.0
    assert not left.reconstructed


def test_future_evidence_fails_closed() -> None:
    future = observation(
        "future",
        provider="kraken",
        available_at=T0 + timedelta(minutes=1),
        fetched_at=T0 + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="unavailable at cutoff"):
        build(observations=(observation("a"), future))


def test_reconstructed_pit_requires_explicit_opt_in() -> None:
    reconstructed = observation(
        "r",
        provider="kraken",
        fetched_at=T0 + timedelta(days=1),
        reconstructed=True,
    )
    with pytest.raises(ValueError, match="explicit opt-in"):
        build(observations=(observation("a"), reconstructed))
    version = build(
        observations=(observation("a"), reconstructed),
        allow_reconstructed=True,
    )
    assert version.reconstructed
    assert version.strict_replay_fraction == 0.5
    assert version.reconstructed_pit_fraction == 0.5


def test_manifest_partition_reference_must_be_exact() -> None:
    other_sha = sha256(b"other-partition").hexdigest()
    with pytest.raises(ValueError, match="not supplied"):
        build(manifests=(manifest(partition_id=f"partition:sha256:{other_sha}"),))


def test_manifest_dataset_and_row_count_must_match() -> None:
    with pytest.raises(ValueError, match="another dataset"):
        build(manifests=(replace(manifest(), dataset="btc_spot_1h"),))
    with pytest.raises(ValueError, match="total_rows"):
        build(manifests=(manifest(row_count=3),))


def test_observation_count_must_match_partition_rows() -> None:
    with pytest.raises(ValueError, match="observation count"):
        build(partitions=(partition(row_count=3),), manifests=(manifest(row_count=3),))


def test_duplicate_identities_fail_closed() -> None:
    with pytest.raises(ValueError, match="manifest ids must be unique"):
        build(manifests=(manifest(), manifest()))
    with pytest.raises(ValueError, match="partition ids must be unique"):
        build(partitions=(partition(row_count=1), partition(row_count=1)))
    item = observation("duplicate")
    with pytest.raises(ValueError, match="observation ids must be unique"):
        build(observations=(item, item))


def test_gap_detection_is_provider_specific() -> None:
    rows = (
        observation(
            "a",
            provider="coinbase",
            observed_at=T0 - timedelta(hours=4),
            available_at=T0 - timedelta(hours=3, minutes=30),
            fetched_at=T0 - timedelta(hours=3),
        ),
        observation(
            "b",
            provider="coinbase",
            observed_at=T0 - timedelta(hours=1),
            available_at=T0 - timedelta(minutes=45),
            fetched_at=T0 - timedelta(minutes=30),
        ),
    )
    version = build(observations=rows, expected_interval=timedelta(hours=1))
    assert version.gaps == (
        DatasetGap(
            provider="coinbase",
            starts_at=T0 - timedelta(hours=3),
            ends_at=T0 - timedelta(hours=1),
            expected_interval_seconds=3600,
        ),
    )


def test_invalid_expected_interval_fails_closed() -> None:
    with pytest.raises(ValueError, match="positive"):
        build(expected_interval=timedelta(0))
    with pytest.raises(ValueError, match="whole positive seconds"):
        build(expected_interval=timedelta(microseconds=1))


def test_created_at_cannot_precede_cutoff() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        build(created_at=T0 - timedelta(seconds=1))


def test_dataset_version_requires_all_surfaces() -> None:
    with pytest.raises(ValueError, match="requires manifests"):
        build(manifests=())
    with pytest.raises(ValueError, match="requires manifests"):
        build(partitions=())
    with pytest.raises(ValueError, match="requires manifests"):
        build(observations=())


def test_provider_coverage_validates_ranges() -> None:
    with pytest.raises(ValueError, match="positive"):
        ProviderCoverage(
            provider="coinbase",
            observation_count=0,
            minimum_observed_at=T0,
            maximum_observed_at=T0,
            minimum_fetched_at=T0,
            maximum_fetched_at=T0,
        )
    with pytest.raises(ValueError, match="observed-at range"):
        ProviderCoverage(
            provider="coinbase",
            observation_count=1,
            minimum_observed_at=T0,
            maximum_observed_at=T0 - timedelta(seconds=1),
            minimum_fetched_at=T0,
            maximum_fetched_at=T0,
        )


def test_dataset_gap_validates_interval_and_range() -> None:
    with pytest.raises(ValueError, match="after"):
        DatasetGap(
            provider="coinbase",
            starts_at=T0,
            ends_at=T0,
            expected_interval_seconds=60,
        )
    with pytest.raises(ValueError, match="positive"):
        DatasetGap(
            provider="coinbase",
            starts_at=T0,
            ends_at=T0 + timedelta(minutes=1),
            expected_interval_seconds=0,
        )


def test_direct_dataset_version_rejects_corrupt_identity() -> None:
    version = build()
    with pytest.raises(ValueError, match="dataset_version_id"):
        replace(version, dataset_version_id="bad")
    with pytest.raises(ValueError, match="sum to one"):
        replace(version, strict_replay_fraction=0.5)
    with pytest.raises(ValueError, match="unique and sorted"):
        replace(version, provider_coverage=tuple(reversed(version.provider_coverage)))


def test_serialized_version_exposes_no_execution_authority() -> None:
    payload = build().to_dict()
    assert payload["dataset_key"] == "xrp-research-1h"
    assert "signal" not in payload
    assert "position" not in payload
    assert "order" not in payload
