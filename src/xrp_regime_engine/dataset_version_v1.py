from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from xrp_regime_engine.historical_contract import EligibilityClass, HistoricalObservation
from xrp_regime_engine.historical_store_v2 import DurableManifest, DurablePartition


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _content_id(value: str, prefix: str, field: str) -> str:
    if not value.startswith(prefix):
        raise ValueError(f"{field} must use {prefix}<digest>")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{field} must contain a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class ProviderCoverage:
    provider: str
    observation_count: int
    minimum_observed_at: datetime
    maximum_observed_at: datetime
    minimum_fetched_at: datetime
    maximum_fetched_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        if self.observation_count < 1:
            raise ValueError("observation_count must be positive")
        for field in (
            "minimum_observed_at",
            "maximum_observed_at",
            "minimum_fetched_at",
            "maximum_fetched_at",
        ):
            object.__setattr__(self, field, _utc(getattr(self, field), field))
        if self.minimum_observed_at > self.maximum_observed_at:
            raise ValueError("provider observed-at range is inverted")
        if self.minimum_fetched_at > self.maximum_fetched_at:
            raise ValueError("provider fetched-at range is inverted")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "observation_count": self.observation_count,
            "minimum_observed_at": self.minimum_observed_at.isoformat(),
            "maximum_observed_at": self.maximum_observed_at.isoformat(),
            "minimum_fetched_at": self.minimum_fetched_at.isoformat(),
            "maximum_fetched_at": self.maximum_fetched_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DatasetGap:
    provider: str
    starts_at: datetime
    ends_at: datetime
    expected_interval_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _text(self.provider, "provider"))
        object.__setattr__(self, "starts_at", _utc(self.starts_at, "starts_at"))
        object.__setattr__(self, "ends_at", _utc(self.ends_at, "ends_at"))
        if self.ends_at <= self.starts_at:
            raise ValueError("gap ends_at must be after starts_at")
        if self.expected_interval_seconds < 1:
            raise ValueError("expected_interval_seconds must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "expected_interval_seconds": self.expected_interval_seconds,
        }


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    dataset_version_id: str
    dataset_sha256: str
    dataset_key: str
    schema_version: str
    source_manifest_ids: tuple[str, ...]
    source_manifest_hashes: tuple[str, ...]
    partition_ids: tuple[str, ...]
    partition_hashes: tuple[str, ...]
    feature_schema_version: str
    label_schema_version: str
    created_at: datetime
    cutoff_at: datetime
    total_rows: int
    strict_replay_fraction: float
    reconstructed_pit_fraction: float
    provider_coverage: tuple[ProviderCoverage, ...]
    gaps: tuple[DatasetGap, ...]

    def __post_init__(self) -> None:
        _content_id(self.dataset_version_id, "dataset-version:sha256:", "dataset_version_id")
        _content_id(
            f"dataset-version:sha256:{self.dataset_sha256}",
            "dataset-version:sha256:",
            "dataset_sha256",
        )
        object.__setattr__(self, "dataset_key", _text(self.dataset_key, "dataset_key"))
        object.__setattr__(self, "schema_version", _text(self.schema_version, "schema_version"))
        object.__setattr__(
            self,
            "feature_schema_version",
            _text(self.feature_schema_version, "feature_schema_version"),
        )
        object.__setattr__(
            self, "label_schema_version", _text(self.label_schema_version, "label_schema_version")
        )
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        object.__setattr__(self, "cutoff_at", _utc(self.cutoff_at, "cutoff_at"))
        if self.created_at < self.cutoff_at:
            raise ValueError("created_at cannot precede cutoff_at")
        if self.total_rows < 1:
            raise ValueError("total_rows must be positive")
        if not self.source_manifest_ids or not self.partition_ids or not self.provider_coverage:
            raise ValueError("dataset version requires manifests, partitions and provider coverage")
        if len(self.source_manifest_ids) != len(self.source_manifest_hashes):
            raise ValueError("manifest ids and hashes must have equal length")
        if len(self.partition_ids) != len(self.partition_hashes):
            raise ValueError("partition ids and hashes must have equal length")
        if len(self.source_manifest_ids) != len(set(self.source_manifest_ids)):
            raise ValueError("source_manifest_ids must be unique")
        if len(self.partition_ids) != len(set(self.partition_ids)):
            raise ValueError("partition_ids must be unique")
        if self.source_manifest_ids != tuple(sorted(self.source_manifest_ids)):
            raise ValueError("source_manifest_ids must be sorted")
        if self.partition_ids != tuple(sorted(self.partition_ids)):
            raise ValueError("partition_ids must be sorted")
        for manifest_id in self.source_manifest_ids:
            _content_id(manifest_id, "manifest:sha256:", "manifest_id")
        for partition_id in self.partition_ids:
            _content_id(partition_id, "partition:sha256:", "partition_id")
        for digest in (*self.source_manifest_hashes, *self.partition_hashes):
            _content_id(f"sha256:{digest}", "sha256:", "content hash")
        for fraction in (self.strict_replay_fraction, self.reconstructed_pit_fraction):
            if not 0.0 <= fraction <= 1.0:
                raise ValueError("eligibility fractions must be within [0, 1]")
        if abs(self.strict_replay_fraction + self.reconstructed_pit_fraction - 1.0) > 1e-12:
            raise ValueError("eligibility fractions must sum to one")
        providers = tuple(item.provider for item in self.provider_coverage)
        if providers != tuple(sorted(providers)) or len(providers) != len(set(providers)):
            raise ValueError("provider_coverage must be unique and sorted by provider")
        if self.dataset_version_id != f"dataset-version:sha256:{self.dataset_sha256}":
            raise ValueError("dataset_version_id must match dataset_sha256")
        material = {
            "dataset_key": self.dataset_key,
            "schema_version": self.schema_version,
            "source_manifests": [
                {"id": manifest_id, "sha256": manifest_hash}
                for manifest_id, manifest_hash in zip(
                    self.source_manifest_ids, self.source_manifest_hashes, strict=True
                )
            ],
            "partitions": [
                {"id": partition_id, "sha256": partition_hash}
                for partition_id, partition_hash in zip(
                    self.partition_ids, self.partition_hashes, strict=True
                )
            ],
            "feature_schema_version": self.feature_schema_version,
            "label_schema_version": self.label_schema_version,
            "created_at": self.created_at.isoformat(),
            "cutoff_at": self.cutoff_at.isoformat(),
            "total_rows": self.total_rows,
            "strict_replay_fraction": self.strict_replay_fraction,
            "reconstructed_pit_fraction": self.reconstructed_pit_fraction,
            "provider_coverage": [item.to_dict() for item in self.provider_coverage],
            "gaps": [item.to_dict() for item in self.gaps],
        }
        expected_digest = sha256(_canonical(material)).hexdigest()
        if self.dataset_sha256 != expected_digest:
            raise ValueError("dataset content-addressed identity does not match canonical payload")

    @property
    def reconstructed(self) -> bool:
        return self.reconstructed_pit_fraction > 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset_version_id": self.dataset_version_id,
            "dataset_sha256": self.dataset_sha256,
            "dataset_key": self.dataset_key,
            "schema_version": self.schema_version,
            "source_manifest_ids": list(self.source_manifest_ids),
            "source_manifest_hashes": list(self.source_manifest_hashes),
            "partition_ids": list(self.partition_ids),
            "partition_hashes": list(self.partition_hashes),
            "feature_schema_version": self.feature_schema_version,
            "label_schema_version": self.label_schema_version,
            "created_at": self.created_at.isoformat(),
            "cutoff_at": self.cutoff_at.isoformat(),
            "total_rows": self.total_rows,
            "strict_replay_fraction": self.strict_replay_fraction,
            "reconstructed_pit_fraction": self.reconstructed_pit_fraction,
            "provider_coverage": [item.to_dict() for item in self.provider_coverage],
            "gaps": [item.to_dict() for item in self.gaps],
        }


