from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_.-]+$")


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def safe_segment(value: str, *, field_name: str) -> str:
    if not _SAFE_SEGMENT.fullmatch(value):
        raise ValueError(f"{field_name} contains unsafe characters")
    return value


def sanitize_source_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError("source_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("credentials are forbidden in source URLs")
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True, slots=True)
class RawPayloadEnvelope:
    provider: str
    received_at: datetime
    observed_at: datetime | None
    source_url: str
    media_type: str
    payload_sha256: str
    byte_count: int
    payload_path: str
    metadata_path: str
    attributes: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["received_at"] = self.received_at.isoformat()
        payload["observed_at"] = self.observed_at.isoformat() if self.observed_at else None
        return payload


class ContentAddressedRawStore:
    """Immutable raw-payload storage keyed by SHA-256 and receipt date."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(
        self,
        *,
        provider: str,
        payload: bytes,
        received_at: datetime,
        source_url: str,
        observed_at: datetime | None = None,
        media_type: str = "application/json",
        attributes: Mapping[str, Any] | None = None,
    ) -> RawPayloadEnvelope:
        provider = safe_segment(provider, field_name="provider")
        received = utc(received_at)
        observed = utc(observed_at) if observed_at else None
        if observed and observed > received:
            raise ValueError("observed_at cannot be later than received_at")
        if not payload:
            raise ValueError("raw payload cannot be empty")
        digest = sha256_hex(payload)
        partition = self.root / "raw" / provider / received.strftime("%Y/%m/%d")
        payload_path = partition / f"{digest}.bin"
        metadata_path = partition / f"{digest}.json"

        if payload_path.exists():
            existing = payload_path.read_bytes()
            if sha256_hex(existing) != digest or existing != payload:
                raise RuntimeError("content-addressed payload collision or corruption")
        else:
            atomic_write(payload_path, payload)

        envelope = RawPayloadEnvelope(
            provider=provider,
            received_at=received,
            observed_at=observed,
            source_url=sanitize_source_url(source_url),
            media_type=media_type,
            payload_sha256=digest,
            byte_count=len(payload),
            payload_path=str(payload_path.relative_to(self.root)),
            metadata_path=str(metadata_path.relative_to(self.root)),
            attributes=dict(attributes or {}),
        )
        metadata_bytes = canonical_json_bytes(envelope.to_dict()) + b"\n"
        if metadata_path.exists():
            existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if existing_metadata != envelope.to_dict():
                raise RuntimeError("immutable raw metadata already exists with different content")
        else:
            atomic_write(metadata_path, metadata_bytes)
        return envelope

    def read(self, envelope: RawPayloadEnvelope) -> bytes:
        path = self.root / envelope.payload_path
        payload = path.read_bytes()
        if sha256_hex(payload) != envelope.payload_sha256:
            raise RuntimeError("raw payload integrity check failed")
        return payload

    def verify(self, envelope: RawPayloadEnvelope) -> None:
        payload = self.read(envelope)
        if len(payload) != envelope.byte_count:
            raise RuntimeError("raw payload byte count does not match metadata")
        metadata_path = self.root / envelope.metadata_path
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata != envelope.to_dict():
            raise RuntimeError("raw metadata integrity check failed")


@dataclass(frozen=True, slots=True)
class HistoricalRecord:
    dataset: str
    record_id: str
    observed_at: datetime
    available_at: datetime
    source: str
    revision: int
    values: Mapping[str, Any]
    raw_payload_sha256: str

    def __post_init__(self) -> None:
        safe_segment(self.dataset, field_name="dataset")
        if not self.record_id:
            raise ValueError("record_id is required")
        if not self.source:
            raise ValueError("source is required")
        observed = utc(self.observed_at)
        available = utc(self.available_at)
        if available < observed:
            raise ValueError("available_at cannot precede observed_at")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if not re.fullmatch(r"[0-9a-f]{64}", self.raw_payload_sha256):
            raise ValueError("raw_payload_sha256 must be a lowercase SHA-256 digest")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "values", dict(self.values))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "record_id": self.record_id,
            "observed_at": self.observed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "source": self.source,
            "revision": self.revision,
            "values": dict(self.values),
            "raw_payload_sha256": self.raw_payload_sha256,
        }

    @property
    def canonical_sha256(self) -> str:
        return sha256_hex(canonical_json_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class DatasetPartition:
    dataset: str
    partition_key: str
    path: str
    row_count: int
    byte_count: int
    file_sha256: str
    minimum_observed_at: datetime
    maximum_observed_at: datetime
    minimum_available_at: datetime
    maximum_available_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for field_name in (
            "minimum_observed_at",
            "maximum_observed_at",
            "minimum_available_at",
            "maximum_available_at",
        ):
            payload[field_name] = getattr(self, field_name).isoformat()
        return payload


class JSONLPartitionStore:
    """Atomic normalized-record partitions with deterministic ordering and hashes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write_partition(
        self,
        *,
        dataset: str,
        partition_key: str,
        records: Iterable[HistoricalRecord],
    ) -> DatasetPartition:
        dataset = safe_segment(dataset, field_name="dataset")
        if not re.fullmatch(r"[a-zA-Z0-9_=.-]+", partition_key):
            raise ValueError("partition_key contains unsafe characters")
        ordered = sorted(
            records,
            key=lambda record: (
                record.observed_at,
                record.available_at,
                record.record_id,
                record.revision,
                record.source,
            ),
        )
        if not ordered:
            raise ValueError("partition must contain at least one record")
        if any(record.dataset != dataset for record in ordered):
            raise ValueError("partition contains a record from another dataset")
        identities = [
            (record.record_id, record.revision, record.source, record.available_at)
            for record in ordered
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("partition contains duplicate record revisions")

        payload = b"".join(canonical_json_bytes(record.to_dict()) + b"\n" for record in ordered)
        digest = sha256_hex(payload)
        relative_path = Path("normalized") / dataset / partition_key / f"part-{digest}.jsonl"
        path = self.root / relative_path
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError("normalized partition collision or corruption")
        else:
            atomic_write(path, payload)

        return DatasetPartition(
            dataset=dataset,
            partition_key=partition_key,
            path=str(relative_path),
            row_count=len(ordered),
            byte_count=len(payload),
            file_sha256=digest,
            minimum_observed_at=min(record.observed_at for record in ordered),
            maximum_observed_at=max(record.observed_at for record in ordered),
            minimum_available_at=min(record.available_at for record in ordered),
            maximum_available_at=max(record.available_at for record in ordered),
        )

    def read_partition(self, partition: DatasetPartition) -> tuple[dict[str, Any], ...]:
        path = self.root / partition.path
        payload = path.read_bytes()
        if sha256_hex(payload) != partition.file_sha256:
            raise RuntimeError("normalized partition integrity check failed")
        rows = tuple(json.loads(line) for line in payload.splitlines() if line)
        if len(rows) != partition.row_count:
            raise RuntimeError("normalized partition row count does not match manifest")
        return rows


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset: str
    schema_version: str
    created_at: datetime
    partitions: tuple[DatasetPartition, ...]
    total_rows: int
    manifest_sha256: str

    @classmethod
    def build(
        cls,
        *,
        dataset: str,
        schema_version: str,
        created_at: datetime,
        partitions: Sequence[DatasetPartition],
    ) -> DatasetManifest:
        dataset = safe_segment(dataset, field_name="dataset")
        if not schema_version:
            raise ValueError("schema_version is required")
        created = utc(created_at)
        ordered = tuple(sorted(partitions, key=lambda partition: (partition.partition_key, partition.path)))
        if not ordered:
            raise ValueError("manifest requires at least one partition")
        if any(partition.dataset != dataset for partition in ordered):
            raise ValueError("manifest contains a partition from another dataset")
        unsigned = {
            "dataset": dataset,
            "schema_version": schema_version,
            "created_at": created.isoformat(),
            "partitions": [partition.to_dict() for partition in ordered],
            "total_rows": sum(partition.row_count for partition in ordered),
        }
        return cls(
            dataset=dataset,
            schema_version=schema_version,
            created_at=created,
            partitions=ordered,
            total_rows=unsigned["total_rows"],
            manifest_sha256=sha256_hex(canonical_json_bytes(unsigned)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "partitions": [partition.to_dict() for partition in self.partitions],
            "total_rows": self.total_rows,
            "manifest_sha256": self.manifest_sha256,
        }


class ManifestStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, manifest: DatasetManifest) -> Path:
        relative_path = (
            Path("manifests")
            / manifest.dataset
            / manifest.schema_version
            / f"{manifest.manifest_sha256}.json"
        )
        path = self.root / relative_path
        payload = canonical_json_bytes(manifest.to_dict()) + b"\n"
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError("manifest collision or corruption")
        else:
            atomic_write(path, payload)
        return relative_path


class PointInTimeCatalog:
    """SQLite index that resolves only records available at the decision timestamp."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS historical_records (
                    dataset TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    raw_payload_sha256 TEXT NOT NULL,
                    canonical_sha256 TEXT NOT NULL,
                    partition_path TEXT NOT NULL,
                    values_json TEXT NOT NULL,
                    PRIMARY KEY(dataset, record_id, source, revision, available_at)
                );
                CREATE INDEX IF NOT EXISTS idx_historical_asof
                    ON historical_records(dataset, available_at, observed_at, record_id);
                """
            )

    def add(self, record: HistoricalRecord, *, partition_path: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO historical_records(
                    dataset, record_id, observed_at, available_at, source, revision,
                    raw_payload_sha256, canonical_sha256, partition_path, values_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.dataset,
                    record.record_id,
                    record.observed_at.isoformat(),
                    record.available_at.isoformat(),
                    record.source,
                    record.revision,
                    record.raw_payload_sha256,
                    record.canonical_sha256,
                    partition_path,
                    json.dumps(record.values, sort_keys=True, separators=(",", ":"), default=str),
                ),
            )
            return cursor.rowcount == 1

    def add_many(self, records: Iterable[HistoricalRecord], *, partition_path: str) -> int:
        return sum(self.add(record, partition_path=partition_path) for record in records)

    def as_of(self, *, dataset: str, decision_time: datetime) -> tuple[HistoricalRecord, ...]:
        cutoff = utc(decision_time).isoformat()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM historical_records
                WHERE dataset = ? AND available_at <= ?
                ORDER BY record_id ASC, observed_at DESC, revision DESC, available_at DESC, source ASC
                """,
                (dataset, cutoff),
            ).fetchall()
        selected: dict[str, sqlite3.Row] = {}
        for row in rows:
            selected.setdefault(row["record_id"], row)
        return tuple(
            HistoricalRecord(
                dataset=row["dataset"],
                record_id=row["record_id"],
                observed_at=datetime.fromisoformat(row["observed_at"]),
                available_at=datetime.fromisoformat(row["available_at"]),
                source=row["source"],
                revision=int(row["revision"]),
                values=json.loads(row["values_json"]),
                raw_payload_sha256=row["raw_payload_sha256"],
            )
            for row in selected.values()
        )

    def count(self, *, dataset: str | None = None) -> int:
        with self._connect() as connection:
            if dataset is None:
                row = connection.execute("SELECT COUNT(*) AS count FROM historical_records").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM historical_records WHERE dataset = ?",
                    (dataset,),
                ).fetchone()
        assert row is not None
        return int(row["count"])


class BackfillCheckpointStore:
    """Idempotent cursor state committed only after durable data writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    job_key TEXT PRIMARY KEY,
                    cursor_json TEXT NOT NULL,
                    completed INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def load(self, job_key: str) -> tuple[Mapping[str, Any], bool] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT cursor_json, completed FROM checkpoints WHERE job_key = ?",
                (job_key,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["cursor_json"]), bool(row["completed"])

    def save(self, job_key: str, *, cursor: Mapping[str, Any], completed: bool) -> None:
        if not job_key:
            raise ValueError("job_key is required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO checkpoints(job_key, cursor_json, completed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    cursor_json = excluded.cursor_json,
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (
                    job_key,
                    json.dumps(cursor, sort_keys=True, separators=(",", ":"), default=str),
                    int(completed),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
