from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AvailabilityPrecision(StrEnum):
    EXACT = "EXACT"
    DATE_ONLY = "DATE_ONLY"
    INFERRED_CONSERVATIVE = "INFERRED_CONSERVATIVE"
    UNKNOWN = "UNKNOWN"


class EligibilityClass(StrEnum):
    STRICT_REPLAY = "STRICT_REPLAY"
    RECONSTRUCTED_PIT = "RECONSTRUCTED_PIT"
    INELIGIBLE = "INELIGIBLE"


class AmbiguousRevisionError(RuntimeError):
    """Equally ranked revisions disagree for one logical source series."""


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _sha(value: str, field: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    return normalized


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _sanitize_uri(uri: str) -> str:
    parsed = urlsplit(_text(uri, "canonical_uri"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("canonical_uri must be an absolute HTTP(S) URI")
    if parsed.username or parsed.password:
        raise ValueError("credentials are forbidden in canonical_uri")
    netloc = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


@dataclass(frozen=True, slots=True)
class FetchReceipt:
    fetch_id: str
    source_id: str
    provider: str
    canonical_uri: str
    endpoint: str
    request_fingerprint: str
    fetched_at: datetime
    payload_sha256: str
    ingestion_version: str
    parser_version: str

    @classmethod
    def create(
        cls,
        *,
        source_id: str,
        provider: str,
        canonical_uri: str,
        endpoint: str,
        request_fingerprint: str,
        fetched_at: datetime,
        payload_sha256: str,
        ingestion_version: str,
        parser_version: str,
    ) -> FetchReceipt:
        fetched = _utc(fetched_at, "fetched_at")
        uri = _sanitize_uri(canonical_uri)
        request_hash = _sha(request_fingerprint, "request_fingerprint")
        payload_hash = _sha(payload_sha256, "payload_sha256")
        material = {
            "source_id": _text(source_id, "source_id"),
            "provider": _text(provider, "provider"),
            "canonical_uri": uri,
            "endpoint": _text(endpoint, "endpoint"),
            "request_fingerprint": request_hash,
            "fetched_at": fetched.isoformat(),
            "payload_sha256": payload_hash,
            "ingestion_version": _text(ingestion_version, "ingestion_version"),
            "parser_version": _text(parser_version, "parser_version"),
        }
        digest = sha256(_canonical(material)).hexdigest()
        return cls(
            fetch_id=f"fetch:sha256:{digest}",
            source_id=material["source_id"],
            provider=material["provider"],
            canonical_uri=uri,
            endpoint=material["endpoint"],
            request_fingerprint=request_hash,
            fetched_at=fetched,
            payload_sha256=payload_hash,
            ingestion_version=material["ingestion_version"],
            parser_version=material["parser_version"],
        )


@dataclass(frozen=True, slots=True)
class HistoricalObservation:
    observation_id: str
    dataset: str
    record_id: str
    provider: str
    source_id: str
    symbol: str
    instrument: str
    observed_at: datetime
    fetched_at: datetime
    fetch_id: str
    payload_sha256: str
    values: Mapping[str, object]
    availability_precision: AvailabilityPrecision
    availability_policy: str
    available_at: datetime | None = None
    available_date: date | None = None
    revision_sequence: int | None = None
    reconstruction_basis_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "observation_id",
            "dataset",
            "record_id",
            "provider",
            "source_id",
            "symbol",
            "instrument",
            "fetch_id",
            "availability_policy",
        ):
            _text(str(getattr(self, name)), name)
        if not self.fetch_id.startswith("fetch:sha256:"):
            raise ValueError("fetch_id must use fetch:sha256:<digest>")
        _sha(self.fetch_id.removeprefix("fetch:sha256:"), "fetch_id digest")
        _sha(self.payload_sha256, "payload_sha256")
        object.__setattr__(self, "observed_at", _utc(self.observed_at, "observed_at"))
        object.__setattr__(self, "fetched_at", _utc(self.fetched_at, "fetched_at"))
        if self.available_at is not None:
            object.__setattr__(self, "available_at", _utc(self.available_at, "available_at"))
        if self.revision_sequence is not None and self.revision_sequence < 0:
            raise ValueError("revision_sequence must be non-negative")
        json.dumps(self.values, allow_nan=False)

        if self.availability_precision is AvailabilityPrecision.EXACT:
            if self.available_at is None or self.available_date is not None:
                raise ValueError("EXACT requires available_at only")
        elif self.availability_precision is AvailabilityPrecision.INFERRED_CONSERVATIVE:
            if self.available_at is None or self.available_date is not None:
                raise ValueError("INFERRED_CONSERVATIVE requires available_at only")
        elif self.availability_precision is AvailabilityPrecision.DATE_ONLY:
            if self.available_at is not None or self.available_date is None:
                raise ValueError("DATE_ONLY requires available_date only")
        elif self.availability_precision is AvailabilityPrecision.UNKNOWN:
            if self.available_at is not None or self.available_date is not None:
                raise ValueError("UNKNOWN cannot carry availability")
        else:
            raise ValueError("unsupported availability precision")

        if self.available_at is not None and self.fetched_at < self.available_at:
            raise ValueError("fetched_at cannot precede available_at")

    def availability_boundary(self) -> datetime | None:
        if self.availability_precision in {
            AvailabilityPrecision.EXACT,
            AvailabilityPrecision.INFERRED_CONSERVATIVE,
        }:
            return self.available_at
        if self.availability_precision is AvailabilityPrecision.DATE_ONLY:
            assert self.available_date is not None
            return datetime.combine(
                self.available_date + timedelta(days=1),
                datetime.min.time(),
                UTC,
            )
        return None

    def eligibility_at(self, prediction_time: datetime) -> EligibilityClass:
        prediction = _utc(prediction_time, "prediction_time")
        boundary = self.availability_boundary()
        if boundary is None or boundary > prediction:
            return EligibilityClass.INELIGIBLE
        if self.fetched_at <= prediction:
            return EligibilityClass.STRICT_REPLAY
        if self.reconstruction_basis_id:
            return EligibilityClass.RECONSTRUCTED_PIT
        return EligibilityClass.INELIGIBLE

    @property
    def canonical_sha256(self) -> str:
        payload = {
            "observation_id": self.observation_id,
            "dataset": self.dataset,
            "record_id": self.record_id,
            "provider": self.provider,
            "source_id": self.source_id,
            "symbol": self.symbol,
            "instrument": self.instrument,
            "observed_at": self.observed_at.isoformat(),
            "fetched_at": self.fetched_at.isoformat(),
            "fetch_id": self.fetch_id,
            "payload_sha256": self.payload_sha256,
            "values": dict(self.values),
            "availability_precision": self.availability_precision.value,
            "availability_policy": self.availability_policy,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "available_date": self.available_date.isoformat() if self.available_date else None,
            "revision_sequence": self.revision_sequence,
            "reconstruction_basis_id": self.reconstruction_basis_id,
        }
        return sha256(_canonical(payload)).hexdigest()


def _revision_rank(observation: HistoricalObservation) -> tuple[datetime, int, datetime]:
    boundary = observation.availability_boundary()
    if boundary is None:
        raise ValueError("cannot rank observation without availability")
    revision = observation.revision_sequence if observation.revision_sequence is not None else -1
    return boundary, revision, observation.fetched_at


def select_as_of(
    observations: Sequence[HistoricalObservation],
    *,
    prediction_time: datetime,
    allow_reconstructed: bool = False,
) -> tuple[HistoricalObservation, ...]:
    prediction = _utc(prediction_time, "prediction_time")
    groups: dict[tuple[str, str, str], list[HistoricalObservation]] = {}
    for observation in observations:
        eligibility = observation.eligibility_at(prediction)
        if eligibility is EligibilityClass.INELIGIBLE:
            continue
        if eligibility is EligibilityClass.RECONSTRUCTED_PIT and not allow_reconstructed:
            continue
        key = (observation.record_id, observation.provider, observation.source_id)
        groups.setdefault(key, []).append(observation)

    selected: list[HistoricalObservation] = []
    for key in sorted(groups):
        candidates = groups[key]
        best_rank = max(_revision_rank(item) for item in candidates)
        best = [item for item in candidates if _revision_rank(item) == best_rank]
        if len({item.canonical_sha256 for item in best}) > 1:
            raise AmbiguousRevisionError(
                f"equally ranked revisions disagree for {key!r}"
            )
        selected.append(min(best, key=lambda item: item.observation_id))
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_snapshot_id: str
    snapshot_sha256: str
    prediction_time: datetime
    eligibility_class: EligibilityClass
    observation_ids: tuple[str, ...]
    observation_hashes: tuple[str, ...]
    fetch_ids: tuple[str, ...]
    provider_universe: tuple[str, ...]

    @classmethod
    def build(
        cls,
        observations: Sequence[HistoricalObservation],
        *,
        prediction_time: datetime,
        allow_reconstructed: bool = False,
    ) -> SourceSnapshot:
        prediction = _utc(prediction_time, "prediction_time")
        ordered = tuple(sorted(observations, key=lambda item: item.observation_id))
        if not ordered:
            raise ValueError("source snapshot requires observations")
        classes = tuple(item.eligibility_at(prediction) for item in ordered)
        if EligibilityClass.INELIGIBLE in classes:
            raise ValueError("source snapshot contains ineligible observations")
        if EligibilityClass.RECONSTRUCTED_PIT in classes and not allow_reconstructed:
            raise ValueError("reconstructed PIT requires explicit opt-in")
        overall = (
            EligibilityClass.RECONSTRUCTED_PIT
            if EligibilityClass.RECONSTRUCTED_PIT in classes
            else EligibilityClass.STRICT_REPLAY
        )
        ids = tuple(item.observation_id for item in ordered)
        hashes = tuple(item.canonical_sha256 for item in ordered)
        fetches = tuple(sorted({item.fetch_id for item in ordered}))
        providers = tuple(sorted({item.provider for item in ordered}))
        material = {
            "prediction_time": prediction.isoformat(),
            "eligibility_class": overall.value,
            "observation_ids": list(ids),
            "observation_hashes": list(hashes),
            "fetch_ids": list(fetches),
            "provider_universe": list(providers),
        }
        digest = sha256(_canonical(material)).hexdigest()
        return cls(
            source_snapshot_id=f"snapshot:sha256:{digest}",
            snapshot_sha256=digest,
            prediction_time=prediction,
            eligibility_class=overall,
            observation_ids=ids,
            observation_hashes=hashes,
            fetch_ids=fetches,
            provider_universe=providers,
        )