def _provider_coverage(
    observations: Sequence[HistoricalObservation],
) -> tuple[ProviderCoverage, ...]:
    grouped: dict[str, list[HistoricalObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.provider].append(observation)
    return tuple(
        ProviderCoverage(
            provider=provider,
            observation_count=len(rows),
            minimum_observed_at=min(item.observed_at for item in rows),
            maximum_observed_at=max(item.observed_at for item in rows),
            minimum_fetched_at=min(item.fetched_at for item in rows),
            maximum_fetched_at=max(item.fetched_at for item in rows),
        )
        for provider, rows in sorted(grouped.items())
    )


def _detect_gaps(
    observations: Sequence[HistoricalObservation],
    expected_interval: timedelta | None,
) -> tuple[DatasetGap, ...]:
    if expected_interval is None:
        return ()
    if expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be positive")
    seconds = int(expected_interval.total_seconds())
    if expected_interval != timedelta(seconds=seconds) or seconds < 1:
        raise ValueError("expected_interval must resolve to whole positive seconds")
    grouped: dict[str, set[datetime]] = defaultdict(set)
    for observation in observations:
        grouped[observation.provider].add(observation.observed_at)
    gaps: list[DatasetGap] = []
    for provider, timestamps in sorted(grouped.items()):
        ordered = sorted(timestamps)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current - previous > expected_interval:
                gaps.append(
                    DatasetGap(
                        provider=provider,
                        starts_at=previous + expected_interval,
                        ends_at=current,
                        expected_interval_seconds=seconds,
                    )
                )
    return tuple(gaps)


def build_dataset_version(
    *,
    dataset_key: str,
    schema_version: str,
    manifests: Sequence[DurableManifest],
    partitions: Sequence[DurablePartition],
    observations: Sequence[HistoricalObservation],
    feature_schema_version: str,
    label_schema_version: str,
    created_at: datetime,
    cutoff_at: datetime,
    expected_interval: timedelta | None = None,
    allow_reconstructed: bool = False,
) -> DatasetVersion:
    dataset_key = _text(dataset_key, "dataset_key")
    schema_version = _text(schema_version, "schema_version")
    feature_schema_version = _text(feature_schema_version, "feature_schema_version")
    label_schema_version = _text(label_schema_version, "label_schema_version")
    created = _utc(created_at, "created_at")
    cutoff = _utc(cutoff_at, "cutoff_at")
    if created < cutoff:
        raise ValueError("created_at cannot precede cutoff_at")
    if not manifests or not partitions or not observations:
        raise ValueError("dataset version requires manifests, partitions and observations")

    manifest_ids = [item.manifest_id for item in manifests]
    partition_ids = [item.partition_id for item in partitions]
    observation_ids = [item.observation_id for item in observations]
    if len(manifest_ids) != len(set(manifest_ids)):
        raise ValueError("manifest ids must be unique")
    if len(partition_ids) != len(set(partition_ids)):
        raise ValueError("partition ids must be unique")
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("observation ids must be unique")

    partition_by_id = {item.partition_id: item for item in partitions}
    referenced_partition_ids: set[str] = set()
    for manifest in manifests:
        if len(manifest.partition_ids) != len(set(manifest.partition_ids)):
            raise ValueError("manifest contains duplicate partition ids")
        referenced_partition_ids.update(manifest.partition_ids)
        manifest_rows = 0
        for partition_id in manifest.partition_ids:
            partition = partition_by_id.get(partition_id)
            if partition is None:
                raise ValueError("manifest references a partition not supplied to dataset version")
            if partition.dataset != manifest.dataset:
                raise ValueError("manifest references a partition from another dataset")
            manifest_rows += partition.row_count
        if manifest_rows != manifest.total_rows:
            raise ValueError("manifest total_rows disagrees with referenced partitions")
    if referenced_partition_ids != set(partition_ids):
        raise ValueError("dataset partitions must exactly match manifest references")

    total_rows = sum(item.row_count for item in partitions)
    if total_rows != len(observations):
        raise ValueError("observation count must match durable partition row count")

    eligibility = [item.eligibility_at(cutoff) for item in observations]
    if EligibilityClass.INELIGIBLE in eligibility:
        raise ValueError("dataset version contains evidence unavailable at cutoff")
    reconstructed_count = eligibility.count(EligibilityClass.RECONSTRUCTED_PIT)
    if reconstructed_count and not allow_reconstructed:
        raise ValueError("reconstructed PIT evidence requires explicit opt-in")
    strict_count = eligibility.count(EligibilityClass.STRICT_REPLAY)
    denominator = len(observations)

    coverage = _provider_coverage(observations)
    gaps = _detect_gaps(observations, expected_interval)
    ordered_manifests = tuple(sorted(manifests, key=lambda item: item.manifest_id))
    ordered_partitions = tuple(sorted(partitions, key=lambda item: item.partition_id))
    material = {
        "dataset_key": dataset_key,
        "schema_version": schema_version,
        "source_manifests": [
            {"id": item.manifest_id, "sha256": item.manifest_sha256} for item in ordered_manifests
        ],
        "partitions": [
            {"id": item.partition_id, "sha256": item.file_sha256} for item in ordered_partitions
        ],
        "feature_schema_version": feature_schema_version,
        "label_schema_version": label_schema_version,
        "created_at": created.isoformat(),
        "cutoff_at": cutoff.isoformat(),
        "total_rows": total_rows,
        "strict_replay_fraction": strict_count / denominator,
        "reconstructed_pit_fraction": reconstructed_count / denominator,
        "provider_coverage": [item.to_dict() for item in coverage],
        "gaps": [item.to_dict() for item in gaps],
    }
    digest = sha256(_canonical(material)).hexdigest()
    return DatasetVersion(
        dataset_version_id=f"dataset-version:sha256:{digest}",
        dataset_sha256=digest,
        dataset_key=dataset_key,
        schema_version=schema_version,
        source_manifest_ids=tuple(item.manifest_id for item in ordered_manifests),
        source_manifest_hashes=tuple(item.manifest_sha256 for item in ordered_manifests),
        partition_ids=tuple(item.partition_id for item in ordered_partitions),
        partition_hashes=tuple(item.file_sha256 for item in ordered_partitions),
        feature_schema_version=feature_schema_version,
        label_schema_version=label_schema_version,
        created_at=created,
        cutoff_at=cutoff,
        total_rows=total_rows,
        strict_replay_fraction=strict_count / denominator,
        reconstructed_pit_fraction=reconstructed_count / denominator,
        provider_coverage=coverage,
        gaps=gaps,
    )
