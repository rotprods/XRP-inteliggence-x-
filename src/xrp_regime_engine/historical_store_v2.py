from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from xrp_regime_engine.historical_contract import (
    AvailabilityPrecision,
    FetchReceipt,
    HistoricalObservation,
    select_as_of,
)

_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.=-]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STORE_SCHEMA_VERSION = 1


def _canonical_bytes(payload: object) -> bytes:
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


def _safe_segment(value: str, field: str) -> str:
    if not _SAFE_SEGMENT_RE.fullmatch(value):
        raise ValueError(f"{field} contains unsafe characters")
    return value


def _sha256(value: str, field: str) -> str:
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _receipt_payload(receipt: FetchReceipt) -> dict[str, object]:
    return {
        "fetch_id": receipt.fetch_id,
        "source_id": receipt.source_id,
        "provider": receipt.provider,
        "canonical_uri": receipt.canonical_uri,
        "endpoint": receipt.endpoint,
        "request_fingerprint": receipt.request_fingerprint,
        "fetched_at": receipt.fetched_at.isoformat(),
        "payload_sha256": receipt.payload_sha256,
        "ingestion_version": receipt.ingestion_version,
        "parser_version": receipt.parser_version,
    }


def _observation_payload(observation: HistoricalObservation) -> dict[str, object]:
    return {
        "observation_id": observation.observation_id,
        "dataset": observation.dataset,
        "record_id": observation.record_id,
        "provider": observation.provider,
        "source_id": observation.source_id,
        "symbol": observation.symbol,
        "instrument": observation.instrument,
        "observed_at": observation.observed_at.isoformat(),
        "fetched_at": observation.fetched_at.isoformat(),
        "fetch_id": observation.fetch_id,
        "payload_sha256": observation.payload_sha256,
        "values": dict(observation.values),
        "availability_precision": observation.availability_precision.value,
        "availability_policy": observation.availability_policy,
        "available_at": observation.available_at.isoformat() if observation.available_at else None,
        "available_date": observation.available_date.isoformat()
        if observation.available_date
        else None,
        "revision_sequence": observation.revision_sequence,
        "reconstruction_basis_id": observation.reconstruction_basis_id,
    }


def _observation_from_payload(payload: Mapping[str, object]) -> HistoricalObservation:
    available_at_raw = payload.get("available_at")
    available_date_raw = payload.get("available_date")
    revision_raw = payload.get("revision_sequence")
    values_raw = payload.get("values")
    if not isinstance(values_raw, Mapping):
        raise RuntimeError("stored observation values must be an object")
    return HistoricalObservation(
        observation_id=str(payload["observation_id"]),
        dataset=str(payload["dataset"]),
        record_id=str(payload["record_id"]),
        provider=str(payload["provider"]),
        source_id=str(payload["source_id"]),
        symbol=str(payload["symbol"]),
        instrument=str(payload["instrument"]),
        observed_at=datetime.fromisoformat(str(payload["observed_at"])),
        fetched_at=datetime.fromisoformat(str(payload["fetched_at"])),
        fetch_id=str(payload["fetch_id"]),
        payload_sha256=str(payload["payload_sha256"]),
        values=dict(values_raw),
        availability_precision=AvailabilityPrecision(str(payload["availability_precision"])),
        availability_policy=str(payload["availability_policy"]),
        available_at=datetime.fromisoformat(str(available_at_raw))
        if available_at_raw is not None
        else None,
        available_date=date.fromisoformat(str(available_date_raw))
        if available_date_raw is not None
        else None,
        revision_sequence=int(str(revision_raw)) if revision_raw is not None else None,
        reconstruction_basis_id=str(payload["reconstruction_basis_id"])
        if payload.get("reconstruction_basis_id") is not None
        else None,
    )


@dataclass(frozen=True, slots=True)
class RawBlob:
    payload_sha256: str
    byte_count: int
    relative_path: str


@dataclass(frozen=True, slots=True)
class DurablePartition:
    partition_id: str
    dataset: str
    partition_key: str
    relative_path: str
    file_sha256: str
    row_count: int
    minimum_observed_at: datetime
    maximum_observed_at: datetime
    minimum_fetched_at: datetime
    maximum_fetched_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "partition_id": self.partition_id,
            "dataset": self.dataset,
            "partition_key": self.partition_key,
            "relative_path": self.relative_path,
            "file_sha256": self.file_sha256,
            "row_count": self.row_count,
            "minimum_observed_at": self.minimum_observed_at.isoformat(),
            "maximum_observed_at": self.maximum_observed_at.isoformat(),
            "minimum_fetched_at": self.minimum_fetched_at.isoformat(),
            "maximum_fetched_at": self.maximum_fetched_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DurableManifest:
    manifest_id: str
    manifest_sha256: str
    dataset: str
    schema_version: str
    created_at: datetime
    partition_ids: tuple[str, ...]
    total_rows: int
    relative_path: str


@dataclass(frozen=True, slots=True)
class BackfillCheckpoint:
    job_key: str
    cursor: Mapping[str, object]
    completed: bool
    updated_at: datetime


class HistoricalEvidenceStoreV2:
    """Durable historical evidence substrate with append-only provenance identity.

    Files are written before the SQLite registry/checkpoint is advanced. A crash may
    leave an unreferenced immutable file, but it cannot advance a checkpoint past a
    missing partition.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be positive")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "catalog.sqlite3"
        self.busy_timeout_ms = busy_timeout_ms
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level="DEFERRED",
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS raw_blobs (
                    payload_sha256 TEXT PRIMARY KEY,
                    byte_count INTEGER NOT NULL CHECK(byte_count > 0),
                    relative_path TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS fetch_receipts (
                    fetch_id TEXT PRIMARY KEY,
                    payload_sha256 TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(payload_sha256) REFERENCES raw_blobs(payload_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_fetch_payload
                    ON fetch_receipts(payload_sha256, fetched_at);

                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    instrument TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    fetch_id TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    canonical_sha256 TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(fetch_id) REFERENCES fetch_receipts(fetch_id),
                    FOREIGN KEY(payload_sha256) REFERENCES raw_blobs(payload_sha256)
                );
                CREATE INDEX IF NOT EXISTS idx_observation_dataset
                    ON observations(dataset, record_id, provider, source_id, observed_at);

                CREATE TABLE IF NOT EXISTS partitions (
                    partition_id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    partition_key TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    file_sha256 TEXT NOT NULL UNIQUE,
                    row_count INTEGER NOT NULL CHECK(row_count > 0),
                    minimum_observed_at TEXT NOT NULL,
                    maximum_observed_at TEXT NOT NULL,
                    minimum_fetched_at TEXT NOT NULL,
                    maximum_fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_partition_dataset
                    ON partitions(dataset, partition_key, partition_id);

                CREATE TABLE IF NOT EXISTS partition_members (
                    partition_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    PRIMARY KEY(partition_id, observation_id),
                    FOREIGN KEY(partition_id) REFERENCES partitions(partition_id),
                    FOREIGN KEY(observation_id) REFERENCES observations(observation_id)
                );

                CREATE TABLE IF NOT EXISTS manifests (
                    manifest_id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL UNIQUE,
                    total_rows INTEGER NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    job_key TEXT PRIMARY KEY,
                    cursor_json TEXT NOT NULL,
                    completed INTEGER NOT NULL CHECK(completed IN (0, 1)),
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT INTO store_metadata(key, value) VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(STORE_SCHEMA_VERSION),),
            )

    def _blob_path(self, payload_sha256: str) -> Path:
        digest = _sha256(payload_sha256, "payload_sha256")
        return self.root / "raw" / "sha256" / digest[:2] / digest[2:4] / f"{digest}.blob"

    def put_raw(self, payload: bytes) -> RawBlob:
        if not payload:
            raise ValueError("raw payload cannot be empty")
        digest = sha256(payload).hexdigest()
        path = self._blob_path(digest)
        if path.exists():
            existing = path.read_bytes()
            if sha256(existing).hexdigest() != digest or existing != payload:
                raise RuntimeError("raw blob integrity collision or corruption")
        else:
            _atomic_write(path, payload)
        relative = str(path.relative_to(self.root))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT byte_count, relative_path FROM raw_blobs WHERE payload_sha256=?",
                (digest,),
            ).fetchone()
            if row is not None:
                if int(row["byte_count"]) != len(payload) or str(row["relative_path"]) != relative:
                    raise RuntimeError("raw blob registry collision")
            else:
                connection.execute(
                    """
                    INSERT INTO raw_blobs(payload_sha256, byte_count, relative_path)
                    VALUES (?, ?, ?)
                    """,
                    (digest, len(payload), relative),
                )
        return RawBlob(digest, len(payload), relative)

    def read_raw(self, payload_sha256: str) -> bytes:
        digest = _sha256(payload_sha256, "payload_sha256")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT byte_count, relative_path FROM raw_blobs WHERE payload_sha256=?",
                (digest,),
            ).fetchone()
        if row is None:
            raise KeyError(digest)
        path = self.root / str(row["relative_path"])
        payload = path.read_bytes()
        if len(payload) != int(row["byte_count"]) or sha256(payload).hexdigest() != digest:
            raise RuntimeError("raw blob integrity check failed")
        return payload

    def record_fetch(self, payload: bytes, receipt: FetchReceipt) -> RawBlob:
        actual_digest = sha256(payload).hexdigest()
        if actual_digest != receipt.payload_sha256:
            raise ValueError("fetch receipt payload_sha256 does not match raw bytes")
        blob = self.put_raw(payload)
        receipt_json = _canonical_bytes(_receipt_payload(receipt)).decode("utf-8")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM fetch_receipts WHERE fetch_id=?",
                (receipt.fetch_id,),
            ).fetchone()
            if row is not None:
                if str(row["payload_json"]) != receipt_json:
                    raise ValueError("fetch_id collision with different receipt payload")
                return blob
            connection.execute(
                """
                INSERT INTO fetch_receipts(
                    fetch_id, payload_sha256, source_id, provider, fetched_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    receipt.fetch_id,
                    receipt.payload_sha256,
                    receipt.source_id,
                    receipt.provider,
                    receipt.fetched_at.isoformat(),
                    receipt_json,
                ),
            )
        return blob

    def _validate_observation_receipt(
        self,
        connection: sqlite3.Connection,
        observation: HistoricalObservation,
    ) -> None:
        row = connection.execute(
            """
            SELECT payload_sha256, source_id, provider, fetched_at
            FROM fetch_receipts WHERE fetch_id=?
            """,
            (observation.fetch_id,),
        ).fetchone()
        if row is None:
            raise ValueError("observation fetch_id is not registered")
        expected = (
            observation.payload_sha256,
            observation.source_id,
            observation.provider,
            observation.fetched_at.isoformat(),
        )
        actual = (
            str(row["payload_sha256"]),
            str(row["source_id"]),
            str(row["provider"]),
            str(row["fetched_at"]),
        )
        if actual != expected:
            raise ValueError("observation provenance does not match fetch receipt")

    def save_observation(self, observation: HistoricalObservation) -> None:
        payload_json = _canonical_bytes(_observation_payload(observation)).decode("utf-8")
        with self._connection() as connection:
            self._validate_observation_receipt(connection, observation)
            row = connection.execute(
                """
                SELECT canonical_sha256, payload_json
                FROM observations WHERE observation_id=?
                """,
                (observation.observation_id,),
            ).fetchone()
            if row is not None:
                if (
                    str(row["canonical_sha256"]) != observation.canonical_sha256
                    or str(row["payload_json"]) != payload_json
                ):
                    raise ValueError("observation_id collision with different payload")
                return
            connection.execute(
                """
                INSERT INTO observations(
                    observation_id, dataset, record_id, provider, source_id,
                    symbol, instrument, observed_at, fetched_at, fetch_id,
                    payload_sha256, canonical_sha256, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.observation_id,
                    observation.dataset,
                    observation.record_id,
                    observation.provider,
                    observation.source_id,
                    observation.symbol,
                    observation.instrument,
                    observation.observed_at.isoformat(),
                    observation.fetched_at.isoformat(),
                    observation.fetch_id,
                    observation.payload_sha256,
                    observation.canonical_sha256,
                    payload_json,
                ),
            )

    def _partition_payload(
        self,
        observations: Sequence[HistoricalObservation],
    ) -> bytes:
        ordered = sorted(
            observations,
            key=lambda item: (
                item.observed_at,
                item.record_id,
                item.provider,
                item.source_id,
                item.revision_sequence if item.revision_sequence is not None else -1,
                item.observation_id,
            ),
        )
        identifiers = [item.observation_id for item in ordered]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("partition observation_id values must be unique")
        return b"".join(_canonical_bytes(_observation_payload(item)) + b"\n" for item in ordered)

    def write_partition(
        self,
        *,
        dataset: str,
        partition_key: str,
        observations: Sequence[HistoricalObservation],
    ) -> DurablePartition:
        dataset = _safe_segment(dataset, "dataset")
        partition_key = _safe_segment(partition_key, "partition_key")
        if not observations:
            raise ValueError("partition requires at least one observation")
        if any(item.dataset != dataset for item in observations):
            raise ValueError("partition contains observation from another dataset")
        for observation in observations:
            self.save_observation(observation)

        payload = self._partition_payload(observations)
        digest = sha256(payload).hexdigest()
        partition_id = f"partition:sha256:{digest}"
        relative = Path("normalized") / dataset / partition_key / f"part-{digest}.jsonl"
        path = self.root / relative
        if path.exists():
            existing = path.read_bytes()
            if existing != payload or sha256(existing).hexdigest() != digest:
                raise RuntimeError("partition integrity collision or corruption")
        else:
            _atomic_write(path, payload)

        minimum_observed = min(item.observed_at for item in observations)
        maximum_observed = max(item.observed_at for item in observations)
        minimum_fetched = min(item.fetched_at for item in observations)
        maximum_fetched = max(item.fetched_at for item in observations)
        partition = DurablePartition(
            partition_id=partition_id,
            dataset=dataset,
            partition_key=partition_key,
            relative_path=str(relative),
            file_sha256=digest,
            row_count=len(observations),
            minimum_observed_at=minimum_observed,
            maximum_observed_at=maximum_observed,
            minimum_fetched_at=minimum_fetched,
            maximum_fetched_at=maximum_fetched,
        )
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM partitions WHERE partition_id=?",
                (partition_id,),
            ).fetchone()
            if row is not None:
                if (
                    str(row["relative_path"]) != partition.relative_path
                    or int(row["row_count"]) != partition.row_count
                    or str(row["file_sha256"]) != partition.file_sha256
                ):
                    raise RuntimeError("partition registry collision")
            else:
                connection.execute(
                    """
                    INSERT INTO partitions(
                        partition_id, dataset, partition_key, relative_path,
                        file_sha256, row_count, minimum_observed_at,
                        maximum_observed_at, minimum_fetched_at, maximum_fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        partition.partition_id,
                        partition.dataset,
                        partition.partition_key,
                        partition.relative_path,
                        partition.file_sha256,
                        partition.row_count,
                        partition.minimum_observed_at.isoformat(),
                        partition.maximum_observed_at.isoformat(),
                        partition.minimum_fetched_at.isoformat(),
                        partition.maximum_fetched_at.isoformat(),
                    ),
                )
            for observation in observations:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO partition_members(partition_id, observation_id)
                    VALUES (?, ?)
                    """,
                    (partition_id, observation.observation_id),
                )
        return partition

    def list_partitions(self, dataset: str) -> tuple[DurablePartition, ...]:
        dataset = _safe_segment(dataset, "dataset")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM partitions WHERE dataset=?
                ORDER BY partition_key ASC, partition_id ASC
                """,
                (dataset,),
            ).fetchall()
        return tuple(
            DurablePartition(
                partition_id=str(row["partition_id"]),
                dataset=str(row["dataset"]),
                partition_key=str(row["partition_key"]),
                relative_path=str(row["relative_path"]),
                file_sha256=str(row["file_sha256"]),
                row_count=int(row["row_count"]),
                minimum_observed_at=datetime.fromisoformat(str(row["minimum_observed_at"])),
                maximum_observed_at=datetime.fromisoformat(str(row["maximum_observed_at"])),
                minimum_fetched_at=datetime.fromisoformat(str(row["minimum_fetched_at"])),
                maximum_fetched_at=datetime.fromisoformat(str(row["maximum_fetched_at"])),
            )
            for row in rows
        )

    def verify_partition(self, partition: DurablePartition) -> None:
        path = self.root / partition.relative_path
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != partition.file_sha256:
            raise RuntimeError("partition SHA-256 verification failed")
        rows = [line for line in payload.splitlines() if line]
        if len(rows) != partition.row_count:
            raise RuntimeError("partition row count verification failed")

    def finalize_manifest(
        self,
        *,
        dataset: str,
        schema_version: str,
        created_at: datetime,
    ) -> DurableManifest:
        dataset = _safe_segment(dataset, "dataset")
        schema_version = _safe_segment(schema_version, "schema_version")
        created = _utc(created_at, "created_at")
        partitions = self.list_partitions(dataset)
        if not partitions:
            raise ValueError("manifest requires at least one durable partition")
        for partition in partitions:
            self.verify_partition(partition)
        manifest_payload = {
            "dataset": dataset,
            "schema_version": schema_version,
            "created_at": created.isoformat(),
            "partitions": [partition.to_dict() for partition in partitions],
            "total_rows": sum(partition.row_count for partition in partitions),
        }
        payload = _canonical_bytes(manifest_payload) + b"\n"
        digest = sha256(payload).hexdigest()
        manifest_id = f"manifest:sha256:{digest}"
        relative = Path("manifests") / dataset / schema_version / f"{digest}.json"
        path = self.root / relative
        if path.exists():
            existing = path.read_bytes()
            if existing != payload:
                raise RuntimeError("manifest integrity collision or corruption")
        else:
            _atomic_write(path, payload)
        payload_json = payload.decode("utf-8").rstrip("\n")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM manifests WHERE manifest_id=?",
                (manifest_id,),
            ).fetchone()
            if row is not None:
                if str(row["payload_json"]) != payload_json:
                    raise RuntimeError("manifest registry collision")
            else:
                connection.execute(
                    """
                    INSERT INTO manifests(
                        manifest_id, dataset, schema_version, created_at,
                        manifest_sha256, total_rows, relative_path, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest_id,
                        dataset,
                        schema_version,
                        created.isoformat(),
                        digest,
                        manifest_payload["total_rows"],
                        str(relative),
                        payload_json,
                    ),
                )
        return DurableManifest(
            manifest_id=manifest_id,
            manifest_sha256=digest,
            dataset=dataset,
            schema_version=schema_version,
            created_at=created,
            partition_ids=tuple(partition.partition_id for partition in partitions),
            total_rows=cast(int, manifest_payload["total_rows"]),
            relative_path=str(relative),
        )

    def save_checkpoint(
        self,
        *,
        job_key: str,
        cursor: Mapping[str, object],
        completed: bool,
        updated_at: datetime,
    ) -> None:
        if not job_key.strip():
            raise ValueError("job_key is required")
        updated = _utc(updated_at, "updated_at")
        cursor_json = _canonical_bytes(dict(cursor)).decode("utf-8")
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT completed FROM checkpoints WHERE job_key=?",
                (job_key,),
            ).fetchone()
            if existing is not None and bool(existing["completed"]) and not completed:
                raise ValueError("completed checkpoint cannot be reopened")
            connection.execute(
                """
                INSERT INTO checkpoints(job_key, cursor_json, completed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(job_key) DO UPDATE SET
                    cursor_json=excluded.cursor_json,
                    completed=excluded.completed,
                    updated_at=excluded.updated_at
                """,
                (job_key, cursor_json, int(completed), updated.isoformat()),
            )

    def load_checkpoint(self, job_key: str) -> BackfillCheckpoint | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM checkpoints WHERE job_key=?",
                (job_key,),
            ).fetchone()
        if row is None:
            return None
        cursor = json.loads(str(row["cursor_json"]))
        if not isinstance(cursor, dict):
            raise RuntimeError("stored checkpoint cursor must be an object")
        return BackfillCheckpoint(
            job_key=job_key,
            cursor=cast(dict[str, object], cursor),
            completed=bool(row["completed"]),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def persist_partition_then_checkpoint(
        self,
        *,
        dataset: str,
        partition_key: str,
        observations: Sequence[HistoricalObservation],
        job_key: str,
        cursor: Mapping[str, object],
        completed: bool,
        updated_at: datetime,
    ) -> DurablePartition:
        partition = self.write_partition(
            dataset=dataset,
            partition_key=partition_key,
            observations=observations,
        )
        self.save_checkpoint(
            job_key=job_key,
            cursor=cursor,
            completed=completed,
            updated_at=updated_at,
        )
        return partition

    def load_observations(self, dataset: str) -> tuple[HistoricalObservation, ...]:
        dataset = _safe_segment(dataset, "dataset")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM observations
                WHERE dataset=?
                ORDER BY observed_at, record_id, provider, source_id, observation_id
                """,
                (dataset,),
            ).fetchall()
        observations = []
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            if not isinstance(payload, dict):
                raise RuntimeError("stored observation root must be an object")
            observations.append(_observation_from_payload(payload))
        return tuple(observations)

    def as_of(
        self,
        *,
        dataset: str,
        prediction_time: datetime,
        allow_reconstructed: bool = False,
    ) -> tuple[HistoricalObservation, ...]:
        return select_as_of(
            self.load_observations(dataset),
            prediction_time=prediction_time,
            allow_reconstructed=allow_reconstructed,
        )

    def raw_blob_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM raw_blobs").fetchone()
        return int(row[0])

    def fetch_receipt_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM fetch_receipts").fetchone()
        return int(row[0])

    def observation_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM observations").fetchone()
        return int(row[0])

    def quick_check(self) -> bool:
        with self._connection() as connection:
            row = connection.execute("PRAGMA quick_check").fetchone()
        return bool(row and row[0] == "ok")
